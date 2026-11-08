# -*- coding: utf-8 -*-
"""
هيكلية أبراج ومحطات الاتصالات - مجسّمات جاهزة للطباعة ثلاثية الأبعاد
Telecom towers set - print-ready procedural models for Blender 4.2+ (tested on 5.2).

طريقة الاستخدام / How to use
  1. افتح Blender ← تبويب Scripting ← New ← الصق هذا الملف (أو Open).
  2. اضغط Run Script.  يُبنى المشهد كاملاً بوحدة المليمتر.
  3. تُصدَّر ملفات STL تلقائياً إلى مجلد stl بجانب ملف .blend
     (أو إلى ~/telecom_towers_stl إذا لم يكن الملف محفوظاً).

  Headless:  blender -b -P telecom_towers.py -- --out ./stl [--render preview.png] [--save towers.blend]

كل برج = جسم واحد مغلق (manifold / watertight) مدموج بعملية Boolean Union،
1 وحدة Blender = 1 مم، فيُفتح STL مباشرة في أي Slicer بالمقاس الصحيح.
"""

import bpy
import bmesh
import itertools
import math
import os
import sys
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

# ----------------------------------------------------------------------------
# إعدادات الطباعة / Print settings
# ----------------------------------------------------------------------------
# أقل سماكة لأي عنصر رفيع (دعامات، درابزين، مانعة صواعق).
#   طابعة رزن Resin: 0.6 - 0.8      طابعة FDM بفوهة 0.4: 1.0 - 1.2
MIN_FEATURE = 1.0
TOWER_SPACING = 75.0      # المسافة بين الأبراج في المشهد (مم)
EXPORT_STL = True
CLEAR_SCENE = True
EPS = 0.25                # تداخل بسيط بين القطع لضمان دمج سليم
FIT_SCALE = 1.0           # set while building a scaled print so fit clearances stay in real mm

UP = Vector((0, 0, 1))


def t(x):
    """Clamp a thin dimension to the printable minimum."""
    return max(x, MIN_FEATURE)


def V(x, y=None, z=None):
    if y is None:
        return Vector(x)
    return Vector((x, y, z))


def polar(r, deg, z=0.0):
    a = math.radians(deg)
    return Vector((r * math.cos(a), r * math.sin(a), z))


def frame(origin, z_axis, x_hint=None):
    """4x4 matrix whose local Z follows z_axis and local X follows x_hint."""
    z = Vector(z_axis).normalized()
    candidates = [Vector(x_hint)] if x_hint is not None else []
    candidates += [Vector((1, 0, 0)), Vector((0, 1, 0))]
    for c in candidates:
        x = c - z * c.dot(z)
        if x.length > 1e-6:
            x.normalize()
            break
    y = z.cross(x)
    M = Matrix.Identity(4)
    for i in range(3):
        M[i][0], M[i][1], M[i][2], M[i][3] = x[i], y[i], z[i], origin[i]
    return M


# ----------------------------------------------------------------------------
# Primitive builder: every part is a closed mesh; they are unioned at the end
# ----------------------------------------------------------------------------
class Model:
    def __init__(self, name):
        self.name = name
        self.parts = []          # (verts, faces, material)
        self.cutters = []        # closed meshes subtracted after the union (holes, grooves)
        self.loose = []          # (group, Model, down) parts printed separately; down = side on the bed

    def cut(self):
        """Primitives added to the returned Model become holes in this one."""
        c = Model(self.name + "_cut")
        c.parts = self.cutters
        return c

    def add(self, verts, faces, mat):
        self.parts.append(([tuple(v) for v in verts], faces, mat))

    def revolve(self, profile, M=None, seg=24, closed=False, mat="steel"):
        """Solid of revolution around local Z. Profile points (r, z); r=0 is a pole."""
        M = M if M is not None else Matrix.Identity(4)
        verts, rings = [], []
        for r, z in profile:
            if r < 1e-6:
                rings.append([len(verts)])
                verts.append(M @ Vector((0, 0, z)))
            else:
                ring = []
                for k in range(seg):
                    a = 2 * math.pi * k / seg
                    ring.append(len(verts))
                    verts.append(M @ Vector((r * math.cos(a), r * math.sin(a), z)))
                rings.append(ring)
        pairs = [(i, i + 1) for i in range(len(rings) - 1)]
        if closed:
            pairs.append((len(rings) - 1, 0))
        faces = []
        for a, b in pairs:
            A, B = rings[a], rings[b]
            if len(A) == 1 and len(B) == 1:
                continue
            for k in range(seg):
                k1 = (k + 1) % seg
                if len(A) == 1:
                    faces.append((A[0], B[k1], B[k]))
                elif len(B) == 1:
                    faces.append((A[k], A[k1], B[0]))
                else:
                    faces.append((A[k], A[k1], B[k1], B[k]))
        self.add(verts, faces, mat)

    def cyl(self, p1, p2, r1, r2=None, seg=16, mat="steel", x_hint=None):
        p1, p2 = V(p1), V(p2)
        r2 = r1 if r2 is None else r2
        L = (p2 - p1).length
        self.revolve([(0, 0), (r1, 0), (r2, L), (0, L)], frame(p1, p2 - p1, x_hint), seg, mat=mat)

    def rod(self, p1, p2, d, seg=10, mat="steel"):
        """Thin round member with printable diameter."""
        r = t(d) / 2
        p1, p2 = V(p1), V(p2)
        u = (p2 - p1).normalized()
        self.cyl(p1 - u * r * 0.5, p2 + u * r * 0.5, r, seg=seg, mat=mat)

    def sphere(self, c, r, seg=32, rings=16, mat="steel"):
        prof = [(r * math.sin(math.pi * i / rings), -r * math.cos(math.pi * i / rings)) for i in range(rings + 1)]
        self.revolve(prof, Matrix.Translation(V(c)), seg, mat=mat)

    def torus(self, c, R, r, seg=48, tseg=8, mat="steel", M=None):
        prof = [(R + r * math.cos(2 * math.pi * i / tseg), r * math.sin(2 * math.pi * i / tseg)) for i in range(tseg)]
        self.revolve(prof, M if M is not None else Matrix.Translation(V(c)), seg, closed=True, mat=mat)

    def box(self, M, sx, sy, sz, mat="steel"):
        hx, hy, hz = sx / 2, sy / 2, sz / 2
        verts = [M @ Vector((x, y, z)) for z in (-hz, hz) for y in (-hy, hy) for x in (-hx, hx)]
        faces = [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)]
        self.add(verts, faces, mat)

    def box_at(self, c, size, rotz=0.0, mat="steel"):
        M = Matrix.Translation(V(c)) @ Matrix.Rotation(math.radians(rotz), 4, 'Z')
        self.box(M, *size, mat=mat)

    def beam(self, p1, p2, w, h=None, x_hint=None, mat="steel", ext=None):
        """Rectangular member from p1 to p2 (w along x_hint, h across)."""
        p1, p2 = V(p1), V(p2)
        w = t(w)
        h = t(h) if h is not None else w
        d = p2 - p1
        ext = w * 0.5 if ext is None else ext
        M = frame(p1, d, x_hint) @ Matrix.Translation((0, 0, d.length / 2))
        self.box(M, w, h, d.length + 2 * ext, mat=mat)

    def loft_rects(self, cxy, rects, mat="concrete", rotz=0.0):
        """Stack of rectangles (sx, sy, z) -> closed solid (plinths, chamfers)."""
        R = Matrix.Rotation(math.radians(rotz), 4, 'Z')
        cx, cy = cxy
        verts, faces = [], []
        for sx, sy, z in rects:
            for x, y in ((-sx / 2, -sy / 2), (sx / 2, -sy / 2), (sx / 2, sy / 2), (-sx / 2, sy / 2)):
                verts.append(Vector((cx, cy, 0)) + R @ Vector((x, y, z)))
        n = len(rects)
        faces.append((3, 2, 1, 0))
        faces.append(tuple(4 * (n - 1) + i for i in range(4)))
        for i in range(n - 1):
            a, b = 4 * i, 4 * (i + 1)
            for k in range(4):
                k1 = (k + 1) % 4
                faces.append((a + k, a + k1, b + k1, b + k))
        self.add(verts, faces, mat)


# ----------------------------------------------------------------------------
# Reusable telecom equipment
# ----------------------------------------------------------------------------
def panel_antenna(m, center, outward, w=3.4, d=1.6, h=16.0, mat="white", flush_front=False):
    """Sector panel antenna with end caps and bottom connectors.
    flush_front: caps flush with the front face, so the panel lies flat on the bed."""
    n = V(outward).normalized()
    tang = UP.cross(n)
    M = frame(V(center), UP, tang)   # local x = tangent, y = inward (UP x tangent = -n)
    m.box(M, w, d, h, mat=mat)
    cy = 0.15 if flush_front else 0.0
    for s in (-1, 1):
        m.box(M @ Matrix.Translation((0, cy, s * (h / 2 - 0.3))), w + 0.3, d + 0.3, 0.9, mat="dark")
    for s in (-0.25, 0.25):
        p = M @ Vector((s * w, 0, -h / 2 - 0.2))
        m.rod(p, p - UP * 1.5, 1.0, seg=8, mat="dark")


def mount_pipe(m, p, z0, z1, d=1.2):
    m.rod(V(p.x, p.y, z0), V(p.x, p.y, z1), d, seg=10)


def antenna_on_pipe(m, pipe_xy, outward, zc, w, d, h, pipe_d=1.2, mat="white", separate=False):
    """separate: the panel becomes its own print part (m.loose) with a groove in
    its back that seats on the mount pipe; only the pipe stays on the tower."""
    n = V(outward).normalized()
    n.z = 0
    n.normalize()
    pipe = V(pipe_xy[0], pipe_xy[1], zc)
    c = pipe + n * (t(pipe_d) / 2 + d / 2 - EPS)
    if separate:
        p = Model("panel")
        panel_antenna(p, c, n, w, d, h, mat, flush_front=True)
        p.cut().cyl(pipe - UP * (h / 2 + 1), pipe + UP * (h / 2 + 1), t(pipe_d) / 2 + 0.1 / FIT_SCALE, seg=16)
        m.loose.append(("panels", p, n))
        return
    panel_antenna(m, c, n, w, d, h, mat)
    for s in (-0.3, 0.3):
        m.beam(pipe + UP * (s * h), c + UP * (s * h), 0.9, 1.0, x_hint=UP, ext=0)


def rru(m, pipe_xy, inward, zc, w=2.6, d=1.8, h=5.0):
    """Remote radio unit with cooling fins, clamped to the inner side of a pipe."""
    n = V(inward).normalized()
    n.z = 0
    n.normalize()
    c = V(pipe_xy[0], pipe_xy[1], zc) + n * (0.6 + d / 2 - EPS)
    M = frame(c, UP, UP.cross(n))
    m.box(M, w, d, h, mat="dark")
    for i in range(3):
        x = (i - 1) * w / 3
        m.box(M @ Matrix.Translation((x, d / 2 + 0.25, 0)), t(0.6), 0.8, h * 0.85, mat="dark")


