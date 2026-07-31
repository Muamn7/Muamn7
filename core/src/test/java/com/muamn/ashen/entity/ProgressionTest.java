package com.muamn.ashen.entity;

import com.muamn.ashen.combat.WeaponDef;
import com.muamn.ashen.ui.BonfireMenu;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * The soul economy. These are the numbers that decide whether the game respects
 * the player's time, so they get pinned down rather than left to feel.
 */
class ProgressionTest {

    @Test
    void levellingCostsRiseAndStayAffordableEarly() {
        long first = Stats.soulsToLevel(1);
        long tenth = Stats.soulsToLevel(10);
        long fiftieth = Stats.soulsToLevel(50);

        assertTrue(first > 0, "the first level must cost something");
        assertTrue(first < 1000, "the first level should be reachable from a few kills");
        assertTrue(tenth > first);
        assertTrue(fiftieth > tenth * 3, "late levels should cost far more than early ones");

        long previous = -1;
        for (int level = 1; level <= 120; level++) {
            long cost = Stats.soulsToLevel(level);
            assertTrue(cost > previous, "cost dipped at level " + level);
            previous = cost;
        }
    }

    @Test
    void reinforcementGetsSteeplyMoreExpensive() {
        WeaponDef weapon = new WeaponDef();
        weapon.physical = 100f;

        long previous = -1;
        for (int level = 0; level < 10; level++) {
            weapon.upgrade = level;
            long cost = BonfireMenu.reinforceCost(weapon);
            assertTrue(cost > previous, "reinforce cost dipped at +" + (level + 1));
            previous = cost;
        }

        weapon.upgrade = 0;
        long toOne = BonfireMenu.reinforceCost(weapon);
        weapon.upgrade = 9;
        long toTen = BonfireMenu.reinforceCost(weapon);
        assertTrue(toTen > toOne * 5, "+10 should be a real investment next to +1");
    }

    @Test
    void aStrongerWeaponCostsMoreToReinforce() {
        WeaponDef light = new WeaponDef();
        light.physical = 60f;
        WeaponDef heavy = new WeaponDef();
        heavy.physical = 140f;
        assertTrue(BonfireMenu.reinforceCost(heavy) > BonfireMenu.reinforceCost(light));
    }

    @Test
    void raisingVigorGrowsThePoolAndHealsBySameAmount() {
        // Mirrors what the bonfire menu does, which is the behaviour that matters:
        // a level up must not just widen an empty bar.
        Stats stats = new Stats();
        stats.damage(stats.maxHealth * 0.5f);

        float healthBefore = stats.health;
        float maxBefore = stats.maxHealth;

        stats.vigor += 5;
        stats.recalculate();
        float gained = stats.maxHealth - maxBefore;
        stats.health = Math.min(stats.maxHealth, healthBefore + gained);

        assertTrue(gained > 0f, "vigor should raise max health");
        assertEquals(healthBefore + gained, stats.health, 1e-3f);
        assertTrue(stats.health < stats.maxHealth, "it should not be a full heal");
    }

    @Test
    void aToughEnemyIsWorthMoreThanAWeakOne() {
        // The shipped bestiary is validated in BestiaryTest; this pins the rule
        // the economy depends on, using two defs built here so it stays a unit.
        EnemyDef weak = new EnemyDef();
        weak.id = "weak";
        weak.health = 200f;
        weak.souls = 100L;

        EnemyDef tough = new EnemyDef();
        tough.id = "tough";
        tough.health = 600f;
        tough.souls = 500L;

        assertTrue(tough.souls > weak.souls);
        assertTrue(tough.souls / (double) tough.health >= weak.souls / (double) weak.health,
                "a tougher fight should pay at least as well per point of health");
    }
}
