# -*- coding: utf-8 -*-
"""
Flat 1 mm "Color key" plate as a 3MF file, made from the user's design
(sources/color_key.blend: a panel with raised text).

Nothing is raised: the panel outline and the text outlines are read from the
.blend, the text is inlaid 0.6 mm as an "Ink" part whose top is flush with
the "Background" part, so it prints as a colour change in the top layers.
Run:  python make_colorkey_3mf.py [path/to/source.blend]   (bpy module, or blender -b -P)
Needs: pip install skia-pathops (same as make_plaques_3mf.py)
"""
import math
import os
import sys
import bpy
import pathops

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_sign_3mf as ms          # noqa: E402
import make_plaques_3mf as mp       # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(HERE, "sources", "color_key.blend")
THICK, INLAY = 1.0, 0.6             # mm
BG_COLOR, INK_COLOR = "#E5E6E8", "#0A0A0B"
PANEL, TEXTS = "Key_Panel", "Key_Text"


def read_design(path):
    """panel outline and text outlines (mm, centred on the panel) from the .blend"""
    bpy.context.preferences.filepaths.use_scripts_auto_execute = False
    bpy.ops.wm.open_mainfile(filepath=path, load_ui=False)
    panel = next(o for o in bpy.data.objects if o.name.startswith(PANEL))
    texts = [o for o in bpy.data.objects
             if o.type == "MESH" and (o.name.startswith(TEXTS) or o.name.startswith("Key_Title"))]
    # panel: the widest ring of its bevelled edge, ordered around the centre
    ws = [(panel.matrix_world @ v.co) * 1000.0 for v in panel.data.vertices]
    cx = (min(w.x for w in ws) + max(w.x for w in ws)) / 2
    cy = (min(w.y for w in ws) + max(w.y for w in ws)) / 2
    zmid = sorted({round(w.z, 3) for w in ws})
    ring = []
    best = 0
    for z in zmid:                                  # pick the z level with the largest extent
        pts = [w for w in ws if abs(w.z - z) < 1e-3]
        ext = max(p.x for p in pts) - min(p.x for p in pts)
        if ext > best:
            best, ring = ext, pts
    ring = sorted(ring, key=lambda p: math.atan2(p.y - cy, p.x - cx))
    panel_path = pathops.Path()
    pen = panel_path.getPen()
    pen.moveTo((ring[0].x - cx, ring[0].y - cy))
    for p in ring[1:]:
        pen.lineTo((p.x - cx, p.y - cy))
    pen.closePath()
    # text: union of all upward-facing faces
    text_path = pathops.Path()
    pen = text_path.getPen()
    n_faces = 0
    for ob in texts:
        mw = ob.matrix_world
        for poly in ob.data.polygons:
            if poly.normal.z < 0.99:
                continue
            pts = [((mw @ ob.data.vertices[i].co) * 1000.0) for i in poly.vertices]
            pts = [(p.x - cx, p.y - cy) for p in pts]
            area = sum(pts[i][0] * pts[i - 1][1] - pts[i - 1][0] * pts[i][1]
                       for i in range(len(pts)))
            if area > 0:                            # make every face clockwise-consistent
                pts.reverse()
            pen.moveTo(pts[0])
            for p in pts[1:]:
                pen.lineTo(p)
            pen.closePath()
            n_faces += 1
    text_path.simplify(fix_winding=True)
    print(f"  read {len(texts)} text objects ({n_faces} faces), panel ring of {len(ring)} points")
    return panel_path, text_path


def build(path):
    panel_path, text_path = read_design(path)
    ms.clear()
    bg = mp.solid("Background", panel_path, 0.0, THICK)
    mp.boolean(bg, mp.solid("cut", text_path, THICK - INLAY, THICK + 0.2), "DIFFERENCE")
    ink = mp.solid("Ink", text_path, THICK - INLAY, THICK)
    parts = []
    for name, col, ob in (("Background", BG_COLOR, bg), ("Ink", INK_COLOR, ink)):
        v, t, bad = ms.tri_data(ob, merge=0)
        xs, ys, zs = ([p[i] for p in v] for i in range(3))
        print(f"  {name}: {len(t)} tris, non-manifold = {bad}, {max(xs) - min(xs):.1f} x "
              f"{max(ys) - min(ys):.1f} mm, z {min(zs):.2f}..{max(zs):.2f}")
        parts.append((name, col, v, t))
    out = os.path.join(HERE, "color_key_1mm.3mf")
    ms.write_3mf(out, "Color_Key_1mm", parts, None)
    print("saved", out)


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    build(os.path.abspath(args[0]) if args and args[0].endswith(".blend") else SOURCE)
