"""
Studio + preview renders for hard_hat.blend.

    blender --background hard_hat_classic.blend --python render_previews.py -- OUT_DIR [SIZE] [SAMPLES] [VIEWS] [--save]

VIEWS is a comma list (default: all). --save writes the studio into the .blend.
"""

import math
import os
import sys

import bpy
from mathutils import Quaternion, Vector

LIGHT = float(os.environ.get("LIGHT", "1.25"))

VIEWS = {
    # name: (camera location (m), target (m), focal mm)
    "hero_3q":   ((0.493, -0.250, 0.304), (0.0, -0.020, 0.050), 50),
    "side":      ((1.30, 0.0, 0.06), (0.0, -0.015, 0.060), 105),
    "front":     ((0.0, -1.30, 0.20), (0.0, 0.0, 0.060), 105),
    "back":      ((0.0, 1.30, 0.22), (0.0, 0.0, 0.055), 105),
    "top":       ((0.0, -0.001, 1.40), (0.0, -0.015, 0.0), 105),
    "rear_3q":   ((-0.80, 0.80, 0.50), (0.0, 0.0, 0.050), 95),
    "underside": ((0.25, -0.30, -1.05), (0.0, -0.01, 0.040), 105),
    # same camera as the reference photo (fitted to its outline), with roll
    "photo_angle": ((-0.4642, -0.0998, 0.2744), (0.0144, -0.0171, 0.0012), 50.55, 6.74),
    "detail_band": ((-0.42, -0.22, 0.10), (-0.085, -0.035, 0.020), 85),
}


def look_at(cam, target):
    d = Vector(target) - cam.location
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()


def ensure_studio(scene):
    if "Studio" in bpy.data.collections:
        return bpy.data.collections["Studio"]
    coll = bpy.data.collections.new("Studio")
    scene.collection.children.link(coll)

    # World: white backdrop for camera rays, soft dim light for everything else
    world = bpy.data.worlds.new("Studio_World")
    scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    mix = nt.nodes.new("ShaderNodeMixShader")
    lp = nt.nodes.new("ShaderNodeLightPath")
    bg_cam = nt.nodes.new("ShaderNodeBackground")
    bg_cam.inputs["Color"].default_value = (1, 1, 1, 1)
    bg_cam.inputs["Strength"].default_value = 1.0
    bg_amb = nt.nodes.new("ShaderNodeBackground")
    bg_amb.inputs["Color"].default_value = (1, 1, 1, 1)
    bg_amb.inputs["Strength"].default_value = 0.05 * LIGHT
    nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs[0])
    nt.links.new(bg_amb.outputs[0], mix.inputs[1])
    nt.links.new(bg_cam.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs[0])

    def area(name, loc, size, power, target=(0, 0, 0.05)):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.shape = 'RECTANGLE'
        ld.size, ld.size_y = size
        ld.energy = power
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        look_at(ob, target)
        coll.objects.link(ob)
        return ob

    area("Key", (0.9, -0.9, 1.1), (0.8, 0.8), 18 * LIGHT)
    area("Fill", (-1.1, -0.5, 0.45), (1.2, 0.8), 4 * LIGHT)
    area("Rim", (-0.3, 1.2, 0.9), (1.0, 0.5), 10 * LIGHT)
    area("Top", (0.0, 0.0, 1.4), (1.2, 1.2), 6 * LIGHT)
    area("Bounce", (0.6, -0.2, -0.9), (1.0, 1.0), 2 * LIGHT, target=(0, 0, 0.0))

    # Floor that only catches shadows
    bpy.ops.mesh.primitive_plane_add(size=6)
    floor = bpy.context.active_object
    floor.name = "Floor_ShadowCatcher"
    for c in floor.users_collection:
        c.objects.unlink(floor)
    coll.objects.link(floor)
    hat = bpy.data.objects.get("HardHat")
    zmin = min((hat.matrix_world @ v.co).z for v in hat.data.vertices) if hat else -0.03
    floor.location.z = zmin
    floor.is_shadow_catcher = True
    floor["zmin"] = zmin

    cam_data = bpy.data.cameras.new("Camera")
    cam = bpy.data.objects.new("Camera", cam_data)
    coll.objects.link(cam)
    scene.camera = cam
    return coll


