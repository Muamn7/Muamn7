package com.muamn.ashen.ui;

import com.badlogic.gdx.Gdx;
import com.badlogic.gdx.graphics.GL20;
import com.badlogic.gdx.graphics.g2d.SpriteBatch;
import com.badlogic.gdx.graphics.glutils.ShapeRenderer;
import com.badlogic.gdx.math.MathUtils;
import com.badlogic.gdx.utils.Array;
import com.badlogic.gdx.utils.Disposable;

import com.muamn.ashen.text.Strings;
import com.muamn.ashen.text.Text;

/**
 * The panel someone's words appear in.
 *
 * Wrapping is done here, on the unshaped string, by measuring each candidate
 * line with the real font. Wrapping after shaping would be wrong twice over:
 * the presentation forms are already reordered for the renderer, so a break
 * would land in the middle of a reversed run, and the joins either side of the
 * break would be for neighbours that are no longer adjacent.
 */
public class DialogueBox implements Disposable {

    private final ShapeRenderer shapes = new ShapeRenderer();
    private final SpriteBatch batch = new SpriteBatch();
    private final Text text;
    private final Array<String> wrapped = new Array<>();

    public DialogueBox(Text text) {
        this.text = text;
    }

    private boolean open;
    private String speaker = "";
    private String body = "";
    /** Characters revealed so far. Text arrives at a readable pace, not at once. */
    private float revealed;
    private String hint = "[E]";

    /** Characters per second. Fast enough not to be a wait, slow enough to read to. */
    private static final float REVEAL_SPEED = 52f;

    public boolean isOpen() {
        return open;
    }

    /** Shows a line. Calling it again replaces what is on screen. */
    public void show(String speaker, String line, String hint) {
        this.open = true;
        this.speaker = speaker == null ? "" : speaker;
        this.body = line == null ? "" : line;
        this.hint = hint == null ? "" : hint;
        this.revealed = 0f;
    }

    public void close() {
        open = false;
        body = "";
        revealed = 0f;
    }

    public void update(float dt) {
        if (!open) return;
        revealed = Math.min(body.length(), revealed + REVEAL_SPEED * dt);
    }

    /** True once the whole line is on screen. */
    public boolean isFullyRevealed() {
        return revealed >= body.length();
    }

    /**
     * Skips the reveal.
     *
     * The first press of the advance button finishes the line instead of moving
     * past it, so a player who reads faster than the animation is never punished
     * for pressing on time.
     */
    public void revealAll() {
        revealed = body.length();
    }

    public void render() {
        if (!open) return;

        int screenW = Gdx.graphics.getWidth();
        int screenH = Gdx.graphics.getHeight();
        float scale = MathUtils.clamp(screenW / 960f, 0.85f, 2.0f);

        float margin = 40f * scale;
        float boxW = screenW - margin * 2f;
        float lineH = 22f * scale;

        float fontScale = MathUtils.clamp(scale * 0.5f, 0.34f, 1f);
        text.setScale(fontScale);
        wrap(body.substring(0, (int) revealed), boxW - 32f * scale);
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

        float left = margin + 16f * scale;
        float right = margin + boxW - 16f * scale;

        batch.begin();
        text.setColor(0.92f, 0.82f, 0.56f, 1f);
        text.drawLeading(batch, speaker, left, right, boxY + boxH - 14f * scale);

        text.setColor(0.88f, 0.86f, 0.80f, 1f);
        for (int i = 0; i < wrapped.size; i++) {
            text.drawLeading(batch, wrapped.get(i), left, right,
                    boxY + boxH - 44f * scale - i * lineH);
        }

        // The prompt only appears once there is nothing left to reveal, so it
        // never invites a press that would skip words the player has not seen.
        if (isFullyRevealed() && !hint.isEmpty()) {
            text.setColor(0.70f, 0.66f, 0.56f, 1f);
            text.drawTrailing(batch, hint, left, right, boxY + 22f * scale);
        }
        text.setColor(0.86f, 0.83f, 0.76f, 1f);
        text.setScale(1f);
        batch.end();
    }

    /**
     * Greedy word wrap to a pixel width, measured with the font that will draw
     * it. A character count would be close enough for a monospaced ASCII font
     * and badly wrong for a proportional Arabic one.
     */
    private void wrap(String source, float maxWidth) {
        wrapped.clear();
        if (source.isEmpty()) {
            wrapped.add("");
            return;
        }
        StringBuilder line = new StringBuilder();
        for (String word : source.split(" ")) {
            String candidate = line.length() == 0 ? word : line + " " + word;
            if (line.length() > 0 && text.width(candidate) > maxWidth) {
                wrapped.add(line.toString());
                line.setLength(0);
                line.append(word);
            } else {
                line.setLength(0);
                line.append(candidate);
            }
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
    }
}
