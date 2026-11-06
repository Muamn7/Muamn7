"""
MIMO Technology — 3D diorama (procedural Blender model)
=======================================================

Builds the complete diorama: stepped base with a metal name-plate, glossy
black backboard with the title, a detailed lattice cell tower with antenna
panels / brackets / cables, two buildings with recessed windows, a road with
lane markings, an angled info sign, a 5G smartphone on a pedestal and the
glowing MIMO beams — plus studio backdrop, lights and camera.

Real-world scale: the whole model is exactly 60 cm tall (base bottom to top
of the backboard). Scene units are set to centimetres.

How to use (Blender 4.2 or newer, 5.x tested):
  * Inside Blender: Scripting tab -> Open -> mimo_diorama.py -> Run Script.
  * Command line:
      blender -b -P mimo_diorama.py -- --save mimo.blend --render mimo.png

Optional arguments after "--":
  --save PATH       save the .blend file
  --render PATH     render a still with Cycles
  --samples N       Cycles samples (default 256)
  --percent P       resolution percentage (default 100 of 1920x1280)
"""

import bpy
import bmesh
import math
import os
import sys
from mathutils import Vector, Matrix, Euler

# ---------------------------------------------------------------------------
# Settings you may want to change
# ---------------------------------------------------------------------------
TOTAL_HEIGHT = 0.60                      # metres -> 60 cm
TITLE = "MIMO Technology"
SIGN_HEADER = "MIMO"
SIGN_LINES = ["1. Higher data rates",
              "2. Better reliability",
              "3. Spectral efficiency"]
SHOW_BEAMS = False                       # True = add the coloured MIMO beams back
SILL_D = 0.003                           # how far sills stick out (3 mm)
BEAM_STRENGTH = 2.6                      # emission strength of the beams

# Key heights (metres)
BASE_H = 0.055                           # black plinth
INLAY_H = 0.006                          # grey top surface
G = BASE_H + INLAY_H                     # ground level of the diorama = 6.1 cm
BOARD_H = TOTAL_HEIGHT - G               # backboard reaches exactly 60 cm

DEG = math.pi / 180.0


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------
def clear_scene():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)
    for blocks in (bpy.data.meshes, bpy.data.curves, bpy.data.materials,
                   bpy.data.lights, bpy.data.cameras, bpy.data.images):
        for b in list(blocks):
            if b.users == 0:
                blocks.remove(b)


def new_collection(name, parent=None):
    c = bpy.data.collections.new(name)
    (parent or bpy.context.scene.collection).children.link(c)
    return c


def set_input(node, names, value):
    for n in names if isinstance(names, (list, tuple)) else [names]:
        if n in node.inputs:
            node.inputs[n].default_value = value
            return True
    return False


def _new_material(name):
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    return m


def _principled_node(m):
    nt = m.node_tree
    for n in nt.nodes:
        if n.type == 'BSDF_PRINCIPLED':
            return n
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    out = next(n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL')
    nt.links.new(b.outputs[0], out.inputs[0])
    return b


def _output_node(m):
    nt = m.node_tree
    for n in nt.nodes:
        if n.type == 'OUTPUT_MATERIAL':
            return n
    return nt.nodes.new("ShaderNodeOutputMaterial")


def _blended(m):
    if hasattr(m, "surface_render_method"):
        m.surface_render_method = 'BLENDED'
    elif hasattr(m, "blend_method"):
        m.blend_method = 'BLEND'


def principled(name, color, rough=0.5, metal=0.0, coat=0.0, aniso=0.0,
               spec=0.5, emission=None, strength=0.0):
    m = _new_material(name)
    b = _principled_node(m)
    set_input(b, "Base Color", (*color, 1.0))
    set_input(b, "Roughness", rough)
    set_input(b, "Metallic", metal)
    set_input(b, ["Coat Weight", "Clearcoat"], coat)
    set_input(b, ["Coat Roughness", "Clearcoat Roughness"], 0.05)
    set_input(b, ["Specular IOR Level", "Specular"], spec)
    set_input(b, "Anisotropic", aniso)
    if emission is not None:
        set_input(b, ["Emission Color", "Emission"], (*emission, 1.0))
        set_input(b, "Emission Strength", strength)
    m.diffuse_color = (*color, 1.0)
    return m


def link_obj(ob, coll):
    coll.objects.link(ob)
    return ob


def auto_smooth_bm(bm, angle=35.0):
    """Smooth faces, mark edges sharper than `angle` as sharp (4.1+ normals)."""
    lim = angle * DEG
    for f in bm.faces:
        f.smooth = True
    for e in bm.edges:
        if len(e.link_faces) == 2:
            if e.calc_face_angle(0.0) > lim:
                e.smooth = False
        else:
            e.smooth = False


def obj_from_bm(name, bm, coll, mat=None, smooth=35.0, extra_mats=()):
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-7)
    if smooth:
        auto_smooth_bm(bm, smooth)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    if mat:
        me.materials.append(mat)
    for em in extra_mats:
        me.materials.append(em)
    return link_obj(ob, coll)


def add_bevel(ob, width, segments=3, angle=40.0):
    m = ob.modifiers.new("Bevel", 'BEVEL')
    m.width = width
    m.segments = segments
    m.limit_method = 'ANGLE'
    m.angle_limit = angle * DEG
    try:
        m.harden_normals = True
    except Exception:
        pass
    return m


