# -*- coding: utf-8 -*-
"""
Al-Hadba Minaret (Mosul, Iraq) - souvenir relief plaque / fridge magnet.

Fully procedural Blender scene (tested on Blender 5.3, should run on 4.x too).

HOW TO USE
  * Inside Blender: open the "Scripting" tab, open this file, press "Run Script".
  * Command line:
        blender --background --python hadba_magnet.py -- --save hadba.blend --render hadba.png

WHAT IT BUILDS  (1 Blender unit = 1 cm, plaque = 6.0 x 8.95 x 0.45 cm)
  * Plaque         : arched-top tablet with soft bevelled edges.
  * Relief         : minaret (lathe body with brick patterns: hazarbaf checker,
                     chevron band, diamond lattice), lantern + dome, base block
                     with lattice panels, brick podium, stairs, ruins with arches.
                     Generated as a 16-bit height map -> Subdivision + Displace
                     modifiers (change "Strength" of the Displace modifier to make
                     the relief deeper/shallower; apply both to get real mesh).
  * Text           : real (editable) Text objects. The arched title follows an
                     arc curve through a Curve modifier - edit the text freely.
  * Material, lights, camera, floor, Cycles render settings.
"""

import bpy
import bmesh
import math
import os
import sys
import struct
import zlib

import numpy as np

# ---------------------------------------------------------------------------
#  Global layout: everything is drawn in "reference pixels" (the 1024x1024
#  reference picture) and converted to centimetres.
# ---------------------------------------------------------------------------
S = 6.0 / 553.0          # cm per reference pixel (plaque is 553 px = 6 cm wide)
CX, CY = 513.0, 532.0    # reference pixel that becomes the world origin

PLAQUE_THICK = 0.45      # cm
PLAQUE_BEVEL = 0.075     # cm

# plaque outline (reference px)
PL_LEFT, PL_RIGHT, PL_BOTTOM = 237.0, 790.0, 945.0
ARCH_TOP = 120.0
ARCH_SIDE_Y = 230.0      # where the arch meets the vertical sides
CORNER_R_BOTTOM = 28.0
CORNER_R_TOP = 26.0

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "C:/Windows/Fonts/timesbd.ttf",
    "C:/Windows/Fonts/georgiab.ttf",
    "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf",
    "/Library/Fonts/Georgia Bold.ttf",
]

# printable (watertight) mesh
PRINT_RES = 0.006         # cm grid step of the printable surface (60 micron)
PRINT_TEXT_H = 0.09       # cm height of the raised letters
PRINT_DECIMATE = 0.35     # keep this fraction of triangles on the relief (1 = off)
BUILD_PRINT_MESH = True   # also create the watertight "Magnet_PRINT" object

# height-map resolution (the relief mesh = BASE grid x 2^SUB subdivision)
NX_BASE, NY_BASE, SUB_RENDER, SUB_VIEW = 70, 94, 4, 3


def P(px, py):
    """reference pixel -> world cm (x, y)"""
    return ((px - CX) * S, (CY - py) * S)


# ---------------------------------------------------------------------------
#  Small numpy helpers (signed distance fields etc.)
# ---------------------------------------------------------------------------
def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def shoulder(sdf, b):
    """rounded-edge profile: 0 outside, rises to 1 within b px inside the shape"""
    p = np.clip(-sdf / b, 0.0, 1.0)
    return 1.0 - (1.0 - p) ** 2


def sdf_poly(pts, X, Y):
    pts = np.asarray(pts, dtype=np.float64)
    d2 = np.full(X.shape, np.inf)
    inside = np.zeros(X.shape, dtype=bool)
    n = len(pts)
    for i in range(n):
        ax, ay = pts[i]
        bx, by = pts[(i + 1) % n]
        ex, ey = bx - ax, by - ay
        wx, wy = X - ax, Y - ay
        t = np.clip((wx * ex + wy * ey) / (ex * ex + ey * ey), 0.0, 1.0)
        dx, dy = wx - ex * t, wy - ey * t
        d2 = np.minimum(d2, dx * dx + dy * dy)
        if ay != by:
            cond = ((ay > Y) != (by > Y)) & (X < ex * (Y - ay) / ey + ax)
            inside ^= cond
    d = np.sqrt(d2)
    return np.where(inside, -d, d)


def sdf_box(x0, y0, x1, y1, X, Y, r=0.0):
    cx, cy = (x0 + x1) * 0.5, (y0 + y1) * 0.5
    hx, hy = (x1 - x0) * 0.5 - r, (y1 - y0) * 0.5 - r
    qx, qy = np.abs(X - cx) - hx, np.abs(Y - cy) - hy
    outside = np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qy, 0) ** 2)
    inside = np.minimum(np.maximum(qx, qy), 0.0)
    return outside + inside - r


def sdf_circle(cx, cy, r, X, Y):
    return np.sqrt((X - cx) ** 2 + (Y - cy) ** 2) - r


def sdf_arch(x0, x1, y_spring, y_bottom, X, Y):
    """round-headed arch opening (semi-circle on top of a rectangle)"""
    r = (x1 - x0) * 0.5
    box = sdf_box(x0, y_spring, x1, y_bottom, X, Y)
    circ = sdf_circle((x0 + x1) * 0.5, y_spring, r, X, Y)
    return np.minimum(box, circ)


def brick_grooves(X, Y, bw, bh, gw, ox=0.0, oy=0.0):
    """1.0 inside mortar joints, 0.0 on bricks (running bond)"""
    yy = Y - oy
    row = np.floor(yy / bh)
    xx = X - ox + (np.mod(row, 2.0)) * bw * 0.5
    fx, fy = np.mod(xx, bw), np.mod(yy, bh)
    dx = np.minimum(fx, bw - fx)
    dy = np.minimum(fy, bh - fy)
    return 1.0 - smoothstep(0.25 * gw, gw, np.minimum(dx, dy))


