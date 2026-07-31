package com.muamn.ashen;

/**
 * Tuning values shared across the game. Anything a designer might want to feel
 * out lives here rather than being buried in a system.
 */
public final class Config {

    private Config() {}

    // ---- Presentation -------------------------------------------------

    /** Internal render width. Everything is drawn here, then point-upscaled. */
    public static final int RENDER_WIDTH = 480;
    /** Internal render height (16:9). */
    public static final int RENDER_HEIGHT = 270;

    /** Vertex snap grid, in "virtual pixels". Lower = more PS1-style wobble. */
    public static final float VERTEX_SNAP = 160f;
    /** 0 = perspective correct, 1 = fully affine (PS1 texture warping). */
    public static final float AFFINE_AMOUNT = 0.85f;
    /** Colour levels per channel before dithering. 31 == 5 bits, like a PS1 framebuffer. */
    public static final float COLOR_LEVELS = 31f;

    public static final float FOG_NEAR = 14f;
    public static final float FOG_FAR = 62f;

    public static final float CAMERA_FOV = 62f;
    public static final float CAMERA_NEAR = 0.15f;
    public static final float CAMERA_FAR = 140f;

    // ---- Simulation ---------------------------------------------------

    /** Physics/gameplay step. The renderer interpolates between steps. */
    public static final float FIXED_STEP = 1f / 60f;
    /** Never simulate more than this many seconds of catch-up in one frame. */
    public static final float MAX_FRAME_TIME = 0.25f;

    public static final float GRAVITY = -22f;
    public static final float TERMINAL_VELOCITY = -45f;

    // ---- Player ---------------------------------------------------------

    public static final float PLAYER_RADIUS = 0.32f;
    public static final float PLAYER_HEIGHT = 1.75f;
    /** Ledges up to this height are stepped over instead of blocking. */
    public static final float STEP_HEIGHT = 0.42f;
    /** Slopes steeper than this (degrees) cannot be stood on. */
    public static final float MAX_SLOPE_DEGREES = 50f;

    public static final float WALK_SPEED = 2.1f;
    public static final float RUN_SPEED = 5.4f;
    public static final float TURN_SPEED = 12f;

    public static final float ROLL_SPEED = 8.2f;
    public static final float ROLL_DURATION = 0.55f;
    /** Fraction of the roll spent invulnerable (Souls-style i-frames). */
    public static final float ROLL_IFRAME_START = 0.10f;
    public static final float ROLL_IFRAME_END = 0.53f;
    public static final float ROLL_STAMINA = 22f;

    public static final float BACKSTEP_SPEED = 6.5f;
    public static final float BACKSTEP_DURATION = 0.38f;
    public static final float BACKSTEP_STAMINA = 14f;

    public static final float SPRINT_STAMINA_PER_SEC = 12f;
    public static final float STAMINA_REGEN_PER_SEC = 30f;
    /** Pause before stamina starts coming back after it is spent. */
    public static final float STAMINA_REGEN_DELAY = 0.6f;

    // ---- Camera ---------------------------------------------------------

    public static final float CAM_DISTANCE = 4.2f;
    public static final float CAM_HEIGHT = 1.32f;
    public static final float CAM_MIN_PITCH = -62f;
    public static final float CAM_MAX_PITCH = 48f;
    public static final float CAM_LOCK_RANGE = 16f;
    /** How far the camera keeps off geometry it would otherwise clip through. */
    public static final float CAM_COLLISION_PAD = 0.28f;
}
