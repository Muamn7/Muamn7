# -*- coding: utf-8 -*-
"""
Helper T Lymphocyte  <->  Macrophage  (MHC class II immunological synapse)
3D-printable educational display model  -  procedural Blender script.

  * 1 Blender unit = 1 mm.  Base width = 400 mm (40 cm).
  * Works in Blender 4.2 LTS ... 5.x  (Scripting tab -> Open -> Run Script).
  * WARNING: the script clears the objects of the current scene. Start from File > New.

Headless:
  blender -b -P immune_synapse_model.py -- --export ./stl --save model.blend --render preview.png

Every printable part is a separate, closed (manifold) mesh, all exported in the
SAME assembled coordinates, so you can load all STLs into Bambu Studio / OrcaSlicer /
PrusaSlicer as one multi-part object and assign one filament colour per part,
or print each part on its own and glue it (pegs and holes are already modelled).
"""
import bpy, bmesh, math, random, os, sys, struct, time
from mathutils import Vector, Matrix, Quaternion
from mathutils.bvhtree import BVHTree

# ----------------------------------------------------------------- settings
EXPORT_DIR = ""        # e.g. r"C:\prints\synapse_stl"   ("" = do not export)
SAVE_BLEND = ""        # e.g. r"C:\prints\synapse.blend"
RENDER_PATH = ""       # e.g. r"C:\prints\preview.png"
QUALITY = 1.0          # 0.6 draft / 1.0 print / 1.4 extra fine (slower, heavier STLs)
SAMPLES = 64
SEED = 7
FONT_FILE = ""         # optional .ttf/.otf; "" = first bold sans font found below, else Blender's built-in
FONT_CANDIDATES = [r"C:\Windows\Fonts\ARIALNB.TTF", "/System/Library/Fonts/Supplemental/Arial Narrow Bold.ttf",
                   "/usr/share/fonts/truetype/liberation/LiberationSansNarrow-Bold.ttf",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf", r"C:\Windows\Fonts\arialbd.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                   "/Library/Fonts/Arial Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                   "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
for i, a in enumerate(argv):
    if a == "--export": EXPORT_DIR = argv[i + 1]
    if a == "--save": SAVE_BLEND = argv[i + 1]
    if a == "--render": RENDER_PATH = argv[i + 1]
    if a == "--quality": QUALITY = float(argv[i + 1])
    if a == "--samples": SAMPLES = int(argv[i + 1])

random.seed(SEED)
T0 = time.time()
VIS = 0.574            # visible radius of an isolated metaball / its radius (threshold 0.6)
CLR = 0.25             # radial clearance for pegs / rods in holes (mm)
ROD_R = 4.0            # 8 mm rods
SOLVERS = [e.identifier for e in bpy.types.BooleanModifier.bl_rna.properties['solver'].enum_items]
SOLVER = 'MANIFOLD' if 'MANIFOLD' in SOLVERS else 'EXACT'


def log(*a):
    print("[synapse %6.1fs]" % (time.time() - T0), *a, flush=True)


# ================================================================ helpers
scene = bpy.context.scene
for ob in list(scene.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
for c in list(scene.collection.children):
    scene.collection.children.unlink(c)
us = scene.unit_settings
us.system, us.scale_length, us.length_unit = 'METRIC', 0.001, 'MILLIMETERS'


def coll(name):
    c = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    if c.name not in [x.name for x in scene.collection.children]:
        scene.collection.children.link(c)
    return c


C_BASE, C_MAC, C_TC, C_PROT = coll("01_Base"), coll("02_Macrophage"), coll("03_T_Cell"), coll("04_Proteins")
C_ROD, C_LAB, C_WIRE, C_SCN = coll("05_Rods_Posts"), coll("06_Labels"), coll("07_Leader_Wires"), coll("99_Render_Scene")
C_TMP = coll("zz_tmp")


def dg():
    return bpy.context.evaluated_depsgraph_get()


def obj_from_bm(name, bm, c=C_TMP):
    me = bpy.data.meshes.new(name)
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    c.objects.link(ob)
    return ob


def apply_mods(ob):
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg()))
    old = ob.data
    ob.modifiers.clear()
    ob.data = me
    if old.users == 0:
        bpy.data.meshes.remove(old)


def remesh(ob, voxel):
    m = ob.modifiers.new("rm", 'REMESH')
    m.mode, m.voxel_size, m.adaptivity, m.use_smooth_shade = 'VOXEL', voxel, 0.0, True
    apply_mods(ob)


def displace(ob, scale, strength, basis='ORIGINAL_PERLIN', depth=2):
    tex = bpy.data.textures.new(ob.name + "_noise", 'CLOUDS')
    tex.noise_scale, tex.noise_depth, tex.noise_basis = scale, depth, basis
    m = ob.modifiers.new("d", 'DISPLACE')
    m.texture, m.strength, m.mid_level, m.texture_coords = tex, strength, 0.5, 'GLOBAL'
    apply_mods(ob)


def smooth(ob, factor=0.5, it=4):
    m = ob.modifiers.new("s", 'SMOOTH')
    m.factor, m.iterations = factor, it
    apply_mods(ob)


def boolean(ob, cutter, op='DIFFERENCE'):
    backup = ob.data.copy()
    for solver in ([SOLVER, 'EXACT'] if SOLVER != 'EXACT' else ['EXACT']):
        m = ob.modifiers.new("b", 'BOOLEAN')
        m.operation, m.object, m.solver = op, cutter, solver
        apply_mods(ob)
        if len(ob.data.polygons) > 0:
            break
        log("  boolean %s on %s failed with %s, retrying" % (op, ob.name, solver))
        old = ob.data
        ob.data = backup.copy()
        bpy.data.meshes.remove(old)
    bpy.data.meshes.remove(backup)


def kill(ob):
    me = ob.data if ob.type == 'MESH' else None
    bpy.data.objects.remove(ob, do_unlink=True)
    if me and me.users == 0:
        bpy.data.meshes.remove(me)


def duplicate(ob, name, c=C_TMP):
    o = bpy.data.objects.new(name, ob.data.copy())
    c.objects.link(o)
    return o


def move_to(ob, c):
    for x in ob.users_collection:
        x.objects.unlink(ob)
    c.objects.link(ob)


def bvh(ob):
    return BVHTree.FromObject(ob, dg())


def inside(tree, p, margin=0.0):
    loc, nor, idx, dist = tree.find_nearest(p)
    return loc is not None and (p - loc).dot(nor) < 0 and dist >= margin


def align_z(d):
    return Vector((0, 0, 1)).rotation_difference(d.normalized()).to_matrix().to_4x4()


# ---------- bmesh primitives (all take a 4x4 matrix) ----------
def p_cyl(bm, a, b, r, seg=32, r2=None):
    a, b = Vector(a), Vector(b)
    d = b - a
    M = Matrix.Translation((a + b) / 2) @ align_z(d)
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg, radius1=r,
                          radius2=r if r2 is None else r2, depth=d.length, matrix=M)


def p_box(bm, lo, hi, M=Matrix()):
    lo, hi = Vector(lo), Vector(hi)
    c, s = (lo + hi) / 2, hi - lo
    S = Matrix.Diagonal((s.x, s.y, s.z, 1))
    bmesh.ops.create_cube(bm, size=1.0, matrix=M @ Matrix.Translation(c) @ S)


def p_ellipsoid(bm, M, rx, ry, rz, seg=32, rings=16):
    S = Matrix.Diagonal((rx, ry, rz, 1))
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=rings, radius=1.0, matrix=M @ S)


def p_strip(bm, pts, width, z0, z1, M):
    """closed rectangular-section ribbon along a 2D polyline (local XY), z0..z1"""
    n = len(pts)
    rows = []
    for i, p in enumerate(pts):
        q0 = pts[max(i - 1, 0)]
        q1 = pts[min(i + 1, n - 1)]
        t = Vector((q1[0] - q0[0], q1[1] - q0[1])).normalized()
        nrm = Vector((-t.y, t.x))
        L = Vector(p) + nrm * width / 2
        R = Vector(p) - nrm * width / 2
        rows.append([bm.verts.new(M @ Vector((v.x, v.y, z))) for v, z in ((L, z0), (R, z0), (R, z1), (L, z1))])
    for i in range(n - 1):
        a, b = rows[i], rows[i + 1]
        for k in range(4):
            bm.faces.new((a[k], a[(k + 1) % 4], b[(k + 1) % 4], b[k]))
    bm.faces.new(list(reversed(rows[0])))
    bm.faces.new(rows[-1])


def p_tube(bm, pts, r, seg=28):
    """closed round tube along a 3D polyline (parallel-transport frames)"""
    pts = [Vector(p) for p in pts]
    n = len(pts)
    tang = [(pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]).normalized() for i in range(n)]
    up = Vector((0, 0, 1)) if abs(tang[0].z) < 0.9 else Vector((1, 0, 0))
    u = tang[0].cross(up).normalized()
    rings = []
    for i in range(n):
        if i:
            q = tang[i - 1].rotation_difference(tang[i])
            u = (q @ u).normalized()
        v = tang[i].cross(u)
        rings.append([bm.verts.new(pts[i] + (u * math.cos(2 * math.pi * k / seg) + v * math.sin(2 * math.pi * k / seg)) * r)
                      for k in range(seg)])
    for i in range(n - 1):
        a, b = rings[i], rings[i + 1]
        for k in range(seg):
            bm.faces.new((a[k], a[(k + 1) % seg], b[(k + 1) % seg], b[k]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])


