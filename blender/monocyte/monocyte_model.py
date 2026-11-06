# -*- coding: utf-8 -*-
"""
Monocyte (Mononuclear Phagocyte) - 3D printable display model for Blender
=========================================================================

Builds the full relief model procedurally (no text-only placeholders):
  * Membrane: raised lip + wide ruffled lobed flange (like photo) (white)
  * Cytoplasm plate that drops into the membrane pocket          (light blue)
  * Kidney-shaped nucleus with chromatin texture                 (purple)
  * Rough ER cisternae + ribosomes                               (blue / yellow)
  * Smooth ER tubules                                            (cyan)
  * Golgi apparatus stack + vesicles                             (yellow-orange)
  * Mitochondria: outer rim + transverse cristae folds           (red)
  * Lysosomes                                                    (purple)
  * Cytoplasmic granules                                         (dark blue)
  * Pedestal base with cradle + peg, curved name plaque + text   (white / navy)
  * Optional info card with relief icons on its own stand

Every colour is its own object so it can be printed as a separate part
(FDM, multi-colour PLA) and exported as its own STL.

Units: 1 Blender unit = 1 mm (scene is set to millimetres).

How to use inside Blender:
  Scripting workspace -> Open this file -> Run Script.
Headless (builds, saves .blend, exports STL, renders previews):
  blender -b -P monocyte_model.py -- --export --render
"""

import bpy
import bmesh
import math
import os
import random
import sys
from mathutils import Vector, Matrix, Quaternion, noise, kdtree

# =====================================================================
# PARAMETERS  (millimetres) - edit these freely
# =====================================================================
TOTAL_HEIGHT = 250.0      # whole model incl. base
CELL_WIDTH = 185.0        # 17-19 cm
CELL_HEIGHT = 195.0
CELL_DEPTH = 65.0         # front lip crest -> back (the reference photo is a
                          # thin disc; the client brief said 140-160 mm)
BASE_W = 210.0            # base footprint X
BASE_D = 190.0            # base footprint Y
BASE_H = 45.0

ADD_TEXT = True           # name plaque text on the base
ADD_INFO_CARD = True      # separate legend card with relief icons
FIT_CLEARANCE = 0.25      # gap for parts that slot into each other
PEG_RADIUS = 8.0
SEED = 7

LIP_Z = 12.0              # membrane rim crest above cytoplasm surface
FLOOR_Z = -6.0            # pocket floor (= cytoplasm plate thickness)

# =====================================================================
# Colours (linear RGB) - match the reference photo
# =====================================================================
COLORS = {
    "White":      (0.95, 0.96, 0.98),
    "LightBlue":  (0.20, 0.46, 0.82),
    "Purple":     (0.28, 0.03, 0.70),
    "Blue":       (0.03, 0.22, 0.95),
    "Cyan":       (0.35, 0.68, 0.95),
    "Yellow":     (1.00, 0.45, 0.02),
    "Red":        (0.90, 0.07, 0.02),
    "Orange":     (1.00, 0.30, 0.05),
    "Violet":     (0.40, 0.10, 0.85),
    "DarkBlue":   (0.02, 0.12, 0.70),
    "RiboYellow": (1.00, 0.75, 0.10),
    "Navy":       (0.012, 0.035, 0.12),
}

rng = random.Random(SEED)
TAU = math.tau


# =====================================================================
# Generic helpers
# =====================================================================
def get_collection(name, parent=None):
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        (parent or bpy.context.scene.collection).children.link(coll)
    return coll


def get_material(key):
    name = "MAT_" + key
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    col = COLORS[key]
    bsdf.inputs["Base Color"].default_value = (*col, 1.0)
    bsdf.inputs["Roughness"].default_value = (0.12 if key == "White" else 0.2) if key != "Navy" else 0.35
    for nm, val in (("Coat Weight", 0.6), ("Coat Roughness", 0.08)):
        if nm in bsdf.inputs:
            bsdf.inputs[nm].default_value = val
    if key == "White" and "Subsurface Weight" in bsdf.inputs:
        bsdf.inputs["Subsurface Weight"].default_value = 0.15
        bsdf.inputs["Subsurface Radius"].default_value = (1.0, 1.0, 1.0)
        bsdf.inputs["Subsurface Scale"].default_value = 2.0
    mat.diffuse_color = (*col, 1.0)
    return mat


def mesh_object(name, verts, faces, coll, color=None, smooth=True,
                sharp_angle=None, matrix=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    me.validate(clean_customdata=False)
    me.update()
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    if smooth:
        me.shade_smooth()
        if sharp_angle is not None:
            me.set_sharp_from_angle(angle=math.radians(sharp_angle))
    if color:
        me.materials.append(get_material(color))
    if matrix is not None:
        ob.matrix_world = matrix
    return ob


def bm_object(name, bm, coll, color=None, smooth=True, sharp_angle=None,
              matrix=None):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    if smooth:
        me.shade_smooth()
        if sharp_angle is not None:
            me.set_sharp_from_angle(angle=math.radians(sharp_angle))
    if color:
        me.materials.append(get_material(color))
    if matrix is not None:
        ob.matrix_world = matrix
    return ob


class Geo:
    """Simple vertex/face accumulator (many small parts -> one object)."""

    def __init__(self):
        self.v = []
        self.f = []

    def add(self, verts, faces):
        o = len(self.v)
        self.v.extend(verts)
        self.f.extend([tuple(i + o for i in face) for face in faces])

    def extend(self, other):
        self.add(other.v, other.f)

    def to_bm(self):
        bm = bmesh.new()
        vs = [bm.verts.new(v) for v in self.v]
        for face in self.f:
            try:
                bm.faces.new([vs[i] for i in face])
            except ValueError:
                pass
        bm.verts.ensure_lookup_table()
        return bm


def apply_all_modifiers(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    new_me = bpy.data.meshes.new_from_object(ev)
    old = ob.data
    mats = list(old.materials)
    ob.modifiers.clear()
    ob.data = new_me
    new_me.materials.clear()
    for m in mats:
        new_me.materials.append(m)
    bpy.data.meshes.remove(old)


def boolean(target, cutter, op="DIFFERENCE"):
    mod = target.modifiers.new("bool", "BOOLEAN")
    mod.operation = op
    mod.solver = "EXACT"
    mod.object = cutter
    apply_all_modifiers(target)


def relief_frame(origin):
    """Local relief frame -> world.
    local X -> world X, local Y -> world Z (up), local Z (relief) -> world -Y
    (toward the viewer)."""
    ox, oy, oz = origin
    return Matrix(((1, 0, 0, ox),
                   (0, 0, -1, oy),
                   (0, 1, 0, oz),
                   (0, 0, 0, 1)))


def smoothstep(a, b, x):
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


# =====================================================================
# Relief primitives (built in local frame: flat back on z = 0, relief +z)
# =====================================================================
def sweep_relief(path, radius, n_along=60, n_around=24, hfac=1.0,
                 cap_rings=8, z_of=None):
    """Half-round tube swept along a planar path with a flat bottom and
    rounded (ellipsoidal) end caps.  Returns Geo.
    path(t)->(x, y); radius(t)->r ; t in [0,1]."""
    pts = [Vector(path(i / (n_along - 1))) for i in range(n_along)]
    rs = [radius(i / (n_along - 1)) for i in range(n_along)]
    tans = []
    for i in range(n_along):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, n_along - 1)]
        tans.append((b - a).normalized())

    rings = []  # (center, normal, r)
    t0, r0 = tans[0], rs[0]
    for k in range(cap_rings - 1, 0, -1):
        a = (k / cap_rings) * (math.pi / 2)
        rings.append((pts[0] - t0 * r0 * math.sin(a), t0, r0 * math.cos(a)))
    for i in range(n_along):
        rings.append((pts[i], tans[i], rs[i]))
    t1, r1 = tans[-1], rs[-1]
    for k in range(1, cap_rings):
        a = (k / cap_rings) * (math.pi / 2)
        rings.append((pts[-1] + t1 * r1 * math.sin(a), t1, r1 * math.cos(a)))
    tip0 = pts[0] - t0 * r0
    tip1 = pts[-1] + t1 * r1

    verts, faces = [], []
    m = n_around + 1
    for c, t, r in rings:
        n = Vector((-t.y, t.x))
        h = r * hfac
        for j in range(m):
            al = math.pi * j / n_around
            p = c + n * (r * math.cos(al))
            verts.append(Vector((p.x, p.y, h * math.sin(al))))
    nr = len(rings)
    for i in range(nr - 1):
        for j in range(m):
            j2 = (j + 1) % m
            faces.append((i * m + j, i * m + j2, (i + 1) * m + j2, (i + 1) * m + j))
    i_tip0 = len(verts)
    verts.append(Vector((tip0.x, tip0.y, 0)))
    i_tip1 = len(verts)
    verts.append(Vector((tip1.x, tip1.y, 0)))
    last = (nr - 1) * m
    for j in range(m):
        j2 = (j + 1) % m
        faces.append((i_tip0, j2, j))
        faces.append((i_tip1, last + j, last + j2))
    if z_of is not None:
        for v in verts:
            v.z += z_of(v.x, v.y)
    g = Geo()
    g.add(verts, faces)
    return g


