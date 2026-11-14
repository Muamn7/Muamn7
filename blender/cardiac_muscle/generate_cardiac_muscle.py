"""
Cardiac muscle tissue - procedural high-detail model for Blender (4.2+ / 5.x)
نموذج نسيج عضلة القلب - تصميم عالي الدقة

How to use / طريقة الاستخدام:
  Blender > Scripting tab > Open this file > Run Script
  (or headless:  blender -b -P generate_cardiac_muscle.py)

What it builds / ماذا يبني:
  * Straight striated fibres + diagonal branches as SEPARATE pieces that sit
    on the fibres (each branch is cut to the fibre shape so they fit together)
  * Real geometric striations (cross stripes) following each fibre
  * Intercalated discs (zig-zag step grooves) between cells
  * Purple oval nuclei as SEPARATE grains (one object each), one per cell
  * 3-colour 3MF export (red muscle, white disc lines, purple nuclei)
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
DISC_DEPTH = 0.06            # shallow groove; the disc lines are printed WHITE
DISC_WIDTH = 0.05
BAND_HALF = 0.07            # half width of the white disc line (~1.3 mm wide)
BAND_DEPTH = 0.22           # how deep the white goes into the fibre (~2 mm)
BRANCH_SPAN = (2.4, 3.4)    # short, steep diagonal branches (cut cleanly at both fibres)
BRANCH_CLEARANCE = -0.03    # negative = branch sinks ~0.3 mm into the fibre, so the model prints as one solid
NUCLEUS_HEIGHT = 0.24       # how far each nucleus grain sticks out of the fibre (fibre-radius units)
NUCLEUS_SINK = 0.05         # grain sits slightly into its seat
NUCLEUS_CLEARANCE = -0.02   # negative = grain overlaps its seat ~0.2 mm (prints attached, no floating parts)
DO_RENDER = False           # set True to render a preview PNG next to the .blend
EXPORT_3MF = ""             # e.g. "//cardiac_muscle_3colors.3mf" -> 3-colour print file
COLOR_RED = "#B3261E"       # filament 1: fibres + branches
COLOR_WHITE = "#F2F2F2"     # filament 2: intercalated disc lines
COLOR_PURPLE = "#7B3FA0"    # filament 3: nuclei
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
        span = random.uniform(*BRANCH_SPAN)
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
        # straight diagonal bridge from axis to axis: once the fibres are
        # subtracted it becomes a short piece with clean saddle-shaped cuts
        p0, p3 = a.pos(x0), b.pos(x1)
        ra, rb = a.radius(x0) * 0.84, b.radius(x1) * 0.84
        n = 40
        pts = []
        for k in range(n + 1):
            t = k / n
            r = ra * (1 - t) + rb * t
            r *= 1.0 - 0.08 * math.sin(math.pi * t)
            pts.append((p0.lerp(p3, t), r))
        lines.append(pts)
        used.append((i, j, x0))
        n_branch += 1
    return lines


def curve_tube_mesh(lines, r_add=0.0):
    """Bevelled poly curves -> one combined mesh (r_add enlarges every radius)."""
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
            p.radius = r + r_add
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


def boolean_difference(me, cutter_me):
    """me minus cutter (cutter mesh is kept)."""
    ob = bpy.data.objects.new("_piece", me)
    oc = bpy.data.objects.new("_cutter", cutter_me)
    sc = bpy.context.scene.collection
    sc.objects.link(ob)
    sc.objects.link(oc)
    mod = ob.modifiers.new("Bool", 'BOOLEAN')
    mod.operation = 'DIFFERENCE'
    mod.object = oc
    solvers = mod.bl_rna.properties['solver'].enum_items.keys()
    mod.solver = 'MANIFOLD' if 'MANIFOLD' in solvers else 'EXACT'
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    out = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    bpy.data.objects.remove(ob, do_unlink=True)
    bpy.data.objects.remove(oc, do_unlink=True)
    bpy.data.meshes.remove(me)
    return out


def keep_main_islands(me, min_share=0.03):
    """Drop tiny loose fragments a boolean can leave behind."""
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    seen = set()
    islands = []
    for v in bm.verts:
        if v.index in seen:
            continue
        stack, isl = [v], []
        seen.add(v.index)
        while stack:
            x = stack.pop()
            isl.append(x)
            for e in x.link_edges:
                o = e.other_vert(x)
                if o.index not in seen:
                    seen.add(o.index)
                    stack.append(o)
        islands.append(isl)
    total = len(bm.verts)
    kill = [v for isl in islands if len(isl) < min_share * total for v in isl]
    if kill:
        bmesh.ops.delete(bm, geom=kill, context='VERTS')
    bm.to_mesh(me)
    bm.free()
    me.update()


# --------------------------------------------------------------------------
# Surface detail: striations + intercalated discs
# --------------------------------------------------------------------------
def build_axis_samples(lines, n_main):
    samples = []        # (fid, u, pos, t, N, B, r)
    discs = []          # per line: list of (u, amp, n, phase)
    Z = Vector((0, 0, 1))
    # branch axes, to keep the (white) disc lines away from branch joints
    br_pts = [(co, r) for pts in lines[n_main:] for (co, r) in pts]
    kd_b = kdtree.KDTree(max(1, len(br_pts)))
    for i, (co, r) in enumerate(br_pts):
        kd_b.insert(co, i)
    kd_b.balance()

    def disc_clear(start, u):
        _, co, t, N, B, r = min(((abs(s_[1] - u),) + s_[2:] for s_ in samples[start:]
                                 if abs(s_[1] - u) < 0.06), key=lambda q: q[0])
        for i in range(24):
            a = 2 * math.pi * i / 24
            p = co + (N * math.cos(a) + B * math.sin(a)) * (r + 0.1)
            _, j, dist = kd_b.find(p)
            if br_pts and dist < br_pts[j][1] + 0.35:
                return False
        return True

    for fid, pts in enumerate(lines):
        start = len(samples)
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
        # intercalated discs every 4 - 6.5 radii (straight fibres only)
        d = []
        pos = random.uniform(2.0, 4.0)
        while fid < n_main and pos < total - 1.5:
            amp, nz, ph = random.uniform(0.08, 0.16), random.choice((2, 3, 4)), random.uniform(0, 6.28)
            for shift in (0.0, 0.6, -0.6, 1.2, -1.2):
                if 0.5 < pos + shift < total - 0.5 and disc_clear(start, pos + shift):
                    d.append((pos + shift, amp, nz, ph))
                    break
            pos += random.uniform(4.0, 6.5)
        discs.append(d)
    return samples, discs


def sculpt_detail(me, samples, discs, n_main, mode):
    """mode 'main': straight fibres (+ nucleus sockets); 'branch': a diagonal branch piece."""
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

    # distance to the straight-fibre / branch tube surfaces
    d_m = np.linalg.norm(co - S_c[idx_m], axis=1) - S_r[idx_m]
    d_b = np.linalg.norm(co - S_c[idx_b], axis=1) - S_r[idx_b]
    if not has_br:
        d_b = d_b + 1e9
    if mode == 'branch':
        idx = idx_b
        contact = d_m < BRANCH_CLEARANCE + 0.06      # face that rests on a fibre
    else:
        idx = idx_m
        contact = d_b < 0.12                         # area a branch rests on

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
    if mode == 'branch':
        w[contact] = 0.0          # keep the fitting face exact
    organic[contact] = np.minimum(organic[contact], 0.0)
    organic[contact & (mode == 'branch')] = 0.0

    g = (0.5 - 0.5 * np.cos(2 * np.pi * uu / STRIATION_PITCH)) ** 1.6

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
    for f_i in (range(n_main) if mode == 'main' else []):
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

    disp = w * (-STRIATION_DEPTH * g - DISC_DEPTH * dc) + organic
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
    if mode == 'main':
        sculpt_detail.grains = grains
        sculpt_detail.n_nuclei = len(grains)
    me.vertices.foreach_set("co", co.ravel())

    stria = g * w
    disc_a = dc * w
    me.attributes.new("stria", 'FLOAT', 'POINT').data.foreach_set("value", stria)
    me.attributes.new("disc", 'FLOAT', 'POINT').data.foreach_set("value", disc_a)
    me.attributes.new("nucleus", 'FLOAT', 'POINT').data.foreach_set("value", nuc_a)

    # baked vertex colour too (for GLB / viewport / other software)
    base = np.array((0.52, 0.07, 0.05))
    dark = np.array((0.20, 0.015, 0.012))
    pale = np.array((0.90, 0.88, 0.86))
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
# White intercalated-disc bands (zig-zag rings, used for the 3-colour print)
# --------------------------------------------------------------------------
def make_disc_bands(samples, discs, n_main, steps=256):
    by_f = {}
    for s_ in samples:
        by_f.setdefault(s_[0], []).append(s_)
    bm = bmesh.new()
    prof = ((-BAND_HALF, -BAND_DEPTH), (BAND_HALF, -BAND_DEPTH),
            (BAND_HALF, 0.10), (-BAND_HALF, 0.10))
    for f_i in range(n_main):
        ss = by_f[f_i]
        us = np.array([s_[1] for s_ in ss])
        for (pu, amp, nz, ph) in discs[f_i]:
            rings = []
            for i in range(steps):
                th = 2 * math.pi * i / steps
                uc = pu + amp * math.tanh(4.0 * math.sin(nz * th + ph))
                ring = []
                for du, dr in prof:
                    u = uc + du
                    _, _, c, t, N, B, r = ss[int(np.argmin(np.abs(us - u)))]
                    p = c + t * (u - ss[int(np.argmin(np.abs(us - u)))][1]) \
                        + (N * math.cos(th) + B * math.sin(th)) * (r + dr)
                    ring.append(bm.verts.new(p))
                rings.append(ring)
            for i in range(steps):
                a, b = rings[i], rings[(i + 1) % steps]
                for j in range(4):
                    bm.faces.new((a[j], b[j], b[(j + 1) % 4], a[(j + 1) % 4]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new("Disc_Bands")
    bm.to_mesh(me)
    bm.free()
    return me


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
    m2.inputs['B'].default_value = (0.90, 0.88, 0.86, 1)   # white disc lines
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
# 3D-print export: one 3MF, three colours (red / white / purple)
# --------------------------------------------------------------------------
def _tri_copy(me, name):
    c = me.copy()
    c.name = name
    bm = bmesh.new()
    bm.from_mesh(c)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bm.to_mesh(c)
    bm.free()
    return c


def _boolean_stack(base_me, ops):
    """Apply (operation, mesh-or-list-of-meshes) booleans in order (Manifold solver)."""
    sc = bpy.context.scene.collection
    ob = bpy.data.objects.new("_bool_base", base_me)
    sc.objects.link(ob)
    temps = []
    for k, (op, meshes) in enumerate(ops):
        coll = bpy.data.collections.new("_bool_%d" % k)
        for me in (meshes if isinstance(meshes, list) else [meshes]):
            o = bpy.data.objects.new("_op", me)
            coll.objects.link(o)
            temps.append(o)
        mod = ob.modifiers.new("B%d" % k, 'BOOLEAN')
        mod.operation = op
        mod.operand_type = 'COLLECTION'
        mod.collection = coll
        solvers = mod.bl_rna.properties['solver'].enum_items.keys()
        mod.solver = 'MANIFOLD' if 'MANIFOLD' in solvers else 'EXACT'
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    out = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    for mod in ob.modifiers:
        bpy.data.collections.remove(mod.collection)
    bpy.data.objects.remove(ob, do_unlink=True)
    for o in temps:
        bpy.data.objects.remove(o, do_unlink=True)
    bm = bmesh.new()
    bm.from_mesh(out)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bm.to_mesh(out)
    bm.free()
    return out


def build_print_parts():
    """Return [(name, mesh, colour, filament)] - three solids that touch but never overlap."""
    fib = bpy.data.objects["Cardiac_Fibres"].data
    bands = bpy.data.objects["Disc_Bands_White"].data
    branches = [o.data for o in bpy.data.collections["Branches"].objects]
    nuclei = [o.data for o in bpy.data.collections["Nuclei"].objects]
    temps = []

    def T(me):
        c = _tri_copy(me, "_tmp_print")
        temps.append(c)
        return c

    # white = fibre material inside the disc bands (minus nuclei)
    white = _boolean_stack(T(fib), [('INTERSECT', T(bands)),
                                    ('DIFFERENCE', [T(m) for m in nuclei])])
    # red = fibres without the white bands + branches, minus nuclei
    red = _boolean_stack(T(fib), [('DIFFERENCE', T(bands)),
                                  ('UNION', [T(m) for m in branches]),
                                  ('DIFFERENCE', [T(m) for m in nuclei])])
    # purple = the nucleus grains
    bm = bmesh.new()
    for m in nuclei:
        bm.from_mesh(m)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    purple = bpy.data.meshes.new("print_purple")
    bm.to_mesh(purple)
    bm.free()
    for m in temps:
        if m.users == 0:
            bpy.data.meshes.remove(m)
    red.name, white.name = "print_red", "print_white"
    return [("1_Red_muscle", red, COLOR_RED, 1),
            ("2_White_discs", white, COLOR_WHITE, 2),
            ("3_Purple_nuclei", purple, COLOR_PURPLE, 3)]


def write_3mf(path, parts, name="Cardiac_Muscle_3colors", plate_center=(128.0, 128.0)):
    """3MF with one object made of coloured parts. Works in Bambu Studio / OrcaSlicer
    (per-part filament in Metadata/model_settings.config) and shows colours in any
    3MF viewer (basematerials)."""
    import zipfile
    from xml.sax.saxutils import quoteattr
    out = []
    w = out.append
    w('<?xml version="1.0" encoding="UTF-8"?>\n')
    w('<model unit="millimeter" xml:lang="en-US" '
      'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">\n')
    w(' <metadata name="Title">Cardiac muscle tissue (3 colours)</metadata>\n')
    w(' <metadata name="Application">Blender cardiac_muscle generator</metadata>\n')
    w(' <resources>\n  <basematerials id="1">\n')
    for pname, _me, col, _f in parts:
        w('   <base name=%s displaycolor="%sFF"/>\n' % (quoteattr(pname), col))
    w('  </basematerials>\n')
    for k, (pname, me, _col, _f) in enumerate(parts):
        me.calc_loop_triangles()
        v = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", v)
        v = v.reshape(-1, 3) * 1000.0                       # metres -> mm
        tri = np.empty(len(me.loop_triangles) * 3, dtype=np.int64)
        me.loop_triangles.foreach_get("vertices", tri)
        tri = tri.reshape(-1, 3)
        w('  <object id="%d" name=%s type="model" pid="1" pindex="%d">\n   <mesh>\n    <vertices>\n'
          % (k + 2, quoteattr(pname), k))
        w("".join('     <vertex x="%.4f" y="%.4f" z="%.4f"/>\n' % tuple(r) for r in v.tolist()))
        w('    </vertices>\n    <triangles>\n')
        w("".join('     <triangle v1="%d" v2="%d" v3="%d"/>\n' % tuple(t) for t in tri.tolist()))
        w('    </triangles>\n   </mesh>\n  </object>\n')
    oid = len(parts) + 2
    w('  <object id="%d" name=%s type="model">\n   <components>\n' % (oid, quoteattr(name)))
    for k in range(len(parts)):
        w('    <component objectid="%d"/>\n' % (k + 2))
    w('   </components>\n  </object>\n </resources>\n <build>\n')
    w('  <item objectid="%d" transform="1 0 0 0 1 0 0 0 1 %.3f %.3f 0"/>\n'
      % (oid, plate_center[0], plate_center[1]))
    w(' </build>\n</model>\n')

    cfg = ['<?xml version="1.0" encoding="UTF-8"?>\n<config>\n',
           '  <object id="%d">\n' % oid,
           '    <metadata key="name" value=%s/>\n' % quoteattr(name),
           '    <metadata key="extruder" value="1"/>\n']
    for k, (pname, _me, _col, fil) in enumerate(parts):
        cfg += ['    <part id="%d" subtype="normal_part">\n' % (k + 2),
                '      <metadata key="name" value=%s/>\n' % quoteattr(pname),
                '      <metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>\n',
                '      <metadata key="extruder" value="%d"/>\n' % fil,
                '    </part>\n']
    cfg += ['  </object>\n</config>\n']

    content_types = ('<?xml version="1.0" encoding="UTF-8"?>\n'
                     '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
                     ' <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
                     ' <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>\n'
                     ' <Default Extension="config" ContentType="text/xml"/>\n'
                     '</Types>\n')
    rels = ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
            ' <Relationship Target="/3D/3dmodel.model" Id="rel0" '
            'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n'
            '</Relationships>\n')
    path = bpy.path.abspath(path)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("3D/3dmodel.model", "".join(out))
        z.writestr("Metadata/model_settings.config", "".join(cfg))
    return path


def export_3mf(path):
    parts = build_print_parts()
    write_3mf(path, parts)
    for _n, me, _c, _f in parts:
        bpy.data.meshes.remove(me)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main():
    reset_scene()
    fibres = build_layout()
    lines = make_centerlines(fibres)
    nm = len(fibres)
    samples, discs = build_axis_samples(lines, nm)

    # straight fibres
    fibre_me = fuse_and_smooth(curve_tube_mesh(lines[:nm]))
    sculpt_detail(fibre_me, samples, discs, nm, 'main')
    cut_flat_ends(fibre_me)

    # diagonal branches: separate pieces, shaped to sit on the fibres
    cutter = curve_tube_mesh(lines[:nm], r_add=BRANCH_CLEARANCE)
    branch_meshes = []
    for k, bl in enumerate(lines[nm:]):
        piece = fuse_and_smooth(curve_tube_mesh([bl]))
        piece = boolean_difference(piece, cutter)
        keep_main_islands(piece)
        if len(piece.vertices) == 0:
            continue
        sculpt_detail(piece, samples, discs, nm, 'branch')
        piece.name = "Branch_%02d" % (len(branch_meshes) + 1)
        branch_meshes.append(piece)
    bpy.data.meshes.remove(cutter)
    bands_me = make_disc_bands(samples, discs, nm)

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
    bands_me.transform(M)

    mat_f = material_fibre()
    fibre_me.materials.append(mat_f)

    coll = bpy.data.collections.new("Cardiac_Muscle")
    bpy.context.scene.collection.children.link(coll)
    ob_f = bpy.data.objects.new("Cardiac_Fibres", fibre_me)
    coll.objects.link(ob_f)

    # diagonal branches: separate objects
    coll_b = bpy.data.collections.new("Branches")
    coll.children.link(coll_b)
    for me in branch_meshes:
        me.transform(M)
        for p_ in me.polygons:
            p_.use_smooth = True
        me.materials.append(mat_f)
        coll_b.objects.link(bpy.data.objects.new(me.name, me))

    # nuclei: separate grains, each its own object, seated in its socket
    coll_n = bpy.data.collections.new("Nuclei")
    coll.children.link(coll_n)
    mat_n = material_nucleus()
    for me in make_grain_meshes(sculpt_detail.grains):
        me.transform(M)
        me.materials.append(mat_n)
        ob = bpy.data.objects.new(me.name, me)
        coll_n.objects.link(ob)

    # white disc bands: helper volume for the 3-colour print (hidden)
    mat_w = bpy.data.materials.new("Disc_White")
    mat_w.diffuse_color = (0.95, 0.95, 0.95, 1)
    bands_me.materials.append(mat_w)
    ob_w = bpy.data.objects.new("Disc_Bands_White", bands_me)
    coll.objects.link(ob_w)
    ob_w.hide_render = True
    ob_w.hide_set(True)

    setup_stage(TARGET_HEIGHT_M)

    dims = ob_f.dimensions
    print("Cardiac muscle built: %d fibre verts, %d branches, %d nuclei"
          % (len(fibre_me.vertices), len(branch_meshes), sculpt_detail.n_nuclei))
    print("Size (cm): X=%.1f  Y=%.1f  Z=%.1f" % (dims.x * 100, dims.y * 100, dims.z * 100))

    if EXPORT_3MF:
        export_3mf(EXPORT_3MF)

    if DO_RENDER:
        bpy.context.scene.render.filepath = RENDER_PATH
        bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
