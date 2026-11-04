"""Build every printable part of the IgG antibody model as a closed mesh.

Run with a Python that has numpy, scipy and scikit-image:
    python build_geometry.py OUT.npz

Units are millimetres.  World frame: X = right, Y = depth (away from the
viewer), Z = up.  The top of the base is Z = 0.

Parts
  base, plaque                      display stand + blank front label
  fc_left, fc_right                 Fc region (CH2 + CH3 of both heavy chains)
  fc_bond_1..3                      yellow disulfide rungs between the Fc columns
  hinge                             yellow hinge ladder, collar rings and Fab pegs
  fab_heavy_L/R                     blue heavy chain of each Fab arm
  light_L/R                         pink light chain
  vdomain_L/R                       purple variable domains (antigen-binding site)
  pin                               alignment pin (8 needed)
"""
import sys
import time
import numpy as np

from sdf_lib import (F32, Grid, Frame, LumpyDomain, sphere, ellipsoid, capsule,
                     cylinder, hex_prism, torus, smin, smin_all, carve, sweep,
                     mesh_field, sample_grid_field, transform_points, _cap)

H = 0.2          # voxel size for the organic parts (mm)
CLR = 0.15       # radial clearance of every hole (mm) - 0.3 mm on the diameter
PIN_R = 1.5      # alignment pin radius (3 mm pins)
PIN_HALF = 6.0   # pin half length (12 mm pins)

WORLD = Frame()
a = np.sqrt(0.5)
OUT = {}
T0 = time.time()


def log(*m):
    print(f"[{time.time() - T0:7.1f}s]", *m, flush=True)


def eval_world_fn_on(grid, frame, fn, center_world, radius, fill=50.0):
    """Evaluate a world-space SDF on a sub-box of a (possibly rotated) grid."""
    out = np.full(grid.shape, F32(fill), dtype=F32)
    c_loc = frame.to_local(center_world)
    sl = grid.box(c_loc, radius)
    if sl is None:
        return out
    P = transform_points(grid.points(sl), frame, WORLD)
    out[sl] = np.broadcast_to(fn(P), out[sl].shape)
    return out


def sausage(nodes, k):
    """Smooth chain of spheres/ellipsoids: nodes = [(center, radius_or_radii)]."""
    def fn(P):
        fs = []
        for c, r in nodes:
            if np.isscalar(r):
                fs.append(sphere(P, c, r))
            else:
                fs.append(ellipsoid(P, c, r))
        return smin_all(fs, k)
    return fn


def chain_nodes(p0, p1, r, n, rng, jitter=0.7, rjit=0.06, w_squash=1.0):
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    nodes = []
    for i in range(n):
        t = i / (n - 1)
        c = p0 + t * (p1 - p0) + rng.normal(0, jitter, 3) * np.array([0.4, 1, 1])
        rr = r * (1 + rng.uniform(-rjit, rjit))
        nodes.append((c, (rr, rr, rr * w_squash)))
    return nodes


def first_crossing(field, grid, p0, d, t_max, inside_to_outside):
    d = np.asarray(d, float) / np.linalg.norm(d)
    ts = np.arange(0, t_max, 0.04)
    pts = np.asarray(p0, float)[None] + ts[:, None] * d[None]
    vals = sample_grid_field(field, grid, pts)
    hit = np.nonzero(vals > 0)[0] if inside_to_outside else np.nonzero(vals < 0)[0]
    if len(hit) == 0:
        raise RuntimeError("ray never crossed the surface")
    return float(ts[hit[0]])


