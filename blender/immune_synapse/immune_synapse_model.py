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


# ================================================================ layout
BASE_W, BASE_D, BASE_H = 400.0, 240.0, 40.0
T_C, T_R = Vector((0, 5, 268)), 62.0                       # T cell centre / radius
M_C = Vector((0, 10, 112))                                 # macrophage body centre
M_FLOOR = 76.0                                             # flat underside of macrophage
T_CUT = ((-15, -200, 150), (200, -5, 400))                 # removed wedge of T cell
M_CUT = ((-48, -200, 82), (78, -4, 300))                   # removed window of macrophage
ROD_XY = [Vector((-125, 75)), Vector((125, 75))]
ROD_BEND_Z, ROD_BOTTOM = 305.0, 15.0
POSTS = [Vector((-44, 26)), Vector((44, 26)), Vector((8, 4))]
PY = 6.0                                                   # plane of the receptor complexes


def rod_path(xy, bend_r=12.0):
    d = (Vector((T_C.x, T_C.y)) - xy).normalized()
    dz = ROD_BEND_Z - T_C.z
    rs = math.sqrt(T_R ** 2 - dz ** 2)
    entry = Vector((T_C.x, T_C.y)) - d * rs
    end = entry + d * 14.0
    pts = [Vector((xy.x, xy.y, ROD_BOTTOM)), Vector((xy.x, xy.y, ROD_BEND_Z - bend_r))]
    for k in range(1, 12):
        a = math.pi / 2 * k / 12
        h = xy + d * (bend_r * (1 - math.cos(a)))
        pts.append(Vector((h.x, h.y, ROD_BEND_Z - bend_r + bend_r * math.sin(a))))
    pts.append(Vector((end.x, end.y, ROD_BEND_Z)))
    return pts, Vector((d.x, d.y, 0)), Vector((entry.x, entry.y, ROD_BEND_Z)), Vector((end.x, end.y, ROD_BEND_Z))


ROD_INFO = [rod_path(xy) for xy in ROD_XY]

# ================================================================ macrophage
log("macrophage body")
MRX, MRY, MRZ = 98, 64, 46
els = [E_ell(M_C, MRX, MRY, MRZ)]
for i in range(22):                                      # irregular blebs on the top
    a = random.uniform(0, 2 * math.pi)
    rr = random.uniform(0.25, 0.85)
    p = M_C + Vector((MRX * rr * math.cos(a), MRY * rr * math.sin(a), 0))
    p.z = M_C.z + MRZ * math.sqrt(max(0.0, 1 - rr * rr)) - random.uniform(7, 11)
    els.append(E_ball(p, random.uniform(9, 15)))

PODS = [  # angle, z0, length, tilt(deg, + = up), r0
    (0, 106, 50, -8, 16), (32, 122, 34, 28, 10), (58, 108, 52, -12, 16), (90, 112, 50, -4, 16),
    (122, 106, 52, -10, 16), (180, 108, 50, -8, 16), (155, 124, 34, 32, 10), (212, 110, 52, -14, 16),
    (242, 104, 50, -6, 16), (270, 112, 40, 16, 13), (298, 106, 50, -12, 16), (330, 112, 48, 0, 15),
    (198, 130, 28, 42, 9), (345, 128, 28, 40, 9), (104, 134, 26, 48, 9), (16, 134, 24, 50, 8),
    (68, 136, 22, 55, 8), (225, 132, 24, 50, 8), (312, 132, 24, 45, 8), (282, 136, 20, 55, 7),
]
for ang, z0, length, tilt, r0 in PODS:
    a = math.radians(ang + random.uniform(-4, 4))
    dirv = Vector((math.cos(a), math.sin(a), math.tan(math.radians(tilt)))).normalized()
    start = Vector((M_C.x + 0.72 * MRX * math.cos(a), M_C.y + 0.72 * MRY * math.sin(a), z0))
    side = Vector((-math.sin(a), math.cos(a), 0)) * random.uniform(-0.45, 0.45)
    L = length
    while True:                                           # keep inside the printer volume
        tip = start + dirv * L * 0.5 + (dirv + side).normalized() * L * 0.5
        if -118 < tip.x < 118 and -94 < tip.y < 101 and 86 < tip.z < 160 or L < 8:
            break
        L -= 2
    n = max(6, int(L / 2.2))
    ctrl = start + dirv * L * 0.5
    for k in range(n + 1):
        t = k / n
        p = (1 - t) ** 2 * start + 2 * (1 - t) * t * ctrl + t * t * tip
        r = r0 * (1 - t) ** 0.7 + 6.0 * t
        els.append(E_ball(p, r * 0.74))

macro = metaball_object("Macrophage_Body", els, 1.6, C_MAC)
remesh(macro, 0.9 / QUALITY)
displace(macro, 16.0, 4.0)
smooth(macro, 0.5, 2)
displace(macro, 5.0, 1.2)
smooth(macro, 0.5, 2)
macro_full = duplicate(macro, "macro_full")
BV_M = bvh(macro_full)

