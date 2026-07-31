package com.muamn.ashen.combat;

/**
 * One attack's frame data.
 *
 * A Souls attack is three windows, and the whole feel of the combat lives in
 * their ratio: a long windup makes an attack readable, a long recovery makes
 * throwing it out a decision rather than a reflex. The hitbox only exists during
 * {@link #active}.
 */
public class AttackDef {

    public enum Motion {
        /** Horizontal sweep; hits everything in the arc. */
        SWING_H,
        /** Overhead chop; narrow but lands with more poise damage. */
        SWING_V,
        /** Straight stab; long reach, almost no arc. */
        THRUST
    }

    public final String id;
    public final Motion motion;

    /** Seconds before the hitbox opens. */
    public final float windup;
    /** Seconds the hitbox stays live. */
    public final float active;
    /** Seconds locked in place afterwards. */
    public final float recovery;

    /** Motion value: multiplies the weapon's base damage. */
    public final float damage;
    /** Poise damage dealt to whatever it hits. */
    public final float poise;
    public final float staminaCost;

    /** Hitbox length from the hand, in metres. */
    public final float reach;
    /** Degrees the hitbox sweeps through, centred on the attacker's facing. */
    public final float arc;
    /** Metres the attacker slides forward across the swing. */
    public final float step;

    /**
     * Whether a parry can catch this attack.
     *
     * Heavy attacks are not parryable, which is what stops parrying from being a
     * universal answer - against a committed overhead you have to roll.
     */
    public final boolean parryable;

    public AttackDef(String id, Motion motion, float windup, float active, float recovery,
                     float damage, float poise, float staminaCost,
                     float reach, float arc, float step) {
        this(id, motion, windup, active, recovery, damage, poise, staminaCost,
                reach, arc, step, true);
    }

    public AttackDef(String id, Motion motion, float windup, float active, float recovery,
                     float damage, float poise, float staminaCost,
                     float reach, float arc, float step, boolean parryable) {
        this.id = id;
        this.motion = motion;
        this.windup = windup;
        this.active = active;
        this.recovery = recovery;
        this.damage = damage;
        this.poise = poise;
        this.staminaCost = staminaCost;
        this.reach = reach;
        this.arc = arc;
        this.step = step;
        this.parryable = parryable;
    }

    public float duration() {
        return windup + active + recovery;
    }

    public float activeStart() {
        return windup;
    }

    public float activeEnd() {
        return windup + active;
    }

    /** True while the hitbox is live at time {@code t} into the attack. */
    public boolean isActiveAt(float t) {
        return t >= windup && t < windup + active;
    }

    /**
     * How far through the swing the attack is, 0..1, used to place the hitbox
     * along its arc and to drive the pose.
     */
    public float swingProgress(float t) {
        if (t <= windup) return 0f;
        float span = active + recovery * 0.35f;
        return Math.min(1f, (t - windup) / Math.max(span, 1e-4f));
    }

    @Override
    public String toString() {
        return id + "(" + motion + " " + windup + "/" + active + "/" + recovery + ")";
    }
}
