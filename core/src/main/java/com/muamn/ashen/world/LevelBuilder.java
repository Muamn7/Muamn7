package com.muamn.ashen.world;

import com.badlogic.gdx.graphics.Color;
import com.badlogic.gdx.graphics.GL20;
import com.badlogic.gdx.graphics.VertexAttributes.Usage;
import com.badlogic.gdx.graphics.g3d.Material;
import com.badlogic.gdx.graphics.g3d.Model;
import com.badlogic.gdx.graphics.g3d.attributes.ColorAttribute;
import com.badlogic.gdx.graphics.g3d.attributes.TextureAttribute;
import com.badlogic.gdx.graphics.g3d.utils.MeshPartBuilder;
import com.badlogic.gdx.graphics.g3d.utils.ModelBuilder;
import com.badlogic.gdx.math.MathUtils;
import com.badlogic.gdx.math.Vector3;
import com.badlogic.gdx.utils.Array;
import com.badlogic.gdx.utils.ObjectMap;

/**
 * Builds level geometry as one model plus its collision mesh, from a handful of
 * primitives.
 *
 * Everything is grouped by material before it is emitted, so a level with a
 * thousand blocks still draws in as many batches as it has textures. That
 * matters far more than triangle count on mobile GPUs.
 */
public class LevelBuilder {

    /** UVs are world-space, so a texture tiles at a constant size everywhere. */
    private static final float DEFAULT_TEXELS_PER_METRE = 0.5f;

    private static final long ATTRS = Usage.Position | Usage.Normal | Usage.TextureCoordinates;

    private interface Shape {
        void emit(MeshPartBuilder mpb);
    }

    private final TextureFactory textures;
    private final CollisionMesh collision = new CollisionMesh();
    private final ObjectMap<String, Array<Shape>> byMaterial = new ObjectMap<>();
    private final Array<String> materialOrder = new Array<>();

    public LevelBuilder(TextureFactory textures) {
        this.textures = textures;
    }

    public CollisionMesh getCollision() {
        return collision;
    }

    private void add(String material, Shape shape) {
        Array<Shape> list = byMaterial.get(material);
        if (list == null) {
            list = new Array<>();
            byMaterial.put(material, list);
            materialOrder.add(material);
        }
        list.add(shape);
    }

    // ---- Primitives -------------------------------------------------------

    /**
     * Axis-aligned box centred on (x, y, z). {@code solid} controls whether it
     * also becomes collision - decorative trim usually should not.
     */
    public LevelBuilder box(String material, float x, float y, float z,
                            float sx, float sy, float sz, boolean solid) {
        return box(material, x, y, z, sx, sy, sz, solid, DEFAULT_TEXELS_PER_METRE);
    }

    public LevelBuilder box(String material, float x, float y, float z,
                            float sx, float sy, float sz, boolean solid, float uvScale) {
        float hx = sx * 0.5f, hy = sy * 0.5f, hz = sz * 0.5f;
        float x0 = x - hx, x1 = x + hx;
        float y0 = y - hy, y1 = y + hy;
        float z0 = z - hz, z1 = z + hz;

        add(material, mpb -> {
            // +Y and -Y
            quad(mpb, x0, y1, z1, x1, y1, z1, x1, y1, z0, x0, y1, z0, 0, 1, 0, sx * uvScale, sz * uvScale);
            quad(mpb, x0, y0, z0, x1, y0, z0, x1, y0, z1, x0, y0, z1, 0, -1, 0, sx * uvScale, sz * uvScale);
            // +Z and -Z
            quad(mpb, x0, y0, z1, x1, y0, z1, x1, y1, z1, x0, y1, z1, 0, 0, 1, sx * uvScale, sy * uvScale);
            quad(mpb, x1, y0, z0, x0, y0, z0, x0, y1, z0, x1, y1, z0, 0, 0, -1, sx * uvScale, sy * uvScale);
            // +X and -X
            quad(mpb, x1, y0, z1, x1, y0, z0, x1, y1, z0, x1, y1, z1, 1, 0, 0, sz * uvScale, sy * uvScale);
            quad(mpb, x0, y0, z0, x0, y0, z1, x0, y1, z1, x0, y1, z0, -1, 0, 0, sz * uvScale, sy * uvScale);
        });

        if (solid) collisionBox(x0, y0, z0, x1, y1, z1);
        return this;
    }

