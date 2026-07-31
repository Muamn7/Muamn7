package com.muamn.ashen.world;

import com.badlogic.gdx.graphics.Color;
import com.badlogic.gdx.graphics.GL20;
import com.badlogic.gdx.graphics.VertexAttributes.Usage;
import com.badlogic.gdx.graphics.g3d.Material;
import com.badlogic.gdx.graphics.g3d.Model;
import com.badlogic.gdx.graphics.g3d.ModelInstance;
import com.badlogic.gdx.graphics.g3d.attributes.BlendingAttribute;
import com.badlogic.gdx.graphics.g3d.attributes.ColorAttribute;
import com.badlogic.gdx.graphics.g3d.attributes.TextureAttribute;
import com.badlogic.gdx.graphics.g3d.utils.MeshPartBuilder;
import com.badlogic.gdx.graphics.g3d.utils.ModelBuilder;
import com.badlogic.gdx.math.MathUtils;
import com.badlogic.gdx.math.Vector3;
import com.badlogic.gdx.utils.Disposable;

/**
 * A wall that is not there.
 *
 * It looks and collides exactly like the masonry around it until it is struck,
 * then fades out and stops being solid. The whole point is that nothing marks
 * it, so it is built from the same material as the wall it sits in and its
 * collision is indistinguishable from the level's own.
 *
 * The one concession to fairness is that these are always placed at the end of
 * something - a dead-end corridor, a blank alcove - because a secret nobody can
 * reason their way to is not a secret, it is a lottery.
 */
public class IllusoryWall implements Disposable {

    /** Stable identity, so a wall opened once stays open across a save. */
    public final String id;

    public final Vector3 position = new Vector3();
    public final float facing;
    public final float width;
    public final float height;
    public final float thickness;
    /** Material of the surrounding wall, so it cannot be spotted by its texture. */
    public final String material;

    private boolean open;
    /** Counts down while it fades away, then the visual is dropped. */
    private float fade;

    private Model model;
    private ModelInstance instance;

    private static final float FADE_TIME = 0.9f;

    public IllusoryWall(String id, float x, float y, float z, float facing,
                        float width, float height, float thickness, String material) {
        this.id = id;
        this.position.set(x, y, z);
        this.facing = facing;
        this.width = width;
        this.height = height;
        this.thickness = thickness;
        this.material = material;
    }

    public boolean isOpen() {
        return open;
    }

    /** Marks it already found, e.g. when loading a save. */
    public void openSilently() {
        open = true;
        fade = 0f;
        instance = null;
    }

    /**
     * Strikes the wall.
     *
     * @return true if this blow is what revealed it
     */
    public boolean strike() {
        if (open) return false;
        open = true;
        fade = FADE_TIME;
        return true;
    }

    /** True if a blow landing at this point, from a swing this long, would hit. */
    public boolean struckBy(Vector3 attackerPosition, float attackerFacing, float reach) {
        if (open) return false;
        float dx = position.x - attackerPosition.x;
        float dz = position.z - attackerPosition.z;
        if (dx * dx + dz * dz > (reach + width * 0.5f) * (reach + width * 0.5f)) return false;
        // The swing has to be aimed at it, not merely near it.
        float toWall = MathUtils.atan2(dx, dz) * MathUtils.radiansToDegrees;
        float delta = ((toWall - attackerFacing) % 360f + 540f) % 360f - 180f;
        return Math.abs(delta) <= 55f;
    }

    public void update(float dt) {
        if (fade <= 0f) return;
        fade -= dt;
        if (fade <= 0f) {
            instance = null;
            return;
        }
        if (instance == null) return;
        // Sinking as it fades reads as the wall dissolving rather than blinking out.
        float t = 1f - fade / FADE_TIME;
        instance.transform.setToTranslation(position.x, position.y - t * 0.6f, position.z);
        instance.transform.rotate(Vector3.Y, facing);
        BlendingAttribute blend = (BlendingAttribute)
                instance.materials.get(0).get(BlendingAttribute.Type);
        if (blend != null) blend.opacity = 1f - t;
    }

    /** Adds this wall's collision to a mesh. Only while it is still solid. */
    public void addCollision(CollisionMesh mesh) {
        if (open) return;
        float cos = MathUtils.cosDeg(facing), sin = MathUtils.sinDeg(facing);
        float hw = width * 0.5f, ht = thickness * 0.5f;
        float y0 = position.y, y1 = position.y + height;

        // Four corners in plan, rotated about the wall's own centre.
        float[][] plan = {{-hw, -ht}, {hw, -ht}, {hw, ht}, {-hw, ht}};
        float[][] world = new float[4][2];
        for (int i = 0; i < 4; i++) {
            world[i][0] = position.x + plan[i][0] * cos + plan[i][1] * sin;
            world[i][1] = position.z - plan[i][0] * sin + plan[i][1] * cos;
        }

        for (int i = 0; i < 4; i++) {
            int j = (i + 1) % 4;
            mesh.addTriangle(world[i][0], y0, world[i][1],
                    world[j][0], y0, world[j][1], world[j][0], y1, world[j][1]);
            mesh.addTriangle(world[i][0], y0, world[i][1],
                    world[j][0], y1, world[j][1], world[i][0], y1, world[i][1]);
        }
        // A lid, so nothing can be walked over the top of a short one.
        mesh.addTriangle(world[0][0], y1, world[0][1],
                world[1][0], y1, world[1][1], world[2][0], y1, world[2][1]);
        mesh.addTriangle(world[0][0], y1, world[0][1],
                world[2][0], y1, world[2][1], world[3][0], y1, world[3][1]);
    }

    /** Builds the panel. It has to match the wall it hides in exactly. */
    public void buildVisual(TextureFactory textures) {
        if (open) return;
        long attrs = Usage.Position | Usage.Normal | Usage.TextureCoordinates;
        Material stone = new Material(
                TextureAttribute.createDiffuse(textures.get(material)),
                ColorAttribute.createDiffuse(Color.WHITE),
                new BlendingAttribute(GL20.GL_SRC_ALPHA, GL20.GL_ONE_MINUS_SRC_ALPHA, 1f));

        ModelBuilder mb = new ModelBuilder();
        mb.begin();
        MeshPartBuilder p = mb.part("wall", GL20.GL_TRIANGLES, attrs, stone);
        MeshUtil.box(p, 0f, height * 0.5f, 0f, width, height, thickness, 0.5f);
        model = mb.end();

        instance = new ModelInstance(model);
        instance.transform.setToTranslation(position.x, position.y, position.z);
        instance.transform.rotate(Vector3.Y, facing);
    }

    /** The panel to draw, or null once it has finished fading. */
    public ModelInstance instance() {
        return open && fade <= 0f ? null : instance;
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
