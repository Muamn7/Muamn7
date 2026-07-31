package com.muamn.ashen.combat;

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

import com.muamn.ashen.world.AssetOverrides;
import com.muamn.ashen.world.MeshUtil;
import com.muamn.ashen.world.TextureFactory;

/**
 * Builds a weapon's model from its {@link WeaponDef}.
 *
 * Every weapon is authored with its grip at the origin and its length running
 * along +Y, so the rig can hold any of them from the same hand node and the
 * hitbox can be derived from the same two points.
 *
 * An imported model named {@code weapon_<id>} takes precedence, which is how a
 * downloaded axe slots in beside fifteen generated ones.
 */
public final class WeaponFactory {

    private static final long ATTRS = Usage.Position | Usage.Normal | Usage.TextureCoordinates;
    private static final float UV = 6f;

    private WeaponFactory() {}

    public static Model build(WeaponDef def, TextureFactory textures) {
        Model imported = AssetOverrides.loadModel("weapon_" + def.id);
        if (imported != null) return imported;

        Material blade = material(textures, def.bladeMaterial);
        Material grip = material(textures, def.gripMaterial);
        Material trim = material(textures, "gold");

        ModelBuilder mb = new ModelBuilder();
        mb.begin();
        switch (def.modelKind) {
            case CURVED:  curved(mb, def, blade, grip, trim); break;
            case AXE:     axe(mb, def, blade, grip, trim); break;
            case MACE:    mace(mb, def, blade, grip, trim); break;
            case SPEAR:   spear(mb, def, blade, grip, trim); break;
            case HALBERD: halberd(mb, def, blade, grip, trim); break;
            case BOW:     bow(mb, def, blade, grip); break;
            case STAFF:   staff(mb, def, blade, grip, trim); break;
            default:      sword(mb, def, blade, grip, trim); break;
        }
        return mb.end();
    }

    // ---- shapes -----------------------------------------------------------

    private static void sword(ModelBuilder mb, WeaponDef d, Material blade,
                              Material grip, Material trim) {
        float gripLen = MathUtils.clamp(d.length * 0.16f, 0.10f, 0.34f);
        handle(mb, d, grip, trim, gripLen);

        MeshPartBuilder p = mb.part("guard", GL20.GL_TRIANGLES, ATTRS, trim);
        MeshUtil.box(p, 0f, gripLen, 0f, d.guardWidth, d.thickness * 2.2f, d.thickness * 3f, UV);

        p = mb.part("blade", GL20.GL_TRIANGLES, ATTRS, blade);
        MeshUtil.blade(p, 0f, gripLen + d.thickness, 0f,
                d.length - gripLen, d.width, d.thickness, 0.16f, UV);
    }

    /**
     * A curved blade, built as a stack of slightly offset segments. Cheap, and
     * the faceting it produces is exactly right for the era.
     */
    private static void curved(ModelBuilder mb, WeaponDef d, Material blade,
                               Material grip, Material trim) {
        float gripLen = MathUtils.clamp(d.length * 0.15f, 0.10f, 0.30f);
        handle(mb, d, grip, trim, gripLen);

        MeshPartBuilder p = mb.part("guard", GL20.GL_TRIANGLES, ATTRS, trim);
        MeshUtil.box(p, 0f, gripLen, 0f, d.guardWidth, d.thickness * 2f, d.thickness * 2.6f, UV);

        p = mb.part("blade", GL20.GL_TRIANGLES, ATTRS, blade);
        int segments = 7;
        float bladeLen = d.length - gripLen;
        float y = gripLen + d.thickness;
        for (int i = 0; i < segments; i++) {
            float t0 = i / (float) segments, t1 = (i + 1) / (float) segments;
            float y0 = y + bladeLen * t0, y1 = y + bladeLen * t1;
            // Offset grows with the square of progress, so the tip curves most.
            float x0 = d.curve * t0 * t0, x1 = d.curve * t1 * t1;
            float w0 = d.width * (1f - 0.25f * t0), w1 = d.width * (1f - 0.25f * t1);
            MeshUtil.taper(p, (x0 + x1) * 0.5f, 0f, y0, y1, w0, d.thickness, w1, d.thickness, UV);
        }
        MeshUtil.blade(p, d.curve, y + bladeLen, 0f,
                bladeLen * 0.16f, d.width * 0.75f, d.thickness, 1f, UV);
    }

