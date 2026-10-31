"""
Helmet lamp shell - procedural Blender model (height exactly 20 cm).

Run inside Blender (Scripting tab -> Run Script), or headless:
    blender -b -P build_helmet.py -- --out <folder> [--render]

Parts (collection "Helmet"):
    Helmet_Shell          orange translucent shell, 3 mm wall, open bottom
    Helmet_Trim_Seam      brass band that outlines the face plate
    Helmet_Trim_Rim       brass U-cap that runs round the bottom opening + chin
    Helmet_Stripe_Upper   black visor stripe
    Helmet_Stripe_Lower   black visor stripe
A "Studio" collection holds the camera, lights, wall and shelf for the renders;
delete it if you only want the helmet.

Axes: Z up, the face looks toward -Y (Blender's Front view looks at the face).
"""

import math
import os
import sys

import bpy  # noqa: I001  (bpy must load before bmesh when run as a module)
import bmesh
import numpy as np

# ----------------------------------------------------------------------------
# Shape parameters (metres). Everything is scaled to exactly 0.20 m at the end.
# ----------------------------------------------------------------------------
A = 0.069        # half width (X)
B_FRONT = 0.083  # half depth toward the face (-Y)
B_BACK = 0.079   # half depth toward the back (+Y)
C_TOP = 0.092    # dome height above the centre
C_BOT = 0.170    # lower extent (cut off at z=0 -> slight tuck-in at the rim)
ZC = 0.108       # centre height
P = 3.0          # horizontal squareness (2 = round, higher = boxier)
Q = 2.4          # vertical squareness

Y0 = 0.004       # where the face-plate seam meets the rim
K = 0.50         # chin slope: the face plate's lower edge rises toward the front
SHELL_T = 0.003  # wall thickness

SEAM_Z1 = 0.105  # seam runs vertically up to here...
SEAM_RY = 0.085  # ...then sweeps forward over the crown on this ellipse
SEAM_RZ = 0.105

# Visor stripes: bands parallel to the chin line (offsets measured in Z above it)
STRIPES = {
    "Helmet_Stripe_Lower": (0.0400, 0.0560),
    "Helmet_Stripe_Upper": (0.0720, 0.0880),
}
STRIPE_GAP = 0.012  # stripes stop this far in front of the seam

TARGET_HEIGHT = 0.200
SHELL_CUTS = 96
RES_PCT = int(os.environ.get("HELMET_RES_PCT", "100"))


# ----------------------------------------------------------------------------
# Implicit surface: F(x, y, z) = 1 on the shell (superellipsoid, split halves)
# ----------------------------------------------------------------------------
def F(x, y, z):
    x, y, z = np.asarray(x, float), np.asarray(y, float), np.asarray(z, float)
    b = np.where(y < 0, B_FRONT, B_BACK)
    zr = z - ZC
    c = np.where(zr > 0, C_TOP, C_BOT)
    return (np.abs(x / A) ** P + np.abs(y / b) ** P) ** (Q / P) + np.abs(zr / c) ** Q


def surface_normal(pts):
    e = 1e-6
    g = np.zeros_like(pts)
    for k in range(3):
        d = np.zeros(3)
        d[k] = e
        g[:, k] = (F(*(pts + d).T) - F(*(pts - d).T)) / (2 * e)
    return g


def project(pts, iters=4):
    """Pull points back onto F=1 along the gradient (Newton)."""
    pts = pts.copy()
    for _ in range(iters):
        g = surface_normal(pts)
        f = F(*pts.T) - 1.0
        pts -= (f / np.maximum((g * g).sum(1), 1e-12))[:, None] * g
    return pts


def unit(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def resample(pts, n, closed=False):
    src = np.vstack([pts, pts[:1]]) if closed else pts
    s = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(src, axis=0), axis=1))])
    t = np.linspace(0.0, s[-1], n + 1 if closed else n)
    out = np.stack([np.interp(t, s, src[:, k]) for k in range(3)], 1)
    return out[:-1] if closed else out


def tangents(pts, closed=False):
    if closed:
        return unit(np.roll(pts, -1, 0) - np.roll(pts, 1, 0))
    return unit(np.gradient(pts, axis=0))


