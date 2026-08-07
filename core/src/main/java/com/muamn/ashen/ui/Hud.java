package com.muamn.ashen.ui;

import com.badlogic.gdx.Gdx;
import com.badlogic.gdx.graphics.GL20;
import com.badlogic.gdx.graphics.g2d.SpriteBatch;
import com.badlogic.gdx.graphics.glutils.ShapeRenderer;
import com.badlogic.gdx.math.MathUtils;
import com.badlogic.gdx.utils.Disposable;

import com.muamn.ashen.entity.Stats;
import com.muamn.ashen.text.Strings;
import com.muamn.ashen.text.Text;

/**
 * The in-game HUD: health, stamina and the soul count.
 *
 * The bars use the trailing-damage trick from the genre - a pale ghost bar drains
 * toward the real value a moment later, so a hit reads as "how much did that
 * cost me" at a glance without the player having to watch a number.
 */
public class Hud implements Disposable {

    private static final float BAR_X = 26f;
    private static final float BAR_TOP = 26f;
    private static final float BAR_HEIGHT = 15f;
    private static final float BAR_GAP = 9f;
    private static final float BORDER = 2f;

    private final ShapeRenderer shapes = new ShapeRenderer();
    private final SpriteBatch batch = new SpriteBatch();
    /** Shared with every other panel; the Hud does not own it. */
    private final Text text;

    private float ghostHealth = 1f;
    private float ghostStamina = 1f;

    /** Set true to draw frame timing and player state. */
    public boolean showDebug;
    private String debugLine = "";

    public Hud(Text text) {
        this.text = text;
    }

    public void resize(int width, int height) {
        shapes.getProjectionMatrix().setToOrtho2D(0f, 0f, width, height);
        batch.getProjectionMatrix().setToOrtho2D(0f, 0f, width, height);
    }

    public void setDebugLine(String line) {
        this.debugLine = line;
    }

    public void update(Stats stats, float dt) {
        float health = stats.healthFraction();
        float stamina = stats.staminaFraction();

        // The ghost bar catches up instantly when refilling, slowly when draining.
        ghostHealth = health > ghostHealth ? health
                : Math.max(health, ghostHealth - dt * 0.55f);
        ghostStamina = stamina > ghostStamina ? stamina
                : Math.max(stamina, ghostStamina - dt * 1.6f);
    }

    public void render(Stats stats) {
        int screenH = Gdx.graphics.getHeight();
        int screenW = Gdx.graphics.getWidth();

        // Bars scale with the screen so they stay readable on a phone.
        float scale = MathUtils.clamp(screenW / 960f, 0.75f, 2.2f);
        float barW = MathUtils.clamp(screenW * 0.30f, 180f, 460f);
        float h = BAR_HEIGHT * scale;
        float x = BAR_X * scale;
        float yHealth = screenH - BAR_TOP * scale - h;
        float yStamina = yHealth - h - BAR_GAP * scale;

        Gdx.gl.glEnable(GL20.GL_BLEND);
        Gdx.gl.glBlendFunc(GL20.GL_SRC_ALPHA, GL20.GL_ONE_MINUS_SRC_ALPHA);
        shapes.begin(ShapeRenderer.ShapeType.Filled);

        // Health bar length grows with vigor, as it does in the genre.
        float healthW = barW * MathUtils.clamp(stats.maxHealth / 900f, 0.42f, 1f);
        bar(x, yHealth, healthW, h, stats.healthFraction(), ghostHealth,
                0.10f, 0.02f, 0.02f, 0.62f, 0.13f, 0.11f, 0.78f, 0.55f, 0.45f);

        float staminaW = barW * MathUtils.clamp(stats.maxStamina / 170f, 0.42f, 1f);
        bar(x, yStamina, staminaW, h, stats.staminaFraction(), ghostStamina,
                0.05f, 0.09f, 0.04f, 0.36f, 0.55f, 0.22f, 0.55f, 0.72f, 0.40f);

        shapes.end();

        batch.begin();
        text.setScale(uiScale(scale));
        text.setColor(0.86f, 0.83f, 0.76f, 1f);
        text.drawRight(batch, Long.toString(stats.souls), screenW - 40f * scale, 42f * scale);
        if (showDebug && debugLine != null) {
            // The debug readout stays English and stays small; it is for me.
            text.setScale(uiScale(scale) * 0.7f);
            text.draw(batch, debugLine, x, yStamina - 18f);
        }
        text.setScale(1f);
        batch.end();
    }

