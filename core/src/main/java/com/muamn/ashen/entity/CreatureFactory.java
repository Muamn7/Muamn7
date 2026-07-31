package com.muamn.ashen.entity;

import com.badlogic.gdx.graphics.GL20;
import com.badlogic.gdx.graphics.VertexAttributes.Usage;
import com.badlogic.gdx.graphics.g3d.Material;
import com.badlogic.gdx.graphics.g3d.Model;
import com.badlogic.gdx.graphics.g3d.attributes.ColorAttribute;
import com.badlogic.gdx.graphics.g3d.attributes.TextureAttribute;
import com.badlogic.gdx.graphics.g3d.model.Node;
import com.badlogic.gdx.graphics.g3d.utils.MeshPartBuilder;
import com.badlogic.gdx.graphics.g3d.utils.ModelBuilder;
import com.badlogic.gdx.math.MathUtils;
import com.badlogic.gdx.utils.GdxRuntimeException;

import com.muamn.ashen.world.AssetOverrides;
import com.muamn.ashen.world.MeshUtil;
import com.muamn.ashen.world.TextureFactory;

/**
 * Builds a jointed creature from a {@link CreatureSpec}.
 *
 * Same jointed-rigid-parts approach as {@link HumanoidFactory}, but the skeleton
 * is generated from the limb plan instead of being fixed, so one builder covers
 * every non-humanoid in the bestiary. Node names follow a pattern the animator
 * can walk without knowing what the creature is:
 *
 * <pre>
 *   root -> body -> neck -> head
 *                -> hipL0..n / hipR0..n -> kneeL0..n / kneeR0..n
 *                -> tail0..n
 *                -> wingL / wingR
 * </pre>
 */
public final class CreatureFactory {

    private static final long ATTRS = Usage.Position | Usage.Normal | Usage.TextureCoordinates;
    private static final float UV = 3.5f;

    private CreatureFactory() {}

    public static Model build(CreatureSpec spec, TextureFactory textures, String importName) {
        if (importName != null) {
            Model imported = AssetOverrides.loadModel(importName);
            if (imported != null) return imported;
        }
        return build(spec, textures);
    }

