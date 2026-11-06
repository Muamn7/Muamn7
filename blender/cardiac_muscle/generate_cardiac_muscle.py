"""
Cardiac muscle tissue - procedural high-detail model for Blender (4.2+ / 5.x)
نموذج نسيج عضلة القلب - تصميم عالي الدقة

How to use / طريقة الاستخدام:
  Blender > Scripting tab > Open this file > Run Script
  (or headless:  blender -b -P generate_cardiac_muscle.py)

What it builds / ماذا يبني:
  * Branching striated fibres fused into one smooth mesh (voxel remesh)
  * Real geometric striations (cross stripes) following each fibre
  * Intercalated discs (zig-zag step grooves) between cells
  * Purple oval nuclei as SEPARATE grains (one object each), one per cell,
    each sitting in a matching socket carved into the fibre
  * Materials (Cycles / EEVEE), lights and a camera
  * Fibres stand vertically, cut flat and level at top and bottom
  * Real-world size: total HEIGHT = 20 cm (change TARGET_HEIGHT_M)

No text / labels are created - model only.
"""

import math
import random

import bmesh
import numpy as np
import bpy
from mathutils import Matrix, Vector, kdtree, noise

# --------------------------------------------------------------------------
# Settings / الإعدادات
# --------------------------------------------------------------------------
TARGET_HEIGHT_M = 0.20      # final height (fibres stand vertically, 20 cm tall)
X_CUT = 10.5                # fibres are cut flat at +/- X_CUT (fibre-radius units)
SEED = 7
VOXEL = 0.05                # remesh voxel size in fibre-radius units (smaller = more detail)
STRIATION_PITCH = 0.30      # distance between striations (fibre-radius units)
STRIATION_DEPTH = 0.035     # deep enough to show on a 3D print
DISC_DEPTH = 0.12
DISC_WIDTH = 0.05
SEAM_DEPTH = 0.09           # groove that separates diagonal (branch) and straight striations
SEAM_WIDTH = 0.05
NUCLEUS_HEIGHT = 0.24       # how far each nucleus grain sticks out of the fibre (fibre-radius units)
NUCLEUS_SINK = 0.05         # grain sits slightly into its socket
NUCLEUS_CLEARANCE = 0.025   # gap between grain and socket (~0.25 mm at 20 cm) for gluing in
DO_RENDER = False           # set True to render a preview PNG next to the .blend
RENDER_PATH = "//cardiac_muscle_render.png"

random.seed(SEED)

# --------------------------------------------------------------------------
# Scene reset
# --------------------------------------------------------------------------
def reset_scene():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.curves, bpy.data.materials,
                 bpy.data.lights, bpy.data.cameras):
        for block in list(coll):
            coll.remove(block)
    sc = bpy.context.scene
    sc.unit_settings.system = 'METRIC'
    sc.unit_settings.length_unit = 'CENTIMETERS'
    sc.unit_settings.scale_length = 1.0


# --------------------------------------------------------------------------
# Fibre network (built in "fibre radius" units, r ~= 1)
# --------------------------------------------------------------------------
class Fibre:
    def __init__(self, y0, z0, xs, xe):
        self.y0, self.z0, self.xs, self.xe = y0, z0, xs, xe
        self.ay = random.uniform(0.18, 0.34)
        self.az = random.uniform(0.18, 0.34)
        self.ky = random.uniform(0.18, 0.32)
        self.kz = random.uniform(0.18, 0.32)
        self.py = random.uniform(0, 6.28)
        self.pz = random.uniform(0, 6.28)
        self.pr1 = random.uniform(0, 6.28)
        self.pr2 = random.uniform(0, 6.28)
        self.r0 = random.uniform(0.92, 1.05)

    def pos(self, x):
        return Vector((x,
                       self.y0 + self.ay * math.sin(self.ky * x + self.py),
                       self.z0 + self.az * math.sin(self.kz * x + self.pz)))

    def tangent(self, x):
        return (self.pos(x + 0.01) - self.pos(x - 0.01)).normalized()

    def radius(self, x):
        return self.r0 * (1.0 + 0.06 * math.sin(0.55 * x + self.pr1)
                          + 0.04 * math.sin(1.3 * x + self.pr2))


