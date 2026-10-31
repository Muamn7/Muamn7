"""
Justice Scale (20 cm) + Judge's Gavel (15 cm) - procedural Blender model
=========================================================================
ميزان العدالة (ارتفاع 20 سم) + مطرقة القاضي (طول 15 سم)

Run inside Blender (4.2 LTS or newer, tested on 5.2):
    Scripting tab -> Open this file -> Run Script
or from a terminal:
    blender --background --python justice_scale_gavel.py

WARNING: the script clears the current scene first. Run it in a new file.

Everything is built at real-world size (metric units, display in cm):
    * Scale  : base 7.9 cm wide, beam 16.4 cm wide, total height exactly 20 cm
    * Gavel  : 15 cm overall (handle tip -> far side of head), head 7 cm long
All wood / gold / brass materials are procedural (no image textures needed).
"""

import math
import bpy
import bmesh
from mathutils import Vector, Matrix

CM = 0.01  # 1 cm in Blender metres

# --------------------------------------------------------------------------
# helpers: scene
# --------------------------------------------------------------------------


def clear_scene():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for coll in list(bpy.data.collections):
        bpy.data.collections.remove(coll)
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.lights,
                  bpy.data.cameras, bpy.data.curves):
        for item in list(block):
            if item.users == 0:
                block.remove(item)


def new_collection(name):
    coll = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(coll)
    return coll


def make_object(name, verts, faces, coll, mats=(), mat_idx=None, smooth=True,
                sharp_angle=35.0):
    """verts in cm -> mesh in metres."""
    me = bpy.data.meshes.new(name)
    me.from_pydata([(x * CM, y * CM, z * CM) for x, y, z in verts], [], faces)
    me.validate()
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-7)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    if mat_idx is not None:
        me.polygons.foreach_set("material_index", mat_idx)
    if smooth:
        me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
        if hasattr(me, "set_sharp_from_angle"):
            me.set_sharp_from_angle(angle=math.radians(sharp_angle))
    me.update()
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    return ob


def parent_to(child, parent):
    child.parent = parent
    child.matrix_parent_inverse = parent.matrix_world.inverted()


# --------------------------------------------------------------------------
# helpers: lathe profile (turned wood parts)
# --------------------------------------------------------------------------


class Profile:
    """2-D (r, z) outline in cm, with automatic rounded corners."""

    def __init__(self, r, z):
        self.p = [[r, z, 0.0]]

    @property
    def last(self):
        return self.p[-1][0], self.p[-1][1]

    def line(self, r, z, f=0.02):
        """straight segment to (r, z); f = fillet radius at that corner."""
        self.p.append([r, z, f])
        return self

    def bez(self, c1, c2, end, n=24, f=0.0):
        """cubic bezier from current point."""
        p0 = self.last
        for i in range(1, n + 1):
            t = i / n
            a = (1 - t) ** 3
            b = 3 * (1 - t) ** 2 * t
            c = 3 * (1 - t) * t * t
            d = t ** 3
            r = a * p0[0] + b * c1[0] + c * c2[0] + d * end[0]
            z = a * p0[1] + b * c1[1] + c * c2[1] + d * end[1]
            self.p.append([r, z, f if i == n else 0.0])
        return self

    def arc(self, center, radius, a0, a1, n=16, f=0.0):
        """circular arc, angles in degrees (0 = +r, 90 = +z)."""
        for i in range(1, n + 1):
            a = math.radians(a0 + (a1 - a0) * i / n)
            self.p.append([center[0] + radius * math.cos(a),
                           center[1] + radius * math.sin(a),
                           f if i == n else 0.0])
        return self

    def mirrored(self):
        """mirror the profile about z=0 (for symmetric parts)."""
        pts = [list(q) for q in self.p]
        mirror = [[r, -z, f] for r, z, f in reversed(pts[:-1])]
        out = Profile(0, 0)
        out.p = pts + mirror
        return out

    def points(self, max_seg=0.2):
        pts = self.p
        # 1) fillets
        out = []
        for i, (r, z, f) in enumerate(pts):
            if f <= 0 or i == 0 or i == len(pts) - 1:
                out.append((r, z))
                continue
            P = Vector((r, z))
            A = Vector(pts[i - 1][:2])
            B = Vector(pts[i + 1][:2])
            u, v = A - P, B - P
            la, lb = u.length, v.length
            if la < 1e-6 or lb < 1e-6:
                out.append((r, z))
                continue
            u.normalize()
            v.normalize()
            ang = math.acos(max(-1.0, min(1.0, u.dot(v))))
            if ang > math.radians(170):
                out.append((r, z))
                continue
            d = min(f / math.tan(ang / 2), 0.45 * la, 0.45 * lb)
            p0, p2 = P + u * d, P + v * d
            n = 6
            for k in range(n + 1):
                t = k / n
                q = (1 - t) ** 2 * p0 + 2 * (1 - t) * t * P + t * t * p2
                out.append((q.x, q.y))
        # 2) split long straight segments, drop duplicates
        res = [out[0]]
        for q in out[1:]:
            a = Vector(res[-1])
            b = Vector(q)
            L = (b - a).length
            if L < 1e-5:
                continue
            k = max(1, int(math.ceil(L / max_seg)))
            for j in range(1, k + 1):
                c = a.lerp(b, j / k)
                res.append((c.x, c.y))
        return res


