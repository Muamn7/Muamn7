package com.muamn.ashen.combat;

import com.badlogic.gdx.math.Vector3;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CombatMathTest {

    /** Direction a blow travels when the attacker stands at the given heading. */
    private static Vector3 blowFrom(float attackerHeadingDeg) {
        double r = Math.toRadians(attackerHeadingDeg);
        return new Vector3((float) Math.sin(r), 0f, (float) Math.cos(r)).nor();
    }

    @Test
    void guardOnlyCoversTheFront() {
        // Victim faces +Z (0 degrees). An attacker in front of it faces -Z.
        assertTrue(CombatMath.isFrontal(0f, blowFrom(180f), CombatMath.GUARD_ARC),
                "a blow straight to the face should be blockable");
        assertFalse(CombatMath.isFrontal(0f, blowFrom(0f), CombatMath.GUARD_ARC),
                "a blow from behind must not be blockable");
        assertFalse(CombatMath.isFrontal(0f, blowFrom(270f), CombatMath.GUARD_ARC),
                "a blow from the flank is outside a 120 degree guard");
    }

    @Test
    void backstabNeedsBothPositionAndAlignment() {
        // Victim faces +Z; attacker behind it, also facing +Z.
        assertTrue(CombatMath.isBackstab(0f, 0f, blowFrom(0f)),
                "behind and aligned should be a backstab");
        // Behind, but facing the wrong way.
        assertFalse(CombatMath.isBackstab(0f, 150f, blowFrom(0f)),
                "a badly aligned attacker should not get a backstab");
        // Aligned, but standing in front.
        assertFalse(CombatMath.isBackstab(0f, 0f, blowFrom(180f)),
                "a frontal hit is never a backstab");
    }

    @Test
    void angleDifferenceWrapsShortWay() {
        assertEquals(20f, CombatMath.angleDifference(350f, 10f), 1e-3f);
        assertEquals(-20f, CombatMath.angleDifference(10f, 350f), 1e-3f);
        assertEquals(0f, CombatMath.angleDifference(180f, 180f), 1e-3f);
    }

    @Test
    void guardReducesDamageAndCostsStamina() {
        WeaponLibraryFixture fixture = new WeaponLibraryFixture();
        WeaponDef shieldy = fixture.weapon(0.60f, 0.40f);
        WeaponDef flimsy = fixture.weapon(0.25f, 0.10f);

        assertTrue(CombatMath.damageThroughGuard(shieldy, 100f)
                        < CombatMath.damageThroughGuard(flimsy, 100f),
                "a better guard should let less through");
        assertTrue(CombatMath.guardStamina(shieldy, 100f) < CombatMath.guardStamina(flimsy, 100f),
                "higher stability should cost less stamina");
        assertTrue(CombatMath.damageThroughGuard(shieldy, 100f) > 0f,
                "blocking should never be free");
    }

    @Test
    void defenceNeverReachesImmunity() {
        assertEquals(100f, CombatMath.afterDefence(100f, 0f), 1e-3f);
        assertTrue(CombatMath.afterDefence(100f, 0.99f) >= 8f,
                "no amount of absorption should make a target immune");
        assertTrue(CombatMath.afterDefence(100f, 0.5f) < 100f);
    }

    @Test
    void hitboxSegmentDistanceIsClamped() {
        Vector3 out = new Vector3();
        Vector3 a = new Vector3(0f, 0f, 0f);
        Vector3 b = new Vector3(0f, 0f, 2f);

        // Beside the middle of the segment.
        assertEquals(1f, AttackRunner.distancePointSegment(new Vector3(1f, 0f, 1f), a, b, out), 1e-4f);
        // Past the far end: distance is measured to the endpoint, not the line.
        assertEquals(3f, AttackRunner.distancePointSegment(new Vector3(0f, 0f, 5f), a, b, out), 1e-4f);
        assertEquals(2f, out.z, 1e-4f);
        // Behind the near end.
        assertEquals(4f, AttackRunner.distancePointSegment(new Vector3(0f, 0f, -4f), a, b, out), 1e-4f);
    }

    /** Builds throwaway weapons for the guard maths. */
    private static class WeaponLibraryFixture {
        WeaponDef weapon(float absorb, float stability) {
            WeaponDef def = new WeaponDef();
            def.guardAbsorb = absorb;
            def.stability = stability;
            return def;
        }
    }
}
