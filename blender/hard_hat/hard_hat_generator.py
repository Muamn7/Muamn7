"""
Vented cap-style safety helmet (hard hat) -- procedural Blender model.

Shell only: no suspension, no straps, no fabric. The shell sits directly on
the head with no extra room: where it touches the head, the inner wall measures
exactly HEAD_CIRC around (58 cm). Change HEAD_CIRC for another size; the whole
helmet, height included, is rescaled to it and the wall stays TH_REAL thick.

Run inside Blender (Scripting tab -> Open -> Run Script; the helmet is built
in a new scene called "HardHat", takes about a minute), or headless:
    blender --background --python hard_hat_generator.py -- /path/to/output.blend

Shape parameters are in "design millimetres"; the solved SCALE turns them into
real millimetres. The model is built at real-world scale (1 Blender unit = 1 m,
scene shows millimetres).
"""

import math
import sys

import bpy  # noqa: E402  (bpy must be imported before bmesh)
import bmesh
import numpy as np
from mathutils import Matrix, Vector

# --------------------------------------------------------------------------
# Head size and fit
# --------------------------------------------------------------------------
HEAD_CIRC = 580.0       # head circumference in mm (58 cm)
TH_REAL = 2.8           # wall thickness of the finished helmet, mm
LIP_BEAD_REAL = 1.8     # extra thickness rolled into the lip / brim edge, mm

# Fit plane: the horizontal plane just above the band step, where the inner
# wall of the dome starts and the shell touches the head (below it the band
# steps outwards and does not touch the head). The generator solves SCALE so
# that the inner wall measures exactly HEAD_CIRC around in this plane, with
# no gap. Everything scales together, so the height follows the size.
FIT_ABOVE_LEDGE = 1.0   # design mm above the highest point of the band step

SCALE = 1.0             # design mm -> real mm (solved in build_shell_rings)
TH = TH_REAL            # wall thickness in design mm (set by set_scale)
LIP_BEAD = LIP_BEAD_REAL
MM = 0.001              # one design millimetre in metres (set by set_scale)
REAL_MM = 0.001
HEAD_TAG = "%gcm" % (HEAD_CIRC / 10)


def set_scale(s):
    global SCALE, TH, LIP_BEAD, MM
    SCALE = s
    TH = TH_REAL / s
    LIP_BEAD = LIP_BEAD_REAL / s
    MM = 0.001 * s


# --------------------------------------------------------------------------
# Shape parameters (design millimetres, see SCALE)
# --------------------------------------------------------------------------
NU = 960            # segments around the helmet
ND_OUT = 230        # rings on the outer dome
ND_IN = 90          # rings on the inner dome (no fine detail inside)
N_CAP = 9           # rings on the rounded lip edge

# Footprint of the shell wall at the rain-gutter ledge (egg shape, wider at back)
A0, DA = 96.5, 1.5  # half width   -> 95 at front-side, 98 at back-side
B0, DB = 123.0, 3.0  # half length -> 120 to the front, 126 to the back
Z_TOP = 150.0       # top of the crown above the brim root
N_SUPER = (2.1, 2.55, 2.35)  # dome superellipse exponent: front, sides, back
APEX_Y = 18.0       # crown apex sits a little behind the centre (forehead slopes back)

# Band (raised strip around the lower shell) and rain gutter
DROP_BACK = 14.0    # how much lower the rim is at the back than at the brim
DROP_SIDE = 5.0     # extra dip of the rim over the ears
R1, R2 = 1.5, 3.6   # ledge fillets (concave, convex)

# Side panel recess (the big rounded "D" on each side)
PANEL_DEPTH = 2.8
PANEL_EDGE = 4.0            # width of the sharp outer step
PANEL_V = (5.0, 134.0)      # bottom / top limit (mm above the ledge)
PANEL_C_U = -10.0           # where the front "C" sweep meets top and bottom
PANEL_C_REACH = 92.0        # how far forward the "C" reaches
PANEL_REAR = 100.0          # rear limit
PANEL_R = dict(tl=0.0, bl=0.0, tr=32.0, br=6.0)  # corner radii of the rear part
RIB = (0.6, 2.6, 1.2)       # bead around the panel: height, offset, width