def lathe(name, prof, coll, mats, zones=(), segs=96, max_seg=0.2):
    """Revolve profile around Z. zones = [(zmin, zmax, mat_index), ...]."""
    pts = prof.points(max_seg)
    verts, faces, rings = [], [], []
    for r, z in pts:
        if abs(r) < 1e-5:
            rings.append([len(verts)])
            verts.append((0.0, 0.0, z))
        else:
            ring = []
            for k in range(segs):
                a = 2 * math.pi * k / segs
                ring.append(len(verts))
                verts.append((r * math.cos(a), r * math.sin(a), z))
            rings.append(ring)
    for i in range(len(rings) - 1):
        A, B = rings[i], rings[i + 1]
        if len(A) == 1 and len(B) == 1:
            continue
        for k in range(segs):
            k2 = (k + 1) % segs
            if len(A) == 1:
                faces.append((A[0], B[k], B[k2]))
            elif len(B) == 1:
                faces.append((A[k], A[k2], B[0]))
            else:
                faces.append((A[k], A[k2], B[k2], B[k]))
    idx = []
    for fc in faces:
        zc = sum(verts[v][2] for v in fc) / len(fc)
        m = 0
        for z0, z1, mi in zones:
            if z0 <= zc <= z1:
                m = mi
        idx.append(m)
    return make_object(name, verts, faces, coll, mats, idx)


# --------------------------------------------------------------------------
# helpers: tubes (gold wire, chain links, hooks)
# --------------------------------------------------------------------------


def tube_geometry(path, radius, sides=10, closed=False, verts=None, faces=None):
    """Sweep a circle along a polyline (cm). Appends into verts/faces."""
    verts = [] if verts is None else verts
    faces = [] if faces is None else faces
    P = [Vector(p) for p in path]
    n = len(P)
    tangents = []
    for i in range(n):
        if closed:
            t = P[(i + 1) % n] - P[i - 1]
        else:
            t = P[min(i + 1, n - 1)] - P[max(i - 1, 0)]
        tangents.append(t.normalized())
    # parallel-transport frame
    ref = Vector((0, 0, 1)) if abs(tangents[0].z) < 0.9 else Vector((1, 0, 0))
    nrm = tangents[0].cross(ref).normalized()
    base = len(verts)
    for i in range(n):
        t = tangents[i]
        nrm = (nrm - t * nrm.dot(t)).normalized()
        bin_ = t.cross(nrm)
        for s in range(sides):
            a = 2 * math.pi * s / sides
            v = P[i] + (nrm * math.cos(a) + bin_ * math.sin(a)) * radius
            verts.append(tuple(v))
    rows = n if closed else n - 1
    for i in range(rows):
        i2 = (i + 1) % n
        for s in range(sides):
            s2 = (s + 1) % sides
            faces.append((base + i * sides + s, base + i * sides + s2,
                          base + i2 * sides + s2, base + i2 * sides + s))
    if not closed:  # caps
        c0 = len(verts)
        verts.append(tuple(P[0]))
        c1 = len(verts)
        verts.append(tuple(P[-1]))
        last = base + (n - 1) * sides
        for s in range(sides):
            s2 = (s + 1) % sides
            faces.append((c0, base + s2, base + s))
            faces.append((c1, last + s, last + s2))
    return verts, faces


def ring_path(center, radius, axis_u, axis_v, n=40):
    c, u, v = Vector(center), Vector(axis_u), Vector(axis_v)
    return [c + (u * math.cos(2 * math.pi * i / n) + v * math.sin(2 * math.pi * i / n)) * radius
            for i in range(n)]


def chain_link_path(a, rc, n=40):
    """stadium centre-line in local XY: long axis = X."""
    pts = []
    m = n // 2
    for i in range(m):  # right semicircle
        t = -math.pi / 2 + math.pi * i / (m - 1)
        pts.append(Vector((a + rc * math.cos(t), rc * math.sin(t), 0)))
    for i in range(m):  # left semicircle
        t = math.pi / 2 + math.pi * i / (m - 1)
        pts.append(Vector((-a + rc * math.cos(t), rc * math.sin(t), 0)))
    return pts


def build_chain(start, end, verts, faces, a=0.07, rc=0.085, wire=0.028, twist=0.0):
    """Interlocking curb chain from start to end (cm)."""
    S, E = Vector(start), Vector(end)
    d = (E - S)
    length = d.length
    d.normalize()
    pitch_nom = 2 * (a + rc) - 2.2 * wire
    n = max(2, int(round((length - 2 * wire) / pitch_nom)))
    pitch = (length - 2 * wire) / n
    ref = Vector((0, 0, 1)) if abs(d.z) < 0.95 else Vector((1, 0, 0))
    e1 = d.cross(ref).normalized()
    e1 = Matrix.Rotation(twist, 3, d) @ e1
    e2 = d.cross(e1).normalized()
    template = chain_link_path(a, rc)
    for i in range(n):
        c = S + d * (wire + pitch * (i + 0.5))
        side = e1 if i % 2 == 0 else e2
        other = d.cross(side)
        path = [c + d * p.x + side * p.y for p in template]
        tube_geometry(path, wire, sides=8, closed=True, verts=verts, faces=faces)
    return verts, faces


# --------------------------------------------------------------------------
# materials
# --------------------------------------------------------------------------


