# =====================================================================
#  قالب الطوب المصغّر - النسخة الأولى (Master للطباعة ثلاثية الأبعاد)
#  Mini Brick Mold - Master (3D print) - Blender script
#
#  طريقة الاستخدام:
#   1) افتح Blender  ->  تبويب Scripting
#   2) New  ->  الصق هذا الكود  ->  Run Script (Alt+P)
#   3) سيظهر الكائن "Brick_Mold_Master" بالمليمتر وجاهز للتصدير STL
#
#  الوحدات: 1 Blender Unit = 1 mm  (التصدير STL يكون بالمليمتر مباشرة)
#  يعمل على Blender 2.93 / 3.x / 4.x
# =====================================================================
import bpy
import math

# ---------------------- الإعدادات (عدّلها كما تريد) ----------------------
BRICK_L = 18.0      # طول الطوبة (mm)  - مقياس 1:12 لطوبة حقيقية 215mm
BRICK_W = 8.5       # عرض الطوبة (mm)
BRICK_H = 5.5       # ارتفاع الطوبة (mm)

HOLES       = 3     # عدد الثقوب في كل طوبة
HOLE_D      = 2.2   # قطر الثقب (mm)
HOLE_STEP   = 5.2   # المسافة بين مراكز الثقوب (mm)
HOLE_SEGS   = 32    # نعومة الدائرة

COLS = 6            # عدد الأعمدة
ROWS = 4            # عدد الصفوف
GAP_X = 4.0         # المسافة بين الطوب أفقياً (mm)
GAP_Y = 5.0         # المسافة بين الصفوف (mm)

MARGIN   = 5.0      # المسافة بين الطوب والجدار (mm)
WALL_T   = 2.0      # سماكة الجدار (mm)
BASE_T   = 2.0      # سماكة القاعدة (mm)
SILICONE_ABOVE = 4.0  # سماكة السيليكون فوق الطوب = ارتفاع الجدار فوق الطوب

MOUSE_EARS = False  # أقراص الزوايا (ملغاة) - غيّرها إلى True إذا احتجتها
EAR_R      = 6.0
EAR_T      = 0.4
# --------------------------------------------------------------------------

INNER_X = COLS * BRICK_W + (COLS - 1) * GAP_X + 2 * MARGIN
INNER_Y = ROWS * BRICK_L + (ROWS - 1) * GAP_Y + 2 * MARGIN
OUTER_X = INNER_X + 2 * WALL_T
OUTER_Y = INNER_Y + 2 * WALL_T
WALL_H  = BASE_T + BRICK_H + SILICONE_ABOVE


def setup_units():
    us = bpy.context.scene.unit_settings
    us.system = 'METRIC'
    us.scale_length = 0.001
    us.length_unit = 'MILLIMETERS'


def clear_old():
    for name in ("Brick_Mold_Master", "_mold_add", "_mold_cut"):
        obj = bpy.data.objects.get(name)
        if obj:
            bpy.data.objects.remove(obj, do_unlink=True)
        col = bpy.data.collections.get(name)
        if col:
            for o in list(col.objects):
                bpy.data.objects.remove(o, do_unlink=True)
            bpy.data.collections.remove(col)


def new_collection(name):
    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)
    return col


def move_to(obj, col):
    for c in obj.users_collection:
        c.objects.unlink(obj)
    col.objects.link(obj)


def box(name, sx, sy, sz, cx, cy, z0, col=None):
    """صندوق: الحجم (sx,sy,sz) ومركزه (cx,cy) وقاعدته على الارتفاع z0"""
    bpy.ops.mesh.primitive_cube_add(size=1, location=(cx, cy, z0 + sz / 2))
    o = bpy.context.active_object
    o.name = name
    o.scale = (sx, sy, sz)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if col:
        move_to(o, col)
    return o


def cylinder(name, r, h, cx, cy, z0, col, segs=HOLE_SEGS):
    bpy.ops.mesh.primitive_cylinder_add(vertices=segs, radius=r, depth=h,
                                        location=(cx, cy, z0 + h / 2))
    o = bpy.context.active_object
    o.name = name
    move_to(o, col)
    return o


def apply_boolean(target, col, op):
    mod = target.modifiers.new(name="bool_" + op, type='BOOLEAN')
    mod.operation = op
    mod.operand_type = 'COLLECTION'
    mod.collection = col
    mod.solver = 'EXACT'
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.modifier_apply(modifier=mod.name)


def build():
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    setup_units()
    clear_old()

    add_col = new_collection("_mold_add")
    cut_col = new_collection("_mold_cut")

    # 1) القاعدة
    master = box("Brick_Mold_Master", OUTER_X, OUTER_Y, BASE_T, 0, 0, 0)

    # 2) الجدران الأربعة (تتداخل مع القاعدة لضمان الالتحام)
    hx, hy = OUTER_X / 2, OUTER_Y / 2
    box("wall_S", OUTER_X, WALL_T, WALL_H, 0, -hy + WALL_T / 2, 0, add_col)
    box("wall_N", OUTER_X, WALL_T, WALL_H, 0,  hy - WALL_T / 2, 0, add_col)
    box("wall_W", WALL_T, OUTER_Y, WALL_H, -hx + WALL_T / 2, 0, 0, add_col)
    box("wall_E", WALL_T, OUTER_Y, WALL_H,  hx - WALL_T / 2, 0, 0, add_col)

    # 3) أقراص الزوايا
    if MOUSE_EARS:
        for sx in (-1, 1):
            for sy in (-1, 1):
                cylinder("ear", EAR_R, EAR_T, sx * hx, sy * hy, 0, add_col, 48)

    # 4) الطوب + الثقوب
    start_x = -INNER_X / 2 + MARGIN + BRICK_W / 2
    start_y = -INNER_Y / 2 + MARGIN + BRICK_L / 2
    hole_h = BRICK_H + 1.0
    for r in range(ROWS):
        for c in range(COLS):
            cx = start_x + c * (BRICK_W + GAP_X)
            cy = start_y + r * (BRICK_L + GAP_Y)
            # الطوبة تبدأ داخل القاعدة بـ 0.01 لضمان الالتحام
            box(f"brick_{r}_{c}", BRICK_W, BRICK_L, BRICK_H + 0.01,
                cx, cy, BASE_T - 0.01, add_col)
            for i in range(HOLES):
                oy = (i - (HOLES - 1) / 2) * HOLE_STEP
                # الثقب نافذ حتى سطح القاعدة -> ينتج دبوس سيليكون كامل الارتفاع
                cylinder(f"hole_{r}_{c}_{i}", HOLE_D / 2, hole_h,
                         cx, cy + oy, BASE_T, cut_col)

    # 5) الدمج ثم الحفر
    apply_boolean(master, add_col, 'UNION')
    apply_boolean(master, cut_col, 'DIFFERENCE')

    # 6) تنظيف الكائنات المساعدة
    for col in (add_col, cut_col):
        for o in list(col.objects):
            bpy.data.objects.remove(o, do_unlink=True)
        bpy.data.collections.remove(col)

    bpy.ops.object.select_all(action='DESELECT')
    master.select_set(True)
    bpy.context.view_layer.objects.active = master
    print(f"Done: {OUTER_X:.1f} x {OUTER_Y:.1f} x {WALL_H:.1f} mm, "
          f"{ROWS*COLS} bricks")


build()