def dome(cx, cy, r, h, seg=20, rings=8, z0=0.0):
    """Ellipsoidal dome (flat bottom) - granules, lysosomes, vesicles."""
    verts, faces = [], []
    for i in range(rings):
        a = (i / rings) * (math.pi / 2)
        rr, zz = r * math.cos(a), h * math.sin(a)
        for j in range(seg):
            b = TAU * j / seg
            verts.append(Vector((cx + rr * math.cos(b), cy + rr * math.sin(b), z0 + zz)))
    top = len(verts)
    verts.append(Vector((cx, cy, z0 + h)))
    bot = len(verts)
    verts.append(Vector((cx, cy, z0)))
    for i in range(rings - 1):
        for j in range(seg):
            j2 = (j + 1) % seg
            faces.append((i * seg + j, i * seg + j2, (i + 1) * seg + j2, (i + 1) * seg + j))
    lr = (rings - 1) * seg
    for j in range(seg):
        j2 = (j + 1) % seg
        faces.append((lr + j, lr + j2, top))
        faces.append((bot, j2, j))
    g = Geo()
    g.add(verts, faces)
    return g


def sphere(c, r, seg=12, rings=8):
    verts, faces = [], []
    for i in range(1, rings):
        a = math.pi * i / rings - math.pi / 2
        for j in range(seg):
            b = TAU * j / seg
            verts.append(c + Vector((r * math.cos(a) * math.cos(b),
                                     r * math.cos(a) * math.sin(b),
                                     r * math.sin(a))))
    s, n = len(verts), len(verts) + 1
    verts.append(c + Vector((0, 0, -r)))
    verts.append(c + Vector((0, 0, r)))
    for i in range(rings - 2):
        for j in range(seg):
            j2 = (j + 1) % seg
            faces.append((i * seg + j, i * seg + j2, (i + 1) * seg + j2, (i + 1) * seg + j))
    lr = (rings - 2) * seg
    for j in range(seg):
        j2 = (j + 1) % seg
        faces.append((s, j2, j))
        faces.append((lr + j, lr + j2, n))
    g = Geo()
    g.add(verts, faces)
    return g


def transform_geo(g, x, y, rot_deg=0.0, s=1.0):
    ca, sa = math.cos(math.radians(rot_deg)), math.sin(math.radians(rot_deg))
    out = Geo()
    out.add([Vector((x + s * (v.x * ca - v.y * sa),
                     y + s * (v.x * sa + v.y * ca), s * v.z)) for v in g.v], g.f)
    return out


def arc_path(cx, cy, r, a0, a1, wobble=0.0, wfreq=0.0, wphase=0.0):
    def f(t):
        a = math.radians(a0 + (a1 - a0) * t)
        rr = r + wobble * math.sin(wfreq * TAU * t + wphase)
        return (cx + rr * math.cos(a), cy + rr * math.sin(a))
    return f


# =====================================================================
# Organelles (relief, local frame)
# =====================================================================
NUCLEUS_LINE = [  # x, y (design mm), radius - measured from the reference photo
    (-4.0, 30.0, 12.0), (-16.0, 37.0, 15.0), (-31.0, 36.0, 16.5), (-39.0, 27.0, 19.5),
    (-40.0, 12.0, 23.0), (-35.0, -4.0, 19.5), (-23.0, -9.0, 17.0), (-8.0, -8.0, 15.0),
    (4.0, -5.0, 12.5)]
NUC_CX = sum(p[0] for p in NUCLEUS_LINE) / len(NUCLEUS_LINE)
NUC_CY = sum(p[1] for p in NUCLEUS_LINE) / len(NUCLEUS_LINE)


def catmull_path(pts):
    """Catmull-Rom through 2D points, t in [0, 1]."""
    n = len(pts)

    def f(t):
        g = min(max(t, 0.0), 1.0) * (n - 1)
        i = min(int(g), n - 2)
        u = g - i
        p0, p1, p2, p3 = pts[max(i - 1, 0)], pts[i], pts[i + 1], pts[min(i + 2, n - 1)]
        q = 0.5 * ((2 * p1) + (-p0 + p2) * u + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u * u
                   + (-p0 + 3 * p1 - 3 * p2 + p3) * u ** 3)
        return (q.x, q.y)
    return f


def make_nucleus(s=1.0, bump_amp=1.15, bump_cell=3.4, res=1.0, hfac=0.68):
    """Fat kidney-shaped nucleus (shallow notch opening to the right) with a
    cobbled chromatin surface.  Metaball blob along the measured centre-line,
    textured, then cut flat at z = 0."""
    pts = [Vector(((x - NUC_CX) * s, (y - NUC_CY) * s)) for x, y, _ in NUCLEUS_LINE]
    rads = [r * s for _, _, r in NUCLEUS_LINE]
    path = catmull_path(pts)
    mb = bpy.data.metaballs.new("mb_nucleus")
    mb.resolution = mb.render_resolution = max(0.25, 0.5 * s) / res
    mb.threshold = 0.6
    ob = bpy.data.objects.new("mb_nucleus", mb)
    bpy.context.scene.collection.objects.link(ob)
    n = 90
    for i in range(n + 1):
        t = i / n
        f = t * (len(rads) - 1)
        j = min(int(f), len(rads) - 2)
        u = f - j
        u = u * u * (3 - 2 * u)
        r = rads[j] * (1 - u) + rads[j + 1] * u
        x, y = path(t)
        e = mb.elements.new(type="ELLIPSOID")
        e.co = (x, y, 0.0)
        e.radius = r * 0.82 / 0.572
        e.size_x = e.size_y = 1.0
        e.size_z = hfac
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bpy.data.objects.remove(ob)
    bpy.data.metaballs.remove(mb)
    bpy.data.meshes.remove(me)
    bm.normal_update()
    cell = bump_cell * s
    for v in bm.verts:
        if v.co.z < 0.05:
            continue
        p = v.co / cell
        d, _ = noise.voronoi(p + Vector((3.1, 7.7, 1.3)), distance_metric="DISTANCE", exponent=2.5)
        f1 = d[0]
        bump = max(0.0, 1.0 - (f1 / 0.62) ** 2) ** 0.8
        fine = noise.noise(v.co * (2.2 / s)) * 0.18
        w = smoothstep(0.0, 4.0 * s, v.co.z)
        v.co += v.normal * (bump_amp * s * (bump + fine) * w)
    res_ = bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], dist=1e-5,
                                  plane_co=(0, 0, 0), plane_no=(0, 0, 1), clear_inner=True)
    cut = [e for e in res_["geom_cut"] if isinstance(e, bmesh.types.BMEdge)]
    for v in bm.verts:
        if abs(v.co.z) < 1e-4:
            v.co.z = 0.0
    filled = bmesh.ops.holes_fill(bm, edges=cut, sides=0)
    bmesh.ops.triangulate(bm, faces=filled["faces"])
    return bm


