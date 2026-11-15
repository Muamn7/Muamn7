"""Render the print plates and an exploded assembly view of the kit.

    blender -b -P render_kit.py -- kit assembled out_dir
"""
import bpy, os, sys, json, math
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
KIT, ASM, OUT = argv[0], argv[1], argv[2]
os.makedirs(OUT, exist_ok=True)
info = json.load(open(os.path.join(KIT, "parts.json")))
FIL = info["filaments"]
BED = info["bed_mm"]


def lin(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c) + (1,)


MATS = {}


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    MATS.clear()
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples = 48
    sc.cycles.use_denoising = True
    sc.view_settings.view_transform = "Standard"
    w = bpy.data.worlds.new("w")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = lin("#E9E8E4")
    w.node_tree.nodes["Background"].inputs[1].default_value = 0.8
    ld = bpy.data.lights.new("sun", "SUN")
    ld.energy = 3.0
    ld.angle = 0.25
    lo = bpy.data.objects.new("sun", ld)
    sc.collection.objects.link(lo)
    lo.rotation_euler = (math.radians(40), math.radians(15), math.radians(-30))
    return sc


def mat(fil):
    if fil not in MATS:
        m = bpy.data.materials.new(fil)
        m.use_nodes = True
        b = m.node_tree.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = lin(FIL.get(fil, "#888888"))
        b.inputs["Roughness"].default_value = 0.45
        MATS[fil] = m
    return MATS[fil]


def load(path):
    bpy.ops.wm.stl_import(filepath=path)
    ob = bpy.context.selected_objects[0]
    fil = os.path.basename(path)[:-4].split("__")[-1]
    ob.data.materials.append(mat(fil))
    for p in ob.data.polygons:
        p.use_smooth = False
    return ob


def camera(sc, loc, target, lens=40, ortho=None):
    cd = bpy.data.cameras.new("cam")
    cd.lens = lens
    cd.clip_end = 10000
    if ortho:
        cd.type = "ORTHO"
        cd.ortho_scale = ortho
    cam = bpy.data.objects.new("cam", cd)
    sc.collection.objects.link(cam)
    cam.location = loc
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    sc.camera = cam


def label(sc, txt, loc, size=7):
    cu = bpy.data.curves.new("t", "FONT")
    cu.body = txt
    cu.size = size
    cu.align_x = "CENTER"
    cu.extrude = 0.8
    cu.offset = 0.35
    ob = bpy.data.objects.new("t", cu)
    sc.collection.objects.link(ob)
    ob.location = loc
    ob.data.materials.append(mat("Label"))
    MATS["Label"].node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.02, 0.02, 0.02, 1)
    c = ob.constraints.new("TRACK_TO")
    c.target = sc.camera
    c.track_axis = "TRACK_Z"
    c.up_axis = "UP_Y"
    return ob


# ------------------------------------------------------------- plates
plates = sorted(d for d in os.listdir(KIT) if d.startswith("plate_"))
for d in plates:
    sc = reset()
    bpy.ops.mesh.primitive_plane_add(size=1)
    bed = bpy.context.active_object
    bed.scale = (BED[0], BED[1], 1)
    bed.location = (BED[0] / 2, BED[1] / 2, -0.01)
    m = bpy.data.materials.new("bed")
    m.use_nodes = True
    m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = lin("#2B2B2E")
    bed.data.materials.append(m)
    for f in sorted(os.listdir(os.path.join(KIT, d))):
        load(os.path.join(KIT, d, f))
    camera(sc, (BED[0] / 2, -BED[1] * 0.28, BED[1] * 1.45), (BED[0] / 2, BED[1] * 0.46, 0), 35)
    sc.render.resolution_x, sc.render.resolution_y = 1400, 1200
    sc.render.filepath = os.path.join(OUT, d + ".png")
    bpy.ops.render.render(write_still=True)

# ------------------------------------------------------------- exploded view
EXPLODE = {
    "BASE_L": (-25, 0, -70), "BASE_R": (25, 0, -70), "BASE": (0, 0, -70),
    "DOWEL": (0, 0, -70), "PLAQUE_CL": (0, -70, -70), "PLAQUE_INHIBITION": (0, -70, -70),
    "ARROW_RIGHT": (0, -70, -70), "TITLE_STAND": (0, 70, 10),
    "MEMBRANE_L": (-70, 25, 0), "MEMBRANE_R": (70, 25, 0), "CHANNEL": (0, -15, -5),
    "ALPHA_BACK_L": (-30, -45, 0), "ALPHA_BACK_R": (30, -45, 0),
    "ALPHA_L": (-35, -95, 0), "ALPHA_R": (35, -95, 0),
    "GAMMA": (0, -45, 45), "BETA_L": (-25, -70, 35), "BETA_R": (25, -70, 35),
    "EXIT_ION": (0, -120, -30), "GABA_BALL": (-35, -150, 15),
    "DIAZEPAM_BALL": (35, -150, 15), "TITLE": (0, 50, 75),
    "STRUT_GABA": (-55, -40, 45), "STRUT_DIAZEPAM": (55, -40, 45),
    "CALLOUT_GABA": (-90, -70, 55), "CALLOUT_DIAZEPAM": (90, -70, 55),
    "ARROW_GABA": (-70, -125, 45), "ARROW_DIAZEPAM": (70, -125, 45),
}
NUM = {p["id"]: p["no"] for p in info["parts"]}
sc = reset()
camera(sc, (380, -900, 520), (0, -60, 90), 50)
seen = set()
for f in sorted(os.listdir(ASM)):
    pid = f.split("__")[0]
    off = EXPLODE.get(pid, EXPLODE.get(pid.split("_")[0], (0, 0, 0)))
    ob = load(os.path.join(ASM, f))
    ob.location = off
    if pid not in seen:
        seen.add(pid)
        bpy.context.view_layer.update()
        bb = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
        top = Vector((sum(v.x for v in bb) / 8, min(v.y for v in bb), max(v.z for v in bb) + 6))
        if not pid.startswith("DOWEL") or pid.endswith("1"):
            label(sc, str(NUM.get(pid, "")) if not pid.startswith("DOWEL") else "2-4", top, 16)
sc.render.resolution_x, sc.render.resolution_y = 1800, 1350
sc.render.filepath = os.path.join(OUT, "exploded_assembly.png")
bpy.ops.render.render(write_still=True)
