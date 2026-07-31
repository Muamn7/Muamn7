package com.muamn.ashen.combat;

import com.badlogic.gdx.math.MathUtils;

import com.muamn.ashen.entity.Stats;

/**
 * One weapon: its numbers, its moveset, and how to build its model.
 *
 * Loaded from {@code assets/data/weapons.json} so the whole armoury can be
 * rebalanced without recompiling.
 */
public class WeaponDef {

    /** Shape family for the procedural weapon mesh. */
    public enum ModelKind { SWORD, CURVED, AXE, MACE, SPEAR, HALBERD, BOW, STAFF }

    public String id;
    public String nameAr;
    public String nameEn;
    public WeaponClass weaponClass;
    public Moveset moveset;

    public float weight;
    public float physical;
    /** Riposte and backstab damage, in percent. */
    public float critical = 100f;

    public int reqStrength, reqDexterity, reqIntelligence, reqFaith;
    public Scaling scaleStrength = Scaling.NONE;
    public Scaling scaleDexterity = Scaling.NONE;
    public Scaling scaleIntelligence = Scaling.NONE;
    public Scaling scaleFaith = Scaling.NONE;

    /** Fraction of incoming damage stopped when guarding with this weapon. */
    public float guardAbsorb = 0.35f;
    /** Fraction of the blocked damage that does NOT become stamina loss. */
    public float stability = 0.25f;

    // ---- model ----
    public ModelKind modelKind = ModelKind.SWORD;
    public float length = 1.0f;
    public float width = 0.09f;
    public float thickness = 0.02f;
    public float guardWidth = 0.30f;
    public float curve;
    public float headWidth, headDepth, headRadius, headLength, haft;
    public String bladeMaterial = "steel";
    public String gripMaterial = "leather";

    /** Upgrade level, +0 to +10. */
    public int upgrade;

    /** The longest reach in this weapon's moveset, for AI spacing and lock-on. */
    public float maxReach() {
        float max = 0f;
        for (AttackDef a : moveset.light) max = Math.max(max, a.reach);
        for (AttackDef a : moveset.heavy) max = Math.max(max, a.reach);
        max = Math.max(max, moveset.running.reach);
        return max;
    }

    /** Each upgrade level adds a flat slice of the base damage. */
    public float upgradedPhysical() {
        return physical * (1f + 0.085f * MathUtils.clamp(upgrade, 0, 10));
    }

    /** True when the wielder meets every attribute requirement. */
    public boolean meetsRequirements(Stats s) {
        return s.strength >= reqStrength && s.dexterity >= reqDexterity
                && s.intelligence >= reqIntelligence && s.faith >= reqFaith;
    }

    /**
     * Damage before the target's defences, for one attack.
     *
     * Scaling follows the genre's shape: each attribute contributes through a
     * saturating curve that is generous early and nearly flat past 40, so the
     * first ten points into a stat matter far more than the last ten. Wielding a
     * weapon you do not meet the requirements for keeps the base damage but
     * throws the scaling away and adds a flat penalty - painful, not impossible.
     */
    public float damageAgainst(Stats wielder, AttackDef attack) {
        float base = upgradedPhysical();
        boolean qualified = meetsRequirements(wielder);

        float bonus = 0f;
        if (qualified) {
            bonus += scaleStrength.multiplier * attributeCurve(wielder.strength);
            bonus += scaleDexterity.multiplier * attributeCurve(wielder.dexterity);
            bonus += scaleIntelligence.multiplier * attributeCurve(wielder.intelligence);
            bonus += scaleFaith.multiplier * attributeCurve(wielder.faith);
        }

        float damage = base * (1f + bonus) * attack.damage;
        if (!qualified) damage *= 0.55f;
        return damage;
    }

    /**
     * Maps an attribute to 0..1. Rises quickly to the soft cap at 40, then
     * crawls; 99 is worth only a little more than 40.
     */
    public static float attributeCurve(int attribute) {
        float a = MathUtils.clamp(attribute, 1, 99);
        if (a <= 40f) {
            float t = (a - 1f) / 39f;
            // Ease-out: early points are worth the most.
            return 1f - (1f - t) * (1f - t) * 0.85f - 0.15f * (1f - t);
        }
        return 1f + (a - 40f) / 59f * 0.18f;
    }

    /**
     * Stamina spent when this weapon blocks {@code damage}.
     *
     * Driven by stability alone. Absorption and stability are separate axes -
     * absorption decides how much damage gets through, stability decides how
     * much the block costs to hold. Folding absorption in here made a heavier
     * guard cost more stamina than a flimsy one, which is backwards.
     */
    public float guardStaminaCost(float damage) {
        return damage * (1f - MathUtils.clamp(stability, 0f, 0.95f)) * 0.55f;
    }

    public String displayName(boolean arabic) {
        String name = arabic ? nameAr : nameEn;
        return upgrade > 0 ? name + " +" + upgrade : name;
    }

    @Override
    public String toString() {
        return id + " +" + upgrade + " (" + weaponClass + ")";
    }
}
