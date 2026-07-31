package com.muamn.ashen.world;

import com.badlogic.gdx.graphics.Color;
import com.badlogic.gdx.graphics.GL20;
import com.badlogic.gdx.graphics.VertexAttributes.Usage;
import com.badlogic.gdx.graphics.g3d.Material;
import com.badlogic.gdx.graphics.g3d.Model;
import com.badlogic.gdx.graphics.g3d.ModelInstance;
import com.badlogic.gdx.graphics.g3d.attributes.ColorAttribute;
import com.badlogic.gdx.graphics.g3d.attributes.TextureAttribute;
import com.badlogic.gdx.graphics.g3d.utils.MeshPartBuilder;
import com.badlogic.gdx.graphics.g3d.utils.ModelBuilder;
import com.badlogic.gdx.math.MathUtils;
import com.badlogic.gdx.math.Vector3;
import com.badlogic.gdx.utils.Disposable;

/**
 * Something in the level that hurts you.
 *
 * Every trap here telegraphs. A dart trap clicks before it fires, a blade is
 * visibly swinging long before you step into its arc, and spikes withdraw on a
 * rhythm you can watch from safety. A trap that kills without warning is not
 * difficulty, it is a memory test that only punishes the first run - and this
 * game already asks the player to learn enough.
 *
 * They are also not scenery with a damage number. Each one has a rest state, a
 * telegraph, a live window and a recovery, exactly like an attack does, because
 * that is what lets a player roll through one.
 */
public class Trap implements Disposable {

    public enum Kind {
        /** Fires along +Z of its facing when the player enters the trigger. */
        DART,
        /** Swings back and forth on its own clock. Never waits for anyone. */
        BLADE,
        /** Rises out of the floor on a rhythm. */
        SPIKES
    }

    public enum Phase { IDLE, TELEGRAPH, ACTIVE, RECOVER }

    public final Kind kind;
    public final Vector3 position = new Vector3();
    public final float facing;
    public final float damage;

    /** Half-extents of the volume that hurts, in the trap's own axes. */
    public final float reach;
    public final float halfWidth;

    /** Seconds of warning, of danger, and of being harmless afterwards. */
    public final float telegraph;
    public final float active;
    public final float recover;
    /**
     * Seconds between cycles for a trap that runs on its own clock. Zero means
     * it waits for the player instead.
     */
    public final float period;
    /** How close the player has to be for a triggered trap to go off. */
    public final float triggerRange;

    private Phase phase = Phase.IDLE;
    private float phaseTime;
    private float clock;
    /** Set for the frame the trap becomes live, so a sound fires once. */
    private boolean justFired;
    /** True once this cycle has already hit; a swing hurts once, not per frame. */
    private boolean hitThisCycle;

    private Model model;
    private ModelInstance instance;

    private final Vector3 tmp = new Vector3();

    private Trap(Kind kind, float x, float z, float facing, float damage,
                 float reach, float halfWidth,
                 float telegraph, float active, float recover,
                 float period, float triggerRange) {
        this.kind = kind;
        this.position.set(x, 0f, z);
        this.facing = facing;
        this.damage = damage;
        this.reach = reach;
        this.halfWidth = halfWidth;
        this.telegraph = telegraph;
        this.active = active;
        this.recover = recover;
        this.period = period;
        this.triggerRange = triggerRange;
    }

    // ---- presets ----------------------------------------------------------

    /**
     * A dart trap in a wall. Waits, clicks, then fires down a narrow lane.
     *
     * The telegraph is a fifth of a second - long enough to react to if you were
     * watching, short enough to catch you if you were not.
     */
    public static Trap dart(float x, float z, float facing, float damage) {
        return new Trap(Kind.DART, x, z, facing, damage,
                9f, 0.65f, 0.22f, 0.12f, 1.6f, 0f, 8f);
    }

    /** A blade on a pendulum, swinging on its own clock forever. */
    public static Trap blade(float x, float z, float facing, float damage, float period) {
        return new Trap(Kind.BLADE, x, z, facing, damage,
                2.6f, 0.5f, 0.30f, 0.34f, 0.3f, period, 0f);
    }