def make_rer(s=1.0, n=4, r0=50.0, a0=14.0, a1=64.0, spacing=6.2, tube=2.6,
             with_ribosomes=True, rib_r=1.15, res=1.0):
    body, ribo = Geo(), Geo()
    for k in range(n):
        R = (r0 + k * spacing) * s
        ph = k * 1.3
        aa0, aa1 = a0 - k * 1.5, a1 + k * 1.2
        path = arc_path(0, 0, R, aa0, aa1, wobble=1.1 * s, wfreq=2.0, wphase=ph)

        def rad(t, k=k):
            return s * tube * (1.0 + 0.18 * math.sin(TAU * 1.5 * t + k) + 0.25 * math.exp(-((t - 0.02) / 0.06) ** 2) + 0.25 * math.exp(-((t - 0.98) / 0.06) ** 2))
        body.extend(sweep_relief(path, rad, n_along=int(110 * res), n_around=int(20 * res), hfac=1.0, cap_rings=6))
        if with_ribosomes:
            arc_len = abs(math.radians(aa1 - aa0)) * R
            cnt = int(arc_len / (3.3 * s))
            for i in range(cnt):
                t = (i + 0.5) / cnt
                p0 = Vector(path(max(t - 0.004, 0)))
                p1 = Vector(path(min(t + 0.004, 1)))
                tg = (p1 - p0).normalized()
                nrm = Vector((-tg.y, tg.x))
                c = Vector(path(t))
                r = rad(t)
                for al in ((0.9,) if (i + k) % 2 else (math.pi - 0.9,)):
                    al2 = al + 0.2 * math.sin(i * 2.3 + k)
                    q = c + nrm * (r * math.cos(al2))
                    z = r * math.sin(al2)
                    ribo.extend(sphere(Vector((q.x, q.y, z)), rib_r * s, seg=10, rings=6))
    return body, ribo


def make_ser(s=1.0, res=1.0):
    g = Geo()
    specs = [  # radius, a0, a1, wobble, freq, tube
        (40, -8, 22, 3.0, 3.5, 2.3),
        (47, -14, 26, 3.4, 4.0, 2.3),
        (54, -18, 18, 3.0, 3.2, 2.2),
        (61, -12, 10, 2.6, 2.6, 2.1),
    ]
    for k, (R, a0, a1, wob, fr, tb) in enumerate(specs):
        path = arc_path(0, 0, R * s, a0, a1, wobble=wob * s, wfreq=fr, wphase=k * 1.7)
        g.extend(sweep_relief(path, lambda t, tb=tb: s * tb * (1 + 0.12 * math.sin(TAU * 4 * t)),
                              n_along=int(120 * res), n_around=int(18 * res), hfac=1.05, cap_rings=6))
    # a couple of short branches joining the tubules
    for (R, a, L) in ((43.5, 2, 9), (50.5, -4, 9), (57.5, 4, 8)):
        cx = R * math.cos(math.radians(a)) * s
        cy = R * math.sin(math.radians(a)) * s
        ang = math.radians(a)
        p0 = (cx - math.cos(ang) * L * 0.5 * s, cy - math.sin(ang) * L * 0.5 * s)
        p1 = (cx + math.cos(ang) * L * 0.5 * s, cy + math.sin(ang) * L * 0.5 * s)
        g.extend(sweep_relief(lambda t, p0=p0, p1=p1: (p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t),
                              lambda t: 1.7 * s, n_along=12, n_around=14, hfac=1.0, cap_rings=4))
    return g


def make_golgi(s=1.0, n=5, res=1.0, vesicles=True, arch=False, tube=2.05, yscale=1.0, r0=13.0, dr=5.4):
    """arch=True: stacked rainbow arcs (like the reference)."""
    body, ves = Geo(), Geo()
    for k in range(n):
        R = (r0 + k * dr) * s
        half = (52 - k * 2.5) if not arch else (68 - k * 3.0)
        mid = 90 if arch else 270
        a0, a1 = mid - half, mid + half

        def rad(t):
            # bulbous ends like real cisternae
            return s * tube * (1.0 + 0.55 * math.exp(-((t - 0.0) / 0.07) ** 2) + 0.55 * math.exp(-((t - 1.0) / 0.07) ** 2) - 0.1 * math.sin(math.pi * t))
        ap = arc_path(0, 0, R, a0, a1, wobble=0.5 * s, wfreq=1.5, wphase=k)
        path = (lambda t, ap=ap: (ap(t)[0], ap(t)[1] * yscale))
        body.extend(sweep_relief(path, rad, n_along=int(90 * res), n_around=int(18 * res), hfac=1.15, cap_rings=6))
    if vesicles:
        pts = [(-36, -12, 2.2), (-40, -20, 1.8), (37, -10, 2.3), (42, -18, 1.9),
               (-30, -46, 1.7), (31, -46, 1.9), (0, -48, 1.6), (-44, -30, 1.5), (46, -28, 1.6)]
        for x, y, r in pts:
            ves.extend(dome(x * s, (-y if arch else y) * s, r * s, r * s * 1.1, seg=14, rings=6))
    return body, ves


def make_rer_stack(n=3, length=32.0, spacing=7.5, sag=4.0, tube=3.0, rib_r=0.95, res=1.0, s=1.0):
    """Stack of short, thick curved cisternae (sausages) with one row of
    ribosome dots on top of each - like the reference."""
    body, ribo = Geo(), Geo()
    for k in range(n):
        y0 = (k - (n - 1) / 2) * spacing * s
        L = length * s * (1.0 - 0.06 * abs(k - (n - 1) / 2))
        ph = k * 1.7

        def path(t, y0=y0, L=L, ph=ph):
            u = 2 * t - 1
            return (u * L / 2, y0 + sag * s * (1 - u * u) + 0.8 * s * math.sin(TAU * t + ph))

        def rad(t):
            return s * tube * (1.0 + 0.08 * math.sin(TAU * 2 * t))
        body.extend(sweep_relief(path, rad, n_along=int(70 * res), n_around=int(22 * res), hfac=0.95, cap_rings=8))
        cnt = int(L / (3.4 * s))
        for i in range(cnt):
            t = (i + 0.5) / cnt
            c = Vector(path(t))
            ribo.extend(sphere(Vector((c.x, c.y + 0.6 * s * math.sin(i * 2.1), tube * s * 0.95 + rib_r * s * 0.45)),
                               rib_r * s, seg=10, rings=6))
    return body, ribo


SER_STRANDS = [  # design mm (absolute positions in the pocket)
    [(2.8, 18.6), (18.2, 25.0), (23.7, 22.4), (26.9, 5.9), (30.2, -1.8), (35.7, 8.4),
     (39.0, 19.9), (46.6, 22.4), (53.2, 13.5), (56.5, -4.3)],
    [(7.2, 10.4), (16.0, 9.6), (20.5, 3.5)],
]


def make_ser_loops(s=1.0, res=1.0, tube=4.0, strands=None):
    """Smooth ER: thick, flat-topped tubes meandering in U-turns."""
    g = Geo()
    for pts in (strands or SER_STRANDS):
        path = catmull_path([Vector((x * s, y * s)) for x, y in pts])
        g.extend(sweep_relief(path, lambda t: s * tube * (1 + 0.06 * math.sin(TAU * 3 * t)),
                              n_along=int(30 * len(pts) * res), n_around=int(20 * res),
                              hfac=0.9, cap_rings=8))
    return g


def revolve(profile, cx, cy, seg=24):
    """Solid of revolution around a vertical axis; profile = [(r, z), ...]
    from the bottom edge to the top centre (last r must be 0)."""
    verts, faces = [], []
    rings = profile[:-1]
    for r, z in rings:
        for j in range(seg):
            a = TAU * j / seg
            verts.append(Vector((cx + r * math.cos(a), cy + r * math.sin(a), z)))
    top = len(verts)
    verts.append(Vector((cx, cy, profile[-1][1])))
    bot = len(verts)
    verts.append(Vector((cx, cy, profile[0][1])))
    for i in range(len(rings) - 1):
        for j in range(seg):
            j2 = (j + 1) % seg
            faces.append((i * seg + j, i * seg + j2, (i + 1) * seg + j2, (i + 1) * seg + j))
    lr = (len(rings) - 1) * seg
    for j in range(seg):
        j2 = (j + 1) % seg
        faces.append((lr + j, lr + j2, top))
        faces.append((bot, j2, j))
    g = Geo()
    g.add(verts, faces)
    return g


def barrel(cx, cy, r, h, hole=True):
    """Short cylinder; with a hole on top like the reference granules."""
    if hole:
        ri = r * 0.45
        prof = [(r, 0.0), (r, h * 0.8), (r * 0.93, h * 0.97), (r * 0.8, h), (ri * 1.25, h),
                (ri, h * 0.9), (ri, h * 0.45), (0.0, h * 0.45)]
    else:
        prof = [(r, 0.0), (r, h * 0.78), (r * 0.9, h * 0.95), (r * 0.6, h), (0.0, h)]
    return revolve(prof, cx, cy, seg=28)


