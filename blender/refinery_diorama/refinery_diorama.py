"""
Oil Refinery Diorama - procedural Blender scene
================================================

Builds a detailed tabletop model of an oil refinery: catalytic cracking
column, hydrotreating column, furnace with striped chimney, heat exchanger,
cooling tower, two spherical tanks, lattice flare stack with flame, water
tank, product storage tanks with spiral stairs, office building, tanker
truck, loading gantry, pipe racks, roads, gravel, grass, trees and labels.

Usage (Blender 4.0 .. 5.x):
    1. Open Blender -> "Scripting" workspace.
    2. Open this file and press "Run Script" (Alt+P).
    3. Press F12 to render (Cycles).

Everything is generated with the data API (no bpy.ops), so it can also run
headless:  blender -b -P refinery_diorama.py -- --render out.png
"""

import bpy
import bmesh
import math
import random
import sys
import os
from mathutils import Vector, Matrix, Euler

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
GRASS_HAIR = True          # particle-hair grass on the green strips
RENDER_SAMPLES = 256       # Cycles samples for F12
RES_X, RES_Y = 1920, 1744  # same aspect as the reference photo
SEED = 7

V = Vector
pi = math.pi
random.seed(SEED)

CAM_LOC = V((-2.9, -17.6, 12.6))
CAM_TARGET = V((0.35, 0.8, 2.45))

BOARD_X, BOARD_Y = 6.9, 5.2      # half extents of the diorama board

# 3D-print mode (set by export_print.py): square board, closed meshes and a
# minimum feature size so railings, ladders and lattices survive printing.
PRINT = False
PRINT_SIZE_MM = 300.0            # outer size of the square board incl. frame
MIN_FEATURE_MM = 0.8             # thinnest wall / rod the printer can make
FRAME_T = 0.16
MIN_T = 0.0                      # MIN_FEATURE_MM in scene units (set in build)


def print_scale():
    """Millimetres per scene unit when printing."""
    return PRINT_SIZE_MM / (2 * (BOARD_X + FRAME_T))


def T(x):
    return max(x, MIN_T)


def linspace(a, b, n):
    if n == 1:
        return [a]
    return [a + (b - a) * i / (n - 1) for i in range(n)]


def arange(a, b, step):
    out = []
    x = a
    while x < b - 1e-9:
        out.append(x)
        x += step
    return out


# ---------------------------------------------------------------------------
# Scene reset & collections
# ---------------------------------------------------------------------------
def reset_scene():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for block in (bpy.data.meshes, bpy.data.curves, bpy.data.materials,
                  bpy.data.lights, bpy.data.cameras, bpy.data.particles):
        for item in list(block):
            block.remove(item)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)


def collection(name):
    sc = bpy.context.scene
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
        sc.collection.children.link(c)
    return c


# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------
MAT = {}


def _sock(node, names):
    if isinstance(names, str):
        names = [names]
    for n in names:
        if n in node.inputs:
            return node.inputs[n]
    return None


def _set(node, names, value):
    s = _sock(node, names)
    if s is not None:
        try:
            s.default_value = value
        except Exception:
            pass


def _ramp(nt, c0, c1, p0=0.0, p1=1.0):
    cr = nt.nodes.new('ShaderNodeValToRGB')
    e = cr.color_ramp.elements
    e[0].position, e[0].color = p0, (*c0, 1.0)
    e[1].position, e[1].color = p1, (*c1, 1.0)
    return cr


def _principled(m):
    m.use_nodes = True
    for n in m.node_tree.nodes:
        if n.type == 'BSDF_PRINCIPLED':
            return n
    b = m.node_tree.nodes.new('ShaderNodeBsdfPrincipled')
    out = next(n for n in m.node_tree.nodes if n.type == 'OUTPUT_MATERIAL')
    m.node_tree.links.new(b.outputs[0], out.inputs['Surface'])
    return b


def mat_pbr(name, col, metal=0.0, rough=0.5, var=0.0, vscale=6.0, rvar=0.0,
            bump=0.0, bscale=60.0, bdist=0.004, spec=0.5, coat=0.0):
    m = bpy.data.materials.new(name)
    b = _principled(m)
    nt = m.node_tree
    L = nt.links
    _set(b, 'Base Color', (*col, 1.0))
    _set(b, 'Metallic', metal)
    _set(b, 'Roughness', rough)
    _set(b, ['Specular IOR Level', 'Specular'], spec)
    if coat:
        _set(b, ['Coat Weight', 'Clearcoat'], coat)
        _set(b, ['Coat Roughness', 'Clearcoat Roughness'], 0.05)
    m.diffuse_color = (*col, 1.0)
    m.metallic = metal
    m.roughness = rough
    if var or rvar or bump:
        tc = nt.nodes.new('ShaderNodeTexCoord')
    if var or rvar:
        nz = nt.nodes.new('ShaderNodeTexNoise')
        _set(nz, 'Scale', vscale)
        _set(nz, 'Detail', 6.0)
        L.new(tc.outputs['Object'], nz.inputs['Vector'])
        if var:
            c0 = tuple(c * (1 - var) for c in col)
            c1 = tuple(min(1.0, c * (1 + var)) for c in col)
            cr = _ramp(nt, c0, c1, 0.3, 0.7)
            L.new(nz.outputs['Fac'], cr.inputs['Fac'])
            L.new(cr.outputs['Color'], b.inputs['Base Color'])
        if rvar:
            r0 = max(0.02, rough - rvar)
            r1 = min(1.0, rough + rvar)
            cr2 = _ramp(nt, (r0,) * 3, (r1,) * 3, 0.25, 0.75)
            L.new(nz.outputs['Fac'], cr2.inputs['Fac'])
            L.new(cr2.outputs['Color'], _sock(b, 'Roughness'))
    if bump:
        nz2 = nt.nodes.new('ShaderNodeTexNoise')
        _set(nz2, 'Scale', bscale)
        _set(nz2, 'Detail', 8.0)
        bp = nt.nodes.new('ShaderNodeBump')
        _set(bp, 'Strength', bump)
        _set(bp, 'Distance', bdist)
        L.new(tc.outputs['Object'], nz2.inputs['Vector'])
        L.new(nz2.outputs['Fac'], bp.inputs['Height'])
        L.new(bp.outputs['Normal'], b.inputs['Normal'])
    MAT[name] = m
    return m


def mat_gravel(name, scale=42.0):
    m = bpy.data.materials.new(name)
    b = _principled(m)
    nt = m.node_tree
    L = nt.links
    _set(b, 'Roughness', 0.88)
    m.diffuse_color = (0.42, 0.42, 0.40, 1)
    tc = nt.nodes.new('ShaderNodeTexCoord')
    vor = nt.nodes.new('ShaderNodeTexVoronoi')
    _set(vor, 'Scale', scale)
    L.new(tc.outputs['Object'], vor.inputs['Vector'])
    col = _ramp(nt, (0.16, 0.16, 0.155), (0.66, 0.65, 0.62))
    col.color_ramp.elements.new(0.5).color = (0.38, 0.37, 0.35, 1)
    L.new(vor.outputs['Color'], col.inputs['Fac'])
    L.new(col.outputs['Color'], b.inputs['Base Color'])
    h = _ramp(nt, (1, 1, 1), (0, 0, 0), 0.0, 0.75)
    L.new(vor.outputs['Distance'], h.inputs['Fac'])
    bp = nt.nodes.new('ShaderNodeBump')
    _set(bp, 'Strength', 0.8)
    _set(bp, 'Distance', 0.012)
    L.new(h.outputs['Color'], bp.inputs['Height'])
    L.new(bp.outputs['Normal'], b.inputs['Normal'])
    MAT[name] = m
    return m


def mat_roof(name, col):
    m = mat_pbr(name, col, rough=0.45, var=0.08, vscale=5)
    nt = m.node_tree
    b = _principled(m)
    tc = next(n for n in nt.nodes if n.type == 'TEX_COORD')
    wave = nt.nodes.new('ShaderNodeTexWave')
    wave.wave_type = 'BANDS'
    try:
        wave.bands_direction = 'Z'
    except Exception:
        pass
    _set(wave, 'Scale', 9.0)
    nt.links.new(tc.outputs['Object'], wave.inputs['Vector'])
    bp = nt.nodes.new('ShaderNodeBump')
    _set(bp, 'Strength', 0.35)
    _set(bp, 'Distance', 0.01)
    nt.links.new(wave.outputs['Color'], bp.inputs['Height'])
    nt.links.new(bp.outputs['Normal'], b.inputs['Normal'])
    return m


def mat_emit(name, col, strength):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    em = nt.nodes.new('ShaderNodeEmission')
    _set(em, 'Color', (*col, 1))
    _set(em, 'Strength', strength)
    nt.links.new(em.outputs[0], out.inputs['Surface'])
    m.diffuse_color = (*col, 1)
    MAT[name] = m
    return m