# Vent strip on the crown (each side)
VENT_CENTER = (17.0, 142.0)  # (u, v)
VENT_HALF = (27.5, 4.0)
VENT_DEPTH = 1.3
VENT_SLOTS_U = (-18.75, -6.25, 6.25, 18.75)
VENT_SLOT = (9.5, 4.4)      # slot length (along strip), width

# Accessory slot boxes (ear-muff / visor adapters)
ACC_U = 8.0
ACC_SIZE = (38.0, 7.0, 26.0)  # width, projection, height

# Suspension key sockets on the inside of the band: none. The shell sits
# directly on the head, so there is no harness to clip in and the sockets
# would only press on the head. (42.0, 138.0, 222.0, 318.0) puts them back.
SOCKET_PHI = ()
SOCKET_SIZE = (16.0, 5.0, 16.0)  # width, inward projection, height


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def lerp(a, b, t):
    return a + (b - a) * t


def footprint(phi):
    """Outer wall at ledge height. phi=0 front (-Y), phi=90deg right (+X)."""
    c, s = np.cos(phi), np.sin(phi)
    a = A0 - DA * c
    b = B0 - DB * c
    r = 1.0 / np.sqrt((s / a) ** 2 + (c / b) ** 2)
    return np.stack([r * s, -r * c], -1), r


def footprint_frame(phi):
    eps = 1e-4
    p, _ = footprint(phi)
    t = footprint(phi + eps)[0] - footprint(phi - eps)[0]
    t /= np.linalg.norm(t, axis=-1, keepdims=True)
    n = np.stack([t[..., 1], -t[..., 0]], -1)  # outward
    return p, t, n


def perimeter_coordinate(phi):
    """Signed arc length along the footprint from the side centre (phi=90deg),
    positive towards the back, mirrored for the left side."""
    dense = np.linspace(0.0, math.pi, 20001)
    p, _ = footprint(dense)
    seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    cum -= np.interp(math.pi / 2, dense, cum)
    ph = np.mod(phi, 2 * math.pi)
    ph = np.where(ph > math.pi, 2 * math.pi - ph, ph)
    return np.interp(ph, dense, cum)


def brim_weight(phi):
    c = np.cos(phi)
    c75 = math.cos(math.radians(75))
    return smoothstep(0.0, 1.0, (c - c75) / (1.0 - c75))


# --------------------------------------------------------------------------
# Profile of the lower shell (ledge, band, gutter / brim), per spoke.
# Coordinates (h, z): h = horizontal offset along the footprint normal.
# --------------------------------------------------------------------------
SEG_COUNTS = dict(s1=3, s2=2, s3=6, s4=26, s5=12, s6=36)


def segment(p0, psi0, psi1, L, n):
    """Constant-curvature segment, vectorised over spokes. Angles in radians.
    Returns samples at fractions k/n, k=1..n (start excluded)."""
    f = (np.arange(1, n + 1) / n)[None, :]
    dpsi = (psi1 - psi0)[:, None]
    psi = psi0[:, None] + dpsi * f
    s = L[:, None] * f
    straight = np.abs(dpsi) < 1e-7
    r = np.where(straight, 1.0, L[:, None] / np.where(straight, 1.0, dpsi))
    h_arc = r * (np.sin(psi) - np.sin(psi0)[:, None])
    z_arc = r * (np.cos(psi0)[:, None] - np.cos(psi))
    h_lin = s * np.cos(psi0)[:, None]
    z_lin = s * np.sin(psi0)[:, None]
    h = np.where(straight, h_lin, h_arc)
    z = np.where(straight, z_lin, z_arc)
    pts = np.stack([p0[:, 0:1] + h, p0[:, 1:2] + z], -1)
    return pts


def rim_heights(phi):
    c, s = np.cos(phi), np.sin(phi)
    z_bb = -DROP_BACK * (1 - c) / 2 - DROP_SIDE * s ** 2      # band bottom
    h_band = 26.0 + 12.0 * s ** 2 + 4.0 * (1 - c) / 2         # band height
    return z_bb, z_bb + h_band


