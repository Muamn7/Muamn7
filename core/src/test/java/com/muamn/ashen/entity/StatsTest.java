package com.muamn.ashen.entity;

import com.muamn.ashen.Config;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class StatsTest {

    @Test
    void poolsStartFull() {
        Stats s = new Stats();
        assertEquals(s.maxHealth, s.health, 1e-4f);
        assertEquals(s.maxStamina, s.stamina, 1e-4f);
        assertEquals(1f, s.healthFraction(), 1e-4f);
    }

    @Test
    void vigorSoftCapsAtForty() {
        float gainBeforeCap = Stats.healthFor(30) - Stats.healthFor(29);
        float gainAfterCap = Stats.healthFor(50) - Stats.healthFor(49);
        assertTrue(gainAfterCap < gainBeforeCap * 0.5f,
                "past 40 vigor should give much less health per point");
    }

    @Test
    void recalculateKeepsTheCurrentFraction() {
        Stats s = new Stats();
        s.damage(s.maxHealth * 0.5f);
        float before = s.healthFraction();

        s.vigor = 25;
        s.recalculate();

        assertEquals(before, s.healthFraction(), 1e-3f);
        assertTrue(s.maxHealth > Stats.healthFor(10));
    }

    @Test
    void spendStaminaFailsWhenShort() {
        Stats s = new Stats();
        s.stamina = 10f;
        assertFalse(s.spendStamina(Config.ROLL_STAMINA));
        assertEquals(10f, s.stamina, 1e-4f);

        assertTrue(s.spendStamina(5f));
        assertEquals(5f, s.stamina, 1e-4f);
    }

    @Test
    void staminaRegenWaitsOutTheDelay() {
        Stats s = new Stats();
        s.spendStamina(30f);
        float afterSpend = s.stamina;

        // Inside the delay window nothing comes back.
        s.update(Config.STAMINA_REGEN_DELAY * 0.5f, false);
        assertEquals(afterSpend, s.stamina, 1e-3f);

        // Past it, stamina climbs again.
        s.update(Config.STAMINA_REGEN_DELAY, false);
        s.update(0.5f, false);
        assertTrue(s.stamina > afterSpend, "stamina should regenerate after the delay");
    }

    @Test
    void blockedRegenHoldsStaminaStill() {
        Stats s = new Stats();
        s.spendStamina(30f);
        float afterSpend = s.stamina;
        for (int i = 0; i < 120; i++) s.update(Config.FIXED_STEP, true);
        assertEquals(afterSpend, s.stamina, 1e-3f);
    }

    @Test
    void staminaNeverExceedsTheMaximum() {
        Stats s = new Stats();
        s.spendStamina(5f);
        for (int i = 0; i < 600; i++) s.update(Config.FIXED_STEP, false);
        assertEquals(s.maxStamina, s.stamina, 1e-3f);
    }

    @Test
    void damageClampsAtZeroAndMarksDeath() {
        Stats s = new Stats();
        s.damage(s.maxHealth * 10f);
        assertEquals(0f, s.health, 1e-4f);
        assertTrue(s.isDead());

        s.heal(50f);
        assertFalse(s.isDead());
        assertEquals(50f, s.health, 1e-4f);
    }

    @Test
    void levelCostGrowsWithLevel() {
        long low = Stats.soulsToLevel(1);
        long mid = Stats.soulsToLevel(40);
        long high = Stats.soulsToLevel(100);
        assertTrue(low > 0, "first level should cost something, got " + low);
        assertTrue(mid > low);
        assertTrue(high > mid);
    }
}