def solve_on_ray(phi, zfun):
    """For each azimuth phi find the surface point on the ray r*(cos, sin) with z=zfun(r)."""
    lo = np.full_like(phi, 1e-4)
    hi = np.full_like(phi, 0.3)
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        inside = F(mid * np.cos(phi), mid * np.sin(phi), zfun(mid, phi)) < 1.0
        lo = np.where(inside, mid, lo)
        hi = np.where(inside, hi, mid)
    r = 0.5 * (lo + hi)
    return np.stack([r * np.cos(phi), r * np.sin(phi), zfun(r, phi)], 1)


# ----------------------------------------------------------------------------
# Mesh helpers
# ----------------------------------------------------------------------------
def make_object(name, verts, faces, collection):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([tuple(v) for v in verts], [], faces)
    mesh.validate()
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    return obj


def loft(name, sections, closed_loop, collection):
    """sections: (NS, M, 3), each section a closed ring of M points."""
    ns, m, _ = sections.shape
    faces = []
    for i in range(ns if closed_loop else ns - 1):
        i2 = (i + 1) % ns
        for j in range(m):
            j2 = (j + 1) % m
            faces.append((i * m + j, i * m + j2, i2 * m + j2, i2 * m + j))
    if not closed_loop:
        faces.append(tuple(range(m))[::-1])
        faces.append(tuple((ns - 1) * m + j for j in range(m)))
    return make_object(name, sections.reshape(-1, 3), faces, collection)


def rounded_rect(u0, u1, w0, w1, n=28, e=0.28):
    """Closed superellipse profile inside [u0,u1] x [w0,w1]."""
    t = np.linspace(0, 2 * math.pi, n, endpoint=False)
    c, s = np.cos(t), np.sin(t)
    u = np.sign(c) * np.abs(c) ** e
    w = np.sign(s) * np.abs(s) ** e
    return np.stack([(u0 + u1) / 2 + u * (u1 - u0) / 2, (w0 + w1) / 2 + w * (w1 - w0) / 2], 1)


def sweep(points, frame_u, frame_n, profile):
    """points (NS,3), frame vectors (NS,3), profile (M,2) -> sections (NS,M,3)."""
    return (points[:, None, :]
            + profile[None, :, 0:1] * frame_u[:, None, :]
            + profile[None, :, 1:2] * frame_n[:, None, :])


# ----------------------------------------------------------------------------
# Geometry builders
# ----------------------------------------------------------------------------
def build_shell(collection):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2.0)
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=SHELL_CUTS, use_grid_fill=True)
    for v in bm.verts:
        c = np.tan(np.array(v.co) * math.pi / 4.0)  # equal-angle cube -> sphere
        d = c / np.linalg.norm(c)
        r = float(F(d[0], d[1], d[2] + ZC)) ** (-1.0 / Q)
        v.co = (d[0] * r, d[1] * r, ZC + d[2] * r)

    for co, no in (((0, 0, 0), (0, 0, 1)), ((0, Y0, 0), (0, K, 1))):
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        n = np.array(no, float)
        bmesh.ops.bisect_plane(bm, geom=geom, plane_co=co, plane_no=tuple(n / np.linalg.norm(n)),
                               clear_inner=True)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=0.00025)
    bmesh.ops.dissolve_degenerate(bm, dist=1e-6, edges=bm.edges[:])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    mesh = bpy.data.meshes.new("Helmet_Shell")
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new("Helmet_Shell", mesh)
    collection.objects.link(obj)

    mod = obj.modifiers.new("Wall", "SOLIDIFY")
    mod.thickness = SHELL_T
    mod.offset = -1.0
    mod.use_even_offset = True
    mod.use_rim = True
    apply_modifiers(obj)
    return obj


