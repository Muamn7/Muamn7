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
def panel_antenna(m, center, outward, w=3.4, d=1.6, h=16.0, mat="white"):
    """Sector panel antenna with end caps and bottom connectors."""
    n = V(outward).normalized()
    tang = UP.cross(n)
    M = frame(V(center), UP, tang)   # local x = tangent, y = outward
    m.box(M, w, d, h, mat=mat)
    for s in (-1, 1):
        m.box(M @ Matrix.Translation((0, 0, s * (h / 2 - 0.3))), w + 0.3, d + 0.3, 0.9, mat="dark")
    for s in (-0.25, 0.25):
        p = M @ Vector((s * w, 0, -h / 2 - 0.2))
        m.rod(p, p - UP * 1.5, 1.0, seg=8, mat="dark")


def mount_pipe(m, p, z0, z1, d=1.2):
    m.rod(V(p.x, p.y, z0), V(p.x, p.y, z1), d, seg=10)


def antenna_on_pipe(m, pipe_xy, outward, zc, w, d, h, pipe_d=1.2, mat="white"):
    n = V(outward).normalized()
    n.z = 0
    n.normalize()
    pipe = V(pipe_xy[0], pipe_xy[1], zc)
    c = pipe + n * (t(pipe_d) / 2 + d / 2 - EPS)
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


def microwave_dish(m, base, direction, R, arm=2.5, mat="white"):
    """Shrouded microwave dish with radome cover, hub, arm and support strut."""
    d = V(direction).normalized()
    base = V(base)
    depth = R * 0.5
    arm_r = max(0.65, R * 0.13, t(1.0) / 2)
    back = base + d * arm
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
def tower_lattice():
    m = Model("01_Lattice_Tower")
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

    def r_leg(z):
        return 1.7 - 0.55 * (z - z0) / (ztop - z0)

    for c in corners:   # legs + splice flanges
        a, b = P(c, z0 - 1.0), P(c, zt)
        m.cyl(a, b, r_leg(z0), r_leg(zt), seg=14)
        m.cyl(P(c, zt) - UP * 1.0, V(c[0] * b1, c[1] * b1, ztop + 0.8), r_leg(zt), r_leg(ztop), seg=14)
        u = (b - a).normalized()
        for z in levels[1:-1]:
            q = P(c, z)
            uu = u if z <= zt else UP
            m.cyl(q - uu * 0.6, q + uu * 0.6, r_leg(z) + 0.45, seg=14)
        # base plate at pier
        m.box_at(P(c, z0) + UP * 0.2, (5.0, 5.0, 1.0))

    for i in range(4):   # X bracing + horizontals on each face
        ca, cb = corners[i], corners[(i + 1) % 4]
        nrm = Vector((ca[0] + cb[0], ca[1] + cb[1], 0)).normalized()
        for j in range(len(levels) - 1):
            za, zc = levels[j], levels[j + 1]
            w = 1.25 if za < 60 else 1.0
            m.beam(P(ca, za), P(cb, zc), w, x_hint=nrm)
            m.beam(P(cb, za), P(ca, zc), w, x_hint=nrm)
            if j > 0:
                m.beam(P(ca, za), P(cb, za), w, x_hint=UP)
        m.beam(P(ca, ztop), P(cb, ztop), 1.1, x_hint=UP)
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
            antenna_on_pipe(m, pipe, nrm, (zp + zu) / 2 + 0.5, 3.6, 1.7, 18.0)
            rru(m, pipe, -nrm, zp + 4.5) if s > 0 else None

    # --- microwave dishes on the legs and faces
    for c, R in (((1, -1), 5.0), ((-1, 1), 4.5)):
        microwave_dish(m, P(c, zt + 9), Vector((c[0], c[1], 0)), R, arm=2.2)

    def face_cross(j):
        za, zc = lv[j], lv[j + 1]
        ba, bc = half(za), half(zc)
        return za + (zc - za) * ba / (ba + bc)

    zc = face_cross(4)
    microwave_dish(m, V(0, -half(zc), zc), V(0, -1, 0), 6.5, arm=2.2)
    zc = face_cross(3)
    microwave_dish(m, V(half(zc), 0, zc), V(1, 0, 0), 5.5, arm=2.2)

    # --- top cap, mast with omni antennas, aviation light, lightning rod
    m.box_at((0, 0, ztop + 0.6), (2 * b1 + 3.5, 2 * b1 + 3.5, 1.3))
    for s in (-1, 1):
        m.beam(V(0, 0, ztop + 8), V(s * 6.2, 0, ztop + 8), 1.0, x_hint=UP)
        m.cyl(V(s * 6.2, 0, ztop + 3), V(s * 6.2, 0, ztop + 15), 0.85, 0.7, seg=12, mat="white")
    top_mast(m, ztop + 1.0, base_r=1.6, mast_h=17.0, rod_h=9.0)
    return m


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