    /**
     * A ramp rising along +Z (or the axis given by {@code facing} in degrees).
     * Used for stairs the player should slide up rather than step over.
     */
    public LevelBuilder ramp(String material, float x, float y, float z,
                             float sx, float rise, float run, float facingDeg, boolean solid) {
        float cos = MathUtils.cosDeg(facingDeg), sin = MathUtils.sinDeg(facingDeg);
        float hx = sx * 0.5f, hz = run * 0.5f;

        // Local corners: low edge at -z, high edge at +z.
        float[][] local = {
                {-hx, 0f, -hz}, {hx, 0f, -hz}, {hx, rise, hz}, {-hx, rise, hz},
                {-hx, 0f, hz}, {hx, 0f, hz},
        };
        float[][] w = new float[local.length][3];
        for (int i = 0; i < local.length; i++) {
            w[i][0] = x + local[i][0] * cos + local[i][2] * sin;
            w[i][1] = y + local[i][1];
            w[i][2] = z - local[i][0] * sin + local[i][2] * cos;
        }
        float slopeLen = (float) Math.sqrt(rise * rise + run * run);

        add(material, mpb -> {
            // Sloped top face.
            Vector3 n = faceNormal(w[0], w[1], w[2]);
            quad(mpb, w[0][0], w[0][1], w[0][2], w[1][0], w[1][1], w[1][2],
                    w[2][0], w[2][1], w[2][2], w[3][0], w[3][1], w[3][2],
                    n.x, n.y, n.z, sx * DEFAULT_TEXELS_PER_METRE, slopeLen * DEFAULT_TEXELS_PER_METRE);
            // Back wall (the tall end).
            quad(mpb, w[4][0], w[4][1], w[4][2], w[5][0], w[5][1], w[5][2],
                    w[2][0], w[2][1], w[2][2], w[3][0], w[3][1], w[3][2],
                    sin, 0f, cos, sx * DEFAULT_TEXELS_PER_METRE, rise * DEFAULT_TEXELS_PER_METRE);
            // Bottom.
            quad(mpb, w[0][0], w[0][1], w[0][2], w[4][0], w[4][1], w[4][2],
                    w[5][0], w[5][1], w[5][2], w[1][0], w[1][1], w[1][2],
                    0f, -1f, 0f, sx * DEFAULT_TEXELS_PER_METRE, run * DEFAULT_TEXELS_PER_METRE);
            // Two triangular sides.
            tri(mpb, w[0], w[3], w[4], -cos, 0f, sin, DEFAULT_TEXELS_PER_METRE);
            tri(mpb, w[1], w[5], w[2], cos, 0f, -sin, DEFAULT_TEXELS_PER_METRE);
        });

        if (solid) {
            addTri(w[0], w[1], w[2]);
            addTri(w[0], w[2], w[3]);
            addTri(w[4], w[5], w[2]);
            addTri(w[4], w[2], w[3]);
            addTri(w[0], w[4], w[5]);
            addTri(w[0], w[5], w[1]);
            addTri(w[0], w[3], w[4]);
            addTri(w[1], w[5], w[2]);
        }
        return this;
    }

    /** Vertical N-sided column. Collision uses the inscribed box, which is enough. */
    public LevelBuilder column(String material, float x, float y, float z,
                               float radius, float heightY, int sides, boolean solid) {
        add(material, mpb -> MeshUtil.prism(mpb, x, y, z, radius, heightY, sides,
                DEFAULT_TEXELS_PER_METRE));
        if (solid) {
            float r = radius * 0.92f;
            collisionBox(x - r, y, z - r, x + r, y + heightY, z + r);
        }
        return this;
    }

    /** An invisible wall. Used to fence off the playable area without art. */
    public LevelBuilder blocker(float x, float y, float z, float sx, float sy, float sz) {
        collisionBox(x - sx * 0.5f, y - sy * 0.5f, z - sz * 0.5f,
                x + sx * 0.5f, y + sy * 0.5f, z + sz * 0.5f);
        return this;
    }

    // ---- Emission ---------------------------------------------------------

    /** Bakes everything added so far into a single model. */
    public Model build() {
        ModelBuilder mb = new ModelBuilder();
        mb.begin();
        for (String materialName : materialOrder) {
            Material material = new Material(
                    TextureAttribute.createDiffuse(textures.get(materialName)),
                    ColorAttribute.createDiffuse(Color.WHITE));
            MeshPartBuilder mpb = mb.part(materialName, GL20.GL_TRIANGLES, ATTRS, material);
            for (Shape shape : byMaterial.get(materialName)) shape.emit(mpb);
        }
        return mb.end();
    }

    // ---- Geometry helpers -------------------------------------------------

    private static void quad(MeshPartBuilder mpb,
                             float ax, float ay, float az, float bx, float by, float bz,
                             float cx, float cy, float cz, float dx, float dy, float dz,
                             float nx, float ny, float nz, float uTiles, float vTiles) {
        MeshUtil.quad(mpb, ax, ay, az, bx, by, bz, cx, cy, cz, dx, dy, dz, nx, ny, nz, uTiles, vTiles);
    }

    private static void tri(MeshPartBuilder mpb, float[] a, float[] b, float[] c,
                            float nx, float ny, float nz, float uvScale) {
        MeshUtil.tri(mpb, a, b, c, nx, ny, nz, uvScale);
    }

    private static Vector3 faceNormal(float[] a, float[] b, float[] c) {
        return MeshUtil.faceNormal(a, b, c);
    }

    private void addTri(float[] a, float[] b, float[] c) {
        collision.addTriangle(a[0], a[1], a[2], b[0], b[1], b[2], c[0], c[1], c[2]);
    }

    /** Twelve outward-facing triangles for an axis-aligned box. */
    private void collisionBox(float x0, float y0, float z0, float x1, float y1, float z1) {
        // top
        collision.addTriangle(x0, y1, z1, x1, y1, z1, x1, y1, z0);
        collision.addTriangle(x0, y1, z1, x1, y1, z0, x0, y1, z0);
        // bottom
        collision.addTriangle(x0, y0, z0, x1, y0, z0, x1, y0, z1);
        collision.addTriangle(x0, y0, z0, x1, y0, z1, x0, y0, z1);
        // +z
        collision.addTriangle(x0, y0, z1, x1, y0, z1, x1, y1, z1);
        collision.addTriangle(x0, y0, z1, x1, y1, z1, x0, y1, z1);
        // -z
        collision.addTriangle(x1, y0, z0, x0, y0, z0, x0, y1, z0);
        collision.addTriangle(x1, y0, z0, x0, y1, z0, x1, y1, z0);
        // +x
        collision.addTriangle(x1, y0, z1, x1, y0, z0, x1, y1, z0);
        collision.addTriangle(x1, y0, z1, x1, y1, z0, x1, y1, z1);
        // -x
        collision.addTriangle(x0, y0, z0, x0, y0, z1, x0, y1, z1);
        collision.addTriangle(x0, y0, z0, x0, y1, z1, x0, y1, z0);
    }
}