def lower_profile(phi):
    c = np.cos(phi)
    nphi = len(phi)
    wb = brim_weight(phi)
    z_bb, z_L = rim_heights(phi)

    # ledge width: a crease at the forehead, a real step along sides and back
    wL = 1.0 + 6.0 * (1.0 - smoothstep(math.cos(math.radians(70)),
                                       math.cos(math.radians(25)), c))
    beta = np.minimum(math.radians(75), np.arccos(np.clip(1 - wL / (R1 + R2), -1, 1)))
    Ls = np.maximum(0.0, (wL - (R1 + R2) * (1 - np.cos(beta))) / np.sin(beta))

    th0 = np.radians(lerp(-8.0, -14.0, wb))     # lip start angle
    th1 = np.radians(lerp(35.0, -30.0, wb))     # lip end angle (gutter up / brim down)
    r3 = lerp(4.5, 9.0, wb)                     # band -> lip fillet
    L_lip = 8.0 + 27.0 * wb                     # gutter width / brim length

    d90 = np.full(nphi, -math.pi / 2)
    d88 = np.full(nphi, math.radians(-88))
    p0 = np.stack([np.zeros(nphi), z_L], -1)
    out = [p0[:, None, :]]

    a1 = d90 + beta
    s1 = segment(p0, d90, a1, R1 * beta, SEG_COUNTS['s1'])
    s2 = segment(s1[:, -1], a1, a1, np.maximum(Ls, 1e-3), SEG_COUNTS['s2'])
    s3 = segment(s2[:, -1], a1, d88, R2 * np.abs(d88 - a1), SEG_COUNTS['s3'])
    dz5 = r3 * (np.cos(d88) - np.cos(th0))
    z3 = s3[:, -1, 1]
    L4 = (z3 + dz5 - z_bb) / math.sin(math.radians(88))
    s4 = segment(s3[:, -1], d88, d88, L4, SEG_COUNTS['s4'])
    s5 = segment(s4[:, -1], d88, th0, r3 * (th0 - d88), SEG_COUNTS['s5'])
    s6 = segment(s5[:, -1], th0, th1, L_lip, SEG_COUNTS['s6'])
    out += [s1, s2, s3, s4, s5, s6]
    prof = np.concatenate(out, axis=1)
    # arc length (negative, downward from the ledge start)
    seg = np.linalg.norm(np.diff(prof, axis=1), axis=2)
    v = -np.concatenate([np.zeros((nphi, 1)), np.cumsum(seg, axis=1)], axis=1)
    return prof, v, z_L


def dome(phi, z_L, nd):
    """Superellipse dome from apex to the ledge, uniform arc length.
    Returns points [NU, nd, 3] (apex first, base excluded), sigma, v."""
    p, r = footprint(phi)
    al = np.linspace(0.0, math.pi / 2, 2400)
    c, s = np.cos(phi), np.sin(phi)
    nf, ns, nb = N_SUPER
    n_sup = np.where(c > 0, nf + (ns - nf) * s ** 2, nb + (ns - nb) * s ** 2)
    H = Z_TOP - z_L
    pts = np.empty((len(phi), nd, 3))
    sg = np.empty((len(phi), nd))
    vv = np.empty((len(phi), nd))
    for i in range(len(phi)):
        e = 2.0 / n_sup[i]
        sig = np.sin(al) ** e
        zr = np.cos(al) ** e
        x = sig * p[i, 0]
        y = APEX_Y + sig * (p[i, 1] - APEX_Y)
        z = z_L[i] + H[i] * zr
        d = np.sqrt(np.diff(x) ** 2 + np.diff(y) ** 2 + np.diff(z) ** 2)
        cum = np.concatenate([[0.0], np.cumsum(d)])
        tgt = np.linspace(0.0, cum[-1], nd + 1)[:-1]
        pts[i, :, 0] = np.interp(tgt, cum, x)
        pts[i, :, 1] = np.interp(tgt, cum, y)
        pts[i, :, 2] = np.interp(tgt, cum, z)
        sg[i] = np.interp(tgt, cum, sig)
        vv[i] = cum[-1] - tgt
    return pts, sg, vv


