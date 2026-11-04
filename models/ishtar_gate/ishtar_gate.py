"""
Ishtar Gate diorama - procedural Blender model, built for 3D printing.

Run inside Blender (Scripting tab -> Open -> Run Script), or headless:
    blender --background --python ishtar_gate.py
    python ishtar_gate.py            (with the `bpy` pip module)

Units: 1 Blender unit = 1 mm. Overall size about 240 x 130 x 90 mm.
Every part is a closed (watertight) mesh. Each object carries a "grp"
custom property naming its print colour; export_stl.py uses it to write
one STL per colour (for multi-colour printers) and a merged STL.
"""

import math
import random

import bmesh
import bpy
from mathutils import Vector
from mathutils.geometry import tessellate_polygon

random.seed(7)

# ---------------------------------------------------------------------------
# Scene / materials
# ---------------------------------------------------------------------------

COLORS = {
    # name: (RGBA, metallic, roughness)
    "BLUE":   ((0.020, 0.045, 0.30, 1), 0.0, 0.35),   # lapis glazed walls
    "PANEL":  ((0.012, 0.025, 0.20, 1), 0.0, 0.25),   # smooth animal panels
    "GOLD":   ((0.80, 0.56, 0.12, 1), 0.85, 0.30),
    "WHITE":  ((0.85, 0.85, 0.82, 1), 0.0, 0.40),
    "SAND":   ((0.55, 0.42, 0.22, 1), 0.35, 0.45),    # plaza floor / kerbs
    "GRASS":  ((0.03, 0.35, 0.03, 1), 0.0, 0.80),
    "STONE":  ((0.42, 0.42, 0.44, 1), 0.0, 0.70),     # central path
    "TRUNK":  ((0.22, 0.12, 0.05, 1), 0.0, 0.80),
    "LEAF":   ((0.04, 0.42, 0.10, 1), 0.0, 0.50),
    "PEOPLE": ((0.80, 0.30, 0.25, 1), 0.0, 0.50),
}

# Which group wins where two colours overlap (higher index = higher priority).
PRIORITY = ["BLUE", "SAND", "PANEL", "GOLD", "STONE", "GRASS", "TRUNK",
            "LEAF", "WHITE", "DOTS", "PEOPLE"]


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.scale_length = 0.001
    sc.unit_settings.length_unit = "MILLIMETERS"


MATS = {}


def make_materials():
    for name, (rgba, metal, rough) in COLORS.items():
        m = bpy.data.materials.new("IG_" + name)
        m.use_nodes = True
        b = m.node_tree.nodes.get("Principled BSDF")
        b.inputs["Base Color"].default_value = rgba
        b.inputs["Metallic"].default_value = metal
        b.inputs["Roughness"].default_value = rough
        m.diffuse_color = rgba
        MATS[name] = m
    MATS["DOTS"] = MATS["BLUE"]


COLL = {}


def coll(name):
    if name not in COLL:
        c = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(c)
        COLL[name] = c
    return COLL[name]


def new_obj(name, bm, grp, collection="Gate", smooth=False):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    if smooth:
        me.shade_smooth()
    ob = bpy.data.objects.new(name, me)
    ob["grp"] = grp
    me.materials.append(MATS[grp])
    coll(collection).objects.link(ob)
    return ob


# ---------------------------------------------------------------------------
# Primitive builders (all closed manifolds)
# ---------------------------------------------------------------------------

def bm_box(bm, x0, x1, y0, y1, z0, z1):
    v = [bm.verts.new(p) for p in (
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1))]
    for f in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
              (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
        bm.faces.new([v[i] for i in f])


def box(name, grp, x0, x1, y0, y1, z0, z1, collection="Gate"):
    bm = bmesh.new()
    bm_box(bm, min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1),
           min(z0, z1), max(z0, z1))
    return new_obj(name, bm, grp, collection)


def bm_cyl(bm, center, axis, r, length, seg=10):
    """Cylinder whose base centre is `center`, extruded `length` along `axis`."""
    axis = Vector(axis).normalized()
    t = axis.orthogonal().normalized()
    b = axis.cross(t)
    c = Vector(center)
    lo, hi = [], []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        p = c + (t * math.cos(a) + b * math.sin(a)) * r
        lo.append(bm.verts.new(p))
        hi.append(bm.verts.new(p + axis * length))
    bm.faces.new(lo[::-1])
    bm.faces.new(hi)
    for i in range(seg):
        j = (i + 1) % seg
        bm.faces.new((lo[i], lo[j], hi[j], hi[i]))


