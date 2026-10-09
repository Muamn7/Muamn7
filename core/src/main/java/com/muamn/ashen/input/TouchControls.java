package com.muamn.ashen.input;

import com.badlogic.gdx.Gdx;
import com.badlogic.gdx.graphics.Color;
import com.badlogic.gdx.graphics.GL20;
import com.badlogic.gdx.graphics.g2d.BitmapFont;
import com.badlogic.gdx.graphics.g2d.GlyphLayout;
import com.badlogic.gdx.graphics.g2d.SpriteBatch;
import com.badlogic.gdx.graphics.glutils.ShapeRenderer;
import com.badlogic.gdx.math.MathUtils;
import com.badlogic.gdx.math.Vector2;
import com.badlogic.gdx.utils.Disposable;

/**
 * On-screen gamepad for the phone build, laid out like the overlay of a PC
 * emulator: two sticks, a D-pad, four face buttons, four shoulder buttons and
 * Select/Start, so a player who knows the game on a controller finds every
 * action where their thumbs expect it.
 *
 * <pre>
 *   LT  lock-on                         RT  heavy attack
 *   LB  guard (+RB = parry)             RB  light attack
 *
 *   left stick: move                        Y  lock-on
 *   (push to the rim to sprint)          X     B  use item / roll
 *                                           A  talk / bonfire
 *   D-pad  left/right: weapon            right stick: camera
 *          down: next item               (tap it: lock-on)
 *          up: use item
 *                 SELECT: language   START: fade the overlay
 * </pre>
 *
 * The left stick floats: it rests at its home spot so the layout reads as a
 * controller, but a thumb landing anywhere in the lower-left re-centres it
 * there, because a stick that has to be found by feel is the most common reason
 * action games feel bad on glass. Dragging any free spot on the right still
 * turns the camera, as the right stick does.
 *
 * Positions are in a 720-pixel-tall design space and scaled to the screen, so
 * the pad keeps its proportions from a small phone to a tablet.
 *
 * State is polled from {@link Gdx#input} instead of going through an
 * InputProcessor, so it composes with whatever else owns the input multiplexer.
 */
public class TouchControls implements Disposable {

    private static final int MAX_POINTERS = 10;

    private enum Anchor { LEFT, RIGHT, CENTER }
    private enum Shape { ROUND, PILL, DPAD }

    /**
     * Every button, as an offset in design pixels from its anchor: LEFT and
     * RIGHT measure x in from that screen edge, CENTER from the middle; y is
     * always up from the bottom.
     */
    private enum Button {
        A("A", Anchor.RIGHT, Shape.ROUND, 165f, 115f, 38f, 0f, 0.36f, 0.78f, 0.38f),
        B("B", Anchor.RIGHT, Shape.ROUND, 83f, 197f, 38f, 0f, 0.88f, 0.33f, 0.30f),
        X("X", Anchor.RIGHT, Shape.ROUND, 247f, 197f, 38f, 0f, 0.32f, 0.52f, 0.92f),
        Y("Y", Anchor.RIGHT, Shape.ROUND, 165f, 279f, 38f, 0f, 0.92f, 0.80f, 0.30f),
        RB("RB", Anchor.RIGHT, Shape.PILL, 120f, 395f, 24f, 64f, 0.82f, 0.80f, 0.74f),
        RT("RT", Anchor.RIGHT, Shape.PILL, 120f, 462f, 24f, 64f, 0.82f, 0.80f, 0.74f),
        LB("LB", Anchor.LEFT, Shape.PILL, 120f, 395f, 24f, 64f, 0.82f, 0.80f, 0.74f),
        LT("LT", Anchor.LEFT, Shape.PILL, 120f, 462f, 24f, 64f, 0.82f, 0.80f, 0.74f),
        UP("", Anchor.LEFT, Shape.DPAD, 395f, 147f, 25f, 90f, 0.82f, 0.80f, 0.74f),
        DOWN("", Anchor.LEFT, Shape.DPAD, 395f, 53f, 25f, 270f, 0.82f, 0.80f, 0.74f),
        LEFT("", Anchor.LEFT, Shape.DPAD, 348f, 100f, 25f, 180f, 0.82f, 0.80f, 0.74f),
        RIGHT("", Anchor.LEFT, Shape.DPAD, 442f, 100f, 25f, 0f, 0.82f, 0.80f, 0.74f),
        // Labels stay ASCII: the built-in bitmap font has no glyphs beyond it.
        SELECT("SEL", Anchor.CENTER, Shape.PILL, -80f, 34f, 17f, 30f, 0.82f, 0.80f, 0.74f),
        START("START", Anchor.CENTER, Shape.PILL, 80f, 34f, 17f, 30f, 0.82f, 0.80f, 0.74f);

