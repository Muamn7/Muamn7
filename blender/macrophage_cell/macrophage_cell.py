"""
Macrophage Cell - Phagocytosis Activity
=======================================
Procedural Blender scene: a high-detail, labelled 3D model of a macrophage
engulfing bacteria, displayed on a pedestal (infographic style).

Works with Blender 4.2 LTS, 4.5 LTS and 5.x (render engine: Cycles).

HOW TO USE (inside Blender)
  1. File > New > General, then open the "Scripting" workspace.
  2. Text Editor > Open > macrophage_cell.py  >  Run Script (Alt+P).
     WARNING: the script clears the current scene first.
  3. Press F12 to render (camera, lights and Cycles settings are ready).

COMMAND LINE
  blender -b -P macrophage_cell.py -- --render out.png [--samples 256]
          [--scale 100] [--save scene.blend] [--no-labels]

Everything is grouped in collections (Cell, Organelles, Bacteria, ECM,
Pedestal, Labels, Lighting) and every material is a normal Principled BSDF
node tree, so you can tweak anything by hand afterwards.
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
SEED = 7
SHOW_LABELS = True
RENDER_SAMPLES = 256
RES_X, RES_Y = 1536, 1024
RES_PERCENT = 100

CELL_A, CELL_B, CELL_C = 3.0, 2.25, 1.05   # cell half-size (x, y, z)
RIM_Z = 0.30                              # height of the cut membrane rim
FLOOR_Z = 0.05                            # top of the cytoplasm
PED_TOP = -1.45                           # top of the pedestal
CELL_TILT = 24.0                          # forward tilt of the cell (deg)
TILT_PIVOT = Vector((0.0, 0.0, -0.95))

ANCHORS = {}                              # label anchor points (world)
OCCUPIED = []                             # (x, y, r) discs used on the floor

random.seed(SEED)


# ---------------------------------------------------------------------------
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
# Cell shape
# ---------------------------------------------------------------------------
def shape_scale(d):
    n = noise.noise(d * 1.6 + Vector((3.1, 1.7, 0.4)))
    lobe = 0.16 * max(0.0, -d.x) * max(0.0, d.y + 0.25)   # upper-left lobe
    return 1.0 + 0.08 * n + lobe


def shell_point(d, k=1.0):
    s = shape_scale(d) * k
    return Vector((d.x * CELL_A * s, d.y * CELL_B * s, d.z * CELL_C * s))


def rim_point(theta_deg, z=RIM_Z, k=1.0):
    """Point on the outer membrane at angle theta (degrees) and height z."""
    t = math.radians(theta_deg)
    dz = max(-0.99, min(0.99, z / CELL_C))
    for _ in range(4):
        r = math.sqrt(1 - dz * dz)
        d = Vector((math.cos(t) * r, math.sin(t) * r, dz))
        p = shell_point(d, k)
        dz = max(-0.99, min(0.99, dz * z / p.z if abs(p.z) > 1e-4 else dz))
    return shell_point(d, k)


def build_cell(coll, M):
    # ---- outer membrane (cut open bowl) ----
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=6, radius=1.0)
    for v in bm.verts:
        d = v.co.normalized()
        p = shell_point(d)
        p += d * (0.022 * noise.noise(d * 7.0) + 0.01 * noise.noise(d * 15.0))
        v.co = p
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    bmesh.ops.bisect_plane(bm, geom=geom, plane_co=(0, 0, RIM_Z),
                           plane_no=(0, 0, 1), clear_outer=True)
    shell = bm_object('Cell_Membrane', bm, coll, [M['membrane'], M['rim']])
    add_mod(shell, 'SOLIDIFY', thickness=0.24, offset=-1.0, use_rim=True,
            use_even_offset=True, material_offset_rim=1)
    add_mod(shell, 'BEVEL', width=0.08, segments=5, limit_method='ANGLE',
            angle_limit=math.radians(35))
    add_mod(shell, 'SUBSURF', levels=0, render_levels=1)

    # ---- cytoplasm (filled interior with flat top) ----
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=5, radius=1.0)
    for v in bm.verts:
        v.co = shell_point(v.co.normalized(), 0.955)
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    bmesh.ops.bisect_plane(bm, geom=geom, plane_co=(0, 0, FLOOR_Z),
                           plane_no=(0, 0, 1), clear_outer=True)
    for f in bm.faces:
        f.smooth = True
    boundary = [e for e in bm.edges if e.is_boundary]
    res = bmesh.ops.holes_fill(bm, edges=boundary, sides=0)
    for f in res['faces']:
        bmesh.ops.triangulate(bm, faces=[f])
    top = [f for f in bm.faces if f.normal.z > 0.999 and
           all(abs(v.co.z - FLOOR_Z) < 1e-4 for v in f.verts)]
    for f in top:
        f.smooth = False
    cyto = bm_object('Cytoplasm', bm, coll, [M['cytoplasm']], smooth=False)
    ANCHORS['cytoplasm'] = Vector((2.25, 0.55, FLOOR_Z))
    ANCHORS['membrane'] = rim_point(20) + Vector((0, 0, 0.05))

    # ---- stand under the cell ----
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=48, radius1=0.95,
                          radius2=0.75, depth=1.3,
                          matrix=Matrix.Translation((0, 0.1, PED_TOP + 0.45)))
    st = bm_object('Cell_Stand', bm, coll, [M['pedestal']], smooth=False)
    add_mod(st, 'BEVEL', width=0.05, segments=3)
    return shell, cyto


def build_pseudopodia(coll, M):
    """Organic pseudopodia and the phagocytic cup (metaballs)."""
    mb = bpy.data.metaballs.new('Pseudopodia')
    mb.resolution = 0.08
    mb.render_resolution = 0.035
    mb.threshold = 0.6

    def chain(ctrl, r0, r1, step=0.06, k=1.55):
        pts = catmull(ctrl, step)
        n = len(pts)
        for i, p in enumerate(pts):
            t = i / (n - 1)
            r = r0 + (r1 - r0) * (t ** 0.85)
            e = mb.elements.new()
            e.co = p
            e.radius = r * k
            e.stiffness = 2.0
        tip = mb.elements.new()
        tip.co = pts[-1]
        tip.radius = r1 * 2.1

    arms = [
        # tall arm rising behind the cup
        ([(-2.55, 1.55, 0.05), (-2.95, 1.95, 0.7), (-3.05, 2.1, 1.35),
          (-2.85, 2.0, 1.75)], 0.36, 0.14),
        # arm reaching up-left
        ([(-2.85, 1.0, 0.1), (-3.55, 1.3, 0.55), (-4.05, 1.65, 1.2),
          (-4.2, 1.9, 1.75)], 0.34, 0.11),
        # long horizontal arms on the left
        ([(-2.95, 0.4, 0.05), (-3.75, 0.35, 0.25), (-4.45, 0.45, 0.5),
          (-4.85, 0.6, 0.62)], 0.33, 0.1),
        ([(-2.95, -0.25, 0.0), (-3.7, -0.55, 0.0), (-4.35, -0.65, 0.18),
          (-4.75, -0.6, 0.3)], 0.32, 0.1),
        ([(-2.65, -0.95, -0.1), (-3.3, -1.45, -0.25), (-3.85, -1.85, -0.2),
          (-4.15, -2.1, -0.05)], 0.3, 0.09),
        ([(-2.1, -1.55, -0.2), (-2.6, -2.2, -0.45), (-3.0, -2.6, -0.55)],
         0.26, 0.08),
        # small side branches
        ([(-3.75, 0.35, 0.25), (-4.0, -0.05, 0.55), (-4.15, -0.2, 0.85)],
         0.16, 0.07),
        ([(-3.55, 1.3, 0.55), (-3.95, 0.95, 1.0), (-4.2, 0.9, 1.25)],
         0.15, 0.07),
        ([(-3.3, -1.45, -0.25), (-3.45, -1.15, 0.15), (-3.7, -1.0, 0.4)],
         0.14, 0.06),
    ]
    for ctrl, r0, r1 in arms:
        chain(ctrl, r0, r1)

    # phagocytic cup: an open ring of membrane wrapping a bacteria cluster
    cup_c = Vector((-3.05, 1.45, 0.95))
    nrm = Vector((-0.45, -0.5, 0.75)).normalized()
    R = nrm.to_track_quat('Z', 'Y').to_matrix()
    ring = []
    for i in range(0, 300, 6):
        a = math.radians(i + 200)
        ring.append(cup_c + R @ Vector((math.cos(a) * 0.62,
                                         math.sin(a) * 0.62, 0)))
    for i, p in enumerate(ring):
        t = i / (len(ring) - 1)
        e = mb.elements.new()
        e.co = p
        e.radius = (0.2 + 0.08 * math.sin(t * math.pi)) * 1.55
    # cup bottom (membrane sheet behind the bacteria)
    for i in range(7):
        a = 2 * math.pi * i / 7
        p = cup_c + R @ Vector((math.cos(a) * 0.3, math.sin(a) * 0.3, -0.36))
        e = mb.elements.new()
        e.co = p
        e.radius = 0.34
    # stalk connecting cup to the cell
    chain([(-2.45, 1.25, 0.1), (-2.75, 1.35, 0.45), cup_c - R @ Vector((0, 0, 0.3))],
          0.34, 0.26, k=1.5)

    ob = bpy.data.objects.new('Pseudopodia', mb)
    mb.materials.append(M['membrane'])
    coll.objects.link(ob)
    ANCHORS['cup'] = cup_c + R @ Vector((0.0, 0.62, 0.0))
    ANCHORS['pseudo_env'] = Vector((-3.6, 1.32, 0.62))
    ANCHORS['pseudo'] = Vector((-3.75, -0.55, 0.12))
    return cup_c, R


def build_receptors(coll, M):
    blue, green = [], []
    for i, th in enumerate([52, 63, 74, 86, 97, 108, 119, 131]):
        base = rim_point(th, RIM_Z - 0.02, 0.985)
        h = random.uniform(0.32, 0.42)
        top = base + Vector((random.uniform(-0.03, 0.03), 0, h))
        spread = 0.13
        lean = Vector((random.uniform(-0.04, 0.04), 0.03, 0))
        armL = top + Vector((-spread, 0, 0.17)) + lean
        armR = top + Vector((spread, 0, 0.17)) + lean
        stalk = catmull([base, base.lerp(top, 0.5) + lean * 0.3, top], 0.03)
        target = blue if i % 2 == 0 else green
        target.append((stalk, None))
        for a in (armL, armR):
            arm = catmull([top, top.lerp(a, 0.55) + Vector((0, 0, 0.03)), a], 0.02)
            target.append((arm, None))
        if i == 4:
            ANCHORS['receptors'] = armR
    for name, sps, mat in (('Receptors_Blue', blue, M['receptor_b']),
                           ('Receptors_Green', green, M['receptor_g'])):
        curve_object(name, sps, coll, mat, bevel=0.032, bevel_res=4)
    # knobs at receptor tips
    bm = bmesh.new()
    for sps in (blue, green):
        for k, (pts, _) in enumerate(sps):
            if k % 3:
                add_sphere(bm, pts[-1], 0.045, 2)
    bm_object('Receptor_Tips', bm, coll, [M['receptor_b']])


# ---------------------------------------------------------------------------
# Organelles
# ---------------------------------------------------------------------------
def build_nucleus(coll, M, c=(0.25, -0.55)):
    cx, cy = c
    rx, ry, rz = 1.08, 1.0, 0.62
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=6, radius=1.0)
    for v in bm.verts:
        d = v.co.normalized()
        p = Vector((d.x * rx, d.y * ry, d.z * rz))
        bumps = (0.045 * noise.noise(d * 4.0 + Vector((5, 2, 1))) +
                 0.025 * noise.noise(d * 9.0) +
                 0.012 * noise.noise(d * 22.0))
        p += d * bumps
        rho = math.hypot(p.x, p.y)
        if d.z > 0:
            pit = 0.24 * max(0.0, 1 - (rho / 0.42) ** 2) ** 2
            lip = 0.05 * math.exp(-((rho - 0.46) / 0.12) ** 2)
            p.z += (lip - pit) * d.z
        v.co = p + Vector((cx, cy, FLOOR_Z - 0.04))
    bm_object('Nucleus', bm, coll, [M['nucleus']])
    top = FLOOR_Z - 0.04 + rz
    bm = bmesh.new()
    add_sphere(bm, (cx, cy, top - 0.1), 0.2, 4)
    bm_object('Nucleolus', bm, coll, [M['nucleolus']])
    # nuclear pores
    bm = bmesh.new()
    for _ in range(90):
        d = Vector((random.uniform(-1, 1), random.uniform(-1, 1),
                    random.uniform(0.15, 1))).normalized()
        p = Vector((d.x * rx, d.y * ry, d.z * rz))
        if math.hypot(p.x, p.y) < 0.55:
            continue
        nrm = Vector((d.x / rx, d.y / ry, d.z / rz)).normalized()
        q = p + Vector((cx, cy, FLOOR_Z - 0.04)) + nrm * 0.035
        res = bmesh.ops.create_circle(bm, cap_ends=False, segments=10,
                                      radius=0.035)
        bmesh.ops.transform(bm, verts=res['verts'], matrix=(
            Matrix.Translation(q) @ nrm.to_track_quat('Z', 'Y').to_matrix().to_4x4()))
    po = bm_object('Nuclear_Pores', bm, coll, [M['nucleolus']])
    add_mod(po, 'WIREFRAME', thickness=0.014, use_even_offset=True)
    OCCUPIED.append((cx, cy, 1.08))
    ANCHORS['nucleus'] = Vector((cx + 0.55, cy + 0.55, FLOOR_Z + 0.45))


def build_vesicle(coll, M, c=(1.0, 1.42)):
    cx, cy = c
    bm = bmesh.new()
    add_sphere(bm, (cx, cy, FLOOR_Z + 0.12), 0.44, 5, scale=(1, 1, 0.92))
    bm_object('Secretory_Vesicle', bm, coll, [M['vesicle']])
    bm = bmesh.new()
    add_sphere(bm, (cx + 0.05, cy - 0.04, FLOOR_Z + 0.12), 0.16, 4)
    bm_object('Vesicle_Core', bm, coll, [M['nucleolus']])
    OCCUPIED.append((cx, cy, 0.46))


def build_mitochondrion(coll, M, name, c, length, radius, angle):
    bm = bmesh.new()
    add_capsule(bm, (0, 0, 0), length, radius, subdiv=4, squash=0.75)
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    bmesh.ops.bisect_plane(bm, geom=geom, plane_co=(0, 0, 0.0),
                           plane_no=(0, 0, 1), clear_outer=True)
    ob = bm_object(name, bm, coll, [M['mito'], M['mito_rim']])
    add_mod(ob, 'SOLIDIFY', thickness=0.035, offset=-1, use_rim=True,
            material_offset_rim=1)
    add_mod(ob, 'BEVEL', width=0.012, segments=2, limit_method='ANGLE')
    add_mod(ob, 'SUBSURF', levels=1, render_levels=2)
    ob.location = (c[0], c[1], FLOOR_Z + 0.06)
    ob.rotation_euler = (0, 0, math.radians(angle))
    # matrix floor + cristae
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
                      bevel=0.014, extrude=radius * 0.32, two_d=True)
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
                mat, ves_mat):
    f = math.radians(facing_deg)
    fd = Vector((math.cos(f), math.sin(f), 0))
    arc_c = Vector((center[0], center[1], 0)) - fd * (base_r + n * 0.045)
    splines = []
    gap = 0.11
    for i in range(n):
        R = base_r + i * gap
        span = math.radians(span_deg * (1.0 - 0.06 * abs(i - n / 2)))
        pts, radii = [], []
        m = 40
        for k in range(m + 1):
            t = k / m
            a = f - span / 2 + span * t
            wob = 0.012 * math.sin(t * 9 + i)
            p = arc_c + Vector((math.cos(a), math.sin(a), 0)) * (R + wob)
            pts.append((p.x, p.y, 0))
            end = min(t, 1 - t) / 0.12
            radii.append(0.35 + 0.65 * min(1.0, end) +
                         0.12 * math.sin(t * math.pi * 3 + i))
        splines.append((pts, radii))
    ob = curve_object(name, splines, coll, mat, bevel=0.042, extrude=0.09,
                      two_d=True, bevel_res=4)
    ob.location.z = FLOOR_Z + 0.04
    # budding vesicles at cisterna tips
    bm = bmesh.new()
    for i in range(n):
        R = base_r + i * gap
        span = math.radians(span_deg * (1.0 - 0.06 * abs(i - n / 2)))
        for side in (-1, 1):
            for j in range(random.randint(1, 2)):
                a = f + side * (span / 2 + random.uniform(0.06, 0.2))
                p = arc_c + Vector((math.cos(a), math.sin(a), 0)) * \
                    (R + random.uniform(-0.05, 0.05))
                add_sphere(bm, (p.x, p.y, FLOOR_Z + random.uniform(0.04, 0.1)),
                           random.uniform(0.035, 0.06), 2)
    bm_object(name + '_Vesicles', bm, coll, [ves_mat])
    mid = arc_c + fd * (base_r + n * gap * 0.5)
    OCCUPIED.append((mid.x, mid.y, n * gap * 0.6 + 0.12))
    return arc_c, mid


def build_rer(coll, M, origin=(1.05, 0.42), width=1.55, rows=6):
    ox, oy = origin
    gap = 0.15
    pts = []
    for r in range(rows):
        y0 = oy + r * gap
        xs = [ox + width * k / 60 for k in range(61)]
        if r % 2:
            xs.reverse()
        for x in xs:
            y = y0 + 0.035 * math.sin((x - ox) * 7.0 + r * 1.3)
            pts.append(Vector((x, y, 0)))
        if r < rows - 1:  # U-turn
            end = pts[-1]
            side = 1 if r % 2 == 0 else -1
            for k in range(1, 10):
                a = math.pi * k / 10
                pts.append(Vector((end.x + side * math.sin(a) * gap * 0.5,
                                   end.y + (1 - math.cos(a)) * gap * 0.5, 0)))
    ob = curve_object('Rough_ER', [([tuple(p) for p in pts], None)], coll,
                      M['rer'], bevel=0.032, extrude=0.08, two_d=True,
                      bevel_res=4)
    ob.location.z = FLOOR_Z + 0.04
    # ribosomes studding the membrane
    bm = bmesh.new()
    for i in range(1, len(pts) - 1, 2):
        p = pts[i]
        t = (pts[i + 1] - pts[i - 1]).normalized()
        nrm = Vector((-t.y, t.x, 0))
        for side in (-1, 1):
            if random.random() < 0.85:
                q = p + nrm * side * random.uniform(0.052, 0.062)
                add_sphere(bm, (q.x, q.y, FLOOR_Z + 0.04 +
                                random.uniform(-0.02, 0.1)),
                           random.uniform(0.016, 0.022), 1)
        if random.random() < 0.5:
            add_sphere(bm, (p.x, p.y, FLOOR_Z + 0.04 + 0.1),
                       0.018, 1)
    bm_object('Ribosomes_on_RER', bm, coll, [M['ribosome']])
    OCCUPIED.append((ox + width / 2, oy + rows * gap / 2, 0.8))
    ANCHORS['rer'] = Vector((ox + width * 0.8, oy + gap * 2.0, FLOOR_Z + 0.1))
    ANCHORS['ribosomes'] = Vector((ox + width * 0.9, oy + gap * (rows - 1) +
                                   0.05, FLOOR_Z + 0.15))


def build_phagolysosome(coll, M, c=(-0.95, -0.02)):
    cx, cy = c
    cz = FLOOR_Z + 0.02
    R = 0.46
    bm = bmesh.new()
    add_sphere(bm, (0, 0, 0), R, 5)
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    bmesh.ops.bisect_plane(bm, geom=geom, plane_co=(0, 0, 0.12),
                           plane_no=(0, 0, 1), clear_outer=True)
    mem = bm_object('Phagolysosome', bm, coll, [M['phago'], M['phago_rim']])
    add_mod(mem, 'SOLIDIFY', thickness=0.04, offset=-1, use_rim=True,
            material_offset_rim=1)
    add_mod(mem, 'SUBSURF', levels=1, render_levels=1)
    mem.location = (cx, cy, cz)
    # digested debris inside (bacterial fragments)
    keys = ['debris_g', 'debris_y', 'debris_p', 'debris_b']
    bms = {k: bmesh.new() for k in keys}
    for i in range(70):
        a = random.uniform(0, 2 * math.pi)
        r = random.uniform(0, R * 0.78) ** 0.8
        z = random.uniform(-0.16, 0.12)
        p = (cx + math.cos(a) * r, cy + math.sin(a) * r, cz + z)
        b = bms[random.choice(keys)]
        if random.random() < 0.45:
            add_capsule(b, p, random.uniform(0.07, 0.15),
                        random.uniform(0.022, 0.035),
                        rot=(random.uniform(0, 3), random.uniform(0, 3),
                             random.uniform(0, 3)), subdiv=2)
        else:
            vs = add_sphere(b, p, random.uniform(0.025, 0.05), 1,
                            scale=(random.uniform(0.7, 1.3),
                                   random.uniform(0.7, 1.3),
                                   random.uniform(0.7, 1.3)))
    for k in keys:
        bm_object('Phagolysosome_' + k, bms[k], coll, [M[k]])
    # radiating tubular fringe (lysosome docking ring)
    bm = bmesh.new()
    for i in range(84):
        a = 2 * math.pi * i / 84 + random.uniform(-0.03, 0.03)
        L = random.uniform(0.12, 0.2)
        rr = R + 0.02 + L / 2
        p = (cx + math.cos(a) * rr, cy + math.sin(a) * rr,
             cz + random.uniform(-0.04, 0.06))
        add_capsule(bm, p, L, random.uniform(0.016, 0.024),
                    rot=(0, random.uniform(-0.3, 0.3), a), subdiv=2)
    bm_object('Phagolysosome_Fringe', bm, coll, [M['fringe']])
    # small lysosomes fusing with it
    bm = bmesh.new()
    for a in (0.6, 2.3, 4.1, 5.3):
        rr = R + 0.32
        add_sphere(bm, (cx + math.cos(a) * rr, cy + math.sin(a) * rr,
                        FLOOR_Z + 0.05), random.uniform(0.07, 0.09), 3)
    bm_object('Fusing_Lysosomes', bm, coll, [M['lysosome']])
    OCCUPIED.append((cx, cy, R + 0.48))
    ANCHORS['phagolysosome'] = Vector((cx, cy - 0.15, cz + 0.08))


def build_lysosomes_and_dots(coll, M):
    bm = bmesh.new()
    placed = 0
    tries = 0
    lys_anchor = None
    fixed = [(-0.15, -1.75, 0.13), (1.15, -1.55, 0.1), (-1.85, -0.75, 0.11),
             (2.35, -0.95, 0.09), (-1.55, 0.55, 0.1)]
    for (x, y, r) in fixed:
        add_sphere(bm, (x, y, FLOOR_Z + r * 0.35), r, 3)
        OCCUPIED.append((x, y, r))
    lys_anchor = Vector((fixed[0][0], fixed[0][1], FLOOR_Z + 0.12))
    while placed < 22 and tries < 4000:
        tries += 1
        x = random.uniform(-2.6, 2.6)
        y = random.uniform(-2.0, 2.0)
        r = random.uniform(0.045, 0.1)
        if inside_floor(x, y, 0.84) and floor_free(x, y, r, 0.04):
            add_sphere(bm, (x, y, FLOOR_Z + r * 0.3), r, 3)
            OCCUPIED.append((x, y, r))
            placed += 1
    bm_object('Lysosomes', bm, coll, [M['lysosome']])
    ANCHORS['lysosome'] = lys_anchor
    # free ribosomes / tiny vesicles speckling the cytoplasm
    bm = bmesh.new()
    n = 0
    tries = 0
    while n < 320 and tries < 20000:
        tries += 1
        x = random.uniform(-2.7, 2.7)
        y = random.uniform(-2.1, 2.1)
        r = random.uniform(0.014, 0.03)
        if inside_floor(x, y, 0.9) and floor_free(x, y, r, 0.0):
            add_sphere(bm, (x, y, FLOOR_Z + 0.005), r, 1)
            n += 1
    bm_object('Free_Ribosomes', bm, coll, [M['ribosome']])
    # exocytosis: vesicle fusing with the plasma membrane (right side)
    bm = bmesh.new()
    p = rim_point(-22, FLOOR_Z, 0.92)
    add_sphere(bm, (p.x, p.y, FLOOR_Z + 0.07), 0.12, 4)
    q = rim_point(-22, -0.15, 1.02)
    for k in range(5):
        add_sphere(bm, (q.x + random.uniform(0.05, 0.25),
                        q.y + random.uniform(-0.2, 0.1),
                        q.z + random.uniform(-0.25, 0.1)),
                   random.uniform(0.025, 0.045), 2)
    bm_object('Exocytosis_Vesicles', bm, coll, [M['lysosome']])
    ANCHORS['exocytosis'] = Vector((p.x, p.y, FLOOR_Z + 0.12))


def build_cytoskeleton(coll, M):
    sps = []
    for i in range(80):
        th = random.uniform(0, 2 * math.pi)
        k0 = random.uniform(0.78, 0.9)
        x0 = math.cos(th) * CELL_A * k0
        y0 = math.sin(th) * CELL_B * k0
        if not inside_floor(x0, y0, 0.92):
            continue
        ctrl = [(x0, y0, FLOOR_Z + 0.006)]
        ang = th + math.pi + random.uniform(-1.2, 1.2)
        L = random.uniform(0.5, 1.3)
        p = Vector((x0, y0, FLOOR_Z + 0.006))
        for s in range(3):
            ang += random.uniform(-0.6, 0.6)
            p = p + Vector((math.cos(ang), math.sin(ang), 0)) * L / 3
            if not inside_floor(p.x, p.y, 0.9):
                break
            ctrl.append(tuple(p))
        if len(ctrl) >= 2:
            sps.append((catmull(ctrl, 0.04), None))
    curve_object('Cytoskeleton', sps, coll, M['cytoskeleton'], bevel=0.007,
                 bevel_res=1)
    ANCHORS['cytoskeleton'] = rim_point(-62, FLOOR_Z + 0.01, 0.86)


# ---------------------------------------------------------------------------
# Bacteria
# ---------------------------------------------------------------------------
def build_bacteria(coll, M, cup_c, cup_R):
    bms = {'bact_a': bmesh.new(), 'bact_b': bmesh.new()}

    def bact(p, rot, L=None):
        b = bms['bact_a' if random.random() < 0.6 else 'bact_b']
        add_capsule(b, p, L or random.uniform(0.42, 0.6),
                    random.uniform(0.075, 0.095), rot=rot, subdiv=3,
                    bend=random.uniform(-0.04, 0.04))

    # cluster inside the phagocytic cup
    for i in range(11):
        a = random.uniform(0, 2 * math.pi)
        r = random.uniform(0.0, 0.33)
        p = cup_c + cup_R @ Vector((math.cos(a) * r, math.sin(a) * r,
                                    random.uniform(-0.12, 0.12)))
        bact(p, (random.uniform(0, 3.1), random.uniform(0, 3.1),
                 random.uniform(0, 3.1)))
    # bacteria approaching from outside
    approach = [(-4.05, 2.35, 2.25, 0.4, 0.2), (-3.55, 2.55, 2.55, -0.3, 0.9),
                (-4.45, 2.0, 1.85, 0.2, -0.6), (-3.2, 2.85, 2.35, 0.6, 0.3),
                (-4.7, 2.5, 2.4, -0.2, 1.4), (-3.85, 2.9, 2.85, 0.1, -0.2),
                (-4.9, 1.7, 2.05, 0.5, 0.5)]
    for (x, y, z, ry, rz) in approach:
        bact(Vector((x, y - 0.3, z - 0.45)), (0.3, ry, rz),
             random.uniform(0.5, 0.65))
    ANCHORS['bacteria'] = Vector((-4.45, 1.7, 1.45))
    # bacteria being wrapped by pseudopodia
    for p in [(-4.25, 1.05, 1.35), (-4.6, 0.25, 0.85), (-4.35, 0.75, 0.75)]:
        bact(Vector(p), (random.uniform(0, 3), random.uniform(0, 3), 0.5))
    for k, b in bms.items():
        ob = bm_object('Bacteria_' + k[-1].upper(), b, coll, [M[k]])
        add_mod(ob, 'SUBSURF', levels=1, render_levels=1)


# ---------------------------------------------------------------------------
# Extracellular matrix
# ---------------------------------------------------------------------------
def build_ecm(coll, M):
    thick, thin = [], []
    for i in range(46):
        phi = random.uniform(0, 2 * math.pi)
        # favour left/right/front where the image shows fibres
        r0 = random.uniform(0.7, 1.6)
        p0 = Vector((math.cos(phi) * r0 * 1.4, math.sin(phi) * r0,
                     -0.85))
        ctrl = [p0]
        L = random.uniform(2.2, 3.4)
        ang = phi
        p = p0.copy()
        for s in range(5):
            ang += random.uniform(-0.35, 0.35)
            p = p + Vector((math.cos(ang) * 1.25, math.sin(ang), 0)) * L / 5
            z = PED_TOP + 0.06 + random.uniform(0.0, 0.25) * (1 - s / 5) + \
                (0.3 if s == 0 else 0)
            ctrl.append(Vector((p.x, p.y, z)))
        if math.hypot(p.x, p.y) > 4.5:
            continue
        pts = catmull(ctrl, 0.06)
        rad = [1.0 - 0.6 * (k / len(pts)) for k in range(len(pts))]
        (thick if i % 3 else thin).append((pts, rad))
    # fibres climbing up to the pseudopodia on the left
    for i in range(9):
        y = random.uniform(-1.8, 0.8)
        ctrl = [Vector((-2.4 - random.uniform(0, 0.4), y, -0.7)),
                Vector((-3.4, y - 0.2, -1.1)),
                Vector((-3.9 - random.uniform(0, 0.3), y - 0.4, PED_TOP + 0.1)),
                Vector((-4.3, y - 0.6, PED_TOP + 0.05))]
        thick.append((catmull(ctrl, 0.06), None))
    curve_object('ECM_Fibres', thick, coll, M['ecm'], bevel=0.085,
                 bevel_res=4)
    curve_object('ECM_Fibrils', thin, coll, M['ecm2'], bevel=0.04,
                 bevel_res=2)
    ANCHORS['ecm_right'] = Vector((3.3, -1.2, PED_TOP + 0.15))
    ANCHORS['ecm_left'] = Vector((-3.6, -1.7, PED_TOP + 0.15))
    ANCHORS['ecm_mid'] = Vector((-1.6, -2.6, PED_TOP + 0.12))


# ---------------------------------------------------------------------------
# Pedestal & name plate
# ---------------------------------------------------------------------------
def load_font(bold=True):
    cands = [
        'C:/Windows/Fonts/segoeuib.ttf', 'C:/Windows/Fonts/arialbd.ttf',
        '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
        '/Library/Fonts/Arial Bold.ttf',
        '/usr/share/fonts/opentype/inter/Inter-Bold.otf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
    ]
    if not bold:
        cands = [c.replace('segoeuib', 'segoeui').replace('arialbd', 'arial')
                 .replace('Arial Bold', 'Arial').replace('-Bold', '-Regular')
                 for c in cands] + cands
    for c in cands:
        if os.path.exists(c):
            try:
                return bpy.data.fonts.load(c, check_existing=True)
            except Exception:
                pass
    return None


def make_text(name, body, size, coll, mat, font=None, extrude=0.0):
    cu = bpy.data.curves.new(name, 'FONT')
    cu.body = body
    cu.size = size
    cu.align_x = 'CENTER'
    cu.align_y = 'CENTER'
    cu.space_line = 0.95
    cu.extrude = extrude
    if font:
        cu.font = font
    ob = bpy.data.objects.new(name, cu)
    cu.materials.append(mat)
    coll.objects.link(ob)
    return ob


def rounded_box(name, size, coll, mat, radius, segs=6):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0,
                          matrix=Matrix.Diagonal((*size, 1.0)))
    ob = bm_object(name, bm, coll, [mat], smooth=False)
    add_mod(ob, 'BEVEL', width=radius, segments=segs, limit_method='NONE')
    return ob


def build_pedestal(coll, M, font_b, font_r):
    tiers = [(5.0, -2.3, -2.0), (4.65, -2.0, -1.72), (4.3, -1.72, PED_TOP)]
    for i, (r, z0, z1) in enumerate(tiers):
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=160, radius1=r,
                              radius2=r, depth=z1 - z0,
                              matrix=Matrix.Translation((0, 0, (z0 + z1) / 2)))
        ob = bm_object('Pedestal_Tier_%d' % (i + 1), bm, coll,
                       [M['pedestal']], smooth=False)
        add_mod(ob, 'BEVEL', width=0.06, segments=4, limit_method='ANGLE',
                angle_limit=math.radians(30))
        for f in ob.data.polygons:
            f.use_smooth = True
        # glowing edge ring
        bm = bmesh.new()
        bmesh.ops.create_circle(bm, cap_ends=False, segments=200,
                                radius=r - 0.035,
                                matrix=Matrix.Translation((0, 0, z1 - 0.005)))
        ring = bm_object('Pedestal_Glow_%d' % (i + 1), bm, coll,
                         [M['glow']], smooth=False)
        add_mod(ring, 'WIREFRAME', thickness=0.018)
    # name plate
    pl = coll
    root = bpy.data.objects.new('NamePlate', None)
    pl.objects.link(root)
    root.location = (0, -4.95, -1.5)
    root.rotation_euler = (math.radians(80), 0, 0)
    frame = rounded_box('NamePlate_Frame', (5.2, 1.4, 0.16), pl, M['glow_edge'],
                        0.12)
    frame.parent = root
    face = rounded_box('NamePlate_Face', (5.0, 1.22, 0.18), pl, M['plate'],
                       0.1)
    face.parent = root
    face.location.z = 0.012
    t1 = make_text('Title', 'Macrophage Cell', 0.58, pl, M['title'], font_b,
                   0.015)
    t1.parent = root
    t1.location = (0, 0.18, 0.105)
    t2 = make_text('Subtitle', 'Phagocytosis Activity', 0.3, pl, M['subtitle'],
                   font_r, 0.01)
    t2.parent = root
    t2.location = (0, -0.38, 0.105)
    for sx in (-1, 1):
        ln = rounded_box('Subtitle_Line', (0.95, 0.025, 0.01), pl,
                         M['subtitle'], 0.008, 2)
        ln.parent = root
        ln.location = (sx * 1.95, -0.37, 0.105)


def build_environment(coll, M):
    # back wall with radial gradient
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=1.0)
    wall = bm_object('Backdrop', bm, coll, [M['backdrop']], smooth=False)
    wall.scale = (40, 24, 1)
    wall.location = (0, 14, 4)
    wall.rotation_euler = (math.radians(90), 0, 0)
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=1.0)
    fl = bm_object('Floor', bm, coll, [M['floor']], smooth=False)
    fl.scale = (40, 40, 1)
    fl.location = (0, 0, -2.3)


# ---------------------------------------------------------------------------
# Camera, lights, labels
# ---------------------------------------------------------------------------
def build_camera(coll):
    cd = bpy.data.cameras.new('Camera')
    cd.lens = 36
    cd.sensor_width = 36
    cd.sensor_fit = 'HORIZONTAL'
    cd.clip_end = 200
    cam = bpy.data.objects.new('Camera', cd)
    coll.objects.link(cam)
    cam.location = (0.0, -13.2, 5.4)
    look_at(cam, (-0.1, -0.6, -0.5))
    bpy.context.scene.camera = cam
    return cam


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
    area('Key', (-6.5, -7.5, 10), (0, 0, 0), 2200, 5, (1.0, 0.96, 0.95))
    area('Fill', (8, -6, 4.5), (0, 0, 0), 900, 5, (0.8, 0.85, 1.0))
    area('Rim', (1.5, 7.5, 6), (0, 0, 0), 2200, 6, (0.65, 0.55, 1.0))
    area('Top', (0, 0, 9), (0, 0, 0), 700, 4, (1.0, 0.9, 1.0))
    area('Front_Plate', (0, -10, -0.5), (0, -4.9, -1.6), 150, 4,
         (0.85, 0.9, 1.0))
    w = bpy.context.scene.world or bpy.data.worlds.new('World')
    bpy.context.scene.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes.get('Background')
    if bg:
        bg.inputs['Color'].default_value = (0.006, 0.012, 0.04, 1)
        bg.inputs['Strength'].default_value = 1.0


LABELS = [
    # (text, anchor key, x px, y px)  - positions follow the reference image
    ('Surface Receptors', 'receptors', 820, 52),
    ('Phagocytic Cup\nFormation', 'cup', 482, 92),
    ('Nucleus', 'nucleus', 1045, 105),
    ('Cell Membrane', 'membrane', 1258, 158),
    ('Cytoplasm', 'cytoplasm', 1278, 225),
    ('Ribosomes', 'ribosomes', 1297, 293),
    ('Rough Endoplasmic\nReticulum (RER)', 'rer', 1362, 358),
    ('Golgi Apparatus', 'golgi_r', 1350, 437),
    ('Golgi Apparatus', 'golgi_c', 1356, 507),
    ('Mitochondrion', 'mito', 1326, 578),
    ('Exocytosis of Waste', 'exocytosis', 1328, 640),
    ('Extracellular Matrix', 'ecm_right', 1345, 712),
    ('Cytoskeleton', 'cytoskeleton', 1210, 771),
    ('Lysosome', 'lysosome', 830, 780),
    ('ECM', 'ecm_mid', 458, 733),
    ('Extracellular Matrix', 'ecm_left', 178, 655),
    ('Pseudopodia\nEnveloping Bacteria', 'pseudo', 170, 475),
    ('Phagocytic\nEnveloping Bacteria', 'pseudo_env', 170, 370),
    ('Bacteria\nApproaching', 'bacteria', 153, 248),
    ('Phagolysosome\nFusion', 'phagolysosome', 556, 537),
]


def build_labels(coll, M, cam, font):
    scene = bpy.context.scene
    cd = cam.data
    aspect = RES_X / RES_Y
    d = 9.0
    hw = d * (cd.sensor_width / 2) / cd.lens
    hh = hw / aspect
    rot = cam.rotation_euler.to_matrix()
    right, up = rot @ Vector((1, 0, 0)), rot @ Vector((0, 1, 0))
    fwd = rot @ Vector((0, 0, -1))
    size = hh * 2 * 0.029
    pad = size * 0.55
    lines_sp = []
    dots = bmesh.new()
    for i, (txt, key, px, py) in enumerate(LABELS):
        if key not in ANCHORS:
            continue
        sx = px / RES_X * 2 - 1
        sy = 1 - py / RES_Y * 2
        pos = cam.location + fwd * d + right * sx * hw + up * sy * hh
        root = bpy.data.objects.new('Label_%02d' % i, None)
        coll.objects.link(root)
        root.location = pos
        root.rotation_euler = cam.rotation_euler
        t = make_text('Label_%02d_Text' % i, txt, size, coll, M['label_text'],
                      font)
        t.parent = root
        t.location = (0, 0, size * 0.12)
        bpy.context.view_layer.update()
        tw, th = t.dimensions.x, t.dimensions.y
        nlines = txt.count('\n') + 1
        if tw < 1e-4:
            tw = 0.52 * size * max(len(s) for s in txt.split('\n'))
        th = max(th, size * (0.8 + 1.0 * (nlines - 1)))
        panel = rounded_box('Label_%02d_Panel' % i,
                            (tw + 2 * pad, th + 1.5 * pad, size * 0.18),
                            coll, M['label_panel'], min(th + pad, tw) * 0.14,
                            5)
        panel.parent = root
        # leader line from behind the panel to the anchor point
        a = ANCHORS[key]
        start = pos + fwd * 0.06
        lines_sp.append(([tuple(start), tuple(start.lerp(a, 0.5)), tuple(a)],
                         None))
        add_sphere(dots, a, 0.035, 2)
    curve_object('Label_Leaders', lines_sp, coll, M['leader'], bevel=0.009,
                 bevel_res=2)
    bm_object('Label_Dots', dots, coll, [M['leader']])


# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------
def build_materials():
    M = {}
    M['membrane'] = make_mat(
        'Membrane', (0.58, 0.16, 0.86), rough=0.3, sss=0.45,
        sss_rad=(1.0, 0.2, 0.8), sss_scale=0.08, coat=0.5,
        ramp=dict(kind='noise', scale=3.0, detail=3,
                  stops=[(0.35, (0.4, 0.1, 0.78)), (0.55, (0.6, 0.18, 0.86)),
                         (0.72, (0.82, 0.28, 0.82))]),
        bump=dict(kind='noise', scale=9.0, detail=8, strength=0.25,
                  distance=0.04))
    M['rim'] = make_mat(
        'Membrane_Cut', (0.82, 0.38, 0.92), rough=0.35, sss=0.5,
        sss_rad=(1.0, 0.45, 0.9), sss_scale=0.1, coat=0.3,
        bump=dict(kind='noise', scale=25.0, strength=0.2, distance=0.02))
    M['cytoplasm'] = make_mat(
        'Cytoplasm', (0.5, 0.2, 0.62), rough=0.45, sss=0.3,
        sss_rad=(0.9, 0.3, 1.0), sss_scale=0.06, coat=0.25,
        ramp=dict(kind='noise', scale=2.5, detail=5,
                  stops=[(0.3, (0.3, 0.12, 0.5)), (0.5, (0.5, 0.22, 0.6)),
                         (0.72, (0.68, 0.3, 0.6))]),
        bump=dict(kind='voronoi', scale=55.0, strength=0.2, distance=0.01))
    M['nucleus'] = make_mat(
        'Nucleus', (0.5, 0.2, 0.85), rough=0.42, sss=0.35,
        sss_rad=(0.7, 0.3, 1.0), sss_scale=0.06, coat=0.25,
        ramp=dict(kind='noise', scale=6.0, detail=6,
                  stops=[(0.3, (0.32, 0.12, 0.72)), (0.55, (0.52, 0.24, 0.88)),
                         (0.75, (0.7, 0.36, 0.92))]),
        bump=dict(kind='noise', scale=30.0, detail=10, rough=0.7,
                  strength=0.55, distance=0.02))
    M['nucleolus'] = make_mat('Nucleolus', (0.16, 0.08, 0.5), rough=0.18,
                              coat=0.8, sss=0.2,
                              bump=dict(kind='noise', scale=20, strength=0.1))
    M['vesicle'] = make_mat('Vesicle', (0.6, 0.35, 0.95), rough=0.08,
                            trans=0.65, ior=1.35, coat=0.6, sss=0.1)
    M['mito'] = make_mat('Mitochondrion', (1.0, 0.42, 0.08), rough=0.3,
                         sss=0.45, sss_rad=(1.0, 0.4, 0.1), coat=0.5,
                         bump=dict(kind='noise', scale=18, strength=0.15))
    M['mito_rim'] = make_mat('Mitochondrion_Cut', (1.0, 0.62, 0.25),
                             rough=0.35, sss=0.3)
    M['mito_matrix'] = make_mat('Mito_Matrix', (0.85, 0.28, 0.06), rough=0.5,
                                sss=0.3)
    M['cristae'] = make_mat('Cristae', (0.95, 0.12, 0.05), rough=0.3,
                            sss=0.3, coat=0.4)
    M['rer'] = make_mat('Rough_ER', (0.14, 0.26, 0.92), rough=0.28, sss=0.35,
                        sss_rad=(0.3, 0.5, 1.0), coat=0.5,
                        bump=dict(kind='noise', scale=25, strength=0.15))
    M['ribosome'] = make_mat('Ribosome', (0.05, 0.08, 0.45), rough=0.2,
                             coat=0.6)
    M['golgi_o'] = make_mat('Golgi_Orange', (0.98, 0.58, 0.16), rough=0.3,
                            sss=0.45, sss_rad=(1.0, 0.5, 0.15), coat=0.45,
                            bump=dict(kind='noise', scale=30, strength=0.15))
    M['golgi_b'] = make_mat(
        'Golgi_Brown', (0.62, 0.32, 0.2), rough=0.35, sss=0.4,
        sss_rad=(1.0, 0.45, 0.3), coat=0.4,
        ramp=dict(kind='voronoi', scale=60.0,
                  stops=[(0.0, (0.38, 0.16, 0.1)), (0.25, (0.45, 0.2, 0.13)),
                         (0.32, (0.72, 0.4, 0.26)), (1.0, (0.78, 0.46, 0.3))]),
        bump=dict(kind='voronoi', scale=60.0, strength=0.25, distance=0.01))
    M['golgi_ves'] = make_mat('Golgi_Vesicle', (0.95, 0.5, 0.15), rough=0.25,
                              sss=0.4, coat=0.5)
    M['lysosome'] = make_mat('Lysosome', (0.06, 0.15, 0.85), rough=0.12,
                             coat=0.9, sss=0.25, sss_rad=(0.2, 0.4, 1.0),
                             spec=0.7)
    M['phago'] = make_mat('Phagolysosome_Membrane', (0.55, 0.25, 0.85),
                          rough=0.1, trans=0.55, coat=0.6, sss=0.2)
    M['phago_rim'] = make_mat('Phagolysosome_Cut', (0.8, 0.5, 0.95),
                              rough=0.3, sss=0.4)
    M['fringe'] = make_mat('Phagolysosome_Fringe', (0.6, 0.3, 0.22),
                           rough=0.35, sss=0.35, coat=0.3)
    M['debris_g'] = make_mat('Debris_Green', (0.42, 0.85, 0.22), rough=0.35,
                             sss=0.3)
    M['debris_y'] = make_mat('Debris_Yellow', (0.98, 0.82, 0.25), rough=0.35,
                             sss=0.3)
    M['debris_p'] = make_mat('Debris_Pink', (0.98, 0.42, 0.65), rough=0.35,
                             sss=0.3)
    M['debris_b'] = make_mat('Debris_Blue', (0.35, 0.55, 1.0), rough=0.35,
                             sss=0.3)
    M['bact_a'] = make_mat('Bacteria_Green', (0.16, 0.62, 0.04), rough=0.35,
                           sss=0.3, sss_rad=(0.2, 1.0, 0.1), coat=0.5,
                           bump=dict(kind='noise', scale=40, strength=0.25))
    M['bact_b'] = make_mat('Bacteria_LightGreen', (0.32, 0.78, 0.08),
                           rough=0.35, sss=0.3, sss_rad=(0.2, 1.0, 0.1),
                           coat=0.5,
                           bump=dict(kind='noise', scale=40, strength=0.25))
    M['receptor_b'] = make_mat('Receptor_Blue', (0.2, 0.45, 1.0), rough=0.25,
                               coat=0.6, sss=0.2)
    M['receptor_g'] = make_mat('Receptor_Green', (0.25, 0.72, 0.32),
                               rough=0.25, coat=0.6, sss=0.2)
    M['cytoskeleton'] = make_mat('Cytoskeleton', (0.95, 0.35, 0.45),
                                 rough=0.4, emit=(1.0, 0.35, 0.45),
                                 emit_str=0.6)
    M['ecm'] = make_mat('ECM', (0.22, 0.32, 1.0), rough=0.1, trans=0.45,
                        ior=1.33, coat=0.7, sss=0.3, sss_rad=(0.3, 0.4, 1.0),
                        emit=(0.15, 0.25, 1.0), emit_str=0.25)
    M['ecm2'] = make_mat('ECM_Fine', (0.45, 0.35, 1.0), rough=0.15, trans=0.3,
                         coat=0.5, emit=(0.35, 0.25, 1.0), emit_str=0.3)
    M['pedestal'] = make_mat('Pedestal', (0.025, 0.05, 0.22), rough=0.22,
                             metal=0.3, coat=0.7)
    M['glow'] = make_mat('Pedestal_Glow', (0.2, 0.45, 1.0), rough=0.3,
                         emit=(0.25, 0.5, 1.0), emit_str=5.0)
    M['glow_edge'] = make_mat('Plate_Edge', (0.3, 0.5, 1.0), rough=0.2,
                              metal=0.6, emit=(0.2, 0.42, 1.0), emit_str=1.6)
    M['plate'] = make_mat('Plate', (0.03, 0.07, 0.3), rough=0.25, coat=0.8)
    M['title'] = make_mat('Title_Text', (0.95, 0.96, 1.0), rough=0.3,
                          emit=(1, 1, 1), emit_str=0.6)
    M['subtitle'] = make_mat('Subtitle_Text', (0.75, 0.85, 1.0), rough=0.3,
                             emit=(0.75, 0.85, 1.0), emit_str=0.5)
    M['label_panel'] = make_mat('Label_Panel', (0.93, 0.94, 0.98), rough=0.4,
                                emit=(0.93, 0.94, 0.98), emit_str=0.25,
                                coat=0.3)
    M['label_text'] = make_mat('Label_Text', (0.004, 0.01, 0.06), rough=0.6,
                               spec=0.2)
    M['leader'] = make_mat('Leader_Line', (0.95, 0.95, 1.0), rough=0.4,
                           emit=(1, 1, 1), emit_str=1.2)
    M['floor'] = make_mat('Floor', (0.008, 0.016, 0.06), rough=0.5, coat=0.2)

    # backdrop: emissive radial gradient
    m = bpy.data.materials.new('Backdrop')
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    em = nt.nodes.new('ShaderNodeEmission')
    tc = nt.nodes.new('ShaderNodeTexCoord')
    mp = nt.nodes.new('ShaderNodeMapping')
    _set(mp, 'Scale', (1.2, 1.6, 1.0))
    _set(mp, 'Location', (0.0, 0.08, 0.0))
    gr = nt.nodes.new('ShaderNodeTexGradient')
    gr.gradient_type = 'SPHERICAL'
    cr = nt.nodes.new('ShaderNodeValToRGB')
    els = cr.color_ramp.elements
    els[0].position, els[0].color = 0.0, (0.004, 0.008, 0.03, 1)
    els[1].position, els[1].color = 0.9, (0.025, 0.06, 0.22, 1)
    nt.links.new(tc.outputs['Object'], mp.inputs['Vector'])
    nt.links.new(mp.outputs['Vector'], gr.inputs['Vector'])
    nt.links.new(gr.outputs['Fac'], cr.inputs['Fac'])
    nt.links.new(cr.outputs['Color'], em.inputs['Color'])
    em.inputs['Strength'].default_value = 1.0
    nt.links.new(em.outputs['Emission'], out.inputs['Surface'])
    M['backdrop'] = m
    return M


# ---------------------------------------------------------------------------
# Render settings
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
    for vt in ('AgX', 'Filmic'):
        try:
            vs.view_transform = vt
            break
        except Exception:
            pass
    for look in ('AgX - Punchy', 'Punchy', 'AgX - Medium High Contrast',
                 'Medium High Contrast'):
        try:
            vs.look = look
            break
        except Exception:
            pass
    vs.exposure = -0.25


def tilt_cell(colls):
    """Parent the whole cell to one empty and tilt it toward the camera,
    like a model presented on a display stand."""
    root = bpy.data.objects.new('Cell_Root', None)
    colls[0].objects.link(root)
    root.empty_display_type = 'ARROWS'
    root.location = TILT_PIVOT
    inv = Matrix.Translation(-TILT_PIVOT)
    for c in colls:
        for ob in c.objects:
            if ob is not root and ob.parent is None:
                ob.parent = root
                ob.matrix_parent_inverse = inv
    root.rotation_euler = (math.radians(CELL_TILT), 0, 0)
    T = (Matrix.Translation(TILT_PIVOT) @
         Matrix.Rotation(math.radians(CELL_TILT), 4, 'X') @ inv)
    for k in list(ANCHORS):
        if not k.startswith('ecm'):
            ANCHORS[k] = T @ ANCHORS[k]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []

    def arg(name, default=None):
        return argv[argv.index(name) + 1] if name in argv else default

    samples = int(arg('--samples', RENDER_SAMPLES))
    percent = int(arg('--scale', RES_PERCENT))
    labels = SHOW_LABELS and '--no-labels' not in argv

    clear_scene()
    M = build_materials()
    C = {k: new_coll(k) for k in ('Cell', 'Organelles', 'Bacteria', 'ECM',
                                  'Pedestal', 'Labels', 'Lighting')}

    build_cell(C['Cell'], M)
    cup_c, cup_R = build_pseudopodia(C['Cell'], M)
    build_receptors(C['Cell'], M)

    org = C['Organelles']
    build_nucleus(org, M)
    build_vesicle(org, M)
    build_phagolysosome(org, M)
    mitos = [('Mito_1', (-0.35, 1.4), 1.1, 0.24, 12),
             ('Mito_2', (2.0, 1.45), 0.9, 0.21, -14),
             ('Mito_3', (2.55, -0.1), 0.7, 0.18, 82),
             ('Mito_4', (1.75, -1.2), 1.05, 0.23, -28),
             ('Mito_5', (-1.05, -1.25), 1.0, 0.22, 22),
             ('Mito_6', (-1.95, 1.05), 0.7, 0.18, 58)]
    for name, c, L, r, a in mitos:
        build_mitochondrion(org, M, name, c, L, r, a)
    ANCHORS['mito'] = Vector((1.8 + 0.3, -1.12 - 0.1, FLOOR_Z + 0.1))
    _, gmid = build_golgi(org, M, 'Golgi_Central', (0.0, 0.78), 90, 7, 1.05,
                          70, M['golgi_b'], M['golgi_ves'])
    ANCHORS['golgi_c'] = Vector((gmid.x + 0.35, gmid.y - 0.05, FLOOR_Z + 0.1))
    _, gmid = build_golgi(org, M, 'Golgi_Right', (1.95, -0.2), 0, 6, 0.85,
                          75, M['golgi_o'], M['golgi_ves'])
    ANCHORS['golgi_r'] = Vector((gmid.x + 0.25, gmid.y + 0.25, FLOOR_Z + 0.1))
    build_rer(org, M)
    build_lysosomes_and_dots(org, M)
    build_cytoskeleton(org, M)

    build_bacteria(C['Bacteria'], M, cup_c, cup_R)
    tilt_cell([C['Cell'], C['Organelles'], C['Bacteria']])
    build_ecm(C['ECM'], M)

    font_b = load_font(True)
    font_r = load_font(False) or font_b
    build_pedestal(C['Pedestal'], M, font_b, font_r)
    build_environment(C['Lighting'], M)
    cam = build_camera(C['Lighting'])
    build_lights(C['Lighting'])
    if labels:
        build_labels(C['Labels'], M, cam, font_b)

    setup_render(samples, percent)

    save = arg('--save')
    if save:
        try:
            bpy.ops.file.pack_all()
        except Exception:
            pass
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(save))
    out = arg('--render')
    if out:
        bpy.context.scene.render.filepath = os.path.abspath(out)
        bpy.ops.render.render(write_still=True)


if __name__ == '__main__':
    main()
