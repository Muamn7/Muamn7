package com.muamn.ashen.entity;

import com.badlogic.gdx.graphics.g3d.Model;
import com.badlogic.gdx.graphics.g3d.ModelInstance;
import com.badlogic.gdx.graphics.g3d.model.Node;
import com.badlogic.gdx.math.MathUtils;
import com.badlogic.gdx.math.Vector3;
import com.badlogic.gdx.utils.Array;

import com.muamn.ashen.combat.AttackDef;

/**
 * Animates any {@link CreatureFactory} skeleton, whatever its limb plan.
 *
 * The gait is a travelling wave: each leg pair is offset a fixed fraction of a
 * cycle behind the one in front, and left and right are half a cycle apart. That
 * one rule produces a dog's trot at two pairs and a spider's ripple at four,
 * which is the whole reason the bestiary can be data.
 */
public class CreatureRig {

    private final Model model;
    public final ModelInstance instance;
    private final CreatureSpec spec;

    private final Node body;
    private final Node neck;
    private final Node head;
    private final Array<Node> hips = new Array<>();
    private final Array<Node> knees = new Array<>();
    /** Parallel to hips: +1 for the left side, -1 for the right. */
    private final Array<Integer> sides = new Array<>();
    /** Parallel to hips: which pair, front to back. */
    private final Array<Integer> pairs = new Array<>();
    private final Array<Node> tail = new Array<>();
    private final Node wingL, wingR;
    private final Node weapon;

    private final float restBodyY;
    private float stridePhase;
    private float time;

    public CreatureRig(Model model, CreatureSpec spec) {
        this.model = model;
        this.spec = spec;
        this.instance = new ModelInstance(model);

        body = require("body");
        neck = instance.getNode("neck", true);
        head = instance.getNode("head", true);
        weapon = instance.getNode("weapon", true);

        for (int pair = 0; pair < spec.legPairs; pair++) {
            for (int side = 0; side < 2; side++) {
                String suffix = (side == 0 ? "L" : "R") + pair;
                Node hip = instance.getNode("hip" + suffix, true);
                Node knee = instance.getNode("knee" + suffix, true);
                if (hip == null || knee == null) continue;
                hips.add(hip);
                knees.add(knee);
                sides.add(side == 0 ? 1 : -1);
                pairs.add(pair);
            }
        }
        for (int i = 0; i < spec.tailSegments; i++) {
            Node segment = instance.getNode("tail" + i, true);
            if (segment != null) tail.add(segment);
        }
        wingL = instance.getNode("wingL", true);
        wingR = instance.getNode("wingR", true);

        restBodyY = body.translation.y;
    }

    private Node require(String id) {
        Node n = instance.getNode(id, true);
        if (n == null) throw new IllegalStateException("creature rig is missing node " + id);
        return n;
    }

    private void clear() {
        body.translation.set(0f, restBodyY, 0f);
        setRot(body, 0f, 0f, 0f);
        if (neck != null) setRot(neck, 0f, 0f, 0f);
        if (head != null) setRot(head, 0f, 0f, 0f);
        for (int i = 0; i < hips.size; i++) {
            // Legs splay outward at rest; a spider's far more than a hound's.
            setRot(hips.get(i), 0f, 0f, -sides.get(i) * spec.kneeFlare);
            setRot(knees.get(i), 0f, 0f, sides.get(i) * spec.kneeFlare * 1.35f);
        }
        for (Node segment : tail) setRot(segment, 0f, 0f, 0f);
        if (wingL != null) setRot(wingL, 0f, 0f, 0f);
        if (wingR != null) setRot(wingR, 0f, 0f, 0f);
    }

    public void poseLocomotion(float dt, float speed) {
        clear();
        time += dt;

        if (speed > 0.05f) {
            stridePhase += speed * dt * MathUtils.PI2 * spec.stridePerMetre * 0.5f;
        }
        float moving = MathUtils.clamp(speed / 3.5f, 0f, 1f);
        float idle = 1f - moving;

        float swing = MathUtils.lerp(3f, 34f, moving);
        float lift = MathUtils.lerp(2f, 30f, moving);

        for (int i = 0; i < hips.size; i++) {
            // Half a cycle between left and right, a third of one between pairs.
            float phase = stridePhase
                    + (sides.get(i) > 0 ? 0f : MathUtils.PI)
                    + pairs.get(i) * MathUtils.PI * 0.66f;
            float forward = MathUtils.sin(phase);
            float raise = Math.max(0f, -MathUtils.cos(phase));

            setRot(hips.get(i), forward * swing, 0f, -sides.get(i) * spec.kneeFlare);
            setRot(knees.get(i), -raise * lift - 4f, 0f,
                    sides.get(i) * spec.kneeFlare * 1.35f);
        }

        // Body bob is twice the stride frequency, as it is on four legs.
        body.translation.y = restBodyY
                + MathUtils.sin(stridePhase * 2f) * spec.bob * moving
                + MathUtils.sin(time * 1.4f) * 0.012f * idle;
        setRot(body, MathUtils.sin(stridePhase) * 3f * moving,
                MathUtils.sin(stridePhase) * 5f * moving, 0f);

        if (neck != null) {
            setRot(neck, -6f * moving + MathUtils.sin(time * 1.7f) * 2f * idle, 0f, 0f);
        }
        wave(tail, stridePhase, 14f * moving + 5f * idle);
        flap(moving);
        instance.calculateTransforms();
    }