# ================================================================ T cell
log("T cell body")
bm = bmesh.new()
p_ellipsoid(bm, Matrix.Translation(T_C), T_R, T_R, T_R, 96, 48)
N_SP = 200
ga = math.pi * (3 - math.sqrt(5))
for i in range(N_SP):
    z = 1 - 2 * (i + 0.5) / N_SP
    rr = math.sqrt(1 - z * z)
    d = Vector((rr * math.cos(ga * i), rr * math.sin(ga * i), z))
    d = (d + Vector([random.uniform(-0.08, 0.08) for _ in range(3)])).normalized()
    if d.z < -0.5:
        continue                                          # keep the synapse face clear
    if any(d.angle(-info[1] + Vector((0, 0, (ROD_BEND_Z - T_C.z) / T_R))) < 0.33 for info in ROD_INFO):
        continue
    h = random.uniform(6, 11)
    p_cyl(bm, T_C + d * (T_R - 4), T_C + d * (T_R + h), random.uniform(4.0, 5.5), 16, r2=1.2)
tcell = obj_from_bm("T_Cell_Body", bm, C_TC)
remesh(tcell, 0.7 / QUALITY)
smooth(tcell, 0.5, 3)
displace(tcell, 12.0, 2.5)
displace(tcell, 4.0, 1.0)
smooth(tcell, 0.4, 2)
tcell_full = duplicate(tcell, "tcell_full")
BV_T = bvh(tcell_full)


def z_mem_mac(x):
    hit = BV_M.ray_cast(Vector((x, PY, 400)), Vector((0, 0, -1)))
    return hit[0].z


def z_mem_t(x):
    hit = BV_T.ray_cast(Vector((x, PY, 0)), Vector((0, 0, 1)))
    return hit[0].z


# ================================================================ receptor proteins
log("proteins")
peg_holes_M, peg_holes_T = [], []


def protein(name, els, pegs, color_coll=C_PROT):
    ob = metaball_object(name, els, 0.45, color_coll)
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    for a, b in pegs:
        p_cyl(bm, a, b, 2.0, 24)
    bm.to_mesh(ob.data)
    bm.free()
    remesh(ob, 0.28 / QUALITY)
    smooth(ob, 0.5, 2)
    return ob


# --- TCR / peptide-MHC-II complex
X0, SEP = -29.0, 5.6
zb = [z_mem_mac(X0 - SEP), z_mem_mac(X0 + SEP)]
zt = [z_mem_t(X0 - SEP), z_mem_t(X0 + SEP)]
g = sum(zt) / 2 - sum(zb) / 2
zp = sum(zb) / 2 + 0.5 * g
hz = 0.105 * g
d1z = zp - 2.0 - 0.8 * hz
d2z = d1z - 1.7 * hz
vz = zp + 2.0 + 0.8 * hz
cz = vz + 1.7 * hz
log("  synapse gap %.1f mm" % g)

mhc_els, mhc_pegs, tcr_els, tcr_pegs = [], [], [], []
for k, s in enumerate((-1, 1)):
    xc = X0 + s * SEP
    mhc_els += [E_caps((xc, PY, zb[k] - 2), (xc, PY, d2z), 2.2),
                E_ell((xc + s * 0.6, PY, d2z), 5.6, 5.3, hz * 1.05),
                E_ell((xc, PY, d1z), 5.5, 5.3, hz)]
    mhc_pegs.append(((xc, PY, zb[k] - 7), (xc, PY, zb[k] + 1)))
    peg_holes_M.append(((xc, PY, zb[k] - 7.5), (xc, PY, zb[k] + 3)))
    tcr_els += [E_caps((xc, PY, zt[k] + 2), (xc + s * 0.5, PY, cz), 1.9),
                E_ell((xc + s * 0.5, PY, cz), 5.7, 5.3, hz * 1.05),
                E_ell((xc, PY, vz), 5.6, 5.3, hz)]
    tcr_pegs.append(((xc, PY, zt[k] - 1), (xc, PY, zt[k] + 7)))
    peg_holes_T.append(((xc, PY, zt[k] - 3), (xc, PY, zt[k] + 7.5)))
mhc = protein("MHC_II", mhc_els, mhc_pegs)
tcr = protein("TCR", tcr_els, tcr_pegs)
pep = protein("Antigen_Peptide", [E_caps((X0 - 7.5, PY, zp), (X0 + 7.5, PY, zp), 2.5),
                                  E_ball((X0 - 3, PY - 1, zp + 0.8), 2.4), E_ball((X0 + 3.5, PY + 1, zp - 0.6), 2.4)], [])

# --- CD4 co-receptor (4 Ig domains, binds the MHC-II beta2 domain)
XC4 = -6.0
zt4 = z_mem_t(XC4)
pa = Vector((XC4, PY, zt4 - 6.5))
pb = Vector((X0 + SEP + 0.6 + 5.6 + 5.4, PY, d2z + 0.5))
ctrl = (pa + pb) / 2 + Vector((6.5, 0, 0))
cd4_els = [E_caps((XC4, PY, zt4 + 2), pa, 1.9)]
for k in range(4):
    t = k / 3
    p = (1 - t) ** 2 * pa + 2 * (1 - t) * t * ctrl + t * t * pb
    cd4_els.append(E_ell(p, 5.4, 5.2, 5.9))