def p_rounded_slab(bm, w, h, t, r, M, z0=0.0, seg=8):
    """rounded rectangle plate in local XY, thickness from z0 to z0+t"""
    pts = []
    for cx, cy, a0 in ((w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90), (-w / 2 + r, -h / 2 + r, 180), (w / 2 - r, -h / 2 + r, 270)):
        for k in range(seg + 1):
            a = math.radians(a0 + 90 * k / seg)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    bot = [bm.verts.new(M @ Vector((x, y, z0))) for x, y in pts]
    top = [bm.verts.new(M @ Vector((x, y, z0 + t))) for x, y in pts]
    bm.faces.new(list(reversed(bot)))
    bm.faces.new(top)
    n = len(pts)
    for i in range(n):
        bm.faces.new((bot[i], bot[(i + 1) % n], top[(i + 1) % n], top[i]))


FONT = None
for fp in ([FONT_FILE] if FONT_FILE else []) + FONT_CANDIDATES:
    if fp and os.path.exists(fp):
        try:
            FONT = bpy.data.fonts.load(fp, check_existing=True)
            break
        except Exception:
            pass


def text_into(bm, body, size, M, height=0.7, max_w=1e9):
    """raised text, sitting on local z=0, centred on local origin"""
    cu = bpy.data.curves.new("txt", 'FONT')
    if FONT:
        cu.font = FONT
    cu.body, cu.size, cu.extrude, cu.resolution_u = body, size, height / 2, 3
    cu.align_x, cu.align_y = 'CENTER', 'CENTER'
    ob = bpy.data.objects.new("txt", cu)
    C_TMP.objects.link(ob)
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg()))
    xs = [v.co.x for v in me.vertices]
    ys = [v.co.y for v in me.vertices]
    sc = min(1.0, max_w / max(1e-6, max(xs) - min(xs)))
    me.transform(Matrix.Translation((-(max(xs) + min(xs)) / 2 * sc, -(max(ys) + min(ys)) / 2 * sc, 0)) @
                 Matrix.Diagonal((sc, sc, 1, 1)))
    me.transform(M @ Matrix.Translation((0, 0, height / 2)))
    tb = bmesh.new()
    tb.from_mesh(me)
    bmesh.ops.remove_doubles(tb, verts=tb.verts, dist=1e-4)
    tb.to_mesh(me)
    tb.free()
    bm.from_mesh(me)
    bpy.data.objects.remove(ob)
    bpy.data.curves.remove(cu)
    bpy.data.meshes.remove(me)


# ---------- metaballs ----------
def metaball_object(name, elements, res, c):
    mb = bpy.data.metaballs.new(name + "_mb")
    mb.resolution = mb.render_resolution = res
    mb.threshold = 0.6
    ob = bpy.data.objects.new("MBALL_" + name.replace(".", "_"), mb)
    scene.collection.objects.link(ob)
    for kind, co, rad, size, rot in elements:
        e = mb.elements.new(type=kind)
        e.co, e.radius, e.stiffness = co, rad, 2.0
        if size:
            e.size_x, e.size_y, e.size_z = size
        if rot:
            e.rotation = rot
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg()))
    bpy.data.objects.remove(ob)
    bpy.data.metaballs.remove(mb)
    o = bpy.data.objects.new(name, me)
    c.objects.link(o)
    return o


def E_ball(c, r):
    return ('BALL', Vector(c), r / VIS, None, None)


def E_ell(c, rx, ry, rz, rot=None):
    m = max(rx, ry, rz)                                   # element size is clamped to 20
    return ('ELLIPSOID', Vector(c), m / VIS, (rx / m, ry / m, rz / m), rot)


def E_caps(a, b, r):
    a, b = Vector(a), Vector(b)
    d = b - a
    q = Vector((1, 0, 0)).rotation_difference(d.normalized())
    return ('CAPSULE', (a + b) / 2, r / VIS, (d.length / 2, 1, 1), q)




# ================================================================ extra helpers
from mathutils import noise as mnoise, Euler

SQ = 1 / math.sqrt(2)


def p_torus(bm, M, R, r, seg=32, rs=12):
    rings = []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        rings.append([bm.verts.new(M @ Vector(((R + r * math.cos(b)) * math.cos(a), (R + r * math.cos(b)) * math.sin(a), r * math.sin(b))))
                      for b in [2 * math.pi * k / rs for k in range(rs)]])
    for i in range(seg):
        A, B = rings[i], rings[(i + 1) % seg]
        for k in range(rs):
            bm.faces.new((A[k], B[k], B[(k + 1) % rs], A[(k + 1) % rs]))


def p_prism(bm, poly, z0, z1):
    bot = [bm.verts.new((x, y, z0)) for x, y in poly]
    top = [bm.verts.new((x, y, z1)) for x, y in poly]
    bm.faces.new(list(reversed(bot)))
    bm.faces.new(top)
    n = len(poly)
    for i in range(n):
        bm.faces.new((bot[i], bot[(i + 1) % n], top[(i + 1) % n], top[i]))


def arc_pts(cx, cy, r, a0, a1, n=28):
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * k / n)), cy + r * math.sin(math.radians(a0 + (a1 - a0) * k / n)))
            for k in range(n + 1)]


def brain(ob, centre, r, freq=8.0, sc=0.085, depth=2.8):
    for v in ob.data.vertices:
        p = v.co - centre
        n = mnoise.noise(p * sc) + 0.5 * mnoise.noise(p * sc * 2.1 + Vector((5, 1, 3)))
        s = abs(math.sin(n * freq))
        v.co = centre + p.normalized() * (r - depth + depth * s ** 0.4)
    ob.data.update()


def rot2(v, deg):
    a = math.radians(deg)
    return Vector((v.x * math.cos(a) - v.y * math.sin(a), v.x * math.sin(a) + v.y * math.cos(a), 0.0))


def cutter_box(name, lo, hi):
    bm = bmesh.new()
    p_box(bm, lo, hi)
    return obj_from_bm(name, bm)


def cutter_cyls(name, pairs, r):
    bm = bmesh.new()
    for a, b in pairs:
        p_cyl(bm, a, b, r, 32)
    return obj_from_bm(name, bm)


# ================================================================ calibrated camera
# Solved by least squares from 14 points measured on the reference photo (rms 7 px).
CAM_LOC = Vector((-1464.18, -3492.15, 1235.09))
CAM_ROT = (1.293544, 0.0, -0.394871)
CAM_LENS, IMG_W, IMG_H = 250.0, 1152, 864
CAM_R = Euler(CAM_ROT, 'XYZ').to_matrix()
VIEW = Vector((CAM_LOC.x, CAM_LOC.y, 0)).normalized()     # horizontal direction towards the viewer


def px_ray(u, v):
    k = CAM_LENS / 36.0 * IMG_W
    return CAM_LOC.copy(), (CAM_R @ Vector(((u - IMG_W / 2) / k, -(v - IMG_H / 2) / k, -1.0))).normalized()


def px_plane(u, v, n, p0):
    o, d = px_ray(u, v)
    n, p0 = Vector(n), Vector(p0)
    return o + d * ((p0 - o).dot(n) / d.dot(n))


def px_axis(u, v, axis, val):
    n = Vector((0, 0, 0))
    n[axis] = 1.0
    p0 = Vector((0, 0, 0))
    p0[axis] = val
    return px_plane(u, v, n, p0)


def px_hit(u, v, tree):
    o, d = px_ray(u, v)
    return tree.ray_cast(o, d)[0]


MM_PX = 0.53                                             # mm per pixel around the model (long lens)

# ================================================================ layout (measured from the photo)
BASE_W, BASE_D = 400.0, 221.3
PL_H, PL_IN, SLAB_IN, SLAB_T = 32.4, 6.0, 4.9, 6.1
ZT = PL_H + SLAB_T                                       # top of the base
ROD_R, ROD_X, ROD_Y, ROD_Z = 3.0, 137.0, 8.7, 274.7      # 6 mm L-rods
POSTS = [(Vector((-124.1, -61.7)), 78.2), (Vector((121.7, -49.4)), 97.2)]
T_C = Vector((0.0, 8.7, 284.4))
T_RX, T_RZ = 67.5, 61.0                                  # slightly flattened sphere
M_C = Vector((9.0, 12.0, 103.0))
M_RX, M_RY, M_RZ = 89.0, 66.0, 57.0
PY = 24.0                                                # plane of the receptor complexes (behind the cut, so the pegs sit in solid membrane)
M_SPLIT_X = -58.0                                        # print split of the macrophage

# ================================================================ macrophage
log("macrophage")
els = [E_ell(M_C, M_RX, M_RY, M_RZ), E_ell((5.0, -20.0, 74.0), 82.0, 48.0, 32.0),
       E_ell((-42.0, -18.0, 88.0), 36.0, 29.0, 26.0), E_ell((58.0, -18.0, 88.0), 36.0, 30.0, 26.0)]   # front shoulders (floor edges in the photo)
for i in range(46):                                      # soft lumps all over the membrane
    d = Vector([random.gauss(0, 1) for _ in range(3)]).normalized()
    if d.z < -0.3:
        d.z = -d.z
    if d.z > 0.8:                                        # keep the synapse membrane under the proteins smooth
        continue
    p = M_C + Vector((d.x * M_RX, d.y * M_RY, d.z * M_RZ)) * 0.9
    els.append(E_ball(p, random.uniform(6, 10)))

