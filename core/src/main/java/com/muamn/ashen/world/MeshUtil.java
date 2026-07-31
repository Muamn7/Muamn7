package com.muamn.ashen.world;

import com.badlogic.gdx.graphics.g3d.utils.MeshPartBuilder;
import com.badlogic.gdx.math.MathUtils;
import com.badlogic.gdx.math.Vector3;

/**
 * Low-level mesh emission shared by the level geometry and the character rigs.
 *
 * Everything writes tiled, world-sized UVs rather than libGDX's default 0..1 per
 * face, because a 64x64 texture stretched over a 12 metre wall does not read as
 * stone - it reads as fog.
 */
public final class MeshUtil {

    private MeshUtil() {}

    private static final MeshPartBuilder.VertexInfo V0 = new MeshPartBuilder.VertexInfo();
    private static final MeshPartBuilder.VertexInfo V1 = new MeshPartBuilder.VertexInfo();
    private static final MeshPartBuilder.VertexInfo V2 = new MeshPartBuilder.VertexInfo();
    private static final MeshPartBuilder.VertexInfo V3 = new MeshPartBuilder.VertexInfo();
    private static final Vector3 NRM = new Vector3();

    /** Quad in counter-clockwise winding, with explicit UV extents. */
    public static void quad(MeshPartBuilder mpb,
                            float ax, float ay, float az, float bx, float by, float bz,
                            float cx, float cy, float cz, float dx, float dy, float dz,
                            float nx, float ny, float nz, float uTiles, float vTiles) {
        V0.setPos(ax, ay, az).setNor(nx, ny, nz).setUV(0f, vTiles);
        V1.setPos(bx, by, bz).setNor(nx, ny, nz).setUV(uTiles, vTiles);
        V2.setPos(cx, cy, cz).setNor(nx, ny, nz).setUV(uTiles, 0f);
        V3.setPos(dx, dy, dz).setNor(nx, ny, nz).setUV(0f, 0f);
        mpb.rect(V0, V1, V2, V3);
    }

    /** Triangle with UVs projected from world position, for odd-shaped filler faces. */
    public static void tri(MeshPartBuilder mpb, float[] a, float[] b, float[] c,
                           float nx, float ny, float nz, float uvScale) {
        V0.setPos(a[0], a[1], a[2]).setNor(nx, ny, nz).setUV(a[0] * uvScale, (a[2] + a[1]) * uvScale);
        V1.setPos(b[0], b[1], b[2]).setNor(nx, ny, nz).setUV(b[0] * uvScale, (b[2] + b[1]) * uvScale);
        V2.setPos(c[0], c[1], c[2]).setNor(nx, ny, nz).setUV(c[0] * uvScale, (c[2] + c[1]) * uvScale);
        mpb.triangle(V0, V1, V2);
    }

    public static Vector3 faceNormal(float[] a, float[] b, float[] c) {
        float e1x = b[0] - a[0], e1y = b[1] - a[1], e1z = b[2] - a[2];
        float e2x = c[0] - a[0], e2y = c[1] - a[1], e2z = c[2] - a[2];
        return NRM.set(e1y * e2z - e1z * e2y, e1z * e2x - e1x * e2z, e1x * e2y - e1y * e2x).nor();
    }

    /** Axis-aligned box centred on (x, y, z), UVs tiled at {@code uvScale} per metre. */
    public static void box(MeshPartBuilder mpb, float x, float y, float z,
                           float sx, float sy, float sz, float uvScale) {
        float hx = sx * 0.5f, hy = sy * 0.5f, hz = sz * 0.5f;
        float x0 = x - hx, x1 = x + hx, y0 = y - hy, y1 = y + hy, z0 = z - hz, z1 = z + hz;
        quad(mpb, x0, y1, z1, x1, y1, z1, x1, y1, z0, x0, y1, z0, 0, 1, 0, sx * uvScale, sz * uvScale);
        quad(mpb, x0, y0, z0, x1, y0, z0, x1, y0, z1, x0, y0, z1, 0, -1, 0, sx * uvScale, sz * uvScale);
        quad(mpb, x0, y0, z1, x1, y0, z1, x1, y1, z1, x0, y1, z1, 0, 0, 1, sx * uvScale, sy * uvScale);
        quad(mpb, x1, y0, z0, x0, y0, z0, x0, y1, z0, x1, y1, z0, 0, 0, -1, sx * uvScale, sy * uvScale);
        quad(mpb, x1, y0, z1, x1, y0, z0, x1, y1, z0, x1, y1, z1, 1, 0, 0, sz * uvScale, sy * uvScale);
        quad(mpb, x0, y0, z0, x0, y0, z1, x0, y1, z1, x0, y1, z0, -1, 0, 0, sz * uvScale, sy * uvScale);
    }

