"""
GABA-A Receptor  -  educational clay-style model for Blender
=============================================================

نموذج مستقبل GABA-A بأسلوب "صلصال/بلاستيك" لبلندر.

* Real-world scale: the base is exactly 30 cm wide (scene units = metres).
* Everything is procedural: run the script and the full scene is built
  (model + labels + lights + camera + Cycles render settings).

HOW TO USE (Blender 4.2 or newer, 5.x supported):
    1. Open Blender  ->  "Scripting" workspace.
    2. Text Editor -> Open -> choose this file  ->  press "Run Script" (Alt+P).
    3. Press F12 to render  (Cycles, 1920 x 1280).

    Or from a terminal (builds, saves a .blend and renders a PNG):
        blender -b -P gaba_a_receptor.py -- --save model.blend --render out.png

NOTE: the script clears the current scene before building.

Dimensions (approx.):  W 30 cm  x  D 12.5 cm  x  H 23 cm
"""

import bpy
import bmesh
import math
import os
import sys
from mathutils import Vector, Matrix

# --------------------------------------------------------------------------
#  Units:  every number written below is in CENTIMETRES; S converts to metres
# --------------------------------------------------------------------------
S = 0.01


def V(x, y, z):
    return Vector((x, y, z)) * S


# --------------------------------------------------------------------------
#  Palette (sRGB hex, taken from the reference picture)
# --------------------------------------------------------------------------
COL = {
    "alpha":      "#8E52D8",   # purple  α (front piece)
    "alpha_back": "#6E3CB6",   # darker purple (back piece of α)
    "beta":       "#2F6FDB",   # blue    β
    "gamma":      "#F3C300",   # yellow  γ
    "channel":    "#22A82A",   # green pore
    "ion":        "#86F23A",   # bright green Cl- ions
    "gaba":       "#E0161F",   # red GABA ligand
    "diazepam":   "#3AB0F2",   # light-blue diazepam
    "head":       "#F5C400",   # lipid heads
    "tail":       "#F4F2EE",   # lipid tails
    "navy":       "#16265E",   # base
    "title":      "#1A2E6E",   # title panel
    "title_rim":  "#2B4796",   # title panel outline
    "white":      "#F8F8F6",
    "ink":        "#172554",   # dark label text
    "red_rim":    "#D62835",
    "blue_rim":   "#2A78D6",
    "wall":       "#BEBAB4",
}


def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_rgba(h):
    h = h.lstrip("#")
    return tuple(srgb_to_linear(int(h[i:i + 2], 16) / 255.0) for i in (0, 2, 4)) + (1.0,)


# --------------------------------------------------------------------------
#  Scene reset
# --------------------------------------------------------------------------
def clear_scene():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for coll in list(bpy.data.collections):
        bpy.data.collections.remove(coll)
    for block in (bpy.data.meshes, bpy.data.curves, bpy.data.metaballs,
                  bpy.data.materials, bpy.data.lights, bpy.data.cameras,
                  bpy.data.node_groups, bpy.data.images):
        for item in list(block):
            if item.users == 0:
                block.remove(item)


_COLLS = {}


def coll(name):
    if name not in _COLLS:
        c = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(c)
        _COLLS[name] = c
    return _COLLS[name]


def link(ob, collection):
    collection.objects.link(ob)
    return ob


def smooth(me):
    for p in me.polygons:
        p.use_smooth = True


def flat_normals_fix(ob):
    """Keep big flat faces flat when bevelled faces are smooth-shaded."""
    if hasattr(ob.data, "use_auto_smooth"):          # Blender < 4.1
        ob.data.use_auto_smooth = True
    m = ob.modifiers.new("WeightedNormal", "WEIGHTED_NORMAL")
    m.keep_sharp = True
    m.weight = 100


# --------------------------------------------------------------------------
#  Materials
# --------------------------------------------------------------------------
def set_in(node, names, value):
    for n in names if isinstance(names, (list, tuple)) else [names]:
        if n in node.inputs:
            node.inputs[n].default_value = value
            return


