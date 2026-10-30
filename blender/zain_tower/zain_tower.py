"""
Telecom site (lattice tower + equipment shelter) — procedural Blender model.

Built for 3D printing at 1:50, in millimetres, standing on its own base plate.
Every overhang is kept at 45 degrees or steeper, every element grows out of
something below it, and the remaining flat undersides are short bridges, so the
model prints in one piece with no (or almost no) support.

Run inside Blender (Scripting tab -> Open -> Run Script) to get the scene, or
from a shell with the `bpy` module to also write the .blend, the STL files and
the preview renders:

    python3 zain_tower.py            # scene + .blend + STL
    RENDER=1 python3 zain_tower.py   # ... + preview renders

The STL export needs `manifold3d` (pip install manifold3d); it unions every
part into one watertight solid and splits it by colour for multi-material
printers.
"""
import math
import os
from collections import defaultdict

import numpy as np
import bpy
import bmesh

# --------------------------------------------------------------------------
# Dimensions (mm, 1 Blender unit = 1 mm)
# --------------------------------------------------------------------------
Z0 = 7.0                      # top of the tower's concrete pad
H = 180.0                     # lattice height
ZT = Z0 + H                   # top of the lattice
HW_KNOTS = ((0.0, 17.0), (0.2, 13.8), (0.6, 9.4), (1.0, 7.6))  # (height fraction, half width)
BANDS = 6                     # aviation red / white bands, bottom one white
BAND = H / BANDS
LEGS = ((-1, -1), (1, -1), (1, 1), (-1, 1))   # counter-clockwise
PIPE_R = 0.85                 # antenna / dish mount pipes

BASE = (-44.0, 110.0, -46.0, 44.0)            # ground plate x0, x1, y0, y1
SH = dict(x0=34.0, x1=96.0, y0=-30.0, y1=26.0, z0=4.0, z1=60.0)  # shelter body
TRAY_Z = 49.0                                 # top of the cable bridge floor

OUT = os.environ.get("ZAIN_OUT") or (
    os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd())

FONT_CANDIDATES = (
    "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
)

# print colour of every material
GROUP_OF = {
    "paint": "tower", "steel": "grey", "rru": "grey", "fence": "grey",
    "concrete": "grey", "gravel": "grey", "grille": "grey",
    "radome": "white", "shelter": "white", "lamp": "white",
    "cable": "black", "dark": "black", "logo": "purple",
}

Z = np.array([0.0, 0.0, 1.0])


def hw(z):
    t = (z - Z0) / H
    return float(np.interp(t, [k[0] for k in HW_KNOTS], [k[1] for k in HW_KNOTS]))


def leg(sx, sy, z):
    h = hw(z)
    return np.array([sx * h, sy * h, z])


def leg_r(z):
    return 1.25 - 0.3 * (z - Z0) / H


def knot_zs():
    return [Z0 + k[0] * H for k in HW_KNOTS]


# --------------------------------------------------------------------------
# Mesh primitives. Each part is a closed, outward-facing solid in world space.
# --------------------------------------------------------------------------
PARTS = []


def part(obj, mat, vf, tris=False):
    v, f = vf
    PARTS.append(dict(obj=obj, mat=mat, v=np.asarray(v, float), f=f, tris=tris))


def signed_volume(v, f):
    vol = 0.0
    for face in f:
        p0 = v[face[0]]
        for j in range(1, len(face) - 1):
            vol += np.dot(p0, np.cross(v[face[j]], v[face[j + 1]]))
    return vol / 6.0


def loft(rings, cap0=True, cap1=True):
    rings = [np.asarray(r, float) for r in rings]
    n, m = len(rings[0]), len(rings)
    v = np.vstack(rings)
    f = []
    for i in range(m - 1):
        a, b = i * n, (i + 1) * n
        for k in range(n):
            k2 = (k + 1) % n
            f.append([a + k, a + k2, b + k2, b + k])
    if cap0:
        f.append(list(range(n))[::-1])
    if cap1:
        f.append(list(range((m - 1) * n, m * n)))
    if signed_volume(v, f) < 0:
        f = [x[::-1] for x in f]
    return v, f


def frame(d):
    d = np.asarray(d, float)
    d = d / np.linalg.norm(d)
    side = np.cross(d, Z)
    if np.linalg.norm(side) < 1e-6:
        side = np.array([1.0, 0.0, 0.0])
    side /= np.linalg.norm(side)
    return d, side, np.cross(side, d)


def circle(c, side, up, r, n, phase=0.0):
    a = phase + 2 * np.pi * np.arange(n) / n
    return np.asarray(c, float) + r * (np.cos(a)[:, None] * side + np.sin(a)[:, None] * up)


def hcircle(c, r, n=12, phase=0.0):
    return circle(c, np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), r, n, phase)


def beam(p1, p2, r, n=8, phase=None, ext=0.25):
    """Prism between two points; profile vertex pointing down when phase=pi/2."""
    p1, p2 = np.asarray(p1, float), np.asarray(p2, float)
    d, side, up = frame(p2 - p1)
    if phase is None:
        phase = np.pi / n
    return loft([circle(p1 - d * ext, side, up, r, n, phase),
                 circle(p2 + d * ext, side, up, r, n, phase)])


def diamond(p1, p2, r, ext=0.25):
    """Square bar standing on an edge: its underside is two 45-degree faces,
    so horizontal members bridge cleanly instead of sagging."""
    return beam(p1, p2, r, 4, np.pi / 2, ext)


def square_bar(p1, p2, a, ext=0.0):
    return beam(p1, p2, a / math.sqrt(2), 4, np.pi / 4, ext)


def rect_ring(x0, x1, y0, y1, z):
    return [(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)]


def box(x0, x1, y0, y1, z0, z1):
    return loft([rect_ring(x0, x1, y0, y1, z0), rect_ring(x0, x1, y0, y1, z1)])


def rrect2d(w, d, r, seg=3):
    r = min(r, w / 2 - 1e-3, d / 2 - 1e-3)
    pts = []
    for cx, cy, a0 in ((w / 2 - r, d / 2 - r, 0), (-w / 2 + r, d / 2 - r, 90),
                       (-w / 2 + r, -d / 2 + r, 180), (w / 2 - r, -d / 2 + r, 270)):
        for k in range(seg + 1):
            a = math.radians(a0 + 90 * k / seg)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return np.array(pts)


def rounded_plate(x0, x1, y0, y1, z0, z1, r, seg=6):
    p = rrect2d(x1 - x0, y1 - y0, r, seg)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    ring = lambda z: [(cx + a, cy + b, z) for a, b in p]
    return loft([ring(z0), ring(z1)])


def prism2d(poly, origin, ax_u, ax_v, ax_w, thick):
    """Extrude a convex 2-D polygon (in the u,v plane) by `thick` along w, centred."""
    o, u, v, w = (np.asarray(x, float) for x in (origin, ax_u, ax_v, ax_w))
    ring = lambda s: [o + a * u + b * v + s * w for a, b in poly]
    return loft([ring(-thick / 2), ring(thick / 2)])