    /**
     * A box whose cross-section shrinks from bottom to top, hanging between
     * {@code yBottom} and {@code yTop}. Limbs built this way read as anatomy at a
     * distance where a plain cube reads as Minecraft.
     */
    public static void taper(MeshPartBuilder mpb, float x, float z,
                             float yBottom, float yTop,
                             float widthBottom, float depthBottom,
                             float widthTop, float depthTop, float uvScale) {
        float bx = widthBottom * 0.5f, bz = depthBottom * 0.5f;
        float tx = widthTop * 0.5f, tz = depthTop * 0.5f;
        float h = yTop - yBottom;

        // Corners, bottom then top, counter-clockwise seen from above.
        float[][] b = {
                {x - bx, yBottom, z + bz}, {x + bx, yBottom, z + bz},
                {x + bx, yBottom, z - bz}, {x - bx, yBottom, z - bz}};
        float[][] t = {
                {x - tx, yTop, z + tz}, {x + tx, yTop, z + tz},
                {x + tx, yTop, z - tz}, {x - tx, yTop, z - tz}};

        for (int i = 0; i < 4; i++) {
            int j = (i + 1) % 4;
            Vector3 n = faceNormal(b[i], b[j], t[j]);
            float w = Vector3.len(b[j][0] - b[i][0], 0f, b[j][2] - b[i][2]);
            quad(mpb, b[i][0], b[i][1], b[i][2], b[j][0], b[j][1], b[j][2],
                    t[j][0], t[j][1], t[j][2], t[i][0], t[i][1], t[i][2],
                    n.x, n.y, n.z, w * uvScale, h * uvScale);
        }
        // Caps.
        quad(mpb, t[0][0], t[0][1], t[0][2], t[1][0], t[1][1], t[1][2],
                t[2][0], t[2][1], t[2][2], t[3][0], t[3][1], t[3][2],
                0f, 1f, 0f, widthTop * uvScale, depthTop * uvScale);
        quad(mpb, b[3][0], b[3][1], b[3][2], b[2][0], b[2][1], b[2][2],
                b[1][0], b[1][1], b[1][2], b[0][0], b[0][1], b[0][2],
                0f, -1f, 0f, widthBottom * uvScale, depthBottom * uvScale);
    }

    /**
     * Flat blade pointing along +Y, rising from {@code yBase} at (x, z).
     * {@code tipFraction} is how much of the length is taken by the point.
     */
    public static void blade(MeshPartBuilder mpb, float x, float yBase, float z,
                             float length, float width, float thickness,
                             float tipFraction, float uvScale) {
        float hw = width * 0.5f, ht = thickness * 0.5f;
        float tipStart = yBase + length * (1f - tipFraction);
        // Body.
        taper(mpb, x, z, yBase, tipStart, width, thickness, width, thickness, uvScale);
        // Point.
        float[][] faces = {
                {x - hw, tipStart, z + ht}, {x + hw, tipStart, z + ht},
                {x + hw, tipStart, z - ht}, {x - hw, tipStart, z - ht}};
        float[] tip = {x, yBase + length, z};
        for (int i = 0; i < 4; i++) {
            int j = (i + 1) % 4;
            Vector3 n = faceNormal(faces[i], faces[j], tip);
            tri(mpb, faces[i], faces[j], tip, n.x, n.y, n.z, uvScale);
        }
    }

    /** Regular prism around the Y axis; the workhorse for columns and pommels. */
    public static void prism(MeshPartBuilder mpb, float x, float y, float z,
                             float radius, float height, int sides, float uvScale) {
        float step = 360f / sides;
        for (int i = 0; i < sides; i++) {
            float a0 = i * step, a1 = (i + 1) * step;
            float x0 = x + MathUtils.cosDeg(a0) * radius, z0 = z + MathUtils.sinDeg(a0) * radius;
            float x1 = x + MathUtils.cosDeg(a1) * radius, z1 = z + MathUtils.sinDeg(a1) * radius;
            float nx = MathUtils.cosDeg(a0 + step * 0.5f), nz = MathUtils.sinDeg(a0 + step * 0.5f);
            float seg = Vector3.len(x1 - x0, 0f, z1 - z0);
            quad(mpb, x0, y, z0, x1, y, z1, x1, y + height, z1, x0, y + height, z0,
                    nx, 0f, nz, seg * uvScale, height * uvScale);
        }
        for (int i = 0; i < sides; i++) {
            float a0 = i * step, a1 = (i + 1) * step;
            float[] c = {x, y + height, z};
            float[] p0 = {x + MathUtils.cosDeg(a0) * radius, y + height, z + MathUtils.sinDeg(a0) * radius};
            float[] p1 = {x + MathUtils.cosDeg(a1) * radius, y + height, z + MathUtils.sinDeg(a1) * radius};
            tri(mpb, c, p0, p1, 0f, 1f, 0f, uvScale);
            float[] cb = {x, y, z};
            float[] q0 = {p0[0], y, p0[2]};
            float[] q1 = {p1[0], y, p1[2]};
            tri(mpb, cb, q1, q0, 0f, -1f, 0f, uvScale);
        }
    }
}