def sitting_sphere(cx, cy, r, lift=0.62, seg=28, rings=14):
    """Sphere whose centre is lift*r above the cytoplasm, cut flat at z=0."""
    zc = lift * r
    a0 = math.asin(-zc / r)                  # latitude of the cut
    prof = []
    for i in range(rings + 1):
        a = a0 + (math.pi / 2 - a0) * i / rings
        prof.append((r * math.cos(a), zc + r * math.sin(a)))
    prof[-1] = (0.0, zc + r)
    return revolve(prof, cx, cy, seg=seg)


def make_mito(s=1.0, L=27.0, W=12.4, res=1.0):
    """Oval mitochondrion (like the reference): raised outer-membrane rim,
    recessed matrix and transverse cristae folds alternating from both
    sides.  Built as a height-field on a stadium outline, flat back."""
    r = W / 2 * s
    hl = L / 2 * s - r
    H_rim, H_in, H_cr = 0.66 * r, 0.40 * r, 0.62 * r
    rw = 0.30 * r
    n_cr = max(3, int(round((2 * hl + 1.3 * r) / (3.2 * s))))
    span = 2 * hl + 1.25 * r
    xs_cr = [-span / 2 + span * (k + 0.5) / n_cr for k in range(n_cr)]
    wc = 0.95 * s

    def height(x, y):
        ds = math.hypot(max(abs(x) - hl, 0.0), y)
        e = r - ds
        if e <= 1e-6:
            return 0.0
        q = min(e / rw, 1.0)
        z_rim = H_rim * math.sqrt(max(0.0, 1 - (1 - q) ** 2))
        best = 0.0
        for k, xc in enumerate(xs_cr):
            side = 1.0 if k % 2 == 0 else -1.0
            ya, yb = side * r, side * (r - 1.5 * r)
            lo, hi = min(ya, yb), max(ya, yb)
            xx = xc + 0.18 * y
            dy = 0.0 if lo <= y <= hi else min(abs(y - lo), abs(y - hi))
            d = math.hypot(x - xx, dy)
            best = max(best, max(0.0, 1 - (d / wc) ** 2))
        z_in = H_in + (H_cr - H_in) * math.sqrt(best)
        t = smoothstep(rw * 0.9, rw * 2.0, e)
        return z_rim * (1 - t) + z_in * t + 0.10 * r * (1 - (ds / r) ** 2)

    nu, nv = int(150 * res), int(64 * res)
    top, bot = [], []
    for j in range(nv + 1):
        v = -1 + 2 * j / nv
        half = hl + r * math.sqrt(max(0.0, 1 - v * v))
        for i in range(nu + 1):
            u = -1 + 2 * i / nu
            x, y = u * half, v * r
            top.append(Vector((x, y, height(x, y))))
            bot.append(Vector((x, y, 0.0)))
    W1 = nu + 1
    faces = []
    off = len(top)
    for j in range(nv):
        for i in range(nu):
            a, b_, c, d = j * W1 + i, j * W1 + i + 1, (j + 1) * W1 + i + 1, (j + 1) * W1 + i
            faces.append((a, b_, c, d))
            faces.append((off + d, off + c, off + b_, off + a))
    g = Geo()
    g.add(top + bot, faces)
    bm = g.to_bm()
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    out = Geo()
    idx = {vv: n for n, vv in enumerate(bm.verts)}
    out.add([vv.co.copy() for vv in bm.verts], [tuple(idx[vv] for vv in f.verts) for f in bm.faces])
    bm.free()
    return out


# =====================================================================
# Membrane (white)
# =====================================================================
def r_ell(theta, a=1.0, b=1.045):
    c, s = math.cos(theta), math.sin(theta)
    return 1.0 / math.sqrt((c / a) ** 2 + (s / b) ** 2)


POCKET_R = 85.0     # nominal pocket radius (whole cell is scaled afterwards)


def pocket_radius(theta):
    n = noise.noise(Vector((math.cos(theta) * 1.5, math.sin(theta) * 1.5, 9.1)))
    return POCKET_R * r_ell(theta) * (1 + 0.018 * n)


def lobe_length(theta):
    """Length of the flange lobes around the cell (measured from the
    reference): long on the left, medium top/bottom, tiny on the right."""
    left = max(0.0, -math.cos(theta - 0.1))
    top = max(0.0, math.sin(theta))
    bottom = max(0.0, -math.sin(theta))
    right = max(0.0, math.cos(theta))
    return max(0.0, 3.0 + 40.0 * left + 17.0 * top * (1 - left) + 17.0 * bottom * (1 - left) - 3.0 * right)


def build_membrane(res=0.8, n_lobes=26):
    """Glossy white membrane like the reference photo:
    - raised rolled lip around the cytoplasm
    - a wide front-facing flange whose outer edge is cut into thick lobes
      with rounded points (a 'splash crown'), each lobe with a fold running
      from the lip to its tip
    - a shallow rounded back."""
    mb = bpy.data.metaballs.new("mb_membrane")
    mb.resolution = res
    mb.render_resolution = res
    mb.threshold = 0.6
    ob = bpy.data.objects.new("mb_membrane", mb)
    bpy.context.scene.collection.objects.link(ob)
    K = 1 / 0.572            # element radius -> visible surface radius
    rnd = random.Random(SEED + 11)

    def ball(x, y, z, R, sx=1.0, sy=1.0, sz=1.0, rot=0.0):
        e = mb.elements.new(type="ELLIPSOID")
        e.co = (x, y, z)
        e.radius = R * K
        e.size_x, e.size_y, e.size_z = sx, sy, sz
        if rot:
            e.rotation = Quaternion((0, 0, 1), rot)
        return e

    # shallow rounded back body
    rb = POCKET_R + 10
    ball(0, 0, -12, rb, sy=1.045, sz=40 / rb)
    for i in range(140):
        th = TAU * i / 140
        rp = pocket_radius(th)
        ball((rp - 8) * math.cos(th), (rp - 8) * math.sin(th), -12, 10)

    # flange band (front-facing ring behind the lobes)
    for i in range(200):
        th = TAU * i / 200
        rp = pocket_radius(th)
        rf = rp + 11 + 7.0 * max(0.0, -math.cos(th - 0.1))
        wave = math.cos(n_lobes / 2 * th) * min(1.0, lobe_length(th) / 12.0)
        ball(rf * math.cos(th), rf * math.sin(th), -3.0 + 3.0 * wave, 10.0, sz=0.72)

    # raised rolled lip around the cytoplasm
    n = 300
    for i in range(n):
        th = TAU * i / n
        rp = pocket_radius(th)
        rr = 8.6 + 0.3 * noise.noise(Vector((math.cos(th) * 3, math.sin(th) * 3, 2.0)))
        rc = rp + rr * 0.88
        z = 3.0 + 0.6 * math.sin(11 * th + 0.5)
        ball(rc * math.cos(th), rc * math.sin(th), z, rr)

    # lobes with a fold on each
    for i in range(n_lobes):
        th = TAU * (i + rnd.uniform(-0.08, 0.08)) / n_lobes
        ruffle = (5.5 if i % 2 == 0 else -6.5) * min(1.0, lobe_length(th) / 12.0)
        L = lobe_length(th) * rnd.uniform(0.85, 1.15)
        rp = pocket_radius(th)
        d = Vector((math.cos(th), math.sin(th)))
        tg = Vector((-d.y, d.x))
        curl = rnd.uniform(-0.12, 0.22)
        root = rp + 15.0 + 7.0 * max(0.0, -math.cos(th - 0.1))
        rroot = 13.0 if L > 8 else 9.0 + 0.5 * L
        steps = max(4, int(L / 1.2))
        for k in range(steps + 1):
            t = k / steps
            p = d * (root + L * t) + tg * (curl * L * t * t)
            rr = 5.0 + (rroot - 5.0) * (1 - t) ** 1.3
            ball(p.x, p.y, -2.0 - 5.0 * t * min(1.0, L / 20.0) + ruffle * min(1.0, 1.6 * t), rr, sz=0.92)
        # fold (crest) running from the lip to the lobe tip
        fl = (root + 0.8 * L) - (rp + 7.0)
        fsteps = max(4, int(fl / 1.4))
        for k in range(fsteps + 1):
            t = k / fsteps
            q = d * (rp + 7.0 + fl * t) + tg * (curl * L * (t * 0.8) ** 2)
            ball(q.x, q.y, 5.0 - 7.0 * t * min(1.0, L / 20.0) + ruffle * max(0.0, 1.6 * t - 0.4), 6.0 - 2.0 * t, sz=0.95)

    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bpy.data.objects.remove(ob)
    bpy.data.metaballs.remove(mb)
    bpy.data.meshes.remove(me)
    return bm