def bm_prism(bm, pts2d, origin, u, v, w, depth):
    """Extrude a 2D polygon (in the u,v plane at origin) along w by depth."""
    o, u, v, w = Vector(origin), Vector(u), Vector(v), Vector(w)
    # force counter-clockwise
    area = sum(pts2d[i][0] * pts2d[(i + 1) % len(pts2d)][1] -
               pts2d[(i + 1) % len(pts2d)][0] * pts2d[i][1]
               for i in range(len(pts2d)))
    if area < 0:
        pts2d = pts2d[::-1]
    lo = [bm.verts.new(o + u * x + v * y) for x, y in pts2d]
    hi = [bm.verts.new(o + u * x + v * y + w * depth) for x, y in pts2d]
    # robust triangulation of concave outlines (animal silhouettes)
    tris = tessellate_polygon([[Vector((x, y, 0)) for x, y in pts2d]])
    for t in tris:
        bm.faces.new([lo[i] for i in t])
        bm.faces.new([hi[i] for i in t])
    n = len(pts2d)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((lo[i], lo[j], hi[j], hi[i]))


def ribbed_box(name, x0, x1, y0, y1, z0, z1, pitch=1.25, gh=0.55,
               depth=0.32, margin=1.2, grp="BLUE", collection="Gate"):
    """Box with horizontal grooves on all four walls - the corrugated
    'glazed brick course' look of the original model."""
    bm = bmesh.new()

    def ring(z, d):
        return [bm.verts.new(p) for p in (
            (x0 + d, y0 + d, z), (x1 - d, y0 + d, z),
            (x1 - d, y1 - d, z), (x0 + d, y1 - d, z))]

    # walls standing on the floor sink 0.5 mm into it so they fuse solidly
    rings = [ring(z0 - 0.5 if z0 == 0 else z0, 0)]
    z = z0 + margin
    while z + gh < z1 - margin:
        rings.append(ring(z, 0))
        rings.append(ring(z, depth))
        rings.append(ring(z + gh, depth))
        rings.append(ring(z + gh, 0))
        z += pitch
    rings.append(ring(z1, 0))
    bm.faces.new(rings[0][::-1])
    bm.faces.new(rings[-1])
    for a, b in zip(rings, rings[1:]):
        for i in range(4):
            j = (i + 1) % 4
            bm.faces.new((a[i], a[j], b[j], b[i]))
    return new_obj(name, bm, grp, collection)


def boolean(target, cutter, op="DIFFERENCE"):
    m = target.modifiers.new("bool", "BOOLEAN")
    m.operation = op
    m.solver = "EXACT"
    m.object = cutter
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    old = target.data
    me = bpy.data.meshes.new_from_object(target.evaluated_get(dg))
    target.modifiers.clear()
    target.data = me
    me.name = old.name
    bpy.data.meshes.remove(old)


def delete(ob):
    bpy.data.objects.remove(ob, do_unlink=True)


# ---------------------------------------------------------------------------
# Decorative elements
# ---------------------------------------------------------------------------

def band_ring(name, bx, z0, z1, proud=0.55, dots=True, dot_pitch=2.3,
              sides="NSEW", collection="Gate"):
    """Gold band wrapped round a block footprint bx=(x0,x1,y0,y1), with
    small square lapis 'rosette' dots (like the painted model)."""
    x0, x1, y0, y1 = bx
    inset = 0.45
    bm = bmesh.new()
    e = proud
    if "S" in sides:
        bm_box(bm, x0 - e, x1 + e, y0 - e, y0 + inset, z0, z1)
    if "N" in sides:
        bm_box(bm, x0 - e, x1 + e, y1 - inset, y1 + e, z0, z1)
    # side runs stop where the front/back runs begin (no coplanar overlap)
    wy0 = y0 + inset if "S" in sides else y0 - e
    wy1 = y1 - inset if "N" in sides else y1 + e
    if "W" in sides:
        bm_box(bm, x0 - e, x0 + inset, wy0, wy1, z0, z1)
    if "E" in sides:
        bm_box(bm, x1 - inset, x1 + e, wy0, wy1, z0, z1)
    gold = new_obj(name, bm, "GOLD", collection)
    if not dots:
        return gold
    s = min(0.75, (z1 - z0) * 0.42)
    zc = (z0 + z1) / 2
    bm = bmesh.new()
    out = e + 0.12

    def run(a0, a1, fn):
        n = max(1, int((a1 - a0) / dot_pitch))
        step = (a1 - a0) / n
        for k in range(n):
            fn(a0 + step * (k + 0.5))
    if "S" in sides:
        run(x0, x1, lambda a: bm_box(bm, a - s / 2, a + s / 2, y0 - out,
                                     y0 - e + 0.25, zc - s / 2, zc + s / 2))
    if "N" in sides:
        run(x0, x1, lambda a: bm_box(bm, a - s / 2, a + s / 2, y1 + e - 0.25,
                                     y1 + out, zc - s / 2, zc + s / 2))
    if "W" in sides:
        run(y0, y1, lambda a: bm_box(bm, x0 - out, x0 - e + 0.25, a - s / 2,
                                     a + s / 2, zc - s / 2, zc + s / 2))
    if "E" in sides:
        run(y0, y1, lambda a: bm_box(bm, x1 + e - 0.25, x1 + out, a - s / 2,
                                     a + s / 2, zc - s / 2, zc + s / 2))
    new_obj(name + "_dots", bm, "DOTS", collection)
    return gold