def seam_curve_3d():
    """Face-plate outline: side profile (y,z) extruded along X, intersected with the shell."""
    t_end = SEAM_Z1 + math.pi / 2

    def yz(t):
        t = np.asarray(t, float)
        th = np.clip(t - SEAM_Z1, 0, None)
        y = np.where(t < SEAM_Z1, Y0, Y0 - SEAM_RY + SEAM_RY * np.cos(th))
        z = np.where(t < SEAM_Z1, t, SEAM_Z1 + SEAM_RZ * np.sin(th))
        return y, z

    def g(t):
        y, z = yz(t)
        b = np.where(y < 0, B_FRONT, B_BACK)
        zr = z - ZC
        c = np.where(zr > 0, C_TOP, C_BOT)
        h = np.clip(1 - np.abs(zr / c) ** Q, 0, None)
        return h ** (P / Q) - np.abs(y / b) ** P

    ts = np.linspace(0, t_end, 20000)
    i = int(np.argmax(g(ts) <= 0))
    lo, hi = ts[i - 1], ts[i]
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if g(mid) > 0 else (lo, mid)
    t_star = lo

    w = np.linspace(0, 1, 8000)
    t = t_star - t_star * (1 - w) ** P  # dense near the crown crossing
    y, z = yz(t)
    x = A * np.clip(g(t), 0, None) ** (1 / P)
    right = np.stack([x, y, z], 1)
    left = right[::-1].copy()
    left[:, 0] *= -1
    pts = np.vstack([right, left[1:]])
    return project(resample(pts, 1400))


def rim_curve_3d():
    phi = np.linspace(-math.pi, math.pi, 12000, endpoint=False)
    pts = solve_on_ray(phi, lambda r, ph: np.maximum(0.0, K * (Y0 - r * np.sin(ph))))
    return resample(pts, 1600, closed=True)


def build_seam_trim(collection):
    pts = seam_curve_3d()
    n = unit(surface_normal(pts))
    t = tangents(pts)
    u = unit(np.cross(n, t))
    prof = rounded_rect(-0.0025, 0.0025, -0.0006, 0.0015)
    return loft("Helmet_Trim_Seam", sweep(pts, u, n, prof), False, collection)


def build_rim_trim(collection):
    pts = rim_curve_3d()
    n = unit(surface_normal(pts))
    t = tangents(pts, closed=True)
    # "up the wall" direction: normal of the cut that made this part of the edge,
    # blended across the seam point so the band twists smoothly.
    chin = np.array([0.0, K, 1.0]) / math.hypot(K, 1.0)
    flat = np.array([0.0, 0.0, 1.0])
    s = np.clip((Y0 + 0.008 - pts[:, 1]) / 0.016, 0, 1)
    s = s * s * (3 - 2 * s)
    cut_n = unit((1 - s)[:, None] * flat + s[:, None] * chin)
    up = cut_n - (cut_n * n).sum(1, keepdims=True) * n - (cut_n * t).sum(1, keepdims=True) * t
    up = unit(up)
    prof = rounded_rect(-0.0010, 0.0042, -(SHELL_T + 0.0009), 0.0010)
    return loft("Helmet_Trim_Rim", sweep(pts, up, n, prof), True, collection)


def build_stripe(name, h0, h1, collection, nu=420, nv=10):
    rows = []
    for h in np.linspace(h0, h1, nv + 1):
        zf = (lambda hh: (lambda r, ph: hh + K * (Y0 - r * np.sin(ph))))(h)
        y_end = Y0 - STRIPE_GAP

        def phi_at(a, b, front_is_b):
            # the face (-Y) is at phi=-pi/2; find where the stripe reaches y_end
            for _ in range(60):
                m = 0.5 * (a + b)
                y = solve_on_ray(np.array([m]), zf)[0, 1]
                if (y < y_end) == front_is_b:
                    b = m
                else:
                    a = m
            return 0.5 * (a + b)

        pa = phi_at(-math.pi, -math.pi / 2, True)   # x < 0 side
        pb = phi_at(-math.pi / 2, 0.0, False)       # x > 0 side
        rows.append(solve_on_ray(np.linspace(pa, pb, nu), zf))
    grid = np.stack(rows, 1)  # (nu, nv+1, 3)
    n = unit(surface_normal(grid.reshape(-1, 3))).reshape(grid.shape)
    top = grid + n * 0.00055
    bot = grid - n * 0.00025
    sections = np.concatenate([top, bot[:, ::-1]], 1)
    return loft(name, sections, False, collection)


# ----------------------------------------------------------------------------
# Materials
# ----------------------------------------------------------------------------
def principled(name, **inputs):
    mat = bpy.data.materials.new(name)
    try:
        mat.use_nodes = True
    except Exception:
        pass
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    for key, val in inputs.items():
        if key == "method":
            bsdf.subsurface_method = val
        elif key in bsdf.inputs:
            bsdf.inputs[key].default_value = val
    mat.diffuse_color = tuple(list(inputs.get("Base Color", (0.8, 0.8, 0.8, 1)))[:3]) + (1.0,)
    return mat


