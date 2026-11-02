"""
IgG Antibody - 3D-print version in 4 parts (Blender 4.2+ / 5.x)

Builds the model with igg_antibody.py, merges it into one watertight solid,
scales it to millimetres and splits it into printable parts joined by pins:

    Part 1  Base       : black pedestal                          (2 pins up)
    Part 2  Stem       : Fc region + hinge (yellow ladder) + the light-blue hinge
                         links                                   (2 holes below)
    Part 3  Arm left   : left Fab arm  (blue/pink/purple + yellow ring)
    Part 4  Arm right  : right Fab arm

The hinge links run parallel to each arm, so they are the arm's pins: the arm
has matching straight sockets and slides onto them in one straight move
(checked by a slide-off test while building).

Output (next to this script, in print/):
    IgG_part*.stl         (mm, single colour)
    IgG_part*.obj + .mtl  (same parts with colours, for multi-colour slicers)
    IgG_print_parts.blend / IgG_print_parts_preview.png (with --render)

Headless:
    blender -b -P igg_antibody_print.py -- --height 180 --render
"""

import math
import os
import sys

import bpy
import bmesh  # noqa: E402  (must come after bpy when using the bpy pip module)
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import igg_antibody as igg  # noqa: E402

# --------------------------------------------------------------------------
# Print settings (millimetres)
# --------------------------------------------------------------------------
PRINT_HEIGHT_MM = 180.0   # total height of the assembled model
VOXEL_MM = 0.4            # surface resolution of the printed solid
MAX_TRIS_TOTAL = 560_000  # whole antibody; the rest is decimated away
MIN_ROD_MM = 1.8          # thinnest tube radius (3.6 mm diameter; the hinge links are the arm pins)
PEG_RADIUS_MM = 2.5
PEG_LENGTH_MM = 6.0
CLEARANCE_MM = 0.2        # radial play in the holes
PIN_SEPARATION_MM = 9.0   # minimum distance between two pins of one joint
FOOT_RADIUS_MM = 4.5           # hidden post under each Fc column, carries the base pins
SOCKET_CLEARANCE_MM = 0.25     # play around the hinge links inside the arm sockets
SPINE_RADIUS_MM = 3.5          # hidden core joining CH3 and CH2 of each Fc column
OUT_DIR = os.path.join(HERE, "print")


# --------------------------------------------------------------------------
# Mesh helpers
# --------------------------------------------------------------------------
def link(obj, coll=None):
    (coll or bpy.context.scene.collection).objects.link(obj)
    return obj


def combine(name, objs):
    """Join copies of objs into one mesh object (world space)."""
    bm = bmesh.new()
    for o in objs:
        me = o.data.copy()
        me.transform(o.matrix_world)
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return link(bpy.data.objects.new(name, me))


def voxel_union(obj, voxel):
    m = obj.modifiers.new("Remesh", "REMESH")
    m.mode = "VOXEL"
    m.voxel_size = voxel
    m.adaptivity = 0.0
    igg.bake_modifiers(obj)


def decimate(obj, max_tris):
    tris = sum(len(p.vertices) - 2 for p in obj.data.polygons)
    if tris <= max_tris:
        return
    m = obj.modifiers.new("Decimate", "DECIMATE")
    m.decimate_type = "COLLAPSE"
    m.ratio = max_tris / tris
    m.use_collapse_triangulate = True
    igg.bake_modifiers(obj)


def displace(obj, dist):
    """Grow (or shrink) obj along its normals."""
    m = obj.modifiers.new("Offset", "DISPLACE")
    m.direction = "NORMAL"
    m.mid_level = 0.0
    m.strength = dist
    igg.bake_modifiers(obj)


def boolean(obj, cutter, op):
    m = obj.modifiers.new("Bool", "BOOLEAN")
    m.operation = op
    m.solver = "EXACT"
    m.object = cutter
    igg.bake_modifiers(obj)


def box(name, zmin, zmax, half=1e4):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= 2 * half
        v.co.y *= 2 * half
        v.co.z = zmin if v.co.z < 0 else zmax
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return link(bpy.data.objects.new(name, me))


