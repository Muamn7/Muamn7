"""
Robotic total station on tripod - procedural Blender model (200 mm / 20 cm tall).
جهاز توتال ستيشن روبوتي على حامل ثلاثي - ارتفاع 20 سم - مطابق للصورة المرجعية

Inside Blender (4.2+ / 5.x): Scripting tab -> Open this file -> Run Script.
A new scene "Robotic_Total_Station" is created (your current scene is untouched).

Headless:
  blender -b -P build_robotic_total_station.py -- --out <folder> [--export] [--render]
"""

import bpy
import bmesh
import math
import os
import sys
from mathutils import Vector, Matrix

TARGET_HEIGHT = 200.0  # mm  (1 Blender unit = 1 mm)
SCENE_NAME = "Robotic_Total_Station"


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
    _set(b, "Roughness", 0.5)
    _set(b, "Coat Weight", 0.08)
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



# ---------------------------------------------------------------------------
# Tripod (slim yellow legs, orange fittings) - head top at z = 124 mm
# ---------------------------------------------------------------------------

HEAD_TOP = 124.0


def build_tripod(B, M):
    hinge_r, hinge_z = 12.0, 119.5
    foot_r = 52.0
    w, d = 7.2, 4.0            # upper leg section (tangential x radial)
    azimuths = [-90.0, 30.0, 150.0]

    # head hub
    B.add("Tripod_Head", bm_lathe([(0, 115.5), (9.0, 115.5), (10.5, 116.5), (11.2, 118.0), (11.2, 122.6),
                                   (10.4, HEAD_TOP), (0, HEAD_TOP)]), M["orange"], bevel=0.3)
    B.add("Tripod_Head_Plate", bm_lathe([(0, HEAD_TOP - 0.2), (10.0, HEAD_TOP - 0.2), (10.0, HEAD_TOP + 0.4),
                                         (0, HEAD_TOP + 0.4)]), M["black"], bevel=0.1)
    B.add("Tripod_Fix_Screw", bm_lathe([(0, 104.0), (1.6, 104.0), (1.6, 116.0), (0, 116.0)], segs=24),
          M["metal"], bevel=0.1)
    B.add("Tripod_Fix_Knob", bm_prism(knurl_pts(4.4, 3.9, 24), 105.0, 109.5), M["orange"], bevel=0.2)
    B.add("Tripod_Plumb_Hook", bm_torus(1.4, 0.35, axis="Y", cx=0, cy=102.8), M["metal"], bevel=0)

    radial = foot_r - hinge_r
    L = math.hypot(radial, hinge_z)
    tilt = math.atan2(radial, hinge_z)

    for idx, az in enumerate(azimuths):
        a = math.radians(az)
        rz = a - math.pi / 2
        tag = "ABC"[idx]

        # head lug: two orange cheeks + bolt
        lug = B.empty(f"Tripod_Lug_{tag}", rot=(0, 0, rz))
        gap = w / 2 + 0.4
        cheek = rrect(9.0, 8.0, 2.2, cx=hinge_r - 1.5, cy=hinge_z - 0.5)
        for s, side in ((-1, "L"), (1, "R")):
            x0, x1 = s * gap, s * (gap + 1.6)
            B.add(f"Tripod_Cheek_{tag}{side}", bm_prism(cheek, min(x0, x1), max(x0, x1), axis="X"),
                  M["orange"], bevel=0.25, parent=lug)
            B.add(f"Tripod_BoltHead_{tag}{side}",
                  bm_lathe([(0, s * (gap + 1.6)), (1.4, s * (gap + 1.6)), (1.2, s * (gap + 2.3)),
                            (0, s * (gap + 2.3))], axis="X", segs=20, cx=hinge_r, cy=hinge_z),
                  M["metal"], bevel=0, parent=lug)

        pivot = B.empty(f"Tripod_Leg_{tag}",
                        loc=(hinge_r * math.cos(a), hinge_r * math.sin(a), hinge_z),
                        rot=(tilt, 0, rz))
        # orange hinge cap
        B.add(f"Leg_{tag}_HingeCap", bm_prism(rrect(w + 0.2, d + 1.4, 1.6), -6.0, 3.6), M["orange"],
              bevel=0.3, parent=pivot)
        # upper section: two rails with a long slot, then solid
        rail_w = 2.1
        for s, side in ((-1, "L"), (1, "R")):
            B.add(f"Leg_{tag}_Rail{side}", bm_prism(rrect(rail_w, d, 0.7, cx=s * (w / 2 - rail_w / 2)),
                                                     -48.0, -4.0), M["yellow"], bevel=0.25, parent=pivot)
        B.add(f"Leg_{tag}_UpperSolid", bm_prism(rrect(w, d, 1.2), -70.0, -46.0), M["yellow"],
              bevel=0.3, parent=pivot)
        B.add(f"Leg_{tag}_SlotEnd", bm_prism(rrect(w - 2 * rail_w + 0.4, d * 0.6, 0.3), -47.0, -45.4),
              M["yellow"], bevel=0.1, parent=pivot)
        # orange clamp + screw
        B.add(f"Leg_{tag}_Clamp", bm_prism(rrect(w + 1.8, d + 1.8, 1.2), -73.0, -65.5), M["orange"],
              bevel=0.3, parent=pivot)
        B.add(f"Leg_{tag}_ClampScrew", bm_prism(knurl_pts(1.8, 1.55, 14, cx=0, cy=-69.2),
                                                d / 2 + 0.9, d / 2 + 3.0, axis="Y"),
              M["orange"], bevel=0.1, parent=pivot)
        # lower sliding section
        lw, ld = w - 1.6, d - 0.8
        B.add(f"Leg_{tag}_Lower", bm_prism(rrect(lw, ld, 0.9), -(L - 9.0), -67.0), M["yellow"],
              bevel=0.25, parent=pivot)
        # orange foot: shoe, side pedal, spike
        shoe_bot = -(L - 4.0)
        B.add(f"Leg_{tag}_Shoe", bm_prism(rrect(w - 0.2, d + 0.6, 1.2), shoe_bot, shoe_bot + 9.0), M["orange"],
              bevel=0.3, parent=pivot)
        B.add(f"Leg_{tag}_Pedal", bm_prism(rpoly([(-2.6, d / 2), (2.6, d / 2), (2.6, d / 2 + 4.6),
                                                  (-2.6, d / 2 + 4.6)], 0.8), shoe_bot + 1.0, shoe_bot + 2.6),
              M["orange"], bevel=0.25, parent=pivot)
        B.add(f"Leg_{tag}_Spike", bm_lathe([(0, -L), (0.8, -L + 1.0), (2.4, shoe_bot), (0, shoe_bot)], segs=24),
              M["orange"], bevel=0.1, parent=pivot)


