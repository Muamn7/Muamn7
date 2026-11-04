"""Turn the generated part meshes into a Blender scene, STL files and renders.

Run with Blender's Python (the `bpy` module or `blender -b -P`):
    python build_blend.py PARTS.npz OUT_DIR [--render]
"""
import os
import sys
import math
import numpy as np
import bpy
import bmesh
from mathutils import Vector, Matrix

NPZ, OUT_DIR = sys.argv[1], sys.argv[2]
DO_RENDER = "--render" in sys.argv
STL_DIR = os.path.join(OUT_DIR, "stl")
IMG_DIR = os.path.join(OUT_DIR, "renders")
os.makedirs(STL_DIR, exist_ok=True)
os.makedirs(IMG_DIR, exist_ok=True)

data = np.load(NPZ)

# ---------------------------------------------------------------------------
# parts: name -> (colour, target triangle count, print quantity, label)
# ---------------------------------------------------------------------------
def srgb(hexstr):
    c = [int(hexstr[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return tuple(round(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4, 4) for x in c)


BLUE = srgb("#2A86E8")
PINK = srgb("#F2779A")
PURPLE = srgb("#8A35DA")
YELLOW = srgb("#F7D31A")
BLACK = srgb("#111113")
WHITE = srgb("#E6E6E6")
PIN_GREY = srgb("#9A9A9A")

PARTS = {
    "base":        ("Base",        BLACK, 90000, 1),
    "plaque":      ("Plaque",      WHITE, 6000, 1),
    "fc_left":     ("Fc_Left",     BLUE, 170000, 1),
    "fc_right":    ("Fc_Right",    BLUE, 170000, 1),
    "fc_bond_1":   ("Fc_Bond_1",   YELLOW, 6000, 1),
    "fc_bond_2":   ("Fc_Bond_2",   YELLOW, 6000, 1),
    "fc_bond_3":   ("Fc_Bond_3",   YELLOW, 6000, 1),
    "hinge":       ("Hinge",       YELLOW, 90000, 1),
    "fab_heavy_L": ("Fab_Heavy_L", BLUE, 190000, 1),
    "fab_heavy_R": ("Fab_Heavy_R", BLUE, 190000, 1),
    "light_L":     ("Light_L",     PINK, 95000, 1),
    "light_R":     ("Light_R",     PINK, 95000, 1),
    "vdomain_L":   ("VDomain_L",   PURPLE, 105000, 1),
    "vdomain_R":   ("VDomain_R",   PURPLE, 105000, 1),
    "pin":         ("Pin_3x12",    PIN_GREY, 3000, 8),
}

STL_NAME = {
    "base": "01_base_black.stl",
    "plaque": "02_plaque_white_optional.stl",
    "fc_left": "03_fc_left_blue.stl",
    "fc_right": "04_fc_right_blue.stl",
    "fc_bond_1": "05_fc_bond_1_bottom_yellow.stl",
    "fc_bond_2": "06_fc_bond_2_middle_yellow.stl",
    "fc_bond_3": "07_fc_bond_3_top_yellow.stl",
    "hinge": "08_hinge_yellow.stl",
    "fab_heavy_L": "09_fab_heavy_left_blue.stl",
    "fab_heavy_R": "10_fab_heavy_right_blue.stl",
    "light_L": "11_light_chain_left_pink.stl",
    "light_R": "12_light_chain_right_pink.stl",
    "vdomain_L": "13_antigen_site_left_purple.stl",
    "vdomain_R": "14_antigen_site_right_purple.stl",
    "pin": "15_pin_3x12mm_print_x8.stl",
}

# ---------------------------------------------------------------------------
# fresh scene in millimetres
# ---------------------------------------------------------------------------
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.unit_settings.system = "METRIC"
scene.unit_settings.scale_length = 0.001
scene.unit_settings.length_unit = "MILLIMETERS"

col_parts = bpy.data.collections.new("IgG_Antibody_Parts")
scene.collection.children.link(col_parts)
col_pins = bpy.data.collections.new("Pins_Assembled")
scene.collection.children.link(col_pins)


def make_material(name, rgb, rough=0.38, coat=0.25):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Roughness"].default_value = rough
    if "Coat Weight" in b.inputs:
        b.inputs["Coat Weight"].default_value = coat
        b.inputs["Coat Roughness"].default_value = 0.25
    m.diffuse_color = (*rgb, 1.0)
    return m


MATS = {}


def mat_for(rgb):
    key = tuple(rgb)
    if key not in MATS:
        names = {BLUE: "Heavy_Chain_Blue", PINK: "Light_Chain_Pink", PURPLE: "Antigen_Site_Purple",
                 YELLOW: "Disulfide_Yellow", BLACK: "Base_Black", WHITE: "Plaque_White",
                 PIN_GREY: "Pin_Grey"}
        rough = 0.55 if rgb == BLACK else 0.38
        MATS[key] = make_material(names.get(rgb, "mat"), rgb, rough)
    return MATS[key]


def mesh_from_arrays(name, v, f):
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(v))
    me.vertices.foreach_set("co", v.astype(np.float32).ravel())
    me.loops.add(f.size)
    me.loops.foreach_set("vertex_index", f.astype(np.int32).ravel())
    me.polygons.add(len(f))
    me.polygons.foreach_set("loop_start", np.arange(0, f.size, 3, dtype=np.int32))
    me.update(calc_edges=True)
    me.validate()
    return me


def check_manifold(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bad_e = sum(1 for e in bm.edges if len(e.link_faces) != 2)
    bad_v = sum(1 for v in bm.verts if not v.is_manifold)
    vol = bm.calc_volume(signed=True)
    bm.free()
    return bad_e, bad_v, vol


def cleanup(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=1e-5)
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])
    bm.to_mesh(obj.data)
    bm.free()


def decimate(obj, target):
    """Collapse-decimate; retry with a gentler ratio if it breaks the manifold."""
    n = len(obj.data.polygons)
    while target < n:
        mod = obj.modifiers.new("dec", "DECIMATE")
        mod.decimate_type = "COLLAPSE"
        mod.ratio = target / n
        mod.use_collapse_triangulate = True
        dg = bpy.context.evaluated_depsgraph_get()
        new = bpy.data.meshes.new_from_object(obj.evaluated_get(dg))
        obj.modifiers.clear()
        old = obj.data
        obj.data = new
        cleanup(obj)
        if check_manifold(obj)[0] == 0:
            bpy.data.meshes.remove(old)
            new.name = obj.name
            return
        print("  decimation broke the manifold, retrying gentler", obj.name, flush=True)
        obj.data = old
        bpy.data.meshes.remove(new)
        target = int(target * 1.25)



objs = {}
report = []
for key, (name, rgb, target, qty) in PARTS.items():
    v, f = data[key + "__v"], data[key + "__f"]
    me = mesh_from_arrays(name, v, f)
    ob = bpy.data.objects.new(name, me)
    col_parts.objects.link(ob)
    cleanup(ob)
    decimate(ob, target)
    ob.data.shade_smooth()
    ob.data.materials.append(mat_for(rgb))
    be, bv, vol = check_manifold(ob)
    dims = ob.dimensions
    report.append((name, len(ob.data.polygons), be, bv, vol, tuple(dims), qty))
    print(f"{name:14s} tris={len(ob.data.polygons):7d} nonmanifold_edges={be} verts={bv} "
          f"vol={vol / 1000:7.2f}cm3 size={dims.x:.1f}x{dims.y:.1f}x{dims.z:.1f}mm", flush=True)
    objs[key] = ob

# ---------------------------------------------------------------------------
# STL export - one file per part, in assembled coordinates (mm)
# ---------------------------------------------------------------------------
for key, ob in objs.items():
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    path = os.path.join(STL_DIR, STL_NAME[key])
    bpy.ops.wm.stl_export(filepath=path, export_selected_objects=True, ascii_format=False,
                          apply_modifiers=True, global_scale=1.0)
    ob.select_set(False)

# pin instances at their assembled positions (hidden inside the arms)
pin_pos = data["pin_positions"]
pin_obj = objs["pin"]
pin_obj.location = (0, 0, 0)
pin_instances = []
for i, row in enumerate(pin_pos):
    p0, p1 = Vector(row[:3]), Vector(row[3:])
    d = (p1 - p0).normalized()
    inst = bpy.data.objects.new(f"Pin_{i + 1}", pin_obj.data)
    inst.matrix_world = Matrix.Translation((p0 + p1) / 2) @ d.to_track_quat("Z", "Y").to_matrix().to_4x4()
    col_pins.objects.link(inst)
    pin_instances.append(inst)
# the master pin stays at the origin for export only
col_parts.objects.unlink(pin_obj)
master = bpy.data.collections.new("Pin_Master_For_Export")
scene.collection.children.link(master)
master.objects.link(pin_obj)
master.hide_render = True
master.hide_viewport = True

with open(os.path.join(OUT_DIR, "parts_report.txt"), "w") as fh:
    fh.write("part            triangles  non-manifold-edges  volume_cm3  size_mm (X x Y x Z)  qty\n")
    for name, n, be, bv, vol, dims, qty in report:
        fh.write(f"{name:15s} {n:9d} {be:19d} {vol / 1000:11.2f}  "
                 f"{dims[0]:6.1f} x {dims[1]:6.1f} x {dims[2]:6.1f}  {qty}\n")

# ---------------------------------------------------------------------------
# studio: backdrop, lights, camera
# ---------------------------------------------------------------------------
world = bpy.data.worlds.new("Studio")
scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes["Background"]
bg.inputs["Color"].default_value = (0.30, 0.30, 0.31, 1)
bg.inputs["Strength"].default_value = 0.55

studio = bpy.data.collections.new("Studio")
scene.collection.children.link(studio)

# curved infinity backdrop
bm = bmesh.new()
W = 1400
prof = [(0, -900, -18)]
for i in range(19):
    th = math.radians(90 * i / 18)
    prof.append((0, 80 + 220 * math.sin(th), 202 - 220 * math.cos(th)))
prof.append((0, 300, 900))
verts_l = [bm.verts.new((-W, y, z)) for _, y, z in prof]
verts_r = [bm.verts.new((W, y, z)) for _, y, z in prof]
for i in range(len(prof) - 1):
    bm.faces.new((verts_l[i], verts_r[i], verts_r[i + 1], verts_l[i + 1]))
bd_me = bpy.data.meshes.new("Backdrop")
bm.to_mesh(bd_me)
bm.free()
bd_me.shade_smooth()
backdrop = bpy.data.objects.new("Backdrop", bd_me)
studio.objects.link(backdrop)
bd_mat = make_material("Backdrop_Grey", (0.36, 0.36, 0.37), 0.8, 0.0)
bd_me.materials.append(bd_mat)


def area_light(name, loc, target, power, size, color=(1, 1, 1)):
    ld = bpy.data.lights.new(name, "AREA")
    ld.energy = power
    ld.size = size
    ld.color = color
    lo = bpy.data.objects.new(name, ld)
    lo.location = loc
    d = Vector(target) - Vector(loc)
    lo.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    studio.objects.link(lo)
    return lo


area_light("Key", (-260, -320, 360), (0, 0, 80), 2.6e6, 260)
area_light("Fill", (320, -260, 160), (0, 0, 80), 1.1e6, 300, (0.95, 0.97, 1.0))
area_light("Rim", (60, 300, 380), (0, 0, 90), 1.4e6, 200)
area_light("Top", (0, -40, 520), (0, 0, 80), 0.8e6, 300)

cam_d = bpy.data.cameras.new("Camera")
cam_d.lens = 85
cam_d.clip_start = 1
cam_d.clip_end = 20000
cam = bpy.data.objects.new("Camera", cam_d)
studio.objects.link(cam)
scene.camera = cam


def aim(obj, loc, target):
    obj.location = loc
    obj.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()


aim(cam, (0, -760, 175), (0, 0, 76))

scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = int(os.environ.get("SAMPLES", "96"))
scene.cycles.use_denoising = True
scene.cycles.max_bounces = 6
scene.render.resolution_x = 1200
scene.render.resolution_y = 1300
scene.render.film_transparent = False
scene.view_settings.view_transform = "Standard"
scene.view_settings.look = "None"
scene.view_settings.exposure = -0.35

blend_path = os.path.join(OUT_DIR, "IgG_Antibody.blend")
bpy.ops.wm.save_as_mainfile(filepath=blend_path, compress=True)
print("saved", blend_path, flush=True)

if not DO_RENDER:
    sys.exit(0)


def render(path):
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print("rendered", path, flush=True)


render(os.path.join(IMG_DIR, "01_front.png"))
aim(cam, (-470, -590, 250), (0, 0, 78))
render(os.path.join(IMG_DIR, "02_three_quarter.png"))

# exploded view -------------------------------------------------------------
a = math.sqrt(0.5)
UL, VL = Vector((-a, 0, a)), Vector((-a, 0, -a))
UR, VR = Vector((a, 0, a)), Vector((a, 0, -a))
off = {
    "base": Vector((0, 0, -30)),
    "plaque": Vector((0, -34, -30)),
    "fc_left": Vector((-16, 0, 0)),
    "fc_right": Vector((16, 0, 0)),
    "fc_bond_1": Vector((0, -14, 0)), "fc_bond_2": Vector((0, -14, 0)), "fc_bond_3": Vector((0, -14, 0)),
    "hinge": Vector((0, 0, 26)),
    "fab_heavy_L": Vector((-26, 0, 30)), "fab_heavy_R": Vector((26, 0, 30)),
}
off["light_L"] = off["fab_heavy_L"] + VL * 26
off["light_R"] = off["fab_heavy_R"] + VR * 26
off["vdomain_L"] = off["light_L"] + UL * 28 - VL * 12
off["vdomain_R"] = off["light_R"] + UR * 28 - VR * 12
for key, o in off.items():
    objs[key].location = o
for i, inst in enumerate(pin_instances):
    side = "L" if i < 4 else "R"
    kind = i % 4
    if kind < 2:
        o = (off[f"fab_heavy_{side}"] + off[f"light_{side}"]) / 2
    else:
        o = (off[f"light_{side}"] + off[f"vdomain_{side}"]) / 2
    inst.location = inst.location + o
scene.render.resolution_x = 1400
scene.render.resolution_y = 1400
backdrop.location.z = -40
aim(cam, (-520, -930, 330), (0, 0, 58))
render(os.path.join(IMG_DIR, "03_exploded.png"))