def _bsdf_set(bsdf, **kw):
    names = {
        "base": "Base Color", "metal": "Metallic", "rough": "Roughness",
        "coat": "Coat Weight", "coat_rough": "Coat Roughness",
        "spec": "Specular IOR Level", "aniso": "Anisotropic",
        "sheen": "Sheen Weight",
    }
    for k, v in kw.items():
        sock = bsdf.inputs.get(names[k])
        if sock is not None:
            sock.default_value = v


def _new_material(name):
    mat = bpy.data.materials.new(name)
    try:
        mat.use_nodes = True
    except Exception:
        pass
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    return mat, nt, bsdf


def _mix_color(nt, fac, a, b, blend="MIX"):
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = blend
    ins = {s.identifier: s for s in mix.inputs}
    outs = {s.identifier: s for s in mix.outputs}
    nt.links.new(fac, ins["Factor_Float"])
    nt.links.new(a, ins["A_Color"])
    if isinstance(b, (tuple, list)):
        ins["B_Color"].default_value = b
    else:
        nt.links.new(b, ins["B_Color"])
    return outs["Result_Color"]


def make_wood(name, grain_axis, dark, mid, light, ring_scale=2.2, rough=0.36,
              coat=0.55, offset=(7.0, 11.0, 3.0)):
    """Procedural lacquered hardwood. grain_axis = 'X' | 'Y' | 'Z' (object space)."""
    mat, nt, bsdf = _new_material(name)
    N, L = nt.nodes, nt.links
    tc = N.new("ShaderNodeTexCoord")
    mp = N.new("ShaderNodeMapping")
    stretch = {"X": (0.12, 1, 1), "Y": (1, 0.12, 1), "Z": (1, 1, 0.12)}[grain_axis]
    mp.inputs["Scale"].default_value = [100 * s for s in stretch]  # metres -> cm
    mp.inputs["Location"].default_value = offset  # move ring centre off the part
    L.new(tc.outputs["Object"], mp.inputs["Vector"])

    # distortion noise
    nz = N.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 0.6
    nz.inputs["Detail"].default_value = 6.0
    L.new(mp.outputs["Vector"], nz.inputs["Vector"])
    vmix = N.new("ShaderNodeVectorMath")
    vmix.operation = "MULTIPLY_ADD"
    L.new(nz.outputs["Color"], vmix.inputs[0])
    vmix.inputs[1].default_value = (0.6, 0.6, 0.6)
    L.new(mp.outputs["Vector"], vmix.inputs[2])

    # growth rings -> long grain lines along the chosen axis
    wave = N.new("ShaderNodeTexWave")
    wave.wave_type = "RINGS"
    wave.rings_direction = grain_axis
    wave.inputs["Scale"].default_value = ring_scale
    wave.inputs["Distortion"].default_value = 5.0
    wave.inputs["Detail"].default_value = 3.0
    wave.inputs["Detail Scale"].default_value = 1.5
    L.new(vmix.outputs["Vector"], wave.inputs["Vector"])

    ramp = N.new("ShaderNodeValToRGB")
    cr = ramp.color_ramp
    cr.elements[0].position = 0.0
    cr.elements[0].color = (*dark, 1)
    cr.elements[1].position = 0.3
    cr.elements[1].color = (*mid, 1)
    e = cr.elements.new(1.0)
    e.color = (*light, 1)
    L.new(wave.outputs["Fac"], ramp.inputs["Fac"])

    # large patches of colour variation (figure)
    patch = N.new("ShaderNodeTexNoise")
    patch.inputs["Scale"].default_value = 0.25
    patch.inputs["Detail"].default_value = 3.0
    L.new(mp.outputs["Vector"], patch.inputs["Vector"])
    patch_ramp = N.new("ShaderNodeMapRange")
    patch_ramp.inputs["From Min"].default_value = 0.35
    patch_ramp.inputs["From Max"].default_value = 0.65
    patch_ramp.inputs["To Min"].default_value = 0.0
    patch_ramp.inputs["To Max"].default_value = 0.55
    L.new(patch.outputs["Fac"], patch_ramp.inputs["Value"])
    col = _mix_color(nt, patch_ramp.outputs["Result"], ramp.outputs["Color"],
                     tuple(c * 0.55 for c in dark) + (1,), "MULTIPLY")
    L.new(col, bsdf.inputs["Base Color"])

    # pores / grain bump
    bump = N.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.08
    bump.inputs["Distance"].default_value = 0.0004
    L.new(wave.outputs["Fac"], bump.inputs["Height"])
    L.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    _bsdf_set(bsdf, rough=rough, coat=coat, coat_rough=0.07, spec=0.5)
    return mat


def make_metal(name, color, rough=0.2, aniso=0.0, scratch=True):
    mat, nt, bsdf = _new_material(name)
    _bsdf_set(bsdf, base=(*color, 1), metal=1.0, rough=rough, aniso=aniso)
    if scratch:
        N, L = nt.nodes, nt.links
        nz = N.new("ShaderNodeTexNoise")
        nz.inputs["Scale"].default_value = 900.0
        nz.inputs["Detail"].default_value = 4.0
        mr = N.new("ShaderNodeMapRange")
        mr.inputs["To Min"].default_value = rough * 0.6
        mr.inputs["To Max"].default_value = rough * 1.5
        L.new(nz.outputs["Fac"], mr.inputs["Value"])
        L.new(mr.outputs["Result"], bsdf.inputs["Roughness"])
    return mat