# ==========================================================================
# 1. Fc region - two lumpy columns (CH3 at the bottom, CH2 on top)
# ==========================================================================
FC_X = 14.0
fc_grid = {}
fc_field = {}
fc_frame = {}
for side, sx, seed in (("left", -1, 11), ("right", 1, 12)):
    rng = np.random.default_rng(seed)
    x0 = sx * FC_X
    prof = [(-4, 8.3), (3, 8.4), (11, 9.0), (19.5, 9.3), (28, 8.8),
            (37.5, 7.8),                                   # waist between CH3 / CH2
            (46.5, 9.1), (55.5, 9.5), (64.5, 9.0)]
    nodes = []
    for z, r in prof:
        c = np.array([x0 + rng.normal(0, 0.45), rng.normal(0, 0.45), z])
        nodes.append((c, (r * 1.02, r, r * 1.0)))
    env = sausage(nodes, 3.2)
    lo = (x0 - 14.5, -14.5, -6)
    hi = (x0 + 14.5, 14.5, 80)
    dom = LumpyDomain(env, (lo, hi), seed + 100)
    g = Grid((x0 - 14.5, -14.5, -1.0), (x0 + 14.5, 14.5, 80.0), H)
    f = dom.field(g)
    X, Y, Z = g.points()
    f = np.maximum(f, -(Z - 0.05))              # flat printable bottom just above Z = 0
    fc_grid[side], fc_field[side], fc_frame[side] = g, f, WORLD
    log("fc", side, g.shape)

# inner surfaces of the columns -> yellow disulfide rungs between them
BOND_Z = [13.5, 37.0, 57.0]
bonds = []
for i, z in enumerate(BOND_Z):
    gL, gR = fc_grid["left"], fc_grid["right"]
    xl = -FC_X + first_crossing(fc_field["left"], gL, (-FC_X, 0, z), (1, 0, 0), 14, True)
    xr = FC_X - first_crossing(fc_field["right"], gR, (FC_X, 0, z), (-1, 0, 0), 14, True)
    a0 = np.array([xl - 5.0, 0, z])
    a1 = np.array([xr + 5.0, 0, z])
    bonds.append((a0, a1))
    log(f"bond {i + 1}: inner faces {xl:.2f} .. {xr:.2f}  length {a1[0] - a0[0]:.2f}")
BOND_R = 2.2


def bond_fn(i, grow=0.0, extra=0.0):
    a0, a1 = bonds[i]
    d = np.array([extra, 0, 0])
    return lambda P: cylinder(P, a0 - d, a1 + d, BOND_R + grow, 0.5)


# ==========================================================================
# 2. Fab arms (built in an arm-local frame: u along the arm, v towards the
#    outer/light-chain side, w = depth)
# ==========================================================================
ARM_ANCHOR_Z = 100.5
ARM_ANCHOR_X = 13.0
arm_frames = {
    "L": Frame((-ARM_ANCHOR_X, 0, ARM_ANCHOR_Z), (-a, 0, a), (-a, 0, -a), (0, -1, 0)),
    "R": Frame((ARM_ANCHOR_X, 0, ARM_ANCHOR_Z), (a, 0, a), (a, 0, -a), (0, 1, 0)),
}
ARM_GRID = ((-6, -21, -17.5), (97, 29, 17.5))
LOWER_BLOB_C = np.array([12.0, 14.0, 0.0])
arm = {}

for side, seed in (("L", 21), ("R", 37)):
    rng = np.random.default_rng(seed)
    g = Grid(ARM_GRID[0], ARM_GRID[1], H)
    fr = arm_frames[side]

    # --- heavy chain (blue): lower globule near the hinge + long CH1/VH body
    lower = [(LOWER_BLOB_C + rng.normal(0, 0.3, 3), (10.6, 9.6, 9.6)),
             (LOWER_BLOB_C + np.array([-2.5, 3.0, 1.0]), (7.5, 7.0, 8.0))]
    heavy_long = chain_nodes((20.5, -3.0, 0), (62.0, -5.0, 0), 9.8, 7, rng, 0.8)
    env_lower = sausage(lower, 2.0)
    env_long = sausage(heavy_long, 3.0)
    env_heavy = lambda P, el=env_lower, eh=env_long: smin(el(P), eh(P), 1.1)
    dom_h = LumpyDomain(env_heavy, ((-6, -20, -14), (76, 28, 14)), seed + 1)
    f_heavy = dom_h.field(g)
    log("arm", side, "heavy", g.shape)

    # --- light chain (pink)
    light_nodes = chain_nodes((33.5, 16.3, 0), (66.0, 15.4, 0), 8.0, 5, rng, 0.5)
    env_light = sausage(light_nodes, 2.4)
    dom_l = LumpyDomain(env_light, ((22, 5, -11), (77, 27, 11)), seed + 2,
                        layers=[(6.0, 3.5, 4.5, 1.2, 1.9), (3.6, 2.2, 2.9, 0.85, 1.4)])
    f_light = dom_l.field(g)
    log("arm", side, "light")

    # --- variable domains (purple) - the antigen-binding tip
    vnodes = [(np.array([78.0, -4.0, 0.3]), (10.2, 10.0, 10.6)),
              (np.array([81.0, 5.5, 1.0]), (11.0, 10.5, 11.2)),
              (np.array([77.8, 14.8, -0.6]), (10.0, 9.4, 10.0))]
    env_v = sausage(vnodes, 3.0)
    dom_v = LumpyDomain(env_v, ((62, -17, -14), (95, 28, 14)), seed + 3,
                        layers=[(7.6, 4.6, 6.0, 1.5, 2.3), (4.2, 2.6, 3.4, 1.0, 1.6)])
    f_v = dom_v.field(g)
    log("arm", side, "vdomain")

    arm[side] = dict(grid=g, frame=fr, heavy=f_heavy, light=f_light, vdom=f_v)

