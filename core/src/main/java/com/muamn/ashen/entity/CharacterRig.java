package com.muamn.ashen.entity;

import com.badlogic.gdx.graphics.g3d.Model;
import com.badlogic.gdx.graphics.g3d.ModelInstance;
import com.badlogic.gdx.graphics.g3d.model.Node;
import com.badlogic.gdx.math.MathUtils;
import com.badlogic.gdx.math.Matrix4;
import com.badlogic.gdx.math.Vector3;

/**
 * Drives a {@link HumanoidFactory} skeleton with hand-written poses.
 *
 * There is no animation file anywhere in this project. Every pose is a function
 * of time and movement speed, which means a walk cycle automatically matches the
 * speed the body is actually travelling at - no foot sliding, no clip blending,
 * and no exported animation to keep in sync when a limb length changes.
 */
public class CharacterRig {

    public final Model model;
    public final ModelInstance instance;

    private final Node hips, torso, head;
    private final Node shoulderL, shoulderR, elbowL, elbowR;
    private final Node hipL, hipR, kneeL, kneeR;
    private final Node weapon;

    private final float restHipY;
    private final float hunch;

    /** Advances with distance travelled, so the stride matches ground speed. */
    private float stridePhase;

    public CharacterRig(Model model, HumanoidSpec spec) {
        this.model = model;
        this.instance = new ModelInstance(model);
        this.hunch = spec.hunch;

        hips = require("hips");
        torso = require("torso");
        head = require("head");
        shoulderL = require("shoulderL");
        shoulderR = require("shoulderR");
        elbowL = require("elbowL");
        elbowR = require("elbowR");
        hipL = require("hipL");
        hipR = require("hipR");
        kneeL = require("kneeL");
        kneeR = require("kneeR");
        weapon = instance.getNode("weapon", true);

        restHipY = hips.translation.y;
    }

    private Node require(String id) {
        Node n = instance.getNode(id, true);
        if (n == null) throw new IllegalStateException("rig is missing node " + id);
        return n;
    }

    /** Resets every joint to the T-less rest pose before a pose function runs. */
    private void clear() {
        hips.translation.set(0f, restHipY, 0f);
        setRot(hips, 0f, 0f, 0f);
        setRot(torso, hunch, 0f, 0f);
        setRot(head, -hunch * 0.5f, 0f, 0f);
        setRot(shoulderL, 0f, 0f, -6f);
        setRot(shoulderR, 0f, 0f, 6f);
        setRot(elbowL, 0f, 0f, 0f);
        setRot(elbowR, 0f, 0f, 0f);
        setRot(hipL, 0f, 0f, 0f);
        setRot(hipR, 0f, 0f, 0f);
        setRot(kneeL, 0f, 0f, 0f);
        setRot(kneeR, 0f, 0f, 0f);
    }

    /**
     * Standing and moving. {@code speed} is metres/second along the ground and
     * {@code runSpeed} is what counts as a full sprint.
     */
    public void poseLocomotion(float dt, float speed, float runSpeed, float time) {
        clear();
        float gait = MathUtils.clamp(speed / Math.max(runSpeed, 0.001f), 0f, 1f);

        if (speed > 0.05f) {
            // One full cycle per 1.35m of travel keeps the feet planted.
            stridePhase += speed * dt * (MathUtils.PI2 / 1.35f);
        } else {
            stridePhase = 0f;
        }
        float ph = stridePhase;

        // Idle breathing, faded out as the character starts moving.
        float idle = 1f - gait;
        float breath = MathUtils.sin(time * 1.6f) * 1.6f * idle;
        setRot(torso, hunch + breath * 0.5f + gait * 9f, 0f, 0f);
        hips.translation.y = restHipY + breath * 0.004f;

        float legSwing = MathUtils.lerp(7f, 42f, gait);
        float armSwing = MathUtils.lerp(4f, 34f, gait);
        float kneeBend = MathUtils.lerp(4f, 58f, gait);

        float sinL = MathUtils.sin(ph), sinR = MathUtils.sin(ph + MathUtils.PI);

        setRot(hipL, sinL * legSwing, 0f, 0f);
        setRot(hipR, sinR * legSwing, 0f, 0f);
        // Knees only fold on the swing-through half of the cycle.
        setRot(kneeL, -Math.max(0f, -sinL) * kneeBend - 3f, 0f, 0f);
        setRot(kneeR, -Math.max(0f, -sinR) * kneeBend - 3f, 0f, 0f);

        // Arms counter-swing against the legs.
        setRot(shoulderL, sinR * armSwing, 0f, -6f - gait * 4f);
        setRot(shoulderR, sinL * armSwing * 0.55f, 0f, 6f + gait * 4f);
        setRot(elbowL, -12f - gait * 26f, 0f, 0f);
        // The weapon arm stays low and ready rather than swinging freely.
        setRot(elbowR, -20f - gait * 18f, 0f, 0f);

        // Vertical bob, twice per stride.
        hips.translation.y += Math.abs(MathUtils.sin(ph)) * 0.035f * gait;

        instance.calculateTransforms();
    }

