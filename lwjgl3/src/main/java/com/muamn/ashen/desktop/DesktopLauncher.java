package com.muamn.ashen.desktop;

import com.badlogic.gdx.ApplicationListener;
import com.badlogic.gdx.Gdx;
import com.badlogic.gdx.backends.lwjgl3.Lwjgl3Application;
import com.badlogic.gdx.backends.lwjgl3.Lwjgl3ApplicationConfiguration;
import com.badlogic.gdx.files.FileHandle;
import com.badlogic.gdx.graphics.Pixmap;
import com.badlogic.gdx.graphics.PixmapIO;

import java.util.zip.Deflater;

import com.muamn.ashen.AshenGame;

/**
 * Desktop launcher, used for development and for automated smoke tests.
 *
 * Switches (all optional, all {@code -Dashen.*}):
 * <pre>
 *   -Dashen.touch=true          draw the phone controls on desktop
 *   -Dashen.debug=true          show the frame/state readout
 *   -Dashen.screenshot=PATH     write a PNG once the world has settled
 *   -Dashen.exitAfter=SECONDS   quit automatically, for CI
 * </pre>
 */
public class DesktopLauncher {

    public static void main(String[] args) {
        Lwjgl3ApplicationConfiguration config = new Lwjgl3ApplicationConfiguration();
        config.setTitle("ASHEN");
        config.setWindowedMode(1280, 720);
        config.setForegroundFPS(60);
        config.useVsync(true);
        // 16-bit-ish colour and a depth buffer; no MSAA, which would fight the
        // deliberately aliased look.
        config.setBackBufferConfig(8, 8, 8, 8, 16, 0, 0);
        config.setWindowIcon("icon.png");

        boolean touch = Boolean.getBoolean("ashen.touch");
        boolean debug = Boolean.getBoolean("ashen.debug");
        String screenshot = System.getProperty("ashen.screenshot");
        float exitAfter = Float.parseFloat(System.getProperty("ashen.exitAfter", "0"));

        float screenshotAt = Float.parseFloat(System.getProperty("ashen.screenshotAt", "0.4"));

        AshenGame game = new AshenGame(touch, debug);
        String camDist = System.getProperty("ashen.camDist");
        if (camDist != null) game.cameraDistance = Float.parseFloat(camDist);
        game.cameraYawOffset = Float.parseFloat(System.getProperty("ashen.camYaw", "0"));
        game.autopilot = Boolean.getBoolean("ashen.autopilot");
        game.viewModel = System.getProperty("ashen.viewModel");
        game.freezeAnimations = Boolean.getBoolean("ashen.freezeAnim");
        game.openMenuOnStart = Boolean.getBoolean("ashen.menu");
        String menuPage = System.getProperty("ashen.menuPage");
        if (menuPage != null) {
            game.openMenuOnStart = true;
            game.menuPage = com.muamn.ashen.ui.BonfireMenu.Page.valueOf(
                    menuPage.toUpperCase());
        }
        ApplicationListener listener = (screenshot != null || exitAfter > 0f)
                ? new HarnessListener(game, screenshot, screenshotAt, exitAfter)
                : game;

        new Lwjgl3Application(listener, config);
    }

    /**
     * Wraps the game so CI can run it for a few seconds, capture a frame and
     * exit with a non-zero status if anything threw on the way.
     */
    private static class HarnessListener implements ApplicationListener {

        private final AshenGame game;
        private final String screenshotPath;
        private final float screenshotAt;
        private final float exitAfter;

        private float elapsed;
        private int frames;
        private boolean captured;

        HarnessListener(AshenGame game, String screenshotPath, float screenshotAt, float exitAfter) {
            this.game = game;
            this.screenshotPath = screenshotPath;
            this.screenshotAt = screenshotAt;
            this.exitAfter = exitAfter;
        }

        @Override public void create() {
            game.create();
        }

        @Override public void resize(int width, int height) {
            game.resize(width, height);
        }

        @Override public void render() {
            game.render();
            elapsed += Gdx.graphics.getDeltaTime();
            frames++;

            // Wait for the requested moment, and for at least a few frames so the
            // first-frame texture uploads have landed.
            if (screenshotPath != null && !captured && frames >= 10 && elapsed >= screenshotAt) {
                capture(screenshotPath);
                captured = true;
            }
            if (exitAfter > 0f && elapsed >= exitAfter) {
                Gdx.app.log("Ashen", "smoke test finished: " + frames + " frames in "
                        + String.format("%.2f", elapsed) + "s ("
                        + Math.round(frames / Math.max(elapsed, 0.001f)) + " fps avg)");
                Gdx.app.exit();
            }
        }

        private void capture(String path) {
            Pixmap pixmap = Pixmap.createFromFrameBuffer(0, 0,
                    Gdx.graphics.getBackBufferWidth(), Gdx.graphics.getBackBufferHeight());
            FileHandle file = Gdx.files.absolute(path);
            file.parent().mkdirs();
            // GL hands back bottom-up rows; PNG expects top-down.
            PixmapIO.writePNG(file, pixmap, Deflater.DEFAULT_COMPRESSION, true);
            pixmap.dispose();
            Gdx.app.log("Ashen", "screenshot written to " + path);
        }

        @Override public void pause() {
            game.pause();
        }

        @Override public void resume() {
            game.resume();
        }

        @Override public void dispose() {
            game.dispose();
        }
    }
}