def make_simple(name, color, rough=0.5, metal=0.0, sheen=0.0, aniso=0.0):
    mat, nt, bsdf = _new_material(name)
    _bsdf_set(bsdf, base=(*color, 1), rough=rough, metal=metal, sheen=sheen, aniso=aniso)
    return mat


# --------------------------------------------------------------------------
# 1. JUSTICE SCALE (height 20 cm)
# --------------------------------------------------------------------------

BEAM_Z = 15.0      # height of beam centre
BEAM_L = 8.2       # half span of the beam
HOOK_S = 0.84      # where the hooks hang (fraction of half span)
PAN_BOTTOM = 4.7   # pan underside height


def beam_shape(s):
    """s = |x| / L  -> (centre-line z, height, depth) in cm."""
    s = min(max(s, 0.0), 1.0)
    zc = 0.42 * math.sin(math.pi * s) - 1.0 * s ** 4
    h = 1.7 - 2.6 * s + 2.2 * s * s
    d = 1.12 - 0.32 * s
    return zc, h, d


def beam_geometry(inflate=0.0):
    """Wing-shaped carved beam: swept rounded-rectangle (super-ellipse).
    inflate (cm) grows the section on every side (used for print clearances)."""
    M = 40          # section resolution
    expo = 2.6      # super-ellipse exponent (2 = ellipse, higher = boxier)
    r_end = 0.55
    xs = []
    n_mid = 220
    x_cap = BEAM_L - r_end
    caps = 14
    # left cap (from tip toward centre)
    for i in range(caps, 0, -1):
        b = math.pi / 2 * i / caps
        xs.append((-(x_cap + r_end * math.sin(b)), math.cos(b)))
    for i in range(n_mid + 1):
        xs.append((-x_cap + 2 * x_cap * i / n_mid, 1.0))
    for i in range(1, caps + 1):
        b = math.pi / 2 * i / caps
        xs.append((x_cap + r_end * math.sin(b), math.cos(b)))

    verts, faces, rings = [], [], []
    for x, k in xs:
        zc, h, d = beam_shape(abs(x) / BEAM_L)
        if k < 1e-4:
            rings.append([len(verts)])
            verts.append((x, 0.0, BEAM_Z + zc))
            continue
        # soften the cap so it becomes a rounded horn tip
        kk = k ** 0.9
        ring = []
        for j in range(M):
            ph = 2 * math.pi * j / M
            c, s_ = math.cos(ph), math.sin(ph)
            y = (d / 2 * kk + inflate) * math.copysign(abs(c) ** (2 / expo), c)
            z = (h / 2 * kk + inflate) * math.copysign(abs(s_) ** (2 / expo), s_)
            ring.append(len(verts))
            verts.append((x, y, BEAM_Z + zc + z))
        rings.append(ring)
    for i in range(len(rings) - 1):
        A, B = rings[i], rings[i + 1]
        for j in range(M):
            j2 = (j + 1) % M
            if len(A) == 1:
                faces.append((A[0], B[j2], B[j]))
            elif len(B) == 1:
                faces.append((A[j], A[j2], B[0]))
            else:
                faces.append((A[j], A[j2], B[j2], B[j]))
    return verts, faces


def build_beam(coll, wood):
    verts, faces = beam_geometry()
    ob = make_object("Scale_Beam", verts, faces, coll, [wood], sharp_angle=60)
    sub = ob.modifiers.new("Subdivision", "SUBSURF")
    sub.levels = 1
    sub.render_levels = 2
    return ob


COLUMN_EBONY_ZONES = [(2.86, 3.72), (6.40, 7.12), (13.28, 13.70), (16.26, 16.90)]


def column_profile():
    p = Profile(0, 0)
    # --- round plinth disc
    p.line(3.95, 0.0, 0.10)
    p.line(3.95, 0.55, 0.12)
    p.line(3.58, 0.55, 0.04)
    p.line(3.58, 0.78, 0.05)
    p.line(3.45, 0.80, 0.03)
    # --- bell / dome of the base
    p.bez((3.40, 1.95), (2.45, 2.62), (1.62, 2.70), n=40)
    p.line(1.62, 2.72, 0.03)
    p.line(1.62, 2.86, 0.04)
    p.line(1.30, 2.88, 0.02)
    # --- ebony bead
    p.arc((1.22, 3.20), 0.30, -90, 90, n=20)
    p.line(1.02, 3.52, 0.03)
    p.line(1.02, 3.70, 0.03)
    # --- vase (baluster)
    p.bez((1.25, 3.72), (1.46, 4.05), (1.46, 4.55), n=24)
    p.bez((1.46, 5.15), (0.62, 5.70), (0.56, 6.38), n=30)
    # --- neck rings (ebony)
    p.line(0.56, 6.42, 0.02)
    p.arc((0.60, 6.62), 0.20, -90, 90, n=16)
    p.line(0.50, 6.86, 0.02)
    p.line(0.86, 6.90, 0.04)
    p.line(0.86, 7.08, 0.04)
    p.line(0.63, 7.12, 0.03)
    # --- long tapered spindle
    p.bez((0.82, 8.6), (0.56, 11.4), (0.48, 13.28), n=50)
    # --- collar under the hub (ebony)
    p.line(0.64, 13.32, 0.04)
    p.line(0.64, 13.62, 0.04)
    p.line(0.55, 13.68, 0.02)
    # --- hub block that holds the beam
    p.line(0.98, 13.80, 0.16)
    p.line(0.98, 16.20, 0.16)
    p.line(0.55, 16.28, 0.02)
    # --- collars above the hub (ebony)
    p.line(0.72, 16.32, 0.04)
    p.line(0.72, 16.56, 0.04)
    p.line(0.46, 16.62, 0.02)
    p.arc((0.46, 16.74), 0.12, -90, 90, n=10)
    p.line(0.36, 16.88, 0.02)
    # --- acorn / flame finial up to exactly 20 cm
    p.bez((0.48, 16.95), (0.64, 17.35), (0.64, 17.85), n=24)
    p.bez((0.64, 18.65), (0.30, 19.40), (0.15, 19.82), n=30)
    p.arc((0.0, 19.82), 0.15, 0, 90, n=10)  # ends at (0, 19.97)
    p.line(0.0, 20.0, 0.0)
    return p


