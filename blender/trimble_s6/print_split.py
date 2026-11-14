"""
Split the (shortened) Trimble S6 model into printable parts -> 3MF.
==================================================================
SketchUp models are open surfaces made of separate pieces that only touch,
so a plain remesh leaves hundreds of loose shells.  This script builds real
solids instead:

  1. scale to the print height (default 200 mm overall), axis at the origin
  2. per part, sample every triangle densely and rasterise into voxels
  3. morphological closing (bridges gaps up to ~1.5 mm between pieces)
  4. fill the inside (everything not reachable from outside = solid)
  5. cut at the top of the tripod head plate:  TRIPOD below, INSTRUMENT above
  6. a 3.2 mm locating hole in both cut faces + a separate 3.0 mm pin
  7. light smoothing + marching cubes, decimate, colours from the nearest
     original face, written as 3MF (millimetres, per-triangle colours)

Print orientation in the files: tripod upside-down on its flat head plate
(legs at 25 deg -> no supports), instrument standing on its flat base.

Needs numpy, scipy, scikit-image next to bpy.
Usage:  python print_split.py IN.blend OUT_DIR [--height 200]
"""

import math
import os
import sys
import zipfile

import bpy
import bmesh
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from scipy import ndimage
from skimage.measure import marching_cubes

HEAD_TOP_M = 0.95          # top of the tripod head plate in the shortened model (m)
HOLE_D, HOLE_DEPTH = 3.2, 4.0
PIN_D, PIN_L = 3.0, 7.6
LEG_CUT_Z = 127.0        # (only used to fit the leg axes)
HEAD_BOTTOM_Z = 137.5    # legs (with hinge blocks) end at 137 mm, the head disc starts at 138 mm
BASE_R = 14.1            # base disc radius (mm) = original tripod head plate
TENON_H = 3.0            # leg tenon height / socket depth (mm)
BASE_COLOUR = "B9BCBF"
SMOOTH_ITERS = 35        # Taubin smoothing passes on every printed part
LEG_PEGS = False         # leg tops are too small for consistent peg holes: glue them to the head
PEG_D, PEG_DEPTH = 1.9, 4.0   # holes for 1.75 mm filament pegs (one per rail) at the leg joints
TARGET_TRIS = {"Hea": 120000, "Leg": 100000, "Ins": 250000}


def arg(argv, name, default):
    return float(argv[argv.index(name) + 1]) if name in argv else default


# --------------------------------------------------------------------------
#  voxel solidification
# --------------------------------------------------------------------------
def rasterise(tris, origin, shape, voxel):
    """Mark every voxel touched by a triangle.  Rows parallel to the longest
    edge, spaced < voxel/2, so the point count follows the area (slivers stay
    cheap)."""
    occ = np.zeros(shape, bool)
    step = voxel * 0.45
    for a, b, c in tris:
        e = [np.linalg.norm(b - a), np.linalg.norm(c - b), np.linalg.norm(a - c)]
        k = int(np.argmax(e))
        a, b, c = [(a, b, c), (b, c, a), (c, a, b)][k]
        base = b - a
        L = np.linalg.norm(base)
        if L < 1e-9:
            continue
        h = np.linalg.norm(np.cross(base, c - a)) / L
        rows = max(1, int(math.ceil(h / step)))
        t = np.linspace(0, 1, rows + 1)
        p0 = a + np.outer(t, c - a)
        p1 = b + np.outer(t, c - b)
        n = np.maximum(1, np.ceil(L * (1 - t) / step).astype(int))
        m = n.max()
        s = np.linspace(0, 1, m + 1)
        pts = (p0[:, None, :] + (p1 - p0)[:, None, :] * s[None, :, None]).reshape(-1, 3)
        ijk = np.floor((pts - origin) / voxel).astype(np.int64)
        ok = np.all((ijk >= 0) & (ijk < shape), axis=1)
        occ[tuple(ijk[ok].T)] = True
    return occ


