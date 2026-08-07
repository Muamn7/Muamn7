package com.muamn.ashen.render;

import com.badlogic.gdx.Gdx;
import com.badlogic.gdx.graphics.Color;
import com.badlogic.gdx.graphics.GL20;
import com.badlogic.gdx.graphics.Pixmap;
import com.badlogic.gdx.graphics.Texture;
import com.badlogic.gdx.graphics.g2d.SpriteBatch;
import com.badlogic.gdx.graphics.glutils.ShapeRenderer;
import com.badlogic.gdx.utils.Disposable;

import com.muamn.ashen.Config;

/**
 * Three squares in the top corner, each reaching the screen by a different road.
 *
 * A phone showed the green one and nothing else - no game, no HUD, no touch
 * controls - while the log reported a healthy render loop at 144fps with no GL
 * error. Green is a scissored clear: it is the only drawing in this game that
 * touches no shader, no vertex and no matrix. So the fault is somewhere in the
 * part of the pipeline that green skips, and that part is large.
 *
 * These narrow it:
 *
 * <ul>
 *   <li><b>green</b> - scissored clear. No shader, no geometry, no matrix.
 *   <li><b>blue</b> - a ShapeRenderer rectangle. libGDX's own shader and its own
 *       projection matrix, with vertex colours and no texture.
 *   <li><b>white</b> - a SpriteBatch quad from a 1x1 texture. The same road the
 *       upscale blit and every glyph in the game travel.
 * </ul>
 *
 * Blue missing means shader draws are dead, and the game's own renderer is not
 * the reason. Blue present and white missing puts it in texturing. All three
 * present means the draw path works and the fault is in what the game feeds it.
 */
public final class GlProbe implements Disposable {

    private static final float SIZE_FRACTION = 1f / 10f;

    private ShapeRenderer shapes;
    private SpriteBatch batch;
    private Texture white;
    private boolean broken;

    /** The scissored clear. Deliberately static and dependency-free. */
    public static void clearSquare(int screenWidth, int screenHeight,
                                   int slot, float r, float g, float b) {
        int size = Math.max(24, (int) (Math.min(screenWidth, screenHeight) * SIZE_FRACTION));
        int margin = size / 4;
        int x = screenWidth - (size + margin) * (slot + 1);
        int y = screenHeight - size - margin;
        Gdx.gl.glEnable(GL20.GL_SCISSOR_TEST);
        Gdx.gl.glScissor(x, y, size, size);
        Gdx.gl.glClearColor(r, g, b, 1f);
        Gdx.gl.glClear(GL20.GL_COLOR_BUFFER_BIT);
        Gdx.gl.glDisable(GL20.GL_SCISSOR_TEST);
    }

    /** Draws all three, newest road last so nothing hides an earlier answer. */
    public void draw() {
        int sw = Gdx.graphics.getWidth();
        int sh = Gdx.graphics.getHeight();
        clearSquare(sw, sh, 0, 0.10f, 0.95f, 0.25f);
        if (broken) return;
        try {
            if (shapes == null) create();

            int size = Math.max(24, (int) (Math.min(sw, sh) * SIZE_FRACTION));
            int margin = size / 4;
            float y = sh - size - margin;

            shapes.getProjectionMatrix().setToOrtho2D(0f, 0f, sw, sh);
            shapes.begin(ShapeRenderer.ShapeType.Filled);
            shapes.setColor(0.15f, 0.35f, 1f, 1f);
            shapes.rect(sw - (size + margin) * 2f, y, size, size);
            shapes.end();

            batch.getProjectionMatrix().setToOrtho2D(0f, 0f, sw, sh);
            batch.disableBlending();
            batch.begin();
            batch.setColor(Color.WHITE);
            batch.draw(white, sw - (size + margin) * 3f, y, size, size);
            batch.end();
            batch.enableBlending();
        } catch (Throwable t) {
            // The probe must never be the thing that takes the game down.
            broken = true;
            Gdx.app.error("Ashen", "probe squares failed", new Exception(t));
        }
    }

    private void create() {
        shapes = new ShapeRenderer();
        batch = new SpriteBatch();
        Pixmap px = new Pixmap(1, 1, Pixmap.Format.RGBA8888);
        px.setColor(Color.WHITE);
        px.fill();
        white = new Texture(px);
        px.dispose();
    }

    /**
     * Writes opaque alpha over the whole frame, touching no colour.
     *
     * The window surface has an alpha channel - the device reported
     * {@code framebuffer (8,8,8,8)} - and a compositor that honours it will show
     * whatever is behind wherever the frame ended up transparent. Since the one
     * thing that did reach the screen was a clear, which writes alpha 1, and
     * everything drawn with blending on did not, this is worth ruling out rather
     * than reasoning about. It costs one full-screen write of a single channel.
     */
    public static void sealAlpha() {
        Gdx.gl.glDisable(GL20.GL_SCISSOR_TEST);
        Gdx.gl.glColorMask(false, false, false, true);
        Gdx.gl.glClearColor(0f, 0f, 0f, 1f);
        Gdx.gl.glClear(GL20.GL_COLOR_BUFFER_BIT);
        Gdx.gl.glColorMask(true, true, true, true);
    }

    /** True when the diagnostic build is asking these questions at all. */
    public static boolean enabled() {
        return Config.GL_PROBE;
    }

    @Override
    public void dispose() {
        if (shapes != null) shapes.dispose();
        if (batch != null) batch.dispose();
        if (white != null) white.dispose();
    }
}