def base_surface(nd):
    phi = np.arange(NU) * (2 * math.pi / NU)
    prof, v_low, z_L = lower_profile(phi)
    P, T, N2 = footprint_frame(phi)
    low = np.empty(prof.shape[:2] + (3,))
    low[..., 0] = P[:, None, 0] + prof[..., 0] * N2[:, None, 0]
    low[..., 1] = P[:, None, 1] + prof[..., 0] * N2[:, None, 1]
    low[..., 2] = prof[..., 1]
    dpts, sig, v_d = dome(phi, z_L, nd)
    pts = np.concatenate([dpts, low], axis=1)
    sigma = np.concatenate([sig, np.ones(low.shape[:2])], axis=1)
    v = np.concatenate([v_d, v_low], axis=1)
    U = perimeter_coordinate(phi)
    u = U[:, None] * sigma
    return phi, pts, u, v


def grid_normals(pts):
    dphi = np.roll(pts, -1, axis=0) - np.roll(pts, 1, axis=0)
    dt = np.empty_like(pts)
    dt[:, 1:-1] = pts[:, 2:] - pts[:, :-2]
    dt[:, 0] = pts[:, 1] - pts[:, 0]
    dt[:, -1] = pts[:, -1] - pts[:, -2]
    n = np.cross(dt, dphi)
    ln = np.linalg.norm(n, axis=-1, keepdims=True)
    n = n / np.maximum(ln, 1e-12)
    n[:, 0] = (0.0, 0.0, 1.0)  # apex
    return n


def sd_round_box(u, v, u0, u1, v0, v1, r):
    cu, cv = (u0 + u1) / 2, (v0 + v1) / 2
    hu, hv = (u1 - u0) / 2, (v1 - v0) / 2
    x, y = u - cu, v - cv
    rr = np.where(x > 0, np.where(y > 0, r['tr'], r['br']),
                  np.where(y > 0, r['tl'], r['bl']))
    qx = np.abs(x) - hu + rr
    qy = np.abs(y) - hv + rr
    return (np.minimum(np.maximum(qx, qy), 0.0)
            + np.hypot(np.maximum(qx, 0.0), np.maximum(qy, 0.0)) - rr)


def sd_ellipse(u, v, cu, cv, a, b):
    x, y = (u - cu) / a, (v - cv) / b
    k0 = np.hypot(x, y)
    k1 = np.hypot(x / a, y / b)
    return k0 * (k0 - 1.0) / np.maximum(k1, 1e-9)


def smin(a, b, k):
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b + (a - b) * h - k * h * (1.0 - h)


def panel_sdf(u, v):
    v0, v1 = PANEL_V
    e = sd_ellipse(u, v, PANEL_C_U, (v0 + v1) / 2, PANEL_C_REACH, (v1 - v0) / 2)
    b = sd_round_box(u, v, PANEL_C_U, PANEL_REAR, v0, v1, PANEL_R)
    d = smin(e, b, 3.0)
    return np.where(v > 0.0, d, 1e3)


def vent_sdf(u, v):
    cu, cv = VENT_CENTER
    r = min(VENT_HALF[1] - 0.2, 3.4)
    rr = dict(tl=r, tr=r, bl=r, br=r)
    d = sd_round_box(u, v, cu - VENT_HALF[0], cu + VENT_HALF[0],
                     cv - VENT_HALF[1], cv + VENT_HALF[1], rr)
    return np.where(v > 0.0, d, 1e3)


# --------------------------------------------------------------------------
# Shell
# --------------------------------------------------------------------------
def inner_offset(Ib, Ni, m_soft):
    """Inner wall: the base surface pushed in by the wall thickness, a soft
    copy of the panel recess (so the wall stays >= TH) and a bead at the lip."""
    nb = 14
    bead = np.zeros(Ib.shape[1])
    bead[-nb:] = LIP_BEAD * smoothstep(0.0, 1.0, np.linspace(0.0, 1.0, nb))
    return Ib - Ni * (TH + PANEL_DEPTH * m_soft + bead[None, :])[..., None]


def fit_plane_z():
    _, z_L = rim_heights(np.linspace(0.0, 2 * math.pi, 3601))
    return float(z_L.max()) + FIT_ABOVE_LEDGE


def horizontal_section(I, z):
    """Where each meridian of the inner wall first crosses height z on its
    way down from the crown: [NU, 2], in the units of I."""
    zc = I[..., 2]
    j = np.argmax(zc < z, axis=1)
    rows = np.arange(I.shape[0])
    a, b = I[rows, j - 1], I[rows, j]
    t = (a[:, 2] - z) / (a[:, 2] - b[:, 2])
    return a[:, :2] + t[:, None] * (b[:, :2] - a[:, :2])


