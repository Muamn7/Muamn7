# -*- coding: utf-8 -*-
"""
Mobile Communications - 3D printable layered sign (600 mm tall)
================================================================

Builds the complete model inside Blender, ready for 3D printing:

  * every coloured element is its own solid, watertight part
  * parts are layered (stacked in depth) exactly like the reference photo
  * real 3D items: phone body, satellite dish (true paraboloid), tower ball,
    wooden base with a slot for the panel
  * exports STL per part (full size) and STL split to fit a 256 mm bed

Run inside Blender 4.2+ / 5.x  (Scripting tab -> Open -> Run Script)
or headless:
    blender -b -P build_sign.py -- [--no-export] [--render]

Units: 1 Blender unit = 1 mm (scene is set to millimetres).
Needs the python package "shapely" (the script installs it into Blender's
python automatically the first time if it is missing).
"""

import bpy
import bmesh
import math
import os
import sys
import subprocess
from mathutils import Vector, Matrix

# ----------------------------------------------------------------------------
# shapely (2D geometry kernel) - auto install into Blender's python if needed
# ----------------------------------------------------------------------------
try:
    import shapely  # noqa: F401
except ImportError:  # pragma: no cover - only inside a fresh Blender
    subprocess.check_call([sys.executable, "-m", "ensurepip", "--user"])
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", "shapely"])
    import site
    sys.path.append(site.getusersitepackages())
    import shapely  # noqa: F401

from shapely.geometry import Point, Polygon, LineString, MultiPolygon, box
from shapely.ops import unary_union
from shapely import affinity


# ----------------------------------------------------------------------------
# paths / options
# ----------------------------------------------------------------------------
def _script_dir():
    cands = []
    try:
        cands.append(os.path.dirname(os.path.abspath(__file__)))
    except NameError:
        pass
    for t in bpy.data.texts:
        if t.filepath:
            cands.append(os.path.dirname(bpy.path.abspath(t.filepath)))
    if bpy.data.filepath:
        cands.append(os.path.dirname(bpy.data.filepath))
    cands.append(os.getcwd())
    for d in cands:
        if os.path.isdir(os.path.join(d, "fonts")):
            return d
    return cands[0]


BASE_DIR = _script_dir()
FONT_DIR = os.path.join(BASE_DIR, "fonts")
ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
DO_EXPORT = "--no-export" not in ARGS
DO_RENDER = "--render" in ARGS
DO_SAVE = "--no-save" not in ARGS

TOTAL_HEIGHT = 600.0       # mm, bottom of wooden base -> top of the cloud
BASE_H = 30.0              # wooden base height
SLOT_DEPTH = 10.0          # how deep the panel sits in the base
BED = 250.0                # max piece size for the split export (256 mm bed)

# ----------------------------------------------------------------------------
# depth stack (Y axis, negative = towards the viewer). Panel front = -10
# ----------------------------------------------------------------------------
Y_PANEL_F, Y_PANEL_B = -10.0, 0.0
Y_RIM_F, Y_RIM_B = 0.0, 8.0
Y_BACKER_F, Y_BACKER_B = 8.0, 11.0

# ----------------------------------------------------------------------------
# colours (filament suggestions in PARTS / README)
# ----------------------------------------------------------------------------
COLORS = {
    "Navy":       ("#2A4790", "Panel navy blue"),
    "SkyBlue":    ("#3B7DE3", "Bright / sky blue"),
    "White":      ("#F7F8FB", "White"),
    "DarkNavy":   ("#182C6B", "Dark navy (title & icons)"),
    "Ink":        ("#2A3352", "Dark grey-blue (small text)"),
    "CardFill":   ("#E3E9F8", "Very light blue / lavender"),
    "Black":      ("#17181B", "Black"),
    "Screen":     ("#A9C3F2", "Light blue (phone screen)"),
    "Signal":     ("#1F5ED8", "Royal blue (5G, phone bars)"),
    "Grey":       ("#A2A7B0", "Light grey"),
    "DarkGrey":   ("#3C4049", "Dark grey"),
    "Wood":       ("#D6AE80", "Wood / beige (or real wood)"),
    "Clear":      ("#DDEBF5", "Clear / transparent PETG"),
}

# ----------------------------------------------------------------------------
# reference image space (px of the 1280x1170 photo, y grows downward)
# ----------------------------------------------------------------------------
PX_CX = 667.5      # horizontal centre of the wooden base in the photo
PX_PANEL_BOTTOM = 1020.0


# ============================================================================
#  2D helpers (all in photo pixel space)
# ============================================================================
QS = 24  # quad segments for circles


def circle(x, y, r):
    return Point(x, y).buffer(r, quad_segs=QS)


def ellipse(x, y, rx, ry, rot=0.0):
    g = affinity.scale(Point(0, 0).buffer(1.0, quad_segs=QS), rx, ry)
    if rot:
        g = affinity.rotate(g, rot, origin=(0, 0))
    return affinity.translate(g, x, y)


def rrect(x0, y0, x1, y1, r):
    r = min(r, (x1 - x0) / 2 - 1e-3, (y1 - y0) / 2 - 1e-3)
    return box(x0 + r, y0 + r, x1 - r, y1 - r).buffer(r, quad_segs=QS)


def seg(p, q, w, cap="round"):
    cs = {"round": 1, "flat": 2, "square": 3}[cap]
    return LineString([p, q]).buffer(w / 2.0, quad_segs=8, cap_style=cs, join_style=1)


def arc(cx, cy, r, a0, a1, w, cap="round", n=48):
    """arc in y-down pixel space; angles in degrees, 0 = +x, 90 = down"""
    pts = []
    for i in range(n + 1):
        a = math.radians(a0 + (a1 - a0) * i / n)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    cs = {"round": 1, "flat": 2}[cap]
    return LineString(pts).buffer(w / 2.0, quad_segs=8, cap_style=cs, join_style=1)


def sparkle(x, y, R, p=2.6, n=96):
    """4 point star (super-astroid)"""
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        c, s = math.cos(t), math.sin(t)
        pts.append((x + R * math.copysign(abs(c) ** p, c), y + R * math.copysign(abs(s) ** p, s)))
    return Polygon(pts).buffer(R * 0.06, quad_segs=6)


def heart(x, y, w):
    r = w * 0.27
    g = unary_union([
        circle(x - r * 0.9, y - r * 0.35, r),
        circle(x + r * 0.9, y - r * 0.35, r),
        Polygon([(x - r * 1.82, y - r * 0.05), (x + r * 1.82, y - r * 0.05), (x, y + r * 2.0)]),
    ])
    return g.buffer(r * 0.15).buffer(-r * 0.15)


def union(*gs):
    return unary_union([g for g in gs if g is not None and not g.is_empty])


def polys(g):
    if g is None or g.is_empty:
        return []
    if isinstance(g, Polygon):
        return [g]
    if isinstance(g, MultiPolygon):
        return list(g.geoms)
    return [p for p in getattr(g, "geoms", []) if isinstance(p, Polygon)]


