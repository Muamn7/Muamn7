package com.muamn.ashen.entity;

import com.badlogic.gdx.utils.Array;
import com.muamn.ashen.combat.WeaponLibrary;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.HashSet;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Guards the shipped bestiary.
 *
 * The point of moving enemies into JSON is that they can be retuned without a
 * compile - which also means a typo in a weapon id or a missing punish window
 * ships silently. These are the checks the compiler no longer does.
 */
class BestiaryTest {

    private static EnemyLibrary bestiary;
    private static WeaponLibrary weapons;

    @BeforeAll
    static void loadFromRepo() throws IOException {
        Path dir = Paths.get("").toAbsolutePath();
        while (dir != null && !Files.exists(dir.resolve("assets/data/enemies.json"))) {
            dir = dir.getParent();
        }
        assertNotNull(dir, "could not find assets/data/enemies.json");

        bestiary = new EnemyLibrary();
        bestiary.parse(read(dir.resolve("assets/data/enemies.json")),
                       read(dir.resolve("assets/data/bosses.json")));

        weapons = new WeaponLibrary();
        weapons.parse(read(dir.resolve("assets/data/movesets.json")),
                      read(dir.resolve("assets/data/weapons.json")));
    }

    private static String read(Path path) throws IOException {
        return new String(Files.readAllBytes(path), StandardCharsets.UTF_8);
    }

    private static Array<EnemyDef> everything() {
        Array<EnemyDef> all = new Array<>();
        all.addAll(bestiary.all());
        all.addAll(bestiary.allBosses());
        return all;
    }

    @Test
    void theRosterIsTheSizeTheDesignCallsFor() {
        assertEquals(20, bestiary.size(), "the game is specified as having 20 monster types");
        assertEquals(16, bestiary.bossCount(), "the game is specified as having 16 bosses");
    }

    @Test
    void idsAreUniqueAcrossEnemiesAndBosses() {
        Set<String> ids = new HashSet<>();
        for (EnemyDef def : everything()) {
            assertTrue(ids.add(def.id), "duplicate id: " + def.id);
        }
    }

    @Test
    void everyEnemyNamesAWeaponThatExists() {
        for (EnemyDef def : everything()) {
            assertTrue(weapons.has(def.weaponId),
                    def.id + " wields '" + def.weaponId + "', which is not in the armoury");
        }
    }

    @Test
    void everyEnemyIsNamedInBothLanguages() {
        for (EnemyDef def : everything()) {
            assertFalse(def.nameEn.isEmpty(), def.id + " has no English name");
            assertFalse(def.nameAr.isEmpty(), def.id + " has no Arabic name");
            assertFalse(def.nameAr.equals(def.id), def.id + " is missing a real Arabic name");
        }
    }

    @Test
    void everyEnemyLeavesThePlayerRoomToAct() {
        for (EnemyDef def : everything()) {
            assertTrue(def.recoverTime > 0.3f,
                    def.id + " has no punish window (" + def.recoverTime + "s)");
            assertTrue(def.alertDelay > 0f, def.id + " aggros with no tell");
            assertTrue(def.circleTime > 0f, def.id + " never stops to space");
            assertTrue(def.leashRange > def.aggroRange,
                    def.id + " leashes inside its own aggro range, so it can never chase");
        }
    }

    @Test
    void everyEnemyHasAUsableBody() {
        for (EnemyDef def : everything()) {
            assertNotNull(def.body, def.id + " has no body");
            assertTrue(def.radius > 0.1f && def.radius < 2f, def.id + " has an odd radius");
            assertTrue(def.height > 0.5f && def.height < 6f, def.id + " has an odd height");
            assertTrue(def.health > 0f, def.id + " has no health");
            assertTrue(def.souls > 0L, def.id + " is worth nothing to kill");
            // A creature body must actually resolve to a preset with legs or a plan.
            if (def.body.kind == BodyDef.Kind.CREATURE) {
                CreatureSpec spec = def.body.toCreature();
                assertTrue(spec.legPairs >= 0 && spec.legPairs <= 6,
                        def.id + " has an implausible leg count");
                assertTrue(spec.bodyLength > 0f, def.id + " has no body length");
            }
        }
    }

    @Test
    void bossesArePhasedAndConsistent() {
        for (EnemyDef boss : bestiary.allBosses()) {
            assertTrue(boss.boss, boss.id + " is in bosses.json but not flagged as a boss");
            assertTrue(boss.phaseThresholds.length >= 1, boss.id + " has no phases");
            assertEquals(boss.phaseThresholds.length + 1, boss.phaseAggression.length,
                    boss.id + " needs one aggression value per phase, including the opening");

            float previous = 1f;
            for (float threshold : boss.phaseThresholds) {
                assertTrue(threshold > 0f && threshold < 1f,
                        boss.id + " has a phase threshold outside 0..1");
                assertTrue(threshold < previous,
                        boss.id + " phase thresholds must descend");
                previous = threshold;
            }
            for (float aggression : boss.phaseAggression) {
                assertTrue(aggression >= 1f && aggression <= 2.5f,
                        boss.id + " has an implausible aggression multiplier");
            }
        }
    }

    @Test
    void bossesAreWorthMoreThanTheMobsAroundThem() {
        long strongestMob = 0;
        for (EnemyDef def : bestiary.all()) strongestMob = Math.max(strongestMob, def.souls);
        for (EnemyDef boss : bestiary.allBosses()) {
            assertTrue(boss.souls > strongestMob,
                    boss.id + " pays less than the toughest ordinary enemy");
            assertTrue(boss.health > 1000f, boss.id + " is not a boss-sized fight");
        }
    }

    @Test
    void theBestiaryIsActuallyVaried() {
        // Twenty reskins of one soldier is not twenty enemies.
        Set<String> shapes = new HashSet<>();
        int creatures = 0;
        for (EnemyDef def : bestiary.all()) {
            shapes.add(def.body.kind + ":" + def.body.preset);
            if (def.body.kind == BodyDef.Kind.CREATURE) creatures++;
        }
        assertTrue(creatures >= 5, "the bestiary should not be all humanoids");
        assertTrue(shapes.size() >= 6, "too few distinct body plans: " + shapes);

        float slowest = Float.MAX_VALUE, fastest = 0f;
        for (EnemyDef def : bestiary.all()) {
            slowest = Math.min(slowest, def.runSpeed);
            fastest = Math.max(fastest, def.runSpeed);
        }
        assertTrue(fastest > slowest * 2f, "every enemy moves at about the same speed");
    }
}
