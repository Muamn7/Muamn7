package com.muamn.ashen.screens;

import com.badlogic.gdx.Application;
import com.badlogic.gdx.Gdx;
import com.badlogic.gdx.Input;
import com.badlogic.gdx.ScreenAdapter;
import com.badlogic.gdx.graphics.g3d.ModelInstance;
import com.badlogic.gdx.math.MathUtils;
import com.badlogic.gdx.math.Vector3;
import com.badlogic.gdx.utils.Array;

import com.muamn.ashen.AshenGame;
import com.muamn.ashen.Config;
import com.muamn.ashen.camera.OrbitCamera;
import com.muamn.ashen.entity.CharacterRig;
import com.muamn.ashen.entity.HumanoidFactory;
import com.muamn.ashen.entity.HumanoidSpec;
import com.muamn.ashen.entity.Player;
import com.muamn.ashen.input.ControlState;
import com.muamn.ashen.input.DesktopControls;
import com.muamn.ashen.input.TouchControls;
import com.muamn.ashen.render.RetroRenderer;
import com.muamn.ashen.render.RetroShader;
import com.muamn.ashen.ui.Hud;
import com.muamn.ashen.world.Level;
import com.muamn.ashen.world.Levels;

/**
 * The playable screen: level, player, camera, HUD.
 *
 * Simulation runs on a fixed 60Hz step regardless of display refresh rate. A
 * game built on i-frames and attack windows cannot have its timing shift when
 * the frame rate does - a roll has to clear the same attack on a 120Hz tablet
 * as it does on a phone struggling at 40.
 */
public class GameScreen extends ScreenAdapter {

    private final AshenGame game;

    private RetroRenderer renderer;
    private OrbitCamera camera;
    private Level level;
    private Player player;
    private Hud hud;

    private final ControlState controls = new ControlState();
    private DesktopControls desktopControls;
    private TouchControls touchControls;

    private final Array<ModelInstance> renderList = new Array<>();

    private float accumulator;
    private float elapsed;

    public GameScreen(AshenGame game) {
        this.game = game;
    }

    @Override
    public void show() {
        renderer = new RetroRenderer();
        renderer.onDisplayResize(Gdx.graphics.getWidth(), Gdx.graphics.getHeight());

        level = Levels.asylumCourtyard(game.textures);
        applyLevelMood();

        HumanoidSpec spec = HumanoidSpec.knight();
        CharacterRig rig = new CharacterRig(
                HumanoidFactory.build(spec, game.textures, "player"), spec);
        player = new Player(rig);
        player.spawn(level.spawn.x, level.spawn.y, level.spawn.z, level.spawnFacing);

        camera = new OrbitCamera(renderer.aspectRatio());
        camera.distance = game.cameraDistance;
        camera.yaw = level.spawnFacing + 180f + game.cameraYawOffset;
        camera.snapTo(player.body.position);

        hud = new Hud();
        hud.resize(Gdx.graphics.getWidth(), Gdx.graphics.getHeight());
        hud.showDebug = game.debugOverlay;

        if (isTouchPlatform()) {
            touchControls = new TouchControls();
            touchControls.updateProjection(Gdx.graphics.getWidth(), Gdx.graphics.getHeight());
        } else {
            desktopControls = new DesktopControls();
            Gdx.input.setCursorCatched(true);
        }
    }

    private boolean isTouchPlatform() {
        if (game.forceTouchControls) return true;
        Application.ApplicationType type = Gdx.app.getType();
        return type == Application.ApplicationType.Android || type == Application.ApplicationType.iOS;
    }

    private void applyLevelMood() {
        RetroShader.Environment env = renderer.env();
        env.fogColor.set(level.fogColor);
        env.ambient.set(level.ambient);
        env.lightColor.set(level.lightColor);
        env.lightDir.set(level.lightDir).nor();
        env.fogNear = level.fogNear;
        env.fogFar = level.fogFar;
    }