# ============================================================================
#  DESIGN (photo pixel space)
# ============================================================================
def design():
    D = {}

    # ---------------- back panel (navy) + light blue rim -----------------
    slot_px = 20.0  # extension below the visible bottom (goes into the base slot)
    p_top = 290.0
    panel = union(rrect(190, p_top, 1222, PX_PANEL_BOTTOM - 40, 62),
                  box(190, PX_PANEL_BOTTOM - 140, 1222, PX_PANEL_BOTTOM + slot_px))
    rim = panel.buffer(9, quad_segs=QS).intersection(box(0, 0, 2000, PX_PANEL_BOTTOM + slot_px))
    D["panel"], D["rim"], D["panel_top_px"] = panel, rim, p_top

    # ---------------- main cloud (white + sky blue outline) --------------
    cloud = union(
        rrect(515, 250, 1190, 396, 50),
        circle(650, 275, 150), circle(560, 300, 65), circle(905, 235, 163),
        circle(1020, 205, 95), circle(1090, 275, 105),
        circle(600, 350, 48), circle(730, 352, 48), circle(860, 352, 48),
        circle(990, 352, 48), circle(1120, 345, 50),
    ).buffer(5).buffer(-5)
    cloud_out = cloud.buffer(13, quad_segs=QS)

    # ---------------- phone (rotated 9 deg clockwise) --------------------
    PC, PA = (696.0, 637.0), 9.0

    def P(g):  # phone local -> photo
        return affinity.translate(affinity.rotate(g, PA, origin=(0, 0)), PC[0], PC[1])

    W, H = 236.0, 486.0
    phone_body = P(rrect(-W / 2, -H / 2, W / 2, H / 2, 40))
    D["phone_body"] = phone_body
    D["phone_bezel"] = P(rrect(-W / 2 + 6, -H / 2 + 6, W / 2 - 6, H / 2 - 6, 35))
    D["phone_screen"] = P(rrect(-W / 2 + 14, -H / 2 + 48, W / 2 - 14, H / 2 - 50, 16))
    D["phone_speaker"] = P(union(seg((-24, -H / 2 + 26), (24, -H / 2 + 26), 9), circle(44, -H / 2 + 26, 5.5)))
    D["phone_home"] = P(seg((-26, H / 2 - 25), (26, H / 2 - 25), 11))
    bars = [rrect(u - 9, -62 - h, u + 9, -62, 3.5) for u, h in [(-39, 30), (-9, 52), (21, 74), (51, 97)]]
    D["phone_bars"] = P(union(*bars))
    # call handset icon (earpiece top-left, mouthpiece bottom-right)
    hc, hr = (28.0, 104.0), 48.0
    a0, a1 = 95.0, 178.0

    def onarc(a, r=hr):
        return (hc[0] + r * math.cos(math.radians(a)), hc[1] + r * math.sin(math.radians(a)))

    def pad(a, sign):
        p0 = onarc(a, hr + 2)
        t = math.radians(a + sign * 90)
        p1 = (p0[0] + 13 * math.cos(t), p0[1] + 13 * math.sin(t))
        return seg(p0, p1, 25)

    hs = union(arc(hc[0], hc[1], hr, a0, a1, 17), pad(a0, -1), pad(a1, +1)).buffer(3).buffer(-3)
    D["phone_handset"] = P(hs)
    D["phone_5g"] = dict(center=P(Point(0, 11)).coords[0], rot=PA)
    D["phone_center"], D["phone_angle"] = PC, PA

    # cloud is cut where the phone overlaps it (phone sits in front)
    cut_phone = phone_body.buffer(4)
    D["cloud_out"] = cloud_out.difference(cut_phone).buffer(-2).buffer(2)
    D["cloud_white"] = cloud.difference(cut_phone.buffer(13)).buffer(-2).buffer(2)
    # navy signal waves on the cloud (top right)
    waves = union(*[arc(900, 222, r, -90, -14, 20) for r in (50, 90, 132)])
    D["cloud_waves"] = waves.intersection(cloud.buffer(-5))

    # ---------------- "Stay Connected" cloud -----------------------------
    stay = union(
        rrect(214, 590, 496, 690, 45),
        circle(255, 615, 50), circle(340, 595, 58), circle(435, 606, 50),
        circle(482, 648, 38), circle(222, 657, 36),
        circle(282, 680, 32), circle(360, 686, 32), circle(440, 678, 32),
    ).buffer(3).buffer(-3)
    stay_out = stay.buffer(11, quad_segs=QS)
    D["stay_white"], D["stay_out"] = stay, stay_out
    D["heart"] = heart(352, 703, 30)

    # ---------------- lattice tower --------------------------------------
    ax, ay = 307.0, 228.0            # apex (under the ball)
    by = 565.0
    xl0, xr0, xl1, xr1 = ax - 16, ax + 16, 212.0, 402.0

    def pt(yy, left):
        t = (yy - ay) / (by - ay)
        return ((xl0 + (xl1 - xl0) * t) if left else (xr0 + (xr1 - xr0) * t), yy)

    parts = [seg((xl0, ay), (xl1, by), 15), seg((xr0, ay), (xr1, by), 15)]
    levels = [262, 330, 415, 500, by]
    prev = ay + 4
    parts.append(seg(pt(ay + 4, True), pt(ay + 4, False), 11))
    for yy in levels:
        parts.append(seg(pt(yy, True), pt(yy, False), 12))
        parts.append(seg(pt(prev, True), pt(yy, False), 9))
        parts.append(seg(pt(prev, False), pt(yy, True), 9))
        prev = yy
    tower = union(*parts)
    tower_hull = tower.convex_hull
    cut = stay_out.buffer(3)
    D["tower"] = tower.difference(cut)
    D["tower_ball"] = (ax - 2, 198.0, 37.0)
    bx, byy, br = D["tower_ball"]
    D["tower_fill"] = tower_hull.buffer(-2).difference(cut).difference(circle(bx, byy, br + 2))
    # signal arcs (sky blue): ((( ball )))
    tw = []
    axis = 290.0
    for spread, r, span in [(70, 55, 38), (110, 88, 46), (152, 125, 50)]:
        tw.append(arc(axis - spread + r, 200, r, 180 - span, 180 + span, 22))
        tw.append(arc(axis + spread - r, 200, r, -span, span, 22))
    D["tower_waves"] = union(*tw)

    # ---------------- stars ----------------------------------------------
    D["stars"] = union(sparkle(462, 456, 19), sparkle(529, 520, 15), sparkle(507, 744, 14),
                       sparkle(803, 864, 15), sparkle(770, 944, 16))

    # ---------------- bottom signal bars ---------------------------------
    D["bars"] = union(*[rrect(x0, y0, x1, 1002, 4) for x0, x1, y0 in
                        [(423, 452, 968), (463, 492, 950), (502, 532, 928), (542, 572, 910), (585, 618, 893)]])

    # ---------------- info cards -----------------------------------------
    cards = [(418, 540), (565, 690), (710, 832), (860, 986)]
    D["cards"] = []
    for (y0, y1) in cards:
        inner = rrect(868, y0 + 8, 1204, y1 - 8, 38)
        D["cards"].append(dict(fill=inner, out=inner.buffer(9, quad_segs=QS), cy=(y0 + y1) / 2))

    # icon 1: base station (navy tower + sky blue arcs)
    cx, cy = 960.0, cards[0][0] + 62
    t0, tb = cy - 28, cy + 44
    ic = [seg((cx - 4, t0), (cx - 20, tb), 6), seg((cx + 4, t0), (cx + 20, tb), 6)]

    def lx(yy, s):
        return cx + s * (4 + 16 * (yy - t0) / (tb - t0))

    lv = [t0 + 14, cy + 12, tb]
    for a, b in zip(lv[:-1], lv[1:]):
        ic += [seg((lx(a, -1), a), (lx(b, 1), b), 4), seg((lx(a, 1), a), (lx(b, -1), b), 4)]
    for yy in lv:
        ic.append(seg((lx(yy, -1), yy), (lx(yy, 1), yy), 5))
    ic.append(circle(cx, t0 - 6, 8))
    D["icon_station"] = union(*ic)
    D["icon_station_waves"] = union(*[arc(cx, t0 + 2, r, 180 - 42, 180 + 42, 6.5) for r in (20, 34)] +
                                     [arc(cx, t0 + 2, r, -42, 42, 6.5) for r in (20, 34)])

    # icon 2: satellite
    sx, sy = 950.0, (cards[1][0] + cards[1][1]) / 2 - 2
    body = union(rrect(-13, -13, 13, 13, 3), seg((-50, 0), (50, 0), 4),
                 seg((6, 12), (14, 25), 5), circle(16, 28, 5.5))
    cells = []
    for x0 in (-58, -45, -32):
        cells.append(rrect(x0, -12, x0 + 11.5, 12, 1.5))
    for x0 in (20.5, 33.5, 46.5):
        cells.append(rrect(x0, -12, x0 + 11.5, 12, 1.5))
    sat_rot = -35
    body = body.difference(union(*cells).buffer(1.0))
    D["icon_sat"] = affinity.translate(affinity.rotate(body, sat_rot, origin=(0, 0)), sx, sy)
    D["icon_sat_panels"] = affinity.translate(affinity.rotate(union(*cells), sat_rot, origin=(0, 0)), sx, sy)
    D["icon_sat_waves"] = union(*[arc(sx + 20, sy + 30, r, 15, 80, 4.5) for r in (15, 25)])

    # icon 3: cellular bars
    bx0, bb = 902.0, cards[2][1] - 24
    D["icon_cell"] = union(*[rrect(bx0 + i * 24.5, bb - h, bx0 + i * 24.5 + 17, bb, 2.5)
                             for i, h in enumerate([22, 42, 62, 80])])

    # icon 4: globe
    gx, gy, gr = 946.0, (cards[3][0] + cards[3][1]) / 2, 44.0
    disk = circle(gx, gy, gr)
    lines = [disk.difference(circle(gx, gy, gr - 6.5)),
             seg((gx - gr, gy), (gx + gr, gy), 4.5, "flat"),
             seg((gx - gr, gy - 21), (gx + gr, gy - 21), 4.5, "flat"),
             seg((gx - gr, gy + 21), (gx + gr, gy + 21), 4.5, "flat"),
             seg((gx, gy - gr), (gx, gy + gr), 4.5, "flat"),
             ellipse(gx, gy, 22, gr).difference(ellipse(gx, gy, 17.5, gr - 4.5))]
    D["icon_globe"] = union(*lines).intersection(disk)

    D["card_text"] = [("Base", "Station"), ("Satellite", "Communication"),
                      ("Cellular", "Networks"), ("Mobile", "Networks")]
    D["cloud"] = cloud
    return D


