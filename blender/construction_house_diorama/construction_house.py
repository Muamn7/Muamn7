# -*- coding: utf-8 -*-
"""
مجسّم بيت طابقين قيد الإنشاء (طابوق + أعمدة + سقوف كونكريت) مع المعدّات
Miniature two-storey brick house under construction + site props.

- كل الوحدات بالمليمتر (1 Blender unit = 1 mm) — جاهز للطباعة ثلاثية الأبعاد.
- All units are millimetres (1 BU = 1 mm), scene unit scale = 0.001.

طريقة التشغيل / How to run
  1) داخل بلندر: Scripting > Open > construction_house.py > Run Script
  2) من الطرفية (يصدّر STL + ملف blend):
     blender --background --python construction_house.py -- --out ./output
     (أضف --render preview.png لعمل صورة معاينة، و --no-union لتسريع التشغيل)

Tested with Blender 5.3 (bpy). Uses only core API, should also work on 4.2+.
"""

import math
import os
import struct
import sys
import time

import bpy  # bpy first (needed when running as a Python module)
import bmesh
from mathutils import Matrix, Vector

# ---------------------------------------------------------------------------
# الإعدادات / SETTINGS  (غيّر الأرقام هنا)
# ---------------------------------------------------------------------------

# الطابوقة الواحدة (من القياسات: طول 1.3-2 سم، عرض 0.6-1 سم، سمك 0.4-0.6 سم)
BRICK_L = 17.0      # طول الطابوقة  mm
BRICK_W = 8.0       # عرض الطابوقة = سمك الجدار  mm
BRICK_H = 5.0       # سمك (ارتفاع) الطابوقة  mm
JOINT = 1.0         # سمك الملاط (السمنت بين الطابوق)  mm
MORTAR_RECESS = 0.5  # عمق فرزة الملاط عن وجه الطابوق  mm

COURSE = BRICK_H + JOINT          # 6 mm per brick course
PITCH = BRICK_L + JOINT           # 18 mm per brick along the wall
CORE_T = BRICK_W - 2 * MORTAR_RECESS

# البيت (بصمة 24 × 17 سم حتى يدخل بطابعة 256 × 256)
HOUSE_X0, HOUSE_X1 = -120.0, 120.0
HOUSE_Y0, HOUSE_Y1 = -45.0, 125.0
COL = 12.0                        # مقطع العمود 1.2 × 1.2 سم
FLOOR_PLATE = 3.0                 # أرضية الطابق الأرضي
SLAB = 10.0                       # سمك السقف 1 سم
GF_COURSES = 22                   # الطابق الأرضي 22 صف = 13.2 سم
FF_COURSES = 20                   # الطابق الثاني 20 صف = 12 سم
PARAPET_COURSES = 4               # الستارة 4 صفوف = 2.4 سم

# القاعدة الخشبية 45 × 35 سم
BASE_W, BASE_D, BASE_T = 450.0, 350.0, 15.0
SPLIT_BASE = True   # قسّم القاعدة إلى 4 قطع (225×175) حتى تدخل الطابعة

STAIRS_SOLID = True  # درج مصمت إلى الأرض (أسهل بالطباعة، بدون دعامات)

# دمج كل قطعة إلى جسم واحد مغلق (Manifold) — أبطأ لكن أنظف للطباعة
UNION_PARTS = True

# ---------------------------------------------------------------------------
# derived layout
# ---------------------------------------------------------------------------
H = COL / 2.0
XL, XR = HOUSE_X0 + H, HOUSE_X1 - H      # wall centre lines (left / right)
YF, YB = HOUSE_Y0 + H, HOUSE_Y1 - H      # wall centre lines (front / back)
XM = 40.0                                # inner column lines x = ±40
YM = 40.0                                # side middle column y = 40

Z_GF = FLOOR_PLATE
Z_GF_TOP = Z_GF + GF_COURSES * COURSE                # 135
Z_SLAB1_TOP = Z_GF_TOP + SLAB                         # 145
Z_FF_TOP = Z_SLAB1_TOP + FF_COURSES * COURSE          # 265
Z_ROOF_TOP = Z_FF_TOP + SLAB                          # 275
ROOF_X1 = 47.0   # roof slab is cast only for x < 47; the rest is formwork