def tube(pts, r, n=8):
    """Round tube swept along a polyline with a parallel-transported frame."""
    pts = np.asarray(pts, float)
    T = np.zeros_like(pts)
    T[1:-1] = pts[2:] - pts[:-2]
    T[0], T[-1] = pts[1] - pts[0], pts[-1] - pts[-2]
    T /= np.linalg.norm(T, axis=1)[:, None]
    nrm = frame(T[0])[1]
    rings = []
    for i, p in enumerate(pts):
        nrm = nrm - np.dot(nrm, T[i]) * T[i]
        nrm /= np.linalg.norm(nrm)
        rings.append(circle(p, nrm, np.cross(T[i], nrm), r, n))
    return loft(rings)


def fillet(points, r, seg=6):
    P = [np.asarray(p, float) for p in points]
    out = [P[0]]
    for i in range(1, len(P) - 1):
        a, b = P[i] - P[i - 1], P[i + 1] - P[i]
        la, lb = np.linalg.norm(a), np.linalg.norm(b)
        a, b = a / la, b / lb
        ang = math.acos(max(-1.0, min(1.0, float(np.dot(a, b)))))
        if ang < 1e-3:
            out.append(P[i])
            continue
        t = min(r * math.tan(ang / 2), la * 0.45, lb * 0.45)
        q0, q1 = P[i] - a * t, P[i] + b * t
        for s in np.linspace(0, 1, seg):
            out.append((1 - s) ** 2 * q0 + 2 * (1 - s) * s * P[i] + s ** 2 * q1)
    out.append(P[-1])
    return out


def ribbon(path, widths, normal, d_in, d_out):
    """Flat strip lying on a wall (for embossed logos)."""
    path = np.asarray(path, float)
    normal = np.asarray(normal, float)
    rings = []
    for i, p in enumerate(path):
        t = path[min(i + 1, len(path) - 1)] - path[max(i - 1, 0)]
        b = np.cross(normal, t / np.linalg.norm(t))
        b /= np.linalg.norm(b)
        w = widths[i] / 2
        rings.append([p + b * w + normal * d_out, p - b * w + normal * d_out,
                      p - b * w + normal * d_in, p + b * w + normal * d_in])
    return loft(rings)


def hanging_box(base, u, w, d, z_bot, z_top, r=0.5, tip_w=1.6, tip_d=1.2, top_bevel=True):
    """Box that hangs off a support (pipe or wall) at `base`, sticking out along
    the horizontal unit vector u. Its underside narrows at 45 degrees onto the
    support, so it needs no support material."""
    base = np.asarray(base, float)
    u = np.asarray(u, float)
    t = np.array([-u[1], u[0], 0.0])
    seg = 3

    def ring(w_, d_, z):
        p = rrect2d(w_, d_, min(r, w_ / 2.2, d_ / 2.2), seg)
        c = d_ / 2 - 0.2
        return [base + t * a + u * (c + b) + Z * (z - base[2]) for a, b in p]

    h_tap = 1.05 * max((w - tip_w) / 2, d - tip_d) + 0.2
    rings = [ring(tip_w, tip_d, z_bot - h_tap), ring(w, d, z_bot), ring(w, d, z_top)]
    if top_bevel:
        rings.append(ring(w - 0.5, d - 0.4, z_top + 0.35))
    return loft(rings)


# --------------------------------------------------------------------------
# Tower
# --------------------------------------------------------------------------
def tower_levels():
    zs = [Z0]
    while True:
        h = 1.05 * 2 * hw(zs[-1])
        if zs[-1] + h > ZT + 1e-6:
            break
        zs.append(zs[-1] + h)
    s = (ZT - Z0) / (zs[-1] - Z0)          # stretch so the top panel ends at ZT
    return [Z0 + (z - Z0) * s for z in zs]


def build_tower():
    levels = tower_levels()

    # legs: continuous round tubes following the taper
    ring_zs = sorted(set(levels + knot_zs()))
    for sx, sy in LEGS:
        rings = [hcircle(leg(sx, sy, z), leg_r(z), 12) for z in ring_zs]
        rings.append(hcircle(leg(sx, sy, ZT) + Z * 1.4, leg_r(ZT) * 0.8, 12))
        part("Tower_Legs", "paint", loft(rings))
        # bolted splice flanges, 45-degree chamfer underneath
        for z in levels[1:-1]:
            c, r0 = leg(sx, sy, z), leg_r(z)
            part("Tower_Legs", "paint", loft([hcircle(c - Z * 0.75, r0 + 0.05, 12),
                                               hcircle(c - Z * 0.35, r0 + 0.4, 12),
                                               hcircle(c + Z * 0.35, r0 + 0.4, 12)]))
        # foot plate and anchor bolts on the pad
        f = leg(sx, sy, Z0)
        part("Tower_Base", "steel", box(f[0] - 2.8, f[0] + 2.8, f[1] - 2.8, f[1] + 2.8, Z0 - 0.2, Z0 + 0.8))
        for bx in (-1.9, 1.9):
            for by in (-1.9, 1.9):
                part("Tower_Base", "steel", loft([hcircle(f + [bx, by, 0.6], 0.38, 8),
                                                   hcircle(f + [bx, by, 1.5], 0.38, 8)]))

    faces = [(LEGS[i], LEGS[(i + 1) % 4]) for i in range(4)]

    # horizontals (square bars on edge) at every level
    for z in levels:
        for a, b in faces:
            part("Tower_Bracing", "paint", diamond(leg(*a, z), leg(*b, z), 0.7))

    # X bracing; wide panels also get a horizontal through the X crossing,
    # which halves its bridge span
    for za, zb in zip(levels[:-1], levels[1:]):
        for a, b in faces:
            part("Tower_Bracing", "paint", beam(leg(*a, za), leg(*b, zb), 0.58, 8))
            part("Tower_Bracing", "paint", beam(leg(*b, za), leg(*a, zb), 0.58, 8))
        wa, wb = hw(za), hw(zb)
        if 2 * wa > 22:
            zm = za + (zb - za) * wa / (wa + wb)
            for a, b in faces:
                part("Tower_Bracing", "paint", diamond(leg(*a, zm), leg(*b, zm), 0.6))

    # plan bracing at the top + lightning rod
    part("Tower_Bracing", "paint", diamond(leg(-1, -1, ZT), leg(1, 1, ZT), 0.65))
    part("Tower_Bracing", "paint", diamond(leg(1, -1, ZT), leg(-1, 1, ZT), 0.65))
    part("Tower_Top", "steel", loft([hcircle([0, 0, ZT], 0.9, 10), hcircle([0, 0, ZT + 2.0], 0.55, 10),
                                      hcircle([0, 0, ZT + 17.0], 0.45, 10), hcircle([0, 0, ZT + 18.0], 0.15, 10)]))
    # obstruction light on top of the back-right leg
    c = leg(1, 1, ZT) + Z * 1.4
    part("Tower_Top", "dark", loft([hcircle(c - Z * 0.2, 0.75, 12), hcircle(c + Z * 0.6, 1.0, 12),
                                     hcircle(c + Z * 1.6, 1.0, 12), hcircle(c + Z * 2.1, 0.5, 12)]))

    # climbing ladder inside the front face, with ties to every horizontal
    inset = 2.4
    for x in (-2.0, 2.0):
        rings = [hcircle([x, -(hw(z) - inset), z], 0.45, 8) for z in ring_zs if z <= ZT - 2]
        rings.append(hcircle([x, -(hw(ZT - 2) - inset), ZT - 2], 0.45, 8))
        part("Tower_Ladder", "steel", loft(rings))
        for z in levels[1:]:
            if z <= ZT - 2:
                part("Tower_Ladder", "steel", diamond([x, -(hw(z) - inset), z], [x, -hw(z), z], 0.45))
    z = Z0 + 3.0
    while z < ZT - 3:
        y = -(hw(z) - inset)
        part("Tower_Ladder", "steel", diamond([-2.0, y, z], [2.0, y, z], 0.42, ext=0.1))
        z += 3.6
    return levels