def build_layout():
    """Hexagonally packed, staggered bundle: 3 depth layers."""
    fibres = []
    layers = [(-2.75, [-3.1, 0.0, 3.1]),
              (0.0, [-4.65, -1.55, 1.55, 4.65]),
              (2.75, [-3.1, 0.0, 3.1])]
    for y0, zs in layers:
        for z0 in zs:
            xs = -X_CUT - 1.5
            xe = X_CUT + 1.5
            fibres.append(Fibre(y0, z0, xs, xe))
    return fibres


def neighbours(fibres, max_d=3.4):
    pairs = []
    for i, a in enumerate(fibres):
        for j, b in enumerate(fibres):
            if j <= i:
                continue
            d = math.hypot(a.y0 - b.y0, a.z0 - b.z0)
            if d < max_d:
                pairs.append((i, j))
    return pairs


def bezier(p0, p1, p2, p3, t):
    u = 1 - t
    return (u * u * u) * p0 + (3 * u * u * t) * p1 + (3 * u * t * t) * p2 + (t * t * t) * p3


def make_centerlines(fibres):
    """Return list of centerlines: each = list of (point, radius)."""
    lines = []
    step = 0.05
    for f in fibres:
        n = int((f.xe - f.xs) / step) + 1
        pts = []
        for k in range(n):
            x = f.xs + k * step
            pts.append((f.pos(x), f.radius(x)))
        lines.append(pts)

    # Branches (Y-shaped connections, typical of cardiac muscle)
    pairs = neighbours(fibres)
    random.shuffle(pairs)
    n_branch = 0
    used = []
    for (i, j) in pairs:
        if n_branch >= 15:
            break
        a, b = fibres[i], fibres[j]
        lo = -X_CUT + 1.2
        hi = X_CUT - 1.2
        span = random.uniform(4.5, 6.0)
        if hi - lo < span + 0.5:
            continue
        for _try in range(10):
            x0 = random.uniform(lo, hi - span)
            if all(abs(x0 - u) > 4.0 for (ii, jj, u) in used if ii in (i, j) or jj in (i, j)):
                break
        else:
            continue
        if random.random() < 0.5:
            a, b = b, a
        x1 = x0 + span
        p0, p3 = a.pos(x0), b.pos(x1)
        h = span * 0.42
        p1 = p0 + a.tangent(x0) * h
        p2 = p3 - b.tangent(x1) * h
        ra, rb = a.radius(x0) * 0.86, b.radius(x1) * 0.86
        n = 60
        pts = []
        for k in range(n + 1):
            t = k / n
            r = ra * (1 - t) + rb * t
            r *= 1.0 - 0.10 * math.sin(math.pi * t)
            pts.append((bezier(p0, p1, p2, p3, t), r))
        lines.append(pts)
        used.append((i, j, x0))
        n_branch += 1
    return lines


def curve_tube_mesh(lines):
    """Bevelled poly curves -> one combined mesh."""
    bm = bmesh.new()
    for idx, pts in enumerate(lines):
        cu = bpy.data.curves.new(f"_fibre_{idx}", 'CURVE')
        cu.dimensions = '3D'
        cu.bevel_depth = 1.0
        cu.bevel_resolution = 8
        cu.use_fill_caps = True
        cu.twist_mode = 'MINIMUM'
        sp = cu.splines.new('POLY')
        sp.points.add(len(pts) - 1)
        for p, (co, r) in zip(sp.points, pts):
            p.co = (co.x, co.y, co.z, 1.0)
            p.radius = r
        ob = bpy.data.objects.new(cu.name, cu)
        bpy.context.scene.collection.objects.link(ob)
        dg = bpy.context.evaluated_depsgraph_get()
        me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
        bm.from_mesh(me)
        bpy.data.objects.remove(ob, do_unlink=True)
        bpy.data.curves.remove(cu)
        bpy.data.meshes.remove(me)
    me = bpy.data.meshes.new("_tubes")
    bm.to_mesh(me)
    bm.free()
    return me


