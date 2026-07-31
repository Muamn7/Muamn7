package com.muamn.ashen.world;

import com.badlogic.gdx.math.Vector3;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Traps and illusory walls, tested where they are pure.
 *
 * The parts worth testing here are the ones a screenshot cannot show: that a
 * trap has a warning before it can hurt anyone, that its damage volume is the
 * volume it looks like, and that a false wall is genuinely solid until it is
 * struck and genuinely not solid afterwards.
 */
class HazardTest {

    private static final Vector3 ORIGIN = new Vector3();

    // ---- traps ------------------------------------------------------------

    @Test
    void aTrapCannotHurtAnyoneDuringItsWarning() {
        Trap trap = Trap.dart(0f, 0f, 0f, 40f);
        Vector3 victim = new Vector3(0f, 0f, 3f);   // squarely in the lane

        // Standing in the trigger starts the telegraph, and the telegraph is safe.
        float dealt = 0f;
        for (int i = 0; i < 12; i++) dealt += trap.update(1f / 60f, victim);
        assertEquals(Trap.Phase.TELEGRAPH, trap.phase());
        assertEquals(0f, dealt, "a trap that hurts during its own warning cannot be reacted to");
    }

    @Test
    void aTrapHurtsOnceItIsLiveAndOnlyOnce() {
        Trap trap = Trap.dart(0f, 0f, 0f, 40f);
        Vector3 victim = new Vector3(0f, 0f, 3f);
        float total = 0f;
        for (int i = 0; i < 60; i++) total += trap.update(1f / 60f, victim);
        assertEquals(40f, total, 0.01f,
                "one cycle must deal its damage exactly once, not once per frame");
    }

    @Test
    void steppingOutOfTheLaneAvoidsIt() {
        Trap trap = Trap.dart(0f, 0f, 0f, 40f);
        Vector3 inLane = new Vector3(0f, 0f, 3f);
        Vector3 aside = new Vector3(4f, 0f, 3f);

        float total = 0f;
        for (int i = 0; i < 12; i++) total += trap.update(1f / 60f, inLane);
        // Out of the way before it fires: the whole point of a telegraph.
        for (int i = 0; i < 48; i++) total += trap.update(1f / 60f, aside);
        assertEquals(0f, total);
    }

    @Test
    void aDartTrapOnlyCoversWhatIsInFrontOfIt() {
        Trap trap = Trap.dart(0f, 0f, 0f, 40f);
        assertTrue(trap.hurts(new Vector3(0f, 0f, 5f)), "straight ahead");
        assertFalse(trap.hurts(new Vector3(0f, 0f, -5f)), "behind it");
        assertFalse(trap.hurts(new Vector3(0f, 0f, 20f)), "past its reach");
        assertFalse(trap.hurts(new Vector3(3f, 0f, 5f)), "beside the lane");
        assertFalse(trap.hurts(new Vector3(0f, 6f, 5f)), "far above it");
    }

    @Test
    void aTrapsFacingRotatesItsLane() {
        // Facing 90 points the lane along world +X.
        Trap trap = Trap.dart(0f, 0f, 90f, 40f);
        assertTrue(trap.hurts(new Vector3(5f, 0f, 0f)));
        assertFalse(trap.hurts(new Vector3(0f, 0f, 5f)));

        Trap opposite = Trap.dart(0f, 0f, 270f, 40f);
        assertTrue(opposite.hurts(new Vector3(-5f, 0f, 0f)));
        assertFalse(opposite.hurts(new Vector3(5f, 0f, 0f)));
    }

    @Test
    void spikesCoverACircleAndBladesCoverABar() {
        Trap spikes = Trap.spikes(0f, 0f, 40f, 2f);
        assertTrue(spikes.hurts(new Vector3(0.8f, 0f, 0.8f)));
        assertFalse(spikes.hurts(new Vector3(4f, 0f, 0f)));

        Trap blade = Trap.blade(0f, 0f, 0f, 40f, 2f);
        assertTrue(blade.hurts(new Vector3(2f, 0f, 0f)), "along the swing");
        assertFalse(blade.hurts(new Vector3(0f, 0f, 3f)), "up the corridor, clear of it");
    }

    @Test
    void aTimedTrapRunsWithoutAnyoneThere() {
        // A blade never waits. That is what makes it a rhythm rather than an ambush.
        Trap blade = Trap.blade(0f, 0f, 0f, 40f, 0.5f);
        boolean wentLive = false;
        for (int i = 0; i < 120; i++) {
            blade.update(1f / 60f, null);
            if (blade.isLive()) wentLive = true;
        }
        assertTrue(wentLive, "a periodic trap must cycle with no player in sight");
    }

    @Test
    void aTriggeredTrapWaitsForSomeone() {
        Trap dart = Trap.dart(0f, 0f, 0f, 40f);
        for (int i = 0; i < 600; i++) dart.update(1f / 60f, null);
        assertEquals(Trap.Phase.IDLE, dart.phase(),
                "a triggered trap must not fire at an empty corridor");
    }

    @Test
    void aTrapRearmsAndCanCatchYouTwice() {
        Trap trap = Trap.dart(0f, 0f, 0f, 40f);
        Vector3 victim = new Vector3(0f, 0f, 3f);
        float total = 0f;
        for (int i = 0; i < 600; i++) total += trap.update(1f / 60f, victim);
        assertTrue(total >= 80f, "standing in a dart lane for ten seconds took " + total);
    }

    // ---- illusory walls ---------------------------------------------------