# ============================================================================
#  Blender helpers
# ============================================================================
S = 1.0          # mm per photo pixel (computed in main)
Z0 = BASE_H      # world Z of the visible panel bottom


def to_mm(g):
    g = affinity.scale(g, xfact=S, yfact=-S, origin=(0, 0))
    return affinity.translate(g, -PX_CX * S, Z0 + PX_PANEL_BOTTOM * S)


def px_to_world(x, y):
    return ((x - PX_CX) * S, Z0 + (PX_PANEL_BOTTOM - y) * S)


MATS = {}


def hex_rgb(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return [((v + 0.055) / 1.055) ** 2.4 if v > 0.04045 else v / 12.92 for v in c]


def make_materials():
    for key, (hx, _) in COLORS.items():
        m = bpy.data.materials.get("MC_" + key) or bpy.data.materials.new("MC_" + key)
        m.use_nodes = True
        nt = m.node_tree
        bsdf = nt.nodes.get("Principled BSDF")
        rgb = hex_rgb(hx)
        bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.55
        m.diffuse_color = (*rgb, 1.0)
        if key == "Clear":
            bsdf.inputs["Roughness"].default_value = 0.0
            bsdf.inputs["IOR"].default_value = 1.08
            for nm in ("Transmission Weight", "Transmission"):
                if nm in bsdf.inputs:
                    bsdf.inputs[nm].default_value = 1.0
            m.diffuse_color = (*rgb, 0.25)
        if key in ("Navy",):          # soft felt / matte foam look
            bsdf.inputs["Roughness"].default_value = 0.9
            tex = nt.nodes.new("ShaderNodeTexNoise")
            tex.inputs["Scale"].default_value = 0.9
            tex.inputs["Detail"].default_value = 12.0
            bump = nt.nodes.new("ShaderNodeBump")
            bump.inputs["Strength"].default_value = 0.12
            bump.inputs["Distance"].default_value = 0.4
            nt.links.new(tex.outputs["Fac"], bump.inputs["Height"])
            nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
        if key == "Wood":
            bsdf.inputs["Roughness"].default_value = 0.45
            coord = nt.nodes.new("ShaderNodeTexCoord")
            mapn = nt.nodes.new("ShaderNodeMapping")
            mapn.inputs["Scale"].default_value = (0.004, 0.05, 0.05)
            mapn.inputs["Location"].default_value = (0.0, 9.0, -6.0)
            wave = nt.nodes.new("ShaderNodeTexWave")
            wave.wave_type = "RINGS"
            wave.rings_direction = "X"
            wave.inputs["Scale"].default_value = 1.2
            wave.inputs["Distortion"].default_value = 5.0
            wave.inputs["Detail"].default_value = 4.0
            ramp = nt.nodes.new("ShaderNodeValToRGB")
            ramp.color_ramp.elements[0].color = (*hex_rgb("#C89A68"), 1)
            ramp.color_ramp.elements[1].color = (*hex_rgb("#E2BE92"), 1)
            nt.links.new(coord.outputs["Object"], mapn.inputs["Vector"])
            nt.links.new(mapn.outputs["Vector"], wave.inputs["Vector"])
            nt.links.new(wave.outputs["Fac"], ramp.inputs["Fac"])
            nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        MATS[key] = m


COLL = {}


def coll(name, parent=None):
    if name in COLL:
        return COLL[name]
    c = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    (parent or bpy.context.scene.collection).children.link(c)
    COLL[name] = c
    return c


PARTS = []   # (object, colour key, group)


def register(obj, color, group):
    obj.data.materials.clear()
    obj.data.materials.append(MATS[color])
    obj["mc_color"] = color
    obj["mc_group"] = group
    for c in obj.users_collection:
        c.objects.unlink(obj)
    coll("Color_" + color, coll("PRINT_PARTS")).objects.link(obj)
    PARTS.append((obj, color, group))
    return obj


def cleanup_mesh(me, dist=0.0008):
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=dist)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=1e-5)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()


def bake_object(obj, name):
    """evaluate (curve / modifiers) -> plain mesh object in world space"""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev)
    me.transform(obj.matrix_world)
    new = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(new)
    old_data = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    if old_data is not None and old_data.users == 0:
        if isinstance(old_data, bpy.types.Curve):
            bpy.data.curves.remove(old_data)
        elif isinstance(old_data, bpy.types.Mesh):
            bpy.data.meshes.remove(old_data)
    cleanup_mesh(me)
    return new


