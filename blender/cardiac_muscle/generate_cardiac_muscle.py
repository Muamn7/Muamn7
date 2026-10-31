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
  * Purple oval central nuclei (separate object)
  * Materials (Cycles / EEVEE), lights and a camera
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
TARGET_HEIGHT_M = 0.20      # final height of the whole bundle (20 cm)
SEED = 7
VOXEL = 0.05                # remesh voxel size in fibre-radius units (smaller = more detail)
STRIATION_PITCH = 0.30      # distance between striations (fibre-radius units)
STRIATION_DEPTH = 0.022
DISC_DEPTH = 0.10
DISC_WIDTH = 0.05
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
    L = 11.0
    layers = [(-2.75, [-3.1, 0.0, 3.1]),
              (0.0, [-4.65, -1.55, 1.55, 4.65]),
              (2.75, [-3.1, 0.0, 3.1])]
    for y0, zs in layers:
        for z0 in zs:
            xs = -L + random.uniform(-1.2, 1.6)
            xe = L + random.uniform(-1.6, 1.2)
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
        lo = max(a.xs, b.xs) + 2.0
        hi = min(a.xe, b.xe) - 2.0
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


def sculpt_detail(me, lines):
    samples, discs = build_axis_samples(lines)
    kd = kdtree.KDTree(len(samples))
    for i, s in enumerate(samples):
        kd.insert(s[2], i)
    kd.balance()

    n = len(me.vertices)
    co = np.empty(n * 3); me.vertices.foreach_get("co", co); co = co.reshape(n, 3)
    nrm = np.empty(n * 3); me.vertices.foreach_get("normal", nrm); nrm = nrm.reshape(n, 3)

    # nearest centre-line sample + organic noise (the only per-vertex python loop)
    idx = np.empty(n, dtype=np.int64)
    organic = np.empty(n)
    nn = noise.noise
    for i, v in enumerate(me.vertices):
        p = v.co
        idx[i] = kd.find(p)[1]
        organic[i] = nn(p * 1.3) * 0.035 + nn(p * 4.0) * 0.008

    S_fid = np.array([s[0] for s in samples])
    S_u = np.array([s[1] for s in samples])
    S_c = np.array([tuple(s[2]) for s in samples])
    S_t = np.array([tuple(s[3]) for s in samples])
    S_N = np.array([tuple(s[4]) for s in samples])
    S_B = np.array([tuple(s[5]) for s in samples])

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

    disp = w * (-STRIATION_DEPTH * g - DISC_DEPTH * dc) + organic
    co = co + nrm * disp[:, None]
    me.vertices.foreach_set("co", co.ravel())

    stria = g * w
    disc_a = dc * w
    me.attributes.new("stria", 'FLOAT', 'POINT').data.foreach_set("value", stria)
    me.attributes.new("disc", 'FLOAT', 'POINT').data.foreach_set("value", disc_a)

    # baked vertex colour too (for GLB / viewport / other software)
    base = np.array((0.52, 0.07, 0.05))
    dark = np.array((0.20, 0.015, 0.012))
    pale = np.array((0.24, 0.06, 0.06))
    c = base + (dark - base) * stria[:, None]
    c = c + (pale - c) * disc_a[:, None]
    rgba = np.concatenate([c, np.ones((n, 1))], axis=1)
    me.color_attributes.new("Col", 'FLOAT_COLOR', 'POINT').data.foreach_set("color", rgba.ravel())
    me.update()
    return samples, discs


