"""
Classic cap-style safety helmet -- procedural Blender model.

Smooth tall dome. A curved line runs down each side from the crown to the band,
so the front of the dome is a slightly raised panel. A raised band runs around
the sides and back and ends square at that line; a narrow slot on each side
splits it into two blocks. Wide front peak, rain gutter around the rim. No ridge
on the crown, no vents.

Shell only: no suspension, no straps, no fabric. The shell sits directly on
the head with no extra room: where it touches the head, the inner wall measures
exactly HEAD_CIRC around (58 cm). Change HEAD_CIRC for another size; the whole
helmet, height included, is rescaled to it and the wall stays TH_REAL thick.

Run inside Blender (Scripting tab -> Open -> Run Script; the helmet is built
in a new scene called "HardHat", takes a few seconds), or headless:
    blender --background --python hard_hat_classic_generator.py -- /path/to/output.blend

Shape parameters are in "design millimetres"; the solved SCALE turns them into
real millimetres. The model is built at real-world scale (1 Blender unit = 1 m,
scene shows millimetres).
"""

import math
import sys

import bpy  # noqa: E402  (bpy must be imported before bmesh)
import bmesh
import numpy as np
from mathutils import Vector

# --------------------------------------------------------------------------
# Head size and fit
# --------------------------------------------------------------------------
HEAD_CIRC = 580.0       # head circumference in mm (58 cm)
TH_REAL = 2.8           # wall thickness of the finished helmet, mm
LIP_BEAD_REAL = 1.8     # extra thickness rolled into the lip / peak edge, mm

# Fit plane: the horizontal plane just above the band step, where the inner
# wall of the dome starts and the shell touches the head (below it the band
# steps outwards and does not touch the head). The generator solves SCALE so
# that the inner wall measures exactly HEAD_CIRC around in this plane, with
# no gap. Everything scales together, so the height follows the size.
FIT_ABOVE_LEDGE = 1.0   # design mm above the highest point of the band step

SCALE = 1.0             # design mm -> real mm (solved in build_shell_rings)
TH = TH_REAL            # wall thickness in design mm (set by set_scale)
LIP_BEAD = LIP_BEAD_REAL
MM = 0.001              # one design millimetre in metres (set by set_scale)
REAL_MM = 0.001
HEAD_TAG = "%gcm" % (HEAD_CIRC / 10)


def set_scale(s):
    global SCALE, TH, LIP_BEAD, MM
    SCALE = s
    TH = TH_REAL / s
    LIP_BEAD = LIP_BEAD_REAL / s
    MM = 0.001 * s


# --------------------------------------------------------------------------
# Shape parameters (design millimetres, see SCALE)
# --------------------------------------------------------------------------
NU = 960            # segments around the helmet
ND_OUT = 240        # rings on the outer dome
ND_IN = 90          # rings on the inner dome
N_CAP = 9           # rings on the rounded lip edge

# Footprint of the dome at the band step (egg shape, a little wider at back)
A0, DA = 96.5, 1.5  # half width   -> 95 at front-side, 98 at back-side
B0, DB = 122.0, 2.0  # half length -> 120 to the front, 124 to the back
Z_TOP = 152.0       # top of the crown above the peak root
N_SUPER = (2.2, 2.35, 2.15)  # dome superellipse exponent: front, sides, back
APEX_Y = 8.0        # crown apex a little behind the centre

# Front panel: the front of the dome between the two side lines, raised a
# little. Each line runs from the crown down to the band, at PANEL_PSI degrees
# from the front (measured around the crown).
PANEL_PSI = 50.0    # where the side lines are, degrees from the front
PANEL_H = 2.0       # how far the panel stands out
PANEL_EDGE = 2.4    # width of the rounded step along the lines

