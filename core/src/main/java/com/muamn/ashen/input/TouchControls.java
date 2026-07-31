package com.muamn.ashen.input;

import com.badlogic.gdx.Gdx;
import com.badlogic.gdx.graphics.Color;
import com.badlogic.gdx.graphics.GL20;
import com.badlogic.gdx.graphics.g2d.BitmapFont;
import com.badlogic.gdx.graphics.g2d.SpriteBatch;
import com.badlogic.gdx.graphics.glutils.ShapeRenderer;
import com.badlogic.gdx.math.MathUtils;
import com.badlogic.gdx.math.Vector2;
import com.badlogic.gdx.utils.Disposable;

/**
 * On-screen controls for the phone build.
 *
 * The left half is a floating stick: it appears wherever the thumb lands rather
 * than at a fixed spot, because a fixed stick is the single most common reason
 * action games feel bad on a touchscreen. The right side holds the attack,
 * dodge, guard and lock-on buttons, laid out for a thumb arc rather than a grid.
 *
 * State is polled from {@link Gdx#input} instead of going through an
 * InputProcessor, so it composes with whatever else owns the input multiplexer.
 */
public class TouchControls implements Disposable {

    private static final int MAX_POINTERS = 10;

    /** Buttons, in screen pixels from the bottom-right corner. */
    private enum Button {
        LIGHT("R1", 118f, 128f, 52f),
        HEAVY("R2", 196f, 210f, 46f),
        ROLL("RL", 232f, 96f, 52f),
        GUARD("L1", 112f, 246f, 44f),
        // Labels stay ASCII: the built-in bitmap font has no glyphs beyond it.
        LOCK("LK", 330f, 78f, 40f),
        USE("IT", 348f, 186f, 40f);

        final String label;
        final float offsetX, offsetY, radius;

        Button(String label, float offsetX, float offsetY, float radius) {
            this.label = label;
            this.offsetX = offsetX;
            this.offsetY = offsetY;
            this.radius = radius;
        }
    }

    private final ShapeRenderer shapes = new ShapeRenderer();
    private final SpriteBatch batch = new SpriteBatch();
    private final BitmapFont font = new BitmapFont();

    private final Vector2 stickOrigin = new Vector2();
    private final Vector2 stickCurrent = new Vector2();
    private int stickPointer = -1;
    private boolean stickActive;

    /** Radius, in pixels, at which the stick reads as fully deflected. */
    private float stickRange = 110f;
    /** Deflection past this fraction counts as sprinting. */
    private float sprintThreshold = 0.92f;
    /** How long the stick must be held past the threshold before sprinting. */
    private float sprintHoldTime = 0.28f;
    private float sprintTimer;

    private final boolean[] buttonDown = new boolean[Button.values().length];
    private final boolean[] buttonPrev = new boolean[Button.values().length];

    private final Vector2 tmp = new Vector2();

    public TouchControls() {
        font.setColor(0.85f, 0.83f, 0.78f, 0.9f);
    }

    /** Scales the touch targets for the current screen. Call on resize. */
    public void resize(int width, int height) {
        stickRange = MathUtils.clamp(Math.min(width, height) * 0.22f, 70f, 160f);
    }

