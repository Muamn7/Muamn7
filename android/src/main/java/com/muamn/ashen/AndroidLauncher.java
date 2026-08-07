package com.muamn.ashen;

import android.graphics.Color;
import android.graphics.Typeface;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.widget.FrameLayout;
import android.widget.TextView;

import com.badlogic.gdx.ApplicationLogger;
import com.badlogic.gdx.backends.android.AndroidApplication;
import com.badlogic.gdx.backends.android.AndroidApplicationConfiguration;

import java.io.PrintWriter;
import java.io.StringWriter;
import java.util.ArrayDeque;

/**
 * Entry point for the Android build.
 *
 * <h3>The boot log overlay</h3>
 * The game's own log is drawn on top of it by an Android {@link TextView} - a
 * plain view, laid out and composited by the platform, sharing nothing with
 * OpenGL. That is the entire point. When a phone shows a black screen there is
 * no console to read and no way to tell a game that never started from a game
 * that is running perfectly behind a surface that never reached the display.
 * These two paths fail independently, so whichever one is broken, the other
 * still speaks:
 *
 * <ul>
 *   <li>log text over the game - everything works
 *   <li>log text over a <b>dark blue</b> background - the window is drawing and
 *       the GL surface is not, and the log says how far the game got
 *   <li>nothing at all, pure black - the activity itself never drew
 * </ul>
 *
 * The blue comes from the root layout, which is visible only where the surface
 * has not punched its hole through the window. It is not decoration; it is the
 * answer to the second question.
 */
public class AndroidLauncher extends AndroidApplication {

    /** Set false once the render path is settled on real hardware. */
    private static final boolean SHOW_BOOT_LOG = true;
    /** How long the overlay stays up. Long enough to photograph. */
    private static final long BOOT_LOG_MILLIS = 40_000L;
    private static final int BOOT_LOG_LINES = 16;
    /** One log line, wrapped, must not be allowed to fill a phone screen. */
    private static final int BOOT_LOG_LINE_CHARS = 150;

    /**
     * libGDX's own boot chatter, which is not what the overlay is for.
     *
     * Its extension dump alone is a single log line that wraps to twenty on a
     * phone - enough to push every line that matters off the bottom of the
     * screen, which is exactly what happened the first time this shipped. The
     * renderer, vendor and version are logged by the game itself anyway.
     */
    private static final String[] MUTED_TAGS = {"AndroidGraphics", "AndroidInput"};

    private final ArrayDeque<String> log = new ArrayDeque<>();
    private final Handler ui = new Handler(Looper.getMainLooper());
    private TextView logView;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // A crash on the GL thread otherwise vanishes into logcat, which nobody
        // holding a phone can read. Keep the platform handler afterwards so the
        // process still dies rather than hanging half-alive.
        final Thread.UncaughtExceptionHandler previous =
                Thread.getDefaultUncaughtExceptionHandler();
        Thread.setDefaultUncaughtExceptionHandler((thread, error) -> {
            Log.e("Ashen", "uncaught on " + thread.getName(), error);
            append("CRASH on " + thread.getName() + ": " + stackOf(error));
            if (previous != null) previous.uncaughtException(thread, error);
        });