    private static void axe(ModelBuilder mb, WeaponDef d, Material blade,
                            Material grip, Material trim) {
        MeshPartBuilder p = mb.part("haft", GL20.GL_TRIANGLES, ATTRS, grip);
        MeshUtil.prism(p, 0f, 0f, 0f, d.haft, d.length, 6, UV);

        p = mb.part("head", GL20.GL_TRIANGLES, ATTRS, blade);
        float top = d.length;
        // Wedge: thick at the haft, thin at the cutting edge.
        MeshUtil.taper(p, d.headWidth * 0.42f, 0f, top - d.headDepth * 1.5f, top,
                d.headWidth * 0.85f, d.headDepth, d.headWidth * 0.35f, d.headDepth * 0.35f, UV);
        MeshUtil.box(p, 0f, top - d.headDepth * 0.75f, 0f,
                d.haft * 2.4f, d.headDepth * 1.6f, d.haft * 2.4f, UV);

        p = mb.part("cap", GL20.GL_TRIANGLES, ATTRS, trim);
        MeshUtil.prism(p, 0f, -0.03f, 0f, d.haft * 1.35f, 0.05f, 6, UV);
    }

    private static void mace(ModelBuilder mb, WeaponDef d, Material blade,
                             Material grip, Material trim) {
        MeshPartBuilder p = mb.part("haft", GL20.GL_TRIANGLES, ATTRS, grip);
        MeshUtil.prism(p, 0f, 0f, 0f, d.haft, d.length, 6, UV);

        p = mb.part("head", GL20.GL_TRIANGLES, ATTRS, blade);
        float top = d.length - d.headRadius * 2f;
        MeshUtil.taper(p, 0f, 0f, top, top + d.headRadius * 0.7f,
                d.headRadius * 1.1f, d.headRadius * 1.1f, d.headRadius * 2f, d.headRadius * 2f, UV);
        MeshUtil.taper(p, 0f, 0f, top + d.headRadius * 0.7f, top + d.headRadius * 2f,
                d.headRadius * 2f, d.headRadius * 2f, d.headRadius * 0.9f, d.headRadius * 0.9f, UV);

        p = mb.part("studs", GL20.GL_TRIANGLES, ATTRS, trim);
        for (int i = 0; i < 6; i++) {
            float a = i * 60f;
            MeshUtil.box(p, MathUtils.cosDeg(a) * d.headRadius, top + d.headRadius * 0.75f,
                    MathUtils.sinDeg(a) * d.headRadius,
                    d.headRadius * 0.5f, d.headRadius * 0.5f, d.headRadius * 0.5f, UV);
        }
    }

    private static void spear(ModelBuilder mb, WeaponDef d, Material blade,
                              Material grip, Material trim) {
        MeshPartBuilder p = mb.part("haft", GL20.GL_TRIANGLES, ATTRS, grip);
        MeshUtil.prism(p, 0f, 0f, 0f, d.haft, d.length - d.headLength, 6, UV);

        p = mb.part("head", GL20.GL_TRIANGLES, ATTRS, blade);
        MeshUtil.blade(p, 0f, d.length - d.headLength, 0f,
                d.headLength, d.haft * 2.6f, d.haft * 1.1f, 0.55f, UV);

        p = mb.part("collar", GL20.GL_TRIANGLES, ATTRS, trim);
        MeshUtil.prism(p, 0f, d.length - d.headLength - 0.05f, 0f, d.haft * 1.5f, 0.06f, 6, UV);
    }

    private static void halberd(ModelBuilder mb, WeaponDef d, Material blade,
                                Material grip, Material trim) {
        MeshPartBuilder p = mb.part("haft", GL20.GL_TRIANGLES, ATTRS, grip);
        MeshUtil.prism(p, 0f, 0f, 0f, d.haft, d.length * 0.86f, 6, UV);

        p = mb.part("head", GL20.GL_TRIANGLES, ATTRS, blade);
        float top = d.length * 0.86f;
        // Axe blade on one side, a spike on the other, point on top.
        MeshUtil.taper(p, d.headWidth * 0.5f, 0f, top - 0.28f, top - 0.02f,
                d.headWidth * 0.9f, 0.05f, d.headWidth * 0.4f, 0.03f, UV);
        MeshUtil.taper(p, -d.headWidth * 0.32f, 0f, top - 0.22f, top - 0.06f,
                d.headWidth * 0.5f, 0.05f, d.headWidth * 0.14f, 0.03f, UV);
        MeshUtil.blade(p, 0f, top - 0.02f, 0f, d.length * 0.14f, d.haft * 2.2f, d.haft, 0.6f, UV);
    }

