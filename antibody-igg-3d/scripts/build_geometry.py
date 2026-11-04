"""Build every printable part of the IgG antibody model as a closed mesh.

Run with a Python that has numpy, scipy and scikit-image:
    python build_geometry.py OUT.npz

Every position below was measured on the reference picture (861 x 824 px):
    x_mm = (px - 452) * 0.3        z_mm = (703 - py) * 0.3
so the model reproduces the picture at 0.3 mm per pixel.  Units: millimetres.
World frame: X = right, Y = depth (away from the viewer), Z = up, base top Z = 0.
"""
import sys
import time
import numpy as np

from sdf_lib import (F32, Grid, Frame, LumpyDomain, sphere, ellipsoid, capsule,
                     cylinder, hex_prism, torus, smin, smin_all, smin_poly, carve, sweep,
                     mesh_field, sample_grid_field, transform_points, _cap)

H = 0.2          # voxel size for the organic parts (mm)
CLR = 0.15       # radial clearance of every hole (mm) -> 0.3 mm on the diameter
PIN_R = 1.5      # alignment pins: 3 mm x 12 mm
PIN_HALF = 6.0

# Soft, glossy lumps like the picture: (spacing, r_min, r_max, protrusion_min, protrusion_max)
LUMPS_FC = [(6.6, 3.8, 4.8, 2.1, 2.9), (4.8, 2.6, 3.4, 1.4, 2.0)]
LUMPS_HEAVY = [(6.4, 3.5, 4.7, 1.6, 2.4), (4.0, 2.4, 3.2, 1.2, 1.8)]
LUMPS_LIGHT = [(5.8, 3.2, 4.2, 1.5, 2.2), (3.8, 2.3, 3.0, 1.1, 1.7)]
LUMPS_VDOM = [(4.6, 2.6, 3.5, 1.5, 2.2), (3.0, 1.7, 2.4, 1.1, 1.6)]
LUMP_K = 0.65
LUMP_SHRINK = 2.6

WORLD = Frame()
a = np.sqrt(0.5)
OUT = {}
T0 = time.time()


def log(*m):
    print(f"[{time.time() - T0:7.1f}s]", *m, flush=True)


def px(x, y, depth=0.0):
    """Reference-picture pixel -> world point (mm)."""
    return np.array([(x - 452) * 0.3, depth, (703 - y) * 0.3])


