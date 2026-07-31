package com.muamn.ashen.combat;

import com.badlogic.gdx.math.Vector3;

import com.muamn.ashen.entity.Stats;
import com.muamn.ashen.world.CharacterBody;

/** Anything that can swing a weapon or be hit by one. */
public interface Combatant {

    /** Hostile pairs only: 0 is the player's side, 1 is everything else. */
    int team();

    CharacterBody body();

    Stats stats();

    /** Heading in degrees; the model's front faces +Z at 0. */
    float facing();

    /** True during roll i-frames, or while already dying. */
    boolean invulnerable();

    /** True while holding guard. Only blocks within the front arc. */
    boolean blocking();

    /**
     * True during the brief window where an incoming parryable attack is
     * deflected instead of landing.
     */
    boolean parrying();

    /**
     * True while open to a critical: staggered out of a parried swing, and
     * waiting for someone to take the opening.
     */
    boolean riposteable();

    /** Called on the attacker when a victim parried its swing. */
    void onAttackParried(Combatant parrier);

    /** Applies a critical - a riposte or a backstab. Bypasses guard and poise. */
    void applyCritical(HitInfo hit);

    /** Weapon in hand, used for guard absorption and reach. */
    WeaponDef weapon();

    /**
     * Flat damage added on top of the weapon's, e.g. from a resin on the blade.
     * Defaulted so nothing that has no notion of buffs has to say it has none.
     */
    default float damageBonus() {
        return 0f;
    }

    /** Torso height point, used as the aim target and hit centre. */
    Vector3 hitCenter(Vector3 out);

    /** Radius of the hurt capsule. */
    float hitRadius();

    boolean dead();

    /** Applies an incoming hit that has already passed the hitbox test. */
    void applyHit(HitInfo hit);
}
