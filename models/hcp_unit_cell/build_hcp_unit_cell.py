"""
HCP (Hexagonal Close-Packed) unit cell - Blender model builder.

Builds the classic "cut-away" HCP unit cell: every atom (sphere) is trimmed
exactly by the hexagonal prism, like the SolidWorks reference image.

  * Total height (c)          : 20.0 cm  (exact)
  * Ideal ratio c/a           : sqrt(8/3) = 1.63299
  * Hexagon edge (a)          : c / 1.63299  = 12.247 cm
  * Atom radius (r = a/2)     : 6.124 cm  (atoms touch each other)
  * 12 corner atoms (1/6 each) + 2 face atoms (1/2 each) + 3 middle atoms

Run inside Blender:   Scripting tab -> Open -> Run Script
or from a terminal:   blender -b -P build_hcp_unit_cell.py
"""
import math
import os
import sys
import bpy
from mathutils import Euler, Vector

# --------------------------------------------------------------------------
# Parameters
# --------------------------------------------------------------------------
HEIGHT = 0.20                       # metres  (20 cm)
C_OVER_A = math.sqrt(8.0 / 3.0)     # ideal HCP ratio
A = HEIGHT / C_OVER_A               # hexagon edge = circumradius
R = A / 2.0                         # atom radius (touching spheres)
SEGMENTS, RINGS = 192, 96           # sphere resolution (high quality)
# small odd rotation so sphere edge-loops never coincide with prism faces
# (keeps the exact boolean clean and the cut circles perfectly round)
SPHERE_ROT = Euler((0.1234, 0.4321, 0.2718))
# The reference image shows only the 17 atoms of the cell. In a real crystal,
# 3 atoms of the neighbouring cells also poke small caps through the 3 side
# faces that have no cut circle. Set True to add them (packing -> 0.7405).
INCLUDE_NEIGHBOR_CAPS = False

OUT_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in dir() else os.getcwd()

# --------------------------------------------------------------------------
# Scene reset + units (centimetres)
# --------------------------------------------------------------------------
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.unit_settings.system = 'METRIC'
scene.unit_settings.scale_length = 1.0
scene.unit_settings.length_unit = 'CENTIMETERS'

col = bpy.data.collections.new("HCP_Unit_Cell")
scene.collection.children.link(col)

# --------------------------------------------------------------------------
# Material (SolidWorks-like satin blue-grey)
# --------------------------------------------------------------------------
mat = bpy.data.materials.new("HCP_Atom")
mat.use_nodes = True
bsdf = mat.node_tree.nodes.get("Principled BSDF")
bsdf.inputs["Base Color"].default_value = (0.30, 0.33, 0.45, 1.0)
bsdf.inputs["Roughness"].default_value = 0.38
bsdf.inputs["Metallic"].default_value = 0.15
mat.diffuse_color = (0.30, 0.33, 0.45, 1.0)

# --------------------------------------------------------------------------
# Hexagonal prism (cutter)  - one vertex points to -Y (front)
# --------------------------------------------------------------------------
hex_angles = [math.radians(30 + 60 * k) for k in range(6)]
hex_xy = [(A * math.cos(t), A * math.sin(t)) for t in hex_angles]

def make_prism(name):
    verts = [(x, y, 0.0) for x, y in hex_xy] + [(x, y, HEIGHT) for x, y in hex_xy]
    faces = [tuple(range(5, -1, -1)), tuple(range(6, 12))]
    for i in range(6):
        j = (i + 1) % 6
        faces.append((i, j, j + 6, i + 6))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    ob = bpy.data.objects.new(name, me)
    scene.collection.objects.link(ob)
    return ob

cutter = make_prism("HCP_Prism_Cutter")

# --------------------------------------------------------------------------
# Atom positions
# --------------------------------------------------------------------------
atoms = []
for z, tag in ((0.0, "Bottom"), (HEIGHT, "Top")):
    for k, (x, y) in enumerate(hex_xy):
        atoms.append((f"Atom_{tag}_Corner_{k+1}", Vector((x, y, z))))
    atoms.append((f"Atom_{tag}_Center", Vector((0.0, 0.0, z))))

# middle (B) layer: above the centroids of alternate triangles
d = A / math.sqrt(3.0)
for k, deg in enumerate((60, 180, 300)):
    t = math.radians(deg)
    atoms.append((f"Atom_Middle_{k+1}", Vector((d * math.cos(t), d * math.sin(t), HEIGHT / 2))))
if INCLUDE_NEIGHBOR_CAPS:
    for k, deg in enumerate((0, 120, 240)):
        t = math.radians(deg)
        atoms.append((f"Atom_Neighbor_Cap_{k+1}",
                      Vector((2 * d * math.cos(t), 2 * d * math.sin(t), HEIGHT / 2))))

