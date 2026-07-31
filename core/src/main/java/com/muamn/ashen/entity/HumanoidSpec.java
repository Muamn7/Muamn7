package com.muamn.ashen.entity;

import com.badlogic.gdx.graphics.Color;

/**
 * Describes one humanoid body so a single builder can produce the player, the
 * hollow soldiers, the knights and the larger bosses.
 *
 * Enemies in Part 3 are variations on these numbers rather than new models,
 * which is how a PS2-era game shipped twenty enemy types on one disc.
 */
public class HumanoidSpec {

    /** Overall size multiplier. 1.0 is a 1.75m human. */
    public float scale = 1f;
    /** Limb and torso thickness multiplier, independent of height. */
    public float bulk = 1f;
    /** Arm length multiplier; over 1 reads as inhuman. */
    public float armLength = 1f;
    /** Forward hunch in degrees, applied to the torso at rest. */
    public float hunch = 0f;

    public String armorMaterial = "iron";
    public String clothMaterial = "cloth_dark";
    public String skinMaterial = "skin_pale";
    public String trimMaterial = "leather";

    public Color tint = new Color(Color.WHITE);

    /** Draws a closed helm with a visor slit instead of a bare head. */
    public boolean helmet = true;
    /** Draws a hanging tabard over the hips. */
    public boolean tabard = true;
    /** Draws shoulder pauldrons. */
    public boolean pauldrons = true;

    public HumanoidSpec() {}

    public HumanoidSpec scale(float v) {
        this.scale = v;
        return this;
    }

    public HumanoidSpec bulk(float v) {
        this.bulk = v;
        return this;
    }

    public HumanoidSpec materials(String armor, String cloth, String skin, String trim) {
        this.armorMaterial = armor;
        this.clothMaterial = cloth;
        this.skinMaterial = skin;
        this.trimMaterial = trim;
        return this;
    }

    public HumanoidSpec tint(Color c) {
        this.tint.set(c);
        return this;
    }

    /** The player's default look: a battered knight in dark iron. */
    public static HumanoidSpec knight() {
        HumanoidSpec s = new HumanoidSpec();
        s.armorMaterial = "iron";
        s.clothMaterial = "cloth_red";
        s.trimMaterial = "leather";
        s.helmet = true;
        s.tabard = true;
        s.pauldrons = true;
        return s;
    }

    /** A hollowed soldier: thinner, hunched, no helmet, rotting skin. */
    public static HumanoidSpec hollow() {
        HumanoidSpec s = new HumanoidSpec();
        s.scale = 0.95f;
        s.bulk = 0.82f;
        s.hunch = 12f;
        s.armorMaterial = "leather";
        s.clothMaterial = "cloth_dark";
        s.skinMaterial = "flesh_rot";
        s.trimMaterial = "iron";
        s.helmet = false;
        s.pauldrons = false;
        return s;
    }
}