def front_strip(name, grp, x0, x1, z0, z1, y, proud, collection="Gate"):
    """Flat strip on a south-facing wall at plane y (wall body is y>=y)."""
    return box(name, grp, x0, x1, y - proud, y + 0.45, z0, z1, collection)


def rosette_band_front(name, x0, x1, z0, z1, y, collection="Gate"):
    """Gold-edged lapis band with white rosettes, on a front wall at plane y."""
    front_strip(name, "GOLD", x0, x1, z0, z1, y, 0.55, collection)
    h = z1 - z0
    bm = bmesh.new()
    bm_box(bm, x0, x1, y - 0.62, y + 0.2, z0 + h * 0.2, z1 - h * 0.2)
    new_obj(name + "_blue", bm, "DOTS", collection)
    r = h * 0.24
    n = max(1, int((x1 - x0) / (h * 0.95)))
    step = (x1 - x0) / n
    bm = bmesh.new()
    for k in range(n):
        bm_cyl(bm, (x0 + step * (k + 0.5), y + 0.1, (z0 + z1) / 2),
               (0, -1, 0), r, 0.1 + 0.9, seg=10)
    new_obj(name + "_ros", bm, "WHITE", collection)


def frame_front(name, x0, x1, z0, z1, y, w=1.4, proud=0.6,
                collection="Gate", grp="GOLD"):
    bm = bmesh.new()
    for (a0, a1, b0, b1) in ((x0, x1, z0, z0 + w), (x0, x1, z1 - w, z1),
                             (x0, x0 + w, z0 + w, z1 - w),
                             (x1 - w, x1, z0 + w, z1 - w)):
        bm_box(bm, a0, a1, y - proud, y + 0.45, b0, b1)
    return new_obj(name, bm, grp, collection)


def stepped_merlon(bm, cx, cy, along_x, w, h, t, z0, steps=3):
    """Babylonian stepped (ziggurat) crenel."""
    for s in range(steps):
        ww = w * (steps - s) / steps
        hz0 = z0 + h * s / steps
        hz1 = z0 + h * (s + 1) / steps
        if along_x:
            bm_box(bm, cx - ww / 2, cx + ww / 2, cy - t / 2, cy + t / 2, hz0, hz1)
        else:
            bm_box(bm, cx - t / 2, cx + t / 2, cy - ww / 2, cy + ww / 2, hz0, hz1)


def merlon_ring(name, bx, z0, w, h, t, pitch, steps=3, grp="BLUE",
                collection="Gate", sides="NSEW", out=0.0):
    """Row of stepped merlons along the top edges of footprint bx."""
    x0, x1, y0, y1 = bx
    x0 -= out
    x1 += out
    y0 -= out
    y1 += out
    bm = bmesh.new()

    def row(a0, a1, fn):
        n = max(1, round((a1 - a0) / pitch))
        step = (a1 - a0 - w) / max(1, n - 1) if n > 1 else 0
        for k in range(n):
            fn(a0 + w / 2 + step * k if n > 1 else (a0 + a1) / 2)
    if "S" in sides:
        row(x0, x1, lambda a: stepped_merlon(bm, a, y0 + t / 2, True, w, h, t, z0, steps))
    if "N" in sides:
        row(x0, x1, lambda a: stepped_merlon(bm, a, y1 - t / 2, True, w, h, t, z0, steps))
    if "W" in sides:
        row(y0 + w, y1 - w, lambda a: stepped_merlon(bm, x0 + t / 2, a, False, w, h, t, z0, steps))
    if "E" in sides:
        row(y0 + w, y1 - w, lambda a: stepped_merlon(bm, x1 - t / 2, a, False, w, h, t, z0, steps))
    return new_obj(name, bm, grp, collection)


# --- animal reliefs -------------------------------------------------------

LION = [(0, 46), (4, 49), (8, 47), (7, 43), (10, 40), (14, 36), (22, 35),
        (40, 36), (54, 38), (60, 42), (66, 48), (74, 51), (78, 49), (84, 49),
        (92, 45), (98, 41), (97, 37), (90, 36), (96, 32), (92, 29), (84, 28),
        (80, 22), (82, 15), (87, 5), (91, 2), (91, 0), (81, 0), (80, 4),
        (74, 14), (72, 8), (74, 2), (74, 0), (65, 0), (66, 6), (64, 17),
        (44, 18), (28, 19), (26, 12), (30, 3), (31, 0), (22, 0), (20, 9),
        (16, 6), (13, 2), (14, 0), (5, 0), (8, 8), (9, 20), (11, 30), (9, 36),
        (5, 41), (3, 44)]

BULL = [(0, 46), (3, 52), (8, 49), (9, 43), (13, 38), (30, 37), (52, 39),
        (60, 43), (66, 45), (70, 55), (72, 63), (66, 71), (64, 78), (69, 77),
        (75, 69), (78, 67), (85, 67), (96, 61), (99, 57), (95, 54), (86, 55),
        (80, 52), (78, 42), (77, 32), (78, 20), (82, 6), (86, 1), (86, 0),
        (77, 0), (72, 14), (69, 10), (70, 0), (61, 0), (61, 17), (57, 20),
        (28, 20), (25, 13), (28, 3), (30, 0), (20, 0), (18, 10), (15, 5),
        (16, 0), (7, 0), (9, 12), (9, 28), (6, 36), (3, 41)]


