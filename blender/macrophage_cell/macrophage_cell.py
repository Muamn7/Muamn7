"""
Macrophage / Phagocyte cell  -  high-detail procedural Blender model
=====================================================================

A 3D-printed-style educational model of a phagocytic cell: nucleus, rough ER,
Golgi, mitochondria, lysosomes, vesicles, the full phagocytosis pathway
(engulfed bacterium -> phagosome -> lysosomes -> phagolysosome -> residual
body), surface receptors, a display base and optional labels with leader lines.

HOW TO USE (Blender 4.0 or newer, tested on 5.1)
  1. Open Blender -> Scripting workspace -> Open this file -> Run Script.
     (Takes ~20-60 s: the cell body is built from a signed-distance field.)
  2. Or from a terminal:
       blender --background --python macrophage_cell.py -- \
               --save cell.blend --render cell.png --res 1600 2000 --samples 128

Everything is real geometry (no add-ons), organised into collections, and
every colour lives in the PALETTE dict below so you can restyle it quickly.
"""

import bpy
import bmesh
import math
import random
import sys
import numpy as np
from mathutils import Vector, Matrix

# --------------------------------------------------------------------------
# SETTINGS
# --------------------------------------------------------------------------
SEED = 11
VOXEL = 0.0105          # cell-body resolution (smaller = more detail, slower)
ADD_LABELS = True       # English callout labels like the reference photo
ADD_ENVIRONMENT = True  # wooden desk, wall, lights, cameras
LAYER_LINES = True      # subtle 3D-print layer lines on the plastic

PALETTE = {
    "body":        "#B59BD8",
    "body_dark":   "#A387CC",
    "nucleus":     "#6C43A8",
    "chromatin":   "#9370CF",
    "nucleolus":   "#5E3696",
    "nuc_env":     "#3F7FD8",
    "er":          "#3B78D2",
    "ribo_er":     "#1F2F78",
    "golgi":       "#E54B5A",
    "mito":        "#F2861F",
    "mito_in":     "#E7681A",
    "cristae":     "#B63A16",
    "lyso":        "#6CC531",
    "lyso_rim":    "#E5F3D3",
    "ves_blue":    "#2FA0E0",
    "ves_purple":  "#7E4CC0",
    "ves_green":   "#86CF45",
    "ribo_free":   "#7348AE",
    "bact":        "#38B12C",
    "bact_spot":   "#22801C",
    "phago_rim":   "#E9BCE7",
    "phago_in":    "#A586CF",
    "pl_rim":      "#EAA8CF",
    "pl_in":       "#C9A07A",
    "debris_or":   "#C0702E",
    "debris_br":   "#7B4A28",
    "res_rim":     "#DDD8E6",
    "res_in":      "#CFCBD4",
    "res_grain":   "#3A3742",
    "arrow":       "#F6F6F4",
    "r_prr":       "#8C3FA6",
    "r_fc":        "#2F63BE",
    "r_cr":        "#F0802A",
    "r_mhc":       "#24A39C",
    "r_other":     "#7B3B9E",
    "r_red":       "#C8445C",
    "r_green":     "#2E9E5B",
    "label_bg":    "#FBFBF8",
    "label_edge":  "#8E8E8E",
    "label_text":  "#1C1C1C",
    "leader":      "#2A2A2A",
    "wood_a":      "#B98451",
    "wood_b":      "#8C5A2E",
    "wall":        "#D8D0C2",
}

random.seed(SEED)
RNG = np.random.default_rng(SEED)
TAU = 2.0 * math.pi
Y_AXIS = Vector((0.0, 1.0, 0.0))

# --------------------------------------------------------------------------
# LAYOUT  (world units; the cell stands in the XZ plane, front faces -Y)
# --------------------------------------------------------------------------
CELL_C = (0.0, 1.68)
CELL_A, CELL_B = 0.86, 1.32
CELL_TILT = math.radians(-5)
H0, HD, R_EDGE = 0.11, 0.075, 0.10

NUC = (-0.49, 1.94)
NUC_R = (0.265, 0.395)
GOLGI = (-0.43, 1.12)

CUP_C, CUP_R = (0.06, 2.84), 0.21
PHAGOSOME = (0.10, 2.34, 0.145)
LYSO_TRIO = [(0.215, 2.075, 0.050), (0.318, 2.105, 0.046), (0.415, 1.995, 0.046)]
FUSION = [(0.20, 1.735, 0.150), (0.405, 1.66, 0.098)]
PHAGOLYSO = (0.37, 1.29, 0.160)
RESIDUAL_R = (0.39, 0.865, 0.122)
RESIDUAL_L = (-0.21, 0.57, 0.098)

# pseudopodia: (base xz, tip xz, base radius, tip radius, knob radius, y-scale)
PSEUDOPODS = [
    ((-0.30, 2.70), (-0.43, 3.02), 0.10, 0.060, 0.090, 1.15),   # top-left knob
    ((-0.60, 2.42), (-0.90, 2.53), 0.105, 0.060, 0.078, 1.10),
    ((-0.78, 2.05), (-0.96, 2.12), 0.090, 0.060, 0.062, 1.05),
    ((-0.80, 1.20), (-1.01, 1.08), 0.100, 0.070, 0.078, 1.10),
    ((-0.68, 0.70), (-0.95, 0.47), 0.120, 0.095, 0.118, 1.15),  # bulbous foot
    ((-0.52, 0.55), (-0.60, 0.10), 0.130, 0.115, 0.000, 1.20),  # legs on the base
    ((-0.18, 0.42), (-0.30, 0.07), 0.110, 0.100, 0.000, 1.15),
    ((0.28, 0.44), (0.36, 0.08), 0.110, 0.095, 0.000, 1.15),
    ((0.58, 0.58), (0.74, 0.20), 0.100, 0.080, 0.090, 1.10),
    ((0.68, 1.55), (1.28, 1.50), 0.120, 0.065, 0.085, 1.10),   # long right arm
    ((0.70, 0.98), (1.08, 0.84), 0.100, 0.060, 0.072, 1.05),
    ((0.58, 2.70), (0.78, 2.86), 0.090, 0.055, 0.068, 1.05),
    ((0.32, 2.86), (0.44, 3.01), 0.085, 0.055, 0.066, 1.05),
    ((-0.12, 2.86), (-0.16, 3.00), 0.080, 0.055, 0.060, 1.05),
]


# --------------------------------------------------------------------------
# COLOUR / MATERIALS
# --------------------------------------------------------------------------
def lin(hexstr, a=1.0):
    h = hexstr.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255.0
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return (out[0], out[1], out[2], a)


def set_in(node, names, value):
    if isinstance(names, str):
        names = [names]
    for n in names:
        if n in node.inputs:
            try:
                node.inputs[n].default_value = value
                return True
            except Exception:
                pass
    return False