    /** Lunging bite or claw. Reuses the attack's own windup/active split. */
    public void poseAttack(AttackDef attack, float t) {
        clear();
        float duration = Math.max(attack.duration(), 1e-4f);
        float windupEnd = attack.windup / duration;
        float activeEnd = attack.activeEnd() / duration;

        float rear;      // pulling back
        float lunge;     // driving forward
        if (t < windupEnd) {
            rear = windupEnd <= 0f ? 1f : t / windupEnd;
            rear = rear * rear * (3f - 2f * rear);
            lunge = 0f;
        } else {
            rear = 1f;
            float span = Math.max(activeEnd - windupEnd, 1e-4f);
            lunge = MathUtils.clamp((t - windupEnd) / span, 0f, 1f);
            if (t > activeEnd) {
                float settle = MathUtils.clamp((t - activeEnd) / Math.max(1f - activeEnd, 1e-4f),
                        0f, 1f);
                rear = 1f - settle;
                lunge = 1f - settle * 0.8f;
            }
        }

        float pitch = -22f * rear + 34f * lunge;
        setRot(body, pitch, 0f, 0f);
        body.translation.y = restBodyY + 0.10f * rear - 0.16f * lunge;
        if (neck != null) setRot(neck, -30f * rear + 52f * lunge, 0f, 0f);
        // The jaw opening is the tell; it happens during the windup.
        if (head != null) setRot(head, -26f * rear + 40f * lunge, 0f, 0f);

        for (int i = 0; i < hips.size; i++) {
            boolean front = pairs.get(i) == 0;
            float amount = front ? (-40f * rear + 55f * lunge) : (18f * rear - 10f * lunge);
            setRot(hips.get(i), amount, 0f, -sides.get(i) * spec.kneeFlare);
            setRot(knees.get(i), -18f - 26f * rear, 0f, sides.get(i) * spec.kneeFlare * 1.35f);
        }
        wave(tail, rear * 6f, 26f);
        flap(lunge);
        instance.calculateTransforms();
    }

    public void poseStagger(float t) {
        clear();
        float arc = MathUtils.sin(MathUtils.clamp(t, 0f, 1f) * MathUtils.PI);
        setRot(body, 22f * arc, -18f * arc, 12f * arc);
        body.translation.y = restBodyY - 0.10f * arc;
        if (neck != null) setRot(neck, 26f * arc, 0f, 0f);
        for (int i = 0; i < hips.size; i++) {
            setRot(hips.get(i), -14f * arc, 0f, -sides.get(i) * spec.kneeFlare);
            setRot(knees.get(i), -30f * arc - 6f, 0f, sides.get(i) * spec.kneeFlare * 1.35f);
        }
        wave(tail, 0f, 24f * arc);
        instance.calculateTransforms();
    }

    /** Collapsing. Legs fold, body drops and rolls onto its side. */
    public void poseDeath(float t) {
        clear();
        float fall = MathUtils.clamp(t, 0f, 1f);
        float ease = fall * fall;
        setRot(body, 10f * ease, 0f, 74f * ease);
        body.translation.y = restBodyY * (1f - 0.80f * ease);
        if (neck != null) setRot(neck, 34f * ease, 0f, 0f);
        if (head != null) setRot(head, 22f * ease, 0f, 0f);
        for (int i = 0; i < hips.size; i++) {
            setRot(hips.get(i), 34f * ease, 0f, -sides.get(i) * spec.kneeFlare * (1f - ease));
            setRot(knees.get(i), -78f * ease, 0f, sides.get(i) * spec.kneeFlare * (1f - ease));
        }
        wave(tail, 0f, 8f * (1f - ease));
        instance.calculateTransforms();
    }

    /** Ripples a chain of segments, each lagging the one before it. */
    private void wave(Array<Node> chain, float phase, float amplitude) {
        for (int i = 0; i < chain.size; i++) {
            float lag = phase - i * 0.7f;
            setRot(chain.get(i), 0f, MathUtils.sin(lag) * amplitude / Math.max(1, chain.size) * 2f, 0f);
        }
    }

    private void flap(float amount) {
        if (wingL == null || wingR == null) return;
        float beat = MathUtils.sin(time * 9f) * (18f + 34f * amount);
        setRot(wingL, 0f, 0f, beat);
        setRot(wingR, 0f, 0f, -beat);
    }

    public void place(Vector3 feetPosition, float facingDeg) {
        instance.transform.setToTranslation(feetPosition);
        instance.transform.rotate(Vector3.Y, facingDeg);
        if (spec.overallScale != 1f) {
            // Scale is baked into the mesh, so nothing more is needed here; this
            // stays as the single place a runtime size tweak would go.
            instance.transform.scale(1f, 1f, 1f);
        }
    }

    public Model getModel() {
        return model;
    }

    public Node getWeaponNode() {
        return weapon;
    }

    private static void setRot(Node n, float pitch, float yaw, float roll) {
        n.rotation.setEulerAngles(yaw, pitch, roll);
    }
}
