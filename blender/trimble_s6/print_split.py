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


def keep_main(solid, min_frac=0.002):
    lab, n = ndimage.label(solid)
    if n <= 1:
        return solid, n, 0
    sizes = ndimage.sum(solid, lab, range(1, n + 1))
    keep = np.where(sizes >= sizes.max() * min_frac)[0] + 1
    return np.isin(lab, keep), n, n - len(keep)


def to_mesh(solid, origin, voxel, name):
    f = ndimage.gaussian_filter(np.pad(solid, 1).astype(np.float32), 0.65)
    verts, faces, _, _ = marching_cubes(f, 0.5, spacing=(voxel,) * 3)
    verts += origin - voxel
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

    results = {}
    for name, voxel, zlo, zhi, target in (("Tripod", 0.25, -1.0, split + 3.0, 350000),
                                          ("Instrument", 0.12, split - 3.0, height + 1.0, 250000)):
        zt = tris[:, :, 2]
        sel = (zt.max(1) >= zlo) & (zt.min(1) <= zhi)
        part = tris[sel]
        lo = part.reshape(-1, 3).min(0)
        hi = part.reshape(-1, 3).max(0)
        solid, origin = solidify(part, lo, hi, voxel)
        zc = origin[2] + (np.arange(solid.shape[2]) + 0.5) * voxel
        if name == "Tripod":
            solid[:, :, zc >= split] = False
        else:
            solid[:, :, zc < split] = False
        xc = origin[0] + (np.arange(solid.shape[0]) + 0.5) * voxel
        yc = origin[1] + (np.arange(solid.shape[1]) + 0.5) * voxel
        if name == "Tripod":
            # solid core under the head plate: joins the loose centring screw to the head
            core = xc[:, None] ** 2 + yc[None, :] ** 2 < 10.5 ** 2
            solid[:, :, (zc > split - 10.0) & (zc < split)] |= core[:, :, None]
        # locating hole on the axis, 4 mm into the cut face
        r2 = xc[:, None] ** 2 + yc[None, :] ** 2 < (HOLE_D / 2) ** 2
        zm = (zc > split - HOLE_DEPTH) & (zc < split) if name == "Tripod" else \
             (zc >= split) & (zc < split + HOLE_DEPTH)
        solid[np.ix_(r2.any(1), r2.any(0), zm)] &= ~r2[np.ix_(r2.any(1), r2.any(0))][:, :, None]
        solid, ncomp, dropped = keep_main(solid)
        ob = to_mesh(solid, origin, voxel, name)
        del solid
        decimate(ob, target)
        n, nm, vol, plo, phi = check(ob)
        if vol < 0:                                   # make normals point outwards
            ob.data.flip_normals()
            vol = -vol
        print(f"[print] {name}: {ncomp} solid pieces ({dropped} specks removed), {n} triangles, "
              f"non-manifold edges {nm}, volume {vol / 1000:.1f} cm3, size "
              f"{phi[0]-plo[0]:.1f} x {phi[1]-plo[1]:.1f} x {phi[2]-plo[2]:.1f} mm", flush=True)
        cols = []
        for p in ob.data.polygons:
            hit = bvh.find_nearest(p.center)
            cols.append(colours[hit[2]] if hit[2] is not None else "9A9A9A")
        results[name] = (ob, cols)

    # print orientation: tripod upside-down on its head plate, instrument on its base
    from mathutils import Matrix
    tob, tcols = results["Tripod"]
    tob.data.transform(Matrix.Translation((0, 0, split)) @ Matrix.Rotation(math.pi, 4, 'X')
                       @ Matrix.Translation((0, 0, -split)))
    tob.data.transform(Matrix.Translation((0, 0, -split)))
    tob.data.transform(Matrix.Translation((0, 0, -min(v.co.z for v in tob.data.vertices))))
    iob, icols = results["Instrument"]
    iob.data.transform(Matrix.Translation((0, 0, -min(v.co.z for v in iob.data.vertices))))
    pin = pin_mesh()
    pcols = ["B4B4B4"] * len(pin.data.polygons)

    os.makedirs(out_dir, exist_ok=True)
    write_3mf(os.path.join(out_dir, "S6_Tripod.3mf"), [("Tripod", tob, tcols, (0, 0))])
    write_3mf(os.path.join(out_dir, "S6_Instrument.3mf"),
              [("Instrument", iob, icols, (0, 0)), ("Pin", pin, pcols, (25, 0))])
    write_3mf(os.path.join(out_dir, "S6_All_Parts.3mf"),
              [("Tripod", tob, tcols, (0, 0)), ("Instrument", iob, icols, (95, 0)),
               ("Pin", pin, pcols, (95, 30))])
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(os.path.join(out_dir, "S6_print_parts.blend")))
    print("[print] wrote", out_dir, flush=True)


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    main(args)