def extrude(geom_mm, y_front, y_back, name, bevel=0.0, res=3):
    """2D shapely geometry (world X,Z in mm) -> solid between y_front..y_back"""
    depth = y_back - y_front
    b = min(bevel, depth * 0.3)
    g = geom_mm.buffer(-b, quad_segs=8) if b > 0 else geom_mm
    if g.is_empty:
        g, b = geom_mm, 0.0
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "2D"
    cu.fill_mode = "BOTH"
    for poly in polys(g):
        poly = poly.simplify(0.02, preserve_topology=True)
        for ring in [poly.exterior] + list(poly.interiors):
            coords = list(ring.coords)[:-1]
            if len(coords) < 3:
                continue
            sp = cu.splines.new("POLY")
            sp.points.add(len(coords) - 1)
            for p, (x, z) in zip(sp.points, coords):
                p.co = (x, z, 0.0, 1.0)
            sp.use_cyclic_u = True
    cu.extrude = max(depth / 2.0 - b, 0.01)
    cu.bevel_depth = b
    cu.bevel_resolution = res if b > 0 else 0
    ob = bpy.data.objects.new(name + "_crv", cu)
    bpy.context.scene.collection.objects.link(ob)
    ob.rotation_euler = (math.pi / 2, 0, 0)
    ob.location = (0, (y_front + y_back) / 2.0, 0)
    bpy.context.view_layer.update()
    return bake_object(ob, name)


def non_manifold(me):
    bm = bmesh.new()
    bm.from_mesh(me)
    n = sum(1 for e in bm.edges if len(e.link_faces) != 2)
    bm.free()
    return n


def boolean(target, others, op="UNION"):
    """apply boolean(s); exact solver first, float solver as fallback"""
    if not isinstance(others, (list, tuple)):
        others = [others]
    others = [o for o in others if o is not None]
    for o in others:
        results = []
        for solver in ("EXACT", "FLOAT"):
            m = target.modifiers.new("b", "BOOLEAN")
            m.operation = op
            m.solver = solver
            m.object = o
            bpy.context.view_layer.update()
            dg = bpy.context.evaluated_depsgraph_get()
            me = bpy.data.meshes.new_from_object(target.evaluated_get(dg))
            target.modifiers.clear()
            cleanup_mesh(me, dist=2e-4)
            results.append((non_manifold(me), solver, me))
            if results[-1][0] == 0:
                break
        results.sort(key=lambda r: r[0])
        old = target.data
        target.data = results[0][2]
        bpy.data.meshes.remove(old)
        for r in results[1:]:
            bpy.data.meshes.remove(r[2])
    for o in others:
        d = o.data
        bpy.data.objects.remove(o, do_unlink=True)
        if d.users == 0:
            bpy.data.meshes.remove(d)
    cleanup_mesh(target.data, dist=2e-4)
    return target


GEO = {}


def layer(name, geom_px, y_front, y_back, color, bevel=1.0, deepen=True, group="Panel"):
    """flat layer that lies on the panel; where it sticks out beyond the panel
    it is automatically made deeper (back to the panel/rim plane) so it reads
    as a solid object from the side and has something to glue to."""
    g = to_mm(geom_px) if geom_px.__class__.__name__ != "dict" else geom_px
    g = g.buffer(0)
    if g.is_empty:
        return None
    obj = extrude(g, y_front, y_back, name, bevel=bevel)
    if deepen:
        extra = []
        ins = min(bevel, (y_back - y_front) * 0.3) + 0.6
        out_panel = g.difference(GEO["panel"].buffer(0.6)).buffer(-ins).buffer(0)
        out_rim = g.difference(GEO["rim"].buffer(0.6)).buffer(-(ins + 0.5)).buffer(0)
        if out_panel.area > 4.0:
            extra.append(extrude(out_panel, y_front + 1.5, Y_PANEL_B, name + "_d1"))
        if out_rim.area > 4.0:
            extra.append(extrude(out_rim, y_front + 2.1, Y_RIM_B, name + "_d2"))
        if extra:
            boolean(obj, extra, "UNION")
    return register(obj, color, group)


# ----------------------------------------------------------------------------
# text
# ----------------------------------------------------------------------------
FONTS = {}


def font(fname):
    if fname not in FONTS:
        FONTS[fname] = bpy.data.fonts.load(os.path.join(FONT_DIR, fname), check_existing=True)
    return FONTS[fname]


def cap_ratio(fname):
    key = "cap_" + fname
    if key in FONTS:
        return FONTS[key]
    cu = bpy.data.curves.new("tmp", "FONT")
    cu.font = font(fname)
    cu.body = "H"
    cu.size = 1.0
    ob = bpy.data.objects.new("tmp", cu)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    zs = [v.co.y for v in me.vertices]
    FONTS[key] = max(zs) - min(zs)
    bpy.data.objects.remove(ob)
    bpy.data.curves.remove(cu)
    bpy.data.meshes.remove(me)
    return FONTS[key]


def text(name, body, fname, cap_px, center_px, y_front, depth, color, rot=0.0,
         max_w_px=None, bevel=0.5, spacing=1.0, group="Text"):
    cu = bpy.data.curves.new(name, "FONT")
    cu.font = font(fname)
    cu.body = body
    cu.size = cap_px * S / cap_ratio(fname)
    cu.space_character = spacing
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    cu.resolution_u = 5
    b = min(bevel, depth * 0.3)
    cu.extrude = depth / 2.0 - b
    cu.bevel_depth = b
    cu.bevel_resolution = 2
    cu.offset = -b * 0.9 if b > 0 else 0.0
    ob = bpy.data.objects.new(name + "_txt", cu)
    bpy.context.scene.collection.objects.link(ob)
    ob.rotation_euler = (math.pi / 2, 0, 0)
    bpy.context.view_layer.update()
    ob = bake_object(ob, name)
    me = ob.data
    xs = [v.co.x for v in me.vertices]
    zs = [v.co.z for v in me.vertices]
    w = max(xs) - min(xs)
    sc = 1.0
    if max_w_px and w > max_w_px * S:
        sc = max_w_px * S / w
    cx, cz = (max(xs) + min(xs)) / 2, (max(zs) + min(zs)) / 2
    tx, tz = px_to_world(*center_px)
    M = (Matrix.Translation((tx, y_front + depth / 2.0, tz)) @
         Matrix.Rotation(math.radians(rot), 4, "Y") @
         Matrix.Scale(sc, 4, (1, 0, 0)) @ Matrix.Scale(sc, 4, (0, 0, 1)) @
         Matrix.Translation((-cx, 0, -cz)))
    me.transform(M)
    return register(ob, color, group)


# ----------------------------------------------------------------------------
# primitives in 3D
# ----------------------------------------------------------------------------
def mesh_obj(name, bm):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def uv_sphere(name, center, r, seg=48, rings=24):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=rings, radius=r)
    bmesh.ops.translate(bm, verts=bm.verts, vec=Vector(center))
    return mesh_obj(name, bm)


def cylinder(name, p0, p1, r, seg=48):
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r, radius2=r, depth=d.length)
    rot = Vector((0, 0, 1)).rotation_difference(d.normalized()).to_matrix().to_4x4()
    bmesh.ops.transform(bm, matrix=Matrix.Translation((p0 + p1) / 2) @ rot, verts=bm.verts)
    return mesh_obj(name, bm)