def value_noise(shape, cell, seed):
    """smooth random field in [-1,1] (bilinear interpolated lattice noise)"""
    rng = np.random.default_rng(seed)
    gh, gw = int(shape[0] / cell) + 3, int(shape[1] / cell) + 3
    g = rng.uniform(-1, 1, (gh, gw))
    yy = np.arange(shape[0]) / cell
    xx = np.arange(shape[1]) / cell
    y0 = np.floor(yy).astype(int)
    x0 = np.floor(xx).astype(int)
    ty = smoothstep(0, 1, yy - y0)[:, None]
    tx = smoothstep(0, 1, xx - x0)[None, :]
    a = g[y0][:, x0]
    b = g[y0][:, x0 + 1]
    c = g[y0 + 1][:, x0]
    d = g[y0 + 1][:, x0 + 1]
    return (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty


def blur(a, sigma):
    """small separable gaussian blur (pure numpy)"""
    rad = max(1, int(math.ceil(sigma * 3)))
    k = np.exp(-0.5 * (np.arange(-rad, rad + 1) / sigma) ** 2)
    k /= k.sum()
    out = np.zeros_like(a)
    pad = np.pad(a, ((0, 0), (rad, rad)), mode="edge")
    for i, w in enumerate(k):
        out += w * pad[:, i:i + a.shape[1]]
    pad = np.pad(out, ((rad, rad), (0, 0)), mode="edge")
    out2 = np.zeros_like(a)
    for i, w in enumerate(k):
        out2 += w * pad[i:i + a.shape[0], :]
    return out2


def write_png16(path, arr01):
    """write a 16-bit grayscale PNG with nothing but zlib (row 0 = top)"""
    a = np.clip(arr01, 0.0, 1.0)
    a = np.round(a * 65535.0).astype(">u2")
    h, w = a.shape
    raw = b"".join(b"\x00" + a[r].tobytes() for r in range(h))

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 16, 0, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9))
    png += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


# ---------------------------------------------------------------------------
#  Height map canvas
# ---------------------------------------------------------------------------
class Canvas:
    def __init__(self):
        self.nx = NX_BASE * 2 ** SUB_RENDER
        self.ny = NY_BASE * 2 ** SUB_RENDER
        self.px0, self.px1 = 258.0, 768.0
        self.spp = self.nx / (self.px1 - self.px0)          # samples / ref px
        self.py0 = 190.0
        self.py1 = self.py0 + self.ny / self.spp
        self.W, self.H = self.nx + 1, self.ny + 1
        self.xs = np.linspace(self.px0, self.px1, self.W)
        self.ys = np.linspace(self.py0, self.py1, self.H)
        self.Z = np.zeros((self.H, self.W))

    def window(self, x0, y0, x1, y1, m=6.0):
        i0 = max(0, int((y0 - m - self.py0) * self.spp))
        i1 = min(self.H, int((y1 + m - self.py0) * self.spp) + 2)
        j0 = max(0, int((x0 - m - self.px0) * self.spp))
        j1 = min(self.W, int((x1 + m - self.px0) * self.spp) + 2)
        X, Y = np.meshgrid(self.xs[j0:j1], self.ys[i0:i1])
        return (slice(i0, i1), slice(j0, j1)), X, Y

    def put_max(self, sl, z):
        self.Z[sl] = np.maximum(self.Z[sl], z)