def microwave_dish(m, base, direction, R, arm=2.5, mat="white", separate=False):
    """Shrouded microwave dish with radome cover, hub, arm and support strut.

    separate: the dish becomes its own print part (m.loose), flat front so it
    prints face down, with a socket in the hub; the tower keeps the arm, which
    ends in a peg that plugs into that socket."""
    d = V(direction).normalized()
    base = V(base)
    depth = R * 0.5
    arm_r = max(0.65, R * 0.13, t(1.0) / 2)
    back = base + d * arm
    if separate:
        peg = 1.2
        m.cyl(base - d * 0.8, back + d * peg, arm_r, seg=12)
        p = Model("dish")
        hole_r = arm_r + 0.15 / FIT_SCALE
        hub_r = max(R * 0.28, hole_r + 0.9)
        center = back + d * depth
        p.cyl(back, back + d * (R * 0.25 + 0.2), hub_r, hub_r * 1.1, seg=24, mat="steel")
        prof = [(0, -depth), (R * 0.35, -depth * 0.93), (R * 0.7, -depth * 0.62),
                (R * 0.95, -depth * 0.15), (R, 0), (R + 0.35, 0), (R + 0.35, R * 0.22), (0, R * 0.22)]
        p.revolve(prof, frame(center, d), seg=40, mat=mat)
        p.cut().cyl(back - d * 0.5, back + d * (peg + 0.25), hole_r, seg=16)
        m.loose.append(("dishes", p, d))
        return
    m.cyl(base - d * 0.8, back + d * 0.5, arm_r, seg=12)
    hub = back + d * (R * 0.25)
    m.cyl(back - d * 0.2, hub + d * 0.2, R * 0.28, R * 0.32, seg=20, mat="steel")
    center = back + d * depth
    prof = [(0, -depth), (R * 0.35, -depth * 0.93), (R * 0.7, -depth * 0.62),
            (R * 0.95, -depth * 0.15), (R, 0), (R + 0.35, 0), (R + 0.35, R * 0.2),
            (R * 0.98, R * 0.23), (R * 0.6, R * 0.27), (0, R * 0.29)]
    m.revolve(prof, frame(center, d), seg=40, mat=mat)
    # mounting strut from the pole/leg up to the dish hub (triangulated mount)
    m.beam(base - UP * (R * 0.9), hub - UP * (R * 0.15), 0.9, 0.9)


def solar_panel(m, center, normal, w, h, cols, rows):
    """PV module: back sheet, aluminium frame, raised cell grid, back rails."""
    n = V(normal).normalized()
    xh = UP.cross(n)
    if xh.length < 1e-4:
        xh = Vector((1, 0, 0))
    M = frame(V(center), n, xh)
    m.box(M @ Matrix.Translation((0, 0, -0.55)), w, h, t(1.1), mat="white")
    fb = 0.8
    for s in (-1, 1):
        m.box(M @ Matrix.Translation((s * (w / 2 - fb / 2), 0, 0.1)), fb, h, 0.8, mat="steel")
        m.box(M @ Matrix.Translation((0, s * (h / 2 - fb / 2), 0.1)), w, fb, 0.8, mat="steel")
    gap = 0.45
    cw = (w - 2 * fb - gap * (cols + 1)) / cols
    ch = (h - 2 * fb - gap * (rows + 1)) / rows
    for i in range(cols):
        for j in range(rows):
            x = -w / 2 + fb + gap + cw / 2 + i * (cw + gap)
            y = -h / 2 + fb + gap + ch / 2 + j * (ch + gap)
            m.box(M @ Matrix.Translation((x, y, -0.05)), cw, ch, 0.5, mat="solar")
    for s in (-1, 1):
        m.box(M @ Matrix.Translation((s * w * 0.28, 0, -1.4)), 1.2, h * 0.9, 1.0, mat="steel")
    return M


def cabinet(m, center, size, facing, mat="white"):
    """Outdoor equipment cabinet with door, handle, louvres and rain roof."""
    sx, sy, sz = size
    n = V(facing).normalized()
    M = frame(V(center), UP, UP.cross(n))     # local +y = facing
    m.box(M, sx, sy, sz, mat=mat)
    m.box(M @ Matrix.Translation((0, 0, sz / 2 + 0.4)), sx + 1.2, sy + 1.2, 0.9, mat=mat)
    door = M @ Matrix.Translation((0, sy / 2, 0))
    m.box(door @ Matrix.Translation((0, 0, -0.3)), sx - 1.6, 0.8, sz - 2.2, mat=mat)
    m.box(door @ Matrix.Translation((sx / 2 - 2.0, 0.5, 0)), 0.8, 1.0, min(3.0, sz * 0.2), mat="dark")
    nl = max(2, int((sz * 0.3) / 1.3))
    for i in range(nl):
        z = -sz / 2 + 2.2 + i * 1.3
        m.box(door @ Matrix.Translation((-sx * 0.12, 0.4, z)), sx * 0.5, 0.8, t(0.6), mat="dark")


def cable_ladder(m, z0, z1, r_at, deg, width=1.8):
    """Vertical feeder tray hugging a (tapered) pole, with clamp blocks."""
    a = polar(1, deg)
    tang = UP.cross(a)
    p0 = a * (r_at(z0) + 0.35) + UP * z0
    p1 = a * (r_at(z1) + 0.35) + UP * z1
    m.beam(p0, p1, width, 1.0, x_hint=tang, mat="steel", ext=0)
    z = z0 + 6
    while z < z1 - 3:
        p = a * (r_at(z) + 0.6) + UP * z
        M = frame(p, UP, tang)
        m.box(M, width + 0.8, 1.6, 0.9, mat="steel")
        z += 9


def pole_base(m, pad=38.0, flange_r=7.5, pole_r=4.0, bolts=8):
    """Concrete plinth + octagonal base flange + anchor bolts + gussets. Returns flange top z."""
    m.loft_rects((0, 0), [(pad, pad, 0), (pad, pad, 2.2), (pad - 1.6, pad - 1.6, 3.0)], "concrete")
    z0 = 3.0
    m.revolve([(0, z0 - EPS), (flange_r, z0 - EPS), (flange_r, z0 + 1.3), (0, z0 + 1.3)],
              Matrix.Rotation(math.pi / 8, 4, 'Z'), seg=8)
    for i in range(bolts):
        p = polar(flange_r - 1.3, 360 * i / bolts + 22.5 / 2)
        m.revolve([(0, z0 + 1.0), (0.95, z0 + 1.0), (0.95, z0 + 2.0), (0, z0 + 2.0)],
                  Matrix.Translation(p), seg=6)
        m.cyl(p + UP * (z0 + 1.5), p + UP * (z0 + 2.8), t(1.0) / 2 + 0.05, seg=8)
    for i in range(4):
        a = 45 + 90 * i
        p = polar(pole_r + 1.4, a, z0 + 2.5)
        m.box_at(p, (3.2, t(0.8), 2.6), rotz=a)
    return z0 + 1.3


def tapered(r0, r1, z0, z1):
    return lambda z: r0 + (r1 - r0) * (min(max(z, z0), z1) - z0) / (z1 - z0)


def top_mast(m, ztop, base_r=1.4, mast_h=10.0, rod_h=8.0, light=True):
    m.cyl((0, 0, ztop - 1.0), (0, 0, ztop + mast_h), base_r, base_r * 0.8, seg=16)
    zr = ztop + mast_h
    if light:
        m.sphere((0, 0, zr + 0.6), 1.4, seg=16, rings=8, mat="red")
    m.cyl((0, 0, zr), (0, 0, zr + rod_h), max(0.7, t(1.0) / 2), t(1.0) / 2, seg=10)
    return zr + rod_h


