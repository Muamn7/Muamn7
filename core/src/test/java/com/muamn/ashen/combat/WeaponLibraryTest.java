package com.muamn.ashen.combat;

import com.badlogic.gdx.utils.Array;
import com.muamn.ashen.entity.Stats;
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
 * Guards the shipped weapon data. Frame data is edited by hand and by feel, so
 * these check the invariants that make an attack playable rather than the exact
 * numbers, which are meant to change.
 */
class WeaponLibraryTest {

    private static WeaponLibrary library;

    @BeforeAll
    static void loadFromRepo() throws IOException {
        // Walk up to the repo root so the test works from any module directory.
        Path dir = Paths.get("").toAbsolutePath();
        while (dir != null && !Files.exists(dir.resolve("assets/data/weapons.json"))) {
            dir = dir.getParent();
        }
        assertNotNull(dir, "could not find assets/data/weapons.json");

        library = new WeaponLibrary();
        library.parse(read(dir.resolve("assets/data/movesets.json")),
                      read(dir.resolve("assets/data/weapons.json")));
    }

    private static String read(Path path) throws IOException {
        return new String(Files.readAllBytes(path), StandardCharsets.UTF_8);
    }

    @Test
    void loadsSixteenWeaponsWithUniqueIds() {
        assertEquals(16, library.size(), "the game is specified as having 16 weapons");
        Set<String> ids = new HashSet<>();
        for (WeaponDef w : library.all()) {
            assertTrue(ids.add(w.id), "duplicate weapon id: " + w.id);
        }
    }

    @Test
    void everyWeaponHasACompleteMoveset() {
        for (WeaponDef w : library.all()) {
            assertNotNull(w.moveset, w.id + " has no moveset");
            assertTrue(w.moveset.light.length >= 1, w.id + " has no light attack");
            assertTrue(w.moveset.heavy.length >= 1, w.id + " has no heavy attack");
            assertNotNull(w.moveset.running, w.id + " has no running attack");
            assertNotNull(w.moveset.rolling, w.id + " has no rolling attack");
        }
    }

    @Test
    void everyWeaponIsNamedInBothLanguages() {
        for (WeaponDef w : library.all()) {
            assertFalse(w.nameEn.isEmpty(), w.id + " has no English name");
            assertFalse(w.nameAr.isEmpty(), w.id + " has no Arabic name");
            assertNotEqualsIgnoringId(w);
        }
    }

    private void assertNotEqualsIgnoringId(WeaponDef w) {
        assertFalse(w.nameAr.equals(w.id), w.id + " is missing a real Arabic name");
    }

    @Test
    void attackWindowsAreOrderedAndPositive() {
        for (WeaponDef w : library.all()) {
            for (AttackDef a : allAttacks(w)) {
                String where = w.id + "/" + a.id;
                assertTrue(a.windup > 0f, where + " needs a windup to be readable");
                assertTrue(a.active > 0f, where + " has no active window");
                assertTrue(a.recovery > 0f, where + " has no recovery, so it is free");
                assertTrue(a.duration() > a.activeEnd(), where + " ends before it recovers");
                assertTrue(a.isActiveAt(a.windup + a.active * 0.5f), where + " hitbox never opens");
                assertFalse(a.isActiveAt(a.windup - 1e-4f), where + " hits during windup");
                assertFalse(a.isActiveAt(a.activeEnd()), where + " hits after the active window");
            }
        }
    }

    @Test
    void heavyAttacksCostMoreAndCommitLonger() {
        for (WeaponDef w : library.all()) {
            AttackDef light = w.moveset.light(0);
            AttackDef heavy = w.moveset.heavy(0);
            // The catalyst is the exception: its "heavy" is a desperate melee
            // swipe, deliberately faster and weaker than casting.
            if (w.weaponClass == WeaponClass.CATALYST) continue;
            assertTrue(heavy.damage > light.damage, w.id + " heavy does not hit harder");
            assertTrue(heavy.windup > light.windup, w.id + " heavy is not slower to start");
            assertTrue(heavy.staminaCost > light.staminaCost, w.id + " heavy is not costlier");
        }
    }

    @Test
    void reachTracksWeaponLength() {
        WeaponDef dagger = library.get("dagger");
        WeaponDef spear = library.get("spear");
        WeaponDef zwei = library.get("zweihander");
        assertTrue(spear.maxReach() > zwei.maxReach(), "a spear should out-range a greatsword");
        assertTrue(zwei.maxReach() > dagger.maxReach(), "a greatsword should out-range a dagger");
    }

    @Test
    void scalingRewardsTheRightAttribute() {
        WeaponDef greataxe = library.get("greataxe");   // strength B
        AttackDef swing = greataxe.moveset.light(0);

        Stats brute = new Stats();
        brute.strength = 40;
        brute.dexterity = 10;
        Stats nimble = new Stats();
        nimble.strength = 32;   // exactly meets the requirement
        nimble.dexterity = 40;

        assertTrue(greataxe.damageAgainst(brute, swing) > greataxe.damageAgainst(nimble, swing),
                "a strength weapon should reward strength, not dexterity");
    }

    @Test
    void missingRequirementsArePunishedNotForbidden() {
        WeaponDef greataxe = library.get("greataxe");
        AttackDef swing = greataxe.moveset.light(0);

        Stats weak = new Stats();
        weak.strength = 10;
        Stats strong = new Stats();
        strong.strength = greataxe.reqStrength;

        float weakDamage = greataxe.damageAgainst(weak, swing);
        float strongDamage = greataxe.damageAgainst(strong, swing);
        assertTrue(weakDamage > 0f, "an under-levelled swing should still do something");
        assertTrue(weakDamage < strongDamage * 0.7f, "wielding it under-levelled should hurt");
    }

    @Test
    void upgradingIncreasesDamageMonotonically() {
        WeaponDef sword = library.get("longsword");
        Stats stats = new Stats();
        AttackDef swing = sword.moveset.light(0);

        float previous = -1f;
        for (int level = 0; level <= 10; level++) {
            sword.upgrade = level;
            float damage = sword.damageAgainst(stats, swing);
            assertTrue(damage > previous, "+" + level + " should beat +" + (level - 1));
            previous = damage;
        }
        sword.upgrade = 0;
    }

    @Test
    void attributeCurveRisesAndSoftCaps() {
        float earlyGain = WeaponDef.attributeCurve(20) - WeaponDef.attributeCurve(10);
        float lateGain = WeaponDef.attributeCurve(60) - WeaponDef.attributeCurve(50);
        assertTrue(earlyGain > 0f, "attributes should be worth something early");
        assertTrue(lateGain > 0f, "attributes should never be worth nothing");
        assertTrue(lateGain < earlyGain * 0.5f, "past the soft cap should be much weaker");

        float previous = -1f;
        for (int a = 1; a <= 99; a++) {
            float value = WeaponDef.attributeCurve(a);
            assertTrue(value >= previous, "attribute curve dipped at " + a);
            previous = value;
        }
    }

    private static Array<AttackDef> allAttacks(WeaponDef w) {
        Array<AttackDef> out = new Array<>();
        out.addAll(w.moveset.light);
        out.addAll(w.moveset.heavy);
        out.add(w.moveset.running);
        out.add(w.moveset.rolling);
        return out;
    }
}