def poly_bbox(pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def wall(cv, pts, h, bricks=(15.0, 7.5), gdepth=0.010, holes=(), seed=1,
         bevel=2.2, rough=0.004):
    """flat raised wall with brick joints, optional recessed openings.
    holes: list of (sdf_fn(X,Y), depth_cm)"""
    sl, X, Y = cv.window(*poly_bbox(pts))
    d = sdf_poly(pts, X, Y)
    z = h * shoulder(d, bevel)
    inner = shoulder(d, bevel * 1.5)
    if bricks:
        z -= gdepth * brick_grooves(X, Y, bricks[0], bricks[1], 1.1,
                                    ox=seed * 3.7) * inner
    if rough:
        z += rough * value_noise(X.shape, 9.0 * cv.spp, seed) * inner
    for fn, depth in holes:
        hd = fn(X, Y)
        z -= depth * shoulder(hd, 1.6)
    cv.put_max(sl, np.where(d < 0.5, z, 0.0) * (z > 0))


# ---------------------------------------------------------------------------
#  Minaret (lathe body -> bas-relief)
# ---------------------------------------------------------------------------
MIN_K = 0.72          # depth flattening of the round body
SHAFT_TOP, SHAFT_BOT = 300.0, 592.0


def minaret_center(py):
    # leaning "hunchback" axis: bottom (497,592) -> top (531,300) + small bow
    s = np.clip((SHAFT_BOT - py) / (SHAFT_BOT - SHAFT_TOP), 0.0, 1.35)
    return 497.0 + 34.0 * s + 3.0 * np.sin(np.pi * np.clip(s, 0, 1))


def minaret_profile():
    """(py, radius px) from the finial down to the foot of the shaft"""
    prof = [(219, 0.0), (220.5, 1.6), (222.5, 2.2), (225, 1.5), (226.5, 3.2),
            (229, 3.5), (231.5, 2.3), (233, 2.0)]
    # onion-ish dome
    for i in range(0, 13):
        a = i / 12.0
        py = 233 + 18.0 * a
        r = 2.0 + 15.5 * math.sin(a * math.pi * 0.5) ** 0.8
        prof.append((py, r))
    prof += [(251.5, 18.5), (254.5, 18.5), (255.3, 16.2),         # dome ring
             (275, 16.2), (276, 30.0), (278, 33.5), (288, 33.5),   # balcony
             (290, 31.5), (291, 30.0), (300, 27.0)]                # corbel
    rings = [(300, 305), (418, 426), (478, 486), (584, 592)]
    n = 60
    for i in range(1, n + 1):
        py = 300 + (592 - 300) * i / n
        prof.append((py, 27.0 + 15.0 * (py - 300) / 292.0))
    prof.sort()
    pys = np.array([p[0] for p in prof])
    rs = np.array([p[1] for p in prof])
    return pys, rs, rings


def shaft_pattern(U, V):
    """offset in cm for the brick patterns on the shaft (U arc-length px)"""
    off = np.zeros_like(U)

    # --- upper band : hazarbaf checker (staggered raised / recessed bricks)
    m = smoothstep(305, 307, V) * (1 - smoothstep(416, 418, V))
    bw, bh = 7.0, 6.0
    row = np.floor(V / bh)
    uu = U + np.mod(row, 2) * bw * 0.5
    cell = np.mod(np.floor(uu / bw), 2)
    fx = np.mod(uu, bw)
    fy = np.mod(V, bh)
    joint = 1 - smoothstep(0.3, 1.1, np.minimum(np.minimum(fx, bw - fx),
                                               np.minimum(fy, bh - fy)))
    off += m * (-0.016 * cell - 0.008 * joint)

    # --- middle band : chevron / zigzag
    m = smoothstep(426, 428, V) * (1 - smoothstep(476, 478, V))
    zz = np.abs(np.mod(U / 16.0, 1.0) - 0.5) * 2.0 * 9.0
    w = V - 426 + zz
    stripe = np.mod(np.floor(w / 6.5), 2)
    fw = np.mod(w, 6.5)
    jw = 1 - smoothstep(0.3, 1.0, np.minimum(fw, 6.5 - fw))
    off += m * (-0.015 * stripe - 0.007 * jw)

    # --- lower band : diamond lattice with bosses
    m = smoothstep(486, 488, V) * (1 - smoothstep(582, 584, V))
    p = 12.0
    a = (U + V * 0.85) / p
    b = (U - V * 0.85) / p
    da = np.abs(a - np.round(a)) * p
    db = np.abs(b - np.round(b)) * p
    line = np.minimum(da, db)
    hole = smoothstep(1.0, 2.0, line)
    boss = 1 - smoothstep(1.3, 2.4, np.maximum(np.abs(np.mod(a, 1) - 0.5),
                                               np.abs(np.mod(b, 1) - 0.5)) * p)
    off += m * (-0.020 * hole + 0.012 * boss)

    # --- thin rings between bands
    for v0, v1 in [(300, 305), (418, 426), (478, 486), (584, 592)]:
        rm = smoothstep(v0, v0 + 1.2, V) * (1 - smoothstep(v1 - 1.2, v1, V))
        mid = (v0 + v1) * 0.5
        off += rm * (0.006 - 0.006 * (1 - smoothstep(0.2, 0.9, np.abs(V - mid))))
    return off


def build_minaret(cv):
    pys, rs, rings = minaret_profile()
    # make rings a touch fatter
    for v0, v1 in rings:
        sel = (pys >= v0) & (pys <= v1)
        rs[sel] += 1.6
    x0, x1 = 440.0, 580.0
    sl, X, Y = cv.window(x0, 200.0, x1, 594.0)
    R = np.interp(Y, pys, rs, left=0.0, right=0.0)
    # soften radius steps a little (rounded mouldings)
    Rb = blur(R, 0.9 * cv.spp)
    R = np.where(R > 0, np.maximum(Rb, 0.0), 0.0)
    Cx = minaret_center(Y)
    with np.errstate(divide="ignore", invalid="ignore"):
        T = np.where(R > 0.05, (X - Cx) / np.maximum(R, 0.05), 9.0)
    inside = np.abs(T) < 1.0
    T = np.clip(T, -1.0, 1.0)
    c = np.sqrt(np.maximum(0.0, 1.0 - T * T))
    z = MIN_K * R * S * c
    U = R * np.arcsin(T)                     # arc length around the shaft
    fade = np.sqrt(c)

    off = np.zeros_like(z)
    shaft = (Y >= 300) & (Y <= 592)
    off += np.where(shaft, shaft_pattern(U, Y), 0.0)

    # lantern window slots
    lm = smoothstep(259, 261, Y) * (1 - smoothstep(271, 273, Y))
    su = np.abs(np.mod(U / 9.0, 1.0) - 0.5) * 9.0
    arch_top = smoothstep(259, 263, Y + (2.2 - np.minimum(su, 2.2)) * 1.5)
    off -= 0.03 * lm * (1 - smoothstep(1.4, 2.4, su)) * arch_top
    # balcony balusters
    bm = smoothstep(279.5, 280.5, Y) * (1 - smoothstep(286.5, 287.5, Y))
    bu = np.abs(np.mod(U / 4.5, 1.0) - 0.5) * 4.5
    off -= 0.012 * bm * (1 - smoothstep(0.4, 1.0, bu))
    # corbel flutes (muqarnas hint)
    cm = smoothstep(291, 292, Y) * (1 - smoothstep(298, 299.5, Y))
    cu = np.abs(np.mod(U / 5.5, 1.0) - 0.5) * 5.5
    off -= 0.012 * cm * (1 - smoothstep(0.5, 1.4, cu))
    # dome rib ring + finial bead
    off += 0.004 * np.exp(-((Y - 242.0) / 1.2) ** 2)

    z = z + off * fade
    z = np.where(inside, np.maximum(z, 0.0), 0.0)
    cv.put_max(sl, z)


# ---------------------------------------------------------------------------
#  Base block under the shaft (seen corner-on)
# ---------------------------------------------------------------------------
def build_base(cv):
    corner = 507.0

    def face(X, lo=0.205, hi=0.285, l=418.0, r=579.0):
        return np.where(X < corner,
                        lo + (hi - lo) * (X - l) / (corner - l),
                        hi - (hi - lo) * (X - corner) / (r - corner))

    # body
    sl, X, Y = cv.window(412, 588, 584, 704)
    d = sdf_box(419, 604, 578, 703, X, Y, r=1.0)
    z = face(X) * shoulder(d, 2.4)
    # corner pilaster (front-facing chamfer)
    pd = sdf_box(491, 606, 523, 703, X, Y, r=1.0)
    z = np.maximum(z, (0.292 + 0.004 * np.cos((X - corner) / 16 * 1.57)) * shoulder(pd, 2.0))
    # lattice panels
    for (a, b, c_, e) in [(427, 614, 485, 695), (529, 614, 571, 695)]:
        pdist = sdf_box(a, b, c_, e, X, Y, r=1.0)
        pm = shoulder(pdist, 1.6)
        p = 9.0
        A = (X + Y) / p
        B = (X - Y) / p
        line = np.minimum(np.abs(A - np.round(A)), np.abs(B - np.round(B))) * p
        lat = 1 - smoothstep(0.9, 1.8, line)
        z -= pm * (0.028 - 0.020 * lat)
    # brick joints on pilaster
    z -= 0.007 * brick_grooves(X, Y, 16, 7, 1.0) * shoulder(pd, 3.0)
    cv.put_max(sl, np.where(d < 0.5, z, 0.0))

    # cornice + dentils
    sl, X, Y = cv.window(408, 586, 588, 612)
    d = sdf_box(411, 589, 584, 604, X, Y, r=1.5)
    z = (face(X, 0.235, 0.318, 411, 584)) * shoulder(d, 2.2)
    z -= 0.010 * np.exp(-((Y - 596.5) / 0.9) ** 2)
    cv.put_max(sl, np.where(d < 0.5, z, 0.0))
    sl, X, Y = cv.window(414, 603, 582, 610)
    dx = np.abs(np.mod(X - 414, 7.0) - 3.5)
    d = np.maximum(sdf_box(416, 603.5, 580, 609, X, Y), dx - 2.3)
    z = (face(X, 0.218, 0.300, 416, 580)) * shoulder(d, 1.0)
    cv.put_max(sl, np.where(d < 0.5, z, 0.0))


# ---------------------------------------------------------------------------
#  Podium, stairs and ruins
# ---------------------------------------------------------------------------
def build_podium(cv):
    # big brick mass under the base block, sloping (battered) left side
    pts = [(424, 702), (583, 702), (586, 858), (377, 858), (377, 850)]
    sl, X, Y = cv.window(*poly_bbox(pts))
    d = sdf_poly(pts, X, Y)
    # battered left face: lower plane near the slope
    slope_x = 424 + (Y - 702) * (377 - 424) / (850 - 702)
    t = smoothstep(0, 26, X - slope_x)
    zf = 0.125 + 0.065 * t
    z = zf * shoulder(d, 2.4)
    inner = shoulder(d, 3.0)
    z -= 0.011 * brick_grooves(X, Y, 15.0, 7.4, 1.1, ox=2.0) * inner
    z += 0.003 * value_noise(X.shape, 10 * cv.spp, 7) * inner
    # small arched doorway
    z -= 0.07 * shoulder(sdf_arch(546, 568, 826, 860, X, Y), 1.5)
    # horizontal string course
    z += 0.008 * (smoothstep(742, 743, Y) * (1 - smoothstep(746, 747, Y))) * inner
    cv.put_max(sl, np.where(d < 0.5, z, 0.0))

    # stairs climbing up to the right
    steps = 9
    for k in range(steps):
        y1 = 858.0 - k * 7.4
        y0 = y1 - 7.4
        x0 = 436.0 + k * 7.6
        sl, X, Y = cv.window(x0, y0, 520, y1)
        d = sdf_box(x0, y0, 520, y1 + 0.5, X, Y, r=0.8)
        z = (0.205 + 0.004 * k) * shoulder(d, 1.6)
        z -= 0.008 * brick_grooves(X, Y, 14.0, 7.4, 1.0, oy=y1) * shoulder(d, 2.5)
        cv.put_max(sl, np.where(d < 0.5, z, 0.0))


def build_ruins(cv):
    # ---- left side
    wall(cv, [(284, 784), (298, 784), (298, 772), (329, 772), (329, 763),
              (348, 763), (352, 757), (372, 757), (372, 751), (410, 751),
              (412, 858), (284, 858)], 0.085, seed=11,
         holes=[(lambda X, Y: sdf_box(338, 776, 358, 800, X, Y, 1), 0.04),
                (lambda X, Y: sdf_box(380, 768, 398, 790, X, Y, 1), 0.04),
                (lambda X, Y: sdf_arch(366, 392, 820, 858, X, Y), 0.05)])
    wall(cv, [(278, 810), (302, 810), (302, 803), (322, 803), (322, 797),
              (352, 797), (352, 858), (278, 858)], 0.125, seed=12,
         holes=[(lambda X, Y: sdf_box(289, 822, 307, 846, X, Y, 1), 0.05),
                (lambda X, Y: sdf_box(325, 812, 342, 832, X, Y, 1), 0.04)])
    # ---- right side
    wall(cv, [(700, 712), (716, 712), (716, 700), (727, 700), (727, 691),
              (753, 691), (753, 858), (700, 858)], 0.09, seed=21,
         holes=[(lambda X, Y: sdf_box(724, 722, 743, 760, X, Y, 1), 0.04),
                (lambda X, Y: sdf_box(724, 790, 743, 830, X, Y, 1), 0.04)])
    wall(cv, [(588, 748), (600, 748), (600, 742), (628, 742), (628, 736),
              (662, 736), (662, 730), (690, 730), (690, 724), (704, 724),
              (706, 858), (588, 858)], 0.135, seed=22,
         holes=[(lambda X, Y: sdf_arch(600, 634, 812, 860, X, Y), 0.075),
                (lambda X, Y: sdf_arch(651, 685, 812, 860, X, Y), 0.075),
                (lambda X, Y: sdf_box(612, 758, 624, 778, X, Y, 1), 0.03),
                (lambda X, Y: sdf_box(663, 750, 675, 770, X, Y, 1), 0.03)])
    # raised archivolts around the two arches
    for (a, b) in [(600, 634), (651, 685)]:
        sl, X, Y = cv.window(a - 6, 790, b + 6, 860)
        outer = sdf_arch(a - 4.5, b + 4.5, 812, 858, X, Y)
        inner = sdf_arch(a, b, 812, 860, X, Y)
        d = np.maximum(outer, -inner)
        d = np.where(Y > 812, np.maximum(d, -(Y - 812) + 0.0), d)  # only the curve
        z = 0.152 * shoulder(d, 1.4)
        # voussoir joints
        ang = np.arctan2(Y - 812, X - (a + b) * 0.5)
        vj = np.abs(np.mod(ang / (np.pi / 9), 1.0) - 0.5)
        z -= 0.008 * (1 - smoothstep(0.08, 0.2, vj)) * shoulder(d, 2.0)
        cv.put_max(sl, np.where(d < 0.5, z, 0.0))
    # low front wall stub between podium and arcade
    wall(cv, [(578, 800), (592, 800), (592, 858), (578, 858)], 0.2, seed=23,
         bricks=(10, 7))

    # ground line
    sl, X, Y = cv.window(268, 850, 762, 870)
    d = sdf_box(270, 856, 760, 868, X, Y, r=4)
    z = 0.06 * shoulder(d, 2.0) + 0.003 * value_noise(X.shape, 6 * cv.spp, 31)
    cv.put_max(sl, np.where(d < 0.5, z, 0.0))


def build_ornaments(cv):
    """two small floral scroll ornaments flanking 'MOSUL'"""
    for ox, oy in [(404.0, 207.0), (622.0, 207.0)]:
        sl, X, Y = cv.window(ox - 18, oy - 12, ox + 18, oy + 12)
        dx = np.abs(X - ox)
        # centre bud
        bud = np.sqrt((dx / 2.6) ** 2 + ((Y - oy + 1.0) / 4.2) ** 2) - 1.0
        bud = bud * 2.6
        # two mirrored curls
        cx, cy = ox + 7.5, oy + 1.5
        rr = np.sqrt((dx + ox - cx) ** 2 + (Y - cy) ** 2)
        ang = np.arctan2(Y - cy, dx + ox - cx)
        curl_r = 4.6 - 0.5 * (ang + np.pi) / (2 * np.pi) * 3.0
        curl = np.abs(rr - curl_r) - 1.0
        curl = np.where((ang > -2.7) & (ang < 2.3), curl, 9.0)
        dot = np.sqrt((dx - 11.8) ** 2 + (Y - oy + 2.5) ** 2) - 1.5
        leaf = np.sqrt(((dx - 3.5) / 1.4) ** 2 + ((Y - oy - 5.0) / 2.6) ** 2) * 1.4 - 1.4
        d = np.minimum(np.minimum(bud, curl), np.minimum(dot, leaf))
        z = 0.055 * shoulder(d, 1.2)
        cv.put_max(sl, z)


def build_heightmap(out_png):
    cv = Canvas()
    build_ruins(cv)
    build_podium(cv)
    build_base(cv)
    build_minaret(cv)
    build_ornaments(cv)
    Z = blur(cv.Z, 0.45)
    cv.Zr = Z.copy()          # relief heights above the plaque face (cm)
    # lift visible parts slightly so they emerge from under the plaque surface
    LIFT = 0.004
    Z = Z + LIFT * smoothstep(0.0, 0.003, Z)
    zmax = float(Z.max()) * 1.02
    write_png16(out_png, Z / zmax)
    return cv, zmax, LIFT


# ---------------------------------------------------------------------------
#  Blender scene construction
# ---------------------------------------------------------------------------
def reset_scene():
    """remove previous objects/data so the script can be re-run safely"""
    sc = bpy.context.scene
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.curves, bpy.data.materials,
                 bpy.data.textures, bpy.data.images, bpy.data.lights,
                 bpy.data.cameras, bpy.data.worlds):
        for d in list(coll):
            if d.users == 0:
                coll.remove(d)
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.scale_length = 0.01
    sc.unit_settings.length_unit = "CENTIMETERS"
    return sc


