"""
IgG Antibody - 3D-print version in 3 parts (Blender 4.2+ / 5.x)

Builds the model with igg_antibody.py, merges it into one watertight solid,
scales it to millimetres and splits it into three printable parts that plug
together with pegs and holes:

    Part 1  Base     : pedestal                                 (pegs up)
    Part 2  Fc stem  : lower half of the Fc region             (holes below, pegs up)
    Part 3  Top      : upper Fc + hinge + both Fab arms         (holes below)

Every part has a flat face to print on. Output (next to this script, in print/):
    IgG_part1_base.stl / IgG_part2_fc.stl / IgG_part3_top.stl   (mm)
    IgG_part*.obj + .mtl  (same parts with colours, for multi-colour slicers)
    IgG_print_parts.blend (the three parts, laid out)

Headless:
    blender -b -P igg_antibody_print.py -- --height 180 --render preview.png
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
MIN_ROD_MM = 1.6          # thinnest tube radius (3.2 mm diameter)
PEG_RADIUS_MM = 2.5
PEG_LENGTH_MM = 6.0
CLEARANCE_MM = 0.2        # radial play in the holes
CUT_1 = igg.BASE_TOP          # base | Fc stem   (model units, top of the pedestal)
CUT_2 = igg.BASE_TOP + 1.12   # Fc stem | top    (between the CH3 and CH2 domains)
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


def section_loops(obj, z):
    """Cross-section islands of obj at height z -> [(centre, inscribed radius)]."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    res = bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
                                 plane_co=(0, 0, z), plane_no=(0, 0, 1))
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
        c.z = z
        r_in = min((Vector((p.x, p.y, z)) - c).length for p in pts)
        out.append((c, r_in))
    bm.free()
    return out


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
def main(height_mm=PRINT_HEIGHT_MM):
    os.makedirs(OUT_DIR, exist_ok=True)

    # 1) build the colour model with print-safe tube thickness
    pedestal_h_guess = 6.6                       # model units, refined below
    igg.MIN_ROD = MIN_ROD_MM / (height_mm / pedestal_h_guess)
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

    # internal posts: a foot under each Fc column (so it sits firmly in the base)
    # and a spine through CH3 -> CH2 (so the stem joint is always thick and solid)
    def centre(ob):
        vs = ob.data.vertices
        return sum((v.co for v in vs), Vector()) / len(vs)

    posts = []
    for side in ("L", "R"):
        ch3 = bpy.data.objects[f"Fc_CH3_{side}"]
        ch2 = bpy.data.objects[f"Fc_CH2_{side}"]
        c3, c2 = centre(ch3), centre(ch2)
        foot = c3.copy()
        foot.z = (igg.BASE_TOP - 0.15) * S
        for nm, a, b in ((f"Fc_Foot_{side}", foot, c3), (f"Fc_Spine_{side}", c3, c2)):
            post = tube(nm, a, b, 0.21 * S)
            post.data.materials.append(ch3.data.materials[0])
            posts.append(post)
    parts = parts + posts

    # 2) one watertight solid for the antibody
    solid = combine("IgG_Solid", parts)
    voxel_union(solid, VOXEL_MM)
    specks = remove_small_islands(solid)
    decimate(solid, MAX_TRIS_TOTAL)          # before the boolean cuts -> they stay manifold
    n = islands(solid)
    print(f"antibody solid: {len(solid.data.polygons):,} faces, {n} island(s) ({specks} voxel specks removed)")

    z1, z2 = CUT_1 * S, CUT_2 * S
    for z in (z1, z2):
        for c, r in section_loops(solid, z):
            print(f"  section z={z:.1f}mm at ({c.x:.1f},{c.y:.1f})  inscribed radius {r:.1f} mm")

    # 3) split into slabs
    def slab(name, zmin, zmax):
        ob = combine(name, [solid])
        cutter = box(name + "_box", zmin, zmax)
        boolean(ob, cutter, "INTERSECT")
        bpy.data.objects.remove(cutter)
        return ob

    p2 = slab("IgG_part2_fc", z1, z2)
    p3 = slab("IgG_part3_top", z2, 1e4)

    # the base is only the pedestal (the antibody below its top surface is discarded)
    p1 = combine("IgG_part1_base", [pedestal])

    # 4) pegs (on the lower part) and holes (in the upper part) at every joint
    for lower, upper, z in ((p1, p2, z1), (p2, p3, z2)):
        centres = []
        for c, r_in in section_loops(upper, z + 1e-3):
            if r_in > PEG_RADIUS_MM + CLEARANCE_MM + 1.2:   # >= 1.2 mm wall around the hole
                centres.append(c)
        rp = PEG_RADIUS_MM
        pegs = cylinders("pegs", centres, rp, z - 1.0, z + PEG_LENGTH_MM, chamfer=0.6)
        holes = cylinders("holes", centres, rp + CLEARANCE_MM, z - 1.0,
                          z + PEG_LENGTH_MM + 0.6)
        boolean(lower, pegs, "UNION")
        boolean(upper, holes, "DIFFERENCE")
        bpy.data.objects.remove(pegs)
        bpy.data.objects.remove(holes)
        print(f"joint z={z:.1f}mm: {len(centres)} peg(s)")

    # 5) colours, checks, export
    sources = parts + [pedestal]
    for o in (p1, p2, p3):
        colour_by_nearest(o, sources)
    igg.shade_smooth(p2.data)
    igg.shade_smooth(p3.data)
    report = []
    for o in (p1, p2, p3):
        nm, vol, tris = check_solid(o)
        dims = o.dimensions
        report.append(f"{o.name}: {dims.x:.0f} x {dims.y:.0f} x {dims.z:.0f} mm, "
                      f"{tris:,} tris, {vol / 1000:.1f} cm3, islands {islands(o)}, "
                      f"non-manifold edges {nm}")
        print(report[-1])

    # print orientation: every part standing on its flat bottom at z = 0
    # (Part 1 & 2 bottoms are flat; Part 3 sits on its cut face)
    for o, zb in ((p1, 0.0), (p2, z1), (p3, z2)):
        o["assembly_z_mm"] = zb             # where this part sits when assembled
        o.data.transform(Matrix.Translation((0, 0, -zb)))
        export(o, o.name)

    # clean scene: keep only the parts, laid out side by side
    keep = {p1, p2, p3}
    for o in list(bpy.data.objects):
        if o not in keep and o.type == "MESH":
            bpy.data.objects.remove(o)
    p1.location.x = -(p1.dimensions.x / 2 + 25)
    p2.location.x = 0
    p3.location.x = p3.dimensions.x / 2 + 25
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT_DIR, "IgG_print_parts.blend"),
                                compress=True)
    return p1, p2, p3, report


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    h = float(argv[argv.index("--height") + 1]) if "--height" in argv else PRINT_HEIGHT_MM
    main(h)
