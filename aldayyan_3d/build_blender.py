"""Build the 3D coin in Blender: black disc 60mm x 2mm + red relief 1mm on top.
Run:  blender -b -P build_blender.py   (or python3 with the bpy module)
"""
import bpy, bmesh, json, math, os, sys
import numpy as np, trimesh
from shapely.geometry import Polygon

HERE = os.path.dirname(os.path.abspath(__file__))
DISC_D, BASE_H, RELIEF_H = 60.0, 2.0, 1.0   # mm

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.unit_settings.system = 'METRIC'
sc.unit_settings.scale_length = 0.001
sc.unit_settings.length_unit = 'MILLIMETERS'

def mat(name, rgb, metal, rough):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    return m

def obj_from_trimesh(name, tm, material):
    me = bpy.data.meshes.new(name)
    me.from_pydata(tm.vertices.tolist(), [], tm.faces.tolist())
    me.update()
    bm = bmesh.new(); bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(1), verts=bm.verts, edges=bm.edges)
    bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); sc.collection.objects.link(ob)
    me.materials.append(material)
    return ob

black = mat("Black_Base", (0.01, 0.01, 0.01), 0.0, 0.35)
red = mat("Red_Logo", (0.8, 0.0, 0.0), 0.3, 0.25)

# Black base
bpy.ops.mesh.primitive_cylinder_add(vertices=256, radius=DISC_D / 2, depth=BASE_H, location=(0, 0, BASE_H / 2))
base = bpy.context.object; base.name = "Base_Black_2mm"; base.data.materials.append(black)

# Red relief
parts = []
for p in json.load(open(os.path.join(HERE, "logo_polys_mm.json"))):
    poly = Polygon(p["ext"], p["holes"])
    parts.append(trimesh.creation.extrude_polygon(poly, RELIEF_H))
relief_tm = trimesh.util.concatenate(parts)
relief_tm.apply_translation((0, 0, BASE_H))
relief = obj_from_trimesh("Logo_Red_1mm", relief_tm, red)
for ob in (base, relief):
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.shade_flat()

# Camera + lights for a quick render
bpy.ops.object.camera_add(location=(0, -55, 95), rotation=(math.radians(30), 0, 0))
sc.camera = bpy.context.object; sc.camera.data.lens = 70
bpy.ops.object.light_add(type='AREA', location=(-40, -40, 80)); bpy.context.object.data.energy = 1.2e5; bpy.context.object.data.size = 60
bpy.ops.object.light_add(type='AREA', location=(50, 30, 60)); bpy.context.object.data.energy = 4e4; bpy.context.object.data.size = 40
w = bpy.data.worlds.new("W"); sc.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.03, 0.03, 0.035, 1)

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HERE, "aldayyan_coin.blend"))

# Exports: separate STLs for 2-colour printing + combined GLB with colours
def export_stl(ob, path):
    bpy.ops.object.select_all(action='DESELECT'); ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.wm.stl_export(filepath=path, export_selected_objects=True, global_scale=1.0, apply_modifiers=True)
export_stl(base, os.path.join(HERE, "base_black_60x2mm.stl"))
export_stl(relief, os.path.join(HERE, "logo_red_1mm.stl"))
bpy.ops.object.select_all(action='DESELECT'); base.select_set(True); relief.select_set(True)
bpy.ops.wm.stl_export(filepath=os.path.join(HERE, "aldayyan_coin_full.stl"), export_selected_objects=True)
bpy.ops.export_scene.gltf(filepath=os.path.join(HERE, "aldayyan_coin.glb"), use_selection=True, export_yup=True)

if "--render" in sys.argv:
    sc.render.engine = 'CYCLES'; sc.cycles.samples = 64; sc.cycles.device = 'CPU'
    sc.render.resolution_x = sc.render.resolution_y = 1200
    sc.render.filepath = os.path.join(HERE, "preview_render.png")
    bpy.ops.render.render(write_still=True)
print("DONE", base.dimensions[:], relief.dimensions[:])
