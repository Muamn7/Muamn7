"""
Export the refinery diorama as 3D-printable STL parts (square board, real mm).

Usage:
    blender -b -P export_print.py -- [--size 300] [--min 0.8] [--out print_30cm] [--save x.blend]

    --size   outer size of the square board in mm (default 300 = 30 x 30 cm)
    --min    thinnest rod / wall in mm (0.8 for FDM 0.4 nozzle, 0.5 for resin)
    --out    output folder (default: print_30cm next to this file)
    --save   also save the print version as a .blend (units set to mm)

The plant is fused with the base and cut into four tiles that fit a 200 mm
bed; the trees, the truck and the flare flame are separate parts.

Inside Blender's Scripting tab you can also just run it; defaults are used.
Every part is checked for open edges before it is written; the result is
listed in parts.txt.
"""

import bpy
import bmesh
import importlib.util
import os
import struct
import sys
from collections import OrderedDict
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()


def _args():
    argv = sys.argv
    a = argv[argv.index('--') + 1:] if '--' in argv else []

    def get(flag, default, cast):
        return cast(a[a.index(flag) + 1]) if flag in a else default

    return get('--size', 300.0, float), get('--min', 0.8, float), get('--out', os.path.join(HERE, 'print_30cm'), str)


def load_scene_module():
    path = os.path.join(HERE, 'refinery_diorama.py')
    spec = importlib.util.spec_from_file_location('refinery_diorama', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Part grouping
# ---------------------------------------------------------------------------
# Everything except these is fused with the base into the board tiles; these
# stay loose because they are easier to paint (and the flame would otherwise
# make the flare tile taller than most printers).
SEPARATE = OrderedDict((('Trees', 'glue onto the grass'), ('TankerTruck', 'stands on the road under the gantry'),
                        ('Flame', 'glue onto the flare tip; print in translucent orange')))

# Tile cut lines in scene units. They were chosen so they only cross pipes,
# roads and flat slabs, never a column, tank or building.
CUT_X = 0.98
CUT_Y_LEFT = 2.2
CUT_Y_RIGHT = 1.7

# tiny connector stubs are printed together with their neighbour
MERGE = {'HX_Feed': 'Pipe_Furnace_Feed', 'Tank2_Out': 'ProductTank_2'}
BASE_PREFIX = ('Board_Gravel', 'Board_Frame', 'Roads', 'Curb_', 'Grass_', 'Concrete_Pads')


def group_objects():
    groups = OrderedDict()

    def add(key, ob):
        groups.setdefault(key, []).append(ob)

    for ob in bpy.data.objects:
        if ob.type not in ('MESH', 'CURVE', 'FONT') or ob.name.startswith('TreeVariant_'):
            continue
        n = ob.name.replace(' ', '_')
        if n in MERGE:
            add(MERGE[n], ob)
        elif n.startswith(BASE_PREFIX):
            add('BASE', ob)
        elif n.startswith(('Label_', 'Text_', 'Leader_')):
            add('Label_' + n.split('_', 1)[1], ob)
        elif n.startswith(('PipeRack', 'Rack_')):
            add('PipeRack', ob)
        elif n.startswith('Flare_Flame'):
            add('Flame', ob)
        elif n.startswith('TankerTruck'):
            add('TankerTruck', ob)
        elif n.startswith('Tree'):
            add('Trees', ob)
        elif n.endswith('_Fittings'):
            add('Pipe_' + n[:-len('_Fittings')], ob)
        elif ob.type == 'CURVE':
            add('Pipe_' + n, ob)
        else:
            add(n, ob)
    return groups


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------
def object_bmesh(ob, dg):
    eo = ob.evaluated_get(dg)
    me = eo.to_mesh()
    bm = bmesh.new()
    bm.from_mesh(me)
    eo.to_mesh_clear()
    if ob.type in ('CURVE', 'FONT'):
        # curve caps / letter fills come out as separate pieces: weld them
        bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-6)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.transform(ob.matrix_world)
    return bm


def merge_into(dst, src):
    me = bpy.data.meshes.new('_tmp')
    src.to_mesh(me)
    dst.from_mesh(me)
    bpy.data.meshes.remove(me)


def open_edges(bm):
    return sum(1 for e in bm.edges if len(e.link_faces) != 2)


def clip(bm, xmin, xmax, ymin, ymax):
    """Cut a bmesh to an XY rectangle and cap the cuts so shells stay closed."""
    planes = (((xmin, 0, 0), (-1, 0, 0)), ((xmax, 0, 0), (1, 0, 0)),
              ((0, ymin, 0), (0, -1, 0)), ((0, ymax, 0), (0, 1, 0)))
    for co, no in planes:
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        bmesh.ops.bisect_plane(bm, geom=geom, plane_co=co, plane_no=no, clear_outer=True)
        bnd = [e for e in bm.edges if e.is_boundary]
        if bnd:
            bmesh.ops.holes_fill(bm, edges=bnd, sides=0)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])