    /** Border, empty track, ghost trail, then the live fill. */
    private void bar(float x, float y, float w, float h, float value, float ghost,
                     float br, float bg, float bb,
                     float fr, float fg, float fb,
                     float gr, float gg, float gb) {
        shapes.setColor(0f, 0f, 0f, 0.72f);
        shapes.rect(x - BORDER, y - BORDER, w + BORDER * 2f, h + BORDER * 2f);
        shapes.setColor(br, bg, bb, 0.92f);
        shapes.rect(x, y, w, h);
        shapes.setColor(gr, gg, gb, 0.55f);
        shapes.rect(x, y, w * MathUtils.clamp(ghost, 0f, 1f), h);
        shapes.setColor(fr, fg, fb, 1f);
        shapes.rect(x, y, w * MathUtils.clamp(value, 0f, 1f), h);
        // Top highlight so the bar does not read as flat.
        shapes.setColor(1f, 1f, 1f, 0.10f);
        shapes.rect(x, y + h * 0.62f, w * MathUtils.clamp(value, 0f, 1f), h * 0.20f);
    }

    /**
     * A small readout in the bottom corner for the first seconds of a session.
     *
     * It exists for one question that cannot be answered any other way: when a
     * player says "black screen", is the display pipeline running at all? If this
     * line is on the photograph, everything from the GL context to the font
     * works and the fault is further in. If it is not, nothing is reaching the
     * display and the fault is the surface itself.
     */
    public void bootInfo(String info) {
        if (info == null || info.isEmpty()) return;
        float scale = MathUtils.clamp(Gdx.graphics.getWidth() / 960f, 0.75f, 2.2f);
        batch.begin();
        text.setScale(uiScale(scale) * 0.62f);
        text.setColor(0.55f, 0.62f, 0.55f, 0.75f);
        text.draw(batch, info, 14f * scale, 22f * scale);
        text.setColor(0.86f, 0.83f, 0.76f, 1f);
        text.setScale(1f);
        batch.end();
    }

    /** Draws only the debug readout, for screens that have no player stats. */
    public void renderDebugOnly() {
        if (debugLine == null || debugLine.isEmpty()) return;
        batch.begin();
        text.setScale(0.5f);
        text.setColor(0.86f, 0.83f, 0.76f, 1f);
        text.draw(batch, debugLine, 14f, Gdx.graphics.getHeight() - 14f);
        text.setScale(1f);
        batch.end();
    }

    /**
     * Converts a layout scale into a font scale.
     *
     * The atlas is rendered at 34px so it never has to be scaled up, which means
     * the default draw scale is well under one. Every call site used to say
     * {@code max(1, scale)} against a 15px bitmap font; this is the one place
     * that conversion now lives.
     */
    private static float uiScale(float layoutScale) {
        return MathUtils.clamp(layoutScale * 0.52f, 0.34f, 1f);
    }

    /** A boss-style bar across the bottom for the locked-on target. */
    public void enemyBar(String name, float fraction) {
        int screenW = Gdx.graphics.getWidth();
        int screenH = Gdx.graphics.getHeight();
        float scale = MathUtils.clamp(screenW / 960f, 0.75f, 2.2f);
        float w = MathUtils.clamp(screenW * 0.42f, 240f, 620f);
        float h = 11f * scale;
        float x = (screenW - w) * 0.5f;
        float y = screenH * 0.13f;

        Gdx.gl.glEnable(GL20.GL_BLEND);
        Gdx.gl.glBlendFunc(GL20.GL_SRC_ALPHA, GL20.GL_ONE_MINUS_SRC_ALPHA);
        shapes.begin(ShapeRenderer.ShapeType.Filled);
        shapes.setColor(0f, 0f, 0f, 0.78f);
        shapes.rect(x - BORDER, y - BORDER, w + BORDER * 2f, h + BORDER * 2f);
        shapes.setColor(0.12f, 0.03f, 0.03f, 0.95f);
        shapes.rect(x, y, w, h);
        shapes.setColor(0.66f, 0.16f, 0.12f, 1f);
        shapes.rect(x, y, w * MathUtils.clamp(fraction, 0f, 1f), h);
        shapes.end();

        batch.begin();
        text.setScale(uiScale(scale) * 0.9f);
        text.setColor(0.86f, 0.83f, 0.76f, 1f);
        text.drawLeading(batch, name, x, x + w, y + h + 20f * scale);
        text.setScale(1f);
        batch.end();
    }

