package com.muamn.ashen.screens;

import com.badlogic.gdx.Gdx;
import com.badlogic.gdx.Screen;
import com.badlogic.gdx.graphics.g2d.BitmapFont;
import com.badlogic.gdx.graphics.g2d.SpriteBatch;
import com.badlogic.gdx.utils.ScreenUtils;

import java.io.PrintWriter;
import java.io.StringWriter;

/**
 * What the game shows instead of dying.
 *
 * On a phone there is no console. If something throws, the alternative to this
 * screen is a black rectangle and a player who cannot tell a crash from a bug
 * from a dead battery - which is exactly the report this screen exists to
 * prevent. The background is deliberately dark red: even if the font, the
 * texture upload or the whole 2D path is what broke, a red screen still says
 * "the game is running and it has failed" rather than nothing at all.
 *
 * Everything here is built from libGDX's own bundled font, with no asset, no
 * shader and no framebuffer of ours involved, so it has the best chance of
 * working when the rest does not.
 */
public class ErrorScreen implements Screen {

    private static final int MAX_LINES = 18;

    private final String[] lines;
    private SpriteBatch batch;
    private BitmapFont font;
    private boolean usable = true;

    public ErrorScreen(String where, Throwable error) {
        lines = describe(where, error);
        for (String line : lines) Gdx.app.error("Ashen", line);
        try {
            batch = new SpriteBatch();
            font = new BitmapFont();   // bundled inside gdx.jar; needs no asset
            font.setColor(1f, 0.88f, 0.84f, 1f);
        } catch (Throwable t) {
            // If even this fails, the red background is the whole message.
            usable = false;
        }
    }

    /** The exception, plus enough of the stack to name the file that broke. */
    private static String[] describe(String where, Throwable error) {
        StringWriter buffer = new StringWriter();
        error.printStackTrace(new PrintWriter(buffer));

        java.util.ArrayList<String> out = new java.util.ArrayList<>();
        out.add("ASHEN stopped in " + where + "()");
        out.add("");
        for (String line : buffer.toString().split("\n")) {
            if (out.size() >= MAX_LINES) break;
            out.add(line.replace('\t', ' ').trim());
        }
        out.add("");
        out.add("Screenshot this and send it - it says exactly what broke.");
        return out.toArray(new String[0]);
    }

    @Override
    public void render(float delta) {
        ScreenUtils.clear(0.22f, 0.04f, 0.04f, 1f);
        if (!usable) return;
        try {
            batch.getProjectionMatrix().setToOrtho2D(0f, 0f,
                    Gdx.graphics.getWidth(), Gdx.graphics.getHeight());
            float scale = Math.max(1f, Gdx.graphics.getWidth() / 640f);
            font.getData().setScale(scale);
            float lineHeight = font.getLineHeight();
            float y = Gdx.graphics.getHeight() - 20f;
            batch.begin();
            for (String line : lines) {
                font.draw(batch, line, 16f, y);
                y -= lineHeight;
            }
            batch.end();
        } catch (Throwable t) {
            usable = false;
        }
    }

    @Override public void resize(int width, int height) { }
    @Override public void show() { }
    @Override public void hide() { }
    @Override public void pause() { }
    @Override public void resume() { }

    @Override
    public void dispose() {
        if (batch != null) batch.dispose();
        if (font != null) font.dispose();
    }
}