# Band around the sides and back, rain gutter and peak
DROP_BACK = 14.0    # how much lower the rim is at the back than at the peak
DROP_SIDE = 5.0     # extra dip of the rim over the ears
R1, R2 = 1.5, 3.6   # band top fillets (concave, convex)
BAND_STEP = 8.0     # how far the band stands out from the dome
SLOT_PHI = 100.0    # accessory slot (gap in the band) on each side, degrees
SLOT_GAP = 6.0      # slot width along the band
FRONT_BLOCK_DROP = 5.0  # band top is this much lower in front of the slot
PEAK = 58.0         # length of the front peak
GUTTER = 8.0        # width of the rain gutter on the sides and back


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def lerp(a, b, t):
    return a + (b - a) * t


def footprint(phi):
    """Dome base outline. phi=0 front (-Y), phi=90deg right (+X)."""
    c, s = np.cos(phi), np.sin(phi)
    a = A0 - DA * c
    b = B0 - DB * c
    r = 1.0 / np.sqrt((s / a) ** 2 + (c / b) ** 2)
    return np.stack([r * s, -r * c], -1), r


def footprint_frame(phi):
    eps = 1e-4
    p, _ = footprint(phi)
    t = footprint(phi + eps)[0] - footprint(phi - eps)[0]
    t /= np.linalg.norm(t, axis=-1, keepdims=True)
    n = np.stack([t[..., 1], -t[..., 0]], -1)  # outward
    return p, t, n


_HALF = np.linspace(0.0, math.pi, 20001)


def footprint_arc(phi):
    """Arc length along the footprint from the front centre (mirrored)."""
    p, _ = footprint(_HALF)
    cum = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])
    ph = np.mod(phi, 2 * math.pi)
    ph = np.where(ph > math.pi, 2 * math.pi - ph, ph)
    return np.interp(ph, _HALF, cum)


def crown_angle(phi):
    """Angle of the footprint point around the crown axis, degrees from the
    front (0) to the back (180)."""
    p, _ = footprint(phi)
    return np.degrees(np.arctan2(np.abs(p[..., 0]), -(p[..., 1] - APEX_Y)))


def band_layout(phi):
    """band: 1 where the raised band is, 0 at the front panel and in the slot.
    drop: how much lower the band top is (front block)."""
    s_col = footprint_arc(phi)
    s_slot = footprint_arc(np.radians(SLOT_PHI))
    on = smoothstep(PANEL_PSI + 1.0, PANEL_PSI + 3.5, crown_angle(phi))
    gap = 1.0 - smoothstep(SLOT_GAP / 2, SLOT_GAP / 2 + 1.2, np.abs(s_col - s_slot))
    drop = FRONT_BLOCK_DROP * (1.0 - smoothstep(s_slot - 2.5, s_slot + 2.5, s_col))
    return on * (1.0 - gap), drop


def brim_weight(phi):
    c = np.cos(phi)
    c75 = math.cos(math.radians(75))
    return smoothstep(0.0, 1.0, (c - c75) / (1.0 - c75))


# --------------------------------------------------------------------------
# Profile of the lower shell (step, band, gutter / peak), per spoke.
# Coordinates (h, z): h = horizontal offset along the footprint normal.
# --------------------------------------------------------------------------
SEG_COUNTS = dict(s1=3, s2=2, s3=6, s4=26, s5=12, s6=36)


def segment(p0, psi0, psi1, L, n):
    """Constant-curvature segment, vectorised over spokes. Angles in radians.
    Returns samples at fractions k/n, k=1..n (start excluded)."""
    f = (np.arange(1, n + 1) / n)[None, :]
    dpsi = (psi1 - psi0)[:, None]
    psi = psi0[:, None] + dpsi * f
    s = L[:, None] * f
    straight = np.abs(dpsi) < 1e-7
    r = np.where(straight, 1.0, L[:, None] / np.where(straight, 1.0, dpsi))
    h_arc = r * (np.sin(psi) - np.sin(psi0)[:, None])
    z_arc = r * (np.cos(psi0)[:, None] - np.cos(psi))
    h_lin = s * np.cos(psi0)[:, None]
    z_lin = s * np.sin(psi0)[:, None]
    h = np.where(straight, h_lin, h_arc)
    z = np.where(straight, z_lin, z_arc)
    return np.stack([p0[:, 0:1] + h, p0[:, 1:2] + z], -1)