    private static void bow(ModelBuilder mb, WeaponDef d, Material blade, Material grip) {
        MeshPartBuilder p = mb.part("limbs", GL20.GL_TRIANGLES, ATTRS, blade);
        int segments = 8;
        float half = d.length * 0.5f;
        for (int i = 0; i < segments; i++) {
            for (int side = -1; side <= 1; side += 2) {
                float t0 = i / (float) segments, t1 = (i + 1) / (float) segments;
                float y0 = half + side * half * t0, y1 = half + side * half * t1;
                // Bow belly curves away from the string.
                float z0 = -0.10f * (1f - t0 * t0), z1 = -0.10f * (1f - t1 * t1);
                MeshUtil.taper(p, 0f, (z0 + z1) * 0.5f, Math.min(y0, y1), Math.max(y0, y1),
                        d.thickness * 1.6f, d.thickness, d.thickness * 1.2f, d.thickness, UV);
            }
        }
        p = mb.part("grip", GL20.GL_TRIANGLES, ATTRS, grip);
        MeshUtil.box(p, 0f, half, -0.10f, d.thickness * 2.2f, d.length * 0.16f,
                d.thickness * 2.4f, UV);
        // The string, as a thin taut box.
        p = mb.part("string", GL20.GL_TRIANGLES, ATTRS, grip);
        MeshUtil.taper(p, 0f, 0f, 0.02f, d.length - 0.02f, 0.008f, 0.008f, 0.008f, 0.008f, UV);
    }

    private static void staff(ModelBuilder mb, WeaponDef d, Material blade,
                              Material grip, Material trim) {
        MeshPartBuilder p = mb.part("haft", GL20.GL_TRIANGLES, ATTRS, grip);
        MeshUtil.prism(p, 0f, 0f, 0f, d.haft, d.length - d.headRadius * 2f, 6, UV);

        p = mb.part("crown", GL20.GL_TRIANGLES, ATTRS, trim);
        float top = d.length - d.headRadius * 2f;
        MeshUtil.taper(p, 0f, 0f, top, top + d.headRadius * 0.6f,
                d.haft * 1.2f, d.haft * 1.2f, d.headRadius * 1.4f, d.headRadius * 1.4f, UV);

        // The focus stone reads as lit, so it stands out in a dim level.
        Material glow = new Material(ColorAttribute.createDiffuse(new Color(0.55f, 0.72f, 1f, 1f)),
                ColorAttribute.createEmissive(0.85f, 0.85f, 0.85f, 1f));
        p = mb.part("stone", GL20.GL_TRIANGLES, ATTRS, glow);
        MeshUtil.taper(p, 0f, 0f, top + d.headRadius * 0.5f, top + d.headRadius * 1.9f,
                d.headRadius * 1.1f, d.headRadius * 1.1f, d.headRadius * 0.3f, d.headRadius * 0.3f, UV);
    }

    /** Grip and pommel, shared by the bladed weapons. */
    private static void handle(ModelBuilder mb, WeaponDef d, Material grip,
                               Material trim, float gripLen) {
        MeshPartBuilder p = mb.part("grip", GL20.GL_TRIANGLES, ATTRS, grip);
        MeshUtil.taper(p, 0f, 0f, 0f, gripLen,
                d.thickness * 1.9f, d.thickness * 1.9f, d.thickness * 1.7f, d.thickness * 1.7f, UV);

        p = mb.part("pommel", GL20.GL_TRIANGLES, ATTRS, trim);
        MeshUtil.taper(p, 0f, 0f, -d.thickness * 2.2f, 0f,
                d.thickness * 1.5f, d.thickness * 1.5f, d.thickness * 2.4f, d.thickness * 2.4f, UV);
    }

    private static Material material(TextureFactory textures, String name) {
        return new Material(TextureAttribute.createDiffuse(textures.get(name)),
                ColorAttribute.createDiffuse(Color.WHITE));
    }
}
