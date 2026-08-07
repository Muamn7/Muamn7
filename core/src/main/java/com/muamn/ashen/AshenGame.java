package com.muamn.ashen;

import com.badlogic.gdx.Game;
import com.badlogic.gdx.Gdx;
import com.badlogic.gdx.graphics.glutils.ShaderProgram;

import com.muamn.ashen.combat.WeaponLibrary;
import com.muamn.ashen.entity.EnemyLibrary;
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
    /** The bestiary and the boss roster. */
    public EnemyLibrary bestiary;
    /** Consumables and reinforcement materials. */
    public com.muamn.ashen.item.ItemLibrary items;
    /** Synthesised sound effects and music beds. */
    public com.muamn.ashen.audio.Audio audio;
    /** The people still standing, and what they sell. */
    public com.muamn.ashen.npc.NpcLibrary npcs;
    /** The font and every string that reaches the screen. */
    public com.muamn.ashen.text.Text text;

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
    /** Overrides the player's start position as "x,z". Debug and screenshots. */
    public String spawnAt;
    /** Starts in a named area instead of the saved one. Debug and screenshots. */
    public String startArea;
    /** Holds imported rigs at their bind pose, to separate rig bugs from animation bugs. */
    public boolean freezeAnimations;
    /** Opens the bonfire menu immediately, for screenshots and UI work. */
    public boolean openMenuOnStart;
    /** Starts a conversation with this npc id on the first frame. Screenshots. */
    public String talkTo;
    /** Skips straight to that character's stock, if they have any. Screenshots. */
    public boolean openShopOnStart;
    /** Which page that menu opens on. */
    public com.muamn.ashen.ui.BonfireMenu.Page menuPage =
            com.muamn.ashen.ui.BonfireMenu.Page.ROOT;
    /**
     * Builds every area, reports anything broken and quits. Building an area needs
     * textures, and textures need a GL context, so this check cannot live in the
     * unit tests - it runs in CI as a separate launch instead.
     */
    public boolean validateWorld;
    /** Skips synthesising and loading the sound bank. CI and screenshots. */
    public boolean muteAudio;
    /** Forces a language code, overriding the save. Screenshots and testing. */
    public String forceLanguage;
    /** Draws the scene straight to the display, with no offscreen downscale. */
    public boolean noOffscreenBuffer;

    public AshenGame() {
        this(false, false);
    }

    public AshenGame(boolean forceTouchControls, boolean debugOverlay) {
        this.forceTouchControls = forceTouchControls;
        this.debugOverlay = debugOverlay;
    }

    /** Set when something threw; from then on the game only draws the report. */
    private com.muamn.ashen.screens.ErrorScreen failure;
    /** Frames drawn. Only the first few are logged, and only to prove they happen. */
    private int frames;
    /** Seconds left of the plain-clear probe. See {@link Config#GL_PROBE}. */
    private float probeRemaining = Config.GL_PROBE ? Config.GL_PROBE_SECONDS : 0f;
    /** The three squares, drawn after everything else so nothing can cover them. */
    private com.muamn.ashen.render.GlProbe probe;

    @Override
    public void create() {
        try {
            boot();
        } catch (Throwable t) {
            fail("create", t);
        }
    }

    /**
     * Draws a frame, or the failure report if there has been one.
     *
     * A phone has nowhere to print a stack trace, and an exception escaping here
     * takes the whole process down mid-frame with nothing on screen to say why.
     * Catching it costs a branch and turns every crash into something the player
     * can photograph.
     */
    @Override
    public void render() {
        if (failure != null) {
            failure.render(Gdx.graphics.getDeltaTime());
            return;
        }
        if (probeRemaining > 0f) {
            probeRemaining -= Gdx.graphics.getDeltaTime();
            // Clear and swap. There is no smaller GL program, and nothing in this
            // project is between it and the display.
            com.badlogic.gdx.utils.ScreenUtils.clear(0.85f, 0.10f, 0.65f, 1f);
            if (probeRemaining <= 0f) {
                Gdx.app.log("Ashen", "probe over: the screen was magenta for "
                        + Config.GL_PROBE_SECONDS + "s at "
                        + Gdx.graphics.getBackBufferWidth() + "x"
                        + Gdx.graphics.getBackBufferHeight() + " back buffer");
            }
            return;
        }
        try {
            super.render();
        } catch (Throwable t) {
            fail("render", t);
            return;
        }
        if (Config.GL_PROBE) {
            if (probe == null) probe = new com.muamn.ashen.render.GlProbe();
            probe.draw();
            // Last of all, and after the probe squares, so it covers the whole frame.
            com.muamn.ashen.render.GlProbe.sealAlpha();
        }

        // "The render loop is running" is not something a black screen can tell
        // you, and it is the first thing worth knowing about one.
        frames++;
        if (frames == 1 || frames == 60 || frames == 240) {
            // glGetError is the only thing that will say a driver rejected a draw
            // it had no intention of complaining about any other way.
            int error = Gdx.gl.glGetError();
            Gdx.app.log("Ashen", "frame " + frames + " drawn at "
                    + Gdx.graphics.getWidth() + "x" + Gdx.graphics.getHeight()
                    + ", " + Gdx.graphics.getFramesPerSecond() + "fps"
                    + (error == 0 ? "" : ", GL ERROR 0x" + Integer.toHexString(error)));
        }
    }

    private void fail(String where, Throwable t) {
        Gdx.app.error("Ashen", "fatal in " + where, new Exception(t));
        try {
            if (screen != null) screen.hide();
        } catch (Throwable ignored) {
            // The screen is already broken; that is why we are here.
        }
        screen = null;
        failure = new com.muamn.ashen.screens.ErrorScreen(where, t);
    }

    private void boot() {
        // A missing uniform is a normal outcome once a driver optimises one away,
        // so tolerate it rather than crashing on device-specific GLSL compilers.
        ShaderProgram.pedantic = false;

        com.badlogic.gdx.graphics.GL20 gl = Gdx.gl;
        Gdx.app.log("Ashen", "starting on " + Gdx.app.getType()
                + " gl=" + gl.glGetString(com.badlogic.gdx.graphics.GL20.GL_VERSION)
                + " renderer=" + gl.glGetString(com.badlogic.gdx.graphics.GL20.GL_RENDERER)
                + " vendor=" + gl.glGetString(com.badlogic.gdx.graphics.GL20.GL_VENDOR));

        textures = new TextureFactory();
        weapons = new WeaponLibrary();
        weapons.load();
        bestiary = new EnemyLibrary();
        bestiary.load();
        items = new com.muamn.ashen.item.ItemLibrary();
        items.load();
        npcs = new com.muamn.ashen.npc.NpcLibrary();
        npcs.load();
        text = new com.muamn.ashen.text.Text();
        text.load();
        audio = new com.muamn.ashen.audio.Audio();
        if (!muteAudio) audio.load();
        if (validateWorld) {
            runWorldValidation();
            return;
        }
        if (viewModel != null && !viewModel.isEmpty()) {
            setScreen(new com.muamn.ashen.screens.ModelViewerScreen(this, viewModel));
        } else {
            setScreen(new GameScreen(this));
        }
    }

    /** Prints the world's problems and exits non-zero if there are any. */
    private void runWorldValidation() {
        com.badlogic.gdx.utils.Array<String> problems =
                com.muamn.ashen.world.WorldValidator.validate(
                        textures, bestiary, weapons, npcs, items);
        if (problems.size == 0) {
            Gdx.app.log("Ashen", "world validation passed");
            Gdx.app.exit();
            return;
        }
        for (String problem : problems) Gdx.app.error("Ashen", "world: " + problem);
        Gdx.app.error("Ashen", problems.size + " world problem(s)");
        // Gdx.app.exit() would run the normal shutdown and return 0; this must fail
        // the build.
        dispose();
        System.exit(1);
    }

    @Override
    public void dispose() {
        if (probe != null) probe.dispose();
        if (failure != null) failure.dispose();
        if (screen != null) screen.dispose();
        if (textures != null) textures.dispose();
        if (audio != null) audio.dispose();
        if (text != null) text.dispose();
    }
}