cd4 = protein("CD4", cd4_els, [((XC4, PY, zt4 - 1), (XC4, PY, zt4 + 7))])
peg_holes_T.append(((XC4, PY, zt4 - 3), (XC4, PY, zt4 + 7.5)))

# --- CD28 (T cell)  /  B7 = CD80/CD86 (macrophage)  co-stimulation
X1, SEP1 = 38.0, 5.4
zbb = [z_mem_mac(X1 - SEP1), z_mem_mac(X1 + SEP1)]
ztb = [z_mem_t(X1 - SEP1), z_mem_t(X1 + SEP1)]
gb = sum(ztb) / 2 - sum(zbb) / 2
zpb = sum(zbb) / 2 + 0.47 * gb
hb = 0.105 * gb
b7_els, b7_pegs, cd28_els, cd28_pegs = [], [], [], []
for k, s in enumerate((-1, 1)):
    xc = X1 + s * SEP1
    bv = zpb - 0.8 * hb
    bc = bv - 1.7 * hb
    b7_els += [E_caps((xc, PY, zbb[k] - 2), (xc, PY, bc), 1.9),
               E_ell((xc + s * 0.4, PY, bc), 5.4, 5.2, hb), E_ell((xc, PY, bv), 5.3, 5.2, hb * 0.95)]
    b7_pegs.append(((xc, PY, zbb[k] - 7), (xc, PY, zbb[k] + 1)))
    peg_holes_M.append(((xc, PY, zbb[k] - 7.5), (xc, PY, zbb[k] + 3)))
    cv = zpb + 0.8 * hb
    cd28_els += [E_caps((xc, PY, ztb[k] + 2), (xc + s * 0.3, PY, cv), 1.9),
                 E_ell((xc + s * 0.3, PY, cv), 5.5, 5.3, hb * 1.05)]
    cd28_pegs.append(((xc, PY, ztb[k] - 1), (xc, PY, ztb[k] + 7)))
    peg_holes_T.append(((xc, PY, ztb[k] - 3), (xc, PY, ztb[k] + 7.5)))
b7 = protein("B7_CD80_CD86", b7_els, b7_pegs)
cd28 = protein("CD28", cd28_els, cd28_pegs)

# make the parts fit each other instead of overlapping (glue faces)
for a, b in ((mhc, pep), (tcr, pep), (tcr, mhc), (cd4, mhc), (cd4, tcr), (cd28, b7)):
    boolean(a, b, 'DIFFERENCE')

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


cut_T = cutter_box("cut_T", *T_CUT)
cut_M = cutter_box("cut_M", *M_CUT)
boolean(tcell, cut_T)
boolean(macro, cut_M)
floor_cut = cutter_box("floor_cut", (-300, -300, -50), (300, 300, M_FLOOR))
boolean(macro, floor_cut)

holes = cutter_cyls("holes_T", peg_holes_T, 2.0 + CLR)
boolean(tcell, holes)
rod_holes_T = [(info[2] - info[1] * 12, info[3] + info[1] * 0.8) for info in ROD_INFO]
boolean(tcell, cutter_cyls("rodholes_T", rod_holes_T, ROD_R + CLR))
post_top = M_FLOOR + 12.0
boolean(macro, cutter_cyls("holes_M", peg_holes_M, 2.0 + CLR))
boolean(macro, cutter_cyls("postholes_M", [((p.x, p.y, M_FLOOR - 2), (p.x, p.y, post_top + 0.5)) for p in POSTS], ROD_R + CLR))

# ================================================================ organelles
log("organelles")


def face_matrix(origin, X, Y):
    X, Y = Vector(X), Vector(Y)
    N = X.cross(Y)
    o = Vector(origin)
    return Matrix(((X.x, Y.x, N.x, o.x), (X.y, Y.y, N.y, o.y), (X.z, Y.z, N.z, o.z), (0, 0, 0, 1)))


class Placer:
    def __init__(self, tree, box, blockers):
        self.tree, self.lo, self.hi = tree, Vector(box[0]), Vector(box[1])
        self.placed = list(blockers)                     # (centre, radius)

    def ok(self, M, samples, radius):
        c = M @ Vector((0, 0, 0))
        for pc, pr in self.placed:
            if (c - pc).length < pr + radius + 1.2:
                return False
        N = (M.to_3x3() @ Vector((0, 0, 1))).normalized()
        for s in samples:
            p = M @ Vector(s)
            if not inside(self.tree, p, 1.2):
                return False
            if abs(s[2]) < 0.01:                         # footprint must lie on the cut face
                for i in range(3):
                    if abs(N[i]) < 0.5 and not (self.lo[i] + 0.8 < p[i] < self.hi[i] - 0.8):
                        return False
        self.placed.append((c, radius))
        return True