def make_material():
    m = bpy.data.materials.new("Plaster_Cream")
    if not m.node_tree:
        m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (0.73, 0.57, 0.36, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.62
    try:
        bsdf.inputs["Subsurface Weight"].default_value = 0.06
        bsdf.inputs["Subsurface Radius"].default_value = (0.05, 0.03, 0.02)
    except KeyError:
        pass
    # fine casting grain
    tc = nt.nodes.new("ShaderNodeTexCoord")
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 60.0
    nz.inputs["Detail"].default_value = 8.0
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.08
    bump.inputs["Distance"].default_value = 0.002
    nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
    nt.links.new(nz.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return m


def plaque_outline(n_arc=160, n_corner=14):
    """outline points (cm) counter-clockwise"""
    R = ((PL_RIGHT - PL_LEFT) ** 2 / 4 + (ARCH_SIDE_Y - ARCH_TOP) ** 2) / (2 * (ARCH_SIDE_Y - ARCH_TOP))
    acx, acy = (PL_LEFT + PL_RIGHT) / 2, ARCH_TOP + R      # arch centre (px)
    pts = []
    rb = CORNER_R_BOTTOM
    # bottom-left corner -> bottom-right corner
    for cxp, cyp, a0, a1 in [(PL_LEFT + rb, PL_BOTTOM - rb, 180, 90),
                             (PL_RIGHT - rb, PL_BOTTOM - rb, 90, 0)]:
        for i in range(n_corner + 1):
            a = math.radians(a0 + (a1 - a0) * i / n_corner)
            pts.append((cxp + rb * math.cos(a), cyp + rb * math.sin(a)))
    # fillets between sides and arch
    rf = CORNER_R_TOP
    fcx_r = PL_RIGHT - rf
    fcy = acy - math.sqrt((R - rf) ** 2 - (fcx_r - acx) ** 2)
    fcx_l = PL_LEFT + rf
    # right fillet: from side tangent (angle 0) up to arch tangent
    ang_r = math.degrees(math.atan2(fcy - acy, fcx_r - acx))   # dir arch centre->fillet
    for i in range(n_corner + 1):
        a = math.radians(0 + (ang_r - 0) * i / n_corner)
        pts.append((fcx_r + rf * math.cos(a), fcy + rf * math.sin(a)))
    # arch from right tangent to left tangent (over the top: angles go -> -90 -> ...)
    ang_l = math.degrees(math.atan2(fcy - acy, fcx_l - acx))
    for i in range(1, n_arc):
        a = math.radians(ang_r + (ang_l - ang_r) * i / n_arc)
        pts.append((acx + R * math.cos(a), acy + R * math.sin(a)))
    for i in range(n_corner + 1):
        a = math.radians(ang_l + (-180 - ang_l) * i / n_corner)
        pts.append((fcx_l + rf * math.cos(a), fcy + rf * math.sin(a)))
    # px -> cm ; note py axis is downwards, so reverse to get CCW in world
    out = [P(x, y) for (x, y) in pts]
    return out[::-1] if _signed_area(out) < 0 else out


def _signed_area(pts):
    a = 0.0
    for i in range(len(pts)):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % len(pts)]
        a += x0 * y1 - x1 * y0
    return a * 0.5


def point_in_poly(x, y, pts):
    inside = False
    n = len(pts)
    for i in range(n):
        ax, ay = pts[i]
        bx, by = pts[(i + 1) % n]
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
            inside = not inside
    return inside


def build_plaque(mat):
    outline = plaque_outline()
    me = bpy.data.meshes.new("Plaque")
    bm = bmesh.new()
    vs = [bm.verts.new((x, y, 0.0)) for x, y in outline]
    f = bm.faces.new(vs)
    ret = bmesh.ops.extrude_face_region(bm, geom=[f])
    ev = [e for e in ret["geom"] if isinstance(e, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=ev, vec=(0, 0, -PLAQUE_THICK))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("Plaque", me)
    bpy.context.collection.objects.link(ob)
    ob.data.materials.append(mat)
    bev = ob.modifiers.new("Bevel", "BEVEL")
    bev.width = PLAQUE_BEVEL
    bev.segments = 8
    bev.limit_method = "ANGLE"
    bev.angle_limit = math.radians(40)
    bev.profile = 0.6
    bev.harden_normals = True
    ob.modifiers.new("WeightedNormal", "WEIGHTED_NORMAL").keep_sharp = True
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob, outline


def build_relief(mat, png_path, cv, zmax, lift, outline):
    x0, y1 = P(cv.px0, cv.py0)     # top-left in world
    x1, y0 = P(cv.px1, cv.py1)     # bottom-right in world
    me = bpy.data.meshes.new("Relief")
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    nx, ny = NX_BASE, NY_BASE
    grid = [[bm.verts.new((x0 + (x1 - x0) * i / nx, y0 + (y1 - y0) * j / ny, -lift))
             for i in range(nx + 1)] for j in range(ny + 1)]
    # keep only cells well inside the plaque (all hidden anyway)
    inset = [(x, y) for x, y in outline]
    cxw = sum(p[0] for p in inset) / len(inset)
    cyw = sum(p[1] for p in inset) / len(inset)
    shrink = [(cxw + (x - cxw) * 0.975, cyw + (y - cyw) * 0.975) for x, y in inset]
    for j in range(ny):
        for i in range(nx):
            q = [grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]]
            if not all(point_in_poly(v.co.x, v.co.y, shrink) for v in q):
                continue
            f = bm.faces.new(q)
            for loop in f.loops:
                v = loop.vert
                loop[uvl].uv = ((v.co.x - x0) / (x1 - x0), (v.co.y - y0) / (y1 - y0))
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context="VERTS")
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("Relief_Minaret", me)
    bpy.context.collection.objects.link(ob)
    ob.data.materials.append(mat)
    for p in ob.data.polygons:
        p.use_smooth = True

    img = bpy.data.images.load(png_path, check_existing=False)
    img.name = "Hadba_Relief_Height"
    img.colorspace_settings.name = "Non-Color"
    try:
        img.pack()
    except Exception as exc:          # pragma: no cover
        print("could not pack height map:", exc)
    tex = bpy.data.textures.new("Hadba_Relief_Height", "IMAGE")
    tex.image = img
    tex.extension = "EXTEND"
    tex.use_interpolation = True

    sub = ob.modifiers.new("Subdivision", "SUBSURF")
    sub.subdivision_type = "SIMPLE"
    sub.levels = SUB_VIEW
    sub.render_levels = SUB_RENDER
    disp = ob.modifiers.new("Displace_Relief", "DISPLACE")
    disp.texture = tex
    disp.texture_coords = "UV"
    disp.uv_layer = "UVMap"
    disp.direction = "Z"
    disp.mid_level = 0.0
    disp.strength = zmax
    return ob


