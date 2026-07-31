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
import com.badlogic.gdx.utils.GdxRuntimeException;

import com.muamn.ashen.world.AssetOverrides;
import com.muamn.ashen.world.MeshUtil;
import com.muamn.ashen.world.TextureFactory;

/**
 * Builds a jointed humanoid model in code.
 *
 * Rather than skinned meshes, each body part is rigid geometry parented to a
 * joint node - exactly how characters were built in the PS1/PS2 era, before
 * hardware skinning was cheap. It costs nothing at runtime, animates from plain
 * node rotations (see {@link CharacterRig}), and every proportion is a number
 * we can vary per enemy type.
 *
 * Named nodes, all authored with their pivot at the joint:
 * <pre>
 *   hips -> torso -> head
 *                 -> shoulderL/R -> elbowL/R -> handL/R -> weapon
 *        -> hipL/R -> kneeL/R
 * </pre>
 */
public final class HumanoidFactory {

    private static final long ATTRS = Usage.Position | Usage.Normal | Usage.TextureCoordinates;
    /** Character textures are small, so tile them densely. */
    private static final float UV = 4f;

    private HumanoidFactory() {}

    /**
     * @param importName if a model of this name sits in {@code assets/imported/models}
     *                   it is used verbatim instead of the generated body.
     */
    public static Model build(HumanoidSpec spec, TextureFactory textures, String importName) {
        if (importName != null) {
            Model imported = AssetOverrides.loadModel(importName);
            if (imported != null) return imported;
        }
        return build(spec, textures);
    }

