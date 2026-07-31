package com.muamn.ashen.entity;

import com.badlogic.gdx.graphics.Color;

/**
 * How an enemy is built, as data.
 *
 * A preset plus a handful of overrides rather than every field of
 * {@link HumanoidSpec} and {@link CreatureSpec} spelled out in JSON. Twenty
 * enemies each need a different silhouette, not a different rig, so the parts
 * worth varying per enemy are scale, bulk, posture, materials and tint - and
 * those are exactly what is exposed here.
 */
public class BodyDef {

    public enum Kind {
        /** Two arms, carries a weapon. Uses {@link HumanoidFactory}. */
        HUMANOID,
        /** Legs and a body plan. Uses {@link CreatureFactory}. */
        CREATURE,
        /** An imported model, animated by its own exported clips. */
        IMPORTED
    }

    public Kind kind = Kind.HUMANOID;

    /**
     * Preset name within the kind. Humanoids: {@code knight} or {@code hollow}.
     * Creatures: {@code hound}, {@code spider}, {@code bat}, {@code serpent},
     * {@code drake}, {@code maggot}.
     */
    public String preset = "hollow";

    /** Imported model name, for {@link Kind#IMPORTED}. */
    public String model;

    public float scale = 1f;
    public float bulk = 1f;
    public float hunch;
    public float armLength = 1f;

    // Humanoid materials.
    public String armor;
    public String cloth;
    public String skin;
    public String trim;
    public Boolean helmet;
    public Boolean tabard;
    public Boolean pauldrons;

    // Creature materials.
    public String bodyMaterial;
    public String limbMaterial;
    public String detailMaterial;
    /** Overrides the preset's leg pair count when positive. */
    public int legPairs = -1;

    public final Color tint = new Color(Color.WHITE);

    /** Applies the humanoid overrides onto a preset spec. */
    public HumanoidSpec toHumanoid() {
        HumanoidSpec spec = "knight".equals(preset)
                ? HumanoidSpec.knight() : HumanoidSpec.hollow();
        spec.scale *= scale;
        spec.bulk *= bulk;
        if (hunch != 0f) spec.hunch = hunch;
        spec.armLength = armLength;
        if (armor != null) spec.armorMaterial = armor;
        if (cloth != null) spec.clothMaterial = cloth;
        if (skin != null) spec.skinMaterial = skin;
        if (trim != null) spec.trimMaterial = trim;
        if (helmet != null) spec.helmet = helmet;
        if (tabard != null) spec.tabard = tabard;
        if (pauldrons != null) spec.pauldrons = pauldrons;
        spec.tint.set(tint);
        return spec;
    }

    /** Applies the creature overrides onto a preset spec. */
    public CreatureSpec toCreature() {
        CreatureSpec spec;
        switch (preset == null ? "" : preset.toLowerCase()) {
            case "spider":  spec = CreatureSpec.spider(); break;
            case "bat":     spec = CreatureSpec.bat(); break;
            case "serpent": spec = CreatureSpec.serpent(); break;
            case "drake":   spec = CreatureSpec.drake(); break;
            case "maggot":  spec = CreatureSpec.maggot(); break;
            default:        spec = CreatureSpec.hound(); break;
        }
        spec.overallScale = scale;
        if (legPairs >= 0) spec.legPairs = legPairs;
        if (bodyMaterial != null) spec.bodyMaterial = bodyMaterial;
        if (limbMaterial != null) spec.limbMaterial = limbMaterial;
        if (detailMaterial != null) spec.detailMaterial = detailMaterial;
        spec.tint.set(tint);
        return spec;
    }
}