def find_font():
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            f = bpy.data.fonts.load(p)
            try:
                f.pack()
            except Exception:
                pass
            return f
    return None


def text_object(name, body, size, font, mat, extrude=0.04, bevel=0.012, spacing=1.0):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = body
    if font:
        cu.font = font
    cu.size = size
    cu.align_x = "CENTER"
    cu.align_y = "BOTTOM_BASELINE"
    cu.extrude = extrude
    cu.bevel_depth = bevel
    cu.bevel_resolution = 4
    cu.resolution_u = 8
    cu.space_character = spacing
    ob = bpy.data.objects.new(name, cu)
    bpy.context.collection.objects.link(ob)
    ob.data.materials.append(mat)
    ob.location.z = extrude + bevel * 0.2
    return ob


def text_width(ob):
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    xs = [v[0] for v in ev.bound_box]
    return max(xs) - min(xs)


def build_texts(font, mat):
    # ---- arched title along a circle concentric with the plaque arch
    R_arch = ((PL_RIGHT - PL_LEFT) ** 2 / 4 + (ARCH_SIDE_Y - ARCH_TOP) ** 2) / (2 * (ARCH_SIDE_Y - ARCH_TOP))
    acx, acy = (PL_LEFT + PL_RIGHT) / 2, ARCH_TOP + R_arch
    base_r_px = acy - 177.0                     # baseline radius
    cxw, cyw = P(acx, acy)
    rw = base_r_px * S
    half = math.radians(52.0)
    n = 256
    pts = []
    for i in range(n + 1):
        a = math.pi / 2 + half - 2 * half * i / n     # left -> right over the top
        pts.append((cxw + rw * math.cos(a), cyw + rw * math.sin(a)))
    start = pts[0]
    cu = bpy.data.curves.new("TitleArc", "CURVE")
    cu.dimensions = "2D"
    sp = cu.splines.new("POLY")
    sp.points.add(len(pts) - 1)
    for p, (x, y) in zip(sp.points, pts):
        p.co = (x - start[0], y - start[1], 0.0, 1.0)
    arc = bpy.data.objects.new("TitleArc", cu)
    bpy.context.collection.objects.link(arc)
    arc.location = (start[0], start[1], 0.0)
    arc.hide_render = True
    arc_len = rw * 2 * half

    title = text_object("Title_AlHadba_Minaret", "AL-HADBA MINARET", 0.62, font, mat,
                        spacing=0.92)
    title.data.align_x = "LEFT"
    target = (2 * math.radians(47.0)) * rw     # arc length actually covered by text
    w = text_width(title)
    sx = min(1.0, target / w)
    title.data.size *= sx
    w = text_width(title)
    title.data.offset_x = (arc_len - w) / 2.0
    title.location.x, title.location.y = start
    mod = title.modifiers.new("FollowArc", "CURVE")
    mod.object = arc
    mod.deform_axis = "POS_X"

    sub = text_object("Subtitle_Mosul", "MOSUL", 0.40, font, mat, spacing=1.0)
    sub.location.x, sub.location.y = P(513, 216)
    iraq = text_object("Footer_Iraq", "IRAQ", 0.60, font, mat, spacing=1.04)
    iraq.location.x, iraq.location.y = P(513, 930)
    return title, sub, iraq, arc


