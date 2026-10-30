"""
IgG Antibody (Immunoglobulin G) - procedural high-detail model for Blender 4.x / 5.x

How to use inside Blender:
    1. Open the "Scripting" workspace.
    2. Open this file (or paste it) and press "Run Script".
    3. The scene is cleared and rebuilt: antibody + black pedestal + grey studio + lights + camera.
    4. Press F12 to render (Cycles).

Headless:
    blender -b -P igg_antibody.py -- --render out.png --save out.blend

Every protein domain is built from a cloud of metaballs (gives the lumpy
"space-filling" molecular surface), converted to a mesh, voxel-remeshed for
clean topology, smoothed and given a fine noise displacement.
"""

import math
import random
import sys

import bpy
import bmesh  # noqa: E402  (must come after bpy when using the bpy pip module)
from mathutils import Vector, Matrix, Quaternion

# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------
QUALITY = 1.0            # 1.0 = high. Lower (e.g. 0.6) for a faster, lighter build.
VOXEL = 0.018 / QUALITY  # remesh voxel size (smaller = more polygons / detail)
MB_RES = 0.03 / QUALITY  # metaball polygonisation resolution
SEED = 7
BASE_TOP = 0.45         # height of the pedestal
MIN_ROD = 0.0           # minimum tube radius (raised by the 3D-print script)

COLORS = {               # sRGB hex, matched to the reference picture
    "heavy":  "#2F86E8",  # blue  - heavy chain
    "light":  "#F0708C",  # pink  - light chain
    "var":    "#8C3FD2",  # purple - variable region / antigen-binding site
    "ss":     "#FFCC00",  # yellow - disulfide bonds
    "linker": "#4DB6EA",  # light blue thin hinge links
    "base":   "#0B0B0D",  # black pedestal
    "studio": "#8A8A8C",  # grey backdrop
}


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def hex_to_linear(h):
    h = h.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255.0
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return (*out, 1.0)


def clear_scene():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.metaballs, bpy.data.curves,
                 bpy.data.materials, bpy.data.lights, bpy.data.cameras,
                 bpy.data.textures):
        for block in list(coll):
            coll.remove(block)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)


def get_collection(name):
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(coll)
    return coll


def set_input(node, names, value):
    """Set the first existing socket from a list of names (API differs between versions)."""
    for n in names:
        if n in node.inputs:
            node.inputs[n].default_value = value
            return


def make_plastic(name, hex_color, roughness=0.32, coat=0.35, specular=0.5):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    col = hex_to_linear(hex_color)
    bsdf.inputs["Base Color"].default_value = col
    bsdf.inputs["Roughness"].default_value = roughness
    set_input(bsdf, ["Specular IOR Level", "Specular"], specular)
    set_input(bsdf, ["Coat Weight", "Clearcoat"], coat)
    set_input(bsdf, ["Coat Roughness", "Clearcoat Roughness"], 0.08)
    # a touch of subsurface makes the plastic look like a printed model
    set_input(bsdf, ["Subsurface Weight", "Subsurface"], 0.06)
    set_input(bsdf, ["Subsurface Radius"], Vector((0.05, 0.05, 0.05)))
    mat.diffuse_color = col  # viewport solid colour
    return mat


def bake_modifiers(obj):
    """Apply all modifiers without bpy.ops (works headless and in the UI)."""
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    new_mesh = bpy.data.meshes.new_from_object(obj.evaluated_get(dg))
    old = obj.data
    obj.modifiers.clear()
    obj.data = new_mesh
    if old.users == 0:
        bpy.data.meshes.remove(old)


def shade_smooth(mesh):
    mesh.polygons.foreach_set("use_smooth", [True] * len(mesh.polygons))
    mesh.update()


_noise_tex = None


def noise_texture():
    global _noise_tex
    if _noise_tex is None:
        _noise_tex = bpy.data.textures.new("MolecularNoise", type="CLOUDS")
        _noise_tex.noise_scale = 0.06
        _noise_tex.noise_depth = 2
    return _noise_tex


def frame_from_axis(axis, up_hint=Vector((0, 1, 0))):
    """Orthonormal frame (u, v, w) with w = axis."""
    w = axis.normalized()
    if abs(w.dot(up_hint)) > 0.95:
        up_hint = Vector((1, 0, 0))
    u = up_hint.cross(w).normalized()
    v = w.cross(u).normalized()
    return u, v, w


