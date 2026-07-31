package com.muamn.ashen.camera;

import com.badlogic.gdx.graphics.PerspectiveCamera;
import com.badlogic.gdx.math.MathUtils;
import com.badlogic.gdx.math.Vector3;

import com.muamn.ashen.Config;
import com.muamn.ashen.world.CollisionMesh;

/**
 * Third-person camera with free orbit and Souls-style lock-on.
 *
 * Two details do most of the work for how the game feels:
 * the pivot lags the character with a frame-rate independent smoothing term, so
 * the world does not snap around during a roll; and the boom is shortened by a
 * raycast so the camera never ends up inside a wall - it slides in close instead,
 * which is what every third-person game of this era did.
 */
public class OrbitCamera {

    public final PerspectiveCamera camera;

    /** Orbit angles in degrees. Yaw is around +Y, pitch is above/below the horizon. */
    public float yaw = 0f;
    public float pitch = -8f;
    public float distance = Config.CAM_DISTANCE;

    private final Vector3 pivot = new Vector3();
    private final Vector3 desiredPivot = new Vector3();
    private final Vector3 boom = new Vector3();
    private final Vector3 tmp = new Vector3();
    private final Vector3 rayDir = new Vector3();
    private final Vector3 hitNormal = new Vector3();

    /** Non-null while locked on; the camera frames this point instead of orbiting. */
    private Vector3 lockTarget;

    private boolean initialised;

    public OrbitCamera(float aspect) {
        camera = new PerspectiveCamera(Config.CAMERA_FOV, aspect, 1f);
        camera.near = Config.CAMERA_NEAR;
        camera.far = Config.CAMERA_FAR;
        camera.update();
    }

    public void setAspect(float aspect) {
        // PerspectiveCamera derives aspect from viewport dimensions.
        camera.viewportWidth = aspect;
        camera.viewportHeight = 1f;
        camera.update();
    }

    public void setLockTarget(Vector3 target) {
        this.lockTarget = target;
    }

    public boolean isLocked() {
        return lockTarget != null;
    }

    /** Applies player look input. Ignored on the yaw axis while locked on. */
    public void applyLook(float deltaYaw, float deltaPitch) {
        if (lockTarget == null) yaw += deltaYaw;
        pitch = MathUtils.clamp(pitch + deltaPitch, Config.CAM_MIN_PITCH, Config.CAM_MAX_PITCH);
    }

    /**
     * @param focus  point the camera looks at, usually the player's chest
     * @param mesh   level collision, used to pull the camera out of walls
     */
    public void update(Vector3 focus, CollisionMesh mesh, float dt) {
        desiredPivot.set(focus.x, focus.y + Config.CAM_HEIGHT, focus.z);
        if (!initialised) {
            pivot.set(desiredPivot);
            initialised = true;
        } else {
            // Exponential smoothing, rewritten to be independent of frame rate.
            float t = 1f - (float) Math.pow(0.0016f, dt);
            pivot.lerp(desiredPivot, t);
        }

        float targetPitch = pitch;
        if (lockTarget != null) {
            // Face the target, and look down at it if it is shorter than the player.
            tmp.set(lockTarget).sub(pivot);
            float horiz = Vector3.len(tmp.x, 0f, tmp.z);
            float wantYaw = MathUtils.atan2(tmp.x, tmp.z) * MathUtils.radiansToDegrees;
            yaw = approachAngle(yaw, wantYaw + 180f, 620f * dt);
            float wantPitch = MathUtils.clamp(
                    MathUtils.atan2(tmp.y, Math.max(horiz, 0.01f)) * MathUtils.radiansToDegrees - 6f,
                    Config.CAM_MIN_PITCH, 20f);
            targetPitch = MathUtils.lerp(pitch, wantPitch, Math.min(1f, 8f * dt));
            pitch = targetPitch;
        }

        // Boom direction: behind the pivot, raised by pitch.
        float cy = MathUtils.cosDeg(targetPitch);
        boom.set(MathUtils.sinDeg(yaw) * cy, -MathUtils.sinDeg(targetPitch), MathUtils.cosDeg(yaw) * cy);
        boom.nor();

        float wanted = distance;
        if (mesh != null && mesh.triangleCount() > 0) {
            rayDir.set(boom);
            float hit = mesh.raycast(pivot, rayDir, wanted + Config.CAM_COLLISION_PAD, hitNormal);
            if (hit >= 0f) wanted = Math.max(0.6f, hit - Config.CAM_COLLISION_PAD);
        }

        camera.position.set(pivot).mulAdd(boom, wanted);
        camera.up.set(Vector3.Y);
        camera.lookAt(pivot);
        camera.update();
    }

    /** Yaw of the camera projected onto the ground, for camera-relative movement. */
    public float groundYaw() {
        return yaw + 180f;
    }

    /** Places the camera without smoothing, e.g. after a respawn. */
    public void snapTo(Vector3 focus) {
        desiredPivot.set(focus.x, focus.y + Config.CAM_HEIGHT, focus.z);
        pivot.set(desiredPivot);
        initialised = true;
    }

    private static float approachAngle(float current, float target, float maxDelta) {
        float diff = ((target - current) % 360f + 540f) % 360f - 180f;
        if (Math.abs(diff) <= maxDelta) return target;
        return current + Math.signum(diff) * maxDelta;
    }
}