def build_stage():
    sc = bpy.context.scene
    # floor
    bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, -PLAQUE_THICK - 0.001))
    floor = bpy.context.active_object
    floor.name = "Studio_Floor"
    fm = bpy.data.materials.new("Studio_Grey")
    if not fm.node_tree:
        fm.use_nodes = True
    b = fm.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (0.70, 0.70, 0.71, 1)
    b.inputs["Roughness"].default_value = 0.8
    floor.data.materials.append(fm)

    # world
    w = bpy.data.worlds.new("Studio")
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.75, 0.75, 0.76, 1)
    bg.inputs["Strength"].default_value = 0.22
    sc.world = w

    def area(name, loc, size, power, color=(1, 1, 1)):
        ld = bpy.data.lights.new(name, "AREA")
        ld.shape = "DISK"
        ld.size = size
        ld.energy = power
        ld.color = color
        ob = bpy.data.objects.new(name, ld)
        sc.collection.objects.link(ob)
        ob.location = loc
        d = -ob.location.normalized()
        ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
        return ob

    from mathutils import Vector
    area("Key", Vector((17.0, 19.0, 21.0)), 7.0, 5200.0, (1.0, 0.96, 0.90))
    area("Fill", Vector((-30.0, -10.0, 24.0)), 30.0, 1400.0, (0.92, 0.95, 1.0))
    area("Top", Vector((0.0, 6.0, 45.0)), 40.0, 2200.0)

    cam_d = bpy.data.cameras.new("Camera")
    cam_d.lens = 100.0
    cam = bpy.data.objects.new("Camera", cam_d)
    sc.collection.objects.link(cam)
    cam.location = (0.0, 0.0, 30.6)
    cam.rotation_euler = (0, 0, 0)
    cam_d.clip_start = 1.0
    cam_d.clip_end = 500.0
    sc.camera = cam

    # angled hero camera (not active)
    cam2_d = bpy.data.cameras.new("Camera_Angle")
    cam2_d.lens = 85.0
    cam2 = bpy.data.objects.new("Camera_Angle", cam2_d)
    sc.collection.objects.link(cam2)
    cam2.location = (9.0, -19.0, 20.0)
    d = -cam2.location.normalized()
    cam2.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()

    r = sc.render
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = 96
    sc.cycles.use_denoising = True
    r.resolution_x = 1024
    r.resolution_y = 1024
    r.film_transparent = False
    try:
        sc.view_settings.view_transform = "AgX"
        sc.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    sc.view_settings.exposure = 0.0