# ---------------------------------------------------------------------------
# Robotic total station (grey body, yellow C-handle, three side knobs)
# ---------------------------------------------------------------------------

def build_tribrach(B, M, z0):
    corners = [(14.5 * math.cos(math.radians(a)), 14.5 * math.sin(math.radians(a))) for a in (90, 210, 330)]
    B.add("Tribrach_Base", bm_prism(rpoly(corners, 4.5, 8), z0, z0 + 2.6), M["black"], bevel=0.3)
    for i, a in enumerate((90.0, 210.0, 330.0)):
        cx, cy = 10.8 * math.cos(math.radians(a)), 10.8 * math.sin(math.radians(a))
        B.add(f"Tribrach_LevelScrew_{i}", bm_prism(knurl_pts(3.0, 2.65, 22, cx, cy), z0 + 2.6, z0 + 6.2),
              M["black"], bevel=0.12)
        B.add(f"Tribrach_LevelThread_{i}", bm_lathe([(0, z0 + 6.2), (1.0, z0 + 6.2), (1.0, z0 + 7.6),
                                                     (0, z0 + 7.6)], segs=16, cx=cx, cy=cy), M["metal"], bevel=0)
    B.add("Tribrach_Plate", bm_lathe([(0, z0 + 6.6), (12.6, z0 + 6.6), (13.2, z0 + 7.2), (13.2, z0 + 8.6),
                                      (12.4, z0 + 9.2), (0, z0 + 9.2)]), M["black"], bevel=0.15)
    a = math.radians(-35.0)
    bx, by = 9.5 * math.cos(a), 9.5 * math.sin(a)
    B.add("Tribrach_Bubble", bm_lathe([(0, z0 + 9.2), (1.6, z0 + 9.2), (1.6, z0 + 9.8), (0, z0 + 10.1)],
                                      segs=24, cx=bx, cy=by), M["bubble"], bevel=0)
    B.add("Tribrach_Lock", bm_prism(rpoly([(-1.5, 0), (1.5, 0), (1.2, 6.0), (-1.2, 6.0)], 0.6), z0 + 1.0, z0 + 2.2),
          M["black"], bevel=0.15, rot=(0, 0, math.radians(60)))
    return z0 + 9.2