def unit(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


def eval_world_fn_on(grid, frame, fn, center_world, radius, fill=50.0):
    out = np.full(grid.shape, F32(fill), dtype=F32)
    sl = grid.box(frame.to_local(center_world), radius)
    if sl is None:
        return out
    P = transform_points(grid.points(sl), frame, WORLD)
    out[sl] = np.broadcast_to(fn(P), out[sl].shape)
    return out


def blobs(nodes, k):
    def fn(P):
        out = None
        for c, r in nodes:
            f = sphere(P, c, r) if np.isscalar(r) else ellipsoid(P, c, r)
            out = f if out is None else smin_poly(out, f, k)
        return out
    return fn


def tube(nodes):
    """Chain of capsules through (centre, radius) nodes - a lobed sausage."""
    def fn(P):
        out = None
        for (c0, r0), (c1, r1) in zip(nodes[:-1], nodes[1:]):
            f = capsule(P, c0, c1, 0.5 * (r0 + r1))
            out = f if out is None else smin_poly(out, f, 1.5)
        return out
    return fn


def lumpy(env, bounds, seed, layers):
    return LumpyDomain(env, bounds, seed, layers=layers, shrink=LUMP_SHRINK, k=LUMP_K)


def first_crossing(field, grid, p0, d, t_max, inside_to_outside):
    d = unit(d)
    ts = np.arange(0, t_max, 0.04)
    pts = np.asarray(p0, float)[None] + ts[:, None] * d[None]
    vals = sample_grid_field(field, grid, pts)
    hit = np.nonzero(vals > 0)[0] if inside_to_outside else np.nonzero(vals < 0)[0]
    if len(hit) == 0:
        raise RuntimeError("ray never crossed the surface")
    return float(ts[hit[0]])


def at(field, grid, p):
    return float(sample_grid_field(field, grid, [p])[0])


# ==========================================================================
# 1. Fc region: two thick lumpy columns, 4 mm apart
#    picture: left column x 378-445, right 460-528, top y 450, bottom y 705
# ==========================================================================
FC_X = 13.2
FC_TOP = px(0, 450)[2]          # 75.9
fc_grid, fc_field = {}, {}
for side, sx, seed in (("left", -1, 11), ("right", 1, 12)):
    rng = np.random.default_rng(seed)
    x0 = sx * FC_X
    nodes = []
    for z in np.linspace(-4.0, FC_TOP - 1.6 - 9.0, 8):
        r = 8.8 * (1 + rng.uniform(-0.08, 0.08))
        nodes.append((np.array([x0 + sx * abs(rng.normal(0, 0.5)), rng.normal(0, 0.6), z]), r))
    nodes[-1] = (np.array([x0, 0, FC_TOP - 1.6 - 9.0]), 9.0)
    env = tube(nodes)
    dom = lumpy(env, ((x0 - 14, -14, -8), (x0 + 14, 14, 82)), seed + 100, LUMPS_FC)
    g = Grid((x0 - 14.5, -14.5, -1.0), (x0 + 14.5, 14.5, 82.0), H)
    f = dom.field(g)
    X, Y, Z = g.points()
    f = np.maximum(f, -(Z - 0.05))              # flat printable bottom
    fc_grid[side], fc_field[side] = g, f
    log("fc", side, g.shape)

# yellow disulfide rungs between the columns (picture y = 655, 573, 508)
BOND_Z = [px(0, 655)[2], px(0, 573)[2], px(0, 508)[2]]
BOND_R = 2.4
bonds = []
for i, z in enumerate(BOND_Z):
    xl = -FC_X + first_crossing(fc_field["left"], fc_grid["left"], (-FC_X, 0, z), (1, 0, 0), 14, True)
    xr = FC_X - first_crossing(fc_field["right"], fc_grid["right"], (FC_X, 0, z), (-1, 0, 0), 14, True)
    bonds.append((np.array([xl - 5.0, 0, z]), np.array([xr + 5.0, 0, z])))
    log(f"bond {i + 1}: z={z:.1f} faces {xl:.2f} .. {xr:.2f}")


def bond_fn(i, extra=0.0):
    a0, a1 = bonds[i]
    d = np.array([extra, 0, 0])
    return lambda P: cylinder(P, a0 - d, a1 + d, BOND_R, 0.6 if extra == 0 else 0.0)


# ==========================================================================
# 2. hinge layout (measured)
#    yellow square: rungs at y 440 / 400, sides at x 427 / 477
#    cyan strands up the outside, cross-bar at y 372, yellow rings at (410, 363)
# ==========================================================================
RUNG_LOW_Z = px(0, 440)[2]       # 78.9
RUNG_TOP_Z = px(0, 400)[2]       # 90.9
SIDE_X = 7.2
STRAND_X = 9.9
CROSS_Z = px(0, 372)[2]          # 99.3
RING_C = {"L": px(408, 363), "R": px(496, 363)}
RING_R, RING_r = 4.7, 2.2

# ==========================================================================
# 3. Fab arms - measured on the left arm of the picture, mirrored for the right
# ==========================================================================
HEAVY_TOP = px(275, 212)         # tip of the long blue heavy chain
LIGHT_BOT = px(303, 333)         # ends of the pink light chain
LIGHT_TOP = px(207, 233)
LOWER_C = px(342, 363)           # lower heavy-chain globule
arm_frames = {
    "L": Frame(RING_C["L"], (-a, 0, a), (-a, 0, -a), (0, -1, 0)),
    "R": Frame(RING_C["R"], (a, 0, a), (a, 0, -a), (0, 1, 0)),
}
ARM_GRID = ((-9, -26, -18), (98, 30, 18))
arm = {}
ring_axis = {}


def mirror(p, side):
    p = np.array(p, float)
    if side == "R":
        p[0] = -p[0]
    return p


for side, seed in (("L", 21), ("R", 37)):
    rng = np.random.default_rng(seed)
    fr = arm_frames[side]
    g = Grid(ARM_GRID[0], ARM_GRID[1], H)
    L = lambda p: fr.to_local(mirror(p, side))

    # --- heavy chain: two twisted strands rising out of the yellow ring
    base = RING_C["L"]
    D = unit(HEAVY_TOP - base)
    ring_axis[side] = unit(mirror(D, side))
    perp = unit(np.cross(D, [0, 1, 0]))
    length = np.linalg.norm(HEAVY_TOP - base)
    nodes = []
    for s in (-1, 1):
        for t in np.linspace(0, 1, 9):
            ramp = min(t / 0.1, 1.0)
            dist = 7.0 + t * (length - 15.0)
            r = (4.2 + 1.2 * ramp) * (1 + rng.uniform(-0.06, 0.06))
            sep = 2.0 + 2.4 * ramp
            ang = np.radians(-15 + 50 * t)
            off = s * sep * (np.cos(ang) * perp + np.sin(ang) * np.array([0, 1.0, 0]))
            nodes.append((L(base + dist * D + off), r))
    env_strands = blobs(nodes, 2.4)
    ld = unit([-1, 0, 1])
    lower = [(L(LOWER_C + 4.6 * ld + [0, 0.4, 0]), (7.1, 6.9, 6.9)),
             (L(LOWER_C - 4.6 * ld - [0, 0.3, 0]), (6.8, 6.6, 6.6))]
    env_lower = blobs(lower, 2.5)
    env_heavy = lambda P, a_=env_strands, b_=env_lower: smin(a_(P), b_(P), 0.9)
    f_heavy = lumpy(env_heavy, ((-9, -25, -16), (80, 30, 16)), seed + 1, LUMPS_HEAVY).field(g)
    log("arm", side, "heavy", g.shape)

    # --- light chain (pink), 15 mm wide
    pd = unit(LIGHT_TOP - LIGHT_BOT)
    plen = np.linalg.norm(LIGHT_TOP - LIGHT_BOT)
    lnodes = []
    for t in np.linspace(0, 1, 6):
        c = LIGHT_BOT + (7.6 + t * (plen - 15.2)) * pd + rng.normal(0, 0.3, 3)
        lnodes.append((L(c), 6.0 * (1 + rng.uniform(-0.05, 0.05))))
    f_light = lumpy(tube(lnodes), ((10, -5, -14), (85, 30, 14)), seed + 2, LUMPS_LIGHT).field(g)
    log("arm", side, "light")

    # --- variable domains / antigen-binding site (purple): picture 157-280 x 140-223
    vnodes = [(L(px(185, 185, 0.3)), (7.5, 7.6, 8.4)),
              (L(px(219, 176, 0.8)), (9.0, 9.0, 9.0)),
              (L(px(252, 185, -0.6)), (7.5, 7.6, 8.2)),
              (L(px(210, 203, 0.0)), (7.0, 7.0, 7.6))]
    f_v = lumpy(blobs(vnodes, 3.2), ((50, -25, -16), (98, 30, 16)), seed + 3, LUMPS_VDOM).field(g)
    log("arm", side, "vdomain")
    arm[side] = dict(grid=g, frame=fr, heavy=f_heavy, light=f_light, vdom=f_v,
                     light_u=(L(LIGHT_BOT)[0], L(LIGHT_TOP)[0]), heavy_top=L(HEAVY_TOP))

# --------------------------------------------------------------------------
# snap the pieces of each arm together: the picture shows them packed tightly
# (pink against the blue, purple sitting on both).  Shift whole voxel fields.
# --------------------------------------------------------------------------
def shift(f, axis, n):
    out = np.full_like(f, F32(50.0))
    src = [slice(None)] * 3
    dst = [slice(None)] * 3
    if n > 0:
        src[axis], dst[axis] = slice(0, -n), slice(n, None)
    elif n < 0:
        src[axis], dst[axis] = slice(-n, None), slice(0, n)
    else:
        return f
    out[tuple(dst)] = f[tuple(src)]
    return out


def contact_gap(lower, upper, axis, keep):
    """Per column along `axis`: lowest coordinate of `upper` minus the highest of `lower` below it."""
    n = lower.shape[axis]
    idx = np.arange(n).reshape([-1 if i == axis else 1 for i in range(3)])
    up_in = upper < 0
    lo_in = lower < 0
    first_up = np.where(up_in.any(axis), np.argmax(up_in, axis=axis), -1)
    below = lo_in & (idx < np.expand_dims(np.where(first_up >= 0, first_up, 0), axis))
    last_lo = np.where(below.any(axis), n - 1 - np.argmax(np.flip(below, axis), axis=axis), -1)
    ok = (first_up >= 0) & (last_lo >= 0) & keep
    return (first_up - last_lo)[ok]


for side in ("L", "R"):
    A = arm[side]
    g = A["grid"]
    U = g.axes[0][:, None]
    u0, u1 = A["light_u"]
    keep = (U > u0 + 4) & (U < u1 - 4)                         # (u, w) columns along the pink
    gaps = contact_gap(A["heavy"], A["light"], 1, keep)
    n = int(round(np.percentile(gaps, 12))) - 1 + int(round(0.8 / g.h))
    A["light"] = shift(A["light"], 1, -n)
    log("arm", side, f"light chain moved {-n * g.h:+.1f} mm towards the heavy chain")
    gaps = contact_gap(np.minimum(A["heavy"], A["light"]), A["vdom"], 0, True)
    n = int(round(np.percentile(gaps, 15))) - 1 + int(round(1.2 / g.h))
    A["vdom"] = shift(A["vdom"], 0, -n)
    log("arm", side, f"purple tip moved {-n * g.h:+.1f} mm down onto the chains")

# hex peg from the ring into the bottom of the heavy chain
PEG_RC = 2.7
for side in ("L", "R"):
    A = arm[side]
    fr = A["frame"]
    Dw = ring_axis[side]
    t_s = first_crossing(A["heavy"], A["grid"], [0, 0, 0], fr.dir_to_local(Dw), 25, False)
    A["peg_a"] = RING_C[side] - 0.8 * Dw
    A["peg_b"] = RING_C[side] + (t_s + 9.0) * Dw
    log("arm", side, f"heavy chain starts {t_s:.2f} mm above the ring centre")


# ==========================================================================
# 4. hinge as two touching bodies: yellow (bonds + rings) and cyan (strands)
# ==========================================================================
def hinge_yellow(P, pegs=True):
    parts = [capsule(P, (-FC_X, 0, RUNG_LOW_Z), (FC_X, 0, RUNG_LOW_Z), 2.35),
             capsule(P, (-SIDE_X - 2.2, 0, RUNG_TOP_Z), (SIDE_X + 2.2, 0, RUNG_TOP_Z), 2.3)]
    for sx in (-1, 1):
        parts.append(sphere(P, (sx * FC_X, 0, RUNG_LOW_Z), 3.1))
        parts.append(sphere(P, (sx * (SIDE_X + 2.2), 0, RUNG_TOP_Z), 2.8))
        parts.append(capsule(P, (sx * SIDE_X, 0, RUNG_LOW_Z), (sx * SIDE_X, 0, RUNG_TOP_Z), 1.85))
        if pegs:
            parts.append(cylinder(P, (sx * FC_X, 0, RUNG_LOW_Z - 9.5), (sx * FC_X, 0, RUNG_LOW_Z),
                                  1.9, 0.35))
    for side in ("L", "R"):
        parts.append(torus(P, RING_C[side], ring_axis[side], RING_R, RING_r))
    return smin_all(parts, 0.6)


def hinge_cyan(P, pegs=True):
    parts = [capsule(P, (-STRAND_X - 0.3, 0, CROSS_Z), (STRAND_X + 0.3, 0, CROSS_Z), 1.55)]
    for side, sx in (("L", -1), ("R", 1)):
        bend = np.array([sx * STRAND_X, 0, CROSS_Z - 2.0])
        low = np.array([sx * STRAND_X, 0, RUNG_LOW_Z + 4])
        parts.append(capsule(P, (sx * (FC_X - 1.2), 0, RUNG_LOW_Z), low, 1.7))
        parts.append(capsule(P, low, bend, 1.7))
        parts.append(capsule(P, bend, RING_C[side], 1.8))
        if pegs:
            parts.append(hex_prism(P, arm[side]["peg_a"], arm[side]["peg_b"], PEG_RC, 0.35))
    return smin_all(parts, 0.5)


def hinge_fn(P, pegs=True):
    return np.minimum(hinge_yellow(P, pegs), hinge_cyan(P, pegs))


hg = Grid((-34, -8, RUNG_LOW_Z - 12), (34, 8, 118), 0.13)
Phg = hg.points()
f_hy = hinge_yellow(Phg)
f_hc = np.maximum(hinge_cyan(Phg), -f_hy)        # cyan body ends where the yellow starts
log("hinge", hg.shape)

# ==========================================================================
# 5. alignment pins inside each Fab arm
# ==========================================================================
pins = {}
for side in ("L", "R"):
    A = arm[side]
    g = A["grid"]
    lst = []
    u0, u1 = A["light_u"]
    v_light = []
    # light chain sits on the outer (+v) side of the heavy chain
    for u in (u0 + 0.30 * (u1 - u0), u0 + 0.62 * (u1 - u0)):
        iu, iw = int(round((u - g.lo[0]) / g.h)), int(round(-g.lo[2] / g.h))
        inside = np.nonzero(A["light"][iu, :, iw] < 0)[0]
        vl = g.lo[1] + g.h * (inside[0] + inside[-1]) / 2
        vh = vl - first_crossing(A["heavy"], g, (u, vl, 0), (0, -1, 0), 25, False)
        lst.append(("light-heavy", np.array([u, vh - PIN_HALF, 0]), np.array([u, vh + PIN_HALF, 0])))
        v_light.append(vl)
    # purple sits on the light chain's tip ...
    vl = float(v_light[1])
    for w in (-3.0, 3.0):        # two pins so the purple tip cannot turn
        ut = u1 - 15 + first_crossing(A["light"], g, (u1 - 15, vl, w), (1, 0, 0), 30, True)
        lst.append(("vdom", np.array([ut - PIN_HALF, vl, w]), np.array([ut + PIN_HALF, vl, w])))
    # ... and on the heavy chain's tip when they overlap enough
    hu, hv = A["heavy_top"][0], A["heavy_top"][1] + 1.0
    uh = hu - 15 + first_crossing(A["heavy"], g, (hu - 15, hv, 0), (1, 0, 0), 30, True)
    if at(A["vdom"], g, (uh + 4.5, hv, 0)) < -1.5 and at(A["heavy"], g, (uh - 5.5, hv, 0)) < -1.5:
        lst.append(("vdom", np.array([uh - PIN_HALF, hv, 0]), np.array([uh + PIN_HALF, hv, 0])))
    pins[side] = lst
    log("pins", side, [(n, p0.round(1), p1.round(1)) for n, p0, p1 in lst])


def pin_hole(P, p0, p1):
    d = unit(p1 - p0)
    return cylinder(P, p0 - 0.45 * d, p1 + 0.45 * d, PIN_R + CLR, 0.0)


# ==========================================================================
# 6. carve the mating surfaces and mesh everything
# ==========================================================================
for side in ("L", "R"):
    A = arm[side]
    g, fr = A["grid"], A["frame"]
    P = g.points()
    heavy, light, vdom = A["heavy"], A["light"], A["vdom"]

    light = carve(light, sweep(heavy, 1, +1), CLR * 0.7)                       # slides on along -v
    vdom = carve(vdom, sweep(np.minimum(heavy, light), 0, +1), CLR * 0.7)       # slides on along -u

    for kind, p0, p1 in pins[side]:
        hole = pin_hole(P, p0, p1)
        heavy = np.maximum(heavy, -hole)
        light = np.maximum(light, -hole)
        if kind == "vdom":
            vdom = np.maximum(vdom, -hole)
        else:   # keep the purple tip clear of these pins along its slide-on direction
            vdom = carve(vdom, sweep(hole, 0, +1), 0.2)

    Dw = ring_axis[side]
    rc = RING_C[side]

    def socket(Pw, A=A, Dw=Dw, rc=rc):
        hexhole = hex_prism(Pw, rc - 30 * Dw, A["peg_b"] + 0.5 * Dw, PEG_RC + CLR, 0.0)
        bore = cylinder(Pw, rc - 30 * Dw, rc + (RING_r + 0.3) * Dw, RING_R + RING_r + 0.3, 0.0)
        return np.minimum(hexhole, bore)

    heavy = np.maximum(heavy, -eval_world_fn_on(g, fr, socket, rc, 20))
    heavy = carve(heavy, eval_world_fn_on(g, fr, lambda Pw: hinge_fn(Pw, pegs=False), rc, 26), 0.35)
    A.update(heavy=heavy, light=light, vdom=vdom)
    OUT[f"fab_heavy_{side}"] = mesh_field(heavy, g, fr)
    OUT[f"light_{side}"] = mesh_field(light, g, fr)
    OUT[f"vdomain_{side}"] = mesh_field(vdom, g, fr)
    log("meshed arm", side)

# ---- base: a frustum like the picture (top 88 mm, bottom 104 mm, 22 mm tall)
BASE_RT, BASE_RB, BASE_H = 44.0, 52.0, 22.0
BASE_PEG_RC, BASE_PEG_TOP = 3.4, 8.0
SLOPE = (BASE_RB - BASE_RT) / BASE_H
NRM = float(np.sqrt(1 + SLOPE * SLOPE))


def base_peg_fn(P, rr=0.6):
    return np.minimum(hex_prism(P, (-FC_X, 0, -2), (-FC_X, 0, BASE_PEG_TOP), BASE_PEG_RC, rr),
                      hex_prism(P, (FC_X, 0, -2), (FC_X, 0, BASE_PEG_TOP), BASE_PEG_RC, rr))


for side, sx in (("left", -1), ("right", 1)):
    g, f = fc_grid[side], fc_field[side]
    P = g.points()
    hin = eval_world_fn_on(g, WORLD, hinge_fn, (sx * FC_X, 0, 78), 16)
    f = carve(f, sweep(hin, 2, -1), CLR)                        # hinge lifts off upwards
    f = carve(f, sweep(base_peg_fn(P, 0.0), 2, +1), CLR)        # column lifts off the base
    for i in range(len(bonds)):
        f = carve(f, sweep(bond_fn(i, 0.45)(P), 0, sx), CLR)    # pulled sideways off the rungs
    OUT[f"fc_{side}"] = mesh_field(f, g, WORLD)
    log("meshed fc", side)

for i in range(len(bonds)):
    a0, a1 = bonds[i]
    g = Grid(a0 - 3.5, a1 + 3.5, 0.1)
    OUT[f"fc_bond_{i + 1}"] = mesh_field(bond_fn(i)(g.points()), g, WORLD)

OUT["hinge_yellow"] = mesh_field(f_hy, hg, WORLD)
OUT["hinge_cyan"] = mesh_field(f_hc, hg, WORLD)
OUT["hinge_one_piece"] = mesh_field(np.minimum(f_hy, f_hc), hg, WORLD)
log("meshed hinge + bonds")

PLQ_HS, PLQ_HZ, PLQ_ZC = 31.5, 7.0, -BASE_H / 2 - 0.3


def _cone_coords(P):
    """(arc length, distance from the sloped side face, z) around the base front."""
    X, Y, Z = P
    rad = np.sqrt(X * X + Y * Y)
    dface = (rad - (F32(BASE_RT) - F32(SLOPE) * Z)) / F32(NRM)
    s = F32((BASE_RT + BASE_RB) / 2) * np.arctan2(X, -Y)
    return s, dface, Z


def _rrect(s, z, hs, hz, rc):
    qx = np.abs(s) - F32(hs - rc)
    qz = np.abs(z - F32(PLQ_ZC)) - F32(hz - rc)
    return (np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qz, 0) ** 2)
            + np.minimum(np.maximum(qx, qz), 0) - F32(rc))


