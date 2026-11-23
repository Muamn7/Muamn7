"""Builds the .blend, STL files and preview renders.
usage: python3 blend_build.py OUTDIR [stand1] [stand2] [--norender] [--samples N]"""
import sys, os, math, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bpy, bmesh
from mathutils import Matrix, Vector
from lib import to_arrays, write_stl

args = sys.argv[1:]
OUT = args[0]
which = [a for a in args[1:] if a.startswith('stand') or a == 'roles'] or ['stand1', 'stand2', 'roles']
RENDER = '--norender' not in args
SAMPLES = 64
if '--samples' in args:
    SAMPLES = int(args[args.index('--samples') + 1])
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.preferences.filepaths.save_version = 0  # no .blend1 backup files
scene = bpy.context.scene
scene.unit_settings.system = 'METRIC'
scene.unit_settings.scale_length = 0.001
scene.unit_settings.length_unit = 'MILLIMETERS'


def srgb(c):
    return tuple(((x / 255.0 + 0.055) / 1.055) ** 2.4 if x / 255.0 > 0.04045 else x / 255.0 / 12.92 for x in c)


def make_mat(name, rgb255, rough=0.5, spec=0.5, coat=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (*srgb(rgb255), 1)
    b.inputs['Roughness'].default_value = rough
    if 'Coat Weight' in b.inputs:
        b.inputs['Coat Weight'].default_value = coat
    m.diffuse_color = (*srgb(rgb255), 1)
    return m


MATS = {
    'black': make_mat('PLA_Black', (22, 22, 24), rough=0.55),
    'yellow': make_mat('PLA_Yellow', (246, 196, 0), rough=0.42),
    'white': make_mat('PLA_White', (225, 228, 232), rough=0.38),
    'phone': make_mat('Phone_Dummy', (55, 60, 72), rough=0.18),
}


def new_collection(name, parent=None):
    c = bpy.data.collections.new(name)
    (parent or scene.collection).children.link(c)
    return c


def mesh_from_manifold(name, m, tidy=True):
    v, f = to_arrays(m)
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(v))
    me.vertices.foreach_set('co', v.astype(np.float32).ravel())
    me.loops.add(len(f) * 3)
    me.loops.foreach_set('vertex_index', f.astype(np.int32).ravel())
    me.polygons.add(len(f))
    me.polygons.foreach_set('loop_start', np.arange(0, len(f) * 3, 3, dtype=np.int32))
    me.update(calc_edges=True)
    me.validate()
    if tidy:  # merge coplanar triangles into clean n-gons (nicer to edit in Blender)
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
        bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(0.3), verts=bm.verts, edges=bm.edges,
                                 delimit={'NORMAL'})
        bm.to_mesh(me)
        bm.free()
    try:
        me.shade_flat()
    except Exception:
        me.polygons.foreach_set('use_smooth', np.zeros(len(me.polygons), dtype=bool))
    return me


def link_obj(name, me, coll, mat, matrix=None):
    ob = bpy.data.objects.new(name, me)
    if mat.name not in [s.name for s in me.materials if s]:
        me.materials.append(mat)
    coll.objects.link(ob)
    if matrix is not None:
        M = np.eye(4)
        M[:3, :] = matrix
        ob.matrix_world = Matrix(M.tolist())
    return ob