def write_stl(path, bm, scale, center_xy=True):
    bm = bm.copy()
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bm.verts.ensure_lookup_table()
    xs = [v.co.x for v in bm.verts]
    ys = [v.co.y for v in bm.verts]
    zs = [v.co.z for v in bm.verts]
    off = Vector(((min(xs) + max(xs)) / 2 if center_xy else 0.0,
                  (min(ys) + max(ys)) / 2 if center_xy else 0.0, min(zs)))
    tris = bm.faces[:]
    with open(path, 'wb') as f:
        f.write(b'Refinery diorama part (mm)'.ljust(80, b' '))
        f.write(struct.pack('<I', len(tris)))
        for t in tris:
            n = t.normal
            f.write(struct.pack('<3f', n.x, n.y, n.z))
            for v in t.verts:
                p = (v.co - off) * scale
                f.write(struct.pack('<3f', p.x, p.y, p.z))
            f.write(b'\0\0')
    size = ((max(xs) - min(xs)) * scale, (max(ys) - min(ys)) * scale, (max(zs) - min(zs)) * scale)
    n = len(tris)
    bm.free()
    return n, size


# ---------------------------------------------------------------------------
def main():
    size_mm, min_mm, out = _args()
    mod = load_scene_module()
    mod.PRINT = True
    mod.PRINT_SIZE_MM = size_mm
    mod.MIN_FEATURE_MM = min_mm
    mod.build()
    S = mod.print_scale()
    os.makedirs(out, exist_ok=True)
    for f in os.listdir(out):
        if f.endswith('.stl'):
            os.remove(os.path.join(out, f))

    dg = bpy.context.evaluated_depsgraph_get()
    report = []
    plant = bmesh.new()
    for key, obs in group_objects().items():
        bm = bmesh.new()
        for ob in obs:
            part = object_bmesh(ob, dg)
            merge_into(bm, part)
            part.free()
        if key in SEPARATE:
            name = '02_%s.stl' % key
            n, sz = write_stl(os.path.join(out, name), bm, S)
            report.append((name, n, sz, open_edges(bm), SEPARATE[key]))
        else:
            merge_into(plant, bm)
        bm.free()

    name = '00_Full_model_%dmm.stl' % round(size_mm)
    n, sz = write_stl(os.path.join(out, name), plant, S)
    report.append((name, n, sz, open_edges(plant), 'one piece, needs a %d mm bed' % round(size_mm)))
    H = mod.BOARD_X + mod.FRAME_T + 0.05
    for name, x0, x1, y0, y1 in (('01_Tile_front_left', -H, CUT_X, -H, CUT_Y_LEFT),
                                 ('01_Tile_back_left', -H, CUT_X, CUT_Y_LEFT, H),
                                 ('01_Tile_front_right', CUT_X, H, -H, CUT_Y_RIGHT),
                                 ('01_Tile_back_right', CUT_X, H, CUT_Y_RIGHT, H)):
        t = plant.copy()
        clip(t, x0, x1, y0, y1)
        n, sz = write_stl(os.path.join(out, name + '.stl'), t, S)
        report.append((name + '.stl', n, sz, open_edges(t), ''))
        t.free()
    plant.free()

    report.sort()
    lines = ['Refinery diorama - printable parts',
             'board %.0f x %.0f mm, scale 1 unit = %.3f mm, min feature %.2f mm' % (size_mm, size_mm, S, min_mm),
             '', '%-34s %9s  %-26s %s' % ('file', 'triangles', 'size X x Y x Z (mm)', 'open edges')]
    for name, n, sz, oe, note in report:
        lines.append('%-34s %9d  %7.1f x %6.1f x %6.1f   %d  %s' % (name, n, sz[0], sz[1], sz[2], oe, note))
    txt = '\n'.join(lines)
    with open(os.path.join(out, 'parts.txt'), 'w') as f:
        f.write(txt + '\n')
    print(txt)

    if '--save' in sys.argv:
        sc = bpy.context.scene
        sc.unit_settings.system = 'METRIC'
        sc.unit_settings.scale_length = S / 1000.0
        sc.unit_settings.length_unit = 'MILLIMETERS'
        for f in bpy.data.fonts:
            if f.filepath and f.filepath != '<builtin>' and not f.packed_file:
                f.pack()
        argv = sys.argv
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(argv[argv.index('--save') + 1]), compress=True)


if __name__ == '__main__':
    main()