def build_station(B, M):
    z = build_tribrach(B, M, HEAD_TOP + 0.4)                     # -> ~133.6
    # rotating base (dark)
    B.add("Base_Rotation", bm_lathe([(0, z), (11.5, z), (12.6, z + 1.2), (12.6, z + 4.6), (13.6, z + 5.6),
                                     (13.6, z + 6.4), (0, z + 6.4)]), M["dark"], bevel=0.2)
    zb = z + 6.4                                                  # body bottom ~140
    zt = zb + 40.0                                                # body top ~180
    W, D = 26.5, 25.0
    xh, yh = W / 2, D / 2

    # main body
    B.add("Body", bm_prism(rrect(W, D, 3.2), zb, zt), M["grey"], bevel=0.9)
    B.add("Body_TopCap", bm_prism(rrect(W - 2.0, D - 2.0, 2.6), zt - 0.2, zt + 1.0), M["grey_dark"], bevel=0.4)

    # ---- front face (-Y): light frame, darker telescope panel, lens, chin
    yf = -yh
    B.add("Front_Panel", bm_prism(rrect(W - 8.0, 27.0, 1.8, cx=0, cy=zb + 25.5), yf + 0.3, yf - 0.4, axis="Y"),
          M["grey_dark"], bevel=0.25)
    for s, side in ((-1, "L"), (1, "R")):
        B.add(f"Front_Frame_{side}", bm_prism(rrect(3.6, 32.0, 1.2, cx=s * (xh - 2.1), cy=zb + 22.5),
                                              yf + 0.3, yf - 0.9, axis="Y"), M["grey_light"], bevel=0.3)
    B.add("Front_Frame_Top", bm_prism(rrect(W - 2.0, 3.6, 1.4, cx=0, cy=zt - 2.2), yf + 0.3, yf - 0.9, axis="Y"),
          M["grey_light"], bevel=0.3)
    # telescope objective
    lx, lz = -2.5, zb + 30.5
    B.add("Lens_Barrel", bm_lathe([(0, yf - 0.4), (4.6, yf - 0.4), (4.6, yf - 2.2), (4.0, yf - 2.8),
                                   (3.3, yf - 2.8), (3.3, yf - 2.0), (0, yf - 2.0)], axis="Y", segs=48,
                                  cx=lx, cy=lz), M["black"], bevel=0.12)
    B.add("Lens_Coating", bm_lathe([(0, yf - 1.9), (3.3, yf - 1.9), (3.3, yf - 1.7), (0, yf - 1.7)], axis="Y",
                                   segs=48, cx=lx, cy=lz), M["coating"], bevel=0)
    B.add("Lens_Glass", bm_lathe([(0, yf - 2.5), (2.0, yf - 2.4), (3.3, yf - 2.1), (3.3, yf - 1.9), (0, yf - 1.9)],
                                 axis="Y", segs=48, cx=lx, cy=lz), M["glass"], bevel=0)
    B.add("Tracker_Window", bm_prism(rrect(3.6, 2.0, 0.7, cx=4.6, cy=lz + 2.0), yf - 0.4, yf - 1.0, axis="Y"),
          M["black"], bevel=0.1)
    B.add("Laser_Dot", bm_lathe([(0, yf - 0.4), (1.1, yf - 0.4), (1.1, yf - 1.0), (0, yf - 1.0)], axis="Y",
                                segs=24, cx=4.6, cy=lz - 3.2), M["black"], bevel=0)
    # sloped chin at the bottom of the front
    chin = rpoly([(yf + 0.5, zb + 0.4), (yf + 0.5, zb + 12.0), (yf - 1.6, zb + 12.0), (yf - 4.4, zb + 1.2),
                  (yf - 3.6, zb + 0.4)], 0.7)
    B.add("Front_Chin", bm_prism(chin, -xh + 1.6, xh - 1.6, axis="X"), M["grey_light"], bevel=0.35)

    # ---- right side (+X): dark recessed panel with three black knobs
    xs = xh
    B.add("Side_Panel_R", bm_prism(rrect(22.5, 35.0, 2.2, cx=-1.0, cy=zb + 20.0), xs - 0.3, xs + 0.5, axis="X"),
          M["grey_dark"], bevel=0.25)
    for i, (ky, kz, kr) in enumerate(((-2.0, zb + 31.5, 2.9), (-1.5, zb + 21.5, 3.7), (-1.5, zb + 10.5, 3.7))):
        B.add(f"Side_Knob_{i}", bm_lathe([(0, xs + 0.4), (kr, xs + 0.4), (kr, xs + 2.6), (kr - 0.5, xs + 3.4),
                                          (0, xs + 3.7)], axis="X", segs=48, cx=ky, cy=kz),
              M["black"], bevel=0.15)
        B.add(f"Side_Knob_Ring_{i}", bm_torus(kr + 0.2, 0.25, axis="X", cx=ky, cy=kz, d=xs + 0.55), M["black"],
              bevel=0)

    # ---- left side (-X): servo cover + function key
    B.add("Side_Panel_L", bm_prism(rrect(18.0, 35.0, 2.2, cx=-1.5, cy=zb + 20.0), -xs - 0.5, -xs + 0.3, axis="X"),
          M["grey_dark"], bevel=0.25)
    B.add("Servo_Cover_L", bm_lathe([(0, -xs - 0.4), (6.0, -xs - 0.4), (6.0, -xs - 1.4), (5.2, -xs - 2.0),
                                     (0, -xs - 2.2)], axis="X", segs=64, cx=-2.0, cy=zb + 27.0), M["black"],
          bevel=0.15)
    B.add("Side_Knob_L", bm_lathe([(0, -xs - 0.4), (3.2, -xs - 0.4), (3.2, -xs - 2.6), (2.7, -xs - 3.3),
                                   (0, -xs - 3.6)], axis="X", segs=48, cx=-1.5, cy=zb + 11.0), M["black"],
          bevel=0.15)

    # ---- back (+Y): control panel with display + keypad
    yb = yh
    B.add("Back_Bezel", bm_prism(rrect(19.0, 13.0, 1.6, cx=0.0, cy=zb + 12.0), yb - 0.3, yb + 0.8, axis="Y"),
          M["black"], bevel=0.2)
    B.add("Back_LCD", bm_prism(rrect(9.0, 7.5, 0.5, cx=-4.0, cy=zb + 12.6), yb + 0.8, yb + 1.0, axis="Y"),
          M["lcd"], bevel=0)
    for r in range(3):
        for c in range(3):
            B.add(f"Back_Key_{r}{c}", bm_prism(rrect(1.7, 1.3, 0.4, cx=2.6 + c * 2.2, cy=zb + 15.0 - r * 2.3),
                                               yb + 0.8, yb + 1.35, axis="Y"),
                  M["key_red"] if (r, c) == (0, 2) else M["key"], bevel=0.12)
    B.add("Back_Eyepiece", bm_lathe([(0, yb - 0.2), (3.0, yb - 0.2), (3.0, yb + 2.2), (3.5, yb + 2.6),
                                     (3.5, yb + 4.0), (2.0, yb + 4.0), (0, yb + 3.4)], axis="Y", segs=40,
                                    cx=-2.5, cy=zb + 30.5), M["black"], bevel=0.12)

    # ---- yellow handle: cross bar over the top + C-frame around the knob side
    top0, top1 = zt + 10.0, zt + 14.5
    by0, by1 = -6.5, -0.5                    # cross bar depth (Y)
    fx0, fx1 = xs - 0.2, xs + 4.0            # side frame slab (X)
    B.add("Handle_CrossBar", bm_prism(rpoly([(-xh - 1.8, top0 + 0.4), (fx1 - 0.5, top0), (fx1, top1 - 0.6),
                                             (fx1 - 1.2, top1), (-xh - 1.8, top1)], 1.4), by0, by1, axis="Y"),
          M["yellow_h"], bevel=0.5)
    frame = rpoly([(by0, top1), (yh - 3.0, top1), (yh + 4.0, top1 - 7.0), (yh + 4.0, zb + 1.0),
                   (yh + 1.5, zb - 1.8), (-yh + 0.5, zb - 1.8), (-yh + 0.5, zb + 1.0), (-yh + 2.0, zb + 2.6),
                   (yh - 1.5, zb + 2.6), (yh - 1.5, top0 - 4.0), (yh - 4.5, top0), (by0, top0)], 2.2, 10)
    B.add("Handle_SideFrame", bm_prism(frame, fx0, fx1, axis="X"), M["yellow_h"], bevel=0.5)
    # grey stem joining the body top and the cross bar
    B.add("Handle_Stem", bm_prism(rpoly([(-0.5, zt - 0.5), (7.0, zt - 0.5), (5.0, top0 + 0.5), (1.0, top0 + 0.5)],
                                        1.0), by0 + 1.0, by1 - 1.0, axis="Y"), M["grey_light"], bevel=0.3)
    # black antenna housing on the left end of the bar + post down to the body
    B.add("Antenna_Block", bm_prism(rrect(10.0, top1 - top0 + 1.4, 1.2, cx=-xh + 4.2, cy=(top0 + top1) / 2),
                                    by0 - 0.6, by1 + 0.6, axis="Y"), M["black"], bevel=0.3)
    B.add("Antenna_Post", bm_prism(rrect(4.0, 4.0, 1.0, cx=-xh + 3.2, cy=(by0 + by1) / 2), zt - 0.5, top0 + 0.2),
          M["black"], bevel=0.25)
    ant = B.empty("Antenna_Pivot", loc=(-xh + 3.2, (by0 + by1) / 2, top1 + 0.5),
                  rot=(math.radians(-3), math.radians(-6), 0))
    B.add("Antenna_Base", bm_lathe([(0, 0), (1.6, 0), (1.6, 1.4), (1.0, 2.4), (0, 2.4)], segs=24),
          M["black"], bevel=0.1, parent=ant)
    B.add("Antenna_Rod", bm_lathe([(0, 2.0), (0.65, 2.0), (0.5, 13.0), (0.75, 13.4), (0.75, 14.6), (0, 15.0)],
                                  segs=20), M["black"], bevel=0, parent=ant)