def cylinders(name, centers, radius, z0, z1, chamfer=0.0, segs=48):
    """One mesh holding a vertical cylinder per centre (optional chamfer on top)."""
    bm = bmesh.new()
    for c in centers:
        ring0, ring1, ring2 = [], [], []
        for i in range(segs):
            a = 2 * math.pi * i / segs
            dx, dy = math.cos(a), math.sin(a)
            ring0.append(bm.verts.new((c.x + dx * radius, c.y + dy * radius, z0)))
            ring1.append(bm.verts.new((c.x + dx * radius, c.y + dy * radius, z1 - chamfer)))
            if chamfer > 0:
                r2 = radius - chamfer
                ring2.append(bm.verts.new((c.x + dx * r2, c.y + dy * r2, z1)))
        rings = [ring0, ring1] + ([ring2] if chamfer > 0 else [])
        for ra, rb in zip(rings, rings[1:]):
            for i in range(segs):
                j = (i + 1) % segs
                bm.faces.new((ra[i], ra[j], rb[j], rb[i]))
        bm.faces.new(list(reversed(ring0)))
        bm.faces.new(rings[-1])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return link(bpy.data.objects.new(name, me))


def tube(name, p0, p1, radius, segs=48):
    """Closed cylinder between two points."""
    d = p1 - p0
    rot = Vector((0, 0, 1)).rotation_difference(d.normalized()).to_matrix().to_4x4()
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segs,
                          radius1=radius, radius2=radius, depth=d.length,
                          matrix=Matrix.Translation((p0 + p1) * 0.5) @ rot)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return link(bpy.data.objects.new(name, me))


def islands(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    seen, count = set(), 0
    for v in bm.verts:
        if v.index in seen:
            continue
        count += 1
        stack = [v]
        seen.add(v.index)
        while stack:
            cur = stack.pop()
            for e in cur.link_edges:
                o = e.other_vert(cur)
                if o.index not in seen:
                    seen.add(o.index)
                    stack.append(o)
    bm.free()
    return count


def check_solid(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    non_manifold = sum(1 for e in bm.edges if not e.is_manifold)
    volume = bm.calc_volume(signed=False)
    tris = sum(len(f.verts) - 2 for f in bm.faces)
    bm.free()
    return non_manifold, volume, tris


def section(obj, co, no):
    """Cross-section islands of obj on a plane -> [(centre, inscribed radius)]."""
    co, no = Vector(co), Vector(no).normalized()
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    res = bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
                                 plane_co=co, plane_no=no)
    cut_edges = [e for e in res["geom_cut"] if isinstance(e, bmesh.types.BMEdge)]
    parent = {}

    def find(a):
        while parent.setdefault(a, a) != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for e in cut_edges:
        a, b = (v.index for v in e.verts)
        parent[find(a)] = find(b)
    bm.verts.ensure_lookup_table()
    groups = {}
    for i in parent:
        groups.setdefault(find(i), []).append(bm.verts[i].co.copy())
    out = []
    for pts in groups.values():
        if len(pts) < 8:
            continue
        c = sum(pts, Vector()) / len(pts)
        c -= no * (c - co).dot(no)          # back onto the plane
        r_in = min((p - c).length for p in pts)
        out.append((c, r_in))
    bm.free()
    return sorted(out, key=lambda t: -t[1])


def pin_points(obj, co, no, count=2, r_min=0.0, sep=0.0, step=0.5):
    """
    Up to `count` points on the cross-section of obj with the plane (co, no) that lie
    deepest inside the material -> [(point, distance to the section's edge)].
    Points are at least `sep` apart and at least `r_min` from the edge.
    """
    from mathutils.kdtree import KDTree
    co, no = Vector(co), Vector(no).normalized()
    u = no.orthogonal().normalized()
    v = no.cross(u)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    res = bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
                                 plane_co=co, plane_no=no)
    edges = [e for e in res["geom_cut"] if isinstance(e, bmesh.types.BMEdge)]
    segs = [tuple(((x.co - co).dot(u), (x.co - co).dot(v)) for x in e.verts) for e in edges]
    bm.free()
    if not segs:
        return []
    pts = {p for sgm in segs for p in sgm}
    kd = KDTree(len(pts))
    for i, (a, b) in enumerate(pts):
        kd.insert((a, b, 0.0), i)
    kd.balance()
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]

    def inside(x, y):                     # even-odd rule, edge order not needed
        n = 0
        for (x1, y1), (x2, y2) in segs:
            if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                n += 1
        return n % 2 == 1

    cands = []
    y = min(ys)
    while y <= max(ys):
        x = min(xs)
        while x <= max(xs):
            clear = kd.find((x, y, 0.0))[2]
            if clear >= r_min and inside(x, y):
                cands.append((clear, x, y))
            x += step
        y += step
    cands.sort(reverse=True)
    chosen = []
    for clear, x, y in cands:
        if all(((x - a) ** 2 + (y - b) ** 2) ** 0.5 >= sep for _, a, b in chosen):
            chosen.append((clear, x, y))
            if len(chosen) == count:
                break
    return [(co + u * x + v * y, clear) for clear, x, y in chosen]