def setup_render(scene, size, samples):
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = samples
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.use_denoising = True
    try:
        scene.cycles.denoiser = 'OPENIMAGEDENOISE'
    except Exception:
        pass
    scene.cycles.max_bounces = 8
    scene.render.resolution_x = size
    scene.render.resolution_y = size
    scene.render.film_transparent = False
    try:
        scene.view_settings.view_transform = 'Khronos PBR Neutral'
    except Exception:
        scene.view_settings.view_transform = 'Standard'
    scene.view_settings.look = 'None'
    scene.render.image_settings.file_format = 'PNG'


def render_lineup(scene, cam, out_dir, size):
    """White, yellow and blue side by side, like the reference photo
    (temporary linked copies)."""
    hat = bpy.data.objects["HardHat"]
    names = ["White", "Yellow", "Blue"]
    tmp = bpy.data.collections.new("_lineup")
    scene.collection.children.link(tmp)
    hat.hide_render = True
    k = hat.get("shell_scale", 1.0)
    copies = []
    for i, n in enumerate(names):
        ob = bpy.data.objects.new("lineup_" + n, hat.data)
        tmp.objects.link(ob)
        ob.location = ((i - (len(names) - 1) / 2) * 0.30 * k, 0.0, 0.0)
        ob.rotation_euler = (0.0, 0.0, math.radians(-40))
        ob.material_slots[0].link = 'OBJECT'
        ob.material_slots[0].material = bpy.data.materials["HardHat_" + n]
        copies.append(ob)
    rx, ry = scene.render.resolution_x, scene.render.resolution_y
    scene.render.resolution_x, scene.render.resolution_y = int(size * 2.0), size
    cam.location = (0.0, -1.55 * k, 0.95 * k)
    look_at(cam, (0.0, 0.0, 0.035 * k))
    cam.data.lens = 56
    scene.render.filepath = os.path.join(out_dir, "lineup.png")
    bpy.ops.render.render(write_still=True)
    print("rendered lineup")
    for ob in copies:
        bpy.data.objects.remove(ob)
    bpy.data.collections.remove(tmp)
    hat.hide_render = False
    scene.render.resolution_x, scene.render.resolution_y = rx, ry


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    save = "--save" in argv
    argv = [a for a in argv if a != "--save"]
    out_dir = argv[0] if argv else "renders"
    size = int(argv[1]) if len(argv) > 1 else 1200
    samples = int(argv[2]) if len(argv) > 2 else 96
    views = argv[3].split(",") if len(argv) > 3 and argv[3] != "all" else list(VIEWS) + ["lineup"]
    os.makedirs(out_dir, exist_ok=True)

    scene = bpy.context.scene
    ensure_studio(scene)
    setup_render(scene, size, samples)
    if os.environ.get("CLAY"):
        clay = bpy.data.materials.new("clay")
        clay.diffuse_color = (0.5, 0.5, 0.5, 1)
        bsdf = clay.node_tree.nodes.get("Principled BSDF") if clay.node_tree else None
        if bsdf is None:
            clay.use_nodes = True
            bsdf = clay.node_tree.nodes.get("Principled BSDF")
        bsdf.inputs["Base Color"].default_value = (0.75, 0.75, 0.75, 1)
        bsdf.inputs["Roughness"].default_value = 0.35
        hat = bpy.data.objects["HardHat"]
        hat.data.materials[0] = clay
        scene.view_settings.view_transform = 'AgX'

    cam = scene.camera
    floor = bpy.data.objects.get("Floor_ShadowCatcher")
    # camera positions are drawn for the scale-1 helmet; follow its size
    k = bpy.data.objects["HardHat"].get("shell_scale", 1.0)

    def place(name):
        loc, tgt, focal = VIEWS[name][:3]
        roll = VIEWS[name][3] if len(VIEWS[name]) > 3 else 0.0
        cam.location = [c * k for c in loc]
        look_at(cam, [c * k for c in tgt])
        q = cam.rotation_euler.to_quaternion() @ Quaternion((0.0, 0.0, 1.0), math.radians(roll))
        cam.rotation_euler = q.to_euler()
        cam.data.lens = focal

    for name in views:
        if name == "lineup":
            render_lineup(scene, cam, out_dir, size)
            continue
        place(name)
        cam.data.clip_start = 0.01
        if floor:
            floor.hide_render = name in ("underside", "top")
        scene.render.filepath = os.path.join(out_dir, name + ".png")
        bpy.ops.render.render(write_still=True)
        print("rendered", name)

    if save:
        place("hero_3q")
        if floor:
            floor.hide_render = False
        bpy.ops.wm.save_mainfile(compress=True)


if __name__ == "__main__":
    main()