# ---------------------------------------------------------------------------
# Scene
# ---------------------------------------------------------------------------

def materials():
    return {
        "grey": make_mat("Body_Grey", "8c9196", rough=0.45, coat=0.15),
        "grey_light": make_mat("Body_Grey_Light", "aab0b5", rough=0.45, coat=0.15),
        "grey_dark": make_mat("Body_Grey_Dark", "5f6469", rough=0.5),
        "dark": make_mat("Base_Dark", "3a3c3f", rough=0.45),
        "black": make_mat("Black_Plastic", "1b1c1e", rough=0.45),
        "yellow_h": make_mat("Handle_Yellow", "f0be14", rough=0.38, coat=0.25),
        "yellow": make_mat("Tripod_Yellow", "f4e12c", rough=0.4, coat=0.2),
        "orange": make_mat("Tripod_Orange", "f2701a", rough=0.42, coat=0.2),
        "metal": make_mat("Metal_Steel", "c9ccd0", rough=0.22, metal=1.0),
        "key": make_mat("Key_Grey", "4a4d52", rough=0.55),
        "key_red": make_mat("Key_Red", "c62a1e", rough=0.45),
        "lcd": make_mat("LCD_Screen", "6e7f6a", rough=0.12, emission="9fb59a", emit_strength=0.35),
        "glass": make_mat("Lens_Glass", "e8f0ff", rough=0.0, transmission=1.0, ior=1.52),
        "coating": make_mat("Lens_Coating", "3a2a6e", rough=0.06, metal=0.85),
        "bubble": make_mat("Bubble_Vial", "9fe07a", rough=0.05, emission="7fd35b", emit_strength=0.6),
    }


