# =====================================================================
#  Pipe clamp bracket for a 155 mm pipe  —  Blender 4.2+ / 5.x script
#  قطعة تثبيت بوري قطر 155mm  —  سكربت بلندر بارامتري
#
#  How to use in Blender:
#     Scripting tab -> Text -> Open -> this file -> Run Script (Alt+P)
#  It builds one clean, manifold object named "PipeClamp_155" in mm.
#  Change the numbers in PARAMETERS and run again to regenerate.
#
#  Command line (optional, exports STL + .blend):
#     blender -b -P pipe_clamp_155.py -- --out ./export [--tab-align BOTTOM]
# =====================================================================
import bpy
import bmesh
import math
import os
import sys

# ----------------------------- PARAMETERS (mm) -----------------------
PIPE_D = 155.0          # قطر البوري الخارجي
WALL = 4.0              # سماكة جدار الحلقة
HEIGHT = 50.0           # ارتفاع الحلقة 5cm

TAB_LEN = 30.0          # بروز اللسان من سطح الحلقة 3cm
TAB_H = 30.0            # ارتفاع اللسان 3cm
TAB_T = 4.0             # سماكة اللسان
TAB_ALIGN = "CENTER"    # "CENTER" مثل الرسم ، "BOTTOM" للطباعة بدون دعامات
TAB_CORNER_R = 5.0      # تدوير زوايا اللسان الخارجية

HOLE_D = 2.0            # قطر ثقب المسمار
HOLE_FROM_WALL = 15.0   # بعد مركز الثقب عن سطح الحلقة (منتصف اللسان)

FILLET_R = 4.0          # تدوير وصلة اللسان مع الحلقة (يمنع الكسر)
CHAMFER_IN = 1.0        # شطفة الحافة الداخلية لتسهيل إدخال البوري
CHAMFER_OUT = 0.6       # شطفة الحافة الخارجية

# Grip ribs: small vertical ribs inside the bore that get crushed when the
# pipe is pushed in -> tight grip that tolerates printer inaccuracy.
# أضلاع شد داخلية: تنضغط عند إدخال البوري فتعطي مسكة قوية
GRIP_RIBS = True
RIB_COUNT = 12
RIB_R = 0.8             # نصف قطر الضلع
BORE_CLEAR = 0.2        # خلوص نصف قطري للفتحة (عند تفعيل الأضلاع)
RIB_INTERFERENCE = 0.2  # كم يدخل الضلع في سطح البوري (نصف قطري)

SEGMENTS = 256          # دقة الدائرة
NAME = "PipeClamp_155"
# ---------------------------------------------------------------------


def _cli_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    out, align = None, None
    for i, a in enumerate(argv):
        if a == "--out" and i + 1 < len(argv):
            out = argv[i + 1]
        if a == "--tab-align" and i + 1 < len(argv):
            align = argv[i + 1].upper()
    return out, align


def _obj_from_pydata(name, verts, faces):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _prism(name, poly, a0, a1, plane):
    """Extrude a 2D polygon. plane 'XY' -> along Z, 'XZ' -> along Y."""
    n = len(poly)
    verts = []
    for a in (a0, a1):
        for u, v in poly:
            verts.append((u, v, a) if plane == "XY" else (u, a, v))
    faces = [tuple(range(n)), tuple(range(2 * n - 1, n - 1, -1))]
    for k in range(n):
        k2 = (k + 1) % n
        faces.append((k, k2, n + k2, n + k))
    return _obj_from_pydata(name, verts, faces)


def _arc(cx, cy, r, a0, a1, steps):
    return [(cx + r * math.cos(a0 + (a1 - a0) * i / steps),
             cy + r * math.sin(a0 + (a1 - a0) * i / steps))
            for i in range(steps + 1)]