        final String label;
        final Anchor anchor;
        final Shape shape;
        final float offsetX, offsetY;
        /** Radius for round buttons and D-pad arms, half-height for pills. */
        final float radius;
        /** Half the straight run of a pill, or the arrow direction of a D-pad arm. */
        final float extra;
        final float r, g, b;

        Button(String label, Anchor anchor, Shape shape, float offsetX, float offsetY,
               float radius, float extra, float r, float g, float b) {
            this.label = label;
            this.anchor = anchor;
            this.shape = shape;
            this.offsetX = offsetX;
            this.offsetY = offsetY;
            this.radius = radius;
            this.extra = extra;
            this.r = r;
            this.g = g;
            this.b = b;
        }
    }

    // Stick homes, in design pixels from their corner.
    private static final float LSTICK_X = 175f, LSTICK_Y = 190f, LSTICK_RANGE = 85f;
    private static final float RSTICK_X = 410f, RSTICK_Y = 100f, RSTICK_RANGE = 60f;
    /** Degrees per second the camera turns with the right stick fully pushed. */
    private static final float RSTICK_TURN_RATE = 170f;
    /** A right-stick touch shorter and smaller than this is a click (R3). */
    private static final float RSTICK_TAP_TIME = 0.22f;

    private final ShapeRenderer shapes = new ShapeRenderer();
    private final SpriteBatch batch = new SpriteBatch();
    private final BitmapFont font = new BitmapFont();
    private final GlyphLayout layout = new GlyphLayout();

    private int screenW = 1, screenH = 1;
    private float scale = 1f;

    // Left stick: floating, owned by one pointer at a time.
    private final Vector2 stickHome = new Vector2();
    private final Vector2 stickOrigin = new Vector2();
    private final Vector2 stickCurrent = new Vector2();
    private int stickPointer = -1;
    private float stickRange = LSTICK_RANGE;

    // Right stick: fixed, drives the camera at a rate.
    private final Vector2 rstickHome = new Vector2();
    private final Vector2 rstickCurrent = new Vector2();
    private int rstickPointer = -1;
    private float rstickRange = RSTICK_RANGE;
    private float rstickHeldTime;
    private float rstickMaxDeflection;

    /** Deflection past this fraction counts as sprinting. */
    private float sprintThreshold = 0.92f;
    /** How long the stick must be held past the threshold before sprinting. */
    private float sprintHoldTime = 0.28f;
    private float sprintTimer;

    private final boolean[] buttonDown = new boolean[Button.values().length];
    private final boolean[] buttonPrev = new boolean[Button.values().length];
    private final boolean[] pointerPrev = new boolean[MAX_POINTERS];

    /** START dims the overlay to a ghost; the buttons keep working underneath. */
    private boolean faded;

    private final Vector2 tmp = new Vector2();

    public TouchControls() {
        font.setColor(0.95f, 0.93f, 0.88f, 1f);
        font.setUseIntegerPositions(false);
    }

    /** Scales the pad for the current screen. Call on resize. */
    public void resize(int width, int height) {
        screenW = Math.max(1, width);
        screenH = Math.max(1, height);
        // Fit the shorter side, and never let the pad outgrow a narrow screen:
        // the left and right clusters each need about 500 design pixels.
        scale = Math.min(Math.min(screenW, screenH) / 720f, screenW / 1100f);
        scale = MathUtils.clamp(scale, 0.55f, 2.6f);
        stickRange = LSTICK_RANGE * scale;
        rstickRange = RSTICK_RANGE * scale;
        stickHome.set(LSTICK_X * scale, LSTICK_Y * scale);
        rstickHome.set(screenW - RSTICK_X * scale, RSTICK_Y * scale);
        if (stickPointer < 0) stickOrigin.set(stickHome);
        font.getData().setScale(Math.max(1f, 1.35f * scale));
    }