def mat_clay(name, hexcol, rough=0.5, sss=0.12, coat=0.08, bump=0.22, emit=0.0):
    """Matte polymer-clay look: fine grain + slight hand-made unevenness."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (700, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (400, 0)
    col = hex_rgba(hexcol)
    set_in(bsdf, "Base Color", col)
    set_in(bsdf, "Roughness", rough)
    set_in(bsdf, ["Subsurface Weight", "Subsurface"], sss)
    set_in(bsdf, "Subsurface Scale", 0.003)
    set_in(bsdf, "Subsurface Radius", Vector((1.0, 0.5, 0.35)))
    set_in(bsdf, ["Coat Weight", "Clearcoat"], coat)
    set_in(bsdf, ["Coat Roughness", "Clearcoat Roughness"], 0.3)
    set_in(bsdf, ["Sheen Weight", "Sheen"], 0.15)
    if emit > 0:
        set_in(bsdf, ["Emission Color", "Emission"], col)
        set_in(bsdf, "Emission Strength", emit)
    nt.links.new(bsdf.outputs[0], out.inputs["Surface"])
    if bump > 0:
        tc = nt.nodes.new("ShaderNodeTexCoord")
        tc.location = (-800, 0)
        prev = None
        for i, (scale, strength, dist) in enumerate(((14.0, bump * 0.35, 0.002),
                                                     (260.0, bump, 0.0004))):
            nz = nt.nodes.new("ShaderNodeTexNoise")
            nz.location = (-550, -i * 250)
            nz.inputs["Scale"].default_value = scale
            nz.inputs["Detail"].default_value = 5.0
            bp = nt.nodes.new("ShaderNodeBump")
            bp.location = (-250 + i * 200, -i * 250)
            bp.inputs["Strength"].default_value = strength
            bp.inputs["Distance"].default_value = dist
            nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
            nt.links.new(nz.outputs["Fac"], bp.inputs["Height"])
            if prev:
                nt.links.new(prev.outputs["Normal"], bp.inputs["Normal"])
            prev = bp
        nt.links.new(prev.outputs["Normal"], bsdf.inputs["Normal"])
    return m


def mat_wood(name="Wood_Table"):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1.0, 14.0, 1.0)
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.wave_type = "BANDS"
    wave.bands_direction = "Y"
    wave.inputs["Scale"].default_value = 6.0
    wave.inputs["Distortion"].default_value = 9.0
    wave.inputs["Detail"].default_value = 4.0
    wave.inputs["Detail Scale"].default_value = 2.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = hex_rgba("#B8946B")
    ramp.color_ramp.elements[1].color = hex_rgba("#D6B892")
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], wave.inputs["Vector"])
    nt.links.new(wave.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    set_in(bsdf, "Roughness", 0.55)
    set_in(bsdf, ["Coat Weight", "Clearcoat"], 0.15)
    nt.links.new(bsdf.outputs[0], out.inputs["Surface"])
    return m


def mat_matte(name, hexcol, rough=0.9):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    set_in(b, "Base Color", hex_rgba(hexcol))
    set_in(b, "Roughness", rough)
    return m


# --------------------------------------------------------------------------
#  Geometry helpers  (all sizes in cm)
# --------------------------------------------------------------------------
def rbox(name, dims, loc, collection, mat, bevel=0.3, seg=6, rot=(0, 0, 0)):
    """Rounded box: real dimensions in the mesh, bevel as a modifier."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * dims[0], v.co.y * dims[1], v.co.z * dims[2])) * S
    bm.to_mesh(me)
    bm.free()
    smooth(me)
    ob = link(bpy.data.objects.new(name, me), collection)
    ob.location = V(*loc)
    ob.rotation_euler = rot
    b = ob.modifiers.new("Bevel", "BEVEL")
    b.width = bevel * S
    b.segments = seg
    b.limit_method = "NONE"
    flat_normals_fix(ob)
    me.materials.append(mat)
    return ob


def sphere(name, r, loc, collection, mat, seg=48):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=seg // 2, radius=r * S)
    bm.to_mesh(me)
    bm.free()
    smooth(me)
    me.materials.append(mat)
    ob = link(bpy.data.objects.new(name, me), collection)
    ob.location = V(*loc)
    return ob


def flat_arrow(name, length, collection, mat, loc, plane_rot, shaft=0.35,
               head_w=1.0, head_l=0.8, depth=0.25, angle_deg=0.0):
    """2-D arrow (pointing +X when angle=0) extruded along Y.
    plane_rot: Matrix (3x3) that tilts the arrow plane (e.g. on a slope)."""
    L, sw, hw, hl = length, shaft, head_w, head_l
    pts = [(0, -sw / 2), (L - hl, -sw / 2), (L - hl, -hw / 2), (L, 0),
           (L - hl, hw / 2), (L - hl, sw / 2), (0, sw / 2)]
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    vs = [bm.verts.new(Vector((u - L / 2, 0, v)) * S) for u, v in pts]
    f = bm.faces.new(vs)
    res = bmesh.ops.extrude_face_region(bm, geom=[f])
    nv = [g for g in res["geom"] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=nv, vec=Vector((0, depth * S, 0)))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bmesh.ops.translate(bm, verts=bm.verts, vec=Vector((0, -depth * S / 2, 0)))
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    ob = link(bpy.data.objects.new(name, me), collection)
    rot = plane_rot.to_4x4() @ Matrix.Rotation(math.radians(-angle_deg), 4, "Y")
    ob.matrix_world = Matrix.Translation(V(*loc)) @ rot
    b = ob.modifiers.new("Bevel", "BEVEL")
    b.width = 0.05 * S
    b.segments = 3
    b.limit_method = "ANGLE"
    smooth(me)
    flat_normals_fix(ob)
    return ob


