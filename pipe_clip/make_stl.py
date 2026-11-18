"""Builds pipe_clip.stl + preview images without Blender (uses the same profile)."""
import sys, math
import numpy as np, trimesh
from shapely.geometry import Polygon, Point
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from pipe_clip_blender import build_profile, PARAMS

pts, info = build_profile(PARAMS)
poly = Polygon(pts)
assert poly.is_valid, "profile self-intersects"
cx, cz = info["pipe_center"]; r = (PARAMS["pipe_d"] + PARAMS["clearance"]) / 2
print({k: (round(v, 2) if isinstance(v, float) else v) for k, v in info.items()})
print("min z", round(min(z for _, z in pts), 3), "area mm2", round(poly.area, 1))
# min thickness: neck, and lip
print("neck width at pipe-center height", round(2 * (cx - r), 2))

m = trimesh.creation.extrude_polygon(poly, PARAMS["depth"])   # profile in XY, extrude Z
# reorient: profile X->X, profile Y(height)->Z, extrusion -> Y
m.apply_transform(np.array([[1,0,0,0],[0,0,-1,PARAMS["depth"]/2],[0,1,0,0],[0,0,0,1]]))
print("watertight", m.is_watertight, "volume cm3", round(m.volume/1000, 2), "bbox", np.round(m.extents, 2))
m.export("pipe_clip.stl")

# --- preview: dimensioned front view + 3D view ---
fig = plt.figure(figsize=(13, 6))
ax = fig.add_subplot(1, 2, 1)
xs, zs = zip(*(pts + [pts[0]]))
ax.fill(xs, zs, color="#9fb4c8"); ax.plot(xs, zs, color="#1d2b38", lw=1.5)
for sx in (-1, 1):
    ax.add_patch(plt.Circle((sx*cx, cz), PARAMS["pipe_d"]/2, fill=False, ec="#d1352b", lw=1.5, ls="--"))
W, H = info["width"], info["height"]
def dim(x0, y0, x1, y1, txt, off=(0, 0)):
    ax.annotate("", (x0, y0), (x1, y1), arrowprops=dict(arrowstyle="<->", lw=1))
    ax.text((x0+x1)/2+off[0], (y0+y1)/2+off[1], txt, ha="center", va="center", fontsize=10,
            bbox=dict(fc="white", ec="none", pad=1))
dim(-W/2, -6, W/2, -6, f"{W:.1f} mm")
dim(-PARAMS["base_w"]/2, -2, PARAMS["base_w"]/2, -2, f"{PARAMS['base_w']:.0f}", (0, 0))
dim(W/2+4, 0, W/2+4, H, f"{H:.1f} mm", (4, 0))
dim(cx - PARAMS["pipe_d"]/2, cz, cx + PARAMS["pipe_d"]/2, cz, "Ø17.5", (0, 2))
dim(-cx - PARAMS["pipe_d"]/2, cz, -cx + PARAMS["pipe_d"]/2, cz, "Ø17.5", (0, 2))
ax.set_aspect("equal"); ax.set_xlim(-W/2-6, W/2+12); ax.set_ylim(-10, H+5)
ax.text(cx+11, cz-9, f"hook {PARAMS['hook_deg']:.0f}°\nopening {info['opening']:.1f}", fontsize=9, color="#d1352b")
ax.set_title("Front view (mm)  -  red dashed = pipe"); ax.grid(alpha=.25)

ax3 = fig.add_subplot(1, 2, 2, projection="3d")
tri = m.vertices[m.faces]
n = m.face_normals; light = np.clip(n @ np.array([0.4, -0.7, 0.6]), 0, 1)*0.6 + 0.35
ax3.add_collection3d(Poly3DCollection(tri, facecolors=plt.cm.Blues(light*0.8+0.1), edgecolor="none"))
lim = max(m.extents)/2+2
ax3.set_xlim(-lim, lim); ax3.set_ylim(-lim, lim); ax3.set_zlim(0, 2*lim)
ax3.view_init(elev=22, azim=-60); ax3.set_box_aspect((1, 1, 1)); ax3.set_axis_off()
ax3.set_title("3D (50 mm long)")
plt.tight_layout(); plt.savefig("pipe_clip_preview.png", dpi=110)