def build_device(scene, name="Robotic_Total_Station"):
    coll = bpy.data.collections.new(name)
    scene.collection.children.link(coll)
    root = bpy.data.objects.new(f"{name}_ROOT", None)
    root.empty_display_type = "ARROWS"
    root.empty_display_size = 30
    coll.objects.link(root)
    B = Builder(coll, root)
    M = materials()
    build_tripod(B, M)
    build_station(B, M)

    scene.view_layers[0].update()
    zmin, zmax = 1e9, -1e9
    for o in coll.objects:
        if o.type != "MESH":
            continue
        mw = o.matrix_world
        for v in o.data.vertices:
            zz = (mw @ v.co).z
            zmin, zmax = min(zmin, zz), max(zmax, zz)
    s = TARGET_HEIGHT / (zmax - zmin)
    root.scale = (s, s, s)
    root.location = (0.0, 0.0, -zmin * s)
    root["height_mm"] = TARGET_HEIGHT
    scene.view_layers[0].update()
    print(f"[{name}] parts={B.count}  raw height={zmax - zmin:.2f} mm  scale={s:.4f}")
    return coll


def orbit_cam(scene, name, az_deg, dist, height, target, lens):
    a = math.radians(az_deg)
    loc = (target[0] + dist * math.sin(a), target[1] - dist * math.cos(a), height)
    return add_camera(scene, name, loc, target, lens)