def loop_length(p):
    return float(np.sum(np.linalg.norm(np.roll(p, -1, axis=0) - p, axis=1)))


def solve_scale(Ib, Ni, m_soft, z_fit):
    """SCALE that makes the inner wall exactly HEAD_CIRC around at z_fit."""
    s = 0.85
    for _ in range(50):
        set_scale(s)
        circ = s * loop_length(horizontal_section(inner_offset(Ib, Ni, m_soft), z_fit))
        if abs(circ - HEAD_CIRC) < 1e-6:
            break
        s *= (HEAD_CIRC + 2 * math.pi * TH_REAL) / (circ + 2 * math.pi * TH_REAL)
    return s


def build_shell_rings():
    # inner base surface first: the size of the helmet is set from it
    _, Ib, ui, vi = base_surface(ND_IN)
    Ni = grid_normals(Ib)
    m_soft = 1.0 - smoothstep(-5.0, 5.0, panel_sdf(ui, vi) - 3.0)
    z_fit = fit_plane_z()
    set_scale(solve_scale(Ib, Ni, m_soft, z_fit))
    I = inner_offset(Ib, Ni, m_soft)
    fit = (horizontal_section(I, z_fit), z_fit, float(I[0, 0, 2]))

    # outer
    phi, Ob, u, v = base_surface(ND_OUT)
    Nb = grid_normals(Ob)
    m_panel = 1.0 - smoothstep(-PANEL_EDGE / 2, PANEL_EDGE / 2, panel_sdf(u, v))
    m_vent = 1.0 - smoothstep(-0.8, 0.8, vent_sdf(u, v))
    d_panel = panel_sdf(u, v)
    rib = RIB[0] * np.exp(-0.5 * ((d_panel - RIB[1]) / RIB[2]) ** 2) * smoothstep(0.0, 1.5, v)
    O = Ob - Nb * (PANEL_DEPTH * m_panel + VENT_DEPTH * m_vent - rib)[..., None]

    # rounded lip edge between the two
    oe, ne = Ob[:, -1], Nb[:, -1]
    te = Ob[:, -1] - Ob[:, -2]
    te /= np.linalg.norm(te, axis=-1, keepdims=True)
    rad = (TH + LIP_BEAD) / 2
    ctr = oe - ne * rad
    cap = []
    for k in range(1, N_CAP + 1):
        g = math.pi * k / (N_CAP + 1)
        cap.append(ctr + rad * (math.cos(g) * ne + math.sin(g) * te))
    cap = np.stack(cap, axis=1)
    I[:, -1] = oe - ne * 2 * rad

    rings = np.concatenate([O, cap, I[:, ::-1]], axis=1)  # [NU, R, 3]
    return np.transpose(rings, (1, 0, 2)), (phi, Ob, Nb, u, v), fit


def rings_to_mesh(name, rings):
    R, n, _ = rings.shape
    verts = [tuple(rings[0, 0])]
    for r in range(1, R - 1):
        verts.extend(map(tuple, rings[r]))
    verts.append(tuple(rings[-1, 0]))
    last = len(verts) - 1

    def vid(r, i):
        return 1 + (r - 1) * n + (i % n)

    faces = []
    for i in range(n):
        faces.append((0, vid(1, i), vid(1, i + 1)))
    for r in range(1, R - 2):
        for i in range(n):
            faces.append((vid(r, i), vid(r + 1, i), vid(r + 1, i + 1), vid(r, i + 1)))
    for i in range(n):
        faces.append((vid(R - 2, i), last, vid(R - 2, i + 1)))
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(c * MM for c in v) for v in verts], [], faces)
    me.validate()
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    return me


# --------------------------------------------------------------------------
# Detail solids (booleans)
# --------------------------------------------------------------------------
def rounded_box(name, size, radius, segments=4, frame=Matrix.Identity(4)):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    if radius > 0:
        bmesh.ops.bevel(bm, geom=bm.edges[:] + bm.verts[:], offset=radius,
                        segments=segments, profile=0.5, affect='EDGES',
                        clamp_overlap=True)
    bmesh.ops.transform(bm, matrix=frame, verts=bm.verts)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    return ob