def rim_heights(phi):
    c, s = np.cos(phi), np.sin(phi)
    z_bb = -DROP_BACK * (1 - c) / 2 - DROP_SIDE * s ** 2      # band bottom
    h_band = 22.0 + 8.0 * s ** 2 + 4.0 * (1 - c) / 2          # band height
    _, drop = band_layout(phi)
    return z_bb, z_bb + h_band - drop


def lower_profile(phi):
    c = np.cos(phi)
    nphi = len(phi)
    wb = brim_weight(phi)
    z_bb, z_L = rim_heights(phi)

    # band: stands out BAND_STEP on the sides and back, almost nothing at the
    # front panel and in the slots
    band, _ = band_layout(phi)
    wL = 0.3 + (BAND_STEP - 0.3) * band
    beta = np.minimum(math.radians(75), np.arccos(np.clip(1 - wL / (R1 + R2), -1, 1)))
    Ls = np.maximum(0.0, (wL - (R1 + R2) * (1 - np.cos(beta))) / np.sin(beta))

    th0 = np.radians(lerp(-8.0, -14.0, wb))     # lip start angle
    th1 = np.radians(lerp(35.0, -38.0, wb))     # lip end angle (gutter up / peak down)
    r3 = lerp(4.5, 9.0, wb)                     # band -> lip fillet
    L_lip = GUTTER + (PEAK - GUTTER) * wb       # gutter width / peak length

    d90 = np.full(nphi, -math.pi / 2)
    d88 = np.full(nphi, math.radians(-88))
    p0 = np.stack([np.zeros(nphi), z_L], -1)
    out = [p0[:, None, :]]

    a1 = d90 + beta
    s1 = segment(p0, d90, a1, R1 * beta, SEG_COUNTS['s1'])
    s2 = segment(s1[:, -1], a1, a1, np.maximum(Ls, 1e-3), SEG_COUNTS['s2'])
    s3 = segment(s2[:, -1], a1, d88, R2 * np.abs(d88 - a1), SEG_COUNTS['s3'])
    dz5 = r3 * (np.cos(d88) - np.cos(th0))
    z3 = s3[:, -1, 1]
    L4 = (z3 + dz5 - z_bb) / math.sin(math.radians(88))
    s4 = segment(s3[:, -1], d88, d88, L4, SEG_COUNTS['s4'])
    s5 = segment(s4[:, -1], d88, th0, r3 * (th0 - d88), SEG_COUNTS['s5'])
    s6 = segment(s5[:, -1], th0, th1, L_lip, SEG_COUNTS['s6'])
    out += [s1, s2, s3, s4, s5, s6]
    return np.concatenate(out, axis=1), z_L


def dome(phi, z_L, nd):
    """Superellipse dome from apex to the step, uniform arc length.
    Returns points [NU, nd, 3] (apex first, base excluded)."""
    p, r = footprint(phi)
    al = np.linspace(0.0, math.pi / 2, 2400)
    c, s = np.cos(phi), np.sin(phi)
    nf, ns, nb = N_SUPER
    n_sup = np.where(c > 0, nf + (ns - nf) * s ** 2, nb + (ns - nb) * s ** 2)
    H = Z_TOP - z_L
    pts = np.empty((len(phi), nd, 3))
    for i in range(len(phi)):
        e = 2.0 / n_sup[i]
        sig = np.sin(al) ** e
        zr = np.cos(al) ** e
        x = sig * p[i, 0]
        y = APEX_Y + sig * (p[i, 1] - APEX_Y)
        z = z_L[i] + H[i] * zr
        d = np.sqrt(np.diff(x) ** 2 + np.diff(y) ** 2 + np.diff(z) ** 2)
        cum = np.concatenate([[0.0], np.cumsum(d)])
        tgt = np.linspace(0.0, cum[-1], nd + 1)[:-1]
        pts[i, :, 0] = np.interp(tgt, cum, x)
        pts[i, :, 1] = np.interp(tgt, cum, y)
        pts[i, :, 2] = np.interp(tgt, cum, z)
    return pts