def build_stand(mod, x_offset, layout_y):
    t0 = time.time()
    d = mod.build()
    name = d['name']
    acc = d['accent_name']
    sdir = os.path.join(OUT, name)
    os.makedirs(sdir, exist_ok=True)
    root = new_collection(name)
    c_asm = new_collection(name + '_Assembled', root)
    c_prn = new_collection(name + '_Print_Layout', root)
    objs_asm = []
    meshes = {}
    lay_x = 0.0
    cnames = {'black': 'black', 'accent': acc, 'accent2': d.get('accent2_name')}
    for pname, p in d['parts'].items():
        for color in ('black', 'accent', 'accent2'):
            m = p.get(color)
            if m is None or m.is_empty():
                continue
            cname = cnames[color]
            # STL in print orientation, part sits on z=0 (all colours share one frame)
            fname = '%s_%s_%s.stl' % (name, pname, cname)
            write_stl(os.path.join(sdir, fname), m, fname)
            me = mesh_from_manifold('%s_%s_%s' % (name, pname, cname), m)
            meshes[(pname, cname)] = me
            mat = MATS[cname]
            A = p['assembly']
            Mw = np.eye(4)[:3].copy() if A is None else np.asarray(A)
            Mw = Mw.copy()
            Mw[0, 3] += x_offset
            if p.get('show', True):
                objs_asm.append(link_obj('%s_%s_%s' % (name, pname, cname), me, c_asm, mat, Mw))
            L = np.eye(4)[:3].copy()
            L[0, 3] = x_offset + lay_x
            L[1, 3] = layout_y
            link_obj('%s_%s_%s_print' % (name, pname, cname), me, c_prn, mat, L)
        bb = (p['black'] + p['accent'] + p.get('accent2', p['accent'])).bounding_box()
        lay_x += (bb[3] - bb[0]) + 25
    c_prn.hide_render = True
    if hasattr(mod, 'LAYOUT'):
        # group of role stands: one shared base mesh + each role's plate, arranged like the logo sheet
        for role, (gx, gy) in mod.LAYOUT.items():
            c_r = new_collection('%s_%s' % (name, role), c_asm)
            for (pname, cname), me in meshes.items():
                if pname not in ('Base', 'Plate_' + role):
                    continue
                A = d['parts'][pname]['assembly']
                Mw = (np.eye(4)[:3] if A is None else np.asarray(A)).copy()
                Mw[0, 3] += x_offset + gx
                Mw[1, 3] += gy
                objs_asm.append(link_obj('%s_%s_%s' % (role, pname.replace('Plate_' + role, 'Plate'), cname),
                                         me, c_r, MATS[cname], Mw))
        print(name, 'built in %.1fs' % (time.time() - t0))
        return name, objs_asm, d, None
    # phone dummy (78 x 165 x 9 mm) resting on the ledge, for a size check
    from check import phone
    c_ph = new_collection(name + '_Phone_Dummy_78x165', root)
    ph_me = mesh_from_manifold(name + '_Phone_Dummy', phone(mod.REST + 0.05), tidy=False)
    Mw = np.asarray(d['parts']['Plate']['assembly']).copy()
    Mw[0, 3] += x_offset
    ph = link_obj(name + '_Phone_Dummy', ph_me, c_ph, MATS['phone'], Mw)
    ph.hide_render = True
    c_ph.hide_viewport = False
    print(name, 'built in %.1fs' % (time.time() - t0))
    return name, objs_asm, d, ph


def look_at(ob, target):
    direction = Vector(target) - ob.location
    ob.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()


def setup_world(color, strength):
    w = bpy.data.worlds.new('World')
    scene.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes['Background']
    bg.inputs['Color'].default_value = (*color, 1)
    bg.inputs['Strength'].default_value = strength


def render(path, cam_loc, target, res, world_col, world_str, sun_rot, sun_str, lens=60, floor_col=None,
           visible=None, ortho=None):
    for ob in scene.objects:
        if ob.type == 'MESH' and ob.name != 'Floor':
            ob.hide_render = visible is not None and ob not in visible
    for c in bpy.data.collections:
        if c.name.endswith('_Print_Layout'):
            c.hide_render = not (visible and any(o.name.endswith('_print') for o in visible))
    setup_world(world_col, world_str)
    for ob in [o for o in scene.objects if o.type in ('CAMERA', 'LIGHT')]:
        bpy.data.objects.remove(ob)
    cam_d = bpy.data.cameras.new('Cam')
    cam_d.lens = lens
    cam_d.clip_end = 20000
    if ortho:
        cam_d.type = 'ORTHO'
        cam_d.ortho_scale = ortho
    cam = bpy.data.objects.new('Cam', cam_d)
    scene.collection.objects.link(cam)
    cam.location = cam_loc
    look_at(cam, target)
    scene.camera = cam
    for i, (rot, st) in enumerate(zip(sun_rot, sun_str)):
        ld = bpy.data.lights.new('Sun%d' % i, 'SUN')
        ld.energy = st
        ld.angle = math.radians(12)
        lo = bpy.data.objects.new('Sun%d' % i, ld)
        lo.rotation_euler = [math.radians(a) for a in rot]
        scene.collection.objects.link(lo)
    fl = bpy.data.objects.get('Floor')
    if fl:
        fl.data.materials[0].node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (*floor_col, 1)
    r = scene.render
    r.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = SAMPLES
    scene.cycles.use_denoising = True
    r.resolution_x, r.resolution_y = res
    r.resolution_percentage = 100
    r.filepath = path
    r.image_settings.file_format = 'PNG'
    scene.view_settings.view_transform = 'Standard'
    scene.view_settings.look = 'None'
    t0 = time.time()
    bpy.ops.render.render(write_still=True)
    print('rendered', path, '%.1fs' % (time.time() - t0))


