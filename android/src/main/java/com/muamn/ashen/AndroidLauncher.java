package com.muamn.ashen;

import android.os.Build;
import android.os.Bundle;
import android.util.Log;
import android.view.View;
import android.view.WindowManager;

import com.badlogic.gdx.backends.android.AndroidApplication;
import com.badlogic.gdx.backends.android.AndroidApplicationConfiguration;

/** Entry point for the Android build. */
public class AndroidLauncher extends AndroidApplication {

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

        initialize(new AshenGame(), config);
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