def make_materials():
    return {
        "shell": principled(
            "Orange_Glass",
            **{"Base Color": (1.0, 0.24, 0.008, 1), "Roughness": 0.30,
               "Subsurface Weight": 1.0, "Subsurface Radius": (1.0, 0.35, 0.08),
               "Subsurface Scale": 0.008, "IOR": 1.5, "Coat Weight": 1.0,
               "Coat Roughness": 0.04, "method": "RANDOM_WALK"}),
        "brass": principled(
            "Brass",
            **{"Base Color": (0.86, 0.60, 0.26, 1), "Metallic": 1.0, "Roughness": 0.24}),
        "black": principled(
            "Black_Gloss",
            **{"Base Color": (0.010, 0.008, 0.007, 1), "Roughness": 0.30,
               "Coat Weight": 0.6, "Coat Roughness": 0.08}),
    }


# ----------------------------------------------------------------------------
# Scene helpers
# ----------------------------------------------------------------------------
def apply_modifiers(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    mesh = bpy.data.meshes.new_from_object(obj.evaluated_get(dg))
    old = obj.data
    obj.modifiers.clear()
    obj.data = mesh
    mesh.name = old.name
    bpy.data.meshes.remove(old)


def smooth_by_angle(obj, degrees):
    mesh = obj.data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    lim = math.radians(degrees)
    for f in bm.faces:
        f.smooth = True
    for e in bm.edges:
        e.smooth = not (len(e.link_faces) == 2 and e.calc_face_angle(0) > lim)
    bm.to_mesh(mesh)
    bm.free()


def new_collection(name):
    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)
    return col


