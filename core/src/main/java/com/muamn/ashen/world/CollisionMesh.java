package com.muamn.ashen.world;

import com.badlogic.gdx.math.MathUtils;
import com.badlogic.gdx.math.Vector3;
import com.badlogic.gdx.math.collision.BoundingBox;
import com.badlogic.gdx.utils.Array;
import com.badlogic.gdx.utils.IntArray;
import com.badlogic.gdx.utils.LongMap;

/**
 * Static level collision: a triangle soup in a uniform spatial hash.
 *
 * A full physics engine is overkill for a game whose world is hand-placed boxes
 * and ramps, and Bullet would add several MB to the APK. Triangles plus a grid
 * give exact geometry, deterministic results (important for a game where a roll
 * either clears an attack or does not), and a broadphase that costs one hash
 * lookup per cell.
 */
public class CollisionMesh {

    /** Cell size of the broadphase grid, in metres. */
    private static final float CELL = 4f;

    private final Array<float[]> triangles = new Array<>();
    private final Array<Vector3> normals = new Array<>();
    private final LongMap<IntArray> grid = new LongMap<>();
    private final BoundingBox bounds = new BoundingBox();

    /**
     * Optional extra collision layered on top, used for boss arena barriers.
     *
     * A boss fight has to seal itself in and open again afterwards, and rebuilding
     * a level's whole spatial hash to add two dozen wall triangles would be
     * absurd. Queries and raycasts fall through to the overlay with the indices
     * offset past our own, so callers never need to know there are two meshes.
     */
    private CollisionMesh overlay;

    private final Vector3 t0 = new Vector3(), t1 = new Vector3(), t2 = new Vector3();
    private final Vector3 e1 = new Vector3(), e2 = new Vector3(), n = new Vector3();
    private final IntArray queryResult = new IntArray();

    public CollisionMesh() {
        bounds.inf();
    }

    /** Adds a triangle. Winding decides the normal, which decides which side is solid. */
    public void addTriangle(float ax, float ay, float az, float bx, float by, float bz,
                            float cx, float cy, float cz) {
        e1.set(bx - ax, by - ay, bz - az);
        e2.set(cx - ax, cy - ay, cz - az);
        n.set(e1).crs(e2);
        if (n.len2() < 1e-12f) return; // degenerate, contributes nothing
        n.nor();

        int index = triangles.size;
        triangles.add(new float[]{ax, ay, az, bx, by, bz, cx, cy, cz});
        normals.add(new Vector3(n));

        bounds.ext(ax, ay, az);
        bounds.ext(bx, by, bz);
        bounds.ext(cx, cy, cz);

        int minX = cell(Math.min(ax, Math.min(bx, cx)));
        int maxX = cell(Math.max(ax, Math.max(bx, cx)));
        int minY = cell(Math.min(ay, Math.min(by, cy)));
        int maxY = cell(Math.max(ay, Math.max(by, cy)));
        int minZ = cell(Math.min(az, Math.min(bz, cz)));
        int maxZ = cell(Math.max(az, Math.max(bz, cz)));
        for (int x = minX; x <= maxX; x++) {
            for (int y = minY; y <= maxY; y++) {
                for (int z = minZ; z <= maxZ; z++) {
                    long key = key(x, y, z);
                    IntArray list = grid.get(key);
                    if (list == null) {
                        list = new IntArray(8);
                        grid.put(key, list);
                    }
                    list.add(index);
                }
            }
        }
    }

    /** Layers extra collision on top, or clears it with null. */
    public void setOverlay(CollisionMesh overlay) {
        this.overlay = overlay;
    }

    public CollisionMesh getOverlay() {
        return overlay;
    }

    /** Triangles owned by this mesh, ignoring any overlay. */
    public int ownTriangleCount() {
        return triangles.size;
    }

    public int triangleCount() {
        return triangles.size + (overlay != null ? overlay.triangleCount() : 0);
    }

    public BoundingBox getBounds() {
        return bounds;
    }

    public Vector3 normalOf(int tri) {
        if (tri < normals.size) return normals.get(tri);
        return overlay.normalOf(tri - normals.size);
    }

    public float[] vertsOf(int tri) {
        if (tri < triangles.size) return triangles.get(tri);
        return overlay.vertsOf(tri - triangles.size);
    }

    private static int cell(float v) {
        return MathUtils.floor(v / CELL);
    }