# ----------------------------------------------------------------------------
# 1) أبراج شبكية - Lattice (self-supporting, 4-legged) tower
# ----------------------------------------------------------------------------
def tower_lattice(name="01_Lattice_Tower", x_bays=None, split=False):
    """x_bays: print mode. Same tower (levels, horizontals, head), but each X
    brace spans as many panels as needed to climb at >= PRINT_MIN_ANGLE, with
    x_bays X braces side by side across the face; the lattice body then
    prints without supports.
    split: dishes and panel antennas are separate print parts (Model.loose)."""
    steep_x = x_bays is not None
    m = Model(name)
    m.loft_rects((0, 0), [(58, 58, 0), (58, 58, 2.2), (55, 55, 3.0)], "concrete")
    zb = 3.0
    b0, b1 = 21.0, 6.5
    z0, zt, ztop = zb + 3.5, 138.0, 174.0
    corners = [(1, 1), (-1, 1), (-1, -1), (1, -1)]

    def half(z):
        return b0 + (b1 - b0) * (z - z0) / (zt - z0) if z < zt else b1

    def P(c, z):
        h = half(z)
        return Vector((c[0] * h, c[1] * h, z))

    for c in corners:   # concrete piers
        p = P(c, z0)
        m.loft_rects((p.x, p.y), [(8.5, 8.5, zb - EPS), (8.5, 8.5, z0 - 0.7), (7.0, 7.0, z0 + 0.3)], "concrete")

    lv = [z0]
    h = 21.0
    while lv[-1] + h < zt - 6:
        lv.append(lv[-1] + h)
        h *= 0.86
    lv.append(zt)
    top = [zt + 9 * i for i in range(1, 5)]
    levels = lv + top
    m.cut_info = dict(levels=list(levels), avoid=[], max_cut=zt + 7,
                      leg_xy=lambda z: [(c[0] * half(z), c[1] * half(z)) for c in corners])

    def r_leg(z):
        return 1.7 - 0.55 * (z - z0) / (ztop - z0)
    m.cut_info["leg_r"] = r_leg

    for c in corners:   # legs + splice flanges
        a, b = P(c, z0 - 1.0), P(c, zt)
        m.cyl(a, b, r_leg(z0), r_leg(zt), seg=14)
        m.cyl(P(c, zt) - UP * 1.0, V(c[0] * b1, c[1] * b1, ztop + 0.8), r_leg(zt), r_leg(ztop), seg=14)
        u = (b - a).normalized()
        for z in levels[1:-1]:
            q = P(c, z)
            uu = u if z <= zt else UP
            if steep_x:     # same flange, 45 degree chamfer underneath (no lip to print in the air)
                r = r_leg(z)
                m.revolve([(0, -1.3), (r - 0.1, -1.3), (r + 0.45, -0.6), (r + 0.45, 0.6), (0, 0.6)],
                          frame(q, uu), seg=19)
            else:
                m.cyl(q - uu * 0.6, q + uu * 0.6, r_leg(z) + 0.45, seg=14)
        # base plate at pier
        m.box_at(P(c, z0) + UP * 0.2, (5.0, 5.0, 1.0))

    if steep_x and x_bays > 1:
        # ground tie beams on the plinth: the bottom row of X braces starts on them
        zg = zb + 0.6
        levels = [zg] + levels[1:]
        for i in range(4):
            ca, cb = corners[i], corners[(i + 1) % 4]
            m.beam(P(ca, zg), P(cb, zg), 1.4, 1.4, x_hint=UP)

    def Q(ca, cb, z, f):
        return P(ca, z).lerp(P(cb, z), f)

    k = x_bays or 1
    tan_min = math.tan(math.radians(PRINT_MIN_ANGLE))

    def steep_enough(ja, jc):
        d = Q(corners[0], corners[1], levels[jc], 1.0 / k) - Q(corners[0], corners[1], levels[ja], 0.0)
        return d.z >= d.xy.length * tan_min

    # each X spans one panel (original) or as many panels as it needs (print mode)
    spans, j, n = [], 0, len(levels) - 1
    while j < n:
        e = j + 1
        while steep_x and e < n and not steep_enough(j, e):
            e += 1
        spans.append((j, e))
        j = e
    if steep_x and len(spans) > 1 and not steep_enough(*spans[-1]):
        spans[-2:] = [(spans[-2][0], spans[-1][1])]

    brace_angles = []
    for i in range(4):   # X bracing + horizontals on each face
        ca, cb = corners[i], corners[(i + 1) % 4]
        nrm = Vector((ca[0] + cb[0], ca[1] + cb[1], 0)).normalized()
        for ja, jc in spans:
            za, zc = levels[ja], levels[jc]
            w = 1.25 if za < 60 else 1.0
            for b in range(k):
                f0, f1 = b / k, (b + 1) / k
                for pa, pc in ((Q(ca, cb, za, f0), Q(ca, cb, zc, f1)), (Q(ca, cb, za, f1), Q(ca, cb, zc, f0))):
                    d = pc - pa
                    if steep_x:   # overlap only at the top end, so nothing pokes out below a joint
                        m.beam(pa, pc + d.normalized() * 0.35, w, x_hint=nrm, ext=0)
                    else:
                        m.beam(pa, pc, w, x_hint=nrm)
                    brace_angles.append(math.degrees(math.atan2(d.z, d.xy.length)))
        for j in range(1, n):
            w = 1.25 if levels[j] < 60 else 1.0
            m.beam(P(ca, levels[j]), P(cb, levels[j]), w, x_hint=UP)
        m.beam(P(ca, ztop), P(cb, ztop), 1.1, x_hint=UP)
    m.x_per_face = len(spans) * k
    m.brace_angles = (min(brace_angles), max(brace_angles))
    for z in (zt, lv[len(lv) // 2]):   # plan bracing
        m.beam(P(corners[0], z), P(corners[2], z), 1.0, x_hint=UP)
        m.beam(P(corners[1], z), P(corners[3], z), 1.0, x_hint=UP)

    # --- antenna platform (top) with handrail, mount pipes and 8 panels
    zp, F = zt + 18.0, 13.0
    zu = zp + 17.0
    sq = [Vector((c[0] * F, c[1] * F, 0)) for c in corners]
    for k in range(4):
        a, b = sq[k], sq[(k + 1) % 4]
        m.beam(a + UP * zp, b + UP * zp, 1.4, 1.2, x_hint=UP)
        m.beam(a + UP * zu, b + UP * zu, 1.0, x_hint=UP)
        m.beam(P(corners[k], zp), a + UP * zp, 1.4, 1.2, x_hint=UP)
        m.beam(P(corners[k], zu), a + UP * zu, 1.0, x_hint=UP)
        m.beam(P(corners[k], zp - 9), a + UP * (zp - 0.3), 1.0)
        nrm = Vector((corners[k][0] + corners[(k + 1) % 4][0], corners[k][1] + corners[(k + 1) % 4][1], 0)).normalized()
        tang = (b - a).normalized()
        mid = (a + b) / 2
        # walkway plate
        m.box(frame(mid * ((F + b1) / 2 / F) + UP * (zp - 0.1), UP, tang), 2 * F, F - b1 + 0.8, t(0.9), mat="steel")
        # handrail
        for s in (-1, 0, 1):
            pp = mid * (12.4 / F) + tang * (s * 12.4) + UP * zp
            m.beam(pp, pp + UP * 5.2, 0.9, x_hint=tang)
        a2, b2 = mid * (12.4 / F) - tang * 12.4, mid * (12.4 / F) + tang * 12.4
        m.beam(a2 + UP * (zp + 5.2), b2 + UP * (zp + 5.2), 1.0, x_hint=UP)
        m.beam(a2 + UP * (zp + 2.7), b2 + UP * (zp + 2.7), t(0.8), x_hint=UP)
        # two panel antennas per face
        for s in (-5.5, 5.5):
            pipe = mid + nrm * 1.3 + tang * s
            mount_pipe(m, pipe, zp - 3, zu + 3)
            for zz in (zp, zu):
                m.beam(mid + tang * s + UP * zz, pipe + UP * zz, 1.0, x_hint=UP, ext=0.3)
            antenna_on_pipe(m, pipe, nrm, (zp + zu) / 2 + 0.5, 3.6, 1.7, 18.0, separate=split)
            rru(m, pipe, -nrm, zp + 4.5) if s > 0 else None

    # --- microwave dishes on the legs and faces
    for c, R in (((1, -1), 5.0), ((-1, 1), 4.5)):
        # split: mount below the platform struts (which start at zt + 9) so the dish can be fitted
        microwave_dish(m, P(c, zt - 5 if split else zt + 9), Vector((c[0], c[1], 0)), R, arm=2.2, separate=split)
        m.cut_info["avoid"].append(zt - 5 if split else zt + 9)

    def face_cross(j):
        za, zc = lv[j], lv[j + 1]
        ba, bc = half(za), half(zc)
        return za + (zc - za) * ba / (ba + bc)

    def face_mount(j):
        # with several X braces per panel the panel centre may be empty:
        # mount the dish on the horizontal at the top of that panel instead
        return lv[j + 1] if steep_x else face_cross(j)

    zc = face_mount(4)
    m.cut_info["avoid"] += [face_mount(4), face_mount(3)]
    microwave_dish(m, V(0, -half(zc), zc), V(0, -1, 0), 6.5, arm=2.2, separate=split)
    zc = face_mount(3)
    microwave_dish(m, V(half(zc), 0, zc), V(1, 0, 0), 5.5, arm=2.2, separate=split)

    # --- top cap, mast with omni antennas, aviation light, lightning rod
    m.box_at((0, 0, ztop + 0.6), (2 * b1 + 3.5, 2 * b1 + 3.5, 1.3))
    for s in (-1, 1):
        m.beam(V(0, 0, ztop + 8), V(s * 6.2, 0, ztop + 8), 1.0, x_hint=UP)
        m.cyl(V(s * 6.2, 0, ztop + 3), V(s * 6.2, 0, ztop + 15), 0.85, 0.7, seg=12, mat="white")
    top_mast(m, ztop + 1.0, base_r=1.6, mast_h=17.0, rod_h=9.0)
    return m




# ----------------------------------------------------------------------------
# 1b) أبراج شبكية - نفس البرج، حدايد X بزاوية تطبع بدون سبورت
# ----------------------------------------------------------------------------
PRINT_MIN_ANGLE = 45.0    # أقل زاوية لحدايد X عن الأفقي (45 تطبع بدون سبورت)


def tower_lattice_print_a():
    """خيار A: X واحد عريض في كل وجه مثل القديم، كل X يغطي عدة مستويات.
    الأطباق والهوائيات المستطيلة قطع منفصلة تُطبع وحدها وتُركّب."""
    return tower_lattice("07_Lattice_PrintX_A", x_bays=1, split=True)


def tower_lattice_print_b():
    """خيار B: X صغيرتان جنب بعض، كثافة قريبة من القديم."""
    return tower_lattice("08_Lattice_PrintX_B", x_bays=2)

# ----------------------------------------------------------------------------
# 2) أبراج أحادية - Monopole
# ----------------------------------------------------------------------------
def tower_monopole():
    m = Model("02_Monopole")
    zf = pole_base(m, pad=38, flange_r=7.5, pole_r=4.0)
    H = 176.0
    R = tapered(4.0, 2.3, zf, H)
    m.cyl((0, 0, zf - 1.0), (0, 0, H), R(zf), R(H), seg=48)
    for zj in (62.0, 118.0):      # slip joints
        m.cyl((0, 0, zj - 0.8), (0, 0, zj + 0.8), R(zj) + 0.4, R(zj) + 0.3, seg=48)
    z, side = 16.0, 0              # climbing step bolts
    while z < 150:
        a = polar(1, 205 + (18 if side else -18))
        m.rod(a * (R(z) - 0.5) + UP * z, a * (R(z) + 2.4) + UP * z, 1.0, seg=8)
        z += 5.5
        side ^= 1
    cable_ladder(m, zf + 0.5, 155, R, 0)

    # top sector head frame (triangular) with 6 panels + 3 RRUs
    Rt = 10.0
    tri = [polar(Rt, 90 + 120 * i) for i in range(3)]
    for zz in (158.0, 175.0):
        for i in range(3):
            m.beam(tri[i] + UP * zz, tri[(i + 1) % 3] + UP * zz, 1.2, x_hint=UP)
            m.beam(UP * zz, tri[i] * 0.97 + UP * zz, 1.1, 1.3, x_hint=UP, ext=0)
        m.cyl((0, 0, zz - 1.2), (0, 0, zz + 1.2), R(zz) + 0.5, seg=32)
    for i in range(3):
        a, b = tri[i], tri[(i + 1) % 3]
        mid = (a + b) / 2
        nrm = mid.normalized()
        tang = (b - a).normalized()
        for s in (-3.3, 3.3):
            pipe = mid + nrm * 0.9 + tang * s
            mount_pipe(m, pipe, 156.0, 178.0)
            for zz in (158.0, 175.0):
                m.beam(mid + tang * s + UP * zz, pipe + UP * zz, 1.0, x_hint=UP, ext=0.3)
            antenna_on_pipe(m, pipe, nrm, 166.5, 3.3, 1.5, 16.0)
        rru(m, mid + nrm * 0.9 + tang * 3.3, -nrm, 165.0, w=2.2, d=1.4, h=4.5)

    # middle cluster: round platform, handrail, 3 panels, 1 dish
    zm = 110.0
    m.revolve([(0, zm - 1.0), (8.2, zm - 1.0), (8.2, zm), (0, zm)], seg=40)
    for i in range(6):
        p = polar(7.6, 30 + 60 * i)
        m.beam(p + UP * (zm - 0.2), p + UP * (zm + 4.2), 0.9)
        m.beam(polar(R(zm - 6), 30 + 60 * i, zm - 6), polar(7.8, 30 + 60 * i, zm - 0.5), 1.0)
    m.torus((0, 0, zm + 4.6), 7.6, t(1.0) / 2, seg=48, tseg=8)
    for i, ang in enumerate((60, 180, 300)):
        nrm = polar(1, ang)
        pipe = polar(8.6, ang)
        mount_pipe(m, pipe, zm - 1.5, zm + 13.5)
        antenna_on_pipe(m, pipe, nrm, zm + 6.0, 3.0, 1.4, 12.0)
    microwave_dish(m, polar(R(96), 120, 96), polar(1, 120), 4.5, arm=2.0)

    top_mast(m, H, base_r=1.3, mast_h=10.0, rod_h=8.0)
    return m


# ----------------------------------------------------------------------------
# 3) أبراج مايكروويف - Microwave backhaul tower
# ----------------------------------------------------------------------------
def tower_microwave():
    m = Model("03_Microwave_Tower")
    zf = pole_base(m, pad=40, flange_r=7.5, pole_r=3.8)
    H = 178.0
    R = tapered(3.8, 2.3, zf, H)
    m.cyl((0, 0, zf - 1.0), (0, 0, H), R(zf), R(H), seg=48)
    for zj in (55.0, 120.0):
        m.cyl((0, 0, zj - 0.8), (0, 0, zj + 0.8), R(zj) + 0.4, R(zj) + 0.3, seg=48)
    cable_ladder(m, zf + 0.5, 170, R, 270)

    dishes = [(172, 20, 4.5), (169, 200, 4.5), (156, -10, 6.5), (151, 170, 7.0),
              (135, 50, 5.5), (131, 230, 6.0), (113, 5, 7.5), (109, 185, 7.0),
              (91, 120, 5.0), (87, 300, 5.0)]
    for z, ang, rad in dishes:
        d = polar(1, ang)
        m.cyl((0, 0, z - 2.0), (0, 0, z + 2.0), R(z) + 0.45, seg=32)   # clamp collar
        microwave_dish(m, d * (R(z) - 0.3) + UP * z, d, rad, arm=2.3)

    # small sector antennas at the head
    for ang in (90, 210, 330):
        nrm = polar(1, ang)
        pipe = polar(R(176) + 2.4, ang)
        m.beam(polar(R(184) - 0.3, ang, 184), pipe + UP * 184, 1.0, x_hint=UP, ext=0.3)
        mount_pipe(m, pipe, 177.0, 190.0)
        antenna_on_pipe(m, pipe, nrm, 184.0, 2.6, 1.2, 9.0)
    m.cyl((0, 0, H - 1.0), (0, 0, 190.0), R(H), 1.6, seg=24)
    top_mast(m, 190.0, base_r=1.3, mast_h=3.0, rod_h=8.0)
    return m


# ----------------------------------------------------------------------------
# 4) محطات رادوم (حماية) - Radome station
# ----------------------------------------------------------------------------
def geodesic_radome(m, c, Rr, subdiv=2, shrink=0.9, grid=3):
    """Geodesic dome: smooth core + slightly curved panels separated by seams."""
    c = V(c)
    m.sphere(c, Rr - 0.85, seg=64, rings=32, mat="white")
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=1.0)
    tris = [[v.co.copy() for v in f.verts] for f in bm.faces]
    bm.free()
    for v0, v1, v2 in tris:
        g = (v0 + v1 + v2) / 3
        v0, v1, v2 = (g + (v - g) * shrink for v in (v0, v1, v2))
        idx = {}
        pts = []
        for i in range(grid + 1):
            for j in range(grid + 1 - i):
                idx[(i, j)] = len(pts)
                pts.append((v0 + (v1 - v0) * (i / grid) + (v2 - v0) * (j / grid)).normalized())
        n = len(pts)
        verts = [c + p * Rr for p in pts] + [c + p * (Rr - 2.0) for p in pts]
        faces = []
        for i in range(grid):
            for j in range(grid - i):
                a, b, d = idx[(i, j)], idx[(i + 1, j)], idx[(i, j + 1)]
                faces.append((a, b, d))
                faces.append((n + a, n + d, n + b))
                if j < grid - i - 1:
                    e = idx[(i + 1, j + 1)]
                    faces.append((b, e, d))
                    faces.append((n + b, n + d, n + e))
        edge = ([idx[(i, 0)] for i in range(grid + 1)] +
                [idx[(grid - k, k)] for k in range(1, grid + 1)] +
                [idx[(0, grid - k)] for k in range(1, grid)])
        for k in range(len(edge)):
            a, b = edge[k], edge[(k + 1) % len(edge)]
            faces.append((a, n + a, n + b, b))
        m.add(verts, faces, "white")


def tower_radome():
    m = Model("04_Radome_Station")
    zf = pole_base(m, pad=40, flange_r=8.0, pole_r=4.4)
    zp = 116.0
    R = tapered(4.4, 3.5, zf, zp)
    m.cyl((0, 0, zf - 1.0), (0, 0, zp + 0.5), R(zf), R(zp), seg=48)
    m.cyl((0, 0, 60 - 0.8), (0, 0, 60 + 0.8), R(60) + 0.4, seg=48)

    # ladder with stand-offs
    a = polar(1, 0)
    tang = polar(1, 90)
    for s in (-1.7, 1.7):
        m.beam(a * (R(zf) + 2.4) + tang * s + UP * (zf + 0.5), a * (R(zp) + 2.4) + tang * s + UP * (zp - 0.5), 0.9, x_hint=tang, ext=0)
    z = zf + 4
    while z < zp - 2:
        m.beam(a * (R(z) + 2.4) - tang * 1.7 + UP * z, a * (R(z) + 2.4) + tang * 1.7 + UP * z, t(0.8), x_hint=UP)
        if int(z) % 15 < 3:
            for s in (-1.7, 1.7):
                m.beam(a * (R(z) - 0.3) + tang * s + UP * z, a * (R(z) + 2.4) + tang * s + UP * z, 0.9, x_hint=UP, ext=0)
        z += 3.2
    cable_ladder(m, zf + 0.5, zp - 1, R, 180, width=1.6)

    # circular platform with brackets and double handrail
    Rp = 15.0
    m.revolve([(0, zp - 1.2), (Rp, zp - 1.2), (Rp, zp), (0, zp)], seg=64)
    m.torus((0, 0, zp - 0.6), Rp, 0.75, seg=64, tseg=8)
    for i in range(8):
        ang = 22.5 + 45 * i
        m.beam(polar(R(zp - 11), ang, zp - 11), polar(Rp - 1.5, ang, zp - 0.8), 1.1)
    for i in range(16):
        p = polar(Rp - 0.6, 360 * i / 16)
        m.beam(p + UP * (zp - 0.2), p + UP * (zp + 5.4), 0.9)
    m.torus((0, 0, zp + 5.4), Rp - 0.6, t(1.0) / 2 + 0.05, seg=64, tseg=8)
    m.torus((0, 0, zp + 2.8), Rp - 0.6, t(0.8) / 2, seg=64, tseg=8)

    # equipment pedestal (drum) with access door and collar
    zd = zp + 10.0
    m.cyl((0, 0, zp - 0.5), (0, 0, zd), 9.0, 8.6, seg=48, mat="white")
    m.cyl((0, 0, zd - 1.2), (0, 0, zd + 0.4), 10.0, seg=48, mat="steel")
    m.box(frame(polar(8.7, 270, zp + 4.6), UP, polar(1, 0)), 4.2, 1.0, 6.5, mat="white")

    # geodesic radome
    Rr = 24.0
    cz = zd + Rr * 0.86
    geodesic_radome(m, (0, 0, cz), Rr)
    m.sphere((0, 0, cz + Rr + 0.2), 1.3, seg=16, rings=8, mat="red")
    m.cyl((0, 0, cz + Rr - 1.0), (0, 0, cz + Rr + 8.0), 0.8, t(1.0) / 2, seg=10)
    return m


# ----------------------------------------------------------------------------
# 5) محطات خلايا (4G/5G) - Cell site with 4G panels, 5G AAUs and ground cabinet
# ----------------------------------------------------------------------------
def tower_cell():
    m = Model("05_Cell_Site_4G_5G")
    m.loft_rects((0, -3), [(40, 44, 0), (40, 44, 2.2), (38.4, 42.4, 3.0)], "concrete")
    zf = pole_base(m, pad=24, flange_r=7.5, pole_r=4.2)
    H = 178.0
    R = tapered(4.2, 2.7, zf, H)
    m.cyl((0, 0, zf - 1.0), (0, 0, H), R(zf), R(H), seg=48)
    for zj in (58.0, 112.0):
        m.cyl((0, 0, zj - 0.8), (0, 0, zj + 0.8), R(zj) + 0.4, R(zj) + 0.3, seg=48)
    cable_ladder(m, 19.0, 160, R, 135)

    # ground cabinet + ice bridge to the pole
    cab = V(-8.5, -14.0, 3.0 + 8.0)
    cabinet(m, cab, (11.0, 8.0, 16.0), V(0, -1, 0))
    m.loft_rects((cab.x, cab.y), [(13, 10, 3.0 - EPS), (13, 10, 4.0)], "concrete")
    ib0 = V(-8.5, -9.6, 19.5)
    ib1 = polar(R(19.5) - 0.3, 135, 19.5)
    m.beam(ib0, ib1, 2.2, 0.9, x_hint=UP.cross(ib1 - ib0))
    m.beam(V(-8.5, -9.6, 3.0), V(-8.5, -9.6, 19.5), 1.2)

    # 4G tier: two rings, 3 sectors x 2 panels + RRUs
    Rr, z1, z2 = 10.5, 160.0, 177.0
    for zz in (z1, z2):
        m.torus((0, 0, zz), Rr, 0.75, seg=64, tseg=8)
        for i in range(3):
            ang = 90 + 120 * i + 60
            m.beam(polar(R(zz) - 0.3, ang, zz), polar(Rr, ang, zz), 1.3, x_hint=UP)
        m.cyl((0, 0, zz - 1.4), (0, 0, zz + 1.4), R(zz) + 0.5, seg=32)
    for i in range(3):
        ang = 90 + 120 * i
        nrm = polar(1, ang)
        for ds in (-17, 17):
            pipe = polar(Rr + 0.4, ang + ds)
            mount_pipe(m, pipe, z1 - 3, z2 + 2.5)
            antenna_on_pipe(m, pipe, nrm, (z1 + z2) / 2, 3.6, 1.7, 20.0)
            rru(m, pipe, -nrm, z1 + 4.0 if ds < 0 else z2 - 4.0)

    # 5G tier: massive-MIMO AAUs with cooling fins
    z5, R5 = 128.0, 8.5
    m.torus((0, 0, z5 - 5), R5, 0.75, seg=48, tseg=8)
    m.torus((0, 0, z5 + 5), R5, 0.75, seg=48, tseg=8)
    for zz in (z5 - 5, z5 + 5):
        for i in range(3):
            ang = 150 + 120 * i
            m.beam(polar(R(zz) - 0.3, ang, zz), polar(R5, ang, zz), 1.3, x_hint=UP)
    for i in range(3):
        ang = 90 + 120 * i
        nrm = polar(1, ang)
        pipe = polar(R5 + 0.4, ang)
        mount_pipe(m, pipe, z5 - 7, z5 + 7)
        d = 2.4
        c = pipe + nrm * (0.6 + d / 2 + 0.6) + UP * z5
        M = frame(c, UP, UP.cross(nrm))
        m.box(M, 6.0, d, 10.5, mat="white")
        m.box(M @ Matrix.Translation((0, d / 2, 0)), 5.2, 0.5, 9.7, mat="white")
        for k in range(5):
            m.box(M @ Matrix.Translation(((k - 2) * 1.15, -d / 2 - 0.3, 0)), t(0.6), 1.1, 9.5, mat="dark")
        for s in (-3.2, 3.2):
            m.beam(pipe + UP * (z5 + s), c - nrm * (d / 2) + UP * s, 1.0, x_hint=UP, ext=0.3)

    microwave_dish(m, polar(R(143) - 0.3, 210, 143), polar(1, 210), 4.5, arm=2.0)
    microwave_dish(m, polar(R(140) - 0.3, 330, 140), polar(1, 330), 3.8, arm=2.0)
    top_mast(m, H, base_r=1.3, mast_h=9.0, rod_h=8.0)
    return m


# ----------------------------------------------------------------------------
# 6) أبراج ذكية ومستدامة - Smart solar-powered pole
# ----------------------------------------------------------------------------
def tower_smart():
    m = Model("06_Smart_Solar_Pole")
    zf = pole_base(m, pad=34, flange_r=6.0, pole_r=3.0)
    H = 166.0
    R = tapered(3.0, 2.0, zf, H)
    m.cyl((0, 0, zf - 1.0), (0, 0, H), R(zf), R(H), seg=48)
    for zj in (40.0, 90.0, 140.0):
        m.cyl((0, 0, zj - 0.6), (0, 0, zj + 0.6), R(zj) + 0.35, seg=48)

    # battery / control cabinet + sensor box
    cabinet(m, polar(R(22) + 2.8 - 0.4, 270, 22.0), (8.0, 5.6, 22.0), V(0, -1, 0))
    cabinet(m, polar(R(64) + 2.2 - 0.4, 270, 64.0), (6.0, 4.4, 10.0), V(0, -1, 0))

    # 5G small cell shroud
    m.cyl((0, 0, 118), (0, 0, 131), 3.4, seg=40, mat="white")
    for zz in (118.3, 130.7):
        m.cyl((0, 0, zz - 0.5), (0, 0, zz + 0.5), 3.8, seg=40, mat="steel")
    for k in range(6):
        p = polar(3.35, 30 + 60 * k, 124.5)
        m.box(frame(p, UP, polar(1, 120 + 60 * k)), 0.8, 0.8, 10.5, mat="steel")

    # middle solar wings (two modules in a V)
    zc = 96.0
    for s in (-1, 1):
        nrm = Vector((s * 0.55, -0.45, 0.70)).normalized()
        c = V(s * 9.5, -1.5, zc)
        M = solar_panel(m, c, nrm, 13.0, 24.0, 4, 8)
        back = M @ Vector((0, 0, -1.6))
        m.cyl(V(0, 0, zc - 2.0), back, 0.9, seg=12)
        m.beam(V(0, 0, zc - 9.0), M @ Vector((0, -8.0, -1.6)), 1.2)
        m.beam(V(0, 0, zc + 7.0), M @ Vector((0, 8.0, -1.6)), 1.2)

    # street light arm (curved) + LED luminaire + CCTV camera
    zl = 146.0
    pts = []
    for i in range(7):
        u = i / 6
        pts.append(V(-21.0 * u, 0, zl + 7.0 * math.sin(u * math.pi * 0.6)))
    pts[0] = V(0, 0, zl - 1.0)
    for i in range(len(pts) - 1):
        m.cyl(pts[i], pts[i + 1], 1.0, 0.9, seg=12)
        m.sphere(pts[i + 1], 0.9 if i < len(pts) - 2 else 1.0, seg=12, rings=6)
    m.cyl((0, 0, zl - 2.0), (0, 0, zl + 2.0), R(zl) + 0.5, seg=32)
    head_c = pts[-1] + V(-4.5, 0, -0.6)
    Mh = frame(head_c, Vector((0.08, 0, 1)), V(1, 0, 0))
    m.box(Mh, 12.0, 5.2, 1.8, mat="steel")
    m.box(Mh @ Matrix.Translation((0, 0, 1.0)), 10.0, 4.0, 0.6, mat="steel")
    m.box(Mh @ Matrix.Translation((0, 0, -1.0)), 10.0, 4.0, 0.6, mat="light")
    cam = V(-9.0, 0, zl + 1.0)
    m.rod(pts[3] + V(0, 0, -0.5), cam + V(0, 0, -1.2), 1.0)
    Mc = frame(cam + V(0, 0, -2.4), UP, V(1, 0, 0))
    m.box(Mc, 2.4, 4.0, 2.2, mat="white")
    m.cyl(cam + V(0, -2.0, -2.4), cam + V(0, -3.0, -2.6), 0.85, seg=16, mat="dark")

    # top solar module tilted toward the front
    m.cyl((0, 0, H - 1.0), (0, 0, H + 4.0), R(H), 1.6, seg=24)
    nrm = Vector((0, -0.72, 0.69))
    M = solar_panel(m, V(0, -1.2, H + 8.0), nrm, 18.0, 12.0, 6, 4)
    m.beam(V(0, 0, H + 3.5), M @ Vector((0, 0, -1.6)), 1.6)
    m.beam(V(0, 0, H + 2.5), M @ Vector((0, -4.0, -1.6)), 1.0)
    p = M @ Vector((7.5, 4.5, 0))
    m.cyl(p - UP * 0.5, p + UP * 6.0, t(1.0) / 2, seg=8)
    return m


TOWERS = [tower_lattice, tower_monopole, tower_microwave, tower_radome, tower_cell, tower_smart,
          tower_lattice_print_a, tower_lattice_print_b]

# ----------------------------------------------------------------------------
# Materials (for rendering in Blender; STL ignores them)
# ----------------------------------------------------------------------------
MAT_DEFS = {
    "steel":    dict(color=(0.50, 0.53, 0.56, 1), metallic=0.9, rough=0.32),
    "white":    dict(color=(0.80, 0.81, 0.80, 1), metallic=0.0, rough=0.4),
    "dark":     dict(color=(0.07, 0.08, 0.09, 1), metallic=0.2, rough=0.5),
    "solar":    dict(color=(0.02, 0.05, 0.16, 1), metallic=0.5, rough=0.15),
    "concrete": dict(color=(0.36, 0.35, 0.33, 1), metallic=0.0, rough=0.9),
    "red":      dict(color=(0.8, 0.05, 0.03, 1), metallic=0.0, rough=0.4, emit=2.0),
    "light":    dict(color=(1.0, 0.95, 0.85, 1), metallic=0.0, rough=0.2, emit=4.0),
}


def get_mat(name):
    mname = "TT_" + name
    mat = bpy.data.materials.get(mname)
    if mat:
        return mat
    d = MAT_DEFS[name]
    mat = bpy.data.materials.new(mname)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = d["color"]
    bsdf.inputs["Metallic"].default_value = d["metallic"]
    bsdf.inputs["Roughness"].default_value = d["rough"]
    if "emit" in d:
        bsdf.inputs["Emission Color"].default_value = d["color"]
        bsdf.inputs["Emission Strength"].default_value = d["emit"]
    mat.diffuse_color = d["color"]
    return mat


# ----------------------------------------------------------------------------
# Build: parts -> boolean union (Manifold solver) -> single watertight mesh
# ----------------------------------------------------------------------------
def make_part_objects(model, coll):
    objs = []
    for i, (verts, faces, mat) in enumerate(model.parts):
        me = bpy.data.meshes.new(f"{model.name}_part{i:04d}")
        me.from_pydata(verts, [], faces)
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
        bm.free()
        me.materials.append(get_mat(mat))
        ob = bpy.data.objects.new(me.name, me)
        coll.objects.link(ob)
        objs.append(ob)
    return objs


def union_model(model, target_coll, solver="MANIFOLD"):
    parts = bpy.data.collections.new(model.name + "_parts")
    bpy.context.scene.collection.children.link(parts)
    objs = make_part_objects(model, parts)
    main = objs[0]
    parts.objects.unlink(main)
    target_coll.objects.link(main)
    if len(objs) == 1:          # nothing to merge with
        bpy.data.collections.remove(parts)
        main.name = model.name
        main.data.name = model.name
        return main
    mod = main.modifiers.new("Union", 'BOOLEAN')
    mod.operation = 'UNION'
    mod.operand_type = 'COLLECTION'
    mod.collection = parts
    mod.solver = solver
    if solver == "EXACT":
        mod.material_mode = 'TRANSFER'
    dg = bpy.context.evaluated_depsgraph_get()
    new_me = bpy.data.meshes.new_from_object(main.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    old_me = main.data
    main.modifiers.clear()
    main.data = new_me
    if not new_me.materials:
        for mt in {p[2] for p in model.parts}:
            new_me.materials.append(get_mat(mt))
    bpy.data.meshes.remove(old_me)
    for ob in objs[1:]:
        me = ob.data
        bpy.data.objects.remove(ob)
        bpy.data.meshes.remove(me)
    bpy.data.collections.remove(parts)
    main.name = model.name
    new_me.name = model.name
    return main


def subtract_cutters(ob, model):
    """Boolean-difference the model's cutters (holes, grooves) out of ob."""
    if not model.cutters:
        return
    coll = bpy.data.collections.new(model.name + "_cutters")
    bpy.context.scene.collection.children.link(coll)
    cut = Model(model.name + "_cut")
    cut.parts = model.cutters
    objs = make_part_objects(cut, coll)
    mod = ob.modifiers.new("Cut", 'BOOLEAN')
    mod.operation = 'DIFFERENCE'
    mod.operand_type = 'COLLECTION'
    mod.collection = coll
    mod.solver = 'MANIFOLD'
    dg = bpy.context.evaluated_depsgraph_get()
    new_me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    old_me = ob.data
    ob.modifiers.clear()
    ob.data = new_me
    new_me.name = old_me.name
    bpy.data.meshes.remove(old_me)
    for o in objs:
        me = o.data
        bpy.data.objects.remove(o)
        bpy.data.meshes.remove(me)
    bpy.data.collections.remove(coll)


def assign_materials(ob, model):
    """The union drops per-part materials; recover them from the nearest source part."""
    groups = {}
    for verts, faces, mat in model.parts:
        gv, gf = groups.setdefault(mat, ([], []))
        off = len(gv)
        gv.extend(verts)
        gf.extend(tuple(i + off for i in f) for f in faces)
    names = list(groups)
    trees = [BVHTree.FromPolygons(groups[n][0], groups[n][1]) for n in names]
    me = ob.data
    me.materials.clear()
    for n in names:
        me.materials.append(get_mat(n))
    for p in me.polygons:
        best, idx = None, 0
        for i, tree in enumerate(trees):
            hit = tree.find_nearest(p.center)
            if hit[0] is not None and (best is None or hit[3] < best):
                best, idx = hit[3], i
        p.material_index = idx


def _sliver_edge(f, tol=1e-4):
    """Longest edge of a zero-height triangle, else None."""
    e = max(f.edges, key=lambda e: e.calc_length())
    L = e.calc_length()
    if L < 1e-9 or 2 * f.calc_area() / L < tol:
        return e
    return None


def _flip_slivers(bm, max_iter=30):
    """Remove zero-height triangles by flipping their longest edge by hand
    (bmesh.ops.rotate_edges refuses because the quad has a 180 degree corner)."""
    for _ in range(max_iter):
        done = 0
        for f in list(bm.faces):
            if not f.is_valid:
                continue
            e = _sliver_edge(f)
            if e is None or len(e.link_faces) != 2:
                continue
            f1 = f
            f2 = e.link_faces[0] if e.link_faces[1] == f1 else e.link_faces[1]
            vs1 = [l.vert for l in f1.loops]
            i = next(k for k in range(3) if {vs1[k], vs1[(k + 1) % 3]} == set(e.verts))
            P, Q, Vv = vs1[i], vs1[(i + 1) % 3], vs1[(i + 2) % 3]
            C = next(v for v in f2.verts if v not in e.verts)
            if C == Vv or bm.edges.get((Vv, C)) is not None:
                continue
            mats = f1.material_index, f2.material_index
            bm.faces.remove(f1)
            bm.faces.remove(f2)
            bm.edges.remove(e)
            n1 = bm.faces.new((P, C, Vv))
            n2 = bm.faces.new((C, Q, Vv))
            n1.material_index, n2.material_index = mats
            done += 1
        if not done:
            break
    return sum(1 for f in bm.faces if _sliver_edge(f) is not None)


def _count_bad(bm):
    return (sum(1 for e in bm.edges if not e.is_manifold) +
            sum(1 for f in bm.faces if _sliver_edge(f) is not None))


def _score(bm):
    """Non-manifold edges are fatal for printing; slivers are only untidy."""
    nm = sum(1 for e in bm.edges if not e.is_manifold)
    return nm * 1000 + sum(1 for f in bm.faces if _sliver_edge(f) is not None)


def _collapse_short_edges(bm, tol):
    """Collapse edges shorter than tol, one at a time, only when the link
    condition holds, so the mesh stays manifold (triangle mesh expected)."""
    for _ in range(10):
        done = 0
        for e in list(bm.edges):
            if not e.is_valid or len(e.link_faces) != 2 or e.calc_length() >= tol:
                continue
            a, b = e.verts
            na = {o for ed in a.link_edges for o in ed.verts if o != a}
            nb = {o for ed in b.link_edges for o in ed.verts if o != b}
            opp = {v for f in e.link_faces for v in f.verts if v not in (a, b)}
            if (na & nb) != opp or len(opp) != 2:
                continue
            bmesh.ops.pointmerge(bm, verts=[a, b], merge_co=(a.co + b.co) / 2)
            done += 1
        if not done:
            break


def _weld_cleanup(bm, dist):
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=dist)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=dist)
    bmesh.ops.triangulate(bm, faces=bm.faces, quad_method='BEAUTY', ngon_method='BEAUTY')


