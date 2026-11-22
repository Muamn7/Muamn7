"""Printability + assembly checks."""
import sys, math
import numpy as np
from lib import to_arrays, apply, bevel_hull, union
import stand1, stand2


def overhangs(m, limit_deg=45.0, bed_tol=0.35):
    v, f = to_arrays(m)
    tri = v[f]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    area = np.linalg.norm(n, axis=1) / 2
    nz = n[:, 2] / np.maximum(np.linalg.norm(n, axis=1), 1e-12)
    cz = tri[:, :, 2].mean(axis=1)
    thr = -math.cos(math.radians(limit_deg))  # facing down more than limit from vertical
    bad = (nz < thr - 1e-3) & (cz > bed_tol)
    return area[bad].sum(), tri[bad]


def phone(rest, w=78.0, h=165.0, t=9.0, y0=20.0):
    pts = [(x, y, z) for x in (-w / 2 + 3, w / 2 - 3) for y in (y0 + 3, y0 + h - 3) for z in (rest + 3, rest + t - 3)]
    return bevel_hull(pts, 3.0)


ok = True
for mod in (stand1, stand2):
    d = mod.build()
    print('==', d['name'])
    for pname, p in d['parts'].items():
        both = p['black'] + p['accent']
        a, bad = overhangs(both)
        bb = both.bounding_box()
        print('  %-7s size %.0f x %.0f x %.0f mm | overhang area >45deg: %.1f mm2' % (
            pname, bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2], a))
        if a > 10:
            ok = False
            zs = bad[:, :, 2].mean(axis=1)
            cs = bad.mean(axis=1)
            for k in np.argsort(-zs)[:6]:
                print('      at', np.round(cs[k], 1))
        print('          fits 220x220 bed:', (bb[3] - bb[0]) <= 215 and (bb[4] - bb[1]) <= 215)
    base = d['parts']['Base']['black'] + d['parts']['Base']['accent']
    for pname, p in d['parts'].items():
        if p['assembly'] is None:
            continue
        placed = apply(p['black'] + p['accent'], p['assembly'])
        inter = (placed ^ base).volume()
        print('  %s vs Base overlap volume: %.3f mm3' % (pname, inter))
        if inter > 1.0:
            ok = False
    # phone fit: 78 x 165 x 9 mm phone and a thick 13 mm (with case) variant
    rest = mod.REST if hasattr(mod, 'REST') else mod.F + 2.2
    plate = d['parts']['Plate']['black'] + d['parts']['Plate']['accent']
    for t in (9.0, 13.0):
        ph = phone(rest + 0.05, t=t)
        inter = (ph ^ plate).volume()
        print('  phone %.0fmm thick vs plate overlap: %.3f mm3' % (t, inter))

def edge_check(m):
    v, f = to_arrays(m)
    v32 = v.astype(np.float32).astype(np.float64)
    q = np.round(v32 * 1e4).astype(np.int64)
    _, inv = np.unique(q, axis=0, return_inverse=True)
    ff = inv.reshape(-1)[f]
    e = np.sort(np.concatenate([ff[:, [0, 1]], ff[:, [1, 2]], ff[:, [2, 0]]]), axis=1)
    _, cnt = np.unique(e, axis=0, return_counts=True)
    return int((cnt != 2).sum())

for mod in (stand1, stand2):
    d = mod.build()
    for pname, p in d['parts'].items():
        for c in ('black', 'accent'):
            if p[c].is_empty():
                continue
            k = edge_check(p[c])
            if k:
                ok = False
            print('  %s %s %s non-manifold edges after STL export: %d' % (d['name'], pname, c, k))
print('ALL OK' if ok else 'ISSUES FOUND')