# pseudopodia: tip pixel in the photo, depth plane of the tip, base radius, tip radius
PODS = [
    ((300, 552), -20, 9.5, 5.8), ((370, 446), -12, 9.0, 5.4), ((455, 393), 0, 9.5, 5.2),
    ((382, 640), -62, 11.5, 6.0), ((545, 692), -58, 9.5, 5.4), ((612, 688), -62, 9.0, 5.2),
    ((706, 684), -58, 9.5, 5.4), ((810, 630), -50, 12.5, 6.0), ((880, 524), -48, 10.5, 5.8, (0, 4, -24)),
    ((815, 458), 14, 11.0, 5.8, (0, 14, 0)), ((738, 388), 0, 10.5, 5.4), ((628, 383), 25, 8.0, 4.8),
    ((520, 392), 35, 8.0, 4.6),
]
BACK_PODS = [(45, 95, 34), (80, 92, 30), (115, 98, 34), (150, 92, 30), (20, 120, 26), (160, 122, 26), (95, 130, 26)]


def pod_balls(start, tip, r0, rt, droop=0.0):
    ctrl = start + (tip - start) * 0.5 + Vector((0, 0, droop))
    L = (tip - start).length
    n = max(10, int(L / 2.0))
    for k in range(n + 1):
        t = k / n
        p = (1 - t) ** 2 * start + 2 * (1 - t) * t * ctrl + t * t * tip
        els.append(E_ball(p, (r0 * (1 - t) ** 0.55 + rt * t) * 0.8))
    els.append(E_ball(tip, rt * 1.1))


for spec in PODS:
    (u, v), y, r0, rt = spec[:4]
    tip = px_axis(u, v, 1, y)
    d = tip - M_C
    d = Vector((d.x / M_RX, d.y / M_RY, d.z / M_RZ)).normalized()
    start = M_C + Vector((d.x * M_RX, d.y * M_RY, d.z * M_RZ)) * 0.74
    if len(spec) > 4:                                    # root moved so the arm stays out of the cut-away
        start += Vector(spec[4])
    rt_eff = rt * 1.25
    tip = tip - (tip - start).normalized() * rt_eff * 1.05     # pixel = outer edge of the bulb
    pod_balls(start, tip, r0 * 0.98, rt_eff, droop=3.0)
for az, z, L in BACK_PODS:                                # hidden side, keeps the cell round in 3D
    a = math.radians(az)
    start = M_C + Vector((M_RX * 0.7 * math.cos(a), M_RY * 0.7 * math.sin(a), z - M_C.z))
    tip = start + Vector((math.cos(a), math.sin(a), 0.15)) * L
    tip.y = min(tip.y, 100.0)
    pod_balls(start, tip, 11.0, 5.4)

macro = metaball_object("Macrophage_Body", els, 1.6, C_MAC)
remesh(macro, 1.0 / QUALITY)
displace(macro, 20.0, 3.0)
smooth(macro, 0.5, 2)
displace(macro, 7.0, 1.6)
smooth(macro, 0.6, 4)
boolean(macro, cutter_box("seat", (-400, -400, -50), (400, 400, ZT)))   # sits flat on the base
macro_full = duplicate(macro, "macro_full")
BV_M = bvh(macro_full)

# ================================================================ T cell
log("T cell")
bm = bmesh.new()
p_ellipsoid(bm, Matrix.Translation(T_C), T_RX, T_RX, T_RZ, 96, 48)
N_B = 72
ga = math.pi * (3 - math.sqrt(5))
rod_dirs = [Vector((s, 0, -0.2)).normalized() for s in (-1, 1)]
for i in range(N_B):                                     # blunt rounded "crown" bumps
    z = 1 - 2 * (i + 0.5) / N_B
    rr = math.sqrt(1 - z * z)
    d = Vector((rr * math.cos(ga * i), rr * math.sin(ga * i), z))
    d = (d + Vector([random.uniform(-0.07, 0.07) for _ in range(3)])).normalized()
    if d.z < -0.62 or any(d.angle(rd) < 0.28 for rd in rod_dirs):
        continue
    surf = T_C + Vector((d.x * T_RX, d.y * T_RX, d.z * T_RZ))
    nrm = Vector((d.x / T_RX, d.y / T_RX, d.z / T_RZ)).normalized()
    lean = (nrm + Vector([random.uniform(-0.25, 0.25) for _ in range(3)])).normalized()
    hgt, rb = random.uniform(8.0, 11.5), random.uniform(10.0, 12.5)
    p_cyl(bm, surf - nrm * 6, surf + lean * hgt, rb, 20, r2=rb * random.uniform(0.38, 0.5))
tcell = obj_from_bm("T_Cell_Body", bm, C_TC)
remesh(tcell, 0.75 / QUALITY)
smooth(tcell, 0.6, 6)
displace(tcell, 7.0, 1.8)
displace(tcell, 16.0, 2.0)
smooth(tcell, 0.4, 2)
tcell_full = duplicate(tcell, "tcell_full")
BV_T = bvh(tcell_full)

# ================================================================ receptor proteins (pixel-driven)
log("proteins")


def P(u, v):
    return px_axis(u, v, 1, PY)


def z_mac(x, y=PY):
    return BV_M.ray_cast(Vector((x, y, 400)), Vector((0, 0, -1)))[0].z


def z_t(x, y=PY):
    return BV_T.ray_cast(Vector((x, y, 0)), Vector((0, 0, 1)))[0].z


peg_holes_M, peg_holes_T = [], []


def bean(u, v, wpx, hpx, depth=0.8, rot=None):
    c = P(u, v)
    rx, rz = wpx / 2 * MM_PX, hpx / 2 * MM_PX
    return E_ell(c, rx, rx * depth, rz, rot)


def stalk(u0, v0, u1, v1, r=2.1):
    return E_caps(P(u0, v0), P(u1, v1), r)


def protein(name, chains, pegs):
    if chains and not isinstance(chains[0], list):
        chains = [chains]
    bm = bmesh.new()
    for k, els in enumerate(chains):
        part = metaball_object("%s_c%d" % (name, k), els, 0.45, C_TMP)
        bm.from_mesh(part.data)
        kill(part)
    for a, b in pegs:
        p_cyl(bm, a, b, 2.0, 24)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    C_PROT.objects.link(ob)
    remesh(ob, 0.3 / QUALITY)
    smooth(ob, 0.5, 2)
    displace(ob, 2.2, 0.45)
    smooth(ob, 0.5, 1)
    return ob


def helix(u, v, half_depth=6.0, r=2.1):
    c = P(u, v)
    return E_caps(c - Vector((0, half_depth, 0)), c + Vector((0, half_depth, 0)), r)


def peg_into_M(u):
    x = P(u, 400).x
    zb = z_mac(x)
    peg_holes_M.append(((x, PY, zb - 21), (x, PY, zb + 3)))
    return ((x, PY, zb - 20), (x, PY, zb + 1))


def peg_into_T(u):
    x = P(u, 300).x
    zt = z_t(x)
    peg_holes_T.append(((x, PY, zt - 3), (x, PY, zt + 13)))
    return ((x, PY, zt - 1), (x, PY, zt + 12))


def anchor_T(u):
    x = P(u, 300).x
    return Vector((x, PY, z_t(x) + 2))


def anchor_M(u):
    x = P(u, 400).x
    return Vector((x, PY, z_mac(x) - 2))


# widths / heights in photo pixels, measured on the 2x zoom of the reference
tcr = protein("TCR", [
    [E_caps(anchor_T(544), P(543, 296), 2.0), bean(543, 302, 25, 28), bean(539, 330, 32, 27), E_ball(P(547, 344), 2.6)],
    [E_caps(anchor_T(570), P(570, 300), 2.0), bean(570, 307, 25, 30), bean(574, 333, 31, 25), E_ball(P(563, 345), 2.6)]],
    [peg_into_T(544), peg_into_T(570)])
mhc = protein("MHC_II", [
    [bean(538, 366, 33, 32), bean(543, 392, 27, 25), E_caps(P(543, 398), anchor_M(543), 2.0), helix(544, 352)],
    [bean(572, 366, 33, 32), bean(575, 392, 26, 25), E_caps(P(570, 398), anchor_M(567), 2.0), helix(564, 352)]],
    [peg_into_M(543), peg_into_M(567)])
pep = protein("Antigen_Peptide", [bean(554, 352, 24, 23, depth=1.0)], [])
cd4 = protein("CD4", [
    E_caps(anchor_T(605), P(606, 300), 1.9), bean(606, 312, 22, 24), bean(604, 336, 23, 24),
    bean(598, 359, 24, 24), bean(586, 384, 28, 27)], [peg_into_T(605)])
cd28 = protein("CD28", [
    [E_caps(anchor_T(643), P(653, 300), 1.9), bean(656, 320, 28, 44)],
    [E_caps(anchor_T(662), P(682, 296), 1.9), bean(686, 316, 27, 42)]], [peg_into_T(643), peg_into_T(662)])
b7 = protein("B7_CD80_CD86", [
    [bean(665, 359, 28, 40), E_caps(P(662, 372), anchor_M(660), 1.9)],
    [bean(691, 354, 26, 40), E_caps(P(684, 368), anchor_M(677), 1.9)]], [peg_into_M(660), peg_into_M(677)])
for a, b in ((mhc, pep), (tcr, pep), (tcr, mhc), (cd4, mhc), (cd4, tcr), (cd28, b7)):
    boolean(a, b, 'DIFFERENCE')

# ================================================================ cut-aways
log("cut-aways")
L = 400.0
# T cell: 90 deg wedge opening towards the viewer, floor 44 mm below the centre
T_FLOOR = T_C.z - 44.0
ta, tb = rot2(VIEW, 45), rot2(VIEW, -45)
bm = bmesh.new()
poly = [(T_C.x, T_C.y), (T_C.x + tb.x * L, T_C.y + tb.y * L), (T_C.x + (VIEW.x) * L * 1.5, T_C.y + VIEW.y * L * 1.5),
        (T_C.x + ta.x * L, T_C.y + ta.y * L)]
