"""
Total Station on Tripod  -  photo-matched model, 200 mm tall
=============================================================
Blender 4.2+ / 5.x.   Units: metres in Blender (1 BU = 1 m), the geometry
below is written in millimetres and scaled on creation.

Every dimension comes from the reference photo: a pinhole camera was fitted
to hand-measured pixels of the photo (body corners, antenna tip, three foot
tips, tribrach centre; rms error ~1 px), then each visible feature was
back-projected onto its own face plane to get real millimetres.  The camera
"Cam_Photo" reproduces the photo's exact viewpoint (incl. its 4.4 deg roll).

Use inside Blender:  Scripting tab -> Open -> total_station.py -> Run Script
Headless:            blender -b -P total_station.py -- --render --export
                     (or `python total_station.py --render --export` with bpy)

Collections
  TS_Tripod      yellow slotted legs, orange hinge caps / clamps / shoes, head
  TS_Tribrach    levelling base with three knurled foot screws
  TS_Instrument  body, yoke window, telescope, knobs, console, handle, antenna
  TS_Stage       table, wall, lights, cameras (rendering only)

Pivots (Empties): Alidade_Pivot rotates the whole instrument about the
vertical axis, Telescope_Pivot tilts the telescope about the trunnion axis.
"""

import bpy
import bmesh
import math
import os
import sys
from mathutils import Vector, Matrix

MM = 0.001
RAD = math.radians

# --------------------------------------------------------------------------
#  Solution of the photo fit (see README) - do not edit unless re-fitting
# --------------------------------------------------------------------------
FIT = dict(img_w=203, img_h=393, dist=332.67, cam_z=159.64,
           yaw=1.206, pitch=-9.221, roll=4.394, f_px=485.57)
INST_YAW = -52.80          # instrument heading (deg) - knob side faces the camera
LEG_AZ = -87.94            # azimuth of the leg that points at the camera (deg)
FOOT_R = 65.37             # radius of the three foot tips on the ground (mm)
WALL = dict(y=198.0, angle=9.7)

# Instrument (local frame: +X knob side, -Y operator side, z=0 body bottom)
Z0 = 132.0                 # world height of the body bottom
BW, BD, BH = 22.7, 22.6, 44.1
TRUNNION_Z = 30.5          # eyepiece and top knob share this axis
WIN_X, WIN_Z0, WIN_Z1 = 5.3, 12.6, 40.5      # yoke window (half width, z range)

# Tripod
HINGE_R, HINGE_Z = 14.5, 113.1