def fuse_and_smooth(me):
    """Voxel remesh fuses the branches into one organic surface."""
    ob = bpy.data.objects.new("_fuse", me)
    bpy.context.scene.collection.objects.link(ob)
    rm = ob.modifiers.new("Remesh", 'REMESH')
    rm.mode = 'VOXEL'
    rm.voxel_size = VOXEL
    rm.adaptivity = 0.0
    sm = ob.modifiers.new("Smooth", 'SMOOTH')
    sm.factor = 0.7
    sm.iterations = 4
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    out = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    out.name = "CardiacFibres"
    bpy.data.objects.remove(ob, do_unlink=True)
    bpy.data.meshes.remove(me)
    return out


# --------------------------------------------------------------------------
# Surface detail: striations + intercalated discs
# --------------------------------------------------------------------------
def build_axis_samples(lines):
    samples = []        # (fid, u, pos, t, N, B, r)
    discs = []          # per line: list of (u, amp, n, phase)
    Z = Vector((0, 0, 1))
    for fid, pts in enumerate(lines):
        u = 0.0
        total = sum((pts[k + 1][0] - pts[k][0]).length for k in range(len(pts) - 1))
        for k, (co, r) in enumerate(pts):
            if k > 0:
                u += (co - pts[k - 1][0]).length
            a = pts[max(k - 1, 0)][0]
            b = pts[min(k + 1, len(pts) - 1)][0]
            t = (b - a).normalized()
            N = (Z - Z.dot(t) * t).normalized()
            B = t.cross(N)
            samples.append((fid, u, co.copy(), t, N, B, r))
        # intercalated discs every 4 - 6.5 radii
        d = []
        pos = random.uniform(2.0, 4.0)
        while pos < total - 1.5:
            d.append((pos, random.uniform(0.08, 0.16), random.choice((2, 3, 4)),
                      random.uniform(0, 6.28)))
            pos += random.uniform(4.0, 6.5)
        discs.append(d)
    return samples, discs