# --------------------------------------------------------------------------
# Build: sphere  ∩  prism   (exact boolean, applied)
# --------------------------------------------------------------------------
root = bpy.data.objects.new("HCP_Unit_Cell_20cm", None)
root.empty_display_type = 'PLAIN_AXES'
root.empty_display_size = 0.05
col.objects.link(root)

for name, loc in atoms:
    bpy.ops.mesh.primitive_uv_sphere_add(segments=SEGMENTS, ring_count=RINGS,
                                         radius=R, location=loc, rotation=SPHERE_ROT)
    ob = bpy.context.active_object
    ob.name = ob.data.name = name
    mod = ob.modifiers.new("Cut", 'BOOLEAN')
    mod.operation = 'INTERSECT'
    mod.solver = 'EXACT'
    mod.object = cutter
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.modifier_apply(modifier=mod.name)

    # smooth spheres, crisp flat cut faces
    for p in ob.data.polygons:
        p.use_smooth = True
    ob.data.set_sharp_from_angle(angle=math.radians(35))
    ob.data.materials.clear()
    ob.data.materials.append(mat)

    # move into collection + parent to root
    for c in ob.users_collection:
        c.objects.unlink(ob)
    col.objects.link(ob)
    ob.parent = root

bpy.data.objects.remove(cutter, do_unlink=True)

# --------------------------------------------------------------------------
# Camera, lights, world  (studio look like the reference)
# --------------------------------------------------------------------------
target = Vector((0, 0, HEIGHT / 2))
cam_data = bpy.data.cameras.new("Camera")
cam_data.lens = 60
cam = bpy.data.objects.new("Camera", cam_data)
scene.collection.objects.link(cam)
cam.location = Vector((0.30, -0.78, 0.36))
cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
scene.camera = cam

def add_light(name, kind, loc, energy, size=0.5):
    ld = bpy.data.lights.new(name, kind)
    ld.energy = energy
    if kind == 'AREA':
        ld.size = size
    lo = bpy.data.objects.new(name, ld)
    lo.location = loc
    lo.rotation_euler = (target - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    scene.collection.objects.link(lo)

add_light("Key",  'AREA', (0.6, -0.7, 0.9), 25, 0.8)
add_light("Fill", 'AREA', (-0.8, -0.4, 0.4), 8, 1.0)
add_light("Rim",  'AREA', (-0.2, 0.8, 0.7), 12, 0.6)

world = bpy.data.worlds.new("World")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.85, 0.87, 0.9, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 0.35
scene.world = world

# white floor catching soft shadow
bpy.ops.mesh.primitive_plane_add(size=4, location=(0, 0, -0.0001))
floor = bpy.context.active_object
floor.name = "Floor"
fmat = bpy.data.materials.new("Floor")
fmat.use_nodes = True
fmat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.95, 0.95, 0.96, 1)
fmat.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.9
floor.data.materials.append(fmat)
floor.hide_viewport = True   # visible only in renders

# Render settings
scene.render.engine = 'CYCLES'
scene.cycles.samples = 128
scene.cycles.use_denoising = True
scene.render.resolution_x = 1600
scene.render.resolution_y = 1200
scene.view_settings.view_transform = 'AgX'
scene.view_settings.look = 'AgX - Medium High Contrast'
scene.view_settings.exposure = -1.3

# --------------------------------------------------------------------------
# Report + save
# --------------------------------------------------------------------------
bpy.context.view_layer.update()
mins = Vector((1e9,) * 3); maxs = Vector((-1e9,) * 3)
tris = 0
for ob in col.objects:
    if ob.type != 'MESH':
        continue
    tris += sum(len(p.vertices) - 2 for p in ob.data.polygons)
    for v in ob.data.vertices:
        w = ob.matrix_world @ v.co
        mins = Vector(map(min, mins, w)); maxs = Vector(map(max, maxs, w))
size = maxs - mins
print(f"a = {A*100:.3f} cm, r = {R*100:.3f} cm, c = {HEIGHT*100:.3f} cm")
print(f"Bounding box: X {size.x*100:.3f} cm  Y {size.y*100:.3f} cm  Z {size.z*100:.3f} cm")
print(f"Atoms: {len(atoms)}   Triangles: {tris}")

if "--no-save" not in sys.argv:
    blend_path = os.path.join(OUT_DIR, "hcp_unit_cell_20cm.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend_path, compress=True)
    print("Saved", blend_path)

    # STL export (one joined, watertight-per-atom mesh, units = millimetres)
    stl_path = os.path.join(OUT_DIR, "hcp_unit_cell_20cm.stl")
    bpy.ops.object.select_all(action='DESELECT')
    for ob in col.objects:
        if ob.type == 'MESH':
            ob.select_set(True)
    bpy.ops.wm.stl_export(filepath=stl_path, export_selected_objects=True,
                          global_scale=1000.0, apply_modifiers=True)
    print("Saved", stl_path)
