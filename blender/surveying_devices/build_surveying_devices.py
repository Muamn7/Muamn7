"""
Surveying devices (total station + tripod) - procedural Blender model.
نموذج أجهزة مساحة (توتال ستيشن + حامل ثلاثي) - مولّد برمجياً في بلندر

Two devices, each exactly 200 mm (20 cm) tall, built in millimetres:
  1) TS_Classic  - green classic total station on a yellow / red tripod
  2) TS_Robotic  - grey / yellow robotic total station on a yellow / orange tripod

How to use inside Blender (4.2+ / 5.x):
  Scripting tab -> Open this file -> Run Script.
  A new scene "Surveying_Devices" is created (your current scene is not touched).

Headless:
  blender -b -P build_surveying_devices.py -- --out <folder> [--render]
"""

import bpy
import bmesh
import math
import os
import sys
from mathutils import Vector, Matrix

TARGET_HEIGHT = 200.0  # mm  (1 Blender unit = 1 mm)
SCENE_NAME = "Surveying_Devices"


# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------

def srgb(h):
    """Hex sRGB -> linear RGBA."""
    h = h.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255.0
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return (out[0], out[1], out[2], 1.0)


def _bsdf(mat):
    if bpy.app.version < (5, 0, 0):
        mat.use_nodes = True
    return mat.node_tree.nodes.get("Principled BSDF")


def _set(node, name, value):
    if name in node.inputs:
        node.inputs[name].default_value = value


def make_mat(name, color, rough=0.45, metal=0.0, coat=0.0, spec=0.5,
             transmission=0.0, ior=1.45, emission=None, emit_strength=0.0):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    b = _bsdf(mat)
    _set(b, "Base Color", srgb(color) if isinstance(color, str) else color)
    _set(b, "Roughness", rough)
    _set(b, "Metallic", metal)
    _set(b, "Coat Weight", coat)
    _set(b, "Coat Roughness", 0.08)
    _set(b, "Specular IOR Level", spec)
    _set(b, "Transmission Weight", transmission)
    _set(b, "IOR", ior)
    if emission:
        _set(b, "Emission Color", srgb(emission))
        _set(b, "Emission Strength", emit_strength)
    mat.diffuse_color = srgb(color) if isinstance(color, str) else color
    return mat


def wood_material():
    mat = bpy.data.materials.new("Wood_Table")
    b = _bsdf(mat)
    nt = mat.node_tree
    n, l = nt.nodes, nt.links
    tc = n.new("ShaderNodeTexCoord")
    mp = n.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (0.004, 0.06, 0.004)
    wave = n.new("ShaderNodeTexWave")
    wave.wave_type = "RINGS"
    wave.inputs["Scale"].default_value = 2.0
    wave.inputs["Distortion"].default_value = 6.0
    wave.inputs["Detail"].default_value = 3.0
    noise = n.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 40.0
    noise.inputs["Detail"].default_value = 8.0
    mix = n.new("ShaderNodeMix")
    mix.data_type = "FLOAT"
    mix.inputs["Factor"].default_value = 0.25
    ramp = n.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = srgb("5a2d14")
    ramp.color_ramp.elements[1].color = srgb("9c5a2e")
    bump = n.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.08
    l.new(tc.outputs["Object"], mp.inputs["Vector"])
    l.new(mp.outputs["Vector"], wave.inputs["Vector"])
    l.new(mp.outputs["Vector"], noise.inputs["Vector"])
    l.new(wave.outputs["Fac"], mix.inputs["A"])
    l.new(noise.outputs["Fac"], mix.inputs["B"])
    l.new(mix.outputs["Result"], ramp.inputs["Fac"])
    l.new(ramp.outputs["Color"], b.inputs["Base Color"])
    l.new(mix.outputs["Result"], bump.inputs["Height"])
    l.new(bump.outputs["Normal"], b.inputs["Normal"])
    _set(b, "Roughness", 0.35)
    _set(b, "Coat Weight", 0.3)
    mat.diffuse_color = srgb("8a4f28")
    return mat


# ---------------------------------------------------------------------------
# Geometry helpers  (everything is created as real mesh data, no booleans)
# ---------------------------------------------------------------------------

def _map(a, b, d, axis):
    """Profile coords (a, b) + depth d -> xyz for the chosen extrusion axis."""
    if axis == "Z":
        return (a, b, d)
    if axis == "X":
        return (d, a, b)      # a = y, b = z
    return (a, d, b)          # axis Y: a = x, b = z


def rpoly(corners, r, seg=6):
    """Polygon with filleted corners (works for convex and concave corners)."""
    if r <= 0:
        return list(corners)
    out = []
    n = len(corners)
    for i in range(n):
        P = Vector(corners[i])
        A = Vector(corners[i - 1])
        B = Vector(corners[(i + 1) % n])
        u = (A - P).normalized()
        v = (B - P).normalized()
        ang = u.angle(v)
        rr = min(r, 0.49 * min((A - P).length, (B - P).length) * math.tan(ang / 2))
        t = rr / math.tan(ang / 2)
        p1, p2 = P + u * t, P + v * t
        C = P + (u + v).normalized() * (rr / math.sin(ang / 2))
        a1 = math.atan2(p1.y - C.y, p1.x - C.x)
        a2 = math.atan2(p2.y - C.y, p2.x - C.x)
        da = a2 - a1
        while da > math.pi:
            da -= 2 * math.pi
        while da < -math.pi:
            da += 2 * math.pi
        for k in range(seg + 1):
            a = a1 + da * k / seg
            out.append((C.x + rr * math.cos(a), C.y + rr * math.sin(a)))
    return out


def rrect(w, h, r, cx=0.0, cy=0.0, seg=6):
    w2, h2 = w / 2, h / 2
    return rpoly([(cx - w2, cy - h2), (cx + w2, cy - h2),
                  (cx + w2, cy + h2), (cx - w2, cy + h2)], r, seg)