p_prism(bm, poly, T_FLOOR, T_C.z + 200)
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
cut_T = obj_from_bm("cut_T", bm)

# macrophage: back wall + left wall + floor, read from the photo
M_FLOOR = 93.0
K = px_axis(545, 553, 2, M_FLOOR)                         # back-left corner of the floor
Bp = px_axis(740, 548, 2, M_FLOOR)                        # floor back edge, right
Wf = px_axis(470, 594, 2, M_FLOOR)                        # floor front-left corner
back_dir = (Bp - K).normalized()
left_dir = (Wf - K).normalized()
RIGHT_X = Vector((-VIEW.y, VIEW.x, 0))                   # viewer's right
Rp = px_axis(768, 560, 2, M_FLOOR)                       # right end of the floor
far = K + back_dir * ((Rp - K).dot(RIGHT_X) / back_dir.dot(RIGHT_X))
bm = bmesh.new()
pts = [K, far, far + VIEW * L, K + left_dir * L]
p_prism(bm, [(p.x, p.y) for p in pts], M_FLOOR, 400)
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
cut_M = obj_from_bm("cut_M", bm)

boolean(tcell, cut_T)
boolean(macro, cut_M)
boolean(tcell, cutter_cyls("holes_T", peg_holes_T, 2.0 + CLR))
ENTRY = [px_axis(455, 207, 2, ROD_Z), px_axis(722, 172, 2, ROD_Z)]
rod_ends = []
for s in (-1, 1):
    x_surf = T_C.x + s * T_RX * math.sqrt(max(0.0, 1 - ((ROD_Z - T_C.z) / T_RZ) ** 2 - ((ROD_Y - T_C.y) / T_RX) ** 2))
    rod_ends.append(x_surf - s * 14.0)
boolean(tcell, cutter_cyls("rodholes_T", [((s * 300, ROD_Y, ROD_Z), (e - s * 0.8, ROD_Y, ROD_Z)) for s, e in zip((-1, 1), rod_ends)],
                           ROD_R + CLR))
boolean(macro, cutter_cyls("holes_M", peg_holes_M, 2.0 + CLR))
boolean(macro, cutter_cyls("rodclear", [((s * ROD_X, ROD_Y, 0), (s * ROD_X, ROD_Y, 300)) for s in (-1, 1)], ROD_R + 0.8))
boolean(macro, cutter_cyls("posttops", [((p.x, p.y, 0), (p.x, p.y, top + 4)) for p, top in POSTS], ROD_R + CLR))

# ================================================================ organelles (pixel-driven)
log("organelles")


def frame(origin, normal):
    N = Vector(normal).normalized()
    Y = Vector((0, 0, 1)) if abs(N.z) < 0.9 else Vector((0, 1, 0))
    X = Y.cross(N).normalized()
    Y = N.cross(X)
    o = Vector(origin)
    return Matrix(((X.x, Y.x, N.x, o.x), (X.y, Y.y, N.y, o.y), (X.z, Y.z, N.z, o.z), (0, 0, 0, 1)))


def face_point(face, u, v):
    o, n = face
    return px_plane(u, v, n, o)


def at(face, u, v, ang=0.0):
    o, n = face
    return frame(face_point(face, u, v), n) @ Matrix.Rotation(math.radians(ang), 4, 'Z')


groups = {}
grooves = {}


def G(prefix, name):
    return groups.setdefault(prefix + name, bmesh.new())


def GR(prefix, name):
    return grooves.setdefault(prefix + name, bmesh.new())


def mito(prefix, M, Lm, W, color="Mitochondria"):
    """cut-open mitochondrion: outer membrane cup + folded cristae inside (two colours)"""
    p_ellipsoid(G(prefix, color), M, Lm / 2, W / 2, W * 0.45, 28, 14)
    p_ellipsoid(GR(prefix, color), M @ Matrix.Translation((0, 0, W * 0.2)), Lm / 2 - 1.3, W / 2 - 1.3, W * 0.45, 28, 14)
    n = max(4, int(Lm / 3.2))
    for k in range(n):
        x = -Lm / 2 * 0.72 + Lm * 0.72 * k / (n - 1)
        yy = (W / 2 - 1.0) * math.sqrt(max(0.05, 1 - (2 * x / Lm) ** 2))
        pts = [(x + 0.9 * math.sin(j * 1.3), -yy + 2 * yy * j / 8) for j in range(9)]
        p_strip(G(prefix, "Cristae"), pts, 0.9, -1.0, W * 0.36, M)


def dot(prefix, M, r, color):
    p_ellipsoid(G(prefix, color), M, r, r, r, 14, 7)


def relief_arcs(prefix, color, M, r0, n, a0, a1, w=2.4, gap=1.4, h=3.0):
    for i in range(n):
        p_strip(G(prefix, color), arc_pts(0, 0, r0 + i * (w + gap), a0 + i * 2, a1 - i * 2), w, -2.5, h, M)


def p_shell_patch(bm, C, R, t, az0, az1, el0, el1, nu=28, nv=14):
    def P_(r, i, j):
        az = math.radians(az0 + (az1 - az0) * i / nu)
        el = math.radians(el0 + (el1 - el0) * j / nv)
        return bm.verts.new(C + Vector((math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el))) * r)
    O = [[P_(R + t / 2, i, j) for j in range(nv + 1)] for i in range(nu + 1)]
    I = [[P_(R - t / 2, i, j) for j in range(nv + 1)] for i in range(nu + 1)]
    for i in range(nu):
        for j in range(nv):
            bm.faces.new((O[i][j], O[i + 1][j], O[i + 1][j + 1], O[i][j + 1]))
            bm.faces.new((I[i][j], I[i][j + 1], I[i + 1][j + 1], I[i + 1][j]))
    for i in range(nu):
        bm.faces.new((O[i][0], I[i][0], I[i + 1][0], O[i + 1][0]))
        bm.faces.new((O[i][nv], O[i + 1][nv], I[i + 1][nv], I[i][nv]))
    for j in range(nv):
        bm.faces.new((O[0][j], O[0][j + 1], I[0][j + 1], I[0][j]))
        bm.faces.new((O[nu][j], I[nu][j], I[nu][j + 1], O[nu][j + 1]))


def cisternae(prefix, color, C, r0, n, az0, az1, el0, el1, t=2.2, gap=1.3):
    for i in range(n):
        shrink = i * 3.0
        p_shell_patch(G(prefix, color), C, r0 + i * (t + gap), t, az0 + shrink, az1 - shrink, el0 + shrink * 0.6, el1 - shrink * 0.6)
    # thin spine joining the stack at its back so it prints as one piece
    p_shell_patch(G(prefix, color), C, r0 + (n - 1) * (t + gap) / 2, (n - 1) * (t + gap) + t, az0 + (az1 - az0) * 0.45,
                  az0 + (az1 - az0) * 0.55, el0, el1)


def standing_stack(prefix, color, centre, z0, r_in, n, az0, az1, h, w=2.6, gap=1.3, top_bulge=0.0):
    """concentric curved cisternae standing on a floor (solid at the base so it prints)"""
    M = Matrix.Translation((centre.x, centre.y, z0))
    for i in range(n):
        r = r_in + i * (w + gap)
        p_strip(G(prefix, color), arc_pts(0, 0, r, az0, az1, 36), w, -2.0, h - i * 1.2, M)
    p_strip(G(prefix, color), arc_pts(0, 0, r_in + (n - 1) * (w + gap) / 2, az0, az1, 36), (n - 1) * (w + gap) + w, -2.0, 2.0, M)


# ---- T cell interior (faces of the V-cut) ----
face_TL = (T_C, ta)        # left face (normal faces right-front)
face_TR = (T_C, tb)        # right face
TN_R = 44 * MM_PX
TN_C = px_plane(595, 177, VIEW, T_C + VIEW * 12)
bm = bmesh.new()
p_ellipsoid(bm, Matrix.Translation(TN_C), TN_R, TN_R, TN_R, 64, 32)
t_nuc = obj_from_bm("T_Nucleus", bm, C_TC)
remesh(t_nuc, 0.4 / QUALITY)
displace(t_nuc, 3.0, 1.2)
displace(t_nuc, 9.0, 1.4)
smooth(t_nuc, 0.5, 1)
bm = bmesh.new()
p_ellipsoid(bm, Matrix.Translation(TN_C), TN_R + 0.3, TN_R + 0.3, TN_R + 0.3, 48, 24)
boolean(tcell, obj_from_bm("nuc_socket", bm))


def nuc_on_face(face):
    o, n = face
    q = TN_C - n * (TN_C - o).dot(n)
    return frame(q, n)


MTL = nuc_on_face(face_TL)
MTR = nuc_on_face(face_TR)
relief_arcs("T_", "ER", MTL, TN_R + 2.0, 5, 100, 190, w=2.0, gap=1.2)
relief_arcs("T_", "ER", MTR, TN_R + 2.0, 5, -88, -12, w=2.0, gap=1.2)
mito("T_", at(face_TR, 645, 123, 125), 22, 14)
mito("T_", at(face_TL, 552, 218, 80), 20, 12)
mito("T_", at(face_TL, 515, 120, 40), 15, 9)
mito("T_", at(face_TR, 690, 160, 95), 14, 8.5)
# Golgi stack on the right face, ribosomes along the ER, nucleolus, centrioles, lysosomes
relief_arcs("T_", "Golgi", at(face_TR, 690, 105, 0) @ Matrix.Translation((-14, -10, 0)), 9.0, 4, 30, 100, w=1.6, gap=1.0, h=2.2)
for M_, a0, a1 in ((MTL, 102, 188), (MTR, -86, -14)):
    for k in range(14):
        a = math.radians(a0 + (a1 - a0) * k / 13)
        r = TN_R + 2.0 + (k % 5) * 3.2 + 1.0
        dot("T_", M_ @ Matrix.Translation((r * math.cos(a), r * math.sin(a), 2.6)), 0.8, "Ribosomes")