    private static long key(int x, int y, int z) {
        // 21 bits per axis, biased to keep negatives positive.
        long kx = (x + 0x0FFFFF) & 0x1FFFFF;
        long ky = (y + 0x0FFFFF) & 0x1FFFFF;
        long kz = (z + 0x0FFFFF) & 0x1FFFFF;
        return (kx << 42) | (ky << 21) | kz;
    }

    /**
     * Collects triangle indices whose cells overlap the box. The result is
     * de-duplicated and reused between calls, so do not hold on to it.
     */
    public IntArray query(float minX, float minY, float minZ, float maxX, float maxY, float maxZ) {
        queryResult.clear();
        int cx0 = cell(minX), cx1 = cell(maxX);
        int cy0 = cell(minY), cy1 = cell(maxY);
        int cz0 = cell(minZ), cz1 = cell(maxZ);
        for (int x = cx0; x <= cx1; x++) {
            for (int y = cy0; y <= cy1; y++) {
                for (int z = cz0; z <= cz1; z++) {
                    IntArray list = grid.get(key(x, y, z));
                    if (list == null) continue;
                    for (int i = 0; i < list.size; i++) {
                        int tri = list.get(i);
                        if (!queryResult.contains(tri)) queryResult.add(tri);
                    }
                }
            }
        }
        if (overlay != null) {
            IntArray extra = overlay.query(minX, minY, minZ, maxX, maxY, maxZ);
            // Copy before appending: the overlay hands back its own scratch array.
            int base = triangles.size;
            for (int i = 0; i < extra.size; i++) overlayScratch.add(extra.get(i) + base);
            queryResult.addAll(overlayScratch);
            overlayScratch.clear();
        }
        return queryResult;
    }

    private final IntArray overlayScratch = new IntArray();

    // ---- Ray casting ------------------------------------------------------

    private final Vector3 rayTmpA = new Vector3(), rayTmpB = new Vector3();
    private final Vector3 rayTmpC = new Vector3(), rayTmpD = new Vector3();

    /**
     * Casts a ray and returns the distance to the nearest hit, or -1 for a miss.
     * {@code outNormal} receives the surface normal when non-null.
     */
    public float raycast(Vector3 origin, Vector3 dir, float maxDist, Vector3 outNormal) {
        float minX = Math.min(origin.x, origin.x + dir.x * maxDist);
        float maxX = Math.max(origin.x, origin.x + dir.x * maxDist);
        float minY = Math.min(origin.y, origin.y + dir.y * maxDist);
        float maxY = Math.max(origin.y, origin.y + dir.y * maxDist);
        float minZ = Math.min(origin.z, origin.z + dir.z * maxDist);
        float maxZ = Math.max(origin.z, origin.z + dir.z * maxDist);

        IntArray candidates = query(minX, minY, minZ, maxX, maxY, maxZ);
        float best = -1f;
        for (int i = 0; i < candidates.size; i++) {
            int tri = candidates.get(i);
            float[] v = vertsOf(tri);
            float d = rayTriangle(origin, dir, v);
            if (d >= 0 && d <= maxDist && (best < 0 || d < best)) {
                best = d;
                if (outNormal != null) outNormal.set(normalOf(tri));
            }
        }
        return best;
    }

    /**
     * Moller-Trumbore, double sided.
     *
     * The barycentric tests are widened by {@link #EDGE_EPSILON}. Level floors are
     * built from triangle pairs, so a character standing on the shared diagonal
     * sits exactly on the boundary of both triangles - with an exact test,
     * rounding decides whether the ground probe finds anything at all, and the
     * body flickers between grounded and airborne every other frame.
     */
    private float rayTriangle(Vector3 o, Vector3 d, float[] v) {
        rayTmpA.set(v[3] - v[0], v[4] - v[1], v[5] - v[2]);
        rayTmpB.set(v[6] - v[0], v[7] - v[1], v[8] - v[2]);
        rayTmpC.set(d).crs(rayTmpB);
        float det = rayTmpA.dot(rayTmpC);
        if (Math.abs(det) < 1e-8f) return -1f;
        float invDet = 1f / det;
        rayTmpD.set(o.x - v[0], o.y - v[1], o.z - v[2]);
        float u = rayTmpD.dot(rayTmpC) * invDet;
        if (u < -EDGE_EPSILON || u > 1f + EDGE_EPSILON) return -1f;
        rayTmpC.set(rayTmpD).crs(rayTmpA);
        float w = d.dot(rayTmpC) * invDet;
        if (w < -EDGE_EPSILON || u + w > 1f + EDGE_EPSILON) return -1f;
        float t = rayTmpB.dot(rayTmpC) * invDet;
        return t >= 0f ? t : -1f;
    }