def frame_matrix(origin, xaxis, yaxis, zaxis):
    m = Matrix.Identity(4)
    for i in range(3):
        m[i][0], m[i][1], m[i][2] = xaxis[i], yaxis[i], zaxis[i]
        m[i][3] = origin[i]
    return m


def surface_frame_at(phi_grid, pts, nrm, u, v, uc, vc, sides=(1, -1)):
    """Nearest grid point to chart coordinate (uc, vc) on each side."""
    frames = []
    for sd in sides:
        x_ok = (pts[..., 0] * sd) > 0
        d = np.where(x_ok, (u - uc) ** 2 + (v - vc) ** 2, np.inf)
        i, j = np.unravel_index(np.argmin(d), d.shape)
        p = pts[i, j]
        n = nrm[i, j]
        tu = pts[(i + 1) % NU, j] - pts[(i - 1) % NU, j]
        tu = tu - n * np.dot(tu, n)
        tu /= np.linalg.norm(tu)
        if sd < 0:
            tu = -tu  # keep "u" pointing to the back on both sides
        tv = np.cross(n, tu)
        frames.append((p, tu, tv, n))
    return frames


def link(ob, coll):
    coll.objects.link(ob)
    return ob


def apply_boolean(target, operand, operation):
    mod = target.modifiers.new("bool", 'BOOLEAN')
    mod.operation = operation
    mod.solver = 'MANIFOLD'
    if operand.type == 'MESH':
        mod.operand_type = 'OBJECT'
        mod.object = operand
    with bpy.context.temp_override(object=target, active_object=target):
        bpy.ops.object.modifier_apply(modifier=mod.name)