def section_loops(obj, z):
    return section(obj, (0, 0, z), (0, 0, 1))


def halfspace(name, co, no, size=2000.0):
    """Huge box filling the side of the plane (co, no) that `no` points to."""
    no = Vector(no).normalized()
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * size, v.co.y * size, (v.co.z + 0.5) * size))
    rot = Vector((0, 0, 1)).rotation_difference(no).to_matrix().to_4x4()
    bm.transform(Matrix.Translation(co) @ rot)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return link(bpy.data.objects.new(name, me))


def remove_small_islands(obj, keep_ratio=0.01):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    seen, comps = set(), []
    for v in bm.verts:
        if v in seen:
            continue
        comp, stack = [], [v]
        seen.add(v)
        while stack:
            cur = stack.pop()
            comp.append(cur)
            for e in cur.link_edges:
                o = e.other_vert(cur)
                if o not in seen:
                    seen.add(o)
                    stack.append(o)
        comps.append(comp)
    biggest = max(len(c) for c in comps)
    junk = [v for c in comps if len(c) < biggest * keep_ratio for v in c]
    if junk:
        bmesh.ops.delete(bm, geom=junk, context="VERTS")
        bm.to_mesh(obj.data)
    bm.free()
    return len(comps) - 1 if junk else 0


def colour_by_nearest(obj, sources):
    """Give each face of obj the material of the nearest original (coloured) part."""
    bm = bmesh.new()
    face_mat = []
    mats = []
    for src in sources:
        mat = src.data.materials[0]
        if mat not in mats:
            mats.append(mat)
        me = src.data.copy()
        me.transform(src.matrix_world)
        n0 = len(bm.faces)
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
        face_mat += [mats.index(mat)] * (len(bm.faces) - n0)
    bm.faces.ensure_lookup_table()
    tree = BVHTree.FromBMesh(bm)
    bm.free()

    me = obj.data
    me.materials.clear()
    for m in mats:
        me.materials.append(m)
    idx = []
    for poly in me.polygons:
        hit = tree.find_nearest(obj.matrix_world @ poly.center)
        idx.append(face_mat[hit[2]] if hit[2] is not None else 0)
    me.polygons.foreach_set("material_index", idx)
    me.update()


def export(obj, base):
    for o in bpy.context.scene.objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.wm.stl_export(filepath=os.path.join(OUT_DIR, base + ".stl"),
                          export_selected_objects=True, ascii_format=False,
                          apply_modifiers=True, global_scale=1.0)
    bpy.ops.wm.obj_export(filepath=os.path.join(OUT_DIR, base + ".obj"),
                          export_selected_objects=True, export_materials=True,
                          export_uv=False, export_normals=False, global_scale=1.0,
                          forward_axis="Y", up_axis="Z")