def torus(name, center, axis, R, r, seg=96, rseg=20):
    bm = bmesh.new()
    verts = []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        ring = []
        for j in range(rseg):
            b = 2 * math.pi * j / rseg
            x = (R + r * math.cos(b)) * math.cos(a)
            y = (R + r * math.cos(b)) * math.sin(a)
            z = r * math.sin(b)
            ring.append(bm.verts.new((x, y, z)))
        verts.append(ring)
    for i in range(seg):
        for j in range(rseg):
            a, b = verts[i][j], verts[(i + 1) % seg][j]
            c, d = verts[(i + 1) % seg][(j + 1) % rseg], verts[i][(j + 1) % rseg]
            bm.faces.new((a, b, c, d))
    rot = Vector((0, 0, 1)).rotation_difference(Vector(axis).normalized()).to_matrix().to_4x4()
    bmesh.ops.transform(bm, matrix=Matrix.Translation(center) @ rot, verts=bm.verts)
    return mesh_obj(name, bm)


def rounded_box(name, x0, x1, y0, y1, z0, z1, bevel=2.0, segs=4):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.transform(bm, matrix=Matrix.Translation(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)) @
                        Matrix.Diagonal((x1 - x0, y1 - y0, z1 - z0, 1)), verts=bm.verts)
    if bevel > 0:
        bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bevel, segments=segs, profile=0.5,
                        affect="EDGES", clamp_overlap=True)
    return mesh_obj(name, bm)


def paraboloid_shell(name, center, normal, R, depth, thick, seg=96, rings=28):
    """dish: opening plane at `center`, bowl bulges along -normal, wall grows outward"""
    bm = bmesh.new()
    f = R * R / (4.0 * depth)

    def surf(rr, a, off):
        z = rr * rr / (4.0 * f) - depth           # 0 at rim, -depth at centre
        # outward normal of z = r^2/4f - d  is (-r/2f, 1)... offset towards back (-z)
        nx, nz = rr / (2 * f), -1.0
        ln = math.hypot(nx, nz)
        x = rr + off * nx / ln
        zz = z + off * nz / ln
        return (x * math.cos(a), x * math.sin(a), zz)

    inner, outer = [], []
    for k in range(rings + 1):
        rr = R * k / rings
        ri, ro = [], []
        cnt = 1 if k == 0 else seg
        for i in range(cnt):
            a = 2 * math.pi * i / seg
            ri.append(bm.verts.new(surf(rr, a, 0.0)))
            ro.append(bm.verts.new(surf(rr, a, thick)))
        inner.append(ri)
        outer.append(ro)
    for k in range(rings):
        for i in range(seg):
            j = (i + 1) % seg
            if k == 0:
                bm.faces.new((inner[0][0], inner[1][i], inner[1][j]))
                bm.faces.new((outer[0][0], outer[1][j], outer[1][i]))
            else:
                bm.faces.new((inner[k][i], inner[k + 1][i], inner[k + 1][j], inner[k][j]))
                bm.faces.new((outer[k][j], outer[k + 1][j], outer[k + 1][i], outer[k][i]))
    for i in range(seg):
        j = (i + 1) % seg
        bm.faces.new((inner[rings][i], outer[rings][i], outer[rings][j], inner[rings][j]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    rot = Vector((0, 0, 1)).rotation_difference(Vector(normal).normalized()).to_matrix().to_4x4()
    bmesh.ops.transform(bm, matrix=Matrix.Translation(center) @ rot, verts=bm.verts)
    return mesh_obj(name, bm)


# ============================================================================
#  BUILD
# ============================================================================
def reset_scene():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)
    for blk in (bpy.data.meshes, bpy.data.curves, bpy.data.materials, bpy.data.cameras,
                bpy.data.lights):
        for d in list(blk):
            blk.remove(d)
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.scale_length = 0.001
    sc.unit_settings.length_unit = "MILLIMETERS"


def tapered_block(name, cx, cy, z0, z1, wx0, wy0, wx1, wy1, bevel=1.5):
    """box whose bottom is wx0 x wy0 and top wx1 x wy1 (trapezoid stand)"""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        top = v.co.z > 0
        wx, wy = (wx1, wy1) if top else (wx0, wy0)
        v.co = Vector((cx + v.co.x * wx, cy + v.co.y * wy, z1 if top else z0))
    if bevel > 0:
        bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bevel, segments=3, profile=0.5,
                        affect="EDGES", clamp_overlap=True)
    return mesh_obj(name, bm)


def squash_y(obj, y_pivot, k):
    obj.data.transform(Matrix.Translation((0, y_pivot, 0)) @ Matrix.Diagonal((1, k, 1, 1)) @
                       Matrix.Translation((0, -y_pivot, 0)))