# ---------------------------------------------------------------------------
#  Watertight single-body mesh for 3D printing
#  (plaque + relief + letters merged into ONE closed height-field solid)
# ---------------------------------------------------------------------------
def _flat_text_triangles(text_obs):
    """2D triangles (world cm) of the letters, after the arc deformation"""
    saved = []
    for ob in text_obs:
        cu = ob.data
        saved.append((cu, cu.extrude, cu.bevel_depth))
        cu.extrude = 0.0
        cu.bevel_depth = 0.0
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    tris = []
    for ob in text_obs:
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        me.calc_loop_triangles()
        co = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        mw = np.array(ob.matrix_world)
        co = co @ mw[:3, :3].T + mw[:3, 3]
        idx = np.empty(len(me.loop_triangles) * 3, dtype=np.int64)
        me.loop_triangles.foreach_get("vertices", idx)
        tris.append(co[idx.reshape(-1, 3)][:, :, :2])
        ev.to_mesh_clear()
    for cu, e, b in saved:
        cu.extrude = e
        cu.bevel_depth = b
    bpy.context.view_layer.update()
    return np.concatenate(tris) if tris else np.zeros((0, 3, 2))


def _raster_triangles(tris, xs, ys):
    mask = np.zeros((len(ys), len(xs)), dtype=bool)
    x0, dx = xs[0], xs[1] - xs[0]
    y0, dy = ys[0], ys[1] - ys[0]
    for (ax, ay), (bx, by), (cx, cy) in tris:
        j0 = max(0, int(math.floor((min(ax, bx, cx) - x0) / dx)))
        j1 = min(len(xs) - 1, int(math.ceil((max(ax, bx, cx) - x0) / dx)))
        i0 = max(0, int(math.floor((min(ay, by, cy) - y0) / dy)))
        i1 = min(len(ys) - 1, int(math.ceil((max(ay, by, cy) - y0) / dy)))
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if j1 < j0 or i1 < i0 or abs(den) < 1e-14:
            continue
        X = xs[j0:j1 + 1][None, :]
        Y = ys[i0:i1 + 1][:, None]
        l1 = ((by - cy) * (X - cx) + (cx - bx) * (Y - cy)) / den
        l2 = ((cy - ay) * (X - cx) + (ax - cx) * (Y - cy)) / den
        e = -1e-9
        mask[i0:i1 + 1, j0:j1 + 1] |= (l1 >= e) & (l2 >= e) & (1.0 - l1 - l2 >= e)
    return mask


def _sample_canvas(cv, X, Y):
    """bilinear lookup of the relief height map at world (cm) positions"""
    jf = ((X / S + CX) - cv.px0) * cv.spp
    if_ = ((CY - Y / S) - cv.py0) * cv.spp
    valid = (jf >= 0) & (jf <= cv.W - 1) & (if_ >= 0) & (if_ <= cv.H - 1)
    jf = np.clip(jf, 0, cv.W - 1.001)
    if_ = np.clip(if_, 0, cv.H - 1.001)
    j0 = jf.astype(np.int64)
    i0 = if_.astype(np.int64)
    tx, ty = jf - j0, if_ - i0
    Z = cv.Zr
    v = (Z[i0, j0] * (1 - tx) * (1 - ty) + Z[i0, j0 + 1] * tx * (1 - ty) +
         Z[i0 + 1, j0] * (1 - tx) * ty + Z[i0 + 1, j0 + 1] * tx * ty)
    return np.where(valid, v, 0.0)