def _fresh_tree(mat):
    try:
        mat.use_nodes = True
    except Exception:
        pass
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (700, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (400, 0)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    tc = nt.nodes.new("ShaderNodeTexCoord")
    tc.location = (-900, 0)
    return nt, bsdf, tc


def _bump(nt, height_socket, strength, distance, prev=None):
    b = nt.nodes.new("ShaderNodeBump")
    set_in(b, "Strength", strength)
    set_in(b, "Distance", distance)
    nt.links.new(height_socket, b.inputs["Height"])
    if prev is not None:
        nt.links.new(prev.outputs["Normal"], b.inputs["Normal"])
    return b


def _ramp(nt, fac_socket, stops):
    r = nt.nodes.new("ShaderNodeValToRGB")
    els = r.color_ramp.elements
    els[0].position, els[0].color = stops[0]
    els[1].position, els[1].color = stops[-1]
    for pos, col in stops[1:-1]:
        e = els.new(pos)
        e.color = col
    nt.links.new(fac_socket, r.inputs["Fac"])
    return r


def plastic(name, color, rough=0.42, sss=0.06, noise_bump=0.10, layer=True,
            color_var=0.0, coat=0.0, transmission=0.0):
    """3D-printed PLA look: soft subsurface, fine noise and layer lines."""
    mat = bpy.data.materials.new(name)
    nt, bsdf, tc = _fresh_tree(mat)
    base = lin(color)
    if color_var > 0:
        n = nt.nodes.new("ShaderNodeTexNoise")
        set_in(n, "Scale", 4.0)
        set_in(n, "Detail", 3.0)
        nt.links.new(tc.outputs["Object"], n.inputs["Vector"])
        dark = tuple(max(0.0, c * (1.0 - color_var)) for c in base[:3]) + (1.0,)
        lite = tuple(min(1.0, c * (1.0 + color_var)) for c in base[:3]) + (1.0,)
        r = _ramp(nt, n.outputs["Fac"], [(0.3, dark), (0.7, lite)])
        nt.links.new(r.outputs["Color"], bsdf.inputs["Base Color"])
    else:
        set_in(bsdf, "Base Color", base)
    set_in(bsdf, "Roughness", rough)
    if sss > 0:
        set_in(bsdf, ["Subsurface Weight", "Subsurface"], sss)
        set_in(bsdf, "Subsurface Radius", (1.0, 0.6, 0.45))
        set_in(bsdf, "Subsurface Scale", 0.015)
    if coat > 0:
        set_in(bsdf, ["Coat Weight", "Clearcoat"], coat)
    if transmission > 0:
        set_in(bsdf, ["Transmission Weight", "Transmission"], transmission)
    prev = None
    if noise_bump > 0:
        n2 = nt.nodes.new("ShaderNodeTexNoise")
        set_in(n2, "Scale", 70.0)
        set_in(n2, "Detail", 6.0)
        nt.links.new(tc.outputs["Object"], n2.inputs["Vector"])
        prev = _bump(nt, n2.outputs["Fac"], noise_bump, 0.003)
    if layer and LAYER_LINES:
        w = nt.nodes.new("ShaderNodeTexWave")
        w.wave_type = "BANDS"
        try:
            w.bands_direction = "Z"
        except Exception:
            pass
        set_in(w, "Scale", 42.0)
        nt.links.new(tc.outputs["Object"], w.inputs["Vector"])
        prev = _bump(nt, w.outputs["Fac"], 0.12, 0.0008, prev)
    if prev is not None:
        nt.links.new(prev.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def nucleus_material():
    mat = bpy.data.materials.new("Nucleus_Chromatin")
    nt, bsdf, tc = _fresh_tree(mat)
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    try:
        vor.feature = "DISTANCE_TO_EDGE"
    except Exception:
        pass
    set_in(vor, "Scale", 16.0)
    set_in(vor, "Randomness", 0.9)
    nt.links.new(tc.outputs["Object"], vor.inputs["Vector"])
    r = _ramp(nt, vor.outputs["Distance"],
              [(0.0, lin(PALETTE["chromatin"])), (0.07, lin(PALETTE["nucleus"])),
               (1.0, lin(PALETTE["nucleus"]))])
    nt.links.new(r.outputs["Color"], bsdf.inputs["Base Color"])
    set_in(bsdf, "Roughness", 0.45)
    set_in(bsdf, ["Subsurface Weight", "Subsurface"], 0.05)
    set_in(bsdf, "Subsurface Scale", 0.01)
    inv = nt.nodes.new("ShaderNodeMath")
    inv.operation = "SUBTRACT"
    inv.inputs[0].default_value = 0.08
    nt.links.new(vor.outputs["Distance"], inv.inputs[1])
    clamp = nt.nodes.new("ShaderNodeClamp")
    nt.links.new(inv.outputs[0], clamp.inputs["Value"])
    b = _bump(nt, clamp.outputs[0], 0.9, 0.004)
    nt.links.new(b.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def nucleolus_material():
    mat = bpy.data.materials.new("Nucleolus")
    nt, bsdf, tc = _fresh_tree(mat)
    set_in(bsdf, "Base Color", lin(PALETTE["nucleolus"]))
    set_in(bsdf, "Roughness", 0.42)
    w = nt.nodes.new("ShaderNodeTexWave")
    w.wave_type = "RINGS"
    try:
        w.rings_direction = "SPHERICAL"
    except Exception:
        pass
    set_in(w, "Scale", 9.0)
    set_in(w, "Distortion", 0.6)
    mp = nt.nodes.new("ShaderNodeMapping")
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    mp.inputs["Location"].default_value = (-(NUC[0] + 0.01), 0.0, -(NUC[1] - 0.01))
    nt.links.new(mp.outputs["Vector"], w.inputs["Vector"])
    b = _bump(nt, w.outputs["Fac"], 0.5, 0.003)
    nt.links.new(b.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def wood_material():
    mat = bpy.data.materials.new("Desk_Wood")
    nt, bsdf, tc = _fresh_tree(mat)
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (0.12, 1.0, 1.0)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    w = nt.nodes.new("ShaderNodeTexWave")
    w.wave_type = "BANDS"
    try:
        w.bands_direction = "Y"
    except Exception:
        pass
    set_in(w, "Scale", 2.2)
    set_in(w, "Distortion", 9.0)
    set_in(w, "Detail", 4.0)
    set_in(w, "Detail Scale", 1.5)
    nt.links.new(mp.outputs["Vector"], w.inputs["Vector"])
    r = _ramp(nt, w.outputs["Fac"],
              [(0.0, lin(PALETTE["wood_b"])), (0.45, lin(PALETTE["wood_a"])),
               (1.0, lin("#C99560"))])
    nt.links.new(r.outputs["Color"], bsdf.inputs["Base Color"])
    set_in(bsdf, "Roughness", 0.55)
    set_in(bsdf, ["Coat Weight", "Clearcoat"], 0.15)
    b = _bump(nt, w.outputs["Fac"], 0.08, 0.01)
    nt.links.new(b.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def flat_material(name, color, rough=0.6, emission=0.0):
    mat = bpy.data.materials.new(name)
    nt, bsdf, tc = _fresh_tree(mat)
    set_in(bsdf, "Base Color", lin(color))
    set_in(bsdf, "Roughness", rough)
    if emission > 0:
        set_in(bsdf, ["Emission Color", "Emission"], lin(color))
        set_in(bsdf, "Emission Strength", emission)
    return mat


MATS = {}


def build_materials():
    P = PALETTE
    MATS["body"] = plastic("Cell_Body", P["body"], rough=0.46, sss=0.08,
                           noise_bump=0.12, color_var=0.06)
    MATS["nucleus"] = nucleus_material()
    MATS["nucleolus"] = nucleolus_material()
    for key in ("nuc_env", "er", "ribo_er", "golgi", "mito", "mito_in", "cristae",
                "lyso", "ves_blue", "ves_purple", "ves_green", "ribo_free", "bact",
                "bact_spot", "phago_rim", "phago_in", "pl_rim", "pl_in", "debris_or",
                "debris_br", "res_rim", "res_in", "res_grain", "arrow", "r_prr",
                "r_fc", "r_cr", "r_mhc", "r_other", "r_red", "r_green"):
        MATS[key] = plastic(key.capitalize(), P[key], rough=0.40, sss=0.04,
                            noise_bump=0.06)
    MATS["lyso_rim"] = plastic("Lyso_rim", P["lyso_rim"], rough=0.25, sss=0.3,
                               noise_bump=0.03, transmission=0.25)
    MATS["label_bg"] = flat_material("Label_Plate", P["label_bg"], 0.5, 0.15)
    MATS["label_edge"] = flat_material("Label_Border", P["label_edge"], 0.5)
    MATS["label_text"] = flat_material("Label_Text", P["label_text"], 0.6)
    MATS["leader"] = flat_material("Leader_Line", P["leader"], 0.5)
    MATS["wood"] = wood_material()
    MATS["wall"] = flat_material("Wall", P["wall"], 0.9)
    MATS["base"] = plastic("Display_Base", P["body"], rough=0.44, sss=0.06,
                           noise_bump=0.08, color_var=0.04)


# --------------------------------------------------------------------------
# SCENE HELPERS
# --------------------------------------------------------------------------
def clean_scene():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.curves, bpy.data.materials,
                 bpy.data.lights, bpy.data.cameras):
        for b in list(coll):
            coll.remove(b)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)


COLLS = {}


def coll(name):
    if name not in COLLS:
        c = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(c)
        COLLS[name] = c
    return COLLS[name]


class MB:
    """Mesh builder: accumulate many primitives into one bmesh/object."""

    def __init__(self, name, mat_keys):
        self.name = name
        self.keys = list(mat_keys)
        self.bm = bmesh.new()

    def _mi(self, key):
        if key not in self.keys:
            self.keys.append(key)
        return self.keys.index(key)

    def _tag(self, verts, key):
        mi = self._mi(key)
        for f in {f for v in verts for f in v.link_faces}:
            f.material_index = mi
            f.smooth = True

    def sphere(self, c, radii, key, rot=None, seg=24, rings=14):
        if isinstance(radii, (int, float)):
            radii = (radii, radii, radii)
        m = Matrix.Translation(Vector(c))
        if rot is not None:
            m = m @ rot
        m = m @ Matrix.Diagonal((radii[0], radii[1], radii[2], 1.0))
        r = bmesh.ops.create_uvsphere(self.bm, u_segments=seg, v_segments=rings,
                                      radius=1.0, matrix=m)
        self._tag(r["verts"], key)

    def cone(self, c, direction, r1, r2, depth, key, yscale=1.0, seg=20):
        d = Vector(direction).normalized()
        rot = Vector((0, 0, 1)).rotation_difference(d).to_matrix().to_4x4()
        m = (Matrix.Translation(Vector(c)) @ Matrix.Diagonal((1, yscale, 1, 1)) @ rot)
        r = bmesh.ops.create_cone(self.bm, cap_ends=True, segments=seg, radius1=r1,
                                  radius2=r2, depth=depth, matrix=m)
        self._tag(r["verts"], key)

    def tube(self, pts, radius, key, closed=False, seg=12, ysc=1.0, caps=True):
        pts = [Vector(p) for p in pts]
        n = len(pts)
        if n < 2:
            return
        rads = radius if isinstance(radius, (list, tuple, np.ndarray)) else [radius] * n
        rings = []
        angs = [TAU * k / seg for k in range(seg)]
        for i, p in enumerate(pts):
            if closed:
                t = pts[(i + 1) % n] - pts[(i - 1) % n]
            else:
                t = pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]
            if t.length < 1e-9:
                t = Vector((1, 0, 0))
            t.normalize()
            N = Y_AXIS.cross(t)
            if N.length < 1e-5:
                N = Vector((1, 0, 0)).cross(t)
            N.normalize()
            B = t.cross(N)
            r = float(rads[i])
            rings.append([self.bm.verts.new(p + N * (r * math.cos(a)) + B * (r * ysc * math.sin(a)))
                          for a in angs])
        mi = self._mi(key)
        last = n if closed else n - 1
        for i in range(last):
            r0, r1 = rings[i], rings[(i + 1) % n]
            for j in range(seg):
                f = self.bm.faces.new((r0[j], r0[(j + 1) % seg], r1[(j + 1) % seg], r1[j]))
                f.material_index = mi
                f.smooth = True
        if caps and not closed:
            for idx in (0, n - 1):
                r = float(rads[idx])
                if r > 0.003:
                    self.sphere(pts[idx], (r, r * ysc, r), key, seg=seg, rings=max(6, seg // 2))

    def slab(self, outline_xz, y_front, thickness, key):
        """Closed flat solid from a 2D outline (list of (x,z)), front face at y_front."""
        bm = self.bm
        fr = [bm.verts.new((x, y_front, z)) for x, z in outline_xz]
        bk = [bm.verts.new((x, y_front + thickness, z)) for x, z in outline_xz]
        mi = self._mi(key)
        cx = sum(p[0] for p in outline_xz) / len(outline_xz)
        cz = sum(p[1] for p in outline_xz) / len(outline_xz)
        made = []
        f = bm.faces.new(fr)
        f.normal_update()
        if f.normal.y > 0:
            f.normal_flip()
        made.append(f)
        f = bm.faces.new(bk)
        f.normal_update()
        if f.normal.y < 0:
            f.normal_flip()
        made.append(f)
        n = len(outline_xz)
        for i in range(n):
            j = (i + 1) % n
            f = bm.faces.new((fr[i], fr[j], bk[j], bk[i]))
            f.normal_update()
            mid = (fr[i].co + fr[j].co) * 0.5
            if f.normal.dot(Vector((mid.x - cx, 0, mid.z - cz))) < 0:
                f.normal_flip()
            made.append(f)
        for f in made:
            f.material_index = mi
            f.smooth = False

    def finish(self, collection, smooth=True):
        me = bpy.data.meshes.new(self.name)
        self.bm.to_mesh(me)
        self.bm.free()
        for k in self.keys:
            me.materials.append(MATS[k])
        ob = bpy.data.objects.new(self.name, me)
        collection.objects.link(ob)
        return ob


# --------------------------------------------------------------------------
# SIGNED DISTANCE FIELD OF THE CELL BODY
# --------------------------------------------------------------------------
def smin(a, b, k):
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b * (1.0 - h) + a * h - k * h * (1.0 - h)


def smax(a, b, k):
    return -smin(-a, -b, k)


def _ellipse_q(X, Z):
    dx, dz = X - CELL_C[0], Z - CELL_C[1]
    ct, st = math.cos(CELL_TILT), math.sin(CELL_TILT)
    u = ct * dx + st * dz
    v = -st * dx + ct * dz
    a = CELL_A * (1.0 - 0.06 * v / CELL_B)       # a little narrower at the top
    b = CELL_B
    q = np.sqrt((u / a) ** 2 + (v / b) ** 2)
    g = np.sqrt((u / a ** 2) ** 2 + (v / b ** 2) ** 2) + 1e-9
    phi = np.arctan2(v, u)
    return u, v, q, g, phi


def sdf2d_cell(X, Z):
    u, v, q, g, phi = _ellipse_q(X, Z)
    d = (q - 1.0) * q / g
    d -= 0.022 * np.sin(5 * phi + 0.4) + 0.014 * np.sin(9 * phi + 1.7) + 0.008 * np.sin(14 * phi + 0.3)
    return d, q


def round_cone(X, Y, Z, a, b, ra, rb, ysc):
    px, pz = X - a[0], Z - a[1]
    dx, dz = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dz * dz
    t = np.clip((px * dx + pz * dz) / L2, 0.0, 1.0)
    qx, qz = px - t * dx, pz - t * dz
    return np.sqrt(qx * qx + qz * qz + (Y / ysc) ** 2) - (ra + (rb - ra) * t)


def sphere_sdf(X, Y, Z, c, r, ysc):
    return np.sqrt((X - c[0]) ** 2 + (Z - c[1]) ** 2 + (Y / ysc) ** 2) - r


def arc_tube(X, Y, Z, c, R, a0, a1, w, ysc):
    dx, dz = X - c[0], Z - c[1]
    ang = np.arctan2(dz, dx)
    span = a1 - a0
    rel = np.mod(ang - a0, TAU)
    out = rel > span
    relc = np.where(out, np.where((rel - span) < (TAU - rel), span, 0.0), rel)
    angc = a0 + relc
    px, pz = c[0] + R * np.cos(angc), c[1] + R * np.sin(angc)
    return np.sqrt((X - px) ** 2 + (Z - pz) ** 2 + (Y / ysc) ** 2) - w


def sdf_base(X, Y, Z):
    d2, q = sdf2d_cell(X, Z)
    h = H0 + HD * np.clip(1.0 - q * q, 0.0, 1.0)
    dx = d2 + R_EDGE
    dy = np.abs(Y) - h + R_EDGE
    d = (np.sqrt(np.maximum(dx, 0) ** 2 + np.maximum(dy, 0) ** 2)
         + np.minimum(np.maximum(dx, dy), 0.0) - R_EDGE)
    for a, b, ra, rb, kr, ysc in PSEUDOPODS:
        d = smin(d, round_cone(X, Y, Z, a, b, ra, rb, ysc), 0.09)
        if kr > 0:
            d = smin(d, sphere_sdf(X, Y, Z, b, kr, ysc), 0.035)
    # phagocytic cup: membrane arms wrapping the microbe + a deep pocket
    arms = arc_tube(X, Y, Z, CUP_C, CUP_R, math.radians(128), math.radians(52 + 360), 0.06, 2.0)
    d = smin(d, arms, 0.05)
    pocket = np.maximum(np.sqrt((X - CUP_C[0]) ** 2 + (Z - CUP_C[1]) ** 2) - (CUP_R - 0.03), Y - 0.035)
    d = smax(d, -pocket, 0.025)
    return d


RECESSES = []  # list of (circles[(x,z,r)], y_cut)


def sdf_full(X, Y, Z):
    d = sdf_base(X, Y, Z)
    for circles, ycut in RECESSES:
        c2 = None
        for cx, cz, r in circles:
            e = np.sqrt((X - cx) ** 2 + (Z - cz) ** 2) - r
            c2 = e if c2 is None else np.minimum(c2, e)
        rec = np.maximum(c2, Y - ycut)
        d = smax(d, -rec, 0.012)
    return d


def front_y(xs, zs, f=sdf_base):
    """Y of the front surface (first hit travelling +Y) for arrays of x,z."""
    xs = np.atleast_1d(np.asarray(xs, float))
    zs = np.atleast_1d(np.asarray(zs, float))
    ys = np.linspace(-0.6, 0.35, 191)
    X = xs[:, None] + 0 * ys[None, :]
    Z = zs[:, None] + 0 * ys[None, :]
    Y = ys[None, :] + 0 * xs[:, None]
    inside = f(X, Y, Z) < 0
    has = inside.any(axis=1)
    first = np.argmax(inside, axis=1)
    hi = ys[first]
    lo = ys[np.maximum(first - 1, 0)]
    for _ in range(22):
        mid = 0.5 * (lo + hi)
        ins = f(xs, mid, zs) < 0
        hi = np.where(ins, mid, hi)
        lo = np.where(ins, lo, mid)
    return np.where(has, hi, 0.0)


def fy(x, z):
    return float(front_y([x], [z])[0])


def edge_point(x, z, iters=30):
    """Project (x,z) onto the cell silhouette at y=0; return point and outward normal."""
    e = 1e-4
    p = np.array([x, z], float)
    for _ in range(iters):
        f0 = sdf_base(np.array([p[0]]), np.array([0.0]), np.array([p[1]]))[0]
        gx = (sdf_base(np.array([p[0] + e]), np.array([0.0]), np.array([p[1]]))[0] - f0) / e
        gz = (sdf_base(np.array([p[0]]), np.array([0.0]), np.array([p[1] + e]))[0] - f0) / e
        g2 = gx * gx + gz * gz + 1e-12
        p = p - f0 * np.array([gx, gz]) / g2
        if abs(f0) < 1e-5:
            break
    n = np.array([gx, gz])
    n /= np.linalg.norm(n) + 1e-12
    return (float(p[0]), float(p[1])), (float(n[0]), float(n[1]))


# --------------------------------------------------------------------------
# SURFACE NETS (numpy) -> smooth quad mesh from the SDF
# --------------------------------------------------------------------------
def surface_nets(sdf, lo, hi, step):
    xs = np.arange(lo[0], hi[0] + step, step, dtype=np.float32)
    ys = np.arange(lo[1], hi[1] + step, step, dtype=np.float32)
    zs = np.arange(lo[2], hi[2] + step, step, dtype=np.float32)
    nx, ny, nz = len(xs), len(ys), len(zs)
    F = np.empty((nx, ny, nz), np.float32)
    for i in range(nx):                      # slice-wise to keep memory low
        Y, Z = np.meshgrid(ys, zs, indexing="ij")
        F[i] = sdf(np.full_like(Y, xs[i]), Y, Z)
    inside = F < 0
    corners = [(i, j, k) for i in (0, 1) for j in (0, 1) for k in (0, 1)]
    edges = [(a, b) for a in range(8) for b in range(a + 1, 8)
             if sum(abs(corners[a][t] - corners[b][t]) for t in range(3)) == 1]
    cs = (nx - 1, ny - 1, nz - 1)
    vals = [F[c[0]:c[0] + cs[0], c[1]:c[1] + cs[1], c[2]:c[2] + cs[2]] for c in corners]
    acc = np.zeros(cs + (3,), np.float32)
    cnt = np.zeros(cs, np.float32)
    for a, b in edges:
        fa, fb = vals[a], vals[b]
        m = (fa < 0) != (fb < 0)
        t = np.where(m, fa / np.where(m, fa - fb, 1.0), 0.0)
        ca, cb = corners[a], corners[b]
        for ax in range(3):
            acc[..., ax] += np.where(m, ca[ax] + t * (cb[ax] - ca[ax]), 0.0)
        cnt += m
    active = cnt > 0
    idx = -np.ones(cs, np.int64)
    idx[active] = np.arange(int(active.sum()))
    gi = np.argwhere(active)
    verts = (gi + acc[active] / cnt[active][:, None]) * step + np.array(lo, np.float32)
    faces = []
    for axis in range(3):
        b_ax, c_ax = (axis + 1) % 3, (axis + 2) % 3
        sl_lo = [slice(1, -1)] * 3
        sl_hi = [slice(1, -1)] * 3
        sl_lo[axis] = slice(0, -1)
        sl_hi[axis] = slice(1, None)
        A = inside[tuple(sl_lo)]
        B = inside[tuple(sl_hi)]
        m = A != B
        nzs = np.nonzero(m)
        base = [nzs[0].copy(), nzs[1].copy(), nzs[2].copy()]
        for ax in range(3):
            if ax != axis:
                base[ax] += 1
        flip = A[m]

        def cell(db, dc):
            c = [base[0].copy(), base[1].copy(), base[2].copy()]
            c[b_ax] += db
            c[c_ax] += dc
            return idx[c[0], c[1], c[2]]

        q = np.stack([cell(-1, -1), cell(0, -1), cell(0, 0), cell(-1, 0)], axis=1)
        q[~flip] = q[~flip][:, ::-1]
        faces.append(q)
    faces = np.concatenate(faces, axis=0)
    return verts, faces


def build_cell_body():
    verts, faces = surface_nets(sdf_full, (-1.30, -0.42, -0.12), (1.52, 0.42, 3.30), VOXEL)
    me = bpy.data.meshes.new("Cell_Body")
    me.vertices.add(len(verts))
    me.vertices.foreach_set("co", verts.astype(np.float32).ravel())
    nf = len(faces)
    me.loops.add(nf * 4)
    me.loops.foreach_set("vertex_index", faces.astype(np.int32).ravel())
    me.polygons.add(nf)
    me.polygons.foreach_set("loop_start", np.arange(0, nf * 4, 4, dtype=np.int32))
    try:
        me.polygons.foreach_set("loop_total", np.full(nf, 4, np.int32))
    except Exception:
        pass
    me.update(calc_edges=True)
    me.validate()
    if hasattr(me, "shade_smooth"):
        me.shade_smooth()
    else:
        me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    me.materials.append(MATS["body"])
    ob = bpy.data.objects.new("Cell_Body", me)
    coll("Cell_Body").objects.link(ob)
    sm = ob.modifiers.new("Relax", "CORRECTIVE_SMOOTH")
    sm.iterations = 4
    sm.factor = 0.5
    try:
        sm.smooth_type = "LENGTH_WEIGHTED"
        sm.use_only_smooth = True
    except Exception:
        pass
    return ob


# --------------------------------------------------------------------------
# ORGANELLES
# --------------------------------------------------------------------------
OCC = []          # occupied discs (x, z, r) to keep things from overlapping
ANCHOR = {}       # label anchors


def occupy(x, z, r):
    OCC.append((x, z, r))


def is_free(x, z, margin=0.0):
    for ox, oz, r in OCC:
        if (x - ox) ** 2 + (z - oz) ** 2 < (r + margin) ** 2:
            return False
    return True


def interior(x, z, margin):
    d = sdf_base(np.array([x]), np.array([0.0]), np.array([z]))[0]
    return d < -margin


def ellipse_pts(c, rx, rz, n, wob=0.0, f=7, ph=0.0):
    out = []
    for i in range(n):
        t = TAU * i / n
        w = 1.0 + wob * math.sin(f * t + ph)
        out.append((c[0] + rx * w * math.cos(t), c[1] + rz * w * math.sin(t)))
    return out


def build_nucleus():
    c = coll("Nucleus")
    x, z = NUC
    y0 = fy(x, z)
    mb = MB("Nucleus", ["nucleus"])
    mb.sphere((x, y0 + 0.03, z), (NUC_R[0], 0.10, NUC_R[1]), "nucleus", seg=64, rings=40)
    mb.finish(c)
    # nucleolus
    nl = MB("Nucleolus", ["nucleolus"])
    ny = y0 + 0.03 - 0.10 + 0.012
    nl.sphere((x + 0.01, ny, z - 0.01), (0.072, 0.034, 0.072), "nucleolus", seg=40, rings=20)
    nl.finish(c)
    # nuclear envelope: thick blue band + thin inner line + pores
    env = MB("Nuclear_Envelope", ["nuc_env", "ribo_er"])
    ring = ellipse_pts(NUC, NUC_R[0] * 1.07, NUC_R[1] * 1.055, 160, 0.012, 11)
    ys = front_y([p[0] for p in ring], [p[1] for p in ring])
    env.tube([(p[0], yy - 0.005, p[1]) for p, yy in zip(ring, ys)], 0.030, "nuc_env",
             closed=True, seg=14, ysc=0.85)
    inner = ellipse_pts(NUC, NUC_R[0] * 0.985, NUC_R[1] * 0.99, 140)
    yi = front_y([p[0] for p in inner], [p[1] for p in inner])
    env.tube([(p[0], yy - 0.012, p[1]) for p, yy in zip(inner, yi)], 0.010, "nuc_env",
             closed=True, seg=8, ysc=0.8)
    for i in range(46):
        t = TAU * i / 46 + 0.03
        px = NUC[0] + NUC_R[0] * 1.17 * math.cos(t)
        pz = NUC[1] + NUC_R[1] * 1.12 * math.sin(t)
        env.sphere((px, fy(px, pz) - 0.008, pz), (0.016, 0.013, 0.016), "nuc_env", seg=12, rings=8)
    for i in range(30):
        t = TAU * i / 30 + 0.1
        px = NUC[0] + NUC_R[0] * 1.07 * math.cos(t)
        pz = NUC[1] + NUC_R[1] * 1.055 * math.sin(t)
        env.sphere((px, fy(px, pz) - 0.033, pz), 0.0085, "ribo_er", seg=10, rings=6)
    env.finish(c)
    ANCHOR["nucleus"] = (x - 0.10, z + 0.30, y0 - 0.06)
    ANCHOR["nuc_env"] = (NUC[0] + NUC_R[0] * 1.07 * math.cos(2.55),
                         NUC[1] + NUC_R[1] * 1.055 * math.sin(2.55), None)
    ANCHOR["chromatin"] = (x - 0.15, z + 0.06, y0 - 0.06)
    ANCHOR["nucleolus"] = (x - 0.02, z, ny - 0.03)


def build_er():
    c = coll("Rough_ER")
    mb = MB("Rough_ER", ["er", "ribo_er"])
    first_left = None
    for i in range(6):
        ra = 0.335 + i * 0.040
        rb = 0.470 + i * 0.043
        th0 = math.radians(108 - 3 * i + random.uniform(-6, 6))
        th1 = math.radians(-200 + 7 * i + random.uniform(-6, 6))
        n = 220
        ts = np.linspace(th0, th1, n)
        cand = []
        for t in ts:
            wob = 0.012 * math.sin(10 * t + i * 1.3) + 0.006 * math.sin(19 * t + i)
            x = NUC[0] + (ra + wob) * math.cos(t)
            z = NUC[1] + (rb + wob * 1.2) * math.sin(t)
            ok = interior(x, z, 0.075) and is_free(x, z, 0.035)
            cand.append((x, z, ok))
        # random gaps for a fragmented, folded look
        gap_at = set(random.sample(range(20, n - 20), 2))
        segs, cur = [], []
        for k, (x, z, ok) in enumerate(cand):
            if ok and k not in gap_at and not any(abs(k - g) < 4 for g in gap_at):
                cur.append((x, z))
            else:
                if len(cur) > 6:
                    segs.append(cur)
                cur = []
        if len(cur) > 6:
            segs.append(cur)
        for seg in segs:
            ys = front_y([p[0] for p in seg], [p[1] for p in seg])
            pts = [(p[0], yy + 0.002, p[1]) for p, yy in zip(seg, ys)]
            mb.tube(pts, 0.019, "er", seg=10, ysc=0.75)
            for k in range(2, len(pts) - 2, 3):
                p0, p1 = Vector(pts[k - 1]), Vector(pts[k + 1])
                t = (p1 - p0).normalized()
                nrm = Y_AXIS.cross(t).normalized()
                side = 1 if (k // 3) % 2 == 0 else -1
                q = Vector(pts[k]) + nrm * side * 0.026 + Vector((0, -0.010, 0))
                mb.sphere(q, 0.0078, "ribo_er", seg=8, rings=5)
            if i == 4:
                cand_l = min(seg, key=lambda p: (p[0] + 0.72) ** 2 + (p[1] - 1.58) ** 2)
                if first_left is None or ((cand_l[0] + 0.72) ** 2 + (cand_l[1] - 1.58) ** 2 <
                                          (first_left[0] + 0.72) ** 2 + (first_left[1] - 1.58) ** 2):
                    first_left = cand_l
    mb.finish(c)
    if first_left:
        ANCHOR["er"] = (first_left[0], first_left[1], None)


def build_golgi():
    c = coll("Golgi_Apparatus")
    gx, gz = GOLGI
    mb = MB("Golgi_Apparatus", ["golgi"])
    ends = []
    for i in range(5):
        w = 0.205 - 0.022 * abs(i - 1.5) + random.uniform(-0.01, 0.01)
        zoff = (i - 2) * 0.046
        pts2 = []
        for s in np.linspace(-1, 1, 60):
            x = gx + s * w
            z = gz + zoff + 0.075 * (1 - s * s) + 0.010 * math.sin(s * 13 + i * 1.7)
            pts2.append((x, z))
        ys = front_y([p[0] for p in pts2], [p[1] for p in pts2])
        pts = [(p[0], yy - 0.002, p[1]) for p, yy in zip(pts2, ys)]
        rads = [0.0165 + 0.009 * abs(s) ** 4 for s in np.linspace(-1, 1, 60)]
        mb.tube(pts, rads, "golgi", seg=12, ysc=0.8)
        ends += [pts[0], pts[-1]]
    for e in ends:
        for _ in range(1):
            off = Vector((random.uniform(-0.05, 0.05), 0, random.uniform(-0.04, 0.04)))
            p = Vector(e) + off + Vector((math.copysign(0.035, e[0] - gx), 0, 0))
            r = random.uniform(0.011, 0.018)
            mb.sphere((p.x, fy(p.x, p.z) - r * 0.4, p.z), (r, r * 0.8, r), "golgi", seg=12, rings=8)
    mb.finish(c)
    occupy(gx, gz + 0.02, 0.24)
    ANCHOR["golgi"] = (gx - 0.17, gz + 0.02, None)


def build_mito(name, c, L, w, ang):
    x, z = c
    y0 = fy(x, z)
    rot = Matrix.Rotation(-ang, 4, "Y")
    mb = MB(name, ["mito", "mito_in", "cristae"])
    mb.sphere((x, y0 + 0.01, z), (L, 0.055, w), "mito", rot=rot, seg=48, rings=24)
    mb.sphere((x, y0 + 0.002, z), (L * 0.84, 0.052, w * 0.70), "mito_in", rot=rot, seg=40, rings=20)
    ax = Vector((math.cos(ang), 0, math.sin(ang)))
    pr = Vector((-math.sin(ang), 0, math.cos(ang)))
    pts = []
    for s in np.linspace(-0.74, 0.74, 140):
        amp = w * 0.55 * math.sqrt(max(0.0, 1 - (s / 0.84) ** 2))
        tri = 2 / math.pi * math.asin(math.sin(s * L * 2 * math.pi / (L * 0.27)))
        p = Vector((x, 0, z)) + ax * (s * L) + pr * (amp * tri)
        pts.append(p)
    ys = front_y([p.x for p in pts], [p.z for p in pts])
    pts = [(p.x, min(yy, y0) - 0.044, p.z) for p, yy in zip(pts, ys)]
    mb.tube(pts, 0.0115, "cristae", seg=8, ysc=0.7)
    mb.finish(coll("Mitochondria"))
    occupy(x, z, L + 0.02)
    return (x, z, y0 - 0.05)


def blob(mb, x, z, r, key, rim_key=None, ysc=0.62):
    y0 = fy(x, z)
    mb.sphere((x, y0 + r * 0.25, z), (r, r * ysc, r), key, seg=24, rings=14)
    if rim_key:
        ring = ellipse_pts((x, z), r * 1.05, r * 1.05, 40)
        mb.tube([(p[0], y0 - 0.004, p[1]) for p in ring], r * 0.22, rim_key, closed=True,
                seg=10, ysc=0.8)
    occupy(x, z, r * 1.25)


def build_cytoplasm_bits():
    vc = coll("Vesicles_Lysosomes")
    mb = MB("Vesicles_Lysosomes", ["lyso", "lyso_rim", "ves_blue", "ves_purple", "ves_green"])
    # lysosomes (green core + pale rim)
    for x, z, r in [(-0.315, 0.825, 0.055), (0.06, 1.185, 0.030), (-0.03, 1.09, 0.022),
                    (-0.20, 1.42, 0.026)]:
        blob(mb, x, z, r, "lyso", "lyso_rim")
    # endosomes / vesicles
    for x, z, r, k in [(0.135, 0.99, 0.047, "ves_blue"), (0.12, 1.155, 0.034, "ves_blue"),
                       (-0.135, 0.735, 0.050, "ves_purple"), (0.045, 0.72, 0.038, "ves_purple"),
                       (-0.285, 0.675, 0.022, "ves_purple"), (0.24, 0.62, 0.026, "ves_green"),
                       (0.10, 1.36, 0.022, "ves_green"), (-0.05, 1.27, 0.018, "ves_blue"),
                       (0.55, 0.62, 0.024, "ves_blue"), (-0.70, 1.55, 0.022, "ves_purple")]:
        blob(mb, x, z, r, k)
    # secretory vesicles (purple with light rim)
    for x, z, r in [(-0.375, 0.585, 0.042), (-0.48, 0.705, 0.020), (-0.43, 0.47, 0.022)]:
        blob(mb, x, z, r, "ves_purple", "lyso_rim")
    mb.finish(vc)
    ANCHOR["lyso_l"] = (-0.315, 0.825, None)
    ANCHOR["vesicle"] = (-0.135, 0.735, None)
    ANCHOR["secretory"] = (-0.375, 0.585, None)


def build_free_ribosomes():
    mb = MB("Free_Ribosomes", ["ribo_free", "ves_blue", "ves_green"])
    pts, tries = [], 0
    while len(pts) < 230 and tries < 20000:
        tries += 1
        x = random.uniform(-0.95, 0.95)
        z = random.uniform(0.35, 3.0)
        if not interior(x, z, 0.06) or not is_free(x, z, 0.03):
            continue
        if ((x - NUC[0]) / 0.57) ** 2 + ((z - NUC[1]) / 0.72) ** 2 < 1.0 and \
                math.atan2(z - NUC[1], x - NUC[0]) < math.radians(112):
            continue
        if any((x - a) ** 2 + (z - b) ** 2 < 0.045 ** 2 for a, b, _ in pts):
            continue
        r = random.uniform(0.008, 0.014)
        pts.append((x, z, r))
    ys = front_y([p[0] for p in pts], [p[1] for p in pts])
    for (x, z, r), yy in zip(pts, ys):
        roll = random.random()
        key = "ribo_free" if roll < 0.82 else ("ves_blue" if roll < 0.93 else "ves_green")
        mb.sphere((x, yy + r * 0.2, z), (r, r * 0.8, r), key, seg=10, rings=6)
    mb.finish(coll("Cytoplasm_Ribosomes"))
    best = min(pts, key=lambda p: (p[0] + 0.80) ** 2 + (p[1] - 1.42) ** 2)
    ANCHOR["ribo"] = (best[0], best[1], None)


# --------------------------------------------------------------------------
# PHAGOCYTOSIS PATHWAY
# --------------------------------------------------------------------------
def bacterium(mb, c, length, radius, ang, pili=True, spots=16):
    cx, cy, cz = c
    ax = Vector((math.cos(ang), 0, math.sin(ang)))
    pr = Vector((-math.sin(ang), 0, math.cos(ang)))
    half = length / 2
    core = half - radius
    ss = [half * math.sin(t) for t in np.linspace(-math.pi / 2, math.pi / 2, 34)]
    pts, rads = [], []
    for s in ss:
        r = radius if abs(s) <= core else math.sqrt(max(radius ** 2 - (abs(s) - core) ** 2, 0.0))
        pts.append(Vector(c) + ax * s)
        rads.append(max(r, 0.0015))
    mb.tube(pts, rads, "bact", seg=18, ysc=0.9, caps=False)
    for _ in range(spots):
        s = random.uniform(-core, core)
        th = random.uniform(0.25 * math.pi, 1.75 * math.pi)
        dirv = (pr * math.cos(th) - Y_AXIS * math.sin(th) * 0.9)
        p = Vector(c) + ax * s + dirv * radius * 0.96
        rr = random.uniform(0.008, 0.016)
        mb.sphere(p, (rr, rr * 0.7, rr), "bact_spot", seg=10, rings=6)
    if pili:
        for _ in range(22):
            s = random.uniform(-half * 0.95, half * 0.95)
            side = random.choice((-1, 1))
            if abs(s) > core:
                base_dir = (ax * math.copysign(1, s) * 0.7 + pr * side * 0.7).normalized()
            else:
                base_dir = pr * side
            r_here = radius if abs(s) <= core else math.sqrt(max(radius ** 2 - (abs(s) - core) ** 2, 0))
            p0 = Vector(c) + ax * s + base_dir * r_here * 0.9
            ln = random.uniform(0.04, 0.075)
            bend = random.uniform(-0.5, 0.5)
            ptsp = []
            for k in range(6):
                t = k / 5
                d = (base_dir + ax * bend * t).normalized()
                ptsp.append(p0 + d * ln * t + Vector((0, -0.01 * t, 0)))
            mb.tube(ptsp, 0.0042, "bact", seg=6, ysc=1.0)


def circle_union_outline(circles, n=200):
    """Outline points of the union of circles (works for 1 or 2 circles)."""
    pts = []
    for i, (cx, cz, r) in enumerate(circles):
        for k in range(n):
            t = TAU * k / n
            x, z = cx + r * math.cos(t), cz + r * math.sin(t)
            if all((x - ox) ** 2 + (z - oz) ** 2 >= orr ** 2 * 0.999
                   for j, (ox, oz, orr) in enumerate(circles) if j != i):
                pts.append((x, z))
    cx = sum(p[0] for p in pts) / len(pts)
    cz = sum(p[1] for p in pts) / len(pts)
    pts.sort(key=lambda p: math.atan2(p[1] - cz, p[0] - cx))
    return pts


def vesicle_ring(name, circles, rim_key, in_key, ycut, collection):
    mb = MB(name, [rim_key, in_key])
    outline = circle_union_outline(circles)
    ring = []
    for x, z in outline:
        # push the rim a hair outwards from the nearest circle centre
        best = min(circles, key=lambda c: abs(math.hypot(x - c[0], z - c[1]) - c[2]))
        d = math.hypot(x - best[0], z - best[1]) + 1e-9
        ring.append((best[0] + (x - best[0]) / d * (best[2] + 0.004),
                     best[1] + (z - best[1]) / d * (best[2] + 0.004)))
    ys = front_y([p[0] for p in ring], [p[1] for p in ring])
    mb.tube([(p[0], yy - 0.006, p[1]) for p, yy in zip(ring, ys)], 0.026, rim_key,
            closed=True, seg=14, ysc=0.95)
    inner = []
    for x, z in outline:
        best = min(circles, key=lambda c: abs(math.hypot(x - c[0], z - c[1]) - c[2]))
        d = math.hypot(x - best[0], z - best[1]) + 1e-9
        inner.append((best[0] + (x - best[0]) / d * (best[2] - 0.004),
                       best[1] + (z - best[1]) / d * (best[2] - 0.004)))
    mb.slab(inner, ycut - 0.006, 0.02, in_key)
    for cx, cz, r in circles:
        occupy(cx, cz, r + 0.03)
    return mb


def granules(mb, cx, cz, r, ycut, n, keys, rmin=0.008, rmax=0.022):
    placed = []
    tries = 0
    while len(placed) < n and tries < 4000:
        tries += 1
        a = random.uniform(0, TAU)
        d = r * math.sqrt(random.random()) * 0.85
        x, z = cx + d * math.cos(a), cz + d * math.sin(a)
        rr = random.uniform(rmin, rmax)
        if any((x - px) ** 2 + (z - pz) ** 2 < (rr + pr) ** 2 * 0.7 for px, pz, pr in placed):
            continue
        placed.append((x, z, rr))
        mb.sphere((x, ycut - 0.006 - rr * 0.55, z), (rr, rr * 0.8, rr), random.choice(keys),
                  seg=12, rings=8)


def arrow(mb, p0, p1, key="arrow"):
    a = Vector((p0[0], 0, p0[1]))
    b = Vector((p1[0], 0, p1[1]))
    y = min(fy(p0[0], p0[1]), fy(p1[0], p1[1])) - 0.035
    a.y = b.y = y
    d = (b - a).normalized()
    head = 0.05
    mb.tube([a, b - d * head * 0.9], 0.016, key, seg=12, ysc=0.6)
    mb.cone(b - d * head * 0.5, d, 0.042, 0.0, head, key, yscale=0.6)


def build_phagocytosis():
    c = coll("Phagocytosis_Pathway")
    # 1) engulfed bacterium inside the phagocytic cup
    b = MB("Engulfed_Bacterium", ["bact", "bact_spot"])
    bx, bz = CUP_C[0] - 0.01, CUP_C[1] - 0.01
    bacterium(b, (bx, -0.005, bz), 0.30, 0.068, math.radians(14))
    b.finish(c)
    ANCHOR["microbe"] = (bx + 0.02, bz + 0.07, -0.08)
    occupy(CUP_C[0], CUP_C[1], CUP_R + 0.05)

    # 2) phagosome
    x, z, r = PHAGOSOME
    ycut = RECESS_Y["phagosome"]
    mb = vesicle_ring("Phagosome", [(x, z, r)], "phago_rim", "phago_in", ycut, c)
    bacterium(mb, (x - 0.005, ycut - 0.006 - 0.045, z + 0.005), 0.18, 0.045,
              math.radians(-25), pili=False, spots=8)
    mb.sphere((x + 0.06, ycut - 0.02, z - 0.07), (0.035, 0.02, 0.028), "ves_purple")
    mb.finish(c)
    ANCHOR["phagosome"] = (x + r, z + 0.02, None)

    # 3) lysosomes heading for the phagosome
    ly = MB("Lysosomes_Pathway", ["lyso", "lyso_rim"])
    for lx, lz, lr in LYSO_TRIO:
        blob(ly, lx, lz, lr, "lyso", "lyso_rim", ysc=0.7)
    ly.finish(c)
    ANCHOR["lyso_r"] = (LYSO_TRIO[1][0] + 0.03, LYSO_TRIO[1][1] + 0.02, None)

    # 4) fusion of phagosome + lysosome
    ycut = RECESS_Y["fusion"]
    mb = vesicle_ring("Phagosome_Lysosome_Fusion", FUSION, "phago_rim", "phago_in", ycut, c)
    (ax_, az_, ar_), (bx_, bz_, br_) = FUSION
    bacterium(mb, (ax_ - 0.01, ycut - 0.006 - 0.042, az_ + 0.01), 0.17, 0.042,
              math.radians(30), pili=False, spots=8)
    granules(mb, ax_ + 0.06, az_ - 0.07, 0.05, ycut, 6, ["debris_or", "ves_green"], 0.008, 0.016)
    granules(mb, bx_, bz_, br_ * 0.8, ycut, 9, ["debris_or", "debris_br", "lyso", "ves_green"],
             0.009, 0.022)
    mb.sphere((bx_ + 0.02, ycut - 0.03, bz_ - 0.02), (0.034, 0.024, 0.034), "lyso")
    mb.finish(c)

    # 5) phagolysosome (digestion)
    x, z, r = PHAGOLYSO
    ycut = RECESS_Y["phagolyso"]
    mb = vesicle_ring("Phagolysosome", [(x, z, r)], "pl_rim", "pl_in", ycut, c)
    granules(mb, x, z, r, ycut, 34, ["debris_or", "debris_br", "lyso", "ves_green", "res_grain"],
             0.007, 0.024)
    mb.finish(c)
    ANCHOR["phagolyso"] = (x + r * 0.7, z + r * 0.7, None)

    # 6) residual bodies
    for key, (x, z, r) in (("residual_r", RESIDUAL_R), ("residual_l", RESIDUAL_L)):
        ycut = RECESS_Y[key]
        mb = vesicle_ring("Residual_Body" + ("" if key == "residual_r" else "_2"),
                          [(x, z, r)], "res_rim", "res_in", ycut, c)
        granules(mb, x, z, r, ycut, 40 if key == "residual_r" else 26,
                 ["res_grain", "res_grain", "debris_br"], 0.005, 0.014)
        mb.finish(c)
        ANCHOR[key] = (x, z - r * 0.6, None)

    # white process arrows
    ar = MB("Process_Arrows", ["arrow"])
    for p0, p1 in [((0.075, 2.615), (0.090, 2.500)),
                   ((0.170, 2.215), (0.205, 2.140)),
                   ((0.300, 2.030), (0.255, 1.900)),
                   ((0.355, 1.585), (0.365, 1.465)),
                   ((0.380, 1.125), (0.388, 0.995))]:
        arrow(ar, p0, p1)
    ar.finish(c)


RECESS_Y = {}


def plan_recesses():
    """Carve shallow pockets into the body for the vesicle rings."""
    items = {
        "phagosome": [PHAGOSOME],
        "fusion": FUSION,
        "phagolyso": [PHAGOLYSO],
        "residual_r": [RESIDUAL_R],
        "residual_l": [RESIDUAL_L],
    }
    for k, circles in items.items():
        ys = front_y([c[0] for c in circles], [c[1] for c in circles])
        ycut = float(np.max(ys)) + 0.055
        RECESS_Y[k] = ycut
        RECESSES.append(([(cx, cz, r) for cx, cz, r in circles], ycut))


# --------------------------------------------------------------------------
# SURFACE RECEPTORS
# --------------------------------------------------------------------------
def _frame(p, n):
    base = Vector((p[0], 0.0, p[1]))
    out = Vector((n[0], 0.0, n[1])).normalized()
    side = Vector((-n[1], 0.0, n[0])).normalized()
    return base, out, side


RECEPTOR_SCALE = 1.35


def receptor(kind, approx, mb):
    bm = mb.bm
    old = set(bm.verts)          # bmesh may reuse freed slots, so diff by identity
    tip = _receptor(kind, approx, mb)
    p, n = edge_point(*approx)
    pivot = Vector((p[0], 0.0, p[1]))
    for v in [v for v in bm.verts if v not in old]:
        v.co = pivot + (v.co - pivot) * RECEPTOR_SCALE
    t = pivot + (Vector((tip[0], 0.0, tip[1])) - pivot) * RECEPTOR_SCALE
    return (t.x, t.z, 0.0)


def _receptor(kind, approx, mb):
    p, n = edge_point(*approx)
    base, out, side = _frame(p, n)
    start = base - out * 0.03
    k = {"prr": "r_prr", "fc": "r_fc", "cr": "r_cr", "mhc": "r_mhc",
         "other": "r_other", "red": "r_red", "green": "r_green"}[kind]
    if kind == "prr":
        top = base + out * 0.15
        mb.tube([start, base + out * 0.06 + side * 0.008, top], 0.017, k, seg=12)
        ring = [top + out * 0.035 + (out * math.cos(t) + side * math.sin(t)) * 0.032
                for t in np.linspace(0, TAU, 40, endpoint=False)]
        mb.tube(ring, 0.011, k, closed=True, seg=10)
        tip = top + out * 0.07
    elif kind == "fc":
        fork = base + out * 0.11
        mb.tube([start, fork], 0.018, k, seg=12)
        tip = fork
        for sgn in (-1, 1):
            arm_end = fork + (out * 0.75 + side * sgn * 0.66).normalized() * 0.08
            mb.tube([fork, arm_end], 0.014, k, seg=10)
            mb.sphere(arm_end, 0.019, k, seg=12, rings=8)
            tip = arm_end
    elif kind == "cr":
        top = base + out * 0.12
        mb.tube([start, top], 0.017, k, seg=12)
        hook = [top + out * 0.035 + (out * math.cos(t) + side * math.sin(t)) * 0.035
                for t in np.linspace(math.pi, math.pi + 1.6 * math.pi, 30)]
        mb.tube(hook, 0.013, k, seg=10)
        tip = top + out * 0.06
    elif kind == "mhc":
        top = base + out * 0.10
        mb.tube([start, top], 0.021, k, seg=12)
        mb.sphere(top, (0.03, 0.022, 0.03), k)
        for sgn in (-1, 1):
            a0 = top + side * sgn * 0.022
            a1 = a0 + out * 0.07 + side * sgn * 0.01
            mb.tube([a0, a1], 0.012, k, seg=10)
        tip = top + out * 0.07
    else:
        ln = 0.10 if kind == "other" else 0.07
        top = base + out * ln
        mb.tube([start, top], 0.013, k, seg=10)
        mb.sphere(top + out * 0.012, 0.024 if kind == "other" else 0.019, k, seg=14, rings=10)
        tip = top
    return (tip.x, tip.z, 0.0)


def build_receptors():
    mb = MB("Surface_Receptors", ["r_prr"])
    ANCHOR["r_prr"] = receptor("prr", (0.74, 2.66), mb)
    ANCHOR["r_fc"] = receptor("fc", (0.86, 2.36), mb)
    ANCHOR["r_cr"] = receptor("cr", (0.92, 2.08), mb)
    ANCHOR["r_mhc"] = receptor("mhc", (0.94, 1.82), mb)
    ANCHOR["r_other"] = receptor("other", (0.88, 1.20), mb)
    receptor("other", (0.84, 1.33), mb)
    receptor("red", (0.66, 0.42), mb)
    receptor("green", (0.71, 0.36), mb)
    receptor("red", (-0.05, 0.36), mb)
    receptor("other", (-0.80, 2.80), mb)
    receptor("green", (0.92, 2.22), mb)
    mb.finish(coll("Surface_Receptors"))


# --------------------------------------------------------------------------
# BASE, LABELS, ENVIRONMENT
# --------------------------------------------------------------------------
def build_base():
    mb = MB("Display_Base", ["base"])
    outline = [(0.70 * math.cos(t), 0.70 * math.sin(t)) for t in np.linspace(0, TAU, 128, endpoint=False)]
    bm = mb.bm
    bot = [bm.verts.new((x, y, 0.0)) for x, y in outline]
    top = [bm.verts.new((x, y, 0.085)) for x, y in outline]
    fb = bm.faces.new(list(reversed(bot)))
    ft = bm.faces.new(top)
    for i in range(len(outline)):
        j = (i + 1) % len(outline)
        bm.faces.new((bot[i], bot[j], top[j], top[i]))
    for f in bm.faces:
        f.smooth = True
    ob = mb.finish(coll("Display_Base"))
    bev = ob.modifiers.new("Bevel", "BEVEL")
    bev.width = 0.022
    bev.segments = 5
    try:
        bev.limit_method = "ANGLE"
    except Exception:
        pass


LABEL_Y = -0.52
LABEL_SIZE = 0.056


def rounded_rect(cx, cz, w, h, r, n=6):
    pts = []
    for (ox, oz, a0) in ((w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90),
                         (-w / 2 + r, -h / 2 + r, 180), (w / 2 - r, -h / 2 + r, 270)):
        for k in range(n + 1):
            a = math.radians(a0 + 90 * k / n)
            pts.append((cx + ox + r * math.cos(a), cz + oz + r * math.sin(a)))
    return pts


def make_text(name, body, align):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = body
    cu.size = LABEL_SIZE
    cu.align_x = align
    cu.align_y = "CENTER"
    cu.extrude = 0.0015
    cu.space_line = 0.92
    ob = bpy.data.objects.new(name, cu)
    ob.rotation_euler = (math.radians(90), 0, 0)
    cu.materials.append(MATS["label_text"])
    coll("Labels").objects.link(ob)
    return ob


def build_labels():
    L = ANCHOR
    left = [
        ("Pseudopodia", (-0.43, 3.03, None)),
        ("Plasma membrane", None),
        ("Cytoplasm", (-0.56, 2.48, None)),
        ("Nucleus", L["nucleus"]),
        ("Nuclear membrane", L["nuc_env"]),
        ("Chromatin", L["chromatin"]),
        ("Nucleolus", L["nucleolus"]),
        ("Rough\nendoplasmic\nreticulum", L.get("er", (-0.9, 1.7, None))),
        ("Free ribosomes", L["ribo"]),
        ("Golgi apparatus", L["golgi"]),
        ("Mitochondria", L["mito"]),
        ("Lysosomes", L["lyso_l"]),
        ("Endosomes /\nvesicles", L["vesicle"]),
        ("Secretory vesicles", L["secretory"]),
        ("Residual body\n(if shown)", L["residual_l"]),
    ]
    ep, _ = edge_point(-0.62, 2.74)
    left[1] = ("Plasma membrane", (ep[0], ep[1], None))
    inner = [
        ("Phagosome\n(microbe enclosed)", L["phagosome"], 0.31, None),
        ("Lysosomes", L["lyso_r"], 0.50, None),
        ("Phagolysosome\n(fusion and digestion)", L["phagolyso"], 0.58, 1.43),
        ("Residual body\n(indigestible remains)", L["residual_r"], 0.20, 0.62),
    ]
    right = [
        ("Pattern-recognition\nreceptors (PRRs /\nToll-like receptors)", L["r_prr"]),
        ("Fc receptor\n(antibody binding)", L["r_fc"]),
        ("Complement\nreceptor (CR)", L["r_cr"]),
        ("MHC class II\nmolecule (MHC II)", L["r_mhc"]),
        ("Cell surface\nreceptors (others)", L["r_other"]),
    ]
    bpy.context.view_layer.update()

    def column(items, x_edge, align, desired_z=None):
        objs = []
        for i, it in enumerate(items):
            text, anc = it[0], it[1]
            ob = make_text("Label_%s" % text.split("\n")[0][:18].replace(" ", "_"), text, align)
            z = desired_z[i] if desired_z and desired_z[i] is not None else anc[1]
            ob.location = (x_edge, LABEL_Y, z)
            objs.append([ob, anc, z])
        bpy.context.view_layer.update()
        recs = []
        for ob, anc, z in objs:
            bb = [Vector(c) for c in ob.bound_box]
            minx, maxx = min(v.x for v in bb), max(v.x for v in bb)
            miny, maxy = min(v.y for v in bb), max(v.y for v in bb)
            recs.append({"ob": ob, "anc": anc, "z": z, "h": maxy - miny + 0.05,
                         "w": maxx - minx, "dx": (minx + maxx) / 2, "dz": (miny + maxy) / 2})
        return recs

    def relax(recs, gap=0.018):
        recs.sort(key=lambda r: -r["z"])
        for _ in range(200):
            moved = False
            for a, b in zip(recs, recs[1:]):
                need = (a["h"] + b["h"]) / 2 + gap
                if a["z"] - b["z"] < need - 1e-6:
                    d = (need - (a["z"] - b["z"])) / 2
                    a["z"] += d
                    b["z"] -= d
                    moved = True
            if not moved:
                break

    def place(recs, side):
        plates = MB("Label_Plates_%s" % side, ["label_bg", "label_edge", "leader"])
        for r in recs:
            ob = r["ob"]
            ob.location.z = r["z"] - r["dz"]
            cx = ob.location.x + r["dx"]
            cz = r["z"]
            w, h = r["w"] + 0.05, r["h"]
            plates.slab(rounded_rect(cx, cz, w, h, 0.018), LABEL_Y + 0.0035, 0.008, "label_bg")
            plates.slab(rounded_rect(cx, cz, w + 0.012, h + 0.012, 0.022), LABEL_Y + 0.0115, 0.006,
                        "label_edge")
            ax, az, ay = r["anc"]
            if ay is None:
                ay = fy(ax, az) - 0.03 if interior(ax, az, 0.0) else -0.02
            if side == "right_in":
                sx = cx - w / 2 - 0.006
                if ax > cx:
                    sx = cx + w / 2 + 0.006
                sz = cz
                if abs(ax - cx) < w / 2:
                    sx, sz = ax, (cz - h / 2 - 0.006) if az < cz else (cz + h / 2 + 0.006)
            elif side == "left":
                sx, sz = cx + w / 2 + 0.006, cz
            elif side == "top":
                sx, sz = cx, cz - h / 2 - 0.006
            else:
                sx, sz = cx - w / 2 - 0.006, cz
            plates.tube([(sx, LABEL_Y + 0.002, sz), (ax, ay, az)], 0.0042, "leader", seg=8)
            plates.sphere((ax, ay, az), 0.0085, "leader", seg=10, rings=6)
        plates.finish(coll("Labels"))

    recs = column(left, -0.99, "RIGHT")
    relax(recs)
    place(recs, "left")
    recs = column(right, 1.17, "LEFT")
    relax(recs, 0.03)
    place(recs, "right")
    recs = column([(t, a) for t, a, _, _ in inner], 0.0, "LEFT",
                  [dz for _, _, _, dz in inner])
    for r, (_, _, x, _) in zip(recs, inner):
        r["ob"].location.x = x
    relax(recs, 0.03)
    place(recs, "right_in")
    # title-style callout for the microbe, centred above the cell
    recs = column([("Engulfed microbe\n(bacterium)", L["microbe"])], 0.08, "CENTER", [3.42])
    place(recs, "top")
    # the top label's leader should start from its bottom edge
    return


def look_at(ob, target):
    d = Vector(target) - ob.location
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def build_environment():
    sc = bpy.context.scene
    env = coll("Environment")
    # desk
    me = bpy.data.meshes.new("Desk")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=7.0)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(MATS["wood"])
    desk = bpy.data.objects.new("Desk", me)
    desk.location = (0, 2.0, 0)
    env.objects.link(desk)
    # back wall
    me = bpy.data.meshes.new("Wall")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=8.0)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(MATS["wall"])
    wall = bpy.data.objects.new("Wall", me)
    wall.location = (0, 6.0, 4.0)
    wall.rotation_euler = (math.radians(90), 0, 0)
    env.objects.link(wall)
    # world
    w = bpy.data.worlds.new("Studio")
    sc.world = w
    try:
        w.use_nodes = True
    except Exception:
        pass
    bg = w.node_tree.nodes.get("Background")
    if bg is None:
        bg = w.node_tree.nodes.new("ShaderNodeBackground")
        out = w.node_tree.nodes.new("ShaderNodeOutputWorld")
        w.node_tree.links.new(bg.outputs[0], out.inputs[0])
    bg.inputs[0].default_value = lin("#CFCBC4")
    bg.inputs[1].default_value = 0.55
    # lights
    target = Vector((0.1, 0.0, 1.7))

    def area(name, loc, power, size, color="#FFFFFF"):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy = power
        ld.size = size
        ld.color = lin(color)[:3]
        lo = bpy.data.objects.new(name, ld)
        lo.location = loc
        look_at(lo, target)
        env.objects.link(lo)

    area("Key_Light", (-3.0, -4.5, 5.0), 900, 3.0, "#FFF4E6")
    area("Fill_Light", (4.0, -3.5, 2.5), 380, 3.5, "#EEF2FF")
    area("Rim_Light", (1.5, 3.5, 5.0), 500, 2.5)
    area("Top_Light", (0.0, -1.0, 6.0), 250, 4.0)
    # cameras
    cd = bpy.data.cameras.new("Camera_Front")
    cd.lens = 72
    cd.dof.use_dof = True
    cd.dof.aperture_fstop = 9.0
    cam = bpy.data.objects.new("Camera_Front", cd)
    cam.location = (0.14, -9.2, 2.15)
    look_at(cam, (0.14, 0.0, 1.70))
    cd.dof.focus_distance = (cam.location - Vector((0.12, -0.2, 1.66))).length
    env.objects.link(cam)
    sc.camera = cam
    cd2 = bpy.data.cameras.new("Camera_3_4")
    cd2.lens = 62
    cd2.dof.use_dof = True
    cd2.dof.aperture_fstop = 6.0
    cam2 = bpy.data.objects.new("Camera_3_4", cd2)
    cam2.location = (4.6, -7.6, 3.0)
    look_at(cam2, (0.05, 0.0, 1.58))
    cd2.dof.focus_distance = (cam2.location - Vector((0.05, 0.0, 1.58))).length
    env.objects.link(cam2)


def render_settings(res=(1600, 2000), samples=128):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    try:
        sc.cycles.device = "CPU"
        sc.cycles.samples = samples
        sc.cycles.use_denoising = True
        sc.cycles.max_bounces = 8
    except Exception:
        pass
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    try:
        sc.view_settings.view_transform = "AgX"
        for look in ("AgX - Medium High Contrast", "Medium High Contrast", "AgX - Punchy", "Punchy"):
            try:
                sc.view_settings.look = look
                break
            except Exception:
                continue
    except Exception:
        pass


# --------------------------------------------------------------------------
# MAIN
# --------------------------------------------------------------------------
def main(argv):
    clean_scene()
    build_materials()
    plan_recesses()
    print("[cell] building body (surface nets)...")
    build_cell_body()
    print("[cell] organelles...")
    build_nucleus()
    occupy(GOLGI[0], GOLGI[1] + 0.02, 0.24)
    for (x, z, r) in [PHAGOSOME, PHAGOLYSO, RESIDUAL_R] + FUSION + LYSO_TRIO:
        occupy(x, z, r + 0.05)
    occupy(CUP_C[0], CUP_C[1], CUP_R + 0.06)
    occupy(-0.60, 0.88, 0.2)
    occupy(-0.11, 1.07, 0.18)
    build_er()
    occupy(NUC[0], NUC[1], NUC_R[1] * 1.12)
    build_golgi()
    ANCHOR["mito"] = build_mito("Mitochondrion_1", (-0.60, 0.89), 0.17, 0.078, math.radians(-38))
    build_mito("Mitochondrion_2", (-0.11, 1.065), 0.15, 0.072, math.radians(62))
    build_cytoplasm_bits()
    build_phagocytosis()
    build_free_ribosomes()
    build_receptors()
    build_base()
    if ADD_ENVIRONMENT:
        build_environment()
    if ADD_LABELS:
        print("[cell] labels...")
        build_labels()

    res, samples, save, render, cam = (1600, 2000), 128, None, None, None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--res":
            res = (int(argv[i + 1]), int(argv[i + 2]))
            i += 2
        elif a == "--samples":
            samples = int(argv[i + 1])
            i += 1
        elif a == "--save":
            save = argv[i + 1]
            i += 1
        elif a == "--render":
            render = argv[i + 1]
            i += 1
        elif a == "--camera":
            cam = argv[i + 1]
            i += 1
        elif a == "--no-labels":
            if "Labels" in COLLS:
                COLLS["Labels"].hide_render = True
                COLLS["Labels"].hide_viewport = True
        i += 1
    render_settings(res, samples)
    if cam and cam in bpy.data.objects:
        bpy.context.scene.camera = bpy.data.objects[cam]
    if save:
        bpy.ops.wm.save_as_mainfile(filepath=save)
        print("[cell] saved", save)
    if render:
        bpy.context.scene.render.filepath = render
        bpy.ops.render.render(write_still=True)
        print("[cell] rendered", render)
    print("[cell] done.")


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