def sculpt_detail(me, lines, n_main):
    samples, discs = build_axis_samples(lines)
    # two trees: straight (main) fibres and diagonal branches
    main_ids = [i for i, s in enumerate(samples) if s[0] < n_main]
    br_ids = [i for i, s in enumerate(samples) if s[0] >= n_main]
    kd_m = kdtree.KDTree(len(main_ids))
    for i in main_ids:
        kd_m.insert(samples[i][2], i)
    kd_m.balance()
    kd_b = kdtree.KDTree(max(1, len(br_ids)))
    for i in br_ids:
        kd_b.insert(samples[i][2], i)
    kd_b.balance()

    n = len(me.vertices)
    co = np.empty(n * 3); me.vertices.foreach_get("co", co); co = co.reshape(n, 3)
    nrm = np.empty(n * 3); me.vertices.foreach_get("normal", nrm); nrm = nrm.reshape(n, 3)

    # nearest centre-line sample + organic noise (the only per-vertex python loop)
    idx_m = np.empty(n, dtype=np.int64)
    idx_b = np.empty(n, dtype=np.int64)
    organic = np.empty(n)
    nn = noise.noise
    has_br = len(br_ids) > 0
    for i, v in enumerate(me.vertices):
        p = v.co
        idx_m[i] = kd_m.find(p)[1]
        idx_b[i] = kd_b.find(p)[1] if has_br else idx_m[i]
        organic[i] = nn(p * 1.3) * 0.035 + nn(p * 4.0) * 0.008

    S_fid = np.array([s[0] for s in samples])
    S_u = np.array([s[1] for s in samples])
    S_c = np.array([tuple(s[2]) for s in samples])
    S_t = np.array([tuple(s[3]) for s in samples])
    S_N = np.array([tuple(s[4]) for s in samples])
    S_B = np.array([tuple(s[5]) for s in samples])
    S_r = np.array([s[6] for s in samples])

    # Owner = the tube whose SURFACE is closest (distance to axis minus radius).
    # This gives a clean boundary curve where a branch leaves / joins a fibre,
    # instead of a patchwork of mixed stripes.
    d_m = np.linalg.norm(co - S_c[idx_m], axis=1) - S_r[idx_m]
    d_b = np.linalg.norm(co - S_c[idx_b], axis=1) - S_r[idx_b]
    if not has_br:
        d_b = d_b + 1e9
    on_branch = d_b < d_m
    idx = np.where(on_branch, idx_b, idx_m)
    seam = np.exp(-((d_b - d_m) / SEAM_WIDTH) ** 2)
    seam[np.minimum(d_b, d_m) > 0.35] = 0.0      # only on the real surface crease

    fid = S_fid[idx]
    t = S_t[idx]
    d = co - S_c[idx]
    axial = np.einsum('ij,ij->i', d, t)
    uu = S_u[idx] + axial
    radial = d - axial[:, None] * t
    theta = np.arctan2(np.einsum('ij,ij->i', radial, S_B[idx]),
                       np.einsum('ij,ij->i', radial, S_N[idx]))

    # only on the sides of the fibre, not on the cut end caps
    side = 1.0 - np.abs(np.einsum('ij,ij->i', nrm, t))
    w = np.clip((side - 0.25) / 0.45, 0.0, 1.0)

    g = (0.5 - 0.5 * np.cos(2 * np.pi * uu / STRIATION_PITCH)) ** 1.6
    g = g * (1.0 - seam)        # stripes stop cleanly at the seam

    dc = np.zeros(n)
    for f_i, dl in enumerate(discs):
        sel = np.nonzero(fid == f_i)[0]
        if len(sel) == 0:
            continue
        for (pu, amp, nz, ph) in dl:
            s2 = sel[np.abs(uu[sel] - pu) < 0.5]
            off = amp * np.tanh(4.0 * np.sin(nz * theta[s2] + ph))
            dist = uu[s2] - (pu + off)
            dc[s2] = np.maximum(dc[s2], np.exp(-(dist / DISC_WIDTH) ** 2))

    # ---- Nuclei: one oval "grain" per cell, part of the same solid mesh ----
    nuclei = []
    for f_i in range(n_main):
        sel_s = np.nonzero(S_fid == f_i)[0]
        su = S_u[sel_s]
        bounds = [0.0] + [dd[0] for dd in discs[f_i]] + [su.max()]
        for b0, b1 in zip(bounds[:-1], bounds[1:]):
            if b1 - b0 < 2.2:
                continue
            un = 0.5 * (b0 + b1) + random.uniform(-0.3, 0.3)
            k = sel_s[np.argmin(np.abs(su - un))]
            c = Vector(S_c[k])
            if abs(c.x) > X_CUT - 0.9:
                continue
            r = S_r[k]
            Nk, Bk = Vector(S_N[k]), Vector(S_B[k])
            th = None
            # face the outside of the bundle so the nuclei are visible
            o = Vector((0.0, c.y, c.z))
            th_out = math.atan2(o.dot(Bk), o.dot(Nk)) if o.length > 0.5 else None
            for _try in range(10):           # pick a side that is clear of branches
                if th_out is not None and _try < 7:
                    cand = th_out + random.uniform(-0.9, 0.9)
                else:
                    cand = random.uniform(-math.pi, math.pi)
                p_s = c + (Nk * math.cos(cand) + Bk * math.sin(cand)) * r
                if not has_br:
                    th = cand
                    break
                _, kb, db = kd_b.find(p_s)
                if db - S_r[kb] > 0.6:
                    th = cand
                    break
            if th is None:
                continue
            nuclei.append((f_i, un, th,
                           r * random.uniform(0.68, 0.80), r * random.uniform(0.36, 0.42),
                           NUCLEUS_HEIGHT * random.uniform(0.9, 1.1)))
    qmin = np.full(n, 9.0)
    best = []                          # vertex closest to each nucleus centre
    r_loc = S_r[idx]
    for (f_i, un, th, A, Bn, H) in nuclei:
        sel = np.nonzero((fid == f_i) & (np.abs(uu - un) < A * 1.3))[0]
        if len(sel) == 0:
            best.append(-1)
            continue
        dth = (theta[sel] - th + np.pi) % (2 * np.pi) - np.pi
        q = ((uu[sel] - un) / A) ** 2 + (dth * r_loc[sel] / Bn) ** 2
        qmin[sel] = np.minimum(qmin[sel], q)
        best.append(int(sel[np.argmin(q)]))
    # no stripes / discs under a nucleus: smooth seat with a clean rim
    clear = np.clip((qmin - 0.8) / 0.35, 0.0, 1.0)
    clear = clear * clear * (3 - 2 * clear)
    g = g * clear
    dc = dc * clear
    nuc_a = np.clip((1.0 - qmin) * 4.0, 0.0, 1.0)

    disp = w * (-STRIATION_DEPTH * g - DISC_DEPTH * dc - SEAM_DEPTH * seam) + organic
    co = co + nrm * disp[:, None]

    # ---- separate nucleus "grains" + matching sockets carved in the fibre ----
    grains = []
    for (f_i, un, th, A, Bn, H), kv in zip(nuclei, best):
        if kv < 0:
            continue
        t_k = t[kv] / np.linalg.norm(t[kv])
        n_k = nrm[kv] - np.dot(nrm[kv], t_k) * t_k
        n_k /= np.linalg.norm(n_k)
        b_k = np.cross(n_k, t_k)                 # (t, b, n) right-handed
        P = co[kv] - n_k * (NUCLEUS_SINK * r_loc[kv])
        grains.append((P.copy(), t_k, b_k, n_k, A, Bn, H))
        # socket = the grain's lower half, enlarged by the fit clearance
        Ae, Be, Ce = A + NUCLEUS_CLEARANCE, Bn + NUCLEUS_CLEARANCE, H + NUCLEUS_CLEARANCE
        dv = co - P
        x = dv @ t_k
        y = dv @ b_k
        zz = dv @ n_k
        qq = (x / Ae) ** 2 + (y / Be) ** 2
        m = (qq < 1.0) & (np.abs(zz) < Ce * 1.5) & (np.abs(x) < Ae) & (np.abs(y) < Be)
        ze = -Ce * np.sqrt(np.clip(1.0 - qq[m], 0.0, 1.0))
        push = np.clip(zz[m] - ze, 0.0, None)
        co[m] -= np.outer(push, n_k)
    sculpt_detail.grains = grains
    sculpt_detail.n_nuclei = len(grains)
    dc = np.maximum(dc, seam)   # seam gets the same dark colour as the discs
    me.vertices.foreach_set("co", co.ravel())

    stria = g * w
    disc_a = dc * w
    me.attributes.new("stria", 'FLOAT', 'POINT').data.foreach_set("value", stria)
    me.attributes.new("disc", 'FLOAT', 'POINT').data.foreach_set("value", disc_a)
    me.attributes.new("nucleus", 'FLOAT', 'POINT').data.foreach_set("value", nuc_a)

    # baked vertex colour too (for GLB / viewport / other software)
    base = np.array((0.52, 0.07, 0.05))
    dark = np.array((0.20, 0.015, 0.012))
    pale = np.array((0.24, 0.06, 0.06))
    c = base + (dark - base) * stria[:, None]
    c = c + (pale - c) * disc_a[:, None]
    purple = np.array((0.30, 0.16, 0.42))
    c = c + (purple - c) * nuc_a[:, None]
    rgba = np.concatenate([c, np.ones((n, 1))], axis=1)
    me.color_attributes.new("Col", 'FLOAT_COLOR', 'POINT').data.foreach_set("color", rgba.ravel())
    me.update()
    return samples, discs