def ring(rx, ry, h=0.0, n=12):
    return [(rx * math.cos(2 * math.pi * k / n), ry * math.sin(2 * math.pi * k / n), h) for k in range(n)]


def loc(F, u, v, ang=0.0):
    return F @ Matrix.Translation((u, v, 0)) @ Matrix.Rotation(math.radians(ang), 4, 'Z')


def build_organelles(prefix, P, faces, specs, cutbox, c, voxel):
    groups = {}
    grooves = bmesh.new()
    for kind, fname, u, v, ang, a, b in specs:
        F = faces[fname]
        M = loc(F, u, v, ang)
        gb_ = groups.setdefault(kind, bmesh.new())
        if kind == "Mitochondria":
            L, W = a, b
            if not P.ok(M, ring(L / 2, W / 2) + [(0, 0, W * 0.42)], L / 2):
                continue
            p_ellipsoid(gb_, M, L / 2, W / 2, W * 0.45, 24, 12)
            for x in [L * f for f in (-0.3, -0.15, 0.0, 0.15, 0.3)]:
                p_box(grooves, (x - 0.45, -W, W * 0.2), (x + 0.45, W, W), M)
        elif kind == "Vesicles":
            if not P.ok(M, ring(a, a) + [(0, 0, a)], a):
                continue
            p_ellipsoid(gb_, M, a, a, a, 16, 8)
        elif kind in ("ER", "Rough_ER"):
            n_b, L = int(a), b
            pts_all = []
            for i in range(n_b):
                off = (i - (n_b - 1) / 2) * 4.6
                pts = [(x, off + 1.3 * math.sin(x / L * 4 * math.pi + i)) for x in [L * (k / 30 - 0.5) for k in range(31)]]
                pts_all.append(pts)
            hh = n_b * 4.6 / 2 + 1
            if not P.ok(M, ring(L / 2, hh, 0, 16) + [(0, 0, 2.0)], max(L / 2, hh)):
                continue
            for pts in pts_all:
                p_strip(gb_, pts, 1.9, -2.0, 2.0, M)
                if kind == "Rough_ER":
                    for x, y in pts[2:-2:3]:
                        for sgn in (-1, 1):
                            p_ellipsoid(gb_, M @ Matrix.Translation((x, y + sgn * 1.25, 1.2)), 0.85, 0.85, 0.85, 10, 6)
        elif kind == "Golgi":
            n_b, r0 = int(a), b
            rmax = r0 + (n_b - 1) * 3.0
            if not P.ok(M @ Matrix.Translation((-rmax * 0.8, 0, 0)), ring(rmax * 0.45, rmax * 0.8) + [(0, 0, 2)], rmax * 0.5):
                continue
            for i in range(n_b):
                r = r0 + i * 3.0
                span = math.radians(52 - i * 3)
                pts = [(-r * math.cos(span * (k / 20 * 2 - 1)), r * math.sin(span * (k / 20 * 2 - 1))) for k in range(21)]
                p_strip(gb_, pts, 1.9, -2.0, 2.2, M)
            for sgn in (-1, 1):
                for rr in (r0 - 1, rmax + 2.6):
                    ang2 = math.radians(56) * sgn
                    p_ellipsoid(gb_, M @ Matrix.Translation((-rr * math.cos(ang2), rr * math.sin(ang2), 0)), 1.4, 1.4, 1.4, 12, 6)
        elif kind == "Lysosome":
            L, W = a, b
            if not P.ok(M, ring(L / 2, W / 2) + [(0, 0, W * 0.45)], L / 2):
                continue
            p_ellipsoid(gb_, M, L / 2, W / 2, W * 0.5, 28, 14)
            for k in range(6):
                x, y = random.uniform(-L * 0.3, L * 0.3), random.uniform(-W * 0.22, W * 0.22)
                zz = W * 0.5 * math.sqrt(max(0.05, 1 - (2 * x / L) ** 2 - (2 * y / W) ** 2))
                p_ellipsoid(gb_, M @ Matrix.Translation((x, y, zz)), 1.0, 1.0, 1.0, 10, 6)
        elif kind == "Phagosome":
            r = a
            if not P.ok(M, ring(r, r) + [(0, 0, 2.5)], r):
                continue
            p_cyl(gb_, M @ Vector((0, 0, -2)), M @ Vector((0, 0, 2.4)), r, 36)
            p_ellipsoid(gb_, M @ Matrix.Translation((0, 0, 2.4)), r * 0.5, r * 0.5, r * 0.32, 20, 10)
    out = []
    for kind, gbm in groups.items():
        if len(gbm.verts) == 0:
            gbm.free()
            continue
        ob = obj_from_bm(prefix + kind, gbm, c)
        remesh(ob, voxel)
        if kind == "Mitochondria" and len(grooves.verts):
            gob = obj_from_bm("grooves", grooves.copy())
            boolean(ob, gob)
        boolean(ob, cutbox, 'INTERSECT')
        out.append(ob)
    grooves.free()
    return out