def _collapse_cleanup(bm, tol):
    bmesh.ops.triangulate(bm, faces=bm.faces, quad_method='BEAUTY', ngon_method='BEAUTY')
    _collapse_short_edges(bm, tol)
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])


def clean_for_print(ob):
    """Remove the tiny edges and zero-area slivers the boolean leaves behind so
    the STL is a clean watertight triangle mesh. Two strategies (global weld,
    or link-checked edge collapse) at several tolerances; the best is kept."""
    src = ob.data.copy()
    best = None
    tries = [(_weld_cleanup, d) for d in (5e-4, 1e-4, 1e-3, 2e-3)]
    tries += [(_collapse_cleanup, d) for d in (2e-3, 5e-4, 5e-3, 1e-4)]
    for fn, tol in tries:
        bm = bmesh.new()
        bm.from_mesh(src)
        fn(bm, tol)
        _flip_slivers(bm)
        bad = _score(bm)
        if best is None or bad < best[0]:
            if best:
                best[1].free()
            best = (bad, bm)
        else:
            bm.free()
        if bad == 0:
            break
    best[1].to_mesh(ob.data)
    best[1].free()
    bpy.data.meshes.remove(src)


def check_manifold(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    shells = 0
    seen = set()
    for f in bm.faces:
        if f.index in seen:
            continue
        shells += 1
        stack = [f]
        seen.add(f.index)
        while stack:
            cur = stack.pop()
            for e in cur.edges:
                for g in e.link_faces:
                    if g.index not in seen:
                        seen.add(g.index)
                        stack.append(g)
    vol = bm.calc_volume(signed=True)
    bad = sum(1 for e in bm.edges if not e.is_manifold)
    bm.free()
    return bad, shells, vol


def support_report(ob, max_angle=45.0, bed_tol=0.05):
    """Printability check for an upright print (bed at the lowest Z).

    steep_mm2  : downward faces flatter than max_angle (true overhangs)
    flat_mm2   : horizontal downward faces (bridges if both ends are supported)
    islands    : places where material starts in mid-air (always need support)
    """
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.verts.ensure_lookup_table()
    zmin = min(v.co.z for v in bm.verts)
    lim = -math.cos(math.radians(max_angle))
    steep = flat = 0.0
    bad_faces = []
    for f in bm.faces:
        nz = f.normal.z
        if f.calc_center_median().z < zmin + bed_tol:
            continue
        if nz < -0.985:
            flat += f.calc_area()
            bad_faces.append(f.index)
        elif nz < lim:
            steep += f.calc_area()
            bad_faces.append(f.index)
    # islands: flat-connected vertex groups with nothing lower around them
    parent = list(range(len(bm.verts)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for e in bm.edges:
        a, b = e.verts
        if abs(a.co.z - b.co.z) < 0.02:
            parent[find(a.index)] = find(b.index)
    groups = {}
    for v in bm.verts:
        groups.setdefault(find(v.index), []).append(v)
    islands = []
    for vs in groups.values():
        z = min(v.co.z for v in vs)
        if z < zmin + bed_tol:
            continue
        lower = any(o.co.z < z - 0.02 for v in vs for e in v.link_edges for o in e.verts)
        if lower:
            continue
        nz = sum(f.normal.z for v in vs for f in v.link_faces)
        if nz < 0:
            c = sum((v.co for v in vs), Vector()) / len(vs)
            islands.append(tuple(round(x, 1) for x in c))
    bm.free()
    return dict(steep_mm2=steep, flat_mm2=flat, islands=islands, bad_faces=bad_faces)


def setup_scene():
    sc = bpy.context.scene
    us = sc.unit_settings
    us.system = 'METRIC'
    us.scale_length = 0.001
    us.length_unit = 'MILLIMETERS'
    for area in getattr(bpy.context, "screen", None).areas if getattr(bpy.context, "screen", None) else []:
        if area.type == 'VIEW_3D':
            for sp in area.spaces:
                if sp.type == 'VIEW_3D':
                    sp.clip_end = 10000
                    sp.overlay.grid_scale = 1.0


def clear_scene():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    for coll in list(bpy.data.collections):
        bpy.data.collections.remove(coll)
    for me in list(bpy.data.meshes):
        bpy.data.meshes.remove(me)


def export_stl(ob, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    loc = ob.location.copy()
    ob.location = (0, 0, 0)
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    path = os.path.join(out_dir, ob.name + ".stl")
    bpy.ops.wm.stl_export(filepath=path, export_selected_objects=True, apply_modifiers=True,
                          ascii_format=False, global_scale=1.0, use_scene_unit=False)
    ob.location = loc
    return path


def build_loose_parts(model, coll, offset_x, out_dir, scale=1.0, suffix=""):
    """Separate print parts: shown assembled on the tower in the scene, and
    exported as one print plate per group, each part turned to its print side."""
    groups = {}
    for i, (group, piece, down) in enumerate(model.loose):
        piece.name = f"{model.name}{suffix}_{group}_{len(groups.get(group, [])) + 1}"
        ob = union_model(piece, coll, "MANIFOLD")
        subtract_cutters(ob, piece)
        clean_for_print(ob)
        assign_materials(ob, piece)
        if scale != 1.0:
            ob.data.transform(Matrix.Scale(scale, 4))
        bad, shells, _ = check_manifold(ob)
        ob.location.x = offset_x
        groups.setdefault(group, []).append((ob, down, bad, shells))
    for group, items in groups.items():
        bad = sum(b for _, _, b, _ in items)
        shells = sum(sh for _, _, _, sh in items)
        print(f"    + {model.name}{suffix}_{group}: {len(items)} parts  non-manifold={bad}  shells={shells}")
        if not (EXPORT_STL and out_dir):
            continue
        plate = bpy.data.meshes.new(f"{model.name}{suffix}_{group}")
        bm = bmesh.new()
        cols = max(1, math.ceil(math.sqrt(len(items) * 2)) // 2 * 2) if len(items) > 4 else len(items)
        x = y = row_h = 0.0
        for k, (ob, down, _, _) in enumerate(items):
            tmp = ob.data.copy()
            tmp.transform(V(down).normalized().rotation_difference(Vector((0, 0, -1))).to_matrix().to_4x4())
            xs = [v.co.x for v in tmp.vertices]
            ys = [v.co.y for v in tmp.vertices]
            if max(xs) - min(xs) > max(ys) - min(ys):     # long side along Y
                tmp.transform(Matrix.Rotation(math.pi / 2, 4, 'Z'))
            xs = [v.co.x for v in tmp.vertices]
            ys = [v.co.y for v in tmp.vertices]
            zs = [v.co.z for v in tmp.vertices]
            if k and k % cols == 0:
                x, y, row_h = 0.0, y + row_h + 3.0, 0.0
            tmp.transform(Matrix.Translation((x - min(xs), y - min(ys), -min(zs))))
            x += max(xs) - min(xs) + 3.0
            row_h = max(row_h, max(ys) - min(ys))
            bm.from_mesh(tmp)
            bpy.data.meshes.remove(tmp)
        bm.to_mesh(plate)
        bm.free()
        tmp_ob = bpy.data.objects.new(plate.name, plate)
        bpy.context.scene.collection.objects.link(tmp_ob)
        export_stl(tmp_ob, out_dir)
        bpy.data.objects.remove(tmp_ob)
        bpy.data.meshes.remove(plate)


# ----------------------------------------------------------------------------
# برج كبير مقسّم إلى أجزاء تدخل الطابعة - Big tower split into printable sections
# ----------------------------------------------------------------------------
BIG_TOWER_HEIGHT = 600.0  # الارتفاع الكلي (مم)
MAX_SECTION = 220.0       # أقصى ارتفاع لكل جزء (مم) - حسب ارتفاع الطابعة
PIN_LEN = 6.0             # طول وتد التوصيل في كل رجل (مم)
PIN_FIT = 0.15            # فراغ الوتد داخل الفتحة (مم)


def mesh_boolean(ob, model, op):
    """Apply a Manifold boolean of ob with the closed meshes in model.parts."""
    coll = bpy.data.collections.new(ob.name + "_op")
    bpy.context.scene.collection.children.link(coll)
    objs = make_part_objects(model, coll)
    mod = ob.modifiers.new("Op", 'BOOLEAN')
    mod.operation = op
    mod.operand_type = 'COLLECTION'
    mod.collection = coll
    mod.solver = 'MANIFOLD'
    dg = bpy.context.evaluated_depsgraph_get()
    new_me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    old_me = ob.data
    ob.modifiers.clear()
    ob.data = new_me
    new_me.name = old_me.name
    bpy.data.meshes.remove(old_me)
    for o in objs:
        me = o.data
        bpy.data.objects.remove(o)
        bpy.data.meshes.remove(me)
    bpy.data.collections.remove(coll)


def choose_cuts(info, top, scale, max_section):
    """Cut heights (model units): between horizontal levels, clear of the leg
    flanges and dish arms, below the head. Fewest sections that each fit
    max_section, then the most even split among those."""
    lv = info["levels"]
    cands = [(a + b) / 2 for a, b in zip(lv, lv[1:])]
    cands = [z for z in cands if z <= info["max_cut"]
             and min(abs(z - l) for l in lv) >= 1.6
             and all(abs(z - a) >= 2.5 for a in info["avoid"])]
    for n_cuts in range(math.ceil(top * scale / max_section) - 1, len(cands) + 1):
        best = None
        for cuts in itertools.combinations(cands, n_cuts):
            edges = [0.0, *cuts, top]
            tallest = max(b - a for a, b in zip(edges, edges[1:])) * scale
            if tallest <= max_section and (best is None or tallest < best[0]):
                best = (tallest, list(cuts))
        if best:
            return best[1]
    raise RuntimeError(f"cannot split the tower into sections of at most {max_section} mm")


def build_big_tower(fn, out_dir, height=BIG_TOWER_HEIGHT, max_section=MAX_SECTION):
    """Build fn() at `height`, cut it into sections that fit the printer, add a
    pin/socket in every leg at each cut, and export sections + loose parts."""
    global FIT_SCALE
    if CLEAR_SCENE:
        clear_scene()
    setup_scene()
    coll = bpy.data.collections.new("Big_Tower")
    bpy.context.scene.collection.children.link(coll)
    probe = fn()
    natural = max(v[2] for verts, _, _ in probe.parts for v in verts)
    scale = height / natural
    FIT_SCALE = scale
    try:
        model = fn()
        tag = f"_{height / 10:.0f}cm"
        body = union_model(model, coll, "MANIFOLD")
        clean_for_print(body)
        assign_materials(body, model)
        body.data.transform(Matrix.Scale(scale, 4))
        info = model.cut_info
        cuts = choose_cuts(info, natural, scale, max_section)
        bounds = [0.0] + [c * scale for c in cuts] + [height + 1.0]
        print(f"  {model.name}{tag}: scale x{scale:.3f}, cuts at " + ", ".join(f"{c * scale:.1f}" for c in cuts) + " mm")
        sections = []
        for k in range(len(bounds) - 1):
            lo, hi = bounds[k], bounds[k + 1]
            ob = body.copy()
            ob.data = body.data.copy()
            ob.name = f"{model.name}{tag}_part{k + 1}"
            ob.data.name = ob.name
            coll.objects.link(ob)
            box = Model("box")
            box.box(Matrix.Translation((0, 0, (lo + hi) / 2)), 1000, 1000, hi - lo)
            mesh_boolean(ob, box, 'INTERSECT')
            joints = Model("joints")
            if k > 0:          # socket for the pins of the section below
                zc = cuts[k - 1]
                for x, y in info["leg_xy"](zc):
                    c = V(x * scale, y * scale, lo)
                    joints.cyl(c - UP * 1.0, c + UP * (PIN_LEN + 0.5), PIN_R(info, zc, scale) + PIN_FIT, seg=24)
                mesh_boolean(ob, joints, 'DIFFERENCE')
            if k < len(cuts):  # pins on top, into the section above
                zc = cuts[k]
                pins = Model("pins")
                for x, y in info["leg_xy"](zc):
                    c = V(x * scale, y * scale, hi)
                    pins.cyl(c - UP * 3.0, c + UP * PIN_LEN, PIN_R(info, zc, scale), seg=24)
                mesh_boolean(ob, pins, 'UNION')
            clean_for_print(ob)
            assign_materials(ob, model)
            sections.append(ob)
        bpy.data.objects.remove(body)
        for k, ob in enumerate(sections):
            bad, shells, vol = check_manifold(ob)
            d = ob.dimensions
            print(f"    part{k + 1}: {d.x:6.1f} x {d.y:6.1f} x {d.z:6.1f} mm  non-manifold={bad}  shells={shells}  "
                  f"volume={vol / 1000:.1f} cm3")
            if EXPORT_STL and out_dir:
                zmin = min(v.co.z for v in ob.data.vertices)
                ob.data.transform(Matrix.Translation((0, 0, -zmin)))
                export_stl(ob, out_dir)
                ob.data.transform(Matrix.Translation((0, 0, zmin)))
        if model.loose:
            build_loose_parts(model, coll, 0.0, out_dir, scale=scale, suffix=tag)
        if model.name in LABELS:
            build_labels([(sections[0], model.name, model.name + tag)], coll, out_dir, k=scale)
        return sections, cuts, scale
    finally:
        FIT_SCALE = 1.0


def PIN_R(info, zc, scale):
    """Pin radius: 40% of the leg radius at the cut, at most 2 mm."""
    return min(2.0, 0.4 * info["leg_r"](zc) * scale)


# ----------------------------------------------------------------------------
# لوحات الأسماء بالإنجليزي - English name plates (2 mm plate + slotted stand)
# ----------------------------------------------------------------------------
LABELS = {
    "01_Lattice_Tower": ["LATTICE TOWER"],
    "02_Monopole": ["MONOPOLE TOWER"],
    "03_Microwave_Tower": ["MICROWAVE TOWER"],
    "04_Radome_Station": ["RADOME STATION"],
    "05_Cell_Site_4G_5G": ["CELL SITE", "4G / 5G"],
    "06_Smart_Solar_Pole": ["SMART &", "SUSTAINABLE"],
    "07_Lattice_PrintX_A": ["LATTICE TOWER"],
    "08_Lattice_PrintX_B": ["LATTICE TOWER"],
}
LABEL_PLATE = 2.0         # سماكة خلفية اللوحة (مم)
LABEL_RELIEF = 0.8        # ارتفاع الحروف والإطار فوق الخلفية (مم)
LABEL_TEXT = 5.0          # حجم الخط (مم)
LABEL_SLOT_DEPTH = 4.0    # عمق دخول اللوحة في القاعدة (مم)
LABEL_FIT = 0.25          # فراغ اللوحة داخل شق القاعدة (مم)
LABEL_FONTS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
               "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
               "C:/Windows/Fonts/arialbd.ttf", "/Library/Fonts/Arial Bold.ttf"]


def rounded_rect(w, h, r, seg=6):
    pts = []
    for cx, cy, a0 in ((w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90),
                       (-w / 2 + r, -h / 2 + r, 180), (w / 2 - r, -h / 2 + r, 270)):
        for k in range(seg + 1):
            a = math.radians(a0 + 90 * k / seg)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def add_prism(m, poly, z0, z1, mat, hole=None):
    """Extrude a 2D outline (optionally with a same-size hole outline) between z0 and z1."""
    n = len(poly)
    verts = [Vector((x, y, z)) for z in (z0, z1) for x, y in poly]
    if hole is None:
        faces = [tuple(reversed(range(n))), tuple(range(n, 2 * n))]
        faces += [(k, (k + 1) % n, n + (k + 1) % n, n + k) for k in range(n)]
    else:
        assert len(hole) == n
        verts += [Vector((x, y, z)) for z in (z0, z1) for x, y in hole]
        o0, o1, i0, i1 = 0, n, 2 * n, 3 * n
        faces = []
        for k in range(n):
            k1 = (k + 1) % n
            faces += [(o0 + k, o0 + k1, o1 + k1, o1 + k), (i0 + k1, i0 + k, i1 + k, i1 + k1),
                      (o1 + k, o1 + k1, i1 + k1, i1 + k), (o0 + k1, o0 + k, i0 + k, i0 + k1)]
    m.add(verts, faces, mat)


def shape_text(line):
    """Arabic needs joined letter forms and right-to-left order, which Blender's
    text does not do: reshape to presentation forms and reorder for display."""
    if not any("\u0600" <= ch <= "\u06ff" for ch in line):
        return line
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
    except ImportError:
        raise RuntimeError("Arabic text needs: pip install arabic-reshaper python-bidi "
                           "(into Blender's Python)")
    return get_display(arabic_reshaper.reshape(line))


def text_parts(lines, size, z0, z1):
    """Raised text as closed meshes (one shell per glyph), centred on the origin."""
    font = None
    for path in LABEL_FONTS:
        if os.path.exists(path):
            font = bpy.data.fonts.load(path, check_existing=True)
            break
    cu = bpy.data.curves.new("label_text", 'FONT')
    cu.body = "\n".join(shape_text(line) for line in lines)
    if font:
        cu.font = font
    cu.size = size
    cu.space_line = 1.15
    cu.align_x = 'CENTER'
    cu.align_y = 'CENTER'
    cu.extrude = (z1 - z0) / 2
    cu.fill_mode = 'BOTH'
    ob = bpy.data.objects.new("label_text", cu)
    bpy.context.scene.collection.objects.link(ob)
    ob.location.z = (z0 + z1) / 2
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), depsgraph=dg)
    me.transform(ob.matrix_world)
    bpy.data.objects.remove(ob)
    bpy.data.curves.remove(cu)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.verts.ensure_lookup_table()
    # one closed shell per glyph: joined (Arabic) letters overlap, so each
    # shell must be its own part for the boolean union to merge them
    shells, seen = [], set()
    for f0 in bm.faces:
        if f0.index in seen:
            continue
        stack, fs = [f0], []
        seen.add(f0.index)
        while stack:
            f = stack.pop()
            fs.append(f)
            for e in f.edges:
                for g in e.link_faces:
                    if g.index not in seen:
                        seen.add(g.index)
                        stack.append(g)
        vmap = {}
        for f in fs:
            for v in f.verts:
                vmap.setdefault(v.index, len(vmap))
        verts = [None] * len(vmap)
        for vi, k in vmap.items():
            verts[k] = bm.verts[vi].co.copy()
        shells.append((verts, [tuple(vmap[v.index] for v in f.verts) for f in fs]))
    xs = [v.co.x for v in bm.verts]
    ys = [v.co.y for v in bm.verts]
    bm.free()
    bpy.data.meshes.remove(me)
    return shells, (max(xs) - min(xs), max(ys) - min(ys))


def label_models(name, lines, k=1.0):
    """Plate (built lying flat, text up = its print side) and slotted stand.
    k scales the lettering and stand; the plate stays LABEL_PLATE thick."""
    return plate_models(name, [(lines, LABEL_TEXT * k)], k)


def plate_models(name, blocks, k=1.0, gap=2.5):
    """Name plate with stacked text blocks [(lines, letter size), ...]."""
    relief = LABEL_RELIEF * (1.5 if k > 1.5 else 1.0)
    slot = LABEL_SLOT_DEPTH * k
    made = [text_parts(lines, size, LABEL_PLATE - 0.2, LABEL_PLATE + relief) for lines, size in blocks]
    tw = max(bw for _, (bw, _) in made)
    th = sum(bh for _, (_, bh) in made) + gap * k * (len(made) - 1)
    glyphs, y = [], th / 2
    for shells, (_, bh) in made:       # stack the blocks top to bottom
        glyphs += [([v + Vector((0, y - bh / 2, 0)) for v in sv], sf) for sv, sf in shells]
        y -= bh + gap * k
    margin, frame_w = 3.5 * k, 1.2 * k
    w = max(tw + 2 * (margin + frame_w), 34.0 * k)
    text_h = th + 2 * margin + 2 * frame_w
    h = text_h + slot
    plate = Model(f"label_{name}_plate")
    add_prism(plate, rounded_rect(w, h, 2.0 * k), 0.0, LABEL_PLATE, "white")
    # text area sits above the part that goes into the slot
    oy = slot / 2
    ow, oh = w - 1.0 * k, text_h - 1.0 * k
    outer = [(x, y + oy) for x, y in rounded_rect(ow, oh, 1.6 * k)]
    inner = [(x, y + oy) for x, y in rounded_rect(ow - 2 * frame_w, oh - 2 * frame_w, 0.6 * k)]
    add_prism(plate, outer, LABEL_PLATE - 0.2, LABEL_PLATE + relief, "dark", hole=inner)
    for sv, sf in glyphs:
        plate.add([v + Vector((0, oy, 0)) for v in sv], sf, "dark")
    stand = Model(f"label_{name}_stand")
    sw, sd, sh = w + 6.0 * k, 12.0 * k, 7.0 * k
    stand.loft_rects((0, 0), [(sw, sd, 0.0), (sw, sd, sh - 1.5 * k), (sw - 3.0 * k, sd - 3.0 * k, sh)], "concrete")
    slot_w = LABEL_PLATE + LABEL_FIT
    stand.cut().box(Matrix.Translation((0, 0, sh - slot / 2 + 0.5)), w + 2 * LABEL_FIT, slot_w, slot + 1.0)
    return plate, stand, (w, h, sh, slot)


def build_labels(pairs, coll, out_dir, k=1.0):
    """Name plate + stand in front of each (tower object, LABELS key, file name);
    one STL per tower with both parts laid out in their print orientation."""
    for tower, key, name in pairs:
        lines = LABELS[key]
        plate_m, stand_m, (w, h, sh, slot) = label_models(name, lines, k)
        plate = union_model(plate_m, coll, "MANIFOLD")
        clean_for_print(plate)
        assign_materials(plate, plate_m)
        stand = union_model(stand_m, coll, "MANIFOLD")
        subtract_cutters(stand, stand_m)
        clean_for_print(stand)
        assign_materials(stand, stand_m)
        bad = check_manifold(plate)[0] + check_manifold(stand)[0]
        shells = check_manifold(plate)[1], check_manifold(stand)[1]
        if EXPORT_STL and out_dir:
            bm = bmesh.new()
            for me, M in ((plate.data, Matrix.Identity(4)),
                          (stand.data, Matrix.Translation((0, -(h / 2 + 12.0 * k), 0)))):
                tmp = me.copy()
                tmp.transform(M)
                bm.from_mesh(tmp)
                bpy.data.meshes.remove(tmp)
            out = bpy.data.meshes.new(f"label_{name}")
            bm.to_mesh(out)
            bm.free()
            tmp_ob = bpy.data.objects.new(out.name, out)
            bpy.context.scene.collection.objects.link(tmp_ob)
            export_stl(tmp_ob, os.path.join(out_dir, "labels"))
            bpy.data.objects.remove(tmp_ob)
            bpy.data.meshes.remove(out)
        # stand it up in front of the tower: plate's print-up (+Z) faces the viewer (-Y)
        front = min((tower.matrix_world @ Vector(c)).y for c in tower.bound_box)
        y = front - 9.0 * k
        x = tower.location.x
        plate.data.transform(Matrix.Translation((0, h / 2 - slot, 0)))
        plate.data.transform(Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1))))
        plate.location = (x, y + LABEL_PLATE / 2, sh + 0.05)     # bottom edge on the slot floor
        stand.location = (x, y, 0)
        print(f"    label {name:24s} '{' / '.join(lines)}'  plate {w:.0f} x {h:.0f} mm, {LABEL_PLATE:.0f} mm back"
              f"  non-manifold={bad}  shells={shells}")