    /** Barycentric slack for ray hits, so shared triangle edges are never a gap. */
    private static final float EDGE_EPSILON = 1e-4f;

    // ---- Closest point queries -------------------------------------------

    private static final Vector3 cpAb = new Vector3(), cpAc = new Vector3(), cpAp = new Vector3();
    private static final Vector3 cpBp = new Vector3(), cpCp = new Vector3();

    /** Closest point on triangle {@code abc} to {@code p} (Ericson, RTCD 5.1.5). */
    public static Vector3 closestPointOnTriangle(Vector3 p, Vector3 a, Vector3 b, Vector3 c,
                                                 Vector3 out) {
        cpAb.set(b).sub(a);
        cpAc.set(c).sub(a);
        cpAp.set(p).sub(a);
        float d1 = cpAb.dot(cpAp), d2 = cpAc.dot(cpAp);
        if (d1 <= 0f && d2 <= 0f) return out.set(a);

        cpBp.set(p).sub(b);
        float d3 = cpAb.dot(cpBp), d4 = cpAc.dot(cpBp);
        if (d3 >= 0f && d4 <= d3) return out.set(b);

        float vc = d1 * d4 - d3 * d2;
        if (vc <= 0f && d1 >= 0f && d3 <= 0f) {
            float v = d1 / (d1 - d3);
            return out.set(a).mulAdd(cpAb, v);
        }

        cpCp.set(p).sub(c);
        float d5 = cpAb.dot(cpCp), d6 = cpAc.dot(cpCp);
        if (d6 >= 0f && d5 <= d6) return out.set(c);

        float vb = d5 * d2 - d1 * d6;
        if (vb <= 0f && d2 >= 0f && d6 <= 0f) {
            float w = d2 / (d2 - d6);
            return out.set(a).mulAdd(cpAc, w);
        }

        float va = d3 * d6 - d5 * d4;
        if (va <= 0f && (d4 - d3) >= 0f && (d5 - d6) >= 0f) {
            float w = (d4 - d3) / ((d4 - d3) + (d5 - d6));
            return out.set(b).mulAdd(cpCp.set(c).sub(b), w);
        }

        float denom = 1f / (va + vb + vc);
        float v = vb * denom, w = vc * denom;
        return out.set(a).mulAdd(cpAb, v).mulAdd(cpAc, w);
    }

    private static final Vector3 ssD1 = new Vector3(), ssD2 = new Vector3(), ssR = new Vector3();

    /**
     * Closest points between segments p1-q1 and p2-q2 (Ericson, RTCD 5.1.9).
     * Writes the results into {@code c1} and {@code c2}, returns squared distance.
     */
    public static float closestSegmentSegment(Vector3 p1, Vector3 q1, Vector3 p2, Vector3 q2,
                                              Vector3 c1, Vector3 c2) {
        ssD1.set(q1).sub(p1);
        ssD2.set(q2).sub(p2);
        ssR.set(p1).sub(p2);
        float a = ssD1.len2(), e = ssD2.len2(), f = ssD2.dot(ssR);
        float s, t;
        final float EPS = 1e-8f;

        if (a <= EPS && e <= EPS) {
            c1.set(p1);
            c2.set(p2);
            return c1.dst2(c2);
        }
        if (a <= EPS) {
            s = 0f;
            t = MathUtils.clamp(f / e, 0f, 1f);
        } else {
            float c = ssD1.dot(ssR);
            if (e <= EPS) {
                t = 0f;
                s = MathUtils.clamp(-c / a, 0f, 1f);
            } else {
                float b = ssD1.dot(ssD2);
                float denom = a * e - b * b;
                s = denom != 0f ? MathUtils.clamp((b * f - c * e) / denom, 0f, 1f) : 0f;
                t = (b * s + f) / e;
                if (t < 0f) {
                    t = 0f;
                    s = MathUtils.clamp(-c / a, 0f, 1f);
                } else if (t > 1f) {
                    t = 1f;
                    s = MathUtils.clamp((b - c) / a, 0f, 1f);
                }
            }
        }
        c1.set(p1).mulAdd(ssD1, s);
        c2.set(p2).mulAdd(ssD2, t);
        return c1.dst2(c2);
    }
}
