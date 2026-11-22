"""Geometry helpers: chamfered prisms, lofts, hulls, text, transforms (manifold3d based)."""
import math
import numpy as np
from manifold3d import Manifold, CrossSection, Mesh, triangulate, FillRule, JoinType
from shapely.geometry import Polygon, LineString, MultiPolygon
from shapely.geometry.polygon import orient

EMPTY = Manifold()


# ---------------------------------------------------------------- 2D helpers
def ccw(pts):
    p = Polygon(pts)
    p = orient(p, 1.0)
    return [tuple(c) for c in list(p.exterior.coords)[:-1]]


def mirror_x(pts):
    return ccw([(-x, y) for x, y in pts])


def rot180(pts):
    return ccw([(-x, -y) for x, y in pts])


def translate2(pts, dx, dy):
    return [(x + dx, y + dy) for x, y in pts]


def scale2(pts, s, sy=None):
    sy = s if sy is None else sy
    return [(x * s, y * sy) for x, y in pts]


def inset(pts, c):
    """Mitre offset of a CCW simple polygon. c>0 shrinks, c<0 grows. Keeps vertex correspondence.
    Returns None when the result is not valid (an edge would flip / polygon self-intersects)."""
    if abs(c) < 1e-9:
        return list(pts)
    P = np.asarray(pts, float)
    n = len(P)
    out = []
    for i in range(n):
        a, b, d = P[i - 1], P[i], P[(i + 1) % n]
        e1 = b - a
        e2 = d - b
        e1 /= np.linalg.norm(e1)
        e2 /= np.linalg.norm(e2)
        n1 = np.array([-e1[1], e1[0]])
        n2 = np.array([-e2[1], e2[0]])
        den = 1.0 + float(n1 @ n2)
        if den < 0.15:
            return None
        out.append(b + c * (n1 + n2) / den)
    Q = np.array(out)
    for i in range(n):
        eo = P[(i + 1) % n] - P[i]
        eq = Q[(i + 1) % n] - Q[i]
        if float(eo @ eq) <= 1e-6:
            return None
    poly = Polygon(Q)
    if not poly.is_valid or poly.area <= 0:
        return None
    return [tuple(q) for q in Q]


def poly_line(points, width, join='mitre'):
    """Flat-ended strip polygon along a polyline."""
    ls = LineString(points)
    g = ls.buffer(width / 2.0, cap_style='flat', join_style=join, mitre_limit=5.0)
    g = g.simplify(0.01)
    return ccw(list(g.exterior.coords)[:-1])


def regular_poly(n, r_in, cx=0.0, cy=0.0, rot=None):
    """Regular n-gon with inradius r_in. Default rotation gives a flat top edge."""
    R = r_in / math.cos(math.pi / n)
    if rot is None:
        rot = math.pi / n + math.pi / 2  # flat top
    return [(cx + R * math.cos(rot + 2 * math.pi * k / n), cy + R * math.sin(rot + 2 * math.pi * k / n))
            for k in range(n)]


def octagon(across, cx=0.0, cy=0.0):
    return regular_poly(8, across / 2.0, cx, cy, rot=math.pi / 8)


def long_hex(cx, cy, hw, hh, pd):
    return ccw([(cx - hw, cy), (cx - hw + pd, cy - hh), (cx + hw - pd, cy - hh), (cx + hw, cy),
                (cx + hw - pd, cy + hh), (cx - hw + pd, cy + hh)])


def rect(x0, y0, x1, y1, ch=0.0):
    if ch <= 0:
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return [(x0 + ch, y0), (x1 - ch, y0), (x1, y0 + ch), (x1, y1 - ch), (x1 - ch, y1), (x0 + ch, y1),
            (x0, y1 - ch), (x0, y0 + ch)]


def offset_poly(pts, d):
    """Shapely mitre offset (no correspondence guarantee). d>0 grows."""
    g = Polygon(pts).buffer(d, join_style='mitre', mitre_limit=4.0)
    if isinstance(g, MultiPolygon):
        g = max(g.geoms, key=lambda q: q.area)
    return ccw(list(g.exterior.coords)[:-1])


