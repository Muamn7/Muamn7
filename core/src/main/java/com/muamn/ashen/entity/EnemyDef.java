package com.muamn.ashen.entity;

/**
 * An enemy archetype.
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

    /** Imported model to use, or null for the procedural humanoid. */
    public String modelName;
    /** Weapon id from the library. */
    public String weaponId = "hand_axe";

    public static EnemyDef hollowSoldier() {
        EnemyDef d = new EnemyDef();
        d.id = "hollow_soldier";
        d.nameAr = "جندي جوّاف";
        d.nameEn = "Hollow Soldier";
        d.health = 220f;
        d.souls = 100L;
        d.poise = 22f;
        d.weaponId = "broadsword";
        return d;
    }

    /**
     * The imported rigged creature: taller, tougher, slower to commit but with a
     * long reach. Falls back to the procedural body if the model is absent.
     */
    public static EnemyDef reaper() {
        EnemyDef d = new EnemyDef();
        d.id = "hollow_reaper";
        d.nameAr = "حاصد الرماد";
        d.nameEn = "Ashen Reaper";
        d.health = 520f;
        d.souls = 600L;
        d.poise = 48f;
        d.absorption = 0.12f;
        d.strength = 20;
        d.dexterity = 16;
        d.radius = 0.42f;
        d.height = 2.10f;
        d.walkSpeed = 2.1f;
        d.runSpeed = 4.6f;
        d.aggroRange = 15f;
        d.alertDelay = 0.6f;
        d.circleTime = 1.35f;
        d.recoverTime = 0.85f;
        d.heavyChance = 0.35f;
        d.weaponId = "halberd";
        d.modelName = "hollow_reaper";
        return d;
    }
}