# --------------------------------------------------------------------------
# Flat, level ends (top and bottom) - good for display and 3D printing
# --------------------------------------------------------------------------
def cut_flat_ends(me):
    bm = bmesh.new()
    bm.from_mesh(me)
    for sign in (1.0, -1.0):
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        res = bmesh.ops.bisect_plane(bm, geom=geom, dist=1e-5,
                                     plane_co=(sign * X_CUT, 0, 0),
                                     plane_no=(sign, 0, 0), clear_outer=True)
        cut_edges = [e for e in res['geom_cut'] if isinstance(e, bmesh.types.BMEdge)]
        bmesh.ops.holes_fill(bm, edges=cut_edges, sides=0)
    # triangulate the new flat caps so the mesh is clean for slicers
    caps = [f for f in bm.faces if len(f.verts) > 4]
    if caps:
        bmesh.ops.triangulate(bm, faces=caps)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    for f in bm.faces:
        f.smooth = abs(f.normal.x) < 0.999
    bm.to_mesh(me)
    bm.free()
    me.update()


# --------------------------------------------------------------------------
# Nuclei - separate grains (one object each)
# --------------------------------------------------------------------------
def make_grain_meshes(grains):
    meshes = []
    for i, (P, t_k, b_k, n_k, A, Bn, H) in enumerate(grains):
        bm = bmesh.new()
        rot = Matrix((Vector(t_k), Vector(b_k), Vector(n_k))).transposed().to_4x4()
        mat = Matrix.Translation(Vector(P)) @ rot @ Matrix.Diagonal((A, Bn, H, 1.0))
        bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=24, radius=1.0, matrix=mat)
        for f in bm.faces:
            f.smooth = True
        me = bpy.data.meshes.new("Nucleus_%02d" % (i + 1))
        bm.to_mesh(me)
        bm.free()
        meshes.append(me)
    return meshes