def build():
    global S
    D = design()

    # scale so that  base bottom -> top of cloud outline == TOTAL_HEIGHT
    top_px = min(g.bounds[1] for g in (D["cloud_out"], D["tower_waves"], D["rim"]))
    S = (TOTAL_HEIGHT - BASE_H) / (PX_PANEL_BOTTOM - top_px)
    print("scale: %.5f mm/px" % S)

    GEO["panel"] = to_mm(D["panel"]).intersection(box(-5000, BASE_H - SLOT_DEPTH, 5000, 5000))
    GEO["rim"] = to_mm(D["rim"]).intersection(box(-5000, BASE_H - SLOT_DEPTH, 5000, 5000))

    # ---------------- panel + rim --------------------------------------
    register(extrude(GEO["rim"], Y_RIM_F, Y_RIM_B, "Rim_LightBlue", bevel=1.5), "SkyBlue", "Panel")
    register(extrude(GEO["panel"], Y_PANEL_F, Y_PANEL_B, "Panel_Navy", bevel=1.2), "Navy", "Panel")

    # ---------------- main cloud + title -------------------------------
    layer("Cloud_Outline", D["cloud_out"], -20, Y_PANEL_F, "SkyBlue", bevel=1.5, group="Cloud")
    layer("Cloud_White", D["cloud_white"], -25, -20, "White", bevel=1.5, deepen=False, group="Cloud")
    layer("Cloud_Waves", D["cloud_waves"], -29, -25, "DarkNavy", bevel=0.9, deepen=False, group="Cloud")
    text("Title_Mobile", "Mobile", "Nunito-ExtraBold.ttf", 74, (742, 208), -30, 5.0, "DarkNavy",
         bevel=0.8, group="Cloud")
    text("Title_Communications", "Communications", "Nunito-ExtraBold.ttf", 76, (836, 306), -30, 5.0,
         "DarkNavy", max_w_px=664, bevel=0.8, group="Cloud")

    # ---------------- tower --------------------------------------------
    # light backing triangle inside the lattice, lattice on top of it
    layer("Tower_Fill", D["tower_fill"], -13, Y_PANEL_F, "CardFill", bevel=0.8, group="Tower")
    tower = layer("Tower_Black", D["tower"], -22, -13, "Black", bevel=1.0, deepen=False, group="Tower")
    bx, by, br = D["tower_ball"]
    wx, wz = px_to_world(bx, by)
    ball = uv_sphere("ball", (0, 0, 0), br * S)
    ball.data.transform(Matrix.Translation((wx, -19.0, wz)) @ Matrix.Diagonal((1, 0.5, 1, 1)))
    stem = cylinder("stem", (wx, -12.0, wz), (wx, Y_BACKER_F, wz), br * S * 0.78)
    boolean(tower, [ball, stem], "UNION")
    layer("Tower_Waves", D["tower_waves"], -18, Y_PANEL_F, "SkyBlue", bevel=1.2, group="Tower")

    # clear backer that holds the free-standing arcs / tower top
    tw_mm = to_mm(union(D["tower_waves"], D["tower_fill"], circle(bx, by, br)))
    panel_top_z = Z0 + (PX_PANEL_BOTTOM - D["panel_top_px"]) * S
    hull = tw_mm.intersection(box(-5000, panel_top_z - 30, 5000, 5000)).convex_hull.buffer(7, quad_segs=QS)
    backer = hull.intersection(box(-5000, panel_top_z - 28, 5000, 5000))
    register(extrude(backer, Y_BACKER_F, Y_BACKER_B, "Backer_Clear", bevel=0.8), "Clear", "Tower")

    # ---------------- stay connected cloud ----------------------------
    layer("Stay_Outline", D["stay_out"], -22, Y_PANEL_F, "SkyBlue", bevel=1.4, group="StayCloud")
    layer("Stay_White", D["stay_white"], -26, -22, "White", bevel=1.2, deepen=False, group="StayCloud")
    text("Stay_Text1", "Stay", "Nunito-ExtraBold.ttf", 34, (350, 602), -29.5, 3.5, "Ink", bevel=0.5,
         group="StayCloud")
    text("Stay_Text2", "Connected", "Nunito-ExtraBold.ttf", 33, (352, 651), -29.5, 3.5, "Ink", max_w_px=236,
         bevel=0.5, group="StayCloud")
    layer("Stay_Heart", D["heart"], -29.5, -26, "DarkNavy", bevel=0.6, deepen=False, group="StayCloud")

    # ---------------- phone -------------------------------------------
    layer("Phone_Body", D["phone_body"], -32, Y_PANEL_F, "Black", bevel=3.0, group="Phone")
    layer("Phone_Screen", D["phone_screen"], -34, -32, "Screen", bevel=0.6, deepen=False, group="Phone")
    layer("Phone_Speaker", union(D["phone_speaker"], D["phone_home"]), -33.2, -32, "DarkGrey",
          bevel=0.4, deepen=False, group="Phone")
    layer("Phone_Bars", D["phone_bars"], -36.5, -34, "Signal", bevel=0.6, deepen=False, group="Phone")
    layer("Phone_Handset", D["phone_handset"], -36.5, -34, "DarkNavy", bevel=0.6, deepen=False,
          group="Phone")
    text("Phone_5G", "5G", "Nunito-Black.ttf", 82, D["phone_5g"]["center"], -37.0, 3.0, "Signal",
         rot=D["phone_5g"]["rot"], bevel=0.6, group="Phone")

    # ---------------- stars + bars ------------------------------------
    layer("Stars", D["stars"], -14, Y_PANEL_F, "White", bevel=0.8, deepen=False, group="Panel")
    layer("Signal_Bars", D["bars"], -18, Y_PANEL_F, "SkyBlue", bevel=1.2, deepen=False, group="Panel")

    # ---------------- cards -------------------------------------------
    for i, c in enumerate(D["cards"]):
        n = i + 1
        layer("Card%d_Outline" % n, c["out"], -18, Y_PANEL_F, "SkyBlue", bevel=1.2, group="Cards")
        layer("Card%d_Fill" % n, c["fill"], -22, -18, "CardFill", bevel=1.0, deepen=False, group="Cards")
        l1, l2 = D["card_text"][i]
        cap = 25 if i != 1 else 22
        text("Card%d_Text1" % n, l1, "Roboto-Medium.ttf", cap, (1102, c["cy"] - 19), -24.5, 2.5, "Ink",
             max_w_px=178, bevel=0.35, group="Cards")
        text("Card%d_Text2" % n, l2, "Roboto-Medium.ttf", cap, (1102, c["cy"] + 18), -24.5, 2.5, "Ink",
             max_w_px=178, bevel=0.35, group="Cards")
    layer("Card1_Icon", D["icon_station"], -25, -22, "DarkNavy", bevel=0.4, deepen=False, group="Cards")
    layer("Card1_IconWaves", D["icon_station_waves"], -25, -22, "SkyBlue", bevel=0.4, deepen=False,
          group="Cards")
    layer("Card2_Icon", union(D["icon_sat"], D["icon_sat_waves"]), -25, -22, "DarkNavy", bevel=0.4,
          deepen=False, group="Cards")
    layer("Card2_IconPanels", D["icon_sat_panels"], -25, -22, "SkyBlue", bevel=0.4, deepen=False,
          group="Cards")
    layer("Card3_Icon", D["icon_cell"], -25, -22, "DarkNavy", bevel=0.4, deepen=False, group="Cards")
    layer("Card4_Icon", D["icon_globe"], -25, -22, "DarkNavy", bevel=0.4, deepen=False, group="Cards")

    # ---------------- satellite dish (real 3D paraboloid) -------------
    # built as a true dish, then pressed to 55 % depth (relief) so it stays
    # compact in front of the panel - the front view is unchanged.
    K = 0.55
    n = Vector((0.525, -0.51, 0.68)).normalized()
    dcx, dcz = px_to_world(333, 850)
    C = Vector((dcx, -84.0, dcz))
    R, DEPTH, TH, RIM_R = 78.0, 20.0, 3.5, 4.6
    dish_objs = []
    bowl = paraboloid_shell("Dish_Bowl", C, n, R, DEPTH, TH)
    rim_c = C - n * 0.8
    rim_cut = torus("rim_cut", rim_c, n, R + 1.0, RIM_R + 0.15)
    bowl_bottom = C - n * DEPTH
    feed_end = C + n * 43.0
    arm_cut = cylinder("arm_cut", bowl_bottom - n * 10, bowl_bottom + n * 6, 3.4)
    boolean(bowl, [rim_cut, arm_cut], "DIFFERENCE")
    dish_objs.append((bowl, "Grey"))
    rim = torus("Dish_Rim_White", rim_c, n, R + 1.0, RIM_R)
    dish_objs.append((rim, "White"))
    arm = cylinder("Dish_Feed_Arm", bowl_bottom - n * (TH + 2.0), feed_end, 3.2, seg=32)
    dish_objs.append((arm, "DarkGrey"))
    fball = uv_sphere("Dish_Feed_Ball", feed_end + n * 6.0, 8.0)
    arm_c2 = cylinder("arm_cut2", feed_end - n * 2, feed_end + n * 3, 3.25, seg=32)
    boolean(fball, [arm_c2], "DIFFERENCE")
    dish_objs.append((fball, "White"))
    # mount: hub behind the bowl + yoke + post
    hub0 = bowl_bottom - n * (TH - 0.6)
    hub1 = bowl_bottom - n * (TH + 15.0)
    hub = cylinder("Dish_Mount", hub0, hub1, 13.0)
    block_top = BASE_H + 12.0 + 26.0
    post = rounded_box("post", hub1.x - 11, hub1.x + 11, hub1.y - 10, hub1.y + 10, block_top - 6.0,
                       hub1.z + 4, 2.0)
    yoke = rounded_box("yoke", hub1.x - 19, hub1.x + 19, hub1.y - 9, hub1.y + 9, hub1.z - 12,
                       hub1.z + 6, 2.5)
    boolean(hub, [post, yoke], "UNION")
    arm_c3 = cylinder("arm_cut3", bowl_bottom - n * (TH + 2.2), bowl_bottom + n * 2, 3.45, seg=32)
    boolean(hub, [arm_c3], "DIFFERENCE")
    bowl_cut = bowl.copy()
    bowl_cut.data = bowl.data.copy()
    bpy.context.scene.collection.objects.link(bowl_cut)
    boolean(hub, [bowl_cut], "DIFFERENCE")      # hub follows the curved back of the dish
    dish_objs.append((hub, "DarkGrey"))
    for ob, col in dish_objs:
        squash_y(ob, Y_PANEL_F - 1.0, K)
    # stand: dark trapezoid block + light grey plate (not squashed)
    sx_ = hub1.x
    sy_ = Y_PANEL_F - 1.0 + (hub1.y - (Y_PANEL_F - 1.0)) * K
    block = tapered_block("Dish_Stand", sx_, sy_, BASE_H + 12.0, block_top, 66, 40, 44, 28)
    # post sits in the trapezoid block: one dark grey part
    boolean(hub, [block], "UNION")
    plate = rounded_box("Dish_Plate", sx_ - 53, sx_ + 53, sy_ - 30, Y_PANEL_F - 0.5, BASE_H,
                        BASE_H + 12.0, 3.0)
    dish_objs.append((plate, "Grey"))
    for ob, col in dish_objs:
        cleanup_mesh(ob.data)
        register(ob, col, "Dish")
    # small blue waves next to the feed (flat on the panel)
    fe = feed_end + n * 6.0
    print("feed ball px: %.0f %.0f" % (fe.x / S + PX_CX, PX_PANEL_BOTTOM - (fe.z - Z0) / S))
    dwaves = union(*[arc(398, 806, r, -88, -8, 10) for r in (26, 46, 66)])
    layer("Dish_Waves", dwaves, -16, Y_PANEL_F, "SkyBlue", bevel=0.8, deepen=False, group="Dish")

    # ---------------- wooden base -------------------------------------
    bx0, _ = px_to_world(110, 0)
    bx1, _ = px_to_world(1246, 0)
    base = rounded_box("Base_Wood", bx0, bx1, -165.0, 28.0, 0.0, BASE_H, 2.5)
    pxmin, _, pxmax, _ = GEO["rim"].bounds
    slot = rounded_box("slot", pxmin - 0.3, pxmax + 0.3, Y_PANEL_F - 0.25, Y_RIM_B + 0.25,
                       BASE_H - SLOT_DEPTH - 0.3, BASE_H + 5, 0.0)
    boolean(base, [slot], "DIFFERENCE")
    register(base, "Wood", "Base")
    return D


