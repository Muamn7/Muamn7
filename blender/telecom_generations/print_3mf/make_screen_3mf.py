# -*- coding: utf-8 -*-
"""
Print-ready phone screens (3G, 4G, 5G) as 3MF files.

Each screen is a FLAT 2 mm plate the size of the smartphone display in the
model (54.5 x 110.5 mm, 5.5 mm corner radius) made of two flush parts:
  * Screen  - the coloured background
  * Content - the network label and the signal bars, inlaid 0.6 mm (white)
Run:  blender -b -P make_screen_3mf.py   (or python make_screen_3mf.py with bpy)
"""
import os
import sys
import math
import bpy
import bmesh
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_sign_3mf as ms   # noqa: E402

W, H, R = 54.5, 110.5, 5.5     # mm, display size and corner radius
THICK = 2.0                    # mm, plate thickness
INLAY = 0.6                    # mm, white content depth (3 layers @ 0.2)
TEXT_SIZE = 27.0               # mm
TEXT_Z = -9.0                  # mm, label centre from the screen centre
BARS = dict(x0=-15.0, z0=-43.5, w=5.5, h0=4.5, dh=4.0, gap=3.0)
CONTENT_COLOR = "#FFFFFF"
SCREENS = [("3G", "#0F3D22"), ("4G", "#5A240A"), ("5G", "#24104A")]


def rrect(w, h, r, seg=12):
    pts = []
    for cx, cy, a0 in ((w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90),
                       (-w / 2 + r, -h / 2 + r, 180), (w / 2 - r, -h / 2 + r, 270)):
        for i in range(seg + 1):
            a = math.radians(a0 + 90.0 * i / seg)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def add_prism(bm, pts, z0, z1, off=(0, 0)):
    lo = [bm.verts.new((x + off[0], y + off[1], z0)) for x, y in pts]
    hi = [bm.verts.new((x + off[0], y + off[1], z1)) for x, y in pts]
    bm.faces.new(hi)
    bm.faces.new(list(reversed(lo)))
    n = len(pts)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((lo[i], lo[j], hi[j], hi[i]))


def prism_obj(name, shapes, z0, z1):
    """shapes: [(points, (dx, dy))] -> one mesh object"""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    for pts, off in shapes:
        add_prism(bm, pts, z0, z1, off)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def bar_shapes():
    b = BARS
    out = []
    for i in range(4):
        h = b["h0"] + i * b["dh"]
        out.append((rrect(b["w"], h, min(b["w"], h) * 0.2, 4),
                    (b["x0"] + b["w"] / 2 + i * (b["w"] + b["gap"]), b["z0"] + h / 2)))
    return out


def content(name, label, z0, z1, font):
    """label text + signal bars as one object between z0..z1"""
    ms.TEXT_SIZE = TEXT_SIZE
    txt = ms.text_solid(name + "_txt", label, z0, z1, font)
    for v in txt.data.vertices:
        v.co.y += TEXT_Z
    clean = bmesh.new()             # merge duplicate glyph vertices before the boolean
    clean.from_mesh(txt.data)
    bmesh.ops.remove_doubles(clean, verts=clean.verts, dist=1e-3)
    bmesh.ops.dissolve_degenerate(clean, edges=clean.edges, dist=1e-3)
    bmesh.ops.triangulate(clean, faces=clean.faces)
    clean.to_mesh(txt.data)
    clean.free()
    bars = prism_obj(name + "_bars", bar_shapes(), z0, z1)
    bm = bmesh.new()
    bm.from_mesh(txt.data)
    bm.from_mesh(bars.data)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for o in (txt, bars):
        bpy.data.objects.remove(o, do_unlink=True)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def build_screen(label, color, font):
    ms.clear()
    screen = prism_obj("Screen", [(rrect(W, H, R), (0, 0))], 0.0, THICK)
    ms.subtract(screen, content("cut", label, THICK - INLAY, THICK + 0.2, font),
                use_self=True)
    cont = content("Content", label, THICK - INLAY, THICK, font)
    parts = []
    for name, col, ob in (("Screen", color, screen), ("Content", CONTENT_COLOR, cont)):
        v, t, bad = ms.tri_data(ob)
        print(f"  {label} {name}: {len(t)} triangles, non-manifold edges = {bad}")
        parts.append((name, col, v, t))
    out = os.path.join(ms.HERE, f"screen_{label}.3mf")
    ms.write_3mf(out, f"Screen_{label}", parts, None)
    print("saved", out)


if __name__ == "__main__":
    font = bpy.data.fonts.load(os.path.abspath(ms.FONT_PATH), check_existing=True)
    for label, col in SCREENS:
        build_screen(label, col, font)
