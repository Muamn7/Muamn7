"""
Group name plaque (Arabic) — 3D model for Blender + 3D printing.

Blender cannot join Arabic letters by itself, so this script shapes the text
(joined letter forms + right-to-left order) before creating the 3D text.
The bundled font (Noto Kufi Arabic ExtraBold, SIL OFL) is packed into the
.blend so it opens correctly on any computer.

Change the names in LINES below, then run:
  Blender -> Scripting -> Open -> name_plate.py -> Run Script
or
  blender -b -P name_plate.py -- --save name_plate.blend --render name_plate.png --stl name_plate.stl
"""

import bpy
import bmesh
import math
import os
import sys
from mathutils import Vector

# ---------------------------------------------------------------------------
# Text (logical order, type it normally)
# ---------------------------------------------------------------------------
TITLE = "كروب B"
LINES = [
    "الدكتورة زهراء علاء الخفاجي",
    "سيف الدين علاء",
    "زيد محمد عبد",
    "رضا صباح",
    "محمد رضا حيدر",
    "حسين كاظم خيون",
]

# Plaque size in millimetres
PLATE_W, PLATE_H = 200.0, 190.0
BASE_T = 3.0        # plate thickness
FRAME_W = 7.0       # raised frame width
FRAME_T = 2.0       # frame height above the plate
TEXT_T = 1.4        # text height above the plate
CORNER_R = 12.0
TITLE_SIZE = 24.0
NAME_SIZE = 17.5
MM = 0.001

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
FONT_FILE = os.path.join(HERE, "NotoKufiArabic-ExtraBold.ttf")

# ---------------------------------------------------------------------------
# Minimal Arabic shaper (presentation forms) + right-to-left ordering
# ---------------------------------------------------------------------------
# letter: (isolated, final, initial, medial); None = form does not exist
FORMS = {
    0x0621: (0xFE80, None, None, None),
    0x0622: (0xFE81, 0xFE82, None, None), 0x0623: (0xFE83, 0xFE84, None, None),
    0x0624: (0xFE85, 0xFE86, None, None), 0x0625: (0xFE87, 0xFE88, None, None),
    0x0626: (0xFE89, 0xFE8A, 0xFE8B, 0xFE8C), 0x0627: (0xFE8D, 0xFE8E, None, None),
    0x0628: (0xFE8F, 0xFE90, 0xFE91, 0xFE92), 0x0629: (0xFE93, 0xFE94, None, None),
    0x062A: (0xFE95, 0xFE96, 0xFE97, 0xFE98), 0x062B: (0xFE99, 0xFE9A, 0xFE9B, 0xFE9C),
    0x062C: (0xFE9D, 0xFE9E, 0xFE9F, 0xFEA0), 0x062D: (0xFEA1, 0xFEA2, 0xFEA3, 0xFEA4),
    0x062E: (0xFEA5, 0xFEA6, 0xFEA7, 0xFEA8), 0x062F: (0xFEA9, 0xFEAA, None, None),
    0x0630: (0xFEAB, 0xFEAC, None, None), 0x0631: (0xFEAD, 0xFEAE, None, None),
    0x0632: (0xFEAF, 0xFEB0, None, None), 0x0633: (0xFEB1, 0xFEB2, 0xFEB3, 0xFEB4),
    0x0634: (0xFEB5, 0xFEB6, 0xFEB7, 0xFEB8), 0x0635: (0xFEB9, 0xFEBA, 0xFEBB, 0xFEBC),
    0x0636: (0xFEBD, 0xFEBE, 0xFEBF, 0xFEC0), 0x0637: (0xFEC1, 0xFEC2, 0xFEC3, 0xFEC4),
    0x0638: (0xFEC5, 0xFEC6, 0xFEC7, 0xFEC8), 0x0639: (0xFEC9, 0xFECA, 0xFECB, 0xFECC),
    0x063A: (0xFECD, 0xFECE, 0xFECF, 0xFED0), 0x0641: (0xFED1, 0xFED2, 0xFED3, 0xFED4),
    0x0642: (0xFED5, 0xFED6, 0xFED7, 0xFED8), 0x0643: (0xFED9, 0xFEDA, 0xFEDB, 0xFEDC),
    0x0644: (0xFEDD, 0xFEDE, 0xFEDF, 0xFEE0), 0x0645: (0xFEE1, 0xFEE2, 0xFEE3, 0xFEE4),
    0x0646: (0xFEE5, 0xFEE6, 0xFEE7, 0xFEE8), 0x0647: (0xFEE9, 0xFEEA, 0xFEEB, 0xFEEC),
    0x0648: (0xFEED, 0xFEEE, None, None), 0x0649: (0xFEEF, 0xFEF0, None, None),
    0x064A: (0xFEF1, 0xFEF2, 0xFEF3, 0xFEF4),
}
LAM_ALEF = {0x0622: (0xFEF5, 0xFEF6), 0x0623: (0xFEF7, 0xFEF8),
            0x0625: (0xFEF9, 0xFEFA), 0x0627: (0xFEFB, 0xFEFC)}
