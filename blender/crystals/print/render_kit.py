# -*- coding: utf-8 -*-
"""صور معاينة لطقم الطباعة: المجسم مركّباً، منظر مفكّك، وصفّ القطع على السرير.
blender -b Crystal_Print_Kit.blend -P render_kit.py -- --out . [--samples 64]
"""
import bpy
import math
import os
import sys
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = os.path.abspath(argv[argv.index("--out") + 1]) if "--out" in argv else os.getcwd()
SAMPLES = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 64
os.makedirs(OUT, exist_ok=True)

sc = bpy.context.scene
sc.render.engine = 'CYCLES'
sc.cycles.samples = SAMPLES
sc.cycles.use_denoising = True
sc.cycles.transmission_bounces = 12
sc.cycles.max_bounces = 12
sc.view_settings.view_transform = 'AgX'
try:
    sc.view_settings.look = 'AgX - Medium High Contrast'
except TypeError:
    pass

studio = bpy.data.collections.new("Render_Studio")
sc.collection.children.link(studio)

# أرضية
me = bpy.data.meshes.new("Floor")
me.from_pydata([(-3000, -3000, -1.2), (3000, -3000, -1.2), (3000, 3000, -1.2), (-3000, 3000, -1.2)], [], [(0, 1, 2, 3)])
m = bpy.data.materials.new("Floor_Mat")
m.use_nodes = True
b = m.node_tree.nodes["Principled BSDF"]
b.inputs["Base Color"].default_value = (0.78, 0.78, 0.8, 1)
b.inputs["Roughness"].default_value = 0.8
me.materials.append(m)
floor = bpy.data.objects.new("Floor", me)
studio.objects.link(floor)

w = bpy.data.worlds.new("W")
w.use_nodes = True
w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.85, 0.87, 0.9, 1)
w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.55
sc.world = w

for name, rot, strength, ang in (("Sun_Key", (50, 0, -35), 3.2, 8), ("Sun_Fill", (65, 0, 140), 0.9, 25)):
    ld = bpy.data.lights.new(name, 'SUN')
    ld.energy = strength
    ld.angle = math.radians(ang)
    ob = bpy.data.objects.new(name, ld)
    ob.rotation_euler = [math.radians(v) for v in rot]
    studio.objects.link(ob)


def text(body, loc, size=9.0, rot_x=0.0):
    cu = bpy.data.curves.new("T", 'FONT')
    cu.body = body
    cu.size = size
    cu.align_x = 'CENTER'
    cu.extrude = 0.3
    ob = bpy.data.objects.new("Label", cu)
    ob.location = loc
    ob.rotation_euler = (rot_x, 0, 0)
    mt = bpy.data.materials.new("Label_Mat")
    mt.diffuse_color = (0.05, 0.05, 0.05, 1)
    mt.use_nodes = True
    mt.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.03, 0.03, 0.04, 1)
    cu.materials.append(mt)
    studio.objects.link(ob)
    return ob


def cam(name, loc, target, lens):
    cd = bpy.data.cameras.new(name)
    cd.lens = lens
    cd.clip_start = 1
    cd.clip_end = 10000
    ob = bpy.data.objects.new(name, cd)
    ob.location = loc
    d = Vector(target) - Vector(loc)
    ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    studio.objects.link(ob)
    return ob


# ---------------------------------------- المنظر المفكك (نسخ من المركّب)
asm = [c for c in bpy.data.collections if c.name.endswith("_Assembled")]
expl = bpy.data.collections.new("Exploded")
sc.collection.children.link(expl)
centers = {"BCC": Vector((-130, 0, 75)), "HCP": Vector((130, 0, 75))}
for c in asm:
    label = c.name.split("_")[0]
    cen = centers[label]
    for ob in c.objects:
        dup = ob.copy()
        expl.objects.link(dup)
        if "_Atom_" in ob.name:
            p = ob.location.copy()
            off = (p - cen) * 0.35 + Vector((0, 0, 7 if ob.name.endswith("Upper") else -7))
        else:
            mw = ob.matrix_world
            mid = sum((mw @ Vector(v) for v in ob.bound_box), Vector()) / 8
            off = (mid - cen) * 0.35
        dup.matrix_world = ob.matrix_world.copy()
        dup.matrix_world.translation += off
        dup.location.z += 22   # يرفع المنظر المفكك عن الأرض

plates = [c for c in bpy.data.collections if "_Plate" in c.name and c.name != "Print_Plates"]
plate_labels = {
    "BCC_Plate1_Atoms_Black": "BCC  plate 1\natoms x18  (black)",
    "BCC_Plate2_Rods_Clear": "BCC  plate 2\nrods x20  (clear)",
    "HCP_Plate1_Atoms_Silver": "HCP  plate 1\natoms x34  (silver)",
    "HCP_Plate2_Rods_Grey": "HCP  plate 2\nrods x28  (grey)",
    "HCP_Plate3_Rods_Yellow": "HCP  plate 3\nrods x12  (yellow)",
}
labels = []
for c in plates:
    bed = [o for o in c.objects if o.get("bed")][0]
    o = bed.location
    labels.append(text(plate_labels.get(c.name, c.name), (o.x + 100, o.y + 232, 0), size=13))


def show(colls_visible):
    for c in bpy.data.collections:
        if c is studio:
            continue
        vis = any(c.name == v or c.name.startswith(v) for v in colls_visible)
        for ob in c.objects:
            ob.hide_render = not vis
    for l in labels:
        l.hide_render = "Print_Plates" not in colls_visible


def shot(fname, camera, rx, ry):
    sc.camera = camera
    sc.render.resolution_x, sc.render.resolution_y = rx, ry
    sc.render.filepath = os.path.join(OUT, fname)
    bpy.ops.render.render(write_still=True)


# Print_Plates مجموعة أم؛ القطع داخل مجموعات فرعية
def show_plates():
    for c in bpy.data.collections:
        if c is studio:
            continue
        vis = "_Plate" in c.name
        for ob in c.objects:
            ob.hide_render = not vis
    for l in labels:
        l.hide_render = False


show(["BCC_Assembled", "HCP_Assembled"])
shot("preview_assembled.png", cam("Cam_Asm", (0, -720, 300), (0, 0, 70), 50), 1800, 1100)

show(["Exploded"])
shot("preview_exploded.png", cam("Cam_Exp", (0, -860, 380), (0, 0, 95), 50), 1800, 1100)

show_plates()
shot("preview_plates.png", cam("Cam_Plates", (100, -1300, 1050), (100, -400, 0), 50), 2000, 1000)


def show_catalog():
    for c in bpy.data.collections:
        if c is studio:
            continue
        for ob in c.objects:
            ob.hide_render = c.name != "Parts_Catalog"
    for l in labels:
        l.hide_render = True


show_catalog()
shot("preview_parts.png", cam("Cam_Parts", (125, 490, 720), (125, 612, 0), 50), 1600, 1400)