def build_print_mesh(cv, outline, text_obs, res=PRINT_RES):
    xs_o = [p[0] for p in outline]
    ys_o = [p[1] for p in outline]
    xs = np.arange(min(xs_o) - 2 * res, max(xs_o) + 3 * res, res)
    ys = np.arange(min(ys_o) - 2 * res, max(ys_o) + 3 * res, res)
    X, Y = np.meshgrid(xs, ys)                       # row i <-> ys[i]
    print("print grid", X.shape)

    # plaque: flat top, rounded (quarter-round) edge, vertical sides
    di = -sdf_poly(outline, X, Y)                    # cm inside distance
    T, b = PLAQUE_THICK, PLAQUE_BEVEL
    zp = np.where(di >= b, T, T - b + np.sqrt(np.maximum(0.0, b * b - (b - di) ** 2)))
    zp = np.where(di > 0, zp, 0.0)

    # relief + letters
    rel = _sample_canvas(cv, X, Y)
    mask = _raster_triangles(_flat_text_triangles(text_obs), xs, ys)
    soft = blur(mask.astype(np.float64), max(0.6, 0.005 / res))
    txt = PRINT_TEXT_H * smoothstep(0.2, 0.8, soft)
    top = np.maximum(rel, txt) * smoothstep(b, b + 0.05, di)
    Z = zp + top

    inside = Z > 0
    K = inside[:-1, :-1] | inside[1:, :-1] | inside[:-1, 1:] | inside[1:, 1:]
    for _ in range(20):                               # remove pinch vertices
        sw, se = K[:-1, :-1], K[:-1, 1:]
        nw, ne = K[1:, :-1], K[1:, 1:]
        pinch = (sw & ne & ~se & ~nw) | (se & nw & ~sw & ~ne)
        if not pinch.any():
            break
        K[:-1, :-1] |= pinch
        K[:-1, 1:] |= pinch
        K[1:, :-1] |= pinch
        K[1:, 1:] |= pinch

    ny, nx = Z.shape
    vid = np.arange(ny * nx).reshape(ny, nx)
    ci, cj = np.nonzero(K)
    quads = np.stack([vid[ci, cj], vid[ci, cj + 1], vid[ci + 1, cj + 1], vid[ci + 1, cj]], 1)
    used = np.unique(quads)
    remap = np.full(ny * nx, -1, dtype=np.int64)
    remap[used] = np.arange(len(used))
    quads = remap[quads]
    co = np.stack([X.ravel()[used], Y.ravel()[used], Z.ravel()[used]], 1)
    # split every cell along the diagonal with the higher corners, so that
    # no triangle ever lies flat on the bottom (z = 0) plane
    zc = co[:, 2]
    use_ac = (zc[quads[:, 0]] + zc[quads[:, 2]]) >= (zc[quads[:, 1]] + zc[quads[:, 3]])
    q = quads
    t1 = np.where(use_ac[:, None], q[:, [0, 1, 2]], q[:, [0, 1, 3]])
    t2 = np.where(use_ac[:, None], q[:, [0, 2, 3]], q[:, [1, 2, 3]])
    tris = np.concatenate([t1, t2])

    me = bpy.data.meshes.new("Magnet_PRINT")
    me.vertices.add(len(co))
    me.vertices.foreach_set("co", co.astype(np.float32).ravel())
    me.loops.add(tris.size)
    me.loops.foreach_set("vertex_index", tris.astype(np.int32).ravel())
    me.polygons.add(len(tris))
    me.polygons.foreach_set("loop_start", (np.arange(len(tris)) * 3).astype(np.int32))
    me.update(calc_edges=True)

    bm = bmesh.new()
    bm.from_mesh(me)
    # flat bottom: all boundary vertices lie on z = 0
    border = [e for e in bm.edges if e.is_boundary]
    filled = bmesh.ops.holes_fill(bm, edges=border, sides=0)["faces"]
    bmesh.ops.triangulate(bm, faces=filled, quad_method="BEAUTY", ngon_method="BEAUTY")
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("Magnet_PRINT", me)
    coll = bpy.data.collections.new("PRINT_3D")
    bpy.context.scene.collection.children.link(coll)
    coll.objects.link(ob)

    if PRINT_DECIMATE < 1.0:
        dec = ob.modifiers.new("Decimate", "DECIMATE")
        dec.decimate_type = "COLLAPSE"
        dec.ratio = PRINT_DECIMATE
        bpy.context.view_layer.objects.active = ob
        with bpy.context.temp_override(object=ob, active_object=ob):
            bpy.ops.object.modifier_apply(modifier=dec.name)
    ob.hide_render = True
    return ob


def check_manifold(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bad_e = sum(1 for e in bm.edges if len(e.link_faces) != 2)
    bad_v = sum(1 for v in bm.verts if not v.is_manifold)
    vol = bm.calc_volume(signed=True)
    nf = len(bm.faces)
    bm.free()
    return bad_e, bad_v, vol, nf


def export_stl(ob, path, scale=10.0):
    """binary STL in millimetres (model units are cm)"""
    me = ob.data
    me.calc_loop_triangles()
    co = np.empty(len(me.vertices) * 3, dtype=np.float32)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3) * scale
    mw = np.array(ob.matrix_world, dtype=np.float32)
    co = co @ mw[:3, :3].T + mw[:3, 3] * scale
    idx = np.empty(len(me.loop_triangles) * 3, dtype=np.int64)
    me.loop_triangles.foreach_get("vertices", idx)
    tri = co[idx.reshape(-1, 3)]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    rec = np.zeros(len(tri), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    rec["n"] = n
    rec["v"] = tri
    with open(path, "wb") as f:
        f.write(b"Al-Hadba Minaret magnet - units: mm".ljust(80, b" "))
        f.write(struct.pack("<I", len(tri)))
        f.write(rec.tobytes())


def main(stl=None, save=None, render=None, render_angle=None, outdir=None):
    if outdir is None:
        outdir = os.path.dirname(os.path.abspath(save)) if save else (
            bpy.path.abspath("//") or os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(outdir, exist_ok=True)
    reset_scene()
    png = os.path.join(outdir, "hadba_relief_height.png")
    print("building height map ...")
    cv, zmax, lift = build_heightmap(png)
    print("height map", cv.W, "x", cv.H, "max relief %.3f cm" % zmax)
    mat = make_material()
    plaque, outline = build_plaque(mat)
    build_relief(mat, png, cv, zmax, lift, outline)
    font = find_font()
    texts = build_texts(font, mat)
    build_stage()
    if BUILD_PRINT_MESH or stl:
        print("building watertight print mesh ...")
        pm = build_print_mesh(cv, outline, list(texts[:3]))
        bad_e, bad_v, vol, nf = check_manifold(pm)
        print("print mesh: %d tris, non-manifold edges %d, verts %d, volume %.3f cm3"
              % (nf, bad_e, bad_v, vol))
        if stl:
            export_stl(pm, stl)
            print("exported", stl)
        pm.hide_set(True)
    if save:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(save), compress=True)
        print("saved", save)
    sc = bpy.context.scene
    if render:
        sc.render.filepath = os.path.abspath(render)
        bpy.ops.render.render(write_still=True)
        print("rendered", render)
    if render_angle:
        sc.camera = bpy.data.objects["Camera_Angle"]
        sc.render.filepath = os.path.abspath(render_angle)
        bpy.ops.render.render(write_still=True)
        sc.camera = bpy.data.objects["Camera"]
        print("rendered", render_angle)


def _cli():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    opts = {"stl": None, "save": None, "render": None, "render_angle": None, "outdir": None}
    i = 0
    while i < len(argv):
        k = argv[i].lstrip("-").replace("-", "_")
        if k in opts and i + 1 < len(argv):
            opts[k] = argv[i + 1]
            i += 2
        else:
            i += 1
    return opts


if __name__ == "__main__":
    main(**_cli())
