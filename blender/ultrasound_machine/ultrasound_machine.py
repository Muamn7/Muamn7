# -*- coding: utf-8 -*-
"""
Ultrasound cart (iE33-style) - procedural Blender model for 3D printing.
جهاز سونار (ألتراساوند) - نموذج بلندر جاهز للطباعة ثلاثية الأبعاد.

HOW TO USE / طريقة الاستخدام:
  1. Blender -> Scripting tab -> Open this file -> Run Script (Alt+P)
     بلندر -> تبويب Scripting -> افتح الملف -> Run Script
  2. The model is built in millimetres (1 Blender unit = 1 mm).
     الوحدات بالمليمتر: كل وحدة = 1 مم.
  3. STL files are written next to the .blend file (or ~/ultrasound_export).
     ملفات STL تُحفظ بجانب ملف .blend أو في مجلد ultrasound_export.

Tested with Blender 4.2 (written to also run on 3.6+ and 4.x).
"""

import bpy
import bmesh
import math
import os
import struct
from mathutils import Vector, Matrix

# ---------------------------------------------------------------------------
# SETTINGS / الإعدادات
# ---------------------------------------------------------------------------
TARGET_HEIGHT = 400.0      # total height in mm (الطول الكلي بالمليمتر)
WITH_CABLES = True         # probe cables (كابلات المجسات) - 3 mm thick
WITH_LOGO_TEXT = True      # raised text on the monitor bezel (النص على الشاشة)
LOGO_TEXT = "PHILIPS"
FLAT_WHEELS = True         # flatten wheel bottoms for bed adhesion (تسطيح العجلات)
PRINT_BASE = False         # add a 3 mm display base under the wheels (قاعدة عرض)
MAKE_SOLID_UNION = True    # boolean-union everything into ONE watertight shell
EXPORT_STL = True
RENDER_PREVIEW = False     # set True to render preview PNGs (Cycles, CPU)

OUT_DIR = os.environ.get("ULTRASOUND_OUT", "")

# ---------------------------------------------------------------------------
# Basic helpers
# ---------------------------------------------------------------------------
COL = None
MATS = {}


def clear_scene():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.curves, bpy.data.materials,
                 bpy.data.cameras, bpy.data.lights):
        for d in list(coll):
            coll.remove(d)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)


def setup_scene():
    global COL
    sc = bpy.context.scene
    us = sc.unit_settings
    us.system = 'METRIC'
    us.scale_length = 0.001
    us.length_unit = 'MILLIMETERS'
    COL = bpy.data.collections.new("Ultrasound_Parts")
    sc.collection.children.link(COL)


def make_mat(name, rgb, rough=0.45, metal=0.0):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*rgb, 1.0)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
        bsdf.inputs["Roughness"].default_value = rough
        bsdf.inputs["Metallic"].default_value = metal
    MATS[name] = m
    return m


def init_materials():
    make_mat("Cream_Body",   (0.80, 0.78, 0.72), 0.40)   # الأبيض الكريمي
    make_mat("Light_Grey",   (0.55, 0.56, 0.57), 0.45)   # رمادي فاتح
    make_mat("Dark_Grey",    (0.16, 0.17, 0.18), 0.55)   # رمادي غامق
    make_mat("Tan_Handle",   (0.78, 0.60, 0.40), 0.40)   # المقبض البيج
    make_mat("Screen_Black", (0.01, 0.01, 0.012), 0.15)  # الشاشة
    make_mat("Trackball",    (0.85, 0.62, 0.10), 0.20)   # كرة التتبع
    make_mat("Monitor_White", (0.88, 0.88, 0.86), 0.35)  # إطار الشاشة


def link(obj):
    COL.objects.link(obj)
    return obj


def set_mat(obj, mat_name):
    if mat_name:
        obj.data.materials.clear()
        obj.data.materials.append(MATS[mat_name])


def shade(obj, smooth=True, angle=35.0):
    me = obj.data
    me.polygons.foreach_set("use_smooth", [smooth] * len(me.polygons))
    if not smooth:
        return
    if hasattr(me, "set_sharpness_by_angle"):          # Blender 4.1+
        me.set_sharpness_by_angle(angle=math.radians(angle))
    elif hasattr(me, "use_auto_smooth"):                # Blender <= 4.0
        me.use_auto_smooth = True
        me.auto_smooth_angle = math.radians(angle)
    me.update()


def apply_mods(obj):
    """Apply all modifiers without bpy.ops (works headless)."""
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    new_me = bpy.data.meshes.new_from_object(ev)
    old = obj.data
    obj.modifiers.clear()
    obj.data = new_me
    new_me.name = obj.name
    if old.users == 0:
        bpy.data.meshes.remove(old)