def add_floor():
    me = bpy.data.meshes.new('Floor')
    s = 3000
    me.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
    ob = bpy.data.objects.new('Floor', me)
    m = bpy.data.materials.new('Floor')
    m.use_nodes = True
    m.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value = 0.6
    me.materials.append(m)
    scene.collection.objects.link(ob)
    ob.location.z = -0.05
    return ob


results = {}
mods = {}
if 'stand1' in which:
    import stand1
    mods['stand1'] = (stand1, 0.0)
if 'stand2' in which:
    import stand2
    mods['stand2'] = (stand2, 400.0)
if 'roles' in which:
    import roles
    mods['roles'] = (roles, 0.0)

for key, (mod, xo) in mods.items():
    if key == 'roles':
        results[key] = build_stand(mod, xo, layout_y=-650.0)
    else:
        results[key] = build_stand(mod, xo, layout_y=-350.0)

floor = add_floor()
blend_path = os.path.join(OUT, 'Phone_Stands.blend')
bpy.ops.wm.save_as_mainfile(filepath=blend_path)
print('saved', blend_path)

ROLE_Y = 700.0   # role group sits behind the other stands in the .blend
if 'roles' in results:
    for ob in results['roles'][1]:
        ob.location.y += ROLE_Y
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)

if RENDER:
    floor.hide_render = False
    if 'roles' in results:
        _, objs, _, _ = results['roles']
        render(os.path.join(OUT, 'group_role_stands.png'), (70, ROLE_Y - 760, 520), (0, ROLE_Y + 10, 50),
               (1600, 1100), (0.93, 0.93, 0.93), 0.9, [(50, 0, 20), (60, 0, -120)], [3.2, 1.2], lens=54,
               floor_col=(0.86, 0.86, 0.86), visible=objs)
        plates = [o for o in scene.objects if o.name.startswith('Role_Stands_Plate_') and o.name.endswith('_print')]
        xs = [o.location.x for o in plates]
        cxm = (min(xs) + max(xs)) / 2
        render(os.path.join(OUT, 'role_plates_top.png'), (cxm, -650 + 70, 600), (cxm, -650 + 70, 0),
               (2000, 640), (0.93, 0.93, 0.93), 0.9, [(35, 0, 20), (60, 0, -120)], [3.0, 1.0],
               floor_col=(0.86, 0.86, 0.86), visible=plates, ortho=(max(xs) - min(xs)) + 92 + 30)
    if 'stand1' in results:
        _, objs, _, ph = results['stand1']
        render(os.path.join(OUT, 'fit_S_stand_with_phone.png'), (230, -380, 190), (0, 0, 85), (900, 1200),
               (0.92, 0.92, 0.92), 0.9, [(55, 0, 25), (60, 0, -120)], [3.2, 1.2], lens=55,
               floor_col=(0.85, 0.85, 0.85), visible=objs + [ph])
        render(os.path.join(OUT, 'preview_S_stand.png'), (175, -330, 130), (0, 0, 62), (900, 1200),
               (0.92, 0.92, 0.92), 0.9, [(55, 0, 25), (60, 0, -120)], [3.2, 1.2], lens=62,
               floor_col=(0.85, 0.85, 0.85), visible=objs)
        render(os.path.join(OUT, 'preview_S_stand_back.png'), (-230, 260, 170), (0, 0, 50), (1000, 800),
               (0.92, 0.92, 0.92), 0.9, [(55, 0, 200), (60, 0, 60)], [3.0, 1.2], lens=55,
               floor_col=(0.85, 0.85, 0.85), visible=objs)
    if 'stand2' in results:
        _, objs, _, ph = results['stand2']
        render(os.path.join(OUT, 'fit_ML_stand_with_phone.png'), (400 + 150, -480, 260), (400, 0, 100), (1000, 1200),
               (0.02, 0.022, 0.03), 0.6, [(50, 0, 20), (65, 0, -110), (70, 0, 150)], [2.6, 1.0, 1.5], lens=50,
               floor_col=(0.03, 0.03, 0.035), visible=objs + [ph])
        render(os.path.join(OUT, 'preview_ML_stand.png'), (400 + 70, -520, 215), (400, 0, 78), (1280, 860),
               (0.02, 0.022, 0.03), 0.6, [(50, 0, 20), (65, 0, -110), (70, 0, 150)], [2.6, 1.0, 1.5], lens=50,
               floor_col=(0.03, 0.03, 0.035), visible=objs)
        render(os.path.join(OUT, 'preview_ML_stand_back.png'), (400 - 260, 300, 190), (400, 0, 50), (1000, 800),
               (0.02, 0.022, 0.03), 0.6, [(50, 0, 200), (65, 0, 60)], [2.6, 1.2], lens=55,
               floor_col=(0.03, 0.03, 0.035), visible=objs)
