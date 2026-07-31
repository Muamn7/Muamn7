package com.muamn.ashen.world;

import com.badlogic.gdx.math.Vector3;

/**
 * A way out of one area and into another.
 *
 * Portals are one-way declarations: each area names where its exits lead and
 * where the player should land. Two-way passage is two portals, which sounds
 * redundant until you want a drop you cannot climb back up, or a door that
 * opens onto a different ledge than the one you left.
 */
public class Portal {

    public final String targetArea;
    /** Where the player appears in the target area. */
    public final Vector3 targetPosition = new Vector3();
    public final float targetFacing;

    /** Trigger volume in this area. */
    public final Vector3 position = new Vector3();
    public final float radius;

    /** Shown when the player is close enough to use it. */
    public final String labelAr;
    public final String labelEn;

    /**
     * True for a doorway that needs a deliberate interaction; false for a
     * threshold you simply walk across. A one-way drop should never need a
     * button press, and a door back into a boss area always should.
     */
    public final boolean requiresInteract;

    public Portal(String targetArea, float x, float z, float radius,
                  float targetX, float targetZ, float targetFacing,
                  String labelAr, String labelEn, boolean requiresInteract) {
        this.targetArea = targetArea;
        this.position.set(x, 0f, z);
        this.radius = radius;
        this.targetPosition.set(targetX, 0.4f, targetZ);
        this.targetFacing = targetFacing;
        this.labelAr = labelAr;
        this.labelEn = labelEn;
        this.requiresInteract = requiresInteract;
    }

    /** True while the player stands in the trigger. */
    public boolean contains(Vector3 playerPosition) {
        float dx = playerPosition.x - position.x;
        float dz = playerPosition.z - position.z;
        return dx * dx + dz * dz <= radius * radius;
    }
}
