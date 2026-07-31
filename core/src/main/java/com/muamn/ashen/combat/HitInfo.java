package com.muamn.ashen.combat;

import com.badlogic.gdx.math.Vector3;

/** One resolved hit, handed to the victim. */
public class HitInfo {

    public Combatant attacker;
    /** Damage before the victim's guard and defences. */
    public float damage;
    /** Poise damage; when a victim's accumulated poise breaks, it staggers. */
    public float poise;
    /** Direction from attacker to victim, normalised, for knockback and arcs. */
    public final Vector3 direction = new Vector3();
    /** Where the hit landed, for effects. */
    public final Vector3 point = new Vector3();
    /** True for ripostes and backstabs. */
    public boolean critical;

    /** Set by the victim so the attacker can react (sparks, no stamina refund). */
    public boolean wasBlocked;
    /** Set by the victim when the hit broke its guard or poise. */
    public boolean staggered;

    public HitInfo set(Combatant attacker, float damage, float poise) {
        this.attacker = attacker;
        this.damage = damage;
        this.poise = poise;
        this.critical = false;
        this.wasBlocked = false;
        this.staggered = false;
        return this;
    }
}
