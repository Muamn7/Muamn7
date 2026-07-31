package com.muamn.ashen.screens;

import com.badlogic.gdx.Gdx;
import com.badlogic.gdx.ScreenAdapter;
import com.badlogic.gdx.graphics.PerspectiveCamera;
import com.badlogic.gdx.graphics.g3d.Model;
import com.badlogic.gdx.graphics.g3d.ModelInstance;
import com.badlogic.gdx.graphics.g3d.model.Animation;
import com.badlogic.gdx.graphics.g3d.model.Node;
import com.badlogic.gdx.graphics.g3d.utils.AnimationController;
import com.badlogic.gdx.math.MathUtils;
import com.badlogic.gdx.math.Vector3;
import com.badlogic.gdx.math.collision.BoundingBox;

import com.muamn.ashen.AshenGame;
import com.muamn.ashen.Config;
import com.muamn.ashen.render.RetroRenderer;
import com.muamn.ashen.ui.Hud;
import com.muamn.ashen.world.AssetOverrides;

/**
 * A turntable for one imported model.
 *
 * Debugging a bad import inside the running game is miserable - you cannot tell
 * a broken bind pose from a bad spawn point. This shows the model alone, frames
 * it automatically from its bounding box, cycles its animations, and prints what
 * actually loaded. Run it with {@code -Dashen.viewModel=hollow_reaper}.
 */
public class ModelViewerScreen extends ScreenAdapter {

    private final AshenGame game;
    private final String modelName;

    private RetroRenderer renderer;
    private PerspectiveCamera camera;
    private Model model;
    private ModelInstance instance;
    private AnimationController animator;
    private Hud hud;

    private final BoundingBox bounds = new BoundingBox();
    private final Vector3 center = new Vector3();
    private final Vector3 size = new Vector3();

    private float angle;
    private float distance;
    private int animationIndex = -1;
    private float animationTimer;
    private String info = "";

    public ModelViewerScreen(AshenGame game, String modelName) {
        this.game = game;
        this.modelName = modelName;
    }

    @Override
    public void show() {
        renderer = new RetroRenderer();
        renderer.onDisplayResize(Gdx.graphics.getWidth(), Gdx.graphics.getHeight());
        // A neutral studio light, not the level's mood, so problems are visible.
        renderer.env().ambient.set(0.45f, 0.45f, 0.48f, 1f);
        renderer.env().lightColor.set(0.9f, 0.87f, 0.8f, 1f);
        renderer.env().fogNear = 40f;
        renderer.env().fogFar = 120f;

        model = AssetOverrides.loadModel(modelName);
        if (model == null) {
            info = "model not found: " + modelName;
            Gdx.app.error("ModelViewer", info);
        } else {
            instance = new ModelInstance(model);
            instance.calculateBoundingBox(bounds);
            bounds.getCenter(center);
            bounds.getDimensions(size);
            // A skinned mesh's vertices are in bind space, so the bounding box
            // ignores the rig node that scales and places the model. Fold it in
            // by hand or the camera frames a model several times its real size.
            Node rig = instance.getNode(modelName + "_rig", true);
            if (rig != null) {
                size.scl(rig.scale);
                center.scl(rig.scale).add(rig.translation);
            }
            distance = Math.max(size.len() * 1.15f, 1.5f);

            StringBuilder sb = new StringBuilder();
            sb.append(modelName)
              .append(" | size ").append(fmt(size.x)).append('x').append(fmt(size.y))
              .append('x').append(fmt(size.z))
              .append(" | meshes ").append(model.meshes.size)
              .append(" | parts ").append(model.meshParts.size)
              .append(" | anims ").append(model.animations.size);
            info = sb.toString();
            Gdx.app.log("ModelViewer", info);
            for (Animation a : model.animations) {
                Gdx.app.log("ModelViewer", "  animation '" + a.id + "' "
                        + fmt(a.duration) + "s");
            }
            if (model.animations.size > 0 && !game.freezeAnimations) {
                animator = new AnimationController(instance);
                playNext();
            }
        }

        camera = new PerspectiveCamera(Config.CAMERA_FOV, renderer.aspectRatio(), 1f);
        camera.near = 0.05f;
        camera.far = 400f;

        hud = new Hud();
        hud.showDebug = true;
        hud.resize(Gdx.graphics.getWidth(), Gdx.graphics.getHeight());
    }

    private void playNext() {
        if (animator == null || model.animations.size == 0) return;
        animationIndex = (animationIndex + 1) % model.animations.size;
        Animation a = model.animations.get(animationIndex);
        animator.setAnimation(a.id, -1);      // loop
        animationTimer = Math.max(a.duration, 0.4f) * 2f;
    }

    @Override
    public void render(float delta) {
        float dt = Math.min(delta, Config.MAX_FRAME_TIME);
        angle += dt * 38f;

        if (animator != null) {
            animator.update(dt);
            animationTimer -= dt;
            if (animationTimer <= 0f) playNext();
        }

        camera.position.set(
                center.x + MathUtils.cosDeg(angle) * distance,
                center.y + size.y * 0.35f + distance * 0.22f,
                center.z + MathUtils.sinDeg(angle) * distance);
        camera.up.set(Vector3.Y);
        camera.lookAt(center);
        camera.update();

        renderer.beginScene(0.20f, 0.21f, 0.23f);
        if (instance != null) renderer.renderScene(camera, instance);
        renderer.endScene();
        renderer.present();

        String anim = animator != null && animationIndex >= 0
                ? model.animations.get(animationIndex).id : "-";
        hud.setDebugLine(info + " | playing " + anim
                + " | fps " + Gdx.graphics.getFramesPerSecond());
        hud.renderDebugOnly();
    }

    private static String fmt(float v) {
        return String.format("%.2f", v);
    }

    @Override
    public void resize(int width, int height) {
        if (width == 0 || height == 0) return;
        renderer.onDisplayResize(width, height);
        camera.viewportWidth = renderer.aspectRatio();
        camera.viewportHeight = 1f;
        camera.update();
        hud.resize(width, height);
    }

    @Override
    public void dispose() {
        if (renderer != null) renderer.dispose();
        if (model != null) model.dispose();
        if (hud != null) hud.dispose();
    }
}