def base_surface(nd):
    phi = np.arange(NU) * (2 * math.pi / NU)
    prof, z_L = lower_profile(phi)
    P, T, N2 = footprint_frame(phi)
    low = np.empty(prof.shape[:2] + (3,))
    low[..., 0] = P[:, None, 0] + prof[..., 0] * N2[:, None, 0]
    low[..., 1] = P[:, None, 1] + prof[..., 0] * N2[:, None, 1]
    low[..., 2] = prof[..., 1]
    return np.concatenate([dome(phi, z_L, nd), low], axis=1)


def grid_normals(pts):
    dphi = np.roll(pts, -1, axis=0) - np.roll(pts, 1, axis=0)
    dt = np.empty_like(pts)
    dt[:, 1:-1] = pts[:, 2:] - pts[:, :-2]
    dt[:, 0] = pts[:, 1] - pts[:, 0]
    dt[:, -1] = pts[:, -1] - pts[:, -2]
    n = np.cross(dt, dphi)
    ln = np.linalg.norm(n, axis=-1, keepdims=True)
    n = n / np.maximum(ln, 1e-12)
    n[:, 0] = (0.0, 0.0, 1.0)  # apex
    return n


def panel_height(P, nd):
    """Raised front panel between the two side lines. It fades out at the
    crown and runs down the front to the root of the peak."""
    x, y = P[..., 0], P[..., 1] - APEX_Y
    rho = np.hypot(x, y)
    psi = np.degrees(np.arctan2(np.abs(x), -y))
    inside = np.radians(PANEL_PSI - psi) * rho        # mm inside the line
    m = smoothstep(-PANEL_EDGE / 2, PANEL_EDGE / 2, inside)
    m = m * smoothstep(6.0, 26.0, rho)
    rows = np.ones(P.shape[1])
    k5 = nd + 1 + SEG_COUNTS['s1'] + SEG_COUNTS['s2'] + SEG_COUNTS['s3'] + SEG_COUNTS['s4']
    rows[k5:k5 + SEG_COUNTS['s5']] = np.linspace(1.0, 0.0, SEG_COUNTS['s5'])
    rows[k5 + SEG_COUNTS['s5']:] = 0.0
    return PANEL_H * m * rows[None, :]


# --------------------------------------------------------------------------
# Shell
# --------------------------------------------------------------------------
def inner_offset(Ib, Ni):
    """Inner wall: the base surface pushed in by the wall thickness, with a
    bead along the lip."""
    nb = 14
    bead = np.zeros(Ib.shape[1])
    bead[-nb:] = LIP_BEAD * smoothstep(0.0, 1.0, np.linspace(0.0, 1.0, nb))
    return Ib - Ni * (TH + bead[None, :])[..., None]


def fit_plane_z():
    _, z_L = rim_heights(np.linspace(0.0, 2 * math.pi, 3601))
    return float(z_L.max()) + FIT_ABOVE_LEDGE


def horizontal_section(I, z):
    """Where each meridian of the inner wall first crosses height z on its
    way down from the crown: [NU, 2], in the units of I."""
    zc = I[..., 2]
    j = np.argmax(zc < z, axis=1)
    rows = np.arange(I.shape[0])
    a, b = I[rows, j - 1], I[rows, j]
    t = (a[:, 2] - z) / (a[:, 2] - b[:, 2])
    return a[:, :2] + t[:, None] * (b[:, :2] - a[:, :2])