def pocket_cutter(sx, sy, ox, oy, n_theta=540, z0=FLOOR_Z, z1=80.0):
    verts = []
    for z in (z0, z1):
        for i in range(n_theta):
            th = TAU * i / n_theta
            r = pocket_radius(th)
            verts.append(Vector((r * math.cos(th) * sx + ox, r * math.sin(th) * sy + oy, z)))
    faces = [tuple(range(n_theta - 1, -1, -1)), tuple(range(n_theta, 2 * n_theta))]
    for i in range(n_theta):
        i2 = (i + 1) % n_theta
        faces.append((i, i2, n_theta + i2, n_theta + i))
    g = Geo()
    g.add(verts, faces)
    return g


def build_cytoplasm(sx, sy, n_theta=540, clearance=FIT_CLEARANCE, chamfer=0.8):
    rings = []
    for (z, inset) in ((FLOOR_Z, 0.0), (-chamfer, 0.0), (0.0, chamfer)):
        ring = []
        for i in range(n_theta):
            th = TAU * i / n_theta
            r = pocket_radius(th)
            x, y = r * math.cos(th) * sx, r * math.sin(th) * sy
            rho = math.hypot(x, y)
            k = (rho - clearance - inset) / rho
            ring.append(Vector((x * k, y * k, z)))
        rings.append(ring)
    verts = [v for ring in rings for v in ring]
    faces = []
    for p in range(2):
        for i in range(n_theta):
            i2 = (i + 1) % n_theta
            faces.append((p * n_theta + i, p * n_theta + i2, (p + 1) * n_theta + i2, (p + 1) * n_theta + i))
    cb = len(verts)
    verts.append(Vector((0, 0, FLOOR_Z)))
    ct = len(verts)
    verts.append(Vector((0, 0, 0)))
    for i in range(n_theta):
        i2 = (i + 1) % n_theta
        faces.append((cb, i2, i))
        faces.append((ct, 2 * n_theta + i, 2 * n_theta + i2))
    g = Geo()
    g.add(verts, faces)
    return g


def inside_pocket(x, y, sx, sy, margin):
    th = math.atan2(y / sy, x / sx)
    r = pocket_radius(th)
    px, py = r * math.cos(th) * sx, r * math.sin(th) * sy
    return math.hypot(x, y) < math.hypot(px, py) - margin


# =====================================================================
# Base / pedestal
# =====================================================================
BASE_PROFILE = [  # (radius factor, z)
    (0.0, 0.0), (0.975, 0.0), (0.995, 0.8), (1.0, 2.2), (1.0, 8.8), (0.99, 10.6),
    (0.955, 12.6), (0.92, 23.0), (0.885, 34.0), (0.872, 36.0), (0.875, 37.0),
    (0.902, 39.2), (0.906, 41.8), (0.896, 44.0), (0.875, BASE_H), (0.0, BASE_H)]


def base_r_at(z):
    """radius factor of the base body at height z (for the plaque wrap)."""
    for (r0, z0), (r1, z1) in zip(BASE_PROFILE[1:-1], BASE_PROFILE[2:-1]):
        if z0 <= z <= z1 and z1 > z0:
            return r0 + (r1 - r0) * (z - z0) / (z1 - z0)
    return BASE_PROFILE[-2][0]


def build_base_body(n=320):
    A, B = BASE_W / 2, BASE_D / 2
    prof = BASE_PROFILE
    verts, faces = [], []
    inner = prof[1:-1]
    for r, z in inner:
        for i in range(n):
            th = TAU * i / n
            verts.append((A * r * math.cos(th), B * r * math.sin(th), z))
    P = len(inner)
    for p in range(P - 1):
        for i in range(n):
            i2 = (i + 1) % n
            faces.append((p * n + i, p * n + i2, (p + 1) * n + i2, (p + 1) * n + i))
    b = len(verts)
    verts.append((0, 0, 0))
    t = len(verts)
    verts.append((0, 0, BASE_H))
    last = (P - 1) * n
    for i in range(n):
        i2 = (i + 1) % n
        faces.append((b, i2, i))
        faces.append((t, last + i, last + i2))
    return verts, faces


def wrap_on_base(u, z, h):
    """Map plaque coords (u = arc mm across the front, z height, h offset out
    of the surface) to world, following the curved front of the base."""
    f = base_r_at(z)
    A, B = BASE_W / 2 * f, BASE_D / 2 * f
    psi = u / A
    x, y = A * math.sin(psi), -B * math.cos(psi)
    nrm = Vector((math.sin(psi) / A, -math.cos(psi) / B)).normalized()
    return Vector((x + nrm.x * h, y + nrm.y * h, z))


def build_plaque(W=118.0, H=19.0, zc=24.0, rc=3.5, h0=-0.6, h1=2.0, nu=120):
    verts, faces = [], []
    cols = []
    for i in range(nu + 1):
        u = -W / 2 + W * i / nu
        d = abs(u) - (W / 2 - rc)
        cut = 0.0
        if d > 0:
            cut = rc - math.sqrt(max(rc * rc - d * d, 0.0))
        z0, z1 = zc - H / 2 + cut, zc + H / 2 - cut
        cols.append((u, z0, z1))
    for (u, z0, z1) in cols:
        verts += [wrap_on_base(u, z0, h1), wrap_on_base(u, z1, h1),
                  wrap_on_base(u, z0, h0), wrap_on_base(u, z1, h0)]
    for i in range(nu):
        a, b = 4 * i, 4 * (i + 1)
        faces.append((a + 0, b + 0, b + 1, a + 1))      # front
        faces.append((a + 2, a + 3, b + 3, b + 2))      # back
        faces.append((a + 1, b + 1, b + 3, a + 3))      # top
        faces.append((a + 0, a + 2, b + 2, b + 0))      # bottom
    e = 4 * nu
    faces.append((0, 1, 3, 2))
    faces.append((e + 0, e + 2, e + 3, e + 1))
    return verts, faces


def membrane_bottom_z(membrane, x, y):
    bpy.context.view_layer.update()
    Minv = membrane.matrix_world.inverted()
    dloc = (Minv.to_3x3() @ Vector((0, 0, 1))).normalized()
    o = Minv @ Vector((x, y, BASE_H - 20.0))
    hit, loc, _, _ = membrane.ray_cast(o, dloc)
    if not hit:
        return None
    return (membrane.matrix_world @ loc).z


def build_cradle(membrane, peg_y, peg_z, rx=30.0, ry=17.0, n_seg=96, n_ring=14, sink=4.0):
    """Pillar whose top follows the underside of the cell (height-field via
    ray casts) - the cell rests in it like in a saddle."""
    cy = peg_y

    def top_at(x, y):
        return membrane_bottom_z(membrane, x, y)

    verts, faces = [], []
    tops = []
    for k in range(1, n_ring + 1):
        f = k / n_ring
        ring = []
        for j in range(n_seg):
            a = TAU * j / n_seg
            x, y = rx * f * math.cos(a), cy + ry * f * math.sin(a)
            z = top_at(x, y)
            ring.append((x, y, z))
        tops.append(ring)
    zc = top_at(0, cy)
    zcap = peg_z + 28.0

    def clampz(z):
        if z is None or z > zcap:
            return BASE_H + 2.0
        return z + sink
    verts.append((0, cy, clampz(zc)))
    for ring in tops:
        for x, y, z in ring:
            verts.append((x, y, clampz(z)))
    # flared foot ring
    foot = len(verts)
    for j in range(n_seg):
        a = TAU * j / n_seg
        verts.append((rx * 1.22 * math.cos(a), cy + ry * 1.12 * math.sin(a), BASE_H - 1.0))
    bc = len(verts)
    verts.append((0, cy, BASE_H - 1.0))
    for j in range(n_seg):
        j2 = (j + 1) % n_seg
        faces.append((0, 1 + j, 1 + j2))
    for k in range(n_ring - 1):
        o0, o1 = 1 + k * n_seg, 1 + (k + 1) * n_seg
        for j in range(n_seg):
            j2 = (j + 1) % n_seg
            faces.append((o0 + j, o1 + j, o1 + j2, o0 + j2))
    lo = 1 + (n_ring - 1) * n_seg
    for j in range(n_seg):
        j2 = (j + 1) % n_seg
        faces.append((lo + j, foot + j, foot + j2, lo + j2))
        faces.append((bc, foot + j2, foot + j))
    g = Geo()
    g.add([Vector(v) for v in verts], faces)
    return bm_object("tmp_cradle", g.to_bm(), membrane.users_collection[0], "White")