# ---------------------------------------------------------------- 3D builders
def _mesh_from(verts, tris):
    m = Manifold(Mesh(vert_properties=np.asarray(verts, np.float32), tri_verts=np.asarray(tris, np.uint32)))
    if m.status().name != 'NoError':
        raise RuntimeError('bad mesh: %s' % m.status())
    return m


def loft(rings):
    """rings: list of (pts CCW Nx2 with same N, z) ascending z. Returns closed solid."""
    n = len(rings[0][0])
    verts = []
    for pts, z in rings:
        for x, y in pts:
            verts.append((x, y, z))
    tris = []
    cap = triangulate([np.asarray(rings[0][0], float)])
    for t in cap:  # bottom faces down
        tris.append((t[0], t[2], t[1]))
    top_off = (len(rings) - 1) * n
    capt = triangulate([np.asarray(rings[-1][0], float)])
    for t in capt:
        tris.append((t[0] + top_off, t[1] + top_off, t[2] + top_off))
    for r in range(len(rings) - 1):
        a0 = r * n
        b0 = (r + 1) * n
        for j in range(n):
            j1 = (j + 1) % n
            tris.append((a0 + j, a0 + j1, b0 + j1))
            tris.append((a0 + j, b0 + j1, b0 + j))
    return _mesh_from(verts, tris)


def cprism(pts, z0, z1, ct=0.0, cb=0.0):
    """Prism of polygon pts between z0 and z1 with 45deg chamfer ct on top edge, cb on bottom edge.
    Negative ct flares the top outward (useful for cutters)."""
    pts = ccw(pts)
    h = z1 - z0
    ct = min(ct, h * 0.45) if ct > 0 else ct
    cb = min(cb, h * 0.45)
    top = inset(pts, ct) if ct else pts
    bot = inset(pts, cb) if cb else pts
    if top is None or bot is None:
        # fall back to a plain extrusion
        cs = CrossSection([np.asarray(pts, float)], FillRule.NonZero)
        return Manifold.extrude(cs, h).translate((0, 0, z0))
    rings = []
    if cb > 0:
        rings.append((bot, z0))
        rings.append((pts, z0 + cb))
    else:
        rings.append((pts, z0))
    if ct > 0:
        rings.append((pts, z1 - ct))
        rings.append((top, z1))
    elif ct < 0:
        rings.append((pts, z1 + ct))  # ct negative -> lower
        rings.append((top, z1))
    else:
        rings.append((pts, z1))
    return loft(rings)


def cut_prism(pts, z0, z1, flare=0.0):
    """Cutter with an optional flared (countersunk) top so the cut gets a chamfered rim."""
    pts = ccw(pts)
    if flare <= 0:
        return cprism(pts, z0, z1)
    big = inset(pts, -flare)
    if big is None:
        return cprism(pts, z0, z1)
    return loft([(pts, z0), (pts, z1 - flare - 1e-3), (big, z1 + 1e-3)])


def ring(outer, inner, z0, z1, ct=0.0):
    body = cprism(outer, z0, z1, ct)
    hole = cut_prism(inner, z0 - 0.05, z1 + 0.05, flare=ct)
    return body - hole


def cs_prism(cs, z0, z1):
    return Manifold.extrude(cs, z1 - z0).translate((0, 0, z0))


def hull_pts(pts):
    return Manifold.hull_points(np.asarray(pts, float))


def bevel_hull(pts, r=0.8):
    """Convex hull with every edge chamfered (Minkowski with an octahedron)."""
    P = np.asarray(pts, float)
    offs = np.array([[r, 0, 0], [-r, 0, 0], [0, r, 0], [0, -r, 0], [0, 0, r], [0, 0, -r]])
    allp = (P[:, None, :] + offs[None, :, :]).reshape(-1, 3)
    return Manifold.hull_points(allp)


def union(parts):
    parts = [p for p in parts if p is not None and not p.is_empty()]
    if not parts:
        return Manifold()
    return Manifold.batch_boolean(parts, OpType_add())


def OpType_add():
    from manifold3d import OpType
    return OpType.Add


