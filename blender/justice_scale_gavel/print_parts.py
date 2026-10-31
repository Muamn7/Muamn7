"""
3D-print kit: Justice Scale (20 cm) + Gavel (15 cm), split into parts that
print WITHOUT supports (FDM, every overhang <= 45 degrees).
تقسيم الميزان والمطرقة إلى أجزاء قابلة للطباعة بدون دعامات

Run:  blender --background --python print_parts.py
  ->  print_stl/*.stl                    (millimetres, already in print orientation)
      justice_scale_gavel_print.blend    (all parts laid out + exploded assembly)
      renders/print_plate.png, renders/print_exploded.png

How the parts stay support-free
  * every turned part is printed standing on a flat cut face, and its outline is
    limited to a 45 degree slope in the print direction (bead undersides become
    small 45 degree cones - the classic "printable turning" look);
  * the beam is split lengthwise into two identical halves printed flat;
  * the hub is split at the beam axis so the beam drops into an open notch;
  * the gavel head is split at the handle axis so the handle socket is an
    open groove, and the brass band is two rings that clamp around it;
  * holes that open onto the bed end in a 45 degree cone (no flat ceiling);
  * parts are aligned with round pins (printed too, or 4/5 mm wooden dowels).
"""

import math
import os
import struct
import sys

import bpy
import bmesh
from mathutils import Matrix, Vector


def _here():
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except NameError:
        return os.getcwd()


HERE = _here()
if not os.path.exists(os.path.join(HERE, "justice_scale_gavel.py")):
    # running from Blender's text editor: use the .blend / text location
    for t in bpy.data.texts:
        if t.filepath:
            HERE = os.path.dirname(bpy.path.abspath(t.filepath))
sys.path.insert(0, HERE)
import justice_scale_gavel as J  # noqa: E402

CM = J.CM
SLOPE = 1.0          # tan(45 deg): max outward growth per unit of print height
CLR = 0.015          # 0.15 mm radial clearance for fits
PIN5, PIN4, PIN3 = 0.265, 0.215, 0.165   # hole radii for 5 / 4 / 3 mm pins

STAND_H = 1.7
BLOCK_H = 1.44
HEAD_C_Z = STAND_H + BLOCK_H + J.HEAD_HALF   # head centre height in the gavel set

J1, J2, J3 = 7.10, 13.68, 16.28              # column split heights (cm)


# --------------------------------------------------------------------------
# geometry helpers
# --------------------------------------------------------------------------


def envelope(profile, z0, z1, step=0.02):
    """Outer silhouette r(z) of a lathe profile between z0 and z1."""
    pts = profile.points(max_seg=0.05)
    segs = list(zip(pts[:-1], pts[1:]))
    zs = {round(z0 + i * step, 5) for i in range(int((z1 - z0) / step) + 1)}
    zs |= {round(p[1], 5) for p in pts if z0 <= p[1] <= z1}
    zs |= {z0, z1}
    out = []
    for z in sorted(zs):
        best = 0.0
        for (ra, za), (rb, zb) in segs:
            lo, hi = (za, zb) if za <= zb else (zb, za)
            if lo - 1e-9 <= z <= hi + 1e-9:
                if abs(zb - za) < 1e-9:
                    v = max(ra, rb)
                else:
                    v = ra + (z - za) / (zb - za) * (rb - ra)
                best = max(best, v)
        out.append([best, z])
    return out


def clamp_overhang(rz, upward=True):
    """Limit outward growth to 45 deg in the print direction."""
    idx = range(1, len(rz)) if upward else range(len(rz) - 2, -1, -1)
    for i in idx:
        j = i - 1 if upward else i + 1
        dz = abs(rz[i][1] - rz[j][1])
        rz[i][0] = min(rz[i][0], rz[j][0] + dz * SLOPE)
    return rz