def metaball_to_mesh(mb_obj, name, mat, coll, displace=0.014, smooth_iter=2):
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    mesh = bpy.data.meshes.new_from_object(mb_obj.evaluated_get(dg))
    mesh.name = name
    mb_data = mb_obj.data
    bpy.data.objects.remove(mb_obj, do_unlink=True)
    bpy.data.metaballs.remove(mb_data)

    obj = bpy.data.objects.new(name, mesh)
    coll.objects.link(obj)

    rem = obj.modifiers.new("Remesh", "REMESH")
    rem.mode = "VOXEL"
    rem.voxel_size = VOXEL
    rem.adaptivity = 0.0
    sm = obj.modifiers.new("Smooth", "CORRECTIVE_SMOOTH")
    sm.iterations = smooth_iter
    sm.factor = 0.5
    sm.use_only_smooth = True
    if displace > 0:
        d = obj.modifiers.new("MicroDetail", "DISPLACE")
        d.texture = noise_texture()
        d.texture_coords = "GLOBAL"
        d.strength = displace
        d.mid_level = 0.5
    bake_modifiers(obj)
    shade_smooth(obj.data)
    obj.data.materials.append(mat)
    return obj


def new_metaball(name, coll, threshold=0.6):
    mb = bpy.data.metaballs.new(name)
    mb.resolution = MB_RES
    mb.render_resolution = MB_RES
    mb.threshold = threshold
    obj = bpy.data.objects.new(name, mb)
    coll.objects.link(obj)
    return obj


def protein_domain(name, center, axis, radii, mat, coll, rng,
                   blob_r=(0.08, 0.125), density=1.0, bulge=0.0):
    """
    Lumpy protein domain: metaball lobes in an ellipsoid, covered with atom spheres.
    radii = (r_u, r_v, half_length_along_axis)
    """
    obj = new_metaball(name.replace(".", "_"), coll)
    mb = obj.data
    u, v, w = frame_from_axis(Vector(axis))
    c = Vector(center)
    ru, rv, rw = radii

    def local(x, y, z):
        # gentle sinusoidal bulge so the domain is not a perfect ellipsoid
        b = 1.0 + bulge * math.sin(3.1 * z + 1.7)
        return c + u * (x * ru * b) + v * (y * rv * b) + w * (z * rw)

    def rand_in_sphere():
        while True:
            p = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1)))
            if p.length <= 1.0:
                return p

    # 1) large sub-lobes -> the "cluster of bumps" silhouette of a folded protein
    volume = 4.0 / 3.0 * math.pi * ru * rv * rw
    n_lobes = max(5, int(volume / 0.035))
    lobes = []
    for _ in range(n_lobes):
        p = rand_in_sphere()
        p = p.normalized() * (0.45 + 0.4 * rng.random())
        lobes.append(p)
        el = mb.elements.new(type="BALL")
        el.co = local(*p)
        el.radius = rng.uniform(0.26, 0.34) * min(ru, rv) / 0.3
        el.stiffness = 2.0

    # 2) solid core so the domain never has holes
    core = mb.elements.new(type="ELLIPSOID")
    core.co = c
    core.radius = 1.0
    core.size_x = ru * 1.45
    core.size_y = rv * 1.45
    core.size_z = rw * 1.45
    core.rotation = Matrix((u, v, w)).transposed().to_quaternion()
    core.stiffness = 2.0

    # 3) polygonise the smooth body, then cover it with "atoms" (real spheres)
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    body = bpy.data.meshes.new_from_object(obj.evaluated_get(dg))
    mb_data = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.metaballs.remove(mb_data)
    add_atoms(body, rng, blob_r, density)
    return mesh_to_domain(body, name, mat, coll)


def add_atoms(mesh, rng, r_range, density=1.0):
    """Scatter half-buried spheres over the surface -> space-filling molecular look."""
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.normal_update()
    verts = list(bm.verts)
    rng.shuffle(verts)
    placed = []                # (co, r)
    grid = {}
    cell = r_range[1] * 2.0

    def key(p):
        return (int(math.floor(p.x / cell)), int(math.floor(p.y / cell)), int(math.floor(p.z / cell)))

    spacing = 1.25 / max(density, 0.1) ** 0.5
    for vtx in verts:
        r = rng.uniform(*r_range)
        p = vtx.co - vtx.normal * r * rng.uniform(0.25, 0.55)
        k = key(p)
        ok = True
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for (q, rq) in grid.get((k[0] + dx, k[1] + dy, k[2] + dz), ()):
                        if (p - q).length < (r + rq) * 0.5 * spacing:
                            ok = False
                            break
                    if not ok:
                        break
                if not ok:
                    break
            if not ok:
                break
        if not ok:
            continue
        grid.setdefault(k, []).append((p, r))
        placed.append((p, r))
    for p, r in placed:
        bmesh.ops.create_icosphere(bm, subdivisions=2, radius=r,
                                   matrix=Matrix.Translation(p), calc_uvs=False)
    bm.to_mesh(mesh)
    bm.free()
    return len(placed)