def axis_prism_x(profile_yz, x0, x1, ce=0.0):
    """Prism along X of a (y,z) profile, with chamfer ce on both X ends."""
    m = cprism(profile_yz, x0, x1, ct=ce, cb=ce)  # built along 'z' in (y,z,x) frame
    # map (a,b,c) -> (x=c, y=a, z=b): cyclic permutation, det=+1
    M = np.array([[0, 0, 1, 0], [1, 0, 0, 0], [0, 1, 0, 0]], float)
    return m.transform(M)


def axis_prism_y(profile_zx, y0, y1, ce=0.0):
    """Prism along Y of a (z,x) profile (cyclic frame)."""
    m = cprism(profile_zx, y0, y1, ct=ce, cb=ce)
    M = np.array([[0, 1, 0, 0], [0, 0, 1, 0], [1, 0, 0, 0]], float)
    return m.transform(M)


def rot_x_matrix(theta_deg, origin):
    t = math.radians(theta_deg)
    c, s = math.cos(t), math.sin(t)
    return np.array([[1, 0, 0, origin[0]], [0, c, -s, origin[1]], [0, s, c, origin[2]]], float)


def apply(m, M):
    return m.transform(np.asarray(M, float))


def face_strip(R0, R1, F0, F1, width, center_ref, out=0.7, inn=0.7, t0=0.0, shrink=0.0, with_normal=False):
    """Thin raised strip lying on the plane through ridge R0-R1 and points F0,F1, along the ridge.
    t0 = start distance from the ridge (mm, along face), width in mm. shrink trims both ends (mm)."""
    R0, R1, F0, F1 = [np.asarray(v, float) for v in (R0, R1, F0, F1)]
    ridge = R1 - R0
    L = np.linalg.norm(ridge)
    dr = ridge / L
    R0s = R0 + dr * shrink
    R1s = R1 - dr * shrink
    F0s = F0 + dr * shrink
    F1s = F1 - dr * shrink
    nrm = np.cross(R1 - R0, F0 - R0)
    nrm /= np.linalg.norm(nrm)
    mid = (R0 + R1 + F0 + F1) / 4
    if np.dot(nrm, mid - np.asarray(center_ref, float)) < 0:
        nrm = -nrm
    pts = []
    for R, F in ((R0s, F0s), (R1s, F1s)):
        d = F - R
        dl = np.linalg.norm(d)
        for t in (t0, t0 + width):
            p = R + d * (t / dl)
            pts.append(p + nrm * out)
            pts.append(p - nrm * inn)
    if with_normal:
        return hull_pts(pts), nrm, dr
    return hull_pts(pts)


def rot_to_z(n):
    """3x3 rotation taking unit vector n onto +Z."""
    a = np.asarray(n, float) / np.linalg.norm(n)
    b = np.array([0.0, 0.0, 1.0])
    v = np.cross(a, b)
    s = np.linalg.norm(v)
    c = float(a @ b)
    if s < 1e-9:
        return np.eye(3) if c > 0 else np.diag([1.0, -1.0, -1.0])
    K = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + K + K @ K * ((1 - c) / (s * s))


def lay_flat(pieces, row_w=190.0, gap=6.0):
    """pieces: list of (manifold, normal, long_dir). Rotates each so normal -> +Z, long axis -> X,
    and arranges them in rows on the bed. Returns one manifold."""
    out = []
    x = y = 0.0
    row_h = 0.0
    for m, n, d in pieces:
        R = rot_to_z(n)
        d2 = R @ np.asarray(d, float)
        phi = -math.atan2(d2[1], d2[0])
        Rz = np.array([[math.cos(phi), -math.sin(phi), 0], [math.sin(phi), math.cos(phi), 0], [0, 0, 1]])
        RR = Rz @ R
        M = np.zeros((3, 4))
        M[:, :3] = RR
        q = m.transform(M)
        bb = q.bounding_box()
        w, h = bb[3] - bb[0], bb[4] - bb[1]
        if x + w > row_w and x > 0:
            x = 0.0
            y += row_h + gap
            row_h = 0.0
        out.append(q.translate((x - bb[0], y - bb[1], -bb[2])))
        x += w + gap
        row_h = max(row_h, h)
    return union(out)


# ---------------------------------------------------------------- text
class _FlatPen:
    pass