def simplify(rz, tol=0.001):
    """Douglas-Peucker on the (r, z) polyline."""
    if len(rz) < 3:
        return rz
    a, b = Vector(rz[0]), Vector(rz[-1])
    ab = b - a
    L = ab.length
    dmax, imax = 0.0, 0
    for i in range(1, len(rz) - 1):
        p = Vector(rz[i])
        d = abs(ab.x * (a.y - p.y) - ab.y * (a.x - p.x)) / L if L > 1e-12 else (p - a).length
        if d > dmax:
            dmax, imax = d, i
    if dmax <= tol:
        return [rz[0], rz[-1]]
    return simplify(rz[:imax + 1], tol)[:-1] + simplify(rz[imax:], tol)


def lathe_from_points(name, pts, coll, segs=128):
    p = J.Profile(*pts[0])
    p.p = [[r, z, 0.0] for r, z in pts]
    return J.lathe(name, p, coll, [], segs=segs, max_seg=10.0)


def turned_part(name, coll, profile, z0, z1, upward, bottom_hole=None, top_hole=None,
                through=None, segs=128):
    """Support-free solid of revolution between z0 and z1.
    bottom_hole / top_hole = (radius, depth); through = radius.
    upward=True: printed standing on z0.  upward=False: printed on z1 (flipped)."""
    rz = simplify(clamp_overhang(envelope(profile, z0, z1), upward))
    c = 0.04  # 0.4 mm entry chamfer on holes
    # never let the outline dip inside a hole near the end faces
    lo_r = (through or (bottom_hole or (0,))[0] or 0) + c + 0.01
    hi_r = (through or (top_hole or (0,))[0] or 0) + c + 0.01
    if through or bottom_hole:
        while len(rz) > 2 and rz[0][0] < lo_r:
            rz.pop(0)
    if through or top_hole:
        while len(rz) > 2 and rz[-1][0] < hi_r:
            rz.pop()
    path = []
    if through:
        path = [(through, z0 + c), (through + c, z0)] + [tuple(q) for q in rz] \
            + [(through + c, z1), (through, z1 - c), (through, z0 + c)]
        return lathe_from_points(name, path, coll, segs)
    if bottom_hole:
        hr, hd = bottom_hole
        if upward:   # opens on the bed -> pointed (45 deg) ceiling
            path += [(0, z0 + hd + hr), (hr, z0 + hd)]
        else:
            path += [(0, z0 + hd), (hr, z0 + hd)]
        path += [(hr, z0 + c), (hr + c, z0)]
    else:
        path += [(0, z0)]
    path += [tuple(q) for q in rz]
    if top_hole:
        hr, hd = top_hole
        path += [(hr + c, z1), (hr, z1 - c)]
        if upward:
            path += [(hr, z1 - hd), (0, z1 - hd)]
        else:        # opens on the bed (part is flipped)
            path += [(hr, z1 - hd), (0, z1 - hd - hr)]
    else:
        path += [(0, z1)]
    return lathe_from_points(name, path, coll, segs)


