package com.muamn.ashen;

import com.badlogic.gdx.Game;
import com.badlogic.gdx.Gdx;
import com.badlogic.gdx.graphics.glutils.ShaderProgram;

import com.muamn.ashen.combat.WeaponLibrary;
import com.muamn.ashen.screens.GameScreen;
import com.muamn.ashen.world.TextureFactory;

/**
 * Application entry point, shared by the desktop and Android launchers.
 *
 * <h3>ASHEN</h3>
 * A PS2-era Souls-like. See {@code PLAN.md} for the four-part build plan; this
 * is Part 1 - engine, movement, camera, controls and the retro render pipeline.
 */
public class AshenGame extends Game {

    /** Procedural texture cache, shared by every level and character. */
    public TextureFactory textures;
    /** Weapons and their frame data, loaded from JSON. */
    public WeaponLibrary weapons;

    /** Draws the on-screen stick and buttons even on desktop. */
    public boolean forceTouchControls;
    /** Shows the frame timing / state readout. */
    public boolean debugOverlay;
    /** Camera boom length. Overridable so screenshots can frame the character. */
    public float cameraDistance = Config.CAM_DISTANCE;
    /** Extra yaw applied to the starting camera, for framing screenshots. */
    public float cameraYawOffset;
    /**
     * Drives the player with a scripted input loop instead of the controls.
     * CI uses it to prove that movement, collision and the roll all still run.
     */
    public boolean autopilot;
    /** When set, opens the turntable model viewer for this imported model. */
    public String viewModel;
    /** Holds imported rigs at their bind pose, to separate rig bugs from animation bugs. */
    public boolean freezeAnimations;
    /** Opens the bonfire menu immediately, for screenshots and UI work. */
    public boolean openMenuOnStart;
    /** Which page that menu opens on. */
    public com.muamn.ashen.ui.BonfireMenu.Page menuPage =
            com.muamn.ashen.ui.BonfireMenu.Page.ROOT;

    public AshenGame() {
        this(false, false);
    }

    public AshenGame(boolean forceTouchControls, boolean debugOverlay) {
        this.forceTouchControls = forceTouchControls;
        this.debugOverlay = debugOverlay;
    }

    @Override
    public void create() {
        // A missing uniform is a normal outcome once a driver optimises one away,
        // so tolerate it rather than crashing on device-specific GLSL compilers.
        ShaderProgram.pedantic = false;

        Gdx.app.log("Ashen", "starting on " + Gdx.app.getType()
                + " gl=" + Gdx.gl.glGetString(com.badlogic.gdx.graphics.GL20.GL_VERSION));

        textures = new TextureFactory();
        weapons = new WeaponLibrary();
        weapons.load();
        if (viewModel != null && !viewModel.isEmpty()) {
            setScreen(new com.muamn.ashen.screens.ModelViewerScreen(this, viewModel));
        } else {
            setScreen(new GameScreen(this));
        }
    }

    @Override
    public void dispose() {
        if (screen != null) screen.dispose();
        if (textures != null) textures.dispose();
    }
}