    /** Forward tuck-and-roll. {@code t} runs 0..1 across the whole roll. */
    public void poseRoll(float t) {
        clear();
        float spin = MathUtils.clamp(t, 0f, 1f);
        // Ease the spin so the character commits fast and lands settled.
        float eased = spin < 0.5f ? 2f * spin * spin : 1f - (float) Math.pow(-2f * spin + 2f, 2f) / 2f;

        setRot(hips, -360f * eased, 0f, 0f);
        // Duck toward the ground through the middle of the roll.
        float tuck = MathUtils.sin(spin * MathUtils.PI);
        hips.translation.y = restHipY - 0.34f * tuck;

        setRot(torso, hunch + 42f * tuck, 0f, 0f);
        setRot(hipL, 78f * tuck, 0f, 0f);
        setRot(hipR, 78f * tuck, 0f, 0f);
        setRot(kneeL, -104f * tuck, 0f, 0f);
        setRot(kneeR, -104f * tuck, 0f, 0f);
        setRot(shoulderL, 52f * tuck, 0f, -16f);
        setRot(shoulderR, 52f * tuck, 0f, 16f);
        setRot(elbowL, -84f * tuck, 0f, 0f);
        setRot(elbowR, -84f * tuck, 0f, 0f);

        instance.calculateTransforms();
    }

    /** Short hop backwards; the body stays upright and leans away. */
    public void poseBackstep(float t) {
        clear();
        float arc = MathUtils.sin(MathUtils.clamp(t, 0f, 1f) * MathUtils.PI);
        setRot(torso, hunch - 22f * arc, 0f, 0f);
        hips.translation.y = restHipY + 0.10f * arc;
        setRot(hipL, -34f * arc, 0f, 0f);
        setRot(hipR, -20f * arc, 0f, 0f);
        setRot(kneeL, -62f * arc, 0f, 0f);
        setRot(kneeR, -40f * arc, 0f, 0f);
        setRot(shoulderL, -30f * arc, 0f, -14f);
        setRot(shoulderR, -18f * arc, 0f, 12f);
        setRot(elbowL, -46f * arc, 0f, 0f);
        setRot(elbowR, -34f * arc, 0f, 0f);
        instance.calculateTransforms();
    }

    /** Airborne: legs trail, arms come up. */
    public void poseFall(float verticalSpeed) {
        clear();
        float fall = MathUtils.clamp(-verticalSpeed / 12f, 0f, 1f);
        setRot(torso, hunch + 10f * fall, 0f, 0f);
        setRot(hipL, -18f - 14f * fall, 0f, 0f);
        setRot(hipR, 12f + 10f * fall, 0f, 0f);
        setRot(kneeL, -40f - 20f * fall, 0f, 0f);
        setRot(kneeR, -14f, 0f, 0f);
        setRot(shoulderL, -46f * fall, 0f, -24f);
        setRot(shoulderR, -34f * fall, 0f, 20f);
        setRot(elbowL, -50f, 0f, 0f);
        setRot(elbowR, -40f, 0f, 0f);
        instance.calculateTransforms();
    }

    /** Places the rig in the world. {@code facingDeg} is a heading around +Y. */
    public void place(Vector3 feetPosition, float facingDeg) {
        instance.transform.setToTranslation(feetPosition);
        instance.transform.rotate(Vector3.Y, facingDeg);
    }

    /** World transform of the weapon grip, for drawing a held weapon. */
    public Matrix4 weaponTransform(Matrix4 out) {
        if (weapon == null) return out.set(instance.transform);
        return out.set(instance.transform).mul(weapon.globalTransform);
    }

    private static void setRot(Node n, float pitch, float yaw, float roll) {
        n.rotation.setEulerAngles(yaw, pitch, roll);
    }

    public float getStridePhase() {
        return stridePhase;
    }
}
