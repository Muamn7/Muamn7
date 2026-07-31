package com.muamn.ashen.world;

import com.badlogic.gdx.math.MathUtils;
import com.badlogic.gdx.math.Vector3;
import com.badlogic.gdx.utils.IntArray;

import com.muamn.ashen.Config;

/**
 * A vertical capsule that walks, slides and climbs steps over a
 * {@link CollisionMesh}. Used by the player and by every enemy.
 *
 * The order of operations matters and is deliberate: vertical first (so landing
 * is resolved before anything else), then horizontal, then a step-up retry, then
 * a downward snap. That sequence is what stops the classic problems - bouncing
 * down stairs, catching on the seam between two floor tiles, and launching off
 * the top of a ramp.
 */
public class CharacterBody {

    /** Contact tolerance for standing on a surface, beyond the depenetration radius. */
    private static final float GROUND_SKIN = 0.03f;

    /** Feet position: the bottom centre of the capsule. */
    public final Vector3 position = new Vector3();
    public final Vector3 velocity = new Vector3();

    public float radius = Config.PLAYER_RADIUS;
    public float height = Config.PLAYER_HEIGHT;
    public float stepHeight = Config.STEP_HEIGHT;
    public float maxSlopeCos = MathUtils.cosDeg(Config.MAX_SLOPE_DEGREES);

    public boolean grounded;
    public final Vector3 groundNormal = new Vector3(0f, 1f, 0f);
    /** True on the frame the body went from airborne to grounded. */
    public boolean justLanded;
    /** Downward speed at the moment of landing, for fall damage and effects. */
    public float landingImpact;

    private final Vector3 p0 = new Vector3(), p1 = new Vector3();
    private final Vector3 onSeg = new Vector3(), onTri = new Vector3();
    private final Vector3 triA = new Vector3(), triB = new Vector3(), triC = new Vector3();
    private final Vector3 push = new Vector3(), tmp = new Vector3();
    private final Vector3 bestSeg = new Vector3(), bestTri = new Vector3();
    private final Vector3 preMove = new Vector3(), stepResult = new Vector3();
    private final Vector3 probeDir = new Vector3(0f, -1f, 0f);
    private final Vector3 probeNormal = new Vector3();

    /**
     * Integrates one fixed step. {@code velocity} is read and written; callers set
     * the horizontal components and let gravity handle y.
     */
    public void step(CollisionMesh mesh, float dt) {
        boolean wasGrounded = grounded;
        justLanded = false;

        if (!grounded) {
            velocity.y = Math.max(velocity.y + Config.GRAVITY * dt, Config.TERMINAL_VELOCITY);
        } else if (velocity.y < 0f) {
            velocity.y = 0f;
        }

        // --- vertical ---
        float fallSpeed = velocity.y;
        position.y += velocity.y * dt;
        grounded = false;
        groundNormal.set(0f, 1f, 0f);
        resolve(mesh);
        if (grounded) {
            if (!wasGrounded) {
                justLanded = true;
                landingImpact = -fallSpeed;
            }
            velocity.y = 0f;
        }

        // --- horizontal ---
        preMove.set(position);
        position.x += velocity.x * dt;
        position.z += velocity.z * dt;
        resolve(mesh);

        float wantedX = velocity.x * dt, wantedZ = velocity.z * dt;
        float wanted2 = wantedX * wantedX + wantedZ * wantedZ;
        float gotX = position.x - preMove.x, gotZ = position.z - preMove.z;
        float got2 = gotX * gotX + gotZ * gotZ;

        // Blocked by something short? Try again from a raised start and drop back
        // down. This is what makes stairs and kerbs walkable without ramps.
        if (wanted2 > 1e-6f && got2 < wanted2 * 0.65f && (wasGrounded || grounded)) {
            stepResult.set(position);
            position.set(preMove);
            position.y += stepHeight;
            resolve(mesh);
            position.x += wantedX;
            position.z += wantedZ;
            resolve(mesh);

            float stepX = position.x - preMove.x, stepZ = position.z - preMove.z;
            if (stepX * stepX + stepZ * stepZ > got2 + 1e-5f) {
                // Find the highest surface to come down onto. Probing only the
                // capsule centre is not enough: after a single frame of travel the
                // centre is still over the lower floor while the capsule's leading
                // edge already overhangs the step, so a centre-only probe drops the
                // body straight back down and the step never gets climbed.
                float dirLen = (float) Math.sqrt(wanted2);
                float aheadX = dirLen > 1e-6f ? wantedX / dirLen * radius * 0.95f : 0f;
                float aheadZ = dirLen > 1e-6f ? wantedZ / dirLen * radius * 0.95f : 0f;

                float landing = probeGround(mesh, position.x, position.z);
                float ahead = probeGround(mesh, position.x + aheadX, position.z + aheadZ);
                float best = Math.max(landing, ahead);

                boolean reachable = best > Float.NEGATIVE_INFINITY
                        && best <= preMove.y + stepHeight + 0.02f
                        && best >= preMove.y - 0.02f;
                if (reachable) {
                    position.y = best;
                    grounded = true;
                    groundNormal.set(probeNormal);
                    resolve(mesh);
                } else {
                    position.set(stepResult); // nothing to stand on, keep the blocked result
                }
            } else {
                position.set(stepResult);
            }
        }

        // Walking down a slope or stairs would otherwise leave the body airborne
        // for a frame each step, which reads as a stutter. Snap to the floor.
        if (wasGrounded && !grounded && velocity.y <= 0f) {
            tmp.set(position.x, position.y + radius * 0.5f, position.z);
            float dist = mesh.raycast(tmp, probeDir, stepHeight + radius * 0.5f + 0.05f, probeNormal);
            if (dist >= 0f && probeNormal.y >= maxSlopeCos) {
                position.y = tmp.y - dist;
                grounded = true;
                groundNormal.set(probeNormal);
                velocity.y = 0f;
            }
        }
    }