def loop_length(p):
    return float(np.sum(np.linalg.norm(np.roll(p, -1, axis=0) - p, axis=1)))


def solve_scale(Ib, Ni, z_fit):
    """SCALE that makes the inner wall exactly HEAD_CIRC around at z_fit."""
    s = 0.85
    for _ in range(50):
        set_scale(s)
        circ = s * loop_length(horizontal_section(inner_offset(Ib, Ni), z_fit))
        if abs(circ - HEAD_CIRC) < 1e-6:
            break
        s *= (HEAD_CIRC + 2 * math.pi * TH_REAL) / (circ + 2 * math.pi * TH_REAL)
    return s


def build_shell_rings():
    # inner wall first: the size of the helmet is set from it
    Ib = base_surface(ND_IN)
    Ni = grid_normals(Ib)
    z_fit = fit_plane_z()
    set_scale(solve_scale(Ib, Ni, z_fit))
    I = inner_offset(Ib, Ni)
    fit = (horizontal_section(I, z_fit), z_fit, float(I[0, 0, 2]))

    # outer wall with the raised front panel
    Ob = base_surface(ND_OUT)
    Nb = grid_normals(Ob)
    O = Ob + Nb * panel_height(Ob, ND_OUT)[..., None]

    # rounded lip edge between the two
    oe, ne = Ob[:, -1], Nb[:, -1]
    te = Ob[:, -1] - Ob[:, -2]
    te /= np.linalg.norm(te, axis=-1, keepdims=True)
    rad = (TH + LIP_BEAD) / 2
    ctr = oe - ne * rad
    cap = []
    for k in range(1, N_CAP + 1):
        g = math.pi * k / (N_CAP + 1)
        cap.append(ctr + rad * (math.cos(g) * ne + math.sin(g) * te))
    cap = np.stack(cap, axis=1)
    I[:, -1] = oe - ne * 2 * rad

    rings = np.concatenate([O, cap, I[:, ::-1]], axis=1)  # [NU, R, 3]
    return np.transpose(rings, (1, 0, 2)), fit


def rings_to_mesh(name, rings):
    R, n, _ = rings.shape
    verts = [tuple(rings[0, 0])]
    for r in range(1, R - 1):
        verts.extend(map(tuple, rings[r]))
    verts.append(tuple(rings[-1, 0]))
    last = len(verts) - 1

    def vid(r, i):
        return 1 + (r - 1) * n + (i % n)

    faces = []
    for i in range(n):
        faces.append((0, vid(1, i), vid(1, i + 1)))
    for r in range(1, R - 2):
        for i in range(n):
            faces.append((vid(r, i), vid(r + 1, i), vid(r + 1, i + 1), vid(r, i + 1)))
    for i in range(n):
        faces.append((vid(R - 2, i), last, vid(R - 2, i + 1)))
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(c * MM for c in v) for v in verts], [], faces)
    me.validate()
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    return me


# --------------------------------------------------------------------------
# Materials, fit-line ring
# --------------------------------------------------------------------------
COLORS = {
    "White": (0.80, 0.80, 0.78),
    "Yellow": (0.95, 0.70, 0.0),
    "Blue": (0.0, 0.22, 0.75),
    "Orange": (0.95, 0.24, 0.02),
    "Red": (0.62, 0.015, 0.02),
}