# ==========================================================================
# 3. hinge (yellow) - ladder of disulfide bonds, collar rings and Fab pegs
# ==========================================================================
RAIL_X = 10.0
RUNG_Z = [78.6, 86.4, 94.0]
RAIL_TOP = RUNG_Z[-1]
# where the rails meet the lumpy top of the Fc columns
rail_bottom = {}
for side, sx in (("left", -1), ("right", 1)):
    t = first_crossing(fc_field[side], fc_grid[side], (sx * RAIL_X, 0, 85), (0, 0, -1), 20, False)
    rail_bottom[side] = 85 - t
    log("rail bottom", side, rail_bottom[side])

ring = {}
for side in ("L", "R"):
    A = arm[side]
    D_loc = LOWER_BLOB_C / np.linalg.norm(LOWER_BLOB_C)
    t_s = first_crossing(A["heavy"], A["grid"], (0, 0, 0), D_loc, 25, False)
    ring_t = t_s - 4.0
    fr = A["frame"]
    D = fr.dir_to_world(D_loc)
    c = fr.to_world(ring_t * D_loc)
    peg_a = c - 0.6 * D
    peg_b = c + (4.0 + 8.0) * D          # 8 mm deep into the Fab
    ring[side] = dict(c=c, D=D, peg_a=peg_a, peg_b=peg_b)
    log("ring", side, c, "surface at", t_s)

RING_R, RING_r = 3.8, 1.6
PEG_RC = 2.7


def hinge_fn(P, grow=0.0, pegs=True):
    g = F32(grow)
    parts = []
    for side, sx in (("left", -1), ("right", 1)):
        x = sx * RAIL_X
        zb = rail_bottom[side]
        parts.append(capsule(P, (x, 0, zb + 0.6), (x, 0, RAIL_TOP), 2.2) - g)
        if pegs:
            parts.append(cylinder(P, (x, 0, zb - 7.0), (x, 0, zb + 1.0), 1.75 + grow, 0.35))
        for z in RUNG_Z:
            parts.append(sphere(P, (x, 0, z), 3.0) - g)
    for z in RUNG_Z:
        parts.append(capsule(P, (-RAIL_X, 0, z), (RAIL_X, 0, z), 2.45) - g)
    for side, sx in (("L", -1), ("R", 1)):
        r = ring[side]
        parts.append(capsule(P, (sx * RAIL_X, 0, RAIL_TOP), r["c"] - 1.0 * r["D"], 2.2) - g)
        parts.append(torus(P, r["c"], r["D"], RING_R, RING_r) - g)
        if pegs:
            parts.append(hex_prism(P, r["peg_a"], r["peg_b"], PEG_RC + grow, 0.35))
    return smin_all(parts, 0.55)


hz0 = min(rail_bottom.values()) - 9
hg = Grid((-33, -8, hz0), (33, 8, 108), 0.13)
f_hinge = hinge_fn(hg.points())
log("hinge", hg.shape)