def mesh_to_domain(mesh, name, mat, coll):
    mesh.name = name
    obj = bpy.data.objects.new(name, mesh)
    coll.objects.link(obj)
    rem = obj.modifiers.new("Remesh", "REMESH")       # boolean-union of all atoms
    rem.mode = "VOXEL"
    rem.voxel_size = VOXEL
    rem.adaptivity = 0.0
    d = obj.modifiers.new("MicroDetail", "DISPLACE")
    d.texture = noise_texture()
    d.texture_coords = "GLOBAL"
    d.strength = 0.006
    bake_modifiers(obj)
    shade_smooth(obj.data)
    obj.data.materials.append(mat)
    return obj


def rod_network(name, segments, radius, mat, coll, joint_scale=1.15):
    """Smooth tubes (metaball capsules) through a list of (p0, p1) segments."""
    obj = new_metaball(name.replace(".", "_"), coll, threshold=0.6)
    mb = obj.data
    mb.resolution = min(MB_RES, radius * 0.35)
    # visible radius of a capsule of radius R and stiffness 2 at threshold .6 ~ 0.58R
    radius = max(radius, MIN_ROD)
    R = radius / 0.58
    joints = set()
    for p0, p1 in segments:
        p0, p1 = Vector(p0), Vector(p1)
        d = p1 - p0
        L = d.length
        el = mb.elements.new(type="CAPSULE")
        el.co = (p0 + p1) * 0.5
        el.radius = R
        el.size_x = max(L * 0.5, 1e-4)
        el.stiffness = 2.0
        el.rotation = Vector((1, 0, 0)).rotation_difference(d.normalized())
        joints.add(tuple(round(c, 4) for c in p0))
        joints.add(tuple(round(c, 4) for c in p1))
    for j in joints:   # round knuckles at every joint
        el = mb.elements.new(type="BALL")
        el.co = j
        el.radius = R * joint_scale
        el.stiffness = 1.6
    return metaball_to_mesh(obj, name, mat, coll, displace=0.0, smooth_iter=3)


def torus_ring(name, center, axis, major, minor, mat, coll):
    segs = []
    u, v, w = frame_from_axis(Vector(axis))
    n = 14
    c = Vector(center)
    pts = [c + (u * math.cos(2 * math.pi * i / n) + v * math.sin(2 * math.pi * i / n)) * major
           for i in range(n)]
    for i in range(n):
        segs.append((pts[i], pts[(i + 1) % n]))
    return rod_network(name, segs, minor, mat, coll, joint_scale=1.0)


# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------
def build():
    clear_scene()
    rng = random.Random(SEED)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"

    col_ab = get_collection("IgG_Antibody")
    col_base = get_collection("Pedestal")
    col_studio = get_collection("Studio")

    M = {k: make_plastic(f"MAT_{k}", v) for k, v in COLORS.items() if k not in ("base", "studio")}
    M["base"] = make_plastic("MAT_base", COLORS["base"], roughness=0.22, coat=0.6)
    M["studio"] = make_plastic("MAT_studio", COLORS["studio"], roughness=0.85, coat=0.0, specular=0.3)

    parts = []

    # ---------------- Fc region: two columns of 2 domains (CH2, CH3) -------------
    fc_x = 0.5
    for side, sx in (("L", -1), ("R", 1)):
        x = sx * fc_x
        tilt = Vector((sx * 0.03, 0.0, 1.0))
        parts.append(protein_domain(f"Fc_CH3_{side}", (x, 0.0, BASE_TOP + 0.62), tilt,
                                    (0.31, 0.32, 0.62), M["heavy"], col_ab, rng, bulge=0.06))
        parts.append(protein_domain(f"Fc_CH2_{side}", (x + sx * 0.02, 0.02, BASE_TOP + 1.86), tilt,
                                    (0.30, 0.31, 0.62), M["heavy"], col_ab, rng, bulge=0.06))

    # yellow inter-chain bridges between the Fc columns
    bridges = []
    for z in (BASE_TOP + 0.55, BASE_TOP + 1.25, BASE_TOP + 1.95):
        bridges.append(((-0.28, 0.0, z), (0.28, 0.0, z)))
    parts.append(rod_network("Fc_Disulfide", bridges, 0.06, M["ss"], col_ab))

    # ---------------- Hinge: yellow ladder + light-blue links -------------------
    hz0, hz1 = BASE_TOP + 2.55, BASE_TOP + 3.30
    hx = 0.24
    hmid = (hz0 + hz1) * 0.5
    ladder = [
        ((-hx, 0, hz0), (-hx, 0, hz1)),
        ((hx, 0, hz0), (hx, 0, hz1)),
        ((-hx, 0, hz0), (hx, 0, hz0)),
        ((-hx, 0, hmid), (hx, 0, hmid)),
        ((-hx, 0, hz1), (hx, 0, hz1)),
    ]
    parts.append(rod_network("Hinge_Disulfide", ladder, 0.065, M["ss"], col_ab))

    # ---------------- Fab arms --------------------------------------------------
    arm_angle = math.radians(46)          # from vertical
    links = []
    for side, sx in (("L", -1), ("R", 1)):
        d = Vector((sx * math.sin(arm_angle), 0.0, math.cos(arm_angle)))     # along arm
        n_out = Vector((sx * math.cos(arm_angle), 0.0, -math.sin(arm_angle)))  # outer / lower side
        root = Vector((sx * 0.62, 0.0, BASE_TOP + 3.38))
        off = 0.29
        inner = root - n_out * off      # heavy chain strand (upper side)
        outer = root + n_out * off      # light chain strand (lower side)

        def at(base, t, lift=0.0, y=0.0):
            return base + d * t + n_out * lift + Vector((0, y, 0))

        # heavy chain: CH1 + VH (blue)
        parts.append(protein_domain(f"Fab_{side}_CH1", at(inner, 0.62, y=0.02), d,
                                    (0.30, 0.31, 0.66), M["heavy"], col_ab, rng, bulge=0.08))
        parts.append(protein_domain(f"Fab_{side}_VH", at(inner, 1.86, y=-0.02), d,
                                    (0.30, 0.31, 0.64), M["heavy"], col_ab, rng, bulge=0.08))
        # light chain: CL (blue, next to hinge) + VL (pink)
        parts.append(protein_domain(f"Fab_{side}_CL", at(outer, 0.36, lift=0.03), d,
                                    (0.29, 0.30, 0.42), M["heavy"], col_ab, rng, bulge=0.05))
        parts.append(protein_domain(f"Fab_{side}_VL", at(outer, 1.45, lift=0.02), d,
                                    (0.28, 0.29, 0.80), M["light"], col_ab, rng, bulge=0.07))
        # antigen-binding site (purple cap) on the tip
        parts.append(protein_domain(f"Fab_{side}_Paratope", at(outer, 2.66, lift=-0.06), d,
                                    (0.35, 0.34, 0.46), M["var"], col_ab, rng,
                                    blob_r=(0.075, 0.125), density=1.0, bulge=0.1))

        # yellow ring + small bridge at the arm root (inter-chain S-S)
        parts.append(torus_ring(f"Fab_{side}_Ring", root + d * 0.02 - n_out * 0.05, d,
                                0.17, 0.05, M["ss"], col_ab))
        parts.append(rod_network(f"Fab_{side}_HL_Disulfide",
                                 [(at(inner, 0.10, lift=0.10), at(outer, 0.10, lift=-0.10))],
                                 0.06, M["ss"], col_ab))

        # light-blue hinge links: Fc top -> ladder -> arm root
        top_fc = Vector((sx * fc_x * 0.75, 0.0, BASE_TOP + 2.45))
        links += [
            (top_fc, (sx * hx, 0.0, hz0)),
            ((sx * hx, 0.0, hz1), root - n_out * 0.05),
            ((sx * hx * 0.2, 0.0, hz1 + 0.02), root - n_out * 0.22 + d * 0.05),
        ]
    parts.append(rod_network("Hinge_Links", links, 0.045, M["linker"], col_ab))

    # ---------------- Pedestal --------------------------------------------------
    bpy.ops.mesh.primitive_cylinder_add(vertices=128, radius=1.85, depth=BASE_TOP,
                                        location=(0, 0, BASE_TOP / 2))
    base = bpy.context.active_object
    base.name = "Pedestal"
    for c in base.users_collection:
        c.objects.unlink(base)
    col_base.objects.link(base)
    # taper the top a little
    for vtx in base.data.vertices:
        if vtx.co.z > 0:
            vtx.co.x *= 0.95
            vtx.co.y *= 0.95
    bev = base.modifiers.new("Bevel", "BEVEL")
    bev.width = 0.06
    bev.segments = 6
    bev.limit_method = "ANGLE"
    bake_modifiers(base)
    shade_smooth(base.data)
    base.data.materials.append(M["base"])
    # weighted normals keep the flat top crisp
    try:
        base.modifiers.new("WeightedNormal", "WEIGHTED_NORMAL").keep_sharp = True
    except Exception:
        pass

    # ---------------- Parent everything to one empty ----------------------------
    root_empty = bpy.data.objects.new("IgG_Root", None)
    root_empty.empty_display_type = "PLAIN_AXES"
    col_ab.objects.link(root_empty)
    for p in parts:
        p.parent = root_empty

    build_studio(col_studio, M["studio"])
    setup_render()
    return parts