def make_materials():
    mats = {}
    for name, col in COLORS.items():
        m = bpy.data.materials.get("HardHat_" + name) or bpy.data.materials.new("HardHat_" + name)
        m.use_nodes = True
        bsdf = m.node_tree.nodes.get("Principled BSDF")
        bsdf.inputs["Base Color"].default_value = (*col, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.16
        if "Coat Weight" in bsdf.inputs:
            bsdf.inputs["Coat Weight"].default_value = 0.6
            bsdf.inputs["Coat Roughness"].default_value = 0.04
        if "Subsurface Weight" in bsdf.inputs and name == "White":
            bsdf.inputs["Subsurface Weight"].default_value = 0.04
            bsdf.inputs["Subsurface Radius"].default_value = (2.0, 2.0, 2.0)
            bsdf.inputs["Subsurface Scale"].default_value = 0.002
        m.diffuse_color = (*col, 1.0)
        m.use_fake_user = True
        mats[name] = m
    return mats


def fit_ring(coll, loop, z):
    """Thin ring whose centre line is the inner wall at the fit plane (real mm):
    the line where the head touches the shell, HEAD_CIRC long."""
    n, sides, tube = len(loop), 12, 0.8
    d = np.roll(loop, -1, axis=0) - np.roll(loop, 1, axis=0)
    bm = bmesh.new()
    rings = []
    for i in range(n):
        c = Vector((loop[i, 0], loop[i, 1], z))
        t = Vector((d[i, 0], d[i, 1], 0.0)).normalized()
        out = Vector((t.y, -t.x, 0.0))
        ring = []
        for k in range(sides):
            g = 2 * math.pi * k / sides
            p = c + (out * math.cos(g) + Vector((0, 0, 1)) * math.sin(g)) * tube
            ring.append(bm.verts.new(p * REAL_MM))
        rings.append(ring)
    for i in range(n):
        r0, r1 = rings[i], rings[(i + 1) % n]
        for k in range(sides):
            bm.faces.new((r0[k], r1[k], r1[(k + 1) % sides], r0[(k + 1) % sides]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    name = "Head_%s_fit_line" % HEAD_TAG
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    ob.hide_render = True
    return ob


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main(out_path=None):
    if bpy.app.background:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        scene = bpy.context.scene
    else:
        # inside the Blender UI: build in a fresh scene, leave the user's file alone
        scene = bpy.data.scenes.new("HardHat")
        bpy.context.window.scene = scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.length_unit = 'MILLIMETERS'

    coll = bpy.data.collections.new("HardHat")
    scene.collection.children.link(coll)

    rings, (fit, z_fit, z_crown) = build_shell_rings()
    me = rings_to_mesh("HardHat_Shell", rings)
    shell = bpy.data.objects.new("HardHat", me)
    coll.objects.link(shell)
    bpy.context.view_layer.objects.active = shell

    me.shade_smooth()
    mats = make_materials()
    me.materials.append(mats["Yellow"])

    # size report (real mm)
    loop = fit * SCALE
    fit_z = z_fit * SCALE
    size = dict(
        inner_circumference_at_fit_mm=loop_length(loop),
        inner_width_at_fit_mm=float(np.ptp(loop[:, 0])),
        inner_length_at_fit_mm=float(np.ptp(loop[:, 1])),
        fit_plane_height_mm=fit_z,
        inner_depth_mm=(z_crown - z_fit) * SCALE,
    )
    ref = bpy.data.collections.new("Reference_Head_%s" % HEAD_TAG)
    scene.collection.children.link(ref)
    ring = fit_ring(ref, loop, fit_z)

    # keep the generator inside the .blend (Text Editor) so it can be re-run
    try:
        txt = bpy.data.texts.new("hard_hat_classic_generator.py")
        txt.write(open(__file__, encoding="utf-8").read())
    except Exception:
        pass
    shell["head_circumference_mm"] = HEAD_CIRC
    shell["wall_thickness_mm"] = TH_REAL
    shell["shell_scale"] = SCALE
    for k, val in size.items():
        shell[k] = round(val, 2)
    print("HardHat (classic) for a %.1f cm head: scale %.5f" % (HEAD_CIRC / 10, SCALE))
    for k, val in size.items():
        print("  %-32s %8.2f" % (k, val))

    if out_path:
        bpy.ops.wm.save_as_mainfile(filepath=out_path, compress=True)
    return shell, ring, size


if __name__ == "__main__":
    argv = sys.argv
    out = argv[argv.index("--") + 1] if "--" in argv else None
    main(out)
