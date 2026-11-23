"""The five role emblems (Roamer, Jungler, Mid, Exp, Gold) as 2D polygons in mm, centred on (0, 0).
Each function returns a list of (polygon_points, colour) where colour is 'y' (yellow) or 'w' (white).
Shapes traced from the reference sheet; size chosen to sit inside the octagon frame of the stand."""
import math
from shapely.geometry import Polygon, Point, box, MultiPolygon
from shapely.ops import unary_union
from shapely import affinity
from lib import ccw

SIZE = 42.0   # emblem width in mm (square logos)


def _pieces(geom, colour, scale, min_area=0.004):
    out = []
    geoms = geom.geoms if isinstance(geom, MultiPolygon) else [geom]
    for g in geoms:
        if g.is_empty or g.area < min_area:
            continue
        g = g.simplify(0.002)
        pts = [(x * scale, y * scale) for x, y in list(g.exterior.coords)[:-1]]
        out.append((ccw(pts), colour))
    return out


def _rot180(g):
    return affinity.rotate(g, 180, origin=(0, 0))


def roamer(size=SIZE):
    sq = box(-0.5, -0.5, 0.5, 0.5)
    cut_a = Polygon([(-0.3125, 0.3304), (0.1607, 0.3304), (-0.6, -0.4197), (-0.6, -0.2786),
                     (-0.1429, 0.1786), (-0.3125, 0.1786)])
    z = sq.difference(cut_a).difference(_rot180(cut_a))
    return _pieces(z, 'y', size)


def jungler(size=SIZE):
    sq = box(-0.5, -0.5, 0.5, 0.5)
    l1 = box(-0.5, 0.36, 0.20, 0.5).union(box(-0.5, -0.19, -0.36, 0.5))
    disc = Point(0.5, 0.5).buffer(0.26, 48).intersection(sq)
    whites = unary_union([l1, _rot180(l1), disc, _rot180(disc)])
    tri = Polygon([(-0.29, 0.29), (0.175, 0.29), (-0.29, -0.175)])
    yellows = unary_union([tri, _rot180(tri)])
    return _pieces(whites, 'w', size) + _pieces(yellows, 'y', size)


def mid(size=SIZE):
    sq = box(-0.5, -0.5, 0.5, 0.5)
    band = Polygon([(-0.366, -0.489), (0.489, 0.366), (0.366, 0.489), (-0.489, -0.366)])
    keep_out = band.buffer(0.06, join_style='mitre')
    frame = sq.difference(box(-0.35, -0.35, 0.35, 0.35)).difference(keep_out)
    inner = box(-0.28, -0.28, 0.28, 0.28).difference(keep_out)
    return _pieces(frame, 'w', size, min_area=0.01) + _pieces(inner, 'w', size) + _pieces(band, 'y', size)


def exp(size=SIZE):
    # traced in image pixels (y down), then normalised
    cx, cy, s = 352.0, 300.0, 595.0

    def n(pts):
        return [((x - cx) / s, (cy - y) / s) for x, y in pts]

    sigma = Polygon(n([(55, 10), (640, 10), (580, 95), (275, 95), (360, 245), (490, 245), (490, 335),
                       (360, 335), (275, 500), (580, 500), (645, 590), (55, 590), (235, 300)]))
    wedge = Polygon(n([(55, 10), (235, 300), (55, 590)]))
    left = wedge.difference(sigma.buffer(45 / s, join_style='mitre'))
    bracket = Polygon(n([(570, 160), (650, 115), (650, 470), (570, 425)]))
    return _pieces(sigma, 'y', size) + _pieces(left, 'y', size) + _pieces(bracket, 'w', size)


def gold(scale=0.95):
    body = [(-23, -22), (17, -22), (18.5, -20.5), (18.5, -14.2), (-7.5, 14.2), (18.5, 14.2), (23, 18.7),
            (23, 22), (-17, 22), (-18.5, 20.5), (-18.5, 14.2), (7.5, -14.2), (-18.5, -14.2), (-23, -18.7)]
    stub = [(2.0, 21.5), (8.3, 21.5), (8.3, 28.7), (2.0, 28.7)]
    side = [(-23.4, 3.0), (-17.0, 0.4), (-17.0, -8.9), (-23.4, -10.2)]   # white bracket pieces
    out = []
    for p, c in ((body, 'y'), (stub, 'y'), ([(-x, -y) for x, y in stub], 'y'),
                 (side, 'w'), ([(-x, -y) for x, y in side], 'w')):
        out.append((ccw([(x * scale, y * scale) for x, y in p]), c))
    return out


ROLES = {
    'Roamer': roamer,
    'Jungler': jungler,
    'Mid_Laner': mid,
    'Exp_Laner': exp,
    'Gold_Laner': gold,
}


if __name__ == '__main__':
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axs = plt.subplots(1, 5, figsize=(15, 3.4))
    for ax, (k, f) in zip(axs, ROLES.items()):
        ax.set_facecolor('#2a2a2a')
        oct_r = 31.5 / math.cos(math.pi / 8)
        o = [(oct_r * math.cos(math.pi / 8 + i * math.pi / 4), oct_r * math.sin(math.pi / 8 + i * math.pi / 4))
             for i in range(9)]
        ax.plot([p[0] for p in o], [p[1] for p in o], color='#f5c400', lw=1)
        for pts, c in f():
            xs = [p[0] for p in pts] + [pts[0][0]]
            ys = [p[1] for p in pts] + [pts[0][1]]
            ax.fill(xs, ys, color='#f5c400' if c == 'y' else 'white')
        ax.set_aspect('equal')
        ax.set_xlim(-36, 36)
        ax.set_ylim(-36, 36)
        ax.set_title(k)
        ax.set_xticks([])
        ax.set_yticks([])
    plt.tight_layout()
    plt.savefig('../ref/logos_check.png', dpi=110)
    print('ok')