    public static Model build(CreatureSpec spec, TextureFactory textures) {
        final float s = spec.overallScale;
        Material body = material(textures, spec.bodyMaterial, spec);
        Material limb = material(textures, spec.limbMaterial, spec);
        Material detail = material(textures, spec.detailMaterial, spec);

        ModelBuilder mb = new ModelBuilder();
        mb.begin();

        // --- torso, built as two tapering halves so it reads as a spine ---
        node(mb, "body");
        MeshPartBuilder p = mb.part("torso", GL20.GL_TRIANGLES, ATTRS, body);
        float halfLen = spec.bodyLength * 0.5f * s;
        float w = spec.bodyWidth * s, h = spec.bodyHeight * s;
        // Authored along Z, the creature's forward axis.
        taperZ(p, -halfLen, 0f, w * spec.rearTaper, h * spec.rearTaper, w, h);
        taperZ(p, 0f, halfLen, w, h, w * 0.72f, h * 0.82f);

        if (spec.spines > 0) {
            p = mb.part("spines", GL20.GL_TRIANGLES, ATTRS, detail);
            for (int i = 0; i < spec.spines; i++) {
                float t = (i + 0.5f) / spec.spines;
                float z = MathUtils.lerp(-halfLen * 0.9f, halfLen * 0.7f, t);
                float height = h * (0.35f + 0.35f * MathUtils.sin(t * MathUtils.PI));
                MeshUtil.blade(p, 0f, h * 0.48f, z, height, w * 0.16f, w * 0.06f, 0.7f, UV);
            }
        }

        // --- neck and head ---
        if (spec.head) {
            node(mb, "neck");
            p = mb.part("neck", GL20.GL_TRIANGLES, ATTRS, body);
            taperZ(p, 0f, spec.neckLength * s, w * 0.55f, h * 0.55f, w * 0.44f, h * 0.48f);

            node(mb, "head");
            p = mb.part("skull", GL20.GL_TRIANGLES, ATTRS, body);
            float hl = spec.headLength * s, hw = spec.headWidth * s;
            taperZ(p, 0f, hl * 0.55f, hw * 0.75f, hw * 0.70f, hw, hw * 0.85f);
            taperZ(p, hl * 0.55f, hl, hw, hw * 0.85f, hw * 0.40f, hw * 0.34f);

            if (spec.fangs > 0) {
                p = mb.part("fangs", GL20.GL_TRIANGLES, ATTRS, detail);
                for (int i = 0; i < spec.fangs; i++) {
                    float a = -1f + 2f * (i + 0.5f) / spec.fangs;
                    // Fangs point forward along +Z, so build them along Y and lay
                    // them down by authoring the taper directly.
                    fang(p, a * hw * 0.34f, -hw * 0.18f, hl * 0.72f, hw * 0.10f, hl * 0.34f);
                }
            }
        }

        // --- legs ---
        for (int pair = 0; pair < spec.legPairs; pair++) {
            for (int side = 0; side < 2; side++) {
                String suffix = (side == 0 ? "L" : "R") + pair;
                float thigh = spec.legLength * spec.thighFraction * s;
                float shin = spec.legLength * (1f - spec.thighFraction) * s;

                node(mb, "hip" + suffix);
                p = mb.part("thigh" + suffix, GL20.GL_TRIANGLES, ATTRS, limb);
                MeshUtil.taper(p, 0f, 0f, -thigh, 0f,
                        spec.legThickness * 0.8f * s, spec.legThickness * 0.8f * s,
                        spec.legThickness * s, spec.legThickness * s, UV);

                node(mb, "knee" + suffix);
                p = mb.part("shin" + suffix, GL20.GL_TRIANGLES, ATTRS, limb);
                MeshUtil.taper(p, 0f, 0f, -shin, 0f,
                        spec.legThickness * 0.5f * s, spec.legThickness * 0.5f * s,
                        spec.legThickness * 0.85f * s, spec.legThickness * 0.85f * s, UV);
                p = mb.part("foot" + suffix, GL20.GL_TRIANGLES, ATTRS, detail);
                MeshUtil.box(p, 0f, -shin + spec.legThickness * 0.3f * s,
                        spec.legThickness * 0.6f * s,
                        spec.legThickness * 1.1f * s, spec.legThickness * 0.6f * s,
                        spec.legThickness * 2.2f * s, UV);
            }
        }

        // --- tail ---
        if (spec.tail) {
            float segment = spec.tailLength * s / Math.max(1, spec.tailSegments);
            for (int i = 0; i < spec.tailSegments; i++) {
                node(mb, "tail" + i);
                float t0 = i / (float) spec.tailSegments;
                float t1 = (i + 1) / (float) spec.tailSegments;
                p = mb.part("tailSeg" + i, GL20.GL_TRIANGLES, ATTRS, body);
                taperZ(p, -segment, 0f,
                        w * 0.30f * (1f - t1), h * 0.30f * (1f - t1),
                        w * 0.30f * (1f - t0), h * 0.30f * (1f - t0));
            }
        }

        // --- wings ---
        if (spec.wings) {
            for (int side = 0; side < 2; side++) {
                String suffix = side == 0 ? "L" : "R";
                float dir = side == 0 ? 1f : -1f;
                node(mb, "wing" + suffix);
                p = mb.part("wing" + suffix, GL20.GL_TRIANGLES, ATTRS, limb);
                float span = spec.wingSpan * 0.5f * s;
                // A thin membrane plus a leading-edge spar.
                MeshUtil.box(p, dir * span * 0.5f, 0f, -span * 0.10f,
                        span, h * 0.06f, span * 0.85f, UV);
                MeshUtil.taper(p, dir * span * 0.5f, span * 0.34f, -h * 0.05f, h * 0.05f,
                        span * 0.98f, h * 0.10f, span * 0.98f, h * 0.10f, UV);
            }
        }

        // A grip node, so a creature can carry a weapon if its def gives it one.
        node(mb, "weapon");
        p = mb.part("gripmark", GL20.GL_TRIANGLES, ATTRS, detail);
        MeshUtil.box(p, 0f, 0f, 0f, 0.001f, 0.001f, 0.001f, 1f);

        Model model = mb.end();
        assemble(model, spec, s);
        return model;
    }