# --------------------------------------------------------------------------
# Antennas, RRUs, microwave dishes and their mounts
# --------------------------------------------------------------------------
def unit(deg):
    a = math.radians(deg)
    return np.array([math.cos(a), math.sin(a), 0.0])


def mount(pxy, z_bot, z_top, legs, arm_zs, obj):
    """Vertical pipe tied back to tower legs. Its bottom end sits on a
    45-degree knee brace, so nothing starts in mid-air."""
    px, py = pxy
    part(obj, "steel", loft([hcircle([px, py, z_bot - 0.3], PIPE_R, 10), hcircle([px, py, z_top], PIPE_R, 10),
                             hcircle([px, py, z_top + 0.4], PIPE_R * 0.6, 10)]))
    for sx, sy in legs:
        for z in arm_zs:
            part(obj, "steel", diamond(leg(sx, sy, z), [px, py, z], 0.55))
        L = math.hypot(px - leg(sx, sy, z_bot)[0], py - leg(sx, sy, z_bot)[1])
        part(obj, "steel", beam(leg(sx, sy, z_bot - 1.12 * L), [px, py, z_bot + 0.2], 0.5, 8))


ANTENNAS = (  # direction, mounting legs, width, depth, bottom of the panel
    dict(ang=225, legs=((-1, -1),), w=6.0, d=2.6, zb=146.5),
    dict(ang=270, legs=((-1, -1), (1, -1)), w=8.6, d=2.9, zb=148.0),
    dict(ang=315, legs=((1, -1),), w=8.6, d=2.9, zb=148.0),
    dict(ang=0, legs=((1, -1), (1, 1)), w=6.0, d=2.6, zb=146.5),
    dict(ang=90, legs=((1, 1), (-1, 1)), w=8.6, d=2.9, zb=148.0),
    dict(ang=135, legs=((-1, 1),), w=6.0, d=2.6, zb=146.5),
)
ANT_TOP = ZT + 1.0
RRU_Z = (134.5, 142.5)
PIPE_Z = (131.5, ANT_TOP + 2.0)


def build_antennas():
    for a in ANTENNAS:
        u = unit(a["ang"])
        t = np.array([-u[1], u[0], 0.0])
        if len(a["legs"]) == 1:           # corner mount, out along the diagonal
            sx, sy = a["legs"][0]
            c = leg(sx, sy, 160)
            pxy = c[:2] + u[:2] * 5.5
        else:                              # face mount, in front of the face
            pxy = u[:2] * (hw(160) + 5.0)
        mount(pxy, PIPE_Z[0], PIPE_Z[1], a["legs"], (PIPE_Z[0], 160.0, ZT - 2.0), "Antenna_Mounts")
        p3 = lambda z: np.array([pxy[0], pxy[1], z])
        surf = lambda z: p3(z) + u * PIPE_R

        # panel antenna + clamps
        part("Antennas", "radome", hanging_box(surf(a["zb"]), u, a["w"], a["d"], a["zb"], ANT_TOP, r=0.7))
        for zc in (a["zb"] + 3.0, ANT_TOP - 3.0):
            c = p3(zc) + u * (PIPE_R * 0.5)
            q = [c + t * x + u * y for x, y in ((-1.2, -0.6), (1.2, -0.6), (1.2, 0.9), (-1.2, 0.9))]
            part("Antennas", "steel", loft([[p - Z * 0.6 for p in q], [p + Z * 0.6 for p in q]]))

        # remote radio unit under the antenna, and jumpers between the two
        part("RRUs", "rru", hanging_box(surf(RRU_Z[0]), u, 4.4, 2.4, RRU_Z[0], RRU_Z[1], r=0.4))
        tip = surf(0) + u * 0.4
        for off in (-0.5, 0.5):
            p = tip + t * off
            part("Cables", "cable", tube([p + Z * (RRU_Z[1] - 0.3), p + Z * (a["zb"] - 3.3)], 0.4, 8))

        # power / fibre from the RRU down to the tower legs (>= 50 degrees)
        h_tap = 1.05 * max((4.4 - 1.6) / 2, 2.4 - 1.2) + 0.2
        start = tip + Z * (RRU_Z[0] - h_tap + 0.3)
        for i, (sx, sy) in enumerate(a["legs"] * (2 if len(a["legs"]) == 1 else 1)):
            s = start + t * ((i - 0.5) * 0.7 if len(a["legs"]) == 1 else 0)
            p1 = s - Z * 1.2
            tgt = leg(sx, sy, p1[2] - 1.25 * np.linalg.norm(leg(sx, sy, p1[2])[:2] - p1[:2]) - 1.6 * i)
            part("Cables", "cable", tube(fillet([s, p1, tgt], 1.5), 0.42, 8))


DISHES = (  # leg, facing direction, centre height
    dict(leg=(-1, -1), ang=200, z=117.0),
    dict(leg=(1, -1), ang=-15, z=108.0),
    dict(leg=(-1, -1), ang=215, z=78.0),
)
DISH_R = 6.5


def build_dishes():
    for dsh in DISHES:
        u = unit(dsh["ang"])
        _, side, up = frame(u)
        zc, R = dsh["z"], DISH_R
        sx, sy = dsh["leg"]
        pxy = leg(sx, sy, zc)[:2] + u[:2] * 3.5
        pc = np.array([pxy[0], pxy[1], zc])
        drop = PIPE_R + 4.4
        z_bot = zc - R - drop - 0.6
        mount(pxy, z_bot, zc + R - 0.5, (dsh["leg"],), (z_bot, zc + 5.0), "Dish_Mounts")

        base = pc + u * PIPE_R
        ring = lambda s, r: circle(base + u * s, side, up, r, 40)
        part("Microwave_Dishes", "steel", loft([ring(*p) for p in (
            (-0.4, 2.0), (0.9, 2.0), (0.9, 3.2), (2.3, 6.25), (2.5, 6.45))]))
        part("Microwave_Dishes", "radome", loft([ring(*p) for p in (
            (2.4, 6.5), (4.3, 6.5), (4.6, 6.2), (4.9, 5.0), (5.05, 3.0))]))
        # mounting fin under the dish: its lower edge is a 45-degree ramp from
        # the pipe to the front of the rim, so the round dish has a floor to
        # grow from
        fin = [(0.0, -R - drop), (PIPE_R + 4.3, -R + 0.4), (0.0, -1.0)]
        part("Dish_Mounts", "steel", prism2d(fin, pc, u, Z, side, 1.0))