def bake_transform(obj):
    # matrix_basis is computed immediately from loc/rot/scale
    # (matrix_world is only refreshed after a depsgraph update)
    obj.data.transform(obj.matrix_basis.copy())
    obj.matrix_basis = Matrix.Identity(4)
    obj.data.update()


def mesh_obj(name, bm, mat=None):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = link(bpy.data.objects.new(name, me))
    set_mat(obj, mat)
    return obj


# ---------------------------------------------------------------------------
# Primitive builders (all sizes in mm)
# ---------------------------------------------------------------------------
def rbox(name, center, size, bevel=2.0, segs=4, mat="Cream_Body", rot=None):
    """Rounded box. size = full (x, y, z) dimensions."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    obj = mesh_obj(name, bm, mat)
    b = min(bevel, min(size) * 0.5 - 0.02)
    if b > 0.05:
        m = obj.modifiers.new("Bevel", 'BEVEL')
        m.width = b
        m.segments = segs
        m.limit_method = 'NONE'
        apply_mods(obj)
    if rot:
        obj.rotation_euler = rot
    obj.location = center
    bake_transform(obj)
    shade(obj)
    return obj


def cyl(name, center, r, h, axis='Z', segs=48, r2=None, mat="Light_Grey",
        sx=1.0, sy=1.0):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segs,
                          radius1=r, radius2=(r if r2 is None else r2), depth=h)
    if sx != 1.0 or sy != 1.0:
        bmesh.ops.scale(bm, vec=(sx, sy, 1.0), verts=bm.verts)
    if axis == 'X':
        bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 2, 3, 'Y'), verts=bm.verts)
    elif axis == 'Y':
        bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 2, 3, 'X'), verts=bm.verts)
    bmesh.ops.translate(bm, vec=Vector(center), verts=bm.verts)
    obj = mesh_obj(name, bm, mat)
    shade(obj, angle=40)
    return obj


def cyl_between(name, p1, p2, r, segs=40, mat="Light_Grey"):
    p1, p2 = Vector(p1), Vector(p2)
    d = p2 - p1
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segs,
                          radius1=r, radius2=r, depth=d.length)
    q = Vector((0, 0, 1)).rotation_difference(d.normalized())
    bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=q.to_matrix(), verts=bm.verts)
    bmesh.ops.translate(bm, vec=(p1 + p2) * 0.5, verts=bm.verts)
    obj = mesh_obj(name, bm, mat)
    shade(obj, angle=40)
    return obj


def sphere(name, center, r, mat="Light_Grey", segs=32, sz=1.0):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=segs // 2, radius=r)
    if sz != 1.0:
        bmesh.ops.scale(bm, vec=(1, 1, sz), verts=bm.verts)
    bmesh.ops.translate(bm, vec=Vector(center), verts=bm.verts)
    obj = mesh_obj(name, bm, mat)
    shade(obj, angle=80)
    return obj


def cut(target, cutter):
    """Boolean difference, cutter is deleted."""
    m = target.modifiers.new("Cut", 'BOOLEAN')
    m.operation = 'DIFFERENCE'
    m.object = cutter
    if hasattr(m, "solver"):
        m.solver = 'EXACT'
    cutter.hide_render = True
    apply_mods(target)
    bpy.data.objects.remove(cutter, do_unlink=True)
    shade(target)
    return target


def catmull_rom(pts, steps=10):
    pts = [Vector(p) for p in pts]
    ext = [pts[0] + (pts[0] - pts[1])] + pts + [pts[-1] + (pts[-1] - pts[-2])]
    out = []
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        for s in range(steps):
            t = s / steps
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t +
                              (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 +
                              (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    out.append(pts[-1])
    return out


def curve_to_mesh(curve_obj, name, mat):
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(curve_obj.evaluated_get(dg))
    me.name = name
    obj = link(bpy.data.objects.new(name, me))
    obj.matrix_basis = curve_obj.matrix_basis.copy()
    data = curve_obj.data
    bpy.data.objects.remove(curve_obj, do_unlink=True)
    bpy.data.curves.remove(data)
    bake_transform(obj)
    # merge duplicate verts produced by the curve sweep
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.001)
    bm.to_mesh(obj.data)
    bm.free()
    set_mat(obj, mat)
    shade(obj, angle=60)
    return obj


def tube(name, pts, r, mat="Light_Grey", closed=False, smooth_steps=10):
    cu = bpy.data.curves.new(name + "_curve", 'CURVE')
    cu.dimensions = '3D'
    cu.bevel_depth = r
    cu.bevel_resolution = 4
    cu.use_fill_caps = True
    sp = cu.splines.new('POLY')
    if closed:
        pts = list(pts)
        sm = catmull_rom(pts + pts[:3], smooth_steps)
        n = len(pts)
        sm = sm[smooth_steps: smooth_steps * (n + 1)]
    else:
        sm = catmull_rom(pts, smooth_steps)
    sp.points.add(len(sm) - 1)
    for p, co in zip(sp.points, sm):
        p.co = (co.x, co.y, co.z, 1.0)
    sp.use_cyclic_u = closed
    cobj = link(bpy.data.objects.new(name + "_curve", cu))
    return curve_to_mesh(cobj, name, mat)


def rounded_rect_path(x0, x1, y0, y1, z, r, n=8):
    """Closed rounded rectangle in the XY plane (corner points)."""
    pts = []
    corners = [(x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90),
               (x0 + r, y0 + r, 180), (x1 - r, y0 + r, 270)]
    for cx, cy, a0 in corners:
        for i in range(n + 1):
            a = math.radians(a0 + 90.0 * i / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a), z))
    return pts


def text_obj(name, body, loc, size, depth, mat):
    cu = bpy.data.curves.new(name + "_txt", 'FONT')
    cu.body = body
    cu.size = size
    cu.extrude = depth
    cu.align_x = 'CENTER'
    cu.align_y = 'CENTER'
    cu.space_character = 1.15
    t = link(bpy.data.objects.new(name + "_txt", cu))
    t.rotation_euler = (math.pi / 2, 0, 0)      # face the operator (-Y)
    t.location = loc
    return curve_to_mesh(t, name, mat)


def prism(name, profile, x0, x1, bevel=3.0, segs=4, mat="Cream_Body", angle=30.0):
    """Extrude a side profile [(y, z), ...] along X from x0 to x1, then round
    the sharp outline edges (gives sculpted, non-boxy shapes)."""
    bm = bmesh.new()
    left = [bm.verts.new((x0, y, z)) for y, z in profile]
    right = [bm.verts.new((x1, y, z)) for y, z in profile]
    bm.faces.new(left)
    bm.faces.new(list(reversed(right)))
    n = len(profile)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((left[i], left[j], right[j], right[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    obj = mesh_obj(name, bm, mat)
    if bevel > 0:
        m = obj.modifiers.new("Bevel", 'BEVEL')
        m.width = bevel
        m.segments = segs
        m.limit_method = 'ANGLE'
        m.angle_limit = math.radians(angle)
        apply_mods(obj)
    shade(obj, angle=40)
    return obj


def arc(cy, cz, r, a0, a1, n=10):
    """Points on an arc in the YZ plane (angles in degrees, 0 = +Y, 90 = +Z)."""
    return [(cy + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cz + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def stadium(a, b, r, n=10):
    """Rounded slot outline in the YZ plane between centres a and b."""
    a, b = Vector(a), Vector(b)
    d = (b - a).normalized()
    ang = math.degrees(math.atan2(d.y, d.x))
    pts = arc(b.x, b.y, r, ang - 90, ang + 90, n) + arc(a.x, a.y, r, ang + 90, ang + 270, n)
    return pts


def transform_objs(objs, M):
    for o in objs:
        o.data.transform(M)
        o.data.update()


# ---------------------------------------------------------------------------
# MODEL  (front / operator side = -Y,  up = +Z,  units = mm,  height ~ 400)
# ---------------------------------------------------------------------------
def build_caster(tag, x, y):
    """Twin-wheel caster like the photo (dark tyres, grey hub, grey fork)."""
    parts = []
    R = 14.0
    wheel_r = R + 0.6 if FLAT_WHEELS else R
    for side in (-1, 1):
        parts.append(cyl(f"Caster_{tag}_Wheel{side}", (x + side * 4.2, y, R), wheel_r, 6.0,
                         axis='X', segs=56, mat="Dark_Grey"))
        parts.append(cyl(f"Caster_{tag}_HubCap{side}", (x + side * 7.4, y, R), 6.5, 0.8,
                         axis='X', segs=40, mat="Light_Grey"))
    parts.append(cyl(f"Caster_{tag}_Axle", (x, y, R), 3.0, 16.0, axis='X', segs=24, mat="Light_Grey"))
    parts.append(rbox(f"Caster_{tag}_Fork", (x, y + 3, 27), (12.0, 22.0, 14.0), bevel=4.0, mat="Light_Grey"))
    parts.append(cyl(f"Caster_{tag}_Swivel", (x, y + 3, 35), 6.5, 6.0, mat="Dark_Grey"))
    return parts


def build_base():
    parts = []
    # grey plinth (القاعدة الرمادية)
    base = rbox("Base_Plinth", (0, 15, 51), (146, 170, 42), bevel=8, mat="Light_Grey")
    # vents at the rear of both sides - فتحات التهوية
    for sx in (-1, 1):
        for i in range(7):
            cut(base, rbox("cut", (sx * 73.5, 64, 37 + i * 4.0), (4.0, 44, 2.0), bevel=0.6))
    parts.append(base)
    # two chunky front feet (الأرجل الأمامية) - side profile extruded across X
    foot = [(-66, 31), (-66, 66)] + arc(-112, 52, 14, 90, 30, 6) + [(-140, 44), (-142, 36), (-138, 31)]
    for s, (x0, x1) in (("L", (-72, -30)), ("R", (30, 72))):
        parts.append(prism(f"Base_Foot_{s}", foot, x0, x1, bevel=5, mat="Light_Grey"))
    # low step between the feet + grey skirt under the bin
    parts.append(rbox("Base_Step", (0, -97, 31), (62, 70, 14), bevel=4, mat="Light_Grey"))
    parts.append(rbox("Base_Skirt", (0, -78, 47), (62, 30, 22), bevel=4, mat="Light_Grey"))
    for tag, x, y in (("FL", -51, -124), ("FR", 51, -124), ("RL", -56, 80), ("RR", 56, 80)):
        parts += build_caster(tag, x, y)
    return parts


def build_body():
    parts = []
    # main cream body - side profile (y, z); its front is hidden by the cover
    body_prof = [(-82, 54), (98, 54), (98, 188), (-5, 185), (-22, 174), (-42, 152), (-62, 140), (-82, 120)]
    body = prism("Body_Main", body_prof, -68, 68, bevel=9, mat="Cream_Body")
    parts.append(body)

    # sculpted front cover - the rear edge is the S-shaped seam seen on the side
    seam = [(-80, 106), (-64, 108), (-50, 114), (-38, 125), (-28, 141), (-20, 159), (-13, 175)]
    cover_prof = ([(-4, 188), (-20, 179), (-40, 159)] + arc(-62, 128, 22, 80, 175, 10)
                  + [(-85, 120), (-86, 109)] + seam)
    parts.append(prism("Body_FrontCover", cover_prof, -71.5, 71.5, bevel=5, mat="Cream_Body"))

    # low front bin across the whole front (open top) - الحاوية الأمامية
    bin_prof = [(-62, 56), (-62, 104), (-99, 104), (-101, 97), (-100, 66), (-95, 57), (-86, 56)]
    bin_ = prism("Body_Bin", bin_prof, -66, 66, bevel=4, mat="Cream_Body")
    cut(bin_, rbox("cut", (0, -87.5, 96), (122, 15, 40), bevel=3))
    parts.append(bin_)
    parts.append(rbox("Body_BinSlot", (0, -100.4, 80), (5.5, 2.2, 12), bevel=1.0, mat="Dark_Grey"))

    # tilted speaker grille on the left side, on the cover seam - شبكة السماعة
    grille = prism("Body_Speaker", stadium((-30, 134), (-6, 182), 6.0), -73.0, -66.0,
                   bevel=0.6, mat="Dark_Grey")
    holes = bmesh.new()
    a, b = Vector((-30, 134)), Vector((-6, 182))
    u = (b - a).normalized()
    v = Vector((-u.y, u.x))
    L = (b - a).length
    t = -3.0
    while t <= L + 3.0:
        for k in (-2, -1, 0, 1, 2):
            c = a + u * t + v * (k * 1.9 + (0.95 if int(t / 2.0) % 2 else 0.0))
            if (c - a).dot(v) ** 2 > 4.4 ** 2:
                continue
            nearest = a + u * max(0.0, min(L, (c - a).dot(u)))
            if (c - nearest).length > 4.4:
                continue
            r = bmesh.ops.create_cone(holes, cap_ends=True, cap_tris=False, segments=10,
                                      radius1=0.55, radius2=0.55, depth=1.6)
            vs = r["verts"]
            bmesh.ops.rotate(holes, cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 2, 3, 'Y'), verts=vs)
            bmesh.ops.translate(holes, vec=(-73.0, c.x, c.y), verts=vs)
        t += 2.0
    cut(grille, mesh_obj("cut", holes))
    parts.append(grille)

    # grey shoulder band
    parts.append(rbox("Body_Shoulder", (0, 34, 188), (136, 124, 6), bevel=2.5, mat="Light_Grey"))
    # rear tower (holds printer + probe holders) - البرج الخلفي
    parts.append(rbox("Tower", (0, 62, 207), (140, 76, 66), bevel=9, mat="Cream_Body"))
    parts.append(rbox("Tower_Cap", (0, 62, 241), (130, 70, 6), bevel=2.5, mat="Light_Grey"))
    parts.append(rbox("Tower_PrinterBay", (-70.6, 62, 214), (2.0, 34, 20), bevel=0.8, mat="Dark_Grey"))
    parts.append(rbox("Tower_PrinterBay_R", (70.6, 62, 214), (2.0, 34, 20), bevel=0.8, mat="Dark_Grey"))
    # rear handle
    parts.append(tube("Tower_RearHandle",
                      [(-45, 99, 225), (-45, 110, 228), (-30, 113, 230), (30, 113, 230),
                       (45, 110, 228), (45, 99, 225)], 3.5, mat="Light_Grey"))
    # rear vents + cable hooks - فتحات وخطافات خلفية
    back = parts[0]
    for i in range(6):
        cut(back, rbox("cut", (0, 98.5, 80 + i * 6.5), (90, 4.0, 2.6), bevel=0.8))
    parts.append(rbox("Body_RearLabel", (38, 98.6, 150), (26, 1.4, 16), bevel=0.5, mat="Light_Grey"))
    for sx in (-1, 1):
        parts.append(tube(f"Body_CableHook_{sx}", [(sx * 40, 96, 160), (sx * 40, 108, 160),
                                                  (sx * 40, 111, 167), (sx * 40, 110, 172)], 3.0,
                          mat="Light_Grey"))
    # column under the control panel - العمود الرمادي
    parts.append(cyl("Column", (0, -42, 183), 21, 86, r2=33, sx=1.35, segs=64, mat="Light_Grey"))
    parts.append(cyl("Column_Collar", (0, -42, 186), 28.3, 4, sx=1.35, segs=64, mat="Dark_Grey"))
    return parts


def build_control_panel():
    parts = []
    Z = 239.0  # top surface of the panel
    parts.append(rbox("Panel", (0, -70, 231), (172, 116, 16), bevel=6, mat="Cream_Body"))
    parts.append(rbox("Panel_Trim", (0, -68, 222), (162, 106, 6), bevel=2.5, mat="Light_Grey"))
    parts.append(rbox("Panel_Deck", (0, -66, Z + 0.3), (156, 88, 1.2), bevel=0.5, mat="Monitor_White"))
    # keyboard drawer groove on the front edge
    parts.append(rbox("Panel_Drawer", (0, -128.4, 228.5), (130, 1.4, 1.4), bevel=0.5, mat="Dark_Grey"))

    top = Z + 0.9
    # rotary knobs row - صف المقابض الدوارة
    for i in range(9):
        x = -52 + i * 13
        parts.append(cyl(f"Knob_{i}", (x, -36, top + 1.4), 3.0, 2.8, segs=24, mat="Light_Grey"))
    # soft keys row
    for i in range(11):
        x = -60 + i * 12
        parts.append(rbox(f"Key_A{i}", (x, -48, top + 0.8), (8, 5, 1.6), bevel=0.6, mat="Monitor_White"))
    # TGC sliders - منزلقات TGC
    parts.append(rbox("TGC_Panel", (-30, -72, top + 0.2), (44, 26, 0.6), bevel=0.25, mat="Dark_Grey"))
    for i in range(8):
        x = -47 + i * 5
        parts.append(rbox(f"TGC_Slot_{i}", (x, -72, top + 0.5), (1.0, 22, 0.4), bevel=0.15, mat="Light_Grey"))
        off = 4.0 * math.sin(i * 0.8)
        parts.append(rbox(f"TGC_Knob_{i}", (x, -72 + off, top + 1.4), (3.2, 4.2, 2.4), bevel=0.8, mat="Light_Grey"))
    # trackball - كرة التتبع
    parts.append(cyl("Trackball_Ring", (25, -82, top + 0.7), 10.0, 1.6, segs=48, mat="Light_Grey"))
    parts.append(sphere("Trackball", (25, -82, top + 0.4), 6.6, mat="Trackball"))
    # keys around the trackball
    for x in (10, 40):
        parts.append(rbox(f"Key_TB_{x}", (x, -82, top + 0.8), (8, 6, 1.6), bevel=0.7, mat="Monitor_White"))
    parts.append(cyl("Key_Update", (46, -70, top + 0.9), 3.2, 1.8, segs=24, mat="Trackball"))
    parts.append(cyl("Key_Freeze", (25, -100, top + 0.9), 3.6, 1.8, segs=24, mat="Light_Grey"))
    # left and right key clusters
    for r in range(3):
        for c in range(2):
            parts.append(rbox(f"Key_L{r}{c}", (-74 + c * 9, -62 - r * 9, top + 0.8), (7, 6, 1.6),
                              bevel=0.6, mat="Monitor_White"))
            parts.append(rbox(f"Key_R{r}{c}", (62 + c * 9, -62 - r * 9, top + 0.8), (7, 6, 1.6),
                              bevel=0.6, mat="Monitor_White"))
    for i in range(4):
        parts.append(cyl(f"Key_Mode_{i}", (-24 + i * 9, -96, top + 0.9), 3.0, 1.8, segs=24, mat="Monitor_White"))

    # touch screen (tilted back) - الشاشة اللمسية
    ts = [
        rbox("Touch_Frame", (0, 0, 26), (112, 7, 52), bevel=3.0, mat="Monitor_White"),
        rbox("Touch_Screen_L", (-27, -3.4, 27), (50, 1.2, 42), bevel=0.4, mat="Screen_Black"),
        rbox("Touch_Screen_R", (27, -3.4, 27), (50, 1.2, 42), bevel=0.4, mat="Screen_Black"),
        rbox("Touch_Back", (0, 5, 25), (90, 6, 40), bevel=2.5, mat="Light_Grey"),
    ]
    M = Matrix.Translation((0, -24, Z - 1.0)) @ Matrix.Rotation(math.radians(-32), 4, 'X')
    transform_objs(ts, M)
    parts += ts
    parts.append(rbox("Touch_Bracket", (0, -12, 245), (46, 16, 14), bevel=4, mat="Light_Grey"))

    # front handle (tan) - المقبض الأمامي
    loop = rounded_rect_path(-80, 80, -152, -110, 215.5, 15, n=8)
    parts.append(tube("Handle_Loop", loop, 4.2, mat="Tan_Handle", closed=True, smooth_steps=3))
    parts.append(tube("Handle_Center", [(0, -112, 216), (0, -132, 215.5), (0, -150, 215.5)], 4.0,
                      mat="Tan_Handle"))
    parts.append(rbox("Handle_Hub", (0, -118, 217.5), (28, 22, 10), bevel=4, mat="Tan_Handle"))
    for sx in (-1, 1):
        parts.append(rbox(f"Handle_Mount_{sx}", (sx * 60, -114, 219), (14, 12, 8), bevel=3, mat="Light_Grey"))
    return parts


def build_probe(tag, base, height=14.0):
    """Holder cup + transducer standing in it."""
    x, y, z = base
    parts = []
    cup = cyl(f"ProbeCup_{tag}", (x, y, z + 9), 7.2, 18, segs=40, mat="Light_Grey")
    cut(cup, cyl("cut", (x, y, z + 14), 5.6, 16, segs=40))
    parts.append(cup)
    parts.append(cyl(f"Probe_{tag}_Grip", (x, y, z + 12 + height * 0.5), 4.4, height, segs=32, mat="Cream_Body"))
    parts.append(rbox(f"Probe_{tag}_Head", (x, y, z + 13 + height), (11, 7, 10), bevel=3.0, mat="Cream_Body"))
    parts.append(cyl(f"Probe_{tag}_Strain", (x, y, z + 9), 2.4, 10, segs=20, mat="Light_Grey"))  # joins cup floor and grip
    return parts


def build_probes_and_cables():
    parts = []
    # holder on the panel's left edge (tallest probe, as in the photo)
    parts += build_probe("A", (-93, -28, 212), height=18)
    parts.append(rbox("ProbeCup_A_Arm", (-88, -28, 220), (10, 10, 8), bevel=2.5, mat="Light_Grey"))
    # two holders on the tower's left side
    parts += build_probe("B", (-77, 40, 184), height=12)
    parts += build_probe("C", (-77, 78, 184), height=12)
    # connector bay under the left of the panel (cables plug in here)
    parts.append(rbox("Connector_Bay", (-60, -50, 212), (32, 40, 18), bevel=3, mat="Dark_Grey"))

    if WITH_CABLES:
        R = 1.5  # 3 mm cable
        parts.append(tube("Cable_A1", [(-93, -28, 208), (-98, -40, 182), (-101, -56, 146),
                                       (-94, -70, 124), (-82, -72, 128), (-76, -66, 156),
                                       (-72, -58, 186), (-66, -52, 210)], R, mat="Light_Grey"))
        parts.append(tube("Cable_A2", [(-93, -28, 208), (-104, -32, 176), (-108, -48, 136),
                                       (-99, -64, 114), (-85, -64, 118), (-77, -60, 148),
                                       (-71, -50, 180), (-62, -46, 210)], R, mat="Light_Grey"))
    return parts


def build_monitor():
    parts = []
    # arm - ذراع الشاشة
    parts.append(cyl("Arm_Base", (0, 70, 247), 13, 6, segs=48, mat="Light_Grey"))
    parts.append(cyl_between("Arm_Post", (0, 70, 245), (0, 70, 282), 8.5))
    parts.append(sphere("Arm_Joint1", (0, 70, 282), 8.5))
    parts.append(cyl_between("Arm_Link", (0, 70, 282), (0, 50, 306), 7.5))
    parts.append(sphere("Arm_Joint2", (0, 50, 306), 7.5))
    parts.append(rbox("Monitor_Mount", (0, 48, 316), (32, 12, 28), bevel=4, mat="Light_Grey"))
    # monitor
    mon = rbox("Monitor_Bezel", (0, 36, 349), (138, 10, 102), bevel=4, mat="Monitor_White")
    cut(mon, rbox("cut", (0, 31, 345.5), (120, 3.0, 81), bevel=0.6))
    parts.append(mon)
    parts.append(rbox("Monitor_Screen", (0, 32.4, 345.5), (119.4, 1.0, 80.4), bevel=0.3, mat="Screen_Black"))
    parts.append(rbox("Monitor_Back", (0, 44, 347), (106, 10, 78), bevel=4.5, mat="Light_Grey"))
    parts.append(rbox("Monitor_PowerLED", (0, 30.8, 301.5), (5, 0.8, 1.6), bevel=0.3, mat="Dark_Grey"))
    if WITH_LOGO_TEXT:
        try:
            parts.append(text_obj("Monitor_Logo", LOGO_TEXT, (0, 31.0, 393.2), 5.6, 0.35, "Dark_Grey"))
        except Exception as e:  # font missing etc.
            print("Logo text skipped:", e)
    return parts


# ---------------------------------------------------------------------------
# Print preparation / تجهيز الطباعة
# ---------------------------------------------------------------------------
def scale_to_height(objs, target):
    zmin = min((o.matrix_world @ v.co).z for o in objs for v in o.data.vertices)
    zmax = max((o.matrix_world @ v.co).z for o in objs for v in o.data.vertices)
    f = target / (zmax - zmin)
    M = Matrix.Diagonal((f, f, f, 1.0)) @ Matrix.Translation((0, 0, -zmin))
    transform_objs(objs, M)
    return f


def flatten_bottom(objs):
    """Cut anything below z=0 (gives the wheels flat contact patches)."""
    for o in objs:
        zmin = min(v.co.z for v in o.data.vertices)
        if zmin < -0.001:
            cut(o, rbox("cut", (0, 0, -50), (1000, 1000, 100), bevel=0))


def dims(objs):
    vs = [v.co for o in objs for v in o.data.vertices]
    lo = Vector((min(v.x for v in vs), min(v.y for v in vs), min(v.z for v in vs)))
    hi = Vector((max(v.x for v in vs), max(v.y for v in vs), max(v.z for v in vs)))
    return lo, hi


def solid_union(objs, name):
    """One watertight shell using the exact boolean solver (collection union)."""
    tmp_col = bpy.data.collections.new("_union_tmp")
    bpy.context.scene.collection.children.link(tmp_col)
    biggest = max(objs, key=lambda o: len(o.data.vertices) * 0 + o.dimensions.x * o.dimensions.y * o.dimensions.z)
    base = bpy.data.objects.new(name, biggest.data.copy())
    bpy.context.scene.collection.objects.link(base)
    for o in objs:
        if o is biggest:
            continue
        tmp_col.objects.link(o)
    m = base.modifiers.new("Union", 'BOOLEAN')
    m.operation = 'UNION'
    m.operand_type = 'COLLECTION'
    m.collection = tmp_col
    m.solver = 'EXACT'
    apply_mods(base)
    for o in list(tmp_col.objects):
        tmp_col.objects.unlink(o)
    bpy.data.collections.remove(tmp_col)
    return base


def manifold_report(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bad = sum(1 for e in bm.edges if not e.is_manifold)
    tris = sum(len(f.verts) - 2 for f in bm.faces)
    bm.free()
    return bad, tris


def write_stl(path, objs):
    """Binary STL writer (independent of Blender's exporter version). mm units."""
    tris = []
    for o in objs:
        me = o.data
        me.calc_loop_triangles()
        mw = o.matrix_world
        vs = [mw @ v.co for v in me.vertices]
        for t in me.loop_triangles:
            a, b, c = (vs[i] for i in t.vertices)
            n = (b - a).cross(c - a)
            if n.length > 0:
                n.normalize()
            tris.append((n, a, b, c))
    with open(path, "wb") as f:
        f.write(b"Ultrasound cart - units: mm".ljust(80, b" "))
        f.write(struct.pack("<I", len(tris)))
        for n, a, b, c in tris:
            f.write(struct.pack("<12fH", n.x, n.y, n.z, a.x, a.y, a.z,
                                b.x, b.y, b.z, c.x, c.y, c.z, 0))
    return len(tris)


def output_dir():
    if OUT_DIR:
        d = OUT_DIR
    elif bpy.data.filepath:
        d = os.path.join(os.path.dirname(bpy.data.filepath), "ultrasound_export")
    else:
        d = os.path.join(os.path.expanduser("~"), "ultrasound_export")
    os.makedirs(d, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Preview render (optional)
# ---------------------------------------------------------------------------
def look_at(obj, target):
    d = Vector(target) - obj.location
    obj.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()


def setup_render(out_dir):
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.samples = 48
    if hasattr(sc.cycles, "use_denoising"):
        sc.cycles.use_denoising = True
    sc.render.resolution_x = 1000
    sc.render.resolution_y = 1000
    sc.view_settings.view_transform = 'Standard' if 'Standard' in [
        i.identifier for i in sc.view_settings.bl_rna.properties['view_transform'].enum_items] else sc.view_settings.view_transform
    world = bpy.data.worlds.new("World") if not sc.world else sc.world
    sc.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = (0.75, 0.76, 0.78, 1)
    bg.inputs[1].default_value = 0.6
    # floor
    floor = rbox("Floor", (0, 0, -2), (3000, 3000, 4), bevel=0, mat=None)
    fm = make_mat("Floor", (0.62, 0.63, 0.66), 0.8)
    floor.data.materials.append(fm)
    # lights
    for name, loc, energy, size in (("Key", (-500, -700, 900), 2.5e6, 600),
                                    ("Fill", (700, -300, 500), 1.0e6, 800),
                                    ("Rim", (0, 700, 800), 1.2e6, 500)):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = energy
        ld.size = size
        lo = bpy.data.objects.new(name, ld)
        sc.collection.objects.link(lo)
        lo.location = loc
        look_at(lo, (0, 0, 180))
    cd = bpy.data.cameras.new("Cam")
    cd.lens = 70
    cd.clip_start = 10
    cd.clip_end = 10000
    cam = bpy.data.objects.new("Cam", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    views = {
        "preview_front_left": (-620, -760, 470),
        "preview_operator": (420, -900, 520),
        "preview_back": (650, 780, 520),
    }
    for fname, loc in views.items():
        cam.location = loc
        look_at(cam, (0, -10, 200))
        sc.render.filepath = os.path.join(out_dir, fname + ".png")
        bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(floor, do_unlink=True)


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main():
    clear_scene()
    setup_scene()
    init_materials()

    parts = []
    parts += build_base()
    parts += build_body()
    parts += build_control_panel()
    parts += build_probes_and_cables()
    parts += build_monitor()

    if FLAT_WHEELS:
        flatten_bottom(parts)
        parts = [o for o in COL.objects]

    if PRINT_BASE:
        parts.append(rbox("Display_Base", (0, -20, -1.5), (190, 300, 3), bevel=1.2, mat="Dark_Grey"))

    f = scale_to_height(parts, TARGET_HEIGHT)
    lo, hi = dims(parts)
    size = hi - lo
    print("Scale factor: %.4f" % f)
    print("Final size (mm): W %.1f x D %.1f x H %.1f" % (size.x, size.y, size.z))

    out = output_dir()
    if EXPORT_STL:
        # 1) whole model (overlapping shells - every slicer merges them)
        n = write_stl(os.path.join(out, "ultrasound_full.stl"), parts)
        print("ultrasound_full.stl  triangles:", n)
        # 2) one STL per colour, for multi-colour printers / painting guides
        by_mat = {}
        for o in parts:
            key = o.data.materials[0].name if o.data.materials else "Misc"
            by_mat.setdefault(key, []).append(o)
        for key, objs in by_mat.items():
            write_stl(os.path.join(out, "color_%s.stl" % key), objs)
        # 3) single watertight solid
        if MAKE_SOLID_UNION:
            try:
                solid = solid_union(parts, "Ultrasound_SOLID")
                bad, tris = manifold_report(solid)
                print("Solid union: %d triangles, non-manifold edges: %d" % (tris, bad))
                write_stl(os.path.join(out, "ultrasound_solid.stl"), [solid])
                solid.hide_viewport = True
                solid.hide_render = True
            except Exception as e:
                print("Solid union failed (use ultrasound_full.stl):", e)
    print("Output folder:", out)

    if RENDER_PREVIEW:
        setup_render(out)


if __name__ == "__main__":
    main()
