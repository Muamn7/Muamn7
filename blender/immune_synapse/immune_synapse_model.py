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
FONT_CANDIDATES = [r"C:\Windows\Fonts\arialbd.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
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
from mathutils import noise as mnoise

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
    """vertical prism from a convex CCW polygon (list of (x, y))"""
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
    """winding gyri / sulci from iso-lines of smooth noise"""
    for v in ob.data.vertices:
        p = v.co - centre
        n = mnoise.noise(p * sc) + 0.5 * mnoise.noise(p * sc * 2.1 + Vector((5, 1, 3)))
        s = abs(math.sin(n * freq))
        v.co = centre + p.normalized() * (r - depth + depth * s ** 0.4)
    ob.data.update()


def fit_xy(ob, max_x, max_y, centre):
    xs = [v.co.x for v in ob.data.vertices]
    ys = [v.co.y for v in ob.data.vertices]
    f = min(1.0, max_x / (max(xs) - min(xs)), max_y / (max(ys) - min(ys)))
    if f < 1.0:
        for v in ob.data.vertices:
            v.co.x = centre.x + (v.co.x - centre.x) * f
            v.co.y = centre.y + (v.co.y - centre.y) * f
        ob.data.update()
        log("  scaled %s by %.3f in XY to fit the print bed" % (ob.name, f))


# ================================================================ layout
BASE_W, BASE_D, BASE_H = 400.0, 246.0, 34.0
M_C = Vector((0, 8, 112))
MRX, MRY, MRZ = 88, 66, 64
M_FLOOR = 62.0                       # flat underside of the macrophage (print face)
M_MAX_X, M_MAX_Y = 246.0, 204.0      # macrophage must fit a 250 x 210 bed
T_R = 57.0
PY = 12.0                            # plane of the receptor complexes
GAP = 68.0                           # membrane-to-membrane distance at the TCR
ROD_XY = [Vector((-128, 26)), Vector((128, 26))]
ROD_BOTTOM = 12.0
POSTS = [Vector((-34, -10)), Vector((34, -10)), Vector((-34, 30)), Vector((34, 30))]
M_NOTCH = (-30.0, 60.0, 94.0)        # back wall from x=-30..60 (y=0), 45 deg side walls, floor z=94

# ================================================================ macrophage
log("macrophage body")
els = [E_ell(M_C, MRX, MRY, MRZ)]
for i in range(22):
    a = random.uniform(0, 2 * math.pi)
    rr = random.uniform(0.2, 0.85)
    p = M_C + Vector((MRX * rr * math.cos(a), MRY * rr * math.sin(a), 0))
    p.z = M_C.z + MRZ * math.sqrt(max(0.0, 1 - rr * rr)) - random.uniform(8, 12)
    els.append(E_ball(p, random.uniform(9, 15)))

ROD_ANG = [math.degrees(math.atan2(xy.y - M_C.y, xy.x - M_C.x)) for xy in ROD_XY]


def pod(ang, z0, L, tilt, r0, tip, inset):
    a = math.radians(ang)
    f = math.sqrt(max(0.05, 1 - ((z0 - M_C.z) / MRZ) ** 2))
    start = Vector((M_C.x + inset * MRX * f * math.cos(a), M_C.y + inset * MRY * f * math.sin(a), z0))
    dirv = Vector((math.cos(a), math.sin(a), math.tan(math.radians(tilt)))).normalized()
    side = Vector((-math.sin(a), math.cos(a), 0)) * random.uniform(-0.35, 0.35)
    while True:
        tipp = start + dirv * L * 0.55 + (dirv + side).normalized() * L * 0.45 + Vector((0, 0, -0.08 * L))
        if (abs(tipp.x) < M_MAX_X / 2 - tip - 4 and -M_MAX_Y / 2 + tip + 4 < tipp.y < M_MAX_Y / 2 + tip - 2
                and tipp.z > M_FLOOR + tip + 2) or L < 8:
            break
        L -= 2
    n = max(8, int(L / 2.0))
    ctrl = start + dirv * L * 0.55
    wave = Vector((-math.sin(a), math.cos(a), 0)) * random.uniform(-3.5, 3.5)
    for k in range(n + 1):
        t = k / n
        p = (1 - t) ** 2 * start + 2 * (1 - t) * t * ctrl + t * t * tipp + wave * math.sin(math.pi * t) + Vector((0, 0, 2.5 * math.sin(2 * math.pi * t)))
        r = r0 * (1 - t) ** 0.75 + tip * t
        els.append(E_ball(p, r * 0.74))
    els.append(E_ball(tipp, tip * 0.95))                 # rounded bulb tip


k = 0
for i in range(16):                                      # finger-like pseudopodia around the equator
    ang = i * 22.5 + random.uniform(-5, 5)
    if min(abs((ang - ra + 180) % 360 - 180) for ra in ROD_ANG) < 8:
        continue
    pod(ang, random.uniform(92, 106), random.uniform(46, 60), random.uniform(-8, 8), random.uniform(11.5, 13), 6.4, 0.86)
for i in range(10):                                      # pseudopodia on the upper dome
    ang = i * 36 + 18 + random.uniform(-10, 10)
    pod(ang, random.uniform(126, 146), random.uniform(30, 40), random.uniform(18, 40), random.uniform(9, 10.5), 5.8, 0.84)

macro = metaball_object("Macrophage_Body", els, 1.6, C_MAC)
remesh(macro, 1.0 / QUALITY)
displace(macro, 18.0, 3.0)
smooth(macro, 0.5, 2)
displace(macro, 5.0, 1.0)
smooth(macro, 0.5, 2)
fit_xy(macro, M_MAX_X, M_MAX_Y, M_C)
macro_full = duplicate(macro, "macro_full")
BV_M = bvh(macro_full)


def z_mem_mac(x, y=PY):
    return BV_M.ray_cast(Vector((x, y, 400)), Vector((0, 0, -1)))[0].z


# ================================================================ T cell
X0 = -30.0                                               # TCR / MHC-II column
Z_T = z_mem_mac(X0) + GAP + math.sqrt(T_R ** 2 - X0 ** 2 - PY ** 2)
T_C = Vector((0, 0, Z_T))
ROD_Z = Z_T + 18.0
T_FLOOR = Z_T - 40.0
log("T cell body (centre z = %.1f)" % Z_T)


def rod_entry_x():
    dy, dz = ROD_XY[0].y - T_C.y, ROD_Z - T_C.z
    return math.sqrt(T_R ** 2 - dy ** 2 - dz ** 2)


ENTRY_X = rod_entry_x()
bm = bmesh.new()
p_ellipsoid(bm, Matrix.Translation(T_C), T_R, T_R, T_R, 96, 48)
N_SP = 150
ga = math.pi * (3 - math.sqrt(5))
rod_dirs = [Vector((s * ENTRY_X, ROD_XY[0].y, ROD_Z - Z_T)).normalized() for s in (-1, 1)]
for i in range(N_SP):
    z = 1 - 2 * (i + 0.5) / N_SP
    rr = math.sqrt(1 - z * z)
    d = Vector((rr * math.cos(ga * i), rr * math.sin(ga * i), z))
    d = (d + Vector([random.uniform(-0.05, 0.05) for _ in range(3)])).normalized()
    if d.z < -0.5 or any(d.angle(rd) < 0.32 for rd in rod_dirs):
        continue
    p_cyl(bm, T_C + d * (T_R - 4), T_C + d * (T_R + random.uniform(7, 10)), random.uniform(4.3, 5.3), 16, r2=1.1)
tcell = obj_from_bm("T_Cell_Body", bm, C_TC)
remesh(tcell, 0.7 / QUALITY)
smooth(tcell, 0.5, 2)
displace(tcell, 9.0, 2.0)
displace(tcell, 3.5, 0.8)
smooth(tcell, 0.4, 2)
tcell_full = duplicate(tcell, "tcell_full")
BV_T = bvh(tcell_full)


def z_mem_t(x, y=PY):
    return BV_T.ray_cast(Vector((x, y, 0)), Vector((0, 0, 1)))[0].z


# ================================================================ receptor proteins
log("proteins")
peg_holes_M, peg_holes_T = [], []


def protein(name, els, pegs):
    ob = metaball_object(name, els, 0.45, C_PROT)
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    for a, b in pegs:
        p_cyl(bm, a, b, 2.0, 24)
    bm.to_mesh(ob.data)
    bm.free()
    remesh(ob, 0.28 / QUALITY)
    smooth(ob, 0.5, 2)
    return ob


def peg_M(xc, zb):
    peg_holes_M.append(((xc, PY, zb - 9), (xc, PY, zb + 3)))
    return ((xc, PY, zb - 8.5), (xc, PY, zb + 1))


def peg_T(xc, zt):
    peg_holes_T.append(((xc, PY, zt - 3), (xc, PY, zt + 9)))
    return ((xc, PY, zt - 1), (xc, PY, zt + 8.5))


BRX, BRY, BRZ = 6.0, 5.6, 6.6
PEP_R = 4.4
SEP = 6.4
zb = [z_mem_mac(X0 - SEP), z_mem_mac(X0 + SEP)]
zt = [z_mem_t(X0 - SEP), z_mem_t(X0 + SEP)]
g = sum(zt) / 2 - sum(zb) / 2
zp = sum(zb) / 2 + 0.52 * g
d1z = zp - PEP_R * 0.5 - BRZ * 0.8
d2z = d1z - 1.75 * BRZ
vz = zp + PEP_R * 0.5 + BRZ * 0.8
cz = vz + 1.75 * BRZ
log("  synapse gap %.1f mm" % g)
glycans = []
mhc_els, mhc_pegs, tcr_els, tcr_pegs = [], [], [], []
for k, s in enumerate((-1, 1)):
    xc = X0 + s * SEP
    mhc_els += [E_caps((xc, PY, zb[k] - 2), (xc + s * 0.6, PY, d2z), 2.3),
                E_ell((xc + s * 0.6, PY, d2z), BRX, BRY, BRZ),
                E_ell((xc, PY, d1z), BRX * 0.95, BRY, BRZ * 0.95)]
    mhc_pegs.append(peg_M(xc, zb[k]))
    tcr_els += [E_caps((xc, PY, zt[k] + 2), (xc + s * 0.6, PY, cz), 2.3),
                E_ell((xc + s * 0.6, PY, cz), BRX, BRY, BRZ),
                E_ell((xc, PY, vz), BRX * 0.95, BRY, BRZ * 0.95)]
    tcr_pegs.append(peg_T(xc, zt[k]))
    glycans += [Vector((xc + s * (BRX + 0.2), PY - 2.5, (cz + vz) / 2)), Vector((xc + s * (BRX + 0.4), PY - 2.5, (d1z + d2z) / 2))]
mhc = protein("MHC_II", mhc_els, mhc_pegs)
tcr = protein("TCR", tcr_els, tcr_pegs)
pep = protein("Antigen_Peptide", [E_ball((X0, PY, zp), PEP_R), E_caps((X0 - 3.5, PY, zp), (X0 + 3.5, PY, zp), 3.4)], [])

XC4 = -3.0                                               # CD4: 4 Ig domains, binds MHC-II beta2
zt4 = z_mem_t(XC4)
pa = Vector((XC4 + 1, PY, zt4 - 7))
pb = Vector((X0 + SEP + 0.6 + BRX + 5.4, PY, d2z + 1.0))
ctrl = (pa + pb) / 2 + Vector((7.0, 0, 0))
cd4_els = [E_caps((XC4, PY, zt4 + 2), pa, 2.3)]
for k in range(4):
    t = k / 3
    cd4_els.append(E_ell((1 - t) ** 2 * pa + 2 * (1 - t) * t * ctrl + t * t * pb, 5.6, 5.4, 6.3))
cd4 = protein("CD4", cd4_els, [peg_T(XC4, zt4)])

X1, SEP1 = 40.0, 6.0                                     # CD28 / B7 (CD80/CD86)
zbb = [z_mem_mac(X1 - SEP1), z_mem_mac(X1 + SEP1)]
ztb = [z_mem_t(X1 - SEP1), z_mem_t(X1 + SEP1)]
gb = sum(ztb) / 2 - sum(zbb) / 2
zpb = sum(zbb) / 2 + 0.5 * gb
b7_els, b7_pegs, cd28_els, cd28_pegs = [], [], [], []
for k, s in enumerate((-1, 1)):
    xc = X1 + s * SEP1
    bv = zpb - 0.85 * 7.0
    bc = bv - 1.75 * 7.0
    b7_els += [E_caps((xc, PY, zbb[k] - 2), (xc + s * 0.5, PY, bc), 2.3),
               E_ell((xc + s * 0.5, PY, bc), 6.0, 5.6, 7.0), E_ell((xc, PY, bv), 5.8, 5.6, 7.0)]
    b7_pegs.append(peg_M(xc, zbb[k]))
    cv = zpb + 0.85 * 8.2
    cd28_els += [E_caps((xc, PY, ztb[k] + 2), (xc + s * 0.4, PY, cv), 2.3),
                 E_ell((xc + s * 0.4, PY, cv), 6.2, 5.8, 8.2)]
    cd28_pegs.append(peg_T(xc, ztb[k]))
    glycans += [Vector((xc + s * 6.4, PY - 2.5, bc + 3)), Vector((xc + s * 6.6, PY - 2.5, cv + 2))]
b7 = protein("B7_CD80_CD86", b7_els, b7_pegs)
cd28 = protein("CD28", cd28_els, cd28_pegs)

for a, b in ((mhc, pep), (tcr, pep), (tcr, mhc), (cd4, mhc), (cd4, tcr), (cd28, b7)):
    boolean(a, b, 'DIFFERENCE')
bm = bmesh.new()
for p in glycans:
    p_ellipsoid(bm, Matrix.Translation(p), 1.9, 1.9, 1.9, 16, 8)
gly = obj_from_bm("Glycans", bm, C_PROT)
for a in (mhc, tcr, b7, cd28):
    boolean(a, gly, 'DIFFERENCE')

# ================================================================ cut the cells, holes
log("cutting cells")


def cutter_box(name, lo, hi):
    bm = bmesh.new()
    p_box(bm, lo, hi)
    return obj_from_bm(name, bm)


def cutter_cyls(name, pairs, r):
    bm = bmesh.new()
    for a, b in pairs:
        p_cyl(bm, a, b, r, 32)
    return obj_from_bm(name, bm)


L = 300
bm = bmesh.new()                                         # T cell: 90 deg V-notch facing the viewer
p_prism(bm, [(T_C.x, T_C.y), (T_C.x - L, T_C.y - L), (T_C.x + L, T_C.y - L)], T_FLOOR, Z_T + 200)
cut_T = obj_from_bm("cut_T", bm)
xa, xb, zf = M_NOTCH
bm = bmesh.new()                                         # macrophage: back wall + two 45 deg walls + floor
p_prism(bm, [(xa, 0), (xa - L, -L), (xb + L, -L), (xb, 0)], zf, 400)
cut_M = obj_from_bm("cut_M", bm)
# half-spaces (n, d): inside the removed region when n.p - d > 0
HS_T = [(Vector((-SQ, -SQ, 0)), Vector((-SQ, -SQ, 0)).dot(T_C)), (Vector((SQ, -SQ, 0)), Vector((SQ, -SQ, 0)).dot(T_C)),
        (Vector((0, 0, 1)), T_FLOOR)]
HS_M = [(Vector((0, -1, 0)), 0.0), (Vector((SQ, -SQ, 0)), SQ * xa), (Vector((-SQ, -SQ, 0)), -SQ * xb), (Vector((0, 0, 1)), zf)]

boolean(tcell, cut_T)
boolean(macro, cut_M)
boolean(macro, cutter_box("floor_cut", (-300, -300, -50), (300, 300, M_FLOOR)))
boolean(tcell, cutter_cyls("holes_T", peg_holes_T, 2.0 + CLR))
rod_holes_T = [((s * (ENTRY_X + 12), ROD_XY[0].y, ROD_Z), (s * (ENTRY_X - 13.8), ROD_XY[0].y, ROD_Z)) for s in (-1, 1)]
boolean(tcell, cutter_cyls("rodholes_T", rod_holes_T, ROD_R + CLR))
POST_TOP = M_FLOOR + 12.0
boolean(macro, cutter_cyls("holes_M", peg_holes_M, 2.0 + CLR))
boolean(macro, cutter_cyls("postholes_M", [((p.x, p.y, M_FLOOR - 2), (p.x, p.y, POST_TOP + 0.5)) for p in POSTS], ROD_R + CLR))
boolean(macro, cutter_cyls("rodclear", [((xy.x, xy.y, 0), (xy.x, xy.y, 260)) for xy in ROD_XY], ROD_R + 0.8))
for p in POSTS:
    if BV_M.ray_cast(Vector((p.x, p.y, 0)), Vector((0, 0, 1)))[0] is None:
        log("  WARNING post at %s misses the macrophage" % tuple(p))

# ================================================================ organelles
log("organelles")


def face_matrix(origin, X, Y):
    X, Y = Vector(X).normalized(), Vector(Y).normalized()
    N = X.cross(Y)
    o = Vector(origin)
    return Matrix(((X.x, Y.x, N.x, o.x), (X.y, Y.y, N.y, o.y), (X.z, Y.z, N.z, o.z), (0, 0, 0, 1)))


class Placer:
    """keeps organelles inside the cell, on their cut face and apart from each other"""

    def __init__(self, tree, halfspaces, blockers):
        self.tree, self.hs = tree, halfspaces
        self.placed = list(blockers)

    def region(self, q, m):
        return all(n.dot(q) - d > m for n, d in self.hs)

    def ok(self, M, samples, radius, commit=True):
        c = M @ Vector((0, 0, 0))
        for pc, pr in self.placed:
            if (c - pc).length < pr + radius + 1.2:
                return False
        N = (M.to_3x3() @ Vector((0, 0, 1))).normalized()
        for s in samples:
            p = M @ Vector(s)
            if not inside(self.tree, p, 1.3):
                return False
            if abs(s[2]) < 0.01 and not self.region(p + N * 1.0, 0.7):
                return False
        if commit:
            self.placed.append((c, radius))
        return True


def ring(rx, ry, h=0.0, n=12):
    return [(rx * math.cos(2 * math.pi * k / n), ry * math.sin(2 * math.pi * k / n), h) for k in range(n)]


def locm(F, u, v, ang=0.0):
    return F @ Matrix.Translation((u, v, 0)) @ Matrix.Rotation(math.radians(ang), 4, 'Z')


def build_organelles(prefix, P, faces, specs, cutter, c, voxel, scatter):
    groups, grooves = {}, bmesh.new()

    def G(name):
        return groups.setdefault(name, bmesh.new())

    for spec in specs:
        grp, kind, fname, u, v, ang = spec[:6]
        n_before = len(P.placed)
        prm = spec[6] if len(spec) > 6 else {}
        F = faces[fname]
        M = locm(F, u, v, ang)
        if kind == "mito":
            Lm, W = prm.get("L", 17), prm.get("W", 8)
            if not P.ok(M, ring(Lm / 2, W / 2) + [(0, 0, W * 0.42)], Lm / 2):
                continue
            p_ellipsoid(G(grp), M, Lm / 2, W / 2, W * 0.48, 28, 14)
            for x in [Lm * f for f in (-0.3, -0.15, 0.0, 0.15, 0.3)]:      # cristae
                p_box(grooves, (x - 0.45, -W * 0.36, W * 0.24), (x + 0.45, W * 0.36, W), M)
        elif kind == "ves":
            r = prm.get("r", 2.5)
            if not P.ok(M, ring(r, r) + [(0, 0, r)], r):
                continue
            p_ellipsoid(G(grp), M, r, r, r, 16, 8)
        elif kind == "ring":
            R, r = prm.get("R", 4.5), prm.get("r", 1.7)
            if not P.ok(M, ring(R + r, R + r) + [(R, 0, r)], R + r):
                continue
            p_torus(G(grp), M, R, r, 32, 12)
        elif kind == "caps":
            Lm, W = prm.get("L", 20), prm.get("W", 10)
            if not P.ok(M, ring(Lm / 2, W / 2) + [(0, 0, W * 0.45)], Lm / 2):
                continue
            p_ellipsoid(G(grp), M, Lm / 2, W / 2, W * 0.55, 28, 14)
            for k in range(6):
                x, y = random.uniform(-Lm * 0.3, Lm * 0.3), random.uniform(-W * 0.2, W * 0.2)
                zz = W * 0.55 * math.sqrt(max(0.05, 1 - (2 * x / Lm) ** 2 - (2 * y / W) ** 2))
                p_ellipsoid(G(grp), M @ Matrix.Translation((x, y, zz)), 1.0, 1.0, 1.0, 10, 6)
        elif kind == "disk":
            r = prm.get("r", 6.5)
            if not P.ok(M, ring(r, r) + [(0, 0, 2.5)], r):
                continue
            p_cyl(G(grp), M @ Vector((0, 0, -2)), M @ Vector((0, 0, 2.4)), r, 36)
            p_ellipsoid(G(grp), M @ Matrix.Translation((0, 0, 2.4)), r * 0.5, r * 0.5, r * 0.35, 20, 10)
        elif kind == "arcs":                              # relief stack of curved cisternae on a wall
            n, r0, a0, a1 = prm["n"], prm["r0"], prm["a0"], prm["a1"]
            rmax = r0 + (n - 1) * 3.3
            mid = math.radians((a0 + a1) / 2)
            samples = []
            for rr in (r0 - 1, rmax + 1):
                samples += [(x, y, 0) for x, y in arc_pts(0, 0, rr, a0, a1, 10)]
            Mc = M @ Matrix.Translation(((r0 + rmax) / 2 * math.cos(mid), (r0 + rmax) / 2 * math.sin(mid), 0))
            if not P.ok(Mc, [tuple((Mc.inverted() @ (M @ Vector(s)))) for s in samples], 1.0, commit=False):
                continue
            for x, y in arc_pts(0, 0, (r0 + rmax) / 2, a0, a1, 6):
                P.placed.append((M @ Vector((x, y, 0)), (rmax - r0) / 2 + 2))
            for i in range(n):
                p_strip(G(grp), arc_pts(0, 0, r0 + i * 3.3, a0 + i * 2, a1 - i * 2), 2.2, -2.0, 2.6, M)
            if prm.get("rib"):
                for i in range(n):
                    for x, y in arc_pts(0, 0, r0 + i * 3.3 + 1.35, a0 + 6, a1 - 6, 8):
                        p_ellipsoid(G(grp), M @ Matrix.Translation((x, y, 1.6)), 0.85, 0.85, 0.85, 10, 6)
        elif kind == "stack":                             # free-standing curved stack on the floor
            r_in, r_out, a0, a1, h, nl = prm["r_in"], prm["r_out"], prm["a0"], prm["a1"], prm["h"], prm["layers"]
            rm = (r_in + r_out) / 2
            p_strip(G(grp), arc_pts(0, 0, rm, a0, a1, 32), r_out - r_in, -2.0, h, M)
            for i in range(1, nl):
                zz = h * i / nl
                p_strip(grooves, arc_pts(0, 0, r_out - 1.9, a0 - 3, a1 + 3, 32), 4.4, zz - 0.5, zz + 0.5, M)
            if prm.get("rib"):
                for rr in (r_in + 1.5, rm, r_out - 1.5):
                    for x, y in arc_pts(0, 0, rr, a0 + 4, a1 - 4, int((a1 - a0) / 5)):
                        p_ellipsoid(G(grp), M @ Matrix.Translation((x, y, h)), 0.9, 0.9, 0.9, 10, 6)
            for x, y in arc_pts(0, 0, rm, a0, a1, 8):
                P.placed.append((M @ Vector((x, y, 0)), (r_out - r_in) / 2 + 1.5))
        if len(P.placed) == n_before and kind != "stack":
            log("  (skipped %s %s on %s: no room)" % (prefix, grp, fname))
    # random granules / vesicles on every face
    for fname, (u0, u1, v0, v1, count) in scatter.items():
        for k in range(count):
            r = random.uniform(1.1, 2.1)
            grp = random.choice(["Vesicles", "Granules", "Vesicles"])
            M = locm(faces[fname], random.uniform(u0, u1), random.uniform(v0, v1))
            if P.ok(M, ring(r, r) + [(0, 0, r)], r):
                p_ellipsoid(G(grp), M, r, r, r, 14, 7)
    out = []
    for name, gbm in groups.items():
        if len(gbm.verts) == 0:
            gbm.free()
            continue
        ob = obj_from_bm(prefix + name, gbm, c)
        remesh(ob, voxel)
        if len(grooves.verts):
            boolean(ob, obj_from_bm("grooves", grooves.copy()))
        boolean(ob, cutter, 'INTERSECT')
        out.append(ob)
    grooves.free()
    return out


def nucleus(name, centre, r, c, vox, cutter, kind):
    bm = bmesh.new()
    p_ellipsoid(bm, Matrix.Translation(centre), r, r, r, 64, 32)
    ob = obj_from_bm(name, bm, c)
    remesh(ob, vox)
    if kind == "brain":
        brain(ob, centre, r, 8.0, 0.085, 2.8)
        smooth(ob, 0.5, 1)
    else:
        displace(ob, 3.0, 1.4)
        displace(ob, 9.0, 1.5)
        smooth(ob, 0.5, 1)
    boolean(ob, cutter, 'INTERSECT')
    return ob


TN_C, TN_R = Vector((0, -7, Z_T + 2)), 25.0
MN_C, MN_R = Vector((14, -6, 116)), 32.0
t_nuc = nucleus("T_Nucleus", TN_C, TN_R, C_TC, 0.4 / QUALITY, cut_T, "bumpy")
m_nuc = nucleus("M_Nucleus", MN_C, MN_R, C_MAC, 0.35 / QUALITY, cut_M, "brain")

Z = Z_T
T_FACES = {"left": face_matrix((T_C.x, T_C.y, 0), (SQ, SQ, 0), (0, 0, 1)),        # u < 0
           "right": face_matrix((T_C.x, T_C.y, 0), (SQ, -SQ, 0), (0, 0, 1)),      # u > 0
           "floor": face_matrix((0, 0, T_FLOOR), (1, 0, 0), (0, 1, 0))}
T_SPECS = [
    ("ER", "arcs", "left", -5, Z + 2, 0, dict(n=3, r0=29, a0=105, a1=225)),
    ("ER", "arcs", "right", 5, Z + 2, 0, dict(n=3, r0=29, a0=-48, a1=72)),
    ("Mitochondria", "mito", "left", -5 + 46.5 * math.cos(math.radians(150)), Z + 2 + 46.5 * math.sin(math.radians(150)), 240, dict(L=13, W=6.8)),
    ("Mitochondria", "mito", "left", -5 + 46.5 * math.cos(math.radians(200)), Z + 2 + 46.5 * math.sin(math.radians(200)), 290, dict(L=13, W=6.8)),
    ("Mitochondria", "mito", "right", 5 + 46.5 * math.cos(math.radians(40)), Z + 2 + 46.5 * math.sin(math.radians(40)), 130, dict(L=13, W=6.8)),
    ("Mitochondria", "mito", "right", 5 + 46.5 * math.cos(math.radians(-25)), Z + 2 + 46.5 * math.sin(math.radians(-25)), 65, dict(L=13, W=6.8)),
    ("Mitochondria", "mito", "floor", 24, -30, -45, dict(L=13, W=6.8)),
]
T_SCATTER = {"left": (-52, -3, Z - 38, Z + 52, 45), "right": (3, 52, Z - 38, Z + 52, 45), "floor": (-40, 40, -50, -3, 15)}
PT = Placer(BV_T, HS_T, [(TN_C, TN_R)])
t_org = build_organelles("T_", PT, T_FACES, T_SPECS, cut_T, C_TC, 0.3 / QUALITY, T_SCATTER)

M_FACES = {"back": face_matrix((0, 0, 0), (1, 0, 0), (0, 0, 1)),
           "left": face_matrix((xa, 0, 0), (SQ, SQ, 0), (0, 0, 1)),                # u < 0
           "right": face_matrix((xb, 0, 0), (SQ, -SQ, 0), (0, 0, 1)),              # u > 0
           "floor": face_matrix((0, 0, zf), (1, 0, 0), (0, 1, 0))}
M_SPECS = [
    ("Golgi", "stack", "floor", MN_C.x, MN_C.y, 0, dict(r_in=36, r_out=46, a0=188, a1=262, h=13, layers=4)),
    ("Rough_ER", "stack", "floor", MN_C.x, MN_C.y, 0, dict(r_in=36, r_out=45, a0=278, a1=338, h=10, layers=3, rib=True)),
    ("Golgi", "arcs", "left", -36, 104, 0, dict(n=3, r0=5, a0=-60, a1=60)),
    ("Lysosome", "caps", "left", -14, 134, 80, dict(L=18, W=9)),
    ("Mitochondria", "mito", "back", 14, 159, 0, dict(L=18, W=7.5)),
    ("Mitochondria", "mito", "right", 11, 124, 80, dict(L=15, W=7)),
    ("Mitochondria", "mito", "left", -30, 132, 60, dict(L=14, W=7)),
    ("Rings", "ring", "right", 20, 104, 0, dict(R=4.0, r=1.6)),
    ("Rings", "ring", "back", -24, 152, 0, dict(R=4.0, r=1.6)),
    ("Rings", "ring", "back", 52, 152, 0, dict(R=3.6, r=1.5)),
    ("Phagosome", "disk", "floor", -45, -40, 0, dict(r=6.5)),
    ("Mitochondria", "mito", "floor", -20, -58, 10, dict(L=14, W=7)),
]
M_SCATTER = {"back": (-29, 59, 96, 170, 40), "left": (-60, -2, 96, 165, 40), "right": (2, 40, 96, 150, 30),
             "floor": (-70, 90, -80, -3, 40)}
PM = Placer(BV_M, HS_M, [(MN_C, MN_R)])
m_org = build_organelles("M_", PM, M_FACES, M_SPECS, cut_M, C_MAC, 0.3 / QUALITY, M_SCATTER)

# ================================================================ rods, posts, collars
log("rods / posts / collars")


def rod_path(xy, bend_r=14.0):
    s = 1 if xy.x < 0 else -1                           # direction towards the T cell
    end_x = -s * (ENTRY_X - 13.0)
    pts = [Vector((xy.x, xy.y, ROD_BOTTOM)), Vector((xy.x, xy.y, ROD_Z - bend_r))]
    for k in range(1, 12):
        a = math.pi / 2 * k / 12
        pts.append(Vector((xy.x + s * bend_r * (1 - math.cos(a)), xy.y, ROD_Z - bend_r + bend_r * math.sin(a))))
    pts.append(Vector((end_x, xy.y, ROD_Z)))
    return pts


rods = []
for i, xy in enumerate(ROD_XY):
    bm = bmesh.new()
    p_tube(bm, rod_path(xy), ROD_R, 32)
    rods.append(obj_from_bm("Rod_%s" % ("Left", "Right")[i], bm, C_ROD))
for i, p in enumerate(POSTS):
    bm = bmesh.new()
    p_cyl(bm, (p.x, p.y, BASE_H - 15), (p.x, p.y, POST_TOP), ROD_R, 32)
    obj_from_bm("Post_%d" % (i + 1), bm, C_ROD)


def collar(bm, centre, axis, h=5.0, ro=7.0):
    d = Vector(axis).normalized()
    p_cyl(bm, Vector(centre) - d * h / 2, Vector(centre) + d * h / 2, ro, 40)


bm = bmesh.new()
for xy in ROD_XY:
    collar(bm, (xy.x, xy.y, BASE_H + 2.5), (0, 0, 1))
for p in POSTS:
    collar(bm, (p.x, p.y, BASE_H + 2.5), (0, 0, 1), 4.0, 6.5)
    collar(bm, (p.x, p.y, M_FLOOR - 2.0), (0, 0, 1), 4.0, 6.5)
for s in (-1, 1):
    collar(bm, (s * (ENTRY_X + 6.5), ROD_XY[0].y, ROD_Z), (1, 0, 0), 6.0, 7.0)
collars = obj_from_bm("Gold_Collars", bm, C_ROD)
remesh(collars, 0.3)
boolean(collars, cutter_cyls("collar_holes", [((xy.x, xy.y, 0), (xy.x, xy.y, 300)) for xy in ROD_XY] +
                             [((p.x, p.y, 0), (p.x, p.y, 120)) for p in POSTS] +
                             [((-200, ROD_XY[0].y, ROD_Z), (200, ROD_XY[0].y, ROD_Z))], ROD_R + 0.15))
boolean(collars, tcell)                                  # sit flush on the spiky surface

# ================================================================ base
log("base")
TOP_SIDE, TOP_BACK, TOP_FRONT = 12.0, 10.0, 28.0
bm = bmesh.new()
BW, BD = BASE_W + 1.2, BASE_D + 1.2                      # +1.2: the 2 mm edge bevel trims the outline back to 400 mm
for x, y, z in ((-BW / 2, -BD / 2, 0), (BW / 2, -BD / 2, 0), (BW / 2, BD / 2, 0), (-BW / 2, BD / 2, 0),
                (-BASE_W / 2 + TOP_SIDE, -BASE_D / 2 + TOP_FRONT, BASE_H), (BASE_W / 2 - TOP_SIDE, -BASE_D / 2 + TOP_FRONT, BASE_H),
                (BASE_W / 2 - TOP_SIDE, BASE_D / 2 - TOP_BACK, BASE_H), (-BASE_W / 2 + TOP_SIDE, BASE_D / 2 - TOP_BACK, BASE_H)):
    bm.verts.new((x, y, z))
bmesh.ops.convex_hull(bm, input=bm.verts)
bmesh.ops.dissolve_limit(bm, angle_limit=0.01, verts=bm.verts, edges=bm.edges)
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
base = obj_from_bm("Base", bm, C_BASE)
bv = base.modifiers.new("bevel", 'BEVEL')
bv.width, bv.segments, bv.limit_method = 2.0, 3, 'ANGLE'
apply_mods(base)

SLOPE_A = math.atan2(BASE_H, TOP_FRONT)
M_SLOPE = Matrix.Translation((0, -BASE_D / 2 + TOP_FRONT / 2, BASE_H / 2)) @ Matrix.Rotation(SLOPE_A, 4, 'X')
PLQ_W, PLQ_H = 184.0, 30.0
bm = bmesh.new()
p_box(bm, (-PLQ_W / 2 - 0.3, -PLQ_H / 2 - 0.3, -1.2), (PLQ_W / 2 + 0.3, PLQ_H / 2 + 0.3, 6), M_SLOPE)
for xy in ROD_XY:
    p_cyl(bm, (xy.x, xy.y, ROD_BOTTOM - 0.5), (xy.x, xy.y, BASE_H + 1), ROD_R + CLR)
for p in POSTS:
    p_cyl(bm, (p.x, p.y, BASE_H - 15.5), (p.x, p.y, BASE_H + 1), ROD_R + CLR)
for y in (-40, 80):                                      # 6 mm dowels joining the halves
    p_cyl(bm, (-16, y, 14), (16, y, 14), 3.0 + 0.15)
boolean(base, obj_from_bm("base_cut", bm))
base_L = duplicate(base, "Base_Left", C_BASE)
base_R = duplicate(base, "Base_Right", C_BASE)
boolean(base_L, cutter_box("hL", (-300, -300, -10), (0, 300, 100)), 'INTERSECT')
boolean(base_R, cutter_box("hR", (0, -300, -10), (300, 300, 100)), 'INTERSECT')
kill(base)

# ================================================================ plaque & labels
log("plaque / labels")


def plate_and_text(name, M, w, h, lines, sizes, gap):
    bm = bmesh.new()
    p_rounded_slab(bm, w, h, 2.4, 2.0, M, -1.2)
    plate = obj_from_bm(name + "_Plate", bm, C_LAB)
    bm = bmesh.new()
    top = M @ Matrix.Translation((0, 0, 1.2))
    ins, lw = 1.8, 0.8
    for (x0, y0, x1, y1) in ((-w / 2 + ins, h / 2 - ins - lw, w / 2 - ins, h / 2 - ins),
                             (-w / 2 + ins, -h / 2 + ins, w / 2 - ins, -h / 2 + ins + lw),
                             (-w / 2 + ins, -h / 2 + ins + lw, -w / 2 + ins + lw, h / 2 - ins - lw),
                             (w / 2 - ins - lw, -h / 2 + ins + lw, w / 2 - ins, h / 2 - ins - lw)):
        p_box(bm, (x0, y0, 0), (x1, y1, 0.6), top)
    n = len(lines)
    for i, (txt, sz) in enumerate(zip(lines, sizes)):
        y = (n - 1) / 2 * gap - i * gap
        text_into(bm, txt, sz, top @ Matrix.Translation((0, y, 0)), max_w=w - 9)
    return plate, obj_from_bm(name + "_Text", bm, C_LAB)


plate_and_text("Plaque", M_SLOPE, PLQ_W, PLQ_H, ["ATTACHMENT OF HELPER T LYMPHOCYTE", "TO MACROPHAGE VIA MHC CLASS II",
                                                "3D Educational Anatomical Model"], [7.5, 7.5, 5.0], 8.8)

LAB_H = 24.0
PLATE_BACK_Y = ROD_XY[0].y - (ROD_R + 2.6)
LABELS = [  # side, z, lines, target, plate x-offset from the rod, plate width
    (-1, Z_T - 8, ["Helper T Lymphocyte", "(CD4+)"], "tcell", -6, 92),
    (-1, Z_T - 48, ["T-Cell Receptor (TCR)"], "tcr", -6, 92),
    (-1, Z_T - 88, ["MHC Class II", "& Antigenic Peptide"], "pep", -6, 92),
    (-1, 150, ["Macrophage"], "macro", -30, 72),
    (1, Z_T - 8, ["CD4 Co-receptor"], "cd4", 6, 92),
    (1, Z_T - 48, ["CD28 / B7 (CD80/CD86)", "Co-stimulation"], "cd28", 6, 92),
    (1, Z_T - 88, ["Immunological Synapse"], "syn", 6, 92),
]
ROT_FRONT = Matrix.Rotation(math.radians(90), 4, 'X')    # local +Z -> world -Y
label_objs = []
for i, (side, z, lines, tgt, dx, w) in enumerate(LABELS):
    xr = ROD_XY[0 if side < 0 else 1].x
    M = Matrix.Translation((xr + dx, PLATE_BACK_Y - 1.2, z)) @ ROT_FRONT
    sizes = [7.4] * len(lines) if len(lines) > 1 else [8.6]
    pl, tx = plate_and_text("Label_%d" % (i + 1), M, w, LAB_H, lines, sizes, 8.6)
    label_objs.append((pl, tx, side, z, tgt, xr + dx, w))
    bm = bmesh.new()                                     # snap clip, glued to the back of the plate
    p_cyl(bm, (xr, ROD_XY[0].y, z - 6), (xr, ROD_XY[0].y, z + 6), ROD_R + 2.6, 48)
    p_box(bm, (xr - 9, PLATE_BACK_Y, z - 6), (xr + 9, PLATE_BACK_Y + 2.6, z + 6))
    clip = obj_from_bm("Label_%d_Clip" % (i + 1), bm, C_LAB)
    remesh(clip, 0.35)
    bm = bmesh.new()
    p_cyl(bm, (xr, ROD_XY[0].y, z - 8), (xr, ROD_XY[0].y, z + 8), ROD_R + 0.15, 48)
    p_box(bm, (xr - 3.4, ROD_XY[0].y + 2.0, z - 8), (xr + 3.4, ROD_XY[0].y + 12, z + 8))
    boolean(clip, obj_from_bm("clipcut", bm))
    for ob in (pl, clip):                                # collision check
        t = bvh(ob)
        for other in (macro, tcell):
            if t.overlap(bvh(other)):
                log("  WARNING %s touches %s" % (ob.name, other.name))

# ================================================================ leader wires
log("leader wires")
TREES = [bvh(o) for o in [macro, tcell, mhc, tcr, pep, cd4, cd28, b7] + rods]
TARGETS = {
    "tcell": Vector((-40, -18, Z_T + 2)), "tcr": Vector((X0 - SEP - 1, PY, cz)), "pep": Vector((X0 - 2, PY, zp)),
    "macro": Vector((-88, 0, 118)), "cd4": Vector((XC4 + 4, PY, (zt4 + d2z) / 2 + 4)),
    "cd28": Vector((X1 + SEP1 + 2, PY, zpb + 4)), "syn": Vector((X1 + SEP1, PY, zbb[1] + 5)),
}
for pl, tx, side, z, tgt, xc, w in label_objs:
    start = Vector((xc - side * (w / 2 - 3), PLATE_BACK_Y - 1.2, z))
    goal = TARGETS[tgt]
    d = (goal - start).normalized()
    best = (goal - start).length
    for tree in TREES:
        hit = tree.ray_cast(start + d * 4, d, best)
        if hit[0] is not None:
            best = min(best, (hit[0] - start).length + 0.8)
    bm = bmesh.new()
    p_cyl(bm, start, start + d * best, 0.8, 12)
    p_ellipsoid(bm, Matrix.Translation(start + d * best), 1.5, 1.5, 1.5, 12, 6)
    obj_from_bm("Wire_%s" % tgt, bm, C_WIRE)

for ob in list(C_TMP.objects):
    kill(ob)
bpy.data.collections.remove(C_TMP)

# ================================================================ materials
log("materials")


def mat(name, col, metal=0.0, rough=0.4, sss=0.0, trans=0.0, emit=0.0, coat=0.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    b = m.node_tree.nodes.get("Principled BSDF")
    vals = {"Base Color": (*col, 1), "Metallic": metal, "Roughness": rough, "Subsurface Weight": sss,
            "Subsurface Scale": 4.0, "Transmission Weight": trans, "Coat Weight": coat,
            "Emission Color": (*col, 1), "Emission Strength": emit}
    if sss:
        vals["Subsurface Radius"] = (1.0, 0.6, 0.4)
    for k, v in vals.items():
        if k in b.inputs:
            b.inputs[k].default_value = v
    m.diffuse_color = (*col, 1)
    return m


GOLD = mat("Gold", (0.9, 0.68, 0.32), metal=1.0, rough=0.22)
MATS = {
    "Macrophage_Body": mat("Macrophage (translucent violet)", (0.36, 0.1, 0.95), rough=0.1, sss=0.15, trans=0.3, coat=1.0),
    "T_Cell_Body": mat("T cell (translucent orange)", (1.0, 0.3, 0.0), rough=0.1, sss=0.15, trans=0.3, coat=1.0),
    "T_Nucleus": mat("T nucleus (tan)", (0.72, 0.45, 0.28), rough=0.45),
    "M_Nucleus": mat("M nucleus (lavender)", (0.55, 0.38, 0.9), rough=0.35, sss=0.2),
    "Mitochondria": mat("Mitochondria (orange)", (0.95, 0.38, 0.06), rough=0.35),
    "T_ER": mat("T ER (red-orange)", (0.8, 0.18, 0.06), rough=0.35),
    "Rough_ER": mat("Rough ER (blue)", (0.1, 0.2, 0.85), rough=0.3),
    "Golgi": mat("Golgi (blue)", (0.12, 0.24, 0.9), rough=0.3),
    "Vesicles": mat("Vesicles (yellow)", (1.0, 0.75, 0.1), rough=0.3),
    "Granules": mat("Granules (red)", (0.85, 0.08, 0.12), rough=0.3),
    "Rings": mat("Ring vesicles (magenta)", (0.85, 0.15, 0.6), rough=0.3),
    "Lysosome": mat("Lysosome (green)", (0.2, 0.7, 0.15), rough=0.3),
    "Phagosome": mat("Phagosome (peach)", (0.95, 0.5, 0.25), rough=0.4),
    "TCR": mat("TCR (blue)", (0.02, 0.12, 0.85), rough=0.2, coat=0.8),
    "MHC_II": mat("MHC-II (green)", (0.15, 0.65, 0.05), rough=0.2, coat=0.8),
    "Antigen_Peptide": mat("Peptide (glowing)", (1.0, 0.42, 0.05), rough=0.2, emit=12.0),
    "CD4": mat("CD4 (red)", (0.85, 0.02, 0.03), rough=0.2, coat=0.8),
    "CD28": mat("CD28 (yellow)", (1.0, 0.78, 0.0), rough=0.2, coat=0.8),
    "B7_CD80_CD86": mat("B7 (teal)", (0.0, 0.55, 0.6), rough=0.2, coat=0.8),
    "Glycans": GOLD, "Gold_Collars": GOLD, "Plate": GOLD, "Clip": GOLD,
    "Base": mat("Base (black satin)", (0.01, 0.01, 0.012), rough=0.3, coat=0.6),
    "Rod": mat("Rods (steel)", (0.85, 0.85, 0.88), metal=1.0, rough=0.12),
    "Post": mat("Rods (steel)", (0.85, 0.85, 0.88), metal=1.0, rough=0.12),
    "Wire": mat("Wire (brass)", (0.8, 0.65, 0.35), metal=1.0, rough=0.3),
    "Text": mat("Text (black)", (0.01, 0.01, 0.01), rough=0.5),
}
PRINT_COLLS = [C_BASE, C_MAC, C_TC, C_PROT, C_ROD, C_LAB, C_WIRE]
for c in PRINT_COLLS:
    for ob in c.objects:
        key = "T_ER" if ob.name == "T_ER" else next((k for k in sorted(MATS, key=len, reverse=True) if k in ob.name), None)
        if key:
            ob.data.materials.clear()
            ob.data.materials.append(MATS[key])
        for p in ob.data.polygons:
            p.use_smooth = ob.name.split("_")[0] not in ("Base", "Label", "Plaque")

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
pts = rod_path(ROD_XY[0])
log("rods: 8 mm, developed length %.0f mm, vertical leg %.0f mm, horizontal leg %.0f mm, bend R14" %
    (sum((pts[k + 1] - pts[k]).length for k in range(len(pts) - 1)), ROD_Z - ROD_BOTTOM, abs(pts[-1].x - ROD_XY[0].x)))
log("posts: 4 x 8 mm, length %.0f mm" % (POST_TOP - (BASE_H - 15)))


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
    with open(os.path.join(d, "mesh_report.txt"), "w") as fh:
        fh.write("\n".join(report) + "\n")
    log("STL files written to", d)

# ================================================================ render scene
bm = bmesh.new()
p_box(bm, (-900, -700, -30), (900, 900, -0.01))
obj_from_bm("Table", bm, C_SCN).data.materials.append(mat("Table (walnut)", (0.16, 0.06, 0.025), rough=0.3, coat=0.6))
bm = bmesh.new()
p_box(bm, (-1500, 700, -30), (1500, 720, 1600))
obj_from_bm("Wall", bm, C_SCN).data.materials.append(mat("Wall", (0.2, 0.2, 0.21), rough=0.8))

cam_d = bpy.data.cameras.new("Camera")
cam_d.lens, cam_d.clip_start, cam_d.clip_end = 50, 10, 10000
cam = bpy.data.objects.new("Camera", cam_d)
C_SCN.objects.link(cam)
cam.location = (-110, -820, 470)
target = Vector((0, 0, 178))
cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
scene.camera = cam
for nm, rot, en in (("Key", (math.radians(45), 0, math.radians(-30)), 3.2),
                    ("Fill", (math.radians(60), 0, math.radians(55)), 1.2),
                    ("Rim", (math.radians(-55), 0, math.radians(175)), 2.5)):
    ld = bpy.data.lights.new(nm, 'SUN')
    ld.energy, ld.angle = en, math.radians(10)
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
    bg.inputs[0].default_value = (0.3, 0.3, 0.32, 1)
    bg.inputs[1].default_value = 0.7

scene.render.engine = 'CYCLES'
scene.cycles.samples = SAMPLES
scene.cycles.use_denoising = True
scene.cycles.max_bounces = 16
scene.cycles.transmission_bounces = 16
scene.render.resolution_x, scene.render.resolution_y = 1152, 864

if SAVE_BLEND:
    bpy.ops.wm.save_as_mainfile(filepath=bpy.path.abspath(SAVE_BLEND))
    log("saved", SAVE_BLEND)
if RENDER_PATH:
    scene.render.filepath = bpy.path.abspath(RENDER_PATH)
    log("rendering ...")
    bpy.ops.render.render(write_still=True)
    log("render written", RENDER_PATH)
log("done")