# --------------------------------------------------------------------------
# Cables down the tower and over the bridge into the shelter
# --------------------------------------------------------------------------
def bundle_y(z, k):
    return hw(z) - 2.2 - 1.15 * k


def build_cable_run():
    zc = TRAY_Z + 0.5
    rb = 3.0
    for k in range(3):
        zs = [z for z in sorted(set([176.0, zc + rb] + knot_zs()), reverse=True) if zc + rb <= z <= 176.0]
        pts = [np.array([hw(z) + 0.95, bundle_y(z, k), z]) for z in zs]
        xf, y = pts[-1][0], pts[-1][1]
        for a in np.linspace(180, 270, 8)[1:]:
            r = math.radians(a)
            pts.append(np.array([xf + rb + rb * math.cos(r), y, zc + rb + rb * math.sin(r)]))
        pts.append(np.array([SH["x0"] + 1.5, y, zc]))
        part("Cables", "cable", tube(pts, 0.5, 8))
        # down the shelter wall into the slab
        yw = bundle_y(zc, 1) + (k - 1) * 1.2
        part("Cables", "cable", tube([[SH["x0"] - 0.4, yw, 45.0], [SH["x0"] - 0.4, yw, 3.5]], 0.5, 8))


def build_cable_bridge():
    yc = bundle_y(TRAY_Z + 0.5, 1)
    x0, x1 = hw(TRAY_Z) - 0.6, SH["x0"] + 0.3
    obj = "Cable_Bridge"
    part(obj, "steel", box(x0, x1, yc - 2.6, yc + 2.6, TRAY_Z - 0.8, TRAY_Z))
    for ya, yb in ((yc - 2.6, yc - 2.0), (yc + 2.0, yc + 2.6)):
        part(obj, "steel", box(x0, x1, ya, yb, TRAY_Z - 0.8, TRAY_Z + 1.4))
    px = 29.1
    part(obj, "steel", box(px - 0.7, px + 0.7, yc - 0.7, yc + 0.7, 0.0, TRAY_Z - 0.6))
    part(obj, "concrete", box(px - 1.8, px + 1.8, yc - 1.8, yc + 1.8, -0.2, 0.9))
    # strut from the back-right leg up under the tray, steeper than 45 degrees
    tip = np.array([hw(TRAY_Z) + 5.0, yc, TRAY_Z - 0.7])
    zs = tip[2] - 1.15 * np.linalg.norm(leg(1, 1, tip[2])[:2] - tip[:2])
    part(obj, "steel", beam(leg(1, 1, zs), tip, 0.5, 4, np.pi / 4))


# --------------------------------------------------------------------------
# Shelter
# --------------------------------------------------------------------------
def blender_difference(vf, cutters):
    """Boolean difference with Blender's exact solver; returns triangles."""
    col = bpy.data.collections.new("_csg")
    bpy.context.scene.collection.children.link(col)
    base = mesh_object("_base", [vf], col)
    for i, c in enumerate(cutters):
        mesh_object("_cut%d" % i, [c], col)
    cut_col = bpy.data.collections.new("_csg_cut")
    for o in list(col.objects):
        if o is not base:
            cut_col.objects.link(o)
            col.objects.unlink(o)
    col.children.link(cut_col)
    mod = base.modifiers.new("cut", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.operand_type = "COLLECTION"
    mod.collection = cut_col
    mod.solver = "EXACT"
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(base.evaluated_get(dg))
    out = mesh_triangles(me)
    bpy.data.meshes.remove(me)
    for o in list(cut_col.objects) + [base]:
        m = o.data
        bpy.data.objects.remove(o)
        bpy.data.meshes.remove(m)
    bpy.data.collections.remove(cut_col)
    bpy.data.collections.remove(col)
    return out


def mesh_triangles(me, matrix=None, merge=0.0):
    bm = bmesh.new()
    bm.from_mesh(me)
    if matrix is not None:
        bm.transform(matrix)
    if merge:
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=merge)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    bm.verts.index_update()
    v = np.array([vv.co[:] for vv in bm.verts])
    f = [[vv.index for vv in face.verts] for face in bm.faces]
    bm.free()
    return v, f


def spiral(cx, cz, r0, r1, turns, w0, w1, y_wall, d_in, d_out, obj, mat):
    th = np.linspace(0, turns * 2 * np.pi, int(turns * 40))
    r = r0 + (r1 - r0) * th / th[-1]
    a = th + np.pi * 0.35
    path = np.stack([cx + r * np.cos(a), np.full_like(r, y_wall), cz + r * np.sin(a)], 1)
    widths = w0 + (w1 - w0) * th / th[-1]
    part(obj, mat, ribbon(path, widths, [0, -1, 0], d_in, d_out))


FONT = None


def text_part(body, size, x, y, z, extrude, obj, mat):
    global FONT
    if FONT is None:
        FONT = False
        for p in FONT_CANDIDATES:
            if os.path.exists(p):
                FONT = bpy.data.fonts.load(p)
                break
    cu = bpy.data.curves.new("_txt", "FONT")
    cu.body = body
    cu.size = size
    cu.extrude = extrude
    cu.align_x, cu.align_y = "CENTER", "CENTER"
    cu.resolution_u = 6
    if FONT:
        cu.font = FONT
    ob = bpy.data.objects.new("_txt", cu)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = (x, y, z)
    ob.rotation_euler = (math.pi / 2, 0, 0)          # face the -y wall normal
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    part(obj, mat, mesh_triangles(me, ob.matrix_world, merge=1e-4), tris=True)
    bpy.data.meshes.remove(me)
    bpy.data.objects.remove(ob)
    bpy.data.curves.remove(cu)