# =====================================================================
# Text -> mesh
# =====================================================================
def text_geo(body, size, align="CENTER", thick=0.8):
    cu = bpy.data.curves.new("tmp_txt", "FONT")
    cu.body = body
    cu.size = size
    cu.align_x = align
    cu.align_y = "CENTER"
    cu.extrude = thick / 2
    cu.resolution_u = 4
    ob = bpy.data.objects.new("tmp_txt", cu)
    bpy.context.scene.collection.objects.link(ob)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0005)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    g = Geo()
    idx = {v: i for i, v in enumerate(bm.verts)}
    g.add([Vector((v.co.x, v.co.y, v.co.z + thick / 2)) for v in bm.verts],
          [tuple(idx[v] for v in f.verts) for f in bm.faces])
    bm.free()
    bpy.data.objects.remove(ob)
    bpy.data.curves.remove(cu)
    bpy.data.meshes.remove(me)
    return g


def rounded_rect_slab(x0, y0, x1, y1, rc, z0, z1, seg=8):
    pts = []
    corners = [(x1 - rc, y0 + rc, -90), (x1 - rc, y1 - rc, 0), (x0 + rc, y1 - rc, 90), (x0 + rc, y0 + rc, 180)]
    for cx, cy, a0 in corners:
        for k in range(seg + 1):
            a = math.radians(a0 + 90 * k / seg)
            pts.append((cx + rc * math.cos(a), cy + rc * math.sin(a)))
    n = len(pts)
    verts = [Vector((x, y, z0)) for x, y in pts] + [Vector((x, y, z1)) for x, y in pts]
    faces = [tuple(range(n - 1, -1, -1)), tuple(range(n, 2 * n))]
    for i in range(n):
        i2 = (i + 1) % n
        faces.append((i, i2, n + i2, n + i))
    g = Geo()
    g.add(verts, faces)
    return g


# =====================================================================
# BUILD
# =====================================================================
def clear_scene():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for coll in list(bpy.data.collections):
        bpy.data.collections.remove(coll)
    for blk in (bpy.data.meshes, bpy.data.curves, bpy.data.materials, bpy.data.lights, bpy.data.cameras):
        for d in list(blk):
            blk.remove(d)


def setup_units():
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.scale_length = 0.001
    sc.unit_settings.length_unit = "MILLIMETERS"
    for area in getattr(bpy.context.screen, "areas", []) if bpy.context.screen else []:
        if area.type == "VIEW_3D":
            for sp in area.spaces:
                if sp.type == "VIEW_3D":
                    sp.clip_start = 0.5
                    sp.clip_end = 100000
                    sp.overlay.grid_scale = 0.001


