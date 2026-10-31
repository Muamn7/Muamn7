"""
3D-print kit: Justice Scale (20 cm) + Gavel (15 cm), split into parts that
print WITHOUT supports (FDM, every overhang <= 45 degrees).
تقسيم الميزان والمطرقة إلى أجزاء قابلة للطباعة بدون دعامات

Run:  blender --background --python print_parts.py
  ->  print_stl/*.stl                    (millimetres, already in print orientation)
      justice_scale_gavel_print.blend    (all parts laid out + exploded assembly)
      renders/print_plate.png, renders/print_exploded.png

Only 8 prints (7 files):
  scale : column, top+finial, beam (with hooks), pan+3 chains+loop (x2)
  gavel : base (stand + sound block + handle rest), head (with band), handle

How the parts stay support-free
  * turned parts stand on flat faces; their outline is limited to a 45 degree
    slope in the print direction (bead undersides become small 45 deg cones);
  * the beam prints face-up on a flattened back, its J-hooks lie on the bed;
  * the hub has an open U-slot: the beam drops in, the top piece closes it;
  * the chains are flat diamond links (28 deg points, alternating 90 deg)
    that grow straight out of the pan rim and meet in a pointed hanging loop;
  * the handle socket is a teardrop hole; bed-side holes end in a 45 deg cone.
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
PIN4 = 0.215                         # hole radius for the 3.8 / 4 mm pins

STAND_H = 1.7
BLOCK_H = 1.44
HEAD_C_Z = STAND_H + BLOCK_H + J.HEAD_HALF   # head centre height in the gavel set

BAND_Z0, BAND_Z1 = 2.10, 4.90        # gold band height on the printed head (cm)


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


# --------------------------------------------------------------------------
# parts (built in assembled position, then rotated to print orientation)
# --------------------------------------------------------------------------

PARTS = []   # [object, print_rotation, copies, group, note]


def add(ob, rot=Matrix.Identity(4), copies=1, group="scale", note=""):
    PARTS.append([ob, rot, copies, group, note])
    return ob


def union(base, others):
    """Boolean-union a list of objects into base (exact solver, watertight)."""
    tmp = bpy.data.collections.new("tmp_union")
    bpy.context.scene.collection.children.link(tmp)
    for o in others:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        tmp.objects.link(o)
    mod = base.modifiers.new("union", "BOOLEAN")
    mod.operation = "UNION"
    mod.operand_type = "COLLECTION"
    mod.collection = tmp
    try:
        mod.solver = "EXACT"
    except Exception:
        pass
    dg = bpy.context.evaluated_depsgraph_get()
    new_me = bpy.data.meshes.new_from_object(base.evaluated_get(dg))
    old = base.data
    base.modifiers.remove(mod)
    base.data = new_me
    new_me.name = base.name
    bpy.data.meshes.remove(old)
    for o in others:
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.data.collections.remove(tmp)
    return base


def extrude_polygon(name, coll, pts2d, plane_u, plane_v, normal, t0, t1):
    """Prism from a 2-D outline (cm) spanned by plane_u/plane_v, from t0 to t1 along normal."""
    u, v, n = Vector(plane_u), Vector(plane_v), Vector(normal)
    k = len(pts2d)
    verts = [tuple(u * a + v * b + n * t) for t in (t0, t1) for a, b in pts2d]
    faces = [tuple(reversed(range(k))), tuple(range(k, 2 * k))]
    faces += [(i, (i + 1) % k, k + (i + 1) % k, k + i) for i in range(k)]
    return J.make_object(name, verts, faces, coll, smooth=False)


def plate_link(verts, faces, tip, axis, wdir, W, L, b, t, half_angle=28.0, side=None):
    """Flat diamond chain link with a window. Both pointed ends follow `half_angle`
    from the axis, so it prints upright without support. tip = bottom point."""
    th = math.radians(half_angle)
    a = Vector(axis).normalized()
    w = Vector(wdir)
    w = (w - a * w.dot(a)).normalized()
    n = a.cross(w)
    ho = (W / 2) / math.tan(th)
    s = L - 2 * ho if side is None else side
    L = 2 * ho + s
    outer = [(0, 0), (W / 2, ho), (W / 2, ho + s), (0, L), (-W / 2, ho + s), (-W / 2, ho)]
    off = b / math.sin(th)
    wi = W / 2 - b / math.cos(th)
    hi = wi / math.tan(th)
    si = L - 2 * off - 2 * hi
    inner = [(0, off), (wi, off + hi), (wi, off + hi + si), (0, L - off),
             (-wi, off + hi + si), (-wi, off + hi)]
    P = Vector(tip)
    base = len(verts)
    for d in (-t / 2, t / 2):
        for poly in (outer, inner):
            for x, y in poly:
                verts.append(tuple(P + w * x + a * y + n * d))
    O0, I0, O1, I1 = base, base + 6, base + 12, base + 18
    for i in range(6):
        j = (i + 1) % 6
        faces.append((O0 + i, I0 + i, I0 + j, O0 + j))      # back face ring
        faces.append((O1 + i, O1 + j, I1 + j, I1 + i))      # front face ring
        faces.append((O0 + i, O0 + j, O1 + j, O1 + i))      # outer wall
        faces.append((I0 + i, I1 + i, I1 + j, I0 + j))      # window wall
    return L


# ---- print versions of the beam -----------------------------------------

BEAM_BED_Y = 0.34    # the beam's back is flattened at y = +3.4 mm (printed face down)
HOOK_T = 0.24        # hook plate thickness (y)
HOOK_RI, HOOK_RO = 0.28, 0.48


def print_beam_geometry(inflate=0.0, levels=16):
    """Beam with a flat back (+Y) and <=45 deg flanks, front (-Y) unchanged."""
    expo = 2.6
    r_end, n_mid, caps = 0.55, 220, 14
    x_cap = J.BEAM_L - r_end
    xs = []
    for i in range(caps, 0, -1):
        bb = math.pi / 2 * i / caps
        xs.append((-(x_cap + r_end * math.sin(bb)), math.cos(bb)))
    for i in range(n_mid + 1):
        xs.append((-x_cap + 2 * x_cap * i / n_mid, 1.0))
    for i in range(1, caps + 1):
        bb = math.pi / 2 * i / caps
        xs.append((x_cap + r_end * math.sin(bb), math.cos(bb)))
    yb = BEAM_BED_Y + inflate
    verts, faces, rings = [], [], []
    for x, k in xs:
        zc, h, d = J.beam_shape(abs(x) / J.BEAM_L)
        kk = k ** 0.9
        ay, az = d / 2 * kk + inflate, h / 2 * kk + inflate
        zc += J.BEAM_Z
        if k < 1e-4:
            rings.append([len(verts)])
            verts.append((x, yb, zc))
            continue
        yc = max(0.0, yb - 0.85 * ay)
        yf = yc - ay
        ys, hz = [], []
        for i in range(levels + 1):
            y = yb + (yf - yb) * math.sin(math.pi / 2 * i / levels)
            q = min(1.0, abs((y - yc) / ay))
            hv = az * max(0.0, 1 - q ** expo) ** (1 / expo)
            if i:
                hv = min(hv, hz[-1] + abs(y - ys[-1]))   # 45 deg growth limit
            ys.append(y)
            hz.append(hv)
        hz[-1] = 0.0
        ring = []
        for i in range(levels + 1):
            ring.append(len(verts))
            verts.append((x, ys[i], zc + hz[i]))
        for i in range(levels - 1, -1, -1):
            ring.append(len(verts))
            verts.append((x, ys[i], zc - hz[i]))
        rings.append(ring)
    M = len(rings[1])
    for i in range(len(rings) - 1):
        A, B = rings[i], rings[i + 1]
        for j in range(M):
            j2 = (j + 1) % M
            if len(A) == 1:
                faces.append((A[0], B[j2], B[j]))
            elif len(B) == 1:
                faces.append((A[j], A[j2], B[0]))
            else:
                faces.append((A[j], A[j2], B[j2], B[j]))
    return verts, faces


def beam_bottom_at(x, y):
    """lowest z of the print beam at (x, y) (approx., from its sections)."""
    zc, h, d = J.beam_shape(abs(x) / J.BEAM_L)
    ay, az = d / 2, h / 2
    yc = max(0.0, BEAM_BED_Y - 0.85 * ay)
    q = min(1.0, abs((y - yc) / ay))
    return J.BEAM_Z + zc - az * (1 - q ** 2.6) ** (1 / 2.6)


HOOK_X = J.HOOK_S * J.BEAM_L
HOOK_Y = BEAM_BED_Y - HOOK_T / 2                   # centre plane of the hooks
# curl centre: hook tip (zc + 0.40) stays 3.5 mm below the beam -> room to hang the loop
HOOK_ZC = min(beam_bottom_at(HOOK_X + s, y) for s in (-0.5, 0, 0.5)
              for y in (BEAM_BED_Y - HOOK_T, BEAM_BED_Y)) - 0.35 - 0.40


def hook_outline(sx):
    """J-hook in the XZ plane, curl at the bottom, open end pointing up/outwards."""
    hx, zc, ri, ro = HOOK_X, HOOK_ZC, HOOK_RI, HOOK_RO
    top = beam_bottom_at(HOOK_X, HOOK_Y) + 0.45     # buried in the beam
    tip = zc + 0.30
    rc, rr = (ri + ro) / 2, (ro - ri) / 2
    pts = [(hx - ro, top), (hx - ro, zc)]
    pts += [(hx + ro * math.cos(math.pi + math.pi * i / 24),
             zc + ro * math.sin(math.pi + math.pi * i / 24)) for i in range(1, 24)]
    pts += [(hx + ro, zc)]
    pts += [(hx + rc + rr * math.cos(math.pi * i / 12), tip + rr * math.sin(math.pi * i / 12))
            for i in range(13)]
    pts += [(hx + ri, zc)]
    pts += [(hx + ri * math.cos(-math.pi * i / 24), zc + ri * math.sin(-math.pi * i / 24))
            for i in range(1, 24)]
    pts += [(hx - ri, zc), (hx - ri, top)]
    if sx < 0:                       # mirror for the left hook (keep a valid winding)
        pts = [(-x, z) for x, z in reversed(pts)]
    return pts, tip + rr


def build_scale_parts(coll):
    prof = J.column_profile()
    # top of the column = just above the beam inside the hub
    zt = max(J.BEAM_Z + J.beam_shape(abs(x) / J.BEAM_L)[0] + J.beam_shape(abs(x) / J.BEAM_L)[1] / 2
             for x in [i * 0.05 for i in range(-20, 21)]) + 0.08

    # 1) COLUMN: base -> hub, open U-slot for the beam, built-in 3.8 mm pin
    col = turned_part("S1_Column", coll, prof, 0.0, zt, True)
    v, f = print_beam_geometry(inflate=CLR)
    slot = J.make_object("slot", v, f, coll, smooth=False)
    # open the slot straight up so the beam can be dropped in from above
    union(slot, [box(coll, -1.3, 1.3, -0.56 - CLR, BEAM_BED_Y + CLR, J.BEAM_Z, zt + 1)])
    boolean(col, slot)
    pin_pts = [(0, 13.6), (0.19, 13.6), (0.19, zt + 0.66), (0.15, zt + 0.70), (0, zt + 0.70)]
    union(col, [lathe_from_points("pin", pin_pts, coll, segs=32)])
    add(col, note="standing on its base; beam drops into the slot")

    # 2) TOP: hub cap + collars + finial, hole for the pin
    add(turned_part("S2_Top", coll, prof, zt, 20.0, True, bottom_hole=(PIN4, 0.8)),
        note="standing")

    # 3) BEAM: one piece, printed face-down on its flat back, hooks built in
    v, f = print_beam_geometry()
    beam = J.make_object("S3_Beam", v, f, coll)
    hooks = []
    for sx in (-1, 1):
        pts, _ = hook_outline(sx)
        hooks.append(extrude_polygon("hook", coll, pts, (1, 0, 0), (0, 0, 1), (0, 1, 0),
                                     BEAM_BED_Y - HOOK_T, BEAM_BED_Y))
    union(beam, hooks)
    boolean(beam, teardrop(coll, (0, 0, 12.5), (0, 0, 17.5), PIN4, up=(0, -1, 0)))
    add(beam, Matrix.Rotation(-math.pi / 2, 4, "X"),
        note="front face up, flat back on the bed")

    # 4) PAN + 3 CHAINS + HANGING LOOP: one piece (print 2)
    p = J.Profile(0, 0)
    p.line(1.80, 0.0, 0.0)
    p.bez((2.15, 0.35), (2.40, 0.70), (2.42, 1.18), n=30)
    p.arc((2.30, 1.18), 0.12, 0, 180, n=16)
    p.bez((2.17, 0.70), (1.95, 0.34), (1.30, 0.30), n=26)
    p.line(0.0, 0.30, 0.0)
    pan = J.lathe("S4_Pan_with_Chains", p, coll, [], segs=128, max_seg=0.1)
    apply_matrix(pan, Matrix.Translation(Vector((HOOK_X, HOOK_Y, J.PAN_BOTTOM)) * CM))

    # hanging loop (YZ plane) whose top bar sits inside the J-hook's curl
    LW, LB, LT, LS = 0.56, 0.10, 0.12, 0.10
    l_len = 2 * (LW / 2) / math.tan(math.radians(28)) + LS
    apex_out = HOOK_ZC + LB / math.sin(math.radians(28))
    node = Vector((HOOK_X, HOOK_Y, apex_out - l_len))
    lv, lf = [], []
    plate_link(lv, lf, node, (0, 0, 1), (0, 1, 0), LW, l_len, LB, LT, side=LS)
    others = [J.make_object("loop", lv, lf, coll, smooth=False)]

    # three chains of flat diamond links, alternating +-45 deg to the radial plane
    W, b, t, L0 = 0.28, 0.08, 0.10, 0.62
    overlap = 0.15
    for ang in (90, 210, 330):
        a = math.radians(ang)
        radial = Vector((math.cos(a), math.sin(a), 0))
        rim = Vector((HOOK_X, HOOK_Y, J.PAN_BOTTOM + 1.30 - 0.04)) + radial * 2.30
        axis = (node - rim)
        length = axis.length
        axis.normalize()
        n = max(2, int(round((length - L0) / (L0 - overlap))) + 1)
        pitch = (length - L0) / (n - 1)
        cv, cf = [], []
        for i in range(n):
            rot = Matrix.Rotation(math.radians(45 if i % 2 == 0 else -45), 3, (0, 0, 1))
            wdir = rot @ radial
            plate_link(cv, cf, rim + axis * (pitch * i), axis, wdir, W, L0, b, t)
        others.append(J.make_object("chain", cv, cf, coll, smooth=False))
    union(pan, others)
    add(pan, copies=2, note="standing on its foot; chains + loop print with it")


def build_gavel_parts(coll):
    head_c = Vector((0, 0, HEAD_C_Z))

    # 1) BASE: stand + sound block + handle rest + pin, one piece
    st = box(coll, -3.7, 13.7, -3.6, 3.6, 0, STAND_H, "G1_Base")
    bm = bmesh.new()
    bm.from_mesh(st.data)
    edges = [e for e in bm.edges if not all(abs(v.co.z) < 1e-6 for v in e.verts)]
    bmesh.ops.bevel(bm, geom=edges, offset=0.22 * CM, segments=5, profile=0.6,
                    affect="EDGES")
    bm.to_mesh(st.data)
    bm.free()
    boolean(st, box(coll, 3.6, J.REST_X - 1.6, -0.55, 0.55, STAND_H - 0.32, STAND_H + 1))
    blk = turned_part("blk", coll, J.sound_block_profile(), 0.0, BLOCK_H, True)
    apply_matrix(blk, Matrix.Translation(Vector((0, 0, STAND_H - 0.02)) * CM))
    rp, rim_z, zc = J.rest_profile(STAND_H, HEAD_C_Z, 0.60, with_cup=False)
    rz = simplify(clamp_overhang(envelope(rp, 0.0, rim_z), True))
    top_r = rz[-1][0]
    path = [(0, 0.0)] + [tuple(q) for q in rz] + [(top_r, zc - 0.12), (0, zc - 0.12)]
    rest = lathe_from_points("rest", path, coll, segs=96)
    apply_matrix(rest, Matrix.Translation(Vector((J.REST_X, 0, STAND_H - 0.02)) * CM))
    # saddle = the handle's own shape (+clearance) cut out of the rest's top
    hz = envelope(J.handle_profile(), J.REST_X - 1.5, J.HANDLE_LEN)
    hz = simplify([[r + CLR + 0.005, z] for r, z in hz])
    cut = lathe_from_points("saddle", [(0, hz[0][1])] + [tuple(q) for q in hz] +
                            [(0, hz[-1][1])], coll, segs=96)
    apply_matrix(cut, Matrix.Translation(head_c * CM) @ Matrix.Rotation(math.pi / 2, 4, "Y"))
    boolean(rest, cut)
    top = STAND_H + BLOCK_H
    pin_pts = [(0, top - 0.2), (0.24, top - 0.2), (0.24, top + 0.71), (0.20, top + 0.75),
               (0, top + 0.75)]
    pn = lathe_from_points("pin", pin_pts, coll, segs=32)
    union(st, [blk, rest, pn])
    add(st, group="gavel", note="flat on the bed")

    # 2) HEAD: one piece incl. the band (switch to gold filament for the band)
    hp = J.head_half_profile().mirrored()
    bp = J.Profile(1.30, -1.40)
    for r, z, f in ((1.46, -1.40, 0.0), (1.50, -1.28, 0.02), (1.46, -1.20, 0.015),
                    (1.46, 1.20, 0.015), (1.50, 1.28, 0.02), (1.46, 1.40, 0.0),
                    (1.30, 1.40, 0.0)):
        bp.line(r, z, f)
    z0, z1 = -J.HEAD_HALF, J.HEAD_HALF
    e1, e2 = envelope(hp, z0, z1), envelope(bp, z0, z1)
    merged = {round(z, 5): r for r, z in e1}
    for r, z in e2:
        merged[round(z, 5)] = max(r, merged.get(round(z, 5), 0.0))
    rz = [[merged[z], z] for z in sorted(merged)]
    rz = simplify(clamp_overhang(rz, True))
    hr, hd = PIN4 + 0.05, 0.8
    path = [(0, z0 + hd + hr), (hr, z0 + hd), (hr, z0 + 0.04), (hr + 0.04, z0)]
    path += [tuple(q) for q in rz] + [(0, z1)]
    head = lathe_from_points("G2_Head", path, coll, segs=128)
    boolean(head, teardrop(coll, (0.55, 0, 0), (2.5, 0, 0), 0.48 + CLR + 0.005))
    apply_matrix(head, Matrix.Translation(head_c * CM))
    add(head, group="gavel", note="striking face down; gold filament 21.0-49.0 mm")

    # 3) HANDLE
    handle = turned_part("G3_Handle", coll, J.handle_profile(), 0.6, J.HANDLE_LEN, True)
    apply_matrix(handle, Matrix.Translation(head_c * CM) @ Matrix.Rotation(math.pi / 2, 4, "Y"))
    add(handle, Matrix.Rotation(-math.pi / 2, 4, "Y"), group="gavel",
        note="standing on the tenon end - use a brim")


# --------------------------------------------------------------------------
# checks + export
# --------------------------------------------------------------------------


def _non_manifold(bm):
    return sum(1 for e in bm.edges if not e.is_manifold)


def clean(ob):
    """If booleans left degenerate bits, merge vertices closer than 1 micron and
    drop zero-area faces - kept only when it really reduces non-manifold edges."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    before = _non_manifold(bm)
    if before:
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
        bmesh.ops.dissolve_degenerate(bm, dist=1e-6, edges=bm.edges)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        if _non_manifold(bm) < before:
            bm.to_mesh(ob.data)
            ob.data.update()
    bm.free()


