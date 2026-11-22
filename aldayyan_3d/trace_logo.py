"""Trace the red Al-Dayyan logo from the image into clean 2D polygons (mm) + SVG.

Method
  1. the red channel, upscaled 4x with cubic interpolation -> sub-pixel iso-contour
     (smooth outlines while keeping the pointed calligraphy tips).
  2. tiny morphological closing fills the hairline shading slits inside strokes.
  3. corner-preserving smoothing: curves are smoothed, sharp tips/corners are left untouched.
  4. the outer ring and the two diamond dots are rebuilt as exact geometry.
Usage: python3 trace_logo.py <image> <out_dir>
"""
import sys, json, cv2, numpy as np
from shapely.geometry import Polygon, Point, MultiPolygon, LinearRing
from shapely.ops import unary_union
from shapely import affinity

IMG, OUT = sys.argv[1], sys.argv[2]

DISC_D = 60.0            # mm, black disc diameter
MARGIN = 1.0             # mm, black margin outside the red ring
CX, CY = 621, 603        # ring centre (image px)
R_IN, R_OUT = 542, 566   # ring radii (image px)
SCALE = (DISC_D / 2 - MARGIN) / R_OUT   # px -> mm

UP = 4                   # supersampling factor
RED_LEVEL = 50           # iso level on the red channel
CLOSE_PX = 4.0           # closing radius (image px) -> fills slits < ~0.4 mm (unprintable anyway)
SMOOTH_MM = 0.22         # smoothing on curves
STEP_MM = 0.025          # outline resampling step

# two diamond dots under the letter (image px corners: top, left/right, bottom ...)
DIAMONDS = [
    [(550, 856), (513, 900), (553, 938), (586, 894)],   # left diamond
    [(614, 852), (578, 892), (616, 935), (654, 891)],   # right diamond (overlaps left a little)
]

im = cv2.imread(IMG).astype(np.float32)
red = im[:, :, 2].copy()   # red channel: strokes + white highlights are bright, background/shading dark
yy, xx = np.indices(red.shape)
red[np.hypot(xx - CX, yy - CY) > 532] = 0              # ring rebuilt geometrically
dmask = np.zeros(red.shape, np.uint8)                    # diamonds rebuilt geometrically
for d in DIAMONDS:
    cv2.fillPoly(dmask, [np.array(d, np.int32)], 255)
dmask = cv2.dilate(dmask, np.ones((7, 7), np.uint8))
red[dmask > 0] = 0

big = cv2.resize(red, None, fx=UP, fy=UP, interpolation=cv2.INTER_CUBIC)
big = cv2.GaussianBlur(big, (0, 0), 1.0)
m = (big > RED_LEVEL).astype(np.uint8) * 255
r = int(round(CLOSE_PX * UP))
m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)))

cs, hier = cv2.findContours(m, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
hier = hier[0]


def to_mm(c):
    p = c[:, 0].astype(float) / UP + 0.5 / UP
    return np.c_[(p[:, 0] - CX) * SCALE, -(p[:, 1] - CY) * SCALE]


def smooth_ring(pts, keep_corners=True, smooth_mm=SMOOTH_MM):
    """Corner-preserving smoothing of a closed outline (mm)."""
    lr = LinearRing(pts)
    n = max(int(lr.length / STEP_MM), 24)
    P = np.array([lr.interpolate(i * lr.length / n).coords[0] for i in range(n)])
    k = max(int(0.2 / STEP_MM), 2)
    a, b = np.roll(P, k, 0) - P, np.roll(P, -k, 0) - P
    cosang = (a * b).sum(1) / (np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1) + 1e-12)
    ang = np.degrees(np.arccos(np.clip(cosang, -1, 1)))         # 180 = straight, small = sharp tip
    s = (np.clip((ang - 110) / (165 - 110), 0, 1) if keep_corners else np.ones(n)) * smooth_mm / STEP_MM
    # keep the low sigma around corners over a neighbourhood
    W = int(3 * smooth_mm / STEP_MM)
    smin = s.copy()
    for j in range(1, W // 2 + 1):
        smin = np.minimum(smin, np.minimum(np.roll(s, j), np.roll(s, -j)))
    s = np.maximum(smin, 0.3)
    acc, wsum = np.zeros_like(P), np.zeros(n)
    for j in range(-W, W + 1):
        w = np.exp(-(j * j) / (2 * s * s))
        acc += w[:, None] * np.roll(P, -j, 0)
        wsum += w
    return acc / wsum[:, None]


polys = []
for i, c in enumerate(cs):
    if hier[i][3] != -1 or len(c) < 12:
        continue
    holes, j = [], hier[i][2]
    while j != -1:
        if cv2.contourArea(cs[j]) > 40 * UP * UP:
            holes.append(smooth_ring(to_mm(cs[j])))
        j = hier[j][0]
    p = Polygon(smooth_ring(to_mm(c)), holes).buffer(0)
    far = np.hypot(p.centroid.x, p.centroid.y) > 460 * SCALE
    if p.area > 0.4 and not far:        # drop specks and ring-glow scratches
        polys.append(p)

# local cleanup where overlapping strokes leave small notches: (x_mm, y_mm, radius_mm)
LOCAL_CLEAN = [(14.0, -15.4, 2.2), (-0.25, 18.25, 0.8), (8.5, -10.75, 0.8)]
letters = unary_union(polys)
for x, y, rad in LOCAL_CLEAN:
    c = Point(x, y).buffer(rad, 64)
    fixed = letters.buffer(0.35, 64).buffer(-0.35, 64)
    fixed = unary_union([Polygon(smooth_ring(g.exterior.coords, False, 0.45),
                                 [smooth_ring(h.coords, False, 0.45) for h in g.interiors]).buffer(0)
                         for g in getattr(fixed, "geoms", [fixed])])
    letters = unary_union([letters.difference(c), fixed.intersection(c)]).buffer(0.01).buffer(-0.01)
# final very light pass (0.08 mm) to blend the seams of the local zones
polys = [Polygon(smooth_ring(g.exterior.coords, False, 0.08), [smooth_ring(h.coords, False, 0.08) for h in g.interiors]).buffer(0)
         for g in getattr(letters, "geoms", [letters])]

diamonds = [Polygon([((x - CX) * SCALE, -(y - CY) * SCALE) for x, y in d]) for d in DIAMONDS]
ring = Point(0, 0).buffer(R_OUT * SCALE, 512).difference(Point(0, 0).buffer(R_IN * SCALE, 512))
logo = unary_union(polys + diamonds + [ring]).simplify(0.002)
if isinstance(logo, Polygon):
    logo = MultiPolygon([logo])

data = [{"ext": list(p.exterior.coords), "holes": [list(h.coords) for h in p.interiors]} for p in logo.geoms]
json.dump(data, open(OUT + "/logo_polys_mm.json", "w"))


def path(p):
    out = ""
    for rr in [p.exterior, *p.interiors]:
        out += "M" + " L".join(f"{x:.3f},{-y:.3f}" for x, y in rr.coords) + " Z "
    return out


svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{DISC_D}mm" height="{DISC_D}mm" '
       f'viewBox="{-DISC_D/2} {-DISC_D/2} {DISC_D} {DISC_D}">'
       f'<circle cx="0" cy="0" r="{DISC_D/2}" fill="#000"/>'
       f'<path fill="#e00000" fill-rule="evenodd" d="{"".join(path(p) for p in logo.geoms)}"/></svg>')
open(OUT + "/aldayyan_logo.svg", "w").write(svg)
print("parts:", len(logo.geoms), "red area mm2:", round(logo.area, 1))