    /**
     * Casts down from just above the capsule's feet at (x, z).
     *
     * @return world y of the standable surface, or -inf if there is none
     */
    private float probeGround(CollisionMesh mesh, float x, float z) {
        tmp.set(x, position.y + radius * 0.5f, z);
        float dist = mesh.raycast(tmp, probeDir, stepHeight * 2f + radius, probeNormal);
        if (dist < 0f || probeNormal.y < maxSlopeCos) return Float.NEGATIVE_INFINITY;
        return tmp.y - dist;
    }

    /** Pushes the capsule out of anything it overlaps, up to a few iterations. */
    private void resolve(CollisionMesh mesh) {
        for (int iter = 0; iter < 4; iter++) {
            p0.set(position.x, position.y + radius, position.z);
            p1.set(position.x, position.y + height - radius, position.z);

            float pad = radius + 0.05f;
            IntArray candidates = mesh.query(position.x - pad, position.y - pad, position.z - pad,
                    position.x + pad, position.y + height + pad, position.z + pad);
            if (candidates.size == 0) return;

            boolean touched = false;
            for (int i = 0; i < candidates.size; i++) {
                int tri = candidates.get(i);
                float[] v = mesh.vertsOf(tri);
                triA.set(v[0], v[1], v[2]);
                triB.set(v[3], v[4], v[5]);
                triC.set(v[6], v[7], v[8]);

                float dist = closestSegmentTriangle(p0, p1, triA, triB, triC, bestSeg, bestTri);
                // Ground detection uses a skin wider than the depenetration test.
                // Resolving pushes the capsule to exactly one radius away, so an
                // exact test would report "not touching" on the very next frame
                // and the body would flicker between grounded and falling.
                if (dist >= radius + GROUND_SKIN) continue;

                push.set(bestSeg).sub(bestTri);
                if (push.len2() < 1e-10f) {
                    // Dead centre on the surface: fall back to the face normal.
                    push.set(mesh.normalOf(tri));
                    tmp.set(p0).add(p1).scl(0.5f).sub(bestTri);
                    if (tmp.dot(push) < 0f) push.scl(-1f);
                    dist = 0f;
                }
                push.nor();

                if (dist < radius) {
                    position.mulAdd(push, radius - dist + 1e-4f);
                    p0.set(position.x, position.y + radius, position.z);
                    p1.set(position.x, position.y + height - radius, position.z);
                    touched = true;
                }

                // A contact pointing up under the capsule is floor to stand on.
                if (push.y >= maxSlopeCos && bestTri.y <= position.y + radius + 0.02f) {
                    if (!grounded || push.y > groundNormal.y) groundNormal.set(push);
                    grounded = true;
                }
            }
            if (!touched) return;
        }
    }

    /**
     * Distance between segment p0-p1 and triangle abc, writing the closest pair
     * into {@code outSeg} / {@code outTri}. The closest pair always lies at a
     * segment endpoint or on a triangle edge, so those five cases cover it.
     */
    static float closestSegmentTriangle(Vector3 p0, Vector3 p1, Vector3 a, Vector3 b, Vector3 c,
                                        Vector3 outSeg, Vector3 outTri) {
        float best = Float.MAX_VALUE;

        CollisionMesh.closestPointOnTriangle(p0, a, b, c, SCRATCH_TRI);
        float d = p0.dst2(SCRATCH_TRI);
        if (d < best) { best = d; outSeg.set(p0); outTri.set(SCRATCH_TRI); }

        CollisionMesh.closestPointOnTriangle(p1, a, b, c, SCRATCH_TRI);
        d = p1.dst2(SCRATCH_TRI);
        if (d < best) { best = d; outSeg.set(p1); outTri.set(SCRATCH_TRI); }

        d = CollisionMesh.closestSegmentSegment(p0, p1, a, b, SCRATCH_A, SCRATCH_B);
        if (d < best) { best = d; outSeg.set(SCRATCH_A); outTri.set(SCRATCH_B); }

        d = CollisionMesh.closestSegmentSegment(p0, p1, b, c, SCRATCH_A, SCRATCH_B);
        if (d < best) { best = d; outSeg.set(SCRATCH_A); outTri.set(SCRATCH_B); }

        d = CollisionMesh.closestSegmentSegment(p0, p1, c, a, SCRATCH_A, SCRATCH_B);
        if (d < best) { best = d; outSeg.set(SCRATCH_A); outTri.set(SCRATCH_B); }

        return (float) Math.sqrt(best);
    }

    // Single-threaded game loop, so shared scratch is safe and keeps this
    // allocation-free in the hot path.
    private static final Vector3 SCRATCH_TRI = new Vector3();
    private static final Vector3 SCRATCH_A = new Vector3();
    private static final Vector3 SCRATCH_B = new Vector3();

    /** Places the body at a spawn point without carrying velocity over. */
    public void teleport(float x, float y, float z) {
        position.set(x, y, z);
        velocity.setZero();
        grounded = false;
        justLanded = false;
    }

    /** Centre of the capsule, useful for camera targets and lock-on. */
    public Vector3 center(Vector3 out) {
        return out.set(position.x, position.y + height * 0.5f, position.z);
    }
}