# --------------------------------------------------------------------------
# Materials
# --------------------------------------------------------------------------
def _principled(nt):
    for n in nt.nodes:
        if n.type == 'BSDF_PRINCIPLED':
            return n
    return nt.nodes.new('ShaderNodeBsdfPrincipled')


def _set(node, name, value):
    if name in node.inputs:
        node.inputs[name].default_value = value


def material_fibre():
    m = bpy.data.materials.new("Cardiac_Fibre")
    m.use_nodes = True
    nt = m.node_tree
    bsdf = _principled(nt)
    L = nt.links

    a_str = nt.nodes.new('ShaderNodeAttribute'); a_str.attribute_name = "stria"
    a_dsc = nt.nodes.new('ShaderNodeAttribute'); a_dsc.attribute_name = "disc"
    tc = nt.nodes.new('ShaderNodeTexCoord')
    nz = nt.nodes.new('ShaderNodeTexNoise')
    nz.inputs['Scale'].default_value = 60.0
    nz.inputs['Detail'].default_value = 6.0
    L.new(tc.outputs['Object'], nz.inputs['Vector'])

    m1 = nt.nodes.new('ShaderNodeMix'); m1.data_type = 'RGBA'
    m1.inputs['A'].default_value = (0.52, 0.07, 0.05, 1)
    m1.inputs['B'].default_value = (0.20, 0.015, 0.012, 1)
    str_ramp = nt.nodes.new('ShaderNodeMapRange')
    str_ramp.inputs['To Max'].default_value = 0.95
    L.new(a_str.outputs['Fac'], str_ramp.inputs['Value'])
    L.new(str_ramp.outputs['Result'], m1.inputs['Factor'])

    m2 = nt.nodes.new('ShaderNodeMix'); m2.data_type = 'RGBA'
    m2.inputs['B'].default_value = (0.24, 0.06, 0.06, 1)
    L.new(m1.outputs['Result'], m2.inputs['A'])
    L.new(a_dsc.outputs['Fac'], m2.inputs['Factor'])

    m3 = nt.nodes.new('ShaderNodeMix'); m3.data_type = 'RGBA'
    m3.blend_type = 'OVERLAY'
    m3.inputs['Factor'].default_value = 0.15
    L.new(m2.outputs['Result'], m3.inputs['A'])
    L.new(nz.outputs['Color'], m3.inputs['B'])
    # nuclei (purple grains)
    a_nuc = nt.nodes.new('ShaderNodeAttribute'); a_nuc.attribute_name = "nucleus"
    nz2 = nt.nodes.new('ShaderNodeTexNoise')
    nz2.inputs['Scale'].default_value = 400.0
    L.new(tc.outputs['Object'], nz2.inputs['Vector'])
    pm = nt.nodes.new('ShaderNodeMix'); pm.data_type = 'RGBA'
    pm.inputs['A'].default_value = (0.30, 0.16, 0.42, 1)
    pm.inputs['B'].default_value = (0.19, 0.09, 0.29, 1)
    L.new(nz2.outputs['Fac'], pm.inputs['Factor'])
    m4 = nt.nodes.new('ShaderNodeMix'); m4.data_type = 'RGBA'
    L.new(m3.outputs['Result'], m4.inputs['A'])
    L.new(pm.outputs['Result'], m4.inputs['B'])
    L.new(a_nuc.outputs['Fac'], m4.inputs['Factor'])
    L.new(m4.outputs['Result'], bsdf.inputs['Base Color'])

    bump = nt.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.15
    bump.inputs['Distance'].default_value = 0.0004
    L.new(nz.outputs['Fac'], bump.inputs['Height'])
    L.new(bump.outputs['Normal'], bsdf.inputs['Normal'])

    _set(bsdf, 'Roughness', 0.55)
    _set(bsdf, 'Specular IOR Level', 0.35)
    _set(bsdf, 'Subsurface Weight', 0.25)
    _set(bsdf, 'Subsurface Radius', (1.0, 0.15, 0.08))
    _set(bsdf, 'Subsurface Scale', 0.004)
    _set(bsdf, 'Coat Weight', 0.04)
    _set(bsdf, 'Coat Roughness', 0.25)
    _set(bsdf, 'Sheen Weight', 0.0)
    return m