nucleolus = TN_C + (VIEW * 0.85 + Vector((0.25, 0, 0.35))).normalized() * (TN_R - 2.5)
dot("T_", Matrix.Translation(nucleolus), 6.0, "Nucleolus")
Mc = at(face_TR, 640, 238)                                # pair of centrioles at right angles
p_cyl(G("T_", "Centrioles"), Mc @ Vector((-4.0, 0, 0.6)), Mc @ Vector((3.0, 0, 0.6)), 1.8, 9)
p_cyl(G("T_", "Centrioles"), Mc @ Vector((4.5, -3.0, 0.6)), Mc @ Vector((4.5, 3.5, 0.6)), 1.8, 9)
for (u, v, r) in ((660, 210, 3.4), (528, 190, 3.0)):
    dot("T_", at(face_TL if u < 600 else face_TR, u, v), r, "Lysosomes_dense")
for (u, v, r, c) in ((618, 90, 3.0, "Vesicles"), (568, 90, 2.4, "Granules"), (668, 165, 2.6, "Granules"), (530, 161, 2.4, "Vesicles"),
                     (575, 245, 2.4, "Lysosome"), (690, 225, 2.2, "Vesicles"), (540, 250, 2.0, "Granules"),
                     (595, 75, 2.0, "Vesicles"), (650, 80, 1.8, "Granules"), (705, 135, 2.0, "Vesicles"), (500, 150, 1.8, "Granules"),
                     (512, 210, 2.0, "Vesicles"), (600, 262, 1.8, "Vesicles"), (675, 240, 1.8, "Granules"), (545, 105, 1.6, "Vesicles")):
    face = face_TL if u < 600 else face_TR
    dot("T_", at(face, u, v), r, c)

# ---- macrophage interior ----
face_MB = (K, Vector((-back_dir.y, back_dir.x, 0)) if Vector((-back_dir.y, back_dir.x, 0)).dot(VIEW) > 0 else Vector((back_dir.y, -back_dir.x, 0)))
face_ML = (K, Vector((-left_dir.y, left_dir.x, 0)) if Vector((-left_dir.y, left_dir.x, 0)).dot(back_dir) > 0 else Vector((left_dir.y, -left_dir.x, 0)))
face_MF = (Vector((0, 0, M_FLOOR)), Vector((0, 0, 1)))
MN_R = 52 * MM_PX
MN_C = px_plane(607, 520, face_MB[1], face_MB[0] + face_MB[1] * 12)
MN_C.z = M_FLOOR + MN_R * 0.55                         # the floor cuts through the lower nucleus (photo)
bm = bmesh.new()
p_ellipsoid(bm, Matrix.Translation(MN_C), MN_R, MN_R, MN_R, 64, 32)
m_nuc = obj_from_bm("M_Nucleus", bm, C_MAC)
remesh(m_nuc, 0.35 / QUALITY)
brain(m_nuc, MN_C, MN_R, 8.0, 0.085, 2.8)
smooth(m_nuc, 0.5, 1)
boolean(m_nuc, cut_M, 'INTERSECT')

vaz = math.degrees(math.atan2(VIEW.y, VIEW.x))
cisternae("M_", "Golgi", MN_C, MN_R + 1.5, 5, vaz - 128, vaz - 58, -30, 68)
ER_AZ0, ER_AZ1 = vaz - 8, vaz + 100
for i in range(5):                                       # stacked sheets hugging the lower nucleus
    z0 = M_FLOOR + 1.5 + i * 3.6
    rz = math.sqrt(max(4.0, MN_R ** 2 - (z0 + 0.9 - MN_C.z) ** 2))
    r_in, r_out = rz - 1.0, rz + 15.0 - i * 1.0
    pts = arc_pts(MN_C.x, MN_C.y, (r_in + r_out) / 2, ER_AZ0 + i * 3, ER_AZ1 - i * 3, 36)
    p_strip(G("M_", "Rough_ER"), pts, r_out - r_in, z0, z0 + 1.9, Matrix())
    for x, y in arc_pts(MN_C.x, MN_C.y, r_out - 0.9, ER_AZ0 + i * 3 + 4, ER_AZ1 - i * 3 - 4, 12):
        dot("M_", Matrix.Translation((x, y, z0 + 2.0)), 0.85, "Rough_ER")
a_end = math.radians(ER_AZ1)
end_pts = [(MN_C.x + r * math.cos(a_end), MN_C.y + r * math.sin(a_end)) for r in (MN_R - 14, MN_R + 12)]
p_strip(G("M_", "Rough_ER"), end_pts, 2.0, M_FLOOR - 1, M_FLOOR + 1.5 + 4 * 3.6 + 1.9, Matrix())   # end wall joins the stack
mito("M_", at(face_MB, 672, 468, -32), 24, 15)
mito("M_", at(face_ML, 505, 455, 70), 15, 9)
mito("M_", at(face_MF, 700, 585, 15), 16, 9)
# smooth ER tubules on the back wall, dense lysosomes
for k in range(3):
    pts = [(x, 1.6 * math.sin(x / 3.2 + k)) for x in [-12 + 24 * j / 30 for j in range(31)]]
    p_strip(G("M_", "Smooth_ER"), pts, 1.6, -2.0, 2.0, at(face_MB, 735, 455 + k * 9, -20) @ Matrix.Translation((0, 0, 0)))
for (face, u, v, r) in ((face_MB, 742, 498, 4.2), (face_MF, 680, 575, 3.6), (face_ML, 488, 470, 3.6), (face_MB, 560, 440, 3.2)):
    dot("M_", at(face, u, v), r, "Lysosomes_dense")
mvb = at(face_MB, 712, 500)
p_torus(G("M_", "Vesicles_MVB"), mvb, 7.6, 1.9, 40, 12)
p_ellipsoid(G("M_", "Vesicles_MVB"), mvb, 7.0, 7.0, 1.2, 32, 8)
for k in range(7):
    a = k * 2 * math.pi / 7
    dot("M_", mvb @ Matrix.Translation((3.6 * math.cos(a), 3.6 * math.sin(a), 1.2)), 1.1, "Granules")
p_ellipsoid(G("M_", "Lysosome"), at(face_ML, 515, 496, 85), 13.5, 5.8, 4.5, 28, 14)
ph = Matrix.Translation(face_point(face_MF, 555, 571))
p_cyl(G("M_", "Phagosome"), ph @ Vector((0, 0, -2)), ph @ Vector((0, 0, 2.6)), 10.5, 48)
p_ellipsoid(G("M_", "Phagosome"), ph @ Matrix.Translation((0, 0, 2.6)), 7.5, 7.5, 1.4, 32, 8)
for (face, u, v, r, c) in ((face_MB, 625, 437, 2.8, "Vesicles"), (face_MB, 735, 522, 2.2, "Granules"), (face_MB, 700, 455, 2.0, "Granules"),
                           (face_MB, 760, 545, 2.6, "Vesicles"), (face_ML, 470, 525, 2.6, "Vesicles"), (face_ML, 490, 548, 2.0, "Granules"),
                           (face_MF, 595, 568, 2.0, "Granules"), (face_MF, 720, 565, 2.4, "Vesicles"), (face_MF, 505, 580, 2.0, "Granules"),
                           (face_MB, 680, 525, 1.8, "Vesicles"), (face_MB, 755, 470, 1.8, "Granules"), (face_MB, 655, 440, 1.6, "Vesicles"),
                           (face_ML, 515, 545, 1.8, "Vesicles"), (face_ML, 478, 500, 1.6, "Granules"), (face_MF, 640, 585, 1.8, "Vesicles"),
                           (face_MF, 750, 562, 1.6, "Granules"), (face_MF, 530, 588, 1.6, "Vesicles"), (face_MB, 590, 430, 1.6, "Granules")):
    dot("M_", at(face, u, v), r, c)

org_objs = []
for name, gbm in sorted(groups.items(), key=lambda kv: kv[0].endswith("Cristae")):
    coll_ = C_TC if name.startswith("T_") else C_MAC
    ob = obj_from_bm(name, gbm, coll_)
    remesh(ob, 0.3 / QUALITY)
    if name in grooves:
        boolean(ob, obj_from_bm("gr", grooves[name]))
    boolean(ob, cut_T if name.startswith("T_") else cut_M, 'INTERSECT')
    if name.endswith("Cristae"):
        mobj = next((o for o in org_objs if o.name == name.replace("Cristae", "Mitochondria")), None)
        if mobj:
            boolean(ob, mobj)
    tree = BV_T if name.startswith("T_") else BV_M
    bad = sum(1 for v in list(ob.data.vertices)[::25] if not inside(tree, v.co, 0.0))
    if bad:
        log("  note: %s has %d sample points outside the cell" % (name, bad))
    org_objs.append(ob)

nl = next((o for o in org_objs if o.name == "T_Nucleolus"), None)
if nl:
    boolean(t_nuc, nl)                                   # nucleolus sits in a socket of the nucleus