# --------------------------------------------------------------------------
def main(height_mm=PRINT_HEIGHT_MM, render=False):
    os.makedirs(OUT_DIR, exist_ok=True)
    for f in os.listdir(OUT_DIR):
        os.remove(os.path.join(OUT_DIR, f))

    # 1) build the colour model with print-safe tube thickness, scale to mm
    igg.MIN_ROD = MIN_ROD_MM / (height_mm / 6.0)
    parts = igg.build()
    pedestal = bpy.data.objects["Pedestal"]
    top = max((p.matrix_world @ Vector(c)).z for p in parts for c in p.bound_box)
    S = height_mm / top                          # model units -> mm
    print(f"model height {top:.3f} units -> scale {S:.2f} mm/unit")
    for o in parts + [pedestal]:
        o.data.transform(o.matrix_world)
        o.parent = None
        o.matrix_world = Matrix.Identity(4)
        o.data.transform(Matrix.Scale(S, 4))
    base_top = igg.BASE_TOP * S

    def centre(ob):
        vs = ob.data.vertices
        return sum((v.co for v in vs), Vector()) / len(vs)

    # internal posts (hidden inside the domains): a foot under each Fc column that
    # carries the base pins, and a spine CH3 -> CH2 so each column is one solid
    posts = []
    for side in ("L", "R"):
        ch3 = bpy.data.objects[f"Fc_CH3_{side}"]
        c3, c2 = centre(ch3), centre(bpy.data.objects[f"Fc_CH2_{side}"])
        foot = c3.copy()
        foot.z = base_top - 3.0
        for nm, a, b, r in ((f"Fc_Foot_{side}", foot, c3, FOOT_RADIUS_MM),
                            (f"Fc_Spine_{side}", c3, c2, SPINE_RADIUS_MM)):
            post = tube(nm, a, b, r)
            post.data.materials.append(ch3.data.materials[0])
            posts.append(post)
    parts = parts + posts

    # 2) split by membership: each Fab arm is its own solid, everything else is the stem
    arm_parts = {side: [p for p in parts if p.name.startswith(f"Fab_{side}_")] for side in "LR"}
    stem_parts = [p for p in parts if not p.name.startswith("Fab_")]

    def solid_of(name, objs):
        ob = combine(name, objs)
        voxel_union(ob, VOXEL_MM)
        remove_small_islands(ob)
        return ob

    stem = solid_of("IgG_part2_stem", stem_parts)
    decimate(stem, MAX_TRIS_TOTAL // 2)
    above = box("above_base", base_top, 1e4)
    boolean(stem, above, "INTERSECT")                 # flat bottom on the pedestal
    bpy.data.objects.remove(above)

    # sockets: every arm loses the stem (grown by the clearance), so the hinge links
    # that run into the arm become pins sitting in straight sockets
    fat_stem = solid_of("fat_stem", stem_parts)
    displace(fat_stem, SOCKET_CLEARANCE_MM)
    voxel_union(fat_stem, VOXEL_MM)
    arms = {}
    for side, nm in (("L", "IgG_part3_arm_left"), ("R", "IgG_part4_arm_right")):
        arm = solid_of(nm, arm_parts[side])
        decimate(arm, MAX_TRIS_TOTAL // 4)
        boolean(arm, fat_stem, "DIFFERENCE")
        voxel_union(arm, VOXEL_MM * 0.8)              # clean surface after the cut
        remove_small_islands(arm)
        arms[side] = arm
    bpy.data.objects.remove(fat_stem)
    arm_l, arm_r = arms["L"], arms["R"]
    base = combine("IgG_part1_base", [pedestal])

    # 3) base -> stem pins (vertical)
    min_wall = PEG_RADIUS_MM + CLEARANCE_MM + 1.2
    centres = [c for c, r in pin_points(stem, Vector((0, 0, base_top + 1e-3)), Vector((0, 0, 1)),
                                        2, min_wall, PIN_SEPARATION_MM)]
    for c in centres:
        peg = tube("peg", c - Vector((0, 0, 1.0)), c + Vector((0, 0, PEG_LENGTH_MM)), PEG_RADIUS_MM)
        hole = tube("hole", c - Vector((0, 0, 1.0)), c + Vector((0, 0, PEG_LENGTH_MM + 0.6)),
                    PEG_RADIUS_MM + CLEARANCE_MM)
        boolean(base, peg, "UNION")
        boolean(stem, hole, "DIFFERENCE")
        bpy.data.objects.remove(peg)
        bpy.data.objects.remove(hole)
    voxel_union(stem, VOXEL_MM * 0.8)     # clean surface: exact-boolean slivers -> holes in slicers
    print(f"base -> stem: {len(centres)} pin(s)")

    # 4) assembly test: each arm must slide off its pins along the arm without touching
    for side, arm in arms.items():
        d = igg.ARM_DIRS[side]
        worst = 0.0
        for dist in (2.0, 6.0, 12.0, 25.0):
            probe = combine("probe", [arm])
            probe.data.transform(Matrix.Translation(d * dist))
            boolean(probe, stem, "INTERSECT")
            worst = max(worst, check_solid(probe)[1])
            bpy.data.objects.remove(probe)
        print(f"arm {side}: slide-off test, worst overlap {worst:.2f} mm3")

    # 6) colours, checks
    pieces = (base, stem, arm_l, arm_r)
    sources = parts + [pedestal]
    for o in pieces:
        colour_by_nearest(o, sources)
        if o is not base:
            igg.shade_smooth(o.data)
    report = []
    for o in pieces:
        nm, vol, tris = check_solid(o)
        dims = o.dimensions
        report.append(f"{o.name}: {dims.x:.0f} x {dims.y:.0f} x {dims.z:.0f} mm, "
                      f"{tris:,} tris, {vol / 1000:.1f} cm3, islands {islands(o)}, "
                      f"non-manifold edges {nm}")
        print(report[-1])

    # 7) export in print orientation, on the bed (z = 0)
    #    base & stem stand on their flat bottoms; each arm points down with its
    #    sockets facing up (so no support material ends up inside them)
    for o in pieces:
        name = o.name
        o.name = name + "_assembled"
        me = o.data.copy()
        if o in (arm_l, arm_r):
            d = igg.ARM_DIRS["L" if o is arm_l else "R"]
            me.transform(d.rotation_difference(Vector((0, 0, -1))).to_matrix().to_4x4())
        zs = [v.co.z for v in me.vertices]
        xs = [v.co.x for v in me.vertices]
        ys = [v.co.y for v in me.vertices]
        me.transform(Matrix.Translation((-(min(xs) + max(xs)) / 2,
                                         -(min(ys) + max(ys)) / 2, -min(zs))))
        tmp = link(bpy.data.objects.new(name, me))
        export(tmp, name)
        bpy.data.objects.remove(tmp)
        bpy.data.meshes.remove(me)
        o.name = name

    # keep only the pieces (assembled) in the saved file
    keep = set(pieces)
    for o in list(bpy.data.objects):
        if o.type == "MESH" and o not in keep and o.name != "Backdrop":
            bpy.data.objects.remove(o)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT_DIR, "IgG_print_parts.blend"),
                                compress=True)
    if render:
        render_exploded(base, stem, arms, arm_l, arm_r, S)
    return report


def render_exploded(base, stem, arms, arm_l, arm_r, S):
    stem.location = (0, 0, 22)
    arm_l.location = stem.location + igg.ARM_DIRS["L"] * 28
    arm_r.location = stem.location + igg.ARM_DIRS["R"] * 28
    sc = bpy.context.scene
    for o in bpy.data.objects:
        if o.type == "LIGHT":
            o.location *= S
            o.data.energy *= S * S
            o.data.size *= S
        if o.name == "Backdrop":
            o.scale = (S, S, S)
    cam = sc.camera
    cam.location = Vector((0, -600, 190))
    t = Vector((0, 0, 110))
    cam.rotation_euler = (t - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.lens = 62
    cam.data.clip_end = 5000
    igg.setup_render(96)
    sc.render.resolution_x, sc.render.resolution_y = 1400, 1400
    sc.render.filepath = os.path.join(OUT_DIR, "IgG_print_parts_preview.png")
    bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    h = float(argv[argv.index("--height") + 1]) if "--height" in argv else PRINT_HEIGHT_MM
    main(h, render="--render" in argv)
