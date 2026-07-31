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

/**
 * An item lying on the ground where something died.
 *
 * Drawn as a small emissive shard rather than as a model of the item itself. At
 * this polygon budget a bottle and a stone read as the same grey lump, and the
 * thing that actually has to work is being visible on a dark floor from across a
 * room - so the item's colour does the identifying, and picking it up names it.
 */
public class Pickup {

    public final String itemId;
    public final int count;
    public final Vector3 position = new Vector3();
    public final ModelInstance instance;

    /**
     * Set for loot placed by hand rather than dropped by something, so taking it
     * can be remembered. Null for an ordinary drop, which is gone when you leave
     * the area anyway.
     */
    public String treasureId;

    private float bob;
    private float settle;

    /** How close the player has to be. Generous: hunting for a shard is not play. */
    public static final float REACH = 1.5f;
    /**
     * A drop cannot be collected for this long.
     *
     * Without it, a melee kill drops the item under the player's own feet and it
     * vanishes into the pack in the same frame it appeared - the player is told
     * what they got but never sees where it came from. Half a second is enough to
     * read the shard as an object on the floor, and short enough that stepping
     * forward after the kill still collects it.
     */
    private static final float SETTLE = 0.55f;

    public Pickup(String itemId, int count, float x, float y, float z, Model shared) {
        this.itemId = itemId;
        this.count = count;
        this.position.set(x, y, z);
        this.instance = new ModelInstance(shared);
        // Start at a random point in the bob so a pile does not pulse in unison.
        this.bob = (Math.abs(itemId.hashCode()) % 628) / 100f;
        updateTransform();
    }

    public void update(float dt) {
        bob += dt * 2.4f;
        settle += dt;
        updateTransform();
    }

    private void updateTransform() {
        instance.transform.setToTranslation(
                position.x, position.y + 0.45f + MathUtils.sin(bob) * 0.09f, position.z);
        instance.transform.rotate(Vector3.Y, bob * 46f);
    }

    /** Tints the shared model for this instance only. */
    public void tint(Color color) {
        instance.materials.get(0).set(ColorAttribute.createDiffuse(color));
        instance.materials.get(0).set(ColorAttribute.createEmissive(
                color.r * 0.9f, color.g * 0.9f, color.b * 0.9f, 1f));
    }

    public boolean inReach(Vector3 player) {
        if (settle < SETTLE) return false;
        float dx = player.x - position.x;
        float dy = player.y - position.y;
        float dz = player.z - position.z;
        return dx * dx + dz * dz <= REACH * REACH && Math.abs(dy) < 2.2f;
    }

    /**
     * The shard every pickup shares. One model, many instances, each tinted -
     * a model per drop would be a model allocation per kill.
     */
    public static Model buildModel(TextureFactory textures) {
        long attrs = Usage.Position | Usage.Normal | Usage.TextureCoordinates;
        Material material = new Material(
                TextureAttribute.createDiffuse(textures.get("ember")),
                ColorAttribute.createDiffuse(Color.WHITE),
                ColorAttribute.createEmissive(1f, 1f, 1f, 1f));

        ModelBuilder mb = new ModelBuilder();
        mb.begin();
        MeshPartBuilder p = mb.part("shard", GL20.GL_TRIANGLES, attrs, material);
        // Two tapers meeting at the waist make a rough octahedron: a crystal,
        // not a cube. taper is (x, z, yBottom, yTop, wBottom, dBottom, wTop, dTop).
        MeshUtil.taper(p, 0f, 0f, 0f, 0.20f, 0.14f, 0.14f, 0.02f, 0.02f, 4f);
        MeshUtil.taper(p, 0f, 0f, -0.18f, 0f, 0.02f, 0.02f, 0.14f, 0.14f, 4f);
        return mb.end();
    }
}