    public void update(ControlState out, float dt) {
        if (Gdx.graphics.getWidth() != screenW || Gdx.graphics.getHeight() != screenH) {
            updateProjection(Gdx.graphics.getWidth(), Gdx.graphics.getHeight());
        }

        System.arraycopy(buttonDown, 0, buttonPrev, 0, buttonDown.length);
        java.util.Arrays.fill(buttonDown, false);

        boolean stickStillHeld = false, rstickStillHeld = false;
        float lookX = 0f, lookY = 0f;

        for (int p = 0; p < MAX_POINTERS; p++) {
            boolean touched = Gdx.input.isTouched(p);
            boolean justDown = touched && !pointerPrev[p];
            pointerPrev[p] = touched;
            if (!touched) continue;

            float x = Gdx.input.getX(p);
            float y = screenH - Gdx.input.getY(p); // to y-up

            if (p == stickPointer) {
                stickCurrent.set(x, y);
                stickStillHeld = true;
                continue;
            }
            if (p == rstickPointer) {
                rstickCurrent.set(x, y);
                rstickStillHeld = true;
                continue;
            }

            Button hit = buttonAt(x, y);
            if (hit != null) {
                buttonDown[hit.ordinal()] = true;
                continue;
            }

            // Sticks are only claimed by a fresh touch, so a thumb sliding off a
            // button does not suddenly grab one.
            if (justDown && rstickPointer < 0
                    && tmp.set(x, y).dst2(rstickHome) <= sq(rstickRange * 1.35f)) {
                rstickPointer = p;
                rstickCurrent.set(x, y);
                rstickHeldTime = 0f;
                rstickMaxDeflection = 0f;
                rstickStillHeld = true;
            } else if (justDown && stickPointer < 0
                    && x < screenW * 0.42f && y < screenH * 0.62f) {
                stickPointer = p;
                stickOrigin.set(x, y);
                stickCurrent.set(x, y);
                stickStillHeld = true;
            } else if (x >= screenW * 0.42f) {
                // Anywhere on the right that is not a control drags the camera.
                lookX += Gdx.input.getDeltaX(p) * 0.22f;
                lookY -= Gdx.input.getDeltaY(p) * 0.22f;
            }
        }

        // --- left stick to movement ---
        if (stickStillHeld) {
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
            stickPointer = -1;
            stickOrigin.set(stickHome);
            sprintTimer = 0f;
            out.move.setZero();
            out.sprintHeld = false;
        }

        // --- right stick to camera ---
        boolean rstickClick = false;
        if (rstickStillHeld) {
            rstickHeldTime += dt;
            tmp.set(rstickCurrent).sub(rstickHome);
            if (tmp.len() > rstickRange) tmp.setLength(rstickRange);
            float mag = tmp.len() / rstickRange;
            rstickMaxDeflection = Math.max(rstickMaxDeflection, mag);
            if (mag > 0.15f) {
                float k = (mag - 0.15f) / 0.85f;
                tmp.nor().scl(k * k * RSTICK_TURN_RATE * dt);
                lookX += tmp.x;
                lookY += tmp.y;
            }
        } else if (rstickPointer >= 0) {
            rstickClick = rstickHeldTime < RSTICK_TAP_TIME && rstickMaxDeflection < 0.35f;
            rstickPointer = -1;
        }

        out.look.add(lookX, lookY);

        // --- buttons ---
        out.rollHeld = down(Button.B);
        out.guardHeld = down(Button.LB);
        out.rollPressed |= edge(Button.B);
        out.attackLightPressed |= edge(Button.RB);
        out.attackHeavyPressed |= edge(Button.RT);
        out.lockOnPressed |= edge(Button.Y) || edge(Button.LT) || rstickClick;
        out.usePressed |= edge(Button.X) || edge(Button.UP);
        out.cycleItemPressed |= edge(Button.DOWN);
        out.interactPressed |= edge(Button.A);
        if (edge(Button.LEFT)) out.weaponStep = -1;
        if (edge(Button.RIGHT)) out.weaponStep = 1;
        out.languagePressed |= edge(Button.SELECT);
        if (edge(Button.START)) faded = !faded;
    }

