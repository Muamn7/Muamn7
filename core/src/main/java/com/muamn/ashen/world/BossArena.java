package com.muamn.ashen.world;

import com.badlogic.gdx.graphics.Color;
import com.badlogic.gdx.graphics.GL20;
import com.badlogic.gdx.graphics.VertexAttributes.Usage;
import com.badlogic.gdx.graphics.g3d.Material;
import com.badlogic.gdx.graphics.g3d.Model;
import com.badlogic.gdx.graphics.g3d.ModelInstance;
import com.badlogic.gdx.graphics.g3d.attributes.BlendingAttribute;
import com.badlogic.gdx.graphics.g3d.attributes.ColorAttribute;
import com.badlogic.gdx.graphics.g3d.attributes.IntAttribute;
import com.badlogic.gdx.graphics.g3d.attributes.TextureAttribute;
import com.badlogic.gdx.graphics.g3d.utils.MeshPartBuilder;
import com.badlogic.gdx.graphics.g3d.utils.ModelBuilder;
import com.badlogic.gdx.math.MathUtils;
import com.badlogic.gdx.math.Vector3;

/**
 * A boss encounter: a fog gate, an arena, and the fight behind it.
 *
 * The fog gate is not decoration. It is the game asking "are you ready", and it
 * has to be a deliberate step through, not a line you cross by accident while
 * running away - so the trigger is a small volume at the gate itself rather than
 * the arena boundary.
 *
 * Once entered, the gate becomes solid from the inside. Nothing about the fight
 * is fair if you can walk out of it, and nothing about it is tense if you can.
 */
public class BossArena {

    public enum Phase { DORMANT, ACTIVE, CLEARED }

    public final String id;
    public final String bossId;

    /** Centre of the arena, on the ground. */
    public final Vector3 center = new Vector3();
    public final float radius;

    /** Where the fog gate stands, and which way it faces (degrees). */
    public final Vector3 gate = new Vector3();
    public final float gateFacing;
    public final float gateWidth;

    /** Where the boss waits. */
    public final Vector3 bossSpawn = new Vector3();

    private Phase phase = Phase.DORMANT;
    private ModelInstance fogInstance;
    private Model fogModel;
    /** Collision added when the fight starts, removed when it ends. */
    private CollisionMesh barrier;

    private float fogScroll;

    public BossArena(String id, String bossId, float cx, float cz, float radius,
                     float gateX, float gateZ, float gateFacing, float gateWidth,
                     float bossX, float bossZ) {
        this.id = id;
        this.bossId = bossId;
        this.center.set(cx, 0f, cz);
        this.radius = radius;
        this.gate.set(gateX, 0f, gateZ);
        this.gateFacing = gateFacing;
        this.gateWidth = gateWidth;
        this.bossSpawn.set(bossX, 0.2f, bossZ);
    }

    public Phase getPhase() {
        return phase;
    }

    public boolean isActive() {
        return phase == Phase.ACTIVE;
    }

    public boolean isCleared() {
        return phase == Phase.CLEARED;
    }

    /** Marks the arena as already beaten, e.g. when loading a save. */
    public void markCleared() {
        phase = Phase.CLEARED;
        if (fogInstance != null) fogInstance = null;
    }

    /**
     * @return true if the player just stepped through the gate
     */
    public boolean checkEntry(Vector3 playerPosition) {
        if (phase != Phase.DORMANT) return false;
        // A small box at the gate, not the whole arena: you enter on purpose.
        float dx = playerPosition.x - gate.x;
        float dz = playerPosition.z - gate.z;
        if (dx * dx + dz * dz > (gateWidth * 0.6f) * (gateWidth * 0.6f)) return false;
        phase = Phase.ACTIVE;
        return true;
    }

    /** Resets the encounter after the player dies to it. */
    public void markDormant() {
        if (phase == Phase.ACTIVE) phase = Phase.DORMANT;
    }

    /** Called when the boss dies. */
    public void clear() {
        phase = Phase.CLEARED;
        barrier = null;
    }

    /**
     * Collision that seals the arena while the fight is on.
     *
     * Built as a ring of wall segments around the arena edge, tall enough that
     * nothing can be climbed out over.
     */
    public CollisionMesh barrier() {
        if (barrier != null) return barrier;
        barrier = new CollisionMesh();
        int segments = 24;
        float height = 6f;
        for (int i = 0; i < segments; i++) {
            float a0 = i * 360f / segments;
            float a1 = (i + 1) * 360f / segments;
            float x0 = center.x + MathUtils.cosDeg(a0) * radius;
            float z0 = center.z + MathUtils.sinDeg(a0) * radius;
            float x1 = center.x + MathUtils.cosDeg(a1) * radius;
            float z1 = center.z + MathUtils.sinDeg(a1) * radius;
            // Two triangles per segment, facing inward.
            barrier.addTriangle(x0, 0f, z0, x0, height, z0, x1, height, z1);
            barrier.addTriangle(x0, 0f, z0, x1, height, z1, x1, 0f, z1);
        }
        return barrier;
    }

    /** True while the player is inside the arena bounds. */
    public boolean contains(Vector3 position) {
        float dx = position.x - center.x;
        float dz = position.z - center.z;
        return dx * dx + dz * dz <= radius * radius;
    }

    // ---- fog gate visual --------------------------------------------------

    /** Builds the fog wall. Call once, after the textures exist. */
    public void buildVisual(TextureFactory textures) {
        long attrs = Usage.Position | Usage.Normal | Usage.TextureCoordinates;
        Material fog = new Material(
                TextureAttribute.createDiffuse(textures.get("fog_gate")),
                ColorAttribute.createDiffuse(new Color(0.72f, 0.76f, 0.82f, 1f)),
                ColorAttribute.createEmissive(0.55f, 0.55f, 0.55f, 1f),
                new BlendingAttribute(GL20.GL_SRC_ALPHA, GL20.GL_ONE_MINUS_SRC_ALPHA, 0.72f),
                IntAttribute.createCullFace(GL20.GL_NONE));

        ModelBuilder mb = new ModelBuilder();
        mb.begin();
        MeshPartBuilder p = mb.part("fog", GL20.GL_TRIANGLES, attrs, fog);
        float hw = gateWidth * 0.5f, h = 3.6f;
        MeshUtil.quad(p, -hw, 0f, 0f, hw, 0f, 0f, hw, h, 0f, -hw, h, 0f,
                0f, 0f, 1f, 2f, 2f);
        fogModel = mb.end();

        fogInstance = new ModelInstance(fogModel);
        fogInstance.transform.setToTranslation(gate.x, gate.y, gate.z);
        fogInstance.transform.rotate(Vector3.Y, gateFacing);
    }

    /** Drifts the fog so it reads as alive rather than as a flat decal. */
    public void update(float dt) {
        if (fogInstance == null) return;
        fogScroll += dt * 0.35f;
        float sway = MathUtils.sin(fogScroll) * 0.06f;
        fogInstance.transform.setToTranslation(gate.x + sway, gate.y, gate.z);
        fogInstance.transform.rotate(Vector3.Y, gateFacing);
    }

    /** The fog instance to draw, or null once the arena is cleared. */
    public ModelInstance fogInstance() {
        return phase == Phase.CLEARED ? null : fogInstance;
    }

    public void dispose() {
        if (fogModel != null) {
            fogModel.dispose();
            fogModel = null;
            fogInstance = null;
        }
    }
}