HARAKAT = set(range(0x064B, 0x0653))


def _joins_next(cp):
    f = FORMS.get(cp)
    return bool(f and f[2] is not None)


def shape_word(word):
    cps = [ord(c) for c in word if ord(c) not in HARAKAT]
    out, i = [], 0
    while i < len(cps):
        cp = cps[i]
        prev = cps[i - 1] if i > 0 else None
        joined_prev = prev is not None and _joins_next(prev)
        # lam + alef ligature
        if cp == 0x0644 and i + 1 < len(cps) and cps[i + 1] in LAM_ALEF:
            iso, fin = LAM_ALEF[cps[i + 1]]
            out.append(fin if joined_prev else iso)
            i += 2
            continue
        f = FORMS.get(cp)
        if not f:
            out.append(cp)
            i += 1
            continue
        nxt = cps[i + 1] if i + 1 < len(cps) else None
        joins_next = _joins_next(cp) and nxt is not None and nxt in FORMS
        if joined_prev and joins_next:
            form = f[3]
        elif joined_prev:
            form = f[1]
        elif joins_next:
            form = f[2]
        else:
            form = f[0]
        out.append(form if form is not None else f[0])
        i += 1
    return "".join(chr(c) for c in out)


def is_arabic(word):
    return any(0x0600 <= ord(c) <= 0x06FF for c in word)


def visual(line):
    """Logical Arabic line -> left-to-right glyph string for Blender."""
    words = line.split(" ")
    vis = [shape_word(w)[::-1] if is_arabic(w) else w for w in words]
    return " ".join(reversed(vis))


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------
def clear_scene():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for blocks in (bpy.data.meshes, bpy.data.curves, bpy.data.materials,
                   bpy.data.lights, bpy.data.cameras):
        for b in list(blocks):
            if b.users == 0:
                blocks.remove(b)


def rr_points(w, h, r, seg=16):
    pts = []
    for cx, cy, a0 in ((w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90),
                       (-w / 2 + r, -h / 2 + r, 180), (w / 2 - r, -h / 2 + r, 270)):
        for i in range(seg + 1):
            a = math.radians(a0 + 90 * i / seg)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def solid(name, outer, inner, z0, z1, mat):
    """Extruded rounded rectangle (inner=None) or frame (outer minus inner)."""
    bm = bmesh.new()
    ob_ = [bm.verts.new((x, y, z0)) for x, y in outer]
    ot = [bm.verts.new((x, y, z1)) for x, y in outer]
    n = len(outer)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((ob_[i], ob_[j], ot[j], ot[i]))
    if inner is None:
        bm.faces.new(list(reversed(ob_)))
        bm.faces.new(ot)
    else:
        ib = [bm.verts.new((x, y, z0)) for x, y in inner]
        it = [bm.verts.new((x, y, z1)) for x, y in inner]
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((it[i], it[j], ib[j], ib[i]))
            bm.faces.new((ot[i], ot[j], it[j], it[i]))
            bm.faces.new((ib[i], ib[j], ob_[j], ob_[i]))
    for f in bm.faces:
        f.smooth = False
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    me.materials.append(mat)
    bpy.context.scene.collection.objects.link(ob)
    bv = ob.modifiers.new("Bevel", 'BEVEL')
    bv.width = 0.6 * MM
    bv.segments = 3
    bv.limit_method = 'ANGLE'
    return ob


