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
    "alpha":     "#8B4FD0",   # purple  α
    "beta":      "#2D6CDB",   # blue    β
    "gamma":     "#F5C518",   # yellow  γ
    "channel":   "#2FA81C",   # green pore
    "ion":       "#7CF02E",   # bright green Cl- ions
    "gaba":      "#E21B26",   # red GABA ligand
    "diazepam":  "#36A9F2",   # light blue diazepam
    "head":      "#F7C81E",   # lipid heads
    "tail":      "#F5F3EE",   # lipid tails
    "navy":      "#1C3A8C",   # base + title panel
    "white":     "#F8F8F6",
    "ink":       "#14213D",   # dark label text
    "red_rim":   "#D8232E",
    "blue_rim":  "#2C7FDA",
    "wall":      "#CFCDC8",
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


def mat_clay(name, hexcol, rough=0.42, sss=0.10, coat=0.30, bump=0.12,
             emit=0.0, noise_scale=420.0):
    """Soft plastic / polymer-clay look with a very fine surface texture."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (600, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (300, 0)
    col = hex_rgba(hexcol)
    set_in(bsdf, "Base Color", col)
    set_in(bsdf, "Roughness", rough)
    set_in(bsdf, ["Subsurface Weight", "Subsurface"], sss)
    set_in(bsdf, "Subsurface Scale", 0.003)
    set_in(bsdf, "Subsurface Radius", Vector((1.0, 0.5, 0.35)))
    set_in(bsdf, ["Coat Weight", "Clearcoat"], coat)
    set_in(bsdf, ["Coat Roughness", "Clearcoat Roughness"], 0.25)
    if emit > 0:
        set_in(bsdf, ["Emission Color", "Emission"], col)
        set_in(bsdf, "Emission Strength", emit)
    nt.links.new(bsdf.outputs[0], out.inputs["Surface"])

    if bump > 0:
        tc = nt.nodes.new("ShaderNodeTexCoord")
        tc.location = (-600, 0)
        nz = nt.nodes.new("ShaderNodeTexNoise")
        nz.location = (-400, 0)
        nz.inputs["Scale"].default_value = noise_scale
        nz.inputs["Detail"].default_value = 6.0
        bp = nt.nodes.new("ShaderNodeBump")
        bp.location = (-150, 0)
        bp.inputs["Strength"].default_value = bump
        bp.inputs["Distance"].default_value = 0.0004
        nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
        nt.links.new(nz.outputs["Fac"], bp.inputs["Height"])
        nt.links.new(bp.outputs["Normal"], bsdf.inputs["Normal"])
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
    ramp.color_ramp.elements[0].color = hex_rgba("#A47E57")
    ramp.color_ramp.elements[1].color = hex_rgba("#C9A57C")
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


def blob(name, elements, collection, mat, res=0.11, threshold=0.6):
    """Organic clay shape from metaball elements, converted to a real mesh.

    elements: list of (centre_xyz_cm, semi_axes_xyz_cm)  -> ellipsoids
    (a single isolated ellipsoid reaches ~0.575 * radius * size on each axis;
     neighbours blend together and grow slightly)
    """
    mb = bpy.data.metaballs.new(name + "_mb")
    mb.resolution = res * S
    mb.render_resolution = res * S
    mb.threshold = threshold
    for co, semi in elements:
        R = max(semi) / 0.575
        el = mb.elements.new(type="ELLIPSOID")
        el.co = V(*co)
        el.radius = R * S
        el.size_x, el.size_y, el.size_z = (a / (0.575 * R) for a in semi)
        el.stiffness = 2.0
    tmp = link(bpy.data.objects.new("MB" + name.replace("_", "").replace(".", ""), mb),
               collection)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(tmp.evaluated_get(dg))
    me.name = name
    bpy.data.objects.remove(tmp, do_unlink=True)
    bpy.data.metaballs.remove(mb)
    smooth(me)
    me.materials.append(mat)
    ob = link(bpy.data.objects.new(name, me), collection)
    # tiny relax for an even "hand-modelled" surface
    cs = ob.modifiers.new("Relax", "CORRECTIVE_SMOOTH")
    cs.iterations = 4
    cs.use_only_smooth = True
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


# --------------------------------------------------------------------------
#  Text helpers
# --------------------------------------------------------------------------
FONT = None


def load_font():
    cands = [
        r"C:\Windows\Fonts\arialbd.ttf",
        r"C:\Windows\Fonts\segoeuib.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
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


def surface_y(ob, x, z, y_from=-40.0):
    """Ray-cast from the front (-Y) to find the visible surface depth (cm)."""
    bpy.context.view_layer.update()
    inv = ob.matrix_world.inverted()
    o = inv @ V(x, y_from, z)
    d = (inv.to_3x3() @ Vector((0, 1, 0))).normalized()
    hit, loc, nor, idx = ob.ray_cast(o, d)
    if not hit:
        return None
    return (ob.matrix_world @ loc).y / S


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
         if k not in ("wall", "ion", "channel")}
    M["navy"] = mat_clay("M_navy", COL["navy"], rough=0.35, coat=0.45, bump=0.05)
    M["white"] = mat_clay("M_white", COL["white"], rough=0.35, coat=0.4, bump=0.04)
    M["channel"] = mat_clay("M_channel", COL["channel"], rough=0.35, emit=0.25)
    M["ion"] = mat_clay("M_ion", COL["ion"], rough=0.25, coat=0.6, emit=0.9, bump=0.03)
    M["gaba"] = mat_clay("M_gaba", COL["gaba"], rough=0.25, coat=0.7, bump=0.03)
    M["diazepam"] = mat_clay("M_diazepam", COL["diazepam"], rough=0.25, coat=0.7, bump=0.03)

    # ------------------------------------------------------------------ BASE
    # stepped pedestal, 30 cm wide, sloped front face carrying the plaques
    prof = [(-8.0, 0.0), (-8.0, 1.0), (-6.4, 3.5), (4.5, 3.5), (4.5, 0.0)]
    me = bpy.data.meshes.new("Base_Pedestal")
    bm = bmesh.new()
    left = [bm.verts.new(V(-15.0, y, z)) for y, z in prof]
    f = bm.faces.new(left)
    res = bmesh.ops.extrude_face_region(bm, geom=[f])
    nv = [g for g in res["geom"] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=nv, vec=V(30.0, 0, 0))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    smooth(me)
    me.materials.append(M["navy"])
    base = link(bpy.data.objects.new("Base_Pedestal", me), C_base)
    bv = base.modifiers.new("Bevel", "BEVEL")
    bv.width = 0.35 * S
    bv.segments = 6
    bv.limit_method = "ANGLE"
    flat_normals_fix(base)

    rbox("Base_MembranePlatform", (25.0, 5.0, 3.0), (0, 1.0, 5.0), C_base, M["navy"],
         bevel=0.3)

    # ------------------------------------------------------------- MEMBRANE
    head_r = 0.55
    xs = []
    x = 6.4
    while x <= 13.3:
        xs.append(x)
        x += 1.1
    rows_y = [-1.0, 0.1, 1.2, 2.3]
    z_top, z_bot = 14.0, 7.0

    hm = bpy.data.meshes.new("Lipid_Heads")
    bm = bmesh.new()
    tails = bpy.data.curves.new("Lipid_Tails", "CURVE")
    tails.dimensions = "3D"
    tails.bevel_depth = 0.11 * S
    tails.bevel_resolution = 3
    tails.use_fill_caps = True
    k = 0
    for side in (-1, 1):
        for ri, y in enumerate(rows_y):
            stagger = 0.55 if ri % 2 else 0.0
            for xi in xs:
                xx = side * (xi + stagger)
                if abs(xx) > 13.4:
                    continue
                for zc, sgn in ((z_top, -1), (z_bot, 1)):
                    bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=12,
                                              radius=head_r * S,
                                              matrix=Matrix.Translation(V(xx, y, zc)))
                    for t in (-0.17, 0.17):
                        sp = tails.splines.new("NURBS")
                        n = 6
                        sp.points.add(n - 1)
                        for i in range(n):
                            f_ = i / (n - 1)
                            wig = 0.10 * (1 if (i + k) % 2 else -1) if 0 < i < n - 1 else 0
                            pz = zc + sgn * (head_r * 0.6 + f_ * 2.8)
                            sp.points[i].co = (*(V(xx + t + wig, y, pz)), 1.0)
                        sp.order_u = 3
                        sp.use_endpoint_u = True
                    k += 1
    bm.to_mesh(hm)
    bm.free()
    smooth(hm)
    hm.materials.append(M["head"])
    link(bpy.data.objects.new("Lipid_Heads", hm), C_mem)
    tails.materials.append(M["tail"])
    link(bpy.data.objects.new("Lipid_Tails", tails), C_mem)

    # ------------------------------------------------------------- RECEPTOR
    # α subunits (left / right) - kidney-shaped clay blobs
    alphas = []
    for side, nm in ((-1, "L"), (1, "R")):
        o = side          # outward direction
        cx = 4.7 * side
        el = [
            ((cx + o * 0.20, -0.4, 14.2), (3.1, 2.2, 2.0)),    # top lobe
            ((cx + o * 0.40, -0.4, 11.4), (2.7, 2.2, 2.2)),    # upper body
            ((cx - o * 0.30, -0.4, 8.5), (2.2, 2.1, 2.2)),     # waist
            ((cx - o * 0.70, -0.4, 5.8), (1.8, 2.0, 1.7)),     # foot
            ((cx + o * 1.00, 1.3, 10.6), (2.2, 1.6, 4.4)),     # back layer
        ]
        alphas.append(blob("Alpha_" + nm, el, C_rec, M["alpha"]))

    # β subunits (behind the α tops)
    for side, nm in ((-1, "L"), (1, "R")):
        cx = 3.6 * side
        el = [
            ((cx, 0.6, 16.6), (2.4, 2.0, 2.1)),
            ((cx + side * 0.7, 0.6, 15.4), (1.7, 1.8, 1.5)),
        ]
        blob("Beta_" + nm, el, C_rec, M["beta"])

    # γ subunit (top centre)
    gamma = blob("Gamma", [
        ((0, -0.2, 17.9), (2.0, 1.9, 1.6)),
        ((0, -0.2, 15.9), (1.75, 1.8, 2.0)),
    ], C_rec, M["gamma"])

    # Cl- channel (pore) between the two α
    rbox("Channel_Pore", (3.0, 2.6, 10.0), (0, 0.4, 8.9), C_rec, M["channel"],
         bevel=0.8, seg=8)
    sphere("Cl_Ion_1", 0.6, (0, -1.0, 12.0), C_rec, M["ion"])
    sphere("Cl_Ion_2", 0.6, (0, -1.0, 9.7), C_rec, M["ion"])
    flat_arrow("Channel_Arrow", 1.9, C_rec, M["ion"], (0, -0.95, 7.55),
               Matrix.Identity(3), shaft=0.28, head_w=0.85, head_l=0.7, depth=0.2,
               angle_deg=-90)
    cl_ball = sphere("Cl_Ion_Exit", 1.15, (0, -2.4, 4.75), C_rec, M["ion"])

    # ligands sitting on the surface
    gaba_x, gaba_z = -5.7, 15.7
    dz_x, dz_z = 5.7, 15.1
    gy = surface_y(alphas[0], gaba_x, gaba_z) or -2.5
    dy = surface_y(alphas[1], dz_x, dz_z) or -2.5
    gaba = sphere("GABA_Ligand", 0.85, (gaba_x, gy + 0.25, gaba_z), C_rec, M["gaba"])
    diaz = sphere("Diazepam_Ligand", 0.80, (dz_x, dy + 0.25, dz_z), C_rec, M["diazepam"])

    # ---------------------------------------------------------- GREEK LETTERS
    Mw = M["white"]
    Mink = mat_clay("M_ink", COL["ink"], rough=0.4, bump=0.02)
    up = Matrix.Identity(3)
    for ob, xx, zz, ch, mat, sz in (
        (alphas[0], -5.6, 11.3, "α", Mw, 2.4),
        (alphas[1], 5.6, 11.3, "α", Mw, 2.4),
        (bpy.data.objects["Beta_L"], -3.7, 17.0, "β", Mw, 2.0),
        (bpy.data.objects["Beta_R"], 3.7, 17.0, "β", Mw, 2.0),
        (gamma, 0.0, 17.9, "γ", Mink, 2.0),
    ):
        sy = surface_y(ob, xx, zz) or -2.5
        t = text("Letter_" + ch + "_" + ob.name, ch, sz, C_lab, mat, extrude=0.12)
        place_row([(t, None, 0)], (xx, sy - 0.02, zz), up)

    # ------------------------------------------------------------------ TITLE
    rbox("Title_Stand", (1.2, 0.8, 7.0), (0, 1.8, 17.8), C_lab, M["white"], bevel=0.3)
    rbox("Title_Panel_Rim", (21.4, 0.8, 2.9), (0, 1.2, 21.9), C_lab, M["navy"], bevel=0.6)
    rbox("Title_Panel", (21.0, 0.8, 2.5), (0, 1.05, 21.9), C_lab,
         mat_clay("M_navy_panel", "#1E3F93", rough=0.3, coat=0.5, bump=0.03), bevel=0.5)
    t1 = text("Title_GABA", "GABA", 1.95, C_lab, Mw, extrude=0.1)
    t2 = text("Title_sub_A", "A", 1.2, C_lab, Mw, extrude=0.1)
    t3 = text("Title_Receptor", "Receptor", 1.95, C_lab, Mw, extrude=0.1)
    w2 = text_width_cm(t2)
    place_row([(t1, None, 0.0), (t2, w2 + 0.3, -0.5), (t3, None, 0.0)],
              (0, 0.55, 21.9), up, gap=0.12)

    # ------------------------------------------------------------- CALLOUTS
    def callout(name, label, center, w, rim_mat):
        cx, cy, cz = center
        rbox(name + "_Rim", (w, 0.5, 2.0), (cx, cy, cz), C_lab, rim_mat, bevel=0.45)
        rbox(name + "_Face", (w - 0.42, 0.5, 1.58), (cx, cy - 0.07, cz), C_lab,
             M["white"], bevel=0.3)
        t = text(name + "_Text", label, 1.2, C_lab, Mink, extrude=0.06)
        place_row([(t, None, 0)], (cx, cy - 0.35, cz), up)

    rim_red = mat_clay("M_rim_red", COL["red_rim"], rough=0.3, coat=0.5, bump=0.03)
    rim_blue = mat_clay("M_rim_blue", COL["blue_rim"], rough=0.3, coat=0.5, bump=0.03)
    callout("Callout_GABA", "GABA", (-12.4, -1.6, 18.4), 5.2, rim_red)
    callout("Callout_Diazepam", "Diazepam", (11.4, -1.6, 18.7), 6.6, rim_blue)

    def pointer(name, start, target_ob, r, mat):
        tgt = target_ob.location / S
        d = (tgt - Vector(start)).normalized()
        tube_arrow(name, start, tgt - d * (r + 0.05), C_lab, mat)

    pointer("Arrow_GABA", (-10.6, -1.7, 17.5), gaba, 0.85, rim_red)
    pointer("Arrow_Diazepam", (9.6, -1.7, 17.8), diaz, 0.80, rim_blue)

    # ------------------------------------------------- BOTTOM PLAQUES (slope)
    p0, p1 = Vector((-8.0, 1.0)), Vector((-6.4, 3.5))          # slope (y,z)
    mid = (p0 + p1) / 2
    tilt = math.atan2(p1.x - p0.x, p1.y - p0.y)                # from vertical
    frame = Matrix.Rotation(-tilt, 3, "X")
    nrm = frame @ Vector((0, -1, 0))
    upv = frame @ Vector((0, 0, 1))
    slope_c = Vector((0, mid.x, mid.y))

    def plaque(name, cx, w):
        c = slope_c + Vector((cx, 0, 0)) + nrm * 0.18
        rbox(name, (w, 0.36, 1.95), tuple(c), C_lab, M["white"], bevel=0.3,
             rot=frame.to_euler())
        return c

    # "↑ Cl-"   plaque
    c = plaque("Plaque_Cl", -5.6, 6.2)
    up_arrow = flat_arrow("Plaque_UpArrow", 1.3, C_lab, Mink, (0, 0, 0), frame,
                          shaft=0.22, head_w=0.75, head_l=0.55, depth=0.08,
                          angle_deg=90)
    tcl = text("Plaque_Cl_Text", "Cl", 1.35, C_lab, Mink, extrude=0.05)
    tmn = text("Plaque_Cl_minus", "\u2212", 0.85, C_lab, Mink, extrude=0.05)
    place_row([(up_arrow, 0.75, 0.0), (tcl, None, 0.0), (tmn, None, 0.42)],
              tuple(c + nrm * 0.2), frame, gap=0.35)

    # "→"  between plaques (white, embossed on the base)
    ar = flat_arrow("Plaque_RightArrow", 2.1, C_lab, M["white"], (0, 0, 0), frame,
                    shaft=0.3, head_w=0.95, head_l=0.75, depth=0.12, angle_deg=0)
    ar.matrix_world = Matrix.Translation((slope_c + Vector((-1.2, 0, 0)) + nrm * 0.06) * S) \
        @ frame.to_4x4()

    # "Inhibition"   plaque
    c = plaque("Plaque_Inhibition", 5.0, 8.6)
    ti = text("Plaque_Inhibition_Text", "Inhibition", 1.35, C_lab, Mink, extrude=0.05)
    place_row([(ti, None, 0.0)], tuple(c + nrm * 0.2), frame)

    # Cl- on the big exit ion
    tcx = text("Ion_Cl_Text", "Cl", 0.95, C_lab, Mw, extrude=0.05)
    tcm = text("Ion_Cl_minus", "\u2212", 0.65, C_lab, Mw, extrude=0.05)
    cy = surface_y(cl_ball, 0, 4.75) or -2.85
    place_row([(tcx, None, 0), (tmn2 := tcm, None, 0.3)], (0.0, cy - 0.04, 4.72), up,
              gap=0.03)

    # ---------------------------------------------------------------- STUDIO
    build_studio(C_env)


def build_studio(C_env):
    sc = bpy.context.scene

    # table + wall
    me = bpy.data.meshes.new("Table")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * 1.2, v.co.y * 0.6 + 0.2, 0))
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat_wood())
    link(bpy.data.objects.new("Table", me), C_env)

    me = bpy.data.meshes.new("Wall")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * 1.5, 0.45, (v.co.y + 1) * 0.8))
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat_matte("M_wall", COL["wall"], 0.95))
    link(bpy.data.objects.new("Wall", me), C_env)

    # lights
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

    area("Key_Light", (-45, -55, 60), (0, 0, 10), 45, 14, (1.0, 0.97, 0.93))
    area("Fill_Light", (55, -45, 30), (0, 0, 10), 60, 6, (0.93, 0.96, 1.0))
    area("Top_Light", (0, -10, 75), (0, 0, 10), 50, 7)
    area("Rim_Light", (0, 35, 45), (0, 0, 14), 40, 5)

    w = sc.world or bpy.data.worlds.new("World")
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = hex_rgba("#D9D8D4")
    bg.inputs[1].default_value = 0.25

    # camera
    cd = bpy.data.cameras.new("Camera")
    cd.lens = 70
    cd.sensor_width = 36
    cd.dof.use_dof = True
    cd.dof.aperture_fstop = 11
    cam = link(bpy.data.objects.new("Camera", cd), C_env)
    cam.location = V(0, -80, 24)
    tgt = V(0, -1, 11.0)
    cam.rotation_euler = (tgt - cam.location).to_track_quat("-Z", "Y").to_euler()
    cd.dof.focus_distance = (tgt - cam.location).length
    sc.camera = cam

    # render settings
    sc.render.engine = "CYCLES"
    sc.cycles.samples = 256
    sc.cycles.use_denoising = True
    sc.render.resolution_x = 1920
    sc.render.resolution_y = 1280
    sc.render.film_transparent = False
    # "Standard" keeps the saturated toy/clay colours of the reference
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.view_settings.exposure = -0.35


# --------------------------------------------------------------------------
if __name__ == "__main__":
    build()
    # pack the font so the .blend opens anywhere
    for f in bpy.data.fonts:
        if f.filepath and not f.packed_file:
            try:
                f.pack()
            except Exception:
                pass

    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
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
