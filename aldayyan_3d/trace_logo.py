"""Trace the red logo from the image into clean 2D polygons (mm) and an SVG."""
import sys, json, cv2, numpy as np
from shapely.geometry import Polygon, Point, MultiPolygon
from shapely.ops import unary_union
from shapely import affinity

IMG = sys.argv[1]
OUT = sys.argv[2]
DISC_D = 60.0      # mm
MARGIN = 1.0       # black margin outside the red ring (mm)
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
polys = []
for i, c in enumerate(cs):
    if hier[i][3] != -1:
        continue  # holes handled with parent
    holes = []
    j = hier[i][2]
    while j != -1:
        if len(cs[j]) >= 8 and cv2.contourArea(cs[j]) > 30 * up * up:
            holes.append(cs[j][:, 0] / up)
        j = hier[j][0]
    if len(c) < 8:
        continue
    p = Polygon(c[:, 0] / up, holes).buffer(0)
    far = np.hypot(p.centroid.x - CX, p.centroid.y - CY) > 400
    if p.area > 250 and not (far and p.area < 3000):  # drop glow scratches near the ring
        polys.append(p)
letters = unary_union(polys).simplify(0.35)
ring = Point(CX, CY).buffer(R_OUT, 256).difference(Point(CX, CY).buffer(R_IN, 256))
logo = unary_union([letters, ring])

# to mm, centred, flip Y (image y down -> Blender y up)
logo = affinity.translate(logo, -CX, -CY)
logo = affinity.scale(logo, SCALE, -SCALE, origin=(0, 0))
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