def make_membrane(body, full, thick, core_name, coll, voxel):
    core0 = duplicate(full, core_name + "_offset")
    m = core0.modifiers.new("off", 'DISPLACE')
    m.strength, m.mid_level = -thick, 0.0
    apply_mods(core0)
    remesh(core0, voxel)
    smooth(core0, 0.5, 2)
    core = duplicate(core0, core_name, coll)
    boolean(core, body, 'INTERSECT')                     # cytoplasm keeps every cut and hole
    boolean(body, core0)                                 # body becomes the membrane shell
    return core, core0


def inclusions(name, core0, shell, n, rmin, rmax, coll):
    tree = bvh(core0)
    shell_tree = bvh(shell)
    bm = bmesh.new()
    placed = 0
    for v in random.sample(list(core0.data.vertices), min(len(core0.data.vertices), n * 30)):
        if placed >= n:
            break
        if v.normal.dot(VIEW) < 0.15:
            continue
        r = random.uniform(rmin, rmax)
        c = v.co + v.normal * 1.8
        if all(inside(shell_tree, c + d * r * 1.1, 0.0) for d in (Vector((1, 0, 0)), Vector((-1, 0, 0)), Vector((0, 1, 0)),
                                                                   Vector((0, -1, 0)), Vector((0, 0, 1)), Vector((0, 0, -1)))):
            p_ellipsoid(bm, Matrix.Translation(c), r, r, r, 16, 8)
            placed += 1
    ob = obj_from_bm(name, bm, coll)
    remesh(ob, 0.3)
    boolean(shell, ob)                                   # sockets in the membrane
    return ob


log("membranes")
m_core, m_core0 = make_membrane(macro, macro_full, 3.5, "Macrophage_Cytoplasm", C_MAC, 1.0 / QUALITY)
t_core, t_core0 = make_membrane(tcell, tcell_full, 4.0, "T_Cell_Cytoplasm", C_TC, 0.8 / QUALITY)
inclusions("M_Inclusions", m_core0, macro, 45, 1.1, 1.6, C_MAC)
inclusions("T_Inclusions", t_core0, tcell, 30, 1.1, 1.6, C_TC)


def mark_cut_faces(ob, planes):
    for poly in ob.data.polygons:
        c, n = poly.center, poly.normal
        for p0, pn in planes:
            pn = Vector(pn).normalized()
            if abs((c - Vector(p0)).dot(pn)) < 0.05 and abs(n.dot(pn)) > 0.995:
                poly.material_index = 1
                break


CUT_PLANES = {"T_Cell_Body": [(T_C, ta), (T_C, tb), (Vector((0, 0, T_FLOOR)), (0, 0, 1))],
              "Macrophage_Body": [(K, face_MB[1]), (K, face_ML[1]), (Vector((0, 0, M_FLOOR)), (0, 0, 1)), (far, -RIGHT_X)]}
CUT_PLANES["T_Cell_Cytoplasm"] = CUT_PLANES["T_Cell_Body"]
CUT_PLANES["Macrophage_Cytoplasm"] = CUT_PLANES["Macrophage_Body"]

# ================================================================ rods, posts, collars
log("rods / posts / collars")