    private boolean down(Button b) {
        return buttonDown[b.ordinal()];
    }

    private boolean edge(Button b) {
        return buttonDown[b.ordinal()] && !buttonPrev[b.ordinal()];
    }

    private static float sq(float v) {
        return v * v;
    }

    private float centerX(Button b) {
        switch (b.anchor) {
            case LEFT: return b.offsetX * scale;
            case RIGHT: return screenW - b.offsetX * scale;
            default: return screenW * 0.5f + b.offsetX * scale;
        }
    }

    private float centerY(Button b) {
        return b.offsetY * scale;
    }

    private Button buttonAt(float x, float y) {
        for (Button b : Button.values()) {
            float dx = x - centerX(b), dy = y - centerY(b);
            float r = b.radius * scale;
            if (b.shape == Shape.PILL) {
                // A generous box around the pill: shoulders are hit by feel.
                float halfW = (b.extra + b.radius) * scale * 1.1f;
                float halfH = r * 1.35f;
                if (Math.abs(dx) <= halfW && Math.abs(dy) <= halfH) return b;
                continue;
            }
            // Generous hit radius; the drawn shape stays the visual size. D-pad
            // arms sit close together, so they get less slack than face buttons.
            r *= b.shape == Shape.DPAD ? 1.3f : 1.25f;
            if (dx * dx + dy * dy <= r * r) return b;
        }
        return null;
    }

    /** Draws the overlay. Call after the 3D scene has been presented. */
    public void render() {
        float alpha = faded ? 0.35f : 1f;

        // ShapeRenderer does not manage blend state, so set it explicitly or the
        // translucent buttons come out solid white.
        Gdx.gl.glEnable(GL20.GL_BLEND);
        Gdx.gl.glBlendFunc(GL20.GL_SRC_ALPHA, GL20.GL_ONE_MINUS_SRC_ALPHA);
        shapes.begin(ShapeRenderer.ShapeType.Filled);

        // Sticks: base, then knob.
        tmp.set(stickCurrent).sub(stickOrigin);
        if (stickPointer < 0) tmp.setZero();
        else if (tmp.len() > stickRange) tmp.setLength(stickRange);
        drawStick(stickOrigin.x, stickOrigin.y, stickRange, tmp.x, tmp.y, stickPointer >= 0, alpha);

        tmp.set(rstickCurrent).sub(rstickHome);
        if (rstickPointer < 0) tmp.setZero();
        else if (tmp.len() > rstickRange) tmp.setLength(rstickRange);
        drawStick(rstickHome.x, rstickHome.y, rstickRange, tmp.x, tmp.y, rstickPointer >= 0, alpha);

        // D-pad hub, so the four arms read as one cross.
        float hubX = centerX(Button.UP), hubY = (centerY(Button.UP) + centerY(Button.DOWN)) * 0.5f;
        shapes.setColor(0.10f, 0.10f, 0.12f, 0.30f * alpha);
        shapes.rect(hubX - 22f * scale, hubY - 22f * scale, 44f * scale, 44f * scale);

        for (Button b : Button.values()) {
            boolean pressed = down(b);
            float cx = centerX(b), cy = centerY(b), r = b.radius * scale;
            float fill = pressed ? 0.70f : 0.30f;
            float tint = pressed ? 1f : 0.75f;
            shapes.setColor(b.r * tint, b.g * tint, b.b * tint, fill * alpha);
            switch (b.shape) {
                case ROUND:
                    shapes.circle(cx, cy, r, 32);
                    break;
                case PILL:
                    pill(cx, cy, b.extra * scale, r);
                    break;
                case DPAD:
                    shapes.rect(cx - r, cy - r, r * 2f, r * 2f);
                    // The arrow, pointing away from the hub.
                    shapes.setColor(0.95f, 0.93f, 0.88f, (pressed ? 0.95f : 0.7f) * alpha);
                    float a = b.extra * MathUtils.degreesToRadians;
                    float tipX = cx + MathUtils.cos(a) * r * 0.55f, tipY = cy + MathUtils.sin(a) * r * 0.55f;
                    float px = -MathUtils.sin(a) * r * 0.45f, py = MathUtils.cos(a) * r * 0.45f;
                    float baseX = cx - MathUtils.cos(a) * r * 0.25f, baseY = cy - MathUtils.sin(a) * r * 0.25f;
                    shapes.triangle(tipX, tipY, baseX + px, baseY + py, baseX - px, baseY - py);
                    break;
            }
        }
        shapes.end();

        shapes.begin(ShapeRenderer.ShapeType.Line);
        shapes.setColor(0.95f, 0.93f, 0.88f, 0.45f * alpha);
        for (Button b : Button.values()) {
            float cx = centerX(b), cy = centerY(b), r = b.radius * scale;
            switch (b.shape) {
                case ROUND: shapes.circle(cx, cy, r, 32); break;
                case PILL: pillOutline(cx, cy, b.extra * scale, r); break;
                case DPAD: shapes.rect(cx - r, cy - r, r * 2f, r * 2f); break;
            }
        }
        shapes.circle(stickOrigin.x, stickOrigin.y, stickRange, 40);
        shapes.circle(rstickHome.x, rstickHome.y, rstickRange, 40);
        shapes.end();

        batch.begin();
        font.setColor(0.97f, 0.95f, 0.90f, 0.95f * alpha);
        for (Button b : Button.values()) {
            if (b.label.isEmpty()) continue;
            layout.setText(font, b.label);
            font.draw(batch, layout, centerX(b) - layout.width * 0.5f, centerY(b) + layout.height * 0.5f);
        }
        drawCaption("L", stickOrigin.x, stickOrigin.y);
        drawCaption("R", rstickHome.x, rstickHome.y);
        batch.end();
    }