def build(tab_align=TAB_ALIGN):
    # remove previous result
    for ob in list(bpy.data.objects):
        if ob.name.startswith(NAME):
            bpy.data.objects.remove(ob, do_unlink=True)

    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.scale_length = 0.001      # 1 Blender unit = 1 mm
    sc.unit_settings.length_unit = "MILLIMETERS"

    r_in = PIPE_D / 2 + (BORE_CLEAR if GRIP_RIBS else 0.0)
    r_out = r_in + WALL
    H = HEIGHT

    # ---- 1. sleeve ring (revolved profile with chamfers) -------------
    ci, co = CHAMFER_IN, CHAMFER_OUT
    prof = [(r_in + ci, 0), (r_out - co, 0), (r_out, co), (r_out, H - co),
            (r_out - co, H), (r_in + ci, H), (r_in, H - ci), (r_in, ci)]
    n = len(prof)
    verts, faces = [], []
    for i in range(SEGMENTS):
        a = 2 * math.pi * i / SEGMENTS
        ca, sa = math.cos(a), math.sin(a)
        verts += [(r * ca, r * sa, z) for r, z in prof]
    for i in range(SEGMENTS):
        j = (i + 1) % SEGMENTS
        for k in range(n):
            k2 = (k + 1) % n
            faces.append((i * n + k, j * n + k, j * n + k2, i * n + k2))
    sleeve = _obj_from_pydata(NAME, verts, faces)

    helpers = []

    # ---- 2. tab (profile in XZ, rounded outer corners) ---------------
    zb = 0.0 if tab_align == "BOTTOM" else (H - TAB_H) / 2
    zt = zb + TAB_H
    x0 = r_in + 1.0                       # starts inside the wall
    x1 = r_out + TAB_LEN
    cr = TAB_CORNER_R
    poly = [(x0, zb)]
    if tab_align == "BOTTOM":             # sharp bottom corner sits on the bed
        poly.append((x1, zb))
        poly += _arc(x1 - cr, zt - cr, cr, 0, math.pi / 2, 12)
    else:
        poly += _arc(x1 - cr, zb + cr, cr, -math.pi / 2, 0, 12)
        poly += _arc(x1 - cr, zt - cr, cr, 0, math.pi / 2, 12)
    poly.append((x0, zt))
    helpers.append(_prism(NAME + "_tab", poly, -TAB_T / 2, TAB_T / 2, "XZ"))

    # ---- 3. root fillets on both faces of the tab --------------------
    fr = FILLET_R
    t2 = TAB_T / 2
    yc = t2 + fr
    xc = math.sqrt((r_out + fr) ** 2 - yc ** 2)
    a_end = math.atan2(-yc, -xc)          # direction from fillet centre to axis
    arc = _arc(xc, yc, fr, -math.pi / 2, a_end, 16)
    tx, ty = arc[-1]
    rq = r_out - 1.5
    s = rq / math.hypot(tx, ty)
    poly = [(math.sqrt(rq ** 2 - (t2 - 0.05) ** 2), t2 - 0.05), (xc, t2 - 0.05)]
    poly += arc + [(tx * s, ty * s)]
    helpers.append(_prism(NAME + "_filletA", poly, zb, zt, "XY"))
    mirrored = [(u, -v) for u, v in reversed(poly)]
    helpers.append(_prism(NAME + "_filletB", mirrored, zb, zt, "XY"))

    # ---- 4. grip ribs -------------------------------------------------
    if GRIP_RIBS:
        tip = PIPE_D / 2 - RIB_INTERFERENCE
        rc = tip + RIB_R
        z0, z1, taper = ci + 1.0, H - ci - 1.0, 3.0
        rings = [(z0, 0.05), (z0 + taper, RIB_R), (z1 - taper, RIB_R), (z1, 0.05)]
        m = 24
        for k in range(RIB_COUNT):
            a = 2 * math.pi * (k + 0.5) / RIB_COUNT
            cx, cy = rc * math.cos(a), rc * math.sin(a)
            v, f = [], []
            for z, r in rings:
                v += [(cx + r * math.cos(2 * math.pi * q / m),
                       cy + r * math.sin(2 * math.pi * q / m), z) for q in range(m)]
            for ri in range(len(rings) - 1):
                for q in range(m):
                    q2 = (q + 1) % m
                    f.append((ri * m + q, ri * m + q2, (ri + 1) * m + q2, (ri + 1) * m + q))
            f.append(tuple(range(m - 1, -1, -1)))
            f.append(tuple(range(3 * m, 4 * m)))
            helpers.append(_obj_from_pydata(f"{NAME}_rib{k}", v, f))

    # ---- 5. screw hole (axis along Y, through the tab) ---------------
    hx, hz, hr = r_out + HOLE_FROM_WALL, (zb + zt) / 2, HOLE_D / 2
    hs = 48
    v, f = [], []
    for y in (-t2 - 2, t2 + 2):
        v += [(hx + hr * math.cos(2 * math.pi * q / hs), y,
               hz + hr * math.sin(2 * math.pi * q / hs)) for q in range(hs)]
    for q in range(hs):
        q2 = (q + 1) % hs
        f.append((q, q2, hs + q2, hs + q))
    f.append(tuple(range(hs - 1, -1, -1)))
    f.append(tuple(range(hs, 2 * hs)))
    hole = _obj_from_pydata(NAME + "_hole", v, f)

    # ---- 6. booleans ----------------------------------------------------
    coll = bpy.data.collections.new(NAME + "_add")
    sc.collection.children.link(coll)
    for h in helpers:
        sc.collection.objects.unlink(h)
        coll.objects.link(h)
    mod = sleeve.modifiers.new("union", "BOOLEAN")
    mod.operation, mod.operand_type, mod.solver = "UNION", "COLLECTION", "EXACT"
    mod.collection = coll
    mod = sleeve.modifiers.new("hole", "BOOLEAN")
    mod.operation, mod.object, mod.solver = "DIFFERENCE", hole, "EXACT"

    dg = bpy.context.evaluated_depsgraph_get()
    new_me = bpy.data.meshes.new_from_object(sleeve.evaluated_get(dg))
    old_me = sleeve.data
    sleeve.modifiers.clear()
    sleeve.data = new_me
    new_me.name = NAME
    new_me.materials.clear()
    bpy.data.meshes.remove(old_me)

    for h in helpers + [hole]:
        me = h.data
        bpy.data.objects.remove(h, do_unlink=True)
        bpy.data.meshes.remove(me)
    bpy.data.collections.remove(coll)

    # clean + smooth shading for curved faces only
    bm = bmesh.new()
    bm.from_mesh(sleeve.data)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=1e-4)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bad = sum(1 for e in bm.edges if not e.is_manifold)
    vol = bm.calc_volume(signed=False)
    bm.to_mesh(sleeve.data)
    bm.free()
    sleeve.data.shade_smooth_by_angle(angle=math.radians(30)) if hasattr(
        sleeve.data, "shade_smooth_by_angle") else None

    bpy.context.view_layer.update()
    for o in bpy.context.scene.objects:
        o.select_set(False)
    sleeve.select_set(True)
    bpy.context.view_layer.objects.active = sleeve

    print(f"[{NAME}] bore Ø{2*r_in:.2f}  outer Ø{2*r_out:.2f}  "
          f"tab z {zb:.1f}-{zt:.1f}  non-manifold edges: {bad}  "
          f"volume: {vol/1000:.1f} cm3  (~{vol/1000*1.24:.0f} g PLA solid)")
    return sleeve, bad, vol


if __name__ == "__main__":
    out_dir, align = _cli_args()
    obj, bad, vol = build(align or TAB_ALIGN)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        tag = "flat_bottom" if (align or TAB_ALIGN) == "BOTTOM" else "center"
        stl = os.path.join(out_dir, f"{NAME}_{tag}.stl")
        bpy.ops.wm.stl_export(filepath=stl, export_selected_objects=True,
                              ascii_format=False, global_scale=1.0)
        print("STL ->", stl)