def build_column(coll, wood, ebony):
    zones = [(a, b, 1) for a, b in COLUMN_EBONY_ZONES]
    return lathe("Scale_Column", column_profile(), coll, [wood, ebony], zones,
                 segs=112, max_seg=0.18)


def pan_profile():
    p = Profile(0, 0.08)
    p.line(1.18, 0.08, 0.02)
    p.line(1.24, 0.0, 0.03)
    p.line(1.50, 0.0, 0.08)
    p.bez((2.12, 0.06), (2.40, 0.62), (2.42, 1.18), n=30)
    p.arc((2.30, 1.18), 0.12, 0, 180, n=16)
    p.bez((2.17, 0.70), (1.95, 0.34), (1.30, 0.30), n=26)
    p.line(0.0, 0.30, 0.0)
    return p


def build_pan(name, coll, wood, centre, hole_angles, hole_z=1.02):
    ob = lathe(name, pan_profile(), coll, [wood], segs=112, max_seg=0.15)
    # drill the three chain holes through the rim (boolean, then baked)
    cutters = []
    for a in hole_angles:
        v, f = [], []
        u = Vector((math.cos(a), math.sin(a), 0))
        tube_geometry([u * 1.7 + Vector((0, 0, hole_z)), u * 2.9 + Vector((0, 0, hole_z))],
                      0.065, sides=16, verts=v, faces=f)
        cutters.append((v, f))
    v_all, f_all = [], []
    for v, f in cutters:
        off = len(v_all)
        v_all += v
        f_all += [tuple(i + off for i in fc) for fc in f]
    cut = make_object(name + "_cutter", v_all, f_all, coll, smooth=False)
    mod = ob.modifiers.new("Holes", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.object = cut
    try:
        mod.solver = "EXACT"
    except Exception:
        pass
    dg = bpy.context.evaluated_depsgraph_get()
    new_me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    old = ob.data
    ob.modifiers.remove(mod)
    ob.data = new_me
    new_me.name = name
    bpy.data.meshes.remove(old)
    bpy.data.objects.remove(cut, do_unlink=True)
    ob.location = Vector(centre) * CM
    return ob


def build_scale(gold, wood, ebony, wood_x):
    coll = new_collection("Scale_Mizan_20cm")
    root = bpy.data.objects.new("SCALE_ROOT", None)
    root.empty_display_type = "PLAIN_AXES"
    root.empty_display_size = 0.05
    coll.objects.link(root)

    parts = [build_column(coll, wood, ebony), build_beam(coll, wood_x)]

    for side in (-1, 1):
        tag = "L" if side < 0 else "R"
        hx = side * HOOK_S * BEAM_L
        zc, h, d = beam_shape(HOOK_S)
        beam_bottom = BEAM_Z + zc - h / 2

        v, f = [], []
        # screw eye under the beam (+ shank going up into the wood)
        eye_c = Vector((hx, 0, beam_bottom - 0.10))
        tube_geometry(ring_path(eye_c, 0.16, (1, 0, 0), (0, 0, 1), 36) , 0.042,
                      sides=10, closed=True, verts=v, faces=f)
        tube_geometry([eye_c + Vector((0, 0, 0.16)), eye_c + Vector((0, 0, 0.75))], 0.045,
                      sides=10, verts=v, faces=f)
        # S-hook (in the YZ plane, through the eye)
        top = eye_c + Vector((0, 0, -0.16))
        r_h = 0.11
        z_top_c = top.z + 0.0
        z_bot_c = z_top_c - 0.85
        path = []
        for i in range(19):  # upper hook: open end on -Y, over the eye wire, down +Y
            a = math.radians(205 - 205 * i / 18)
            path.append(Vector((hx, r_h * math.cos(a), z_top_c + r_h * math.sin(a))))
        for i in range(1, 9):  # shank
            t = i / 9
            path.append(Vector((hx, r_h * (1 - 2 * t), z_top_c - (z_top_c - z_bot_c) * t)))
        for i in range(19):  # lower hook
            a = math.radians(180 + 205 * i / 18)
            path.append(Vector((hx, r_h * math.cos(a), z_bot_c + r_h * math.sin(a))))
        tube_geometry(path, 0.04, sides=10, verts=v, faces=f)
        # jump ring hanging in the lower hook
        ring_r = 0.17
        ring_c = Vector((hx, 0, z_bot_c - r_h + 0.08 - ring_r))
        tube_geometry(ring_path(ring_c, ring_r, (1, 0, 0), (0, 0, 1), 40), 0.038,
                      sides=10, closed=True, verts=v, faces=f)
        chain_top = ring_c + Vector((0, 0, -ring_r))

        # pan + 3 chains
        pan_c = Vector((hx, 0, PAN_BOTTOM))
        angles = [math.radians(a) for a in (90, 210, 330)]
        pan = build_pan("Scale_Pan_" + tag, coll, wood, pan_c, angles)
        parts.append(pan)
        hole_z = 1.02
        for k, a in enumerate(angles):
            u = Vector((math.cos(a), math.sin(a), 0))
            rr = 2.27  # middle of the wall at that height
            rc = pan_c + u * rr + Vector((0, 0, hole_z + 0.13))
            tube_geometry(ring_path(rc, 0.13, u, (0, 0, 1), 32), 0.03, sides=8,
                          closed=True, verts=v, faces=f)
            end = rc + Vector((0, 0, 0.13))
            start = chain_top + u * 0.05
            build_chain(start, end, v, f, twist=k * 0.4)
        parts.append(make_object("Scale_Gold_Hardware_" + tag, v, f, coll, [gold],
                                 sharp_angle=80))

    for ob in parts:
        parent_to(ob, root)
    return root


# --------------------------------------------------------------------------
# 2. GAVEL (overall length 15 cm) + sound block + stand
# --------------------------------------------------------------------------

HEAD_HALF = 3.5     # head length 7 cm
HANDLE_LEN = 13.4   # from head axis to handle tip (13.4 + 1.6 head radius = 15 cm)
REST_X = 11.0       # position of the handle rest (from head axis)


def rest_profile(base_z, handle_z, cup_r, with_cup=True):
    """Turned post with a spherical cup on top that cradles the handle."""
    top_r = 0.80
    cup_rim = 0.56
    zc = handle_z - base_z                 # handle axis height above the stand
    rim_z = zc - math.sqrt(cup_r ** 2 - cup_rim ** 2)
    p = Profile(0, 0)
    p.line(1.05, 0.0, 0.06)
    p.line(1.05, 0.28, 0.08)
    p.line(0.86, 0.32, 0.03)
    p.bez((0.80, 0.70), (0.42, 0.75), (0.36, 1.10), n=20)
    p.line(0.36, 1.20, 0.02)
    p.arc((0.36, 1.36), 0.16, -90, 90, n=12)        # ebony bead
    p.line(0.34, 1.56, 0.02)
    p.bez((0.62, 2.10), (0.62, 2.70), (0.32, rim_z - 1.05), n=24)
    p.line(0.32, rim_z - 0.90, 0.02)
    p.arc((0.32, rim_z - 0.75), 0.15, -90, 90, n=12)  # ebony bead
    p.line(0.36, rim_z - 0.58, 0.02)
    p.bez((0.55, rim_z - 0.45), (top_r, rim_z - 0.30), (top_r, rim_z - 0.08), n=14)
    p.arc((top_r - 0.08, rim_z - 0.08), 0.08, 0, 90, n=6)
    p.line(cup_rim, rim_z, 0.02)
    if not with_cup:
        return p, rim_z, zc
    for i in range(1, 17):                          # spherical cup = handle seat
        r = cup_rim * (1 - i / 16)
        p.line(r, zc - math.sqrt(cup_r ** 2 - r * r), 0.0)
    return p, rim_z, zc


def build_handle_rest(coll, wood, ebony, base_z, handle_z, cup_r):
    p, rim_z, _ = rest_profile(base_z, handle_z, cup_r)
    zones = [(1.18, 1.54, 1), (rim_z - 0.92, rim_z - 0.58, 1)]
    ob = lathe("Gavel_Handle_Rest", p, coll, [wood, ebony], zones, segs=96, max_seg=0.15)
    ob.location = (0, 0, base_z * CM)
    return ob


def head_half_profile():
    p = Profile(0, -HEAD_HALF - 0.04)          # slightly domed striking face
    p.line(1.10, -HEAD_HALF, 0.0)
    p.line(1.53, -HEAD_HALF, 0.14)
    p.line(1.60, -2.95, 0.10)
    p.line(1.38, -2.90, 0.02)
    p.line(1.38, -2.74, 0.02)
    p.line(1.53, -2.70, 0.05)
    p.line(1.53, -2.34, 0.05)
    p.line(1.36, -2.30, 0.02)
    p.line(1.43, -2.22, 0.03)
    p.line(1.43, -1.48, 0.03)
    p.line(1.32, -1.44, 0.02)
    p.line(1.32, 0.0, 0.0)
    return p


def build_gavel_head(coll, wood, ebony, brass):
    full = head_half_profile().mirrored()
    zones = [(-2.96, -2.28, 1), (2.28, 2.96, 1)]
    head = lathe("Gavel_Head", full, coll, [wood, ebony], zones, segs=112, max_seg=0.15)

    b = Profile(1.30, -1.40)
    b.line(1.46, -1.40, 0.025)
    b.line(1.49, -1.28, 0.02)
    b.line(1.44, -1.20, 0.015)
    b.line(1.44, 1.20, 0.015)
    b.line(1.49, 1.28, 0.02)
    b.line(1.46, 1.40, 0.025)
    b.line(1.30, 1.40, 0.0)
    b.line(1.30, -1.40, 0.0)
    band = lathe("Gavel_Brass_Band", b, coll, [brass], segs=112, max_seg=0.1)
    return head, band


def handle_profile():
    p = Profile(0, 0.6)
    p.line(0.48, 0.6, 0.02)
    p.line(0.48, 1.30, 0.0)
    p.bez((0.55, 1.62), (0.80, 1.70), (0.80, 2.05), n=20)
    p.bez((0.80, 2.42), (0.60, 2.58), (0.55, 2.72), n=20)
    p.line(0.70, 2.78, 0.04)
    p.line(0.70, 3.04, 0.04)
    p.line(0.50, 3.10, 0.02)
    p.bez((0.50, 3.8), (0.49, 4.5), (0.48, 5.0), n=12)
    p.arc((0.48, 5.15), 0.15, -90, 90, n=12)
    p.line(0.47, 5.30, 0.02)
    p.bez((0.47, 7.0), (0.43, 8.2), (0.46, 9.5), n=30)
    p.bez((0.50, 10.6), (0.63, 11.4), (0.63, 12.35), n=24)
    p.bez((0.64, 13.05), (0.36, HANDLE_LEN), (0.0, HANDLE_LEN), n=20)
    return p


def build_gavel_handle(coll, wood, ebony):
    p = handle_profile()
    zones = [(2.76, 3.08, 1), (4.98, 5.32, 1)]
    return lathe("Gavel_Handle", p, coll, [wood, ebony], zones, segs=64, max_seg=0.2)


def sound_block_profile():
    p = Profile(0, 0)
    p.line(2.90, 0.0, 0.08)
    p.line(2.95, 0.85, 0.12)
    p.line(2.62, 0.92, 0.04)
    p.bez((2.62, 1.10), (2.55, 1.30), (2.40, 1.42), n=12)
    p.line(0.0, 1.44, 0.0)
    return p


def build_sound_block(coll, wood):
    return lathe("Gavel_Sound_Block", sound_block_profile(), coll, [wood], segs=112, max_seg=0.15)


def build_stand(coll, wood, length=17.4, width=7.2, height=1.7, x0=-3.7):
    x1 = x0 + length
    w = width / 2
    v = [(x0, -w, 0), (x1, -w, 0), (x1, w, 0), (x0, w, 0),
         (x0, -w, height), (x1, -w, height), (x1, w, height), (x0, w, height)]
    f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    ob = make_object("Gavel_Stand", v, f, coll, [wood], smooth=False)
    # decorative groove along the top (rest for the handle) - boolean, baked
    gv, gf = [], []
    gx0, gx1, gw, gd = 3.6, REST_X - 1.6, 0.55, 0.32
    gv = [(gx0, -gw, height - gd), (gx1, -gw, height - gd), (gx1, gw, height - gd), (gx0, gw, height - gd),
          (gx0, -gw, height + 1), (gx1, -gw, height + 1), (gx1, gw, height + 1), (gx0, gw, height + 1)]
    cutter = make_object("tmp_groove", gv, f, coll, smooth=False)
    mod = ob.modifiers.new("Groove", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.object = cutter
    try:
        mod.solver = "EXACT"
    except Exception:
        pass
    dg = bpy.context.evaluated_depsgraph_get()
    new_me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    old = ob.data
    ob.modifiers.remove(mod)
    ob.data = new_me
    new_me.name = "Gavel_Stand"
    bpy.data.meshes.remove(old)
    bpy.data.objects.remove(cutter, do_unlink=True)
    # rounded / ogee edges, kept live so it stays editable
    bev = ob.modifiers.new("Bevel", "BEVEL")
    bev.width = 0.22 * CM
    bev.segments = 5
    bev.limit_method = "ANGLE"
    bev.angle_limit = math.radians(40)
    bev.profile = 0.6
    try:
        bev.harden_normals = True
    except Exception:
        pass
    for poly in ob.data.polygons:
        poly.use_smooth = True
    return ob, height, gx0, gx1


def build_gavel(wood, wood_x, ebony, brass):
    coll = new_collection("Gavel_Mitraqa_15cm")
    root = bpy.data.objects.new("GAVEL_ROOT", None)
    root.empty_display_type = "PLAIN_AXES"
    root.empty_display_size = 0.05
    coll.objects.link(root)

    stand, stand_h, gx0, gx1 = build_stand(coll, wood_x)
    block = build_sound_block(coll, wood_x)
    block.location = (0, 0, stand_h * CM)
    block_top = stand_h + 1.44

    head, band = build_gavel_head(coll, wood, ebony, brass)
    head_c = Vector((0, 0, block_top + HEAD_HALF))
    head.location = head_c * CM
    band.location = head_c * CM

    # handle perfectly straight: horizontal and at right angles to the head
    handle = build_gavel_handle(coll, wood, ebony)
    handle.rotation_euler = (0.0, math.pi / 2, 0.0)  # local +Z -> +X
    handle.location = head_c * CM

    # small turned rest under the grip so the straight handle is supported
    rest = build_handle_rest(coll, wood, ebony, base_z=stand_h, handle_z=head_c.z,
                             cup_r=0.60)
    rest.location = (REST_X * CM, 0, stand_h * CM)

    for ob in (stand, block, head, band, handle, rest):
        parent_to(ob, root)
    return root


# --------------------------------------------------------------------------
# 3. STUDIO (table, wall, satin curtain, lights, camera) - optional
# --------------------------------------------------------------------------


def build_studio():
    coll = new_collection("Studio")
    table = make_simple("Table_White", (0.78, 0.77, 0.75), rough=0.35)
    wall = make_simple("Wall_Cream", (0.70, 0.68, 0.63), rough=0.8)
    satin = make_simple("Curtain_Gold_Satin", (0.75, 0.48, 0.12), rough=0.28,
                        metal=0.55, aniso=0.6)

    s = 80
    make_object("Studio_Table", [(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)],
                [(0, 1, 2, 3)], coll, [table], smooth=False)
    make_object("Studio_Wall", [(-s, 22, 0), (s, 22, 0), (s, 22, 60), (-s, 22, 60)],
                [(0, 3, 2, 1)], coll, [wall], smooth=False)

    # draped curtain: wavy sheet behind the scale on the right
    nx, nz = 160, 60
    v, f = [], []
    for j in range(nz + 1):
        z = 60 * j / nz
        for i in range(nx + 1):
            x = 1.0 + 40 * i / nx
            y = 12 + 1.6 * math.sin(x * 0.75 + 0.3 * math.sin(z * 0.15)) \
                + 0.5 * math.sin(x * 2.1 + z * 0.12) + 0.04 * x
            v.append((x, y, z))
    for j in range(nz):
        for i in range(nx):
            a = j * (nx + 1) + i
            f.append((a, a + 1, a + nx + 2, a + nx + 1))
    cur = make_object("Studio_Curtain", v, f, coll, [satin], smooth=True, sharp_angle=180)
    cur.data.polygons.foreach_set("use_smooth", [True] * len(cur.data.polygons))

    def area(name, loc, energy, size, color, target=(0, 0, 0.08)):
        ld = bpy.data.lights.new(name, "AREA")
        ld.energy = energy
        ld.size = size
        ld.color = color
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        coll.objects.link(ob)
        d = Vector(target) - Vector(loc)
        ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
        return ob

    area("Key_Light", (-0.45, -0.40, 0.55), 9, 0.35, (1.0, 0.93, 0.85))
    area("Fill_Light", (0.55, -0.35, 0.25), 2.5, 0.5, (0.9, 0.95, 1.0))
    area("Rim_Light", (-0.10, 0.30, 0.45), 5, 0.25, (1.0, 0.85, 0.65))

    cam_d = bpy.data.cameras.new("Camera")
    cam_d.lens = 62
    cam_d.dof.use_dof = True
    cam_d.dof.aperture_fstop = 8.0
    cam = bpy.data.objects.new("Camera", cam_d)
    coll.objects.link(cam)
    cam.location = (-0.26, -0.62, 0.27)
    target = Vector((0.005, -0.045, 0.085))
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam_d.dof.focus_distance = (target - cam.location).length
    bpy.context.scene.camera = cam

    # extra close-up cameras (switch with Ctrl+Numpad0)
    for name, loc, tgt, lens in (
            ("Camera_Scale_Front", (0.13, -0.70, 0.14), (0.012, 0.0, 0.10), 80),
            ("Camera_Gavel_Close", (-0.20, -0.38, 0.17), (-0.04, -0.10, 0.04), 70)):
        cd = bpy.data.cameras.new(name)
        cd.lens = lens
        co = bpy.data.objects.new(name, cd)
        co.location = loc
        co.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        coll.objects.link(co)

    world = bpy.context.scene.world or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    try:
        world.use_nodes = True
    except Exception:
        pass
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.35, 0.33, 0.30, 1)
        bg.inputs["Strength"].default_value = 0.25
    return coll


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def main(with_studio=True):
    clear_scene()
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.scale_length = 1.0
    sc.unit_settings.length_unit = "CENTIMETERS"

    wood = make_wood("Wood_Mahogany_Turned", "Z",
                     dark=(0.045, 0.014, 0.006), mid=(0.125, 0.042, 0.016),
                     light=(0.20, 0.075, 0.030))
    wood_x = make_wood("Wood_Mahogany_Plank", "X",
                       dark=(0.045, 0.014, 0.006), mid=(0.125, 0.042, 0.016),
                       light=(0.20, 0.075, 0.030), offset=(3.0, 9.0, 13.0))
    ebony = make_wood("Wood_Dark_Rings", "Z",
                      dark=(0.006, 0.003, 0.002), mid=(0.020, 0.009, 0.005),
                      light=(0.045, 0.020, 0.010), rough=0.3)
    gold = make_metal("Gold_Chain", (1.0, 0.72, 0.30), rough=0.18)
    brass = make_metal("Brass_Band", (0.86, 0.53, 0.16), rough=0.16)

    scale_root = build_scale(gold, wood, ebony, wood_x)
    gavel_root = build_gavel(wood, wood_x, ebony, brass)

    # arrange like the reference photo: gavel in front, scale behind
    scale_root.location = (0.0, 0.0, 0)
    gavel_root.location = (-0.085, -0.10, 0)
    gavel_root.rotation_euler = (0, 0, 0)

    if with_studio:
        build_studio()
        sc.render.engine = "CYCLES"
        sc.cycles.samples = 128
        sc.cycles.use_denoising = True
        sc.render.resolution_x = 1080
        sc.render.resolution_y = 1350
        try:
            sc.view_settings.view_transform = "AgX"
            sc.view_settings.look = "AgX - Medium High Contrast"
        except Exception:
            pass


if __name__ == "__main__":
    main()