    /** Floor spikes that rise, hold, and sink again. */
    public static Trap spikes(float x, float z, float damage, float period) {
        return new Trap(Kind.SPIKES, x, z, 0f, damage,
                1.3f, 1.3f, 0.45f, 0.85f, 0.6f, period, 0f);
    }

    // ---- simulation -------------------------------------------------------

    public Phase phase() {
        return phase;
    }

    public boolean isLive() {
        return phase == Phase.ACTIVE;
    }

    /** True for the one frame the trap goes live. */
    public boolean justFired() {
        return justFired;
    }

    /**
     * Advances the trap.
     *
     * @return the damage to deal this frame, or 0
     */
    public float update(float dt, Vector3 playerPosition) {
        justFired = false;
        phaseTime += dt;

        switch (phase) {
            case IDLE:
                clock += dt;
                if (period > 0f) {
                    if (clock >= period) enter(Phase.TELEGRAPH);
                } else if (playerPosition != null && withinTrigger(playerPosition)) {
                    enter(Phase.TELEGRAPH);
                }
                break;
            case TELEGRAPH:
                if (phaseTime >= telegraph) {
                    enter(Phase.ACTIVE);
                    justFired = true;
                    hitThisCycle = false;
                }
                break;
            case ACTIVE:
                if (phaseTime >= active) enter(Phase.RECOVER);
                break;
            default:
                if (phaseTime >= recover) {
                    enter(Phase.IDLE);
                    clock = 0f;
                }
                break;
        }

        updateVisual();

        if (phase != Phase.ACTIVE || hitThisCycle || playerPosition == null) return 0f;
        if (!hurts(playerPosition)) return 0f;
        hitThisCycle = true;
        return damage;
    }

    private void enter(Phase next) {
        phase = next;
        phaseTime = 0f;
    }

    private boolean withinTrigger(Vector3 playerPosition) {
        // Only in front, and only in the lane the darts will actually cross.
        toLocal(playerPosition);
        return tmp.z > 0.4f && tmp.z <= triggerRange && Math.abs(tmp.x) <= halfWidth * 2.2f;
    }

    /** True while the player is standing in the part of the world that hurts. */
    public boolean hurts(Vector3 playerPosition) {
        if (kind == Kind.SPIKES) {
            float dx = playerPosition.x - position.x;
            float dz = playerPosition.z - position.z;
            return dx * dx + dz * dz <= reach * reach
                    && playerPosition.y < position.y + 2.2f;
        }
        toLocal(playerPosition);
        if (playerPosition.y < position.y - 1.2f || playerPosition.y > position.y + 2.4f) {
            return false;
        }
        if (kind == Kind.BLADE) {
            // The blade sweeps across its facing, so the danger is a bar, not a lane.
            return Math.abs(tmp.x) <= reach && Math.abs(tmp.z) <= halfWidth + 0.35f;
        }
        return tmp.z > 0f && tmp.z <= reach && Math.abs(tmp.x) <= halfWidth;
    }

    /** Puts the player into the trap's own axes, +Z along its facing. */
    private void toLocal(Vector3 world) {
        float dx = world.x - position.x;
        float dz = world.z - position.z;
        float cos = MathUtils.cosDeg(facing), sin = MathUtils.sinDeg(facing);
        tmp.set(dx * cos - dz * sin, world.y - position.y, dx * sin + dz * cos);
    }

    // ---- visual -----------------------------------------------------------

