"""
Dental desk nameplate - procedural Blender model.

A white-enamel tooth framed in polished gold, black-faced gold letters
("Dr" / "Rahma Ali"), a heartbeat line ending in a heart, a gold holder with a
dental mirror and explorer, all on a white Carrara marble base. Only the
model is built, with studio lights and a camera for rendering it.

Usage
-----
Inside Blender: Scripting tab -> Open this file -> Run Script.

From the command line (render straight to a PNG):
    blender -b -P dental_nameplate.py -- --render out.png --samples 256

Options after "--":
    --title TEXT      small line above the name        (default "Dr")
    --name TEXT       main name line                   (default "Rahma Ali")
    --font PATH       .ttf/.otf font for the letters
    --render PATH     render a still to PATH
    --save PATH       save the .blend to PATH
    --samples N       Cycles samples                   (default 256)
    --percent P       resolution percentage            (default 100)

Works with Blender 4.2 and newer (tested on 5.0). Units are metres; the scene
is displayed in centimetres.
"""

import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

# ---------------------------------------------------------------------------
# Settings - change these and run again.
# ---------------------------------------------------------------------------

TITLE = "Dr"
NAME = "Rahma Ali"

# Leave empty to pick the first font found from FONT_CANDIDATES.
FONT_PATH = ""
FONT_CANDIDATES = [
    # Windows
    "C:/Windows/Fonts/georgiab.ttf",
    "C:/Windows/Fonts/ROCKB.TTF",
    "C:/Windows/Fonts/timesbd.ttf",
    # macOS
    "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
    "/Library/Fonts/Georgia Bold.ttf",
    # Linux
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "/usr/share/fonts/truetype/crosextra/Caladea-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
]

SAMPLES = 256
RESOLUTION = (1920, 1600)

# Physical sizes (metres).
TOOTH_HEIGHT = 0.175
TOOTH_DEPTH = 0.037
NAME_CAP_HEIGHT = 0.052
NAME_WIDTH = 0.27           # letters are condensed/stretched to this width
TITLE_SCALE = 0.74           # "Dr" size relative to the name
LETTER_DEPTH = 0.015
BASE_HEIGHT = 0.024
BASE_DEPTH = 0.078

UP = Vector((0, 0, 1))
FRONT = Matrix.Rotation(math.pi / 2, 4, "X")   # local XY plane -> world XZ, +Z faces the camera (-Y)


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

def clear_scene():
    for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.curves,
                 bpy.data.materials, bpy.data.lights, bpy.data.cameras,
                 bpy.data.node_groups):
        for block in list(coll):
            coll.remove(block)
    for coll in list(bpy.data.collections):
        bpy.data.collections.remove(coll)


def collection(name):
    coll = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(coll)
    return coll


def add_object(name, data, coll):
    obj = bpy.data.objects.new(name, data)
    coll.objects.link(obj)
    return obj


def set_input(node, names, value):
    if isinstance(names, str):
        names = (names,)
    for name in names:
        sock = node.inputs.get(name)
        if sock is not None:
            sock.default_value = value
            return sock
    return None


def smooth(obj, angle=32):
    me = obj.data
    me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    if hasattr(me, "set_sharp_from_angle"):
        me.set_sharp_from_angle(angle=math.radians(angle))
    elif hasattr(me, "use_auto_smooth"):
        me.use_auto_smooth = True
        me.auto_smooth_angle = math.radians(angle)
    me.update()


def curve_to_mesh(obj):
    """Replace a curve/text object with an equivalent mesh object."""
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(obj.evaluated_get(dg))
    name, colls, mw, data = obj.name, list(obj.users_collection), obj.matrix_world.copy(), obj.data
    bpy.data.objects.remove(obj)
    if data.users == 0:
        bpy.data.curves.remove(data)
    new = bpy.data.objects.new(name, me)
    new.matrix_world = mw
    for c in colls:
        c.objects.link(new)
    return new


def assign(obj, *mats):
    obj.data.materials.clear()
    for m in mats:
        obj.data.materials.append(m)