def chaikin(pts, it=2):
    for _ in range(it):
        out = []
        n = len(pts)
        for i in range(n):
            p, q = pts[i], pts[(i + 1) % n]
            out.append((0.75 * p[0] + 0.25 * q[0], 0.75 * p[1] + 0.25 * q[1]))
            out.append((0.25 * p[0] + 0.75 * q[0], 0.25 * p[1] + 0.75 * q[1]))
        pts = out
    return pts


SHAPES = {"LION": chaikin(LION), "BULL": chaikin(BULL)}


def animal(bm, kind, cx, cz, width, y, face_right=True, proud=0.6):
    """Relief animal on a south-facing wall at plane y, centred at cx,cz."""
    pts = SHAPES[kind]
    s = width / 100.0
    hgt = (max(p[1] for p in pts)) * s
    sx = 1 if face_right else -1
    p2 = [(cx + sx * (x - 50) * s, cz - hgt / 2 + yy * s) for x, yy in pts]
    # plane: u=x, v=z, extrude toward -y
    bm_prism(bm, p2, (0, y + 0.3, 0), (1, 0, 0), (0, 0, 1), (0, -1, 0),
             proud + 0.3)


def animal_panel(name, x0, x1, z0, z1, y, rows, cols, face_right,
                 color_seed, width, collection="Gate"):
    """Smooth lapis panel with gold frame and alternating lion / bull rows."""
    frame_front(name + "_frame", x0, x1, z0, z1, y, w=1.3, proud=0.75,
                collection=collection)
    box(name + "_plate", "PANEL", x0 + 1.0, x1 - 1.0, y - 0.35, y + 0.45,
        z0 + 1.0, z1 - 1.0, collection)
    gold = bmesh.new()
    white = bmesh.new()
    inner_h = (z1 - z0) - 2.6
    rh = inner_h / rows
    cw = ((x1 - x0) - 2.6) / cols
    for r in range(rows):
        kind = "LION" if r % 2 == 0 else "BULL"
        cz = z1 - 1.3 - rh * (r + 0.5)
        for c in range(cols):
            cx = x0 + 1.3 + cw * (c + 0.5)
            is_gold = (r + c + color_seed) % 2 == 0
            w = width * (1.0 if kind == "LION" else 0.78)
            animal(gold if is_gold else white, kind, cx, cz, w, y - 0.35,
                   face_right)
    new_obj(name + "_gold", gold, "GOLD", collection)
    new_obj(name + "_white", white, "WHITE", collection)


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

BASE = dict(x0=-110, x1=110, y0=-65, y1=65, t=6.0)

# Gate (all z in mm above the plaza floor)
FY = 22.0           # facade front plane
G_HALF = 65.0       # facade half width
FACADE_H = 54.0
BACK = (36.0, 58.0)
BACK_H = 64.0
TOWER_X = (20.0, 56.0)
TOWER_Y = (FY + 0.4, 50.0)   # 0.4 behind the facade face: no coplanar overlap
TOWER_H = 76.0
CROWN_H = 85.5
ARCH_R = 8.0
ARCH_SPRING = 27.0


def build_base():
    b = BASE
    box("Base", "SAND", b["x0"], b["x1"], b["y0"], b["y1"], -b["t"], 0.0,
        "Plaza")
    # light front lip like the cardboard edge of the original
    box("Base_lip", "SAND", b["x0"], b["x1"], b["y0"] - 0.6, b["y0"] + 0.5,
        -b["t"], 0.4, "Plaza")


def arch_cutter(y0, y1, r=ARCH_R, spring=ARCH_SPRING, seg=24):
    pts = [(-r, -1.0), (r, -1.0), (r, spring)]
    for i in range(1, seg):
        a = math.pi * i / seg
        pts.append((r * math.cos(a), spring + r * math.sin(a)))
    pts.append((-r, spring))
    bm = bmesh.new()
    bm_prism(bm, pts, (0, y0, 0), (1, 0, 0), (0, 0, 1), (0, 1, 0), y1 - y0)
    return new_obj("arch_cutter", bm, "BLUE")