# --------------------------------------------------------------------------
# Nuclei
# --------------------------------------------------------------------------
def make_nuclei(lines, n_fibres, discs):
    bm = bmesh.new()
    count = 0
    for fid, pts in enumerate(lines):
        if fid >= n_fibres:       # nuclei only on main fibres
            continue
        total = sum((pts[k + 1][0] - pts[k][0]).length for k in range(len(pts) - 1))
        dlist = [d[0] for d in discs[fid]]
        u = random.uniform(1.8, 3.2)
        while u < total - 1.8:
            if all(abs(u - du) > 1.1 for du in dlist):
                # locate sample at arc length u
                acc = 0.0
                k = 0
                while k < len(pts) - 1 and acc < u:
                    acc += (pts[k + 1][0] - pts[k][0]).length
                    k += 1
                co, r = pts[k]
                t = (pts[min(k + 1, len(pts) - 1)][0] - pts[max(k - 1, 0)][0]).normalized()
                Z = Vector((0, 0, 1))
                N = (Z - Z.dot(t) * t).normalized()
                B = t.cross(N)
                ang = random.uniform(0, 2 * math.pi)
                radial = (N * math.cos(ang) + B * math.sin(ang)).normalized()
                ax_long = r * random.uniform(0.70, 0.85)
                ax_w = r * random.uniform(0.36, 0.42)
                ax_h = r * random.uniform(0.26, 0.31)
                center = co + radial * (r * 1.0 - ax_h * 0.35)
                side = t.cross(radial).normalized()
                rot = Matrix((t, side, radial)).transposed().to_4x4()
                mat = (Matrix.Translation(center) @ rot @
                       Matrix.Diagonal((ax_long, ax_w, ax_h, 1.0)))
                ret = bmesh.ops.create_uvsphere(bm, u_segments=40, v_segments=20,
                                                radius=1.0, matrix=mat)
                for vv in ret['verts']:
                    vv.co += (vv.co - center).normalized() * noise.noise(vv.co * 6.0) * 0.02
                count += 1
            u += random.uniform(3.2, 4.6)
    for f in bm.faces:
        f.smooth = True
    me = bpy.data.meshes.new("Nuclei")
    bm.to_mesh(me)
    bm.free()
    return me, count


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
    L.new(m3.outputs['Result'], bsdf.inputs['Base Color'])

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
    _set(bsdf, 'Subsurface Weight', 0.25)
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
    cam.location = target + Vector((0.10, -0.80, 0.42))
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
    sc.render.resolution_x = 1600
    sc.render.resolution_y = 1000
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
    _, discs = sculpt_detail(fibre_me, lines)
    nuc_me, n_nuc = make_nuclei(lines, len(fibres), discs)

    # Scale to real size: height = TARGET_HEIGHT_M, sitting on the floor (z = 0)
    zs = [v.co.z for v in fibre_me.vertices]
    xs = [v.co.x for v in fibre_me.vertices]
    ys = [v.co.y for v in fibre_me.vertices]
    s = TARGET_HEIGHT_M / (max(zs) - min(zs))
    cx, cy = (max(xs) + min(xs)) * 0.5, (max(ys) + min(ys)) * 0.5
    M = Matrix.Diagonal((s, s, s, 1.0)) @ Matrix.Translation((-cx, -cy, -min(zs)))
    fibre_me.transform(M)
    nuc_me.transform(M)
    for p in fibre_me.polygons:
        p.use_smooth = True

    fibre_me.materials.append(material_fibre())
    nuc_me.materials.append(material_nucleus())

    coll = bpy.data.collections.new("Cardiac_Muscle")
    bpy.context.scene.collection.children.link(coll)
    ob_f = bpy.data.objects.new("Cardiac_Fibres", fibre_me)
    ob_n = bpy.data.objects.new("Nuclei", nuc_me)
    coll.objects.link(ob_f)
    coll.objects.link(ob_n)
    ob_n.parent = ob_f

    setup_stage(TARGET_HEIGHT_M)

    dims = ob_f.dimensions
    print("Cardiac muscle built: %d fibre verts, %d nuclei" % (len(fibre_me.vertices), n_nuc))
    print("Size (cm): X=%.1f  Y=%.1f  Z=%.1f" % (dims.x * 100, dims.y * 100, dims.z * 100))

    if DO_RENDER:
        bpy.context.scene.render.filepath = RENDER_PATH
        bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