# ==========================================================================
# 4. pins inside each Fab arm (light->heavy, vdomain->light/heavy)
# ==========================================================================
pins = {}
for side in ("L", "R"):
    A = arm[side]
    g = A["grid"]
    lst = []
    for u in (42.0, 58.0):
        v_axis = -3.0 - 2.0 * (u - 20) / 42
        vh = v_axis + first_crossing(A["heavy"], g, (u, v_axis, 0), (0, 1, 0), 20, True)
        lst.append(("light-heavy", np.array([u, vh - PIN_HALF, 0]), np.array([u, vh + PIN_HALF, 0])))
    both = np.minimum(A["heavy"], A["light"])
    for v in (15.6, -3.8):
        ut = 55 + first_crossing(both, g, (55, v, 0), (1, 0, 0), 30, True)
        lst.append(("vdom", np.array([ut - PIN_HALF, v, 0]), np.array([ut + PIN_HALF, v, 0])))
    pins[side] = lst
    log("pins", side, [(n, p0.round(1), p1.round(1)) for n, p0, p1 in lst])


def pin_hole(P, p0, p1):
    d = (p1 - p0) / np.linalg.norm(p1 - p0)
    return cylinder(P, p0 - 0.45 * d, p1 + 0.45 * d, PIN_R + CLR, 0.0)


# ==========================================================================
# 5. carve all mating surfaces
# ==========================================================================
for side in ("L", "R"):
    A = arm[side]
    g, fr = A["grid"], A["frame"]
    P = g.points()
    heavy, light, vdom = A["heavy"], A["light"], A["vdom"]

    # light chain is pushed onto the heavy chain along -v  (pulled off along +v)
    light = carve(light, sweep(heavy, 1, +1), CLR * 0.7)
    # variable domains sit on top of both chains (pulled off along +u)
    vdom = carve(vdom, sweep(np.minimum(heavy, light), 0, +1), CLR * 0.7)

    for kind, p0, p1 in pins[side]:
        hole = pin_hole(P, p0, p1)
        if kind == "light-heavy":
            heavy = np.maximum(heavy, -hole)
            light = np.maximum(light, -hole)
        else:
            vdom = np.maximum(vdom, -hole)
            heavy = np.maximum(heavy, -hole)
            light = np.maximum(light, -hole)

    # hex socket + collar counterbore for the hinge peg (Fab slides on along D)
    r = ring[side]
    D = r["D"]

    def socket(Pw, r=r, D=D):
        hexhole = hex_prism(Pw, r["c"] - 30 * D, r["peg_b"] + 0.5 * D, PEG_RC + CLR, 0.0)
        bore = cylinder(Pw, r["c"] - 30 * D, r["c"] + (RING_r + 0.35) * D,
                        RING_R + RING_r + 0.35, 0.0)
        return np.minimum(hexhole, bore)

    heavy = np.maximum(heavy, -eval_world_fn_on(g, fr, socket, r["c"], 18))
    # stay clear of the rest of the hinge too
    heavy = carve(heavy, eval_world_fn_on(g, fr, lambda Pw: hinge_fn(Pw, pegs=False), r["c"], 22), 0.4)

    A.update(heavy=heavy, light=light, vdom=vdom)
    OUT[f"fab_heavy_{side}"] = mesh_field(heavy, g, fr)
    OUT[f"light_{side}"] = mesh_field(light, g, fr)
    OUT[f"vdomain_{side}"] = mesh_field(vdom, g, fr)
    log("meshed arm", side)

# Fc columns: sockets for the hinge pegs, the disulfide rungs and the base pegs
BASE_R = 64.0
BASE_H = 18.0
BASE_PEG_RC = 3.5
BASE_PEG_TOP = 8.0


def base_peg_fn(P, grow=0.0):
    return np.minimum(
        hex_prism(P, (-FC_X, 0, -2), (-FC_X, 0, BASE_PEG_TOP), BASE_PEG_RC + grow, 0.6 if grow == 0 else 0.0),
        hex_prism(P, (FC_X, 0, -2), (FC_X, 0, BASE_PEG_TOP), BASE_PEG_RC + grow, 0.6 if grow == 0 else 0.0))