def rod_path(s, bend_r=10.0):
    x0, end_x = s * ROD_X, rod_ends[(s + 1) // 2]
    pts = [Vector((x0, ROD_Y, ZT - 22)), Vector((x0, ROD_Y, ROD_Z - bend_r))]
    for k in range(1, 12):
        a = math.pi / 2 * k / 12
        pts.append(Vector((x0 - s * bend_r * (1 - math.cos(a)), ROD_Y, ROD_Z - bend_r + bend_r * math.sin(a))))
    pts.append(Vector((end_x, ROD_Y, ROD_Z)))
    return pts


rods = []
for i, s in enumerate((-1, 1)):
    bm = bmesh.new()
    p_tube(bm, rod_path(s), ROD_R, 28)
    rods.append(obj_from_bm("Rod_%s" % ("Left", "Right")[i], bm, C_ROD))
for i, (p, top) in enumerate(POSTS):
    bm = bmesh.new()
    p_cyl(bm, (p.x, p.y, ZT - 15), (p.x, p.y, top), ROD_R, 28)
    obj_from_bm("Post_%d" % (i + 1), bm, C_ROD)
bm = bmesh.new()
for s in (-1, 1):
    p_cyl(bm, (s * ROD_X, ROD_Y, ZT), (s * ROD_X, ROD_Y, ZT + 3.0), 5.6, 40)
    x_surf = rod_ends[(s + 1) // 2] + s * 14.0
    p_cyl(bm, (x_surf - s * 4, ROD_Y, ROD_Z), (x_surf + s * 5, ROD_Y, ROD_Z), 4.8, 40)
for p, top in POSTS:
    p_cyl(bm, (p.x, p.y, ZT), (p.x, p.y, ZT + 3.0), 5.6, 40)
    p_cyl(bm, (p.x, p.y, top - 2.5), (p.x, p.y, top + 0.5), 4.6, 40)
collars = obj_from_bm("Gold_Collars", bm, C_ROD)
remesh(collars, 0.25)
boolean(collars, cutter_cyls("collar_holes", [((s * ROD_X, ROD_Y, 0), (s * ROD_X, ROD_Y, 400)) for s in (-1, 1)] +
                             [((p.x, p.y, 0), (p.x, p.y, 200)) for p, t in POSTS] +
                             [((-300, ROD_Y, ROD_Z), (300, ROD_Y, ROD_Z))], ROD_R + 0.15))
boolean(collars, tcell)

# ================================================================ base
log("base")
BW, BD = BASE_W, BASE_D
tw, td = BW / 2 - PL_IN, BD / 2 - PL_IN
bm = bmesh.new()
for x, y, z in ((-BW / 2, -BD / 2, 0), (BW / 2, -BD / 2, 0), (BW / 2, BD / 2, 0), (-BW / 2, BD / 2, 0),
                (-tw, -td, PL_H), (tw, -td, PL_H), (tw, td, PL_H), (-tw, td, PL_H)):
    bm.verts.new((x, y, z))
bmesh.ops.convex_hull(bm, input=bm.verts)
bmesh.ops.dissolve_limit(bm, angle_limit=0.01, verts=bm.verts, edges=bm.edges)
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
base = obj_from_bm("Base", bm, C_BASE)
sw, sd = tw - SLAB_IN, td - SLAB_IN
bm = bmesh.new()
p_box(bm, (-sw, -sd, PL_H - 1.0), (sw, sd, ZT))
slab = obj_from_bm("slab", bm)
bv = slab.modifiers.new("bevel", 'BEVEL')
bv.width, bv.segments, bv.limit_method = 1.2, 2, 'ANGLE'
apply_mods(slab)
boolean(base, slab, 'UNION')

# plaque on the sloped front face (position read from the photo: it sits right of centre)
FRONT_N = Vector((0, -PL_H, PL_IN)).normalized()
FRONT_P = Vector((0, -BD / 2, 0))
c4 = [px_plane(u, v, FRONT_N, FRONT_P) for u, v in ((567, 752), (850, 718), (573, 812), (855, 780))]
PLQ_C = sum(c4, Vector()) / 4
PLQ_W = ((c4[1] - c4[0]).length + (c4[3] - c4[2]).length) / 2
PLQ_H = min(((c4[2] - c4[0]).length + (c4[3] - c4[1]).length) / 2, PL_H / math.cos(math.atan2(PL_IN, PL_H)) - 4)
M_PLQ = Matrix.Translation(PLQ_C) @ frame(Vector(), FRONT_N).to_3x3().to_4x4()
bm = bmesh.new()
p_box(bm, (-PLQ_W / 2 - 0.3, -PLQ_H / 2 - 0.3, -1.0), (PLQ_W / 2 + 0.3, PLQ_H / 2 + 0.3, 6), M_PLQ)
for s in (-1, 1):
    p_cyl(bm, (s * ROD_X, ROD_Y, ZT - 22.5), (s * ROD_X, ROD_Y, ZT + 1), ROD_R + CLR)
for p, top in POSTS:
    p_cyl(bm, (p.x, p.y, ZT - 15.5), (p.x, p.y, ZT + 1), ROD_R + CLR)
for y in (-45, 60):
    p_cyl(bm, (-16, y, 16), (16, y, 16), 3.0 + 0.15)
boolean(base, obj_from_bm("base_cut", bm))
base_L = duplicate(base, "Base_Left", C_BASE)
base_R = duplicate(base, "Base_Right", C_BASE)
boolean(base_L, cutter_box("hL", (-300, -300, -10), (0, 300, 100)), 'INTERSECT')
boolean(base_R, cutter_box("hR", (0, -300, -10), (300, 300, 100)), 'INTERSECT')
kill(base)

# ================================================================ plates, text, leaders
log("plaque / labels")


def plate(name, M, w, h, lines, sizes, gap, t=3.0, border=False):
    bm = bmesh.new()
    p_rounded_slab(bm, w, h, t - 0.8, 1.6, M, -t / 2)
    p_rounded_slab(bm, w - 1.6, h - 1.6, 0.8, 1.0, M, t / 2 - 0.8)       # bevelled face
    pl = obj_from_bm(name + "_Plate", bm, C_LAB)
    remesh(pl, 0.25)
    bm = bmesh.new()
    top = M @ Matrix.Translation((0, 0, t / 2))
    n = len(lines)
    for i, (txt, sz) in enumerate(zip(lines, sizes)):
        y = (n - 1) / 2 * gap - i * gap
        text_into(bm, txt, sz, top @ Matrix.Translation((0, y, 0)), height=0.8, max_w=w - 5)
    return pl, obj_from_bm(name + "_Text", bm, C_LAB)


plate("Plaque", M_PLQ @ Matrix.Translation((0, 0, 0.5)), PLQ_W, PLQ_H,
      ["ATTACHMENT OF HELPER T LYMPHOCYTE", "TO MACROPHAGE VIA MHC CLASS II", "3D Educational Anatomical Model"],
      [PLQ_H * 0.31, PLQ_H * 0.31, PLQ_H * 0.21], PLQ_H * 0.29, t=2.0)
bm = bmesh.new()
for su, sv in ((-1, 1), (1, 1), (-1, -1), (1, -1)):
    p_ellipsoid(bm, M_PLQ @ Matrix.Translation((su * (PLQ_W / 2 - 4), sv * (PLQ_H / 2 - 4), 1.5)), 1.6, 1.6, 0.9, 16, 8)
obj_from_bm("Plaque_Screws", bm, C_LAB)

LAB_N = VIEW                                             # plates face the viewer, as in the photo
def lab_plane(side):
    return Vector((side * ROD_X, ROD_Y, 0)) + VIEW * (ROD_R + 4.0)
LABELS = [  # name, rect in photo (u0, v0, u1, v1), lines, leader start px, leader end px, target object, on rod
    ("helper", (200, 105, 395, 165), ["Helper T Lymphocyte", "(CD4+)"], (395, 150), (473, 157), "tcell", None),
    ("tcr", (245, 275, 475, 312), ["T-Cell Receptor (TCR)"], (475, 296), (536, 316), "tcr", -1),
    ("mhc", (258, 340, 410, 395), ["MHC Class II", "& Antigenic Peptide"], (410, 371), (538, 388), "mhc", -1),
    ("macro", (195, 460, 318, 500), ["Macrophage"], (318, 484), (458, 507), "macro", None),
    ("cd4", (755, 240, 905, 277), ["CD4 Co-receptor"], (755, 261), (607, 322), "cd4", 1),
    ("cd28", (755, 305, 965, 362), ["CD28 / B7 (CD80/CD86)", "Co-stimulation"], (755, 340), (679, 350), "b7", 1),
    ("syn", (808, 397, 1010, 437), ["Immunological Synapse"], (808, 416), (688, 386), "macro", 1),
]
OBJ = {"tcell": tcell, "tcr": tcr, "mhc": mhc, "macro": macro, "cd4": cd4, "b7": b7}
TREES = {k: bvh(v) for k, v in OBJ.items()}
for i, (nm, (u0, v0, u1, v1), lines, ls, le, tgt, rod) in enumerate(LABELS):
    LAB_P = lab_plane(rod if rod is not None else -1)
    a = px_plane(u0, v0, LAB_N, LAB_P)
    b = px_plane(u1, v1, LAB_N, LAB_P)
    c = (a + b) / 2
    X = Vector((0, 0, 1)).cross(LAB_N).normalized()
    w = abs((b - a).dot(X))
    h = abs(a.z - b.z)
    M = Matrix.Translation(c) @ frame(Vector(), LAB_N).to_3x3().to_4x4()
    sz = h * (0.42 if len(lines) > 1 else 0.62)
    plate("Label_%d_%s" % (i + 1, nm), M, w, h, lines, [sz] * len(lines), h * 0.42, t=3.2)
    if rod is not None:                                   # snap clip behind the plate
        rx = rod * ROD_X
        bm = bmesh.new()
        p_cyl(bm, (rx, ROD_Y, c.z - 6), (rx, ROD_Y, c.z + 6), ROD_R + 2.2, 40)
        back = c - LAB_N * 1.6
        p_cyl(bm, back, Vector((rx, ROD_Y, c.z)) + LAB_N * 0.5, 4.0, 24)
        clip = obj_from_bm("Label_%d_Clip" % (i + 1), bm, C_LAB)
        remesh(clip, 0.3)
        bm = bmesh.new()
        p_cyl(bm, (rx, ROD_Y, c.z - 8), (rx, ROD_Y, c.z + 8), ROD_R + 0.12, 40)
        p_box(bm, (-2.4, -8, 1.5), (2.4, 8, 12), Matrix.Translation((rx, ROD_Y, c.z)) @ frame(Vector(), -LAB_N).to_3x3().to_4x4())
        boolean(clip, obj_from_bm("clipcut", bm))
    start = px_plane(ls[0], ls[1], LAB_N, LAB_P - LAB_N * 0.0)
    end = px_hit(le[0], le[1], TREES[tgt])
    if end is None:
        end = px_axis(le[0], le[1], 1, PY)
    bm = bmesh.new()
    p_cyl(bm, start, end, 0.8, 12)
    M_end = Matrix.Translation(end) @ frame(Vector(), LAB_N).to_3x3().to_4x4()
    p_cyl(bm, M_end @ Vector((0, 0, -0.5)), M_end @ Vector((0, 0, 1.2)), 2.6, 24)
    obj_from_bm("Wire_%s" % nm, bm, C_WIRE)

for ob in list(C_TMP.objects):
    kill(ob)
bpy.data.collections.remove(C_TMP)

# ================================================================ materials
log("materials")


def mat(name, col, metal=0.0, rough=0.4, sss=0.0, trans=0.0, emit=0.0, coat=0.0, alpha=1.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    b = m.node_tree.nodes.get("Principled BSDF")
    vals = {"Base Color": (*col, 1), "Metallic": metal, "Roughness": rough, "Subsurface Weight": sss,
            "Subsurface Scale": 6.0, "Transmission Weight": trans, "Coat Weight": coat,
            "Emission Color": (*col, 1), "Emission Strength": emit, "Alpha": alpha}
    if sss:
        vals["Subsurface Radius"] = (1.0, 0.7, 0.9)
    for k, v in vals.items():
        if k in b.inputs:
            b.inputs[k].default_value = v
    m.diffuse_color = (*col, 1)
    return m


def membrane_mat(name, col, absorb, density):
    m = mat(name, col, rough=0.05, trans=0.93, coat=1.0)
    b = m.node_tree.nodes.get("Principled BSDF")
    for k, v in (("IOR", 1.38), ("Coat Roughness", 0.03), ("Specular IOR Level", 0.6)):
        if k in b.inputs:
            b.inputs[k].default_value = v
    nt = m.node_tree
    out = nt.nodes.get("Material Output")
    va = nt.nodes.get("Volume Absorption") or nt.nodes.new("ShaderNodeVolumeAbsorption")
    va.inputs["Color"].default_value = (*absorb, 1)
    va.inputs["Density"].default_value = density
    nt.links.new(va.outputs[0], out.inputs["Volume"])
    return m


GOLD = mat("Gold (brushed)", (0.86, 0.66, 0.34), metal=1.0, rough=0.3)
PLATE = mat("Plate gold (satin)", (0.9, 0.78, 0.55), metal=0.85, rough=0.35)
MATS = {
    "Macrophage_Body": membrane_mat("Macrophage membrane (glossy translucent)", (0.85, 0.74, 1.0), (0.7, 0.55, 0.95), 0.035),
    "T_Cell_Body": membrane_mat("T cell membrane (glossy translucent)", (1.0, 0.72, 0.42), (1.0, 0.5, 0.15), 0.04),
    "Macrophage_Cytoplasm": mat("Macrophage cytoplasm", (0.62, 0.46, 0.86), rough=0.3, sss=0.45),
    "T_Cell_Cytoplasm": mat("T cell cytoplasm", (1.0, 0.42, 0.06), rough=0.3, sss=0.4),
    "Cristae": mat("Mitochondrial cristae (deep red)", (0.42, 0.06, 0.04), rough=0.35),
    "Smooth_ER": mat("Smooth ER (pale violet)", (0.62, 0.5, 0.9), rough=0.3),
    "Ribosomes": mat("Ribosomes (dark red)", (0.45, 0.07, 0.05), rough=0.35),
    "Nucleolus": mat("Nucleolus (dark brown)", (0.16, 0.07, 0.03), rough=0.4),
    "Centrioles": mat("Centrioles (amber)", (0.85, 0.55, 0.15), rough=0.3),
    "Lysosomes_dense": mat("Lysosomes (plum)", (0.45, 0.1, 0.32), rough=0.25, coat=0.8),
    "M_Inclusions": mat("Macrophage inclusions (magenta)", (0.55, 0.12, 0.45), rough=0.3),
    "T_Inclusions": mat("T cell inclusions (yellow)", (0.95, 0.65, 0.12), rough=0.3),
    "T_Golgi": mat("T Golgi (copper)", (0.65, 0.22, 0.1), rough=0.35),
    "T_Nucleus": mat("T nucleus (tan)", (0.33, 0.18, 0.09), rough=0.45),
    "M_Nucleus": mat("M nucleus (violet)", (0.5, 0.33, 0.82), rough=0.4, sss=0.2),
    "Mitochondria": mat("Mitochondria (rust)", (0.62, 0.2, 0.08), rough=0.35),
    "T_ER": mat("T ER (copper)", (0.72, 0.3, 0.16), rough=0.35),
    "Rough_ER": mat("Rough ER (violet)", (0.45, 0.32, 0.85), rough=0.3),
    "Golgi": mat("Golgi (violet)", (0.42, 0.3, 0.86), rough=0.3),
    "Vesicles_MVB": mat("MVB (mauve)", (0.75, 0.4, 0.75), rough=0.3),
    "Vesicles": mat("Vesicles (yellow)", (1.0, 0.72, 0.15), rough=0.3),
    "Granules": mat("Granules (red)", (0.8, 0.1, 0.12), rough=0.3),
    "Lysosome": mat("Lysosome (green)", (0.3, 0.6, 0.2), rough=0.3),
    "Phagosome": mat("Phagosome (orange)", (0.88, 0.45, 0.2), rough=0.4),
    "TCR": mat("TCR (blue)", (0.03, 0.1, 0.7), rough=0.25, coat=0.8),
    "MHC_II": mat("MHC-II (green)", (0.06, 0.26, 0.02), rough=0.25, coat=0.8),
    "Antigen_Peptide": mat("Peptide (glowing)", (1.0, 0.38, 0.08), rough=0.2, emit=2.2),
    "CD4": mat("CD4 (red)", (0.75, 0.02, 0.03), rough=0.25, coat=0.8),
    "CD28": mat("CD28 (yellow)", (0.95, 0.75, 0.05), rough=0.25, coat=0.8),
    "B7_CD80_CD86": mat("B7 (teal)", (0.0, 0.45, 0.55), rough=0.25, coat=0.8),
    "Gold_Collars": GOLD, "Plaque_Screws": GOLD, "Plate": PLATE, "Clip": PLATE,
    "Base": mat("Base (black wood)", (0.012, 0.01, 0.01), rough=0.35, coat=0.4),
    "Rod": mat("Rods (steel)", (0.85, 0.85, 0.88), metal=1.0, rough=0.15),
    "Post": mat("Rods (steel)", (0.85, 0.85, 0.88), metal=1.0, rough=0.15),
    "Wire": mat("Leader wire (dark brass)", (0.45, 0.36, 0.2), metal=1.0, rough=0.4),
    "Text": mat("Text (black)", (0.01, 0.01, 0.01), rough=0.5),
}
PRINT_COLLS = [C_BASE, C_MAC, C_TC, C_PROT, C_ROD, C_LAB, C_WIRE]
CYTO = {"Macrophage_Body": mat("Macrophage membrane rim (cut)", (0.7, 0.55, 0.9), rough=0.15, trans=0.6, coat=1.0),
        "T_Cell_Body": mat("T cell membrane rim (cut)", (1.0, 0.7, 0.45), rough=0.15, trans=0.6, coat=1.0),
        "Macrophage_Cytoplasm": mat("Macrophage cytoplasm (cut face)", (0.46, 0.35, 0.58), rough=0.35, sss=0.25),
        "T_Cell_Cytoplasm": mat("T cell cytoplasm (cut face)", (0.7, 0.36, 0.13), rough=0.35, sss=0.25)}
for c in PRINT_COLLS:
    for ob in c.objects:
        key = ob.name if ob.name in ("T_ER", "T_Golgi") else next((k for k in sorted(MATS, key=len, reverse=True) if k in ob.name), None)
        if key:
            ob.data.materials.clear()
            ob.data.materials.append(MATS[key])
            if ob.name in CYTO:
                ob.data.materials.append(CYTO[ob.name])
                mark_cut_faces(ob, CUT_PLANES[ob.name])        # after the slots exist (clear() resets indices)
        for p in ob.data.polygons:
            p.use_smooth = ob.name.split("_")[0] not in ("Base",) and p.material_index == 0

# ================================================================ report
log("checking meshes")
report = []
mins, maxs = Vector((1e9,) * 3), Vector((-1e9,) * 3)
for c in PRINT_COLLS:
    for ob in c.objects:
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        nm = sum(1 for e in bm.edges if not e.is_manifold)
        bm.free()
        dims = ob.dimensions
        report.append("%-28s %7.1f x %6.1f x %6.1f mm  tris=%7d  non-manifold-edges=%d" %
                      (ob.name, dims.x, dims.y, dims.z, sum(len(p.vertices) - 2 for p in ob.data.polygons), nm))
        for v in ob.data.vertices:
            for k in range(3):
                mins[k] = min(mins[k], v.co[k])
                maxs[k] = max(maxs[k], v.co[k])
print("\n".join(report))
log("assembly size: %.1f x %.1f x %.1f mm" % tuple(maxs - mins))


# ================================================================ STL export
def write_stl(ob, path):
    me = ob.data
    me.calc_loop_triangles()
    mw = ob.matrix_world
    with open(path, "wb") as fh:
        fh.write(b"immune synapse model".ljust(80, b" "))
        fh.write(struct.pack("<I", len(me.loop_triangles)))
        for t in me.loop_triangles:
            vs = [mw @ me.vertices[i].co for i in t.vertices]
            n = (vs[1] - vs[0]).cross(vs[2] - vs[0]).normalized()
            fh.write(struct.pack("<12fH", n.x, n.y, n.z, *vs[0], *vs[1], *vs[2], 0))


if EXPORT_DIR:
    d = bpy.path.abspath(EXPORT_DIR)
    os.makedirs(d, exist_ok=True)
    for c in PRINT_COLLS:
        for ob in c.objects:
            write_stl(ob, os.path.join(d, "%s__%s.stl" % (c.name, ob.name)))
    # the macrophage is ~310 mm wide: also export it in two halves with dowel holes (fits a 250 x 210 bed)
    halves = []
    for src, nm, lo, hi in ((macro, "Macrophage_Body_PART_L", (-400, -400, -10), (M_SPLIT_X, 400, 400)),
                            (macro, "Macrophage_Body_PART_R", (M_SPLIT_X, -400, -10), (400, 400, 400)),
                            (m_core, "Macrophage_Cytoplasm_PART_L", (-400, -400, -10), (M_SPLIT_X, 400, 400)),
                            (m_core, "Macrophage_Cytoplasm_PART_R", (M_SPLIT_X, -400, -10), (400, 400, 400))):
        h = duplicate(src, nm, C_SCN)
        cb = bmesh.new()
        p_box(cb, lo, hi)
        cut = obj_from_bm("half", cb, C_SCN)
        boolean(h, cut, 'INTERSECT')
        kill(cut)
        dw = bmesh.new()
        for y, z in ((-10, 80), (30, 110)):
            p_cyl(dw, (M_SPLIT_X - 12, y, z), (M_SPLIT_X + 12, y, z), 3.0 + 0.15, 24)
        dwo = obj_from_bm("dowels", dw, C_SCN)
        boolean(h, dwo)
        kill(dwo)
        write_stl(h, os.path.join(d, "02_Macrophage__%s.stl" % nm))
        report.append("%-28s %7.1f x %6.1f x %6.1f mm (print split)" % (nm, *h.dimensions))
        kill(h)
    with open(os.path.join(d, "mesh_report.txt"), "w") as fh:
        fh.write("\n".join(report) + "\n")
    log("STL files written to", d)

# ================================================================ render scene (calibrated to the photo)
bm = bmesh.new()
p_box(bm, (-1500, -1200, -40), (1500, 480, -0.01))
obj_from_bm("Table", bm, C_SCN).data.materials.append(mat("Table (walnut)", (0.1, 0.045, 0.025), rough=0.35, coat=0.5))
bm = bmesh.new()
p_box(bm, (-3000, 480, -40), (3000, 500, 3000))
obj_from_bm("Wall", bm, C_SCN).data.materials.append(mat("Wall", (0.2, 0.2, 0.19), rough=0.9))
cam_d = bpy.data.cameras.new("Camera")
cam_d.lens, cam_d.sensor_width, cam_d.sensor_fit = CAM_LENS, 36.0, 'HORIZONTAL'
cam_d.clip_start, cam_d.clip_end = 100, 20000
cam = bpy.data.objects.new("Camera", cam_d)
C_SCN.objects.link(cam)
cam.location, cam.rotation_euler = CAM_LOC, CAM_ROT
scene.camera = cam
for nm, rot, en in (("Key", (math.radians(40), 0, math.radians(-30)), 3.0),
                    ("Fill", (math.radians(60), 0, math.radians(60)), 1.0),
                    ("Rim", (math.radians(-50), 0, math.radians(175)), 2.0)):
    ld = bpy.data.lights.new(nm, 'SUN')
    ld.energy, ld.angle = en, math.radians(15)
    lo = bpy.data.objects.new(nm, ld)
    lo.rotation_euler = rot
    C_SCN.objects.link(lo)
world = scene.world or bpy.data.worlds.new("World")
scene.world = world
try:
    world.use_nodes = True
except Exception:
    pass
bg = world.node_tree.nodes.get("Background")
if bg:
    bg.inputs[0].default_value = (0.35, 0.35, 0.36, 1)
    bg.inputs[1].default_value = 0.8
scene.render.engine = 'CYCLES'
scene.cycles.samples = SAMPLES
scene.cycles.use_denoising = True
scene.cycles.max_bounces = 16
scene.cycles.transmission_bounces = 16
scene.cycles.volume_bounces = 2
scene.cycles.blur_glossy = 1.0                           # no sparkling fireflies on the glossy membranes
scene.cycles.sample_clamp_indirect = 6.0
RES_PCT = int(argv[argv.index("--respct") + 1]) if "--respct" in argv else 100
scene.render.resolution_percentage = RES_PCT
scene.render.resolution_x, scene.render.resolution_y = IMG_W, IMG_H
scene.view_settings.exposure = -0.35
if SAVE_BLEND:
    bpy.ops.wm.save_as_mainfile(filepath=bpy.path.abspath(SAVE_BLEND))
    log("saved", SAVE_BLEND)
if RENDER_PATH:
    scene.render.filepath = bpy.path.abspath(RENDER_PATH)
    log("rendering ...")
    bpy.ops.render.render(write_still=True)
    log("render written", RENDER_PATH)
log("done")