def paint_front_face(obj, index):
    """Give the flat front cap (+Z local) its own material slot - black face, gold sides."""
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    top = max(v.co.z for v in me.vertices)
    for p in me.polygons:
        if abs(p.normal.z) > 0.995 and p.center.z > top - 1e-5:
            p.material_index = index


def bevel(obj, width, segments=3, angle=35):
    mod = obj.modifiers.new("Bevel", "BEVEL")
    mod.width = width
    mod.segments = segments
    mod.limit_method = "ANGLE"
    mod.angle_limit = math.radians(angle)
    return mod


def local_bounds(obj):
    xs = [v.co.x for v in obj.data.vertices]
    ys = [v.co.y for v in obj.data.vertices]
    zs = [v.co.z for v in obj.data.vertices]
    return Vector((min(xs), min(ys), min(zs))), Vector((max(xs), max(ys), max(zs)))


def catmull(points, samples=12, closed=True):
    pts = [Vector(p) for p in points]
    n = len(pts)
    out = []
    segs = n if closed else n - 1
    for i in range(segs):
        p0 = pts[(i - 1) % n] if closed or i > 0 else pts[0]
        p1 = pts[i]
        p2 = pts[(i + 1) % n]
        p3 = pts[(i + 2) % n] if closed or i + 2 < n else pts[-1]
        for k in range(samples):
            t = k / samples
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t
                              + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    if not closed:
        out.append(pts[-1])
    return out


def offset_loop(loop, dist):
    """Offset a closed 2D loop outwards (dist > 0) or inwards (dist < 0)."""
    n = len(loop)
    area = sum(loop[i].x * loop[(i + 1) % n].y - loop[(i + 1) % n].x * loop[i].y for i in range(n))
    sign = 1 if area > 0 else -1
    out = []
    for i in range(n):
        t = (loop[(i + 1) % n] - loop[i - 1]).normalized()
        out.append(loop[i] + Vector((t.y, -t.x)) * dist * sign)
    return out


def curve_data(name, splines, dims="2D", cyclic=True, **props):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = dims
    for pts in splines:
        sp = cu.splines.new("POLY")
        sp.points.add(len(pts) - 1)
        for p, co in zip(sp.points, pts):
            co = Vector(co).to_3d()
            p.co = (co.x, co.y, co.z, 1.0)
        sp.use_cyclic_u = cyclic
    for key, value in props.items():
        setattr(cu, key, value)
    return cu


# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------

def new_material(name):
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except AttributeError:
        pass
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    return m, nt, bsdf


def principled(name, color, metallic=0.0, rough=0.5, coat=0.0, coat_rough=0.03, spec=0.5):
    m, nt, bsdf = new_material(name)
    set_input(bsdf, "Base Color", (*color, 1.0))
    set_input(bsdf, "Metallic", metallic)
    set_input(bsdf, "Roughness", rough)
    set_input(bsdf, ("Specular IOR Level", "Specular"), spec)
    set_input(bsdf, ("Coat Weight", "Clearcoat"), coat)
    set_input(bsdf, ("Coat Roughness", "Clearcoat Roughness"), coat_rough)
    m.diffuse_color = (*color, 1.0)
    return m


def mix_rgb(nt, fac, a, b):
    node = nt.nodes.new("ShaderNodeMix")
    node.data_type = "RGBA"
    if isinstance(fac, float):
        node.inputs[0].default_value = fac
    else:
        nt.links.new(fac, node.inputs[0])
    for sock, val in ((node.inputs[6], a), (node.inputs[7], b)):
        if isinstance(val, tuple):
            sock.default_value = (*val, 1.0) if len(val) == 3 else val
        else:
            nt.links.new(val, sock)
    return node.outputs[2]


def map_range(nt, value, a, b, c, d):
    node = nt.nodes.new("ShaderNodeMapRange")
    nt.links.new(value, node.inputs["Value"])
    node.inputs["From Min"].default_value = a
    node.inputs["From Max"].default_value = b
    node.inputs["To Min"].default_value = c
    node.inputs["To Max"].default_value = d
    return node.outputs[0]