    /**
     * The boss bar: wider, lower, and divided into phase ticks so the player can
     * see how much of the fight is left rather than only how much health is.
     */
    public void bossBar(String name, float fraction, int phase, int phaseCount) {
        int screenW = Gdx.graphics.getWidth();
        int screenH = Gdx.graphics.getHeight();
        float scale = MathUtils.clamp(screenW / 960f, 0.75f, 2.2f);
        float w = MathUtils.clamp(screenW * 0.62f, 320f, 900f);
        float h = 15f * scale;
        float x = (screenW - w) * 0.5f;
        float y = screenH * 0.10f;

        Gdx.gl.glEnable(GL20.GL_BLEND);
        Gdx.gl.glBlendFunc(GL20.GL_SRC_ALPHA, GL20.GL_ONE_MINUS_SRC_ALPHA);
        shapes.begin(ShapeRenderer.ShapeType.Filled);
        shapes.setColor(0f, 0f, 0f, 0.85f);
        shapes.rect(x - BORDER * 2f, y - BORDER * 2f, w + BORDER * 4f, h + BORDER * 4f);
        shapes.setColor(0.14f, 0.03f, 0.03f, 0.96f);
        shapes.rect(x, y, w, h);
        shapes.setColor(0.72f, 0.14f, 0.10f, 1f);
        shapes.rect(x, y, w * MathUtils.clamp(fraction, 0f, 1f), h);
        // Phase ticks.
        shapes.setColor(0f, 0f, 0f, 0.7f);
        for (int i = 1; i < phaseCount; i++) {
            float tickX = x + w * (1f - i / (float) phaseCount);
            shapes.rect(tickX - 1f, y, 2f, h);
        }
        shapes.setColor(1f, 1f, 1f, 0.09f);
        shapes.rect(x, y + h * 0.62f, w * MathUtils.clamp(fraction, 0f, 1f), h * 0.20f);
        shapes.end();

        batch.begin();
        text.setScale(uiScale(scale));
        text.setColor(0.90f, 0.86f, 0.78f, 1f);
        text.drawLeading(batch, name, x, x + w, y + h + 26f * scale);
        if (phase > 0) {
            text.setColor(0.88f, 0.60f, 0.26f, 1f);
            text.drawTrailing(batch, Strings.get(Strings.PHASE) + " " + (phase + 1),
                    x, x + w, y + h + 26f * scale);
        }
        text.setColor(0.86f, 0.83f, 0.76f, 1f);
        text.setScale(1f);
        batch.end();
    }

    /** Short-lived message above the bars: pickups, weapon swaps, soul gains. */
    public void toast(String message, float alpha) {
        if (message == null || message.isEmpty()) return;
        int screenW = Gdx.graphics.getWidth();
        float scale = MathUtils.clamp(screenW / 960f, 0.75f, 2.0f);
        batch.begin();
        this.text.setScale(uiScale(scale));
        this.text.setColor(0.90f, 0.86f, 0.72f, MathUtils.clamp(alpha, 0f, 1f));
        this.text.drawLeading(batch, message, 26f * scale, screenW - 26f * scale,
                Gdx.graphics.getHeight() * 0.72f);
        this.text.setColor(0.86f, 0.83f, 0.76f, 1f);
        this.text.setScale(1f);
        batch.end();
    }