def text_polys(text, font_path, cap_height, tracking=0.0, steps=6):
    """Return list of contours (np arrays) for text, baseline at y=0, starting x=0, plus total width."""
    from fontTools.ttLib import TTFont
    from fontTools.pens.basePen import BasePen

    font = TTFont(font_path)
    gs = font.getGlyphSet()
    cmap = font.getBestCmap()
    upm = font['head'].unitsPerEm
    capu = getattr(font['OS/2'], 'sCapHeight', 0) or 0.72 * upm
    s = cap_height / capu

    class Pen(BasePen):
        def __init__(self, glyphSet):
            super().__init__(glyphSet)
            self.contours = []
            self.cur = []

        def _moveTo(self, p):
            self.cur = [p]

        def _lineTo(self, p):
            self.cur.append(p)

        def _curveToOne(self, p1, p2, p3):
            p0 = self.cur[-1]
            for i in range(1, steps + 1):
                t = i / steps
                mt = 1 - t
                x = mt ** 3 * p0[0] + 3 * mt * mt * t * p1[0] + 3 * mt * t * t * p2[0] + t ** 3 * p3[0]
                y = mt ** 3 * p0[1] + 3 * mt * mt * t * p1[1] + 3 * mt * t * t * p2[1] + t ** 3 * p3[1]
                self.cur.append((x, y))

        def _qCurveToOne(self, p1, p2):
            p0 = self.cur[-1]
            for i in range(1, steps + 1):
                t = i / steps
                mt = 1 - t
                x = mt * mt * p0[0] + 2 * mt * t * p1[0] + t * t * p2[0]
                y = mt * mt * p0[1] + 2 * mt * t * p1[1] + t * t * p2[1]
                self.cur.append((x, y))

        def _closePath(self):
            c = self.cur
            if len(c) > 2:
                if abs(c[0][0] - c[-1][0]) < 1e-6 and abs(c[0][1] - c[-1][1]) < 1e-6:
                    c = c[:-1]
                self.contours.append(c)
            self.cur = []

        _endPath = _closePath

    contours = []
    x = 0.0
    for i, ch in enumerate(text):
        if ch == ' ':
            name = cmap[ord(' ')]
            x += font['hmtx'][name][0] * s + tracking
            continue
        name = cmap[ord(ch)]
        pen = Pen(gs)
        gs[name].draw(pen)
        for c in pen.contours:
            arr = np.array([(px * s + x, py * s) for px, py in c], float)
            # drop consecutive duplicates
            keep = [0]
            for k in range(1, len(arr)):
                if np.linalg.norm(arr[k] - arr[keep[-1]]) > 1e-4:
                    keep.append(k)
            arr = arr[keep]
            if len(arr) >= 3:
                contours.append(arr)
        x += font['hmtx'][name][0] * s + (tracking if i < len(text) - 1 else 0)
    return contours, x


def text_cs(text, font_path, cap_height, tracking=0.0):
    cont, w = text_polys(text, font_path, cap_height, tracking)
    cs = CrossSection(cont, FillRule.NonZero)
    b = cs.bounds()  # (xmin, ymin, xmax, ymax)
    return cs, b


# ---------------------------------------------------------------- export
def to_arrays(m):
    mesh = m.to_mesh()
    v = np.asarray(mesh.vert_properties)[:, :3].astype(np.float64)
    f = np.asarray(mesh.tri_verts).astype(np.int64)
    return v, f


def write_stl(path, m, name='part'):
    v, f = to_arrays(m)
    tri = v[f]
    nrm = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    ln = np.linalg.norm(nrm, axis=1, keepdims=True)
    ln[ln == 0] = 1
    nrm = nrm / ln
    data = np.zeros(len(f), dtype=[('n', '<f4', 3), ('v', '<f4', (3, 3)), ('a', '<u2')])
    data['n'] = nrm
    data['v'] = tri
    with open(path, 'wb') as fh:
        hdr = (name.encode('ascii', 'ignore') + b' ' * 80)[:80]
        fh.write(hdr)
        fh.write(np.uint32(len(f)).tobytes())
        fh.write(data.tobytes())