def build_details(shell, data, coll):
    phi, Ob, Nb, u, v = data
    Nb_out = Nb

    # ---- vent slots: through holes on both sides of the crown ----
    for us in VENT_SLOTS_U:
        for (p, tu, tv, n) in surface_frame_at(phi, Ob, Nb_out, u, v,
                                               VENT_CENTER[0] + us, VENT_CENTER[1]):
            m = frame_matrix(Vector(p * MM), Vector(tu), Vector(tv), Vector(n))
            cut = rounded_box("vent_cut", (VENT_SLOT[0] * MM, VENT_SLOT[1] * MM, 30 * MM),
                              1.4 * MM, 3)
            cut.matrix_world = m
            link(cut, coll)
            apply_boolean(shell, cut, 'DIFFERENCE')
            bpy.data.objects.remove(cut)

    # ---- accessory slot boxes on the band (both sides) ----
    W, D, Hh = ACC_SIZE
    U = perimeter_coordinate(phi)
    i_r = int(np.argmin(np.abs(np.where(phi < math.pi, U - ACC_U, 1e9))))
    for sd in (1, -1):
        i = i_r if sd > 0 else (NU - i_r) % NU
        ph = phi[i]
        P, T, N2 = footprint_frame(np.array([ph]))
        prof, _, _ = lower_profile(np.array([ph]))
        z_bb, _ = rim_heights(np.array([ph]))
        z_bb = float(z_bb[0])
        # band face position at mid height of the box
        z_mid = z_bb - 0.5 + Hh / 2
        seg = prof[0]
        k4 = 1 + SEG_COUNTS['s1'] + SEG_COUNTS['s2'] + SEG_COUNTS['s3']
        band = seg[k4:k4 + SEG_COUNTS['s4'] + 1]
        h_face = float(np.interp(z_mid, band[::-1, 1], band[::-1, 0]))
        n3 = Vector((N2[0, 0], N2[0, 1], 0.0))
        t3 = Vector((T[0, 0], T[0, 1], 0.0)) * (1 if sd > 0 else -1)
        z3 = Vector((0, 0, 1))
        x_axis = t3
        y_axis = n3
        z_axis = x_axis.cross(y_axis)
        if z_axis.z < 0:
            x_axis = -x_axis
            z_axis = -z_axis
        base = Vector((P[0, 0], P[0, 1], 0.0)) + n3 * h_face
        embed = 2.2
        ctr = base + n3 * ((D + embed) / 2 - embed) + z3 * z_mid
        box = rounded_box("acc_box", (W * MM, (D + embed) * MM, Hh * MM), 1.6 * MM, 4)
        box.matrix_world = frame_matrix(ctr * MM, x_axis, y_axis, z_axis)
        link(box, coll)
        apply_boolean(shell, box, 'UNION')
        bpy.data.objects.remove(box)

        # slot opening (from below, through the gutter floor)
        cw, ct = W - 6.0, 3.2
        c_lo, c_hi = z_bb - 14.0, z_bb - 0.5 + Hh - 5.0
        cctr = base + n3 * (1.2 + ct / 2) + z3 * ((c_lo + c_hi) / 2)
        cut = rounded_box("acc_cut", (cw * MM, ct * MM, (c_hi - c_lo) * MM), 0.8 * MM, 2)
        cut.matrix_world = frame_matrix(cctr * MM, x_axis, y_axis, z_axis)
        link(cut, coll)
        apply_boolean(shell, cut, 'DIFFERENCE')
        bpy.data.objects.remove(cut)

    # ---- suspension key sockets on the inner band wall ----
    for deg in SOCKET_PHI:
        ph = math.radians(deg)
        P, T, N2 = footprint_frame(np.array([ph]))
        prof, _, _ = lower_profile(np.array([ph]))
        z_bb, _ = rim_heights(np.array([ph]))
        z_bb = float(z_bb[0])
        sw, sp, sh = SOCKET_SIZE
        z0, z1 = z_bb + 5.0, z_bb + 5.0 + sh
        k4 = 1 + SEG_COUNTS['s1'] + SEG_COUNTS['s2'] + SEG_COUNTS['s3']
        band = prof[0][k4:k4 + SEG_COUNTS['s4'] + 1]
        h_face = float(np.interp((z0 + z1) / 2, band[::-1, 1], band[::-1, 0]))
        n3 = Vector((N2[0, 0], N2[0, 1], 0.0))
        x_axis = Vector((T[0, 0], T[0, 1], 0.0))
        z_axis = x_axis.cross(n3)
        if z_axis.z < 0:
            x_axis, z_axis = -x_axis, -z_axis
        wall = Vector((P[0, 0], P[0, 1], 0.0)) + n3 * (h_face - TH)
        embed = 1.5
        ctr = wall + n3 * ((embed - sp) / 2) + Vector((0, 0, (z0 + z1) / 2))
        blk = rounded_box("socket", (sw * MM, (sp + embed) * MM, sh * MM), 1.2 * MM, 3)
        blk.matrix_world = frame_matrix(ctr * MM, x_axis, n3, z_axis)
        link(blk, coll)
        apply_boolean(shell, blk, 'UNION')
        bpy.data.objects.remove(blk)
        # key slot, open at the bottom
        kz0, kz1 = z0 - 2.0, z1 - 3.5
        kctr = wall - n3 * (sp / 2 + 0.2) + Vector((0, 0, (kz0 + kz1) / 2))
        cut = rounded_box("socket_cut", (10.0 * MM, 2.4 * MM, (kz1 - kz0) * MM), 0.6 * MM, 2)
        cut.matrix_world = frame_matrix(kctr * MM, x_axis, n3, z_axis)
        link(cut, coll)
        apply_boolean(shell, cut, 'DIFFERENCE')
        bpy.data.objects.remove(cut)


# --------------------------------------------------------------------------
# Materials, reference head ring
# --------------------------------------------------------------------------
COLORS = {
    "White": (0.80, 0.80, 0.78),
    "Orange": (0.95, 0.24, 0.02),
    "Red": (0.62, 0.015, 0.02),
    "Blue": (0.0, 0.22, 0.75),
    "Yellow": (0.95, 0.70, 0.0),
}


