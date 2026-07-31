package com.muamn.ashen.world;

import com.badlogic.gdx.math.Vector3;
import com.badlogic.gdx.utils.IntArray;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CollisionMeshTest {

    /** A 1x1 floor quad at y = 0, spanning 0..1 on both horizontal axes. */
    private static CollisionMesh floorQuad() {
        CollisionMesh mesh = new CollisionMesh();
        mesh.addTriangle(0, 0, 0, 1, 0, 0, 1, 0, 1);
        mesh.addTriangle(0, 0, 0, 1, 0, 1, 0, 0, 1);
        return mesh;
    }

    @Test
    void degenerateTrianglesAreRejected() {
        CollisionMesh mesh = new CollisionMesh();
        mesh.addTriangle(0, 0, 0, 1, 0, 0, 2, 0, 0); // collinear
        assertEquals(0, mesh.triangleCount());
    }

    @Test
    void normalFollowsWinding() {
        CollisionMesh mesh = new CollisionMesh();
        mesh.addTriangle(0, 0, 0, 0, 0, 1, 1, 0, 0);
        assertEquals(1f, mesh.normalOf(0).y, 1e-5f);
    }

    @Test
    void raycastFindsTheFloorBelow() {
        CollisionMesh mesh = floorQuad();
        Vector3 normal = new Vector3();
        float dist = mesh.raycast(new Vector3(0.5f, 3f, 0.5f), new Vector3(0f, -1f, 0f), 10f, normal);
        assertEquals(3f, dist, 1e-3f);
        assertEquals(1f, Math.abs(normal.y), 1e-3f);
    }

    @Test
    void raycastMissesOutsideTheTriangle() {
        CollisionMesh mesh = floorQuad();
        float dist = mesh.raycast(new Vector3(5f, 3f, 5f), new Vector3(0f, -1f, 0f), 10f, null);
        assertTrue(dist < 0f, "expected a miss, got distance " + dist);
    }

    @Test
    void raycastRespectsMaxDistance() {
        CollisionMesh mesh = floorQuad();
        float dist = mesh.raycast(new Vector3(0.5f, 3f, 0.5f), new Vector3(0f, -1f, 0f), 1f, null);
        assertTrue(dist < 0f, "hit beyond maxDist should be rejected");
    }

    @Test
    void broadphaseReturnsOverlappingTrianglesOnly() {
        CollisionMesh mesh = new CollisionMesh();
        mesh.addTriangle(0, 0, 0, 1, 0, 0, 1, 0, 1);       // near the origin
        mesh.addTriangle(60, 0, 60, 61, 0, 60, 61, 0, 61); // far away

        IntArray near = mesh.query(-1f, -1f, -1f, 2f, 1f, 2f);
        assertEquals(1, near.size);
        assertEquals(0, near.get(0));
    }

    @Test
    void closestPointOnTriangleClampsToTheFace() {
        Vector3 a = new Vector3(0, 0, 0), b = new Vector3(1, 0, 0), c = new Vector3(0, 0, 1);
        Vector3 out = new Vector3();

        // Directly above the interior.
        CollisionMesh.closestPointOnTriangle(new Vector3(0.25f, 5f, 0.25f), a, b, c, out);
        assertEquals(0.25f, out.x, 1e-4f);
        assertEquals(0f, out.y, 1e-4f);
        assertEquals(0.25f, out.z, 1e-4f);

        // Well outside past vertex b: the closest point is b itself.
        CollisionMesh.closestPointOnTriangle(new Vector3(9f, 0f, -9f), a, b, c, out);
        assertEquals(0f, out.dst(b), 1e-4f);
    }

    @Test
    void closestSegmentSegmentFindsPerpendicularDistance() {
        Vector3 c1 = new Vector3(), c2 = new Vector3();
        // Two crossing segments offset by 2 on the y axis.
        float d2 = CollisionMesh.closestSegmentSegment(
                new Vector3(-1, 0, 0), new Vector3(1, 0, 0),
                new Vector3(0, 2, -1), new Vector3(0, 2, 1), c1, c2);
        assertEquals(4f, d2, 1e-4f);
        assertEquals(0f, c1.x, 1e-4f);
        assertEquals(0f, c2.z, 1e-4f);
    }
}