    public void update(ControlState out, float dt) {
        int screenH = Gdx.graphics.getHeight();
        int screenW = Gdx.graphics.getWidth();

        System.arraycopy(buttonDown, 0, buttonPrev, 0, buttonDown.length);
        java.util.Arrays.fill(buttonDown, false);

        boolean stickStillHeld = false;
        float lookX = 0f, lookY = 0f;

        for (int p = 0; p < MAX_POINTERS; p++) {
            if (!Gdx.input.isTouched(p)) continue;
            float x = Gdx.input.getX(p);
            float y = screenH - Gdx.input.getY(p); // to y-up

            if (p == stickPointer) {
                stickCurrent.set(x, y);
                stickStillHeld = true;
                continue;
            }

            Button hit = buttonAt(x, y, screenW);
            if (hit != null) {
                buttonDown[hit.ordinal()] = true;
                continue;
            }

            if (x < screenW * 0.45f && stickPointer < 0) {
                stickPointer = p;
                stickOrigin.set(x, y);
                stickCurrent.set(x, y);
                stickActive = true;
                stickStillHeld = true;
            } else if (x >= screenW * 0.45f) {
                // Anywhere on the right that is not a button drags the camera.
                lookX += Gdx.input.getDeltaX(p) * 0.22f;
                lookY -= Gdx.input.getDeltaY(p) * 0.22f;
            }
        }

        if (!stickStillHeld) {
            stickPointer = -1;
            stickActive = false;
            sprintTimer = 0f;
        }

        // --- stick to movement ---
        if (stickActive) {
            tmp.set(stickCurrent).sub(stickOrigin);
            float len = tmp.len();
            if (len > stickRange) {
                // Let the origin trail the thumb so the stick never runs out of travel.
                stickOrigin.add(tmp.x * (1f - stickRange / len), tmp.y * (1f - stickRange / len));
                tmp.setLength(stickRange);
                len = stickRange;
            }
            float mag = len / stickRange;
            // Small dead zone: a resting thumb should not creep.
            mag = mag < 0.12f ? 0f : (mag - 0.12f) / 0.88f;
            out.move.set(tmp).nor().scl(mag);
            if (mag <= 0f) out.move.setZero();

            sprintTimer = mag >= sprintThreshold ? sprintTimer + dt : 0f;
            out.sprintHeld = sprintTimer >= sprintHoldTime;
        } else {
            out.move.setZero();
            out.sprintHeld = false;
        }

        out.look.add(lookX, lookY);

        // --- buttons ---
        out.rollHeld = buttonDown[Button.ROLL.ordinal()];
        out.guardHeld = buttonDown[Button.GUARD.ordinal()];
        out.rollPressed |= edge(Button.ROLL);
        out.attackLightPressed |= edge(Button.LIGHT);
        out.attackHeavyPressed |= edge(Button.HEAVY);
        out.lockOnPressed |= edge(Button.LOCK);
        out.usePressed |= edge(Button.USE);
        out.interactPressed |= edge(Button.USE) && out.move.isZero();
    }

    private boolean edge(Button b) {
        return buttonDown[b.ordinal()] && !buttonPrev[b.ordinal()];
    }

    private Button buttonAt(float x, float y, int screenW) {
        for (Button b : Button.values()) {
            float bx = screenW - b.offsetX;
            float by = b.offsetY;
            float dx = x - bx, dy = y - by;
            // Generous hit radius; the drawn circle stays the visual size.
            float r = b.radius * 1.25f;
            if (dx * dx + dy * dy <= r * r) return b;
        }
        return null;
    }

    /** Draws the overlay. Call after the 3D scene has been presented. */
    public void render() {
        int screenW = Gdx.graphics.getWidth();

        // ShapeRenderer does not manage blend state, so set it explicitly or the
        // translucent buttons come out solid white.
        Gdx.gl.glEnable(GL20.GL_BLEND);
        Gdx.gl.glBlendFunc(GL20.GL_SRC_ALPHA, GL20.GL_ONE_MINUS_SRC_ALPHA);
        shapes.begin(ShapeRenderer.ShapeType.Filled);

        if (stickActive) {
            shapes.setColor(0.85f, 0.83f, 0.78f, 0.16f);
            shapes.circle(stickOrigin.x, stickOrigin.y, stickRange, 32);
            tmp.set(stickCurrent).sub(stickOrigin);
            if (tmp.len() > stickRange) tmp.setLength(stickRange);
            shapes.setColor(0.92f, 0.88f, 0.78f, 0.34f);
            shapes.circle(stickOrigin.x + tmp.x, stickOrigin.y + tmp.y, stickRange * 0.34f, 24);
        }

        for (Button b : Button.values()) {
            float bx = screenW - b.offsetX;
            boolean down = buttonDown[b.ordinal()];
            shapes.setColor(down ? 0.95f : 0.80f, down ? 0.72f : 0.78f,
                    down ? 0.35f : 0.72f, down ? 0.42f : 0.20f);
            shapes.circle(bx, b.offsetY, b.radius, 28);
        }
        shapes.end();

        shapes.begin(ShapeRenderer.ShapeType.Line);
        shapes.setColor(0.9f, 0.88f, 0.82f, 0.35f);
        for (Button b : Button.values()) {
            shapes.circle(screenW - b.offsetX, b.offsetY, b.radius, 28);
        }
        shapes.end();

        batch.begin();
        for (Button b : Button.values()) {
            float bx = screenW - b.offsetX;
            // Rough centring is fine for one- and two-character labels.
            font.draw(batch, b.label, bx - b.label.length() * 4.5f, b.offsetY + 6f);
        }
        batch.end();
    }

    /** Updates the projection after a resize. */
    public void updateProjection(int width, int height) {
        shapes.getProjectionMatrix().setToOrtho2D(0f, 0f, width, height);
        batch.getProjectionMatrix().setToOrtho2D(0f, 0f, width, height);
        resize(width, height);
    }

    public void setColor(Color c) {
        font.setColor(c);
    }

    @Override
    public void dispose() {
        shapes.dispose();
        batch.dispose();
        font.dispose();
    }
}