    public static Model build(HumanoidSpec spec, TextureFactory textures) {
        final float s = spec.scale;
        final float b = spec.bulk;

        // Skeleton lengths, in metres at scale 1.
        final float shinLen = 0.45f * s;
        final float thighLen = 0.47f * s;
        final float hipY = 0.92f * s;
        final float torsoLen = 0.53f * s;
        final float headLen = 0.26f * s;
        final float upperArm = 0.30f * s * spec.armLength;
        final float foreArm = 0.28f * s * spec.armLength;
        final float shoulderY = 0.46f * s;
        // Shoulders sit wider than the torso so the arms read as separate limbs
        // in silhouette - at this resolution, silhouette is all you get.
        final float shoulderX = 0.25f * s * b;
        final float hipX = 0.105f * s;

        Material armor = material(textures, spec.armorMaterial, spec);
        Material cloth = material(textures, spec.clothMaterial, spec);
        Material skin = material(textures, spec.skinMaterial, spec);
        Material trim = material(textures, spec.trimMaterial, spec);

        ModelBuilder mb = new ModelBuilder();
        mb.begin();

        // --- hips: an empty joint that everything hangs from ---
        node(mb, "hips");
        MeshPartBuilder p = mb.part("pelvis", GL20.GL_TRIANGLES, ATTRS, armor);
        MeshUtil.taper(p, 0f, 0f, -0.10f * s, 0.06f * s,
                0.30f * b * s, 0.20f * b * s, 0.32f * b * s, 0.21f * b * s, UV);

        // --- torso ---
        node(mb, "torso");
        p = mb.part("torso", GL20.GL_TRIANGLES, ATTRS, armor);
        MeshUtil.taper(p, 0f, 0f, 0f, torsoLen * 0.52f,
                0.28f * b * s, 0.19f * b * s, 0.33f * b * s, 0.21f * b * s, UV);
        MeshUtil.taper(p, 0f, 0f, torsoLen * 0.52f, torsoLen,
                0.33f * b * s, 0.21f * b * s, 0.30f * b * s, 0.18f * b * s, UV);
        // Breastplate ridge, so the chest catches light differently to the flanks.
        p = mb.part("plate", GL20.GL_TRIANGLES, ATTRS, trim);
        MeshUtil.taper(p, 0f, 0.10f * b * s, torsoLen * 0.14f, torsoLen * 0.80f,
                0.22f * b * s, 0.04f * s, 0.20f * b * s, 0.04f * s, UV);
        if (spec.tabard) {
            p = mb.part("tabard", GL20.GL_TRIANGLES, ATTRS, cloth);
            MeshUtil.taper(p, 0f, 0f, -0.34f * s, 0.10f * s,
                    0.30f * b * s, 0.05f * s, 0.26f * b * s, 0.05f * s, UV);
        }

        // --- head ---
        node(mb, "head");
        p = mb.part("neck", GL20.GL_TRIANGLES, ATTRS, skin);
        MeshUtil.taper(p, 0f, 0f, -0.03f * s, 0.05f * s,
                0.11f * s, 0.11f * s, 0.12f * s, 0.12f * s, UV);
        if (spec.helmet) {
            p = mb.part("helm", GL20.GL_TRIANGLES, ATTRS, armor);
            // Straight-sided skull, then a domed crown, then a short neck guard
            // flaring at the back - a great helm reads best as three stacked slabs.
            MeshUtil.taper(p, 0f, 0f, 0.03f * s, headLen * 0.60f,
                    0.19f * s, 0.21f * s, 0.20f * s, 0.23f * s, UV);
            MeshUtil.taper(p, 0f, 0f, headLen * 0.60f, headLen * 0.92f,
                    0.20f * s, 0.23f * s, 0.15f * s, 0.17f * s, UV);
            MeshUtil.taper(p, 0f, 0f, headLen * 0.92f, headLen * 1.06f,
                    0.15f * s, 0.17f * s, 0.05f * s, 0.06f * s, UV);
            MeshUtil.taper(p, 0f, -0.055f * s, 0.02f * s, 0.10f * s,
                    0.21f * s, 0.10f * s, 0.20f * s, 0.09f * s, UV);
            // Visor slit, proud of the face so it casts its own dark band.
            p = mb.part("visor", GL20.GL_TRIANGLES, ATTRS, cloth);
            MeshUtil.box(p, 0f, 0.155f * s, 0.116f * s, 0.145f * s, 0.030f * s, 0.022f * s, UV);
        } else {
            p = mb.part("head", GL20.GL_TRIANGLES, ATTRS, skin);
            MeshUtil.taper(p, 0f, 0f, 0.04f * s, headLen * 0.75f,
                    0.17f * s, 0.19f * s, 0.18f * s, 0.20f * s, UV);
            MeshUtil.taper(p, 0f, 0f, headLen * 0.75f, headLen,
                    0.18f * s, 0.20f * s, 0.09f * s, 0.10f * s, UV);
        }

        // --- arms ---
        for (int side = 0; side < 2; side++) {
            String sfx = side == 0 ? "L" : "R";
            float dir = side == 0 ? 1f : -1f;

            node(mb, "shoulder" + sfx);
            if (spec.pauldrons) {
                p = mb.part("pauldron" + sfx, GL20.GL_TRIANGLES, ATTRS, armor);
                MeshUtil.taper(p, dir * 0.02f * s, 0f, -0.06f * s, 0.07f * s,
                        0.20f * b * s, 0.24f * b * s, 0.16f * b * s, 0.20f * b * s, UV);
            }
            p = mb.part("upperarm" + sfx, GL20.GL_TRIANGLES, ATTRS, armor);
            MeshUtil.taper(p, 0f, 0f, -upperArm, 0f,
                    0.10f * b * s, 0.10f * b * s, 0.13f * b * s, 0.13f * b * s, UV);

            node(mb, "elbow" + sfx);
            p = mb.part("forearm" + sfx, GL20.GL_TRIANGLES, ATTRS, trim);
            MeshUtil.taper(p, 0f, 0f, -foreArm, 0f,
                    0.09f * b * s, 0.09f * b * s, 0.11f * b * s, 0.11f * b * s, UV);

            node(mb, "hand" + sfx);
            p = mb.part("hand" + sfx, GL20.GL_TRIANGLES, ATTRS, trim);
            MeshUtil.box(p, 0f, -0.045f * s, 0.01f * s,
                    0.09f * s, 0.11f * s, 0.10f * s, UV);
        }

        // --- legs ---
        for (int side = 0; side < 2; side++) {
            String sfx = side == 0 ? "L" : "R";

            node(mb, "hip" + sfx);
            p = mb.part("thigh" + sfx, GL20.GL_TRIANGLES, ATTRS, armor);
            MeshUtil.taper(p, 0f, 0f, -thighLen, 0f,
                    0.13f * b * s, 0.14f * b * s, 0.17f * b * s, 0.18f * b * s, UV);

            node(mb, "knee" + sfx);
            p = mb.part("shin" + sfx, GL20.GL_TRIANGLES, ATTRS, armor);
            MeshUtil.taper(p, 0f, 0f, -shinLen, 0f,
                    0.11f * b * s, 0.12f * b * s, 0.13f * b * s, 0.14f * b * s, UV);
            p = mb.part("foot" + sfx, GL20.GL_TRIANGLES, ATTRS, trim);
            MeshUtil.box(p, 0f, -shinLen + 0.035f * s, 0.045f * s,
                    0.13f * s, 0.07f * s, 0.26f * s, UV);
        }

        // A bare joint the weapon model is attached to at runtime.
        node(mb, "weapon");
        p = mb.part("gripmark", GL20.GL_TRIANGLES, ATTRS, trim);
        MeshUtil.box(p, 0f, 0f, 0f, 0.001f, 0.001f, 0.001f, 1f);

        Model model = mb.end();

        // ModelBuilder can only make siblings, so build the hierarchy afterwards.
        reparent(model, "torso", "hips", 0f, 0f, 0f);
        reparent(model, "head", "torso", 0f, torsoLen, 0f);

        reparent(model, "shoulderL", "torso", shoulderX, shoulderY, 0f);
        reparent(model, "shoulderR", "torso", -shoulderX, shoulderY, 0f);
        reparent(model, "elbowL", "shoulderL", 0f, -upperArm, 0f);
        reparent(model, "elbowR", "shoulderR", 0f, -upperArm, 0f);
        reparent(model, "handL", "elbowL", 0f, -foreArm, 0f);
        reparent(model, "handR", "elbowR", 0f, -foreArm, 0f);
        reparent(model, "weapon", "handR", 0f, -0.06f * s, 0.03f * s);

        reparent(model, "hipL", "hips", hipX, 0f, 0f);
        reparent(model, "hipR", "hips", -hipX, 0f, 0f);
        reparent(model, "kneeL", "hipL", 0f, -thighLen, 0f);
        reparent(model, "kneeR", "hipR", 0f, -thighLen, 0f);

        Node hips = model.getNode("hips", false);
        hips.translation.set(0f, hipY, 0f);
        model.calculateTransforms();
        return model;
    }

    private static void node(ModelBuilder mb, String id) {
        Node n = mb.node();
        n.id = id;
    }

    private static Material material(TextureFactory textures, String name, HumanoidSpec spec) {
        return new Material(
                TextureAttribute.createDiffuse(textures.get(name)),
                ColorAttribute.createDiffuse(spec.tint));
    }

    /** Moves a root node under a parent and sets its joint offset. */
    private static void reparent(Model model, String childId, String parentId,
                                 float x, float y, float z) {
        Node child = model.getNode(childId, true);
        Node parent = model.getNode(parentId, true);
        if (child == null || parent == null) {
            throw new GdxRuntimeException("humanoid rig missing node: " + childId + " / " + parentId);
        }
        model.nodes.removeValue(child, true);
        parent.addChild(child);
        child.translation.set(x, y, z);
    }
}