def make_materials():
    mats = {}
    for name, col in COLORS.items():
        m = bpy.data.materials.get("HardHat_" + name) or bpy.data.materials.new("HardHat_" + name)
        m.use_nodes = True
        nt = m.node_tree
        bsdf = nt.nodes.get("Principled BSDF")
        bsdf.inputs["Base Color"].default_value = (*col, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.16
        if "Coat Weight" in bsdf.inputs:
            bsdf.inputs["Coat Weight"].default_value = 0.6
            bsdf.inputs["Coat Roughness"].default_value = 0.04
        if "Subsurface Weight" in bsdf.inputs and name == "White":
            bsdf.inputs["Subsurface Weight"].default_value = 0.04
            bsdf.inputs["Subsurface Radius"].default_value = (2.0, 2.0, 2.0)
            bsdf.inputs["Subsurface Scale"].default_value = 0.002
        m.diffuse_color = (*col, 1.0)
        m.use_fake_user = True
        mats[name] = m
    return mats


def fit_ring(coll, loop, z):
    """Thin ring whose centre line is the inner wall at the fit plane (real mm):
    the line where the head touches the shell, HEAD_CIRC long."""
    n, sides, tube = len(loop), 12, 0.8
    d = np.roll(loop, -1, axis=0) - np.roll(loop, 1, axis=0)
    bm = bmesh.new()
    rings = []
    for i in range(n):
        c = Vector((loop[i, 0], loop[i, 1], z))
        t = Vector((d[i, 0], d[i, 1], 0.0)).normalized()
        out = Vector((t.y, -t.x, 0.0))
        ring = []
        for k in range(sides):
            g = 2 * math.pi * k / sides
            p = c + (out * math.cos(g) + Vector((0, 0, 1)) * math.sin(g)) * tube
            ring.append(bm.verts.new(p * REAL_MM))
        rings.append(ring)
    for i in range(n):
        r0, r1 = rings[i], rings[(i + 1) % n]
        for k in range(sides):
            bm.faces.new((r0[k], r1[k], r1[(k + 1) % sides], r0[(k + 1) % sides]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    name = "Head_%s_fit_line" % HEAD_TAG
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    link(ob, coll)
    ob.hide_render = True
    return ob


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main(out_path=None):
    if bpy.app.background:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        scene = bpy.context.scene
    else:
        # inside the Blender UI: build in a fresh scene, leave the user's file alone
        scene = bpy.data.scenes.new("HardHat")
        bpy.context.window.scene = scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.length_unit = 'MILLIMETERS'

    coll = bpy.data.collections.new("HardHat")
    scene.collection.children.link(coll)
    tmp = bpy.data.collections.new("_tmp")
    scene.collection.children.link(tmp)

    rings, data, (fit, z_fit, z_crown) = build_shell_rings()
    me = rings_to_mesh("HardHat_Shell", rings)
    shell = bpy.data.objects.new("HardHat", me)
    coll.objects.link(shell)
    bpy.context.view_layer.objects.active = shell

    build_details(shell, data, tmp)
    bpy.data.collections.remove(tmp)

    me = shell.data
    me.shade_smooth()
    if hasattr(me, "set_sharp_from_angle"):
        me.set_sharp_from_angle(angle=math.radians(40))
    mats = make_materials()
    me.materials.clear()          # booleans can leave empty slots behind
    me.materials.append(mats["White"])
    me.polygons.foreach_set("material_index", [0] * len(me.polygons))
    me.update()

    # size report (real mm)
    loop = fit * SCALE
    fit_z = z_fit * SCALE
    size = dict(
        inner_circumference_at_fit_mm=loop_length(loop),
        inner_width_at_fit_mm=float(np.ptp(loop[:, 0])),
        inner_length_at_fit_mm=float(np.ptp(loop[:, 1])),
        fit_plane_height_mm=fit_z,
        inner_depth_mm=(z_crown - z_fit) * SCALE,
    )
    ref = bpy.data.collections.new("Reference_Head_%s" % HEAD_TAG)
    scene.collection.children.link(ref)
    ring = fit_ring(ref, loop, fit_z)

    # keep the generator inside the .blend (Text Editor) so it can be re-run
    try:
        txt = bpy.data.texts.new("hard_hat_generator.py")
        txt.write(open(__file__, encoding="utf-8").read())
    except Exception:
        pass
    shell["head_circumference_mm"] = HEAD_CIRC
    shell["wall_thickness_mm"] = TH_REAL
    shell["shell_scale"] = SCALE
    for k, val in size.items():
        shell[k] = round(val, 2)
    print("HardHat for a %.1f cm head: scale %.5f" % (HEAD_CIRC / 10, SCALE))
    for k, val in size.items():
        print("  %-32s %8.2f" % (k, val))

    if out_path:
        bpy.ops.wm.save_as_mainfile(filepath=out_path, compress=True)
    return shell, ring, size


if __name__ == "__main__":
    argv = sys.argv
    out = argv[argv.index("--") + 1] if "--" in argv else None
    main(out)