# ============================================================================
#  checks, preview scene, export
# ============================================================================
def report():
    lines = []
    bad = 0
    for ob, color, group in PARTS:
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        nm = sum(1 for e in bm.edges if len(e.link_faces) != 2)
        bm.free()
        dims = ob.dimensions
        if nm:
            bad += 1
        lines.append((ob.name, color, group, dims.x, dims.z, dims.y, len(ob.data.polygons), nm))
    print("\n%-26s %-9s %-9s %8s %8s %8s %8s %s" % ("part", "color", "group", "W", "H", "D", "tris", "nonmanifold"))
    for l in lines:
        print("%-26s %-9s %-9s %8.1f %8.1f %8.1f %8d %d" % l)
    zmin = min(min((ob.matrix_world @ Vector(c)).z for c in ob.bound_box) for ob, _, _ in PARTS)
    zmax = max(max((ob.matrix_world @ Vector(c)).z for c in ob.bound_box) for ob, _, _ in PARTS)
    xmin = min(min((ob.matrix_world @ Vector(c)).x for c in ob.bound_box) for ob, _, _ in PARTS)
    xmax = max(max((ob.matrix_world @ Vector(c)).x for c in ob.bound_box) for ob, _, _ in PARTS)
    print("\nTOTAL  height %.1f mm   width %.1f mm   parts %d   non-manifold parts %d" %
          (zmax - zmin, xmax - xmin, len(PARTS), bad))
    return lines, (zmax - zmin, xmax - xmin)


