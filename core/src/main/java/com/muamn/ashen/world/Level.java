package com.muamn.ashen.world;

import com.badlogic.gdx.graphics.Color;
import com.badlogic.gdx.graphics.g3d.Model;
import com.badlogic.gdx.graphics.g3d.ModelInstance;
import com.badlogic.gdx.math.Vector3;
import com.badlogic.gdx.utils.Array;
import com.badlogic.gdx.utils.Disposable;

/** One playable area: its geometry, its collision and its lighting mood. */
public class Level implements Disposable {

    public final String id;
    public final Model model;
    public final ModelInstance instance;
    public final CollisionMesh collision;

    public final Vector3 spawn = new Vector3();
    public float spawnFacing;

    public final Color fogColor = new Color(0.42f, 0.44f, 0.46f, 1f);
    public final Color ambient = new Color(0.30f, 0.31f, 0.38f, 1f);
    public final Color lightColor = new Color(0.85f, 0.80f, 0.70f, 1f);
    public final Vector3 lightDir = new Vector3(-0.45f, -0.82f, -0.35f).nor();
    public float fogNear = 14f;
    public float fogFar = 62f;

    /** Extra instances drawn with the level, e.g. props with their own transform. */
    public final Array<ModelInstance> props = new Array<>();
    /** Models this level owns and must dispose. */
    private final Array<Model> ownedModels = new Array<>();

    public Level(String id, Model model, CollisionMesh collision) {
        this.id = id;
        this.model = model;
        this.instance = new ModelInstance(model);
        this.collision = collision;
        ownedModels.add(model);
    }

    /** Registers a model whose lifetime is tied to this level. */
    public void own(Model m) {
        ownedModels.add(m);
    }

    /** Everything to draw for this level, level geometry first. */
    public Array<ModelInstance> renderables(Array<ModelInstance> out) {
        out.clear();
        out.add(instance);
        out.addAll(props);
        return out;
    }

    @Override
    public void dispose() {
        for (Model m : ownedModels) m.dispose();
        ownedModels.clear();
        props.clear();
    }
}