    private void drawStick(float x, float y, float range, float knobDx, float knobDy,
                           boolean active, float alpha) {
        shapes.setColor(0.10f, 0.10f, 0.12f, (active ? 0.35f : 0.25f) * alpha);
        shapes.circle(x, y, range, 40);
        shapes.setColor(0.85f, 0.83f, 0.78f, (active ? 0.55f : 0.32f) * alpha);
        shapes.circle(x + knobDx, y + knobDy, range * 0.42f, 32);
    }

    private void drawCaption(String text, float x, float y) {
        layout.setText(font, text);
        font.draw(batch, layout, x - layout.width * 0.5f, y + layout.height * 0.5f);
    }

    private void pill(float cx, float cy, float halfRun, float r) {
        // Half-disc caps, not full circles: the fill is translucent, so any
        // overlap with the middle would show as a darker band.
        shapes.rect(cx - halfRun, cy - r, halfRun * 2f, r * 2f);
        shapes.arc(cx - halfRun, cy, r, 90f, 180f, 16);
        shapes.arc(cx + halfRun, cy, r, -90f, 180f, 16);
    }

    private void pillOutline(float cx, float cy, float halfRun, float r) {
        shapes.line(cx - halfRun, cy - r, cx + halfRun, cy - r);
        shapes.line(cx - halfRun, cy + r, cx + halfRun, cy + r);
        // ShapeRenderer.arc also draws the two radii, which would cut the caps.
        halfCircle(cx - halfRun, cy, r, 90f);
        halfCircle(cx + halfRun, cy, r, -90f);
    }

    private void halfCircle(float cx, float cy, float r, float startDeg) {
        final int segments = 16;
        float step = 180f / segments;
        for (int i = 0; i < segments; i++) {
            float a0 = startDeg + i * step, a1 = a0 + step;
            shapes.line(cx + MathUtils.cosDeg(a0) * r, cy + MathUtils.sinDeg(a0) * r,
                    cx + MathUtils.cosDeg(a1) * r, cy + MathUtils.sinDeg(a1) * r);
        }
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