def build_model():
    random.seed(SEED)
    clear_scene()
    setup_units()
    c_cell = get_collection("Monocyte_Cell")
    c_base = get_collection("Monocyte_Base")

    # ---------------- membrane & scale ------------------------------
    mbm = build_membrane()
    xs = [v.co.x for v in mbm.verts]
    ys = [v.co.y for v in mbm.verts]
    sx = CELL_WIDTH / (max(xs) - min(xs))
    sy = CELL_HEIGHT / (max(ys) - min(ys))
    cx_off = -(max(xs) + min(xs)) / 2 * sx
    cy_off = -(max(ys) + min(ys)) / 2 * sy
    # depth: rim crest -> back of the body = CELL_DEPTH
    rim_z = max(v.co.z for v in mbm.verts
                if math.hypot(v.co.x, v.co.y) > pocket_radius(math.atan2(v.co.y, v.co.x)) + 1.0)
    zmin0 = min(v.co.z for v in mbm.verts)
    sz = CELL_DEPTH / (rim_z - zmin0)
    for v in mbm.verts:
        v.co = Vector((v.co.x * sx + cx_off, v.co.y * sy + cy_off, v.co.z * sz))
    zmax, zmin = rim_z * sz, zmin0 * sz

    cell_center_z = TOTAL_HEIGHT - CELL_HEIGHT / 2
    depth_mid = (zmax + zmin) / 2
    M = relief_frame((0.0, depth_mid, cell_center_z))   # world_y = depth_mid - z

    membrane = bm_object("Membrane_White", mbm, c_cell, "White", matrix=M)
    cutter = bm_object("tmp_pocket", pocket_cutter(sx, sy, cx_off, cy_off).to_bm(), c_cell, matrix=M)
    boolean(membrane, cutter, "DIFFERENCE")
    bpy.data.objects.remove(cutter)
    membrane.data.shade_smooth()

    cg = build_cytoplasm(sx, sy)
    for v in cg.v:
        v.x += cx_off
        v.y += cy_off
    bm_object("Cytoplasm_LightBlue", cg.to_bm(), c_cell, "LightBlue", sharp_angle=40, matrix=M)

    # organelle layout was designed for a ~74 x 81 mm pocket: map it into
    # the real pocket (uniform scale k, centred on the pocket)
    k = min(POCKET_R * sx / 74.4, POCKET_R * 1.045 * sy / 80.9)

    def ok(x, y, m):
        return inside_pocket(x - cx_off, y - cy_off, sx, sy, m)

    occupied = []   # (x, y) samples of organelle footprints

    def add_part(name, g_or_bm, color, sharp=None):
        bm = g_or_bm if isinstance(g_or_bm, bmesh.types.BMesh) else g_or_bm.to_bm()
        for v in bm.verts:
            v.co = Vector((cx_off + k * v.co.x, cy_off + k * v.co.y, k * v.co.z))
            if v.co.z < 0.6:
                occupied.append((v.co.x, v.co.y))
        return bm_object(name, bm, c_cell, color, sharp_angle=sharp, matrix=M)

    # Layout below is in "design mm" for a ~74 x 81 mm half-size pocket.
    # Every position / angle / size was measured from the reference photo.
    # ---------------- nucleus ---------------------------------------
    nb = make_nucleus()
    bmesh.ops.translate(nb, verts=nb.verts, vec=(NUC_CX, NUC_CY, 0.0))
    add_part("Nucleus_Purple", nb, "Purple")

    # ---------------- rough ER: two stacks top-right ----------------
    rer, ribo = Geo(), Geo()
    for (cx, cy, n, L, ang, sp) in ((1.0, 66.0, 3, 29.0, -18.0, 7.6), (27.0, 44.0, 3, 37.0, -28.0, 8.5)):
        b_, r_ = make_rer_stack(n=n, length=L, spacing=sp, tube=3.6, rib_r=1.0)
        rer.extend(transform_geo(b_, cx, cy, ang))
        ribo.extend(transform_geo(r_, cx, cy, ang))
    add_part("RoughER_Blue", rer, "Blue")
    add_part("RoughER_Ribosomes_Yellow", ribo, "RiboYellow")

    # ---------------- smooth ER: thick meander right-middle ----------
    add_part("SmoothER_Cyan", make_ser_loops(), "Cyan")

    # ---------------- golgi: flat rainbow stack + legs ---------------
    gb, gv = make_golgi(s=1.0, n=4, arch=True, tube=2.4, yscale=0.8, r0=12.0, dr=5.0, vesicles=False)
    golgi = transform_geo(gb, 20.4, -50.2, 0.0)
    for (x, y) in ((10.5, -55.5), (26.9, -55.5), (3.5, -52.5)):
        golgi.extend(sweep_relief(lambda t, x=x, y=y: (x, y + 2.5 - 5.0 * t), lambda t: 2.0,
                                  n_along=10, n_around=16, hfac=1.1, cap_rings=6))
    add_part("Golgi_Yellow", golgi, "Yellow")
    ves = Geo()
    for (x, y, r) in ((10.5, -60.0, 2.6), (27.5, -60.0, 2.6), (-0.5, -44.0, 2.3), (43.0, -45.0, 2.3)):
        ves.extend(sitting_sphere(x, y, r, lift=0.4, seg=20, rings=8))
    add_part("Golgi_Vesicles_Yellow", ves, "Yellow")

    # ---------------- mitochondria ----------------------------------
    mito_body = Geo()
    for (x, y, rot) in ((-47.0, -30.3, -47.5), (44.0, -17.1, -39.4), (49.3, -52.7, 43.7), (27.4, -67.5, -18.3)):
        mito_body.extend(transform_geo(make_mito(L=27.0, W=15.0), x, y, rot))
    add_part("Mitochondria_Red", mito_body, "Red")

    # ---------------- lysosomes (spheres) ----------------------------
    lyso = Geo()
    for x, y, r in ((-16.9, -42.5, 7.6), (55.4, -33.6, 5.0), (-28.2, 61.4, 4.0), (-31.1, -46.4, 2.8),
                    (65.9, -18.3, 3.0)):
        lyso.extend(sitting_sphere(x, y, r))
    add_part("Lysosomes_Violet", lyso, "Violet")

    # ---------------- hollow blue barrels ---------------------------
    bar = Geo()
    for x, y in ((-25.6, -54.0), (-15.1, -57.3), (-6.4, -52.2), (-1.5, -60.9), (-10.7, -67.5), (-22.3, -63.1)):
        bar.extend(barrel(x, y, 3.0, 4.2))
    add_part("Granules_Barrels_Blue", bar, "Blue")
    lbar = Geo()
    for x, y in ((14.9, -24.5), (21.0, -17.5)):
        lbar.extend(barrel(x, y, 3.0, 4.2))
    add_part("Granules_Barrels_LightCyan", lbar, "Cyan")

    # ---------------- granules (scatter) ----------------------------
    kd = kdtree.KDTree(len(occupied))
    for i, (x, y) in enumerate(occupied):
        kd.insert((x, y, 0.0), i)
    kd.balance()
    gran = Geo()
    placed = []
    tries = 0
    while len(placed) < int(150 * k * k) and tries < 40000:
        tries += 1
        x, y = cx_off + rng.uniform(-80, 80) * k, cy_off + rng.uniform(-85, 85) * k
        r = (rng.uniform(1.3, 2.0) if rng.random() < 0.75 else rng.uniform(2.0, 2.9)) * k
        if not ok(x, y, r + 2.2):
            continue
        _, _, d = kd.find((x, y, 0.0))
        if d is not None and d < r + 1.6:
            continue
        if any((x - px) ** 2 + (y - py) ** 2 < (r + pr + 3.2) ** 2 for px, py, pr in placed):
            continue
        placed.append((x, y, r))
        gran.extend(sitting_sphere(x, y, r, lift=0.35, seg=16, rings=6))
    bm_object("Granules_DarkBlue", gran.to_bm(), c_cell, "DarkBlue", matrix=M)

    # ---------------- base ------------------------------------------
    bv, bf = build_base_body()
    base = mesh_object("Base_White", bv, bf, c_base, "White", sharp_angle=28)

    # cradle stem: find lowest point of membrane under the cell
    mw = membrane.matrix_world
    low = min((mw @ v.co for v in membrane.data.vertices if abs(v.co.x) < 6), key=lambda p: p.z)
    # peg sits well behind the pocket floor (solid part of the dome)
    stem_y = depth_mid + 5.0   # under the bottom of the flange, below the pocket wall
    peg_bottom = membrane_bottom_z(membrane, 0.0, stem_y)
    stem = build_cradle(membrane, stem_y, peg_bottom)
    boolean(base, stem, "UNION")
    # carve the cradle so the cell sits snugly
    boolean(base, membrane, "DIFFERENCE")
    bpy.data.objects.remove(stem)
    # peg (on base) + hole (in membrane)
    peg_z0 = peg_bottom - 3.0
    for (r, L, target, op) in ((PEG_RADIUS, 18.0, base, "UNION"),
                               (PEG_RADIUS + FIT_CLEARANCE, 19.0, membrane, "DIFFERENCE")):
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=48, radius1=r, radius2=r if op == "DIFFERENCE" else r - 0.6,
                              depth=L, matrix=Matrix.Translation((0, stem_y, peg_z0 + L / 2)))
        cut = bm_object("tmp_peg", bm, c_base)
        boolean(target, cut, op)
        bpy.data.objects.remove(cut)
    base.data.shade_smooth()
    base.data.set_sharp_from_angle(angle=math.radians(28))

    # ---------------- plaque + text ---------------------------------
    pv, pf = build_plaque()
    mesh_object("Base_Plaque_Navy", pv, pf, c_base, "Navy", sharp_angle=30)
    if ADD_TEXT:
        tg = Geo()
        t1 = text_geo("Monocyte", 9.5, thick=1.0)
        for v in t1.v:
            v.y += 4.6
        tg.extend(t1)
        t2 = text_geo("Mononuclear Phagocyte", 5.0, thick=1.0)
        for v in t2.v:
            v.y -= 5.0
        tg.extend(t2)
        for sgn in (-1, 1):  # decorative rules beside the title
            tg.extend(rounded_rect_slab(sgn * 33 - 11, 4.2, sgn * 33 + 11, 4.9, 0.3, 0.0, 1.0, seg=2))
        verts = [wrap_on_base(v.x, 24.0 + v.y, 1.8 + v.z) for v in tg.v]
        mesh_object("Base_Text_White", verts, tg.f, c_base, "White", sharp_angle=30)

    if ADD_INFO_CARD:
        build_info_card()

    bpy.context.view_layer.update()
    return M


# =====================================================================
# Info card with relief icons
# =====================================================================
CARD_W, CARD_H, CARD_T = 92.0, 196.0, 4.0
CARD_POS = (178.0, -10.0)