CREDITS = [
    (["كروب B"], 8.0),
    (["الدكتورة زهراء علاء الخفاجي"], 6.0),
    (["سجاد خضير حليم", "كرار فرحان عبد الكاظم", "سيف سعد نجم",
      "سلام ستار", "علي حسين عبد الهادي", "حسين علي حسين"], 5.5),
]


def build_credits(coll, out_dir, x, y):
    """Group-B credits plaque (same 2 mm plate + stand), standing behind the towers."""
    name = "Credits_Group_B"
    plate_m, stand_m, (w, h, sh, slot) = plate_models(name, CREDITS, gap=3.0)
    plate = union_model(plate_m, coll, "MANIFOLD")
    clean_for_print(plate)
    assign_materials(plate, plate_m)
    stand = union_model(stand_m, coll, "MANIFOLD")
    subtract_cutters(stand, stand_m)
    clean_for_print(stand)
    assign_materials(stand, stand_m)
    if EXPORT_STL and out_dir:
        bm = bmesh.new()
        for me, M in ((plate.data, Matrix.Identity(4)),
                      (stand.data, Matrix.Translation((0, -(h / 2 + 12.0), 0)))):
            tmp = me.copy()
            tmp.transform(M)
            bm.from_mesh(tmp)
            bpy.data.meshes.remove(tmp)
        out = bpy.data.meshes.new("credits_group_B")
        bm.to_mesh(out)
        bm.free()
        tmp_ob = bpy.data.objects.new(out.name, out)
        bpy.context.scene.collection.objects.link(tmp_ob)
        export_stl(tmp_ob, os.path.join(out_dir, "labels"))
        bpy.data.objects.remove(tmp_ob)
        bpy.data.meshes.remove(out)
    plate.data.transform(Matrix.Translation((0, h / 2 - slot, 0)))
    plate.data.transform(Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1))))
    plate.location = (x, y + LABEL_PLATE / 2, sh + 0.05)
    stand.location = (x, y, 0)
    bad = check_manifold(plate)[0] + check_manifold(stand)[0]
    print(f"    credits plaque {w:.0f} x {h:.0f} mm, {LABEL_PLATE:.0f} mm back  non-manifold={bad}  "
          f"shells={check_manifold(plate)[1]}, {check_manifold(stand)[1]}")