# --- nuclei
def nucleus(name, centre, r, c, scale, strength, basis, cutbox, vox):
    bm = bmesh.new()
    p_ellipsoid(bm, Matrix.Translation(centre), r, r, r, 64, 32)
    ob = obj_from_bm(name, bm, c)
    remesh(ob, vox)
    displace(ob, scale, strength, basis, 2)
    smooth(ob, 0.5, 1)
    boolean(ob, cutbox, 'INTERSECT')
    return ob


TN_C, TN_R = Vector((2, -9, 270)), 26.0
MN_C, MN_R = Vector((12, -10, 114)), 30.0
t_nuc = nucleus("T_Nucleus", TN_C, TN_R, C_TC, 6.0, 1.2, 'ORIGINAL_PERLIN', cut_T, 0.45 / QUALITY)
m_nuc = nucleus("M_Nucleus", MN_C, MN_R, C_MAC, 5.0, 3.2, 'VORONOI_CRACKLE', cut_M, 0.4 / QUALITY)

T_FACES = {"front": face_matrix((0, T_CUT[1][1], 0), (1, 0, 0), (0, 0, 1)),
           "side": face_matrix((T_CUT[0][0], 0, 0), (0, 1, 0), (0, 0, 1))}
T_SPECS = [
    ("Mitochondria", "front", 40, 284, 65, 17, 8), ("Mitochondria", "front", 37, 250, -25, 17, 8),
    ("Mitochondria", "front", 14, 232, 5, 16, 7.5), ("Mitochondria", "side", -42, 272, 85, 16, 7.5),
    ("ER", "front", 16, 310, 0, 3, 20), ("ER", "side", -36, 300, 80, 2, 14),
    ("Vesicles", "front", -6, 309, 0, 3.0, 0), ("Vesicles", "front", 45, 266, 0, 3.0, 0),
    ("Vesicles", "front", 27, 240, 0, 2.6, 0), ("Vesicles", "front", 36, 306, 0, 2.5, 0),
    ("Vesicles", "front", -8, 236, 0, 2.8, 0), ("Vesicles", "side", -38, 242, 0, 3.0, 0),
    ("Vesicles", "side", -22, 236, 0, 2.5, 0), ("Vesicles", "side", -30, 322, 0, 2.4, 0),
]
PT = Placer(BV_T, T_CUT, [(TN_C, TN_R)])
t_org = build_organelles("T_", PT, T_FACES, T_SPECS, cut_T, C_TC, 0.3 / QUALITY)

M_FACES = {"back": face_matrix((0, M_CUT[1][1], 0), (1, 0, 0), (0, 0, 1)),
           "floor": face_matrix((0, 0, M_CUT[0][2]), (1, 0, 0), (0, 1, 0)),
           "left": face_matrix((M_CUT[0][0], 0, 0), (0, 1, 0), (0, 0, 1)),
           "right": face_matrix((M_CUT[1][0], 0, 0), (0, -1, 0), (0, 0, 1))}
M_SPECS = [
    ("Golgi", "back", -15, 114, 0, 4, 9.5),
    ("Rough_ER", "back", 59, 112, 90, 4, 30),
    ("Mitochondria", "back", -38, 136, 70, 17, 8), ("Mitochondria", "floor", -28, -18, 15, 16, 7.5),
    ("Mitochondria", "right", 15, 106, 80, 13, 6.5), ("Mitochondria", "back", 46, 140, 10, 14, 6.5),
    ("Lysosome", "left", -22, 114, 90, 18, 9),
    ("Phagosome", "floor", 40, -16, 0, 6.5, 0),
    ("Vesicles", "back", -40, 95, 0, 3.0, 0), ("Vesicles", "back", 42, 92, 0, 2.6, 0),
    ("Vesicles", "back", -30, 148, 0, 2.4, 0), ("Vesicles", "back", -37, 120, 0, 2.2, 0),
    ("Vesicles", "floor", 5, -26, 0, 2.6, 0), ("Vesicles", "floor", -8, -15, 0, 2.2, 0),
    ("Vesicles", "floor", 22, -24, 0, 2.4, 0), ("Vesicles", "left", -34, 95, 0, 2.4, 0),
    ("Vesicles", "left", -12, 132, 0, 2.2, 0), ("Vesicles", "right", 10, 121, 0, 2.2, 0),
]
PM = Placer(BV_M, M_CUT, [(MN_C, MN_R)])
m_org = build_organelles("M_", PM, M_FACES, M_SPECS, cut_M, C_MAC, 0.3 / QUALITY)

# ================================================================ rods & posts
log("rods / posts")
rods = []
for i, info in enumerate(ROD_INFO):
    bm = bmesh.new()
    p_tube(bm, info[0], ROD_R, 32)
    rods.append(obj_from_bm("Rod_%s" % ("Left", "Right")[i], bm, C_ROD))
posts = []
for i, p in enumerate(POSTS):
    bm = bmesh.new()
    p_cyl(bm, (p.x, p.y, BASE_H - 15), (p.x, p.y, post_top), ROD_R, 32)
    posts.append(obj_from_bm("Post_%d" % (i + 1), bm, C_ROD))