FRAME_W = 1.3     # white border of the (blank) label, like the picture


def plaque_fn(P):
    s, dface, Z = _cone_coords(P)
    ring2d = np.maximum(_rrect(s, Z, PLQ_HS, PLQ_HZ, 1.4), -_rrect(s, Z, PLQ_HS - FRAME_W, PLQ_HZ - FRAME_W, 0.6))
    return _cap(ring2d, np.abs(dface + F32(0.15)) - F32(0.75), 0.25)        # 0.6 mm proud


def pocket_fn(P):
    s, dface, Z = _cone_coords(P)
    groove = np.maximum(_rrect(s, Z, PLQ_HS + 0.2, PLQ_HZ + 0.2, 1.6),
                        -_rrect(s, Z, PLQ_HS - FRAME_W - 0.2, PLQ_HZ - FRAME_W - 0.2, 0.4))
    return np.maximum(groove, np.abs(dface - F32(2.0)) - F32(2.9))         # 0.9 mm deep


def base_fn(P):
    X, Y, Z = P
    s, side_d, _ = _cone_coords(P)
    rr = F32(3.0)
    q1, q2 = side_d + rr, Z + rr                                     # rounded top edge
    body = (np.sqrt(np.maximum(q1, 0) ** 2 + np.maximum(q2, 0) ** 2)
            + np.minimum(np.maximum(q1, q2), 0) - rr)
    body = np.maximum(body, -(Z + F32(BASE_H)))                      # flat bottom
    body = np.maximum(body, (side_d - (Z + F32(BASE_H)) + F32(1.0)) * F32(0.7071))  # bevel
    body = np.minimum(body, base_peg_fn(P))
    return np.maximum(body, -pocket_fn(P))


