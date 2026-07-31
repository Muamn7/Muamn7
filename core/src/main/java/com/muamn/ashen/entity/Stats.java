package com.muamn.ashen.entity;

import com.badlogic.gdx.math.MathUtils;

import com.muamn.ashen.Config;

/**
 * Health, stamina and the RPG attributes behind them.
 *
 * The derived values follow Souls conventions: attributes feed pools through a
 * curve with soft caps, so the first twenty levels matter far more than the next
 * twenty. Part 2 hangs weapon scaling and damage off the same attributes.
 */
public class Stats {

    public int vigor = 10;
    public int endurance = 10;
    public int strength = 10;
    public int dexterity = 10;
    public int intelligence = 9;
    public int faith = 9;

    public int level = 1;
    public long souls;

    public float health;
    public float maxHealth;
    public float stamina;
    public float maxStamina;

    /** Counts down after stamina is spent; regen is paused while it runs. */
    private float regenDelay;

    public Stats() {
        recalculate();
        health = maxHealth;
        stamina = maxStamina;
    }

    /** Recomputes pools from attributes. Call after any attribute change. */
    public void recalculate() {
        float healthRatio = maxHealth > 0f ? health / maxHealth : 1f;
        float staminaRatio = maxStamina > 0f ? stamina / maxStamina : 1f;

        maxHealth = healthFor(vigor);
        maxStamina = staminaFor(endurance);

        health = maxHealth * healthRatio;
        stamina = maxStamina * staminaRatio;
    }

    /** Soft-capped at 40; past that each point is worth a fifth as much. */
    public static float healthFor(int vigor) {
        float v = Math.max(1, vigor);
        float base = 300f;
        float upTo40 = Math.min(v, 40f) - 1f;
        float past40 = Math.max(0f, v - 40f);
        return base + upTo40 * 22f + past40 * 5f;
    }

    public static float staminaFor(int endurance) {
        float e = Math.max(1, endurance);
        float upTo40 = Math.min(e, 40f) - 1f;
        float past40 = Math.max(0f, e - 40f);
        return 80f + upTo40 * 2.2f + past40 * 0.4f;
    }

    /** Souls cost to go from {@code level} to {@code level + 1}. */
    public static long soulsToLevel(int level) {
        float l = level + 9f;
        return (long) (0.02f * l * l * l + 3.06f * l * l + 105.6f * l - 895f);
    }

    public boolean canAfford(long cost) {
        return souls >= cost;
    }

    /** @return true if the cost was paid. */
    public boolean spendStamina(float amount) {
        if (stamina < amount) return false;
        stamina -= amount;
        regenDelay = Config.STAMINA_REGEN_DELAY;
        return true;
    }

    /** Spends stamina even if it takes the pool to zero (attacks always land). */
    public void drainStamina(float amount) {
        stamina = Math.max(0f, stamina - amount);
        regenDelay = Config.STAMINA_REGEN_DELAY;
    }

    public void update(float dt, boolean regenBlocked) {
        if (regenDelay > 0f) regenDelay -= dt;
        if (!regenBlocked && regenDelay <= 0f && stamina < maxStamina) {
            stamina = Math.min(maxStamina, stamina + Config.STAMINA_REGEN_PER_SEC * dt);
        }
    }

    public void damage(float amount) {
        health = MathUtils.clamp(health - amount, 0f, maxHealth);
    }

    public void heal(float amount) {
        health = MathUtils.clamp(health + amount, 0f, maxHealth);
    }

    public boolean isDead() {
        return health <= 0f;
    }

    public float healthFraction() {
        return maxHealth > 0f ? MathUtils.clamp(health / maxHealth, 0f, 1f) : 0f;
    }

    public float staminaFraction() {
        return maxStamina > 0f ? MathUtils.clamp(stamina / maxStamina, 0f, 1f) : 0f;
    }
}
