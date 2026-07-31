package com.muamn.ashen.combat;

import com.badlogic.gdx.math.MathUtils;
import com.badlogic.gdx.math.Vector3;

/**
 * The pure functions behind a trade: whether a hit was blocked, what it costs to
 * block it, and whether it broke the victim's poise.
 *
 * Kept free of any engine state so the numbers can be unit tested - a game where
 * one point of poise decides whether you get to finish your swing cannot have
 * this logic buried in a frame update.
 */
public final class CombatMath {

    /** A guard covers this much of the front, in degrees. */
    public static final float GUARD_ARC = 120f;
    /** Attacks landing behind this arc count as backstabs. */
    public static final float BACKSTAB_ARC = 80f;
    /** How long a stagger lasts. */
    public static final float STAGGER_DURATION = 0.55f;
    /** Longer stagger when a guard is broken outright. */
    public static final float GUARD_BREAK_DURATION = 1.15f;
    /** Poise recovers fully this many seconds after the last hit. */
    public static final float POISE_RECOVERY = 2.4f;

    private CombatMath() {}

    /**
     * @param facingDeg  victim's heading
     * @param direction  attacker -> victim, normalised
     * @param arcDegrees total width of the front cone
     * @return true if the blow came at the victim's front
     */
    public static boolean isFrontal(float facingDeg, Vector3 direction, float arcDegrees) {
        float fx = MathUtils.sinDeg(facingDeg), fz = MathUtils.cosDeg(facingDeg);
        // direction points the way the blow travels, so a frontal hit opposes facing.
        float dot = -(direction.x * fx + direction.z * fz);
        return dot >= MathUtils.cosDeg(arcDegrees * 0.5f);
    }

    /** True when the attacker is behind the victim and roughly aligned with it. */
    public static boolean isBackstab(float victimFacing, float attackerFacing, Vector3 direction) {
        float fx = MathUtils.sinDeg(victimFacing), fz = MathUtils.cosDeg(victimFacing);
        float alongBack = direction.x * fx + direction.z * fz;
        if (alongBack < MathUtils.cosDeg(BACKSTAB_ARC * 0.5f)) return false;
        // Both must be facing the same way, or it is a shoulder barge, not a stab.
        float delta = Math.abs(angleDifference(victimFacing, attackerFacing));
        return delta <= 55f;
    }

    /** Signed smallest difference between two headings, in degrees. */
    public static float angleDifference(float a, float b) {
        return ((b - a) % 360f + 540f) % 360f - 180f;
    }

    /** Damage that gets through a successful block. */
    public static float damageThroughGuard(WeaponDef guard, float raw) {
        float absorb = MathUtils.clamp(guard == null ? 0.3f : guard.guardAbsorb, 0f, 0.95f);
        return raw * (1f - absorb);
    }

    /** Stamina a successful block costs. */
    public static float guardStamina(WeaponDef guard, float raw) {
        return guard == null ? raw * 0.5f : guard.guardStaminaCost(raw);
    }

    /**
     * Damage after armour. Absorption never reaches 100%, so nothing in the game
     * can be made immune by stacking defence.
     */
    public static float afterDefence(float raw, float absorption) {
        float clamped = MathUtils.clamp(absorption, 0f, 0.85f);
        return Math.max(raw * (1f - clamped), raw * 0.08f);
    }
}