# material slots
M_BRICK, M_MORTAR, M_CONCRETE, M_WOOD, M_METAL, M_BAG, M_RUBBER, M_SAND, M_BOARD = range(9)
MATERIALS = [
    ("Brick",    (0.42, 0.11, 0.06, 1), 0.85),
    ("Mortar",   (0.58, 0.56, 0.52, 1), 0.95),
    ("Concrete", (0.48, 0.48, 0.47, 1), 0.90),
    ("Wood",     (0.62, 0.45, 0.27, 1), 0.70),
    ("Metal",    (0.38, 0.39, 0.40, 1), 0.45),
    ("CementBag", (0.74, 0.71, 0.60, 1), 0.90),
    ("Rubber",   (0.04, 0.04, 0.04, 1), 0.80),
    ("Sand",     (0.52, 0.47, 0.40, 1), 1.00),
    ("Board",    (0.40, 0.27, 0.15, 1), 0.75),
]


# ---------------------------------------------------------------------------
# Mesh builder: accumulates closed shells, builds one object at the end
# ---------------------------------------------------------------------------
class MB:
    BOX_FACES = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
                 (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]

    def __init__(self):
        self.v, self.f, self.m = [], [], []

    def add(self, verts, faces, mat, matrix=None):
        b = len(self.v)
        if matrix is not None:
            verts = [tuple(matrix @ Vector(p)) for p in verts]
        self.v.extend(verts)
        for face in faces:
            self.f.append(tuple(b + i for i in face))
            self.m.append(mat)

    def box(self, x0, x1, y0, y1, z0, z1, mat, matrix=None):
        if x1 - x0 < 1e-4 or y1 - y0 < 1e-4 or z1 - z0 < 1e-4:
            return
        v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
             (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        self.add(v, self.BOX_FACES, mat, matrix)

    def cbox(self, cx, cy, cz, sx, sy, sz, mat, matrix=None):
        """box centred on x/y, z from cz to cz+sz"""
        self.box(cx - sx / 2, cx + sx / 2, cy - sy / 2, cy + sy / 2, cz, cz + sz, mat, matrix)

    def bar(self, p0, p1, size, mat, matrix=None):
        """square-section bar between two points"""
        p0, p1 = Vector(p0), Vector(p1)
        d = (p1 - p0).normalized()
        up = Vector((0, 0, 1)) if abs(d.z) < 0.9 else Vector((1, 0, 0))
        a = d.cross(up).normalized() * size / 2
        b = d.cross(a).normalized() * size / 2
        v = []
        for p in (p0, p1):
            v += [tuple(p - a - b), tuple(p + a - b), tuple(p + a + b), tuple(p - a + b)]
        f = [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
        self.add(v, f, mat, matrix)

    def hull(self, points, mat, matrix=None):
        bm = bmesh.new()
        for p in points:
            bm.verts.new(p)
        bmesh.ops.convex_hull(bm, input=bm.verts)
        bm.verts.index_update()
        verts = [tuple(v.co) for v in bm.verts]
        faces = [tuple(v.index for v in f.verts) for f in bm.faces]
        bm.free()
        self.add(verts, faces, mat, matrix)

    def lathe(self, profile, mat, seg=32, matrix=None):
        """closed (r, z) profile revolved around Z. r == 0 points become poles."""
        verts, rings = [], []
        for r, z in profile:
            if r < 1e-6:
                rings.append([len(verts)])
                verts.append((0.0, 0.0, z))
            else:
                ring = []
                for i in range(seg):
                    a = 2 * math.pi * i / seg
                    ring.append(len(verts))
                    verts.append((r * math.cos(a), r * math.sin(a), z))
                rings.append(ring)
        faces = []
        n = len(rings)
        for k in range(n):
            ra, rb = rings[k], rings[(k + 1) % n]
            if len(ra) == 1 and len(rb) == 1:
                continue
            for i in range(seg):
                j = (i + 1) % seg
                if len(ra) == 1:
                    faces.append((ra[0], rb[i], rb[j]))
                elif len(rb) == 1:
                    faces.append((ra[i], ra[j], rb[0]))
                else:
                    faces.append((ra[i], ra[j], rb[j], rb[i]))
        self.add(verts, faces, mat, matrix)

    def extrude_x(self, poly_yz, x0, x1, mat):
        """extrude a (possibly concave) Y/Z polygon along X"""
        n = len(poly_yz)
        v = [(x0, y, z) for y, z in poly_yz] + [(x1, y, z) for y, z in poly_yz]
        f = [tuple(range(n)), tuple(range(2 * n - 1, n - 1, -1))]
        for i in range(n):
            j = (i + 1) % n
            f.append((i, j, n + j, n + i))
        self.add(v, f, mat)

    def build(self, name, collection):
        me = bpy.data.meshes.new(name)
        me.from_pydata(self.v, [], self.f)
        me.validate()
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
        bm.free()
        for i, (mname, _, _) in enumerate(MATERIALS):
            me.materials.append(bpy.data.materials[mname])
        me.polygons.foreach_set("material_index", self.m)
        me.update()
        ob = bpy.data.objects.new(name, me)
        collection.objects.link(ob)
        return ob


# ---------------------------------------------------------------------------
# brick wall generator
# ---------------------------------------------------------------------------
def wall(mb, axis, c, u0, u1, zb, courses, openings=(), segments=None, lintels=True):
    """
    axis 'x' : wall runs along X on the line y = c
    axis 'y' : wall runs along Y on the line x = c
    courses  : number of brick courses (if segments is None)
    segments : [(ua, ub, n_courses), ...] for stepped / unfinished walls
    openings : [(ua, ub, k0, k1), ...]  door/window, courses k0..k1-1 removed
    """
    if segments is None:
        segments = [(u0, u1, courses)]

    def put(ua, ub, ta, tb, za, zz, mat):
        if axis == 'x':
            mb.box(ua, ub, c + ta, c + tb, za, zz, mat)
        else:
            mb.box(c + ta, c + tb, ua, ub, za, zz, mat)

    def n_at(u):
        for a, b, n in segments:
            if a - 1e-6 <= u <= b + 1e-6:
                return n
        return 0

    # --- bricks (running bond) ---
    for sa, sb, n in segments:
        for k in range(n):
            cuts = sorted((oa, ob) for oa, ob, k0, k1 in openings if k0 <= k < k1)
            intervals, cur = [], sa
            for oa, ob in cuts:
                if ob <= cur or oa >= sb:
                    continue
                if oa > cur:
                    intervals.append((cur, oa))
                cur = max(cur, ob)
            if cur < sb:
                intervals.append((cur, sb))
            off = 0.0 if k % 2 == 0 else PITCH / 2
            z0 = zb + k * COURSE + JOINT / 2
            for a, b in intervals:
                j = math.floor((a - u0 + off) / PITCH) - 1
                while True:
                    p = u0 - off + j * PITCH
                    if p >= b:
                        break
                    ba, bb = max(p, a), min(p + BRICK_L, b)
                    if bb - ba >= 2.5:
                        put(ba, bb, -BRICK_W / 2, BRICK_W / 2, z0, z0 + BRICK_H, M_BRICK)
                    j += 1

    # --- mortar core (recessed), split in vertical bands around openings ---
    xs = {s[0] for s in segments} | {s[1] for s in segments}
    for oa, ob, _, _ in openings:
        xs |= {oa, ob}
    xs = sorted(x for x in xs if u0 <= x <= u1)
    for xa, xb in zip(xs, xs[1:]):
        m = (xa + xb) / 2
        n = n_at(m)
        if n == 0:
            continue
        holes = sorted((k0, k1) for oa, ob, k0, k1 in openings if oa < m < ob)
        k = 0
        for k0, k1 in holes:
            if k0 > k:
                put(xa, xb, -CORE_T / 2, CORE_T / 2, zb + k * COURSE, zb + k0 * COURSE, M_MORTAR)
            k = max(k, k1)
        if k < n:
            put(xa, xb, -CORE_T / 2, CORE_T / 2, zb + k * COURSE, zb + n * COURSE, M_MORTAR)

    # --- concrete lintels above openings ---
    if lintels:
        for oa, ob, k0, k1 in openings:
            if k1 < n_at((oa + ob) / 2):
                t = BRICK_W / 2 + 0.5
                put(oa - 8, ob + 8, -t, t, zb + k1 * COURSE, zb + (k1 + 1) * COURSE, M_CONCRETE)


def columns(mb, positions, z0, z1):
    for x, y in positions:
        mb.cbox(x, y, z0, COL, COL, z1 - z0, M_CONCRETE)


COLUMN_POS = [(x, y) for x in (XL, -XM, XM, XR) for y in (YF, YB)] + [(XL, YM), (XR, YM)]


# ---------------------------------------------------------------------------
# PARTS
# ---------------------------------------------------------------------------
def build_ground_floor(col):
    mb = MB()
    mb.box(HOUSE_X0, HOUSE_X1, HOUSE_Y0, HOUSE_Y1, 0, FLOOR_PLATE, M_CONCRETE)
    zb, n = Z_GF, GF_COURSES
    # front: window | door | window
    wall(mb, 'x', YF, XL, XR, zb, n, openings=[(-100, -64, 7, 15), (-20, 18, 0, 16), (62, 98, 7, 15)])
    wall(mb, 'x', YB, XL, XR, zb, n, openings=[(-20, 16, 7, 15)])
    wall(mb, 'y', XL, YF, YB, zb, n, openings=[(60, 96, 7, 15)])
    wall(mb, 'y', XR, YF, YB, zb, n, openings=[(60, 96, 7, 15)])
    # interior partition with doorway
    wall(mb, 'y', -XM, YF, YB, zb, n, openings=[(60, 90, 0, 16)])
    columns(mb, COLUMN_POS, 0, Z_GF_TOP)
    return mb.build("GroundFloor", col)


def build_first_floor(col):
    mb = MB()
    # slab 1 (prints flat on the bed, walls grow up from it)
    mb.box(HOUSE_X0 - 1, HOUSE_X1 + 1, HOUSE_Y0 - 1, HOUSE_Y1 + 1, Z_GF_TOP, Z_SLAB1_TOP, M_CONCRETE)
    zb, n = Z_SLAB1_TOP, FF_COURSES
    # front wall – right part is unfinished (stepped toothing)
    wall(mb, 'x', YF, XL, XR, zb, n,
         segments=[(XL, 40, n), (40, 58, 14), (58, 76, 12), (76, XR, 10)],
         openings=[(-100, -64, 6, 14), (-20, 18, 0, 16)])
    wall(mb, 'x', YB, XL, XR, zb, n, openings=[(-20, 16, 6, 14)])
    wall(mb, 'y', XL, YF, YB, zb, n, openings=[(60, 96, 6, 14)])
    # right wall – unfinished towards the front
    wall(mb, 'y', XR, YF, YB, zb, n,
         segments=[(YF, 0, 10), (0, 18, 12), (18, 36, 14), (36, YB, n)])
    columns(mb, COLUMN_POS, Z_GF_TOP, Z_FF_TOP)

    # concrete stairs up to the formwork (11 risers)
    steps, y0, tread = 11, -5.0, 10.5
    rise = (Z_FF_TOP - Z_SLAB1_TOP) / steps
    x0, x1 = 70.0, XR - BRICK_W / 2 + 0.5
    poly = [(y0, zb)]
    for i in range(steps):
        poly += [(y0 + i * tread, zb + (i + 1) * rise), (y0 + (i + 1) * tread, zb + (i + 1) * rise)]
    if STAIRS_SOLID:
        poly += [(y0 + steps * tread, zb)]
    else:
        waist = 12.0
        poly += [(y0 + steps * tread, Z_FF_TOP - waist - rise), (y0 + tread, zb)]
    mb.extrude_x(poly, x0, x1, M_CONCRETE)
    return mb.build("FirstFloor", col)


def build_roof(col):
    mb = MB()
    zb = Z_FF_TOP
    # roof slab only over the left / middle part
    mb.box(HOUSE_X0 - 1, ROOF_X1, HOUSE_Y0 - 1, HOUSE_Y1 + 1, zb, Z_ROOF_TOP, M_CONCRETE)
    # parapet (unfinished, stepped)
    pz = Z_ROOF_TOP
    wall(mb, 'x', YF, XL, 4, pz, PARAPET_COURSES,
         segments=[(XL, -50, 4), (-50, -32, 3), (-32, -14, 2), (-14, 4, 1)], lintels=False)
    wall(mb, 'x', YB, XL, 40, pz, PARAPET_COURSES, lintels=False)
    wall(mb, 'y', XL, YF, YB, pz, PARAPET_COURSES, lintels=False)

    # timber formwork over the stair opening (bottom flush with slab bottom)
    fx0, fx1, fy0, fy1 = ROOF_X1 - 1, XR + 5, 30.0, HOUSE_Y1
    for y in (fy0, 54, 78, 102, fy1 - 5):
        mb.box(fx0, fx1, y, y + 5, zb, zb + 6, M_WOOD)            # joists along X
    for x in (fx0 + 1, fx1 - 6):
        mb.box(x, x + 5, fy0, fy1, zb, zb + 6, M_WOOD)            # edge bearers along Y
    for x, y in ((fx0 + 1, fy0), (fx1 - 5, fy0), (fx0 + 1, fy1 - 5),
                 (fx1 - 5, fy1 - 5), (fx1 - 5, 78)):
        mb.box(x, x + 4, y, y + 4, zb, zb + 32, M_WOOD)           # standing posts
    return mb.build("Roof", col)


# ---------------------------------------------------------------------------
# PROPS (each one printed separately)
# ---------------------------------------------------------------------------
def place(ob, x, y, rz_deg=0.0, rx_deg=0.0):
    ob.location = (x, y, 0)
    ob.rotation_euler = (math.radians(rx_deg), 0, math.radians(rz_deg))


def build_wheelbarrow(col):
    """طول 9.5 سم، عرض 4.2 سم، ارتفاع 4 سم، قطر العجلة 2.5 سم"""
    mb = MB()
    R = 12.5                                        # wheel radius
    rot_y = Matrix.Rotation(math.radians(90), 4, 'X')  # lathe axis Z -> Y
    # tyre + hub
    mb.lathe([(5, -3), (R - 1, -3), (R, -1.5), (R, 1.5), (R - 1, 3), (5, 3)], M_RUBBER, 32,
             Matrix.Translation((0, 0, R)) @ rot_y)
    mb.lathe([(0, -4.5), (5.5, -4.5), (5.5, 4.5), (0, 4.5)], M_METAL, 16,
             Matrix.Translation((0, 0, R)) @ rot_y)
    # tray: hollow tapered pan, rim 40 mm above ground
    cx, top, depth, wt = -30.0, 40.0, 16.0, 1.6
    tl, tw, bl, bw = 62.0, 42.0, 40.0, 26.0
    def rect(l, w, z, dx=0.0):
        return [(cx + dx - l / 2, -w / 2, z), (cx + dx + l / 2, -w / 2, z),
                (cx + dx + l / 2, w / 2, z), (cx + dx - l / 2, w / 2, z)]
    ob_, ot = rect(bl, bw, top - depth, 4), rect(tl, tw, top)
    it, ib = rect(tl - 2 * wt, tw - 2 * wt, top), rect(bl - 2 * wt, bw - 2 * wt, top - depth + wt, 4)
    v = ob_ + ot + it + ib
    f = [(0, 1, 2, 3), (12, 13, 14, 15)]
    for i in range(4):
        j = (i + 1) % 4
        f += [(i, j, 4 + j, 4 + i), (4 + i, 4 + j, 8 + j, 8 + i), (8 + i, 8 + j, 12 + j, 12 + i)]
    mb.add(v, f, M_METAL)
    # frame / handles (2.5 mm square tube)
    s = 2.5
    for sy in (-1, 1):
        a = (2, sy * 5.5, R)
        b = (-82, sy * 15, 33)
        mb.bar(a, b, s, M_METAL)
        def on_bar(x):
            t = (a[0] - x) / (a[0] - b[0])
            return (x, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)
        p = on_bar(-50)
        mb.bar((p[0], p[1], 0), (p[0], p[1], p[2] + 1), s, M_METAL)            # leg
        mb.bar((p[0] - 4, p[1], 0.6), (p[0] + 4, p[1], 0.6), s, M_METAL)        # foot
        for x in (-14, -40):
            q = on_bar(x)
            mb.bar((q[0], q[1], q[2] - 1), (q[0], q[1], top - depth + 1), s, M_METAL)  # struts
        mb.bar(on_bar(-82), (-86, b[1], 33), 3.2, M_RUBBER)                      # grip
    mb.bar((0, -6.5, R), (0, 6.5, R), 2.8, M_METAL)                              # axle
    ob = mb.build("Wheelbarrow", col)
    place(ob, -50, -115, -30)
    return ob


def build_cement_pallet(col):
    """كيس سمنت 5 × 3 × 1 سم فوق بالِت خشبي"""
    mb = MB()
    PL, PW = 52.0, 64.0
    for x in (-22, 0, 22):
        mb.box(x - 3, x + 3, -PW / 2, PW / 2, 0, 5, M_WOOD)
    for i in range(5):
        y = -PW / 2 + 1 + i * (PW - 12) / 4
        mb.box(-PL / 2, PL / 2, y, y + 10, 4.8, 8, M_WOOD)

    def bag(cx, cy, z, rz=0.0, L=50.0, W=30.0, T=10.0, c=2.0):
        pts = []
        for sx in (-1, 1):
            for sy in (-1, 1):
                for sz in (0, 1):
                    x, y, zz = sx * L / 2, sy * W / 2, z + sz * T
                    pts += [(x - sx * c, y, zz - (sz * 2 - 1) * c * 0.6),
                            (x, y - sy * c, zz - (sz * 2 - 1) * c * 0.6),
                            (x - sx * c, y - sy * c, zz)]
        mat = Matrix.Translation((cx, cy, 0)) @ Matrix.Rotation(math.radians(rz), 4, 'Z')
        mb.hull(pts, M_BAG, mat)

    z = 7.8
    for layer, rot in ((0, 0), (1, 3)):
        for y in (-15.5, 15.5):
            bag(0, y, z + layer * 9.7, rot)
    bag(0, 0, z + 2 * 9.7, 88, L=50, W=30)
    ob = mb.build("CementBags_Pallet", col)
    place(ob, 90, -85)
    return ob


def build_mortar_board(col):
    """طبلية السمنت 7.8 × 6.5 × 1 سم مع كومة سمنت"""
    mb = MB()
    L, W = 78.0, 65.0
    for y in (-W / 2 + 4, 0, W / 2 - 10):
        mb.box(-L / 2 + 3, L / 2 - 3, y, y + 6, 0, 4, M_WOOD)        # battens
    mb.box(-L / 2, L / 2, -W / 2, W / 2, 3.8, 10, M_BOARD)           # top board
    mb.lathe([(0, 9.8), (23, 9.8), (20, 12.5), (13, 16), (6, 17.8), (0, 18.3)], M_SAND, 40,
             Matrix.Translation((3, 2, 0)))
    ob = mb.build("MortarBoard", col)
    place(ob, 20, -130, 12)
    return ob


def build_shovel(col):
    """الكرك: الطول الكلي 7.8 سم، النصل 2.4 × 1.5 سم، اليد 5.4 سم"""
    mb = MB()
    t = 1.6
    blade = [(-7.5, 24), (7.5, 24), (7.5, 9), (0, 0.6), (-7.5, 9)]
    pts = [(x, y, z) for x, z in blade for y in (-t / 2, t / 2)]
    mb.hull(pts, M_METAL)
    mb.bar((0, 0, 20), (0, 0, 30), 3.4, M_METAL)                    # socket
    mb.lathe([(0, 24), (1.4, 24), (1.4, 72), (0, 72)], M_WOOD, 10)  # shaft d=2.8
    mb.bar((0, 0, 71), (-4.5, 0, 76), 2.2, M_WOOD)                  # D-grip
    mb.bar((0, 0, 71), (4.5, 0, 76), 2.2, M_WOOD)
    mb.bar((-5.5, 0, 76.4), (5.5, 0, 76.4), 2.4, M_WOOD)
    ob = mb.build("Shovel", col)
    place(ob, 55, -60, 0, -12)
    return ob


def build_bucket(col):
    """السطل: ارتفاع 2 سم، الفوهة 2.2 سم، القاعدة 1.5 سم"""
    mb = MB()
    h, rt, rb, w = 20.0, 11.0, 7.5, 1.2
    mb.lathe([(0, 0), (rb, 0), (rt, h), (rt - w, h), (rb - w * 0.9, w), (0, w)], M_METAL, 40)
    mb.lathe([(rt - 0.6, h - 1.2), (rt + 0.5, h - 1.2), (rt + 0.5, h - 0.2), (rt - 0.6, h - 0.2)], M_METAL, 40)
    pts = []
    for i in range(11):
        a = math.pi * i / 10
        pts.append((-(rt + 0.1) * math.cos(a), 0, h - 4.5 + 11 * math.sin(a)))
    for p, q in zip(pts, pts[1:]):
        mb.bar(p, q, 1.4, M_METAL)                                   # handle
    ob = mb.build("Bucket", col)
    place(ob, 80, -145, 20)
    return ob


def build_loose_bricks(col):
    mb = MB()

    def brick(x, y, z, rz):
        m = Matrix.Translation((x, y, z)) @ Matrix.Rotation(math.radians(rz), 4, 'Z')
        mb.box(-BRICK_L / 2, BRICK_L / 2, -BRICK_W / 2, BRICK_W / 2, 0, BRICK_H, M_BRICK, m)

    # neat stack at the right (cross-laid, 4 layers)
    sx, sy = 160.0, -120.0
    for layer in range(4):
        z = layer * BRICK_H
        for i in range(3):
            if layer % 2 == 0:
                brick(sx, sy - BRICK_W * 1.05 + i * BRICK_W * 1.05, z, 0)
            else:
                brick(sx - BRICK_W * 1.05 + i * BRICK_W * 1.05, sy, z, 90)
    # scattered bricks in the yard
    for x, y, rz in ((-20, -160, 15), (-2, -166, -20), (-35, -150, 70), (190, -150, 35),
                     (178, -95, -10), (-110, -140, 50)):
        brick(x, y, 0, rz)
    brick(-10, -162, BRICK_H - 0.3, 40)
    ob = mb.build("LooseBricks", col)
    return ob


def build_sand_pile(col):
    mb = MB()
    mb.lathe([(0, 0), (24, 0), (20, 2.5), (13, 7), (6, 10.5), (0, 12)], M_SAND, 40)
    ob = mb.build("SandPile", col)
    ob.scale = (1.0, 0.8, 1.0)
    place(ob, 25, -76, 25)
    return ob


def build_base(col):
    objs = []
    x0, x1, y0, y1 = -BASE_W / 2, BASE_W / 2, -BASE_D / 2, BASE_D / 2
    tiles = [(x0, 0, y0, 0), (0, x1, y0, 0), (x0, 0, 0, y1), (0, x1, 0, y1)] if SPLIT_BASE \
        else [(x0, x1, y0, y1)]
    for i, (a, b, c, d) in enumerate(tiles):
        mb = MB()
        mb.box(a, b, c, d, -BASE_T, 0, M_BOARD)
        objs.append(mb.build(f"Base_{i + 1}" if SPLIT_BASE else "Base", col))
    return objs


# ---------------------------------------------------------------------------
# scene helpers
# ---------------------------------------------------------------------------
def reset_scene():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for coll in list(bpy.data.collections):
        bpy.data.collections.remove(coll)
    for me in list(bpy.data.meshes):
        bpy.data.meshes.remove(me)
    sc = bpy.context.scene
    sc.unit_settings.system = 'METRIC'
    sc.unit_settings.scale_length = 0.001
    sc.unit_settings.length_unit = 'MILLIMETERS'
    for area in getattr(bpy.context.screen, "areas", []) if bpy.context.screen else []:
        if area.type == 'VIEW_3D':
            for sp in area.spaces:
                if sp.type == 'VIEW_3D':
                    sp.clip_start, sp.clip_end = 0.5, 20000
                    sp.overlay.grid_scale = 0.001


def make_materials():
    for name, color, rough in MATERIALS:
        mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        mat.diffuse_color = color
        if hasattr(mat, "node_tree") and mat.node_tree is None:
            mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = color
            bsdf.inputs["Roughness"].default_value = rough
            if name == "Metal":
                bsdf.inputs["Metallic"].default_value = 0.6


def new_collection(name):
    coll = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(coll)
    return coll


def union_self(ob):
    """merge all overlapping shells of an object into one closed manifold mesh"""
    me = bpy.data.meshes.new("tiny")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=0.05)
    bm.to_mesh(me)
    bm.free()
    cutter = bpy.data.objects.new("tiny", me)
    bpy.context.scene.collection.objects.link(cutter)
    # put the tiny cube inside the first vertex area of the object (fully inside a shell)
    v = [ob.data.vertices[i].co for i in range(8)]
    cutter.location = ob.matrix_world @ (sum(v, Vector()) / 8)
    md = ob.modifiers.new("Union", 'BOOLEAN')
    md.operation, md.object, md.solver = 'UNION', cutter, 'EXACT'
    md.use_self = True
    dg = bpy.context.evaluated_depsgraph_get()
    new_me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    ob.modifiers.remove(md)
    old = ob.data
    ob.data = new_me
    bpy.data.meshes.remove(old)
    bpy.data.objects.remove(cutter, do_unlink=True)
    bpy.data.meshes.remove(me)


def write_stl(ob, path):
    dg = bpy.context.evaluated_depsgraph_get()
    eo = ob.evaluated_get(dg)
    me = eo.to_mesh()
    me.transform(ob.matrix_world)
    me.calc_loop_triangles()
    tris = me.loop_triangles
    with open(path, "wb") as fh:
        fh.write(b"construction house diorama - units: mm".ljust(80, b" "))
        fh.write(struct.pack("<I", len(tris)))
        verts = me.vertices
        for t in tris:
            fh.write(struct.pack("<3f", *t.normal))
            for vi in t.vertices:
                fh.write(struct.pack("<3f", *verts[vi].co))
            fh.write(b"\x00\x00")
    eo.to_mesh_clear()
    return len(tris)


def setup_render(path):
    sc = bpy.context.scene
    cam_data = bpy.data.cameras.new("Camera")
    cam_data.lens = 50
    cam_data.clip_start, cam_data.clip_end = 1, 10000
    cam = bpy.data.objects.new("Camera", cam_data)
    sc.collection.objects.link(cam)
    cam.location = (470, -690, 520)
    cam.rotation_euler = (Vector((0, -10, 105)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
    sc.camera = cam
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", 'SUN'))
    sun.data.energy = 3.5
    sun.data.angle = math.radians(8)
    sun.rotation_euler = (math.radians(50), math.radians(10), math.radians(-35))
    sc.collection.objects.link(sun)
    fill = bpy.data.objects.new("Fill", bpy.data.lights.new("Fill", 'AREA'))
    fill.data.energy = 1.5e6
    fill.data.size = 600
    fill.location = (-600, -500, 700)
    fill.rotation_euler = (Vector((0, 0, 0)) - fill.location).to_track_quat('-Z', 'Y').to_euler()
    sc.collection.objects.link(fill)
    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    sc.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.42, 0.40, 0.37, 1)
        bg.inputs[1].default_value = 0.6
    sc.render.engine = 'CYCLES'
    sc.cycles.samples = 64
    sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = 1400, 1000
    sc.render.film_transparent = False
    if path:
        sc.render.filepath = path
        bpy.ops.render.render(write_still=True)


# ---------------------------------------------------------------------------
def main(out_dir=None, render_path=None, do_union=UNION_PARTS):
    t0 = time.time()
    reset_scene()
    make_materials()

    c_base = new_collection("00_Base")
    c_house = new_collection("01_House")
    c_props = new_collection("02_Props")

    parts = []
    parts += build_base(c_base)
    parts += [build_ground_floor(c_house), build_first_floor(c_house), build_roof(c_house)]
    parts += [build_wheelbarrow(c_props), build_cement_pallet(c_props), build_mortar_board(c_props),
              build_shovel(c_props), build_bucket(c_props), build_loose_bricks(c_props),
              build_sand_pile(c_props)]
    print(f"[house] geometry built in {time.time() - t0:.1f}s")

    if do_union:
        for ob in parts:
            if ob.name.startswith("Base"):
                continue
            t = time.time()
            union_self(ob)
            print(f"[house] union {ob.name}: {len(ob.data.polygons)} faces, {time.time() - t:.1f}s")

    if out_dir:
        stl_dir = os.path.join(out_dir, "stl")
        os.makedirs(stl_dir, exist_ok=True)
        for i, ob in enumerate(parts):
            n = write_stl(ob, os.path.join(stl_dir, f"{i + 1:02d}_{ob.name}.stl"))
            print(f"[house] STL {ob.name}: {n} triangles")
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(os.path.join(out_dir, "construction_house.blend")))

    if render_path:
        setup_render(os.path.abspath(render_path))
    print(f"[house] done in {time.time() - t0:.1f}s")


def _cli_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out, render, union = None, None, UNION_PARTS
    i = 0
    while i < len(argv):
        if argv[i] == "--out":
            out = argv[i + 1]; i += 1
        elif argv[i] == "--render":
            render = argv[i + 1]; i += 1
        elif argv[i] == "--no-union":
            union = False
        i += 1
    return out, render, union


if __name__ == "__main__":
    _out, _render, _union = _cli_args()
    main(_out, _render, _union)
