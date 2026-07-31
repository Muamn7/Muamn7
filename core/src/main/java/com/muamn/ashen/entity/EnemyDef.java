package com.muamn.ashen.entity;

/**
 * An enemy archetype, loaded from {@code assets/data/enemies.json}.
 *
 * The timings here are the difficulty dial. {@code alertDelay}, {@code circleTime}
 * and {@code recoverTime} decide how much room a player gets to act, and they
 * matter far more than health or damage - a fast enemy with a long recovery is
 * fair; a slow one with none is not.
 */
public class EnemyDef {

    public String id = "hollow";
    public String nameAr = "جوّاف";
    public String nameEn = "Hollow";

    public float health = 260f;
    public long souls = 120L;
    public float poise = 26f;
    /** Fraction of incoming damage absorbed. */
    public float absorption = 0.05f;

    public int strength = 12;
    public int dexterity = 12;

    public float radius = 0.34f;
    public float height = 1.75f;

    public float walkSpeed = 1.8f;
    public float runSpeed = 4.0f;
    /** Degrees per second. */
    public float turnSpeed = 260f;
    /** Multiplier on the attack's built-in forward step. */
    public float stepScale = 1f;

    public float aggroRange = 12f;
    public float leashRange = 26f;

    /** Pause after noticing the player, before closing in. */
    public float alertDelay = 0.45f;
    /** How long the enemy strafes before committing to another attack. */
    public float circleTime = 1.1f;
    /** The punish window after an attack ends. */
    public float recoverTime = 0.65f;
    /** Chance of picking the heavy attack when in range. */
    public float heavyChance = 0.25f;

    /** Weapon id from the weapon library. */
    public String weaponId = "hand_axe";

    /** How this enemy is built and drawn. */
    public BodyDef body = new BodyDef();

    /** True for bosses: they get an arena, a name bar and phases. */
    public boolean boss;
    /** Health fractions at which the boss changes phase, high to low. */
    public float[] phaseThresholds = new float[0];
    /** Per-phase multipliers applied to speed and aggression. */
    public float[] phaseAggression = new float[0];

    @Override
    public String toString() {
        return id + " (" + Math.round(health) + "hp, " + souls + " souls)";
    }
}