def build_gate():
    # main masses
    facade = ribbed_box("Gate_facade", -G_HALF, G_HALF, FY, BACK[0] + 2.0,
                        0, FACADE_H)
    back = ribbed_box("Gate_backblock", -G_HALF, G_HALF, BACK[0], BACK[1],
                      0, BACK_H)
    towers = []
    for side in (-1, 1):
        xa, xb = sorted((side * TOWER_X[0], side * TOWER_X[1]))
        t = ribbed_box("Gate_tower_" + ("L" if side < 0 else "R"),
                       xa, xb, TOWER_Y[0], TOWER_Y[1], 0, TOWER_H)
        c = ribbed_box("Gate_crown_" + ("L" if side < 0 else "R"),
                       xa - 0.8, xb + 0.8, TOWER_Y[0] - 0.8, TOWER_Y[1] + 0.8,
                       TOWER_H - 0.5, CROWN_H)
        towers += [t, c]
        bx = (xa - 0.8, xb + 0.8, TOWER_Y[0] - 0.8, TOWER_Y[1] + 0.8)
        merlon_ring("Gate_merlons_" + str(side), bx, CROWN_H - 0.2, 5.6, 4.8,
                    2.8, 7.4)
        band_ring("Gate_cband1_" + str(side), bx, 82.8, 84.6)
        band_ring("Gate_cband2_" + str(side), bx, 79.9, 81.7)
        band_ring("Gate_cband3_" + str(side), (xa, xb, TOWER_Y[0], TOWER_Y[1]),
                  74.2, 76.4)
    # arch passage through everything
    cut = arch_cutter(FY - 2, BACK[1] + 2)
    for ob in [facade, back]:
        boolean(ob, cut)
    delete(cut)

    # back block crown, bands
    bbx = (-G_HALF, G_HALF, BACK[0], BACK[1])
    merlon_ring("Gate_back_merlons", bbx, BACK_H - 0.2, 3.8, 3.9, 2.4, 5.2)
    band_ring("Gate_bband1", bbx, 60.6, 62.4)
    band_ring("Gate_bband2", bbx, 57.6, 59.4)
    # facade top band (full width)
    band_ring("Gate_fband", (-G_HALF, G_HALF, FY, BACK[0] + 2.0), 51.0, 53.4,
              sides="SWE")
    # bottom rosette band across the facade (split by the arch)
    for xa, xb in ((-G_HALF, -ARCH_R - 0.6), (ARCH_R + 0.6, G_HALF)):
        rosette_band_front("Gate_rband_bottom_%d" % xa, xa, xb, 0.4, 4.2, FY)

    # big tower panels: 6 rows x 2 cols
    for side in (-1, 1):
        xa, xb = sorted((side * 21.0, side * 52.5))
        animal_panel("Gate_panel_" + str(side), xa, xb, 5.0, 50.0, FY,
                     rows=6, cols=2, face_right=(side < 0),
                     color_seed=0 if side < 0 else 1, width=12.0)
        # little inner portal panels beside the arch: 3 animals
        pa, pb = sorted((side * 9.4, side * 19.2))
        animal_panel("Gate_small_" + str(side), pa, pb, 5.0, 26.0, FY,
                     rows=3, cols=1, face_right=(side < 0),
                     color_seed=0, width=7.5)
        # rosette band over the small panel
        rosette_band_front("Gate_rband_portal_" + str(side), pa - 0.4,
                           pb + 0.4, 26.0, 29.4, FY)
        # gold jamb on the arch opening
        ja, jb = sorted((side * ARCH_R, side * (ARCH_R + 1.4)))
        front_strip("Gate_jamb_" + str(side), "GOLD", ja, jb, 0.0,
                    ARCH_SPRING, FY, 0.6)

    # arch rosette ring (gold outline, lapis centre, white rosettes)
    def arch_ring(name, r0, r1, grp, proud, seg=36):
        pts = []
        for i in range(seg + 1):
            a = math.pi * i / seg
            pts.append((r1 * math.cos(a), ARCH_SPRING + r1 * math.sin(a)))
        for i in range(seg, -1, -1):
            a = math.pi * i / seg
            pts.append((r0 * math.cos(a), ARCH_SPRING + r0 * math.sin(a)))
        bm = bmesh.new()
        bm_prism(bm, pts, (0, FY + 0.45, 0), (1, 0, 0), (0, 0, 1),
                 (0, -1, 0), proud + 0.45)
        return new_obj(name, bm, grp)
    arch_ring("Gate_arch_gold", ARCH_R, ARCH_R + 4.8, "GOLD", 0.6)
    arch_ring("Gate_arch_blue", ARCH_R + 1.0, ARCH_R + 3.8, "DOTS", 0.67)
    bm = bmesh.new()
    rm = ARCH_R + 2.4
    for i in range(11):
        a = math.pi * (i + 0.5) / 11
        bm_cyl(bm, (rm * math.cos(a), FY + 0.1, ARCH_SPRING + rm * math.sin(a)),
               (0, -1, 0), 0.8, 1.05, 10)
    new_obj("Gate_arch_rosettes", bm, "WHITE")


