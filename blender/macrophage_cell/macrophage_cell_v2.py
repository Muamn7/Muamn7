"""
Macrophage Cell v2 - upright cut-away model (4 views)
=====================================================
Procedural Blender scene: a glossy, high-detail macrophage cell standing
on a pedestal, cut open vertically to show its organelles, with flame-like
pseudopodia capturing bacteria and glowing extracellular-matrix roots.

Works with Blender 4.2 LTS, 4.5 LTS and 5.x (render engine: Cycles).

HOW TO USE (inside Blender)
  1. File > New > General, then open the "Scripting" workspace.
  2. Text Editor > Open > macrophage_cell_v2.py  >  Run Script (Alt+P).
     WARNING: the script clears the current scene first.
  3. Four cameras are created: Cam_Front, Cam_Back, Cam_Left34,
     Cam_Right34. Set one active (Ctrl+Numpad0) and press F12.

COMMAND LINE
  blender -b -P macrophage_cell_v2.py -- --render out.png
          [--views front,back,left34,right34] [--samples 256]
          [--scale 100] [--save scene.blend]
  With several views, one PNG per view is written (out_front.png, ...)
  plus a 2x2 contact sheet (out_grid.png).

3D PRINTING
  blender -b -P macrophage_cell_v2.py -- --print macrophage.stl
          [--print-size 150] [--voxel 0.022]
  Fuses every part (cell, organelles, bacteria, ECM, pedestal) into ONE
  watertight manifold solid (voxel remesh), removes any loose island and
  exports a millimetre STL standing on the build plate. Inside Blender you
  can call make_print_model([...collections...], 'path.stl') as well.
"""

import bpy
import bmesh
import math
import os
import random
import sys
from mathutils import Vector, Matrix, Euler, noise

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SEED = 11
RENDER_SAMPLES = 256
RES_X, RES_Y = 1536, 1024
RES_PERCENT = 100

# The cell is modelled "lying down" (cut face = local XY plane, facing +Z)
# and then stood upright: local +Z -> world -Y (towards the front camera),
# local +Y -> world +Z (up).
CELL_A, CELL_B, CELL_C = 3.0, 2.45, 1.9   # half-size: width, height, depth
RIM_Z = 0.32                              # how far the cut rim sticks out
FLOOR_Z = 0.05                            # cut surface of the cytoplasm
CELL_Z = 2.8                              # world height of the cell centre
PED_TOP = 0.0                             # world height of pedestal top

OCCUPIED = []                             # (x, y, r) discs on the cut face

random.seed(SEED)


# Generic helpers
# ---------------------------------------------------------------------------
def clear_scene():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)
    for blocks in (bpy.data.meshes, bpy.data.curves, bpy.data.metaballs,
                   bpy.data.materials, bpy.data.lights, bpy.data.cameras,
                   bpy.data.node_groups):
        for b in list(blocks):
            if b.users == 0:
                blocks.remove(b)


def new_coll(name, parent=None):
    c = bpy.data.collections.new(name)
    (parent or bpy.context.scene.collection).children.link(c)
    return c


def rgba(c, a=1.0):
    return (c[0], c[1], c[2], a)


def _set(node, names, val):
    if isinstance(names, str):
        names = (names,)
    for n in names:
        s = node.inputs.get(n)
        if s is not None:
            try:
                s.default_value = val
                return True
            except Exception:
                pass
    return False


def _tex(nodes, links, texco, kind, scale, detail=4.0, rough=0.55,
         distortion=0.0, coord='Object'):
    if kind == 'voronoi':
        t = nodes.new('ShaderNodeTexVoronoi')
        out = t.outputs['Distance']
    elif kind == 'wave':
        t = nodes.new('ShaderNodeTexWave')
        _set(t, 'Distortion', distortion)
        _set(t, 'Detail', detail)
        out = t.outputs['Fac']
    else:
        t = nodes.new('ShaderNodeTexNoise')
        _set(t, 'Detail', detail)
        _set(t, 'Roughness', rough)
        _set(t, 'Distortion', distortion)
        out = t.outputs['Fac']
    _set(t, 'Scale', scale)
    links.new(texco.outputs[coord], t.inputs['Vector'])
    return out