def build_shelter():
    x0, x1, y0, y1, z0, z1 = (SH[k] for k in ("x0", "x1", "y0", "y1", "z0", "z1"))
    door = (68.0, 86.6, z0 + 1.7, 47.3)
    vent = (45.8, 59.6, 7.4, 16.7)
    g, gd = 0.5, 0.3                  # panel seam width / depth
    cut = []
    # panel seams
    for x in (65.0, ):
        cut.append(box(x - g / 2, x + g / 2, y0 - 1, y0 + gd, z0 + 0.6, z1 - 0.6))
    for x in np.linspace(x0, x1, 7)[1:-1]:
        cut.append(box(x - g / 2, x + g / 2, y1 - gd, y1 + 1, z0 + 0.6, z1 - 0.6))
    for y in np.linspace(y0, y1, 6)[1:-1]:
        cut.append(box(x0 - 1, x0 + gd, y - g / 2, y + g / 2, z0 + 0.6, z1 - 0.6))
        cut.append(box(x1 - gd, x1 + 1, y - g / 2, y + g / 2, z0 + 0.6, z1 - 0.6))
    # door gap
    dx0, dx1, dz0, dz1 = door
    gg, gdp = 0.4, 0.45
    cut += [box(dx0 - gg, dx0, y0 - 1, y0 + gdp, dz0, dz1 + gg),
            box(dx1, dx1 + gg, y0 - 1, y0 + gdp, dz0, dz1 + gg),
            box(dx0 - gg, dx1 + gg, y0 - 1, y0 + gdp, dz1, dz1 + gg)]
    # louvre pocket
    cut.append(box(vent[0], vent[1], y0 - 1, y0 + 0.9, vent[2], vent[3]))
    body = blender_difference(box(x0, x1, y0, y1, z0, z1), cut)
    part("Shelter_Body", "shelter", body, tris=True)

    # roof slab: 45-degree chamfered drip edge, no support needed
    o = 0.8
    part("Shelter_Body", "shelter", loft([rect_ring(x0, x1, y0, y1, z1 - 0.6),
                                          rect_ring(x0 - o, x1 + o, y0 - o, y1 + o, z1 - 0.6 + o),
                                          rect_ring(x0 - o, x1 + o, y0 - o, y1 + o, z1 + 1.6),
                                          rect_ring(x0 - o + 0.3, x1 + o - 0.3, y0 - o + 0.3, y1 + o - 0.3, z1 + 1.9)]))
    # corner posts
    for cx in (x0, x1):
        for cy in (y0, y1):
            part("Shelter_Body", "shelter", box(cx - 0.8, cx + 0.8, cy - 0.8, cy + 0.8, z0, z1))
    # louvre slats, edge-down so each one bridges the pocket
    z = vent[2] + 0.9
    while z < vent[3] - 0.6:
        part("Shelter_Details", "grille", diamond([vent[0], y0 + 0.45, z], [vent[1], y0 + 0.45, z], 0.5, ext=0.0))
        z += 1.3
    # door frame, handle, hinges
    fr = 0.8
    for b in (box(dx0 - gg - fr, dx0 - gg, y0 - 0.3, y0 + 0.1, dz0 - 1.0, dz1 + gg + fr),
              box(dx1 + gg, dx1 + gg + fr, y0 - 0.3, y0 + 0.1, dz0 - 1.0, dz1 + gg + fr),
              box(dx0 - gg - fr, dx1 + gg + fr, y0 - 0.3, y0 + 0.1, dz1 + gg, dz1 + gg + fr)):
        part("Shelter_Details", "shelter", b)
    hz = 27.7
    part("Shelter_Details", "steel", box(dx0 + 1.2, dx0 + 2.2, y0 - 0.3, y0 + 0.1, hz - 2.2, hz + 1.6))
    part("Shelter_Details", "dark", box(dx0 + 1.45, dx0 + 1.95, y0 - 0.9, y0 - 0.1, hz - 0.3, hz + 0.3))
    part("Shelter_Details", "dark", diamond([dx0 + 1.45, y0 - 0.9, hz], [dx0 + 4.2, y0 - 0.9, hz], 0.36, ext=0.0))
    part("Shelter_Details", "dark", loft([hcircle([dx0 + 1.7, y0, hz - 1.5], 0.3, 8),
                                          hcircle([dx0 + 1.7, y0, hz - 1.5], 0.3, 8) + [0, 0, 0.6]]))
    for hzz in (11.0, 27.0, 42.0):
        part("Shelter_Details", "steel", loft([hcircle([dx1 + 0.2, y0 - 0.1, hzz - 0.6], 0.42, 8),
                                               hcircle([dx1 + 0.2, y0 - 0.1, hzz], 0.5, 8),
                                               hcircle([dx1 + 0.2, y0 - 0.1, hzz + 1.6], 0.5, 8)]))
    # bulkhead light over the door and the site sign
    dcx = (dx0 + dx1) / 2
    part("Shelter_Details", "lamp", hanging_box([dcx, y0, 50.5], [0, -1, 0], 4.2, 1.7, 50.5, 52.4,
                                                r=0.4, tip_w=4.2, tip_d=0.4, top_bevel=False))
    part("Shelter_Details", "steel", box(61.4, 66.0, y0 - 0.35, y0 + 0.1, 51.4, 54.4))

    # logo panel + logo (spiral and lettering), and the small one on the door
    lx = 52.7
    part("Shelter_Details", "shelter", box(lx - 8.2, lx + 8.2, y0 - 0.25, y0 + 0.1, 29.8, 50.2))
    spiral(lx, 43.4, 1.0, 5.5, 2.3, 0.6, 1.1, y0, 0.15, 0.6, "Logo", "logo")
    text_part("zain", 5.8, lx, y0 - 0.38, 34.0, 0.26, "Logo", "logo")
    spiral(dcx, 37.6, 0.35, 1.7, 1.6, 0.35, 0.5, y0, -0.1, 0.35, "Logo", "logo")
    text_part("zain", 2.6, dcx, y0 - 0.15, 33.0, 0.2, "Logo", "logo")

    # split air-conditioner on the left wall, sitting on two 45-degree brackets
    ac = dict(xo=x0 - 6.0, y0=-24.0, y1=-7.0, z0=39.6, z1=52.4)
    fan_y, fan_z, fan_r = -18.8, 46.0, 4.4
    ac_cut = [loft([circle([ac["xo"] - 1, fan_y, fan_z], [0, 1, 0], [0, 0, 1], fan_r, 32),
                    circle([ac["xo"] + 0.6, fan_y, fan_z], [0, 1, 0], [0, 0, 1], fan_r, 32)])]
    for zz in np.arange(ac["z0"] + 2.0, ac["z1"] - 1.5, 1.1):     # vent slots right of the fan
        ac_cut.append(box(ac["xo"] - 1, ac["xo"] + 0.35, -13.2, -8.4, zz, zz + 0.45))
    acb = blender_difference(rounded_plate(ac["xo"], x0 + 0.2, ac["y0"], ac["y1"], ac["z0"], ac["z1"], 0.6, 3), ac_cut)
    part("Air_Conditioner", "shelter", acb, tris=True)
    part("Air_Conditioner", "grille", loft([circle([ac["xo"] + 0.8, fan_y, fan_z], [0, 1, 0], [0, 0, 1], 1.3, 16),
                                            circle([ac["xo"] + 0.1, fan_y, fan_z], [0, 1, 0], [0, 0, 1], 1.3, 16)]))
    for ang in (45, 135):
        d = np.array([0, math.cos(math.radians(ang)), math.sin(math.radians(ang))])
        c = np.array([ac["xo"] + 0.45, fan_y, fan_z])
        part("Air_Conditioner", "grille", square_bar(c - d * (fan_r + 0.2), c + d * (fan_r + 0.2), 0.45))
    for yb in (ac["y0"] + 1.0, ac["y1"] - 1.0):
        tri = [(0.0, 0.0), (0.0, -6.2), (-5.6, 0.0)]
        part("Air_Conditioner", "steel", prism2d(tri, [x0 + 0.1, yb, ac["z0"] + 0.05],
                                                 [1, 0, 0], [0, 0, 1], [0, 1, 0], 0.9))
    # refrigerant pipes from the unit into the wall
    for i, zz in enumerate((41.2, 42.4)):
        part("Air_Conditioner", "steel", tube([[ac["xo"] + 3.0, ac["y1"] - 0.3, zz],
                                               [ac["xo"] + 3.0, ac["y1"] + 1.3 + i * 0.9, zz - 2.2],
                                               [ac["xo"] + 3.0, ac["y1"] + 1.3 + i * 0.9, 33.0],
                                               [x0 + 0.3, ac["y1"] + 1.3 + i * 0.9, 33.0]], 0.35, 8))

    # electrical box and conduit, cable entry plate
    part("Shelter_Details", "rru", hanging_box([x0, 5.5, 27.0], [-1, 0, 0], 8.0, 2.6, 13.0, 27.0,
                                               r=0.3, tip_w=8.0, tip_d=0.4))
    part("Shelter_Details", "steel", tube([[x0 - 0.9, 5.5, 3.5], [x0 - 0.9, 5.5, 12.0]], 0.5, 8))
    yc = bundle_y(TRAY_Z + 0.5, 1)
    part("Shelter_Details", "steel", hanging_box([x0, yc, 51.5], [-1, 0, 0], 7.0, 1.6, 44.5, 51.5,
                                                 r=0.3, tip_w=7.0, tip_d=0.4))


