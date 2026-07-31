package com.muamn.ashen.input;

import com.badlogic.gdx.math.Vector2;

/**
 * One frame of player intent, in a form the gameplay code can read without
 * caring whether it came from a thumb, a keyboard or a gamepad.
 *
 * Held flags stay true for as long as the control is down; {@code *Pressed}
 * flags are edges and are cleared once per frame by {@link #clearEdges()}.
 */
public class ControlState {

    /** Stick direction in screen space, length 0..1. y is "forward". */
    public final Vector2 move = new Vector2();
    /** Camera look delta for this frame, in degrees. x is yaw, y is pitch. */
    public final Vector2 look = new Vector2();

    public boolean sprintHeld;
    public boolean guardHeld;

    public boolean rollPressed;
    public boolean attackLightPressed;
    public boolean attackHeavyPressed;
    public boolean lockOnPressed;
    public boolean usePressed;
    /** Steps the quick slot to the next consumable being carried. */
    public boolean cycleItemPressed;
    public boolean interactPressed;
    public boolean pausePressed;

    /** True while the roll button is held, used to tell a roll from a backstep. */
    public boolean rollHeld;

    public float moveMagnitude() {
        return move.len();
    }

    public void clearEdges() {
        rollPressed = false;
        attackLightPressed = false;
        attackHeavyPressed = false;
        lockOnPressed = false;
        usePressed = false;
        cycleItemPressed = false;
        interactPressed = false;
        pausePressed = false;
        look.setZero();
    }

    public void reset() {
        clearEdges();
        move.setZero();
        sprintHeld = false;
        guardHeld = false;
        rollHeld = false;
    }
}
