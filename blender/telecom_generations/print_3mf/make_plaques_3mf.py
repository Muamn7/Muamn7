"""
Print-ready names plaques with stands, as 3MF files (one file per plaque).

Each plaque is FLAT - nothing is raised. The names, the title and the thin
frame line are printed INTO the background: they are a separate "Ink" part
inlaid 0.6 mm whose top is flush with the "Background" part, so the slicer
prints them as a colour change in the top layers.
A separate "Stand" (with a slot) holds the plaque upright.

Text pipeline (no Blender text objects): HarfBuzz shapes the Arabic (proper
joining and ligatures), fontTools draws the glyph outlines, skia-pathops merges
overlapping outlines into clean 2D shapes, and the shapes are extruded into
closed meshes. Needs:  pip install uharfbuzz skia-pathops fonttools

Font: Noto Sans Arabic Medium (+ Noto Sans Medium for Latin letters),
SIL Open Font License, files in ./fonts.
Run:  python make_plaques_3mf.py   (with the bpy module)  or  blender -b -P ...
"""
import math
import os
import sys
import bpy
import bmesh
import pathops
import uharfbuzz as hb
from fontTools.ttLib import TTFont
from fontTools.pens.basePen import BasePen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.transformPen import TransformPen
from mathutils.geometry import tessellate_polygon

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_sign_3mf as ms          # noqa: E402
import make_screen_3mf as sc        # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_FILES = {"ar": os.path.join(HERE, "fonts", "NotoSansArabic-Medium.ttf"),
              "lat": os.path.join(HERE, "fonts", "NotoSans-Medium.ttf")}

# plaque (mm). The design area is W x H; TAB extra mm at the bottom go into the stand
W, H, TAB = 200.0, 155.0, 8.0
THICK, INLAY = 3.0, 0.6
CORNER = 4.0
LINE_INSET, LINE_W = 2.5, 2.2      # frame line: distance from the edge, line width
TITLE_SIZE, NAME_SIZE = 17.0, 16.0
TITLE_Y = 56.7                     # line centres from the design centre (mm)
NAME_YS = (32.7, 10.3, -11.5, -33.5, -55.5)
MAX_W = 176.0
# stand (mm)
STAND = dict(w=218.0, d=30.0, h=16.0, r=3.0, slot_depth=8.0, clearance=0.4)
BG_COLOR, INK_COLOR, STAND_COLOR = "#D9DBDE", "#4A4F57", "#C9CCD0"

AR, LAT = "ar", "lat"
PLAQUES = [
    # file name, title (segments in visual left-to-right order), names
    ("plaque_group_B",
     [("B", LAT), ("كروب", AR)],
     ["شهد بشير ديوان", "عذراء رياض سفيح", "شمس عبد الكاظم", "دلال كاظم", "نور الهدى كامل"]),
    ("plaque_dr_zahraa",
     [("الدكتورة زهراء علاء الخفاجي", AR)],
     ["سجاد خضير حليم", "كرار فرحان عبد الكاظم", "سيف سعد نجم", "سلام ستار",
      "علي حسين عبد الهادي"]),
]

_FONTS = {}


def font(key):
    if key not in _FONTS:
        tt = TTFont(FONT_FILES[key])
        hbf = hb.Font(hb.Face(hb.Blob.from_file_path(FONT_FILES[key])))
        _FONTS[key] = (tt, tt.getGlyphSet(), tt.getGlyphOrder(), hbf, tt["head"].unitsPerEm)
    return _FONTS[key]


def shaped_path(text, key, size):
    """text shaped by HarfBuzz, as a pathops.Path in mm with the baseline on y = 0"""
    tt, gs, order, hbf, upm = font(key)
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(hbf, buf, {"kern": True, "liga": True})
    s = size / upm
    path = pathops.Path()
    pen = path.getPen()
    x = 0
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):    # visual order
        rec = DecomposingRecordingPen(gs)
        gs[order[info.codepoint]].draw(rec)
        rec.replay(TransformPen(pen, (s, 0, 0, s, (x + pos.x_offset) * s, pos.y_offset * s)))
        x += pos.x_advance
    path.simplify(fix_winding=True)            # merge overlapping letter outlines
    return path


def moved(path, k, dx, dy):
    out = pathops.Path()
    path.draw(TransformPen(out.getPen(), (k, 0, 0, k, dx, dy)))
    return out


def line_path(segments, size, y_centre):
    """one text line (segments in visual left-to-right order), centred and fitted to MAX_W"""
    parts = [shaped_path(t, key, size) for t, key in segments]
    gap = 0.28 * size
    widths = [p.bounds[2] - p.bounds[0] for p in parts]
    total = sum(widths) + gap * (len(parts) - 1)
    k = min(1.0, MAX_W / total)
    baseline = y_centre - 0.2 * size * k       # Arabic letters sit mostly above the baseline
    out = pathops.Path()
    x = -total / 2
    for p, w in zip(parts, widths):
        out = pathops.op(out, moved(p, k, (x - p.bounds[0]) * k, baseline), pathops.PathOp.UNION)
        x += w + gap
    return out