# --------------------------------------------------------------------------
#  Materials
# --------------------------------------------------------------------------
def srgb(hexstr):
    hexstr = hexstr.lstrip('#')
    c = [int(hexstr[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    lin = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return (*lin, 1.0)


def _set(bsdf, name, value):
    if name in bsdf.inputs:
        bsdf.inputs[name].default_value = value


def material(name, color, rough=0.45, metal=0.0, coat=0.0, emit=None, emit_str=0.0,
             spec=0.5):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    if bpy.app.version < (5, 0, 0):
        try:
            m.use_nodes = True
        except Exception:
            pass
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    _set(bsdf, "Base Color", srgb(color))
    _set(bsdf, "Roughness", rough)
    _set(bsdf, "Metallic", metal)
    _set(bsdf, "Specular IOR Level", spec)
    _set(bsdf, "Coat Weight", coat)
    _set(bsdf, "Coat Roughness", 0.1)
    if emit:
        _set(bsdf, "Emission Color", srgb(emit))
        _set(bsdf, "Emission Strength", emit_str)
    m.diffuse_color = srgb(color)
    m.roughness = rough
    m.metallic = metal
    return m


def build_materials():
    # colours sampled from the photo (lit areas), as printed-plastic finishes
    return dict(
        leg=material("TS_Leg_Yellow", "#EBD51C", 0.42, coat=0.1),
        handle=material("TS_Handle_Yellow", "#F4BA26", 0.40, coat=0.15),
        orange=material("TS_Orange", "#FA7A0E", 0.45, coat=0.1),
        body=material("TS_Body_Grey", "#5E6569", 0.50),
        panel=material("TS_Panel_Grey", "#4F565A", 0.52),
        light=material("TS_Light_Grey", "#848E92", 0.46),
        post=material("TS_Post_BlueGrey", "#9294A0", 0.40),
        base=material("TS_Base_DarkGrey", "#383936", 0.50),
        black=material("TS_Black", "#0D0E0E", 0.72),
        rubber=material("TS_Black_Rubber", "#0F1011", 0.75),
        radio=material("TS_Radio_Black", "#1A1A1A", 0.50),
        steel=material("TS_Steel", "#B9BCBF", 0.25, metal=1.0),
        lens=material("TS_Lens_Glass", "#071016", 0.03, coat=1.0, spec=1.0),
        coating=material("TS_Lens_Coating", "#2B1E4A", 0.08, metal=0.7, coat=1.0),
        screen=material("TS_Console_Screen", "#7C878B", 0.18, coat=0.6),
    )


# --------------------------------------------------------------------------
#  Geometry helpers (millimetres)
# --------------------------------------------------------------------------
def T(x=0, y=0, z=0):
    return Matrix.Translation((x, y, z))


def R(axis, deg):
    return Matrix.Rotation(RAD(deg), 4, axis)


def frame(o, x, y, z):
    """4x4 matrix from origin + basis vectors (columns)."""
    M = Matrix.Identity(4)
    for i in range(3):
        M[i][0], M[i][1], M[i][2], M[i][3] = x[i], y[i], z[i], o[i]
    return M


def bm_box(sx, sy, sz):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts)
    return bm


def bm_cyl(r, h, n=48, r2=None):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=n,
                          radius1=r, radius2=r if r2 is None else r2, depth=h)
    return bm


def bm_lathe(profile, n=64, knurl=None):
    """Revolve an (r, z) polyline (open at the axis) around Z.
    knurl = (z_min, z_max, depth): alternating radius -> knurled grip."""
    bm = bmesh.new()
    rings = []
    for (r, z) in profile:
        if r < 1e-6:
            rings.append([bm.verts.new((0, 0, z))])
            continue
        ring = []
        for i in range(n):
            a = 2 * math.pi * i / n
            rr = r
            if knurl and knurl[0] - 1e-6 <= z <= knurl[1] + 1e-6 and i % 2:
                rr = r - knurl[2]
            ring.append(bm.verts.new((rr * math.cos(a), rr * math.sin(a), z)))
        rings.append(ring)
    for a, b in zip(rings[:-1], rings[1:]):
        if len(a) == 1 and len(b) == 1:
            continue
        if len(a) == 1:
            for i in range(n):
                bm.faces.new((a[0], b[i], b[(i + 1) % n]))
        elif len(b) == 1:
            for i in range(n):
                bm.faces.new((a[i], b[0], a[(i + 1) % n]))
        else:
            for i in range(n):
                bm.faces.new((a[i], b[i], b[(i + 1) % n], a[(i + 1) % n]))
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def bm_prism(pts, z0, z1):
    """Extrude a simple 2D polygon (x, y) between z0 and z1."""
    bm = bmesh.new()
    bot = [bm.verts.new((x, y, z0)) for x, y in pts]
    top = [bm.verts.new((x, y, z1)) for x, y in pts]
    bm.faces.new(list(reversed(bot)))
    bm.faces.new(top)
    n = len(pts)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((bot[i], bot[j], top[j], top[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def bm_loft(sections):
    """Loft of rectangles along Y: sections = [(y, half_w_x, half_d_z), ...]."""
    bm = bmesh.new()
    rings = []
    for y, hx, hz in sections:
        rings.append([bm.verts.new(v) for v in
                      ((-hx, y, -hz), (hx, y, -hz), (hx, y, hz), (-hx, y, hz))])
    for a, b in zip(rings[:-1], rings[1:]):
        for i in range(4):
            j = (i + 1) % 4
            bm.faces.new((a[i], a[j], b[j], b[i]))
    bm.faces.new(rings[0])
    bm.faces.new(list(reversed(rings[-1])))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def lobed(r0, k, phase_deg, lobes=3, n=96):
    pts = []
    for i in range(n):
        p = 2 * math.pi * i / n
        r = r0 * (1 + k * math.cos(lobes * (p - RAD(phase_deg))))
        pts.append((r * math.cos(p), r * math.sin(p)))
    return pts


def rounded_rect(w, h, r, k=6):
    pts = []
    cs = [(w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90),
          (-w / 2 + r, -h / 2 + r, 180), (w / 2 - r, -h / 2 + r, 270)]
    for cx, cy, a0 in cs:
        for i in range(k + 1):
            a = RAD(a0 + 90 * i / k)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def fillet_path(corners, radius, steps=12):
    """Polyline with circular-ish (quadratic bezier) fillets on inner corners."""
    P = [Vector(c) for c in corners]
    rad = radius if isinstance(radius, (list, tuple)) else [radius] * len(P)
    out = [P[0]]
    for i in range(1, len(P) - 1):
        a = (P[i] - P[i - 1]).normalized()
        b = (P[i + 1] - P[i]).normalized()
        t1 = P[i] - a * rad[i]
        t2 = P[i] + b * rad[i]
        for s in range(steps + 1):
            t = s / steps
            out.append((1 - t) ** 2 * t1 + 2 * (1 - t) * t * P[i] + t ** 2 * t2)
    out.append(P[-1])
    return out


def bm_sweep(path, w, h, r, n0):
    """Sweep a rounded-rect profile (w along the binormal, h along n) along a
    3D path, using rotation-minimising frames.  n0: initial profile 'up'."""
    P = [Vector(p) for p in path]
    T_ = []
    for i in range(len(P)):
        if i == 0:
            t = P[1] - P[0]
        elif i == len(P) - 1:
            t = P[-1] - P[-2]
        else:
            t = (P[i + 1] - P[i]).normalized() + (P[i] - P[i - 1]).normalized()
        T_.append(t.normalized())
    prof = rounded_rect(h, w, r, 4)            # (u along n, v along b)
    bm = bmesh.new()
    n = Vector(n0)
    rings = []
    for i, p in enumerate(P):
        n = (n - n.dot(T_[i]) * T_[i]).normalized()
        b = T_[i].cross(n)
        rings.append([bm.verts.new(p + n * u + b * v) for (u, v) in prof])
    m = len(prof)
    for a, c in zip(rings[:-1], rings[1:]):
        for i in range(m):
            j = (i + 1) % m
            bm.faces.new((a[i], a[j], c[j], c[i]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


# --------------------------------------------------------------------------
#  Object factory
# --------------------------------------------------------------------------
class Builder:
    def __init__(self, mats):
        self.m = mats
        self.coll = None

    def collection(self, name, parent=None):
        old = bpy.data.collections.get(name)
        if old:
            for ob in list(old.all_objects):
                bpy.data.objects.remove(ob, do_unlink=True)
            for ch in list(old.children_recursive):
                bpy.data.collections.remove(ch)
            bpy.data.collections.remove(old)
        c = bpy.data.collections.new(name)
        (parent or bpy.context.scene.collection).children.link(c)
        self.coll = c
        return c

    def make(self, name, bm, mat, M=None, bevel=0.0, seg=3, bevel_angle=30.0,
             sharp_angle=36.0, smooth=True):
        if M is not None:
            bmesh.ops.transform(bm, matrix=M, verts=bm.verts)
            if M.to_3x3().determinant() < 0:
                bmesh.ops.reverse_faces(bm, faces=bm.faces)
        if bevel > 0:
            edges = [e for e in bm.edges
                     if e.is_manifold and e.calc_face_angle(0) > RAD(bevel_angle)]
            if edges:
                bmesh.ops.bevel(bm, geom=edges, offset=bevel, offset_type='OFFSET',
                                segments=seg, profile=0.5, affect='EDGES',
                                clamp_overlap=True)
        for f in bm.faces:
            f.smooth = smooth
        for e in bm.edges:
            if (not e.is_manifold) or e.calc_face_angle(0) > RAD(sharp_angle):
                e.smooth = False
        bmesh.ops.scale(bm, vec=(MM, MM, MM), verts=bm.verts)
        lo = Vector([min(v.co[i] for v in bm.verts) for i in range(3)])
        hi = Vector([max(v.co[i] for v in bm.verts) for i in range(3)])
        c = (lo + hi) / 2
        bmesh.ops.translate(bm, vec=-c, verts=bm.verts)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        me.materials.append(self.m[mat] if isinstance(mat, str) else mat)
        ob = bpy.data.objects.new(name, me)
        ob.location = c
        self.coll.objects.link(ob)
        return ob

    def empty(self, name, loc_mm, size=0.01):
        ob = bpy.data.objects.new(name, None)
        ob.empty_display_type = 'ARROWS'
        ob.empty_display_size = size
        ob.location = Vector(loc_mm) * MM
        self.coll.objects.link(ob)
        return ob


def apply_modifiers(ob, sharp_angle=36.0):
    """Bake the modifier stack into the mesh (works headless)."""
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    old = ob.data
    ob.modifiers.clear()
    ob.data = me
    me.name = ob.name
    bpy.data.meshes.remove(old)
    bm = bmesh.new()
    bm.from_mesh(me)
    for f in bm.faces:
        f.smooth = True
    for e in bm.edges:
        e.smooth = e.is_manifold and e.calc_face_angle(0) <= RAD(sharp_angle)
    bm.to_mesh(me)
    bm.free()


def boolean_cut(ob, cutters):
    for c in cutters:
        md = ob.modifiers.new("cut_" + c.name, 'BOOLEAN')
        md.operation = 'DIFFERENCE'
        md.solver = 'EXACT'
        md.object = c
        c.hide_render = True
        c.display_type = 'WIRE'


def bevel_mod(ob, width_mm, segments=3, angle=30.0):
    md = ob.modifiers.new("bevel", 'BEVEL')
    md.width = width_mm * MM
    md.segments = segments
    md.limit_method = 'ANGLE'
    md.angle_limit = RAD(angle)
    md.use_clamp_overlap = True


def parent_keep(child, parent):
    child.parent = parent
    child.matrix_parent_inverse = parent.matrix_world.inverted()


# --------------------------------------------------------------------------
#  TRIPOD  (built directly in world millimetres)
# --------------------------------------------------------------------------
def leg_frames():
    """For each leg: (azimuth, frame matrix, length).  Frame: origin at the
    hinge centre, x = tangential, y = up along the leg, z = outward normal."""
    out = []
    for k in range(3):
        a = LEG_AZ + 120.0 * k
        ca, sa = math.cos(RAD(a)), math.sin(RAD(a))
        H = Vector((HINGE_R * ca, HINGE_R * sa, HINGE_Z))
        F = Vector((FOOT_R * ca, FOOT_R * sa, 0.0))
        u = (F - H).normalized()
        t = Vector((-sa, ca, 0.0))
        y = -u
        z = t.cross(y)
        out.append((a, frame(H, t, y, z), (F - H).length))
    return out


def build_tripod(B):
    names = ("Front", "Right", "Left")
    for (a, M, Lg), nm in zip(leg_frames(), names):
        s_clamp0, s_clamp1 = 0.710 * Lg, 0.760 * Lg
        s_shoe = 0.900 * Lg

        # upper leg: 10 x 5.2 mm flat bar with the open-top slot (two rails)
        sb = 23.3                                   # slot: centre of round end
        pts = [(-5.0, 1.0), (-5.0, -s_clamp1 + 1.0), (5.0, -s_clamp1 + 1.0), (5.0, 1.0),
               (2.7, 1.0), (2.7, -sb)]
        for i in range(1, 12):
            ang = RAD(-180.0 * i / 12)
            pts.append((2.7 * math.cos(ang), -sb + 2.7 * math.sin(ang)))
        pts += [(-2.7, -sb), (-2.7, 1.0)]
        B.make(f"Leg{nm}_Upper", bm_prism(pts, -2.6, 2.6), "leg", M, bevel=0.45)

        # clamp collar at the end of the upper leg + its knob
        sc = (s_clamp0 + s_clamp1) / 2
        B.make(f"Leg{nm}_Clamp", bm_box(12.3, s_clamp1 - s_clamp0, 7.4), "orange",
               M @ T(0, -sc, 0), bevel=0.9)
        knob = bm_lathe([(0, 0), (1.9, 0), (1.9, 1.5), (1.5, 2.1), (0, 2.1)], 24,
                        knurl=(0.2, 1.5, 0.25))
        B.make(f"Leg{nm}_Clamp_Knob", knob, "orange", M @ T(6.05, -sc, 0) @ R('Y', 90), bevel=0.0)

        # lower (sliding) leg
        s0, s1 = 0.722 * Lg, 0.925 * Lg
        B.make(f"Leg{nm}_Lower", bm_box(7.8, s1 - s0, 5.0), "leg",
               M @ T(0, -(s0 + s1) / 2, 0), bevel=0.45)

        # pointed shoe
        shoe = bm_loft([(-s_shoe, 4.5, 3.2), (-0.955 * Lg, 4.5, 3.2),
                        (-0.985 * Lg, 1.5, 1.3), (-Lg, 0.15, 0.15)])
        B.make(f"Leg{nm}_Shoe", shoe, "orange", M, bevel=0.5, bevel_angle=25.0)

        # step tab: horizontal plate pointing outward from the top of the shoe
        Q = M @ Vector((0, -(s_shoe + 1.6), 2.4))
        Rz = R('Z', a)
        tab = bm_box(5.6, 4.4, 1.5)
        B.make(f"Leg{nm}_Step", tab, "orange",
               T(*Q) @ Rz @ R('Y', -12) @ T(2.4, 0, 0), bevel=0.45)

        # hinge cap block on top of the leg + hinge bolt heads
        ca, sa = math.cos(RAD(a)), math.sin(RAD(a))
        Mh = T(HINGE_R * ca, HINGE_R * sa, HINGE_Z) @ R('Z', a)
        B.make(f"Leg{nm}_Hinge", bm_box(7.0, 12.5, 8.0), "orange", Mh, bevel=1.2)
        for side in (-1, 1):
            bolt = bm_cyl(1.3, 0.6, 24)
            B.make(f"Leg{nm}_Hinge_Pin{'LR'[side > 0]}", bolt, "orange",
                   Mh @ T(0.3, side * 6.4, 0.6) @ R('X', 90), bevel=0.15)

    # head core (black) + its three lugs + centring screw underneath
    prof = [(0, 109.6), (10.4, 109.6), (11.2, 110.4), (11.2, 118.2), (10.6, 118.9), (0, 118.9)]
    B.make("Tripod_Head", bm_lathe(prof, 72), "black", bevel=0.0)
    for k in range(3):
        a = LEG_AZ + 120.0 * k
        B.make(f"Tripod_Head_Lug{k + 1}", bm_box(6.0, 7.0, 5.5), "black",
               T(0, 0, 112.6) @ R('Z', a) @ T(10.5, 0, 0), bevel=0.5)


# --------------------------------------------------------------------------
#  TRIBRACH
# --------------------------------------------------------------------------
def build_tribrach(B):
    ph = LEG_AZ + 60.0
    B.make("Tribrach_Base", bm_prism(lobed(11.4, 0.07, LEG_AZ), 118.9, 120.3), "black",
           bevel=0.4)
    B.make("Tribrach_Core", bm_lathe([(0, 120.2), (8.6, 120.2), (8.6, 124.5), (0, 124.5)], 64),
           "black")
    B.make("Tribrach_Ring", bm_lathe([(0, 121.9), (10.5, 121.9), (10.8, 122.2), (10.8, 122.7),
                                      (10.5, 123.0), (0, 123.0)], 72), "base")
    for k in range(3):
        a = RAD(ph + 120.0 * k)
        knob = bm_lathe([(0, 0), (2.9, 0), (3.1, 0.3), (3.1, 3.1), (2.9, 3.4), (0, 3.4)], 32,
                        knurl=(0.3, 3.1, 0.3))
        B.make(f"Tribrach_Foot_Screw{k + 1}", knob, "black",
               T(8.9 * math.cos(a), 8.9 * math.sin(a), 120.6))
    B.make("Tribrach_Top", bm_prism(lobed(11.3, 0.025, LEG_AZ), 124.4, 126.8), "black",
           bevel=0.6)
    # locking lever (small, on the side away from the camera)
    a = RAD(LEG_AZ + 180.0)
    B.make("Tribrach_Lock", bm_box(4.0, 2.0, 1.6), "base",
           T(0, 0, 125.6) @ R('Z', math.degrees(a)) @ T(12.0, 0, 0), bevel=0.4)


# --------------------------------------------------------------------------
#  INSTRUMENT (local millimetres -> world via inst())
# --------------------------------------------------------------------------
def inst(M=None):
    base = T(0, 0, Z0) @ R('Z', INST_YAW)
    return base if M is None else base @ M


def knob_bm(d, p, n=48):
    """Knurled control knob along +Z: diameter d, protrusion p."""
    r = d / 2
    prof = [(0, 0), (r + 0.35, 0), (r + 0.35, 0.45), (r, 0.6), (r, p - 0.7),
            (r - 0.35, p - 0.3), (r * 0.72, p), (0, p + 0.08)]
    return bm_lathe(prof, n, knurl=(0.6, p - 0.7, 0.28))


def build_instrument(B):
    m = B.m
    piv = B.empty("Alidade_Pivot", (0, 0, Z0 - 5.2), 0.03)

    # ---- body shell with the yoke window cut through (back <-> front) ----
    shell = B.make("Body_Shell", bm_prism(rounded_rect(BW, BD, 1.0, 4), 0.0, BH), "body",
                   inst(), smooth=False)
    cut = B.make("cutter_window", bm_box(2 * WIN_X, BD + 4, WIN_Z1 - WIN_Z0), "body",
                 inst(T(0, 0, (WIN_Z0 + WIN_Z1) / 2)))
    boolean_cut(shell, [cut])
    bevel_mod(shell, 0.55, 3)
    apply_modifiers(shell)
    bpy.data.objects.remove(cut, do_unlink=True)

    # dark inner block below / above the telescope (window depth 5.5 mm)
    inner_d = BD - 2 * 5.5
    B.make("Yoke_Inner_Lower", bm_box(2 * WIN_X + 0.4, inner_d, 24.0 - WIN_Z0 + 0.2), "base",
           inst(T(0, 0, (WIN_Z0 + 24.0) / 2)), bevel=0.0)

    # ---- light-grey bezels around the window (back and front) ----
    pi = [(-8.8, WIN_Z0), (-WIN_X, WIN_Z0), (-WIN_X, WIN_Z1), (WIN_X, WIN_Z1),
          (WIN_X, WIN_Z0), (8.8, WIN_Z0), (8.8, 42.0), (-8.8, 42.0)]
    for side, nm in ((-1, "Back"), (1, "Front")):
        bz = bm_prism(pi, -0.35, 0.35)
        B.make(f"Bezel_{nm}", bz, "light", inst(T(0, side * BD / 2, 0) @ R('X', 90)), bevel=0.22)

    # ---- side details: light strips near the back edge, knob panel ----
    for sx in (1, -1):
        strip = bm_box(0.5, 4.1, 30.0)
        B.make(f"Side_Strip_{'R' if sx > 0 else 'L'}", strip, "light",
               inst(T(sx * (BW / 2 + 0.05), -7.85, 13.5 + 15.0)), bevel=0.18)
        panel = bm_box(0.5, 15.9, 31.8)
        B.make(f"Side_Panel_{'R' if sx > 0 else 'L'}", panel, "panel",
               inst(T(sx * (BW / 2 + 0.05), 2.75, 4.8 + 15.9)), bevel=0.2)

    # three knurled knobs on the +X side (dia / centre measured on the photo)
    for nm, d, p, y, z in (("Knob_Focus", 5.8, 2.5, 0.8, TRUNNION_Z),
                           ("Knob_Vertical", 7.6, 2.8, 5.4, 21.4),
                           ("Knob_Horizontal", 8.35, 3.0, 5.1, 10.1)):
        B.make(nm, knob_bm(d, p), "rubber", inst(T(BW / 2 + 0.3, y, z) @ R('Y', 90)))
    # trunnion cap on the -X side
    cap = bm_lathe([(0, 0), (3.0, 0), (3.0, 0.5), (2.6, 0.9), (0, 0.9)], 48)
    B.make("Trunnion_Cap_L", cap, "panel", inst(T(-BW / 2 - 0.3, 0.8, TRUNNION_Z) @ R('Y', -90)))
    # small battery latch on the -X panel
    B.make("Battery_Latch", bm_box(0.8, 5.0, 2.2), "body",
           inst(T(-BW / 2 - 0.6, 4.0, 12.0)), bevel=0.25)

    # ---- operator console (sloped display / keyboard) on the back ----
    cons = [(-10.3, 0.0), (-15.55, 0.0), (-15.55, 1.7), (-BD / 2, 12.6), (-10.3, 12.6)]
    cb = bm_prism([(y, z) for (y, z) in cons], -BW / 2, BW / 2)
    # prism axes (x, y, z) -> instrument (Y, z, X)
    B.make("Console", cb, "light",
           inst(frame(Vector((0, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1)), Vector((1, 0, 0)))),
           bevel=0.45)
    slope = math.degrees(math.atan2(12.6 - 1.7, 15.55 - BD / 2))       # ~69 deg
    Ms = inst(T(0, -(15.55 + BD / 2) / 2, (1.7 + 12.6) / 2) @ R('X', slope))
    B.make("Console_Screen", bm_box(15.0, 6.0, 0.24), "screen", Ms @ T(0, 0.6, 0.06), bevel=0.1)

    # ---- rotating alidade base ----
    prof = [(0, -5.2), (9.6, -5.2), (10.3, -4.6), (10.3, -2.9), (10.0, -2.6), (10.0, -2.2),
            (10.3, -1.9), (10.3, -0.4), (9.9, 0.05), (0, 0.05)]
    B.make("Alidade_Base", bm_lathe(prof, 72), "base", inst())

    # ---- telescope (pivots on the trunnion axis) ----
    tel_piv = B.empty("Telescope_Pivot", (0, 0, 0), 0.015)
    tel_piv.matrix_world = Matrix.Translation(inst() @ Vector((0, 0, TRUNNION_Z)) * MM) @ \
        R('Z', INST_YAW)
    tel = []
    # telescope housing: 24 -> 40 mm (fills the window top, trunnion at 30.5)
    tel.append(B.make("Telescope_Body", bm_box(9.6, BD - 1.4, 16.0), "light",
                      inst(T(0, 0, 32.0)), bevel=1.1))
    eye = bm_lathe([(0, 0), (2.1, 0), (2.1, 1.4), (3.0, 1.5), (3.0, 2.9), (3.25, 3.0),
                    (3.25, 4.2), (2.4, 4.3), (1.6, 3.9), (0, 3.9)], 48, knurl=(1.6, 2.8, 0.3))
    tel.append(B.make("Eyepiece", eye, "rubber",
                      inst(T(0, -(BD - 1.4) / 2, TRUNNION_Z) @ R('X', 90))))
    ring = bm_lathe([(0, 0), (4.1, 0), (4.1, 0.9), (3.5, 0.9), (3.5, 0.3), (0, 0.3)], 64)
    tel.append(B.make("Objective_Ring", ring, "black",
                      inst(T(0, (BD - 1.4) / 2 - 0.2, TRUNNION_Z) @ R('X', -90))))
    lens = bm_lathe([(0, 0.55), (3.5, 0.3), (3.5, 0.0), (0, 0.0)], 64)
    tel.append(B.make("Objective_Lens", lens, "lens",
                      inst(T(0, (BD - 1.4) / 2 - 0.1, TRUNNION_Z) @ R('X', -90))))
    coat = bm_lathe([(0, 0.0), (2.2, 0.0), (2.2, 0.05), (0, 0.05)], 48)
    tel.append(B.make("Objective_Coating", coat, "coating",
                      inst(T(0, (BD - 1.4) / 2 + 0.45, TRUNNION_Z) @ R('X', -90))))
    trk = bm_lathe([(0, 0.4), (1.0, 0.3), (1.0, 0.0), (0, 0.0)], 32)
    tel.append(B.make("Tracker_Lens", trk, "lens",
                      inst(T(0, (BD - 1.4) / 2 - 0.1, TRUNNION_Z + 6.0) @ R('X', -90))))

    # ---- yellow handle frame: +X bottom rail -> front-right post -> over the
    #      top to the centre -> back to the rear radio block ----
    hz = 55.9                                   # handle bar centre height
    cx, cy = 12.5, 12.9                         # front-right post centre (X, Y)
    path = fillet_path([(cx, -14.6, 2.5), (cx, cy, 2.5), (cx, cy, hz), (0.0, cy, hz),
                        (0.0, -16.6, hz)], [0, 3.2, 6.0, 5.5, 0], steps=16)
    hb = bm_sweep([inst() @ p for p in path], 5.0, 5.0, 1.5, inst().to_3x3() @ Vector((0, 0, 1)))
    B.make("Handle_Frame", hb, "handle", None, bevel=0.6, bevel_angle=50.0, sharp_angle=50.0)
    # radio module on the rear half of the bar
    B.make("Radio_Module", bm_box(6.2, 14.7, 6.5), "radio",
           inst(T(0, (-13.7 + 1.0) / 2, 55.75)), bevel=0.9)
    # supports between body top and handle
    B.make("Handle_Post_Rear", bm_box(6.0, 8.4, 10.4), "post", inst(T(0, 0.1, 43.8 + 5.2)),
           bevel=1.2)
    st = bm_sweep([inst() @ Vector(p) for p in ((7.5, 8.4, 43.6), (7.5, 12.4, 54.0))],
                  3.2, 3.2, 0.8, inst().to_3x3() @ Vector((1, 0, 0)))
    B.make("Handle_Post_Front", st, "body", None, bevel=0.0)
    # antenna standing on the body top near the back edge, through the radio module
    ant = bm_lathe([(0, 0), (1.15, 0), (1.15, 1.2), (0.8, 1.6), (0.6, 1.8), (0.55, 23.4),
                    (0.35, 23.8), (0, 23.9)], 20)
    B.make("Antenna", ant, "black", inst(T(0, -10.8, BH)))

    # ---- parenting for easy posing ----
    bpy.context.view_layer.update()
    for ob in list(B.coll.objects):
        if ob is piv:
            continue
        if ob in tel:
            parent_keep(ob, tel_piv)
        elif ob is not tel_piv:
            parent_keep(ob, piv)
    parent_keep(tel_piv, piv)


# --------------------------------------------------------------------------
#  STAGE: table, wall, lights, cameras
# --------------------------------------------------------------------------
def photo_camera_matrix():
    yaw, pitch, roll = RAD(FIT['yaw']), RAD(FIT['pitch']), RAD(FIT['roll'])
    r, u, fw = Vector((1, 0, 0)), Vector((0, 0, 1)), Vector((0, 1, 0))
    Rz = Matrix.Rotation(yaw, 3, 'Z')
    r, u, fw = Rz @ r, Rz @ u, Rz @ fw
    Rp = Matrix.Rotation(pitch, 3, r)
    u, fw = Rp @ u, Rp @ fw
    Rr = Matrix.Rotation(-roll, 3, fw)
    r, u = Rr @ r, Rr @ u
    C = Vector((0, -FIT['dist'], FIT['cam_z'])) * MM
    return frame(C, r, u, -fw)


def orbit(lx, ly, elev_deg, dist_m, target_z_m):
    """Camera position from a direction in the instrument frame (lx, ly),
    an elevation angle and a distance to the target on the vertical axis."""
    d = (Matrix.Rotation(RAD(INST_YAW), 3, 'Z') @ Vector((lx, ly, 0))).normalized()
    e = RAD(elev_deg)
    return (d.x * math.cos(e) * dist_m, d.y * math.cos(e) * dist_m,
            target_z_m + math.sin(e) * dist_m)


def build_stage(B):
    wood = bpy.data.materials.get("Stage_Walnut") or bpy.data.materials.new("Stage_Walnut")
    if bpy.app.version < (5, 0, 0):
        try:
            wood.use_nodes = True
        except Exception:
            pass
    nt = wood.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1.0, 0.05, 1.0)
    mp.inputs["Rotation"].default_value = (0, 0, RAD(-28))
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 6.0
    noise.inputs["Detail"].default_value = 6.0
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.inputs["Scale"].default_value = 60.0
    wave.inputs["Distortion"].default_value = 14.0
    wave.inputs["Detail"].default_value = 4.0
    wave.inputs["Detail Scale"].default_value = 1.5
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = srgb("#6E4A30")
    ramp.color_ramp.elements[1].color = srgb("#A87E5A")
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], wave.inputs["Vector"])
    nt.links.new(wave.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    _set(bsdf, "Roughness", 0.42)
    _set(bsdf, "Coat Weight", 0.12)
    B.m["wood"] = wood
    B.m["wall"] = material("Stage_Wall", "#D2CEC8", 0.9)

    Mw = R('Z', WALL['angle'])
    B.make("Table", bm_box(3000, 3000, 18), "wood", Mw @ T(0, 0, -9), bevel=1.5)
    B.make("Wall", bm_box(1400, 10, 900), "wall", Mw @ T(0, WALL['y'] + 5, 441))

    def light(name, kind, loc, energy, size, target=(0, 0, 0.12), color=(1, 1, 1)):
        ld = bpy.data.lights.new(name, kind)
        ld.energy = energy
        ld.color = color
        if kind == 'AREA':
            ld.shape = 'DISK'
            ld.size = size
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        d = Vector(target) - Vector(loc)
        ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
        B.coll.objects.link(ob)
        return ob

    # soft window light from the left (operator side lit, knob side in shade)
    light("Key_Window", 'AREA', (-0.55, -0.30, 0.38), 3.0, 0.90, color=(1.0, 0.97, 0.93))
    light("Fill_Right", 'AREA', (0.45, -0.40, 0.22), 0.9, 0.60, color=(0.95, 0.97, 1.0))
    light("Top_Soft", 'AREA', (0.0, -0.05, 0.60), 1.6, 0.80)

    def camera(name, M=None, loc=None, target=None, lens=60.0, fstop=None, sensor=36.0):
        cd = bpy.data.cameras.new(name)
        cd.sensor_fit = 'HORIZONTAL'
        cd.sensor_width = sensor
        cd.lens = lens
        cd.clip_start = 0.005
        ob = bpy.data.objects.new(name, cd)
        if M is not None:
            ob.matrix_world = M
        else:
            ob.location = loc
            d = Vector(target) - Vector(loc)
            ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
            if fstop:
                cd.dof.use_dof = True
                cd.dof.aperture_fstop = fstop
                cd.dof.focus_distance = d.length
        B.coll.objects.link(ob)
        return ob

    cams = dict(
        photo=camera("Cam_Photo", M=photo_camera_matrix(),
                     lens=FIT['f_px'] / FIT['img_w'] * 36.0),
        hero=camera("Cam_Hero", loc=orbit(0.55, 0.83, 10, 0.40, 0.105),
                    target=(0.0, 0.0, 0.105), lens=60, fstop=11.0),
        close=camera("Cam_Closeup", loc=orbit(-0.62, -0.78, 24, 0.23, 0.153),
                     target=(0.0, 0.0, 0.153), lens=70, fstop=16.0),
        front=camera("Cam_Front", loc=orbit(0.18, 0.98, 10, 0.23, 0.158),
                     target=(0.0, 0.0, 0.158), lens=70, fstop=16.0),
    )
    sc = bpy.context.scene
    world = sc.world or bpy.data.worlds.new("World")
    sc.world = world
    if bpy.app.version < (5, 0, 0):
        try:
            world.use_nodes = True
        except Exception:
            pass
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = srgb("#D8D4CE")
        bg.inputs["Strength"].default_value = 0.38
    sc.camera = cams["photo"]
    return cams


# --------------------------------------------------------------------------
#  MAIN
# --------------------------------------------------------------------------
def build(stage=True):
    sc = bpy.context.scene
    sc.unit_settings.system = 'METRIC'
    sc.unit_settings.length_unit = 'CENTIMETERS'
    mats = build_materials()
    B = Builder(mats)
    root = B.collection("Total_Station_20cm")
    B.collection("TS_Tripod", root);     build_tripod(B)
    B.collection("TS_Tribrach", root);   build_tribrach(B)
    B.collection("TS_Instrument", root); build_instrument(B)
    cams = None
    if stage:
        B.collection("TS_Stage");        cams = build_stage(B)
    return root, cams


def model_objects():
    root = bpy.data.collections["Total_Station_20cm"]
    return [o for o in root.all_objects if o.type == 'MESH' and not o.name.startswith("cutter")]


def report():
    bpy.context.view_layer.update()
    obs = model_objects()
    zs, tris = [], 0
    for o in obs:
        for c in o.bound_box:
            zs.append((o.matrix_world @ Vector(c)).z)
        tris += sum(len(p.vertices) - 2 for p in o.data.polygons)
    print(f"[TS] objects: {len(obs)}  triangles: {tris}  height: {(max(zs) - min(zs)) * 1000:.2f} mm "
          f"(z {min(zs) * 1000:.2f} .. {max(zs) * 1000:.2f})")


def render(out_dir, which=("photo", "hero", "close", "front"), samples=96, scale=4):
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = 'PNG'
    try:
        sc.view_settings.view_transform = 'Standard'
        sc.view_settings.look = 'None'
    except Exception:
        pass
    os.makedirs(out_dir, exist_ok=True)
    wall = bpy.data.objects.get("Wall")
    names = dict(photo="Cam_Photo", hero="Cam_Hero", close="Cam_Closeup", front="Cam_Front")
    for key in which:
        cam = bpy.data.objects[names[key]]
        sc.camera = cam
        if key == "photo":
            sc.render.resolution_x = FIT['img_w'] * scale
            sc.render.resolution_y = FIT['img_h'] * scale
        else:
            sc.render.resolution_x, sc.render.resolution_y = 1200, 1500
        if wall:
            wall.hide_render = key != "photo"
        sc.render.filepath = os.path.join(out_dir, f"{key}.png")
        bpy.ops.render.render(write_still=True)
        print("[TS] rendered", sc.render.filepath, flush=True)
    sc.camera = bpy.data.objects["Cam_Photo"]
    if wall:
        wall.hide_render = False


def export(out_dir, base="total_station_20cm"):
    for o in bpy.context.scene.objects:
        o.select_set(False)
    obs = model_objects()
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = obs[0]
    bpy.ops.export_scene.gltf(filepath=os.path.join(out_dir, base + ".glb"),
                              use_selection=True, export_format='GLB')
    bpy.ops.wm.obj_export(filepath=os.path.join(out_dir, base + ".obj"),
                          export_selected_objects=True, export_materials=True)
    bpy.ops.wm.stl_export(filepath=os.path.join(out_dir, base + "_mm.stl"),
                          export_selected_objects=True, global_scale=1000.0)
    print("[TS] exported to", out_dir, flush=True)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    here = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
    standalone = bpy.app.background
    if standalone:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.context.scene.world = bpy.data.worlds.new("World")
    build(stage=True)
    report()
    if standalone:
        out = os.environ.get("TS_OUT", os.path.join(here, "renders"))
        if "--render" in argv:
            which = os.environ.get("TS_VIEWS", "photo,hero,close,front").split(",")
            render(out, which, samples=int(os.environ.get("TS_SAMPLES", "96")),
                   scale=int(os.environ.get("TS_SCALE", "4")))
        if "--nosave" not in argv:
            bpy.ops.wm.save_as_mainfile(filepath=os.path.join(here, "total_station_20cm.blend"))
        if "--export" in argv:
            export(here)