def look_at(obj, target):
    from mathutils import Vector
    d = Vector(target) - obj.location
    obj.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def build_studio(col):
    mats = {
        "wall": principled("Wall", **{"Base Color": (0.30, 0.29, 0.27, 1), "Roughness": 0.9}),
        "shelf": principled("Shelf", **{"Base Color": (0.018, 0.018, 0.02, 1), "Roughness": 0.45}),
    }
    ang = math.radians(40)
    back = np.array([math.cos(ang), math.sin(ang), 0.0])  # away from the camera
    side = np.array([-math.sin(ang), math.cos(ang), 0.0])

    # shelf board, top at z=0
    sv, sf = [], []
    hw, d0, d1, th = 0.60, -0.16, 0.14, 0.022
    for i, (a, b, z) in enumerate([(sx, sy, sz) for sz in (0.0, -th)
                                   for sx, sy in ((-hw, d0), (hw, d0), (hw, d1), (-hw, d1))]):
        sv.append(tuple(side * a + back * b + np.array([0, 0, z])))
    sf = [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    shelf = make_object("Shelf", sv, sf, col)
    shelf.data.materials.append(mats["shelf"])

    wv = [tuple(side * a + back * 0.14 + np.array([0, 0, z])) for a, z in
          ((-2, -1.0), (2, -1.0), (2, 2.0), (-2, 2.0))]
    wall = make_object("Wall", wv, [(0, 1, 2, 3)], col)
    wall.data.materials.append(mats["wall"])

    def light(name, kind, loc, energy, color, size):
        data = bpy.data.lights.new(name, kind)
        data.energy = energy
        data.color = color
        if kind == "AREA":
            data.size = size
        else:
            data.shadow_soft_size = size
        ob = bpy.data.objects.new(name, data)
        ob.location = loc
        col.objects.link(ob)
        return ob

    light("Bulb_Inside", "POINT", (0, -0.005, 0.085), 0.45, (1.0, 0.72, 0.42), 0.025)
    key = light("Key_Soft", "AREA", (-0.55, -0.35, 0.75), 22.0, (1.0, 0.93, 0.85), 0.8)
    look_at(key, (0, 0, 0.1))
    rim = light("Window_Fill", "AREA", (0.6, -0.65, 0.35), 6.0, (0.85, 0.9, 1.0), 0.6)
    look_at(rim, (0, 0, 0.1))

    world = bpy.data.worlds.new("Room")
    try:
        world.use_nodes = True
    except Exception:
        pass
    bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs["Color"].default_value = (0.22, 0.21, 0.20, 1)
    bg.inputs["Strength"].default_value = 0.25
    bpy.context.scene.world = world

    cam_data = bpy.data.cameras.new("Camera")
    cam_data.lens = 55
    cam = bpy.data.objects.new("Camera", cam_data)
    col.objects.link(cam)
    bpy.context.scene.camera = cam
    return cam


CAMERA_VIEWS = {
    "hero": ((-0.40, -0.47, 0.25), (0.0, -0.01, 0.092), 55),
    "front": ((0.0, -0.78, 0.13), (0.0, 0.0, 0.098), 60),
    "side": ((-0.78, -0.02, 0.13), (0.0, -0.01, 0.098), 60),
    "back": ((0.42, 0.50, 0.30), (0.0, 0.0, 0.092), 55),
}


# ----------------------------------------------------------------------------
def main(out_dir, render=False, samples=128):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.length_unit = "CENTIMETERS"

    col = new_collection("Helmet")
    mats = make_materials()

    shell = build_shell(col)
    shell.data.materials.append(mats["shell"])
    seam = build_seam_trim(col)
    rim = build_rim_trim(col)
    for o in (seam, rim):
        o.data.materials.append(mats["brass"])
    stripes = []
    for name, (h0, h1) in STRIPES.items():
        s = build_stripe(name, h0, h1, col)
        s.data.materials.append(mats["black"])
        stripes.append(s)

    parts = [shell, seam, rim] + stripes

    # exact 20 cm overall height, resting on z = 0
    allv = np.concatenate([np.array([v.co[:] for v in o.data.vertices]) for o in parts])
    zmin, zmax = allv[:, 2].min(), allv[:, 2].max()
    s = TARGET_HEIGHT / (zmax - zmin)
    for o in parts:
        co = np.array([v.co[:] for v in o.data.vertices])
        co[:, 2] -= zmin
        co *= s
        o.data.vertices.foreach_set("co", co.ravel())
        o.data.update()
    for o in parts:
        smooth_by_angle(o, 50 if o is not shell else 60)

    root = bpy.data.objects.new("Helmet_Lamp", None)
    root.empty_display_type = "PLAIN_AXES"
    root.empty_display_size = 0.05
    col.objects.link(root)
    for o in parts:
        o.parent = root

    allv = np.concatenate([np.array([v.co[:] for v in o.data.vertices]) for o in parts])
    dims = allv.max(0) - allv.min(0)
    print("HELMET DIMENSIONS (cm): W=%.2f D=%.2f H=%.2f" % tuple(dims * 100))
    print("FACES:", {o.name: len(o.data.polygons) for o in parts})

    studio = new_collection("Studio")
    cam = build_studio(studio)

    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 10
    scene.render.resolution_x = 1000
    scene.render.resolution_y = 1250
    scene.render.resolution_percentage = RES_PCT
    scene.render.film_transparent = False
    try:
        scene.view_settings.look = "AgX - Punchy"
    except Exception:
        pass

    os.makedirs(out_dir, exist_ok=True)
    loc, tgt, lens = CAMERA_VIEWS["hero"]
    cam.location = loc
    look_at(cam, tgt)
    cam.data.lens = lens
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out_dir, "helmet_lamp.blend"), compress=True)

    # exports: helmet only
    for o in bpy.context.view_layer.objects:
        o.select_set(o in parts)
    bpy.ops.wm.stl_export(filepath=os.path.join(out_dir, "helmet_lamp_mm.stl"),
                          export_selected_objects=True, global_scale=1000.0)
    bpy.ops.export_scene.gltf(filepath=os.path.join(out_dir, "helmet_lamp.glb"),
                              export_format="GLB", use_selection=True)

    if render:
        rdir = os.path.join(out_dir, "renders")
        os.makedirs(rdir, exist_ok=True)
        for view in render:
            loc, tgt, lens = CAMERA_VIEWS[view]
            cam.location = loc
            look_at(cam, tgt)
            cam.data.lens = lens
            scene.render.filepath = os.path.join(rdir, view + ".png")
            bpy.ops.render.render(write_still=True)
            print("rendered", view)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else bpy.path.abspath("//")
    views, samples = [], 128
    i = 0
    while i < len(argv):
        if argv[i] == "--out":
            out = argv[i + 1]
            i += 1
        elif argv[i] == "--render":
            views = argv[i + 1].split(",")
            i += 1
        elif argv[i] == "--samples":
            samples = int(argv[i + 1])
            i += 1
        i += 1
    main(out, views, samples)