    @Override
    public void render(float delta) {
        float dt = Math.min(delta, Config.MAX_FRAME_TIME);
        elapsed += dt;

        gatherInput(dt);

        // Fixed-step simulation with a frame-time cap, so a stall cannot make the
        // player tunnel through a wall by simulating a huge step.
        accumulator += dt;
        int steps = 0;
        while (accumulator >= Config.FIXED_STEP && steps < 8) {
            simulate(Config.FIXED_STEP);
            accumulator -= Config.FIXED_STEP;
            steps++;
        }
        if (steps == 8) accumulator = 0f;

        camera.update(player.body.position, level.collision, dt);
        hud.update(player.stats, dt);

        renderer.beginScene(level.fogColor.r, level.fogColor.g, level.fogColor.b);
        level.renderables(renderList);
        renderList.add(player.rig.instance);
        renderer.renderScene(camera.camera, renderList);
        renderer.endScene();
        renderer.present();

        if (hud.showDebug) {
            hud.setDebugLine(String.format(
                    "fps %d | %s | spd %.1f | pos %.1f,%.1f,%.1f | cam %.1f,%.1f,%.1f | tris %d | %dx%d",
                    Gdx.graphics.getFramesPerSecond(), player.getState(), player.groundSpeed(),
                    player.body.position.x, player.body.position.y, player.body.position.z,
                    camera.camera.position.x, camera.camera.position.y, camera.camera.position.z,
                    level.collision.triangleCount(),
                    renderer.getTargetWidth(), renderer.getTargetHeight()));
        }
        hud.render(player.stats);
        if (touchControls != null) touchControls.render();

        controls.clearEdges();
    }

    private void gatherInput(float dt) {
        if (game.autopilot) {
            driveAutopilot();
            return;
        }
        if (desktopControls != null) {
            desktopControls.update(controls);
            // Escape releases the mouse rather than quitting, so the window stays usable.
            if (controls.pausePressed) {
                Gdx.input.setCursorCatched(!Gdx.input.isCursorCatched());
            }
            if (Gdx.input.isKeyJustPressed(Input.Keys.F3)) {
                hud.showDebug = !hud.showDebug;
            }
        }
        if (touchControls != null) touchControls.update(controls, dt);
    }

    /**
     * A fixed input script: sprint forward, sweep the camera, and roll every few
     * seconds. Enough to exercise locomotion, stamina, the ramp, the steps and
     * the collision resolver without a human at the controls.
     */
    private void driveAutopilot() {
        float t = elapsed;
        controls.move.set(MathUtils.sinDeg(t * 47f) * 0.55f, 1f);
        controls.sprintHeld = (t % 6f) < 3.5f;
        controls.look.add(MathUtils.sin(t * 0.7f) * 0.9f, 0f);

        float phase = t % 4f;
        boolean rollNow = phase >= 3.9f;
        controls.rollPressed |= rollNow && !autopilotRolled;
        autopilotRolled = rollNow;
    }

    private boolean autopilotRolled;

    private void simulate(float dt) {
        camera.applyLook(controls.look.x, controls.look.y);
        // Look deltas are consumed by the first substep; later substeps get zero.
        controls.look.setZero();

        if (controls.lockOnPressed) {
            // No enemies until Part 2, so lock-on toggles onto the bonfire for now.
            camera.setLockTarget(camera.isLocked() ? null : bonfireTarget());
        }

        player.update(controls, level.collision, camera.yaw,
                camera.isLocked() ? bonfireTarget() : null, dt);

        // Falling out of the world should never be unrecoverable.
        if (player.body.position.y < -25f) {
            player.spawn(level.spawn.x, level.spawn.y, level.spawn.z, level.spawnFacing);
            camera.snapTo(player.body.position);
        }
    }

    private final Vector3 lockPoint = new Vector3(0f, 1.1f, -6f);

    private Vector3 bonfireTarget() {
        return lockPoint;
    }

    @Override
    public void resize(int width, int height) {
        if (width == 0 || height == 0) return;
        renderer.onDisplayResize(width, height);
        camera.setAspect(renderer.aspectRatio());
        hud.resize(width, height);
        if (touchControls != null) touchControls.updateProjection(width, height);
    }

    @Override
    public void hide() {
        if (desktopControls != null) Gdx.input.setCursorCatched(false);
    }

    @Override
    public void dispose() {
        if (renderer != null) renderer.dispose();
        if (level != null) level.dispose();
        if (hud != null) hud.dispose();
        if (touchControls != null) touchControls.dispose();
        if (player != null) player.rig.model.dispose();
    }

    /** Exposed for the smoke test so it can assert the world actually loaded. */
    public int collisionTriangleCount() {
        return level != null ? level.collision.triangleCount() : 0;
    }

    public float elapsedTime() {
        return elapsed;
    }

    public RetroRenderer getRenderer() {
        return renderer;
    }
}