def preview_scene():
    c = coll("PREVIEW_SCENE (not for print)")
    sc = bpy.context.scene

    def add(ob):
        for cc in ob.users_collection:
            cc.objects.unlink(ob)
        c.objects.link(ob)
        return ob

    wall_m = bpy.data.materials.new("PV_Wall")
    wall_m.use_nodes = True
    wall_m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (*hex_rgb("#EDEBE6"), 1)
    wall_m.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.9
    tab_m = bpy.data.materials.new("PV_Table")
    tab_m.use_nodes = True
    tab_m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (*hex_rgb("#F3F0EA"), 1)
    wall = rounded_box("PV_Wall", -1500, 1500, 60, 80, -20, 1800, 0)
    wall.data.materials.append(wall_m)
    table = rounded_box("PV_Table", -1500, 1500, -1200, 80, -20, 0, 0)
    table.data.materials.append(tab_m)
    add(wall)
    add(table)

    cam_d = bpy.data.cameras.new("Camera")
    cam_d.lens = 70
    cam_d.clip_start, cam_d.clip_end = 5.0, 20000.0
    cam = bpy.data.objects.new("Camera_Front", cam_d)
    add_target = Vector((0, 0, 300))
    cam.location = Vector((25, -1650, 420))
    cam.rotation_euler = (add_target - cam.location).to_track_quat("-Z", "Y").to_euler()
    c.objects.link(cam)
    sc.camera = cam

    cam_d2 = bpy.data.cameras.new("Camera34")
    cam_d2.lens = 60
    cam_d2.clip_start, cam_d2.clip_end = 5.0, 20000.0
    cam2 = bpy.data.objects.new("Camera_3_4", cam_d2)
    cam2.location = Vector((-950, -1350, 620))
    cam2.rotation_euler = (Vector((0, -20, 290)) - cam2.location).to_track_quat("-Z", "Y").to_euler()
    c.objects.link(cam2)

    for nm, loc, e, size in [("Key", (-700, -900, 1100), 2.2e6, 900), ("Fill", (900, -800, 500), 0.9e6, 900),
                             ("Top", (0, -300, 1400), 0.8e6, 700)]:
        ld = bpy.data.lights.new(nm, "AREA")
        ld.energy = e
        ld.size = size
        lo = bpy.data.objects.new("Light_" + nm, ld)
        lo.location = loc
        lo.rotation_euler = (Vector((0, 0, 300)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        c.objects.link(lo)
    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    sc.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.8, 0.8, 0.82, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.35

    sc.render.engine = "CYCLES"
    sc.cycles.samples = 64
    sc.cycles.use_denoising = True
    sc.render.resolution_x = 1280
    sc.render.resolution_y = 1170
    sc.view_settings.view_transform = "AgX" if "AgX" in [i.identifier for i in
                                                          sc.view_settings.bl_rna.properties["view_transform"].enum_items] else "Filmic"


def split_piece_bounds(lo, hi, maxlen, shift_frac):
    L = hi - lo
    n = max(1, math.ceil(L / maxlen))
    if n == 1:
        return [(lo, hi)]
    step = L / n
    shift = min(abs(shift_frac) * step, maxlen - step) * (1 if shift_frac >= 0 else -1)
    cuts = [lo + step * i + shift for i in range(1, n)]
    edges = [lo] + cuts + [hi]
    return list(zip(edges[:-1], edges[1:]))


def world_bounds(ob):
    bb = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    return ([min(v[i] for v in bb) for i in range(3)], [max(v[i] for v in bb) for i in range(3)])


def mesh_islands(ob):
    """split a mesh object into its loose parts (letters, stars...)"""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.faces.ensure_lookup_table()
    seen, comps = set(), []
    for f in bm.faces:
        if f.index in seen:
            continue
        stack, comp = [f], set()
        seen.add(f.index)
        while stack:
            x = stack.pop()
            comp.add(x.index)
            for e in x.edges:
                for g2 in e.link_faces:
                    if g2.index not in seen:
                        seen.add(g2.index)
                        stack.append(g2)
        comps.append(comp)
    out = []
    for i, comp in enumerate(comps):
        b2 = bm.copy()
        b2.faces.ensure_lookup_table()
        bmesh.ops.delete(b2, geom=[f for f in b2.faces if f.index not in comp], context="FACES")
        bmesh.ops.delete(b2, geom=[v for v in b2.verts if not v.link_faces], context="VERTS")
        me = bpy.data.meshes.new(ob.name + "_isl%d" % i)
        b2.to_mesh(me)
        b2.free()
        o = bpy.data.objects.new(me.name, me)
        o.matrix_world = ob.matrix_world.copy()
        bpy.context.scene.collection.objects.link(o)
        out.append(o)
    bm.free()
    return out


def bed_pieces(ob, k):
    """-> list of temporary objects, each fitting the print bed.
    Flat layers are printed lying on their back, so the footprint is X x Z
    (X x Y for the wooden base). Separate islands (letters, stars) are grouped
    whole; only an island that is itself too big gets cut - with cut lines
    staggered between neighbouring layers so seams never line up."""
    ax_b = 1 if ob.name.startswith("Base") else 2
    (lo, hi) = world_bounds(ob)
    if hi[0] - lo[0] <= BED and hi[ax_b] - lo[ax_b] <= BED:
        return None
    islands = mesh_islands(ob)
    small, big = [], []
    for o in islands:
        a, b = world_bounds(o)
        (small if (b[0] - a[0] <= BED and b[ax_b] - a[ax_b] <= BED) else big).append((o, a, b))
    pieces = []
    # group small islands greedily from left to right
    small.sort(key=lambda t: (t[1][0], t[1][ax_b]))
    groups = []
    for o, a, b in small:
        for gp in groups:
            ga = [min(gp["a"][i], a[i]) for i in range(3)]
            gb = [max(gp["b"][i], b[i]) for i in range(3)]
            if gb[0] - ga[0] <= BED and gb[ax_b] - ga[ax_b] <= BED:
                gp["objs"].append(o)
                gp["a"], gp["b"] = ga, gb
                break
        else:
            groups.append(dict(objs=[o], a=a, b=b))
    for gp in groups:
        base_o = gp["objs"][0]
        if len(gp["objs"]) > 1:
            bm = bmesh.new()
            for o in gp["objs"]:
                bm.from_mesh(o.data)
            bm.to_mesh(base_o.data)
            bm.free()
            for o in gp["objs"][1:]:
                d = o.data
                bpy.data.objects.remove(o, do_unlink=True)
                bpy.data.meshes.remove(d)
        pieces.append(base_o)
    # cut big islands
    sa = 0.3 * (1 if k % 2 else -1)
    for o, a, b in big:
        ra = split_piece_bounds(a[0] - 1, b[0] + 1, BED - 2, sa)
        rb = split_piece_bounds(a[ax_b] - 1, b[ax_b] + 1, BED - 2, -sa)
        for (a0, a1) in ra:
            for (b0, b1) in rb:
                cp = o.copy()
                cp.data = o.data.copy()
                bpy.context.scene.collection.objects.link(cp)
                if ax_b == 2:
                    bx = rounded_box("cutbox", a0, a1, a[1] - 5, b[1] + 5, b0, b1, 0)
                else:
                    bx = rounded_box("cutbox", a0, a1, b0, b1, a[2] - 5, b[2] + 5, 0)
                boolean(cp, [bx], "INTERSECT")
                if len(cp.data.polygons):
                    pieces.append(cp)
                else:
                    d = cp.data
                    bpy.data.objects.remove(cp, do_unlink=True)
                    bpy.data.meshes.remove(d)
        d = o.data
        bpy.data.objects.remove(o, do_unlink=True)
        bpy.data.meshes.remove(d)
    return pieces


def export_all(out_dir):
    full = os.path.join(out_dir, "stl_full_size")
    split = os.path.join(out_dir, "stl_split_256mm_bed")
    for d in (full, split):
        os.makedirs(d, exist_ok=True)
        for f in os.listdir(d):
            if f.endswith(".stl"):
                os.remove(os.path.join(d, f))

    def export(objs, path):
        bpy.ops.object.select_all(action="DESELECT")
        for o in objs:
            o.select_set(True)
        bpy.context.view_layer.objects.active = objs[0]
        bpy.ops.wm.stl_export(filepath=path, export_selected_objects=True, global_scale=1.0,
                              use_scene_unit=False, ascii_format=False, apply_modifiers=True)

    rows = []
    for k, (ob, color, group) in enumerate(PARTS):
        fn = "%02d_%s__%s.stl" % (k + 1, ob.name, color)
        export([ob], os.path.join(full, fn))
        lo, hi = world_bounds(ob)
        pcs = bed_pieces(ob, k)
        if pcs is None:
            export([ob], os.path.join(split, fn))
            n_p = 1
        else:
            for i, cp in enumerate(pcs):
                export([cp], os.path.join(split, fn.replace(".stl", "_piece%d.stl" % (i + 1))))
                d = cp.data
                bpy.data.objects.remove(cp, do_unlink=True)
                bpy.data.meshes.remove(d)
            n_p = len(pcs)
        rows.append((k + 1, ob.name, color, COLORS[color][1], hi[0] - lo[0], hi[2] - lo[2], hi[1] - lo[1],
                     n_p, fn))
    return rows


def write_parts_list(rows, total, path):
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Parts list / قائمة القطع\n\n")
        f.write("Total height: **%.1f mm**  ·  total width: **%.1f mm**  ·  parts: **%d**\n\n" %
                (total[0], total[1], len(rows)))
        f.write("| # | Part | Colour | Filament | W (mm) | H (mm) | Depth (mm) | Pieces (256 bed) |\n")
        f.write("|---|------|--------|----------|-------:|-------:|-----------:|-----------------:|\n")
        for r in rows:
            f.write("| %d | `%s` | %s | %s | %.1f | %.1f | %.1f | %d |\n" % r[:8])
        f.write("\n## Colours\n\n| Key | Hex | Filament |\n|---|---|---|\n")
        for k, (hx, desc) in COLORS.items():
            f.write("| %s | `%s` | %s |\n" % (k, hx, desc))


def main():
    reset_scene()
    make_materials()
    build()
    lines, total = report()
    preview_scene()
    out_dir = BASE_DIR
    if DO_EXPORT:
        rows = export_all(out_dir)
        write_parts_list(rows, total, os.path.join(out_dir, "PARTS.md"))
    if DO_SAVE:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out_dir, "mobile_communications_sign.blend"),
                                    compress=True)
    if DO_RENDER:
        sc = bpy.context.scene
        os.makedirs(os.path.join(out_dir, "renders"), exist_ok=True)
        for camname, fn in [("Camera_Front", "preview_front.png"), ("Camera_3_4", "preview_3_4.png")]:
            sc.camera = bpy.data.objects[camname]
            sc.render.filepath = os.path.join(out_dir, "renders", fn)
            bpy.ops.render.render(write_still=True)
        sc.camera = bpy.data.objects["Camera_Front"]


if __name__ == "__main__":
    main()