def circle_pts(r, n=48, cx=0.0, cy=0.0):
    return [(cx + r * math.cos(2 * math.pi * i / n),
             cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]


def knurl_pts(r_out, r_in, teeth=28, cx=0.0, cy=0.0):
    pts = []
    step = 2 * math.pi / teeth
    for i in range(teeth):
        a = i * step
        for frac, rad in ((0.0, r_in), (0.15, r_out), (0.5, r_out), (0.65, r_in)):
            aa = a + frac * step
            pts.append((cx + rad * math.cos(aa), cy + rad * math.sin(aa)))
    return pts


def hex_pts(r, cx=0.0, cy=0.0):
    return [(cx + r * math.cos(math.pi / 6 + i * math.pi / 3),
             cy + r * math.sin(math.pi / 6 + i * math.pi / 3)) for i in range(6)]


def bm_prism(pts, d0, d1, axis="Z", taper=1.0):
    """Extrude a closed 2D profile from depth d0 to d1 (optional taper at d1)."""
    bm = bmesh.new()
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    bot = [bm.verts.new(_map(a, b, d0, axis)) for a, b in pts]
    top = [bm.verts.new(_map(cx + (a - cx) * taper, cy + (b - cy) * taper, d1, axis))
           for a, b in pts]
    bm.faces.new(bot)
    bm.faces.new(top)
    n = len(pts)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((bot[i], bot[j], top[j], top[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def bm_lathe(profile, axis="Z", segs=64, cx=0.0, cy=0.0):
    """Revolve a (radius, height) profile around an axis through (cx, cy)."""
    bm = bmesh.new()
    rings = []
    for r, h in profile:
        if r < 1e-6:
            rings.append([bm.verts.new(_map(cx, cy, h, axis))])
        else:
            rings.append([bm.verts.new(_map(cx + r * math.cos(2 * math.pi * i / segs),
                                             cy + r * math.sin(2 * math.pi * i / segs),
                                             h, axis)) for i in range(segs)])
    for k in range(len(rings) - 1):
        A, B = rings[k], rings[k + 1]
        if len(A) == 1 and len(B) == 1:
            continue
        for i in range(segs):
            j = (i + 1) % segs
            if len(A) == 1:
                bm.faces.new((A[0], B[i], B[j]))
            elif len(B) == 1:
                bm.faces.new((A[i], A[j], B[0]))
            else:
                bm.faces.new((A[i], A[j], B[j], B[i]))
    if len(rings[0]) > 1:
        bm.faces.new(rings[0])
    if len(rings[-1]) > 1:
        bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def bm_torus(R, r, axis="Z", cx=0.0, cy=0.0, d=0.0, seg=48, rseg=16):
    bm = bmesh.new()
    rings = []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        ring = []
        for k in range(rseg):
            b = 2 * math.pi * k / rseg
            rad = R + r * math.cos(b)
            ring.append(bm.verts.new(_map(cx + rad * math.cos(a), cy + rad * math.sin(a),
                                          d + r * math.sin(b), axis)))
        rings.append(ring)
    for i in range(seg):
        A, B = rings[i], rings[(i + 1) % seg]
        for k in range(rseg):
            m = (k + 1) % rseg
            bm.faces.new((A[k], B[k], B[m], A[m]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


class Builder:
    """Creates objects into one collection, parented to a root empty."""

    def __init__(self, coll, parent):
        self.coll = coll
        self.parent = parent
        self.count = 0

    def empty(self, name, loc=(0, 0, 0), rot=(0, 0, 0), parent=None):
        e = bpy.data.objects.new(name, None)
        e.empty_display_size = 6
        e.empty_display_type = "PLAIN_AXES"
        self.coll.objects.link(e)
        e.parent = parent or self.parent
        e.location = loc
        e.rotation_euler = rot
        return e

    def add(self, name, bm, mat, bevel=0.35, seg=3, parent=None, loc=(0, 0, 0),
            rot=(0, 0, 0), sharp=32.0, subsurf=0):
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
        try:
            me.set_sharp_from_angle(angle=math.radians(sharp))
        except Exception:
            pass
        me.materials.append(mat)
        o = bpy.data.objects.new(name, me)
        self.coll.objects.link(o)
        o.parent = parent or self.parent
        o.location = loc
        o.rotation_euler = rot
        if bevel > 0:
            m = o.modifiers.new("Bevel", "BEVEL")
            m.width = bevel
            m.segments = seg
            m.limit_method = "ANGLE"
            m.angle_limit = math.radians(30)
            m.use_clamp_overlap = True
            m.harden_normals = True
            m.miter_outer = "MITER_ARC"
        if subsurf:
            s = o.modifiers.new("Subdivision", "SUBSURF")
            s.levels = subsurf
            s.render_levels = subsurf
        self.count += 1
        return o


# ---------------------------------------------------------------------------
# Tripod
# ---------------------------------------------------------------------------

def build_tripod(B, M, style):
    """Wooden-style surveying tripod. Head top at z = 136 mm."""
    leg_w, leg_d = style["leg_w"], style["leg_d"]
    head_top = 136.0
    hinge_r, hinge_z = 23.5, 128.5
    foot_r = style["foot_r"]
    azimuths = [-90.0, 30.0, 150.0]  # one leg towards the viewer (-Y)

    # --- head plate -------------------------------------------------------
    B.add("Tripod_Head", bm_lathe([(0, 126.0), (19.0, 126.0), (21.0, 127.0), (22.5, 128.6),
                                   (22.5, 133.8), (21.6, 135.2), (20.0, 136.0), (0, 136.0)]),
          M["head"], bevel=0.3)
    B.add("Tripod_Head_Top", bm_lathe([(0, 135.8), (17.0, 135.8), (17.0, head_top + 0.6),
                                       (0, head_top + 0.6)]), M["head_top"], bevel=0.2)
    # central opening ring of the head
    B.add("Tripod_Head_Ring", bm_torus(9.0, 0.6, d=head_top + 0.6), M["metal"], bevel=0)
    # fixing (centring) screw under the head
    B.add("Tripod_Fix_Screw", bm_lathe([(0, 104.0), (2.0, 104.0), (2.0, 126.5), (0, 126.5)], segs=24),
          M["metal"], bevel=0.15)
    B.add("Tripod_Fix_Knob", bm_prism(knurl_pts(6.0, 5.4, 30), 106.0, 112.0), M["knob"], bevel=0.2)
    B.add("Tripod_Fix_Knob_Cap", bm_lathe([(0, 112.0), (5.0, 112.0), (4.0, 113.6), (0, 113.6)], segs=32),
          M["knob"], bevel=0.15)
    B.add("Tripod_Plumb_Hook", bm_torus(1.8, 0.45, axis="Y", cx=0, cy=102.0), M["metal"], bevel=0)

    # tilt of each leg (hinge -> foot)
    radial = foot_r - hinge_r
    L = math.hypot(radial, hinge_z)
    tilt = math.atan2(radial, hinge_z)

    for idx, az in enumerate(azimuths):
        a = math.radians(az)
        rz = a - math.pi / 2
        tag = "ABC"[idx]

        # head lug (two cheeks + bolt), only rotated about Z
        lug = B.empty(f"Tripod_Lug_{tag}", rot=(0, 0, rz))
        cheek = rrect(13.0, 9.0, 2.5, cx=hinge_r - 2.5, cy=hinge_z - 1.0)
        gap = leg_w / 2 + 0.6
        for s, side in ((-1, "L"), (1, "R")):
            x0, x1 = (s * gap, s * (gap + 2.2))
            B.add(f"Tripod_Cheek_{tag}{side}", bm_prism(cheek, min(x0, x1), max(x0, x1), axis="X"),
                  M["head"], bevel=0.3, parent=lug)
            # bolt head / wing nut
            B.add(f"Tripod_Bolt_{tag}{side}",
                  bm_prism(hex_pts(2.1, cx=hinge_r, cy=hinge_z),
                           s * (gap + 2.2), s * (gap + 3.6), axis="X"),
                  M["metal"], bevel=0.15, parent=lug)
        B.add(f"Tripod_Bolt_{tag}", bm_lathe([(0, -gap - 2.4), (1.2, -gap - 2.4), (1.2, gap + 2.4),
                                             (0, gap + 2.4)], axis="X", segs=16,
                                            cx=hinge_r, cy=hinge_z), M["metal"], bevel=0, parent=lug)
        # wing lever on one bolt
        B.add(f"Tripod_Wing_{tag}", bm_prism(rpoly([(-1.2, -2.0), (1.2, -2.0), (0.8, 7.0), (-0.8, 7.0)], 0.6),
                                             gap + 3.6, gap + 4.6, axis="X"),
              M["knob"], bevel=0.15, parent=lug, loc=(0, hinge_r, hinge_z))

        # leg frame: local -Z runs down the leg, +Y is radially outwards
        pivot = B.empty(f"Tripod_Leg_{tag}",
                        loc=(hinge_r * math.cos(a), hinge_r * math.sin(a), hinge_z),
                        rot=(tilt, 0, rz))

        w, d = leg_w, leg_d
        lw, ld = w - 1.8, d - 1.4  # lower sliding section
        if style["twin_legs"]:
            # two slim rails per upper section (modern aluminium look)
            for s, side in ((-1, "L"), (1, "R")):
                rail = rrect(w * 0.36, d, 0.8, cx=s * w * 0.32)
                B.add(f"Leg_{tag}_Upper{side}", bm_prism(rail, -80.0, 3.5), M["leg"],
                      bevel=0.25, parent=pivot)
            B.add(f"Leg_{tag}_Brace", bm_prism(rrect(w, d * 0.7, 0.6), -36.0, -32.0), M["leg"],
                  bevel=0.2, parent=pivot)
        else:
            B.add(f"Leg_{tag}_Upper", bm_prism(rrect(w, d, 1.4), -80.0, 3.5), M["leg"],
                  bevel=0.35, parent=pivot)
            # wood-grain style groove down the outer face
            B.add(f"Leg_{tag}_Groove", bm_prism(rrect(w * 0.5, 0.4, 0.15, cy=d / 2 + 0.05), -72.0, -10.0),
                  M["leg_dark"], bevel=0, parent=pivot)

        # hinge cap at the top of the leg
        B.add(f"Leg_{tag}_HingeCap", bm_prism(rrect(w + 0.6, d + 1.6, 2.4), -9.0, 4.2), M["band"],
              bevel=0.35, parent=pivot)
        # upper band
        B.add(f"Leg_{tag}_Band1", bm_prism(rrect(w + 2.0, d + 2.0, 1.6), -46.0, -40.0), M["band"],
              bevel=0.35, parent=pivot)
        # clamp at the telescopic joint
        B.add(f"Leg_{tag}_Clamp", bm_prism(rrect(w + 2.4, d + 2.4, 1.8), -88.0, -77.0), M["band"],
              bevel=0.4, parent=pivot)
        B.add(f"Leg_{tag}_ClampScrew", bm_lathe([(0, d / 2 + 1.0), (1.3, d / 2 + 1.0), (1.3, d / 2 + 3.0),
                                                  (0, d / 2 + 3.0)], axis="Y", segs=16, cx=0, cy=-82.5),
              M["metal"], bevel=0.1, parent=pivot)
        B.add(f"Leg_{tag}_ClampKnob", bm_prism(knurl_pts(3.0, 2.6, 18, cx=0, cy=-82.5),
                                               d / 2 + 3.0, d / 2 + 5.4, axis="Y"),
              M["knob"], bevel=0.15, parent=pivot)
        # lower sliding section
        lower_end = -(L - 19.0)
        B.add(f"Leg_{tag}_Lower", bm_prism(rrect(lw, ld, 1.1), lower_end, -78.0), M["leg"],
              bevel=0.3, parent=pivot)
        # lower band
        B.add(f"Leg_{tag}_Band2", bm_prism(rrect(lw + 1.8, ld + 1.8, 1.4), lower_end + 14.0,
                                           lower_end + 20.0), M["band"], bevel=0.35, parent=pivot)
        # foot shoe + spike
        shoe_top = lower_end + 3.0
        shoe_bot = -(L - 9.5)
        B.add(f"Leg_{tag}_Shoe", bm_prism(rrect(w + 0.6, d + 0.8, 1.6), shoe_bot, shoe_top), M["foot"],
              bevel=0.35, parent=pivot)
        B.add(f"Leg_{tag}_Spike", bm_lathe([(0, -L + 2.0), (1.6, -L + 3.2), (3.6, shoe_bot + 0.2),
                                             (min(w, d) / 2, shoe_bot), (min(w, d) / 2, shoe_bot + 0.4),
                                             (0, shoe_bot + 0.4)], segs=32),
              M["foot"], bevel=0.2, parent=pivot)
        B.add(f"Leg_{tag}_Tip", bm_lathe([(0, -L), (1.6, -L + 2.4), (0, -L + 2.4)], segs=24),
              M["metal"], bevel=0, parent=pivot)
        # foot step (pedal) on the outer side
        B.add(f"Leg_{tag}_Pedal", bm_prism(rpoly([(-2.6, d / 2 + 0.2), (2.6, d / 2 + 0.2),
                                                  (2.2, d / 2 + 4.2), (-2.2, d / 2 + 4.2)], 0.8),
                                            shoe_bot + 2.0, shoe_bot + 4.0),
              M["foot"], bevel=0.25, parent=pivot)


# ---------------------------------------------------------------------------
# Total station
# ---------------------------------------------------------------------------

def build_tribrach(B, M, z0):
    """Tribrach (levelling base) from z0 up to z0 + 11."""
    corners = [(19.0 * math.cos(math.radians(a)), 19.0 * math.sin(math.radians(a)))
               for a in (90.0, 210.0, 330.0)]
    B.add("Tribrach_Base", bm_prism(rpoly(corners, 6.0, 8), z0, z0 + 3.2), M["dark"], bevel=0.35)
    for i, a in enumerate((90.0, 210.0, 330.0)):
        cx, cy = 14.0 * math.cos(math.radians(a)), 14.0 * math.sin(math.radians(a))
        B.add(f"Tribrach_LevelScrew_{i}", bm_prism(knurl_pts(3.8, 3.35, 26, cx, cy), z0 + 3.2, z0 + 7.6),
              M["knob"], bevel=0.15)
        B.add(f"Tribrach_LevelThread_{i}", bm_lathe([(0, z0 + 7.6), (1.3, z0 + 7.6), (1.3, z0 + 10.6),
                                                     (0, z0 + 10.6)], segs=16, cx=cx, cy=cy),
              M["metal"], bevel=0)
    B.add("Tribrach_Plate", bm_lathe([(0, z0 + 8.4), (15.5, z0 + 8.4), (16.2, z0 + 9.2), (16.2, z0 + 10.6),
                                      (15.2, z0 + 11.2), (0, z0 + 11.2)]), M["dark"], bevel=0.2)
    # circular bubble level
    a = math.radians(-30.0)
    bx, by = 11.0 * math.cos(a), 11.0 * math.sin(a)
    B.add("Tribrach_Bubble_Housing", bm_lathe([(0, z0 + 11.2), (2.6, z0 + 11.2), (2.6, z0 + 12.6),
                                               (2.0, z0 + 12.6), (2.0, z0 + 12.2), (0, z0 + 12.2)],
                                              segs=32, cx=bx, cy=by), M["metal"], bevel=0.1)
    B.add("Tribrach_Bubble", bm_lathe([(0, z0 + 12.2), (2.0, z0 + 12.2), (0, z0 + 13.0)], segs=32, cx=bx, cy=by),
          M["bubble"], bevel=0)
    # locking lever
    B.add("Tribrach_Lock", bm_prism(rpoly([(-2.0, 0), (2.0, 0), (1.6, 8.0), (-1.6, 8.0)], 0.8),
                                     z0 + 1.4, z0 + 3.0),
          M["knob"], bevel=0.2, rot=(0, 0, math.radians(150 - 90)), loc=(0, 0, 0))
    return z0 + 11.2


def build_display(B, M, name, x, z, y_face, facing, w=20.0, h=9.0):
    """Control panel with LCD + keypad on a face at y = y_face (facing = -1 front / +1 back)."""
    f = facing
    B.add(f"{name}_Bezel", bm_prism(rrect(w, h, 1.4, cx=x, cy=z), y_face, y_face + f * 0.8, axis="Y"),
          M["panel"], bevel=0.2)
    sx = x - w * 0.18
    B.add(f"{name}_LCD", bm_prism(rrect(w * 0.5, h * 0.62, 0.5, cx=sx, cy=z + 0.4), y_face + f * 0.8,
                                   y_face + f * 1.0, axis="Y"), M["lcd"], bevel=0)
    # LCD content (simple bar lines, no text)
    for i in range(3):
        bw = w * (0.38 - 0.08 * i)
        B.add(f"{name}_LCD_Line{i}", bm_prism(rrect(bw, 0.45, 0.1, cx=sx - (w * 0.5 - bw) / 2 + 0.8,
                                                    cy=z + 1.9 - i * 1.5),
                                              y_face + f * 1.0, y_face + f * 1.06, axis="Y"),
              M["lcd_ink"], bevel=0)
    kx0 = x + w * 0.16
    for r in range(3):
        for c in range(3):
            mat = M["key_red"] if (r == 0 and c == 2) else M["key"]
            B.add(f"{name}_Key_{r}{c}", bm_prism(rrect(1.7, 1.25, 0.4, cx=kx0 + c * 2.25, cy=z + 2.4 - r * 2.0),
                                                 y_face + f * 0.8, y_face + f * 1.35, axis="Y"),
                  mat, bevel=0.12)


def build_total_station(B, M, style, z0):
    classic = style["kind"] == "classic"
    z = build_tribrach(B, M, z0)                       # ~147.2

    # --- lower body with control panels -----------------------------------
    zb0, zb1 = z, z + 12.0
    if classic:
        prof = rpoly([(-24.0, zb0), (24.0, zb0), (19.5, zb1), (-19.5, zb1)], 1.6)
        B.add("Body_Lower", bm_prism(prof, -17.0, 17.0, axis="Y"), M["body"], bevel=0.4)
    else:
        B.add("Body_Lower", bm_prism(rrect(44.0, 36.0, 7.0), zb0, zb1, taper=0.92), M["dark"], bevel=0.5)
        B.add("Body_Lower_Trim", bm_prism(rrect(41.0, 33.0, 6.0), zb1 - 0.2, zb1 + 0.8), M["accent"], bevel=0.2)
    yf = -17.0 if classic else -16.6
    build_display(B, M, "Panel_Front", -1.0, zb0 + 6.0, yf, -1)
    build_display(B, M, "Panel_Back", 1.0, zb0 + 6.0, -yf, +1, w=16.0)
    # horizontal tangent / clamp knob on the side of the body
    B.add("Knob_HorizTangent", bm_prism(knurl_pts(2.8, 2.45, 22, cx=8.0, cy=zb0 + 5.0), 20.0, 25.5, axis="X"),
          M["knob"], bevel=0.15)
    B.add("Knob_HorizTangent_Shaft", bm_lathe([(0, 18.0), (1.2, 18.0), (1.2, 20.2), (0, 20.2)], axis="X",
                                              segs=16, cx=8.0, cy=zb0 + 5.0), M["metal"], bevel=0)
    B.add("Knob_HorizClamp", bm_prism(rpoly([(-1.6, 0), (1.6, 0), (1.0, 6.0), (-1.0, 6.0)], 0.6),
                                      -1.0, 1.0, axis="Y"), M["knob"], bevel=0.2,
          loc=(-21.5, -8.0, zb0 + 4.0), rot=(0, math.radians(-60), 0))

    # --- rotation ring (horizontal circle housing) -------------------------
    zr0 = zb1 + (0 if classic else 0.8)
    B.add("Body_Ring", bm_lathe([(0, zr0), (18.0, zr0), (18.6, zr0 + 0.6), (18.6, zr0 + 2.2),
                                 (17.6, zr0 + 2.8), (0, zr0 + 2.8)]), M["dark"], bevel=0.15)
    zs0 = zr0 + 2.8

    # --- alidade base + standards (U frame) --------------------------------
    B.add("Alidade_Base", bm_prism(rrect(42.0, 30.0, 6.0), zs0, zs0 + 3.5), M["body"], bevel=0.4)
    zs = zs0 + 3.5                                     # top of base, ~166
    axis_z = zs + 14.5                                 # telescope trunnion axis
    inner, outer = 12.5, 21.0
    if classic:
        std_prof = rpoly([(-14.0, zs - 0.5), (14.0, zs - 0.5), (11.5, zs + 25.0), (-9.5, zs + 25.0)], 4.0)
    else:
        std_prof = rpoly([(-15.0, zs - 0.5), (15.0, zs - 0.5), (15.0, zs + 18.0), (10.5, zs + 25.5),
                          (-12.0, zs + 25.5), (-15.0, zs + 21.0)], 2.2)
    std_top = zs + (25.0 if classic else 25.5)
    for s, side in ((-1, "L"), (1, "R")):
        x0, x1 = s * inner, s * outer
        B.add(f"Standard_{side}", bm_prism(std_prof, min(x0, x1), max(x0, x1), axis="X"),
              M["body"], bevel=0.55)
        # trunnion bearing cover
        B.add(f"Trunnion_Cap_{side}", bm_lathe([(0, s * outer), (6.0, s * outer), (6.0, s * (outer + 0.8)),
                                                (5.2, s * (outer + 1.3)), (0, s * (outer + 1.3))],
                                               axis="X", segs=48, cx=0, cy=axis_z), M["dark"], bevel=0.12)

    if classic:
        # battery cover on the left standard
        B.add("Battery_Cover", bm_prism(rrect(15.0, 9.0, 2.0, cx=0, cy=zs + 6.0), -outer - 0.7, -outer + 0.1,
                                        axis="X"), M["body_dark"], bevel=0.2)
        B.add("Battery_Latch", bm_prism(rrect(4.0, 1.6, 0.6, cx=0, cy=zs + 9.3), -outer - 1.1, -outer - 0.5,
                                        axis="X"), M["knob"], bevel=0.1)
        # vertical tangent + clamp on the right standard
        B.add("Knob_VertTangent", bm_prism(knurl_pts(3.2, 2.8, 24, cx=-7.0, cy=zs + 6.0), outer, outer + 5.0,
                                           axis="X"), M["knob"], bevel=0.15)
        B.add("Knob_VertClamp", bm_prism(knurl_pts(2.4, 2.1, 18, cx=5.0, cy=zs + 6.0), outer, outer + 3.6,
                                         axis="X"), M["knob"], bevel=0.12)
    else:
        # robotic: big servo covers + yellow side plate
        for s, side in ((-1, "L"), (1, "R")):
            B.add(f"Servo_Cover_{side}", bm_lathe([(0, s * (outer + 1.3)), (8.6, s * (outer - 0.2)),
                                                   (9.4, s * (outer - 0.2)), (9.4, s * (outer + 0.6)),
                                                   (8.6, s * (outer + 1.0)), (0, s * (outer + 1.5))],
                                                  axis="X", segs=64, cx=-1.0, cy=axis_z - 1.5),
                  M["dark"], bevel=0.12)
        B.add("Side_Plate_R", bm_prism(rpoly([(-15.6, zs + 1.0), (-11.0, zs + 1.0), (-11.0, zs + 22.0),
                                              (-13.0, zs + 24.6), (-15.6, zs + 20.4)], 1.0),
                                       outer - 0.4, outer + 0.9, axis="X"), M["accent"], bevel=0.2)
        B.add("Knob_VertTangent", bm_prism(knurl_pts(2.6, 2.3, 20, cx=7.5, cy=zs + 4.5), outer, outer + 3.6,
                                           axis="X"), M["knob"], bevel=0.12)
        # keyboard / function button on the left standard
        B.add("Trigger_Key", bm_prism(rrect(5.0, 3.0, 1.0, cx=8.5, cy=zs + 5.0), -outer - 0.8, -outer + 0.2,
                                      axis="X"), M["accent"], bevel=0.15)

    # --- telescope ----------------------------------------------------------
    B.add("Telescope_Trunnion", bm_lathe([(0, -inner - 0.2), (6.5, -inner - 0.2), (6.5, inner + 0.2),
                                          (0, inner + 0.2)], axis="X", segs=48, cx=0, cy=axis_z),
          M["dark"], bevel=0.2)
    if classic:
        B.add("Telescope_Body", bm_lathe([(0, -11.0), (7.6, -11.0), (8.2, -9.0), (8.2, 6.0), (7.0, 8.0),
                                          (5.4, 9.0), (0, 9.0)], axis="Y", segs=64, cx=0, cy=axis_z),
              M["body"], bevel=0.3)
        B.add("Telescope_Hood", bm_lathe([(0, -10.5), (8.0, -10.5), (8.8, -12.0), (8.8, -18.6), (8.2, -19.6),
                                          (7.0, -19.6), (7.0, -18.8), (0, -18.8)], axis="Y", segs=64,
                                         cx=0, cy=axis_z), M["dark"], bevel=0.2)
        lens_r, lens_y = 7.0, -18.8
        B.add("Focus_Ring", bm_prism(knurl_pts(8.75, 8.35, 48, cx=0, cy=axis_z), -1.0, 3.5, axis="Y"),
              M["knob"], bevel=0.12)
        B.add("Eyepiece", bm_lathe([(0, 8.5), (4.6, 8.5), (4.6, 14.0), (5.4, 14.6), (5.4, 18.2), (4.6, 18.8),
                                    (2.6, 18.8), (2.6, 18.2), (0, 18.2)], axis="Y", segs=48,
                                   cx=0, cy=axis_z), M["rubber"], bevel=0.15)
        B.add("Eyepiece_Ring", bm_prism(knurl_pts(5.1, 4.8, 30, cx=0, cy=axis_z), 10.0, 13.2, axis="Y"),
              M["knob"], bevel=0.1)
        # peep sight on top of telescope
        B.add("Sight", bm_prism(rpoly([(-2.2, 0), (2.2, 0), (1.6, 2.8), (-1.6, 2.8)], 0.4), -6.0, 4.0, axis="Y"),
              M["dark"], bevel=0.15, loc=(0, 0, axis_z + 8.0))
        B.add("Sight_Notch", bm_prism(rpoly([(-0.9, 2.8), (0.9, 2.8), (0, 4.0)], 0.1), -6.0, -4.6, axis="Y"),
              M["metal"], bevel=0, loc=(0, 0, axis_z + 8.0 - 0.0))
    else:
        B.add("Telescope_Body", bm_prism(rrect(20.0, 18.0, 4.5, cx=0, cy=axis_z), -12.0, 9.0, axis="Y"),
              M["dark"], bevel=0.4)
        B.add("Telescope_Band", bm_prism(rrect(20.6, 18.6, 4.8, cx=0, cy=axis_z), -2.0, 1.0, axis="Y"),
              M["body"], bevel=0.2)
        B.add("Telescope_Hood", bm_lathe([(0, -11.5), (8.0, -11.5), (8.4, -13.0), (8.4, -16.4), (7.8, -17.2),
                                          (6.6, -17.2), (6.6, -16.6), (0, -16.6)], axis="Y", segs=64,
                                         cx=0, cy=axis_z - 1.0), M["rubber"], bevel=0.2)
        lens_r, lens_y = 6.6, -16.6
        # tracker / guide-light window above the main lens
        B.add("Guide_Light", bm_prism(rrect(9.0, 2.4, 1.0, cx=0, cy=axis_z + 7.4), -12.6, -11.8, axis="Y"),
              M["guide"], bevel=0.1)
        B.add("Eyepiece", bm_lathe([(0, 8.5), (4.2, 8.5), (4.2, 12.0), (5.0, 12.6), (5.0, 15.8), (4.2, 16.3),
                                    (2.4, 16.3), (2.4, 15.8), (0, 15.8)], axis="Y", segs=48,
                                   cx=0, cy=axis_z - 1.0), M["rubber"], bevel=0.15)
    # lens = coated inner disc + glass
    B.add("Lens_Coating", bm_lathe([(0, lens_y + 0.9), (lens_r, lens_y + 0.9), (lens_r, lens_y + 1.2),
                                    (0, lens_y + 1.2)], axis="Y", segs=64, cx=0,
                                   cy=axis_z - (0 if classic else 1.0)), M["coating"], bevel=0)
    B.add("Lens_Glass", bm_lathe([(0, lens_y - 0.35), (lens_r * 0.6, lens_y - 0.25), (lens_r, lens_y + 0.1),
                                  (lens_r, lens_y + 0.8), (0, lens_y + 0.8)], axis="Y", segs=64, cx=0,
                                 cy=axis_z - (0 if classic else 1.0)), M["glass"], bevel=0)

    # --- carrying handle ----------------------------------------------------
    hz0 = std_top - 0.4
    hz1 = hz0 + (8.6 if classic else 7.6)
    handle = rpoly([(-19.5, hz0), (-13.5, hz0), (-12.0, hz1 - 3.4), (12.0, hz1 - 3.4), (13.5, hz0),
                    (19.5, hz0), (18.0, hz1), (-18.0, hz1)], 1.6)
    yy = -1.0 if classic else 2.0
    B.add("Handle", bm_prism(handle, yy - 3.2, yy + 3.2, axis="Y"), M["handle"], bevel=0.45)
    for s, side in ((-1, "L"), (1, "R")):
        B.add(f"Handle_Screw_{side}", bm_lathe([(0, hz1), (1.6, hz1), (1.4, hz1 + 0.6), (0, hz1 + 0.6)],
                                               segs=24, cx=s * 16.2, cy=yy), M["metal"], bevel=0)
    if not classic:
        # radio antenna (robotic instrument)
        ax, ay = -17.0, 9.0
        B.add("Antenna_Base", bm_lathe([(0, std_top - 0.2), (2.2, std_top - 0.2), (2.2, std_top + 2.0),
                                        (1.4, std_top + 3.2), (0, std_top + 3.2)], segs=32, cx=ax, cy=ay),
              M["dark"], bevel=0.15)
        B.add("Antenna_Rod", bm_lathe([(0, std_top + 3.0), (0.8, std_top + 3.0), (0.55, std_top + 11.6),
                                       (0.9, std_top + 12.0), (0.9, std_top + 13.0), (0, std_top + 13.4)],
                                      segs=24, cx=ax, cy=ay), M["rubber"], bevel=0)
        # prism / reflector-less EDM sensor on top
        B.add("Top_Sensor", bm_prism(rrect(8.0, 10.0, 2.0, cx=0, cy=yy), hz1, hz1 + 1.6), M["dark"], bevel=0.2)


# ---------------------------------------------------------------------------
# Scene
# ---------------------------------------------------------------------------

STYLES = {
    "TS_Classic": dict(
        kind="classic", leg_w=9.6, leg_d=7.0, foot_r=73.0, twin_legs=False,
        colors=dict(body="5f7a58", body_dark="4a6145", handle="55704f", accent="c8231d",
                    leg="f2d40f", leg_dark="d6b400", band="d42a1c", head="cc2a1c", head_top="2c2c2e",
                    foot="d42a1c"),
    ),
    "TS_Robotic": dict(
        kind="robotic", leg_w=8.4, leg_d=6.4, foot_r=70.0, twin_legs=True,
        colors=dict(body="7d8287", body_dark="5a5e62", handle="f2c014", accent="f2c014",
                    leg="f5d816", leg_dark="d8bb00", band="f0701a", head="2e2f31", head_top="f0701a",
                    foot="f0701a"),
    ),
}


def device_materials(prefix, c):
    M = {
        "body": make_mat(f"{prefix}_Body", c["body"], rough=0.42, coat=0.2),
        "body_dark": make_mat(f"{prefix}_BodyDark", c["body_dark"], rough=0.5),
        "handle": make_mat(f"{prefix}_Handle", c["handle"], rough=0.38, coat=0.25),
        "accent": make_mat(f"{prefix}_Accent", c["accent"], rough=0.35, coat=0.3),
        "leg": make_mat(f"{prefix}_Leg", c["leg"], rough=0.35, coat=0.35),
        "leg_dark": make_mat(f"{prefix}_LegGroove", c["leg_dark"], rough=0.5),
        "band": make_mat(f"{prefix}_Band", c["band"], rough=0.35, coat=0.3),
        "head": make_mat(f"{prefix}_Head", c["head"], rough=0.4, coat=0.2),
        "head_top": make_mat(f"{prefix}_HeadTop", c["head_top"], rough=0.45),
        "foot": make_mat(f"{prefix}_Foot", c["foot"], rough=0.38, coat=0.25),
    }
    M.update(SHARED)
    return M


SHARED = {}


def shared_materials():
    SHARED.update({
        "dark": make_mat("Plastic_Dark", "2b2c2e", rough=0.4),
        "panel": make_mat("Panel_Black", "141516", rough=0.3),
        "knob": make_mat("Knob_Black", "18191a", rough=0.5),
        "rubber": make_mat("Rubber", "111111", rough=0.8),
        "metal": make_mat("Metal_Steel", "c9ccd0", rough=0.22, metal=1.0),
        "key": make_mat("Key_Grey", "4a4d52", rough=0.55),
        "key_red": make_mat("Key_Red", "c62a1e", rough=0.45),
        "lcd": make_mat("LCD_Screen", "6e7f6a", rough=0.12, emission="9fb59a", emit_strength=0.35),
        "lcd_ink": make_mat("LCD_Ink", "1c241c", rough=0.3),
        "glass": make_mat("Lens_Glass", "e8f0ff", rough=0.0, transmission=1.0, ior=1.52),
        "coating": make_mat("Lens_Coating", "3a2a6e", rough=0.06, metal=0.85),
        "bubble": make_mat("Bubble_Vial", "9fe07a", rough=0.05, emission="7fd35b", emit_strength=0.6),
        "guide": make_mat("Guide_Light", "8a1010", rough=0.1, emission="ff3a2a", emit_strength=1.5),
    })


def build_device(scene, name, style, x_offset):
    coll = bpy.data.collections.new(name)
    scene.collection.children.link(coll)
    root = bpy.data.objects.new(f"{name}_ROOT", None)
    root.empty_display_type = "ARROWS"
    root.empty_display_size = 30
    coll.objects.link(root)
    B = Builder(coll, root)
    M = device_materials(name, style["colors"])
    build_tripod(B, M, style)
    build_total_station(B, M, style, 136.0)

    # normalise to exactly TARGET_HEIGHT (feet on the floor at z = 0)
    scene.view_layers[0].update()
    zmin, zmax = 1e9, -1e9
    for o in coll.objects:
        if o.type != "MESH":
            continue
        mw = o.matrix_world
        for v in o.data.vertices:
            z = (mw @ v.co).z
            zmin, zmax = min(zmin, z), max(zmax, z)
    s = TARGET_HEIGHT / (zmax - zmin)
    root.scale = (s, s, s)
    root.location = (x_offset, 0.0, -zmin * s)
    root["height_mm"] = TARGET_HEIGHT
    scene.view_layers[0].update()
    print(f"[{name}] parts={B.count}  raw height={zmax - zmin:.2f} mm  scale={s:.4f}")
    return coll, root


def build_environment(scene):
    coll = bpy.data.collections.new("Studio")
    scene.collection.children.link(coll)
    wood = wood_material()
    wall = make_mat("Backdrop", "f7f7f5", rough=0.9)

    bm = bm_prism(rrect(1400.0, 520.0, 0.0, cy=60.0), -18.0, 0.0)
    me = bpy.data.meshes.new("Table")
    bm.to_mesh(me)
    bm.free()
    me.materials.append(wood)
    table = bpy.data.objects.new("Table", me)
    coll.objects.link(table)

    # curved backdrop sweep
    bm = bmesh.new()
    # (y, z) profile: flat, quarter circle (R = 150), then vertical wall
    prof = [(170.0 + 150.0 * math.sin(math.pi / 2 * i / 16),
             150.0 - 150.0 * math.cos(math.pi / 2 * i / 16)) for i in range(17)]
    prof += [(320.0, 900.0)]
    rows = []
    for y, z in prof:
        rows.append([bm.verts.new((x, y, z)) for x in (-1400.0, 1400.0)])
    for k in range(len(rows) - 1):
        bm.faces.new((rows[k][0], rows[k][1], rows[k + 1][1], rows[k + 1][0]))
    me = bpy.data.meshes.new("Backdrop")
    bm.to_mesh(me)
    bm.free()
    me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    me.materials.append(wall)
    back = bpy.data.objects.new("Backdrop", me)
    back.location = (0, 0, 0.05)
    coll.objects.link(back)

    # lights (sizes/powers tuned for 1 BU = 1 mm)
    def area(name, loc, target, size, power, color=(1, 1, 1)):
        ld = bpy.data.lights.new(name, "AREA")
        ld.shape = "DISK"
        ld.size = size
        ld.energy = power
        ld.color = color
        lo = bpy.data.objects.new(name, ld)
        lo.location = loc
        d = Vector(target) - Vector(loc)
        lo.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
        coll.objects.link(lo)
        return lo

    area("Key_Light", (-380.0, -520.0, 520.0), (0, 0, 100), 420.0, 9.0e5, (1.0, 0.97, 0.92))
    area("Fill_Light", (520.0, -380.0, 260.0), (0, 0, 90), 500.0, 3.2e5, (0.92, 0.96, 1.0))
    area("Rim_Light", (150.0, 260.0, 520.0), (0, 0, 120), 300.0, 2.5e5)

    world = bpy.data.worlds.new("Studio_World")
    if bpy.app.version < (5, 0, 0):
        world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.82, 0.84, 0.86, 1.0)
    bg.inputs["Strength"].default_value = 0.6
    scene.world = world
    return coll


def add_camera(scene, name, loc, target, lens=50.0):
    cd = bpy.data.cameras.new(name)
    cd.lens = lens
    cd.clip_start = 1.0
    cd.clip_end = 10000.0
    cd.dof.use_dof = True
    cd.dof.aperture_fstop = 11.0
    cd.dof.focus_distance = (Vector(target) - Vector(loc)).length
    co = bpy.data.objects.new(name, cd)
    co.location = loc
    co.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    scene.collection.objects.link(co)
    return co


def setup_render(scene, samples=96):
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 8
    scene.cycles.transmission_bounces = 8
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    try:
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        try:
            scene.view_settings.view_transform = "Filmic"
        except Exception:
            pass


def export_devices(scene, out_dir):
    """Export each device as GLB (with colours) and STL (mm, for 3D printing)."""
    vl = bpy.context.view_layer
    os.makedirs(out_dir, exist_ok=True)
    for name in ("TS_Classic", "TS_Robotic"):
        vl.active_layer_collection = vl.layer_collection.children[name]
        try:
            bpy.ops.wm.stl_export(filepath=os.path.join(out_dir, f"{name}_200mm.stl"),
                                  collection=name, apply_modifiers=True,
                                  global_scale=1.0, use_scene_unit=False, ascii_format=False)
        except Exception as e:
            print("STL export failed:", e)
        try:
            bpy.ops.export_scene.gltf(filepath=os.path.join(out_dir, f"{name}.glb"),
                                      export_format="GLB", use_active_collection=True,
                                      use_active_collection_with_nested=True, export_apply=True)
        except Exception as e:
            print("GLB export failed:", e)
        print("exported", name)


def main(out_dir=None, do_render=False, samples=96, do_export=False):
    scene = bpy.data.scenes.get(SCENE_NAME)
    if scene is not None:
        bpy.data.scenes.remove(scene)
    scene = bpy.data.scenes.new(SCENE_NAME)
    if bpy.context.window is not None:
        bpy.context.window.scene = scene
    else:  # headless: make the new scene the context scene
        for other in list(bpy.data.scenes):
            if other != scene:
                bpy.data.scenes.remove(other)
    us = scene.unit_settings
    us.system = "METRIC"
    us.scale_length = 0.001
    us.length_unit = "MILLIMETERS"

    shared_materials()
    c1, r1 = build_device(scene, "TS_Classic", STYLES["TS_Classic"], -95.0)
    c2, r2 = build_device(scene, "TS_Robotic", STYLES["TS_Robotic"], 95.0)
    build_environment(scene)

    cam_all = add_camera(scene, "Cam_Both", (0.0, -720.0, 175.0), (0.0, 0.0, 98.0), lens=50.0)
    add_camera(scene, "Cam_Classic", (-95.0 - 150.0, -330.0, 165.0), (-95.0, 0.0, 102.0), lens=50.0)
    add_camera(scene, "Cam_Robotic", (95.0 + 150.0, -330.0, 165.0), (95.0, 0.0, 102.0), lens=50.0)
    add_camera(scene, "Cam_Head_Classic", (-95.0 - 70.0, -150.0, 205.0), (-95.0, 0.0, 168.0), lens=60.0)
    add_camera(scene, "Cam_Head_Robotic", (95.0 + 70.0, -150.0, 205.0), (95.0, 0.0, 168.0), lens=60.0)
    scene.camera = cam_all
    setup_render(scene, samples)

    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        blend = os.path.join(out_dir, "surveying_devices.blend")
        bpy.ops.wm.save_as_mainfile(filepath=blend, compress=True)
        print("saved", blend)
        if (do_export or do_render) and bpy.context.window is None:
            # headless: continue from the saved file (the glTF exporter is
            # unstable on freshly generated data in background mode)
            bpy.ops.wm.open_mainfile(filepath=blend)
            scene = bpy.data.scenes[SCENE_NAME]
            cam_all = bpy.data.objects["Cam_Both"]
        if do_export:
            export_devices(scene, os.path.join(out_dir, "export"))
        if do_render:
            shots = [("Cam_Both", 1600, 1000), ("Cam_Classic", 900, 1200), ("Cam_Robotic", 900, 1200),
                     ("Cam_Head_Classic", 1000, 1000), ("Cam_Head_Robotic", 1000, 1000)]
            for cam, w, h in shots:
                scene.camera = bpy.data.objects[cam]
                scene.render.resolution_x = w
                scene.render.resolution_y = h
                scene.render.filepath = os.path.join(out_dir, "renders", f"{cam}.png")
                bpy.ops.render.render(write_still=True, scene=scene.name)
                print("rendered", scene.render.filepath)
            scene.camera = cam_all
    return scene


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = None
    if "--out" in argv:
        out = argv[argv.index("--out") + 1]
    samples = 96
    if "--samples" in argv:
        samples = int(argv[argv.index("--samples") + 1])
    main(out, "--render" in argv, samples, "--export" in argv)
