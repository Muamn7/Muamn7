"""Turn the generated part meshes into a Blender scene, STL files and renders.

Run with Blender's Python (the `bpy` module, or `blender -b -P build_blend.py -- ...`):
    python build_blend.py PARTS.npz OUT_DIR [--render | --quick]
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
QUICK = "--quick" in sys.argv
STL_DIR = os.path.join(OUT_DIR, "stl")
IMG_DIR = os.path.join(OUT_DIR, "renders")
os.makedirs(IMG_DIR, exist_ok=True)
if not QUICK:
    os.makedirs(STL_DIR, exist_ok=True)

data = np.load(NPZ)


def srgb(hexstr):
    c = [int(hexstr[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return tuple(round(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4, 4) for x in c)


# colours sampled from the reference picture
BLUE = srgb("#1E88E5")
CYAN = srgb("#45B8F0")
PINK = srgb("#F06C92")
PURPLE = srgb("#8730D6")
YELLOW = srgb("#F7D21C")
BLACK = srgb("#141416")
WHITE = srgb("#E8E8E8")
PIN_GREY = srgb("#9A9A9A")

# key -> (object name, colour, target triangles, quantity, stl file, show in scene)
PARTS = {
    "base":            ("Base",            BLACK, 90000, 1, "01_base_black.stl", True),
    "plaque":          ("Plaque_Blank",    WHITE, 6000, 1, "02_plaque_white_optional.stl", True),
    "fc_left":         ("Fc_Left",         BLUE, 170000, 1, "03_fc_left_blue.stl", True),
    "fc_right":        ("Fc_Right",        BLUE, 170000, 1, "04_fc_right_blue.stl", True),
    "fc_bond_1":       ("Fc_Bond_1",       YELLOW, 6000, 1, "05_fc_bond_1_bottom_yellow.stl", True),
    "fc_bond_2":       ("Fc_Bond_2",       YELLOW, 6000, 1, "06_fc_bond_2_middle_yellow.stl", True),
    "fc_bond_3":       ("Fc_Bond_3",       YELLOW, 6000, 1, "07_fc_bond_3_top_yellow.stl", True),
    "hinge_yellow":    ("Hinge_Yellow",    YELLOW, 70000, 1, "08a_hinge_part_yellow.stl", True),
    "hinge_cyan":      ("Hinge_Cyan",      CYAN, 50000, 1, "08b_hinge_part_cyan.stl", True),
    "hinge_one_piece": ("Hinge_OnePiece",  YELLOW, 100000, 1, "08_hinge_one_piece.stl", False),
    "fab_heavy_L":     ("Fab_Heavy_L",     BLUE, 190000, 1, "09_fab_heavy_left_blue.stl", True),
    "fab_heavy_R":     ("Fab_Heavy_R",     BLUE, 190000, 1, "10_fab_heavy_right_blue.stl", True),
    "light_L":         ("Light_L",         PINK, 95000, 1, "11_light_chain_left_pink.stl", True),
    "light_R":         ("Light_R",         PINK, 95000, 1, "12_light_chain_right_pink.stl", True),
    "vdomain_L":       ("VDomain_L",       PURPLE, 105000, 1, "13_antigen_site_left_purple.stl", True),
    "vdomain_R":       ("VDomain_R",       PURPLE, 105000, 1, "14_antigen_site_right_purple.stl", True),
    "pin":             ("Pin_3x12",        BLUE, 3000, 0, "15_pin_3x12mm.stl", False),
}

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
col_extra = bpy.data.collections.new("Export_Only")
scene.collection.children.link(col_extra)


def make_material(name, rgb, rough=0.16, coat=0.7):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Coat Weight"].default_value = coat
    b.inputs["Coat Roughness"].default_value = 0.06
    if "Subsurface Weight" in b.inputs:
        b.inputs["Subsurface Weight"].default_value = 0.04
        b.inputs["Subsurface Radius"].default_value = (1.0, 1.0, 1.0)
        b.inputs["Subsurface Scale"].default_value = 0.6
    m.diffuse_color = (*rgb, 1.0)
    return m


MAT_NAMES = {BLUE: "Heavy_Chain_Blue", CYAN: "Hinge_Strand_Cyan", PINK: "Light_Chain_Pink",
             PURPLE: "Antigen_Site_Purple", YELLOW: "Disulfide_Yellow", BLACK: "Base_Black",
             WHITE: "Plaque_White", PIN_GREY: "Pin_Grey"}
MATS = {}


def mat_for(rgb):
    if rgb not in MATS:
        MATS[rgb] = make_material(MAT_NAMES[rgb], rgb, 0.28 if rgb in (BLACK, WHITE) else 0.16,
                                  0.4 if rgb in (BLACK, WHITE) else 0.7)
    return MATS[rgb]


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
for key, (name, rgb, target, qty, stl, show) in PARTS.items():
    v, f = data[key + "__v"], data[key + "__f"]
    ob = bpy.data.objects.new(name, mesh_from_arrays(name, v, f))
    (col_parts if show else col_extra).objects.link(ob)
    cleanup(ob)
    decimate(ob, target if not QUICK else target // 3)
    ob.data.shade_smooth()
    ob.data.materials.append(mat_for(rgb))
    be, bv, vol = check_manifold(ob)
    dims = ob.dimensions
    report.append((name, stl, len(ob.data.polygons), be, vol, tuple(dims), qty))
    print(f"{name:16s} tris={len(ob.data.polygons):7d} nonmanifold_edges={be} verts={bv} "
          f"vol={vol / 1000:7.2f}cm3 size={dims.x:.1f}x{dims.y:.1f}x{dims.z:.1f}mm", flush=True)
    objs[key] = ob

# ---------------------------------------------------------------------------
# STL export - one file per part, in assembled coordinates (mm)
# ---------------------------------------------------------------------------
n_pins = len(data["pin_positions"])
if not QUICK:
    for key, ob in objs.items():
        bpy.ops.object.select_all(action="DESELECT")
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        fname = PARTS[key][4]
        if key == "pin":
            fname = fname.replace(".stl", f"_print_x{n_pins}.stl")
        bpy.ops.wm.stl_export(filepath=os.path.join(STL_DIR, fname), export_selected_objects=True,
                              ascii_format=False, apply_modifiers=True, global_scale=1.0)
        ob.select_set(False)
    with open(os.path.join(OUT_DIR, "parts_report.txt"), "w") as fh:
        fh.write("part              triangles  non-manifold-edges  volume_cm3  size_mm (X x Y x Z)   file\n")
        for name, stl, n, be, vol, dims, qty in report:
            fh.write(f"{name:17s} {n:9d} {be:19d} {vol / 1000:11.2f}  "
                     f"{dims[0]:6.1f} x {dims[1]:6.1f} x {dims[2]:6.1f}   {stl}\n")
        fh.write(f"\nPins needed: {n_pins}\n")
col_extra.hide_render = True
col_extra.hide_viewport = True

# pin instances at their assembled positions (hidden inside the arms)
pin_instances = []
for i, row in enumerate(data["pin_positions"]):
    p0, p1 = Vector(row[0:3]), Vector(row[3:6])
    d = (p1 - p0).normalized()
    inst = bpy.data.objects.new(f"Pin_{i + 1}", objs["pin"].data)
    inst.matrix_world = Matrix.Translation((p0 + p1) / 2) @ d.to_track_quat("Z", "Y").to_matrix().to_4x4()
    col_pins.objects.link(inst)
    pin_instances.append((inst, int(row[6]), "L" if row[7] < 0.5 else "R"))

# ---------------------------------------------------------------------------
# studio like the reference photo: mid-grey sweep, soft key, glossy highlights
# ---------------------------------------------------------------------------
world = bpy.data.worlds.new("Studio")
scene.world = world
world.use_nodes = True
bgn = world.node_tree.nodes["Background"]
bgn.inputs["Color"].default_value = (*srgb("#8A8B8D"), 1)
bgn.inputs["Strength"].default_value = 0.35

studio = bpy.data.collections.new("Studio")
scene.collection.children.link(studio)

bm = bmesh.new()
prof = [(-900, -22.0)]
for i in range(19):
    th = math.radians(90 * i / 18)
    prof.append((140 + 260 * math.sin(th), -22.0 + 260 - 260 * math.cos(th)))
prof.append((400, 1200))
Wd = 1600
vl = [bm.verts.new((-Wd, y, z)) for y, z in prof]
vr = [bm.verts.new((Wd, y, z)) for y, z in prof]
for i in range(len(prof) - 1):
    bm.faces.new((vl[i], vr[i], vr[i + 1], vl[i + 1]))
bd_me = bpy.data.meshes.new("Backdrop")
bm.to_mesh(bd_me)
bm.free()
bd_me.shade_smooth()
backdrop = bpy.data.objects.new("Backdrop", bd_me)
studio.objects.link(backdrop)
bd_me.materials.append(make_material("Backdrop_Grey", srgb("#7C7D80"), 0.9, 0.0))


def area_light(name, loc, target, power, size, color=(1, 1, 1)):
    ld = bpy.data.lights.new(name, "AREA")
    ld.energy = power
    ld.size = size
    ld.color = color
    lo = bpy.data.objects.new(name, ld)
    lo.location = loc
    lo.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    studio.objects.link(lo)


area_light("Key", (-300, -380, 420), (0, 0, 90), 3.2e6, 220)
area_light("Fill", (380, -320, 200), (0, 0, 80), 1.3e6, 320, (0.96, 0.98, 1.0))
area_light("Rim", (120, 320, 420), (0, 0, 100), 1.6e6, 180)
area_light("Top", (0, -60, 600), (0, 0, 90), 1.0e6, 260)

cam_d = bpy.data.cameras.new("Camera")
cam_d.lens = 70
cam_d.sensor_fit = "AUTO"
cam_d.clip_start = 1
cam_d.clip_end = 20000
cam = bpy.data.objects.new("Camera", cam_d)
studio.objects.link(cam)
scene.camera = cam


def aim(loc, target):
    cam.location = loc
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()


# same viewpoint as the reference photo: ~9 degrees above, centred on the model
D_CAM, ELEV, TGT = 500.0, math.radians(9.0), (0, 0, 84.0)
aim((0, -D_CAM * math.cos(ELEV), TGT[2] + D_CAM * math.sin(ELEV)), TGT)

scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = int(os.environ.get("SAMPLES", "96"))
scene.cycles.use_denoising = True
scene.cycles.max_bounces = 6
scene.render.resolution_x = 1292 if not QUICK else 646
scene.render.resolution_y = 1236 if not QUICK else 618
scene.view_settings.view_transform = "Standard"
scene.view_settings.look = "None"
scene.view_settings.exposure = -0.2

if not QUICK:
    blend_path = os.path.join(OUT_DIR, "IgG_Antibody.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend_path, compress=True)
    print("saved", blend_path, flush=True)

if not (DO_RENDER or QUICK):
    sys.exit(0)


def render(path):
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print("rendered", path, flush=True)


render(os.path.join(IMG_DIR, "01_front.png"))
if QUICK:
    sys.exit(0)
aim((-330, -420, 190), (0, 0, 84))
render(os.path.join(IMG_DIR, "02_three_quarter.png"))

# exploded view -------------------------------------------------------------
a = math.sqrt(0.5)
UL, VL = Vector((-a, 0, a)), Vector((-a, 0, -a))
UR, VR = Vector((a, 0, a)), Vector((a, 0, -a))
off = {
    "base": Vector((0, 0, -26)),
    "plaque": Vector((0, -28, -26)),
    "fc_left": Vector((-14, 0, 0)),
    "fc_right": Vector((14, 0, 0)),
    "fc_bond_1": Vector((0, -16, 0)), "fc_bond_2": Vector((0, -16, 0)), "fc_bond_3": Vector((0, -16, 0)),
    "hinge_yellow": Vector((0, 0, 22)), "hinge_cyan": Vector((0, 0, 22)),
    "fab_heavy_L": Vector((-20, 0, 44)), "fab_heavy_R": Vector((20, 0, 44)),
}
off["light_L"] = off["fab_heavy_L"] + VL * 24
off["light_R"] = off["fab_heavy_R"] + VR * 24
off["vdomain_L"] = off["light_L"] + UL * 26 - VL * 10
off["vdomain_R"] = off["light_R"] + UR * 26 - VR * 10
for key, o in off.items():
    objs[key].location = o
for inst, kind, side in pin_instances:
    if kind == 0:
        o = (off[f"fab_heavy_{side}"] + off[f"light_{side}"]) / 2
    else:
        o = (off[f"light_{side}"] + off[f"vdomain_{side}"]) / 2
    inst.location = inst.location + o
backdrop.location.z = -40
scene.render.resolution_x = 1400
scene.render.resolution_y = 1400
aim((-380, -700, 300), (0, 0, 72))
render(os.path.join(IMG_DIR, "03_exploded.png"))
