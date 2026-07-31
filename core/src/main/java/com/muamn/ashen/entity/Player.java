package com.muamn.ashen.entity;

import com.badlogic.gdx.math.MathUtils;
import com.badlogic.gdx.math.Vector2;
import com.badlogic.gdx.math.Vector3;

import com.muamn.ashen.Config;
import com.muamn.ashen.input.ControlState;
import com.muamn.ashen.world.CharacterBody;
import com.muamn.ashen.world.CollisionMesh;

/**
 * The player character: a state machine over a {@link CharacterBody}.
 *
 * Committed actions are the point. Once a roll starts, input stops steering it -
 * you chose a direction and now you live with it. That single rule is most of
 * what separates Souls movement from an action game where dodging is free, and
 * it is why the state machine owns velocity outright instead of blending inputs
 * into it every frame.
 */
public class Player {

    public enum State { GROUNDED, ROLLING, BACKSTEPPING, AIRBORNE, DEAD }

    public final CharacterBody body = new CharacterBody();
    public final Stats stats = new Stats();
    public final CharacterRig rig;

    private State state = State.GROUNDED;
    private float stateTime;

    /** Heading in degrees; the model faces +Z at 0. */
    private float facing;
    private float targetFacing;

    /** Locked movement direction for the duration of a committed action. */
    private final Vector3 lockedDir = new Vector3(0f, 0f, 1f);

    private final Vector3 wish = new Vector3();
    private final Vector3 tmp = new Vector3();
    private final Vector2 flatMove = new Vector2();

    private float time;
    /** Set while a roll's invulnerability window is open. */
    private boolean invulnerable;

    public Player(CharacterRig rig) {
        this.rig = rig;
        body.radius = Config.PLAYER_RADIUS;
        body.height = Config.PLAYER_HEIGHT;
    }

    public State getState() {
        return state;
    }

    public boolean isInvulnerable() {
        return invulnerable;
    }

    public float getFacing() {
        return facing;
    }

    /** Ground speed in metres/second, ignoring vertical motion. */
    public float groundSpeed() {
        return Vector3.len(body.velocity.x, 0f, body.velocity.z);
    }

    public void spawn(float x, float y, float z, float facingDeg) {
        body.teleport(x, y, z);
        facing = targetFacing = facingDeg;
        state = State.GROUNDED;
        stateTime = 0f;
        stats.health = stats.maxHealth;
        stats.stamina = stats.maxStamina;
    }

    /**
     * One fixed simulation step.
     *
     * @param cameraYaw yaw of the camera, so movement is camera-relative
     * @param lockTarget position being locked on to, or null
     */
    public void update(ControlState input, CollisionMesh mesh, float cameraYaw,
                       Vector3 lockTarget, float dt) {
        time += dt;
        stateTime += dt;

        if (state == State.DEAD) {
            body.velocity.x = 0f;
            body.velocity.z = 0f;
            body.step(mesh, dt);
            return;
        }

        // Camera-relative movement basis, flattened to the ground plane.
        float fx = -MathUtils.sinDeg(cameraYaw), fz = -MathUtils.cosDeg(cameraYaw);
        float rx = -fz, rz = fx;
        flatMove.set(input.move);
        if (flatMove.len2() > 1f) flatMove.nor();
        wish.set(fx * flatMove.y + rx * flatMove.x, 0f, fz * flatMove.y + rz * flatMove.x);
        float wishLen = Vector3.len(wish.x, 0f, wish.z);
        if (wishLen > 1e-4f) wish.scl(1f / wishLen);

        switch (state) {
            case GROUNDED:   updateGrounded(input, wishLen, lockTarget, dt); break;
            case ROLLING:    updateRoll(dt); break;
            case BACKSTEPPING: updateBackstep(dt); break;
            case AIRBORNE:   updateAirborne(wishLen, dt); break;
            default: break;
        }

        boolean actionBlocksRegen = state == State.ROLLING || state == State.BACKSTEPPING;
        stats.update(dt, actionBlocksRegen);

        body.step(mesh, dt);

        if (state == State.GROUNDED && !body.grounded) {
            setState(State.AIRBORNE);
        } else if (state == State.AIRBORNE && body.grounded) {
            setState(State.GROUNDED);
        }

        // Turn toward the intended heading. Committed actions keep their facing.
        float turnRate = (state == State.ROLLING || state == State.BACKSTEPPING)
                ? 0f : Config.TURN_SPEED * 57.29578f * dt;
        facing = approachAngle(facing, targetFacing, turnRate);

        updatePose(dt);
    }