def build_wing(side):
    """side=-1 left, +1 right."""
    tag = "L" if side < 0 else "R"
    col = "Wing_" + tag

    def X(a, b):
        return sorted((side * a, side * b))

    # outer front tower
    ox = X(79.0, 109.0)
    oy = (-63.0, -12.5)    # overlaps the inner tower by 2 mm
    OH = 38.0
    # inner tower (connects back to the gate)
    ix = X(65.0, 95.0)
    iy = (-14.5, 46.0)
    IH = 41.0
    outer = ribbed_box("Wing_outer_" + tag, ox[0], ox[1], oy[0], oy[1], 0, OH,
                       collection=col)
    inner = ribbed_box("Wing_inner_" + tag, ix[0], ix[1], iy[0], iy[1], 0, IH,
                       collection=col)

    # doors on the faces that look toward the plaza centre
    def door(ob, face_x, yc, w, h, name):
        d = 1.0
        xa, xb = sorted((face_x - side * 0.01, face_x + side * d))
        cut = box("door_cut", "BLUE", xa, xb, yc - w / 2, yc + w / 2, -1, h)
        boolean(ob, cut)
        delete(cut)
        # gold frame standing proud of the face
        bm = bmesh.new()
        fa, fb = sorted((face_x + side * 0.45, face_x - side * 0.6))
        fw = 1.3
        bm_box(bm, fa, fb, yc - w / 2 - fw, yc - w / 2, 0, h)
        bm_box(bm, fa, fb, yc + w / 2, yc + w / 2 + fw, 0, h)
        bm_box(bm, fa, fb, yc - w / 2 - fw, yc + w / 2 + fw, h, h + fw)
        new_obj(name, bm, "GOLD", col)
        # lapis door leaf in the recess
        la, lb = sorted((face_x + side * 0.65, face_x + side * 1.15))
        box(name + "_leaf", "PANEL", la, lb, yc - w / 2 + 0.01,
            yc + w / 2 - 0.01, 0, h - 0.01, col)

    door(outer, side * 79.0, -36.0, 7.5, 16.0, "Wing_outer_door_" + tag)
    door(inner, side * 65.0, 2.0, 6.5, 15.0, "Wing_inner_door_" + tag)

    for bx, H, name in (((ox[0], ox[1], oy[0], oy[1]), OH, "outer"),
                        ((ix[0], ix[1], iy[0], iy[1]), IH, "inner")):
        merlon_ring("Wing_%s_merlons_%s" % (name, tag), bx, H - 0.2, 6.2,
                    5.6, 3.0, 8.0, steps=2, collection=col)
        # white flat roof inside the parapet
        box("Wing_%s_roof_%s" % (name, tag), "WHITE", bx[0] + 2.6,
            bx[1] - 2.6, bx[2] + 2.6, bx[3] - 2.6, H - 0.5, H + 0.5, col)
        band_ring("Wing_%s_band1_%s" % (name, tag), bx, H - 3.3, H - 1.2,
                  collection=col)
        band_ring("Wing_%s_band2_%s" % (name, tag), bx, H - 8.8, H - 6.7,
                  collection=col)
        band_ring("Wing_%s_band0_%s" % (name, tag), bx, 0.0, 2.1,
                  collection=col)


def build_path():
    """Trapezoidal stone path from the plaza edge through the arch, with a
    pebbled top."""
    bm = bmesh.new()
    pts = [(-13.0, BASE["y0"] + 0.6), (13.0, BASE["y0"] + 0.6),
           (8.6, FY - 0.5), (-8.6, FY - 0.5)]
    bm_prism(bm, pts, (0, 0, -0.3), (1, 0, 0), (0, 1, 0), (0, 0, 1), 1.0)
    new_obj("Path", bm, "STONE", "Plaza")
    box("Path_arch", "STONE", -ARCH_R + 0.05, ARCH_R - 0.05, FY - 0.6,
        BACK[1] + 0.0, -0.3, 0.7, "Plaza")
    # pebbles
    bm = bmesh.new()
    for _ in range(420):
        t = random.random()
        y = BASE["y0"] + 1.5 + t * (FY - BASE["y0"] - 2.5)
        half = 13.0 - (13.0 - 8.6) * t - 0.8
        x = random.uniform(-half, half)
        r = random.uniform(0.35, 0.6)
        bm_cyl(bm, (x, y, 0.4), (0, 0, 1), r, random.uniform(0.45, 0.65), 6)
    new_obj("Path_pebbles", bm, "STONE", "Plaza")