def tube_arrow(name, start, end, collection, mat, r=0.13, head_r=0.38, head_l=0.9):
    """3-D pointer arrow (cylinder + cone) from start to end (cm)."""
    a, b = Vector(start), Vector(end)
    d = b - a
    L = d.length
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=32, radius1=r * S, radius2=r * S,
                          depth=(L - head_l) * S,
                          matrix=Matrix.Translation(Vector((0, 0, (L - head_l) / 2)) * S))
    bmesh.ops.create_cone(bm, cap_ends=True, segments=32, radius1=head_r * S, radius2=0.0,
                          depth=head_l * S,
                          matrix=Matrix.Translation(Vector((0, 0, L - head_l / 2)) * S))
    bm.to_mesh(me)
    bm.free()
    smooth(me)
    me.materials.append(mat)
    ob = link(bpy.data.objects.new(name, me), collection)
    q = d.normalized().to_track_quat("Z", "Y")
    ob.matrix_world = Matrix.Translation(a * S) @ q.to_matrix().to_4x4()
    bv = ob.modifiers.new("Bevel", "BEVEL")
    bv.width = 0.03 * S
    bv.segments = 2
    bv.limit_method = "ANGLE"
    flat_normals_fix(ob)
    return ob


def rod(name, start, end, collection, mat, r=0.3):
    """Closed cylinder from start to end (cm) - hidden print support strut."""
    a, b = Vector(start), Vector(end)
    d = b - a
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=24, radius1=r * S, radius2=r * S,
                          depth=d.length * S,
                          matrix=Matrix.Translation(Vector((0, 0, d.length / 2)) * S))
    bm.to_mesh(me)
    bm.free()
    smooth(me)
    me.materials.append(mat)
    ob = link(bpy.data.objects.new(name, me), collection)
    ob.matrix_world = Matrix.Translation(a * S) @ \
        d.normalized().to_track_quat("Z", "Y").to_matrix().to_4x4()
    return ob


# --------------------------------------------------------------------------
#  Text helpers
# --------------------------------------------------------------------------
FONT = None