# rods must never collide with the macrophage
boolean(macro, cutter_cyls("rodclear", [(Vector((xy.x, xy.y, 0)), Vector((xy.x, xy.y, 250))) for xy in ROD_XY], ROD_R + 0.6))

# ================================================================ base
log("base")
prof = [(-BASE_D / 2, 0), (BASE_D / 2, 0), (BASE_D / 2, BASE_H), (-BASE_D / 2 + 35, BASE_H), (-BASE_D / 2, 6)]
bm = bmesh.new()
vs = [bm.verts.new((-BASE_W / 2, y, z)) for y, z in prof]
f = bm.faces.new(vs)
r = bmesh.ops.extrude_face_region(bm, geom=[f])
bmesh.ops.translate(bm, verts=[e for e in r['geom'] if isinstance(e, bmesh.types.BMVert)], vec=(BASE_W, 0, 0))
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
base = obj_from_bm("Base", bm, C_BASE)
bv = base.modifiers.new("bevel", 'BEVEL')
bv.width, bv.segments, bv.limit_method = 2.5, 3, 'ANGLE'
apply_mods(base)

SLOPE_A = math.atan2(BASE_H - 6, 35)                     # rotation about X of the front slope
SLOPE_C = Vector((0, -BASE_D / 2 + 17.5, (BASE_H + 6) / 2))
M_SLOPE = Matrix.Translation(SLOPE_C) @ Matrix.Rotation(SLOPE_A, 4, 'X')
PLQ_W, PLQ_H = 176.0, 30.0

bm = bmesh.new()
p_box(bm, (-PLQ_W / 2 - 0.3, -PLQ_H / 2 - 0.3, -1.2), (PLQ_W / 2 + 0.3, PLQ_H / 2 + 0.3, 6), M_SLOPE)
for xy in ROD_XY:
    p_cyl(bm, (xy.x, xy.y, ROD_BOTTOM - 0.5), (xy.x, xy.y, BASE_H + 1), ROD_R + CLR)
for p in POSTS:
    p_cyl(bm, (p.x, p.y, BASE_H - 15.5), (p.x, p.y, BASE_H + 1), ROD_R + CLR)
for y in (-50, 95):                                      # 6 mm dowels joining the halves
    p_cyl(bm, (-16, y, 18), (16, y, 18), 3.0 + 0.15)
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
    ins, lw = 1.8, 0.8                                     # thin border frame
    for (x0, y0, x1, y1) in ((-w / 2 + ins, h / 2 - ins - lw, w / 2 - ins, h / 2 - ins),
                             (-w / 2 + ins, -h / 2 + ins, w / 2 - ins, -h / 2 + ins + lw),
                             (-w / 2 + ins, -h / 2 + ins + lw, -w / 2 + ins + lw, h / 2 - ins - lw),
                             (w / 2 - ins - lw, -h / 2 + ins + lw, w / 2 - ins, h / 2 - ins - lw)):
        p_box(bm, (x0, y0, 0), (x1, y1, 0.6), top)
    n = len(lines)
    for i, (txt, sz) in enumerate(zip(lines, sizes)):
        y = (n - 1) / 2 * gap - i * gap
        text_into(bm, txt, sz, top @ Matrix.Translation((0, y, 0)), max_w=w - 9)
    text = obj_from_bm(name + "_Text", bm, C_LAB)
    return plate, text


plaque, plaque_txt = plate_and_text("Plaque", M_SLOPE, PLQ_W, PLQ_H,
                                    ["ATTACHMENT OF HELPER T LYMPHOCYTE", "TO MACROPHAGE VIA MHC CLASS II",
                                     "3D Educational Anatomical Model"], [7.5, 7.5, 5.0], 8.8)

LAB_W, LAB_H = 92.0, 24.0
PLATE_BACK_Y = ROD_XY[0].y - 6.6
LABELS = [  # side, z, lines, target-kind
    (-1, 282, ["Helper T Lymphocyte", "(CD4+)"], "tcell"),
    (-1, 240, ["T-Cell Receptor (TCR)"], "tcr"),
    (-1, 198, ["MHC Class II &", "Antigenic Peptide"], "pep"),
    (-1, 156, ["Macrophage"], "macro"),
    (1, 282, ["CD4 Co-receptor"], "cd4"),
    (1, 240, ["CD28 / B7 (CD80/CD86)", "Co-stimulation"], "cd28"),
    (1, 198, ["Immunological Synapse"], "syn"),
]
ROT_FRONT = Matrix.Rotation(math.radians(90), 4, 'X')    # local +Z -> world -Y
label_objs, clips = [], []
for i, (side, z, lines, tgt) in enumerate(LABELS):
    xr = ROD_XY[0 if side < 0 else 1].x
    M = Matrix.Translation((xr, PLATE_BACK_Y - 1.2, z)) @ ROT_FRONT
    sizes = [7.6] * len(lines) if len(lines) > 1 else [9.0]
    pl, tx = plate_and_text("Label_%d" % (i + 1), M, LAB_W, LAB_H, lines, sizes, 8.6)
    label_objs.append((pl, tx, side, z, tgt))
    # snap clip (prints standing up, glued to the back of the plate)
    bm = bmesh.new()
    p_cyl(bm, (xr, ROD_XY[0].y, z - 6), (xr, ROD_XY[0].y, z + 6), ROD_R + 2.6, 48)
    p_box(bm, (xr - 9, PLATE_BACK_Y, z - 6), (xr + 9, PLATE_BACK_Y + 2.6, z + 6))
    clip = obj_from_bm("Label_%d_Clip" % (i + 1), bm, C_LAB)
    remesh(clip, 0.35)
    bm = bmesh.new()
    p_cyl(bm, (xr, ROD_XY[0].y, z - 8), (xr, ROD_XY[0].y, z + 8), ROD_R + 0.15, 48)
    p_box(bm, (xr - 3.4, ROD_XY[0].y + 2.0, z - 8), (xr + 3.4, ROD_XY[0].y + 12, z + 8))
    boolean(clip, obj_from_bm("clipcut", bm))
    clips.append(clip)