def print_bevel(ob, width, segments=2, angle=40.0, skip_bottom=True, skip_top=False):
    """Bevel only sharp edges, but never the bottom (and optionally top) edges.
    A rounded bottom edge where a part sits on another part leaves a thin
    overhang that slicers put supports under."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    lay = bm.edges.layers.float.get("bevel_weight_edge") or \
        bm.edges.layers.float.new("bevel_weight_edge")
    zs = [v.co.z for v in bm.verts]
    z0, z1 = min(zs), max(zs)
    lim = angle * DEG
    for e in bm.edges:
        a, b = e.verts
        w = 1.0 if (len(e.link_faces) == 2 and e.calc_face_angle(0.0) > lim) else 0.0
        if skip_bottom and abs(a.co.z - z0) < 1e-6 and abs(b.co.z - z0) < 1e-6:
            w = 0.0
        if skip_top and abs(a.co.z - z1) < 1e-6 and abs(b.co.z - z1) < 1e-6:
            w = 0.0
        e[lay] = w
    bm.to_mesh(ob.data)
    bm.free()
    m = add_bevel(ob, width, segments, angle)
    m.limit_method = 'WEIGHT'
    return m


def bm_box(bm, center, size, rot=None):
    mat = Matrix.Translation(Vector(center))
    if rot is not None:
        mat = mat @ rot.to_matrix().to_4x4()
    mat = mat @ Matrix.Diagonal((size[0], size[1], size[2], 1.0))
    bmesh.ops.create_cube(bm, size=1.0, matrix=mat)


def bm_prism(bm, base, n, along, length, prof):
    """Extrude a 2D profile along `along`. Profile points are (u, z):
    u = distance along the wall normal `n` from `base`, z = absolute height."""
    base = Vector((base.x, base.y, 0.0))
    loops = []
    for s in (-0.5, 0.5):
        o = base + along * (s * length)
        loops.append([bm.verts.new(o + n * u + Vector((0, 0, z))) for u, z in prof])
    a, b = loops
    k = len(prof)
    bm.faces.new(a)
    bm.faces.new(list(reversed(b)))
    for i in range(k):
        j = (i + 1) % k
        bm.faces.new((a[j], a[i], b[i], b[j]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)


def bm_cyl(bm, p1, p2, r, seg=8, r2=None):
    p1, p2 = Vector(p1), Vector(p2)
    d = p2 - p1
    L = d.length
    if L < 1e-7:
        return
    rot = d.to_track_quat('Z', 'Y').to_matrix().to_4x4()
    mat = Matrix.Translation((p1 + p2) * 0.5) @ rot
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg,
                          radius1=r, radius2=r if r2 is None else r2,
                          depth=L, matrix=mat)


def bm_lathe(bm, center, prof, seg=16):
    """Closed solid of revolution around Z. prof = [(radius, dz), ...] bottom->top."""
    c = Vector(center)
    rings = []
    for r, dz in prof:
        rings.append([bm.verts.new(c + Vector((r * math.cos(2 * math.pi * i / seg),
                                               r * math.sin(2 * math.pi * i / seg), dz)))
                      for i in range(seg)])
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])
    for a, b in zip(rings, rings[1:]):
        for i in range(seg):
            j = (i + 1) % seg
            bm.faces.new((a[i], a[j], b[j], b[i]))


def bm_sphere(bm, center, r, seg=12):
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=seg // 2,
                              radius=r, matrix=Matrix.Translation(Vector(center)))


def box(name, size, loc, coll, mat, bevel=0.0, seg=3, rot=(0, 0, 0)):
    bm = bmesh.new()
    bm_box(bm, (0, 0, 0), size)
    ob = obj_from_bm(name, bm, coll, mat)
    ob.location = loc
    ob.rotation_euler = rot
    if bevel > 0:
        add_bevel(ob, bevel, seg)
    return ob


def rr_points(w, h, r, seg=8, cx=0.0, cy=0.0):
    """Rounded rectangle outline (CCW). r may be a number or 4 radii
    [top-right, top-left, bottom-left, bottom-right]."""
    rs = r if isinstance(r, (list, tuple)) else [r] * 4
    corners = [(w / 2, h / 2, 0), (-w / 2, h / 2, 90),
               (-w / 2, -h / 2, 180), (w / 2, -h / 2, 270)]
    pts = []
    for (x, y, a0), rr in zip(corners, rs):
        if rr <= 1e-6:
            pts.append((cx + x, cy + y))
            continue
        ccx = x - math.copysign(rr, x)
        ccy = y - math.copysign(rr, y)
        for i in range(seg + 1):
            a = (a0 + 90.0 * i / seg) * DEG
            pts.append((cx + ccx + rr * math.cos(a), cy + ccy + rr * math.sin(a)))
    return pts


def bm_slab(bm, pts, z0, z1):
    """Extrude a CCW 2D outline (local XY) between z0 and z1."""
    n = len(pts)
    vb = [bm.verts.new((x, y, z0)) for x, y in pts]
    vt = [bm.verts.new((x, y, z1)) for x, y in pts]
    bm.faces.new(list(reversed(vb)))
    bm.faces.new(vt)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((vb[i], vb[j], vt[j], vt[i]))


def bm_ring(bm, outer, inner, z0, z1):
    """Extruded ring between two CCW outlines with equal point counts."""
    n = len(outer)
    ob_ = [bm.verts.new((x, y, z0)) for x, y in outer]
    ot = [bm.verts.new((x, y, z1)) for x, y in outer]
    ib = [bm.verts.new((x, y, z0)) for x, y in inner]
    it = [bm.verts.new((x, y, z1)) for x, y in inner]
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((ob_[i], ob_[j], ot[j], ot[i]))       # outer wall
        bm.faces.new((it[i], it[j], ib[j], ib[i]))         # inner wall
        bm.faces.new((ot[i], ot[j], it[j], it[i]))         # top
        bm.faces.new((ib[i], ib[j], ob_[j], ob_[i]))       # bottom


def slab(name, pts, z0, z1, coll, mat, bevel=0.0, seg=3, parent=None):
    bm = bmesh.new()
    bm_slab(bm, pts, z0, z1)
    ob = obj_from_bm(name, bm, coll, mat)
    if bevel > 0:
        add_bevel(ob, bevel, seg)
    if parent:
        ob.parent = parent
    return ob


def empty(name, loc, rot, coll):
    e = bpy.data.objects.new(name, None)
    e.empty_display_size = 0.05
    e.location = loc
    e.rotation_euler = rot
    return link_obj(e, coll)


def find_font(bold=True):
    cands = []
    if bold:
        cands += [r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\segoeuib.ttf",
                  "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                  "/Library/Fonts/Arial Bold.ttf",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                  "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
                  "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]
    else:
        cands += [r"C:\Windows\Fonts\arial.ttf",
                  "/System/Library/Fonts/Supplemental/Arial.ttf",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                  "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"]
    for p in cands:
        if os.path.exists(p):
            try:
                f = bpy.data.fonts.load(p, check_existing=True)
                # Pack the font into the .blend so the text does not turn
                # into squares when the file is opened on another computer.
                if f.packed_file is None:
                    f.pack()
                return f
            except Exception:
                pass
    return None


FONT_BOLD = None


def text(name, body, size, loc, coll, mat, parent=None, rot=(0, 0, 0),
         extrude=0.0008, align_x='CENTER', align_y='CENTER', font=None,
         spacing=1.0, bevel=0.00025):
    cu = bpy.data.curves.new(name, 'FONT')
    cu.body = body
    cu.size = size
    cu.extrude = extrude
    cu.bevel_depth = bevel
    cu.bevel_resolution = 2
    cu.align_x = align_x
    cu.align_y = align_y
    cu.space_character = spacing
    f = font or FONT_BOLD
    if f:
        cu.font = f
    ob = bpy.data.objects.new(name, cu)
    ob.data.materials.append(mat)
    link_obj(ob, coll)
    if parent:
        ob.parent = parent
    ob.location = loc
    ob.rotation_euler = rot
    return ob


def bake_modifiers(ob):
    """Apply all modifiers of `ob` without operators (works headless)."""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev)
    old = ob.data
    ob.modifiers.clear()
    ob.data = me
    if old.users == 0:
        bpy.data.meshes.remove(old)


def boolean_cut(target, cutter_bm, name="Cutter"):
    me = bpy.data.meshes.new(name)
    cutter_bm.to_mesh(me)
    cutter_bm.free()
    cutter = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(cutter)
    cutter.location = target.location.copy()
    cutter.rotation_euler = target.rotation_euler.copy()
    bpy.context.view_layer.update()
    mod = target.modifiers.new("Bool", 'BOOLEAN')
    mod.operation = 'DIFFERENCE'
    mod.solver = 'EXACT'
    mod.object = cutter
    bake_modifiers(target)
    bm = bmesh.new()
    bm.from_mesh(target.data)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=1e-6)
    auto_smooth_bm(bm, 35.0)
    bm.to_mesh(target.data)
    bm.free()
    bpy.data.objects.remove(cutter, do_unlink=True)
    bpy.data.meshes.remove(me)


def self_union(ob):
    """Fuse all overlapping pieces of `ob` into one clean solid (Boolean
    union with itself), then re-apply smooth shading."""
    me = bpy.data.meshes.new("union_dummy")
    dummy = bpy.data.objects.new("union_dummy", me)
    bpy.context.scene.collection.objects.link(dummy)
    mod = ob.modifiers.new("SelfUnion", 'BOOLEAN')
    mod.operation = 'UNION'
    mod.object = dummy
    solvers = mod.bl_rna.properties['solver'].enum_items.keys()
    mod.solver = 'EXACT'
    mod.use_self = True
    mod.use_hole_tolerant = False
    try:
        bake_modifiers(ob)
    finally:
        bpy.data.objects.remove(dummy, do_unlink=True)
        bpy.data.meshes.remove(me)
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=1e-7)
    loose = [e for e in bm.edges if not e.link_faces]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context='EDGES')
    loose_v = [v for v in bm.verts if not v.link_edges]
    if loose_v:
        bmesh.ops.delete(bm, geom=loose_v, context='VERTS')
    auto_smooth_bm(bm, 40.0)
    bm.to_mesh(ob.data)
    bm.free()


def look_at(ob, target):
    d = Vector(target) - ob.location
    ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()


# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------
def make_materials():
    M = {}
    M["base"] = principled("Base_BlackSatin", (0.012, 0.012, 0.013), rough=0.32, coat=0.4)
    M["ground"] = principled("Ground_Grey", (0.075, 0.077, 0.08), rough=0.75)
    M["board"] = principled("Board_GlossBlack", (0.008, 0.008, 0.009), rough=0.18, coat=0.8)
    M["white"] = principled("Text_White", (0.9, 0.9, 0.92), rough=0.45, spec=0.3)
    M["black"] = principled("Text_Black", (0.01, 0.01, 0.01), rough=0.4)
    M["steel"] = principled("Tower_Galvanized", (0.55, 0.57, 0.6), rough=0.33, metal=0.9)
    M["steel_dark"] = principled("Steel_Dark", (0.25, 0.26, 0.28), rough=0.4, metal=0.85)
    M["radome"] = principled("Antenna_WhitePlastic", (0.7, 0.71, 0.72), rough=0.38, coat=0.2)
    M["cap"] = principled("Antenna_Cap", (0.55, 0.56, 0.58), rough=0.45)
    M["cable"] = principled("Cable_Black", (0.015, 0.015, 0.015), rough=0.55)
    M["concrete"] = principled("Concrete", (0.42, 0.42, 0.41), rough=0.85)
    M["building"] = principled("Building_White", (0.62, 0.63, 0.64), rough=0.55)
    M["building_trim"] = principled("Building_Trim", (0.48, 0.49, 0.5), rough=0.5)
    M["glass"] = principled("Window_NavyGlass", (0.008, 0.025, 0.09), rough=0.06, coat=1.0)
    M["asphalt"] = principled("Asphalt", (0.035, 0.036, 0.04), rough=0.85)
    M["curb"] = principled("Curb", (0.3, 0.3, 0.31), rough=0.7)
    M["paint"] = principled("Road_Paint", (0.85, 0.85, 0.85), rough=0.5)
    M["pedestal"] = principled("Pedestal_Grey", (0.45, 0.46, 0.48), rough=0.45)
    M["pedestal_top"] = principled("Pedestal_Top", (0.6, 0.61, 0.63), rough=0.4)
    M["frame"] = principled("Phone_SilverFrame", (0.8, 0.81, 0.83), rough=0.18, metal=1.0)
    M["phone_glass"] = principled("Phone_BlackGlass", (0.004, 0.004, 0.006), rough=0.04, coat=1.0)
    M["led_red"] = principled("Aviation_Light", (1.0, 0.05, 0.02), rough=0.3,
                              emission=(1.0, 0.05, 0.02), strength=8.0)
    M["sign"] = principled("Sign_GlossBlack", (0.006, 0.006, 0.007), rough=0.22, coat=0.25, spec=0.3)
    M["sign_border"] = principled("Sign_Border", (0.9, 0.9, 0.92), rough=0.25, metal=0.6)
    M["silver"] = principled("Silver_Satin", (0.7, 0.71, 0.73), rough=0.3, metal=1.0)

    # Brushed aluminium (name plate)
    m = principled("Brushed_Aluminium", (0.78, 0.79, 0.81), rough=0.28, metal=1.0, aniso=0.7)
    nt = m.node_tree
    b = _principled_node(m)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1.0, 300.0, 300.0)
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 8.0
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.12
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], nz.inputs["Vector"])
    nt.links.new(nz.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    M["alu"] = m

    # Phone screen: glossy glass + glowing blue radial gradient
    m = _new_material("Phone_Screen")
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1.7, 1.25, 1.0)
    mp.inputs["Location"].default_value = (-0.85, -0.58, 0.0)
    gr = nt.nodes.new("ShaderNodeTexGradient")
    gr.gradient_type = 'SPHERICAL'
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    cr = ramp.color_ramp
    cr.elements[0].position = 0.0
    cr.elements[0].color = (0.0, 0.006, 0.05, 1)
    cr.elements[1].position = 0.75
    cr.elements[1].color = (0.0, 0.09, 0.55, 1)
    e = cr.elements.new(0.35)
    e.color = (0.0, 0.025, 0.2, 1)
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = 2.2
    gl = nt.nodes.new("ShaderNodeBsdfPrincipled")
    set_input(gl, "Base Color", (0.0, 0.0, 0.0, 1))
    set_input(gl, "Roughness", 0.03)
    add = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(tc.outputs["Generated"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], gr.inputs["Vector"])
    nt.links.new(gr.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs[0], add.inputs[0])
    nt.links.new(gl.outputs[0], add.inputs[1])
    nt.links.new(add.outputs[0], out.inputs["Surface"])
    m.diffuse_color = (0.0, 0.05, 0.4, 1)
    M["screen"] = m

    M["icon"] = principled("Screen_Icon_Glow", (0.5, 0.75, 1.0), rough=0.3,
                           emission=(0.45, 0.72, 1.0), strength=9.0)

    # Light beams: colour from vertex attribute, soft edges across the ribbon
    m = _new_material("MIMO_Beam")
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_name = "Col"
    uvn = nt.nodes.new("ShaderNodeUVMap")
    uvn.uv_map = "UVMap"
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    m1 = nt.nodes.new("ShaderNodeMath"); m1.operation = 'MULTIPLY_ADD'
    m1.inputs[1].default_value = 2.0; m1.inputs[2].default_value = -1.0
    m2 = nt.nodes.new("ShaderNodeMath"); m2.operation = 'ABSOLUTE'
    m3 = nt.nodes.new("ShaderNodeMath"); m3.operation = 'SUBTRACT'
    m3.inputs[0].default_value = 1.0
    m4 = nt.nodes.new("ShaderNodeMath"); m4.operation = 'POWER'
    m4.inputs[1].default_value = 0.6
    strg = nt.nodes.new("ShaderNodeMath"); strg.operation = 'MULTIPLY_ADD'
    strg.inputs[1].default_value = BEAM_STRENGTH
    strg.inputs[2].default_value = BEAM_STRENGTH * 0.35
    alpha = nt.nodes.new("ShaderNodeMath"); alpha.operation = 'MULTIPLY'
    alpha.inputs[1].default_value = 2.4
    alpha.use_clamp = True
    em = nt.nodes.new("ShaderNodeEmission")
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    L = nt.links.new
    L(uvn.outputs["UV"], sep.inputs[0])
    L(sep.outputs["Y"], m1.inputs[0])
    L(m1.outputs[0], m2.inputs[0])
    L(m2.outputs[0], m3.inputs[1])
    L(m3.outputs[0], m4.inputs[0])
    L(m4.outputs[0], strg.inputs[0])
    L(m4.outputs[0], alpha.inputs[0])
    L(attr.outputs["Color"], em.inputs["Color"])
    L(strg.outputs[0], em.inputs["Strength"])
    L(alpha.outputs[0], mix.inputs[0])
    L(tr.outputs[0], mix.inputs[1])
    L(em.outputs[0], mix.inputs[2])
    L(mix.outputs[0], out.inputs["Surface"])
    _blended(m)
    m.diffuse_color = (0.4, 0.3, 1.0, 1)
    M["beam"] = m
    return M


# ---------------------------------------------------------------------------
# Parts of the diorama
# ---------------------------------------------------------------------------
def build_base(C, M):
    # Black plinth 100 x 62 x 5.5 cm
    box("Base_Plinth", (1.00, 0.62, BASE_H), (0, 0, BASE_H / 2), C, M["base"], bevel=0.008, seg=4)
    # Grey top surface
    box("Base_Ground", (0.95, 0.57, INLAY_H + 0.002), (0, 0.0, BASE_H + (INLAY_H - 0.002) / 2),
        C, M["ground"], bevel=0.002, seg=2)
    # Brushed metal name plate on the front face
    plate = box("NamePlate", (0.40, 0.003, 0.042), (0, -0.31 - 0.0015, BASE_H * 0.5),
                C, M["alu"], bevel=0.0012, seg=3)
    # four little screws
    bm = bmesh.new()
    for sx in (-0.19, 0.19):
        for sz in (-0.014, 0.014):
            bm_sphere(bm, (sx, -0.3132, BASE_H * 0.5 + sz), 0.0018, seg=10)
    obj_from_bm("NamePlate_Screws", bm, C, M["silver"], smooth=80)
    text("NamePlate_Text", TITLE, 0.030, (0, -0.3134, BASE_H * 0.5), C, M["black"],
         rot=(90 * DEG, 0, 0), extrude=0.0004, bevel=0.0001)
    return plate


def build_backboard(C, M):
    T = 0.025
    e = empty("Backboard", (0, 0.245, G), (90 * DEG, 0, 0), C)
    pts = rr_points(0.80, BOARD_H, [0.03, 0.06, 0.0, 0.0], seg=10, cy=BOARD_H / 2)
    slab("Backboard_Panel", pts, 0.0, T, C, M["board"], bevel=0.004, seg=4, parent=e)
    # Thin chrome edge trim on the front face
    outer = rr_points(0.792, BOARD_H - 0.008, [0.026, 0.056, 0.0, 0.0], seg=10, cy=BOARD_H / 2)
    inner = rr_points(0.786, BOARD_H - 0.014, [0.023, 0.053, 0.0, 0.0], seg=10, cy=BOARD_H / 2 + 0.003)
    bm = bmesh.new()
    bm_ring(bm, outer, inner, T, T + 0.0008)
    o = obj_from_bm("Backboard_Trim", bm, C, M["silver"], smooth=0)
    o.parent = e
    # Title "MIMO Technology"
    text("Backboard_Title", TITLE, 0.058, (0.11, BOARD_H - 0.07, T + 0.0015), C, M["white"],
         parent=e, extrude=0.0015, bevel=0.0004)
    return e


def bm_frustum(bm, center, bottom, top, height, rot=None):
    """Box whose bottom footprint (x, y) differs from the top one."""
    tmp = bmesh.new()
    bmesh.ops.create_cube(tmp, size=1.0)
    mat = Matrix.Translation(Vector(center))
    if rot is not None:
        mat = mat @ rot.to_matrix().to_4x4()
    for v in tmp.verts:
        sx, sy = (bottom if v.co.z < 0 else top)
        v.co = mat @ Vector((v.co.x * sx, v.co.y * sy, v.co.z * height))
    me = bpy.data.meshes.new("tmp")
    tmp.to_mesh(me)
    tmp.free()
    bm.from_mesh(me)
    bpy.data.meshes.remove(me)


def bm_rect_loft(bm, base, rot, rings):
    """Closed solid through rectangles [(size_x, size_y, z), ...] bottom->top."""
    R = rot.to_matrix()
    loops = []
    for sx, sy, z in rings:
        loops.append([bm.verts.new(Vector((base.x, base.y, z)) + R @ Vector((qx * sx / 2, qy * sy / 2, 0)))
                      for qx, qy in ((1, 1), (-1, 1), (-1, -1), (1, -1))])
    bm.faces.new(list(reversed(loops[0])))
    bm.faces.new(loops[-1])
    for a, b in zip(loops, loops[1:]):
        for i in range(4):
            j = (i + 1) % 4
            bm.faces.new((a[i], a[j], b[j], b[i]))


def build_tower(C, M, C_white=None):
    """Lattice cell tower that 3D-prints WITHOUT supports.

    * Every brace is steeper than 45 degrees: each face has a centre post and
      an X in each half, so the bays stay short (same look as before).
    * No horizontal bars, no floating parts: the mast stands on four 45-degree
      struts, pipes have pointed bottoms carried by 45-degree struts, brackets
      and radio units grow out of the pipes.
    * The white antenna panels (with their caps) are SEPARATE parts
      (collection "Antenna_Parts_White") to print standing and glue on.
    """
    C_white = C_white or C
    tx, ty = -0.30, 0.075
    z_pad = G + 0.008
    z_top = 0.40
    pad = box("Tower_Pad", (0.15, 0.15, 0.010), (tx, ty, G + 0.003), C, M["concrete"])
    print_bevel(pad, 0.0015, 2)

    bm = bmesh.new()
    a0, a1 = 0.058, 0.017
    STEEP = 1.2            # rise / run of every brace (> 1 means steeper than 45 deg)

    def half(z):
        return a0 + (a1 - a0) * (z - z_pad) / (z_top - z_pad)

    def corners(z, a=None):
        a = half(z) if a is None else a
        return [Vector((tx + sx * a, ty + sy * a, z))
                for sx, sy in ((1, 1), (-1, 1), (-1, -1), (1, -1))]

    def mids(z, a=None):
        c = corners(z, a)
        return [(c[i] + c[(i + 1) % 4]) * 0.5 for i in range(4)]

    # bay heights: run of a half-face X is ~ half-width -> bay = 1.2 x half-width
    levels = [z_pad]
    while True:
        h = half(levels[-1]) * STEEP
        if levels[-1] + h > z_top - half(levels[-1]) * STEEP * 0.75:
            levels.append(z_top)
            break
        levels.append(levels[-1] + h)

    R_LEG, R_H, R_D = 0.0034, 0.0018, 0.0014
    for c0, c1 in zip(corners(z_pad), corners(z_top)):
        bm_cyl(bm, c0 - Vector((0, 0, 0.0003)), c1, R_LEG, seg=32)  # legs (one piece, foot sunk)
    for m0, m1 in zip(mids(z_pad), mids(z_top)):
        bm_cyl(bm, m0 - Vector((0, 0, 0.0003)), m1, R_H, seg=20)   # face centre posts (foot sunk into pad)
    for k in range(len(levels) - 1):
        c0, c1 = corners(levels[k]), corners(levels[k + 1])
        m0, m1 = mids(levels[k]), mids(levels[k + 1])
        for i in range(4):
            j = (i + 1) % 4
            bm_cyl(bm, c0[i], m1[i], R_D, seg=16)                  # X in left half
            bm_cyl(bm, m0[i], c1[i], R_D, seg=16)
            bm_cyl(bm, m0[i], c1[j], R_D, seg=16)                  # X in right half
            bm_cyl(bm, c0[j], m1[i], R_D, seg=16)
    cb = corners(z_pad)
    for i, c in enumerate(cb):                                     # ground ring + feet
        bm_cyl(bm, c - Vector((0, 0, 0.0017)), cb[(i + 1) % 4] - Vector((0, 0, 0.0017)), R_H, seg=6)
        bm_box(bm, c + Vector((0, 0, 0.004)), (0.014, 0.014, 0.008))
        bm_box(bm, c + Vector((0, 0, 0.0005)), (0.02, 0.02, 0.001))
    # Head frame above the lattice: posts + X bracing (bays taller than wide)
    head = [z_top, 0.441, 0.482, 0.522]
    for c0, c1 in zip(corners(z_top, a1), corners(head[-1], a1)):
        bm_cyl(bm, c0 - Vector((0, 0, 0.0006)), c1, R_LEG * 0.85, seg=28)   # sunk into the leg top
    for k in range(len(head) - 1):
        c0, c1 = corners(head[k], a1), corners(head[k + 1], a1)
        for i in range(4):
            j = (i + 1) % 4
            bm_cyl(bm, c0[i], c1[j], R_D, seg=16)
            bm_cyl(bm, c0[j], c1[i], R_D, seg=16)
    # Smooth joints: a ball of the member's own radius where members meet or
    # end (leg tops, centre-post tops, head-post tops) -> no cut ends showing.
    for c in corners(z_top):
        bm_sphere(bm, c, R_LEG, seg=32)
    for m in mids(z_top):
        bm_sphere(bm, m, R_H, seg=20)
    for c in corners(head[-1], a1):
        bm_sphere(bm, c, R_LEG * 0.85, seg=28)
    # Central mast: stands on four 45-degree struts from the leg tops
    run = a1 * math.sqrt(2)
    z_m = z_top + run * STEEP
    for c in corners(z_top, a1):            # struts end inside the mast foot (hidden ends)
        bm_cyl(bm, c, (tx, ty, z_m + 0.0025), R_D * 1.2, seg=16)
    bm_lathe(bm, (tx, ty, z_m), [(0.0008, 0.0), (0.0055, 0.0050), (0.0055, 0.580 - z_m)], seg=32)
    bm_cyl(bm, (tx, ty, 0.580), (tx, ty, 0.5925), 0.0012, seg=16, r2=0.0004)  # lightning rod
    lat = obj_from_bm("Tower_Lattice", bm, C, M["steel"], smooth=40)
    self_union(lat)                          # one clean solid, joints really fused

    # Aviation light on the mast
    bm = bmesh.new()
    bm_sphere(bm, (tx, ty, 0.5815), 0.0035, seg=24)
    obj_from_bm("Tower_AviationLight", bm, C, M["led_red"], smooth=80)

    # Anchor finder: highest point on the mast / head posts / legs from which a
    # straight strut reaches `T` at least 45 degrees (x STEEP) steep.
    def anchor(T):
        best = None
        z = T.z
        while z > z_pad + 0.01:
            cands = []
            if z >= z_m + 0.006:
                cands.append(Vector((tx, ty, z)))
            a = a1 if z >= z_top else half(z)
            if z <= head[-1]:
                cands += corners(z, a)
            for p in cands:
                hd = (Vector((T.x, T.y, 0)) - Vector((p.x, p.y, 0))).length
                if z <= T.z - hd * STEEP + 1e-9:
                    return p
            z -= 0.0005
        return best

    # Antenna panels (white, separate parts) + mounts (part of the tower) -----
    panels = []
    specs = [  # (azimuth deg, centre z, height, width, radius)
        (-15, 0.465, 0.096, 0.038, 0.056),
        (105, 0.465, 0.096, 0.038, 0.056),
        (225, 0.465, 0.096, 0.038, 0.056),
        (20, 0.548, 0.062, 0.030, 0.046),
        (200, 0.548, 0.062, 0.030, 0.046),
    ]
    arm_bm = bmesh.new()
    depth = 0.016
    for i, (az, zc, h, w, R) in enumerate(specs):
        a = az * DEG
        n = Vector((math.cos(a), math.sin(a), 0))
        side = Vector((-n.y, n.x, 0))
        c = Vector((tx, ty, zc)) + n * R
        rot = Euler((0, 0, a), 'XYZ')
        # --- white panel: only vertical edges rounded (prints standing up)
        bm = bmesh.new()
        bm_box(bm, (0, 0, 0), (depth, w, h))
        ob = obj_from_bm("Antenna_Panel_%d" % i, bm, C_white, M["radome"])
        ob.location = c
        ob.rotation_euler = rot
        print_bevel(ob, 0.0055, 5, angle=30, skip_top=True)
        # caps belong to the panel part: flat bottom cap, chamfered top cap
        bm = bmesh.new()
        bm_box(bm, (c.x, c.y, zc - h / 2 - 0.0015), (depth + 0.002, w + 0.002, 0.004), rot)
        obj_from_bm("Antenna_PanelCapBottom_%d" % i, bm, C_white, M["cap"])
        bm = bmesh.new()
        bm_frustum(bm, (c.x, c.y, zc + h / 2 + 0.0015), (depth, w), (depth + 0.002, w + 0.002), 0.004, rot)
        obj_from_bm("Antenna_PanelCapTop_%d" % i, bm, C_white, M["cap"])
        panels.append((c, n, h, w, depth))

        # --- mounts (tower part): pointed pipe, 45-degree struts, wedge brackets
        pipe = c - n * (depth / 2 + 0.006)
        pb = zc - h / 2 - 0.012
        bm_lathe(arm_bm, (pipe.x, pipe.y, pb),
                 [(0.0005, 0.0), (0.0024, 0.0019 * STEEP), (0.0024, h + 0.024)], seg=20)
        # struts start where they always did; the lower one now ends 2.2 mm up
        # inside the pipe so its end is hidden and it wraps the pipe tip
        for T, T_end in ((Vector((pipe.x, pipe.y, pb + 0.0003)), Vector((pipe.x, pipe.y, pb + 0.0025))),
                         (Vector((pipe.x, pipe.y, zc + 0.3 * h)), None)):
            A = anchor(T)
            if A is not None:
                bm_cyl(arm_bm, A, T_end or T, 0.0019, seg=16)
        u_pipe, u_back = -(depth / 2 + 0.006), -depth / 2       # brackets end flush on the
        gap = u_back - u_pipe                                     # panel back (glue face)
        for s in (0.32, -0.32):
            zz = zc + s * h
            bm_prism(arm_bm, c, n, side, 0.012, [
                (u_pipe, zz - 0.002 - gap * STEEP), (u_back, zz - 0.002),
                (u_back, zz + 0.002), (u_pipe, zz + 0.002)])
        # radio unit clamped on the pipe, with a pointed (45 deg) underside
        if R > 0.045:
            zr = zc - h * 0.15
            # one solid: pointed 45-degree bottom + box (no seam between them)
            bm_rect_loft(arm_bm, Vector((pipe.x, pipe.y, 0)), rot, [
                (0.0015, 0.0015, zr - 0.014), (0.010, 0.018, zr - 0.004), (0.010, 0.018, zr + 0.014)])
    mounts = obj_from_bm("Antenna_Mounts", arm_bm, C, M["steel_dark"], smooth=40)
    self_union(mounts)
    return panels


def build_building(C, M, name, cx, cy, w, d, h, rows, cols_f, cols_s, door=True):
    z0 = G
    pod = 0.006
    podium = box(name + "_Podium", (w + 0.010, d + 0.010, pod), (cx, cy, z0 + pod / 2), C,
                 M["building_trim"])
    print_bevel(podium, 0.0012, 2)
    zb = z0 + pod
    # Walls + parapet are ONE solid (roof is recessed into it) so nothing
    # overhangs at the roof edge when 3D printing.
    t, ph = 0.004, 0.007
    body = box(name + "_Body", (w, d, h + ph), (cx, cy, zb + (h + ph) / 2), C, M["building"])

    ww, wh = 0.018, 0.024
    depth = 0.003
    cut = bmesh.new()
    panes = bmesh.new()
    sills = bmesh.new()
    margin = 0.022
    row_z = [zb + margin + (h - 2 * margin) * (r + 0.5) / rows - 0.004 for r in range(rows)]

    faces = [  # (normal, along vector, half-depth, half-width-along, columns)
        (Vector((0, -1, 0)), Vector((1, 0, 0)), d / 2, w, cols_f, True),
        (Vector((1, 0, 0)), Vector((0, 1, 0)), w / 2, d, cols_s, False),
        (Vector((-1, 0, 0)), Vector((0, -1, 0)), w / 2, d, cols_s, False),
        (Vector((0, 1, 0)), Vector((-1, 0, 0)), d / 2, w, cols_f, False),
    ]
    centre = Vector((cx, cy, 0))
    door_w, door_h = 0.024, 0.042
    for n, along, hd, span, cols, is_front in faces:
        step = span / (cols + 0.35)
        for ci in range(cols):
            off = (ci - (cols - 1) / 2) * step
            for ri, z in enumerate(row_z):
                if door and is_front and ri == 0 and ci == (cols - 1) // 2:
                    continue
                p = centre + n * hd + along * off + Vector((0, 0, z))
                zb_w, zt_w = z - wh / 2, z + wh / 2
                # recess with a 45-degree chamfered top -> prints without supports
                # (the 45-degree line crosses the wall at zt_w; no vertex sits
                #  exactly on the wall plane, which keeps the Boolean clean)
                bm_prism(cut, p, n, along, ww, [
                    (depth, zb_w), (depth, zt_w + depth),
                    (-depth, zt_w - depth), (-depth, zb_w)])
                pp = p - n * (depth * 0.7) - Vector((0, 0, depth / 2))
                psz = Vector((abs(along.x) * ww + abs(n.x) * 0.001,
                              abs(along.y) * ww + abs(n.y) * 0.001, wh - depth))
                bm_box(panes, pp, psz)
                # sill: flat top, 45-degree underside back to the wall
                bm_prism(sills, p, n, along, ww + 0.005, [
                    (-0.001, zb_w), (SILL_D, zb_w), (SILL_D, zb_w - 0.0008),
                    (-0.001, zb_w - 0.0018 - SILL_D)])
        if door and is_front:
            p = centre + n * hd
            zt_d = zb + door_h
            bm_prism(cut, p, n, along, door_w, [
                (depth, zb - 0.001), (depth, zt_d + depth),
                (-depth, zt_d - depth), (-depth, zb - 0.001)])
            bm_box(panes, p - n * depth * 0.7 + Vector((0, 0, zb + (door_h - depth) / 2)),
                   Vector((door_w, 0.001, door_h - depth)))
            # canopy above the door: 45-degree wedge (no supports needed)
            ct, cd = zt_d + 0.0075, 0.006
            bm_prism(sills, p, n, along, door_w + 0.012, [
                (-0.001, ct), (cd, ct), (cd, ct - 0.001),
                (-0.001, ct - 0.002 - cd)])
    # recessed roof inside the parapet
    bm_box(cut, (cx, cy, zb + h + ph / 2 + 0.001), (w - 2 * t, d - 2 * t, ph + 0.002))
    # make cutter local to the body
    for v in cut.verts:
        v.co -= body.location
    boolean_cut(body, cut, name + "_Cutter")
    print_bevel(body, 0.0012, 2)

    gp = obj_from_bm(name + "_Windows", panes, C, M["glass"])
    obj_from_bm(name + "_Sills", sills, C, M["building"])

    # door mullions
    bm = bmesh.new()
    p = Vector((cx, cy - d / 2 - 0.0018, zb + door_h / 2))
    bm_box(bm, p - Vector((0, 0, depth / 2)), (0.0015, 0.0012, door_h - depth))
    # transom bar as a 45-degree wedge (no flat underside)
    tz = zb + door_h / 2 + 0.0047
    bm_prism(bm, Vector((cx, cy - d / 2, 0)), Vector((0, -1, 0)), Vector((1, 0, 0)), door_w,
             [(-0.0024, tz), (-0.0009, tz), (-0.0024, tz - 0.0015)])
    obj_from_bm(name + "_DoorFrame", bm, C, M["building"])

    # Roof: roof box (stair housing) and vents (parapet is part of the body)
    zt = zb + h
    rb = box(name + "_RoofBox", (w * 0.42, d * 0.38, 0.020), (cx, cy, zt + 0.010), C,
             M["building"])
    print_bevel(rb, 0.0012, 2, skip_top=True)
    cap = box(name + "_RoofBoxCap", (w * 0.46, d * 0.42, 0.004), (cx, cy, zt + 0.022), C,
              M["building_trim"])
    # taper the underside so the cap overhang is 45 degrees or less
    sx, sy = (w * 0.42) / (w * 0.46), (d * 0.38) / (d * 0.42)
    for v in cap.data.vertices:
        if v.co.z < 0:
            v.co.x *= sx
            v.co.y *= sy
    print_bevel(cap, 0.0008, 2)
    bm = bmesh.new()
    for vx, vy in ((-w * 0.32, d * 0.3), (w * 0.33, -d * 0.3)):
        # one solid: pipe + flared cap (41 deg overhang, printable)
        bm_lathe(bm, (cx + vx, cy + vy, zt), [(0.0035, 0.0), (0.0035, 0.008),
                                              (0.0048, 0.0095), (0.0048, 0.0105)], seg=16)
    obj_from_bm(name + "_Vents", bm, C, M["building_trim"], smooth=40)
    return body


def build_road(C, M):
    ang = math.atan2(0.6, 0.8)
    d = Vector((math.cos(ang), math.sin(ang), 0))
    p0 = Vector((0.07, -0.005, 0))
    t0, t1 = -0.34, 0.36
    L = t1 - t0
    c = p0 + d * ((t0 + t1) / 2)
    W = 0.072
    road = box("Road_Asphalt", (L, W, 0.002), (c.x, c.y, G + 0.001), C, M["asphalt"],
               rot=(0, 0, ang))
    # curbs + markings in road-local space
    curb = bmesh.new()
    paint = bmesh.new()
    for s in (-1, 1):
        bm_box(curb, (0, s * (W / 2 + 0.003), 0.0025), (L, 0.006, 0.005))
        bm_box(paint, (0, s * (W / 2 - 0.006), 0.0022), (L, 0.0025, 0.0005))
    x = -L / 2 + 0.01
    while x + 0.02 < L / 2:
        bm_box(paint, (x + 0.01, 0, 0.0022), (0.02, 0.0025, 0.0005))
        x += 0.035
    for name, bmx, mat in (("Road_Curbs", curb, M["curb"]), ("Road_Markings", paint, M["paint"])):
        ob = obj_from_bm(name, bmx, C, mat)
        ob.location = (c.x, c.y, G)
        ob.rotation_euler = (0, 0, ang)
    # Small access path from the road to the tower
    box("Road_TowerPath", (0.16, 0.03, 0.0016), (-0.215, -0.02, G + 0.0008), C, M["asphalt"],
        rot=(0, 0, 70 * DEG))
    return road


def build_phone(C, M):
    ped_rot = -20 * DEG
    px, py = 0.345, -0.03
    # pedestal (two tiers)
    box("Phone_Pedestal", (0.18, 0.11, 0.045), (px, py, G + 0.0225), C, M["pedestal"],
        bevel=0.003, seg=3, rot=(0, 0, ped_rot))
    box("Phone_PedestalTop", (0.17, 0.10, 0.010), (px, py, G + 0.050), C, M["pedestal_top"],
        bevel=0.002, seg=3, rot=(0, 0, ped_rot))
    z_floor = G + 0.055
    # phone holder slot (little lip in front of the phone)
    box("Phone_HolderLip", (0.16, 0.012, 0.008), (0, 0, 0), C, M["pedestal_top"], bevel=0.0015)
    lip = bpy.data.objects["Phone_HolderLip"]

    W, H, T = 0.150, 0.310, 0.014
    rot = (90 * DEG, 0, ped_rot)
    e = empty("Phone", (px, py, z_floor), rot, C)
    lip.parent = e
    lip.location = (0, 0.004, T / 2 + 0.008)

    body = rr_points(W, H, 0.021, seg=12, cy=H / 2)
    slab("Phone_Frame", body, -T / 2, T / 2, C, M["frame"], bevel=0.0035, seg=5, parent=e)
    glass = rr_points(W - 0.004, H - 0.004, 0.019, seg=12, cy=H / 2)
    slab("Phone_FrontGlass", glass, T / 2 - 0.0005, T / 2 + 0.0008, C, M["phone_glass"],
         bevel=0.0006, seg=2, parent=e)
    scr = rr_points(W - 0.014, H - 0.014, 0.015, seg=12, cy=H / 2)
    slab("Phone_Screen", scr, T / 2 + 0.0008, T / 2 + 0.0011, C, M["screen"], parent=e)
    notch = rr_points(0.040, 0.009, 0.0045, seg=8, cy=H - 0.0115)
    slab("Phone_Notch", notch, T / 2 + 0.0011, T / 2 + 0.0014, C, M["phone_glass"], parent=e)
    # earpiece + selfie camera
    bm = bmesh.new()
    bm_slab(bm, rr_points(0.012, 0.0016, 0.0008, seg=4, cy=H - 0.0115), T / 2 + 0.0014, T / 2 + 0.0017)
    o = obj_from_bm("Phone_Earpiece", bm, C, M["steel_dark"], smooth=0); o.parent = e
    bm = bmesh.new()
    bm_cyl(bm, (0.012, H - 0.0115, T / 2 + 0.0014), (0.012, H - 0.0115, T / 2 + 0.0017), 0.0016, seg=16)
    o = obj_from_bm("Phone_SelfieCam", bm, C, M["steel_dark"], smooth=0); o.parent = e

    zf = T / 2 + 0.0016           # icon layer
    # Wi-Fi symbol (three arcs + dot)
    bm = bmesh.new()
    cxy = (0.0, H * 0.585)
    for r in (0.010, 0.019, 0.028):
        a0, a1, segs = 45 * DEG, 135 * DEG, 18
        outer = [(cxy[0] + (r + 0.0028) * math.cos(a0 + (a1 - a0) * i / segs),
                  cxy[1] + (r + 0.0028) * math.sin(a0 + (a1 - a0) * i / segs)) for i in range(segs + 1)]
        inner = [(cxy[0] + (r - 0.0028) * math.cos(a0 + (a1 - a0) * i / segs),
                  cxy[1] + (r - 0.0028) * math.sin(a0 + (a1 - a0) * i / segs)) for i in range(segs + 1)]
        bm_slab(bm, outer + list(reversed(inner)), zf, zf + 0.0006)
    bm_cyl(bm, (cxy[0], cxy[1] - 0.0005, zf), (cxy[0], cxy[1] - 0.0005, zf + 0.0006), 0.0036, seg=20)
    o = obj_from_bm("Phone_WifiIcon", bm, C, M["icon"], smooth=0); o.parent = e
    # "5G"
    text("Phone_5G", "5G", 0.048, (0.0, H * 0.45, zf), C, M["icon"], parent=e,
         extrude=0.0003, bevel=0.0001)
    # up/down arrows
    bm = bmesh.new()
    ay = H * 0.315
    for sx, up in ((-0.007, False), (0.007, True)):
        sh, hw, hl, L = 0.0018, 0.0055, 0.007, 0.024
        if up:
            pts = [(sx - sh, ay - L / 2), (sx + sh, ay - L / 2), (sx + sh, ay + L / 2 - hl),
                   (sx + hw, ay + L / 2 - hl), (sx, ay + L / 2), (sx - hw, ay + L / 2 - hl),
                   (sx - sh, ay + L / 2 - hl)]
        else:
            pts = [(sx, ay - L / 2), (sx + hw, ay - L / 2 + hl), (sx + sh, ay - L / 2 + hl),
                   (sx + sh, ay + L / 2), (sx - sh, ay + L / 2), (sx - sh, ay - L / 2 + hl),
                   (sx - hw, ay - L / 2 + hl)]
        bm_slab(bm, pts, zf, zf + 0.0006)
    o = obj_from_bm("Phone_ArrowsIcon", bm, C, M["icon"], smooth=0); o.parent = e
    # side buttons (right: power, left: volume)
    bm = bmesh.new()
    bm_box(bm, (W / 2 + 0.0008, H * 0.68, 0), (0.002, 0.028, 0.004))
    for yb in (H * 0.75, H * 0.66):
        bm_box(bm, (-W / 2 - 0.0008, yb, 0), (0.002, 0.020, 0.004))
    o = obj_from_bm("Phone_Buttons", bm, C, M["frame"]); o.parent = e
    add_bevel(o, 0.0007, 2)
    # rear camera bump
    bm = bmesh.new()
    bm_slab(bm, rr_points(0.04, 0.04, 0.01, seg=8, cx=-0.045, cy=H - 0.035), -T / 2 - 0.0018, -T / 2)
    o = obj_from_bm("Phone_CameraBump", bm, C, M["phone_glass"]); o.parent = e
    bm = bmesh.new()
    for lx, ly in ((-0.055, H - 0.025), (-0.035, H - 0.025), (-0.055, H - 0.045)):
        bm_cyl(bm, (lx, ly, -T / 2 - 0.0018), (lx, ly, -T / 2 - 0.0028), 0.0062, seg=20)
    o = obj_from_bm("Phone_CameraLenses", bm, C, M["frame"], smooth=40); o.parent = e

    mat = Matrix.Translation((px, py, z_floor)) @ Euler(rot, 'XYZ').to_matrix().to_4x4()
    return mat, W, H, T


def build_sign(C, M):
    W, H, T = 0.30, 0.165, 0.012
    alpha = 72 * DEG
    sx, sy = -0.27, -0.205
    zc = G + 0.014 + (H / 2) * math.sin(alpha)
    e = empty("InfoSign", (sx, sy, zc), (alpha, 0, 0), C)
    # silver back plate (shows as a rim) + black glossy face
    slab("InfoSign_Back", rr_points(W + 0.006, H + 0.006, 0.014, seg=8), -T - 0.004, -T + 0.004,
         C, M["silver"], bevel=0.0015, seg=3, parent=e)
    slab("InfoSign_Panel", rr_points(W, H, 0.012, seg=8), -T, 0.0, C, M["sign"],
         bevel=0.002, seg=3, parent=e)
    bm = bmesh.new()
    bm_ring(bm, rr_points(W - 0.010, H - 0.010, 0.008, seg=8),
            rr_points(W - 0.016, H - 0.016, 0.005, seg=8), 0.0, 0.0008)
    o = obj_from_bm("InfoSign_Border", bm, C, M["sign_border"], smooth=0)
    o.parent = e
    text("InfoSign_Header", SIGN_HEADER, 0.038, (-W / 2 + 0.024, 0.044, 0.0004), C, M["white"],
         parent=e, align_x='LEFT', extrude=0.0006)
    for i, line in enumerate(SIGN_LINES):
        text("InfoSign_Line%d" % (i + 1), line, 0.0215,
             (-W / 2 + 0.034, 0.003 - i * 0.033, 0.0004), C, M["white"],
             parent=e, align_x='LEFT', extrude=0.0005)
    # stand: slanted wedge behind and a lip at the bottom
    Mx = Matrix.Translation((sx, sy, zc)) @ Euler((alpha, 0, 0)).to_matrix().to_4x4()
    pb = Mx @ Vector((0, -H / 2 + 0.01, -T - 0.004))
    pt = Mx @ Vector((0, H * 0.25, -T - 0.004))
    prof = [(pb.y, G), (pt.y + 0.002, G), (pt.y, pt.z), (pb.y, pb.z)]
    bm = bmesh.new()
    hw = 0.11
    vl = [bm.verts.new((sx - hw, y, z)) for y, z in prof]
    vr = [bm.verts.new((sx + hw, y, z)) for y, z in prof]
    bm.faces.new(vl)
    bm.faces.new(list(reversed(vr)))
    for i in range(4):
        j = (i + 1) % 4
        bm.faces.new((vl[j], vl[i], vr[i], vr[j]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    o = obj_from_bm("InfoSign_Stand", bm, C, M["base"])
    add_bevel(o, 0.002, 2)
    pbot = Mx @ Vector((0, -H / 2, 0.0))
    box("InfoSign_Lip", (W + 0.01, 0.022, 0.012), (sx, pbot.y - 0.004, G + 0.006), C, M["base"],
        bevel=0.002)


def ribbon(name, p0, p1, w0, w1, c0, c1, C, mat, seg=28, across=6):
    p0, p1 = Vector(p0), Vector(p1)
    d = (p1 - p0).normalized()
    side = d.cross(Vector((0, 0, 1))).normalized()
    wv = side.cross(d).normalized()
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")
    rows = []
    for i in range(seg + 1):
        t = i / seg
        c = p0.lerp(p1, t)
        w = w0 + (w1 - w0) * (t ** 0.85)
        rows.append([bm.verts.new(c + wv * (w * (j / across - 0.5))) for j in range(across + 1)])
    for i in range(seg):
        for j in range(across):
            f = bm.faces.new((rows[i][j], rows[i + 1][j], rows[i + 1][j + 1], rows[i][j + 1]))
            f.smooth = True
            for loop, (ii, jj) in zip(f.loops, ((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1))):
                loop[uv].uv = (ii / seg, jj / across)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ca = me.color_attributes.new("Col", 'FLOAT_COLOR', 'POINT')
    for i in range(seg + 1):
        t = i / seg
        col = [c0[k] + (c1[k] - c0[k]) * t for k in range(3)] + [1.0]
        for j in range(across + 1):
            ca.data[i * (across + 1) + j].color = col
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    try:
        ob.visible_shadow = False
    except Exception:
        pass
    return link_obj(ob, C)


def build_beams(C, M, panels, phone_mat, PW, PH, PT, bldA):
    BLUE = (0.05, 0.25, 1.0)
    CYAN = (0.1, 0.55, 1.0)
    RED = (1.0, 0.06, 0.12)
    ORANGE = (1.0, 0.45, 0.05)
    MAG = (0.95, 0.08, 0.75)
    PURP = (0.45, 0.1, 1.0)
    VIOL = (0.65, 0.2, 1.0)

    front = PT / 2 + 0.003

    def ph(x, y):
        return phone_mat @ Vector((x, y, front))

    # source points on the panels facing the phone
    c1, n1, h1, w1, d1 = panels[0]
    c2, n2, h2, w2, d2 = panels[3]
    s1 = c1 + n1 * (d1 / 2 + 0.002)
    s2 = c2 + n2 * (d2 / 2 + 0.002)
    up = Vector((0, 0, 1))
    ex = -PW / 2 + 0.012
    beams = [
        (s2 + up * 0.012, ph(ex, PH * 0.735), 0.024, 0.0075, BLUE, CYAN),
        (s2 - up * 0.014, ph(ex, PH * 0.705), 0.020, 0.0065, CYAN, BLUE),
        (s1 + up * 0.026, ph(ex, PH * 0.680), 0.030, 0.0085, RED, ORANGE),
        (s1 + up * 0.000, ph(ex, PH * 0.650), 0.030, 0.0085, MAG, (1.0, 0.3, 0.6)),
        (s1 - up * 0.026, ph(ex, PH * 0.620), 0.028, 0.008, PURP, VIOL),
    ]
    # multipath beams reflected from building A
    bx, by, bz = bldA
    beams += [
        (Vector((bx, by + 0.035, bz - 0.020)), ph(ex, PH * 0.565), 0.022, 0.0075, PURP, VIOL),
        (Vector((bx, by + 0.015, bz - 0.040)), ph(ex, PH * 0.535), 0.022, 0.0075, ORANGE, (1.0, 0.6, 0.1)),
        (Vector((bx, by - 0.005, bz - 0.060)), ph(ex, PH * 0.505), 0.020, 0.007, BLUE, CYAN),
    ]
    for i, (a, b, wa, wb, ca, cb) in enumerate(beams):
        ribbon("Beam_%02d" % (i + 1), a, b, wa, wb, ca, cb, C, M["beam"])
    # faint incoming beams from the tower to the building (multipath origin)
    for i, off in enumerate((-0.03, 0.0)):
        ribbon("Beam_Incident_%d" % (i + 1), s1 + up * off,
               Vector((bx - 0.12, by + 0.02, bz - 0.03 + off)), 0.018, 0.012,
               (0.3, 0.2, 1.0), (0.3, 0.2, 1.0), C, M["beam"])
        bpy.data.objects["Beam_Incident_%d" % (i + 1)].hide_render = True
        bpy.data.objects["Beam_Incident_%d" % (i + 1)].hide_viewport = True


def build_studio(C):
    # Seamless curved backdrop
    bm = bmesh.new()
    prof = []
    for i in range(13):
        y = -3.0 + i * 0.25
        prof.append((y, 0.0))
    R = 0.8
    for i in range(1, 17):
        a = (i / 16) * 90 * DEG
        prof.append((0.0 + R * math.sin(a), R - R * math.cos(a)))
    prof.append((R, 2.5))
    left = [bm.verts.new((-4.0, y + 0.9, z - 0.0005)) for y, z in prof]
    right = [bm.verts.new((4.0, y + 0.9, z - 0.0005)) for y, z in prof]
    for i in range(len(prof) - 1):
        bm.faces.new((left[i], right[i], right[i + 1], left[i + 1]))
    m = principled("Studio_Backdrop", (0.22, 0.22, 0.23), rough=0.8)
    obj_from_bm("Studio_Backdrop", bm, C, m, smooth=80)

    def area(name, loc, target, size, power, color=(1, 1, 1)):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.shape = 'RECTANGLE'
        ld.size = size
        ld.size_y = size * 0.7
        ld.energy = power
        ld.color = color
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        look_at(ob, target)
        return link_obj(ob, C)

    tgt = (0, 0.02, 0.25)
    area("Light_Key", (-1.1, -1.3, 1.5), tgt, 1.2, 120)
    area("Light_Fill", (1.3, -1.1, 0.8), tgt, 1.0, 45, (0.95, 0.97, 1.0))
    area("Light_Top", (0.0, -0.2, 1.8), tgt, 1.4, 70)
    area("Light_Rim", (0.9, 1.4, 1.2), tgt, 0.8, 90)

    cam_d = bpy.data.cameras.new("Camera")
    cam_d.lens = 50
    cam_d.clip_start = 0.01
    cam_d.dof.use_dof = True
    cam_d.dof.aperture_fstop = 11.0
    cam = bpy.data.objects.new("Camera", cam_d)
    cam.location = (0.03, -1.62, 0.78)
    link_obj(cam, C)
    look_at(cam, (0.0, 0.02, 0.255))
    cam_d.dof.focus_distance = (Vector((0.0, -0.05, 0.25)) - cam.location).length
    bpy.context.scene.camera = cam

    w = bpy.data.worlds.new("Studio_World") if not bpy.context.scene.world else bpy.context.scene.world
    bpy.context.scene.world = w
    try:
        w.use_nodes = True
    except Exception:
        pass
    bg = next((n for n in w.node_tree.nodes if n.type == 'BACKGROUND'), None)
    if bg:
        bg.inputs[0].default_value = (0.45, 0.46, 0.48, 1)
        bg.inputs[1].default_value = 0.12


def setup_render(scene, samples=256):
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = samples
    try:
        scene.cycles.use_denoising = True
    except Exception:
        pass
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1280
    scene.render.film_transparent = False
    us = scene.unit_settings
    us.system = 'METRIC'
    us.scale_length = 1.0
    us.length_unit = 'CENTIMETERS'
    # 'Standard' keeps the beam colours fully saturated (like the reference);
    # exposure is lowered so the white buildings do not clip.
    vs = scene.view_settings
    vs.view_transform = 'Standard'
    vs.look = 'None'
    vs.exposure = -0.7
    setup_glow(scene)


def setup_glow(scene):
    """Bloom on the beams via the compositor (handles 4.x and 5.x APIs)."""
    try:
        if hasattr(scene, "compositing_node_group"):          # Blender 5.x
            ng = bpy.data.node_groups.new("MIMO_Compositor", "CompositorNodeTree")
            ng.interface.new_socket("Image", in_out='OUTPUT', socket_type='NodeSocketColor')
            rl = ng.nodes.new("CompositorNodeRLayers")
            gl = ng.nodes.new("CompositorNodeGlare")
            out = ng.nodes.new("NodeGroupOutput")
            gl.inputs["Type"].default_value = 'Bloom'
            gl.inputs["Threshold"].default_value = 2.0
            gl.inputs["Strength"].default_value = 0.35
            gl.inputs["Size"].default_value = 0.45
            ng.links.new(rl.outputs["Image"], gl.inputs["Image"])
            ng.links.new(gl.outputs["Image"], out.inputs[0])
            scene.compositing_node_group = ng
        else:                                                   # Blender 4.x
            scene.use_nodes = True
            nt = scene.node_tree
            for n in list(nt.nodes):
                nt.nodes.remove(n)
            rl = nt.nodes.new("CompositorNodeRLayers")
            gl = nt.nodes.new("CompositorNodeGlare")
            comp = nt.nodes.new("CompositorNodeComposite")
            try:
                gl.glare_type = 'BLOOM'
            except Exception:
                gl.glare_type = 'FOG_GLOW'
            gl.threshold = 2.0
            gl.mix = -0.45
            gl.size = 8
            nt.links.new(rl.outputs["Image"], gl.inputs["Image"])
            nt.links.new(gl.outputs["Image"], comp.inputs["Image"])
    except Exception as ex:                                     # glow is optional
        print("Glow setup skipped:", ex)


def fix_viewport():
    """Small-scale model: tighten viewport clipping when run inside the UI."""
    try:
        for win in bpy.context.window_manager.windows:
            for area in win.screen.areas:
                if area.type == 'VIEW_3D':
                    for sp in area.spaces:
                        if sp.type == 'VIEW_3D':
                            sp.clip_start = 0.001
                            sp.clip_end = 100
                            sp.shading.type = 'MATERIAL'
    except Exception:
        pass


def model_bounds(colls):
    dg = bpy.context.evaluated_depsgraph_get()
    zmin, zmax = 1e9, -1e9
    for c in colls:
        for ob in c.all_objects:
            if ob.type not in {'MESH', 'CURVE', 'FONT'} or ob.hide_render:
                continue
            ev = ob.evaluated_get(dg)
            me = ev.to_mesh()
            for v in me.vertices:
                z = (ev.matrix_world @ v.co).z
                zmin, zmax = min(zmin, z), max(zmax, z)
            ev.to_mesh_clear()
    return zmin, zmax


# ---------------------------------------------------------------------------
def build():
    global FONT_BOLD
    clear_scene()
    scene = bpy.context.scene
    FONT_BOLD = find_font(True)
    M = make_materials()

    root = new_collection("MIMO_Diorama")
    C_base = new_collection("Base", root)
    C_board = new_collection("Backboard", root)
    C_tower = new_collection("Tower", root)
    C_city = new_collection("Buildings_Road", root)
    C_phone = new_collection("Phone", root)
    C_sign = new_collection("Info_Sign", root)
    C_studio = new_collection("Studio")

    build_base(C_base, M)
    build_backboard(C_board, M)
    C_white = new_collection("Antenna_Parts_White", C_tower)
    panels = build_tower(C_tower, M, C_white)
    build_road(C_city, M)
    ax, ay, aw, ah = 0.0, 0.105, 0.12, 0.21
    build_building(C_city, M, "BuildingA", ax, ay, aw, 0.12, ah, rows=4, cols_f=3, cols_s=3)
    build_building(C_city, M, "BuildingB", 0.15, -0.12, 0.125, 0.125, 0.17, rows=4, cols_f=3,
                   cols_s=3)
    phone_mat, PW, PH, PT = build_phone(C_phone, M)
    build_sign(C_sign, M)
    if SHOW_BEAMS:
        C_beam = new_collection("MIMO_Beams", root)
        build_beams(C_beam, M, panels, phone_mat, PW, PH, PT,
                    (ax + aw / 2 + 0.002, ay, G + 0.006 + ah))
    build_studio(C_studio)
    setup_render(scene)
    fix_viewport()

    bpy.context.view_layer.update()
    zmin, zmax = model_bounds([root])
    print("MIMO diorama height: %.2f cm (base %.2f -> top %.2f)"
          % ((zmax - zmin) * 100, zmin * 100, zmax * 100))
    return scene


def pack_fonts():
    for f in bpy.data.fonts:
        if f.filepath != '<builtin>' and f.packed_file is None:
            try:
                f.pack()
            except Exception as ex:
                print("Could not pack font", f.name, ex)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []

    def arg(name, default=None):
        return argv[argv.index(name) + 1] if name in argv else default

    scene = build()
    samples = int(arg("--samples", 256))
    scene.cycles.samples = samples
    scene.render.resolution_percentage = int(arg("--percent", 100))
    pack_fonts()
    save = arg("--save")
    if save:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(save))
        print("Saved", save)
    out = arg("--render")
    if out:
        scene.render.filepath = os.path.abspath(out)
        bpy.ops.render.render(write_still=True)
        print("Rendered", out)


if __name__ == "__main__":
    main()