def build_lawn(side):
    """Gold-kerbed lawn in the stepped 'comb' layout of the original:
    three cross bands joined by a central spine, with two-step stone
    benches filling the four bays."""
    tag = "L" if side < 0 else "R"
    xa, xb = sorted((side * 17.0, side * 58.0))
    y0, y1 = -55.0, 4.0
    k = 1.3   # kerb width
    col = "Plaza"
    bm = bmesh.new()
    bm_box(bm, xa, xb, y0, y0 + k, -0.2, 1.6)
    bm_box(bm, xa, xb, y1 - k, y1, -0.2, 1.6)
    bm_box(bm, xa, xa + k, y0 + k, y1 - k, -0.2, 1.6)
    bm_box(bm, xb - k, xb, y0 + k, y1 - k, -0.2, 1.6)
    new_obj("Lawn_kerb_" + tag, bm, "SAND", col)

    ix0, ix1, iy0, iy1 = xa + k, xb - k, y0 + k, y1 - k
    D = iy1 - iy0
    W = ix1 - ix0
    # (from back) top band, bay1, middle band, bay2, bottom band
    fr = [0.16, 0.22, 0.15, 0.24, 0.23]
    edges = [iy1]
    for f in fr:
        edges.append(edges[-1] - f * D)
    spine0 = ix0 + W * 0.37
    spine1 = ix0 + W * 0.63
    grass = bmesh.new()
    bm_box(grass, ix0, ix1, iy0, iy1, -0.2, 0.9)
    new_obj("Lawn_" + tag, grass, "GRASS", col)
    # grass tufts texture
    bm = bmesh.new()
    for _ in range(500):
        x = random.uniform(ix0 + 0.4, ix1 - 0.4)
        y = random.uniform(iy0 + 0.4, iy1 - 0.4)
        bm_cyl(bm, (x, y, 0.8), (0, 0, 1), random.uniform(0.25, 0.45),
               random.uniform(0.25, 0.5), 5)
    new_obj("Lawn_tufts_" + tag, bm, "GRASS", col)
    # benches in the four bays (two steps each), these sit above the grass
    bm = bmesh.new()
    for bay in (1, 3):
        ya, yb = edges[bay + 1], edges[bay]
        ym = (ya + yb) / 2
        for (bx0, bx1) in ((ix0 - 0.01, spine0), (spine1, ix1 + 0.01)):
            bm_box(bm, bx0, bx1, ym, yb, -0.2, 2.4)       # back, high step
            bm_box(bm, bx0, bx1, ya, ym, -0.2, 1.6)       # front, low step
    new_obj("Lawn_benches_" + tag, bm, "SAND", col)
    return (spine0 + spine1) / 2, (edges[2] + edges[3]) / 2


def build_palm(name, x, y, height=40.0):
    col = "Palms"
    # trunk: tapered with growth rings, slight lean
    bm = bmesh.new()
    seg = 12
    rings = []
    nz = 80
    lean = Vector((random.uniform(-0.04, 0.04), random.uniform(-0.04, 0.04), 0))
    for i in range(nz + 1):
        z = height * i / nz - (0.6 if i == 0 else 0.0)
        r = 1.65 - 0.55 * (z / height) + 0.16 * abs(math.sin(z * math.pi / 1.4))
        c = Vector((x, y, z)) + lean * z
        ring = []
        for s in range(seg):
            a = 2 * math.pi * s / seg
            ring.append(bm.verts.new(c + Vector((math.cos(a) * r,
                                                 math.sin(a) * r, 0))))
        rings.append(ring)
    bm.faces.new(rings[0][::-1])
    bm.faces.new(rings[-1])
    for a, b in zip(rings, rings[1:]):
        for s in range(seg):
            t = (s + 1) % seg
            bm.faces.new((a[s], a[t], b[t], b[s]))
    top = Vector((x, y, height)) + lean * height
    new_obj(name + "_trunk", bm, "TRUNK", col, smooth=True)
    # crown knot
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=8, radius=2.0)
    bmesh.ops.translate(bm, verts=bm.verts, vec=top)
    new_obj(name + "_knot", bm, "LEAF", col, smooth=True)

    # fronds: arching, serrated, V-folded, solid 0.8 mm
    bm = bmesh.new()
    nf = 18
    for f in range(nf):
        upper = f % 3 == 0
        ang = 2 * math.pi * f / nf + random.uniform(-0.12, 0.12)
        L = random.uniform(12.0, 15.0) if upper else random.uniform(17.0, 21.0)
        lift = random.uniform(7.0, 10.0) if upper else random.uniform(1.5, 5.0)
        dirv = Vector((math.cos(ang), math.sin(ang), 0))
        side = Vector((-math.sin(ang), math.cos(ang), 0))
        n = 22
        th = 0.8
        top_l, top_c, top_r, bot_l, bot_c, bot_r = [], [], [], [], [], []
        for i in range(n + 1):
            t = i / n
            p = top + dirv * (L * t) + Vector((0, 0, lift * 4 * t * (1 - t) -
                                               L * 0.55 * t * t))
            w = (3.6 * math.sin(math.pi * min(1, t * 1.05)) ** 0.7 + 0.35)
            if 0 < i < n and i % 2 == 1:
                w *= 0.45          # serration -> leaflet tips
            fold = 0.7 * w / 3.6
            pc = p + Vector((0, 0, fold))
            pl = p + side * w
            pr = p - side * w
            for lst, q in ((top_l, pl), (top_c, pc), (top_r, pr)):
                lst.append(bm.verts.new(q))
            for lst, q in ((bot_l, pl), (bot_c, pc), (bot_r, pr)):
                lst.append(bm.verts.new(q - Vector((0, 0, th))))
        for i in range(n):
            j = i + 1
            bm.faces.new((top_l[i], top_c[i], top_c[j], top_l[j]))
            bm.faces.new((top_c[i], top_r[i], top_r[j], top_c[j]))
            bm.faces.new((bot_l[j], bot_c[j], bot_c[i], bot_l[i]))
            bm.faces.new((bot_c[j], bot_r[j], bot_r[i], bot_c[i]))
            bm.faces.new((top_l[j], bot_l[j], bot_l[i], top_l[i]))
            bm.faces.new((top_r[i], bot_r[i], bot_r[j], top_r[j]))
        for i in (0, n):
            bm.faces.new((top_l[i], top_c[i], top_r[i], bot_r[i], bot_c[i],
                          bot_l[i]))
    new_obj(name + "_fronds", bm, "LEAF", col, smooth=True)