def to_print_orientation(ob, rot):
    clean(ob)
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
        ob.data.materials.append(wood)
        if ob.name.startswith("G2"):        # band = gold filament section
            ob.data.materials.append(gold)
            ob.data.update()
            idx = [1 if BAND_Z0 * CM <= p.center.z <= BAND_Z1 * CM else 0
                   for p in ob.data.polygons]
            ob.data.polygons.foreach_set("material_index", idx)
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
    lift = {"S1": 0, "S2": 4.0, "S3": 2.0, "S4": -1.5, "G1": 0, "G2": 3.0, "G3": 3.0}
    for ob, rot, copies, group, note in PARTS:
        base = assembled[ob.name]
        variants = [Matrix.Identity(4)]
        if ob.name.startswith("S4"):        # second pan hangs on the left hook
            variants = [Matrix.Identity(4),
                        Matrix.Translation((-2 * HOOK_X * CM, 0, 0))]
        for k, V in enumerate(variants):
            d = ob.copy()
            d.name = ob.name + f"_asm{k}"
            off = Vector((0, 0, lift[ob.name[:2]] * CM))
            if ob.name.startswith("G3"):
                off.x += 0.03
            if group == "gavel":
                off += Vector((-0.30, 0, 0))
            d.matrix_world = Matrix.Translation(off) @ V @ base
            ex.objects.link(d)

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