def build_all(out_dir=None):
    if CLEAR_SCENE:
        clear_scene()
    setup_scene()
    coll = bpy.data.collections.new("Telecom_Towers")
    bpy.context.scene.collection.children.link(coll)
    results = []
    n = len(TOWERS)
    for i, fn in enumerate(TOWERS):
        model = fn()
        ob = union_model(model, coll, "MANIFOLD")
        clean_for_print(ob)
        bad, shells, vol = check_manifold(ob)
        if bad or shells != 1:
            print(f"  {model.name}: manifold solver gave {bad} bad edges / {shells} shells, retrying EXACT")
            bpy.data.objects.remove(ob)
            model = fn()
            ob = union_model(model, coll, "EXACT")
            clean_for_print(ob)
            bad, shells, vol = check_manifold(ob)
        assign_materials(ob, model)
        ob.location.x = (i - (n - 1) / 2) * TOWER_SPACING
        for p in ob.data.polygons:
            p.use_smooth = False
        dims = ob.dimensions
        info = dict(name=ob.name, x=dims.x, y=dims.y, z=dims.z, faces=len(ob.data.polygons),
                    parts=len(model.parts), bad_edges=bad, shells=shells, volume_cm3=vol / 1000)
        results.append(info)
        print("  {name:24s} {x:6.1f} x {y:6.1f} x {z:6.1f} mm  faces={faces:7d}  parts={parts:5d}  "
              "non-manifold={bad_edges}  shells={shells}  volume={volume_cm3:.1f} cm3".format(**info))
        if EXPORT_STL and out_dir:
            export_stl(ob, out_dir)
        if model.loose:
            build_loose_parts(model, coll, ob.location.x, out_dir)
    build_labels([(o, o.name, o.name) for o in coll.objects if o.name in LABELS], coll, out_dir)
    back = max((o.matrix_world @ Vector(c)).y for o in coll.objects if o.name in LABELS for c in o.bound_box)
    build_credits(coll, out_dir, 0.0, back + 25.0)
    return results