def distorted_coords(nt, scale, noise_scale, strength, seed_offset):
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = scale
    mp.inputs["Location"].default_value = seed_offset
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = noise_scale
    noise.inputs["Detail"].default_value = 10.0
    noise.inputs["Roughness"].default_value = 0.62
    nt.links.new(mp.outputs[0], noise.inputs["Vector"])
    centred = nt.nodes.new("ShaderNodeVectorMath")
    centred.operation = "SUBTRACT"
    centred.inputs[1].default_value = (0.5, 0.5, 0.5)
    nt.links.new(noise.outputs["Color"], centred.inputs[0])
    add = nt.nodes.new("ShaderNodeVectorMath")
    add.operation = "MULTIPLY_ADD"
    add.inputs[1].default_value = (strength, strength, strength)
    nt.links.new(centred.outputs[0], add.inputs[0])
    nt.links.new(mp.outputs[0], add.inputs[2])
    return add.outputs[0]


def marble_material():
    m, nt, bsdf = new_material("Marble")
    set_input(bsdf, "Roughness", 0.14)
    set_input(bsdf, ("Coat Weight", "Clearcoat"), 0.6)
    set_input(bsdf, ("Coat Roughness", "Clearcoat Roughness"), 0.04)
    set_input(bsdf, ("Subsurface Weight", "Subsurface"), 0.06)
    set_input(bsdf, "Subsurface Radius", (0.004, 0.004, 0.004))
    set_input(bsdf, "Subsurface Scale", 1.0)

    # Long crack-like veins: distance to Voronoi cell edges on warped coordinates.
    def veins(scale, warp, thickness, seed):
        coords = distorted_coords(nt, (scale, scale * 1.6, scale), 2.2, warp, seed)
        vor = nt.nodes.new("ShaderNodeTexVoronoi")
        vor.feature = "DISTANCE_TO_EDGE"
        vor.inputs["Scale"].default_value = 1.0
        nt.links.new(coords, vor.inputs["Vector"])
        return map_range(nt, vor.outputs["Distance"], 0.0, thickness, 1.0, 0.0)

    main = veins(9.0, 0.9, 0.022, (3.1, 7.2, 1.3))
    fine = veins(22.0, 1.3, 0.016, (11.0, 2.0, 5.5))
    haze_noise = nt.nodes.new("ShaderNodeTexNoise")
    haze_noise.inputs["Scale"].default_value = 18.0
    haze_noise.inputs["Detail"].default_value = 6.0
    haze = map_range(nt, haze_noise.outputs["Fac"], 0.45, 0.75, 0.0, 1.0)

    col = mix_rgb(nt, haze, (0.93, 0.93, 0.91), (0.80, 0.80, 0.79))
    fine_mix = nt.nodes.new("ShaderNodeMath")
    fine_mix.operation = "MULTIPLY"
    fine_mix.inputs[1].default_value = 0.55
    nt.links.new(fine, fine_mix.inputs[0])
    col = mix_rgb(nt, fine_mix.outputs[0], col, (0.36, 0.36, 0.36))
    col = mix_rgb(nt, main, col, (0.12, 0.12, 0.12))
    nt.links.new(col, bsdf.inputs["Base Color"])
    m.diffuse_color = (0.9, 0.9, 0.9, 1)
    return m