    private void updateGrounded(ControlState input, float wishLen, Vector3 lockTarget, float dt) {
        boolean wantsRoll = input.rollPressed;

        if (wantsRoll) {
            if (wishLen > 0.2f) {
                if (stats.spendStamina(Config.ROLL_STAMINA)) {
                    lockedDir.set(wish);
                    targetFacing = facing = headingOf(lockedDir);
                    setState(State.ROLLING);
                    return;
                }
            } else if (stats.spendStamina(Config.BACKSTEP_STAMINA)) {
                lockedDir.set(MathUtils.sinDeg(facing), 0f, MathUtils.cosDeg(facing)).scl(-1f);
                setState(State.BACKSTEPPING);
                return;
            }
        }

        boolean sprinting = input.sprintHeld && wishLen > 0.1f && stats.stamina > 0f;
        if (sprinting) {
            stats.drainStamina(Config.SPRINT_STAMINA_PER_SEC * dt);
            if (stats.stamina <= 0f) sprinting = false;
        }

        float speed = sprinting ? Config.RUN_SPEED : Config.WALK_SPEED * MathUtils.clamp(wishLen / 0.9f, 0f, 1f);
        if (wishLen <= 0.05f) speed = 0f;

        // Accelerate rather than snap, so direction changes have weight.
        float accel = sprinting ? 22f : 18f;
        tmp.set(wish).scl(speed);
        body.velocity.x = MathUtils.lerp(body.velocity.x, tmp.x, Math.min(1f, accel * dt));
        body.velocity.z = MathUtils.lerp(body.velocity.z, tmp.z, Math.min(1f, accel * dt));

        if (wishLen > 0.05f) {
            // While locked on, walk sideways facing the target instead of turning.
            if (lockTarget != null && !input.sprintHeld) {
                tmp.set(lockTarget).sub(body.position);
                targetFacing = headingOf(tmp);
            } else {
                targetFacing = headingOf(wish);
            }
        } else if (lockTarget != null) {
            tmp.set(lockTarget).sub(body.position);
            targetFacing = headingOf(tmp);
        }
    }

    private void updateRoll(float dt) {
        float t = stateTime / Config.ROLL_DURATION;
        invulnerable = t >= Config.ROLL_IFRAME_START && t <= Config.ROLL_IFRAME_END;

        // Fast out of the gate, settling toward the end.
        float speed = Config.ROLL_SPEED * (1f - MathUtils.clamp(t, 0f, 1f) * 0.72f);
        body.velocity.x = lockedDir.x * speed;
        body.velocity.z = lockedDir.z * speed;

        if (t >= 1f) {
            invulnerable = false;
            setState(State.GROUNDED);
        }
    }

    private void updateBackstep(float dt) {
        float t = stateTime / Config.BACKSTEP_DURATION;
        float speed = Config.BACKSTEP_SPEED * (1f - MathUtils.clamp(t, 0f, 1f)) * 1.3f;
        body.velocity.x = lockedDir.x * speed;
        body.velocity.z = lockedDir.z * speed;
        if (t >= 1f) setState(State.GROUNDED);
    }

    private void updateAirborne(float wishLen, float dt) {
        // Very little air control, by design.
        if (wishLen > 0.05f) {
            body.velocity.x = MathUtils.lerp(body.velocity.x, wish.x * Config.WALK_SPEED, Math.min(1f, 1.6f * dt));
            body.velocity.z = MathUtils.lerp(body.velocity.z, wish.z * Config.WALK_SPEED, Math.min(1f, 1.6f * dt));
            targetFacing = headingOf(wish);
        }
    }

    private void updatePose(float dt) {
        switch (state) {
            case ROLLING:
                rig.poseRoll(stateTime / Config.ROLL_DURATION);
                break;
            case BACKSTEPPING:
                rig.poseBackstep(stateTime / Config.BACKSTEP_DURATION);
                break;
            case AIRBORNE:
                rig.poseFall(body.velocity.y);
                break;
            default:
                rig.poseLocomotion(dt, groundSpeed(), Config.RUN_SPEED, time);
                break;
        }
        rig.place(body.position, facing);
    }

    private void setState(State next) {
        state = next;
        stateTime = 0f;
        if (next != State.ROLLING) invulnerable = false;
    }

    /** Heading in degrees for a direction vector, matching the model's +Z front. */
    private static float headingOf(Vector3 dir) {
        return MathUtils.atan2(dir.x, dir.z) * MathUtils.radiansToDegrees;
    }

    private static float approachAngle(float current, float target, float maxDelta) {
        if (maxDelta <= 0f) return current;
        float diff = ((target - current) % 360f + 540f) % 360f - 180f;
        if (Math.abs(diff) <= maxDelta) return target;
        return current + Math.signum(diff) * maxDelta;
    }

    /** Chest height, used as the camera focus and the lock-on anchor. */
    public Vector3 chest(Vector3 out) {
        return out.set(body.position.x, body.position.y + body.height * 0.62f, body.position.z);
    }
}