def rect_path(w, h, r):
    p = pathops.Path()
    pen = p.getPen()
    pts = sc.rrect(w, h, r, 16)
    pen.moveTo(pts[0])
    for q in pts[1:]:
        pen.lineTo(q)
    pen.closePath()
    return p


def ink_path(title, names):
    """frame line + title + names as one clean 2D path"""
    ow, oh = W - 2 * LINE_INSET, H - 2 * LINE_INSET
    path = pathops.op(rect_path(ow, oh, CORNER),
                      rect_path(ow - 2 * LINE_W, oh - 2 * LINE_W, max(CORNER - LINE_W, 0.5)),
                      pathops.PathOp.DIFFERENCE)
    lines = [line_path(title, TITLE_SIZE, TITLE_Y)]
    lines += [line_path([(n, AR)], NAME_SIZE, y) for n, y in zip(names, NAME_YS)]
    for lp in lines:
        path = pathops.op(path, lp, pathops.PathOp.UNION)
    return path


class FlattenPen(BasePen):
    """collects closed polylines from a path, flattening curves"""

    def __init__(self, steps=8):
        super().__init__(None)
        self.contours, self.cur, self.steps = [], None, steps

    def _moveTo(self, p):
        self.cur = [p]

    def _lineTo(self, p):
        self.cur.append(p)

    def _curveToOne(self, p1, p2, p3):
        p0 = self.cur[-1]
        for i in range(1, self.steps + 1):
            t = i / self.steps
            u = 1 - t
            self.cur.append(tuple(u ** 3 * a + 3 * u * u * t * b + 3 * u * t * t * c + t ** 3 * d
                                  for a, b, c, d in zip(p0, p1, p2, p3)))

    def _qCurveToOne(self, p1, p2):
        p0 = self.cur[-1]
        for i in range(1, self.steps + 1):
            t = i / self.steps
            u = 1 - t
            self.cur.append(tuple(u * u * a + 2 * u * t * b + t * t * c
                                  for a, b, c in zip(p0, p1, p2)))

    def _closePath(self):
        pts = []
        for p in self.cur:
            if not pts or math.dist(p, pts[-1]) > 1e-4:
                pts.append(p)
        if len(pts) > 2 and math.dist(pts[0], pts[-1]) <= 1e-4:
            pts.pop()
        if len(pts) >= 3:
            self.contours.append(pts)
        self.cur = None

    _endPath = _closePath


def solid(name, path, z0, z1):
    """extrude a clean 2D path (outer contours + holes) into a closed mesh"""
    pen = FlattenPen()
    path.draw(pen)
    cs = pen.contours
    tris = tessellate_polygon([[(x, y, 0.0) for x, y in c] for c in cs])
    flat = [p for c in cs for p in c]
    bm = bmesh.new()
    lo = [bm.verts.new((x, y, z0)) for x, y in flat]
    hi = [bm.verts.new((x, y, z1)) for x, y in flat]
    for a, b, c in tris:
        bm.faces.new((hi[a], hi[b], hi[c]))
        bm.faces.new((lo[c], lo[b], lo[a]))
    off = 0
    for c in cs:
        n = len(c)
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((lo[off + i], lo[off + j], hi[off + j], hi[off + i]))
        off += n
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
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


def build_plaque(fname, title, names):
    ms.clear()
    ink2d = ink_path(title, names)
    outline = [(sc.rrect(W, H + TAB, CORNER), (0, -TAB / 2))]
    bg = sc.prism_obj("Background", outline, 0.0, THICK)
    boolean(bg, solid("cut", ink2d, THICK - INLAY, THICK + 0.2), "DIFFERENCE")
    ink = solid("Ink", ink2d, THICK - INLAY, THICK)
    # stand with a slot for the plaque's bottom tab
    st = STAND
    stand = sc.prism_obj("Stand", [(sc.rrect(st["w"], st["d"], st["r"]), (0, 0))], 0.0, st["h"])
    slot = sc.rrect(W + 2 * st["clearance"], THICK + st["clearance"], 0.2, 2)
    boolean(stand, sc.prism_obj("slot", [(slot, (0, 0))], st["h"] - st["slot_depth"],
                                st["h"] + 1.0), "DIFFERENCE")
    parts = []
    for name, col, ob in (("Background", BG_COLOR, bg), ("Ink", INK_COLOR, ink)):
        v, t, bad = ms.tri_data(ob, merge=0)
        zs = [p[2] for p in v]
        print(f"  {fname} {name}: {len(t)} tris, non-manifold = {bad}, "
              f"z {min(zs):.2f}..{max(zs):.2f}")
        parts.append((name, col, v, t))
    sv, stt, bad = ms.tri_data(stand, merge=0)
    print(f"  {fname} Stand: {len(stt)} tris, non-manifold = {bad}")
    out = os.path.join(HERE, fname + ".3mf")
    # plaque lies face up, stand in front of it; both fit a 256 x 256 mm bed
    ms.write_3mf(out, fname, parts, (sv, stt), positions=((128.0, 150.0), (128.0, 30.0)),
                 extra_name="Stand", extra_color=STAND_COLOR)
    print("saved", out)


if __name__ == "__main__":
    for fname, title, names in PLAQUES:
        build_plaque(fname, title, names)