TOWERS = [tower_lattice, tower_monopole, tower_microwave, tower_radome, tower_cell, tower_smart]

# ----------------------------------------------------------------------------
# Materials (for rendering in Blender; STL ignores them)
# ----------------------------------------------------------------------------
MAT_DEFS = {
    "steel":    dict(color=(0.60, 0.62, 0.64, 1), metallic=1.0, rough=0.38),
    "white":    dict(color=(0.86, 0.87, 0.86, 1), metallic=0.0, rough=0.45),
    "dark":     dict(color=(0.07, 0.08, 0.09, 1), metallic=0.2, rough=0.5),
    "solar":    dict(color=(0.02, 0.05, 0.16, 1), metallic=0.5, rough=0.15),
    "concrete": dict(color=(0.52, 0.51, 0.49, 1), metallic=0.0, rough=0.9),
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


def clean_for_print(ob):
    """Weld near-duplicate vertices left by the boolean, triangulate, and flip
    away zero-area slivers so the STL is a clean watertight triangle mesh.
    Several weld distances are tried; the first one that gives a perfect mesh wins."""
    src = ob.data.copy()
    best = None
    for dist in (5e-4, 1e-4, 1e-3, 2e-3):
        bm = bmesh.new()
        bm.from_mesh(src)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=dist)
        bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=dist)
        bmesh.ops.triangulate(bm, faces=bm.faces, quad_method='BEAUTY', ngon_method='BEAUTY')
        _flip_slivers(bm)
        bad = _count_bad(bm)
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
    bad = _count_bad(bm)
    bm.free()
    return bad, shells, vol


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
    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    sc.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = (0.92, 0.93, 0.95, 1)
    bg.inputs[1].default_value = 1.1
    # ground
    me = bpy.data.meshes.new("Ground")
    s = 2000
    me.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
    g = bpy.data.objects.new("Ground", me)
    gm = bpy.data.materials.new("Ground")
    gm.use_nodes = True
    gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.8, 0.8, 0.8, 1)
    me.materials.append(gm)
    bpy.context.scene.collection.objects.link(g)
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", 'SUN'))
    sun.data.energy = 4.0
    sun.data.angle = math.radians(8)
    sun.rotation_euler = (math.radians(50), math.radians(10), math.radians(-35))
    bpy.context.scene.collection.objects.link(sun)
    cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
    cam.data.type = 'ORTHO'
    cam.data.ortho_scale = 470
    cam.data.clip_end = 5000
    cam.location = (0, -900, 260)
    cam.rotation_euler = (math.radians(82), 0, 0)
    bpy.context.scene.collection.objects.link(cam)
    sc.camera = cam
    if path:
        sc.render.filepath = path


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out_dir = render = save = None
    for i, a in enumerate(argv):
        if a == "--out":
            out_dir = argv[i + 1]
        elif a == "--render":
            render = argv[i + 1]
        elif a == "--save":
            save = argv[i + 1]
    if out_dir is None:
        out_dir = bpy.path.abspath("//stl") if bpy.data.filepath else os.path.join(os.path.expanduser("~"), "telecom_towers_stl")
    print("Building telecom towers ->", out_dir)
    build_all(out_dir)
    setup_render(os.path.abspath(render) if render else None)
    if save:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(save))
    if render:
        bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