def make_mat(name, color, rough=0.4, metal=0.0, sss=0.0,
             sss_rad=(1.0, 0.4, 0.25), sss_scale=0.1, trans=0.0, ior=1.45,
             coat=0.0, coat_rough=0.08, emit=None, emit_str=0.0, spec=0.5,
             sheen=0.0, bump=None, ramp=None):
    """Principled material. bump/ramp: dict(kind, scale, ...)."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nodes, links = nt.nodes, nt.links
    bsdf = nodes.get('Principled BSDF')
    _set(bsdf, 'Base Color', rgba(color))
    _set(bsdf, 'Roughness', rough)
    _set(bsdf, 'Metallic', metal)
    _set(bsdf, ('Subsurface Weight', 'Subsurface'), sss)
    _set(bsdf, 'Subsurface Radius', sss_rad)
    _set(bsdf, 'Subsurface Scale', sss_scale)
    _set(bsdf, ('Transmission Weight', 'Transmission'), trans)
    _set(bsdf, 'IOR', ior)
    _set(bsdf, ('Coat Weight', 'Clearcoat'), coat)
    _set(bsdf, ('Coat Roughness', 'Clearcoat Roughness'), coat_rough)
    _set(bsdf, ('Specular IOR Level', 'Specular'), spec)
    _set(bsdf, ('Sheen Weight', 'Sheen'), sheen)
    if emit is not None:
        _set(bsdf, ('Emission Color', 'Emission'), rgba(emit))
        _set(bsdf, 'Emission Strength', emit_str)
    m.diffuse_color = rgba(color)
    m.roughness = rough

    if bump or ramp:
        texco = nodes.new('ShaderNodeTexCoord')
        texco.location = (-900, 0)
    if ramp:
        out = _tex(nodes, links, texco, ramp.get('kind', 'noise'),
                   ramp.get('scale', 5.0), ramp.get('detail', 4.0),
                   ramp.get('rough', 0.55), ramp.get('distortion', 0.0))
        cr = nodes.new('ShaderNodeValToRGB')
        cr.location = (-350, 250)
        els = cr.color_ramp.elements
        stops = ramp['stops']
        els[0].position, els[0].color = stops[0][0], rgba(stops[0][1])
        els[1].position, els[1].color = stops[-1][0], rgba(stops[-1][1])
        for pos, col in stops[1:-1]:
            e = els.new(pos)
            e.color = rgba(col)
        links.new(out, cr.inputs['Fac'])
        links.new(cr.outputs['Color'], bsdf.inputs['Base Color'])
    if bump:
        out = _tex(nodes, links, texco, bump.get('kind', 'noise'),
                   bump.get('scale', 8.0), bump.get('detail', 6.0),
                   bump.get('rough', 0.6), bump.get('distortion', 0.0))
        bn = nodes.new('ShaderNodeBump')
        bn.location = (-350, -250)
        _set(bn, 'Strength', bump.get('strength', 0.3))
        _set(bn, 'Distance', bump.get('distance', 0.05))
        links.new(out, bn.inputs['Height'])
        links.new(bn.outputs['Normal'], bsdf.inputs['Normal'])
        cn = bsdf.inputs.get('Coat Normal')
        if cn is not None and coat > 0:
            links.new(bn.outputs['Normal'], cn)
    return m


def bm_object(name, bm, coll, mats, smooth=True):
    if smooth:
        for f in bm.faces:
            f.smooth = True
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    return ob


def add_sphere(bm, center, radius, subdiv=3, scale=(1, 1, 1), rot=(0, 0, 0)):
    M = (Matrix.Translation(Vector(center)) @
         Euler(rot).to_matrix().to_4x4() @
         Matrix.Diagonal((scale[0], scale[1], scale[2], 1.0)))
    return bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=radius,
                                      matrix=M)['verts']


def add_capsule(bm, center, length, radius, rot=(0, 0, 0), subdiv=3,
                bend=0.0, squash=1.0):
    """Rod (bacterium / mitochondrion) along local X, total length `length`."""
    vs = bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=radius,
                                    matrix=Matrix.Identity(4))['verts']
    half = max(0.0, length * 0.5 - radius)
    for v in vs:
        x = v.co.x
        if x > 1e-6:
            v.co.x += half
        elif x < -1e-6:
            v.co.x -= half
        v.co.z *= squash
        if bend:
            v.co.y += bend * (v.co.x / (half + radius)) ** 2
    M = Matrix.Translation(Vector(center)) @ Euler(rot).to_matrix().to_4x4()
    bmesh.ops.transform(bm, matrix=M, verts=vs)
    return vs


def catmull(points, step=0.05):
    """Dense smooth polyline through control points (Catmull-Rom)."""
    P = [Vector(p) for p in points]
    P = [P[0] + (P[0] - P[1])] + P + [P[-1] + (P[-1] - P[-2])]
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        n = max(2, int((p2 - p1).length / step))
        for k in range(n):
            t = k / n
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t +
                              (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 +
                              (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    out.append(P[-2].copy())
    return out


def curve_object(name, splines, coll, mat, bevel=0.03, extrude=0.0,
                 two_d=False, bevel_res=3, cyclic=False):
    """splines: list of (points, radii or None)."""
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '2D' if two_d else '3D'
    cu.bevel_depth = bevel
    cu.bevel_resolution = bevel_res
    cu.extrude = extrude
    cu.use_fill_caps = True
    if two_d:
        cu.fill_mode = 'BOTH'
    for pts, radii in splines:
        sp = cu.splines.new('POLY')
        sp.points.add(len(pts) - 1)
        for i, p in enumerate(pts):
            sp.points[i].co = (p[0], p[1], p[2] if len(p) > 2 else 0.0, 1.0)
            sp.points[i].radius = radii[i] if radii else 1.0
        sp.use_cyclic_u = cyclic
        sp.use_smooth = True
    ob = bpy.data.objects.new(name, cu)
    if mat:
        cu.materials.append(mat)
    coll.objects.link(ob)
    return ob


def add_mod(ob, kind, **kw):
    m = ob.modifiers.new(kind.title(), kind)
    for k, v in kw.items():
        try:
            setattr(m, k, v)
        except Exception:
            pass
    return m


def look_at(ob, target):
    d = Vector(target) - ob.location
    ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()


def floor_free(x, y, r, margin=0.02):
    for (ox, oy, orad) in OCCUPIED:
        if (x - ox) ** 2 + (y - oy) ** 2 < (r + orad + margin) ** 2:
            return False
    return True


def inside_floor(x, y, k=0.86):
    return (x / (CELL_A * k)) ** 2 + (y / (CELL_B * k)) ** 2 < 1.0

# ---------------------------------------------------------------------------
# Cell shape (local space)
# ---------------------------------------------------------------------------
def shape_scale(d):
    n = noise.noise(d * 1.4 + Vector((3.1, 1.7, 0.4)))
    lobe = 0.14 * max(0.0, -d.x) * max(0.0, d.y + 0.3)   # upper-left lobe
    return 1.0 + 0.07 * n + lobe


def shell_point(d, k=1.0):
    s = shape_scale(d) * k
    return Vector((d.x * CELL_A * s, d.y * CELL_B * s, d.z * CELL_C * s))


def rim_point(theta_deg, z=RIM_Z, k=1.0):
    """Point on the membrane at angle theta (deg, in the cut plane), depth z."""
    t = math.radians(theta_deg)
    dz = max(-0.99, min(0.99, z / CELL_C))
    for _ in range(5):
        r = math.sqrt(1 - dz * dz)
        d = Vector((math.cos(t) * r, math.sin(t) * r, dz))
        p = shell_point(d, k)
        if abs(p.z) > 1e-4:
            dz = max(-0.99, min(0.99, dz * z / p.z))
    return shell_point(d, k)


def lumpy(d):
    """Multi-scale lumps for the glossy, blobby membrane."""
    return (0.06 * noise.noise(d * 3.5 + Vector((1, 2, 3))) +
            0.035 * noise.noise(d * 8.0) +
            0.018 * noise.noise(d * 17.0) +
            0.05 * max(0.0, noise.noise(d * 6.0 + Vector((7, 1, 4)))) ** 2)


def build_cell(coll, M):
    # ---- outer membrane: closed blob with the front sliced off ----
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=6, radius=1.0)
    for v in bm.verts:
        d = v.co.normalized()
        v.co = shell_point(d) + d * lumpy(d)
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    bmesh.ops.bisect_plane(bm, geom=geom, plane_co=(0, 0, RIM_Z),
                           plane_no=(0, 0, 1), clear_outer=True)
    shell = bm_object('Cell_Membrane', bm, coll, [M['membrane'], M['rim']])
    add_mod(shell, 'SOLIDIFY', thickness=0.26, offset=-1.0, use_rim=True,
            use_even_offset=True, material_offset_rim=1)
    add_mod(shell, 'BEVEL', width=0.1, segments=5, limit_method='ANGLE',
            angle_limit=math.radians(35))
    add_mod(shell, 'SUBSURF', levels=0, render_levels=1)

    # ---- cytoplasm: filled interior with a flat cut face ----
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=5, radius=1.0)
    for v in bm.verts:
        v.co = shell_point(v.co.normalized(), 0.95)
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    bmesh.ops.bisect_plane(bm, geom=geom, plane_co=(0, 0, FLOOR_Z),
                           plane_no=(0, 0, 1), clear_outer=True)
    for f in bm.faces:
        f.smooth = True
    boundary = [e for e in bm.edges if e.is_boundary]
    res = bmesh.ops.holes_fill(bm, edges=boundary, sides=0)
    for f in res['faces']:
        bmesh.ops.triangulate(bm, faces=[f])
    for f in bm.faces:
        if f.normal.z > 0.999 and all(abs(v.co.z - FLOOR_Z) < 1e-4
                                      for v in f.verts):
            f.smooth = False
    bm_object('Cytoplasm', bm, coll, [M['cytoplasm']], smooth=False)

    # ---- beaded, lumpy lip around the cut ----
    bm = bmesh.new()
    th = 0.0
    while th < 360.0:
        r = random.uniform(0.07, 0.13)
        p = rim_point(th, RIM_Z - 0.03, random.uniform(0.955, 0.985))
        add_sphere(bm, p, r, 2, scale=(1, 1, random.uniform(0.7, 1.0)))
        th += random.uniform(2.0, 3.4)
    beads = bm_object('Membrane_Lip_Beads', bm, coll, [M['rim']])
    add_mod(beads, 'SUBSURF', levels=0, render_levels=1)

    # ---- blebs / ruffles all over the outer surface ----
    bm = bmesh.new()
    zmax = (RIM_Z - 0.15) / CELL_C
    n = 0
    while n < 260:
        d = Vector((random.gauss(0, 1), random.gauss(0, 1),
                    random.gauss(0, 1))).normalized()
        if d.z > zmax:
            continue
        r = random.uniform(0.07, 0.2)
        p = shell_point(d) + d * (lumpy(d) - r * 0.45)
        add_sphere(bm, p, r, 2, scale=(1, 1, random.uniform(0.6, 1.0)),
                   rot=(random.uniform(0, 3), random.uniform(0, 3), 0))
        n += 1
    bl = bm_object('Membrane_Blebs', bm, coll, [M['membrane']])
    add_mod(bl, 'SUBSURF', levels=0, render_levels=1)


FLAMES = []        # [(points, radii)] of every flame, used to seat bacteria


def build_pseudopodia(coll, M):
    """Layered, flame-like pseudopodia joined by membrane webbing, plus the
    phagocytic cup. Built from metaballs so everything fuses into one
    continuous, printable surface."""
    mb = bpy.data.metaballs.new('Pseudopodia')
    mb.resolution = 0.09
    mb.render_resolution = 0.035
    mb.threshold = 0.6
    K, FLAT = 1.6, 0.55

    def ball(p, r, flat=FLAT):
        e = mb.elements.new()
        e.type = 'ELLIPSOID'
        e.co = p
        e.radius = r * K
        e.size_x, e.size_y, e.size_z = 1.0, 1.0, flat
        e.stiffness = 2.0

    def flame(theta, zr, L, r0, back, curl, wave, power=1.3, phi=None):
        # root sits on the membrane at `theta`; the flame points along `phi`
        # (fanned towards the left, like the reference)
        if phi is None:
            phi = 0.45 * theta + 0.55 * 178.0
        t = math.radians(phi)
        u = Vector((math.cos(t), math.sin(t), 0.0))
        side = Vector((-u.y, u.x, 0.0))
        up = Vector((0, 1, 0))
        bk = Vector((0, 0, -1))
        p0 = rim_point(theta, zr, 0.88)
        ctrl = [p0,
                p0 + u * L * 0.35 + bk * L * back * 0.3 + side * wave * L * 0.08,
                p0 + u * L * 0.68 + up * L * curl * 0.35 + bk * L * back * 0.6
                - side * wave * L * 0.1,
                p0 + u * L * 0.88 + up * L * curl * 0.75 + bk * L * back * 0.85
                + side * wave * L * 0.06,
                p0 + u * L * 0.82 + up * L * curl * 1.1 + bk * L * back
                - u * L * 0.1]
        pts = catmull(ctrl, 0.045)
        n = len(pts)
        radii = []
        for i, p in enumerate(pts):
            s = i / (n - 1)
            r = r0 + (0.015 - r0) * (s ** power)
            radii.append(r)
            ball(p, r)
        FLAMES.append((theta, zr, pts, radii))
        return pts, radii

    # three staggered layers of flames along the left side
    layers = [
        (-0.4, [96, 112, 158, 174, 190, 206, 222, 238, 252], 1.0, 0.15),
        (-1.1, [104, 122, 140, 166, 184, 200, 216, 232, 246], 1.12, 0.45),
        (-1.7, [112, 138, 162, 188, 212, 236], 1.05, 0.8),
    ]
    rnd = random.Random(SEED + 3)
    for li, (zr, thetas, lscale, back) in enumerate(layers):
        prev = None
        for th in thetas:
            th_j = th + rnd.uniform(-4, 4)
            phi = 0.45 * th_j + 0.55 * 178.0
            top = max(0.0, math.sin(math.radians(phi)))
            L = lscale * rnd.uniform(2.4, 3.0)
            r0 = rnd.uniform(0.4, 0.5)
            curl = 0.25 + 0.2 * top
            pts, radii = flame(th_j, zr, L, r0, back, curl,
                               rnd.uniform(-1, 1))
            # membrane webbing between neighbouring flames
            if prev is not None and abs(th - prev[0]) < 30:
                a_pts, a_r = prev[1], prev[2]
                for s in (0.1, 0.18, 0.26):
                    ia, ib = int(s * len(a_pts)), int(s * len(pts))
                    pa, pb = a_pts[ia], pts[ib]
                    rr = 0.55 * min(a_r[ia], radii[ib])
                    for k in range(1, 6):
                        ball(pa.lerp(pb, k / 6), rr)
            prev = (th, pts, radii)

    # tall curling flame above the cup (the signature silhouette)
    flame(100, -0.25, 2.4, 0.55, 0.1, 0.5, 0.5, phi=122)

    # feet reaching down to the stand (blend into the ECM roots)
    for ctrl, r0, r1 in [
            ([(-0.9, -2.0, -1.0), (-1.6, -2.55, -1.5), (-2.4, -2.72, -2.1),
              (-3.0, -2.75, -2.5)], 0.34, 0.08),
            ([(1.0, -2.0, -0.9), (1.9, -2.55, -1.3), (2.7, -2.72, -1.8),
              (3.2, -2.75, -2.1)], 0.32, 0.08),
            ([(0.2, -2.1, -1.6), (0.3, -2.6, -2.4), (0.4, -2.74, -3.1)],
             0.32, 0.08)]:
        pts = catmull(ctrl, 0.05)
        for i, p in enumerate(pts):
            s = i / (len(pts) - 1)
            ball(p, r0 + (r1 - r0) * s, 0.85)

    # phagocytic cup: open ring of membrane wrapping a bacteria cluster
    cup_c = Vector((-2.15, 1.75, 0.15))
    nrm = Vector((-0.35, 0.3, 0.9)).normalized()
    R = nrm.to_track_quat('Z', 'Y').to_matrix()
    ring = []
    for i in range(0, 290, 5):
        a = math.radians(i + 215)
        ring.append(cup_c + R @ Vector((math.cos(a) * 0.62,
                                         math.sin(a) * 0.62, 0)))
    for i, p in enumerate(ring):
        t = i / (len(ring) - 1)
        ball(p, 0.16 + 0.1 * math.sin(t * math.pi), 1.0)
    for i in range(7):
        a = 2 * math.pi * i / 7
        ball(cup_c + R @ Vector((math.cos(a) * 0.3, math.sin(a) * 0.3, -0.42)),
             0.225, 1.0)

    ob = bpy.data.objects.new('Pseudopodia', mb)
    mb.materials.append(M['membrane'])
    coll.objects.link(ob)
    return cup_c, R


def build_receptors(coll, M):
    blue, green, tips_b, tips_g = [], [], [], []
    xs = [-1.25, -0.8, -0.35, 0.1, 0.55, 1.0, 1.45]
    for i, xf in enumerate(xs):
        d = Vector((xf / CELL_A, 0.96, -0.12)).normalized()
        base = shell_point(d) + d * (lumpy(d) - 0.06)
        h = random.uniform(0.38, 0.5)
        up = Vector((random.uniform(-0.06, 0.06), 1.0, random.uniform(-0.05, 0.05)))
        top = base + up.normalized() * h
        spread = 0.15
        armL = top + Vector((-spread, 0.18, 0))
        armR = top + Vector((spread, 0.18, 0))
        stalk = catmull([base, base.lerp(top, 0.5), top], 0.03)
        sps, tips = (blue, tips_b) if i % 2 == 0 else (green, tips_g)
        sps.append((stalk, None))
        for a in (armL, armR):
            arm = catmull([top, top.lerp(a, 0.5) + Vector((0, 0.04, 0)), a],
                          0.02)
            sps.append((arm, None))
            tips.append(a)
    for name, sps, tips, mat in (
            ('Receptors_Blue', blue, tips_b, M['receptor_b']),
            ('Receptors_Green', green, tips_g, M['receptor_g'])):
        curve_object(name, sps, coll, mat, bevel=0.05, bevel_res=4)
        bm = bmesh.new()
        for p in tips:
            add_sphere(bm, p, 0.07, 2)
        bm_object(name + '_Tips', bm, coll, [mat])


# ---------------------------------------------------------------------------
# Organelles (local space, on the cut face)
# ---------------------------------------------------------------------------
def build_nucleus(coll, M, name, c, rx, ry, rz, nucleolus_r, mat, pores=True):
    cx, cy = c
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=6, radius=1.0)
    s = min(rx, ry)
    for v in bm.verts:
        d = v.co.normalized()
        p = Vector((d.x * rx, d.y * ry, d.z * rz))
        p += d * s * (0.04 * noise.noise(d * 4.0 + Vector((5, 2, 1))) +
                      0.025 * noise.noise(d * 9.0) +
                      0.014 * noise.noise(d * 22.0))
        rho = math.hypot(p.x / rx, p.y / ry)
        if d.z > 0:
            pit = 0.38 * rz * max(0.0, 1 - (rho / 0.42) ** 2) ** 2
            lip = 0.12 * rz * math.exp(-((rho - 0.78) / 0.12) ** 2)
            p.z += (lip - pit) * d.z
        v.co = p + Vector((cx, cy, FLOOR_Z - 0.06))
    bm_object(name, bm, coll, [mat])
    top = FLOOR_Z - 0.06 + rz * 0.62
    bm = bmesh.new()
    add_sphere(bm, (cx, cy, top), nucleolus_r, 4)
    bm_object(name + '_Nucleolus', bm, coll, [M['nucleolus']])
    if pores:
        bm = bmesh.new()
        for _ in range(110):
            d = Vector((random.uniform(-1, 1), random.uniform(-1, 1),
                        random.uniform(0.1, 1))).normalized()
            p = Vector((d.x * rx, d.y * ry, d.z * rz))
            if math.hypot(p.x / rx, p.y / ry) < 0.5:
                continue
            nrm = Vector((d.x / rx, d.y / ry, d.z / rz)).normalized()
            q = p + Vector((cx, cy, FLOOR_Z - 0.06)) + nrm * 0.03
            add_sphere(bm, q, 0.028, 1, scale=(1, 1, 0.5),
                       rot=nrm.to_track_quat('Z', 'Y').to_euler())
        bm_object(name + '_Pores', bm, coll, [M['nucleolus']])
    OCCUPIED.append((cx, cy, max(rx, ry)))


def build_mitochondrion(coll, M, name, c, length, radius, angle):
    bm = bmesh.new()
    add_capsule(bm, (0, 0, 0), length, radius, subdiv=4, squash=0.75)
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    bmesh.ops.bisect_plane(bm, geom=geom, plane_co=(0, 0, 0.0),
                           plane_no=(0, 0, 1), clear_outer=True)
    ob = bm_object(name, bm, coll, [M['mito'], M['mito_rim']])
    add_mod(ob, 'SOLIDIFY', thickness=0.065, offset=-1, use_rim=True,
            material_offset_rim=1)
    add_mod(ob, 'BEVEL', width=0.015, segments=2, limit_method='ANGLE')
    add_mod(ob, 'SUBSURF', levels=1, render_levels=2)
    ob.location = (c[0], c[1], FLOOR_Z + 0.07)
    ob.rotation_euler = (0, 0, math.radians(angle))
    half = length / 2 - radius * 0.55
    n = max(4, int(length / 0.085))
    pts = []
    steps = n * 8
    for i in range(steps + 1):
        x = -half + 2 * half * i / steps
        prof = math.sqrt(max(0.0, 1 - (max(0, abs(x) - (length / 2 - radius))
                                       / radius) ** 2))
        y = radius * 0.62 * prof * math.sin(i / 8 * math.pi)
        pts.append((x, y, 0))
    cr = curve_object(name + '_Cristae', [(pts, None)], coll, M['cristae'],
                      bevel=0.026, extrude=radius * 0.32, two_d=True)
    cr.parent = ob
    cr.location = (0, 0, -radius * 0.32)
    bm = bmesh.new()
    add_capsule(bm, (0, 0, -radius * 0.45), length * 0.93, radius * 0.9,
                subdiv=3, squash=0.25)
    mx = bm_object(name + '_Matrix', bm, coll, [M['mito_matrix']])
    mx.parent = ob
    OCCUPIED.append((c[0], c[1], length / 2))
    return ob


def build_golgi(coll, M, name, center, facing_deg, n, base_r, span_deg,
                mat, ves_mat, gap=0.11, wobble=0.03):
    f = math.radians(facing_deg)
    fd = Vector((math.cos(f), math.sin(f), 0))
    arc_c = Vector((center[0], center[1], 0)) - fd * (base_r + n * gap * 0.5)
    splines = []
    for i in range(n):
        R = base_r + i * gap
        span = math.radians(span_deg * (1.0 - 0.05 * abs(i - n / 2)))
        pts, radii = [], []
        m = 48
        ph = random.uniform(0, 6)
        for k in range(m + 1):
            t = k / m
            a = f - span / 2 + span * t
            wob = wobble * math.sin(t * 11 + ph) * math.sin(t * math.pi)
            p = arc_c + Vector((math.cos(a), math.sin(a), 0)) * (R + wob)
            pts.append((p.x, p.y, 0))
            end = min(t, 1 - t) / 0.12
            radii.append(0.35 + 0.65 * min(1.0, end) +
                         0.15 * math.sin(t * math.pi * 4 + i))
        splines.append((pts, radii))
    ob = curve_object(name, splines, coll, mat, bevel=0.05, extrude=0.11,
                      two_d=True, bevel_res=4)
    ob.location.z = FLOOR_Z + 0.05
    bm = bmesh.new()
    for i in range(n):
        R = base_r + i * gap
        span = math.radians(span_deg * (1.0 - 0.05 * abs(i - n / 2)))
        for side in (-1, 1):
            for j in range(random.randint(1, 3)):
                a = f + side * (span / 2 + random.uniform(0.05, 0.22))
                p = arc_c + Vector((math.cos(a), math.sin(a), 0)) * \
                    (R + random.uniform(-0.05, 0.05))
                rv = random.uniform(0.045, 0.07)
                add_sphere(bm, (p.x, p.y, FLOOR_Z + rv * 0.4), rv, 2)
    bm_object(name + '_Vesicles', bm, coll, [ves_mat])
    mid = arc_c + fd * (base_r + n * gap * 0.5)
    OCCUPIED.append((mid.x, mid.y, n * gap * 0.6 + 0.15))


def build_rer(coll, M, origin, width, rows, gap=0.15):
    ox, oy = origin
    pts = []
    for r in range(rows):
        y0 = oy + r * gap
        xs = [ox + width * k / 60 for k in range(61)]
        if r % 2:
            xs.reverse()
        for x in xs:
            y = y0 + 0.035 * math.sin((x - ox) * 7.0 + r * 1.3)
            pts.append(Vector((x, y, 0)))
        if r < rows - 1:
            end = pts[-1]
            side = 1 if r % 2 == 0 else -1
            for k in range(1, 10):
                a = math.pi * k / 10
                pts.append(Vector((end.x + side * math.sin(a) * gap * 0.5,
                                   end.y + (1 - math.cos(a)) * gap * 0.5, 0)))
    ob = curve_object('Rough_ER', [([tuple(p) for p in pts], None)], coll,
                      M['rer'], bevel=0.034, extrude=0.085, two_d=True,
                      bevel_res=4)
    ob.location.z = FLOOR_Z + 0.05
    bm = bmesh.new()
    for i in range(1, len(pts) - 1, 2):
        p = pts[i]
        t = (pts[i + 1] - pts[i - 1]).normalized()
        nrm = Vector((-t.y, t.x, 0))
        for side in (-1, 1):
            if random.random() < 0.85:
                q = p + nrm * side * random.uniform(0.042, 0.048)
                add_sphere(bm, (q.x, q.y, FLOOR_Z + 0.05 +
                                random.uniform(-0.02, 0.1)),
                           random.uniform(0.024, 0.03), 1)
        if random.random() < 0.5:
            add_sphere(bm, (p.x, p.y, FLOOR_Z + 0.16), 0.028, 1)
    bm_object('Ribosomes_on_RER', bm, coll, [M['ribosome']])
    OCCUPIED.append((ox + width / 2, oy + rows * gap / 2, width * 0.55))


def build_phagolysosome(coll, M, c, R=0.5):
    cx, cy = c
    cz = FLOOR_Z + 0.03
    bm = bmesh.new()
    add_sphere(bm, (0, 0, 0), R, 5)
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    bmesh.ops.bisect_plane(bm, geom=geom, plane_co=(0, 0, 0.14),
                           plane_no=(0, 0, 1), clear_outer=True)
    mem = bm_object('Phagolysosome', bm, coll, [M['phago'], M['phago_rim']])
    add_mod(mem, 'SOLIDIFY', thickness=0.075, offset=-1, use_rim=True,
            material_offset_rim=1)
    add_mod(mem, 'SUBSURF', levels=1, render_levels=1)
    mem.location = (cx, cy, cz)
    bm = bmesh.new()
    add_sphere(bm, (0, 0, 0), R * 0.97, 4)
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    bmesh.ops.bisect_plane(bm, geom=geom, plane_co=(0, 0, -0.02),
                           plane_no=(0, 0, 1), clear_outer=True)
    bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary])
    lumen = bm_object('Phagolysosome_Lumen', bm, coll, [M['phago_lumen']])
    lumen.location = (cx, cy, cz)
    keys = ['debris_g', 'debris_y', 'debris_p', 'debris_w']
    bms = {k: bmesh.new() for k in keys}
    for i in range(90):
        a = random.uniform(0, 2 * math.pi)
        r = R * 0.8 * math.sqrt(random.random())
        p = (cx + math.cos(a) * r, cy + math.sin(a) * r,
             cz + random.uniform(-0.02, 0.06))
        b = bms[random.choice(keys)]
        if random.random() < 0.4:
            add_capsule(b, p, random.uniform(0.09, 0.16),
                        random.uniform(0.032, 0.04),
                        rot=(random.uniform(-0.4, 0.4), random.uniform(-0.4, 0.4),
                             random.uniform(0, 3)), subdiv=2)
        else:
            add_sphere(b, p, random.uniform(0.035, 0.055), 1,
                       scale=(random.uniform(0.7, 1.3),
                              random.uniform(0.7, 1.3),
                              random.uniform(0.7, 1.3)))
    for k in keys:
        bm_object('Phagolysosome_' + k, bms[k], coll, [M[k]])
    # radiating tubular fringe, two staggered rings
    bm = bmesh.new()
    for ring, cnt, L0 in ((0, 96, 0.2), (1, 70, 0.14)):
        for i in range(cnt):
            a = 2 * math.pi * (i + 0.5 * ring) / cnt + random.uniform(-0.02, 0.02)
            L = random.uniform(L0 * 0.8, L0 * 1.2)
            rr = R + 0.03 + L / 2 + ring * 0.1
            p = (cx + math.cos(a) * rr, cy + math.sin(a) * rr,
                 cz + random.uniform(-0.03, 0.06) - ring * 0.03)
            add_capsule(bm, p, L, random.uniform(0.018, 0.026),
                        rot=(0, random.uniform(-0.35, 0.35), a), subdiv=2)
    bm_object('Phagolysosome_Fringe', bm, coll, [M['fringe']])
    OCCUPIED.append((cx, cy, R + 0.38))


def build_lysosomes_and_dots(coll, M):
    bm = bmesh.new()
    fixed = [(-1.2, -1.75, 0.13), (0.95, -1.9, 0.12), (-0.55, 1.2, 0.12),
             (-2.45, -0.45, 0.1), (2.55, -1.05, 0.1), (0.7, 2.05, 0.1)]
    for (x, y, r) in fixed:
        if floor_free(x, y, r, 0.0) and inside_floor(x, y, 0.88):
            add_sphere(bm, (x, y, FLOOR_Z + r * 0.35), r, 3)
            OCCUPIED.append((x, y, r))
    placed = tries = 0
    while placed < 26 and tries < 5000:
        tries += 1
        x = random.uniform(-2.7, 2.7)
        y = random.uniform(-2.2, 2.2)
        r = random.uniform(0.045, 0.1)
        if inside_floor(x, y, 0.86) and floor_free(x, y, r, 0.04):
            add_sphere(bm, (x, y, FLOOR_Z + r * 0.3), r, 3)
            OCCUPIED.append((x, y, r))
            placed += 1
    bm_object('Lysosomes', bm, coll, [M['lysosome']])
    # free ribosomes (blue) and red granules speckling the cytoplasm
    for name, mat, count, rr in (('Free_Ribosomes', M['ribosome'], 480,
                                  (0.024, 0.036)),
                                 ('Granules', M['granule'], 200,
                                  (0.02, 0.026))):
        bm = bmesh.new()
        n = tries = 0
        while n < count and tries < 30000:
            tries += 1
            x = random.uniform(-2.8, 2.8)
            y = random.uniform(-2.3, 2.3)
            r = random.uniform(*rr)
            if inside_floor(x, y, 0.9) and floor_free(x, y, r, 0.0):
                add_sphere(bm, (x, y, FLOOR_Z + 0.004), r, 1)
                n += 1
        bm_object(name, bm, coll, [mat])
    # exocytosis vesicle fusing with the membrane (right side)
    bm = bmesh.new()
    p = rim_point(-20, FLOOR_Z, 0.915)
    add_sphere(bm, (p.x, p.y, FLOOR_Z + 0.08), 0.13, 4)
    bm_object('Exocytosis_Vesicle', bm, coll, [M['lysosome']])


def build_cytoskeleton(coll, M):
    sps = []
    for i in range(75):
        th = random.uniform(0, 2 * math.pi)
        k0 = random.uniform(0.75, 0.9)
        x0 = math.cos(th) * CELL_A * k0
        y0 = math.sin(th) * CELL_B * k0
        if not inside_floor(x0, y0, 0.92):
            continue
        ctrl = [(x0, y0, FLOOR_Z + 0.006)]
        ang = th + math.pi + random.uniform(-1.2, 1.2)
        L = random.uniform(0.5, 1.4)
        p = Vector((x0, y0, FLOOR_Z + 0.006))
        for s in range(3):
            ang += random.uniform(-0.6, 0.6)
            p = p + Vector((math.cos(ang), math.sin(ang), 0)) * L / 3
            if not inside_floor(p.x, p.y, 0.9):
                break
            ctrl.append(tuple(p))
        if len(ctrl) >= 2:
            sps.append((catmull(ctrl, 0.04), None))
    curve_object('Cytoskeleton', sps, coll, M['cytoskeleton'], bevel=0.02,
                 bevel_res=1)


# ---------------------------------------------------------------------------
# Bacteria (with pili)
# ---------------------------------------------------------------------------
def add_bacterium(bm, center, length, radius, rot, bend=0.0, pili=10,
                  pili_bm=None):
    add_capsule(bm, center, length, radius, rot=rot, subdiv=3, bend=bend)
    if pili_bm is None:
        return
    M = Matrix.Translation(Vector(center)) @ Euler(rot).to_matrix().to_4x4()
    half = max(0.0, length * 0.5 - radius)
    for _ in range(pili):
        x = random.uniform(-half - radius * 0.6, half + radius * 0.6)
        phi = random.uniform(0, 2 * math.pi)
        nrm = Vector((0, math.cos(phi), math.sin(phi)))
        if abs(x) > half:            # on the rounded caps
            s = (abs(x) - half) / radius
            nrm = Vector((math.copysign(s, x), nrm.y * (1 - s * s) ** 0.5,
                          nrm.z * (1 - s * s) ** 0.5)).normalized()
        base = Vector((x, 0, 0)) + nrm * radius * 0.95
        if bend:
            base.y += bend * (x / (half + radius)) ** 2
        L = random.uniform(0.06, 0.1)
        Mc = (M @ Matrix.Translation(base + nrm * L / 2) @
              nrm.to_track_quat('Z', 'Y').to_matrix().to_4x4())
        bmesh.ops.create_cone(pili_bm, cap_ends=True, segments=5,
                              radius1=0.024, radius2=0.012, depth=L,
                              matrix=Mc)


def build_bacteria(coll, M, cup_c, cup_R):
    """Every bacterium is seated on (half-buried in) membrane so the model
    has no floating parts."""
    bms = {'bact_a': bmesh.new(), 'bact_b': bmesh.new()}
    pili = bmesh.new()
    rnd = random.Random(SEED + 5)

    def bact(p, rot, L=None):
        b = bms['bact_a' if rnd.random() < 0.55 else 'bact_b']
        add_bacterium(b, p, L or rnd.uniform(0.45, 0.62),
                      rnd.uniform(0.085, 0.1), rot,
                      bend=rnd.uniform(-0.05, 0.05), pili_bm=pili)

    # cluster pressed into the phagocytic cup
    for i in range(9):
        a = rnd.uniform(0, 2 * math.pi)
        r = rnd.uniform(0.0, 0.3)
        p = cup_c + cup_R @ Vector((math.cos(a) * r, math.sin(a) * r,
                                    rnd.uniform(-0.24, -0.14)))
        bact(p, (rnd.uniform(0, 3.1), rnd.uniform(0, 3.1),
                 rnd.uniform(0, 3.1)))
    # bacteria caught on the flames (front faces and upper edges)
    cands = [f for f in FLAMES if f[1] > -1.2 and 95 < f[0] < 215]
    rnd.shuffle(cands)
    for i, (th, zr, pts, radii) in enumerate(cands[:11]):
        k = int(len(pts) * rnd.uniform(0.45, 0.72))
        p, r = pts[k], radii[k]
        if i % 2 == 0:      # lying on the front face of the flame
            off = Vector((0, 0, r * 1.6 * 0.55 * 0.5 + 0.015))
        else:               # perched on the upper edge
            off = Vector((0, r * 1.6 * 0.5 + 0.01, 0))
        tang = (pts[min(k + 1, len(pts) - 1)] - pts[k - 1]).normalized()
        ang = math.atan2(tang.y, tang.x) + rnd.uniform(-0.6, 0.6)
        bact(p + off, (rnd.uniform(-0.3, 0.3), rnd.uniform(-0.3, 0.3), ang),
             rnd.uniform(0.5, 0.66))
    for k, b in bms.items():
        ob = bm_object('Bacteria_' + k[-1].upper(), b, coll, [M[k]])
        add_mod(ob, 'SUBSURF', levels=1, render_levels=1)
    bm_object('Bacteria_Pili', pili, coll, [M['bact_a']], smooth=False)


# ---------------------------------------------------------------------------
# Stand the cell up
# ---------------------------------------------------------------------------
def stand_up(colls):
    root = bpy.data.objects.new('Cell_Root', None)
    colls[0].objects.link(root)
    root.empty_display_type = 'ARROWS'
    for c in colls:
        for ob in c.objects:
            if ob is not root and ob.parent is None:
                ob.parent = root
    root.location = (0, 0, CELL_Z)
    root.rotation_euler = (math.radians(90), 0, 0)
    return root


def to_world(p):
    """local cell space -> world (matches stand_up)."""
    return Vector((p[0], -p[2], p[1] + CELL_Z))


# ---------------------------------------------------------------------------
# Extracellular matrix roots (world space)
# ---------------------------------------------------------------------------
def build_ecm(coll, M):
    thick, thin = [], []

    def fibre(start, phi, L, lift, out_list, r_scale=1.0, branches=1):
        ctrl = [start]
        p = start.copy()
        ang = phi
        nseg = 5
        for s in range(nseg):
            ang += random.uniform(-0.35, 0.35)
            t = (s + 1) / nseg
            p = p + Vector((math.cos(ang), math.sin(ang), 0)) * L / nseg
            z = PED_TOP + 0.03 + (start.z - PED_TOP) * (1 - t) ** 2.2 + \
                lift * math.sin(t * math.pi) * 0.25
            ctrl.append(Vector((p.x, p.y, z)))
        if math.hypot(p.x, p.y) > 4.15:
            # pull the tip back onto the pedestal
            s = 4.15 / math.hypot(p.x, p.y)
            ctrl[-1] = Vector((p.x * s, p.y * s, ctrl[-1].z))
        pts = catmull(ctrl, 0.05)
        n = len(pts)
        rad = [max(0.42, r_scale * (1.0 - 0.6 * (k / n) ** 0.8))
               for k in range(n)]
        out_list.append((pts, rad))
        for b in range(branches):
            k = random.randint(n // 4, n // 2)
            q = pts[k]
            fibre(Vector((q.x, q.y, q.z)), ang + random.choice((-1, 1)) *
                  random.uniform(0.6, 1.1), L * 0.45, 0.2, thin,
                  r_scale * 0.55, 0)

    # roots spreading from under the cell
    for i in range(24):
        phi = random.uniform(0, 2 * math.pi)
        r0 = random.uniform(0.6, 1.6)
        start = Vector((math.cos(phi) * r0 * 1.3, math.sin(phi) * r0 * 0.6,
                        random.uniform(0.35, 0.9)))
        fibre(start, phi, random.uniform(2.2, 3.4), random.uniform(0, 1),
              thick, random.uniform(0.9, 1.4), random.randint(1, 2))
    # fibres climbing up the flanks of the cell
    for i in range(14):
        side = random.choice((-1, 1))
        th = math.radians(random.uniform(200, 340))
        lp = rim_point(math.degrees(th), random.uniform(-1.4, -0.3), 0.98)
        start = to_world(lp)
        phi = math.atan2(start.y, start.x) + random.uniform(-0.4, 0.4)
        fibre(start, phi, random.uniform(2.0, 3.0), 0.5, thick,
              random.uniform(0.7, 1.0), 1)
    curve_object('ECM_Roots', thick, coll, M['ecm'], bevel=0.12, bevel_res=4)
    curve_object('ECM_Branches', thin, coll, M['ecm2'], bevel=0.12,
                 bevel_res=3)


# ---------------------------------------------------------------------------
# Pedestal, environment, cameras, lights
# ---------------------------------------------------------------------------
def build_pedestal(coll, M):
    tiers = [(4.7, PED_TOP - 0.55, PED_TOP - 0.28),
             (4.35, PED_TOP - 0.28, PED_TOP)]
    for i, (r, z0, z1) in enumerate(tiers):
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=180, radius1=r,
                              radius2=r, depth=z1 - z0,
                              matrix=Matrix.Translation((0, 0, (z0 + z1) / 2)))
        ob = bm_object('Pedestal_Tier_%d' % (i + 1), bm, coll,
                       [M['pedestal']], smooth=False)
        add_mod(ob, 'BEVEL', width=0.09, segments=6, limit_method='ANGLE',
                angle_limit=math.radians(30))
        for f in ob.data.polygons:
            f.use_smooth = True
    # dark stand block under the cell
    for i, (sx, sy, h, z) in enumerate(((2.2, 1.5, 0.22, 0.11),
                                         (1.5, 1.0, 0.5, 0.45))):
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0, matrix=(
            Matrix.Translation((0, 0.35, PED_TOP + z)) @
            Matrix.Diagonal((sx, sy, h, 1))))
        ob = bm_object('Stand_%d' % (i + 1), bm, coll, [M['stand']],
                       smooth=False)
        add_mod(ob, 'BEVEL', width=0.05, segments=3)


def build_environment(coll, M):
    bm = bmesh.new()
    bmesh.ops.create_circle(bm, cap_ends=True, segments=64, radius=60)
    fl = bm_object('Floor', bm, coll, [M['floor']], smooth=False)
    fl.location = (0, 0, PED_TOP - 0.55)
    w = bpy.context.scene.world or bpy.data.worlds.new('World')
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes.get('Background')
    tc = nt.nodes.new('ShaderNodeTexCoord')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    cr = nt.nodes.new('ShaderNodeValToRGB')
    els = cr.color_ramp.elements
    els[0].position, els[0].color = 0.0, (0.004, 0.008, 0.032, 1)
    els[1].position, els[1].color = 0.45, (0.002, 0.004, 0.018, 1)
    nt.links.new(tc.outputs['Generated'], sep.inputs['Vector'])
    nt.links.new(sep.outputs['Z'], cr.inputs['Fac'])
    nt.links.new(cr.outputs['Color'], bg.inputs['Color'])
    bg.inputs['Strength'].default_value = 1.0


TARGET = Vector((-0.9, 0.3, 2.75))
VIEWS = {               # name: (azimuth deg from front, distance, height)
    'front': (0, 19.0, 1.4),
    'back': (180, 19.0, 1.4),
    'left34': (58, 18.5, 2.4),
    'right34': (-58, 18.5, 2.4),
}


def build_cameras(coll):
    cams = {}
    for name, (az, dist, h) in VIEWS.items():
        cd = bpy.data.cameras.new('Cam_' + name)
        cd.lens = 50
        cd.sensor_width = 36
        cd.sensor_fit = 'HORIZONTAL'
        cd.clip_end = 300
        cam = bpy.data.objects.new('Cam_' + name, cd)
        coll.objects.link(cam)
        a = math.radians(az)
        cam.location = TARGET + Vector((-math.sin(a) * dist,
                                        -math.cos(a) * dist, h))
        look_at(cam, TARGET)
        cams[name] = cam
    bpy.context.scene.camera = cams['front']
    return cams


def build_lights(coll):
    def area(name, loc, target, power, size, color):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = power
        ld.size = size
        ld.color = color
        ob = bpy.data.objects.new(name, ld)
        coll.objects.link(ob)
        ob.location = loc
        look_at(ob, target)
        return ob
    c = (-0.6, 0, 2.2)
    area('Key', (-6, -8, 9), c, 1500, 3.5, (1.0, 0.92, 1.0))
    area('Fill', (8, -7, 4), c, 500, 5, (0.8, 0.8, 1.0))
    area('Rim_Left', (-8, 7, 6), c, 2000, 3, (0.9, 0.4, 1.0))
    area('Rim_Right', (8, 7, 6), c, 1600, 3, (0.45, 0.5, 1.0))
    area('Back_Fill', (0, 10, 3), c, 500, 6, (0.8, 0.6, 1.0))
    area('Top', (0, 0, 10), c, 500, 3, (1.0, 0.9, 1.0))
    area('Front_Low', (0, -11, 3.0), c, 500, 5, (0.9, 0.85, 1.0))


# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------
def build_materials():
    M = {}
    M['membrane'] = make_mat(
        'Membrane', (0.7, 0.1, 0.9), rough=0.18, sss=0.22,
        sss_rad=(1.0, 0.15, 0.8), sss_scale=0.05, coat=1.0, coat_rough=0.03,
        ramp=dict(kind='noise', scale=2.6, detail=3,
                  stops=[(0.35, (0.36, 0.04, 0.85)), (0.52, (0.62, 0.08, 0.9)),
                         (0.7, (0.9, 0.16, 0.78))]),
        bump=dict(kind='noise', scale=11.0, detail=8, strength=0.3,
                  distance=0.05))
    M['rim'] = make_mat(
        'Membrane_Lip', (0.92, 0.2, 0.75), rough=0.16, sss=0.25,
        sss_rad=(1.0, 0.2, 0.7), sss_scale=0.05, coat=1.0, coat_rough=0.03,
        bump=dict(kind='noise', scale=20.0, strength=0.2, distance=0.02))
    M['cytoplasm'] = make_mat(
        'Cytoplasm', (0.62, 0.22, 0.6), rough=0.35, sss=0.15,
        sss_rad=(1.0, 0.3, 0.8), sss_scale=0.06, coat=0.5,
        ramp=dict(kind='noise', scale=2.2, detail=5,
                  stops=[(0.3, (0.3, 0.06, 0.5)), (0.5, (0.55, 0.12, 0.52)),
                         (0.72, (0.8, 0.2, 0.42))]),
        bump=dict(kind='voronoi', scale=55.0, strength=0.2, distance=0.01))
    M['nucleus'] = make_mat(
        'Nucleus', (0.5, 0.18, 0.88), rough=0.3, sss=0.15,
        sss_rad=(0.7, 0.3, 1.0), sss_scale=0.06, coat=0.6,
        ramp=dict(kind='noise', scale=6.0, detail=6,
                  stops=[(0.3, (0.25, 0.04, 0.7)), (0.55, (0.45, 0.12, 0.88)),
                         (0.75, (0.62, 0.25, 0.92))]),
        bump=dict(kind='voronoi', scale=26.0, strength=0.6, distance=0.02))
    M['nucleus2'] = make_mat(
        'Nucleus_Small', (0.45, 0.15, 0.85), rough=0.2, sss=0.3, coat=0.8,
        bump=dict(kind='noise', scale=14.0, strength=0.3, distance=0.02))
    M['nucleolus'] = make_mat('Nucleolus', (0.14, 0.06, 0.5), rough=0.12,
                              coat=1.0, sss=0.2)
    M['mito'] = make_mat('Mitochondrion', (1.0, 0.38, 0.04), rough=0.2,
                         sss=0.45, sss_rad=(1.0, 0.4, 0.1), coat=0.8,
                         bump=dict(kind='noise', scale=18, strength=0.15))
    M['mito_rim'] = make_mat('Mitochondrion_Cut', (1.0, 0.58, 0.18),
                             rough=0.3, sss=0.3)
    M['mito_matrix'] = make_mat('Mito_Matrix', (0.9, 0.25, 0.03), rough=0.4,
                                sss=0.3)
    M['cristae'] = make_mat('Cristae', (1.0, 0.1, 0.02), rough=0.25,
                            sss=0.3, coat=0.6)
    M['rer'] = make_mat('Rough_ER', (0.1, 0.25, 0.95), rough=0.2, sss=0.35,
                        sss_rad=(0.3, 0.5, 1.0), coat=0.8,
                        bump=dict(kind='noise', scale=25, strength=0.15))
    M['ribosome'] = make_mat('Ribosome', (0.04, 0.07, 0.55), rough=0.15,
                             coat=0.8)
    M['granule'] = make_mat('Granule', (0.8, 0.08, 0.2), rough=0.3, coat=0.5)
    M['golgi_o'] = make_mat('Golgi_Orange', (1.0, 0.55, 0.12), rough=0.22,
                            sss=0.45, sss_rad=(1.0, 0.5, 0.15), coat=0.7,
                            bump=dict(kind='noise', scale=30, strength=0.15))
    M['golgi_b'] = make_mat(
        'Golgi_Brown', (0.62, 0.3, 0.18), rough=0.3, sss=0.4,
        sss_rad=(1.0, 0.45, 0.3), coat=0.6,
        ramp=dict(kind='voronoi', scale=60.0,
                  stops=[(0.0, (0.36, 0.14, 0.08)), (0.25, (0.45, 0.2, 0.12)),
                         (0.32, (0.72, 0.4, 0.24)), (1.0, (0.8, 0.46, 0.28))]),
        bump=dict(kind='voronoi', scale=60.0, strength=0.3, distance=0.01))
    M['golgi_ves'] = make_mat('Golgi_Vesicle', (0.95, 0.5, 0.12), rough=0.2,
                              sss=0.4, coat=0.7)
    M['lysosome'] = make_mat('Lysosome', (0.05, 0.14, 0.9), rough=0.08,
                             coat=1.0, sss=0.25, sss_rad=(0.2, 0.4, 1.0),
                             spec=0.7)
    M['phago'] = make_mat('Phagolysosome_Membrane', (0.55, 0.2, 0.9),
                          rough=0.05, trans=0.55, coat=0.8, sss=0.2)
    M['phago_lumen'] = make_mat('Phagolysosome_Lumen', (0.4, 0.15, 0.7),
                                rough=0.2, sss=0.3, coat=0.5)
    M['phago_rim'] = make_mat('Phagolysosome_Cut', (0.85, 0.5, 0.95),
                              rough=0.2, sss=0.4)
    M['fringe'] = make_mat('Phagolysosome_Fringe', (0.6, 0.28, 0.18),
                           rough=0.25, sss=0.35, coat=0.5)
    M['debris_g'] = make_mat('Debris_Green', (0.42, 0.85, 0.2), rough=0.3,
                             sss=0.3)
    M['debris_y'] = make_mat('Debris_Yellow', (0.98, 0.85, 0.3), rough=0.3,
                             sss=0.3)
    M['debris_p'] = make_mat('Debris_Pink', (0.98, 0.45, 0.7), rough=0.3,
                             sss=0.3)
    M['debris_w'] = make_mat('Debris_White', (0.92, 0.92, 0.95), rough=0.3,
                             sss=0.3)
    M['bact_a'] = make_mat('Bacteria_Green', (0.12, 0.55, 0.02), rough=0.25,
                           sss=0.3, sss_rad=(0.2, 1.0, 0.1), coat=0.8,
                           bump=dict(kind='noise', scale=40, strength=0.25))
    M['bact_b'] = make_mat('Bacteria_Lime', (0.3, 0.7, 0.03), rough=0.25,
                           sss=0.3, sss_rad=(0.3, 1.0, 0.1), coat=0.8,
                           bump=dict(kind='noise', scale=40, strength=0.25))
    M['receptor_b'] = make_mat('Receptor_Blue', (0.12, 0.38, 1.0), rough=0.2,
                               coat=0.8, sss=0.2)
    M['receptor_g'] = make_mat('Receptor_Green', (0.3, 0.8, 0.12),
                               rough=0.2, coat=0.8, sss=0.2)
    M['cytoskeleton'] = make_mat('Cytoskeleton', (0.85, 0.15, 0.35),
                                 rough=0.4, emit=(0.9, 0.15, 0.35),
                                 emit_str=0.15)
    M['ecm'] = make_mat('ECM', (0.1, 0.14, 0.95), rough=0.08, trans=0.2,
                        ior=1.33, coat=1.0, coat_rough=0.02, sss=0.15,
                        sss_rad=(0.2, 0.3, 1.0), emit=(0.12, 0.15, 1.0),
                        emit_str=0.6)
    M['ecm2'] = make_mat('ECM_Branch', (0.3, 0.12, 0.95), rough=0.1,
                         trans=0.2, coat=1.0, sss=0.15,
                         emit=(0.3, 0.12, 1.0), emit_str=0.6)
    M['pedestal'] = make_mat('Pedestal', (0.02, 0.06, 0.5), rough=0.15,
                             metal=0.25, coat=1.0, coat_rough=0.04)
    M['stand'] = make_mat('Stand', (0.01, 0.015, 0.08), rough=0.3, coat=0.6)
    M['floor'] = make_mat('Floor', (0.003, 0.006, 0.028), rough=0.75,
                          spec=0.15)
    return M


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------
def setup_render(samples, percent):
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.render.resolution_x = RES_X
    sc.render.resolution_y = RES_Y
    sc.render.resolution_percentage = percent
    cy = sc.cycles
    cy.samples = samples
    cy.use_adaptive_sampling = True
    cy.use_denoising = True
    cy.max_bounces = 10
    cy.transmission_bounces = 8
    cy.transparent_max_bounces = 8
    try:
        prefs = bpy.context.preferences.addons['cycles'].preferences
        for dev in ('OPTIX', 'CUDA', 'HIP', 'METAL', 'ONEAPI'):
            try:
                prefs.compute_device_type = dev
                prefs.get_devices()
                if any(d.type == dev for d in prefs.devices):
                    for d in prefs.devices:
                        d.use = True
                    cy.device = 'GPU'
                    break
            except Exception:
                continue
    except Exception:
        pass
    vs = sc.view_settings
    for vt in ('Standard', 'AgX'):
        try:
            vs.view_transform = vt
            break
        except Exception:
            pass
    for look in ('Medium High Contrast', 'None'):
        try:
            vs.look = look
            break
        except Exception:
            pass
    vs.exposure = -0.35


def contact_sheet(paths, out):
    """Combine 4 renders into a 2x2 grid (top: first two)."""
    import numpy as np
    imgs = [bpy.data.images.load(p) for p in paths]
    w, h = imgs[0].size
    arr = []
    for im in imgs:
        a = np.empty(w * h * 4, dtype=np.float32)
        im.pixels.foreach_get(a)
        arr.append(a.reshape(h, w, 4))
    top = np.hstack(arr[:2])
    bottom = np.hstack(arr[2:4])
    grid = np.vstack([bottom, top])       # Blender rows go bottom-up
    out_img = bpy.data.images.new('grid', w * 2, h * 2, alpha=True)
    out_img.pixels.foreach_set(grid.ravel())
    out_img.filepath_raw = out
    out_img.file_format = 'PNG'
    out_img.save()


# ---------------------------------------------------------------------------
# 3D-print export: one watertight, manifold solid
# ---------------------------------------------------------------------------
PRINT_SIZE_MM = 150.0      # longest side of the printed model
PRINT_VOXEL = 0.022        # remesh resolution in scene units (~0.33 mm)
PRINT_MAX_TRIS = 1_000_000


def _apply_modifiers(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    old = ob.data
    ob.modifiers.clear()
    ob.data = me
    bpy.data.meshes.remove(old)


def _keep_largest_island(me):
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    seen = set()
    islands = []
    for v in bm.verts:
        if v.index in seen:
            continue
        stack, comp = [v], []
        seen.add(v.index)
        while stack:
            cur = stack.pop()
            comp.append(cur)
            for e in cur.link_edges:
                o = e.other_vert(cur)
                if o.index not in seen:
                    seen.add(o.index)
                    stack.append(o)
        islands.append(comp)
    islands.sort(key=len, reverse=True)
    removed = sum(len(c) for c in islands[1:])
    if len(islands) > 1:
        bmesh.ops.delete(bm, geom=[v for c in islands[1:] for v in c],
                         context='VERTS')
    bm.to_mesh(me)
    bm.free()
    return len(islands) - 1, removed


def write_stl(me, path):
    """Binary STL writer (independent of the exporter add-on/selection)."""
    import struct
    import numpy as np
    me.calc_loop_triangles()
    n = len(me.loop_triangles)
    co = np.empty(len(me.vertices) * 3, dtype=np.float32)
    me.vertices.foreach_get('co', co)
    co = co.reshape(-1, 3)
    tri = np.empty(n * 3, dtype=np.int32)
    me.loop_triangles.foreach_get('vertices', tri)
    tri = tri.reshape(-1, 3)
    v0, v1, v2 = co[tri[:, 0]], co[tri[:, 1]], co[tri[:, 2]]
    nrm = np.cross(v1 - v0, v2 - v0)
    ln = np.linalg.norm(nrm, axis=1, keepdims=True)
    nrm = nrm / np.where(ln == 0, 1, ln)
    rec = np.zeros(n, dtype=[('n', '<f4', 3), ('a', '<f4', 3), ('b', '<f4', 3),
                             ('c', '<f4', 3), ('attr', '<u2')])
    rec['n'], rec['a'], rec['b'], rec['c'] = nrm, v0, v1, v2
    with open(path, 'wb') as f:
        f.write(b'Macrophage cell - printable solid (mm)'.ljust(80, b' '))
        f.write(struct.pack('<I', n))
        f.write(rec.tobytes())


def make_print_model(colls, out_path=None, size_mm=PRINT_SIZE_MM,
                     voxel=PRINT_VOXEL):
    """Fuse every part into a single solid and export it as STL (mm)."""
    for mb in bpy.data.metaballs:          # full-detail metaballs
        mb.resolution = mb.render_resolution
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    bm = bmesh.new()
    for c in colls:
        for ob in c.all_objects:
            if ob.type not in ('MESH', 'CURVE', 'META', 'FONT'):
                continue
            ev = ob.evaluated_get(dg)
            try:
                me = ev.to_mesh()
            except RuntimeError:
                continue
            if me is None or not len(me.vertices):
                ev.to_mesh_clear()
                continue
            me.transform(ob.matrix_world)
            bm.from_mesh(me)
            ev.to_mesh_clear()
    me = bpy.data.meshes.new('Print_Model')
    bm.to_mesh(me)
    bm.free()
    pc = bpy.data.collections.get('Print') or new_coll('Print')
    ob = bpy.data.objects.new('Print_Model', me)
    pc.objects.link(ob)
    add_mod(ob, 'REMESH', mode='VOXEL', voxel_size=voxel, adaptivity=0.0,
            use_smooth_shade=True)
    _apply_modifiers(ob)
    islands, verts = _keep_largest_island(ob.data)
    tris = sum(len(p.vertices) - 2 for p in ob.data.polygons)
    if tris > PRINT_MAX_TRIS:
        add_mod(ob, 'DECIMATE', decimate_type='COLLAPSE',
                ratio=PRINT_MAX_TRIS / tris, use_collapse_triangulate=True)
        _apply_modifiers(ob)
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bad = sum(1 for e in bm.edges if not e.is_manifold)
    vol = bm.calc_volume()
    tris = sum(len(f.verts) - 2 for f in bm.faces)
    bm.free()
    xs = [v.co for v in ob.data.vertices]
    lo = Vector((min(v.x for v in xs), min(v.y for v in xs),
                 min(v.z for v in xs)))
    hi = Vector((max(v.x for v in xs), max(v.y for v in xs),
                 max(v.z for v in xs)))
    size = hi - lo
    scale = size_mm / max(size)
    # put the model on the build plate (z = 0), centred, in millimetres
    ob.data.transform(Matrix.Scale(scale, 4) @
                      Matrix.Translation(-Vector(((lo.x + hi.x) / 2,
                                                  (lo.y + hi.y) / 2, lo.z))))
    ob.data.materials.append(bpy.data.materials.get('Print_Clay') or
                             make_mat('Print_Clay', (0.75, 0.72, 0.7),
                                      rough=0.5))
    pc.hide_render = True
    report = ('PRINT  islands removed: %d (%d verts) | non-manifold edges: %d'
              ' | triangles: %d | size: %.1f x %.1f x %.1f mm | volume: %.1f cm3'
              % (islands, verts, bad, tris, size.x * scale, size.y * scale,
                 size.z * scale, abs(vol) * scale ** 3 / 1000.0))
    print(report)
    if out_path:
        write_stl(ob.data, out_path)
        print('PRINT  exported', out_path)
    return ob


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []

    def arg(name, default=None):
        return argv[argv.index(name) + 1] if name in argv else default

    samples = int(arg('--samples', RENDER_SAMPLES))
    percent = int(arg('--scale', RES_PERCENT))

    clear_scene()
    M = build_materials()
    C = {k: new_coll(k) for k in ('Cell', 'Organelles', 'Bacteria', 'ECM',
                                  'Pedestal', 'Camera_Lights')}
    build_cell(C['Cell'], M)
    cup_c, cup_R = build_pseudopodia(C['Cell'], M)
    build_receptors(C['Cell'], M)

    org = C['Organelles']
    build_nucleus(org, M, 'Nucleus', (0.25, -0.4), 1.3, 1.2, 0.82, 0.24,
                  M['nucleus'])
    build_nucleus(org, M, 'Nucleus_Small', (1.25, 1.85), 0.46, 0.46, 0.46,
                  0.14, M['nucleus2'], pores=False)
    build_phagolysosome(org, M, (-1.55, 0.3), 0.58)
    for name, c, L, r, a in [('Mito_1', (-0.85, 1.75), 1.15, 0.29, 15),
                             ('Mito_2', (2.15, 1.25), 0.8, 0.24, -45),
                             ('Mito_3', (-1.85, -1.2), 1.1, 0.31, -20),
                             ('Mito_4', (1.85, -1.6), 1.0, 0.25, -30),
                             ('Mito_6', (-0.55, -1.9), 0.85, 0.22, -5)]:
        build_mitochondrion(org, M, name, c, L, r, a)
    build_golgi(org, M, 'Golgi_Central', (0.3, 1.22), 90, 6, 1.45, 50,
                M['golgi_b'], M['golgi_ves'], gap=0.125)
    build_golgi(org, M, 'Golgi_Right', (2.15, -0.3), 0, 6, 0.7, 66,
                M['golgi_o'], M['golgi_ves'])
    build_rer(org, M, (1.25, 0.35), 1.05, 4, gap=0.17)
    build_lysosomes_and_dots(org, M)
    build_cytoskeleton(org, M)
    build_bacteria(C['Bacteria'], M, cup_c, cup_R)
    stand_up([C['Cell'], C['Organelles'], C['Bacteria']])

    build_ecm(C['ECM'], M)
    build_pedestal(C['Pedestal'], M)
    build_environment(C['Camera_Lights'], M)
    cams = build_cameras(C['Camera_Lights'])
    build_lights(C['Camera_Lights'])
    setup_render(samples, percent)

    stl = arg('--print')
    if stl:
        make_print_model([C['Cell'], C['Organelles'], C['Bacteria'],
                          C['ECM'], C['Pedestal']], os.path.abspath(stl),
                         float(arg('--print-size', PRINT_SIZE_MM)),
                         float(arg('--voxel', PRINT_VOXEL)))

    save = arg('--save')
    if save:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(save))
    out = arg('--render')
    if out:
        out = os.path.abspath(out)
        views = arg('--views', 'front').split(',')
        sc = bpy.context.scene
        written = []
        for v in views:
            sc.camera = cams[v]
            path = out if len(views) == 1 else \
                os.path.splitext(out)[0] + '_' + v + '.png'
            sc.render.filepath = path
            bpy.ops.render.render(write_still=True)
            written.append(path)
        if len(written) == 4:
            contact_sheet(written, os.path.splitext(out)[0] + '_grid.png')
        sc.camera = cams['front']


if __name__ == '__main__':
    main()
