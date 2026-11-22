"""Trace the red logo from the image into clean 2D polygons (mm) and an SVG."""
import sys, json, cv2, numpy as np
from shapely.geometry import Polygon, Point, MultiPolygon
from shapely.ops import unary_union
from shapely import affinity

IMG = sys.argv[1]
OUT = sys.argv[2]
DISC_D = 60.0      # mm
MARGIN = 1.0       # black margin outside the red ring (mm)
SMOOTH_SIGMA = 6      # contour smoothing (in upscaled px)
CLOSE_MM = 0.25      # fill slits narrower than 2x this
MIN_WIDTH_MM = 0.4   # remove features thinner than this (nozzle width)
CX, CY = 621, 603  # ring centre in image px
R_IN, R_OUT = 542, 566  # ring radii in image px
SCALE = (DISC_D / 2 - MARGIN) / R_OUT  # px -> mm

im = cv2.imread(IMG).astype(np.int16)
mask = ((im[:, :, 2] > 60) & (im[:, :, 2] - im[:, :, 1] > 40)).astype(np.uint8) * 255
yy, xx = np.indices(mask.shape)
mask[np.hypot(xx - CX, yy - CY) > 532] = 0          # remove ring + glow; ring is rebuilt as a perfect circle

# smooth: upscale, close small gaps, blur, rethreshold, drop specks
up = 3
m = cv2.resize(mask, None, fx=up, fy=up, interpolation=cv2.INTER_CUBIC)
k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, k)
m = cv2.GaussianBlur(m, (0, 0), 3.0)
m = (m > 127).astype(np.uint8) * 255
m = cv2.morphologyEx(m, cv2.MORPH_OPEN, k)
n, lab, st, _ = cv2.connectedComponentsWithStats(m)
for i in range(1, n):
    if st[i, 4] < 600 * up * up / 9:
        m[lab == i] = 0
cv2.imwrite(OUT + "/mask_clean.png", m)

cs, hier = cv2.findContours(m, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
hier = hier[0]
from scipy.ndimage import gaussian_filter1d
def smooth(c, sigma=SMOOTH_SIGMA):
    p = c[:, 0].astype(float)
    if len(p) < 4 * sigma:
        return c
    p = np.c_[gaussian_filter1d(p[:, 0], sigma, mode="wrap"), gaussian_filter1d(p[:, 1], sigma, mode="wrap")]
    return p[:, None, :]
cs = [smooth(c) for c in cs]
polys = []
for i, c in enumerate(cs):
    if hier[i][3] != -1:  # holes handled with parent
        continue
    holes = []
    j = hier[i][2]
    while j != -1:
        if len(cs[j]) >= 8 and cv2.contourArea(cs[j].astype(np.float32)) > 30 * up * up:
            holes.append(cs[j][:, 0] / up)
        j = hier[j][0]
    if len(c) < 8:
        continue
    p = Polygon(c[:, 0] / up, holes).buffer(0)
    far = np.hypot(p.centroid.x - CX, p.centroid.y - CY) > 400
    if p.area > 250 and not (far and p.area < 3000):  # drop glow scratches near the ring
        polys.append(p)
letters = unary_union(polys)
ring = Point(CX, CY).buffer(R_OUT, 256).difference(Point(CX, CY).buffer(R_IN, 256))

letters_mm = affinity.scale(affinity.translate(letters, -CX, -CY), SCALE, -SCALE, origin=(0, 0))
ring_mm = affinity.scale(affinity.translate(ring, -CX, -CY), SCALE, -SCALE, origin=(0, 0))
r = MIN_WIDTH_MM / 2
letters_mm = letters_mm.buffer(CLOSE_MM, 32).buffer(-CLOSE_MM, 32)          # close hairline slits
letters_mm = letters_mm.buffer(-r, 32).buffer(r, 32)                        # drop slivers < nozzle
geoms = getattr(letters_mm, "geoms", [letters_mm])
letters_mm = unary_union([g for g in geoms if g.area > 0.8])
logo = unary_union([letters_mm, ring_mm]).simplify(0.01)
if isinstance(logo, Polygon):
    logo = MultiPolygon([logo])

data = [{"ext": list(p.exterior.coords), "holes": [list(h.coords) for h in p.interiors]} for p in logo.geoms]
json.dump(data, open(OUT + "/logo_polys_mm.json", "w"))

# SVG (mm units) for importing into Blender manually if wanted
def path(p):
    s = ""
    for ring_ in [p.exterior, *p.interiors]:
        pts = list(ring_.coords)
        s += "M" + " L".join(f"{x:.3f},{-y:.3f}" for x, y in pts) + " Z "
    return s
svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{DISC_D}mm" height="{DISC_D}mm" '
       f'viewBox="{-DISC_D/2} {-DISC_D/2} {DISC_D} {DISC_D}">'
       f'<circle cx="0" cy="0" r="{DISC_D/2}" fill="#000"/>'
       f'<path fill="#e00000" fill-rule="evenodd" d="{"".join(path(p) for p in logo.geoms)}"/></svg>')
open(OUT + "/aldayyan_logo.svg", "w").write(svg)
print("parts:", len(logo.geoms), "red area mm2:", round(logo.area, 1), "scale mm/px:", round(SCALE, 5))