def material(name, col, rough=0.5):
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    b = next(n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    b.inputs["Base Color"].default_value = (*col, 1)
    b.inputs["Roughness"].default_value = rough
    m.diffuse_color = (*col, 1)
    return m


def add_text(name, body, size, y, font, mat, max_w):
    cu = bpy.data.curves.new(name, 'FONT')
    cu.body = body
    cu.font = font
    cu.size = size * MM
    cu.align_x = 'CENTER'
    cu.align_y = 'CENTER'
    cu.extrude = TEXT_T * MM / 2
    cu.bevel_depth = 0.25 * MM
    cu.bevel_resolution = 2
    cu.resolution_u = 6
    ob = bpy.data.objects.new(name, cu)
    ob.data.materials.append(mat)
    bpy.context.scene.collection.objects.link(ob)
    # the text sits ON the plate: bottom at plate top
    ob.location = (0, y * MM, (BASE_T + TEXT_T / 2) * MM)
    bpy.context.view_layer.update()
    if ob.dimensions.x > max_w * MM:                 # shrink long lines to fit
        cu.size *= (max_w * MM) / ob.dimensions.x
    return ob


def build():
    clear_scene()
    sc = bpy.context.scene
    us = sc.unit_settings
    us.system, us.scale_length, us.length_unit = 'METRIC', 1.0, 'MILLIMETERS'
    font = bpy.data.fonts.load(FONT_FILE, check_existing=True)
    font.pack()

    light = material("Plate_LightGrey", (0.42, 0.44, 0.47), 0.55)
    dark = material("Frame_Text_DarkGrey", (0.06, 0.065, 0.075), 0.4)

    W, H, R = PLATE_W * MM, PLATE_H * MM, CORNER_R * MM
    outer = rr_points(W, H, R)
    inner = rr_points(W - 2 * FRAME_W * MM, H - 2 * FRAME_W * MM, R - FRAME_W * MM)
    solid("Plate", outer, None, 0, BASE_T * MM, light)
    solid("Frame", outer, inner, BASE_T * MM - 0.2 * MM, (BASE_T + FRAME_T) * MM, dark)

    # layout: title + names evenly spaced inside the frame
    max_w = PLATE_W - 2 * FRAME_W - 12
    n = len(LINES) + 1
    top = PLATE_H / 2 - FRAME_W - 17
    bottom = -PLATE_H / 2 + FRAME_W + 13
    step = (top - bottom) / (n - 1)
    add_text("Title", visual(TITLE), TITLE_SIZE, top, font, dark, max_w)
    for i, line in enumerate(LINES):
        add_text("Name_%d" % (i + 1), visual(line), NAME_SIZE, top - step * (i + 1), font, dark, max_w)

    # studio
    w = sc.world or bpy.data.worlds.new("World")
    sc.world = w
    try:
        w.use_nodes = True
    except Exception:
        pass
    bg = next((nd for nd in w.node_tree.nodes if nd.type == 'BACKGROUND'), None)
    if bg:
        bg.inputs[0].default_value = (0.5, 0.52, 0.55, 1)
        bg.inputs[1].default_value = 0.25
    for nm, loc, pw in (("Key", (-0.25, -0.3, 0.45), 9), ("Fill", (0.3, -0.2, 0.3), 3)):
        ld = bpy.data.lights.new(nm, 'AREA')
        ld.size = 0.4
        ld.energy = pw
        lo = bpy.data.objects.new(nm, ld)
        lo.location = loc
        lo.rotation_euler = (-Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
        sc.collection.objects.link(lo)
    cd = bpy.data.cameras.new("Camera")
    cd.lens = 60
    cd.clip_start = 0.01
    cam = bpy.data.objects.new("Camera", cd)
    cam.location = (0, -0.13, 0.33)
    cam.rotation_euler = (Vector((0, -0.005, 0)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
    sc.collection.objects.link(cam)
    sc.camera = cam
    sc.render.engine = 'CYCLES'
    sc.cycles.samples = 96
    sc.render.resolution_x, sc.render.resolution_y = 1400, 1400
    try:
        sc.view_settings.view_transform = 'AgX'
    except Exception:
        pass
    return sc


def export_stl(path):
    """One STL in millimetres, flat on the bed (text on top, no supports)."""
    dg = bpy.context.evaluated_depsgraph_get()
    bm = bmesh.new()
    for ob in bpy.context.scene.objects:
        if ob.type in {'MESH', 'FONT'}:
            ev = ob.evaluated_get(dg)
            me = ev.to_mesh()
            me.transform(ev.matrix_world)
            bm.from_mesh(me)
            ev.to_mesh_clear()
    me = bpy.data.meshes.new("print")
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("print", me)
    bpy.context.scene.collection.objects.link(ob)
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.wm.stl_export(filepath=path, export_selected_objects=True, global_scale=1000.0)
    print("STL", path, "mm:", [round(d * 1000, 1) for d in ob.dimensions])
    bpy.data.objects.remove(ob, do_unlink=True)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []

    def arg(k):
        return argv[argv.index(k) + 1] if k in argv else None

    sc = build()
    if arg("--save"):
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(arg("--save")))
    if arg("--stl"):
        export_stl(os.path.abspath(arg("--stl")))
    if arg("--render"):
        sc.render.filepath = os.path.abspath(arg("--render"))
        bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