# ================================================================ leader wires
log("leader wires")
BVH_ALL = {}
for ob in [macro, tcell, mhc, tcr, pep, cd4, cd28, b7] + rods:
    BVH_ALL[ob.name] = bvh(ob)
TARGETS = {
    "tcell": Vector((-40, 0, 274)), "tcr": Vector((X0 - SEP, PY, cz)), "pep": Vector((X0 - 7, PY, zp)),
    "macro": Vector((-75, 0, 128)), "cd4": Vector((XC4 - 2, PY, (zt4 + d2z) / 2)),
    "cd28": Vector((X1 + SEP1, PY, zpb)), "syn": Vector((X1 + 4, PY, zbb[1] + 3)),
}
for pl, tx, side, z, tgt in label_objs:
    xr = ROD_XY[0 if side < 0 else 1].x
    start = Vector((xr - side * (LAB_W / 2 - 3), PLATE_BACK_Y - 1.2, z))
    goal = TARGETS[tgt]
    d = (goal - start).normalized()
    best = (goal - start).length
    for tree in BVH_ALL.values():
        hit = tree.ray_cast(start + d * 4, d, best)
        if hit[0] is not None:
            best = min(best, (hit[0] - start).length + 0.8)
    bm = bmesh.new()
    p_cyl(bm, start, start + d * best, 0.8, 12)
    obj_from_bm("Wire_%s" % tgt, bm, C_WIRE)

# ================================================================ clean up
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
            "Subsurface Scale": 6.0, "Transmission Weight": trans, "Coat Weight": coat,
            "Emission Color": (*col, 1), "Emission Strength": emit}
    if sss:
        vals["Subsurface Radius"] = (1.0, 0.5, 0.3)
    for k, v in vals.items():
        if k in b.inputs:
            b.inputs[k].default_value = v
    m.diffuse_color = (*col, 1)
    return m


MATS = {
    "Macrophage_Body": mat("Macrophage (translucent purple)", (0.50, 0.33, 0.85), rough=0.25, sss=0.6, trans=0.15, coat=0.6),
    "T_Cell_Body": mat("T cell (translucent orange)", (1.0, 0.42, 0.10), rough=0.25, sss=0.6, trans=0.15, coat=0.6),
    "T_Nucleus": mat("T nucleus (beige)", (0.62, 0.45, 0.33), rough=0.5),
    "M_Nucleus": mat("M nucleus (violet)", (0.42, 0.24, 0.72), rough=0.45, sss=0.3),
    "Mitochondria": mat("Mitochondria (rust)", (0.75, 0.25, 0.08), rough=0.45),
    "ER": mat("ER (amber)", (0.95, 0.55, 0.15), rough=0.4),
    "Rough_ER": mat("Rough ER (lilac)", (0.55, 0.35, 0.85), rough=0.4),
    "Golgi": mat("Golgi (purple)", (0.36, 0.2, 0.7), rough=0.4),
    "Vesicles": mat("Vesicles (yellow)", (0.95, 0.75, 0.2), rough=0.35),
    "Lysosome": mat("Lysosome (green)", (0.3, 0.65, 0.2), rough=0.35),
    "Phagosome": mat("Phagosome (peach)", (0.9, 0.5, 0.3), rough=0.45),
    "TCR": mat("TCR (blue)", (0.05, 0.15, 0.75), rough=0.3, coat=0.5),
    "MHC_II": mat("MHC-II (green)", (0.12, 0.55, 0.08), rough=0.3, coat=0.5),
    "Antigen_Peptide": mat("Peptide (glowing orange)", (1.0, 0.35, 0.05), rough=0.3, emit=4.0),
    "CD4": mat("CD4 (red)", (0.75, 0.04, 0.04), rough=0.3, coat=0.5),
    "CD28": mat("CD28 (yellow)", (0.95, 0.72, 0.03), rough=0.3, coat=0.5),
    "B7_CD80_CD86": mat("B7 (teal)", (0.0, 0.5, 0.55), rough=0.3, coat=0.5),
    "Base": mat("Base (black gloss)", (0.012, 0.012, 0.014), rough=0.2, coat=1.0),
    "Rod": mat("Rods (steel)", (0.8, 0.8, 0.82), metal=1.0, rough=0.18),
    "Post": mat("Rods (steel)", (0.8, 0.8, 0.82), metal=1.0, rough=0.18),
    "Wire": mat("Wire (brass)", (0.75, 0.6, 0.3), metal=1.0, rough=0.3),
    "Plate": mat("Plate (gold)", (0.85, 0.66, 0.32), metal=1.0, rough=0.28),
    "Clip": mat("Plate (gold)", (0.85, 0.66, 0.32), metal=1.0, rough=0.28),
    "Text": mat("Text (black)", (0.01, 0.01, 0.01), rough=0.5),
}
PRINT_COLLS = [C_BASE, C_MAC, C_TC, C_PROT, C_ROD, C_LAB, C_WIRE]
for c in PRINT_COLLS:
    for ob in c.objects:
        key = next((k for k in sorted(MATS, key=len, reverse=True) if k in ob.name), None)
        if key is None and ob.name.startswith("Base"):
            key = "Base"
        if key:
            ob.data.materials.clear()
            ob.data.materials.append(MATS[key])
        for p in ob.data.polygons:
            p.use_smooth = ob.name.split("_")[0] not in ("Base", "Label", "Plaque")