    /** Wires the flat node list into the skeleton and places every joint. */
    private static void assemble(Model model, CreatureSpec spec, float s) {
        float halfLen = spec.bodyLength * 0.5f * s;
        float ride = spec.rideHeight * s;
        float h = spec.bodyHeight * s;

        if (spec.head) {
            reparent(model, "neck", "body", 0f, h * 0.18f, halfLen * 0.92f);
            reparent(model, "head", "neck", 0f, spec.neckRise * s, spec.neckLength * s);
        }

        for (int pair = 0; pair < spec.legPairs; pair++) {
            // Spread the pairs evenly along the torso, front pair furthest forward.
            float t = spec.legPairs == 1 ? 0.5f : pair / (float) (spec.legPairs - 1);
            float z = MathUtils.lerp(halfLen * 0.72f, -halfLen * 0.72f, t);
            for (int side = 0; side < 2; side++) {
                String suffix = (side == 0 ? "L" : "R") + pair;
                float dir = side == 0 ? 1f : -1f;
                reparent(model, "hip" + suffix, "body",
                        dir * spec.legSpread * s, -h * 0.30f, z);
                reparent(model, "knee" + suffix, "hip" + suffix,
                        0f, -spec.legLength * spec.thighFraction * s, 0f);
            }
        }

        if (spec.tail) {
            float segment = spec.tailLength * s / Math.max(1, spec.tailSegments);
            reparent(model, "tail0", "body", 0f, h * 0.10f, -halfLen);
            for (int i = 1; i < spec.tailSegments; i++) {
                reparent(model, "tail" + i, "tail" + (i - 1), 0f, 0f, -segment);
            }
        }

        if (spec.wings) {
            reparent(model, "wingL", "body", spec.bodyWidth * 0.4f * s, h * 0.35f, 0f);
            reparent(model, "wingR", "body", -spec.bodyWidth * 0.4f * s, h * 0.35f, 0f);
        }

        reparent(model, "weapon", "head", 0f, 0f, spec.headLength * 0.6f * s);

        Node body = model.getNode("body", true);
        body.translation.set(0f, ride, 0f);
        model.calculateTransforms();
    }

    // ---- geometry helpers -------------------------------------------------

    /**
     * A tapering box running along Z rather than Y.
     *
     * {@link MeshUtil#taper} builds along Y because limbs hang; a torso, neck and
     * tail all run forward, so this swaps the axes rather than rotating nodes.
     */
    private static void taperZ(MeshPartBuilder p, float z0, float z1,
                               float w0, float h0, float w1, float h1) {
        float[][] a = {
                {-w0 * 0.5f, -h0 * 0.5f, z0}, {w0 * 0.5f, -h0 * 0.5f, z0},
                {w0 * 0.5f, h0 * 0.5f, z0}, {-w0 * 0.5f, h0 * 0.5f, z0}};
        float[][] b = {
                {-w1 * 0.5f, -h1 * 0.5f, z1}, {w1 * 0.5f, -h1 * 0.5f, z1},
                {w1 * 0.5f, h1 * 0.5f, z1}, {-w1 * 0.5f, h1 * 0.5f, z1}};
        for (int i = 0; i < 4; i++) {
            int j = (i + 1) % 4;
            com.badlogic.gdx.math.Vector3 n = MeshUtil.faceNormal(a[i], b[i], b[j]);
            MeshUtil.quad(p, a[i][0], a[i][1], a[i][2], b[i][0], b[i][1], b[i][2],
                    b[j][0], b[j][1], b[j][2], a[j][0], a[j][1], a[j][2],
                    n.x, n.y, n.z, Math.abs(z1 - z0) * UV, 0.5f * UV);
        }
        // Caps.
        MeshUtil.quad(p, b[0][0], b[0][1], b[0][2], b[1][0], b[1][1], b[1][2],
                b[2][0], b[2][1], b[2][2], b[3][0], b[3][1], b[3][2],
                0f, 0f, Math.signum(z1 - z0), w1 * UV, h1 * UV);
        MeshUtil.quad(p, a[3][0], a[3][1], a[3][2], a[2][0], a[2][1], a[2][2],
                a[1][0], a[1][1], a[1][2], a[0][0], a[0][1], a[0][2],
                0f, 0f, -Math.signum(z1 - z0), w0 * UV, h0 * UV);
    }

    /** A tooth: a small spike pointing forward along +Z. */
    private static void fang(MeshPartBuilder p, float x, float y, float z,
                             float radius, float length) {
        float[][] base = {
                {x - radius, y - radius, z}, {x + radius, y - radius, z},
                {x + radius, y + radius, z}, {x - radius, y + radius, z}};
        float[] tip = {x, y, z + length};
        for (int i = 0; i < 4; i++) {
            int j = (i + 1) % 4;
            com.badlogic.gdx.math.Vector3 n = MeshUtil.faceNormal(base[i], base[j], tip);
            MeshUtil.tri(p, base[i], base[j], tip, n.x, n.y, n.z, UV);
        }
    }

    private static void node(ModelBuilder mb, String id) {
        Node n = mb.node();
        n.id = id;
    }

    private static Material material(TextureFactory textures, String name, CreatureSpec spec) {
        return new Material(TextureAttribute.createDiffuse(textures.get(name)),
                ColorAttribute.createDiffuse(spec.tint));
    }

    private static void reparent(Model model, String childId, String parentId,
                                 float x, float y, float z) {
        Node child = model.getNode(childId, true);
        Node parent = model.getNode(parentId, true);
        if (child == null || parent == null) {
            throw new GdxRuntimeException("creature rig missing node: "
                    + childId + " / " + parentId);
        }
        model.nodes.removeValue(child, true);
        parent.addChild(child);
        child.translation.set(x, y, z);
    }
}