    /** Builds the trap's own geometry. Call once, after the textures exist. */
    public void buildVisual(TextureFactory textures) {
        long attrs = Usage.Position | Usage.Normal | Usage.TextureCoordinates;
        Material steel = new Material(
                TextureAttribute.createDiffuse(textures.get("steel")),
                ColorAttribute.createDiffuse(Color.WHITE));

        ModelBuilder mb = new ModelBuilder();
        mb.begin();
        MeshPartBuilder p = mb.part("trap", GL20.GL_TRIANGLES, attrs, steel);
        switch (kind) {
            case BLADE:
                // A wide flat blade hanging from a bar.
                MeshUtil.box(p, 0f, 2.9f, 0f, 0.14f, 0.5f, 0.14f, 2f);
                MeshUtil.blade(p, 0f, 0.6f, 0f, 2.3f, 1.5f, 0.10f, 0.9f, 2f);
                break;
            case SPIKES:
                for (int i = 0; i < 9; i++) {
                    float a = i * 40f;
                    float r = i == 0 ? 0f : 0.72f;
                    MeshUtil.taper(p, MathUtils.cosDeg(a) * r, MathUtils.sinDeg(a) * r,
                            0f, 1.15f, 0.20f, 0.20f, 0.02f, 0.02f, 2f);
                }
                break;
            default:
                // A plate with the holes the darts come from.
                MeshUtil.box(p, 0f, 1.1f, 0f, 1.3f, 1.5f, 0.22f, 2f);
                MeshUtil.box(p, -0.34f, 1.1f, 0.14f, 0.16f, 0.16f, 0.16f, 4f);
                MeshUtil.box(p, 0.34f, 1.1f, 0.14f, 0.16f, 0.16f, 0.16f, 4f);
                break;
        }
        model = mb.end();
        instance = new ModelInstance(model);
        updateVisual();
    }

    /**
     * Moves the visual to match the phase.
     *
     * This is the telegraph. The blade is where it looks, the spikes are as far
     * up as they look, and a player who reads the geometry is reading the truth -
     * the same volumes the damage test uses.
     */
    private void updateVisual() {
        if (instance == null) return;
        float t = progress();
        switch (kind) {
            case BLADE: {
                // A full swing across the arc, easing at the ends like a pendulum.
                float swing = MathUtils.sinDeg(clockPhase() * 360f) * 62f;
                instance.transform.setToTranslation(position.x, position.y, position.z);
                instance.transform.rotate(Vector3.Y, facing);
                instance.transform.rotate(Vector3.Z, swing);
                break;
            }
            case SPIKES: {
                float height;
                if (phase == Phase.TELEGRAPH) height = -1.1f + 0.35f * t;      // shivering up
                else if (phase == Phase.ACTIVE) height = -0.05f;
                else if (phase == Phase.RECOVER) height = -0.05f - 1.05f * t;
                else height = -1.1f;
                instance.transform.setToTranslation(position.x, position.y + height, position.z);
                break;
            }
            default: {
                // The plate shudders as it winds up, then snaps back.
                float shove = phase == Phase.TELEGRAPH ? -0.06f * t
                        : phase == Phase.ACTIVE ? 0.10f : 0f;
                instance.transform.setToTranslation(position.x, position.y, position.z);
                instance.transform.rotate(Vector3.Y, facing);
                instance.transform.translate(0f, 0f, shove);
                break;
            }
        }
    }

    /** 0..1 through the current phase. */
    private float progress() {
        float length = phase == Phase.TELEGRAPH ? telegraph
                : phase == Phase.ACTIVE ? active
                : phase == Phase.RECOVER ? recover : Math.max(period, 0.001f);
        return MathUtils.clamp(phaseTime / Math.max(length, 0.001f), 0f, 1f);
    }

    /** 0..1 through the whole cycle, for the blade's continuous swing. */
    private float clockPhase() {
        float total = Math.max(0.001f, period + telegraph + active + recover);
        float elapsed = phase == Phase.IDLE ? clock
                : period + (phase == Phase.TELEGRAPH ? phaseTime
                    : phase == Phase.ACTIVE ? telegraph + phaseTime
                    : telegraph + active + phaseTime);
        return (elapsed / total) % 1f;
    }

    public ModelInstance instance() {
        return instance;
    }

    @Override
    public void dispose() {
        if (model != null) {
            model.dispose();
            model = null;
            instance = null;
        }
    }
}