# --------------------------------------------------------------------------
# Ground, pads, fence
# --------------------------------------------------------------------------
def build_ground():
    bx0, bx1, by0, by1 = BASE
    part("Ground", "gravel", rounded_plate(bx0, bx1, by0, by1, -3.0, 0.0, 5.0))
    # tower pad with chamfered top edge
    p = 24.5
    part("Concrete", "concrete", loft([rect_ring(-p, p, -p, p, -0.2), rect_ring(-p, p, -p, p, Z0 - 0.6),
                                       rect_ring(-p + 0.6, p - 0.6, -p + 0.6, p - 0.6, Z0)]))
    sx0, sx1, sy0, sy1 = SH["x0"] - 2, SH["x1"] + 2, SH["y0"] - 2, SH["y1"] + 2
    part("Concrete", "concrete", loft([rect_ring(sx0, sx1, sy0, sy1, -0.2), rect_ring(sx0, sx1, sy0, sy1, 3.6),
                                       rect_ring(sx0 + 0.4, sx1 - 0.4, sy0 + 0.4, sy1 - 0.4, SH["z0"])]))
    part("Concrete", "concrete", box(65.8, 88.8, sy0 - 5.0, sy0 + 0.5, -0.2, 2.2))     # door step
    part("Concrete", "concrete", box(-28.0, -2.0, by0 + 1.5, -24.0, -0.2, 0.6))         # walkway


def build_fence():
    bx0, bx1, by0, by1 = BASE
    fx0, fx1, fy0, fy1 = bx0 + 3, bx1 - 3, by0 + 3, by1 - 3
    top, z_rail = 44.0, 40.5
    runs = [  # start, end, outward normal, post count
        ((fx0, -8.0), (fx0, fy1), (-1, 0), 3),
        ((fx0, fy1), (fx1, fy1), (0, 1), 7),
        ((fx1, fy1), (fx1, -8.0), (1, 0), 3),
    ]
    pitch, wire = 3.6, 0.8
    for (ax, ay), (bx, by), (nx, ny), npost in runs:
        a, b = np.array([ax, ay, 0.0]), np.array([bx, by, 0.0])
        length = np.linalg.norm(b - a)
        dvec = (b - a) / length
        out = np.array([nx, ny, 0.0])
        posts = [a + dvec * s for s in np.linspace(0, length, npost)]
        arm_pts = []
        for i, p in enumerate(posts):
            part("Fence", "fence", loft([hcircle(p - Z * 0.2, 0.85, 10), hcircle(p + Z * top, 0.85, 10)]))
            o = out.copy()
            if i in (0, npost - 1):        # corner posts lean out diagonally
                o = out + (-dvec if i == 0 else dvec) * 0.0
            arm_top = p + Z * top + o * 6.0 + Z * 6.0
            part("Fence", "fence", beam(p + Z * (top - 0.6), arm_top, 0.6, 8))
            arm_pts.append((p + Z * top, arm_top))
        for f in (0.55, 1.0):              # barbed wire strands
            pts = [s + (e - s) * f for s, e in arm_pts]
            part("Fence", "fence", tube(pts, 0.42, 8))
        part("Fence", "fence", tube([a + Z * z_rail, b + Z * z_rail], 0.6, 8))
        # chain-link mesh: 45-degree wires, self-supporting by nature
        z0, z1 = -0.3, z_rail + 0.3
        dz = z1 - z0
        for sign in (1, -1):
            c = -dz if sign > 0 else 0.0
            while c < length + dz:
                if sign > 0:
                    sa, sb = max(c, 0.0), min(c + dz, length)
                    za, zb = z0 + (sa - c), z0 + (sb - c)
                else:
                    sa, sb = max(c - dz, 0.0), min(c, length)
                    za, zb = z0 + (c - sa), z0 + (c - sb)
                if sb - sa > 0.6:
                    part("Fence", "fence", square_bar(a + dvec * sa + Z * za, a + dvec * sb + Z * zb, wire))
                c += pitch


# --------------------------------------------------------------------------
# Blender scene
# --------------------------------------------------------------------------
COLLECTION_OF = {
    "Ground": "Site", "Concrete": "Site", "Fence": "Site",
    "Tower_Legs": "Tower", "Tower_Bracing": "Tower", "Tower_Base": "Tower", "Tower_Top": "Tower",
    "Tower_Ladder": "Tower",
    "Antennas": "Antennas", "Antenna_Mounts": "Antennas", "RRUs": "Antennas",
    "Microwave_Dishes": "Microwave", "Dish_Mounts": "Microwave",
    "Cables": "Cables", "Cable_Bridge": "Cables",
    "Shelter_Body": "Shelter", "Shelter_Details": "Shelter", "Air_Conditioner": "Shelter", "Logo": "Shelter",
}


def mesh_object(name, vfs, collection, mat=None):
    verts, faces, off = [], [], 0
    for v, f in vfs:
        verts.append(np.asarray(v, float))
        faces.extend([[i + off for i in face] for face in f])
        off += len(v)
    me = bpy.data.meshes.new(name)
    me.from_pydata(np.vstack(verts).tolist(), [], faces)
    me.validate()
    ob = bpy.data.objects.new(name, me)
    collection.objects.link(ob)
    if mat is not None:
        me.materials.append(mat)
    return ob


def principled(name, color, rough=0.5, metal=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    m.diffuse_color = (*color, 1)
    return m, b


def noisy(m, b, scale, c1, c2, bump=0.0):
    nt = m.node_tree
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = scale
    n.inputs["Detail"].default_value = 8
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*c1, 1)
    ramp.color_ramp.elements[1].color = (*c2, 1)
    nt.links.new(n.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    if bump:
        bp = nt.nodes.new("ShaderNodeBump")
        bp.inputs["Strength"].default_value = bump
        nt.links.new(n.outputs["Fac"], bp.inputs["Height"])
        nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])