def export_device(out_dir, name="Robotic_Total_Station"):
    vl = bpy.context.view_layer
    os.makedirs(out_dir, exist_ok=True)
    vl.active_layer_collection = vl.layer_collection.children[name]
    bpy.ops.wm.stl_export(filepath=os.path.join(out_dir, f"{name}_200mm.stl"), collection=name,
                          apply_modifiers=True, global_scale=1.0, use_scene_unit=False, ascii_format=False)
    bpy.ops.export_scene.gltf(filepath=os.path.join(out_dir, f"{name}.glb"), export_format="GLB",
                              use_active_collection=True, use_active_collection_with_nested=True,
                              export_apply=True)
    print("exported", name)


SHOTS = [("Cam_Photo", 900, 1500), ("Cam_Front", 900, 1400), ("Cam_Close", 1000, 1000),
         ("Cam_Back", 900, 1400)]


def main(out_dir=None, do_render=False, samples=128, do_export=False):
    scene = bpy.data.scenes.get(SCENE_NAME)
    if scene is not None:
        bpy.data.scenes.remove(scene)
    scene = bpy.data.scenes.new(SCENE_NAME)
    if bpy.context.window is not None:
        bpy.context.window.scene = scene
    else:
        for other in list(bpy.data.scenes):
            if other != scene:
                bpy.data.scenes.remove(other)
    us = scene.unit_settings
    us.system = "METRIC"
    us.scale_length = 0.001
    us.length_unit = "MILLIMETERS"

    build_device(scene)
    build_environment(scene)
    cam = orbit_cam(scene, "Cam_Photo", 40.0, 270.0, 140.0, (0, 0, 102.0), 32.0)
    orbit_cam(scene, "Cam_Front", -25.0, 340.0, 135.0, (0, 0, 100.0), 40.0)
    orbit_cam(scene, "Cam_Close", 40.0, 150.0, 190.0, (0, 0, 160.0), 50.0)
    orbit_cam(scene, "Cam_Back", 140.0, 340.0, 150.0, (0, 0, 104.0), 40.0)
    scene.camera = cam
    setup_render(scene, samples)

    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        blend = os.path.join(out_dir, "robotic_total_station.blend")
        bpy.ops.wm.save_as_mainfile(filepath=blend, compress=True)
        print("saved", blend)
        if (do_export or do_render) and bpy.context.window is None:
            bpy.ops.wm.open_mainfile(filepath=blend)
            scene = bpy.data.scenes[SCENE_NAME]
        if do_export:
            export_device(os.path.join(out_dir, "export"))
        if do_render:
            for c, w, h in SHOTS:
                scene.camera = bpy.data.objects[c]
                scene.render.resolution_x, scene.render.resolution_y = w, h
                scene.render.filepath = os.path.join(out_dir, "renders", f"{c}.png")
                bpy.ops.render.render(write_still=True, scene=scene.name)
                print("rendered", scene.render.filepath)
            scene.camera = bpy.data.objects["Cam_Photo"]
    return scene


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = argv[argv.index("--out") + 1] if "--out" in argv else None
    smp = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 128
    main(out, "--render" in argv, smp, "--export" in argv)