def load_font():
    cands = [
        r"C:\Windows\Fonts\seguibl.ttf",          # Segoe UI Black
        r"C:\Windows\Fonts\segoeuib.ttf",         # Segoe UI Bold
        r"C:\Windows\Fonts\arialbd.ttf",
        "/System/Library/Fonts/Supplemental/Arial Black.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]
    for p in cands:
        if os.path.exists(p):
            try:
                return bpy.data.fonts.load(p, check_existing=True)
            except Exception:
                pass
    return None   # Blender built-in font (also has Greek letters)


def text(name, body, size, collection, mat, extrude=0.08, bevel=0.015):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = body
    if FONT:
        cu.font = FONT
    cu.size = size * S
    cu.extrude = extrude * S
    cu.bevel_depth = bevel * S
    cu.bevel_resolution = 3
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    cu.resolution_u = 24
    ob = link(bpy.data.objects.new(name, cu), collection)
    ob.data.materials.append(mat)
    return ob


def text_width_cm(ob):
    bpy.context.view_layer.update()
    return ob.dimensions.x / S


def place_row(pieces, center, frame, gap=0.25, normal_off=0.0):
    """Lay pieces left->right centred on `center` (cm) in a tilted frame.

    pieces: list of (object, width_cm or None, vertical_offset_cm)
    frame : 3x3 rotation matrix; columns = right, normal(-depth), up
    """
    widths = [w if w is not None else text_width_cm(o) for o, w, _ in pieces]
    total = sum(widths) + gap * (len(pieces) - 1)
    right = frame @ Vector((1, 0, 0))
    up = frame @ Vector((0, 0, 1))
    out = frame @ Vector((0, -1, 0))
    cursor = -total / 2
    c = Vector(center)
    for (ob, _, dz), w in zip(pieces, widths):
        p = c + right * (cursor + w / 2) + up * dz + out * normal_off
        if ob.type == "FONT":
            ob.matrix_world = Matrix.Translation(p * S) @ (
                frame.to_4x4() @ Matrix.Rotation(math.radians(90), 4, "X"))
        else:
            mw = ob.matrix_world.copy()
            ob.matrix_world = Matrix.Translation(p * S) @ mw.to_3x3().to_4x4()
        cursor += w + gap


# --------------------------------------------------------------------------
#  2-D outline  ->  thick clay slab  (flat front, fully rounded edges)
# --------------------------------------------------------------------------
def rrect_pts(w, h, r, cx=0.0, cz=0.0, seg=10):
    """Rounded rectangle outline (cm)."""
    pts = []
    corners = [(w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90),
               (-w / 2 + r, -h / 2 + r, 180), (w / 2 - r, -h / 2 + r, 270)]
    for x0, z0, a0 in corners:
        for i in range(seg + 1):
            a = math.radians(a0 + 90 * i / seg)
            pts.append((cx + x0 + r * math.cos(a), cz + z0 + r * math.sin(a)))
    return pts


def blob_pts(cx, cz, rx, rz, n=48, squash_top=0.0, bulge=0.0):
    """Soft super-ellipse outline (for β): a little flatter on top."""
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        c, s_ = math.cos(a), math.sin(a)
        e = 2.4                                      # >2 = squarer
        x = rx * math.copysign(abs(c) ** (2 / e), c) * (1 + bulge * s_)
        z = rz * math.copysign(abs(s_) ** (2 / e), s_)
        if z > 0:
            z *= (1 - squash_top)
        pts.append((cx + x, cz + z))
    return pts


def slab(name, pts, collection, mat, front_y, depth, bevel, smooth_curve=True,
         mirror=False):
    """Extruded, bevelled 2-D outline in the XZ plane.

    pts      : outline points (x, z) in cm - this IS the final silhouette
    front_y  : y of the front face (camera looks toward +Y)
    depth    : total thickness;  bevel: edge rounding radius
    smooth_curve: True = Bezier/auto handles through the points, False = polyline
    """
    if mirror:
        pts = [(-x, z) for x, z in reversed(pts)]
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "2D"
    cu.fill_mode = "BOTH"
    cu.bevel_depth = bevel * S
    cu.bevel_resolution = 8
    cu.extrude = max(depth / 2 - bevel, 0.0005) * S
    cu.offset = -bevel * S
    cu.resolution_u = 24 if smooth_curve else 2
    if smooth_curve:
        sp = cu.splines.new("BEZIER")
        sp.bezier_points.add(len(pts) - 1)
        for bp, (x, z) in zip(sp.bezier_points, pts):
            bp.co = (x * S, z * S, 0)
            bp.handle_left_type = bp.handle_right_type = "AUTO"
    else:
        sp = cu.splines.new("POLY")
        sp.points.add(len(pts) - 1)
        for p, (x, z) in zip(sp.points, pts):
            p.co = (x * S, z * S, 0, 1)
    sp.use_cyclic_u = True
    sp.use_smooth = True
    cu.materials.append(mat)
    ob = link(bpy.data.objects.new(name, cu), collection)
    ob.rotation_euler = (math.radians(90), 0, 0)
    ob.location = V(0, front_y + depth / 2, 0)
    return ob


# ==========================================================================
#  SHAPES  (traced from the reference picture; x,z in cm, left side)
# ==========================================================================
ALPHA_FRONT = [(-8.4, 14.0), (-7.8, 15.8), (-6.2, 16.5), (-4.7, 16.0), (-3.0, 15.0),
               (-1.75, 14.1), (-1.45, 12.4), (-1.5, 9.8), (-1.65, 7.2), (-2.1, 5.1),
               (-3.1, 3.8), (-4.3, 3.9), (-5.1, 5.4), (-5.6, 7.4), (-6.2, 9.4),
               (-7.0, 10.9), (-8.0, 12.2)]
ALPHA_BACK = [(-6.9, 11.4), (-5.8, 12.0), (-4.8, 10.4), (-4.4, 7.8), (-4.55, 5.7),
              (-5.0, 4.75), (-5.75, 4.55), (-6.35, 5.2), (-6.6, 7.0), (-6.8, 9.4)]
GAMMA = [(-2.05, 18.4), (-1.5, 19.45), (0, 19.7), (1.5, 19.45), (2.05, 18.4),
         (1.75, 16.4), (1.1, 14.6), (0, 14.1), (-1.1, 14.6), (-1.75, 16.4)]


# ==========================================================================
#  BUILD
# ==========================================================================
def build():
    global FONT
    clear_scene()
    _COLLS.clear()
    FONT = load_font()

    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.length_unit = "CENTIMETERS"
    sc.unit_settings.scale_length = 1.0

    C_base = coll("01_Base")
    C_mem = coll("02_Membrane")
    C_rec = coll("03_Receptor")
    C_lab = coll("04_Labels")
    C_env = coll("05_Studio")

    M = {k: mat_clay("M_" + k, v) for k, v in COL.items()
         if k not in ("wall", "channel", "ion", "gaba", "diazepam", "navy", "white", "ink")}
    M["channel"] = mat_clay("M_channel", COL["channel"], emit=0.15)
    M["ion"] = mat_clay("M_ion", COL["ion"], rough=0.35, emit=0.8, bump=0.05)
    M["gaba"] = mat_clay("M_gaba", COL["gaba"], rough=0.35, coat=0.3, bump=0.05)
    M["diazepam"] = mat_clay("M_diazepam", COL["diazepam"], rough=0.35, coat=0.3, bump=0.05)
    M["navy"] = mat_clay("M_navy", COL["navy"], rough=0.45, bump=0.10)
    M["white"] = mat_clay("M_white", COL["white"], rough=0.45, bump=0.06)
    M["ink"] = mat_clay("M_ink", COL["ink"], rough=0.45, bump=0.03)
    up = Matrix.Identity(3)

    # ------------------------------------------------------------------ BASE
    rbox("Base_Pedestal", (30.0, 12.0, 4.0), (0, -1.0, 2.0), C_base, M["navy"],
         bevel=0.45, seg=8)
    rbox("Base_MembranePlatform", (24.7, 5.0, 3.5), (0, 1.3, 5.75), C_base, M["navy"],
         bevel=0.3, seg=6)

    # ------------------------------------------------------------- MEMBRANE
    # PRINTABLE: the tails are not free-floating strands any more. Each side
    # is one SOLID white core block; the heads sit half-buried in its top and
    # bottom, and the front-row tails are raised relief ON the block face.
    head_r = 0.7
    z_top, z_bot = 13.0, 8.15
    rows_y = [-0.5, 0.8, 2.1, 3.3]
    x_in, x_out = 5.0, 13.6                 # core block span (inner end hides in α)
    core_front = -0.3
    for side, nm in ((-1, "L"), (1, "R")):
        w = x_out - x_in
        rbox("Lipid_Core_" + nm, (w, 3.3 - core_front + 0.2, z_top - 7.45),
             (side * (x_in + w / 2), (core_front + 3.5) / 2, (z_top + 7.45) / 2),
             C_mem, M["tail"], bevel=0.2, seg=4)

    hm = bpy.data.meshes.new("Lipid_Heads")
    bm = bmesh.new()
    tails = bpy.data.curves.new("Lipid_Tails_Relief", "CURVE")
    tails.dimensions = "3D"
    tails.bevel_depth = 0.16 * S
    tails.bevel_resolution = 3
    tails.use_fill_caps = True
    for side in (-1, 1):
        for ri, y in enumerate(rows_y):
            x = 5.6 + (0.69 if ri % 2 else 0.0)
            while x <= 13.0:
                xx = side * x
                for zc, sgn in ((z_top, -1), (z_bot, 1)):
                    bmesh.ops.create_uvsphere(bm, u_segments=40, v_segments=20,
                                              radius=head_r * S,
                                              matrix=Matrix.Translation(V(xx, y, zc)))
                    if ri:                  # only the front row is seen
                        continue
                    for t in (-0.2, 0.2):
                        sp = tails.splines.new("NURBS")
                        prof = [0.0, 0.10, 0.02, 0.12, 0.04]      # gentle S-wave
                        sp.points.add(len(prof) - 1)
                        for i, off in enumerate(prof):
                            f_ = i / (len(prof) - 1)
                            pz = zc + sgn * (head_r * 0.6 + f_ * 1.8)
                            px = xx + t + math.copysign(off, t)
                            # centre ON the core face -> half buried, prints as relief
                            sp.points[i].co = (*(V(px, core_front, pz)), 1.0)
                        sp.order_u = 3
                        sp.use_endpoint_u = True
                        sp.use_smooth = True
                x += 1.38

    # the same tails ENGRAVED (grooves) into the outer END face and the BACK face:
    # looks finished from the side / behind and keeps the part's exact size
    core_back = 3.5
    eng = bpy.data.curves.new("Lipid_Tails_Engrave", "CURVE")
    eng.dimensions = "3D"
    eng.bevel_depth = 0.16 * S
    eng.bevel_resolution = 3
    eng.use_fill_caps = True

    def relief_tail(base_xyz, along, t, zc, sgn, k):
        sp = eng.splines.new("NURBS")
        prof = [0.0, 0.10, 0.02, 0.12, 0.04]
        sp.points.add(len(prof) - 1)
        for i, off in enumerate(prof):
            f_ = i / (len(prof) - 1)
            pz = zc + sgn * (head_r * 0.6 + f_ * 1.8)
            d = t + math.copysign(off, t)
            p = Vector(base_xyz) + Vector(along) * d
            sp.points[i].co = (*(V(p.x, p.y, pz)), 1.0)
        sp.order_u = 3
        sp.use_endpoint_u = True
        sp.use_smooth = True

    for side in (-1, 1):
        for y in (0.45, 1.6, 2.75):                                   # end face
            for zc, sgn in ((z_top, -1), (z_bot, 1)):
                for t in (-0.2, 0.2):
                    relief_tail((side * x_out, y, 0), (0, 1, 0), t, zc, sgn, 0)
        x = 5.6 + 0.69
        while x <= 13.0:                                             # back face
            for zc, sgn in ((z_top, -1), (z_bot, 1)):
                for t in (-0.2, 0.2):
                    relief_tail((side * x, core_back, 0), (1, 0, 0), t, zc, sgn, 0)
            x += 1.38
    C_help = coll("99_Helpers")
    eng_ob = link(bpy.data.objects.new("Lipid_Tails_Engrave", eng), C_help)
    bpy.context.view_layer.update()
    cut_me = bpy.data.meshes.new_from_object(
        eng_ob.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    bpy.data.objects.remove(eng_ob, do_unlink=True)
    cutter = link(bpy.data.objects.new("Lipid_Engrave_Cutter", cut_me), C_help)
    cutter.hide_render = True
    cutter.hide_viewport = True
    for nm in ("L", "R"):
        bo = bpy.data.objects["Lipid_Core_" + nm].modifiers.new("Engrave", "BOOLEAN")
        bo.operation = "DIFFERENCE"
        bo.object = cutter
        bo.solver = "EXACT"
    bm.to_mesh(hm)
    bm.free()
    smooth(hm)
    hm.materials.append(M["head"])
    link(bpy.data.objects.new("Lipid_Heads", hm), C_mem)
    tails.materials.append(M["tail"])
    link(bpy.data.objects.new("Lipid_Tails_Relief", tails), C_mem)

    # ------------------------------------------------------------- RECEPTOR
    A_FRONT_Y = -3.2
    for side, nm in ((-1, "L"), (1, "R")):
        mir = side > 0
        slab("Alpha_" + nm, ALPHA_FRONT, C_rec, M["alpha"], A_FRONT_Y, 3.2, 1.0,
             mirror=mir)
        slab("Alpha_" + nm + "_Back", ALPHA_BACK, C_rec, M["alpha_back"], -2.4, 2.6,
             0.6, mirror=mir)
        slab("Beta_" + nm, blob_pts(side * 3.55, 16.4, 2.5, 2.4, squash_top=0.06),
             C_rec, M["beta"], -2.3, 2.8, 1.0, smooth_curve=False)
    slab("Gamma", GAMMA, C_rec, M["gamma"], -1.5, 2.6, 0.9)
    slab("Channel_Pore", rrect_pts(4.0, 10.4, 1.2, 0, 9.7), C_rec, M["channel"],
         -1.0, 2.2, 0.6, smooth_curve=False)

    sphere("Cl_Ion_1", 0.62, (0, -1.2, 12.2), C_rec, M["ion"])
    sphere("Cl_Ion_2", 0.62, (0, -1.2, 9.5), C_rec, M["ion"])
    flat_arrow("Channel_Arrow", 1.7, C_rec, M["ion"], (0, -1.1, 7.4), up,
               shaft=0.3, head_w=1.0, head_l=0.75, depth=0.3, angle_deg=-90)
    sphere("Cl_Ion_Exit", 1.3, (0, -3.0, 5.1), C_rec, M["ion"])

    gaba = sphere("GABA_Ligand", 0.82, (-5.7, A_FRONT_Y + 0.15, 15.85), C_rec, M["gaba"])
    diaz = sphere("Diazepam_Ligand", 0.8, (5.85, A_FRONT_Y + 0.15, 15.65), C_rec,
                  M["diazepam"])

    # greek letters on the flat front faces
    for nm, ch, x, z, sz, fy, mat in (
        ("Alpha_L", "α", -4.5, 12.2, 2.9, A_FRONT_Y, M["white"]),
        ("Alpha_R", "α", 4.5, 12.2, 2.9, A_FRONT_Y, M["white"]),
        ("Beta_L", "β", -3.6, 16.9, 2.2, -2.3, M["white"]),
        ("Beta_R", "β", 3.6, 16.9, 2.2, -2.3, M["white"]),
        ("Gamma", "γ", 0.0, 18.0, 2.4, -1.5, M["ink"]),
    ):
        t = text("Letter_" + nm, ch, sz, C_lab, mat, extrude=0.15)
        place_row([(t, None, 0)], (x, fy - 0.05, z), up)

    t = text("Ion_Cl_Text", "Cl", 1.2, C_lab, M["white"], extrude=0.3)
    m = text("Ion_Cl_minus", "−", 0.75, C_lab, M["white"], extrude=0.3)
    place_row([(t, None, -0.05), (m, None, 0.42)], (0.05, -4.1, 5.1), up, gap=0.1)

    # ------------------------------------------------------------------ TITLE
    rbox("Title_Stand", (5.0, 1.0, 14.5), (0, 1.6, 14.25), C_lab, M["white"], bevel=0.3)
    slab("Title_Panel_Rim", rrect_pts(19.2, 2.75, 0.95, 0, 21.75), C_lab,
         M["title_rim"], 0.55, 0.9, 0.25, smooth_curve=False)
    slab("Title_Panel", rrect_pts(18.8, 2.4, 0.8, 0, 21.75), C_lab, M["title"],
         0.4, 0.9, 0.25, smooth_curve=False)
    t1 = text("Title_GABA", "GABA", 2.25, C_lab, M["white"], extrude=0.15)
    t2 = text("Title_sub_A", "A", 1.35, C_lab, M["white"], extrude=0.15)
    t3 = text("Title_Receptor", "Receptor", 2.25, C_lab, M["white"], extrude=0.15)
    place_row([(t1, None, 0.0), (t2, text_width_cm(t2) + 0.6, -0.62), (t3, None, 0.0)],
              (0, 0.35, 21.8), up, gap=0.05)

    # ------------------------------------------------------------- CALLOUTS
    def callout(name, label, cx, cz, w, rim_mat):
        h = 1.9
        slab(name + "_Rim", rrect_pts(w, h, 0.8, cx, cz), C_lab, rim_mat, -2.2, 0.7,
             0.15, smooth_curve=False)
        slab(name + "_Face", rrect_pts(w - 0.36, h - 0.36, 0.62, cx, cz), C_lab,
             M["white"], -2.28, 0.7, 0.12, smooth_curve=False)
        t = text(name + "_Text", label, 1.4, C_lab, M["ink"], extrude=0.12)
        place_row([(t, None, 0)], (cx, -2.3, cz), up)

    callout("Callout_GABA", "GABA", -10.3, 18.2, 5.2, M["red_rim"])
    callout("Callout_Diazepam", "Diazepam", 11.3, 18.1, 6.5, M["blue_rim"])

    def pointer(name, start, ball, r, mat):
        tgt = ball.location / S
        d = (tgt - Vector(start)).normalized()
        tube_arrow(name, start, tgt - d * (r * 0.4), C_lab, mat, r=0.25,
                   head_r=0.55, head_l=1.0)
        s0 = Vector(start)
        rod(name + "_Strut", (s0.x, -1.25, s0.z), (tgt.x, -1.25, tgt.z), C_lab, mat, r=0.3)

    pointer("Arrow_GABA", (-8.4, -2.0, 17.5), gaba, 0.82, M["red_rim"])
    pointer("Arrow_Diazepam", (8.9, -2.0, 17.4), diaz, 0.8, M["blue_rim"])

    # ------------------------------------------------- PLAQUES (base front)
    FY = -7.0                                    # base front face
    slab("Plaque_Cl", rrect_pts(6.4, 2.1, 0.8, -5.7, 1.8), C_lab, M["white"],
         FY - 0.4, 0.8, 0.15, smooth_curve=False)
    ua = flat_arrow("Plaque_UpArrow", 1.5, C_lab, M["ink"], (0, 0, 0), up,
                    shaft=0.26, head_w=0.85, head_l=0.6, depth=0.16, angle_deg=90)
    tcl = text("Plaque_Cl_Text", "Cl", 1.75, C_lab, M["ink"], extrude=0.12)
    tmn = text("Plaque_Cl_minus", "−", 1.1, C_lab, M["ink"], extrude=0.12)
    place_row([(ua, 0.85, 0.0), (tcl, None, 0.0), (tmn, None, 0.5)],
              (-5.7, FY - 0.42, 1.8), up, gap=0.3)

    slab("Plaque_Inhibition", rrect_pts(8.6, 2.1, 0.8, 5.25, 1.8), C_lab, M["white"],
         FY - 0.4, 0.8, 0.15, smooth_curve=False)
    ti = text("Plaque_Inhibition_Text", "Inhibition", 1.75, C_lab, M["ink"], extrude=0.12)
    place_row([(ti, None, 0.0)], (5.25, FY - 0.42, 1.8), up)

    flat_arrow("Plaque_RightArrow", 2.0, C_lab, M["white"], (-0.8, FY, 1.8), up,
               shaft=0.22, head_w=0.8, head_l=0.6, depth=0.5, angle_deg=0)

    build_studio(C_env)


def build_studio(C_env):
    sc = bpy.context.scene

    me = bpy.data.meshes.new("Table")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * 1.4, v.co.y * 0.6 + 0.2, 0))
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat_wood())
    link(bpy.data.objects.new("Table", me), C_env)

    me = bpy.data.meshes.new("Wall")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * 1.6, 0.40, (v.co.y + 1) * 0.8))
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat_matte("M_wall", COL["wall"], 0.95))
    link(bpy.data.objects.new("Wall", me), C_env)

    def area(name, loc, target, size, power, color=(1, 1, 1)):
        ld = bpy.data.lights.new(name, "AREA")
        ld.shape = "DISK"
        ld.size = size * S
        ld.energy = power
        ld.color = color
        ob = link(bpy.data.objects.new(name, ld), C_env)
        ob.location = V(*loc)
        d = V(*target) - ob.location
        ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
        return ob

    area("Key_Light", (-40, -70, 55), (0, 0, 10), 60, 16, (1.0, 0.98, 0.95))
    area("Fill_Light", (50, -60, 25), (0, 0, 10), 70, 8, (0.95, 0.97, 1.0))
    area("Top_Light", (0, -15, 70), (0, 0, 10), 50, 5)
    area("Rim_Light", (0, 30, 40), (0, 0, 14), 40, 3)

    w = sc.world or bpy.data.worlds.new("World")
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = hex_rgba("#D9D8D4")
    bg.inputs[1].default_value = 0.3

    cd = bpy.data.cameras.new("Camera")
    cd.lens = 62
    cd.sensor_width = 36
    cd.dof.use_dof = True
    cd.dof.aperture_fstop = 16
    cam = link(bpy.data.objects.new("Camera", cd), C_env)
    cam.location = V(0, -66, 24)
    tgt = V(0, -1, 10.9)
    cam.rotation_euler = (tgt - cam.location).to_track_quat("-Z", "Y").to_euler()
    cd.dof.focus_distance = (tgt - cam.location).length
    sc.camera = cam

    sc.render.engine = "CYCLES"
    sc.cycles.samples = 256
    sc.cycles.use_denoising = True
    sc.render.resolution_x = 1920
    sc.render.resolution_y = 1280
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.view_settings.exposure = -0.9