def material_nucleus():
    m = bpy.data.materials.new("Nucleus")
    m.use_nodes = True
    nt = m.node_tree
    bsdf = _principled(nt)
    L = nt.links
    tc = nt.nodes.new('ShaderNodeTexCoord')
    nz = nt.nodes.new('ShaderNodeTexNoise')
    nz.inputs['Scale'].default_value = 400.0
    nz.inputs['Detail'].default_value = 4.0
    L.new(tc.outputs['Object'], nz.inputs['Vector'])
    mix = nt.nodes.new('ShaderNodeMix'); mix.data_type = 'RGBA'
    mix.inputs['A'].default_value = (0.30, 0.16, 0.42, 1)
    mix.inputs['B'].default_value = (0.19, 0.09, 0.29, 1)
    L.new(nz.outputs['Fac'], mix.inputs['Factor'])
    L.new(mix.outputs['Result'], bsdf.inputs['Base Color'])
    bump = nt.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.3
    bump.inputs['Distance'].default_value = 0.0003
    L.new(nz.outputs['Fac'], bump.inputs['Height'])
    L.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    _set(bsdf, 'Roughness', 0.35)
    _set(bsdf, 'Subsurface Weight', 0.2)
    _set(bsdf, 'Subsurface Radius', (0.6, 0.4, 1.0))
    _set(bsdf, 'Subsurface Scale', 0.002)
    _set(bsdf, 'Coat Weight', 0.3)
    return m


