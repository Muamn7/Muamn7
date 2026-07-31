package com.muamn.ashen.input;

import com.badlogic.gdx.Gdx;
import com.badlogic.gdx.Input;

/**
 * Keyboard and mouse bindings, used for development and for the desktop build.
 * The Android build uses {@link TouchControls} instead; both write the same
 * {@link ControlState}, so nothing downstream branches on platform.
 */
public class DesktopControls {

    /** Degrees of camera rotation per pixel of mouse movement. */
    public float mouseSensitivity = 0.16f;
    public boolean invertY = false;

    private boolean prevRoll, prevLight, prevHeavy, prevLock, prevUse, prevInteract, prevPause,
            prevCycle;

    public void update(ControlState out) {
        // --- movement ---
        float x = 0f, y = 0f;
        if (Gdx.input.isKeyPressed(Input.Keys.W) || Gdx.input.isKeyPressed(Input.Keys.UP)) y += 1f;
        if (Gdx.input.isKeyPressed(Input.Keys.S) || Gdx.input.isKeyPressed(Input.Keys.DOWN)) y -= 1f;
        if (Gdx.input.isKeyPressed(Input.Keys.A) || Gdx.input.isKeyPressed(Input.Keys.LEFT)) x -= 1f;
        if (Gdx.input.isKeyPressed(Input.Keys.D) || Gdx.input.isKeyPressed(Input.Keys.RIGHT)) x += 1f;
        out.move.set(x, y);
        if (out.move.len2() > 1f) out.move.nor();

        // --- look ---
        float dx = Gdx.input.getDeltaX();
        float dy = Gdx.input.getDeltaY();
        if (Gdx.input.isCursorCatched()) {
            out.look.add(dx * mouseSensitivity, (invertY ? dy : -dy) * mouseSensitivity);
        }
        // Arrow-key camera for when the cursor is not captured.
        float keyLook = 120f * Gdx.graphics.getDeltaTime();
        if (Gdx.input.isKeyPressed(Input.Keys.J)) out.look.x -= keyLook;
        if (Gdx.input.isKeyPressed(Input.Keys.L)) out.look.x += keyLook;
        if (Gdx.input.isKeyPressed(Input.Keys.I)) out.look.y += keyLook;
        if (Gdx.input.isKeyPressed(Input.Keys.K)) out.look.y -= keyLook;

        // --- buttons ---
        boolean roll = Gdx.input.isKeyPressed(Input.Keys.SPACE);
        boolean light = Gdx.input.isButtonPressed(Input.Buttons.LEFT)
                || Gdx.input.isKeyPressed(Input.Keys.NUM_1);
        boolean heavy = Gdx.input.isKeyPressed(Input.Keys.NUM_2)
                || (Gdx.input.isButtonPressed(Input.Buttons.LEFT)
                    && Gdx.input.isKeyPressed(Input.Keys.SHIFT_LEFT));
        boolean lock = Gdx.input.isKeyPressed(Input.Keys.Q)
                || Gdx.input.isButtonPressed(Input.Buttons.MIDDLE);
        boolean use = Gdx.input.isKeyPressed(Input.Keys.R);
        boolean cycle = Gdx.input.isKeyPressed(Input.Keys.X);
        boolean interact = Gdx.input.isKeyPressed(Input.Keys.E);
        boolean pause = Gdx.input.isKeyPressed(Input.Keys.ESCAPE);

        out.sprintHeld = Gdx.input.isKeyPressed(Input.Keys.SHIFT_LEFT)
                || Gdx.input.isKeyPressed(Input.Keys.SHIFT_RIGHT);
        out.guardHeld = Gdx.input.isButtonPressed(Input.Buttons.RIGHT)
                || Gdx.input.isKeyPressed(Input.Keys.F);
        out.rollHeld = roll;

        out.rollPressed |= roll && !prevRoll;
        out.attackLightPressed |= light && !prevLight && !out.sprintHeld;
        out.attackHeavyPressed |= heavy && !prevHeavy;
        out.lockOnPressed |= lock && !prevLock;
        out.usePressed |= use && !prevUse;
        out.cycleItemPressed |= cycle && !prevCycle;
        out.interactPressed |= interact && !prevInteract;
        out.pausePressed |= pause && !prevPause;

        prevRoll = roll;
        prevLight = light;
        prevHeavy = heavy;
        prevLock = lock;
        prevUse = use;
        prevCycle = cycle;
        prevInteract = interact;
        prevPause = pause;
    }
}