def mat_flame(name, col, strength):
    """Emission that fades out at grazing angles -> soft flame edges."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    em = nt.nodes.new('ShaderNodeEmission')
    _set(em, 'Color', (*col, 1))
    _set(em, 'Strength', strength)
    tr = nt.nodes.new('ShaderNodeBsdfTransparent')
    lw = nt.nodes.new('ShaderNodeLayerWeight')
    _set(lw, 'Blend', 0.55)
    mix = nt.nodes.new('ShaderNodeMixShader')
    nt.links.new(lw.outputs['Facing'], mix.inputs['Fac'])
    nt.links.new(em.outputs[0], mix.inputs[1])
    nt.links.new(tr.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs['Surface'])
    for attr, val in (('blend_method', 'BLEND'), ('surface_render_method', 'BLENDED')):
        try:
            setattr(m, attr, val)
        except Exception:
            pass
    m.diffuse_color = (*col, 1)
    MAT[name] = m
    return m


def build_materials():
    mat_pbr('steel', (0.70, 0.71, 0.73), metal=1.0, rough=0.24, var=0.025, vscale=3, rvar=0.05)
    mat_pbr('steel_bright', (0.78, 0.79, 0.80), metal=1.0, rough=0.18, var=0.04, vscale=2, rvar=0.06)
    mat_pbr('steel_dark', (0.33, 0.34, 0.35), metal=0.9, rough=0.45, var=0.1, vscale=6)
    mat_pbr('furnace', (0.55, 0.56, 0.57), metal=0.85, rough=0.42, var=0.12, vscale=4, rvar=0.1)
    mat_pbr('galv', (0.58, 0.59, 0.60), metal=0.8, rough=0.40, var=0.1, vscale=8, rvar=0.12)
    mat_pbr('galv_dark', (0.36, 0.37, 0.38), metal=0.7, rough=0.5, var=0.1, vscale=8)
    mat_pbr('grating', (0.42, 0.43, 0.44), metal=0.8, rough=0.55, bump=0.4, bscale=160)
    mat_pbr('rail_yellow', (0.88, 0.52, 0.0), rough=0.35, var=0.04)
    mat_pbr('paint_white', (0.86, 0.86, 0.84), rough=0.32, var=0.03, vscale=3, bump=0.05, bscale=40)
    mat_pbr('paint_grey', (0.42, 0.43, 0.44), rough=0.45)
    mat_pbr('paint_green', (0.04, 0.30, 0.20), rough=0.35, var=0.08, vscale=4)
    mat_pbr('paint_green_dk', (0.03, 0.22, 0.15), rough=0.40)
    mat_pbr('paint_red', (0.72, 0.05, 0.04), rough=0.35)
    mat_pbr('paint_blue', (0.07, 0.24, 0.62), rough=0.40)
    mat_roof('roof_blue', (0.025, 0.14, 0.55))
    mat_pbr('wall', (0.80, 0.80, 0.78), rough=0.75, var=0.04, vscale=6, bump=0.08, bscale=90)
    mat_pbr('wall_trim', (0.90, 0.90, 0.88), rough=0.6)
    mat_pbr('glass', (0.06, 0.09, 0.12), rough=0.05, spec=0.9)
    mat_pbr('concrete', (0.55, 0.55, 0.53), rough=0.9, var=0.12, vscale=4, bump=0.2, bscale=90)
    mat_pbr('concrete_dk', (0.30, 0.30, 0.30), rough=0.9, var=0.1, vscale=5)
    mat_gravel('gravel')
    mat_pbr('asphalt', (0.10, 0.10, 0.11), rough=0.85, var=0.25, vscale=3, bump=0.25, bscale=220)
    mat_pbr('road_white', (0.85, 0.85, 0.82), rough=0.6)
    mat_pbr('road_yellow', (0.85, 0.62, 0.05), rough=0.6)
    mat_pbr('grass', (0.13, 0.30, 0.06), rough=0.95, var=0.35, vscale=9, bump=0.3, bscale=120)
    mat_pbr('grass_blade', (0.17, 0.36, 0.07), rough=0.7, var=0.4, vscale=12)
    mat_pbr('foliage', (0.035, 0.15, 0.055), rough=0.85, var=0.35, vscale=14, bump=0.6, bscale=70)
    mat_pbr('trunk', (0.20, 0.12, 0.06), rough=0.9)
    mat_pbr('frame', (0.025, 0.025, 0.03), rough=0.45, var=0.1, vscale=2)
    mat_pbr('table', (0.11, 0.11, 0.115), rough=0.55, var=0.15, vscale=2)
    mat_pbr('backdrop', (0.55, 0.54, 0.52), rough=0.9)
    mat_pbr('sign_white', (0.92, 0.92, 0.90), rough=0.6)
    mat_pbr('sign_text', (0.015, 0.015, 0.015), rough=0.5)
    mat_pbr('rubber', (0.025, 0.025, 0.025), rough=0.8, bump=0.1, bscale=200)
    mat_pbr('truck_yellow', (0.92, 0.58, 0.02), rough=0.25, coat=0.6)
    mat_pbr('chrome', (0.9, 0.9, 0.9), metal=1.0, rough=0.08)
    mat_pbr('valve_red', (0.65, 0.04, 0.03), rough=0.4)
    mat_emit('lamp', (1.0, 0.85, 0.6), 6.0)
    mat_emit('tail_light', (1.0, 0.05, 0.02), 3.0)
    mat_emit('beacon', (1.0, 0.03, 0.02), 8.0)
    mat_flame('flame_core', (1.0, 0.75, 0.30), 40.0)
    mat_flame('flame_outer', (1.0, 0.35, 0.05), 18.0)


# ---------------------------------------------------------------------------
# Mesh builder: accumulates primitives into a single bmesh per object
# ---------------------------------------------------------------------------
class MB:
    def __init__(self, name):
        self.name = name
        self.bm = bmesh.new()
        self.mats = []

    def _mi(self, mat):
        if mat not in self.mats:
            self.mats.append(mat)
        return self.mats.index(mat)

    @staticmethod
    def _faces_of(verts):
        fs = set()
        for v in verts:
            fs.update(v.link_faces)
        return fs

    def _flat(self, verts, mat):
        i = self._mi(mat)
        for f in self._faces_of(verts):
            f.material_index = i
            f.smooth = False

    # -- primitives ---------------------------------------------------------
    def cyl(self, p1, p2, r, mat, segs=24, r2=None, caps=True):
        p1, p2 = V(p1), V(p2)
        d = p2 - p1
        L = d.length
        if L < 1e-6:
            return
        r = max(r, MIN_T / 2)
        if r2 is not None:
            r2 = max(r2, MIN_T / 2)
        caps = caps or PRINT
        M = Matrix.Translation((p1 + p2) / 2) @ d.to_track_quat('Z', 'Y').to_matrix().to_4x4()
        res = bmesh.ops.create_cone(self.bm, cap_ends=caps, cap_tris=False, segments=segs,
                                    radius1=r, radius2=r if r2 is None else r2, depth=L, matrix=M)
        i = self._mi(mat)
        for f in self._faces_of(res['verts']):
            f.material_index = i
            f.smooth = len(f.verts) == 4
            if not f.smooth:
                for e in f.edges:
                    e.smooth = False

    def box(self, c, s, mat, rot=(0, 0, 0), R=None):
        R3 = R if R is not None else Euler(rot).to_matrix()
        s = [T(v) for v in s]
        M = Matrix.Translation(V(c)) @ R3.to_4x4() @ Matrix.Diagonal((s[0], s[1], s[2], 1.0))
        res = bmesh.ops.create_cube(self.bm, size=1.0, matrix=M)
        self._flat(res['verts'], mat)

    def beam(self, p1, p2, w, h, mat):
        p1, p2 = V(p1), V(p2)
        d = p2 - p1
        L = d.length
        if L < 1e-6:
            return
        w, h = T(w), T(h)
        M = (Matrix.Translation((p1 + p2) / 2) @ d.to_track_quat('Z', 'Y').to_matrix().to_4x4()
             @ Matrix.Diagonal((w, h, L, 1.0)))
        res = bmesh.ops.create_cube(self.bm, size=1.0, matrix=M)
        self._flat(res['verts'], mat)

    def sphere(self, c, r, mat, segs=32, rings=16, scale=(1, 1, 1)):
        M = Matrix.Translation(V(c)) @ Matrix.Diagonal((*scale, 1.0))
        res = bmesh.ops.create_uvsphere(self.bm, u_segments=segs, v_segments=rings, radius=r, matrix=M)
        i = self._mi(mat)
        for f in self._faces_of(res['verts']):
            f.material_index = i
            f.smooth = True

    def lathe(self, prof, mat, segs=32, M=None, close_bot=False, close_top=False,
              closed=False, rib=None, sharp_deg=35.0, a0=0.0, a1=None):
        """Surface of revolution of an (r, z) profile around local Z.
        a0/a1 allow a partial sweep (open arc)."""
        M = M if M is not None else Matrix.Identity(4)
        bm = self.bm
        full = a1 is None
        n = segs if full else segs + 1
        span = 2 * pi if full else (a1 - a0)
        rings = []
        for (r, z) in prof:
            if r < 1e-7:
                rings.append([bm.verts.new(M @ V((0, 0, z)))])
                continue
            ring = []
            for k in range(n):
                a = a0 + span * k / segs
                rr = r + (rib[1] * math.cos(rib[0] * a) if rib else 0.0)
                ring.append(bm.verts.new(M @ V((rr * math.cos(a), rr * math.sin(a), z))))
            rings.append(ring)
        i = self._mi(mat)
        pairs = list(zip(rings, rings[1:]))
        if closed:
            pairs.append((rings[-1], rings[0]))
        kmax = segs if full else segs
        for a, b in pairs:
            if len(a) == 1 and len(b) == 1:
                continue
            for k in range(kmax):
                k1 = (k + 1) % n
                if len(a) == 1:
                    vs = (a[0], b[k1], b[k])
                elif len(b) == 1:
                    vs = (a[k], a[k1], b[0])
                else:
                    vs = (a[k], a[k1], b[k1], b[k])
                try:
                    f = bm.faces.new(vs)
                    f.material_index = i
                    f.smooth = True
                except ValueError:
                    pass
        if PRINT and not full and closed:
            # close the open ends of a partial sweep (e.g. a pipe bend)
            for k in (0, n - 1):
                f = bm.faces.new([ring[k] for ring in rings if len(ring) > 1])
                f.material_index = i
        if PRINT and not closed:
            close_bot = close_bot or len(rings[0]) > 1
            close_top = close_top or len(rings[-1]) > 1
        # sharp creases at profile corners
        np_ = len(prof)
        for j in range(np_):
            if not closed and (j == 0 or j == np_ - 1):
                continue
            p0, p1, p2 = V(prof[j - 1]), V(prof[j]), V(prof[(j + 1) % np_])
            d1, d2 = p1 - p0, p2 - p1
            if d1.length < 1e-9 or d2.length < 1e-9:
                continue
            if math.degrees(d1.angle(d2)) > sharp_deg and len(rings[j]) > 1:
                ring = rings[j]
                for k in range(kmax):
                    e = bm.edges.get((ring[k], ring[(k + 1) % n]))
                    if e:
                        e.smooth = False
        for ring, top in ((rings[0], False), (rings[-1], True)):
            if len(ring) < 3 or not full:
                continue
            if (top and close_top) or (not top and close_bot):
                f = bm.faces.new(ring if top else list(reversed(ring)))
                f.material_index = i
                f.smooth = False
                for e in f.edges:
                    e.smooth = False

    def torus(self, R, r, mat, M=None, segs=48, tsegs=8, a0=0.0, a1=None):
        r = max(r, MIN_T / 2)
        prof = [(R + r * math.cos(t), r * math.sin(t)) for t in
                [2 * pi * k / tsegs for k in range(tsegs)]]
        self.lathe(prof, mat, segs=segs, M=M, closed=True, sharp_deg=180, a0=a0, a1=a1)

    def sweep(self, pts, r, mat, segs=8, closed=False, caps=True):
        """Tube of radius r along a polyline (parallel transport frames)."""
        pts = [V(p) for p in pts]
        n = len(pts)
        if n < 2:
            return
        r = max(r, MIN_T / 2)
        T = []
        for k in range(n):
            if closed:
                a, b = pts[(k - 1) % n], pts[(k + 1) % n]
            else:
                a, b = pts[max(k - 1, 0)], pts[min(k + 1, n - 1)]
            t = b - a
            t.normalize()
            T.append(t)
        up = V((0, 0, 1)) if abs(T[0].z) < 0.9 else V((1, 0, 0))
        N = T[0].cross(up).normalized()
        rings = []
        angs = [2 * pi * k / segs for k in range(segs)]
        for k in range(n):
            if k > 0:
                ax = T[k - 1].cross(T[k])
                if ax.length > 1e-8:
                    N = Matrix.Rotation(T[k - 1].angle(T[k]), 3, ax.normalized()) @ N
            B = T[k].cross(N)
            rings.append([self.bm.verts.new(pts[k] + r * (math.cos(a) * N + math.sin(a) * B))
                          for a in angs])
        i = self._mi(mat)
        pairs = list(zip(rings, rings[1:]))
        if closed:
            pairs.append((rings[-1], rings[0]))
        for a, b in pairs:
            for k in range(segs):
                k1 = (k + 1) % segs
                f = self.bm.faces.new((a[k], a[k1], b[k1], b[k]))
                f.material_index = i
                f.smooth = True
        if caps and not closed:
            for ring, rev in ((rings[0], True), (rings[-1], False)):
                f = self.bm.faces.new(list(reversed(ring)) if rev else ring)
                f.material_index = i
                f.smooth = False
                for e in f.edges:
                    e.smooth = False

    def frustum(self, c, sb, st, z0, z1, mat):
        cx, cy = c
        sg = ((-1, -1), (1, -1), (1, 1), (-1, 1))
        vb = [self.bm.verts.new((cx + sx * sb[0] / 2, cy + sy * sb[1] / 2, z0)) for sx, sy in sg]
        vt = [self.bm.verts.new((cx + sx * st[0] / 2, cy + sy * st[1] / 2, z1)) for sx, sy in sg]
        fs = [self.bm.faces.new(list(reversed(vb))), self.bm.faces.new(vt)]
        for k in range(4):
            k1 = (k + 1) % 4
            fs.append(self.bm.faces.new((vb[k], vb[k1], vt[k1], vt[k])))
        i = self._mi(mat)
        for f in fs:
            f.material_index = i
            f.smooth = False

    def hip_roof(self, c, W, D, z0, h, mat):
        cx, cy = c
        Lr = max(0.0, W - D)
        vb = [self.bm.verts.new((cx + sx * W / 2, cy + sy * D / 2, z0))
              for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        r0 = self.bm.verts.new((cx - Lr / 2, cy, z0 + h))
        r1 = self.bm.verts.new((cx + Lr / 2, cy, z0 + h))
        fs = [self.bm.faces.new((vb[0], vb[1], r1, r0)),
              self.bm.faces.new((vb[1], vb[2], r1)),
              self.bm.faces.new((vb[2], vb[3], r0, r1)),
              self.bm.faces.new((vb[3], vb[0], r0)),
              self.bm.faces.new(list(reversed(vb)))]
        i = self._mi(mat)
        for f in fs:
            f.material_index = i
            f.smooth = False

    def _separate_touching_shells(self):
        """Grow each closed shell very slightly about its centre, by a slightly
        different amount, so neighbours that share a face or edge overlap
        instead of touching exactly (which slicers flag as non-manifold)."""
        rnd = random.Random(len(self.bm.verts))
        seen = set()
        for v0 in self.bm.verts:
            if v0 in seen:
                continue
            shell, stack = [], [v0]
            seen.add(v0)
            while stack:
                v = stack.pop()
                shell.append(v)
                for e in v.link_edges:
                    w = e.other_vert(v)
                    if w not in seen:
                        seen.add(w)
                        stack.append(w)
            c = sum((v.co for v in shell), V()) / len(shell)
            k = 1.0 + rnd.uniform(3e-4, 9e-4)
            for v in shell:
                v.co = c + (v.co - c) * k

    def finish(self, coll, bevel=0.0, bevel_segs=2):
        if PRINT:
            # every primitive is a closed shell: make all normals point outwards
            bmesh.ops.recalc_face_normals(self.bm, faces=self.bm.faces[:])
            self._separate_touching_shells()
            bevel = 0.0
        me = bpy.data.meshes.new(self.name)
        self.bm.to_mesh(me)
        self.bm.free()
        for m in self.mats:
            me.materials.append(MAT[m])
        if hasattr(me, 'use_auto_smooth'):          # Blender < 4.1
            me.use_auto_smooth = True
            me.auto_smooth_angle = pi
        ob = bpy.data.objects.new(self.name, me)
        coll.objects.link(ob)
        if bevel > 0:
            mod = ob.modifiers.new('Bevel', 'BEVEL')
            mod.width = bevel
            mod.segments = bevel_segs
            mod.limit_method = 'ANGLE'
            mod.angle_limit = math.radians(40)
            try:
                mod.harden_normals = True
            except Exception:
                pass
        return ob


# ---------------------------------------------------------------------------
# Shared detail helpers (all in world coordinates)
# ---------------------------------------------------------------------------
def circle_pts(c, r, z, n=48, a0=0.0, a1=2 * pi, closed=True):
    cnt = n if closed else n + 1
    return [V((c[0] + r * math.cos(a0 + (a1 - a0) * k / n),
               c[1] + r * math.sin(a0 + (a1 - a0) * k / n), z)) for k in range(cnt)]


def ladder(mb, foot, nrm, z0, z1, cage=True, mat='rail_yellow'):
    """Fixed ladder: foot = (x, y) at wall, nrm = outward (x, y) normal."""
    n = V((nrm[0], nrm[1], 0)).normalized()
    t = V((-n.y, n.x, 0))
    c = V((foot[0], foot[1], 0))
    for s in (-1, 1):
        p = c + t * s * 0.065
        mb.cyl((p.x, p.y, z0), (p.x, p.y, z1), 0.0075, mat, segs=6)
    for z in arange(z0 + 0.08, z1 - 0.02, max(0.07, 2.6 * MIN_T)):
        mb.cyl(c - t * 0.065 + V((0, 0, z)), c + t * 0.065 + V((0, 0, z)), 0.0045, mat, segs=5, caps=False)
    if cage and z1 - z0 > 0.8:
        cc = c + n * 0.11
        hoops = arange(z0 + 0.55, z1 + 0.01, 0.2)
        for z in hoops:
            pts = [cc + 0.115 * (math.cos(a) * n + math.sin(a) * t) + V((0, 0, z))
                   for a in linspace(-pi * 0.55, pi * 0.55, 12)]
            mb.sweep(pts, 0.005, mat, segs=5)
        if hoops:
            for a in linspace(-pi * 0.45, pi * 0.45, 5):
                p = cc + 0.115 * (math.cos(a) * n + math.sin(a) * t)
                mb.cyl((p.x, p.y, hoops[0]), (p.x, p.y, hoops[-1]), 0.004, mat, segs=4)


def railing(mb, pts, h=0.22, closed=True, spacing=0.28, mat='rail_yellow', toe=True):
    pts = [V(p) for p in pts]
    up = V((0, 0, 1))
    mb.sweep([p + up * h for p in pts], 0.008, mat, segs=6, closed=closed)
    mb.sweep([p + up * h * 0.5 for p in pts], 0.006, mat, segs=6, closed=closed)
    if toe and not PRINT:
        mb.sweep([p + up * 0.02 for p in pts], 0.004, mat, segs=4, closed=closed)
    segs = list(zip(pts, pts[1:] + ([pts[0]] if closed else [])))
    acc = spacing
    for a, b in segs:
        L = (b - a).length
        s = 0.0
        while s <= L:
            if acc >= spacing:
                p = a + (b - a) * (s / L if L > 0 else 0)
                mb.cyl(p, p + up * h, 0.0075, mat, segs=6)
                acc = 0.0
            step = min(spacing - acc, L - s) if L - s > 1e-6 else spacing
            if step <= 1e-6:
                step = spacing
            s += step
            acc += step


def flange(mb, p, d, r, mat='steel', thick=0.022, bolts=0):
    d = V(d).normalized()
    thick = T(thick)
    p = V(p)
    mb.cyl(p - d * thick / 2, p + d * thick / 2, r, mat, segs=24)
    if bolts:
        q = d.to_track_quat('Z', 'Y').to_matrix()
        for k in range(bolts):
            a = 2 * pi * k / bolts
            o = q @ V((math.cos(a) * r * 0.82, math.sin(a) * r * 0.82, 0))
            mb.cyl(p + o - d * thick * 0.9, p + o + d * thick * 0.9, r * 0.06, 'steel_dark', segs=6)


def nozzle(mb, p, d, r, length, mat='steel', bolts=8):
    p, d = V(p), V(d).normalized()
    e = p + d * length
    mb.cyl(p, e, r, mat, segs=20)
    flange(mb, e - d * 0.012, d, r * 1.7, mat, bolts=bolts)
    return e


def manhole(mb, p, d, r=0.09):
    p, d = V(p), V(d).normalized()
    e = p + d * 0.12
    mb.cyl(p, e, r, 'steel', segs=24)
    flange(mb, e, d, r * 1.45, 'steel', thick=0.03, bolts=14)
    # davit hinge
    mb.cyl(e + V((0, 0, r * 1.45)), e + V((0, 0, r * 1.45 + 0.05)), 0.008, 'steel_dark', segs=6)


def handwheel(mb, p, r=0.05, axis=(0, 0, 1)):
    ax = V(axis).normalized()
    M = Matrix.Translation(V(p)) @ ax.to_track_quat('Z', 'Y').to_matrix().to_4x4()
    mb.torus(r, r * 0.12, 'valve_red', M=M, segs=20, tsegs=6)
    q = ax.to_track_quat('Z', 'Y').to_matrix()
    for k in range(3):
        a = 2 * pi * k / 3
        mb.cyl(V(p), V(p) + q @ V((math.cos(a) * r, math.sin(a) * r, 0)), r * 0.08, 'valve_red', segs=5)


def gate_valve(mb, p, d, r):
    p, d = V(p), V(d).normalized()
    flange(mb, p - d * r * 1.4, d, r * 1.7)
    flange(mb, p + d * r * 1.4, d, r * 1.7)
    mb.cyl(p - d * r * 1.3, p + d * r * 1.3, r * 1.25, 'valve_red', segs=16)
    up = V((0, 0, 1)) if abs(d.z) < 0.9 else V((1, 0, 0))
    mb.cyl(p, p + up * r * 3.2, r * 0.7, 'valve_red', segs=12)
    mb.cyl(p + up * r * 3.2, p + up * r * 4.6, r * 0.15, 'steel', segs=6)
    handwheel(mb, p + up * r * 4.6, r=r * 1.5, axis=up)


# ---------------------------------------------------------------------------
# Pipes (curve objects with round fillets)
# ---------------------------------------------------------------------------
PIPE_COLL = None
FITTINGS = None   # MB for flanges, valves & supports of all pipes


def rounded_path(pts, rad, steps=6):
    pts = [V(p) for p in pts]
    out = [pts[0]]
    for k in range(1, len(pts) - 1):
        p0, p1, p2 = pts[k - 1], pts[k], pts[k + 1]
        d1, d2 = p1 - p0, p2 - p1
        l1, l2 = d1.length, d2.length
        if l1 < 1e-6 or l2 < 1e-6:
            continue
        d1.normalize()
        d2.normalize()
        ang = d1.angle(d2)
        if ang < 1e-3:
            out.append(p1)
            continue
        t = min(rad * math.tan(ang / 2), l1 * 0.5, l2 * 0.5)
        a, b = p1 - d1 * t, p1 + d2 * t
        for s in range(steps + 1):
            u = s / steps
            out.append((1 - u) ** 2 * a + 2 * (1 - u) * u * p1 + u * u * b)
    out.append(pts[-1])
    return out


def pipe(name, pts, r=0.035, mat='steel', flanges=True, supports=True, valve=False):
    path = rounded_path(pts, r * 3.0)
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    cu.bevel_depth = r
    cu.bevel_resolution = 3
    cu.use_fill_caps = True
    try:
        cu.twist_mode = 'MINIMUM'
    except Exception:
        pass
    sp = cu.splines.new('POLY')
    sp.points.add(len(path) - 1)
    for p, q in zip(sp.points, path):
        p.co = (q.x, q.y, q.z, 1.0)
    sp.use_smooth = True
    ob = bpy.data.objects.new(name, cu)
    ob.data.materials.append(MAT[mat])
    PIPE_COLL.objects.link(ob)
    P = [V(p) for p in pts]
    FIT = MB(name + '_Fittings') if PRINT else FITTINGS
    if flanges:
        flange(FIT, P[0] + (P[1] - P[0]).normalized() * 0.012, P[1] - P[0], r * 1.65)
        flange(FIT, P[-1] - (P[-1] - P[-2]).normalized() * 0.012, P[-1] - P[-2], r * 1.65)
    if supports:
        for a, b in zip(P, P[1:]):
            if abs(a.z - b.z) > 1e-4 or a.z < 0.14 or a.z > 1.35:
                continue
            L = (b - a).length
            if L < 0.7:
                continue
            for s in arange(0.35, L - 0.2, 0.9):
                p = a + (b - a) * (s / L)
                FIT.box((p.x, p.y, (p.z - r) / 2), (0.035, 0.035, p.z - r), 'steel_dark')
                FIT.box((p.x, p.y, p.z - r - 0.008), (0.09, 0.09, 0.016), 'steel_dark')
                FIT.box((p.x, p.y, 0.006), (0.09, 0.09, 0.012), 'concrete')
    if valve:
        best = max(zip(P, P[1:]), key=lambda s: (s[1] - s[0]).length)
        mid = (best[0] + best[1]) / 2
        gate_valve(FIT, mid, best[1] - best[0], r)
    if FIT is not FITTINGS and FIT.bm.verts:
        FIT.finish(PIPE_COLL)
    return ob


# ---------------------------------------------------------------------------
# Board, ground, roads, grass
# ---------------------------------------------------------------------------
GRASS_PATCHES = []   # (x0, y0, x1, y1)


def build_base(coll):
    mb = MB('Board_Gravel')
    mb.box((0, 0, -0.17), (2 * BOARD_X, 2 * BOARD_Y, 0.34), 'gravel')
    mb.finish(coll)

    fr = MB('Board_Frame')
    t = FRAME_T
    X, Y = BOARD_X + t / 2, BOARD_Y + t / 2
    fr.box((0, -Y, -0.17), (2 * BOARD_X + 2 * t, t, 0.42), 'frame')
    fr.box((0, Y, -0.17), (2 * BOARD_X + 2 * t, t, 0.42), 'frame')
    fr.box((-X, 0, -0.17), (t, 2 * BOARD_Y, 0.42), 'frame')
    fr.box((X, 0, -0.17), (t, 2 * BOARD_Y, 0.42), 'frame')
    fr.finish(coll, bevel=0.025, bevel_segs=3)

    if PRINT:
        return
    tb = MB('Table')
    tb.box((0, 4, -0.43), (60, 40, 0.1), 'table')
    tb.box((0, 32, 4), (80, 0.2, 20), 'backdrop')
    # blurred lab benches in the background (out of focus props)
    tb.box((-2, 18, 0.1), (14, 2.5, 0.12), 'frame')
    tb.box((-2, 18, -0.2), (13.6, 2.3, 0.5), 'paint_grey')
    tb.box((-9, 19, 1.4), (2.5, 1.6, 2.8), 'wall_trim')
    tb.box((6, 19, 0.6), (1.2, 1.0, 0.9), 'paint_blue')
    tb.box((3, 18.5, 0.45), (1.0, 0.8, 0.6), 'paint_grey')
    tb.finish(coll)


def build_roads(coll):
    mb = MB('Roads')
    z = 0.012
    roads = [(0.85, -BOARD_Y, 2.35, -0.85),   # main 2-lane road
             (2.62, -BOARD_Y, 3.48, 1.45),     # service road
             (2.35, -1.75, 2.62, -0.85)]       # junction
    for x0, y0, x1, y1 in roads:
        mb.box(((x0 + x1) / 2, (y0 + y1) / 2, z / 2), (x1 - x0, y1 - y0, z), 'asphalt')
    # curb strip along the median
    mb.box((2.485, (-BOARD_Y - 1.75) / 2, 0.02), (0.25, -1.75 + BOARD_Y, 0.04), 'concrete')
    # yellow edge lines
    lz = z + 0.002
    for x, y0, y1 in ((0.9, -BOARD_Y, -0.9), (2.3, -BOARD_Y, -1.8), (2.67, -BOARD_Y, -1.8),
                      (3.43, -BOARD_Y, 1.4), (2.67, -0.8, 1.4)):
        mb.box((x, (y0 + y1) / 2, lz), (0.03, y1 - y0, 0.003), 'road_yellow')
    mb.box((1.6, -0.9, lz), (1.4, 0.03, 0.003), 'road_yellow')
    if PRINT:
        mb.finish(coll)
        return
    # dashed white centre line
    for y in arange(-BOARD_Y + 0.15, -1.1, 0.42):
        mb.box((1.6, y + 0.12, lz), (0.035, 0.24, 0.003), 'road_white')
    for y in arange(-BOARD_Y + 0.15, 1.2, 0.42):
        mb.box((3.05, y + 0.12, lz), (0.03, 0.2, 0.003), 'road_white')
    # turn arrows painted on the road
    for (ax, ay, rot) in ((1.22, -4.5, 0.0), (1.98, -1.4, pi)):
        R = Euler((0, 0, rot)).to_matrix()
        mb.box(V((ax, ay, lz)) + R @ V((0, -0.06, 0)), (0.04, 0.3, 0.003), 'road_white', R=R)
        mb.box(V((ax, ay, lz)) + R @ V((0.06, 0.1, 0)), (0.16, 0.04, 0.003), 'road_white', R=R)
        mb.box(V((ax, ay, lz)) + R @ V((0.13, 0.1, 0)), (0.07, 0.07, 0.003), 'road_white',
               R=R @ Euler((0, 0, pi / 4)).to_matrix())
    # stop line / loading bay markings
    mb.box((1.6, -1.95, lz), (1.4, 0.05, 0.003), 'road_white')
    for y in arange(-3.9, -2.0, 0.25):
        mb.box((2.2, y, lz), (0.18, 0.04, 0.003), 'road_yellow', rot=(0, 0, 0.6))
    mb.finish(coll)


def build_grass(coll):
    patches = [(-BOARD_X, -BOARD_Y, 0.55, -3.95),     # front left
               (3.8, -BOARD_Y, BOARD_X, -3.55),        # front right
               (6.2, -3.55, BOARD_X, 1.1),             # right strip
               (-BOARD_X, -3.3, -5.75, 0.6),           # left strip
               (-2.55, -3.45, 0.45, -2.55)]            # middle strip
    if BOARD_Y > 5.8:                                   # square (print) board: back strip
        patches.append((-BOARD_X, 5.45, BOARD_X, BOARD_Y))
    for i, (x0, y0, x1, y1) in enumerate(patches):
        GRASS_PATCHES.append((x0, y0, x1, y1))
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        curb = MB('Curb_%d' % i)
        curb.box((cx, cy, 0.018), (x1 - x0, y1 - y0, 0.036), 'concrete')
        curb.finish(coll, bevel=0.008)
        mb = MB('Grass_%d' % i)
        inset = 0.04
        gx0 = x0 + (inset if x0 > -BOARD_X + 0.01 else 0)
        gx1 = x1 - (inset if x1 < BOARD_X - 0.01 else 0)
        gy0 = y0 + (inset if y0 > -BOARD_Y + 0.01 else 0)
        gy1 = y1 - (inset if y1 < BOARD_Y - 0.01 else 0)
        mb.box(((gx0 + gx1) / 2, (gy0 + gy1) / 2, 0.025), (gx1 - gx0, gy1 - gy0, 0.05), 'grass')
        mb.mats.append('grass_blade')
        ob = mb.finish(coll, bevel=0.01)
        if GRASS_HAIR:
            add_grass_hair(ob, (gx1 - gx0) * (gy1 - gy0))


def _try(obj, attr, val):
    try:
        setattr(obj, attr, val)
    except Exception:
        pass


def add_grass_hair(ob, area):
    try:
        ob.modifiers.new('GrassHair', 'PARTICLE_SYSTEM')
        s = ob.particle_systems[-1].settings
    except Exception:
        return
    s.type = 'HAIR'
    _try(s, 'count', int(area * 700))
    _try(s, 'emit_from', 'FACE')
    _try(s, 'use_advanced_hair', True)
    _try(s, 'hair_length', 0.045)       # (sets normal_factor internally)
    _try(s, 'factor_random', 0.012)
    _try(s, 'length_random', 0.5)
    _try(s, 'child_type', 'INTERPOLATED')
    _try(s, 'child_nbr', 3)
    _try(s, 'rendered_child_count', 12)
    _try(s, 'child_length', 1.0)
    _try(s, 'child_length_threshold', 0.4)
    _try(s, 'roughness_1', 0.01)
    _try(s, 'roughness_endpoint', 0.012)
    _try(s, 'root_radius', 0.6)
    _try(s, 'tip_radius', 0.0)
    _try(s, 'radius_scale', 0.004)
    _try(s, 'material', 2)
    _try(s, 'display_percentage', 15)
    _try(s, 'render_type', 'PATH')


def pad(mb, c, s, z=0.04):
    mb.box((c[0], c[1], z / 2), (s[0], s[1], z), 'concrete')


# ---------------------------------------------------------------------------
# Process units
# ---------------------------------------------------------------------------
def column(name, cx, cy, r, H, plats, rt=None, zt=None, head=0.55, nozzles=(), coll=None):
    mb = MB(name)
    mb.cyl((cx, cy, 0), (cx, cy, 0.1), r + 0.42, 'concrete', segs=8)
    for k in range(12):
        a = 2 * pi * k / 12
        p = V((cx + math.cos(a) * (r + 0.05), cy + math.sin(a) * (r + 0.05), 0.1))
        mb.cyl(p, p + V((0, 0, 0.05)), 0.012, 'steel_dark', segs=6)
    rt = rt or r

    def rad_at(z):
        if zt is None or z <= zt:
            return r
        if z >= zt + 0.45:
            return rt
        return r + (rt - r) * (z - zt) / 0.45

    prof = [(0, 0.1), (r * 1.1, 0.1), (r * 1.1, 0.17), (r * 1.02, 0.7), (r, 0.72)]
    if zt is not None:
        prof += [(r, zt), (rt, zt + 0.45)]
    prof += [(rt, H)]
    prof += [(rt * math.cos(a), H + head * rt * math.sin(a)) for a in linspace(0.2, 1.35, 6)]
    prof += [(0, H + head * rt)]
    mb.lathe(prof, 'steel', segs=56, M=Matrix.Translation((cx, cy, 0)))
    # skirt base ring + access opening
    mb.torus(r * 1.1 + 0.01, 0.02, 'steel_dark', M=Matrix.Translation((cx, cy, 0.17)))
    mb.box((cx, cy - r * 1.05, 0.38), (0.22, 0.06, 0.3), 'steel_dark')
    # weld seams
    for z in arange(1.1, H - 0.1, 0.8):
        if zt is not None and zt - 0.1 < z < zt + 0.55:
            continue
        mb.torus(rad_at(z) + 0.002, 0.006, 'steel', M=Matrix.Translation((cx, cy, z)), segs=56, tsegs=5)
    # platforms, railings and ladders
    z_prev = 0.1
    for i, zp in enumerate(plats):
        rr = rad_at(zp)
        ro = rr + 0.42
        tp = T(0.03) / 2
        mb.lathe([(ro, zp - tp), (ro, zp + tp), (rr + 0.01, zp + tp), (rr + 0.01, zp - tp)],
                 'grating', segs=48, closed=True, M=Matrix.Translation((cx, cy, 0)))
        mb.lathe([(ro - 0.004 + T(0.01), zp - 0.04), (ro - 0.004 + T(0.01), zp + 0.05), (ro - 0.004, zp + 0.05),
                  (ro - 0.004, zp - 0.04)], 'rail_yellow', segs=48, closed=True,
                 M=Matrix.Translation((cx, cy, 0)))
        for k in range(8):
            a = 2 * pi * (k + 0.5) / 8
            d = V((math.cos(a), math.sin(a), 0))
            mb.beam(V((cx, cy, zp - 0.3)) + d * rr, V((cx, cy, zp - 0.02)) + d * (ro - 0.05),
                    0.02, 0.02, 'steel_dark')
            mb.beam(V((cx, cy, zp - 0.025)) + d * rr, V((cx, cy, zp - 0.025)) + d * ro,
                    0.025, 0.03, 'steel_dark')
        railing(mb, circle_pts((cx, cy), ro - 0.015, zp + 0.015, n=max(24, int(2 * pi * ro / 0.08))),
                h=0.24, spacing=0.3)
        ang = math.radians(-115 if i % 2 == 0 else -65) + (0.35 if i % 3 == 2 else 0)
        n = V((math.cos(ang), math.sin(ang), 0))
        foot = V((cx, cy, 0)) + n * (rad_at((z_prev + zp) / 2) + 0.24)
        ladder(mb, foot, n, z_prev, zp + 0.95, cage=True)
        z_prev = zp
    # nozzles & manholes
    for (z, a_deg, kind, size) in nozzles:
        a = math.radians(a_deg)
        d = V((math.cos(a), math.sin(a), 0))
        p = V((cx, cy, z)) + d * (rad_at(z) - 0.01)
        if kind == 'manhole':
            manhole(mb, p, d, size)
        else:
            nozzle(mb, p, d, size, 0.18)
    # top nozzle + davit
    top = V((cx, cy, H + head * rt))
    nozzle(mb, top - V((0, 0, 0.02)), (0, 0, 1), 0.07, 0.16)
    dp = V((cx + rt * 0.55, cy + rt * 0.3, H + head * rt * 0.6))
    mb.cyl(dp, dp + V((0, 0, 0.75)), 0.022, 'paint_red', segs=10)
    mb.beam(dp + V((0, 0, 0.73)), dp + V((0.45, 0.25, 0.73)), 0.03, 0.03, 'paint_red')
    mb.cyl(dp + V((0.42, 0.23, 0.72)), dp + V((0.42, 0.23, 0.5)), 0.004, 'steel_dark', segs=5)
    return mb.finish(coll)


def furnace(cx, cy, coll):
    mb = MB('Furnace')
    W, D, z0, z1 = 1.7, 1.3, 0.48, 1.62
    pad(mb, (cx, cy), (W + 0.5, D + 0.5), 0.05)
    for x in (-W / 2 + 0.06, 0, W / 2 - 0.06):
        for y in (-D / 2 + 0.06, D / 2 - 0.06):
            mb.box((cx + x, cy + y, (0.05 + z0) / 2), (0.09, 0.09, z0 - 0.05), 'steel_dark')
            mb.box((cx + x, cy + y, 0.06), (0.16, 0.16, 0.02), 'steel_dark')
    mb.box((cx, cy, z0 - 0.04), (W + 0.02, D + 0.02, 0.08), 'steel_dark')
    # burners beneath the floor
    for x in (-0.5, 0, 0.5):
        for y in (-0.3, 0.3):
            mb.cyl((cx + x, cy + y, 0.22), (cx + x, cy + y, z0 - 0.08), 0.05, 'steel', segs=12)
            mb.cyl((cx + x, cy + y, 0.22), (cx + x, cy + y, 0.26), 0.07, 'steel_dark', segs=12)
    mb.box((cx, cy, (z0 + z1) / 2), (W, D, z1 - z0), 'furnace')
    # stiffeners
    hz = z1 - z0
    for x in arange(-W / 2 + 0.12, W / 2 - 0.05, 0.2):
        for s in (-1, 1):
            mb.box((cx + x, cy + s * (D / 2 + 0.012), (z0 + z1) / 2), (0.035, 0.025, hz), 'steel_dark')
    for y in arange(-D / 2 + 0.12, D / 2 - 0.05, 0.2):
        for s in (-1, 1):
            mb.box((cx + s * (W / 2 + 0.012), cy + y, (z0 + z1) / 2), (0.025, 0.035, hz), 'steel_dark')
    for z in (z0 + 0.04, (z0 + z1) / 2, z1 - 0.03):
        mb.box((cx, cy, z), (W + 0.05, D + 0.05, 0.05), 'steel_dark')
    # peep doors
    for x in (-0.55, 0.0, 0.55):
        mb.box((cx + x, cy - D / 2 - 0.03, z0 + 0.3), (0.13, 0.03, 0.1), 'steel_dark')
        mb.cyl((cx + x + 0.05, cy - D / 2 - 0.05, z0 + 0.3), (cx + x + 0.05, cy - D / 2 - 0.07, z0 + 0.3),
               0.012, 'steel', segs=8)
    # hopper -> convection section -> breeching
    mb.frustum((cx, cy), (W + 0.02, D + 0.02), (1.15, 0.85), z1, z1 + 0.38, 'furnace')
    c0, c1 = z1 + 0.38, z1 + 0.82
    mb.box((cx, cy, (c0 + c1) / 2), (1.15, 0.85, c1 - c0), 'furnace')
    for x in arange(-0.5, 0.55, 0.17):
        for s in (-1, 1):
            mb.box((cx + x, cy + s * 0.437, (c0 + c1) / 2), (0.03, 0.025, c1 - c0), 'steel_dark')
    for z in (c0 + 0.03, c1 - 0.03):
        mb.box((cx, cy, z), (1.19, 0.89, 0.05), 'steel_dark')
    # tube return bends on the convection section ends
    for s in (-1, 1):
        for z in arange(c0 + 0.1, c1 - 0.05, 0.1):
            mb.torus(0.05, 0.015, 'steel',
                     M=Matrix.Translation((cx + s * 0.6, cy, z)) @ Matrix.Rotation(pi / 2, 4, 'X')
                     @ Matrix.Rotation(pi / 2, 4, 'Z'),
                     segs=12, tsegs=6, a0=-pi / 2 if s > 0 else pi / 2, a1=pi / 2 if s > 0 else 3 * pi / 2)
    mb.frustum((cx, cy), (1.15, 0.85), (0.46, 0.46), c1, c1 + 0.22, 'furnace')
    # striped chimney
    zc0, zc1, rc = c1 + 0.22, c1 + 2.4, 0.17
    mb.cyl((cx, cy, zc0 - 0.02), (cx, cy, zc0 + 0.06), 0.25, 'steel_dark', segs=32)
    n_str = 8
    for k in range(n_str):
        za = zc0 + (zc1 - zc0) * k / n_str
        zb = zc0 + (zc1 - zc0) * (k + 1) / n_str
        mat = 'paint_red' if (n_str - k) % 2 == 1 else 'paint_white'
        mb.cyl((cx, cy, za), (cx, cy, zb), rc, mat, segs=40, caps=False)
    mb.lathe([(rc + 0.03, zc1 - 0.01), (rc + 0.03, zc1 + 0.05), (rc - 0.03, zc1 + 0.05), (rc - 0.03, zc1 - 0.01)],
             'steel_dark', segs=40, closed=True, M=Matrix.Translation((cx, cy, 0)))
    mb.cyl((cx, cy, zc1 - 0.005), (cx, cy, zc1 + 0.03), rc - 0.03, 'frame', segs=40)
    mb.torus(rc + 0.008, 0.01, 'steel_dark', M=Matrix.Translation((cx, cy, zc0 + 0.9)), segs=40, tsegs=5)
    # chimney sampling platform
    zp = zc0 + 1.2
    tp = T(0.024) / 2
    mb.lathe([(rc + 0.3, zp - tp), (rc + 0.3, zp + tp), (rc, zp + tp), (rc, zp - tp)],
             'grating', segs=40, closed=True, M=Matrix.Translation((cx, cy, 0)))
    railing(mb, circle_pts((cx, cy), rc + 0.29, zp, n=36), h=0.2)
    ladder(mb, (cx + 0.0, cy - rc - 0.12), (0, -1), c1 + 0.1, zp + 0.9, cage=True)
    # side platform & ladder
    mb.box((cx + W / 2 + 0.25, cy, z1), (0.5, D, 0.03), 'grating')
    mb.beam((cx + W / 2, cy - D / 2, z1 - 0.3), (cx + W / 2 + 0.45, cy - D / 2, z1 - 0.02), 0.03, 0.03, 'steel_dark')
    mb.beam((cx + W / 2, cy + D / 2, z1 - 0.3), (cx + W / 2 + 0.45, cy + D / 2, z1 - 0.02), 0.03, 0.03, 'steel_dark')
    x1 = cx + W / 2 + 0.48
    railing(mb, [(cx + W / 2, cy - D / 2, z1), (x1, cy - D / 2, z1), (x1, cy + D / 2, z1),
                 (cx + W / 2, cy + D / 2, z1)], closed=False, h=0.22)
    ladder(mb, (x1 + 0.0, cy + 0.35), (1, 0), 0.05, z1 + 0.9)
    return mb.finish(coll, bevel=0.006)


def cooling_tower(cx, cy, coll):
    mb = MB('CoolingTower')
    W, D, zb, zt = 2.7, 1.85, 0.3, 1.3
    mb.box((cx, cy, zb / 2), (W + 0.24, D + 0.24, zb), 'concrete')
    mb.box((cx, cy, zb + 0.01), (W + 0.26, D + 0.26, 0.02), 'concrete_dk')
    mb.box((cx, cy, (zb + zt) / 2), (W, D, zt - zb), 'galv')
    for sx in (-1, 1):
        for sy in (-1, 1):
            mb.box((cx + sx * W / 2, cy + sy * D / 2, (zb + zt) / 2), (0.07, 0.07, zt - zb + 0.02), 'galv_dark')
    zl = zb + 0.48
    # air inlet louvers
    for z in arange(zb + 0.05, zl - 0.02, 0.055):
        for s in (-1, 1):
            mb.box((cx, cy + s * (D / 2 + 0.018), z), (W - 0.08, 0.01, 0.065), 'galv_dark', rot=(s * 0.7, 0, 0))
            mb.box((cx + s * (W / 2 + 0.018), cy, z), (0.01, D - 0.08, 0.065), 'galv_dark', rot=(0, -s * 0.7, 0))
    # louver frames
    for s in (-1, 1):
        for x in linspace(-W / 2 + 0.03, W / 2 - 0.03, 6):
            mb.box((cx + x, cy + s * (D / 2 + 0.03), (zb + zl) / 2), (0.03, 0.03, zl - zb), 'galv_dark')
        for y in linspace(-D / 2 + 0.03, D / 2 - 0.03, 5):
            mb.box((cx + s * (W / 2 + 0.03), cy + y, (zb + zl) / 2), (0.03, 0.03, zl - zb), 'galv_dark')
    mb.box((cx, cy, zl + 0.015), (W + 0.07, D + 0.07, 0.04), 'galv_dark')
    # corrugated upper casing
    hu = zt - zl - 0.03
    for x in arange(-W / 2 + 0.06, W / 2 - 0.03, 0.08):
        for s in (-1, 1):
            mb.box((cx + x, cy + s * (D / 2 + 0.006), zl + 0.03 + hu / 2), (0.028, 0.014, hu), 'galv')
    for y in arange(-D / 2 + 0.06, D / 2 - 0.03, 0.08):
        for s in (-1, 1):
            mb.box((cx + s * (W / 2 + 0.006), cy + y, zl + 0.03 + hu / 2), (0.014, 0.028, hu), 'galv')
    # deck
    mb.box((cx, cy, zt + 0.025), (W + 0.08, D + 0.08, 0.05), 'galv_dark')
    zd = zt + 0.05
    railing(mb, [(cx - W / 2, cy - D / 2, zd), (cx + W / 2, cy - D / 2, zd), (cx + W / 2, cy + D / 2, zd),
                 (cx - W / 2, cy + D / 2, zd)], h=0.2, mat='galv', spacing=0.3)
    # fan stacks
    for fx in (-0.66, 0.66):
        fc = (cx + fx, cy)
        Mf = Matrix.Translation((fc[0], fc[1], 0))
        R0, R1 = 0.55, 0.52
        mb.lathe([(R0, zd), (R0 - 0.02, zd + 0.3), (R0 + 0.01, zd + 0.33), (R1 - 0.02, zd + 0.33),
                  (R1 - 0.04, zd + 0.3), (R1 - 0.01, zd)], 'galv', segs=64, closed=True, M=Mf)
        mb.torus(R0 - 0.01, 0.018, 'galv', M=Matrix.Translation((fc[0], fc[1], zd + 0.33)), segs=64, tsegs=6)
        mb.torus(R0 + 0.005, 0.012, 'galv_dark', M=Matrix.Translation((fc[0], fc[1], zd + 0.15)), segs=64, tsegs=5)
        mb.cyl((fc[0], fc[1], zd + 0.005), (fc[0], fc[1], zd + 0.01), R1 - 0.03, 'frame', segs=48)
        # fan
        zf = zd + 0.17
        mb.cyl((fc[0], fc[1], zd + 0.01), (fc[0], fc[1], zf), 0.05, 'steel_dark', segs=12)
        mb.cyl((fc[0], fc[1], zf - 0.02), (fc[0], fc[1], zf + 0.03), 0.08, 'galv_dark', segs=16)
        for k in range(8):
            a = 2 * pi * k / 8
            R = Euler((0, 0, a)).to_matrix() @ Euler((0.35, 0, 0)).to_matrix()
            c = V((fc[0], fc[1], zf)) + Euler((0, 0, a)).to_matrix() @ V((0.27, 0, 0))
            mb.box(c, (0.38, 0.075, 0.008), 'galv_dark', R=R)
        # grille: rings + spokes
        zg = zd + 0.34
        for rr in (0.17, 0.33):
            mb.torus(rr, 0.008, 'steel_dark', M=Matrix.Translation((fc[0], fc[1], zg)), segs=40, tsegs=5)
        for k in range(12):
            a = 2 * pi * k / 12
            mb.cyl((fc[0], fc[1], zg), (fc[0] + math.cos(a) * (R1 - 0.03), fc[1] + math.sin(a) * (R1 - 0.03), zg),
                   0.009, 'steel_dark', segs=6)
        mb.cyl((fc[0], fc[1], zg - 0.01), (fc[0], fc[1], zg + 0.02), 0.06, 'steel_dark', segs=16)
    # access ladder & distribution header
    ladder(mb, (cx + 0.95, cy - D / 2 - 0.1), (0, -1), zb, zd + 0.9)
    mb.cyl((cx - W / 2 + 0.15, cy + D / 2 + 0.08, zt - 0.1), (cx + W / 2 - 0.15, cy + D / 2 + 0.08, zt - 0.1),
           0.045, 'steel', segs=20)
    for x in linspace(-W / 2 + 0.3, W / 2 - 0.3, 5):
        mb.cyl((cx + x, cy + D / 2 + 0.08, zt - 0.1), (cx + x, cy + D / 2 - 0.02, zt - 0.1), 0.025, 'steel', segs=12)
    return mb.finish(coll, bevel=0.004)


def heat_exchanger(cx, cy, coll):
    mb = MB('HeatExchanger')
    L, Wd, zd = 2.2, 1.1, 0.75
    pad(mb, (cx, cy), (L + 0.4, Wd + 0.4))
    xs = (-L / 2 + 0.05, 0, L / 2 - 0.05)
    ys = (-Wd / 2 + 0.05, Wd / 2 - 0.05)
    for x in xs:
        for y in ys:
            mb.box((cx + x, cy + y, zd / 2), (0.07, 0.07, zd), 'steel_dark')
            mb.box((cx + x, cy + y, 0.05), (0.15, 0.15, 0.02), 'steel_dark')
    for y in ys:
        for xa, xb in zip(xs, xs[1:]):
            mb.beam((cx + xa, cy + y, 0.1), (cx + xb, cy + y, zd - 0.06), 0.03, 0.03, 'steel_dark')
            mb.beam((cx + xb, cy + y, 0.1), (cx + xa, cy + y, zd - 0.06), 0.03, 0.03, 'steel_dark')
        mb.box((cx, cy + y, zd - 0.04), (L, 0.07, 0.08), 'steel_dark')
    for x in xs:
        mb.box((cx + x, cy, zd - 0.04), (0.07, Wd, 0.08), 'steel_dark')
    mb.box((cx, cy, zd + 0.015), (L, Wd, 0.03), 'grating')
    zr = zd + 0.03
    x0, x1 = cx - L / 2, cx + L / 2
    y0, y1 = cy - Wd / 2, cy + Wd / 2
    railing(mb, [(cx + 0.75, y0, zr), (x1, y0, zr), (x1, y1, zr), (x0, y1, zr), (x0, y0, zr), (cx + 0.45, y0, zr)],
            closed=False, h=0.24)
    ladder(mb, (cx + 0.6, y0 - 0.08), (0, -1), 0.0, zd + 0.95)
    # shell
    zs = zd + 0.03 + 0.14 + 0.32
    R = 0.32
    Mx = Matrix.Translation((cx, cy, zs)) @ Matrix.Rotation(pi / 2, 4, 'Y')
    prof = [(0, -0.8), (R, -0.8), (R, 0.62)]
    prof += [(R * math.cos(a), 0.62 + 0.18 * math.sin(a)) for a in linspace(0.25, 1.35, 6)] + [(0, 0.8)]
    mb.lathe(prof, 'steel', segs=48, M=Mx)
    for z in (-0.3, 0.2):
        mb.torus(R + 0.002, 0.005, 'steel', M=Mx @ Matrix.Translation((0, 0, z)), segs=48, tsegs=5)
    # saddles
    for x in (-0.45, 0.35):
        mb.box((cx + x, cy, zd + 0.1), (0.1, 0.55, 0.14), 'steel_dark')
        mb.box((cx + x, cy, zd + 0.04), (0.16, 0.62, 0.02), 'steel_dark')
    # girth flanges & channel
    for xf in (-0.8, -0.84):
        flange(mb, (cx + xf, cy, zs), (1, 0, 0), R + 0.06, thick=0.035, bolts=20 if xf == -0.84 else 0)
    mb.cyl((cx - 0.86, cy, zs), (cx - 1.08, cy, zs), R, 'steel', segs=48)
    flange(mb, (cx - 1.1, cy, zs), (1, 0, 0), R + 0.06, thick=0.04, bolts=20)
    mb.cyl((cx - 1.12, cy, zs), (cx - 1.16, cy, zs), R + 0.02, 'steel', segs=48)
    # nozzles
    for x in (-0.45, 0.4):
        nozzle(mb, (cx + x, cy, zs + R - 0.01), (0, 0, 1), 0.07, 0.17)
    nozzle(mb, (cx - 0.97, cy, zs + R - 0.01), (0, 0, 1), 0.07, 0.17)
    nozzle(mb, (cx - 0.97, cy, zs - R + 0.01), (0, 0, -1), 0.07, 0.12)
    nozzle(mb, (cx + 0.1, cy, zs - R + 0.01), (0, 0, -1), 0.05, 0.1)
    # vents and gauges
    mb.cyl((cx + 0.0, cy, zs + R), (cx, cy, zs + R + 0.12), 0.015, 'steel', segs=8)
    mb.cyl((cx, cy, zs + R + 0.12), (cx, cy - 0.03, zs + R + 0.12), 0.03, 'chrome', segs=16)
    return mb.finish(coll, bevel=0.004)


def sphere_tank(name, cx, cy, R, zc, ladder_az, coll):
    mb = MB(name)
    nleg = 8
    legs = []
    for k in range(nleg):
        a = 2 * pi * (k + 0.5) / nleg
        p = V((cx + math.cos(a) * R * 0.99, cy + math.sin(a) * R * 0.99, 0))
        legs.append(p)
        mb.box((p.x, p.y, 0.04), (0.2, 0.2, 0.08), 'concrete')
        mb.box((p.x, p.y, 0.09), (0.13, 0.13, 0.02), 'steel_dark')
        mb.cyl(p + V((0, 0, 0.08)), p + V((0, 0, zc + 0.05)), 0.05, 'steel', segs=16)
    for k in range(nleg):
        a, b = legs[k], legs[(k + 1) % nleg]
        mb.cyl(a + V((0, 0, 0.3)), b + V((0, 0, zc - 0.35)), 0.01, 'steel_dark', segs=6)
        mb.cyl(b + V((0, 0, 0.3)), a + V((0, 0, zc - 0.35)), 0.01, 'steel_dark', segs=6)
    mb.sphere((cx, cy, zc), R, 'steel_bright', segs=72, rings=36)
    mb.torus(R + 0.003, 0.012, 'steel', M=Matrix.Translation((cx, cy, zc)), segs=72, tsegs=6)
    for lat in (-0.6, 0.6):
        mb.torus(R * math.cos(lat) + 0.002, 0.005, 'steel_bright',
                 M=Matrix.Translation((cx, cy, zc + R * math.sin(lat))), segs=64, tsegs=5)
    # top platform
    zt = zc + R
    mb.cyl((cx, cy, zt - 0.06), (cx, cy, zt + 0.08), 0.12, 'steel', segs=24)
    flange(mb, (cx, cy, zt + 0.08), (0, 0, 1), 0.17, bolts=12)
    mb.cyl((cx, cy, zt + 0.02), (cx, cy, zt + 0.05), 0.48, 'grating', segs=40)
    railing(mb, circle_pts((cx, cy), 0.46, zt + 0.05, n=36), h=0.2)
    for k in range(4):
        a = 2 * pi * k / 4 + 0.4
        nozzle(mb, (cx + math.cos(a) * 0.28, cy + math.sin(a) * 0.28, zt - 0.06), (0, 0, 1), 0.035, 0.17, bolts=6)
    # curved ladder up the meridian + vertical ladder to the equator
    az = math.radians(ladder_az)
    n = V((math.cos(az), math.sin(az), 0))
    t = V((-n.y, n.x, 0))
    rl = R + 0.1
    for s in (-1, 1):
        pts = [V((cx, cy, zc)) + n * (rl * math.cos(e)) + t * (0.065 * s) + V((0, 0, rl * math.sin(e)))
               for e in linspace(0.0, 1.33, 24)]
        mb.sweep(pts, 0.0075, 'rail_yellow', segs=6)
        pts2 = [p + V((0, 0, 0.22)) + n * 0.06 for p in pts[2:-2]]
        mb.sweep(pts2, 0.006, 'rail_yellow', segs=6)
    for e in linspace(0.03, 1.3, 26):
        p = V((cx, cy, zc)) + n * (rl * math.cos(e)) + V((0, 0, rl * math.sin(e)))
        mb.cyl(p - t * 0.065, p + t * 0.065, 0.0045, 'rail_yellow', segs=5, caps=False)
    foot = V((cx, cy, 0)) + n * rl
    ladder(mb, foot, n, 0.0, zc + 0.02, cage=True)
    # bottom outlet
    mb.cyl((cx, cy, zc - R + 0.02), (cx, cy, 0.42), 0.06, 'steel', segs=20)
    flange(mb, (cx, cy, 0.42), (0, 0, 1), 0.1, bolts=8)
    return mb.finish(coll)


def flare_stack(cx, cy, H, coll):
    mb = MB('FlareStack')
    mb.box((cx, cy, 0.05), (1.4, 1.4, 0.1), 'concrete')
    w0, w1 = 0.52, 0.16
    nlev = 15
    zs = [0.1 + (H - 0.1) * (i / nlev) ** 0.92 for i in range(nlev + 1)]

    def corners(z):
        w = w0 + (w1 - w0) * (z - 0.1) / (H - 0.1)
        return [V((cx + sx * w, cy + sy * w, z)) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]

    levels = [corners(z) for z in zs]
    for i in range(nlev):
        lo, hi = levels[i], levels[i + 1]
        for k in range(4):
            mb.beam(lo[k], hi[k], 0.045, 0.045, 'steel')
            k1 = (k + 1) % 4
            mb.beam(hi[k], hi[k1], 0.025, 0.025, 'steel')
            mb.beam(lo[k], hi[k1], 0.016, 0.016, 'steel')
            mb.beam(lo[k1], hi[k], 0.016, 0.016, 'steel')
    for p in levels[0]:
        mb.box((p.x, p.y, 0.12), (0.14, 0.14, 0.04), 'steel_dark')
    # riser
    mb.cyl((cx, cy, 0.1), (cx, cy, H + 0.45), 0.085, 'steel', segs=24)
    for z in arange(1.0, H, 1.1):
        mb.torus(0.09, 0.008, 'steel_dark', M=Matrix.Translation((cx, cy, z)), segs=24, tsegs=5)
    mb.cyl((cx + 0.12, cy, 0.1), (cx + 0.12, cy, H + 0.45), 0.012, 'steel', segs=8)
    mb.cyl((cx - 0.12, cy, 0.1), (cx - 0.12, cy, H + 0.4), 0.01, 'steel', segs=8)
    # tip
    tip = H + 0.45
    mb.lathe([(0.085, tip), (0.11, tip + 0.05), (0.11, tip + 0.28), (0.13, tip + 0.3), (0.13, tip + 0.33),
              (0.1, tip + 0.33), (0.1, tip + 0.1)], 'steel_dark', segs=32, M=Matrix.Translation((cx, cy, 0)))
    for k in range(6):
        a = 2 * pi * k / 6
        mb.beam((cx + math.cos(a) * 0.11, cy + math.sin(a) * 0.11, tip + 0.06),
                (cx + math.cos(a) * 0.18, cy + math.sin(a) * 0.18, tip + 0.26), 0.012, 0.03, 'steel_dark')
    # top platform
    zp = H - 0.05
    s = w1 + 0.3
    mb.box((cx, cy, zp), (2 * s, 2 * s, 0.03), 'grating')
    railing(mb, [(cx - s, cy - s, zp), (cx + s, cy - s, zp), (cx + s, cy + s, zp), (cx - s, cy + s, zp)], h=0.22)
    # aviation obstruction lights
    for z in (H * 0.5, zp + 0.24):
        mb.sphere((cx + s if z > H * 0.6 else cx + 0.35, cy - (s if z > H * 0.6 else 0.35), z), 0.03, 'beacon',
                  segs=12, rings=8)
    ob = mb.finish(coll)
    # flame
    fl = MB('Flare_Flame')
    ft = tip + 0.3
    core = [(0.0, ft)] + [(0.09 * math.sin(pi * u) ** 0.8 * (1 - u) ** 0.4 + 0.05 * (1 - u), ft + 1.0 * u)
                           for u in linspace(0.02, 0.98, 14)] + [(0.0, ft + 1.0)]
    outer = [(0.0, ft - 0.02)] + [(0.15 * math.sin(pi * u) ** 0.7 * (1 - u) ** 0.35 + 0.08 * (1 - u),
                                   ft - 0.02 + 1.45 * u) for u in linspace(0.02, 0.98, 16)] + [(0.0, ft + 1.43)]
    fl.lathe(core, 'flame_core', segs=24, M=Matrix.Translation((cx, cy, 0)))
    fl.lathe(outer, 'flame_outer', segs=24,
             M=Matrix.Translation((cx, cy, 0)) @ Matrix.Shear('XZ', 4, (0.06, 0.0)))
    fob = fl.finish(coll)
    _try(fob, 'visible_shadow', False)
    ld = bpy.data.lights.new('FlareLight', 'POINT')
    ld.energy = 120
    ld.color = (1.0, 0.55, 0.2)
    ld.shadow_soft_size = 0.25
    lo = bpy.data.objects.new('FlareLight', ld)
    lo.location = (cx, cy, ft + 0.35)
    coll.objects.link(lo)
    return ob


def storage_tank(name, cx, cy, R, H, stair_az, coll, nozzle_az=180):
    mb = MB(name)
    Mt = Matrix.Translation((cx, cy, 0))
    mb.cyl((cx, cy, 0), (cx, cy, 0.08), R + 0.14, 'concrete', segs=64)
    roof = [(R, H), (R + 0.01, H + 0.01), (R * 0.7, H + 0.13), (R * 0.35, H + 0.22), (0.12, H + 0.26), (0, H + 0.265)]
    mb.lathe([(0, 0.08), (R, 0.08), (R, H)], 'paint_white', segs=96, M=Mt)
    mb.lathe(roof, 'paint_white', segs=96, M=Mt, sharp_deg=20)
    mb.lathe([(R - 0.01 + T(0.016), 0.08), (R - 0.01 + T(0.016), 0.24), (R - 0.01, 0.24)], 'paint_grey', segs=96, M=Mt)
    for z in arange(0.45, H - 0.1, 0.32):
        mb.torus(R + 0.002, 0.004, 'paint_white', M=Matrix.Translation((cx, cy, z)), segs=96, tsegs=4)
    # wind girder + top angle
    zg = H - 0.18
    tg = T(0.016) / 2
    mb.lathe([(R + 0.07, zg - tg), (R + 0.07, zg + tg), (R, zg + tg), (R, zg - tg)],
             'paint_white', segs=96, closed=True, M=Mt)
    mb.torus(R + 0.008, 0.012, 'paint_white', M=Matrix.Translation((cx, cy, H)), segs=96, tsegs=6)
    # spiral stair
    a0 = math.radians(stair_az)
    sweep_ang = 1.9
    nsteps = int(H / 0.065)
    rin, rout = R + 0.04, R + 0.3

    def hp(rad, u, dz=0.0):
        a = a0 + sweep_ang * u
        return V((cx + rad * math.cos(a), cy + rad * math.sin(a), 0.08 + (H - 0.08) * u + dz))

    for k in range(nsteps + 1):
        u = k / nsteps
        a = a0 + sweep_ang * u
        c = hp((rin + rout) / 2, u)
        mb.box(c, (rout - rin, 0.08, 0.012), 'galv', R=Euler((0, 0, a)).to_matrix())
    us = linspace(0, 1, 60)
    for rad in (rin, rout):
        mb.sweep([hp(rad, u, -0.03) for u in us], 0.012, 'galv_dark', segs=6)
    mb.sweep([hp(rout, u, 0.24) for u in us], 0.008, 'rail_yellow', segs=6)
    mb.sweep([hp(rout, u, 0.12) for u in us], 0.006, 'rail_yellow', segs=6)
    for u in linspace(0.0, 1.0, 16):
        mb.cyl(hp(rout, u), hp(rout, u, 0.24), 0.0075, 'rail_yellow', segs=6)
    for u in linspace(0.12, 0.92, 6):
        p = hp(rin, u, -0.05)
        mb.beam(p, hp(R, u, -0.05), 0.03, 0.03, 'galv_dark')
    # top landing + roof rail
    a_top = a0 + sweep_ang
    rail_pts = circle_pts((cx, cy), R - 0.03, H + 0.015, n=16, a0=a_top - 0.15, a1=a_top + 0.9, closed=False)
    railing(mb, rail_pts, closed=False, h=0.22, toe=False)
    mb.box(hp((rin + rout) / 2, 1.0, 0.0), (rout - rin + 0.05, 0.3, 0.02), 'grating',
           R=Euler((0, 0, a_top)).to_matrix())
    # roof fittings
    mb.cyl((cx + 0.2, cy + 0.1, H + 0.15), (cx + 0.2, cy + 0.1, H + 0.42), 0.05, 'paint_white', segs=16)
    mb.cyl((cx + 0.2, cy + 0.1, H + 0.42), (cx + 0.2, cy + 0.1, H + 0.47), 0.09, 'paint_white', r2=0.02, segs=16)
    mb.box((cx - 0.4, cy - 0.3, H + 0.12), (0.18, 0.18, 0.06), 'paint_white', rot=(0.12, -0.1, 0.3))
    # shell nozzles + valves
    for da in (-0.25, 0.25):
        a = math.radians(nozzle_az) + da
        d = V((math.cos(a), math.sin(a), 0))
        e = nozzle(mb, V((cx, cy, 0.28)) + d * (R - 0.01), d, 0.05, 0.18)
        gate_valve(mb, e + d * 0.08, d, 0.05)
    # level gauge
    a = a0 + 0.5
    p = V((cx + (R + 0.05) * math.cos(a), cy + (R + 0.05) * math.sin(a), 0))
    mb.cyl(p + V((0, 0, 0.3)), p + V((0, 0, H - 0.05)), 0.012, 'steel', segs=8)
    mb.box(p + V((0, 0, 0.9)), (0.05, 0.05, 0.1), 'steel_dark')
    return mb.finish(coll)


def water_tank(cx, cy, R, H, coll):
    mb = MB('WaterTank')
    Mt = Matrix.Translation((cx, cy, 0))
    mb.cyl((cx, cy, 0), (cx, cy, 0.06), R + 0.1, 'concrete', segs=48)
    mb.lathe([(R, 0.06), (R, H)], 'paint_green', segs=240, M=Mt, rib=(40, 0.012))
    mb.lathe([(0, H), (R + 0.035, H), (R + 0.035, H + 0.04), (0.06, H + 0.24), (0, H + 0.25)],
             'paint_green_dk', segs=96, M=Mt)
    mb.torus(R + 0.012, 0.014, 'paint_green_dk', M=Matrix.Translation((cx, cy, 0.08)), segs=96, tsegs=6)
    for z in (H * 0.35, H * 0.7):
        mb.torus(R + 0.014, 0.008, 'paint_green_dk', M=Matrix.Translation((cx, cy, z)), segs=96, tsegs=5)
    a = math.radians(-35)
    n = V((math.cos(a), math.sin(a), 0))
    ladder(mb, V((cx, cy, 0)) + n * (R + 0.08), n, 0.0, H + 0.4, cage=True, mat='galv')
    mb.box((cx + 0.15, cy - 0.15, H + 0.12), (0.18, 0.18, 0.05), 'paint_green_dk', rot=(0.15, -0.15, 0.3))
    mb.cyl((cx - 0.2, cy + 0.1, H + 0.12), (cx - 0.2, cy + 0.1, H + 0.3), 0.03, 'galv', segs=12)
    mb.cyl((cx - 0.2, cy + 0.1, H + 0.3), (cx - 0.2, cy + 0.1, H + 0.34), 0.06, 'galv', r2=0.02, segs=12)
    d = V((-1, 0.15, 0)).normalized()
    nozzle(mb, V((cx, cy, 0.25)) + d * (R - 0.01), d, 0.045, 0.12)
    d2 = V((0, 1, 0))
    nozzle(mb, V((cx, cy, 0.45)) + d2 * (R - 0.01), d2, 0.04, 0.12)
    return mb.finish(coll)


def office(cx, cy, coll):
    mb = MB('OfficeBuilding')
    W, D, Hf = 2.3, 1.4, 0.56
    zb = 0.07
    H = 2 * Hf
    mb.box((cx, cy, zb / 2), (W + 0.12, D + 0.12, zb), 'concrete')
    mb.box((cx, cy, zb + H / 2), (W, D, H), 'wall')
    mb.box((cx, cy, zb + Hf), (W + 0.025, D + 0.025, 0.05), 'paint_blue')
    mb.box((cx, cy, zb + H - 0.03), (W + 0.035, D + 0.035, 0.06), 'wall_trim')
    mb.box((cx, cy, zb + 0.04), (W + 0.02, D + 0.02, 0.08), 'concrete_dk')

    def window(c, axis, w, h, sign):
        # axis 'y': window on a y-facing wall, sign = facing direction
        x, y, z = c
        fw = 0.022
        if axis == 'y':
            o = sign * 0.006
            mb.box((x, y + o, z), (w, 0.01, h), 'glass')
            mb.box((x, y + o * 2, z + h / 2), (w + fw, 0.02, fw), 'paint_blue')
            mb.box((x, y + o * 2, z - h / 2), (w + fw, 0.02, fw), 'paint_blue')
            mb.box((x - w / 2, y + o * 2, z), (fw, 0.02, h), 'paint_blue')
            mb.box((x + w / 2, y + o * 2, z), (fw, 0.02, h), 'paint_blue')
            mb.box((x, y + o * 2, z), (0.012, 0.016, h), 'paint_blue')
            mb.box((x, y + o * 2, z + h * 0.18), (w, 0.016, 0.012), 'paint_blue')
            mb.box((x, y + sign * 0.03, z - h / 2 - 0.018), (w + 0.05, 0.05, 0.02), 'wall_trim')
        else:
            o = sign * 0.006
            mb.box((x + o, y, z), (0.01, w, h), 'glass')
            mb.box((x + o * 2, y, z + h / 2), (0.02, w + fw, fw), 'paint_blue')
            mb.box((x + o * 2, y, z - h / 2), (0.02, w + fw, fw), 'paint_blue')
            mb.box((x + o * 2, y - w / 2, z), (0.02, fw, h), 'paint_blue')
            mb.box((x + o * 2, y + w / 2, z), (0.02, fw, h), 'paint_blue')
            mb.box((x + o * 2, y, z), (0.016, 0.012, h), 'paint_blue')
            mb.box((x + sign * 0.03, y, z - h / 2 - 0.018), (0.05, w + 0.05, 0.02), 'wall_trim')

    for fl in range(2):
        zc = zb + Hf * fl + Hf * 0.52
        xs = (-0.85, -0.45, 0.45, 0.85) if fl == 0 else (-0.85, -0.45, 0.0, 0.45, 0.85)
        for x in xs:
            window((cx + x, cy - D / 2, zc), 'y', 0.3, 0.28, -1)
        for x in (-0.75, -0.25, 0.25, 0.75):
            window((cx + x, cy + D / 2, zc), 'y', 0.3, 0.28, 1)
        for y in (-0.3, 0.3):
            window((cx - W / 2, cy + y, zc), 'x', 0.3, 0.28, -1)
            window((cx + W / 2, cy + y, zc), 'x', 0.3, 0.28, 1)
    # entrance
    dz = zb + 0.22
    mb.box((cx, cy - D / 2 - 0.006, dz), (0.34, 0.012, 0.42), 'glass')
    for x in (-0.17, 0.0, 0.17):
        mb.box((cx + x, cy - D / 2 - 0.014, dz), (0.025, 0.02, 0.44), 'paint_blue')
    mb.box((cx, cy - D / 2 - 0.014, dz + 0.22), (0.37, 0.02, 0.025), 'paint_blue')
    mb.box((cx, cy - D / 2 - 0.13, zb + 0.47), (0.6, 0.26, 0.03), 'wall_trim')
    for x in (-0.27, 0.27):
        mb.cyl((cx + x, cy - D / 2 - 0.23, zb), (cx + x, cy - D / 2 - 0.23, zb + 0.46), 0.012, 'steel', segs=8)
    for k in range(3):
        mb.box((cx, cy - D / 2 - 0.12 - k * 0.07, zb - 0.02 - k * 0.022), (0.6, 0.12 + k * 0.0, 0.022 * (3 - k) + 0.01),
               'concrete')
    # roof
    ov = 0.13
    zr = zb + H
    mb.box((cx, cy, zr + 0.02), (W + 2 * ov, D + 2 * ov, 0.04), 'paint_blue')
    mb.hip_roof((cx, cy), W + 2 * ov, D + 2 * ov, zr + 0.04, 0.48, 'roof_blue')
    # rain-water pipes & AC units
    for sx in (-1, 1):
        mb.cyl((cx + sx * (W / 2 + 0.03), cy - D / 2 - 0.03, zb), (cx + sx * (W / 2 + 0.03), cy - D / 2 - 0.03, zr),
               0.014, 'paint_white', segs=8)
    for y in (-0.25, 0.25):
        mb.box((cx + W / 2 + 0.08, cy + y, zb + 0.15), (0.14, 0.22, 0.2), 'wall_trim')
        mb.cyl((cx + W / 2 + 0.152, cy + y, zb + 0.15), (cx + W / 2 + 0.156, cy + y, zb + 0.15), 0.07,
               'frame', segs=20)
    return mb.finish(coll, bevel=0.005)


def tanker_truck(cx, cy, coll):
    mb = MB('TankerTruck_Chassis')
    yf = cy - 1.0
    for (y, ax) in ((yf + 0.22, 'f'), (cy + 0.5, 'r'), (cy + 0.76, 'r')):
        for sx in (-1, 1):
            c = V((cx + sx * 0.235, y, 0.135))
            Mw = Matrix.Translation(c) @ Matrix.Rotation(pi / 2, 4, 'Y')
            mb.lathe([(0.132, -0.032), (0.132, 0.032), (0.12, 0.046), (0.08, 0.046), (0.08, -0.046),
                      (0.12, -0.046)], 'rubber', segs=40, closed=True, M=Mw, sharp_deg=60)
            mb.cyl(c - V((0.04, 0, 0)), c + V((0.04, 0, 0)), 0.082, 'chrome', segs=24)
            mb.cyl(c + V((sx * 0.04, 0, 0)), c + V((sx * 0.06, 0, 0)), 0.03, 'steel_dark', segs=12)
            for k in range(8):
                a = 2 * pi * k / 8
                o = V((sx * 0.045, math.cos(a) * 0.05, math.sin(a) * 0.05))
                mb.cyl(c + o, c + o + V((sx * 0.01, 0, 0)), 0.006, 'steel_dark', segs=5)
        mb.cyl((cx - 0.2, y, 0.135), (cx + 0.2, y, 0.135), 0.022, 'steel_dark', segs=10)
    for sx in (-1, 1):
        mb.box((cx + sx * 0.14, cy - 0.05, 0.24), (0.05, 1.85, 0.07), 'steel_dark')
        # mudguards over rear tandem
        mb.box((cx + sx * 0.235, cy + 0.63, 0.29), (0.11, 0.62, 0.015), 'steel_dark')
        mb.box((cx + sx * 0.235, cy + 0.95, 0.17), (0.1, 0.01, 0.16), 'rubber')
        # side under-run guard
        mb.box((cx + sx * 0.25, cy - 0.05, 0.19), (0.015, 0.6, 0.02), 'steel')
        mb.box((cx + sx * 0.25, cy - 0.05, 0.25), (0.015, 0.6, 0.02), 'steel')
    # rear bumper & lights
    mb.box((cx, cy + 0.98, 0.2), (0.5, 0.04, 0.05), 'steel_dark')
    for sx in (-1, 1):
        mb.box((cx + sx * 0.2, cy + 1.0, 0.26), (0.07, 0.015, 0.035), 'tail_light')
    # tank
    Rt = 0.27
    zt = 0.58
    Mtank = Matrix.Translation((cx, cy + 0.27, zt)) @ Matrix.Rotation(-pi / 2, 4, 'X')
    half = 0.64
    prof = [(0, -half - 0.12)] + [(Rt * math.cos(a), -half - 0.12 * math.sin(a)) for a in linspace(1.3, 0.15, 5)]
    prof += [(Rt, -half), (Rt, half)]
    prof += [(Rt * math.cos(a), half + 0.12 * math.sin(a)) for a in linspace(0.15, 1.3, 5)] + [(0, half + 0.12)]
    mb.lathe(prof, 'steel_bright', segs=56, M=Mtank)
    for z in (-0.43, -0.1, 0.23, 0.55):
        mb.torus(Rt + 0.003, 0.009, 'steel', M=Mtank @ Matrix.Translation((0, 0, z)), segs=56, tsegs=5)
    for y in (cy - 0.25, cy + 0.75):
        mb.box((cx, y, 0.3), (0.34, 0.12, 0.08), 'steel_dark')
    # top walkway, manholes and fold-down rail
    ztop = zt + Rt
    mb.box((cx, cy + 0.27, ztop + 0.01), (0.12, 1.25, 0.012), 'grating')
    for y in (cy - 0.15, cy + 0.27, cy + 0.69):
        mb.cyl((cx, y, ztop - 0.02), (cx, y, ztop + 0.04), 0.07, 'steel', segs=20)
        mb.cyl((cx, y, ztop + 0.04), (cx, y, ztop + 0.055), 0.075, 'steel_dark', segs=20)
    for y in linspace(cy - 0.3, cy + 0.85, 6):
        mb.cyl((cx + 0.1, y, ztop), (cx + 0.1, y, ztop + 0.1), 0.005, 'steel', segs=5)
    mb.cyl((cx + 0.1, cy - 0.3, ztop + 0.1), (cx + 0.1, cy + 0.85, ztop + 0.1), 0.006, 'steel', segs=5)
    # rear ladder
    for sx in (-1, 1):
        mb.cyl((cx + sx * 0.06, cy + 1.03, 0.25), (cx + sx * 0.06, cy + 0.98, ztop + 0.05), 0.007, 'steel', segs=6)
    for z in arange(0.3, ztop, 0.08):
        mb.cyl((cx - 0.06, cy + 1.02, z), (cx + 0.06, cy + 1.02, z), 0.005, 'steel', segs=5)
    # discharge valves
    for y in (cy - 0.1, cy + 0.6):
        mb.cyl((cx, y, zt - Rt), (cx, y, 0.22), 0.025, 'steel', segs=10)
        mb.cyl((cx - 0.26, y, 0.22), (cx + 0.26, y, 0.22), 0.022, 'steel', segs=10)
    mb.finish(coll)

    cab = MB('TankerTruck_Cab')
    yc = yf + 0.26
    cab.box((cx, yc, 0.47), (0.52, 0.48, 0.5), 'truck_yellow')
    cab.box((cx, yc + 0.02, 0.76), (0.5, 0.38, 0.08), 'truck_yellow')
    cab.box((cx, yc + 0.06, 0.82), (0.44, 0.22, 0.06), 'truck_yellow', rot=(-0.25, 0, 0))
    cab.box((cx, yf + 0.005, 0.59), (0.45, 0.02, 0.2), 'glass')
    for sx in (-1, 1):
        cab.box((cx + sx * 0.262, yc - 0.06, 0.59), (0.012, 0.24, 0.18), 'glass')
        cab.box((cx + sx * 0.27, yc + 0.05, 0.36), (0.02, 0.2, 0.14), 'truck_yellow')
        # fenders
        cab.box((cx + sx * 0.235, yf + 0.22, 0.29), (0.12, 0.3, 0.02), 'truck_yellow')
        # mirrors
        cab.beam((cx + sx * 0.26, yf + 0.06, 0.6), (cx + sx * 0.36, yf + 0.04, 0.6), 0.012, 0.012, 'steel_dark')
        cab.box((cx + sx * 0.37, yf + 0.04, 0.58), (0.025, 0.04, 0.12), 'steel_dark')
        # headlights
        cab.box((cx + sx * 0.18, yf - 0.006, 0.3), (0.09, 0.01, 0.05), 'lamp')
        # steps
        cab.box((cx + sx * 0.255, yc, 0.21), (0.05, 0.16, 0.015), 'steel')
    cab.box((cx, yf - 0.005, 0.38), (0.3, 0.012, 0.13), 'frame')
    for z in linspace(0.33, 0.43, 5):
        cab.box((cx, yf - 0.012, z), (0.3, 0.006, 0.008), 'chrome')
    cab.box((cx, yf - 0.02, 0.22), (0.56, 0.05, 0.08), 'steel_dark')
    cab.box((cx, yf + 0.25, 0.22), (0.54, 0.4, 0.04), 'steel_dark')
    cab.cyl((cx + 0.22, yc + 0.27, 0.45), (cx + 0.22, yc + 0.27, 0.92), 0.018, 'chrome', segs=10)
    cab.finish(coll, bevel=0.02, bevel_segs=3)


def loading_gantry(x, y, coll):
    mb = MB('LoadingGantry')
    zt = 1.4
    for yy in (y - 0.25, y + 0.25):
        mb.box((x, yy, 0.03), (0.16, 0.16, 0.06), 'concrete')
        mb.box((x, yy, zt / 2), (0.06, 0.06, zt), 'steel_dark')
        mb.beam((x, yy, zt - 0.02), (x - 0.95, yy, zt - 0.02), 0.05, 0.06, 'steel_dark')
        mb.beam((x, yy, zt - 0.45), (x - 0.5, yy, zt - 0.05), 0.03, 0.03, 'steel_dark')
    mb.box((x - 0.48, y, zt + 0.02), (1.0, 0.56, 0.03), 'grating')
    railing(mb, [(x - 0.97, y - 0.27, zt + 0.035), (x - 0.97, y + 0.27, zt + 0.035)], closed=False, h=0.2)
    railing(mb, [(x, y - 0.27, zt + 0.035), (x - 0.97, y - 0.27, zt + 0.035)], closed=False, h=0.2)
    railing(mb, [(x, y + 0.27, zt + 0.035), (x - 0.97, y + 0.27, zt + 0.035)], closed=False, h=0.2)
    ladder(mb, (x + 0.09, y), (1, 0), 0.0, zt + 0.9)
    # loading arm
    ax = x - 0.85
    mb.cyl((ax, y, zt), (ax, y, zt - 0.12), 0.035, 'steel', segs=14)
    mb.sphere((ax, y, zt - 0.14), 0.05, 'steel', segs=16, rings=8)
    mb.cyl((ax, y, zt - 0.14), (ax + 0.0, y - 0.0, zt - 0.38), 0.03, 'steel', segs=14)
    mb.cyl((ax, y, zt - 0.38), (ax, y, zt - 0.42), 0.05, 'steel_dark', segs=14)
    mb.cyl((ax + 0.04, y, zt - 0.2), (ax + 0.04, y, zt - 0.05), 0.008, 'steel', segs=6)
    mb.box((ax + 0.04, y, zt - 0.25), (0.05, 0.05, 0.08), 'paint_red')
    return mb.finish(coll)


def pipe_rack(x0, x1, y, coll):
    mb = MB('PipeRack')
    ya, yb = y - 0.16, y + 0.16
    zt1, zt2 = 0.72, 0.98
    for x in linspace(x0, x1, int((x1 - x0) / 0.9) + 1):
        for yy in (ya, yb):
            mb.box((x, yy, 0.03), (0.14, 0.14, 0.06), 'concrete')
            mb.box((x, yy, zt2 / 2), (0.05, 0.05, zt2), 'steel_dark')
        mb.box((x, y, zt1 - 0.02), (0.05, yb - ya + 0.06, 0.04), 'steel_dark')
        mb.box((x, y, zt2 - 0.02), (0.05, yb - ya + 0.06, 0.04), 'steel_dark')
        mb.beam((x, ya, 0.1), (x, yb, zt1 - 0.05), 0.02, 0.02, 'steel_dark')
    for yy in (ya, yb):
        mb.box(((x0 + x1) / 2, yy, zt2 - 0.02), (x1 - x0, 0.04, 0.04), 'steel_dark')
    mb.finish(coll)
    pipes = []
    for i, (dy, r) in enumerate(((-0.11, 0.03), (-0.04, 0.025), (0.03, 0.035), (0.11, 0.028))):
        pipes.append(pipe('Rack_L1_%d' % i, [(x0 - 0.05, y + dy, zt1 + r), (x1 + 0.05, y + dy, zt1 + r)], r,
                          supports=False))
    for i, (dy, r) in enumerate(((-0.08, 0.045), (0.06, 0.03))):
        pipes.append(pipe('Rack_L2_%d' % i, [(x0 - 0.05, y + dy, zt2 + r), (x1 + 0.05, y + dy, zt2 + r)], r,
                          supports=False))
    return pipes


# ---------------------------------------------------------------------------
# Trees, lamps, signs
# ---------------------------------------------------------------------------
def make_tree_mesh(name, seed):
    rnd = random.Random(seed)
    mb = MB(name)
    Ht = rnd.uniform(0.95, 1.15)
    mb.cyl((0, 0, 0), (0, 0, Ht * 0.4), 0.03, 'trunk', segs=8, r2=0.015)
    tiers = 7
    for i in range(tiers):
        u = i / tiers
        z0 = 0.13 + u * Ht * 0.78
        z1 = z0 + 0.34 * (1 - u * 0.45)
        r = 0.31 * (1 - u * 0.82)
        segs = 16
        ring = []
        for k in range(segs):
            a = 2 * pi * k / segs + rnd.uniform(-0.08, 0.08)
            long = (k % 2 == 0)
            rr = r * (rnd.uniform(0.85, 1.15) if long else rnd.uniform(0.55, 0.7))
            zz = z0 - (0.035 if long else -0.02) * rnd.uniform(0.6, 1.2)
            ring.append(mb.bm.verts.new((rr * math.cos(a), rr * math.sin(a), zz)))
        apex = mb.bm.verts.new((rnd.uniform(-0.01, 0.01), rnd.uniform(-0.01, 0.01), z1))
        under = mb.bm.verts.new((0, 0, z0 + 0.07))
        mi = mb._mi('foliage')
        for k in range(segs):
            k1 = (k + 1) % segs
            for vs in ((ring[k], ring[k1], apex), (under, ring[k1], ring[k])):
                f = mb.bm.faces.new(vs)
                f.material_index = mi
                f.smooth = True
    return mb.finish(bpy.data.collections['Vegetation'])


def scatter_trees(coll, variants):
    for o in variants:
        o.hide_render = True
        o.hide_viewport = True
        o.location = (0, 0, -50)
    rnd = random.Random(SEED)
    placed = []
    keep_out = [(-5.5, -2.85, -2.85, -1.2),    # office front
                (5.8, -3.1, 7.0, 1.2),         # product tank stairs
                (3.3, -4.3, 5.7, -3.3)]       # product tank stair + label
    for (x0, y0, x1, y1) in GRASS_PATCHES:
        area = (x1 - x0) * (y1 - y0)
        n = int(area / 0.62)
        tries = 0
        while n > 0 and tries < 600:
            tries += 1
            x = rnd.uniform(x0 + 0.2, x1 - 0.2)
            y = rnd.uniform(y0 + 0.2, y1 - 0.2)
            if any((V((x, y)) - p).length < 0.42 for p in placed):
                continue
            if any(a <= x <= c and b <= y <= d for a, b, c, d in keep_out):
                continue
            placed.append(V((x, y)))
            n -= 1
            src = rnd.choice(variants)
            ob = bpy.data.objects.new('Tree', src.data)
            s = rnd.uniform(0.75, 1.25)
            ob.scale = (s, s, s * rnd.uniform(0.9, 1.15))
            ob.rotation_euler = (rnd.uniform(-0.04, 0.04), rnd.uniform(-0.04, 0.04), rnd.uniform(0, 2 * pi))
            ob.location = (x, y, 0.05)
            coll.objects.link(ob)


def street_lamps(coll):
    mb = MB('StreetLamps')
    for (x, y, dx) in ((0.6, -2.2, 0.75), (0.6, -3.7, 0.75), (2.55, 0.6, 1), (2.5, -4.0, 1), (-1.9, -2.0, 1)):
        mb.box((x, y, 0.02), (0.1, 0.1, 0.04), 'concrete')
        mb.cyl((x, y, 0.04), (x, y, 1.15), 0.02, 'paint_grey', segs=10, r2=0.013)
        mb.beam((x, y, 1.12), (x + dx * 0.3, y, 1.16), 0.018, 0.018, 'paint_grey')
        mb.box((x + dx * 0.33, y, 1.15), (0.14, 0.07, 0.035), 'paint_grey')
        mb.box((x + dx * 0.33, y, 1.13), (0.11, 0.05, 0.008), 'lamp')
    mb.finish(coll)


def sign(text, pos, coll, anchor=None, size=0.2):
    lines = text.split('\n')
    nch = max(len(l) for l in lines)
    w = nch * size * 0.68 + size * 1.1
    h = len(lines) * size * 1.22 + size * 0.75
    pos = V(pos)
    d = CAM_LOC - pos
    yaw = math.atan2(d.x, -d.y)
    mb = MB('Label_' + lines[0].replace(' ', '_'))
    mb.box((0, 0, 0), (w, 0.025, h), 'sign_white')
    mb.box((0, T(0.025) / 2 + T(0.008) / 2 - 0.001, 0), (w + 0.02, 0.008, h + 0.02), 'paint_grey')
    if anchor is None:
        for x in (-w * 0.3, w * 0.3):
            mb.cyl((x, 0.03, -pos.z), (x, 0.03, -h / 2 + 0.02), 0.012, 'steel', segs=8)
            mb.box((x, 0.03, -pos.z + 0.01), (0.06, 0.06, 0.02), 'concrete')
    ob = mb.finish(coll, bevel=0.004)
    ob.location = pos
    ob.rotation_euler = (0, 0, yaw)
    if anchor is not None:
        ld = MB('Leader_' + lines[0].replace(' ', '_'))
        Rz = Euler((0, 0, yaw)).to_matrix()
        side = 1 if (Rz.transposed() @ (V(anchor) - pos)).x > 0 else -1
        start = pos + Rz @ V((side * w / 2, 0.02, 0))
        mid = V((start.x, start.y, start.z))
        ld.cyl(start, V(anchor), 0.007, 'steel_dark', segs=6)
        ld.box(start, (0.03, 0.03, 0.06), 'steel_dark', R=Rz)
        ld.box(V(anchor), (0.04, 0.04, 0.04), 'steel_dark')
        ld.finish(coll)
    cu = bpy.data.curves.new('Text_' + lines[0], 'FONT')
    cu.body = text
    cu.align_x = 'CENTER'
    cu.align_y = 'CENTER'
    cu.size = size * 1.3
    cu.extrude = 0.0015 if not PRINT else 0.5 / print_scale() / 2
    cu.space_line = 1.0
    if FONT is not None:
        cu.font = FONT
    cu.materials.append(MAT['sign_text'])
    tob = bpy.data.objects.new('Text_' + lines[0], cu)
    coll.objects.link(tob)
    tob.parent = ob
    plate_t = T(0.025)
    tob.location = (0, -plate_t / 2 - cu.extrude * 0.8, -size * 0.1)
    tob.rotation_euler = (pi / 2, 0, 0)
    return ob


FONT = None


def load_font():
    global FONT
    for p in ('C:/Windows/Fonts/arialbd.ttf', '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
              '/Library/Fonts/Arial Bold.ttf', '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
              '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'):
        if os.path.exists(p):
            try:
                FONT = bpy.data.fonts.load(p, check_existing=True)
                return
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Lighting, camera & render settings
# ---------------------------------------------------------------------------
def setup_world_and_lights(coll):
    sc = bpy.context.scene
    world = bpy.data.worlds.get('World') or bpy.data.worlds.new('World')
    sc.world = world
    world.use_nodes = True
    bg = next((n for n in world.node_tree.nodes if n.type == 'BACKGROUND'), None)
    if bg:
        _set(bg, 'Color', (0.42, 0.42, 0.40, 1))
        _set(bg, 'Strength', 0.45)

    def light(name, kind, loc, rot, energy, size=1.0, color=(1, 1, 1)):
        ld = bpy.data.lights.new(name, kind)
        ld.energy = energy
        ld.color = color
        if kind == 'AREA':
            ld.size = size
        elif kind == 'SUN':
            ld.angle = math.radians(size)
        lo = bpy.data.objects.new(name, ld)
        lo.location = loc
        lo.rotation_euler = rot
        coll.objects.link(lo)
        return lo

    light('Key_Sun', 'SUN', (0, 0, 20), (math.radians(42), 0, math.radians(-38)), 3.2, size=6,
          color=(1.0, 0.97, 0.92))
    light('Fill_Area', 'AREA', (-12, -8, 9), (math.radians(55), 0, math.radians(-55)), 4000, size=10,
          color=(0.92, 0.96, 1.0))
    light('Top_Softbox', 'AREA', (1, 1, 14), (0, 0, 0), 4500, size=14)
    light('Rim_Area', 'AREA', (6, 14, 8), (math.radians(-60), 0, math.radians(200)), 2500, size=8)


def setup_camera(coll):
    cd = bpy.data.cameras.new('Camera')
    cd.lens = 42
    cd.sensor_width = 36
    cam = bpy.data.objects.new('Camera', cd)
    cam.location = CAM_LOC
    cam.rotation_euler = (CAM_TARGET - CAM_LOC).to_track_quat('-Z', 'Y').to_euler()
    coll.objects.link(cam)
    focus = bpy.data.objects.new('Camera_Focus', None)
    focus.location = (0.4, -0.6, 0.6)
    coll.objects.link(focus)
    cd.dof.use_dof = True
    cd.dof.focus_object = focus
    cd.dof.aperture_fstop = 2.2
    bpy.context.scene.camera = cam
    return cam


def setup_render():
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.render.resolution_x = RES_X
    sc.render.resolution_y = RES_Y
    sc.render.resolution_percentage = 100
    sc.cycles.samples = RENDER_SAMPLES
    _try(sc.cycles, 'use_denoising', True)
    _try(sc.cycles, 'use_adaptive_sampling', True)
    _try(sc.cycles, 'max_bounces', 8)
    _try(sc.cycles, 'transparent_max_bounces', 16)
    for vt in ('AgX', 'Filmic'):
        try:
            sc.view_settings.view_transform = vt
            break
        except Exception:
            pass
    for lk in ('AgX - Medium High Contrast', 'Medium High Contrast'):
        try:
            sc.view_settings.look = lk
            break
        except Exception:
            pass
    try:
        prefs = bpy.context.preferences.addons['cycles'].preferences
        for t in ('OPTIX', 'CUDA', 'HIP', 'METAL', 'ONEAPI'):
            try:
                prefs.compute_device_type = t
                prefs.get_devices()
                if any(d.type != 'CPU' for d in prefs.devices):
                    break
            except Exception:
                pass
        gpu = False
        for d in prefs.devices:
            d.use = True
            gpu = gpu or d.type != 'CPU'
        if gpu:
            sc.cycles.device = 'GPU'
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def build():
    global PIPE_COLL, FITTINGS, BOARD_Y, MIN_T, GRASS_HAIR
    if PRINT:
        BOARD_Y = BOARD_X
        MIN_T = MIN_FEATURE_MM / print_scale()
        GRASS_HAIR = False
    reset_scene()
    build_materials()
    load_font()
    c_base = collection('Base')
    c_units = collection('Units')
    c_pipes = collection('Piping')
    c_labels = collection('Labels')
    c_veg = collection('Vegetation')
    c_veh = collection('Vehicles')
    c_light = collection('Lighting_Camera')
    PIPE_COLL = c_pipes
    FITTINGS = MB('Pipe_Fittings_Supports')

    build_base(c_base)
    build_roads(c_base)
    build_grass(c_base)

    # --- process units -----------------------------------------------------
    heat_exchanger(-4.7, 1.3, c_units)
    furnace(-2.7, 0.85, c_units)
    column('CatalyticCrackingUnit', -1.0, 3.2, 0.5, 6.9,
           plats=[1.5, 2.6, 3.7, 4.8, 5.9, 6.95], rt=0.42, zt=4.2, coll=c_units,
           nozzles=[(1.0, -90, 'manhole', 0.1), (3.2, -60, 'manhole', 0.1), (5.4, -120, 'manhole', 0.09),
                    (0.95, 0, 'n', 0.06), (2.1, 180, 'n', 0.05), (3.0, 30, 'n', 0.05), (4.4, -30, 'n', 0.045),
                    (6.3, 150, 'n', 0.045), (5.0, 60, 'n', 0.04), (1.9, -140, 'n', 0.04)])
    column('HydrotreatingUnit', 1.75, 3.1, 0.3, 3.9,
           plats=[1.4, 2.6, 3.95], rt=0.24, zt=3.0, head=0.6, coll=c_units,
           nozzles=[(0.9, -90, 'manhole', 0.08), (2.2, -110, 'manhole', 0.07), (0.7, 180, 'n', 0.05),
                    (1.8, 0, 'n', 0.04), (3.4, 160, 'n', 0.035), (2.9, -40, 'n', 0.035)])
    cooling_tower(-0.55, -0.85, c_units)
    water_tank(1.9, 0.15, 0.6, 1.25, c_units)
    sphere_tank('SphericalTank_1', 3.5, 3.3, 0.95, 1.55, 150, c_units)
    sphere_tank('SphericalTank_2', 5.75, 2.95, 0.9, 1.5, -45, c_units)
    flare_stack(4.75, 4.5, 8.1, c_units)
    storage_tank('ProductTank_1', 4.95, 0.1, 1.15, 1.75, 0, c_units)
    storage_tank('ProductTank_2', 4.85, -2.45, 1.15, 1.75, -100, c_units)
    office(-4.2, -2.0, c_units)
    loading_gantry(2.48, -3.0, c_units)

    # concrete pads / walkways
    pads = MB('Concrete_Pads')
    pad(pads, (-0.4, 0.95), (3.2, 0.5), 0.02)
    pad(pads, (1.9, 0.15), (1.5, 1.5), 0.02)
    pad(pads, (4.6, 3.3), (4.6, 2.6), 0.015)
    pad(pads, (-4.2, -2.0), (2.9, 2.0), 0.02)
    pad(pads, (0.3, 3.15), (4.0, 1.6), 0.015)
    pads.finish(c_base, bevel=0.005)

    # --- piping ------------------------------------------------------------
    pipe_rack(-3.3, 4.6, 2.0, c_units)
    # catalytic cracker overhead vapour line
    top = 6.9 + 0.55 * 0.42
    pipe('FCC_Overhead', [(-1.0, 3.2, top + 0.15), (-1.0, 3.2, top + 0.45), (-0.2, 3.2, top + 0.45),
                          (-0.2, 3.2, 1.25), (-0.2, 2.06, 1.25), (-0.2, 2.06, 1.07)], r=0.06, supports=False)
    pipe('FCC_Side1', [(-0.5, 3.4, 3.0), (-0.25, 3.6, 3.0), (-0.25, 3.6, 0.5), (-0.25, 2.11, 0.5),
                       (-0.25, 2.11, 0.75)], r=0.04, supports=False, valve=True)
    pipe('Furnace_Transfer', [(-1.83, 0.75, 1.05), (-1.55, 0.75, 1.05), (-1.55, 3.2, 1.05), (-1.48, 3.2, 1.05)],
         r=0.055, supports=False)
    pipe('Furnace_Feed', [(-3.55, 0.85, 1.25), (-3.95, 0.85, 1.25), (-3.95, 0.85, 1.75), (-4.3, 1.3, 1.75)],
         r=0.045, supports=False)
    pipe('HX_Feed', [(-4.3, 1.3, 1.69), (-4.3, 1.3, 1.75)], r=0.045, flanges=False, supports=False)
    pipe('HX_Channel', [(-5.67, 1.3, 1.67), (-5.67, 1.3, 1.9), (-5.67, 2.5, 1.9), (-5.67, 2.5, 0.85),
                        (-3.3, 2.5, 0.85), (-3.3, 2.09, 0.85), (-3.3, 2.09, 0.78)], r=0.045, supports=True)
    pipe('HX_Bottom', [(-5.67, 1.3, 0.9), (-5.67, 0.6, 0.9), (-5.67, 0.6, 0.35), (-3.75, 0.6, 0.35),
                       (-3.75, 0.1, 0.35)], r=0.04, valve=True)
    pipe('HX_Shell_Top', [(-5.1, 1.3, 1.67), (-5.1, 1.3, 2.05), (-3.3, 1.3, 2.05), (-3.3, 1.94, 2.05),
                          (-3.3, 1.94, 1.07)], r=0.04, supports=False)
    for i, x in enumerate((-0.2, 0.2)):
        pipe('CT_Line_%d' % i, [(x, 0.08, 0.55), (x, 0.75, 0.55), (x, 0.75, 0.9), (x, 1.9 + 0.1 * i, 0.9),
                                (x, 1.9 + 0.1 * i, 0.81)], r=0.045, supports=False, valve=(i == 0))
    pipe('CT_Furnace', [(-1.88, -0.4, 0.5), (-2.15, -0.4, 0.5), (-2.15, -0.4, 0.95), (-2.15, 0.2, 0.95)],
         r=0.04, supports=False)
    pipe('WaterTank_CT', [(1.38, 0.18, 0.25), (1.0, 0.18, 0.25), (1.0, 0.0, 0.25), (0.82, 0.0, 0.25)],
         r=0.04, supports=False)
    pipe('WaterTank_Rack', [(1.9, 0.87, 0.45), (1.9, 1.55, 0.45), (1.9, 1.55, 0.9), (1.9, 1.95, 0.9),
                            (1.9, 1.95, 1.07)], r=0.035, supports=False)
    pipe('Hydro_Overhead', [(1.75, 3.1, 3.9 + 0.6 * 0.24 + 0.16), (1.75, 3.1, 4.4), (2.3, 3.1, 4.4),
                            (2.3, 3.1, 1.2), (2.3, 2.1, 1.2), (2.3, 2.1, 1.07)], r=0.045, supports=False)
    pipe('Hydro_Bottom', [(1.25, 3.1, 0.7), (1.1, 3.1, 0.7), (1.1, 3.1, 0.35), (1.1, 2.0, 0.35),
                          (1.1, 2.0, 0.6)], r=0.04, supports=False, valve=True)
    pipe('Hydro_FCC', [(-0.5, 3.2, 2.1), (0.0, 3.2, 2.1), (0.0, 2.7, 2.1), (1.42, 2.7, 2.1), (1.42, 3.0, 2.1)],
         r=0.035, supports=False)
    pipe('Sphere1_Bottom', [(3.5, 3.3, 0.42), (3.5, 3.3, 0.28), (3.5, 2.2, 0.28), (3.5, 2.2, 0.68)],
         r=0.05, supports=False, valve=True)
    pipe('Sphere1_Top', [(3.73, 3.3, 2.62), (3.73, 3.3, 2.8), (3.73, 2.2, 2.8), (3.73, 2.2, 1.07)],
         r=0.035, supports=False)
    pipe('Sphere2_Bottom', [(5.75, 2.95, 0.42), (5.75, 2.95, 0.3), (5.75, 1.88, 0.3), (4.65, 1.88, 0.3),
                            (4.65, 1.88, 0.75)], r=0.05, supports=False, valve=True)
    pipe('Sphere2_Top', [(5.95, 2.95, 2.52), (5.95, 2.95, 2.7), (5.95, 1.95, 2.7), (4.7, 1.95, 2.7),
                         (4.7, 1.95, 1.07)], r=0.035, supports=False)
    pipe('Flare_Header', [(4.6, 2.12, 1.07), (4.6, 3.6, 1.07), (4.6, 3.6, 0.5), (4.75, 3.98, 0.5),
                          (4.75, 4.42, 0.5)], r=0.06, supports=False)
    pipe('Tank1_Out', [(3.82, 0.25, 0.28), (3.53, 0.25, 0.28), (3.53, -3.25, 0.28), (3.53, -3.25, 1.12),
                       (2.62, -3.25, 1.12)], r=0.04)
    pipe('Tank2_Out', [(3.76, -2.2, 0.28), (3.55, -2.2, 0.28)], r=0.04, flanges=False, supports=False)
    pipe('Rack_To_Tanks', [(4.62, 1.92, 0.75), (4.62, 1.5, 0.75), (4.62, 1.5, 0.45), (4.62, 1.33, 0.45)],
         r=0.04, supports=False)
    if FITTINGS.bm.verts:
        FITTINGS.finish(c_pipes)

    # --- vegetation, vehicles, lamps --------------------------------------
    variants = [make_tree_mesh('TreeVariant_%d' % i, SEED + i) for i in range(4)]
    scatter_trees(c_veg, variants)
    tanker_truck(1.6, -2.9, c_veh)
    street_lamps(c_base)

    # --- labels ------------------------------------------------------------
    sign('CATALYTIC\nCRACKING\nUNIT', (0.15, 3.0, 7.55), c_labels, anchor=(-0.55, 3.1, 7.2))
    sign('HYDROTREATING\nUNIT', (3.05, 2.5, 4.0), c_labels, anchor=(2.0, 3.0, 3.75))
    sign('FLARE\nSTACK', (6.0, 4.1, 7.0), c_labels, anchor=(4.95, 4.35, 6.9))
    sign('HEAT\nEXCHANGER', (-4.7, 0.75, 2.35), c_labels, anchor=(-4.7, 1.25, 1.85))
    sign('FURNACE', (-2.75, 0.12, 0.95), c_labels, anchor=(-2.75, 0.22, 0.95), size=0.18)
    sign('SPHERICAL\nTANK', (3.5, 2.25, 1.6), c_labels, anchor=(3.5, 2.37, 1.6), size=0.18)
    sign('SPHERICAL\nTANK', (5.75, 2.0, 1.55), c_labels, anchor=(5.75, 2.12, 1.55), size=0.18)
    sign('WATER\nTANK', (2.35, -0.72, 0.62), c_labels, size=0.18)
    sign('COOLING\nTOWER', (-0.55, -1.92, 0.72), c_labels, anchor=(-0.55, -1.77, 0.72), size=0.18)
    sign('PRODUCT\nSTORAGE TANKS', (4.05, -3.75, 0.95), c_labels, anchor=(4.3, -3.3, 0.95), size=0.18)
    sign('LOADING / UNLOADING\nAREA', (2.48, -4.55, 0.55), c_labels, size=0.18)

    setup_world_and_lights(c_light)
    setup_camera(c_light)
    setup_render()


def _cli_args():
    argv = sys.argv
    return argv[argv.index('--') + 1:] if '--' in argv else []


if __name__ == '__main__':
    build()
    args = _cli_args()
    if '--samples' in args:
        bpy.context.scene.cycles.samples = int(args[args.index('--samples') + 1])
    if '--percent' in args:
        bpy.context.scene.render.resolution_percentage = int(args[args.index('--percent') + 1])
    if '--no-hair' in args:
        for ob in bpy.data.objects:
            for m in list(ob.modifiers):
                if m.type == 'PARTICLE_SYSTEM':
                    ob.modifiers.remove(m)
    if '--save' in args:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args[args.index('--save') + 1]))
    if '--render' in args:
        sc = bpy.context.scene
        sc.render.filepath = os.path.abspath(args[args.index('--render') + 1])
        bpy.ops.render.render(write_still=True)