# --------------------------------------------------------------------------
# Camera / lights / render
# --------------------------------------------------------------------------
def setup_stage(height):
    sc = bpy.context.scene
    target = Vector((0, 0, height * 0.5))

    cam_data = bpy.data.cameras.new("Camera")
    cam_data.lens = 60
    cam = bpy.data.objects.new("Camera", cam_data)
    sc.collection.objects.link(cam)
    cam.location = target + Vector((0.16, -0.50, 0.15))
    cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
    sc.camera = cam

    def area(name, loc, energy, size, color=(1, 1, 1)):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = energy
        ld.size = size
        ld.color = color
        lo = bpy.data.objects.new(name, ld)
        sc.collection.objects.link(lo)
        lo.location = loc
        lo.rotation_euler = (target - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()

    area("Key", (-0.6, -0.7, 0.9), 60, 0.6, (1.0, 0.97, 0.93))
    area("Fill", (0.8, -0.5, 0.3), 18, 0.8, (0.92, 0.95, 1.0))
    area("Rim", (0.2, 0.9, 0.6), 45, 0.5)

    world = sc.world or bpy.data.worlds.new("World")
    sc.world = world
    world.use_nodes = True
    wn = world.node_tree.nodes
    wl = world.node_tree.links
    bg = wn.get("Background")
    out = wn.get("World Output")
    if bg and out:
        # soft dim light on the model, light-grey backdrop for the camera
        bg.inputs[0].default_value = (0.80, 0.82, 0.86, 1)
        bg.inputs[1].default_value = 0.25
        cam_bg = wn.new('ShaderNodeBackground')
        cam_bg.inputs[0].default_value = (0.88, 0.89, 0.91, 1)
        cam_bg.inputs[1].default_value = 1.0
        lp = wn.new('ShaderNodeLightPath')
        mx = wn.new('ShaderNodeMixShader')
        wl.new(lp.outputs['Is Camera Ray'], mx.inputs[0])
        wl.new(bg.outputs[0], mx.inputs[1])
        wl.new(cam_bg.outputs[0], mx.inputs[2])
        wl.new(mx.outputs[0], out.inputs['Surface'])

    sc.render.engine = 'CYCLES'
    sc.cycles.samples = 96
    sc.cycles.use_denoising = True
    sc.render.resolution_x = 1000
    sc.render.resolution_y = 1400
    sc.view_settings.view_transform = 'Standard'
    sc.view_settings.look = 'None'


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main():
    reset_scene()
    fibres = build_layout()
    lines = make_centerlines(fibres)

    tubes = curve_tube_mesh(lines)
    fibre_me = fuse_and_smooth(tubes)
    _, discs = sculpt_detail(fibre_me, lines, len(fibres))
    cut_flat_ends(fibre_me)

    # Stand the fibres up (X -> Z), real size: height = TARGET_HEIGHT_M, base on z = 0
    ys = [v.co.y for v in fibre_me.vertices]
    zs = [v.co.z for v in fibre_me.vertices]
    cy, cz = (max(ys) + min(ys)) * 0.5, (max(zs) + min(zs)) * 0.5
    s = TARGET_HEIGHT_M / (2.0 * X_CUT)
    M = (Matrix.Translation((0, 0, TARGET_HEIGHT_M * 0.5)) @
         Matrix.Diagonal((s, s, s, 1.0)) @
         Matrix.Rotation(math.radians(-90), 4, 'Y') @
         Matrix.Translation((0, -cy, -cz)))
    fibre_me.transform(M)

    fibre_me.materials.append(material_fibre())

    coll = bpy.data.collections.new("Cardiac_Muscle")
    bpy.context.scene.collection.children.link(coll)
    ob_f = bpy.data.objects.new("Cardiac_Fibres", fibre_me)
    coll.objects.link(ob_f)

    # nuclei: separate grains, each its own object, seated in its socket
    coll_n = bpy.data.collections.new("Nuclei")
    coll.children.link(coll_n)
    mat_n = material_nucleus()
    for me in make_grain_meshes(sculpt_detail.grains):
        me.transform(M)
        me.materials.append(mat_n)
        ob = bpy.data.objects.new(me.name, me)
        coll_n.objects.link(ob)

    setup_stage(TARGET_HEIGHT_M)

    dims = ob_f.dimensions
    print("Cardiac muscle built: %d fibre verts, %d nuclei" % (len(fibre_me.vertices), sculpt_detail.n_nuclei))
    print("Size (cm): X=%.1f  Y=%.1f  Z=%.1f" % (dims.x * 100, dims.y * 100, dims.z * 100))

    if DO_RENDER:
        bpy.context.scene.render.filepath = RENDER_PATH
        bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