bg = Grid((-BASE_RB - 3, -BASE_RB - 3, -BASE_H - 2), (BASE_RB + 3, BASE_RB + 3, BASE_PEG_TOP + 2), 0.22)
OUT["base"] = mesh_field(base_fn(bg.points()), bg, WORLD)
pg = Grid((-36, -BASE_RB - 4, -BASE_H - 1), (36, -BASE_RT + 14, 1), 0.12)
OUT["plaque"] = mesh_field(plaque_fn(pg.points()), pg, WORLD)
log("meshed base + plaque")

pg = Grid((-3, -3, -PIN_HALF - 1), (3, 3, PIN_HALF + 1), 0.08)
OUT["pin"] = mesh_field(cylinder(pg.points(), (0, 0, -PIN_HALF), (0, 0, PIN_HALF), PIN_R, 0.45), pg, WORLD)

meta = []
for side in ("L", "R"):
    fr = arm[side]["frame"]
    for kind, p0, p1 in pins[side]:
        meta.append(np.concatenate([fr.to_world(p0), fr.to_world(p1),
                                    [1.0 if kind == "vdom" else 0.0, 0.0 if side == "L" else 1.0]]))

flat = {}
for k, (v, f) in OUT.items():
    flat[k + "__v"] = v
    flat[k + "__f"] = f
    log(f"{k:16s} {len(f):8d} tris")
flat["pin_positions"] = np.array(meta)
np.savez_compressed(sys.argv[1], **flat)
log("saved", sys.argv[1])