def tower_paint():
    """Red / white bands driven by world height, so the banding stays exact
    whatever the member layout."""
    m, b = principled("Tower_Paint", (0.85, 0.85, 0.84), 0.38)
    nt = m.node_tree
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Position"], sep.inputs[0])
    sub = nt.nodes.new("ShaderNodeMath")
    sub.operation = "SUBTRACT"
    sub.inputs[1].default_value = Z0
    div = nt.nodes.new("ShaderNodeMath")
    div.operation = "DIVIDE"
    div.inputs[1].default_value = BAND
    flo = nt.nodes.new("ShaderNodeMath")
    flo.operation = "FLOOR"
    mod = nt.nodes.new("ShaderNodeMath")
    mod.operation = "FLOORED_MODULO"
    mod.inputs[1].default_value = 2.0
    nt.links.new(sep.outputs["Z"], sub.inputs[0])
    nt.links.new(sub.outputs[0], div.inputs[0])
    nt.links.new(div.outputs[0], flo.inputs[0])
    nt.links.new(flo.outputs[0], mod.inputs[0])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    ins = {i.identifier: i for i in mix.inputs}
    ins["A_Color"].default_value = (0.86, 0.86, 0.85, 1)
    ins["B_Color"].default_value = (0.72, 0.035, 0.03, 1)
    nt.links.new(mod.outputs[0], ins["Factor_Float"])
    nt.links.new({o.identifier: o for o in mix.outputs}["Result_Color"], b.inputs["Base Color"])
    return m


def make_materials():
    M = {"paint": tower_paint()}
    M["steel"] = principled("Galvanised", (0.62, 0.63, 0.64), 0.42, 0.85)[0]
    M["fence"] = principled("Fence", (0.55, 0.56, 0.57), 0.5, 0.8)[0]
    M["radome"] = principled("Radome", (0.88, 0.88, 0.86), 0.55)[0]
    M["rru"] = principled("RRU_Grey", (0.42, 0.44, 0.45), 0.5, 0.2)[0]
    M["cable"] = principled("Cable", (0.012, 0.012, 0.012), 0.55)[0]
    M["shelter"] = principled("Shelter_Panel", (0.83, 0.83, 0.8), 0.45)[0]
    M["logo"] = principled("Logo_Purple", (0.33, 0.1, 0.5), 0.35)[0]
    M["dark"] = principled("Dark", (0.05, 0.05, 0.055), 0.4, 0.3)[0]
    M["grille"] = principled("Grille", (0.25, 0.25, 0.26), 0.5, 0.4)[0]
    M["lamp"] = principled("Lamp", (0.95, 0.95, 0.92), 0.2)[0]
    m, b = principled("Concrete", (0.6, 0.58, 0.55), 0.9)
    noisy(m, b, 0.35, (0.52, 0.5, 0.47), (0.68, 0.66, 0.62), 0.08)
    M["concrete"] = m
    m, b = principled("Gravel", (0.55, 0.5, 0.42), 1.0)
    noisy(m, b, 2.5, (0.42, 0.38, 0.31), (0.72, 0.67, 0.58), 0.4)
    M["gravel"] = m
    return M


def clear_scene():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.curves, bpy.data.cameras, bpy.data.lights):
        for d in list(coll):
            coll.remove(d)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)


def build_scene_objects():
    M = make_materials()
    scene = bpy.context.scene
    cols = {}
    grouped = defaultdict(list)
    for p in PARTS:
        grouped[(p["obj"], p["mat"])].append((p["v"], p["f"]))
    for (obj, mat), vfs in grouped.items():
        cname = COLLECTION_OF.get(obj, "Misc")
        if cname not in cols:
            cols[cname] = bpy.data.collections.new(cname)
            scene.collection.children.link(cols[cname])
        name = obj if sum(1 for k in grouped if k[0] == obj) == 1 else "%s_%s" % (obj, mat)
        ob = mesh_object(name, vfs, cols[cname], M[mat])
        for poly in ob.data.polygons:
            poly.use_smooth = True
        try:
            ob.data.set_sharp_from_angle(angle=math.radians(40))
        except AttributeError:
            pass
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 0.001
    scene.unit_settings.length_unit = "MILLIMETERS"


def setup_render_scene():
    scene = bpy.context.scene
    col = bpy.data.collections.new("Render_Only")
    scene.collection.children.link(col)
    m, b = principled("Desert", (0.55, 0.5, 0.42), 1.0)
    noisy(m, b, 0.05, (0.45, 0.4, 0.33), (0.66, 0.6, 0.5), 0.2)
    mesh_object("Desert_Ground", [box(-3000, 3000, -3000, 3000, -3.6, -3.05)], col, m)

    cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
    col.objects.link(cam)
    cam.data.lens = 24
    cam.data.clip_start = 1
    cam.data.clip_end = 20000
    scene.camera = cam
    aim_camera(cam, (-28, -255, 12), (32, 0, 98))

    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    col.objects.link(sun)
    sun.data.energy = 4.2
    sun.data.angle = math.radians(1.5)
    sun.data.color = (1.0, 0.9, 0.78)
    sun.rotation_euler = (math.radians(62), 0, math.radians(-38))

    world = bpy.data.worlds.new("Sky")
    scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    bg = nt.nodes["Background"]
    sky = nt.nodes.new("ShaderNodeTexSky")
    for st in ("PREETHAM", "HOSEK_WILKIE"):
        try:
            sky.sky_type = st
            break
        except TypeError:
            pass
    try:
        sky.sun_direction = (-0.55, -0.7, 0.45)
        sky.turbidity = 2.2
    except AttributeError:
        pass
    nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 0.45

    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = int(os.environ.get("SAMPLES", "64"))
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 1170
    scene.render.resolution_percentage = int(os.environ.get("RES", "100"))
    try:
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    return cam


def aim_camera(cam, loc, target):
    import mathutils
    cam.location = loc
    d = mathutils.Vector(target) - mathutils.Vector(loc)
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


# --------------------------------------------------------------------------
# Print export
# --------------------------------------------------------------------------
def triangles(p):
    if p["tris"]:
        return p["f"]
    out = []
    for face in p["f"]:
        out.extend([face[0], face[j], face[j + 1]] for j in range(1, len(face) - 1))
    return out