        AndroidApplicationConfiguration config = new AndroidApplicationConfiguration();
        config.useImmersiveMode = true;
        config.useAccelerometer = false;
        config.useCompass = false;
        config.useGyroscope = false;
        // 8888 with a 16-bit depth buffer, which is what every Android GPU can
        // actually give you.
        //
        // This used to ask for 5/6/5/0. It is the more period-accurate surface and
        // it is cheaper, but GLSurfaceView's config chooser demands an *exact*
        // channel match, and on a device whose EGL config list and window pixel
        // format do not line up on 565 the result is a window that composites to
        // black while the game happily runs behind it - audio, input and all. The
        // PS2 colour depth is produced by the shader's 5-bit dither anyway, so the
        // surface format was buying nothing and costing the whole picture.
        config.r = 8;
        config.g = 8;
        config.b = 8;
        config.a = 8;
        config.depth = 16;
        config.stencil = 0;
        config.numSamples = 0;

        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            getWindow().getAttributes().layoutInDisplayCutoutMode =
                    WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES;
        }

        if (!SHOW_BOOT_LOG) {
            initialize(new AshenGame(), config);
            return;
        }

        // initializeForView hands back the game's view instead of installing it,
        // which is the only way to get anything above it in the hierarchy.
        View gameView = initializeForView(new AshenGame(), config);
        setApplicationLogger(new OverlayLogger(getApplicationLogger()));

        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(0xFF001A33);   // seen only where the surface is not
        root.addView(gameView, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

        logView = new TextView(this);
        logView.setTextSize(TypedValue.COMPLEX_UNIT_SP, 8f);
        logView.setTextColor(0xFFBFE8BF);
        logView.setShadowLayer(2f, 1f, 1f, Color.BLACK);
        logView.setBackgroundColor(0x55000000);
        logView.setTypeface(Typeface.MONOSPACE);
        logView.setPadding(8, 8, 8, 8);
        // Not clickable, so every touch falls through to the game behind it.
        logView.setClickable(false);
        logView.setFocusable(false);
        // Anchored to the bottom: if the log ever outgrows the screen it is the
        // oldest lines that get clipped, and the newest - the ones that say where
        // the boot stopped - stay on the photograph.
        FrameLayout.LayoutParams params = new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        params.gravity = Gravity.BOTTOM | Gravity.START;
        root.addView(logView, params);

        setContentView(root);
        append("launcher ready - " + Build.MANUFACTURER + " " + Build.MODEL
                + ", android " + Build.VERSION.RELEASE + " (sdk " + Build.VERSION.SDK_INT + ")");
        ui.postDelayed(() -> {
            if (logView != null) logView.setVisibility(View.GONE);
        }, BOOT_LOG_MILLIS);
    }

    private static boolean muted(String tag) {
        for (String each : MUTED_TAGS) if (each.equals(tag)) return true;
        return false;
    }

    /** Adds a line to the overlay from any thread. */
    private void append(String line) {
        if (!SHOW_BOOT_LOG || line == null) return;
        final String trimmed = line.length() > BOOT_LOG_LINE_CHARS
                ? line.substring(0, BOOT_LOG_LINE_CHARS) + "..." : line;
        ui.post(() -> {
            log.addLast(trimmed);
            while (log.size() > BOOT_LOG_LINES) log.removeFirst();
            if (logView == null) return;
            StringBuilder text = new StringBuilder();
            for (String each : log) text.append(each).append('\n');
            logView.setText(text);
            // A crash is the one thing worth interrupting the countdown for.
            logView.setVisibility(View.VISIBLE);
        });
    }

    private static String stackOf(Throwable t) {
        StringWriter buffer = new StringWriter();
        t.printStackTrace(new PrintWriter(buffer));
        String[] lines = buffer.toString().split("\n");
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < Math.min(lines.length, 8); i++) {
            out.append(lines[i].trim()).append('\n');
        }
        return out.toString();
    }

    /** Mirrors everything the game logs onto the overlay, and into logcat. */
    private class OverlayLogger implements ApplicationLogger {

        private final ApplicationLogger delegate;

        OverlayLogger(ApplicationLogger delegate) {
            this.delegate = delegate;
        }

        @Override public void log(String tag, String message) {
            delegate.log(tag, message);
            if (!muted(tag)) append(tag + ": " + message);
        }

        @Override public void log(String tag, String message, Throwable exception) {
            delegate.log(tag, message, exception);
            if (!muted(tag)) append(tag + ": " + message + "\n" + stackOf(exception));
        }

        @Override public void error(String tag, String message) {
            delegate.error(tag, message);
            append("! " + tag + ": " + message);
        }

        @Override public void error(String tag, String message, Throwable exception) {
            delegate.error(tag, message, exception);
            append("! " + tag + ": " + message + "\n" + stackOf(exception));
        }

        @Override public void debug(String tag, String message) {
            delegate.debug(tag, message);
        }

        @Override public void debug(String tag, String message, Throwable exception) {
            delegate.debug(tag, message, exception);
        }
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus) hideSystemBars();
    }

    private void hideSystemBars() {
        View decor = getWindow().getDecorView();
        decor.setSystemUiVisibility(View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                | View.SYSTEM_UI_FLAG_FULLSCREEN
                | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY);
    }
}