def solidify(tris, lo, hi, voxel, close_mm=0.75):
    pad = int(math.ceil(close_mm / voxel)) + 3
    origin = np.array(lo) - pad * voxel
    shape = tuple(np.ceil((np.array(hi) - np.array(lo)) / voxel).astype(int) + 2 * pad + 1)
    occ = rasterise(tris, origin, shape, voxel)
    n = int(round(close_mm / voxel))
    ball = ndimage.generate_binary_structure(3, 1)
    occ = ndimage.binary_dilation(occ, ball, iterations=n)
    lab, _ = ndimage.label(~occ)
    del occ
    border = np.unique(np.concatenate([lab[0].ravel(), lab[-1].ravel(), lab[:, 0].ravel(),
                                       lab[:, -1].ravel(), lab[:, :, 0].ravel(), lab[:, :, -1].ravel()]))
    border = border[border > 0]
    solid = ~np.isin(lab, border)
    del lab
    solid = ndimage.binary_erosion(solid, ball, iterations=n, border_value=0)
    return solid, origin


def is_orange(hexc):
    r, g, b = (int(hexc[i:i + 2], 16) for i in (0, 2, 4))
    return r > 180 and g < 150 and b < 110 and r - g > 70


def keep_main(solid, min_frac=0.002):
    lab, n = ndimage.label(solid)
    if n <= 1:
        return solid, n, 0
    sizes = ndimage.sum(solid, lab, range(1, n + 1))
    keep = np.where(sizes >= sizes.max() * min_frac)[0] + 1
    return np.isin(lab, keep), n, n - len(keep)


def taubin(verts, faces, iters, lam=0.5, mu=-0.53):
    """Taubin smoothing: removes the voxel staircase without shrinking the part."""
    from scipy import sparse
    n = len(verts)
    e = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    e = np.concatenate([e, e[:, ::-1]])
    A = sparse.csr_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(n, n))
    A.data[:] = 1.0
    deg = np.asarray(A.sum(1)).ravel()
    deg[deg == 0] = 1
    v = verts.astype(np.float64)
    for _ in range(iters):
        v = v + lam * ((A @ v) / deg[:, None] - v)
        v = v + mu * ((A @ v) / deg[:, None] - v)
    return v


def _prism_obj(name, pts, z0, z1):
    bm = bmesh.new()
    bot = [bm.verts.new((x, y, z0)) for x, y in pts]
    top = [bm.verts.new((x, y, z1)) for x, y in pts]
    bm.faces.new(list(reversed(bot)))
    bm.faces.new(top)
    for i in range(len(pts)):
        j = (i + 1) % len(pts)
        bm.faces.new((bot[i], bot[j], top[j], top[i]))
    bmesh.ops.triangulate(bm, faces=bm.faces)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _cut(ob, cutter):
    md = ob.modifiers.new("cut", 'BOOLEAN')
    md.operation = 'DIFFERENCE'
    md.solver = 'EXACT'
    md.object = cutter
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    old = ob.data
    ob.modifiers.clear()
    ob.data = me
    bpy.data.meshes.remove(old)
    bpy.data.objects.remove(cutter, do_unlink=True)


def build_base(feet, x0, y0, voxel, split):
    """Exact base: bevelled cylinder, one socket per leg footprint, pin hole."""
    from skimage.measure import find_contours
    h = split - HEAD_BOTTOM_Z
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=180,
                          radius1=BASE_R, radius2=BASE_R, depth=h)
    bmesh.ops.translate(bm, vec=(0, 0, HEAD_BOTTOM_Z + h / 2), verts=bm.verts)
    rims = [e for e in bm.edges if e.calc_face_angle(0) > 1.0]
    bmesh.ops.bevel(bm, geom=rims, offset=0.4, segments=3, affect='EDGES', profile=0.5)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    me = bpy.data.meshes.new("Head")
    bm.to_mesh(me)
    bm.free()
    base = bpy.data.objects.new("Head", me)
    bpy.context.scene.collection.objects.link(base)
    for k_, foot in enumerate(feet):
        f = ndimage.gaussian_filter(np.pad(foot, 2).astype(np.float32), 0.7)
        cs = find_contours(f, 0.5)
        c = max(cs, key=len)[:-1]
        pts = [(x0 + (i - 2) * voxel, y0 + (j - 2) * voxel) for i, j in c[::2]]
        _cut(base, _prism_obj(f"sock{k_}", pts, HEAD_BOTTOM_Z - 1.0, HEAD_BOTTOM_Z + TENON_H + 0.3))
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=64, radius1=HOLE_D / 2, radius2=HOLE_D / 2,
                          depth=HOLE_DEPTH + 1)
    bmesh.ops.translate(bm, vec=(0, 0, split - (HOLE_DEPTH - 1) / 2), verts=bm.verts)
    me = bpy.data.meshes.new("hole")
    bm.to_mesh(me)
    bm.free()
    hole = bpy.data.objects.new("hole", me)
    bpy.context.scene.collection.objects.link(hole)
    _cut(base, hole)
    return base


