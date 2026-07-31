package com.muamn.ashen.ui;

import com.badlogic.gdx.Gdx;
import com.badlogic.gdx.graphics.GL20;
import com.badlogic.gdx.graphics.g2d.BitmapFont;
import com.badlogic.gdx.graphics.g2d.SpriteBatch;
import com.badlogic.gdx.graphics.glutils.ShapeRenderer;
import com.badlogic.gdx.math.MathUtils;
import com.badlogic.gdx.utils.Disposable;

import com.muamn.ashen.entity.Stats;

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
    private final BitmapFont font = new BitmapFont();

    private float ghostHealth = 1f;
    private float ghostStamina = 1f;

    /** Set true to draw frame timing and player state. */
    public boolean showDebug;
    private String debugLine = "";

    public Hud() {
        font.setColor(0.86f, 0.83f, 0.76f, 1f);
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
        font.getData().setScale(Math.max(1f, scale * 0.9f));
        String souls = Long.toString(stats.souls);
        font.draw(batch, souls, screenW - 40f * scale - souls.length() * 9f * scale, 42f * scale);
        if (showDebug && debugLine != null) {
            font.getData().setScale(1f);
            font.draw(batch, debugLine, x, yStamina - 18f);
        }
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

    /** Draws only the debug readout, for screens that have no player stats. */
    public void renderDebugOnly() {
        if (debugLine == null || debugLine.isEmpty()) return;
        batch.begin();
        font.getData().setScale(1f);
        font.draw(batch, debugLine, 14f, Gdx.graphics.getHeight() - 14f);
        batch.end();
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
        font.getData().setScale(Math.max(1f, scale * 0.85f));
        font.draw(batch, name, x, y + h + 20f * scale);
        font.getData().setScale(1f);
        batch.end();
    }

    /** Short-lived message above the bars: pickups, weapon swaps, soul gains. */
    public void toast(String text, float alpha) {
        if (text == null || text.isEmpty()) return;
        int screenW = Gdx.graphics.getWidth();
        float scale = MathUtils.clamp(screenW / 960f, 0.75f, 2.0f);
        batch.begin();
        font.getData().setScale(Math.max(1f, scale));
        font.setColor(0.90f, 0.86f, 0.72f, MathUtils.clamp(alpha, 0f, 1f));
        font.draw(batch, text, 26f * scale, Gdx.graphics.getHeight() * 0.72f);
        font.setColor(0.86f, 0.83f, 0.76f, 1f);
        font.getData().setScale(1f);
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
    public void centreText(String text, float alpha, float scale) {
        if (alpha <= 0f) return;
        batch.begin();
        font.getData().setScale(scale);
        font.setColor(0.72f, 0.10f, 0.09f, MathUtils.clamp(alpha, 0f, 1f));
        float w = text.length() * 9f * scale;
        font.draw(batch, text, (Gdx.graphics.getWidth() - w) * 0.5f, Gdx.graphics.getHeight() * 0.56f);
        font.setColor(0.86f, 0.83f, 0.76f, 1f);
        font.getData().setScale(1f);
        batch.end();
    }

    @Override
    public void dispose() {
        shapes.dispose();
        batch.dispose();
        font.dispose();
    }
}