# ================================================================ report
log("checking meshes")
report = []
for c in PRINT_COLLS:
    for ob in c.objects:
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        nm = sum(1 for e in bm.edges if not e.is_manifold)
        bm.free()
        dims = ob.dimensions
        report.append("%-28s %7.1f x %6.1f x %6.1f mm  tris=%7d  non-manifold-edges=%d" %
                      (ob.name, dims.x, dims.y, dims.z, sum(len(p.vertices) - 2 for p in ob.data.polygons), nm))
print("\n".join(report))
mins = Vector((1e9,) * 3)
maxs = Vector((-1e9,) * 3)
for c in PRINT_COLLS:
    for ob in c.objects:
        for v in ob.data.vertices:
            for k in range(3):
                mins[k] = min(mins[k], v.co[k])
                maxs[k] = max(maxs[k], v.co[k])
log("assembly size: %.1f x %.1f x %.1f mm" % tuple(maxs - mins))
for i, info in enumerate(ROD_INFO):
    pts = info[0]
    L = sum((pts[k + 1] - pts[k]).length for k in range(len(pts) - 1))
    log("rod %d: 8 mm, developed length %.0f mm (vertical part %.0f mm, bend R12, angle 90 deg)" %
        (i + 1, L, ROD_BEND_Z - ROD_BOTTOM))


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
    for ci, c in enumerate(PRINT_COLLS):
        for ob in c.objects:
            write_stl(ob, os.path.join(d, "%s__%s.stl" % (c.name, ob.name)))
    with open(os.path.join(d, "mesh_report.txt"), "w") as fh:
        fh.write("\n".join(report) + "\n")
    log("STL files written to", d)

# ================================================================ render scene
bm = bmesh.new()
p_box(bm, (-900, -700, -30), (900, 900, -0.01))
obj_from_bm("Table", bm, C_SCN).data.materials.append(mat("Table (walnut)", (0.18, 0.07, 0.03), rough=0.35, coat=0.5))
bm = bmesh.new()
p_box(bm, (-1500, 700, -30), (1500, 720, 1600))
obj_from_bm("Wall", bm, C_SCN).data.materials.append(mat("Wall", (0.35, 0.35, 0.36), rough=0.8))

cam_d = bpy.data.cameras.new("Camera")
cam_d.lens, cam_d.clip_start, cam_d.clip_end = 50, 10, 10000
cam = bpy.data.objects.new("Camera", cam_d)
C_SCN.objects.link(cam)
cam.location = (170, -860, 470)
target = Vector((0, 10, 175))
cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
scene.camera = cam
for nm, rot, en in (("Key", (math.radians(50), 0, math.radians(-35)), 3.5),
                    ("Fill", (math.radians(65), 0, math.radians(60)), 1.2),
                    ("Rim", (math.radians(-60), 0, math.radians(170)), 2.0)):
    ld = bpy.data.lights.new(nm, 'SUN')
    ld.energy, ld.angle = en, math.radians(8)
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
    bg.inputs[0].default_value = (0.32, 0.32, 0.34, 1)
    bg.inputs[1].default_value = 0.6

scene.render.engine = 'CYCLES'
scene.cycles.samples = SAMPLES
scene.cycles.use_denoising = True
scene.render.resolution_x, scene.render.resolution_y = 1152, 864
scene.render.film_transparent = False

if SAVE_BLEND:
    bpy.ops.wm.save_as_mainfile(filepath=bpy.path.abspath(SAVE_BLEND))
    log("saved", SAVE_BLEND)
if RENDER_PATH:
    scene.render.filepath = bpy.path.abspath(RENDER_PATH)
    log("rendering ...")
    bpy.ops.render.render(write_still=True)
    log("render written", RENDER_PATH)
log("done")