# --------------------------------------------------------------------------
#  3-D PRINT EXPORT  (STL in millimetres: 300 mm wide)
# --------------------------------------------------------------------------
PRINT_COLLECTIONS = ("01_Base", "02_Membrane", "03_Receptor", "04_Labels")


def print_meshes():
    """Yield (object, material_name, triangles_mm) for every printable object."""
    dg = bpy.context.evaluated_depsgraph_get()
    for cname in PRINT_COLLECTIONS:
        for ob in bpy.data.collections[cname].objects:
            if ob.type not in {"MESH", "CURVE", "FONT"}:
                continue
            me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
            bm = bmesh.new()
            bm.from_mesh(me)
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=2e-6)
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            bmesh.ops.triangulate(bm, faces=bm.faces)
            bad = sum(1 for e in bm.edges if not e.is_manifold)
            mw = ob.matrix_world
            tris = [tuple(tuple((mw @ v.co) * 1000.0) for v in f.verts) for f in bm.faces]
            bm.free()
            bpy.data.meshes.remove(me)
            mat = ob.active_material.name if ob.active_material else "M_none"
            yield ob, mat, tris, bad


def write_stl(path, tris):
    import struct
    with open(path, "wb") as fh:
        fh.write(b"GABA-A receptor model, units: mm".ljust(80, b" "))
        fh.write(struct.pack("<I", len(tris)))
        for a, b, c in tris:
            n = (Vector(b) - Vector(a)).cross(Vector(c) - Vector(a))
            n = n.normalized() if n.length > 0 else n
            fh.write(struct.pack("<12fH", *n, *a, *b, *c, 0))