def knurled_gold(gold_color):
    m = principled("Gold Knurled", gold_color, metallic=1.0, rough=0.24)
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.wave_type = "BANDS"
    wave.bands_direction = "Z"
    wave.inputs["Scale"].default_value = 260.0
    nt.links.new(tc.outputs["Object"], wave.inputs["Vector"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.7
    bump.inputs["Distance"].default_value = 0.0004
    nt.links.new(wave.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return m


def build_materials():
    gold = (1.0, 0.64, 0.21)
    return {
        "gold": principled("Gold Polished", gold, metallic=1.0, rough=0.11),
        "gold_satin": principled("Gold Satin", gold, metallic=1.0, rough=0.2),
        "gold_knurl": knurled_gold(gold),
        "enamel": principled("Enamel White", (0.93, 0.915, 0.88), rough=0.18, coat=1.0, coat_rough=0.02),
        "black": principled("Black Satin", (0.006, 0.006, 0.006), rough=0.38, spec=0.25),
        "mirror": principled("Mirror", (0.96, 0.96, 0.96), metallic=1.0, rough=0.0),
        "marble": marble_material(),
    }


# ---------------------------------------------------------------------------
# Nameplate parts
# ---------------------------------------------------------------------------

# Molar outline in a unit box: x in [-0.5, 0.5], y from root tips (0) to cusps (~1.14).
TOOTH_OUTLINE = [
    (-0.215, 0.000), (-0.300, 0.040), (-0.355, 0.190), (-0.415, 0.410),
    (-0.475, 0.610), (-0.500, 0.800), (-0.465, 0.975), (-0.365, 1.095),
    (-0.225, 1.130), (-0.085, 1.075), (0.020, 1.020), (0.125, 1.080),
    (0.265, 1.140), (0.400, 1.085), (0.490, 0.925), (0.500, 0.740),
    (0.460, 0.550), (0.400, 0.340), (0.340, 0.140), (0.290, 0.025),
    (0.210, 0.000), (0.140, 0.060), (0.100, 0.220), (0.060, 0.375),
    (0.000, 0.440), (-0.060, 0.375), (-0.100, 0.220), (-0.130, 0.060),
]

TOOTH_SWIRL = [(-0.02, 0.93), (0.12, 0.965), (0.27, 1.035), (0.37, 1.005), (0.41, 0.90)]


def build_tooth(mats, coll, x_center, base_top):
    scale = TOOTH_HEIGHT / 1.14
    outline = catmull([(x * scale, y * scale) for x, y in TOOTH_OUTLINE], samples=14)
    half = TOOTH_DEPTH / 2
    loc = Matrix.Translation((x_center, 0.0, base_top)) @ FRONT

    rim_w, rim_bevel = 0.0042, 0.0010
    rim = add_object("Tooth Gold Rim", curve_data(
        "ToothRim", [offset_loop(outline, rim_w), offset_loop(outline, -0.0006)],
        fill_mode="BOTH", extrude=half - rim_bevel, bevel_depth=rim_bevel,
        bevel_resolution=4, offset=-rim_bevel), coll)
    rim.matrix_world = loc
    rim = curve_to_mesh(rim)
    assign(rim, mats["gold"])
    smooth(rim, 40)

    en_bevel = 0.0042
    front = half - 0.0012
    enamel = add_object("Tooth Enamel", curve_data(
        "ToothEnamel", [outline], fill_mode="BOTH", extrude=front - en_bevel,
        bevel_depth=en_bevel, bevel_resolution=8, offset=-en_bevel), coll)
    enamel.matrix_world = loc
    enamel = curve_to_mesh(enamel)
    assign(enamel, mats["enamel"])
    smooth(enamel, 50)

    swirl_pts = catmull([(x * scale, y * scale, front - 0.0002) for x, y in TOOTH_SWIRL],
                        samples=16, closed=False)
    swirl = add_object("Tooth Gold Swirl", curve_data(
        "ToothSwirl", [swirl_pts], dims="3D", cyclic=False, bevel_depth=0.0009,
        bevel_resolution=4, use_fill_caps=True), coll)
    swirl.matrix_world = loc
    swirl = curve_to_mesh(swirl)
    assign(swirl, mats["gold"])
    smooth(swirl, 60)

    xs = [p.x for p in outline]
    return x_center + min(xs) - rim_w, x_center + max(xs) + rim_w


def resolve_font():
    for path in [FONT_PATH] + FONT_CANDIDATES:
        if path and os.path.isfile(path):
            return bpy.data.fonts.load(path, check_existing=True)
    print("[nameplate] no serif font found, using Blender's built-in font")
    return None


def build_letters(name, text, font, size, coll, mats, depth=LETTER_DEPTH, spacing=0.94):
    """Black-faced gold letters as a mesh in local XY (baseline y=0), front +Z."""
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = text
    if font:
        cu.font = font
    cu.size = size
    cu.space_character = spacing
    cu.fill_mode = "BOTH"
    b = size * 0.012
    cu.bevel_depth = b
    cu.bevel_resolution = 4
    cu.extrude = depth / 2 - b
    obj = add_object(name, cu, coll)
    obj = curve_to_mesh(obj)
    assign(obj, mats["gold"], mats["black"])
    paint_front_face(obj, 1)
    smooth(obj, 35)
    return obj


def cap_height(font, size, coll, mats):
    probe = build_letters("_probe", "H", font, size, coll, mats)
    lo, hi = local_bounds(probe)
    me = probe.data
    bpy.data.objects.remove(probe)
    bpy.data.meshes.remove(me)
    return hi.y - lo.y


def chaikin(points, iterations=4):
    """Corner-cutting smoothing of a closed loop; keeps swept strokes free of miter spikes."""
    pts = [Vector(p) for p in points]
    for _ in range(iterations):
        out = []
        for i in range(len(pts)):
            a, b = pts[i], pts[(i + 1) % len(pts)]
            out += [a.lerp(b, 0.25), a.lerp(b, 0.75)]
        pts = out
    return pts


def heart_points(width, n=40):
    s = width / 32.0
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append(Vector((x * s, (y - 4) * s)))
    return chaikin(pts)


def build_heartbeat(mats, coll, x0, x1, z, depth):
    """Heartbeat line from x0 to x1 at height z, with a heart near the end."""
    w, d = 0.0032, depth
    profile_cu = curve_data("ECGProfile", [[(-w / 2, -d / 2), (w / 2, -d / 2), (w / 2, d / 2), (-w / 2, d / 2)]])
    profile = add_object("_ECGProfile", profile_cu, coll)

    heart_w = 0.021
    tail = 0.007
    hx = x1 - tail - heart_w / 2
    left = hx - heart_w / 2 - x0 + 0.0008
    a = 0.019
    # Shape relative to the start of the beat (px): P wave, Q, R spike, S, T wave.
    px = left * 0.70
    beat = [(0, 0), (0.004, 0.12), (0.007, 0.0), (0.0095, 0.0), (0.0115, -0.22),
            (0.0150, 1.0), (0.0190, -0.62), (0.0215, 0.0), (0.0245, 0.0),
            (0.0285, 0.30), (0.0330, 0.0)]
    pts = [Vector((0, 0))]
    pts += [Vector((px + u, v * a)) for u, v in beat]
    pts.append(Vector((left, 0)))
    tail_pts = [Vector((hx + heart_w / 2 - 0.0008 - x0, 0)), Vector((x1 - x0, 0))]
    heart = [p + Vector((hx - x0, 0)) for p in heart_points(heart_w)]

    cu = curve_data("Heartbeat", [], bevel_mode="OBJECT", bevel_object=profile,
                    use_fill_caps=True)
    cu.dimensions = "2D"
    for spline_pts, cyc in ((pts, False), (tail_pts, False), (heart, True)):
        sp = cu.splines.new("POLY")
        sp.points.add(len(spline_pts) - 1)
        for p, co in zip(sp.points, spline_pts):
            p.co = (co.x, co.y, 0.0, 1.0)
        sp.use_cyclic_u = cyc
    line = add_object("Heartbeat Line", cu, coll)
    line.matrix_world = Matrix.Translation((x0, -0.004, z)) @ FRONT
    line = curve_to_mesh(line)
    bpy.data.objects.remove(profile)
    bpy.data.curves.remove(profile_cu)
    assign(line, mats["gold"], mats["black"])
    paint_front_face(line, 1)
    smooth(line, 30)
    return line


def build_base(mats, coll, x_min, x_max):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    me = bpy.data.meshes.new("MarbleBase")
    bm.to_mesh(me)
    bm.free()
    base = add_object("Marble Base", me, coll)
    base.scale = (x_max - x_min, BASE_DEPTH, BASE_HEIGHT)
    base.location = ((x_min + x_max) / 2, 0.0, BASE_HEIGHT / 2)
    me.transform(Matrix.Diagonal((*base.scale, 1.0)))
    base.scale = (1, 1, 1)
    bevel(base, 0.0022, segments=5)
    assign(base, mats["marble"])
    smooth(base, 40)
    return base


def tube(name, points, radius, coll, mat, closed_caps=True):
    obj = add_object(name, curve_data(name, [points], dims="3D", cyclic=False,
                                      bevel_depth=radius, bevel_resolution=6,
                                      use_fill_caps=closed_caps), coll)
    obj = curve_to_mesh(obj)
    assign(obj, mat)
    smooth(obj, 60)
    return obj


def cylinder(name, radius, height, coll, mat, segments=64, hollow_wall=0.0, top_radius=None):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segments,
                          radius1=radius, radius2=radius if top_radius is None else top_radius,
                          depth=height,
                          matrix=Matrix.Translation((0, 0, height / 2)))
    if hollow_wall:
        top = max(bm.faces, key=lambda f: f.calc_center_median().z)
        bmesh.ops.inset_region(bm, faces=[top], thickness=hollow_wall, depth=0)
        bmesh.ops.translate(bm, vec=(0, 0, -(height - hollow_wall * 2.5)), verts=top.verts)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = add_object(name, me, coll)
    assign(obj, mat)
    smooth(obj, 40)
    return obj


def build_instruments(mats, coll, cx, base_top):
    r_cup, h_cup = 0.0115, 0.066
    cup = cylinder("Instrument Holder", r_cup, h_cup, coll, mats["gold_satin"], hollow_wall=0.0011)
    cup.location = (cx, 0.004, base_top)
    bevel(cup, 0.0005, segments=3)
    collar = cylinder("Holder Collar", r_cup + 0.0009, 0.004, coll, mats["gold"])
    collar.location = (cx, 0.004, base_top)
    bevel(collar, 0.0006, segments=3)
    lip = cylinder("Holder Lip", r_cup + 0.0005, 0.0025, coll, mats["gold"])
    lip.location = (cx, 0.004, base_top + h_cup - 0.0025)
    bevel(lip, 0.0005, segments=3)

    c = Vector((cx, 0.004, base_top + 0.006))

    # Dental mirror: knurled handle leaning left, thin neck, round mirror head.
    m_dir = Vector((-0.13, -0.02, 1.0)).normalized()
    m_top = c + m_dir * 0.112
    tube("Mirror Handle", [c, c + m_dir * 0.03, m_top], 0.0026, coll, mats["gold_knurl"])
    head_r = 0.0135
    head_c = m_top + Vector((-0.018, -0.006, 0.040))
    attach = head_c + Vector((head_r * 0.62, 0.0, -head_r * 0.75))
    neck = catmull([m_top - m_dir * 0.004, m_top + m_dir * 0.010,
                    m_top + m_dir * 0.018 + Vector((-0.001, -0.002, 0.004)), attach],
                   samples=10, closed=False)
    tube("Mirror Neck", neck, 0.0011, coll, mats["gold"])
    ring = cylinder("Mirror Head", head_r + 0.0012, 0.0032, coll, mats["gold"], segments=96)
    tilt = Matrix.Rotation(math.radians(56), 4, "X") @ Matrix.Rotation(math.radians(-12), 4, "Y")
    ring.matrix_world = Matrix.Translation(head_c) @ Matrix.Rotation(math.radians(8), 4, "Z") @ tilt \
        @ Matrix.Translation((0, 0, -0.0016))
    bevel(ring, 0.0007, segments=4)
    glass = cylinder("Mirror Glass", head_r - 0.0002, 0.0005, coll, mats["mirror"], segments=96)
    glass.matrix_world = Matrix.Translation(head_c) @ Matrix.Rotation(math.radians(8), 4, "Z") @ tilt \
        @ Matrix.Translation((0, 0, 0.0014))

    # Explorer probe: knurled handle leaning right, thin neck ending in a hook.
    p0 = c + Vector((0.0025, 0.002, 0.0))
    p_dir = Vector((0.11, 0.015, 1.0)).normalized()
    p_top = p0 + p_dir * 0.098
    tube("Probe Handle", [p0, p0 + p_dir * 0.03, p_top], 0.0024, coll, mats["gold_knurl"])
    cone = cylinder("Probe Taper", 0.0024, 0.006, coll, mats["gold"], top_radius=0.0011)
    cone.matrix_world = Matrix.Translation(p_top) @ p_dir.to_track_quat("Z", "Y").to_matrix().to_4x4()
    hook_c = p_top + p_dir * 0.032 + Vector((0.005, 0, 0))
    hook = [p_top, p_top + p_dir * 0.016, p_top + p_dir * 0.028]
    for ang in range(180, -60, -20):
        a = math.radians(ang)
        hook.append(hook_c + Vector((math.cos(a) * 0.0052, 0, math.sin(a) * 0.0052)))
    tube("Probe Neck", catmull(hook, samples=8, closed=False), 0.00085, coll, mats["gold"])
    return cx + r_cup + 0.001


# ---------------------------------------------------------------------------
# Camera, lights, render
# ---------------------------------------------------------------------------

def area_light(name, coll, loc, target, power, size, color=(1, 1, 1), size_y=None):
    li = bpy.data.lights.new(name, "AREA")
    li.energy = power
    li.color = color
    if size_y:
        li.shape = "RECTANGLE"
        li.size, li.size_y = size, size_y
    else:
        li.size = size
    obj = add_object(name, li, coll)
    obj.location = loc
    obj.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return obj


def build_lighting(coll, target):
    t = Vector(target)
    area_light("Key Softbox", coll, t + Vector((-0.55, -0.60, 0.70)), t, 32, 0.7, (1.0, 0.92, 0.82))
    area_light("Fill", coll, t + Vector((0.75, -0.55, 0.35)), t, 9, 0.9, (0.95, 0.97, 1.0))
    area_light("Top Strip", coll, t + Vector((0.0, -0.15, 0.75)), t, 14, 0.9, (1.0, 0.96, 0.9), size_y=0.18)
    area_light("Rim", coll, t + Vector((0.25, 0.65, 0.45)), t, 22, 0.5, (1.0, 0.88, 0.7))
    area_light("Ceiling Panel", coll, t + Vector((0.0, 0.05, 1.3)), t + Vector((0.0, -0.1, 0.0)), 25, 1.6,
               (1.0, 0.95, 0.88))

    world = bpy.context.scene.world or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    try:
        world.use_nodes = True
    except AttributeError:
        pass
    bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs["Color"].default_value = (0.82, 0.8, 0.77, 1)
    bg.inputs["Strength"].default_value = 0.4


def build_camera(coll, target, focus):
    cam = bpy.data.cameras.new("Camera")
    cam.lens = 50
    cam.dof.use_dof = True
    cam.dof.aperture_fstop = 3.2
    obj = add_object("Camera", cam, coll)
    t = Vector(target)
    obj.location = t + Vector((-0.13, -0.72, 0.15))
    obj.rotation_euler = (t - obj.location).to_track_quat("-Z", "Y").to_euler()
    cam.dof.focus_distance = (Vector(focus) - obj.location).length
    bpy.context.scene.camera = obj
    return obj


def enable_gpu(scene):
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
    except (KeyError, AttributeError):
        return "CPU"
    for kind in ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"):
        try:
            prefs.compute_device_type = kind
            prefs.get_devices()
        except (TypeError, ValueError, AttributeError):
            continue
        devices = [d for d in prefs.devices if d.type == kind]
        if devices:
            for d in devices:
                d.use = True
            scene.cycles.device = "GPU"
            return kind
    return "CPU"


def setup_render(samples, percent):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 12
    scene.cycles.glossy_bounces = 8
    scene.cycles.transparent_max_bounces = 8
    scene.render.resolution_x, scene.render.resolution_y = RESOLUTION
    scene.render.resolution_percentage = percent
    scene.render.film_transparent = False
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.length_unit = "CENTIMETERS"
    for transform in ("AgX", "Filmic"):
        try:
            scene.view_settings.view_transform = transform
            break
        except TypeError:
            continue
    for look in ("AgX - Punchy", "Punchy", "AgX - Medium High Contrast", "Medium High Contrast"):
        try:
            scene.view_settings.look = look
            break
        except TypeError:
            continue
    return enable_gpu(scene)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build(title=TITLE, name=NAME, font_path=None):
    global FONT_PATH
    if font_path:
        FONT_PATH = font_path
    clear_scene()
    plate = collection("Nameplate")
    mats = build_materials()
    base_top = BASE_HEIGHT

    tooth_l, tooth_r = build_tooth(mats, plate, 0.0, base_top)
    font = resolve_font()

    # Size the letters so the capital height matches NAME_CAP_HEIGHT.
    size = 0.08 * NAME_CAP_HEIGHT / cap_height(font, 0.08, plate, mats)
    name_obj = build_letters("Name Letters", name, font, size, plate, mats)
    lo, hi = local_bounds(name_obj)
    squeeze = NAME_WIDTH / (hi.x - lo.x)
    name_obj.data.transform(Matrix.Diagonal((squeeze, 1, 1, 1)))
    lo, hi = local_bounds(name_obj)
    name_x = tooth_r + 0.004 - lo.x
    name_obj.matrix_world = Matrix.Translation((name_x, -0.004, base_top - lo.y)) @ FRONT
    name_right = name_x + hi.x

    t_size = size * TITLE_SCALE
    title_obj = build_letters("Title Letters", title, font, t_size, plate, mats,
                              depth=LETTER_DEPTH * 0.9)
    title_obj.data.transform(Matrix.Diagonal((squeeze, 1, 1, 1)))
    tlo, thi = local_bounds(title_obj)
    title_base = base_top + (hi.y - lo.y) - 0.0008
    title_x = name_x + lo.x + 0.003 - tlo.x
    title_obj.matrix_world = Matrix.Translation((title_x, -0.004, title_base - tlo.y)) @ FRONT
    title_cap = NAME_CAP_HEIGHT * TITLE_SCALE

    cup_x = name_right + 0.004 + 0.0115
    right = build_instruments(mats, plate, cup_x, base_top)
    build_heartbeat(mats, plate, title_x + thi.x - 0.0008, cup_x - 0.030,
                    title_base + title_cap * 0.42, LETTER_DEPTH * 0.6)

    x_min, x_max = tooth_l - 0.014, right + 0.016
    build_base(mats, plate, x_min, x_max)
    cx = (x_min + x_max) / 2

    rig = collection("Camera & Lights")
    target = (cx, 0.0, 0.085)
    build_lighting(rig, target)
    build_camera(rig, target, (cx, -0.012, 0.06))
    return cx


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    opts = {"samples": SAMPLES, "percent": 100}
    i = 0
    while i < len(argv):
        key = argv[i]
        val = argv[i + 1]
        if key in ("--samples", "--percent"):
            opts[key[2:]] = int(val)
        else:
            opts[key[2:]] = val
        i += 2
    return opts


def main():
    opts = parse_args()
    build(opts.get("title", TITLE), opts.get("name", NAME), opts.get("font"))
    device = setup_render(opts["samples"], opts["percent"])
    print(f"[nameplate] scene built, Cycles device: {device}")
    if "save" in opts:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(opts["save"]))
    if "render" in opts:
        bpy.context.scene.render.filepath = os.path.abspath(opts["render"])
        bpy.ops.render.render(write_still=True)
        print(f"[nameplate] rendered {opts['render']}")


if __name__ == "__main__":
    main()
