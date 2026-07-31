package com.muamn.ashen.ui;

import com.badlogic.gdx.Gdx;
import com.badlogic.gdx.graphics.GL20;
import com.badlogic.gdx.graphics.g2d.BitmapFont;
import com.badlogic.gdx.graphics.g2d.SpriteBatch;
import com.badlogic.gdx.graphics.glutils.ShapeRenderer;
import com.badlogic.gdx.math.MathUtils;
import com.badlogic.gdx.utils.Array;
import com.badlogic.gdx.utils.Disposable;

/**
 * The panel someone's words appear in.
 *
 * Text is wrapped here rather than by the font's own wrapping, because the
 * built-in bitmap font is fixed enough that a character count is accurate and
 * the wrap has to survive being handed an Arabic string it cannot render.
 * Labels stay English for now; the Arabic font and the RTL layout are Part 4.
 */
public class DialogueBox implements Disposable {

    private final ShapeRenderer shapes = new ShapeRenderer();
    private final SpriteBatch batch = new SpriteBatch();
    private final BitmapFont font = new BitmapFont();
    private final Array<String> wrapped = new Array<>();

    private boolean open;
    private String speaker = "";
    private String text = "";
    /** Characters revealed so far. Text arrives at a readable pace, not at once. */
    private float revealed;
    private String hint = "[E]";

    /** Characters per second. Fast enough not to be a wait, slow enough to read to. */
    private static final float REVEAL_SPEED = 52f;

    public boolean isOpen() {
        return open;
    }

    /** Shows a line. Calling it again replaces what is on screen. */
    public void show(String speaker, String text, String hint) {
        this.open = true;
        this.speaker = speaker == null ? "" : speaker;
        this.text = text == null ? "" : text;
        this.hint = hint == null ? "" : hint;
        this.revealed = 0f;
    }

    public void close() {
        open = false;
        text = "";
        revealed = 0f;
    }

    public void update(float dt) {
        if (!open) return;
        revealed = Math.min(text.length(), revealed + REVEAL_SPEED * dt);
    }

    /** True once the whole line is on screen. */
    public boolean isFullyRevealed() {
        return revealed >= text.length();
    }

    /**
     * Skips the reveal.
     *
     * The first press of the advance button finishes the line instead of moving
     * past it, so a player who reads faster than the animation is never punished
     * for pressing on time.
     */
    public void revealAll() {
        revealed = text.length();
    }

    public void render() {
        if (!open) return;

        int screenW = Gdx.graphics.getWidth();
        int screenH = Gdx.graphics.getHeight();
        float scale = MathUtils.clamp(screenW / 960f, 0.85f, 2.0f);

        float margin = 40f * scale;
        float boxW = screenW - margin * 2f;
        float lineH = 22f * scale;

        int columns = Math.max(20, (int) (boxW / (9.6f * scale)));
        wrap(text.substring(0, (int) revealed), columns);
        float boxH = lineH * Math.max(1, wrapped.size) + 62f * scale;
        float boxY = screenH * 0.06f;

        Gdx.gl.glEnable(GL20.GL_BLEND);
        Gdx.gl.glBlendFunc(GL20.GL_SRC_ALPHA, GL20.GL_ONE_MINUS_SRC_ALPHA);

        shapes.getProjectionMatrix().setToOrtho2D(0f, 0f, screenW, screenH);
        batch.getProjectionMatrix().setToOrtho2D(0f, 0f, screenW, screenH);

        shapes.begin(ShapeRenderer.ShapeType.Filled);
        shapes.setColor(0.05f, 0.045f, 0.04f, 0.92f);
        shapes.rect(margin, boxY, boxW, boxH);
        shapes.end();

        shapes.begin(ShapeRenderer.ShapeType.Line);
        shapes.setColor(0.52f, 0.45f, 0.30f, 0.85f);
        shapes.rect(margin, boxY, boxW, boxH);
        shapes.end();

        batch.begin();
        font.getData().setScale(scale);
        font.setColor(0.92f, 0.82f, 0.56f, 1f);
        font.draw(batch, speaker, margin + 16f * scale, boxY + boxH - 14f * scale);

        font.setColor(0.88f, 0.86f, 0.80f, 1f);
        for (int i = 0; i < wrapped.size; i++) {
            font.draw(batch, wrapped.get(i), margin + 16f * scale,
                    boxY + boxH - 44f * scale - i * lineH);
        }

        // The prompt only appears once there is nothing left to reveal, so it
        // never invites a press that would skip words the player has not seen.
        if (isFullyRevealed() && !hint.isEmpty()) {
            font.setColor(0.70f, 0.66f, 0.56f, 1f);
            font.draw(batch, hint, margin + boxW - 16f * scale - hint.length() * 9.6f * scale,
                    boxY + 22f * scale);
        }
        font.setColor(0.86f, 0.83f, 0.76f, 1f);
        font.getData().setScale(1f);
        batch.end();
    }

    /** Greedy word wrap into {@code columns} characters. */
    private void wrap(String source, int columns) {
        wrapped.clear();
        if (source.isEmpty()) {
            wrapped.add("");
            return;
        }
        StringBuilder line = new StringBuilder();
        for (String word : source.split(" ")) {
            if (line.length() > 0 && line.length() + 1 + word.length() > columns) {
                wrapped.add(line.toString());
                line.setLength(0);
            }
            if (line.length() > 0) line.append(' ');
            line.append(word);
        }
        wrapped.add(line.toString());
    }

    public void resize(int width, int height) {
        shapes.getProjectionMatrix().setToOrtho2D(0f, 0f, width, height);
        batch.getProjectionMatrix().setToOrtho2D(0f, 0f, width, height);
    }

    @Override
    public void dispose() {
        shapes.dispose();
        batch.dispose();
        font.dispose();
    }
}