def export_raw(outdir):
    """One STL per object (mm, assembled position) - input for make_print_parts.py"""
    os.makedirs(outdir, exist_ok=True)
    for ob, mat, tris, bad in print_meshes():
        write_stl(os.path.join(outdir, ob.name + ".stl"), tris)


def export_print(outdir):
    """full model as one STL + one STL per colour (for multi-colour / painting)."""
    os.makedirs(os.path.join(outdir, "parts_by_color"), exist_ok=True)
    allt, groups, report = [], {}, []
    for ob, mat, tris, bad in print_meshes():
        allt += tris
        groups.setdefault(mat[2:] if mat.startswith("M_") else mat, []).extend(tris)
        report.append((ob.name, len(tris), bad))
    write_stl(os.path.join(outdir, "GABA_A_receptor_300mm.stl"), allt)
    for k, t in groups.items():
        write_stl(os.path.join(outdir, "parts_by_color", "GABA_A_%s.stl" % k), t)
    return report


# --------------------------------------------------------------------------
if __name__ == "__main__":
    build()
    for f in bpy.data.fonts:                    # pack font -> .blend opens anywhere
        if f.filepath and not f.packed_file:
            try:
                f.pack()
            except Exception:
                pass

    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if "--stl" in argv:
        rep = export_print(os.path.abspath(argv[argv.index("--stl") + 1]))
        for name, n, bad in rep:
            if bad:
                print("NON-MANIFOLD", name, n, bad)
        print("STL triangles:", sum(n for _, n, _ in rep))
    if "--raw" in argv:
        export_raw(os.path.abspath(argv[argv.index("--raw") + 1]))
    if "--save" in argv:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(argv[argv.index("--save") + 1]))
    if "--render" in argv:
        sc = bpy.context.scene
        if "--samples" in argv:
            sc.cycles.samples = int(argv[argv.index("--samples") + 1])
        if "--percent" in argv:
            sc.render.resolution_percentage = int(argv[argv.index("--percent") + 1])
        sc.render.filepath = os.path.abspath(argv[argv.index("--render") + 1])
        bpy.ops.render.render(write_still=True)
