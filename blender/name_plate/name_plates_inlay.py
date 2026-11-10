"""
Two flat name plaques with the names PRINTED INTO the face (flush inlay, not
raised) + stands, exported as 3MF for multi-colour printing.

Each plaque 3MF has two parts in one object:
  * Plate  (light grey)  — the plaque body
  * Text   (dark grey)   — names + frame line, set flush into the top 0.6 mm
So the face is completely flat; only the colour changes (AMS / filament swap).

Run:  blender -b -P name_plates_inlay.py -- --out .   (writes the 3MF files,
      the .blend and a preview render)
"""

import bpy
import bmesh
import math
import os
import sys
import zipfile
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
sys.path.insert(0, HERE)
from name_plate import visual            # Arabic shaping (joined letters, RTL)   # noqa: E402

FONT_CANDIDATES = [os.path.join(HERE, "NotoSansArabic-Medium.ttf"),      # font from the picture
                   os.path.join(HERE, "DejaVuSans-Bold.ttf"),
                   "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                   os.path.join(HERE, "NotoKufiArabic-ExtraBold.ttf")]

PLAQUES = {
    "Plaque_Group_B": ["كروب B", "شهد بشير ديوان", "عذراء رياض سفيح",
                       "شمس عبد الكاظم", "دلال كاظم", "نور الهدى كامل"],
    "Plaque_Project_1": ["الدكتورة زهراء علاء الخفاجي",
                         "سجاد خضير حليم", "كرار فرحان عبد الكاظم", "سيف سعد نجم",
                         "سلام ستار", "علي حسين عبد الهادي"],
}
# sizes in mm
PW, PH = 200.0, 170.0      # plaque
T = 3.0                    # plaque thickness
INLAY = 0.6                # colour depth of names + frame (flush with the face)
CORNER = 6.0
EDGE = 4.0                 # light margin outside the frame line
FRAME = 3.0                # frame line width
SLOT_HIDE = 10.0           # bottom strip that goes into the stand
TITLE_EM, BIG_EM, NAME_EM = 18.0, 17.5, 15.5
PITCH = 22.0
FIRST_GAP = 3.0          # a little extra space under the first line
MM = 0.001


def rr(w, h, r, cx=0.0, cy=0.0, seg=12):
    pts = []
    for qx, qy, a0 in ((1, 1, 0), (-1, 1, 90), (-1, -1, 180), (1, -1, 270)):
        ccx, ccy = cx + qx * (w / 2 - r), cy + qy * (h / 2 - r)
        for i in range(seg + 1):
            a = math.radians(a0 + 90 * i / seg)
            pts.append((ccx + r * math.cos(a), ccy + r * math.sin(a)))
    return pts


def slab_bm(bm, outer, z0, z1, inner=None):
    n = len(outer)
    ob_ = [bm.verts.new((x, y, z0)) for x, y in outer]
    ot = [bm.verts.new((x, y, z1)) for x, y in outer]
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((ob_[i], ob_[j], ot[j], ot[i]))
    if inner is None:
        bm.faces.new(list(reversed(ob_)))
        bm.faces.new(ot)
        return
    ib = [bm.verts.new((x, y, z0)) for x, y in inner]
    it = [bm.verts.new((x, y, z1)) for x, y in inner]
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((it[i], it[j], ib[j], ib[i]))
        bm.faces.new((ot[i], ot[j], it[j], it[i]))
        bm.faces.new((ib[i], ib[j], ob_[j], ob_[i]))


def mesh_obj(name, bm):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def bake(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    ob.modifiers.clear()
    ob.data = me


# ---------------------------------------------------------------------------
# 2D text + plaque geometry (font outlines -> pathops booleans -> extrusion).
# Needs fontTools + skia-pathops (only to regenerate; the 3MF files are ready).
# ---------------------------------------------------------------------------
def _font_paths():
    from fontTools.ttLib import TTFont
    path = next(p for p in FONT_CANDIDATES if os.path.exists(p))
    return TTFont(path), path


def _line_path(tt, text, em, y, max_w):
    """Shaped line -> one pathops.Path in mm, centred at (0, y)."""
    import pathops
    from fontTools.pens.transformPen import TransformPen
    gs = tt.getGlyphSet()
    cmap = tt.getBestCmap()
    hmtx = tt["hmtx"]
    upm = tt["head"].unitsPerEm
    glyphs = [cmap.get(ord(ch), ".notdef") for ch in visual(text)]
    width = sum(hmtx[g][0] for g in glyphs)
    s = em / upm
    if width * s > max_w:
        s = max_w / width
    x = -width * s / 2
    base = y - 0.28 * em * (s * upm / em)          # visual centre of Arabic letters
    p = pathops.Path()
    for g in glyphs:
        gs[g].draw(TransformPen(p.getPen(glyphSet=gs), (s, 0, 0, s, x, base)))
        x += hmtx[g][0] * s
    return p


def _rr_path(w, h, r, cy=0.0, reverse=False):
    import pathops
    p = pathops.Path()
    pts = rr(w, h, r, cy=cy)
    if reverse:
        pts = pts[::-1]
    pen = p.getPen()
    pen.moveTo(pts[0])
    for q in pts[1:]:
        pen.lineTo(q)
    pen.closePath()
    return p


def _loops(path, tol=0.08):
    """Flatten a pathops.Path into closed point loops (mm)."""
    from fontTools.pens.basePen import BasePen

    class Flat(BasePen):
        def __init__(self):
            super().__init__(None)
            self.loops, self.cur = [], []

        def _moveTo(self, p):
            self.cur = [p]

        def _lineTo(self, p):
            self.cur.append(p)

        def _qCurveToOne(self, p1, p2):
            p0 = self.cur[-1]
            n = max(2, int(math.dist(p0, p2) / 0.6))
            for i in range(1, n + 1):
                t = i / n
                self.cur.append(((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
                                 (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]))

        def _curveToOne(self, p1, p2, p3):
            p0 = self.cur[-1]
            n = max(3, int(math.dist(p0, p3) / 0.6))
            for i in range(1, n + 1):
                t = i / n
                a, b, c, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t ** 3
                self.cur.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
                                 a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))

        def _closePath(self):
            pts = []
            for q in self.cur:
                if not pts or math.dist(pts[-1], q) > 1e-4:
                    pts.append(q)
            if len(pts) > 2 and math.dist(pts[0], pts[-1]) < 1e-4:
                pts.pop()
            if len(pts) >= 3:
                self.loops.append(pts)
            self.cur = []

        _endPath = _closePath

    pen = Flat()
    path.draw(pen)
    return pen.loops


def _extrude(name, loops, z0, z1):
    """Even-odd filled region (outer loops + holes) -> closed solid."""
    from mathutils.geometry import tessellate_polygon
    bm = bmesh.new()
    bot, top = [], []
    for lp in loops:
        bot.append([bm.verts.new((x, y, z0)) for x, y in lp])
        top.append([bm.verts.new((x, y, z1)) for x, y in lp])
    flat_b = [v for l in bot for v in l]
    flat_t = [v for l in top for v in l]
    tris = tessellate_polygon([[Vector((x, y, 0)) for x, y in lp] for lp in loops])
    for a, b, c in tris:
        for vs in ((flat_t[a], flat_t[b], flat_t[c]), (flat_b[c], flat_b[b], flat_b[a])):
            try:
                bm.faces.new(vs)
            except ValueError:
                pass
    for lb, lt in zip(bot, top):
        n = len(lb)
        for i in range(n):
            j = (i + 1) % n
            try:
                bm.faces.new((lb[i], lb[j], lt[j], lt[i]))
            except ValueError:
                pass
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return mesh_obj(name, bm)


def build_plaque(name, lines, font=None):
    import pathops
    tt, _ = _font_paths()
    fy0, fy1 = -PH / 2 + SLOT_HIDE + EDGE, PH / 2 - EDGE
    fw, fh, fcy = PW - 2 * EDGE, fy1 - fy0, (fy0 + fy1) / 2
    # dark region: frame line (outer minus inner) + all text lines
    dark = pathops.Path()
    _rr_path(fw, fh, CORNER - 1, cy=fcy).draw(dark.getPen())
    _rr_path(fw - 2 * FRAME, fh - 2 * FRAME, CORNER - 1 - FRAME * 0.6, cy=fcy, reverse=True).draw(dark.getPen())
    max_w = fw - 2 * FRAME - 8
    n = len(lines)
    ys = [0.0] + [-(FIRST_GAP + PITCH * i) for i in range(1, n)]
    shift = fcy - (ys[0] + ys[-1]) / 2 - 1.5
    for i, line in enumerate(lines):
        em = BIG_EM if line.startswith("الدكتورة") else (TITLE_EM if i == 0 else NAME_EM)
        _line_path(tt, line, em, ys[i] + shift, max_w).draw(dark.getPen())
    dark.simplify(fix_winding=True)                    # union of everything, no overlaps
    dl = _loops(dark)
    outer = rr(PW, PH, CORNER)
    from mathutils.geometry import tessellate_polygon
    z0, zf, z1 = 0.0, T - INLAY, T
    # ---- plate: ONE solid with pockets shaped exactly like the dark part ----
    bm = bmesh.new()
    ob_ = [bm.verts.new((x, y, z0)) for x, y in outer]
    ot = [bm.verts.new((x, y, z1)) for x, y in outer]
    lt = [[bm.verts.new((x, y, z1)) for x, y in lp] for lp in dl]      # top edges of pockets
    lf = [[bm.verts.new((x, y, zf)) for x, y in lp] for lp in dl]      # pocket floor edges

    def tri_faces(loops_xy, vert_loops, flip=False):
        flat = [v for l in vert_loops for v in l]
        for a_, b_, c_ in tessellate_polygon([[Vector((x, y, 0)) for x, y in lp] for lp in loops_xy]):
            vs = (flat[a_], flat[b_], flat[c_])
            try:
                bm.faces.new(vs[::-1] if flip else vs)
            except ValueError:
                pass

    tri_faces([outer] + dl, [ot] + lt)                 # face of the plaque (with holes)
    tri_faces(dl, lf)                                  # pocket floors
    bm.faces.new(list(reversed(ob_)))                  # bottom
    for loop_a, loop_b in [(ob_, ot)] + list(zip(lf, lt)):
        n = len(loop_a)
        for i in range(n):
            j = (i + 1) % n
            try:
                bm.faces.new((loop_a[i], loop_a[j], loop_b[j], loop_b[i]))
            except ValueError:
                pass
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    plate_ob = mesh_obj(name + "_Plate", bm)
    dark_ob = _extrude(name + "_Text", dl, zf, z1)
    return plate_ob, dark_ob


def build_stand(name, x_off=0.0):
    """Stand with a slot; slot opening faces up (prints without supports)."""
    L, D, H = PW + 16, 34.0, 22.0
    slot_w, slot_d = T + 0.35, SLOT_HIDE
    bm = bmesh.new()
    # lower step + upper block (two-step look like the picture)
    slab_bm(bm, rr(L, D, 3), 0, H * 0.45)
    slab_bm(bm, rr(L - 8, D - 8, 2.5), H * 0.45 - 0.01, H)
    st = mesh_obj(name, bm)
    u = st.modifiers.new("u", 'BOOLEAN')
    dummy = bpy.data.objects.new("d", bpy.data.meshes.new("d"))
    bpy.context.scene.collection.objects.link(dummy)
    u.operation, u.solver, u.use_self, u.object = 'UNION', 'EXACT', True, dummy
    bake(st)
    bpy.data.objects.remove(dummy, do_unlink=True)
    bm = bmesh.new()
    slab_bm(bm, rr(PW + 0.6, slot_w, 0.2), H - slot_d, H + 1)
    cutter = mesh_obj("slot", bm)
    c = st.modifiers.new("c", 'BOOLEAN')
    c.operation, c.solver, c.object = 'DIFFERENCE', 'EXACT', cutter
    bake(st)
    bpy.data.objects.remove(cutter, do_unlink=True)
    st.location.x = x_off
    return st


# ---------------------------------------------------------------------------
def tri_data(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.transform(bm, matrix=ob.matrix_world, verts=bm.verts)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.verts.index_update()
    v = [tuple(x.co) for x in bm.verts]
    f = [tuple(x.index for x in fc.verts) for fc in bm.faces]
    bad = sum(1 for e in bm.edges if not e.is_manifold)
    bm.free()
    return v, f, bad


def write_3mf(path, title, parts, bed=(110.0, 110.0)):
    """parts: [(name, object, '#RRGGBBAA')] -> one object with coloured parts (mm)."""
    data = []
    xs, ys = [], []
    for nm, ob, col in parts:
        v, f, bad = tri_data(ob)
        data.append((nm, v, f, col))
        xs += [p[0] for p in v]
        ys += [p[1] for p in v]
        print("  %-22s tris %6d  open edges %d" % (nm, len(f), bad))
    ox = bed[0] - (min(xs) + max(xs)) / 2
    oy = bed[1] - (min(ys) + max(ys)) / 2
    X = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<model unit="millimeter" xml:lang="en-US" '
         'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">',
         '<metadata name="Title">%s</metadata><resources>' % title,
         '<basematerials id="1">' + "".join('<base name="%s" displaycolor="%s"/>' % (d[0], d[3])
                                             for d in data) + '</basematerials>']
    for i, (nm, v, f, col) in enumerate(data):
        X.append('<object id="%d" name="%s" type="model" pid="1" pindex="%d"><mesh><vertices>'
                 % (i + 2, nm, i))
        X += ['<vertex x="%.4f" y="%.4f" z="%.4f"/>' % (p[0] + ox, p[1] + oy, p[2]) for p in v]
        X.append('</vertices><triangles>')
        X += ['<triangle v1="%d" v2="%d" v3="%d"/>' % t for t in f]
        X.append('</triangles></mesh></object>')
    X.append('<object id="100" name="%s" type="model"><components>' % title +
             "".join('<component objectid="%d"/>' % (i + 2) for i in range(len(data))) +
             '</components></object>')
    X.append('</resources><build><item objectid="100"/></build></model>')
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml',
                   '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/'
                   'package/2006/content-types"><Default Extension="rels" ContentType="application/'
                   'vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" '
                   'ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
        z.writestr('_rels/.rels',
                   '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.'
                   'openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/'
                   '3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/'
                   '2013/01/3dmodel"/></Relationships>')
        z.writestr('3D/3dmodel.model', "\n".join(X))
    print("3MF", path)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = os.path.abspath(argv[argv.index("--out") + 1]) if "--out" in argv else HERE
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    sc = bpy.context.scene
    sc.unit_settings.system, sc.unit_settings.length_unit = 'METRIC', 'MILLIMETERS'
    sc.unit_settings.scale_length = 0.001                    # 1 Blender unit = 1 mm
    font = next(bpy.data.fonts.load(p, check_existing=True) for p in FONT_CANDIDATES if os.path.exists(p))
    font.pack()

    LIGHT, DARK = "#D9DCE0FF", "#55606EFF"
    built = []
    for name, lines in PLAQUES.items():
        plate, dark = build_plaque(name, lines, font)
        write_3mf(os.path.join(out, name + ".3mf"), name,
                  [(name + "_Plate", plate, LIGHT), (name + "_Text", dark, DARK)])
        built.append((plate, dark))
    s1 = build_stand("Stand_1")
    s2 = build_stand("Stand_2")
    s2.location.y = 40
    write_3mf(os.path.join(out, "Stands_x2.3mf"), "Stands_x2",
              [("Stand_1", s1, "#BFC3C8FF"), ("Stand_2", s2, "#BFC3C8FF")])

    # ---- preview scene: plaques standing in their stands -------------------
    def mat(nm, hexcol):
        m = bpy.data.materials.new(nm)
        m.use_nodes = True
        rgb = tuple(int(hexcol[i:i + 2], 16) / 255 for i in (1, 3, 5))
        lin = tuple(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb)
        b = next(n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
        b.inputs["Base Color"].default_value = (*lin, 1)
        b.inputs["Roughness"].default_value = 0.6
        return m
    mL, mD, mS = mat("Light", LIGHT), mat("Dark", DARK), mat("Stand", "#BFC3C8FF")
    s1.location, s2.location = Vector((115, 0, 0)), Vector((-115, 0, 0))
    for (plate, dark), x in zip(built, (-115, 115)):      # Group B on the left, like the picture
        for ob, m in ((plate, mL), (dark, mD)):
            ob.data.materials.append(m)
            ob.rotation_euler = (math.radians(90), 0, 0)
            ob.location = (x, T / 2, 22 - SLOT_HIDE + PH / 2)
    for s in (s1, s2):
        s.data.materials.append(mS)
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.data.lens = 50
    cam.data.clip_end = 5000
    cam.location = (0, -620, 120)
    cam.rotation_euler = (Vector((0, 0, 95)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
    sc.collection.objects.link(cam)
    sc.camera = cam
    for nm, loc, e in (("Key", (-250, -400, 400), 2.5e6), ("Fill", (300, -300, 150), 9e5)):
        ld = bpy.data.lights.new(nm, 'AREA')
        ld.size, ld.energy = 300, e
        lo = bpy.data.objects.new(nm, ld)
        lo.location = loc
        lo.rotation_euler = (Vector((0, 0, 80)) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
        sc.collection.objects.link(lo)
    w = sc.world or bpy.data.worlds.new("W")
    sc.world = w
    w.use_nodes = True
    bg = next(n for n in w.node_tree.nodes if n.type == 'BACKGROUND')
    bg.inputs[0].default_value = (0.35, 0.45, 0.6, 1)
    bg.inputs[1].default_value = 0.6
    sc.render.engine = 'CYCLES'
    sc.cycles.samples = 48
    sc.render.resolution_x, sc.render.resolution_y = 1600, 800
    sc.render.filepath = os.path.join(out, "plaques_preview.png")
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "name_plates_inlay.blend"))
    bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