def build_info_card():
    cc = get_collection("Monocyte_InfoCard")
    x0 = CARD_POS[0] - CARD_W / 2
    yfront = CARD_POS[1] - CARD_T / 2
    zbot = 6.0
    M = relief_frame((x0, yfront, zbot))   # local (0..W, 0..H), relief toward viewer

    plate = rounded_rect_slab(0, 0, CARD_W, CARD_H, 4.0, -CARD_T, 0.0)
    bm_object("Card_Plate_White", plate.to_bm(), cc, "White", sharp_angle=30, matrix=M)

    navy = Geo()
    navy.extend(rounded_rect_slab(3.5, CARD_H - 32, CARD_W - 3.5, CARD_H - 3.5, 3.0, -0.2, 0.8))
    navy.extend(rounded_rect_slab(3.5, 3.5, CARD_W - 3.5, 27.0, 3.0, -0.2, 0.8))
    white_txt = Geo()

    def put(g, x, y, z, store):
        for v in g.v:
            v.x += x
            v.y += y
            v.z += z
        store.extend(g)

    put(text_geo("Monocyte", 9.0, thick=0.8), CARD_W / 2, CARD_H - 15.0, 0.6, white_txt)
    put(text_geo("A Key Player in Innate Immunity", 3.5, thick=0.8), CARD_W / 2, CARD_H - 25.5, 0.6, white_txt)
    put(text_geo("Function:", 5.0, thick=0.8), CARD_W / 2, 20.5, 0.6, white_txt)
    put(text_geo("Phagocytosis, Immune Defense", 3.3, thick=0.8), CARD_W / 2, 13.5, 0.6, white_txt)
    put(text_geo("and Tissue Repair", 3.3, thick=0.8), CARD_W / 2, 8.3, 0.6, white_txt)

    rows = [
        ("Nucleus", ["Kidney-shaped,", "with loose chromatin"]),
        ("Rough ER", ["Synthesizes proteins", "(with ribosomes)"]),
        ("Smooth ER", ["Lipid metabolism &", "detoxification"]),
        ("Golgi Apparatus", ["Processes and", "packages proteins"]),
        ("Mitochondria", ["Site of cellular", "respiration"]),
        ("Lysosomes", ["Digest cellular waste"]),
        ("Cytoplasmic Granules", ["Contain enzymes and", "signaling molecules"]),
    ]
    top, bottom = CARD_H - 38.0, 32.0
    step = (top - bottom) / len(rows)
    for i, (title, lines) in enumerate(rows):
        yc = top - step * (i + 0.5)
        put(text_geo(title, 4.0, align="LEFT", thick=0.8), 31.0, yc + 4.2, -0.2, navy)
        for k, ln in enumerate(lines):
            put(text_geo(ln, 3.0, align="LEFT", thick=0.8), 31.0, yc - 0.6 - k * 3.9, -0.2, navy)

    icon_x = 16.0
    ys = [top - step * (i + 0.5) for i in range(len(rows))]
    parts = {}

    def add(key, g):
        parts.setdefault(key, Geo()).extend(g)

    # nucleus
    nb = make_nucleus(s=0.30, bump_amp=0.9, bump_cell=3.0, res=0.5)
    g = Geo()
    idx = {v: i for i, v in enumerate(nb.verts)}
    g.add([v.co.copy() for v in nb.verts], [tuple(idx[v] for v in f.verts) for f in nb.faces])
    nb.free()
    add("Purple", transform_geo(g, icon_x, ys[0], 0))
    # rough ER
    rer, ribo = make_rer_stack(n=3, length=34.0, spacing=8.0, sag=4.0, tube=3.0, rib_r=1.3, res=0.6, s=0.5)
    add("Blue", transform_geo(rer, icon_x, ys[1] - 1.0))
    add("RiboYellow", transform_geo(ribo, icon_x, ys[1] - 1.0))
    # smooth ER
    ser = Geo()
    for k in range(3):
        ser.extend(sweep_relief(lambda t, k=k: (-9 + 18 * t, -3.2 + 3.2 * k + 1.2 * math.sin(TAU * 2.2 * t + k)),
                                lambda t: 1.05, n_along=60, n_around=12, cap_rings=4))
    add("Cyan", transform_geo(ser, icon_x, ys[2]))
    # golgi
    gb, gv = make_golgi(s=0.27, n=4, res=0.5, vesicles=False, arch=True)
    add("Yellow", transform_geo(gb, icon_x, ys[3] - 7.5))
    # mitochondria
    add("Red", transform_geo(make_mito(s=0.62, res=0.6), icon_x, ys[4], 18))
    # lysosome
    add("Violet", dome(icon_x, ys[5], 4.2, 4.0, seg=28, rings=10))
    # granules
    for gx in (-5.5, 0, 5.5):
        for gy in (-2.5, 2.5):
            add("DarkBlue", dome(icon_x + gx, ys[6] + gy, 1.4, 1.3, seg=14, rings=5))

    bm_object("Card_Navy", navy.to_bm(), cc, "Navy", sharp_angle=30, matrix=M)
    bm_object("Card_Text_White", white_txt.to_bm(), cc, "White", sharp_angle=30, matrix=M)
    for key, g in parts.items():
        bm_object("Card_Icon_" + key, g.to_bm(), cc, key, matrix=M)

    # stand with slot
    st = rounded_rect_slab(-CARD_W / 2 - 4, -17, CARD_W / 2 + 4, 17, 6.0, 0.0, 14.0, seg=10)
    bm = st.to_bm()
    bmesh.ops.translate(bm, verts=bm.verts, vec=(CARD_POS[0], CARD_POS[1], 0.0))
    stand = bm_object("Card_Stand_White", bm, cc, "White", sharp_angle=30)
    slot = bmesh.new()
    bmesh.ops.create_cube(slot, size=1.0, matrix=Matrix.Translation((CARD_POS[0], CARD_POS[1], 10.0 + 4.01)) @
                          Matrix.Diagonal((CARD_W + 2 * FIT_CLEARANCE, CARD_T + 2 * FIT_CLEARANCE, 8.0, 1.0)))
    cut = bm_object("tmp_slot", slot, cc)
    boolean(stand, cut, "DIFFERENCE")
    bpy.data.objects.remove(cut)
    stand.data.shade_smooth()
    stand.data.set_sharp_from_angle(angle=math.radians(30))


# =====================================================================
# Studio scene (preview render only - not exported)
# =====================================================================
def build_studio():
    cs = get_collection("Studio_Preview")
    sc = bpy.context.scene
    # floor
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=1500)
    floor = bm_object("Studio_Floor", bm, cs)
    mat = bpy.data.materials.new("MAT_Marble")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 0.18
    tex = nt.nodes.new("ShaderNodeTexNoise")
    tex.inputs["Scale"].default_value = 0.004
    tex.inputs["Detail"].default_value = 12
    tex.inputs["Distortion"].default_value = 3.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.45
    ramp.color_ramp.elements[0].color = (0.55, 0.56, 0.58, 1)
    ramp.color_ramp.elements[1].position = 0.62
    ramp.color_ramp.elements[1].color = (0.82, 0.82, 0.83, 1)
    nt.links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    floor.data.materials.append(mat)

    # world: cool lab-blue gradient
    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    sc.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.30, 0.48, 0.85, 1)
    bg.inputs["Strength"].default_value = 0.8

    def light(name, loc, energy, size, rot, color=(1, 1, 1)):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy = energy
        ld.size = size
        ld.color = color
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        ob.rotation_euler = rot
        cs.objects.link(ob)
        # aim at the model
        d = Vector((40, 0, 130)) - Vector(loc)
        ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
        return ob

    light("Key", (-420, -520, 560), 4.0e6, 300, (0, 0, 0))
    light("Fill", (520, -380, 260), 1.6e6, 450, (0, 0, 0), (0.85, 0.92, 1.0))
    light("Rim", (120, 520, 520), 2.2e6, 300, (0, 0, 0), (0.75, 0.88, 1.0))
    light("Top", (0, -150, 700), 1.4e6, 250, (0, 0, 0))

    cam_d = bpy.data.cameras.new("Camera")
    cam_d.lens = 55
    cam_d.clip_start = 5
    cam_d.clip_end = 10000
    cam = bpy.data.objects.new("Camera", cam_d)
    cs.objects.link(cam)
    sc.camera = cam
    return cam


def aim(cam, loc, target):
    cam.location = loc
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()


def render_previews(out_dir, samples=96, res=(1600, 1200)):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = int(os.environ.get("MONO_RES_PCT", "100"))
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Punchy"
    cam = sc.camera
    shots = [
        ("preview_reference_angle.png", (-215, -455, 215), (-6, -25, 150), 66),
        ("preview_front_34.png", (-300, -640, 300), (60, 0, 125), 50),
        ("preview_front.png", (0, -760, 140), (0, 0, 140), 50),
        ("preview_cell_closeup.png", (-90, -420, 230), (-5, -40, 150), 50),
        ("preview_side.png", (-720, -60, 170), (0, 0, 125), 50),
    ]
    for fname, loc, tgt, lens in shots:
        aim(cam, loc, tgt)
        cam.data.lens = lens
        sc.render.filepath = os.path.join(out_dir, fname)
        bpy.ops.render.render(write_still=True)
        print("rendered", fname)


def export_stl(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    for coll_name in ("Monocyte_Cell", "Monocyte_Base", "Monocyte_InfoCard"):
        coll = bpy.data.collections.get(coll_name)
        if not coll:
            continue
        for ob in coll.objects:
            if ob.type != "MESH":
                continue
            bpy.ops.object.select_all(action="DESELECT")
            ob.select_set(True)
            bpy.context.view_layer.objects.active = ob
            path = os.path.join(out_dir, ob.name + ".stl")
            bpy.ops.wm.stl_export(filepath=path, export_selected_objects=True,
                                  apply_modifiers=True, ascii_format=False)
            print("exported", path)


# =====================================================================
if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    build_model()
    if bpy.app.background:
        here = os.path.dirname(os.path.abspath(__file__))
        if "--export" in argv:
            export_stl(os.path.join(here, "stl"))
        if "--render" in argv or "--blend" in argv:
            build_studio()
        if "--blend" in argv:
            bpy.ops.wm.save_as_mainfile(filepath=os.path.join(here, "Monocyte_Model.blend"), compress=True)
        if "--render" in argv:
            render_previews(os.path.join(here, "renders"),
                            samples=int(os.environ.get("MONO_SAMPLES", "96")))
    else:
        build_studio()