    @Test
    void aFalseWallIsSolidUntilItIsStruck() {
        IllusoryWall wall = new IllusoryWall("test", 0f, 0f, 0f, 0f,
                4f, 5f, 1f, "brick");
        CollisionMesh mesh = new CollisionMesh();
        wall.addCollision(mesh);
        assertTrue(mesh.ownTriangleCount() > 0, "a wall that is not there yet has to be solid");

        assertTrue(wall.strike());
        assertTrue(wall.isOpen());
        assertFalse(wall.strike(), "striking it again is not a second discovery");

        CollisionMesh after = new CollisionMesh();
        wall.addCollision(after);
        assertEquals(0, after.ownTriangleCount(), "an opened wall must stop colliding");
    }

    @Test
    void collisionSitsWhereTheWallSays() {
        IllusoryWall wall = new IllusoryWall("test", 10f, 0f, -4f, 0f,
                4f, 5f, 1f, "brick");
        CollisionMesh mesh = new CollisionMesh();
        wall.addCollision(mesh);

        // Facing 0: width runs along X, thickness along Z.
        assertEquals(4f, mesh.getBounds().getWidth(), 0.01f);
        assertEquals(5f, mesh.getBounds().getHeight(), 0.01f);
        assertEquals(1f, mesh.getBounds().getDepth(), 0.01f);
        assertEquals(10f, mesh.getBounds().getCenterX(), 0.01f);
        assertEquals(-4f, mesh.getBounds().getCenterZ(), 0.01f);
    }

    @Test
    void aQuarterTurnSwapsTheWallsAxes() {
        IllusoryWall wall = new IllusoryWall("test", 0f, 0f, 0f, 90f,
                4f, 5f, 1f, "brick");
        CollisionMesh mesh = new CollisionMesh();
        wall.addCollision(mesh);
        assertEquals(1f, mesh.getBounds().getWidth(), 0.01f, "thickness now runs along X");
        assertEquals(4f, mesh.getBounds().getDepth(), 0.01f, "width now runs along Z");
    }

    @Test
    void onlyASwingAimedAtTheWallFindsIt() {
        IllusoryWall wall = new IllusoryWall("test", 0f, 0f, 5f, 0f,
                4f, 5f, 1f, "brick");
        // Standing two metres short of it, facing it.
        assertTrue(wall.struckBy(new Vector3(0f, 0f, 3f), 0f, 2.5f));
        // Same spot, facing away.
        assertFalse(wall.struckBy(new Vector3(0f, 0f, 3f), 180f, 2.5f));
        // Facing it from too far off.
        assertFalse(wall.struckBy(new Vector3(0f, 0f, -20f), 0f, 2.5f));
    }

    @Test
    void anOpenedWallCannotBeFoundAgain() {
        IllusoryWall wall = new IllusoryWall("test", 0f, 0f, 5f, 0f,
                4f, 5f, 1f, "brick");
        wall.openSilently();
        assertFalse(wall.struckBy(new Vector3(0f, 0f, 3f), 0f, 2.5f));
        assertTrue(wall.isOpen());
    }

    // ---- the mesh underneath ----------------------------------------------

    @Test
    void clearingAMeshLeavesItUsable() {
        CollisionMesh mesh = new CollisionMesh();
        mesh.addTriangle(0f, 0f, 0f, 1f, 0f, 0f, 0f, 0f, 1f);
        assertEquals(1, mesh.ownTriangleCount());

        mesh.clear();
        assertEquals(0, mesh.ownTriangleCount());

        mesh.addTriangle(0f, 0f, 0f, 2f, 0f, 0f, 0f, 0f, 2f);
        assertEquals(1, mesh.ownTriangleCount());
        // The broadphase has to have been rebuilt too, or the new triangle is
        // present but invisible to every query.
        assertTrue(mesh.query(-1f, -1f, -1f, 3f, 1f, 3f).size > 0,
                "a triangle added after clear() must still be findable");
    }

    @Test
    void overlaysChainSoBothSecretsAndABarrierCanBeLayered() {
        CollisionMesh level = new CollisionMesh();
        level.addTriangle(0f, 0f, 0f, 1f, 0f, 0f, 0f, 0f, 1f);
        CollisionMesh secrets = new CollisionMesh();
        secrets.addTriangle(5f, 0f, 0f, 6f, 0f, 0f, 5f, 0f, 1f);
        CollisionMesh barrier = new CollisionMesh();
        barrier.addTriangle(9f, 0f, 0f, 10f, 0f, 0f, 9f, 0f, 1f);

        level.setOverlay(secrets);
        secrets.setOverlay(barrier);
        assertEquals(3, level.triangleCount(),
                "the boss barrier layers onto the secrets, not instead of them");
        assertEquals(1, level.ownTriangleCount());
    }

    @Test
    void everyTrapPresetTelegraphsLongEnoughToReactTo() {
        Trap[] presets = {
                Trap.dart(0f, 0f, 0f, 10f),
                Trap.blade(0f, 0f, 0f, 10f, 2f),
                Trap.spikes(0f, 0f, 10f, 2f),
        };
        for (Trap trap : presets) {
            assertTrue(trap.telegraph >= 0.2f,
                    trap.kind + " warns for only " + trap.telegraph + "s");
            assertTrue(trap.active > 0f, trap.kind + " is never live");
            assertTrue(trap.damage > 0f, trap.kind + " does nothing");
            assertFalse(trap.hurts(ORIGIN.set(0f, 40f, 0f)),
                    trap.kind + " reaches the sky");
        }
    }
}
