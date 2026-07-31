package com.muamn.ashen.world;

import com.muamn.ashen.Config;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Locks down the movement guarantees the combat in Part 2 depends on: the player
 * lands where the floor is, never passes through a wall, and can climb a kerb.
 */
class CharacterBodyTest {

    private static final float STEP = Config.FIXED_STEP;

    /** Ground plane covering roughly -50..50, built from two big triangles. */
    private static void addGround(CollisionMesh mesh, float y) {
        mesh.addTriangle(-50, y, -50, 50, y, -50, 50, y, 50);
        mesh.addTriangle(-50, y, -50, 50, y, 50, -50, y, 50);
    }

    /** An axis-aligned solid box, as twelve outward-facing triangles. */
    private static void addBox(CollisionMesh m, float x0, float y0, float z0,
                               float x1, float y1, float z1) {
        m.addTriangle(x0, y1, z1, x1, y1, z1, x1, y1, z0);
        m.addTriangle(x0, y1, z1, x1, y1, z0, x0, y1, z0);
        m.addTriangle(x0, y0, z0, x1, y0, z0, x1, y0, z1);
        m.addTriangle(x0, y0, z0, x1, y0, z1, x0, y0, z1);
        m.addTriangle(x0, y0, z1, x1, y0, z1, x1, y1, z1);
        m.addTriangle(x0, y0, z1, x1, y1, z1, x0, y1, z1);
        m.addTriangle(x1, y0, z0, x0, y0, z0, x0, y1, z0);
        m.addTriangle(x1, y0, z0, x0, y1, z0, x1, y1, z0);
        m.addTriangle(x1, y0, z1, x1, y0, z0, x1, y1, z0);
        m.addTriangle(x1, y0, z1, x1, y1, z0, x1, y1, z1);
        m.addTriangle(x0, y0, z0, x0, y0, z1, x0, y1, z1);
        m.addTriangle(x0, y0, z0, x0, y1, z1, x0, y1, z0);
    }

    private static void simulate(CharacterBody body, CollisionMesh mesh, float seconds) {
        int steps = Math.round(seconds / STEP);
        for (int i = 0; i < steps; i++) body.step(mesh, STEP);
    }

    @Test
    void fallsAndLandsOnTheFloor() {
        CollisionMesh mesh = new CollisionMesh();
        addGround(mesh, 0f);

        CharacterBody body = new CharacterBody();
        body.teleport(0f, 5f, 0f);
        simulate(body, mesh, 2f);

        assertTrue(body.grounded, "should be standing on the ground");
        assertEquals(0f, body.position.y, 0.02f);
        assertEquals(0f, body.velocity.y, 1e-3f);
    }

    @Test
    void landingIsReportedOnceWithTheImpactSpeed() {
        CollisionMesh mesh = new CollisionMesh();
        addGround(mesh, 0f);

        CharacterBody body = new CharacterBody();
        body.teleport(0f, 6f, 0f);

        int landings = 0;
        float impact = 0f;
        for (int i = 0; i < 240; i++) {
            body.step(mesh, STEP);
            if (body.justLanded) {
                landings++;
                impact = body.landingImpact;
            }
        }
        assertEquals(1, landings, "justLanded must be a one-frame edge");
        assertTrue(impact > 5f, "expected a real impact speed, got " + impact);
    }

    @Test
    void wallStopsHorizontalMovement() {
        CollisionMesh mesh = new CollisionMesh();
        addGround(mesh, 0f);
        addBox(mesh, 2f, 0f, -5f, 3f, 4f, 5f); // wall at x = 2

        CharacterBody body = new CharacterBody();
        body.teleport(0f, 0f, 0f);
        simulate(body, mesh, 0.3f); // settle on the ground

        for (int i = 0; i < 240; i++) {
            body.velocity.x = 8f; // drive hard into the wall
            body.step(mesh, STEP);
        }

        assertTrue(body.position.x < 2f,
                "player passed through the wall, x = " + body.position.x);
        assertTrue(body.position.x > 2f - body.radius - 0.15f,
                "player should be resting against the wall, x = " + body.position.x);
    }

    @Test
    void climbsAKerbWithinStepHeight() {
        CollisionMesh mesh = new CollisionMesh();
        addGround(mesh, 0f);
        addBox(mesh, 1f, 0f, -5f, 6f, 0.3f, 5f); // 30cm ledge, under STEP_HEIGHT

        CharacterBody body = new CharacterBody();
        body.teleport(0f, 0f, 0f);
        simulate(body, mesh, 0.3f);

        // 60 frames at 3m/s is 3m of travel, which lands well inside the ledge
        // rather than off its far edge.
        for (int i = 0; i < 60; i++) {
            body.velocity.x = 3f;
            body.step(mesh, STEP);
        }

        assertTrue(body.position.x > 1.5f,
                "should have stepped up onto the ledge, x = " + body.position.x);
        assertTrue(body.position.x < 6f, "should still be on the ledge, x = " + body.position.x);
        assertEquals(0.3f, body.position.y, 0.05f);
        assertTrue(body.grounded, "should be standing on the ledge");
    }

    @Test
    void doesNotClimbAWallTallerThanStepHeight() {
        CollisionMesh mesh = new CollisionMesh();
        addGround(mesh, 0f);
        addBox(mesh, 1f, 0f, -5f, 6f, 1.2f, 5f); // way above STEP_HEIGHT

        CharacterBody body = new CharacterBody();
        body.teleport(0f, 0f, 0f);
        simulate(body, mesh, 0.3f);

        for (int i = 0; i < 180; i++) {
            body.velocity.x = 6f;
            body.step(mesh, STEP);
        }

        assertTrue(body.position.y < 0.2f,
                "player climbed a wall it should not have, y = " + body.position.y);
        assertTrue(body.position.x < 1f,
                "player should be blocked, x = " + body.position.x);
    }

    @Test
    void staysGroundedWalkingDownStairs() {
        CollisionMesh mesh = new CollisionMesh();
        addGround(mesh, 0f);
        // Descending steps in +x: each 25cm down.
        for (int i = 0; i < 6; i++) {
            float h = 1.5f - i * 0.25f;
            addBox(mesh, 1f + i * 0.8f, 0f, -3f, 1.8f + i * 0.8f, h, 3f);
        }

        CharacterBody body = new CharacterBody();
        body.teleport(1.4f, 2.0f, 0f);
        simulate(body, mesh, 0.6f);
        assertTrue(body.grounded, "should have landed on the top step");

        int airborneFrames = 0;
        for (int i = 0; i < 200; i++) {
            body.velocity.x = 2.5f;
            body.step(mesh, STEP);
            if (!body.grounded) airborneFrames++;
        }
        assertTrue(airborneFrames < 12,
                "walking down stairs should not launch the body; airborne " + airborneFrames + " frames");
    }

    @Test
    void teleportClearsMotionState() {
        CollisionMesh mesh = new CollisionMesh();
        addGround(mesh, 0f);

        CharacterBody body = new CharacterBody();
        body.teleport(0f, 0f, 0f);
        simulate(body, mesh, 0.5f);
        body.velocity.set(5f, 0f, 5f);

        body.teleport(10f, 3f, -4f);
        assertEquals(10f, body.position.x, 1e-4f);
        assertEquals(0f, body.velocity.len(), 1e-4f);
        assertFalse(body.grounded);
    }
}
