"""Union all closed shells of an STL into ONE watertight solid and report any
floating (disconnected) pieces.

    pip install manifold3d numpy
    python make_single_solid.py print/GABA_A_receptor_300mm.stl out_single.stl

(GABA_A_receptor_300mm.stl is written by:  blender -b -P gaba_a_receptor.py -- --stl print)
"""
import sys, numpy as np, manifold3d as m3d
src, dst = sys.argv[1], sys.argv[2]
raw = np.fromfile(src, dtype=np.uint8)
n = int(np.frombuffer(raw[80:84], "<u4")[0])
rec = np.frombuffer(raw[84:84 + n * 50].tobytes(), dtype=np.dtype([("n", "<3f4"), ("v", "<9f4"), ("a", "<u2")]))
tri = rec["v"].reshape(-1, 3).astype(np.float64)
q = np.round(tri * 1e4).astype(np.int64)                 # weld identical verts
uniq, inv = np.unique(q, axis=0, return_inverse=True)
verts = uniq / 1e4
faces = inv.reshape(-1, 3)
# connected components (union-find on faces via shared vertices)
parent = np.arange(len(verts))
def find(x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]; x = parent[x]
    return x
for a, b, c in faces:
    ra, rb, rc = find(a), find(b), find(c)
    parent[rb] = ra; parent[find(rc)] = ra
roots = np.array([find(i) for i in range(len(verts))])
comp = roots[faces[:, 0]]
shells, bad = [], 0
for r in np.unique(comp):
    f = faces[comp == r]
    used, rem = np.unique(f, return_inverse=True)
    mesh = m3d.Mesh(vert_properties=verts[used].astype(np.float32), tri_verts=rem.reshape(-1, 3).astype(np.uint32))
    man = m3d.Manifold(mesh)
    if man.status() != m3d.Error.NoError or man.is_empty():
        bad += 1; continue
    shells.append(man)
print("input shells:", len(shells), "rejected:", bad)
solid = m3d.Manifold.batch_boolean(shells, m3d.OpType.Add)
parts = solid.decompose()
print("connected solids after union:", len(parts))
for p in sorted(parts, key=lambda p: -p.volume())[:8]:
    bb = p.bounding_box()
    print("  vol %.1f cm3  bbox min %s max %s" % (p.volume() / 1000, np.round(bb[:3], 1), np.round(bb[3:], 1)))
out = solid.to_mesh()
v, t = np.asarray(out.vert_properties)[:, :3], np.asarray(out.tri_verts)
tris = v[t]
nrm = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
recs = np.zeros(len(t), dtype=rec.dtype)
recs["n"] = nrm; recs["v"] = tris.reshape(-1, 9)
with open(dst, "wb") as fh:
    fh.write(b"GABA-A receptor - single watertight solid, mm".ljust(80, b" "))
    fh.write(np.uint32(len(t)).tobytes()); fh.write(recs.tobytes())
bb = solid.bounding_box()
print("final: %d triangles, size %.1f x %.1f x %.1f mm, volume %.0f cm3, genus %d" % (
    len(t), bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2], solid.volume() / 1000, solid.genus()))
