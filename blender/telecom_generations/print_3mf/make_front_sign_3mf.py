# -*- coding: utf-8 -*-
"""
Print-ready front title sign ("Generations of Communication") as 3MF files.

A FLAT 2 mm plate the size of the sign on the model (528 x 84 mm) made of two
flush parts: the light Panel and the dark Text (title, subtitle and the
signal waves) inlaid 0.6 mm.
528 mm does not fit most printers, so the plate is also split into three
pieces (about 176 mm each); the cuts are placed in gaps between letters
whenever possible.
Outputs: front_sign_full.3mf and front_sign_part1..3.3mf
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
PIECES = 3
PLATE_LIMIT = 250.0             # mm, largest piece we accept


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


def letter_islands(font):
    """(xmin, xmax, ycentre) of every separate letter shell"""
    probe = content("probe", 0.0, 1.0, font)
    out = []
    bm = bmesh.new()
    bm.from_mesh(probe.data)
    seen = set()
    for v in bm.verts:
        if v.index in seen:
            continue
        stack, pts = [v], []
        seen.add(v.index)
        while stack:
            cur = stack.pop()
            pts.append(cur.co)
            for e in cur.link_edges:
                o = e.other_vert(cur)
                if o.index not in seen:
                    seen.add(o.index)
                    stack.append(o)
        xs = [p.x for p in pts]
        ys = [p.y for p in pts]
        out.append((min(xs), max(xs), min(ys), max(ys)))
    bm.free()
    bpy.data.objects.remove(probe, do_unlink=True)
    return out


def find_gap(target, covered, margin=0.8, search=30.0):
    for step in range(int(search / 0.125) + 1):
        for x in (target + step * 0.125, target - step * 0.125):
            if not any(a - margin <= x <= b + margin for a, b in covered):
                return x
    return None


def choose_cuts(font):
    """stepped cuts: one x in a gap of the title line, one in a gap of the subtitle line,
    joined by a horizontal step between the two lines"""
    isl = letter_islands(font)
    mid = (TITLE[3] + SUBTITLE[3]) / 2
    title = [(a, b) for a, b, y0, y1 in isl if (y0 + y1) / 2 > mid]
    sub = [(a, b) for a, b, y0, y1 in isl if (y0 + y1) / 2 <= mid]
    y_step = (min(y0 for a, b, y0, y1 in isl if (y0 + y1) / 2 > mid) +
              max(y1 for a, b, y0, y1 in isl if (y0 + y1) / 2 <= mid)) / 2
    cuts = []
    for j in range(1, PIECES):
        target = -W / 2 + W * j / PIECES
        xt, xb = find_gap(target, title), find_gap(target, sub)
        print(f"  cut {j}: title line x = {xt}, subtitle line x = {xb}, step at y = {y_step:.2f}")
        cuts.append((xt if xt is not None else target, xb if xb is not None else target))
    return cuts, y_step


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
    cuts, y_step = choose_cuts(font)
    outline = [(sc.rrect(W, H, R), (0, 0))]
    panel = sc.prism_obj("Panel", outline, 0.0, THICK)
    boolean(panel, content("cut", THICK - INLAY, THICK + 0.2, font), "DIFFERENCE")
    text = sc.prism_obj("Text", outline, THICK - INLAY, THICK)
    boolean(text, content("glyphs", THICK - INLAY - 0.2, THICK + 0.2, font), "INTERSECT")
    export(os.path.join(ms.HERE, "front_sign_full.3mf"), "Front_Sign_Full",
           [("Panel", PANEL_COLOR, panel), ("Text", TEXT_COLOR, text)])
    edges = [(-W / 2 - 1, -W / 2 - 1)] + cuts + [(W / 2 + 1, W / 2 + 1)]
    yb, yt = -H / 2 - 5, H / 2 + 5
    for j in range(PIECES):
        (lt, lb), (rt, rb) = edges[j], edges[j + 1]
        box = [([(lb, yb), (rb, yb), (rb, y_step), (rt, y_step), (rt, yt), (lt, yt),
                 (lt, y_step), (lb, y_step)], (0, 0))]
        pieces = []
        for name, col, src in (("Panel", PANEL_COLOR, panel), ("Text", TEXT_COLOR, text)):
            ob = bpy.data.objects.new(f"{name}_{j}", src.data.copy())
            bpy.context.scene.collection.objects.link(ob)
            boolean(ob, sc.prism_obj("box", box, -1.0, THICK + 1.0), "INTERSECT")
            pieces.append((name, col, ob))
        # centre the piece on the plate using the panel's extent
        xs = [v.co.x for v in pieces[0][2].data.vertices]
        cx = (max(xs) + min(xs)) / 2
        assert max(xs) - min(xs) <= PLATE_LIMIT, "piece too long for the plate"
        for _, _, ob in pieces:
            for v in ob.data.vertices:
                v.co.x -= cx
        out = os.path.join(ms.HERE, f"front_sign_part{j + 1}.3mf")
        parts = []
        for name, col, ob in pieces:
            if not ob.data.polygons:
                continue
            v, t, bad = ms.tri_data(ob, merge=0)
            print(f"  part{j + 1} {name}: {len(t)} tris, non-manifold = {bad}, "
                  f"x {min(p[0] for p in v):.1f}..{max(p[0] for p in v):.1f}")
            parts.append((name, col, v, t))
        ms.write_3mf(out, f"Front_Sign_Part{j + 1}", parts, None)
        print("saved", out)


if __name__ == "__main__":
    build(bpy.data.fonts.load(os.path.abspath(ms.FONT_PATH), check_existing=True))
