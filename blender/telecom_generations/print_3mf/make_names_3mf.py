# -*- coding: utf-8 -*-
"""
Print-ready names plaque ("Group B") as a 3MF file.

A FLAT plate (no raised parts) made of three flush parts:
  * Frame - dark border
  * Panel - light background
  * Text  - the title and names, inlaid 0.6 mm (dark)
Run:  blender -b -P make_names_3mf.py   (or python make_names_3mf.py with bpy)

The Arabic lines are pre-shaped (joined letters, right-to-left order) because
Blender does not shape Arabic itself. To change a name, shape it with
arabic_reshaper + python-bidi and replace the string in LINES.
"""
import os
import sys
import bpy
import bmesh

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_sign_3mf as ms          # noqa: E402
import make_screen_3mf as sc        # noqa: E402

W, H = 180.0, 200.0         # mm, plaque size
FRAME = 7.0                 # mm, frame width
R_OUT, R_IN = 8.0, 4.0      # mm, corner radii
THICK = 3.0                 # mm
INLAY = 0.6                 # mm, text depth (3 layers @ 0.2)
TITLE_SIZE, NAME_SIZE = 25.0, 21.0
MAX_W = W - 2 * FRAME - 10  # mm, longest line is shrunk to this width
FRAME_COLOR, PANEL_COLOR, TEXT_COLOR = "#3A3F47", "#E4E6E9", "#3A3F47"

LINES = [
    "B ﺏﻭﺮﻛ",  # كروب B
    "ﻲﺟﺎﻔﺨﻟﺍ ﺀﻼﻋ ﺀﺍﺮﻫﺯ ﺓﺭﻮﺘﻛﺪﻟﺍ",  # الدكتورة زهراء علاء الخفاجي
    "ﻊﻃﺎﻛ ﺭﻮﺼﻨﻣ ﻞﻴﻘﻋ",  # عقيل منصور كاطع
    "ﻢﻇﺎﻛ ﺩﺎﺠﺳ",  # سجاد كاظم
    "ﺭﺪﻴﺣ ﺎﻤﺳ",  # سما حيدر
    "ﺢﻴﺒﺻ ﻝﻮﺘﺑ",  # بتول صبيح
    "ﺭﺪﻴﺣ ﺭﺍﺮﻛ",  # كرار حيدر
    "ﻥﺯﺎﻣ ﺀﻼﻋ",  # علاء مازن
    "ﺪﻴﻬﺷ ﻩﺪﺟﺎﺳ",  # ساجده شهيد
    "ﻦﺴﺤﻣ ﻲﻠﻋ ﺱﺎﺒﻋ",  # عباس علي محسن
]


def line_centres():
    top, bottom = H / 2 - FRAME - 13, -H / 2 + FRAME + 10
    title_gap = 21.0
    step = (top - title_gap - bottom) / (len(LINES) - 2)
    return [top] + [top - title_gap - i * step for i in range(len(LINES) - 1)]


def text_block(name, z0, z1, font):
    """all lines as one mesh between z0..z1"""
    ms.TEXT_RES = 8
    bm = bmesh.new()
    spans = []
    for i, (line, y) in enumerate(zip(LINES, line_centres())):
        ms.TEXT_SIZE = TITLE_SIZE if i == 0 else NAME_SIZE
        ob = ms.text_solid(f"{name}_{i}", line, z0, z1, font)
        xs = [v.co.x for v in ob.data.vertices]
        w = max(xs) - min(xs)
        k = min(1.0, MAX_W / w)
        for v in ob.data.vertices:
            v.co.x *= k
            v.co.y = v.co.y * k + y
        ys = [v.co.y for v in ob.data.vertices]
        spans.append((min(ys), max(ys)))
        bm.from_mesh(ob.data)
        bpy.data.objects.remove(ob, do_unlink=True)
    shift = -(spans[-1][0] + spans[0][1]) / 2      # centre the block vertically
    bmesh.ops.translate(bm, vec=(0, shift, 0), verts=bm.verts)
    spans = [(a + shift, b + shift) for a, b in spans]
    gaps = [spans[i][0] - spans[i + 1][1] for i in range(len(spans) - 1)]
    print(f"  {name}: smallest gap between lines = {min(gaps):.2f} mm, "
          f"text from y={spans[-1][0]:.1f} to {spans[0][1]:.1f}")
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def intersect(target, cutter):
    mod = target.modifiers.new("bool", "BOOLEAN")
    mod.operation = "INTERSECT"
    mod.solver = "EXACT"
    mod.use_self = True
    mod.object = cutter
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(target.evaluated_get(dg))
    target.modifiers.clear()
    target.data = me
    bpy.data.objects.remove(cutter, do_unlink=True)


def build(font):
    ms.clear()
    inner = sc.rrect(W - 2 * FRAME, H - 2 * FRAME, R_IN)
    frame = sc.prism_obj("Frame", [(sc.rrect(W, H, R_OUT), (0, 0))], 0.0, THICK)
    ms.subtract(frame, sc.prism_obj("hole", [(inner, (0, 0))], -1.0, THICK + 1.0))
    panel = sc.prism_obj("Panel", [(inner, (0, 0))], 0.0, THICK)
    ms.subtract(panel, text_block("cut", THICK - INLAY, THICK + 0.2, font), use_self=True)
    # text = top layer of the panel intersected with the glyphs (merges touching letters)
    text = sc.prism_obj("Text", [(inner, (0, 0))], THICK - INLAY, THICK)
    intersect(text, text_block("glyphs", THICK - INLAY - 0.2, THICK + 0.2, font))
    parts = []
    for name, col, ob in (("Frame", FRAME_COLOR, frame), ("Panel", PANEL_COLOR, panel),
                          ("Text", TEXT_COLOR, text)):
        v, t, bad = ms.tri_data(ob, merge=0)
        print(f"  {name}: {len(t)} triangles, non-manifold edges = {bad}")
        parts.append((name, col, v, t))
    out = os.path.join(ms.HERE, "names_group_B.3mf")
    ms.write_3mf(out, "Names_Group_B", parts, None)
    print("saved", out)


if __name__ == "__main__":
    build(bpy.data.fonts.load(os.path.abspath(ms.FONT_PATH), check_existing=True))
