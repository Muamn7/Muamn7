# -*- coding: utf-8 -*-
"""
Print-ready front title sign ("Generations of Communication") as 3MF files,
always ONE piece (no splitting).

A FLAT 2 mm plate made of two flush parts: the light Panel and the dark Text
(title, subtitle and the signal waves) inlaid 0.6 mm.
Outputs:
  front_sign_full.3mf     - real size of the model's sign, 528 x 84 mm
  front_sign_fit_256.3mf  - same sign scaled to 305 x 48.5 mm and laid
                            diagonally so it fits a 256 x 256 mm bed
Run:  blender -b -P make_front_sign_3mf.py   (or python with the bpy module)
"""
import math
import os
import sys
import bpy
import bmesh

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_sign_3mf as ms          # noqa: E402
import make_screen_3mf as sc        # noqa: E402

W, H, R = 528.0, 84.0, 10.0     # mm
THICK, INLAY = 2.0, 0.6         # mm
TITLE = ("Generations of Communication", 30.0, 380.0, 12.5)            # text, size, max width, y
SUBTITLE = ("From the First Generation ... to the Fifth Generation", 16.0, 360.0, -21.0)
WAVES_X, WAVE_RADII, WAVE_T, WAVE_SPAN = 226.0, (9.0, 16.0, 23.0), 3.2, 48.0
PANEL_COLOR, TEXT_COLOR = "#F7F7F5", "#0A0A0A"
FIT_BED = 250.0                 # mm, usable bed side for the diagonal one-piece version


def wave_band(r, side):
    """flat arc band (radius r, width WAVE_T) with round ends, opening to `side`"""
    a0, a1 = (-WAVE_SPAN, WAVE_SPAN) if side > 0 else (180 - WAVE_SPAN, 180 + WAVE_SPAN)
    n = 24
    ro, ri, rc = r + WAVE_T / 2, r - WAVE_T / 2, WAVE_T / 2
    pts = [(ro * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
            ro * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]
    cx, cy = r * math.cos(math.radians(a1)), r * math.sin(math.radians(a1))
    pts += [(cx + rc * math.cos(math.radians(a1 + 180 * i / 8)),
             cy + rc * math.sin(math.radians(a1 + 180 * i / 8))) for i in range(1, 8)]
    pts += [(ri * math.cos(math.radians(a1 - (a1 - a0) * i / n)),
             ri * math.sin(math.radians(a1 - (a1 - a0) * i / n))) for i in range(n + 1)]
    cx, cy = r * math.cos(math.radians(a0)), r * math.sin(math.radians(a0))
    pts += [(cx + rc * math.cos(math.radians(a0 + 180 + 180 * i / 8)),
             cy + rc * math.sin(math.radians(a0 + 180 + 180 * i / 8))) for i in range(1, 8)]
    return pts


def content(name, z0, z1, font):
    ms.TEXT_RES = 10
    bm = bmesh.new()
    for i, (txt, size, maxw, y) in enumerate((TITLE, SUBTITLE)):
        ms.TEXT_SIZE = size
        ob = ms.text_solid(f"{name}_{i}", txt, z0, z1, font)
        xs = [v.co.x for v in ob.data.vertices]
        k = min(1.0, maxw / (max(xs) - min(xs)))
        for v in ob.data.vertices:
            v.co.x *= k
            v.co.y = v.co.y * k + y
        bm.from_mesh(ob.data)
        bpy.data.objects.remove(ob, do_unlink=True)
    shapes = [(wave_band(r, s), (s * WAVES_X, 0.0)) for s in (-1, 1) for r in WAVE_RADII]
    waves = sc.prism_obj(name + "_waves", shapes, z0, z1)
    bm.from_mesh(waves.data)
    bpy.data.objects.remove(waves, do_unlink=True)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def boolean(target, cutter, op):
    mod = target.modifiers.new("bool", "BOOLEAN")
    mod.operation = op
    mod.solver = "EXACT"
    mod.use_self = True
    mod.object = cutter
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(target.evaluated_get(dg))
    target.modifiers.clear()
    target.data = me
    bpy.data.objects.remove(cutter, do_unlink=True)


def export(path, title, objs):
    parts = []
    for name, col, ob in objs:
        if not ob.data.polygons:
            continue
        v, t, bad = ms.tri_data(ob, merge=0)
        xs = [p[0] for p in v]
        print(f"  {os.path.basename(path)} {name}: {len(t)} tris, non-manifold = {bad}, "
              f"width {max(xs) - min(xs):.1f} mm")
        parts.append((name, col, v, t))     # the plate is already centred on the origin
    ms.write_3mf(path, title, parts, None)


def build(font):
    ms.clear()
    outline = [(sc.rrect(W, H, R), (0, 0))]
    panel = sc.prism_obj("Panel", outline, 0.0, THICK)
    boolean(panel, content("cut", THICK - INLAY, THICK + 0.2, font), "DIFFERENCE")
    text = sc.prism_obj("Text", outline, THICK - INLAY, THICK)
    boolean(text, content("glyphs", THICK - INLAY - 0.2, THICK + 0.2, font), "INTERSECT")
    export(os.path.join(ms.HERE, "front_sign_full.3mf"), "Front_Sign_Full",
           [("Panel", PANEL_COLOR, panel), ("Text", TEXT_COLOR, text)])
    # one piece that fits a square bed: scale so the 45 deg rotated plate fits FIT_BED
    k = FIT_BED * math.sqrt(2) / (W + H)
    c = s_ = math.sqrt(0.5)
    parts = []
    for name, col, ob in (("Panel", PANEL_COLOR, panel), ("Text", TEXT_COLOR, text)):
        v, t, bad = ms.tri_data(ob, merge=0)
        v = [(k * (x * c - y * s_), k * (x * s_ + y * c), z) for x, y, z in v]
        print(f"  fit_256 {name}: {len(t)} tris, non-manifold = {bad}")
        parts.append((name, col, v, t))
    xs = [p[0] for p in parts[0][2]]
    print(f"  fit_256: {W * k:.1f} x {H * k:.1f} mm, diagonal footprint {max(xs) - min(xs):.1f} mm")
    ms.write_3mf(os.path.join(ms.HERE, "front_sign_fit_256.3mf"), "Front_Sign_Fit_256", parts,
                 None)


if __name__ == "__main__":
    build(bpy.data.fonts.load(os.path.abspath(ms.FONT_PATH), check_existing=True))