def write_stl(path, v, t):
    v = np.asarray(v, np.float32)
    t = np.asarray(t, np.int64)
    tri = v[t]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1), 1e-12)[:, None]
    rec = np.zeros(len(t), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    rec["n"], rec["v"] = n, tri
    with open(path, "wb") as fh:
        fh.write(b"Telecom tower site 1:50, units mm".ljust(80, b" "))
        fh.write(np.uint32(len(t)).tobytes())
        fh.write(rec.tobytes())


def export_print(out_dir):
    try:
        import manifold3d as m3
    except ImportError:
        print("manifold3d not installed: skipping STL export")
        return None
    groups = defaultdict(list)
    bad = 0
    # a few microns of sideways offset per part keeps symmetric members from
    # touching exactly along an edge (edges shared by four faces)
    rng = np.random.default_rng(7)
    for p in PARTS:
        jitter = np.append(rng.uniform(-0.004, 0.004, 2), 0.0)
        mesh = m3.Mesh(vert_properties=np.asarray(p["v"] + jitter, np.float32),
                       tri_verts=np.asarray(triangles(p), np.uint32))
        mesh.merge()
        mf = m3.Manifold(mesh)
        if mf.status() != m3.Error.NoError or mf.is_empty():
            bad += 1
            print("  non-manifold part skipped:", p["obj"], p["mat"], mf.status())
            continue
        groups[GROUP_OF[p["mat"]]].append(mf)
    print("parts:", len(PARTS), "rejected:", bad)
    U = {g: m3.Manifold.batch_boolean(ms, m3.OpType.Add) for g, ms in groups.items()}

    # red bands of the tower
    big = 400.0
    red = m3.Manifold.batch_boolean(
        [m3.Manifold.cube([big, big, BAND]).translate([-big / 2, -big / 2, Z0 + BAND * i])
         for i in range(1, BANDS, 2)] +
        [m3.Manifold.cube([big, big, 50.0]).translate([-big / 2, -big / 2, ZT])]
        if BANDS % 2 == 0 else [], m3.OpType.Add)
    U["red"] = U["tower"] ^ red
    U["white"] = U["white"] + (U["tower"] - red)
    del U["tower"]

    full = m3.Manifold.batch_boolean(list(U.values()), m3.OpType.Add)
    os.makedirs(out_dir, exist_ok=True)
    stats = {}

    def save(name, mf):
        msh = mf.to_mesh()
        v, t = np.asarray(msh.vert_properties)[:, :3], np.asarray(msh.tri_verts)
        write_stl(os.path.join(out_dir, name), v, t)
        stats[name] = (len(t), mf.volume(), mf.genus())
        print("  %-28s %8d tris  %9.0f mm3" % (name, len(t), mf.volume()))

    save("zain_tower_site_full.stl", full)
    # colour split: disjoint bodies that share one origin, load them as parts of
    # one object in the slicer
    order = ["purple", "black", "red", "white", "grey"]
    taken = None
    cdir = os.path.join(out_dir, "colors")
    os.makedirs(cdir, exist_ok=True)
    for g in order:
        body = U[g] if taken is None else U[g] - taken
        taken = U[g] if taken is None else taken + U[g]
        save(os.path.join("colors", "%s.stl" % g), body)
    return full, stats


def print_report(full, levels):
    """Count the islands a slicer would need support for: cross-sections that
    start a layer with nothing underneath, plus the downward faces steeper
    than 45 degrees (most of them are bridges)."""
    import manifold3d as m3
    msh = full.to_mesh()
    v, t = np.asarray(msh.vert_properties)[:, :3], np.asarray(msh.tri_verts)
    tri = v[t]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    area = np.linalg.norm(n, axis=1) / 2
    nz = n[:, 2] / np.maximum(2 * area, 1e-12)
    low = tri[:, :, 2].min(1)
    over = (nz < -0.7072) & (low > -2.95)
    print("overhang > 45deg (not on bed): %.0f mm2 of %.0f mm2 surface" % (area[over].sum(), area.sum()))

    layer = 0.2
    prev = None
    islands = []
    z = -3.0 + layer / 2
    while z < v[:, 2].max():
        comps = [(c.bounds(), c) for c in full.slice(z).decompose()]
        if prev is not None:
            for b, comp in comps:
                below = [pc for pb, pc in prev
                         if pb[0] <= b[2] and pb[2] >= b[0] and pb[1] <= b[3] and pb[3] >= b[1]]
                if comp.area() > 1e-3 and all((comp ^ pc).area() < 1e-4 for pc in below):
                    islands.append((round(z, 2), [round(x, 1) for x in b], round(comp.area(), 3)))
        prev = comps
        z += layer
    print("unsupported islands at 0.2 mm layers:", len(islands))
    for isl in islands[:40]:
        print("   z=%s bounds=%s area=%s" % isl)
    return islands


def build():
    clear_scene()
    PARTS.clear()
    build_ground()
    levels = build_tower()
    build_antennas()
    build_dishes()
    build_cable_run()
    build_cable_bridge()
    build_shelter()
    build_fence()
    build_scene_objects()
    return levels


def main():
    levels = build()
    print("tower levels:", [round(z, 1) for z in levels])
    if not bpy.app.background:
        return
    cam = setup_render_scene()
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "zain_tower_site.blend"), compress=True)
    res = export_print(os.path.join(OUT, "stl"))
    if res and os.environ.get("REPORT", "1") == "1":
        print_report(res[0], levels)
    if os.environ.get("RENDER"):
        render_previews(cam)
        if res:
            render_print_check(cam, res[0])


def render_previews(cam):
    scene = bpy.context.scene
    rdir = os.path.join(OUT, "renders")
    os.makedirs(rdir, exist_ok=True)
    views = {
        "photo_match": ((-14, -265, 24), (42, 0, 103), 37),
        "three_quarter": ((-190, -230, 150), (28, 0, 70), 35),
        "shelter_close": ((-20, -120, 30), (60, -10, 40), 30),
        "antenna_close": ((-70, -95, 185), (0, 0, 150), 35),
    }
    only = os.environ.get("VIEWS")
    for name, (loc, tgt, lens) in views.items():
        if only and name not in only.split(","):
            continue
        aim_camera(cam, loc, tgt)
        cam.data.lens = lens
        scene.render.filepath = os.path.join(rdir, name + ".png")
        bpy.ops.render.render(write_still=True)


def render_print_check(cam, full):
    """Render the exported print solid: red = downward faces flatter than 45
    degrees (on this model those are short bridges), grey = prints unaided."""
    scene = bpy.context.scene
    msh = full.to_mesh()
    v, t = np.asarray(msh.vert_properties)[:, :3], np.asarray(msh.tri_verts)
    for c in scene.collection.children:
        if c.name != "Render_Only":
            c.hide_render = True
    col = bpy.data.collections.new("Print_Check")
    scene.collection.children.link(col)
    m, b = principled("Overhang_Check", (0.7, 0.7, 0.72), 0.6)
    nt = m.node_tree
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep_n, sep_p = nt.nodes.new("ShaderNodeSeparateXYZ"), nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["True Normal"], sep_n.inputs[0])
    nt.links.new(geo.outputs["Position"], sep_p.inputs[0])
    lt, gt, mul = (nt.nodes.new("ShaderNodeMath") for _ in range(3))
    lt.operation, gt.operation, mul.operation = "LESS_THAN", "GREATER_THAN", "MULTIPLY"
    lt.inputs[1].default_value = -0.7072
    gt.inputs[1].default_value = -2.9
    nt.links.new(sep_n.outputs["Z"], lt.inputs[0])
    nt.links.new(sep_p.outputs["Z"], gt.inputs[0])
    nt.links.new(lt.outputs[0], mul.inputs[0])
    nt.links.new(gt.outputs[0], mul.inputs[1])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    ins = {i.identifier: i for i in mix.inputs}
    ins["A_Color"].default_value = (0.72, 0.72, 0.74, 1)
    ins["B_Color"].default_value = (0.9, 0.05, 0.05, 1)
    nt.links.new(mul.outputs[0], ins["Factor_Float"])
    nt.links.new({o.identifier: o for o in mix.outputs}["Result_Color"], b.inputs["Base Color"])
    mesh_object("Print_Solid", [(v, t.tolist())], col, m)
    rdir = os.path.join(OUT, "renders")
    for name, loc, tgt in (("print_check_front", (-190, -230, 150), (28, 0, 70)),
                           ("print_check_below", (-160, -200, 20), (28, 0, 80))):
        aim_camera(cam, loc, tgt)
        cam.data.lens = 35
        scene.render.filepath = os.path.join(rdir, name + ".png")
        bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