def build_studio(coll, mat):
    # seamless curved backdrop (cyclorama)
    import bmesh
    bm = bmesh.new()
    width, depth, height, rad = 30.0, 14.0, 16.0, 4.0
    prof = [(-depth + (depth + 4.0) * i / 12, 0.0) for i in range(12)]   # floor
    for i in range(1, 17):                     # curve
        a = (math.pi / 2) * i / 16
        prof.append((4.0 + math.sin(a) * rad, rad - math.cos(a) * rad))
    for i in range(1, 8):                      # wall
        prof.append((4.0 + rad, rad + (height - rad) * i / 7))
    rows = []
    for x in (-width / 2, width / 2):
        rows.append([bm.verts.new((x, y, z)) for (y, z) in prof])
    for i in range(len(prof) - 1):
        bm.faces.new((rows[0][i], rows[1][i], rows[1][i + 1], rows[0][i + 1]))
    me = bpy.data.meshes.new("Backdrop")
    bm.to_mesh(me)
    bm.free()
    shade_smooth(me)
    me.materials.append(mat)
    ob = bpy.data.objects.new("Backdrop", me)
    coll.objects.link(ob)

    # lights
    def area(name, loc, target, power, size, color=(1, 1, 1)):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy = power
        ld.size = size
        ld.color = color
        lo = bpy.data.objects.new(name, ld)
        lo.location = loc
        direction = Vector(target) - Vector(loc)
        lo.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
        coll.objects.link(lo)
        return lo

    area("Key", (-6.0, -7.0, 8.0), (0, 0, 3.0), 1500, 5.0, (1.0, 0.97, 0.93))
    area("Fill", (7.0, -6.0, 4.0), (0, 0, 3.0), 600, 6.0, (0.93, 0.96, 1.0))
    area("Rim", (0.5, 6.0, 9.0), (0, 0, 3.5), 900, 4.0)
    area("Top", (0.0, -1.0, 12.0), (0, 0, 2.0), 500, 6.0)

    # camera
    cd = bpy.data.cameras.new("Camera")
    cd.lens = 70
    cam = bpy.data.objects.new("Camera", cd)
    cam.location = (0.0, -17.0, 6.2)
    target = Vector((0.0, 0.0, 3.25))
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    coll.objects.link(cam)
    bpy.context.scene.camera = cam

    world = bpy.context.scene.world or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.32, 0.32, 0.33, 1)
    bg.inputs["Strength"].default_value = 0.6


def setup_render(samples=128):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.render.resolution_x = 1600
    sc.render.resolution_y = 1700
    sc.render.resolution_percentage = 100
    try:
        sc.view_settings.view_transform = "AgX"
        sc.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        sc.view_settings.view_transform = "Filmic"


# --------------------------------------------------------------------------
if __name__ == "__main__":
    parts = build()
    tris = sum(len(p.data.polygons) for p in parts)
    print(f"IgG antibody built: {len(parts)} parts, {tris:,} faces")

    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if "--save" in argv:
        bpy.ops.wm.save_as_mainfile(filepath=bpy.path.abspath(argv[argv.index("--save") + 1]),
                                    compress=True)
    if "--render" in argv:
        sc = bpy.context.scene
        if "--preview" in argv:
            sc.cycles.samples = 48
            sc.render.resolution_percentage = 50
        sc.render.filepath = argv[argv.index("--render") + 1]
        bpy.ops.render.render(write_still=True)
