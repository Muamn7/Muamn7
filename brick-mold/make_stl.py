# يولّد نفس القالب كملف STL بدون Blender (manifold3d + trimesh)
import numpy as np, trimesh
from manifold3d import Manifold

BRICK_L, BRICK_W, BRICK_H = 18.0, 8.5, 5.5
HOLES, HOLE_D, HOLE_STEP, SEGS = 3, 2.2, 5.2, 32
COLS, ROWS, GAP_X, GAP_Y = 6, 4, 4.0, 5.0
MARGIN, WALL_T, BASE_T, SIL = 5.0, 2.0, 2.0, 4.0
EAR_R, EAR_T = 6.0, 0.4

IX = COLS*BRICK_W + (COLS-1)*GAP_X + 2*MARGIN
IY = ROWS*BRICK_L + (ROWS-1)*GAP_Y + 2*MARGIN
OX, OY = IX + 2*WALL_T, IY + 2*WALL_T
WH = BASE_T + BRICK_H + SIL

def box(sx, sy, sz, cx, cy, z0):
    return Manifold.cube([sx, sy, sz]).translate([cx-sx/2, cy-sy/2, z0])
def cyl(r, h, cx, cy, z0, segs=SEGS):
    return Manifold.cylinder(h, r, r, segs).translate([cx, cy, z0])

parts = [box(OX, OY, BASE_T, 0, 0, 0),
         box(OX, WALL_T, WH, 0, -OY/2+WALL_T/2, 0), box(OX, WALL_T, WH, 0, OY/2-WALL_T/2, 0),
         box(WALL_T, OY, WH, -OX/2+WALL_T/2, 0, 0), box(WALL_T, OY, WH, OX/2-WALL_T/2, 0, 0)]
parts += [cyl(EAR_R, EAR_T, sx*OX/2, sy*OY/2, 0, 48) for sx in (-1,1) for sy in (-1,1)]
holes = []
x0 = -IX/2 + MARGIN + BRICK_W/2
y0 = -IY/2 + MARGIN + BRICK_L/2
for r in range(ROWS):
    for c in range(COLS):
        cx, cy = x0 + c*(BRICK_W+GAP_X), y0 + r*(BRICK_L+GAP_Y)
        parts.append(box(BRICK_W, BRICK_L, BRICK_H+0.01, cx, cy, BASE_T-0.01))
        for i in range(HOLES):
            holes.append(cyl(HOLE_D/2, BRICK_H+1, cx, cy+(i-(HOLES-1)/2)*HOLE_STEP, BASE_T))

m = Manifold.batch_boolean(parts, __import__('manifold3d').OpType.Add) - \
    Manifold.batch_boolean(holes, __import__('manifold3d').OpType.Add)
mesh = m.to_mesh()
tm = trimesh.Trimesh(np.array(mesh.vert_properties)[:, :3], np.array(mesh.tri_verts))
tm.export("brick_mold_master.stl")
print("size mm:", np.round(tm.extents, 2), "watertight:", tm.is_watertight,
      "volume cm3:", round(tm.volume/1000, 2), "tris:", len(tm.faces))