def teardrop(coll, p0, p1, r, up=(0, 0, 1), sides=32, name="cutter"):
    """Horizontal hole cutter with a 45 deg pointed top -> prints without bridging."""
    p0, p1 = Vector(p0), Vector(p1)
    ax = (p1 - p0).normalized()
    u = Vector(up)
    u = (u - ax * u.dot(ax)).normalized()
    sd = ax.cross(u)
    sec = []
    for i in range(sides + 1):
        a = math.radians(135 + 270 * i / sides)
        sec.append((math.cos(a) * r, math.sin(a) * r))
    sec.append((0.0, r * math.sqrt(2)))
    n = len(sec)
    v = [tuple(p + sd * a + u * b) for p in (p0, p1) for a, b in sec]
    f = [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
    f += [tuple(reversed(range(n))), tuple(range(n, 2 * n))]
    return J.make_object(name, v, f, coll, smooth=False)


def split_half(ob, keep_positive_y=True):
    """Cut a mesh at y=0, keep one side and cap the cut (robust for on-plane verts)."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    res = bmesh.ops.bisect_plane(bm, geom=geom, dist=1e-7, plane_co=(0, 0, 0),
                                 plane_no=(0, 1, 0), clear_inner=keep_positive_y,
                                 clear_outer=not keep_positive_y)
    cut_edges = [e for e in res["geom_cut"] if isinstance(e, bmesh.types.BMEdge)]
    bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=False, edges=cut_edges)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()
    return ob


def cylinder(coll, p0, p1, r, sides=48, name="cutter"):
    v, f = J.tube_geometry([Vector(p0), Vector(p1)], r, sides=sides)
    return J.make_object(name, v, f, coll, smooth=False)


def boolean(ob, cutter, op="DIFFERENCE", keep_cutter=False):
    mod = ob.modifiers.new("bool", "BOOLEAN")
    mod.operation = op
    mod.object = cutter
    try:
        mod.solver = "EXACT"
    except Exception:
        pass
    dg = bpy.context.evaluated_depsgraph_get()
    new_me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    old = ob.data
    ob.modifiers.remove(mod)
    ob.data = new_me
    new_me.name = ob.name
    bpy.data.meshes.remove(old)
    if not keep_cutter:
        bpy.data.objects.remove(cutter, do_unlink=True)
    return ob


def apply_matrix(ob, M):
    ob.data.transform(M)
    ob.data.update()


def box(coll, x0, x1, y0, y1, z0, z1, name="box"):
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return J.make_object(name, v, f, coll, smooth=False)


def pin(name, coll, r, length):
    c = 0.04
    pts = [(0, 0), (r - c, 0), (r, c), (r, length - c), (r - c, length), (0, length)]
    return lathe_from_points(name, pts, coll, segs=48)


# --------------------------------------------------------------------------
# parts (built in assembled position, then rotated to print orientation)
# --------------------------------------------------------------------------

PARTS = []   # (object, print_rotation, copies, group, note)


def add(ob, rot=Matrix.Identity(4), copies=1, group="scale", note=""):
    PARTS.append([ob, rot, copies, group, note])
    return ob


FLIP = Matrix.Rotation(math.pi, 4, "X")


def build_scale_parts(coll):
    prof = J.column_profile()
    add(turned_part("S1_Base", coll, prof, 0.0, J1, True, top_hole=(PIN5, 0.8)),
        note="standing on its bottom")
    add(turned_part("S2_Spindle", coll, prof, J1, J2, False,
                    bottom_hole=(PIN5, 0.8), top_hole=(PIN4, 1.0)), FLIP,
        note="upside-down (hub end on the bed)")

    lower = turned_part("S3_Hub_Lower", coll, prof, J2, J.BEAM_Z, True, through=PIN4)
    upper = turned_part("S5_Hub_Upper", coll, prof, J.BEAM_Z, J3, False, through=PIN4)
    v, f = J.beam_geometry(inflate=CLR)
    for hub in (lower, upper):
        cut = J.make_object("notch", v, f, coll, smooth=False)
        boolean(hub, cut)
    add(lower, note="narrow end down, notch open on top")
    add(upper, FLIP, note="upside-down, notch open on top")

    add(turned_part("S6_Finial", coll, prof, J3, 20.0, True, bottom_hole=(PIN4, 0.8)),
        note="standing")

    # beam: two identical lengthwise halves printed flat
    v, f = J.beam_geometry()
    beam = J.make_object("S4_Beam_Half", v, f, coll)
    sub = beam.modifiers.new("sub", "SUBSURF")
    sub.levels = 1
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(beam.evaluated_get(dg))
    beam.modifiers.clear()
    beam.data = me
    boolean(beam, teardrop(coll, (0, 0, 12.5), (0, 0, 17.5), PIN4, up=(0, 1, 0)))
    zc, h, d = J.beam_shape(J.HOOK_S)
    bottom = J.BEAM_Z + zc - h / 2
    for sx in (-1, 1):
        hx = sx * J.HOOK_S * J.BEAM_L
        boolean(beam, teardrop(coll, (hx, 0, bottom - 0.3), (hx, 0, bottom + 0.6), 0.065,
                               up=(0, 1, 0), sides=16))
    split_half(beam, keep_positive_y=True)
    add(beam, Matrix.Rotation(math.pi / 2, 4, "X"), copies=2,
        note="flat face down; print 2, glue together")

    # pans
    p = J.Profile(0, 0)
    p.line(1.80, 0.0, 0.0)
    p.bez((2.15, 0.35), (2.40, 0.70), (2.42, 1.18), n=30)
    p.arc((2.30, 1.18), 0.12, 0, 180, n=16)
    p.bez((2.17, 0.70), (1.95, 0.34), (1.30, 0.30), n=26)
    p.line(0.0, 0.30, 0.0)
    pan = J.lathe("S7_Pan", p, coll, [], segs=128, max_seg=0.1)
    for a in (90, 210, 330):
        u = Vector((math.cos(math.radians(a)), math.sin(math.radians(a)), 0))
        boolean(pan, teardrop(coll, u * 1.9 + Vector((0, 0, 1.02)),
                              u * 2.8 + Vector((0, 0, 1.02)), 0.07, sides=16))
    apply_matrix(pan, Matrix.Translation(Vector((J.HOOK_S * J.BEAM_L, 0, J.PAN_BOTTOM)) * CM))
    add(pan, copies=2, note="standing on its foot")


def build_gavel_parts(coll):
    head_c = Vector((0, 0, HEAD_C_Z))
    hp = J.head_half_profile()

    def head_half(name, with_hole):
        ob = turned_part(name, coll, hp, -J.HEAD_HALF, 0.0, True,
                         bottom_hole=(PIN5, 0.8) if with_hole else None)
        # open groove = handle socket, + two alignment pin holes
        boolean(ob, cylinder(coll, (0.55, 0, 0), (2.5, 0, 0), 0.48 + CLR + 0.005))
        for sy in (-1, 1):
            boolean(ob, cylinder(coll, (0, sy * 0.85, -0.6), (0, sy * 0.85, 0.2), PIN3,
                                 sides=24))
        return ob

    lo = head_half("G3_Head_Half_Bottom", True)
    apply_matrix(lo, Matrix.Translation(head_c * CM))
    add(lo, group="gavel", note="striking face down, groove up")
    hi = head_half("G5_Head_Half_Top", False)
    apply_matrix(hi, Matrix.Translation(head_c * CM) @ FLIP)
    add(hi, FLIP, group="gavel", note="striking face down, groove up")

    # brass band: two rings split at the handle axis
    for k, M in enumerate((Matrix.Identity(4), FLIP)):
        b = J.Profile(1.32 + CLR + 0.005, -1.40)
        b.line(1.46, -1.40, 0.0)
        b.line(1.50, -1.28, 0.02)
        b.line(1.46, -1.20, 0.015)
        b.line(1.46, 0.0, 0.0)
        b.line(1.34, 0.0, 0.0)
        b.line(1.32 + CLR + 0.005, -1.40, 0.0)
        band = J.lathe("G4_Band_Half", b, coll, [], segs=128, max_seg=0.1)
        boolean(band, cylinder(coll, (1.0, 0, 0), (2.5, 0, 0), 0.48 + CLR + 0.005))
        apply_matrix(band, Matrix.Translation(head_c * CM) @ M)
        if k == 0:
            add(band, copies=2, group="gavel", note="gold filament; print 2")
        else:
            band.name = "G4_Band_Half_upper"
            PARTS.append([band, FLIP, 0, "gavel", "(same file as G4)"])

    handle = turned_part("G6_Handle", coll, J.handle_profile(), 0.6, J.HANDLE_LEN, True)
    apply_matrix(handle, Matrix.Translation(head_c * CM) @ Matrix.Rotation(math.pi / 2, 4, "Y"))
    add(handle, Matrix.Rotation(-math.pi / 2, 4, "Y"), group="gavel",
        note="standing on the tenon end - use a brim")

    blk = turned_part("G2_Sound_Block", coll, J.sound_block_profile(), 0.0, BLOCK_H, True,
                      through=PIN5)
    apply_matrix(blk, Matrix.Translation(Vector((0, 0, STAND_H)) * CM))
    add(blk, group="gavel", note="standing")

    # handle rest: outer shape clamped to 45 deg + the spherical cup on top
    rp, rim_z, zc = J.rest_profile(STAND_H, HEAD_C_Z, 0.60, with_cup=False)
    rz = simplify(clamp_overhang(envelope(rp, 0.0, rim_z), True))
    hr, hd = PIN4, 0.6
    path = [(0, hd + hr), (hr, hd), (hr, 0.04), (hr + 0.04, 0.0)]
    path += [tuple(q) for q in rz] + [(0.56, rim_z)]
    for i in range(1, 17):
        r = 0.56 * (1 - i / 16)
        path.append((r, zc - math.sqrt(0.60 ** 2 - r * r)))
    rest = lathe_from_points("G7_Handle_Rest", path, coll, segs=96)
    apply_matrix(rest, Matrix.Translation(Vector((J.REST_X, 0, STAND_H)) * CM))
    add(rest, group="gavel", note="standing")

    # stand: sharp bottom edges, rounded top + vertical edges
    st = box(coll, -3.7, 13.7, -3.6, 3.6, 0, STAND_H, "G1_Stand")
    bm = bmesh.new()
    bm.from_mesh(st.data)
    edges = [e for e in bm.edges
             if not all(abs(v.co.z) < 1e-6 for v in e.verts)]
    bmesh.ops.bevel(bm, geom=edges, offset=0.22 * CM, segments=5, profile=0.6,
                    affect="EDGES")
    bm.to_mesh(st.data)
    bm.free()
    gx0, gx1 = 3.6, J.REST_X - 1.6
    boolean(st, box(coll, gx0, gx1, -0.55, 0.55, STAND_H - 0.32, STAND_H + 1))
    boolean(st, cylinder(coll, (0, 0, STAND_H - 0.8), (0, 0, STAND_H + 0.2), PIN5))
    boolean(st, cylinder(coll, (J.REST_X, 0, STAND_H - 0.6), (J.REST_X, 0, STAND_H + 0.2),
                         PIN4))
    add(st, group="gavel", note="flat on the bed")


def build_pins(coll):
    for name, r, L, n in (("P1_Pin_5x15mm", 0.25, 1.5, 1),
                          ("P2_Pin_4x43mm", 0.20, 4.3, 1),
                          ("P3_Pin_5x29mm", 0.25, 2.9, 1),
                          ("P4_Pin_4x11mm", 0.20, 1.1, 1),
                          ("P5_Pin_3x11mm", 0.15, 1.1, 2)):
        add(pin(name, coll, r, L), copies=n, group="pins", note="standing")


# --------------------------------------------------------------------------
# checks + export
# --------------------------------------------------------------------------


def to_print_orientation(ob, rot):
    apply_matrix(ob, rot)
    bb = [v.co for v in ob.data.vertices]
    mn = Vector((min(v.x for v in bb), min(v.y for v in bb), min(v.z for v in bb)))
    mx = Vector((max(v.x for v in bb), max(v.y for v in bb), max(v.z for v in bb)))
    T = Matrix.Translation(-Vector(((mn.x + mx.x) / 2, (mn.y + mx.y) / 2, mn.z)))
    apply_matrix(ob, T)
    return T @ rot, mx - mn


def check(ob):
    """returns (overhang area mm2 steeper than 45 deg above the first layer,
                non-manifold edge count, volume cm3)"""
    me = ob.data
    me.calc_loop_triangles()
    bad = 0.0
    lim = -math.sin(math.radians(45)) - 0.02
    for t in me.loop_triangles:
        n = t.normal
        if n.z < lim and t.center.z > 0.0003:   # ignore faces on the bed
            bad += t.area * 1e6
    bm = bmesh.new()
    bm.from_mesh(me)
    nm = sum(1 for e in bm.edges if not e.is_manifold)
    vol = abs(bm.calc_volume()) * 1e6
    bm.free()
    return bad, nm, vol


def write_stl(ob, path):
    me = ob.data
    me.calc_loop_triangles()
    co = [v.co for v in me.vertices]
    with open(path, "wb") as fh:
        fh.write(b"Justice scale / gavel print kit - mm".ljust(80, b" "))
        fh.write(struct.pack("<I", len(me.loop_triangles)))
        for t in me.loop_triangles:
            n = t.normal
            fh.write(struct.pack("<3f", n.x, n.y, n.z))
            for vi in t.vertices:
                c = co[vi] * 1000.0
                fh.write(struct.pack("<3f", c.x, c.y, c.z))
            fh.write(b"\0\0")


def main(render=True, samples=48):
    J.clear_scene()
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.length_unit = "MILLIMETERS"
    coll = J.new_collection("Print_Parts")

    build_scale_parts(coll)
    build_gavel_parts(coll)
    build_pins(coll)

    out = os.path.join(HERE, "print_stl")
    os.makedirs(out, exist_ok=True)
    for fn in os.listdir(out):
        if fn.endswith(".stl"):
            os.remove(os.path.join(out, fn))

    report = []
    assembled = {}
    for ob, rot, copies, group, note in PARTS:
        M, size = to_print_orientation(ob, rot)
        assembled[ob.name] = M.inverted()
        bad, nm, vol = check(ob)
        if copies:
            fname = f"{group}_{ob.name}" + (f"_x{copies}" if copies > 1 else "") + ".stl"
            write_stl(ob, os.path.join(out, fname))
        report.append((ob.name, copies, size * 1000, bad, nm, vol, note))

    print("\n%-22s %4s %22s %10s %5s %8s  %s" % ("part", "qty", "size mm (x,y,z)",
                                              "ovh mm2", "nonM", "vol cm3", "orientation"))
    for name, n, s, bad, nm, vol, note in report:
        print("%-22s %4s %6.1f x%6.1f x%6.1f %10.1f %5d %8.1f  %s"
              % (name, n, s.x, s.y, s.z, bad, nm, vol, note))

    layout_and_render(coll, assembled, render, samples)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HERE, "justice_scale_gavel_print.blend"),
                                compress=True)
    return report


# --------------------------------------------------------------------------
# layout (print plate + exploded assembly) and renders
# --------------------------------------------------------------------------


def layout_and_render(coll, assembled, render, samples):
    sc = bpy.context.scene
    wood = J.make_simple("PLA_Wood", (0.16, 0.065, 0.028), rough=0.55)
    dark = J.make_simple("PLA_Dark", (0.05, 0.03, 0.02), rough=0.5)
    gold = J.make_simple("PLA_Silk_Gold", (0.85, 0.58, 0.20), rough=0.3, metal=0.7)
    for ob, *_ in PARTS:
        ob.data.materials.clear()
        if ob.name.startswith("G4"):
            ob.data.materials.append(gold)
        elif ob.name.startswith("P"):
            ob.data.materials.append(dark)
        else:
            ob.data.materials.append(wood)
        ob.data.polygons.foreach_set("use_smooth", [True] * len(ob.data.polygons))
        if hasattr(ob.data, "set_sharp_from_angle"):
            ob.data.set_sharp_from_angle(angle=math.radians(35))

    # --- print plate: simple shelf packing (gap 8 mm)
    gap, row_w = 0.008, 0.46
    x = y = row_h = 0.0
    items = [p for p in PARTS if p[2]]
    items.sort(key=lambda p: -(p[0].dimensions.y))
    for ob, rot, copies, group, note in items:
        for k in range(copies):
            o = ob if k == 0 else ob.copy()
            if k:
                coll.objects.link(o)
                o.name = ob.name + f"_copy{k}"
            dx, dy = ob.dimensions.x, ob.dimensions.y
            if x + dx > row_w:
                x, y, row_h = 0.0, y + row_h + gap, 0.0
            o.location = (x + dx / 2, y + dy / 2, 0)
            x += dx + gap
            row_h = max(row_h, dy)

    # --- exploded assembly (linked duplicates back in assembled position)
    ex = J.new_collection("Exploded_Assembly")
    lift = {"S1": 0, "S2": 1.5, "S3": 3.0, "S4": 4.5, "S5": 6.0, "S6": 7.5, "S7": -1.5,
            "G1": 0, "G2": 1.5, "G3": 3.0, "G4": 5.0, "G5": 8.0, "G6": 5.0, "G7": 1.5}
    for ob, rot, copies, group, note in PARTS:
        if group == "pins":
            continue
        base = assembled[ob.name]
        variants = [Matrix.Identity(4)]
        if ob.name.startswith("S4"):        # second beam half (mirror in Y)
            variants = [Matrix.Translation((0, -0.008, 0)),
                        Matrix.Translation((0, 0.008, 0)) @ Matrix.Scale(-1, 4, (0, 1, 0))]
        if ob.name.startswith("S7"):        # second pan (mirror in X)
            variants = [Matrix.Identity(4), Matrix.Scale(-1, 4, (1, 0, 0))]
        for k, V in enumerate(variants):
            d = ob.copy()
            d.name = ob.name + f"_asm{k}"
            off = Vector((0, 0, lift[ob.name[:2]] * CM))
            if ob.name.startswith("G4_Band_Half_upper"):
                off.z += 0.012
            if ob.name.startswith("G6"):
                off.x += 0.025
            if group == "gavel":
                off += Vector((-0.30, 0, 0))
            d.matrix_world = Matrix.Translation(off) @ V @ base
            if ob.name.startswith("G4_Band_Half_upper"):
                d.data = ob.data
            ex.objects.link(d)
    # the upper band half was only kept for the exploded view
    for ob, rot, copies, group, note in PARTS:
        if copies == 0:
            coll.objects.unlink(ob)

    if not render:
        return
    studio = J.new_collection("Studio")
    floor = J.make_simple("Floor", (0.8, 0.8, 0.8), rough=0.6)
    J.make_object("Floor", [(-500, -500, 0), (500, -500, 0), (500, 500, 0), (-500, 500, 0)],
                  [(0, 1, 2, 3)], studio, [floor], smooth=False)
    for name, loc, e, s in (("Key", (-0.5, -0.6, 0.9), 30, 0.6), ("Fill", (0.7, -0.3, 0.5), 8, 0.8),
                            ("Top", (0.0, 0.3, 1.0), 12, 0.8)):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy, ld.size = e, s
        lo = bpy.data.objects.new(name, ld)
        lo.location = loc
        lo.rotation_euler = (Vector((0.1, 0.1, 0)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        studio.objects.link(lo)
    world = sc.world or bpy.data.worlds.new("World")
    sc.world = world
    try:
        world.use_nodes = True
    except Exception:
        pass
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.9, 0.9, 0.92, 1)
        bg.inputs["Strength"].default_value = 0.15
    cd = bpy.data.cameras.new("Cam")
    cd.lens = 50
    cam = bpy.data.objects.new("Cam", cd)
    studio.objects.link(cam)
    sc.camera = cam
    sc.render.engine = "CYCLES"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = 1600, 1000
    try:
        sc.view_settings.view_transform = "AgX"
    except Exception:
        pass

    def frame(objs, direction):
        bpy.context.view_layer.update()
        pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
        mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        c = (mn + mx) / 2
        rad = (mx - mn).length / 2
        d = Vector(direction).normalized()
        cam.location = c + d * rad / math.sin(math.radians(17)) * 0.95
        cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()

    plate = [o for o in coll.objects]
    asm = [o for o in ex.objects]
    rd = os.path.join(HERE, "renders")
    os.makedirs(rd, exist_ok=True)
    for objs, hide, dirn, fn in ((plate, asm, (0.0, -0.75, 1.0), "print_plate.png"),
                                 (asm, plate, (-0.25, -1.0, 0.45), "print_exploded.png")):
        for o in hide:
            o.hide_render = True
        for o in objs:
            o.hide_render = False
        frame(objs, dirn)
        sc.render.filepath = os.path.join(rd, fn)
        bpy.ops.render.render(write_still=True)
    for o in asm:
        o.hide_render = False
    ex.hide_viewport = True


if __name__ == "__main__":
    main()