def setup_render(path=None):
    """Camera, sun, ground and Cycles settings for a catalogue-style preview."""
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.samples = 96
    sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = 2000, 1200
    sc.render.film_transparent = False
    try:
        sc.view_settings.view_transform = 'AgX'
        sc.view_settings.look = 'AgX - Medium High Contrast'
    except TypeError:
        pass
    # thin outlines so every member reads clearly
    sc.render.use_freestyle = True
    sc.render.line_thickness_mode = 'ABSOLUTE'
    sc.render.line_thickness = 0.7
    for ls in sc.view_layers[0].freestyle_settings.linesets:
        ls.linestyle.color = (0.05, 0.06, 0.08)
        ls.linestyle.alpha = 0.85
    # sky gradient. The camera sees a screen-space gradient (an ortho camera would
    # otherwise see one flat colour); reflections and lighting use a real sky dome.
    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    sc.world = world
    world.use_nodes = True
    nt = world.node_tree
    bg = nt.nodes.get("Background")
    bg.inputs[1].default_value = 0.8

    def gradient(coord, axis, lo, hi, p_hi):
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        e0, e1 = ramp.color_ramp.elements
        e0.position, e0.color = 0.0, lo
        e1.position, e1.color = p_hi, hi
        nt.links.new(coord, sep.inputs[0])
        nt.links.new(sep.outputs[axis], ramp.inputs[0])
        return ramp.outputs["Color"]

    tc = nt.nodes.new("ShaderNodeTexCoord")
    screen = gradient(tc.outputs["Window"], "Y", (0.80, 0.86, 0.93, 1), (0.22, 0.40, 0.68, 1), 1.0)
    dome = gradient(tc.outputs["Generated"], "Z", (0.70, 0.78, 0.88, 1), (0.12, 0.28, 0.60, 1), 0.6)
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = 'RGBA'
    nt.links.new(nt.nodes.new("ShaderNodeLightPath").outputs["Is Camera Ray"], mix.inputs["Factor"])
    nt.links.new(dome, mix.inputs[6])
    nt.links.new(screen, mix.inputs[7])
    nt.links.new(mix.outputs[2], bg.inputs[0])
    # ground
    me = bpy.data.meshes.new("Ground")
    s = 2000
    me.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
    g = bpy.data.objects.new("Ground", me)
    gm = bpy.data.materials.new("Ground")
    gm.use_nodes = True
    gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.42, 0.43, 0.42, 1)
    gm.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.8
    me.materials.append(gm)
    bpy.context.scene.collection.objects.link(g)
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", 'SUN'))
    sun.data.energy = 5.0
    sun.data.angle = math.radians(3)
    sun.rotation_euler = (math.radians(55), math.radians(12), math.radians(-40))
    bpy.context.scene.collection.objects.link(sun)
    cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
    cam.data.type = 'ORTHO'
    cam.data.ortho_scale = len(TOWERS) * TOWER_SPACING + 20
    cam.data.clip_end = 5000
    cam.location = (0, -900, 260)
    cam.rotation_euler = (math.radians(82), 0, 0)
    bpy.context.scene.collection.objects.link(cam)
    sc.camera = cam
    if path:
        sc.render.filepath = path


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out_dir = render = save = big = None
    for i, a in enumerate(argv):
        if a == "--out":
            out_dir = argv[i + 1]
        elif a == "--render":
            render = argv[i + 1]
        elif a == "--save":
            save = argv[i + 1]
        elif a == "--big":
            big = argv[i + 1]
    if out_dir is None:
        out_dir = bpy.path.abspath("//stl") if bpy.data.filepath else os.path.join(os.path.expanduser("~"), "telecom_towers_stl")
    if big:     # 60 cm option A, cut into sections: --big <file.blend>
        print("Building the big segmented tower ->", out_dir)
        build_big_tower(tower_lattice_print_a, out_dir)
        setup_render(None)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(big))
        return
    print("Building telecom towers ->", out_dir)
    build_all(out_dir)
    setup_render(os.path.abspath(render) if render else None)
    if save:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(save))
    if render:
        bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