def to_mesh(solid, origin, voxel, name, sigma=0.65):
    f = ndimage.gaussian_filter(np.pad(solid, 1).astype(np.float32), sigma)
    verts, faces, _, _ = marching_cubes(f, 0.5, spacing=(voxel,) * 3)
    verts += origin - voxel
    verts = taubin(verts, faces, SMOOTH_ITERS)
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(verts))
    me.vertices.foreach_set("co", verts.astype(np.float32).ravel())
    me.loops.add(faces.size)
    me.loops.foreach_set("vertex_index", faces[:, ::-1].astype(np.int32).ravel())
    me.polygons.add(len(faces))
    me.polygons.foreach_set("loop_start", np.arange(0, faces.size, 3, dtype=np.int32))
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def decimate(ob, target):
    n = len(ob.data.polygons)
    if n <= target:
        return
    md = ob.modifiers.new("dec", 'DECIMATE')
    md.ratio = target / n
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    old = ob.data
    ob.modifiers.clear()
    ob.data = me
    bpy.data.meshes.remove(old)


def check(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    nm = sum(1 for e in bm.edges if not e.is_manifold)
    vol = bm.calc_volume(signed=True)
    lo = [min(v.co[i] for v in bm.verts) for i in range(3)]
    hi = [max(v.co[i] for v in bm.verts) for i in range(3)]
    n = len(bm.faces)
    bm.free()
    return n, nm, vol, lo, hi


def pin_mesh():
    """Separate locating pin, chamfered both ends, lying-down-free (printed upright)."""
    r, L, ch, seg = PIN_D / 2, PIN_L, 0.4, 32
    rings = [(r - ch, 0), (r, ch), (r, L - ch), (r - ch, L)]
    bm = bmesh.new()
    loops = [[bm.verts.new((rr * math.cos(2 * math.pi * i / seg), rr * math.sin(2 * math.pi * i / seg), z))
              for i in range(seg)] for rr, z in rings]
    for a, b in zip(loops[:-1], loops[1:]):
        for i in range(seg):
            j = (i + 1) % seg
            bm.faces.new((a[i], a[j], b[j], b[i]))
    bm.faces.new(list(reversed(loops[0])))
    bm.faces.new(loops[-1])
    bmesh.ops.triangulate(bm, faces=bm.faces)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new("Pin")
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("Pin", me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


# --------------------------------------------------------------------------
#  3MF writer (core spec, base materials = per-triangle colours)
# --------------------------------------------------------------------------
def write_3mf(path, parts):
    """parts: list of (name, object, colours per polygon (hex), (x, y) offset)."""
    pal = []
    for _, _, cols, _ in parts:
        for c in set(cols):
            if c not in pal:
                pal.append(c)
    idx = {c: i for i, c in enumerate(pal)}
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<model unit="millimeter" xml:lang="en-US" '
           'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">',
           '<metadata name="Title">Trimble S6 tripod - print parts</metadata>',
           '<resources>', '<basematerials id="1">']
    out += [f'<base name="#{c}" displaycolor="#{c}FF"/>' for c in pal]
    out.append('</basematerials>')
    build = []
    for k, (name, ob, cols, off) in enumerate(parts, start=2):
        me = ob.data
        me.calc_loop_triangles()
        out.append(f'<object id="{k}" name="{name}" type="model" pid="1" pindex="{idx[cols[0]]}">'
                   '<mesh><vertices>')
        out += [f'<vertex x="{v.co.x:.4f}" y="{v.co.y:.4f}" z="{v.co.z:.4f}"/>' for v in me.vertices]
        out.append('</vertices><triangles>')
        for t in me.loop_triangles:
            a, b, c = t.vertices
            out.append(f'<triangle v1="{a}" v2="{b}" v3="{c}" p1="{idx[cols[t.polygon_index]]}"/>')
        out.append('</triangles></mesh></object>')
        build.append(f'<item objectid="{k}" transform="1 0 0 0 1 0 0 0 1 {off[0]:.3f} {off[1]:.3f} 0"/>')
    out += ['</resources>', '<build>'] + build + ['</build>', '</model>']
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml',
                   '<?xml version="1.0" encoding="UTF-8"?>\n<Types xmlns="http://schemas.openxmlformats.org/'
                   'package/2006/content-types"><Default Extension="rels" ContentType="application/'
                   'vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" '
                   'ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
        z.writestr('_rels/.rels',
                   '<?xml version="1.0" encoding="UTF-8"?>\n<Relationships xmlns="http://schemas.'
                   'openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" '
                   'Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
                   '</Relationships>')
        z.writestr('3D/3dmodel.model', '\n'.join(out))


# --------------------------------------------------------------------------
def main(argv):
    src, out_dir = argv[0], argv[1]
    height = arg(argv, "--height", 200.0)
    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(src))
    for o in list(bpy.data.objects):
        if o.name != "Group#1":
            bpy.data.objects.remove(o, do_unlink=True)
    src_ob = bpy.data.objects["Group#1"]

    # 1. millimetres, axis at the origin
    bm = bmesh.new()
    bm.from_mesh(src_ob.data)
    bm.transform(src_ob.matrix_world)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    k = height / max(v.co.z for v in bm.verts)
    low = sorted(bm.verts, key=lambda v: v.co.z)
    tips = []
    for v in low:
        if all((v.co.xy - t).length > 0.1 for t in tips):
            tips.append(v.co.xy.copy())
        if len(tips) == 3:
            break
    axis = sum(tips, Vector((0, 0))) / 3
    bmesh.ops.translate(bm, vec=(-axis.x, -axis.y, 0), verts=bm.verts)
    bmesh.ops.scale(bm, vec=(k, k, k), verts=bm.verts)
    bm.faces.ensure_lookup_table()
    mats = src_ob.data.materials
    colours = []
    for f in bm.faces:
        c = mats[f.material_index].diffuse_color
        colours.append("%02X%02X%02X" % tuple(int(round(max(0.0, min(1.0, x)) ** (1 / 2.2) * 255))
                                             for x in c[:3]))
    tris = np.array([[v.co[:] for v in f.verts] for f in bm.faces])
    bvh = BVHTree.FromBMesh(bm)
    bm.free()
    split = HEAD_TOP_M * k + 0.05
    print(f"[print] scale x{k:.2f} -> {height:.0f} mm, split at z = {split:.2f} mm", flush=True)

    # ---- leg axes (fitted to the original leg vertices below the hinges) ----
    legs = []
    V = np.unique(tris.reshape(-1, 3), axis=0)
    tip_xy = [np.array([t.x - axis.x, t.y - axis.y]) * k for t in tips]
    for t in tip_xy:
        az = math.atan2(t[1], t[0])
        d = np.abs(np.angle(np.exp(1j * (np.arctan2(V[:, 1], V[:, 0]) - az))))
        P = V[(V[:, 2] < 115.0) & (d < 0.6)]
        c = P.mean(0)
        u = np.linalg.svd(P - c)[2][0]
        u = -u if u[2] > 0 else u                       # down the leg
        C = c + u * ((LEG_CUT_Z - c[2]) / u[2])         # cut point on the axis
        Tg = np.array([-math.sin(az), math.cos(az), 0.0])
        Tg -= u * (Tg @ u)
        Tg /= np.linalg.norm(Tg)
        legs.append(dict(az=az, u=u, C=C, T=Tg, N=np.cross(u, Tg)))

    results = {}
    for name, voxel, zlo, zhi in (("Tripod", 0.25, -1.0, split + 3.0),
                                  ("Instrument", 0.12, split - 3.0, height + 1.0)):
        zt = tris[:, :, 2]
        sel = (zt.max(1) >= zlo) & (zt.min(1) <= zhi)
        part = tris[sel]
        lo = part.reshape(-1, 3).min(0)
        hi = part.reshape(-1, 3).max(0)
        solid, origin = solidify(part, lo, hi, voxel)
        xc = origin[0] + (np.arange(solid.shape[0]) + 0.5) * voxel
        yc = origin[1] + (np.arange(solid.shape[1]) + 0.5) * voxel
        zc = origin[2] + (np.arange(solid.shape[2]) + 0.5) * voxel
        r2 = xc[:, None] ** 2 + yc[None, :] ** 2 < (HOLE_D / 2) ** 2
        rows, cols_ = r2.any(1), r2.any(0)
        if name == "Instrument":
            solid[:, :, zc < split] = False
            zm = (zc >= split) & (zc < split + HOLE_DEPTH)
            solid[np.ix_(rows, cols_, zm)] &= ~r2[np.ix_(rows, cols_)][:, :, None]
            solid, ncomp, dropped = keep_main(solid)
            results["Instrument"] = (solid, origin, voxel, ncomp)
            continue
        solid[:, :, zc >= split] = False
        core = xc[:, None] ** 2 + yc[None, :] ** 2 < 10.5 ** 2   # joins the loose centring screw
        solid[:, :, (zc > HEAD_BOTTOM_Z + 0.3) & (zc < split)] |= core[:, :, None]
        zm = (zc > split - HOLE_DEPTH) & (zc < split)
        solid[np.ix_(rows, cols_, zm)] &= ~r2[np.ix_(rows, cols_)][:, :, None]

        # ---- complete legs (with their hinge blocks) below the head disc ----
        X, Y = np.meshgrid(xc, yc, indexing="ij")
        azg = np.arctan2(Y, X)
        below = zc < HEAD_BOTTOM_Z
        leg_masks = []
        for L in legs:
            sector = np.abs(np.angle(np.exp(1j * (azg - L["az"])))) < math.radians(60)
            m = solid & sector[:, :, None] & below[None, None, :]
            leg_masks.append(m)
        head = solid & ~below[None, None, :]
        del solid
        # ---- clean base, rebuilt as a plain disc (no orange) with a socket per leg;
        #      each leg's top block gets a matching tenon (0.25 mm clearance) ----
        kz = int(np.searchsorted(zc, HEAD_BOTTOM_Z))
        disc = (X ** 2 + Y ** 2) < BASE_R ** 2
        zbase = (zc >= HEAD_BOTTOM_Z) & (zc < split)
        head = np.zeros(head.shape, bool)
        head[:, :, zbase] = disc[:, :, None]
        ztenon = (zc >= HEAD_BOTTOM_Z) & (zc < HEAD_BOTTOM_Z + TENON_H)
        zsock = (zc >= HEAD_BOTTOM_Z) & (zc < HEAD_BOTTOM_Z + TENON_H + 0.3)
        cross = ndimage.generate_binary_structure(2, 1)
        feet_2d = []
        for L, m in zip(legs, leg_masks):
            foot = m[:, :, kz - 1] | m[:, :, kz - 2]
            foot = ndimage.binary_fill_holes(foot)
            feet_2d.append(foot)
            tenon = ndimage.binary_erosion(foot, cross, iterations=1) & disc
            m[:, :, ztenon] |= tenon[:, :, None]
            head[:, :, zsock] &= ~foot[:, :, None]
        hole = (X ** 2 + Y ** 2) < (HOLE_D / 2) ** 2
        head[:, :, (zc > split - HOLE_DEPTH) & (zc < split)] &= ~hole[:, :, None]
        # ---- vertical filament-peg holes through each leg-top / head joint ----
        nholes = []
        kz = int(np.searchsorted(zc, HEAD_BOTTOM_Z))
        edt = ndimage.distance_transform_edt(
            np.any(leg_masks, axis=0)[:, :, max(0, kz - 6):kz])[:, :, -2] * voxel
        for L, m in zip(legs, leg_masks):
            top = m[:, :, kz - 2]
            lab, n = ndimage.label(top)
            count = 0
            for c_ in range(1, n + 1):
                e = np.where(lab == c_, edt, 0)
                bi = np.unravel_index(np.argmax(e), e.shape)
                if not LEG_PEGS or e[bi] < PEG_D / 2 + 0.4:
                    continue
                hole = (X - xc[bi[0]]) ** 2 + (Y - yc[bi[1]]) ** 2 < (PEG_D / 2) ** 2
                zr = (zc > HEAD_BOTTOM_Z - PEG_DEPTH) & (zc < HEAD_BOTTOM_Z + 3.0)
                m[:, :, zr] &= ~hole[:, :, None]
                head[:, :, zr] &= ~hole[:, :, None]
                count += 1
            nholes.append(count)
        print(f"[print] leg joints: filament-pin holes per leg {nholes}", flush=True)
        # base built as exact geometry (not voxels): smooth cylinder + sockets
        results["Head"] = ("OBJ", build_base(feet_2d, xc[0], yc[0], voxel, split), None, 1)
        for i_, m in enumerate(leg_masks, 1):
            m, ncomp, dropped = keep_main(m)
            results[f"Leg{i_}"] = (m, origin, voxel, ncomp)

    from mathutils import Matrix
    meshes = {}
    for name, (solid, origin, voxel, ncomp) in results.items():
        if isinstance(solid, str):
            ob = origin                                   # already an exact mesh
        else:
            ob = to_mesh(solid, origin, voxel, name, sigma=0.85 if name.startswith("Leg") else 0.65)
            decimate(ob, TARGET_TRIS.get(name[:3], 150000))
        n, nm, vol, plo, phi = check(ob)
        if vol < 0:
            ob.data.flip_normals()
            vol = -vol
        cols = []
        for p in ob.data.polygons:
            hit = bvh.find_nearest(p.center)
            c = colours[hit[2]] if hit[2] is not None else "9A9A9A"
            if name == "Head":
                c = BASE_COLOUR                        # plain base, no orange
            cols.append(c)
        print(f"[print] {name}: {ncomp} solid piece(s), {n} triangles, non-manifold edges {nm}, "
              f"volume {vol / 1000:.2f} cm3", flush=True)
        meshes[name] = (ob, cols)

    # ---- print orientation ----
    hob, _ = meshes["Head"]                         # upside-down on the head plate
    hob.data.transform(Matrix.Rotation(math.pi, 4, 'X'))
    for i_, L in enumerate(legs, 1):                # lying flat, best face down
        ob, _ = meshes[f"Leg{i_}"]
        best = None
        for sgn in (1, -1):
            R = Matrix(((*L["u"], 0), (*(sgn * L["T"]), 0), (*(sgn * L["N"]), 0), (0, 0, 0, 1)))
            zs = [(R @ v.co).z for v in ob.data.vertices]
            z0 = min(zs)
            area = sum(p.area for p in ob.data.polygons
                       if all(zs[vi] < z0 + 0.3 for vi in p.vertices))
            if best is None or area > best[0]:
                best = (area, R)
        ob.data.transform(best[1])
    for name, (ob, _) in meshes.items():
        vs = ob.data.vertices
        lo = [min(v.co[a] for v in vs) for a in range(3)]
        ob.data.transform(Matrix.Translation((-lo[0], -lo[1], -lo[2])))   # min corner at origin
    pin = pin_mesh()
    meshes["Pin"] = (pin, ["B4B4B4"] * len(pin.data.polygons))

    def size(name):
        vs = meshes[name][0].data.vertices
        return [max(v.co[a] for v in vs) for a in range(2)]

    # simple plate layout (mm): legs side by side, head / instrument / pin in a row above
    place, y = {}, 0.0
    for name in ("Leg1", "Leg2", "Leg3"):
        place[name] = (0.0, y)
        y += size(name)[1] + 6
    x = 0.0
    for name in ("Head", "Instrument", "Pin"):
        place[name] = (x, y + 4)
        x += size(name)[0] + 8

    os.makedirs(out_dir, exist_ok=True)
    item = lambda n, off=(0, 0): (n, meshes[n][0], meshes[n][1], off)
    write_3mf(os.path.join(out_dir, "S6_All_Parts.3mf"), [item(n, place[n]) for n in place])
    write_3mf(os.path.join(out_dir, "S6_Head.3mf"), [item("Head")])
    for n in ("Leg1", "Leg2", "Leg3"):
        write_3mf(os.path.join(out_dir, f"S6_{n}.3mf"), [item(n)])
    write_3mf(os.path.join(out_dir, "S6_Legs_x3.3mf"), [item(n, place[n]) for n in ("Leg1", "Leg2", "Leg3")])
    write_3mf(os.path.join(out_dir, "S6_Instrument.3mf"), [item("Instrument"), item("Pin", (size("Instrument")[0] + 8, 0))])
    for n, (x_, y_) in place.items():
        print(f"[print] plate {n:10s} at ({x_:6.1f}, {y_:6.1f})  footprint "
              f"{size(n)[0]:.1f} x {size(n)[1]:.1f} mm, height "
              f"{max(v.co.z for v in meshes[n][0].data.vertices):.1f} mm", flush=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(os.path.join(out_dir, "S6_print_parts.blend")))
    print("[print] wrote", out_dir, flush=True)


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    main(args)