for side, sx in (("left", -1), ("right", 1)):
    g = fc_grid[side]
    f = fc_field[side]
    P = g.points()
    # hinge lifts off upwards -> column carved by the hinge swept downwards
    hin = eval_world_fn_on(g, WORLD, hinge_fn, (sx * RAIL_X, 0, 78), 16)
    f = carve(f, sweep(hin, 2, -1), CLR)
    # base pegs (column lifts off the base along +z)
    f = carve(f, sweep(base_peg_fn(P), 2, +1), CLR)
    # disulfide rungs (column pulled sideways, away from the gap)
    for i in range(len(bonds)):
        b = bond_fn(i, 0.0, 0.45)(P)
        f = carve(f, sweep(b, 0, sx), CLR)
    OUT[f"fc_{side}"] = mesh_field(f, g, WORLD)
    log("meshed fc", side)

for i in range(len(bonds)):
    a0, a1 = bonds[i]
    g = Grid(a0 - 3, a1 + 3, 0.1)
    OUT[f"fc_bond_{i + 1}"] = mesh_field(bond_fn(i)(g.points()), g, WORLD)

OUT["hinge"] = mesh_field(f_hinge, hg, WORLD)
log("meshed hinge + bonds")

# ==========================================================================
# 6. base + blank plaque
# ==========================================================================
PLQ_HS, PLQ_HZ, PLQ_ZC = 31.0, 5.0, -BASE_H / 2


def _plaque_coords(P):
    X, Y, Z = P
    rad = np.sqrt(X * X + Y * Y)
    s = F32(BASE_R) * np.arctan2(X, -Y)
    return s, rad, Z


def _rrect(s, z, hs, hz, rc):
    qx = np.abs(s) - F32(hs - rc)
    qz = np.abs(z - F32(PLQ_ZC)) - F32(hz - rc)
    return (np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qz, 0) ** 2)
            + np.minimum(np.maximum(qx, qz), 0) - F32(rc))


def plaque_fn(P):
    s, rad, Z = _plaque_coords(P)
    d2 = _rrect(s, Z, PLQ_HS, PLQ_HZ, 1.3)
    r_in, r_out = BASE_R - 0.8, BASE_R + 0.6
    return _cap(d2, np.abs(rad - F32((r_in + r_out) / 2)) - F32((r_out - r_in) / 2), 0.35)


def pocket_fn(P):
    s, rad, Z = _plaque_coords(P)
    d2 = _rrect(s, Z, PLQ_HS + 0.2, PLQ_HZ + 0.2, 1.5)
    return np.maximum(d2, np.abs(rad - F32(BASE_R + 2.2)) - F32(3.0))   # 0.8 mm deep


def base_fn(P):
    X, Y, Z = P
    rad = np.sqrt(X * X + Y * Y)
    body = _cap(rad - F32(BASE_R), np.abs(Z + F32(BASE_H / 2)) - F32(BASE_H / 2), 2.6)
    body = np.minimum(body, base_peg_fn(P))
    return np.maximum(body, -pocket_fn(P))


bg = Grid((-BASE_R - 3, -BASE_R - 3, -BASE_H - 2), (BASE_R + 3, BASE_R + 3, BASE_PEG_TOP + 2), 0.25)
OUT["base"] = mesh_field(base_fn(bg.points()), bg, WORLD)
pg = Grid((-35, -BASE_R - 3, -BASE_H), (35, -BASE_R + 12, 0), 0.12)
OUT["plaque"] = mesh_field(plaque_fn(pg.points()), pg, WORLD)
log("meshed base + plaque")

# one alignment pin (8 needed), modelled at the first left light->heavy position
pg = Grid((-3, -3, -PIN_HALF - 1), (3, 3, PIN_HALF + 1), 0.08)
OUT["pin"] = mesh_field(cylinder(pg.points(), (0, 0, -PIN_HALF), (0, 0, PIN_HALF), PIN_R, 0.45), pg, WORLD)

# keep the pin placements so the Blender scene can show them assembled
meta = []
for side in ("L", "R"):
    fr = arm[side]["frame"]
    for kind, p0, p1 in pins[side]:
        meta.append(np.concatenate([fr.to_world(p0), fr.to_world(p1)]))
OUT_META = np.array(meta)

flat = {}
for k, (v, f) in OUT.items():
    flat[k + "__v"] = v
    flat[k + "__f"] = f
    log(f"{k:14s} {len(f):8d} tris")
flat["pin_positions"] = OUT_META
np.savez_compressed(sys.argv[1], **flat)
log("saved", sys.argv[1])