def build_people():
    col = "People"
    spots = [
        # on the path
        (-1.5, 15), (2.0, 10), (-3.0, 4), (1.0, -2), (4.0, -6), (-4.5, -10),
        (0.5, -14), (5.5, -20), (-2.5, -24), (3.0, -31), (-6.0, -36),
        (6.5, -42), (-1.0, -47), (2.5, 30),
        # plaza
        (-16.0, 12), (17.0, 12), (-70.0, -20), (-68.0, -48), (-60.0, -60),
        (-15.0, -40), (15.5, -33), (60.0, 10), (70.0, -24), (-72.0, -30),
        (-40.0, 10), (40.0, 9),
    ]
    tints = [(0.85, 0.30, 0.25, 1), (0.95, 0.80, 0.25, 1), (0.25, 0.65, 0.6, 1),
             (0.90, 0.55, 0.65, 1), (0.95, 0.95, 0.90, 1), (0.85, 0.45, 0.15, 1)]
    for i, (x, y) in enumerate(spots):
        bm = bmesh.new()
        h = random.uniform(5.2, 6.2)
        bm_box(bm, x - 0.55, x - 0.05, y - 0.35, y + 0.35, -0.3, h * 0.45)
        bm_box(bm, x + 0.05, x + 0.55, y - 0.35, y + 0.35, -0.3, h * 0.45)
        bm_cyl(bm, (x, y, h * 0.42), (0, 0, 1), 0.65, h * 0.38, 8)
        s = bmesh.ops.create_uvsphere(bm, u_segments=10, v_segments=6,
                                      radius=0.55)
        bmesh.ops.translate(bm, verts=s["verts"],
                            vec=(x, y, h * 0.80 + 0.45))
        ob = new_obj("Person_%02d" % i, bm, "PEOPLE", col)
        m = MATS["PEOPLE"].copy()
        m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = tints[i % len(tints)]
        m.diffuse_color = tints[i % len(tints)]
        ob.data.materials[0] = m


def setup_render():
    sc = bpy.context.scene
    # camera matching the reference photo: front, slightly above
    cam_data = bpy.data.cameras.new("Camera")
    cam_data.lens = 35
    cam_data.clip_start = 1
    cam_data.clip_end = 5000
    cam = bpy.data.objects.new("Camera", cam_data)
    sc.collection.objects.link(cam)
    cam.location = (0, -335, 118)
    target = Vector((0, 8, 36))
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    sc.camera = cam

    for name, loc, energy, size in (("Key", (-180, -260, 360), 2.2e6, 220),
                                    ("Fill", (260, -200, 160), 7e5, 260),
                                    ("Rim", (0, 300, 300), 9e5, 200)):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy = energy
        ld.size = size
        lo = bpy.data.objects.new(name, ld)
        lo.location = loc
        lo.rotation_euler = (Vector((0, 0, 20)) - Vector(loc)).to_track_quat(
            "-Z", "Y").to_euler()
        sc.collection.objects.link(lo)

    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.75, 0.73, 0.70, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.35
    sc.world = world

    # display table under the diorama (render only, not exported)
    bm = bmesh.new()
    bm_box(bm, -130, 130, -85, 90, -26, -6)
    tm = bpy.data.meshes.new("Table")
    bm.to_mesh(tm)
    bm.free()
    table = bpy.data.objects.new("Display_table", tm)
    m = bpy.data.materials.new("IG_wood")
    m.use_nodes = True
    m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.05, 0.03, 0.02, 1)
    m.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.3
    tm.materials.append(m)
    table["grp"] = "NONE"
    coll("Display").objects.link(table)
    bm = bmesh.new()
    bm_box(bm, -800, 800, 400, 420, -400, 800)
    bm_box(bm, -800, 800, -800, 420, -40, -26)
    wm = bpy.data.meshes.new("Backdrop")
    bm.to_mesh(wm)
    bm.free()
    wall = bpy.data.objects.new("Backdrop", wm)
    m = bpy.data.materials.new("IG_wall")
    m.use_nodes = True
    m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.8, 0.78, 0.74, 1)
    wm.materials.append(m)
    wall["grp"] = "NONE"
    coll("Display").objects.link(wall)

    sc.render.engine = "CYCLES"
    sc.cycles.samples = 96
    sc.cycles.use_denoising = True
    sc.render.resolution_x = 1600
    sc.render.resolution_y = 1000
    sc.view_settings.view_transform = "AgX"


def build_all():
    reset_scene()
    make_materials()
    build_base()
    build_gate()
    for s in (-1, 1):
        build_wing(s)
        sx, sy = build_lawn(s)
        build_palm("Palm_" + ("L" if s < 0 else "R"), sx, sy)
    build_path()
    build_people()
    setup_render()


if __name__ == "__main__":
    build_all()