    /** The area name, faded in on arrival. */
    public void areaTitle(String name, float alpha) {
        if (name == null || name.isEmpty() || alpha <= 0f) return;
        int screenW = Gdx.graphics.getWidth();
        float scale = MathUtils.clamp(screenW / 960f, 0.9f, 2.4f);
        batch.begin();
        text.setScale(uiScale(scale) * 1.7f);
        text.setColor(0.92f, 0.88f, 0.74f, MathUtils.clamp(alpha, 0f, 1f));
        text.drawCentred(batch, name, screenW * 0.5f, Gdx.graphics.getHeight() * 0.80f);
        text.setColor(0.86f, 0.83f, 0.76f, 1f);
        text.setScale(1f);
        batch.end();
    }

    /** A one-line prompt near the bottom, for doors and pickups. */
    public void prompt(String message) {
        if (message == null || message.isEmpty()) return;
        int screenW = Gdx.graphics.getWidth();
        float scale = MathUtils.clamp(screenW / 960f, 0.85f, 2.0f);
        batch.begin();
        text.setScale(uiScale(scale));
        text.setColor(0.88f, 0.85f, 0.76f, 0.95f);
        text.drawCentred(batch, message, screenW * 0.5f, Gdx.graphics.getHeight() * 0.26f);
        text.setColor(0.86f, 0.83f, 0.76f, 1f);
        text.setScale(1f);
        batch.end();
    }

    /**
     * The quick slot: what the use button will spend, and how many are left.
     *
     * Under the bars rather than in a corner, because the one moment it has to
     * be readable is the moment you are deciding whether to drink, and that is
     * the moment your eyes are on the health bar.
     */
    public void quickSlot(String name, int count, float buffSeconds) {
        int screenH = Gdx.graphics.getHeight();
        int screenW = Gdx.graphics.getWidth();
        float scale = MathUtils.clamp(screenW / 960f, 0.75f, 2.2f);
        float h = BAR_HEIGHT * scale;
        float x = BAR_X * scale;
        float y = screenH - BAR_TOP * scale - h * 2f - BAR_GAP * scale * 2f - 20f * scale;

        batch.begin();
        text.setScale(uiScale(scale) * 0.9f);
        text.setColor(0.88f, 0.84f, 0.70f, 1f);
        text.draw(batch, name + "  x" + count, x, y);
        if (buffSeconds > 0f) {
            // Counts down, because the decision a resin creates is when to spend
            // the rest of it.
            text.setColor(0.95f, 0.62f, 0.24f, 1f);
            text.draw(batch, Strings.get(Strings.BUFF) + " "
                    + (int) Math.ceil(buffSeconds) + "s", x, y - 20f * scale);
        }
        text.setColor(0.86f, 0.83f, 0.76f, 1f);
        text.setScale(1f);
        batch.end();
    }

    /** Full-screen tint, used for the death fade. */
    public void overlay(float r, float g, float b, float alpha) {
        if (alpha <= 0f) return;
        Gdx.gl.glEnable(GL20.GL_BLEND);
        Gdx.gl.glBlendFunc(GL20.GL_SRC_ALPHA, GL20.GL_ONE_MINUS_SRC_ALPHA);
        shapes.begin(ShapeRenderer.ShapeType.Filled);
        shapes.setColor(r, g, b, MathUtils.clamp(alpha, 0f, 1f));
        shapes.rect(0f, 0f, Gdx.graphics.getWidth(), Gdx.graphics.getHeight());
        shapes.end();
    }

    /** Centred message, e.g. YOU DIED. */
    public void centreText(String message, float alpha, float scale) {
        if (alpha <= 0f) return;
        batch.begin();
        text.setScale(scale * 0.52f);
        text.setColor(0.72f, 0.10f, 0.09f, MathUtils.clamp(alpha, 0f, 1f));
        text.drawCentred(batch, message, Gdx.graphics.getWidth() * 0.5f,
                Gdx.graphics.getHeight() * 0.56f);
        text.setColor(0.86f, 0.83f, 0.76f, 1f);
        text.setScale(1f);
        batch.end();
    }

    @Override
    public void dispose() {
        shapes.dispose();
        batch.dispose();
        // The font belongs to the game, not to the Hud, and outlives this screen.
    }
}
