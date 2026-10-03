package com.muamn.kazzab;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ApplicationInfo;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.speech.tts.TextToSpeech;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;

/**
 * The whole Android app: a WebView showing the game from the APK's assets.
 *
 * <h3>Why the assets are served over a fake https origin</h3>
 * The page is loaded from {@code https://appassets.androidplatform.net/} - a
 * domain reserved for exactly this - and every request to it is answered here
 * from the assets. A {@code file://} page has a null origin: localStorage, which
 * holds the player's name and the key that gets a dropped phone its seat back,
 * is unreliable there, and so is everything that wants a secure context.
 * Requests to any other host - the PeerJS broker - go to the network as usual.
 *
 * <h3>The bridge</h3>
 * An Android WebView has no speech engine and no share sheet, so the page gets
 * them from {@link Bridge} as {@code window.KazzabAndroid}.
 */
public class MainActivity extends Activity {

    private static final String HOST = "appassets.androidplatform.net";
    private static final String HOME = "https://" + HOST + "/index.html";

    private WebView web;
    private TextToSpeech tts;
    private volatile boolean ttsReady;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        // The table must not go dark mid-round while someone thinks.
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);

        if ((getApplicationInfo().flags & ApplicationInfo.FLAG_DEBUGGABLE) != 0) {
            // chrome://inspect on a computer, for the debug APK only.
            WebView.setWebContentsDebuggingEnabled(true);
        }

        web = new WebView(this);
        web.setBackgroundColor(0xFF0B1F18);
        web.setFitsSystemWindows(true);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        // The cards are laid out to the pixel; the system font size would
        // push the hand off the bottom of the screen.
        s.setTextZoom(100);

        web.setWebViewClient(new WebViewClient() {
            @Override
            public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                return serveAsset(request.getUrl());
            }

            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                if (HOST.equals(uri.getHost())) return false;
                // Any other link opens in the browser rather than inside the game.
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, uri));
                } catch (ActivityNotFoundException ignored) {
                    // Nothing can open it; stay put.
                }
                return true;
            }
        });
        web.setWebChromeClient(new WebChromeClient());
        web.addJavascriptInterface(new Bridge(), "KazzabAndroid");
        setContentView(web);

        tts = new TextToSpeech(this, status -> {
            if (status != TextToSpeech.SUCCESS) return;
            int result = tts.setLanguage(Locale.forLanguageTag("ar"));
            ttsReady = result != TextToSpeech.LANG_MISSING_DATA && result != TextToSpeech.LANG_NOT_SUPPORTED;
        });

        if (state == null || web.restoreState(state) == null) web.loadUrl(HOME);
    }

    /** Answers requests to the app's own origin from the assets; anything else goes to the network. */
    private WebResourceResponse serveAsset(Uri uri) {
        if (!HOST.equals(uri.getHost())) return null;
        String path = uri.getPath();
        if (path == null || path.isEmpty() || "/".equals(path)) path = "/index.html";
        String name = path.substring(1);
        Map<String, String> headers = new HashMap<>();
        headers.put("Cache-Control", "no-cache");
        try {
            InputStream in = getAssets().open(name);
            String mime = mimeOf(name);
            String encoding = mime.startsWith("text/") || mime.endsWith("json") ? "UTF-8" : null;
            return new WebResourceResponse(mime, encoding, 200, "OK", headers, in);
        } catch (IOException e) {
            return new WebResourceResponse("text/plain", "UTF-8", 404, "Not Found", headers,
                    new ByteArrayInputStream(new byte[0]));
        }
    }

    private static String mimeOf(String name) {
        int dot = name.lastIndexOf('.');
        String ext = dot < 0 ? "" : name.substring(dot + 1).toLowerCase(Locale.ROOT);
        switch (ext) {
            case "html": return "text/html";
            case "js": return "text/javascript";
            case "css": return "text/css";
            case "png": return "image/png";
            case "svg": return "image/svg+xml";
            case "woff2": return "font/woff2";
            case "json":
            case "webmanifest": return "application/json";
            case "txt": return "text/plain";
            default: return "application/octet-stream";
        }
    }

    /**
     * Back walks the page's own history first: the game keeps one entry there
     * so that back opens its menu instead of leaving a room by accident.
     */
    @Override
    @SuppressWarnings("deprecation")
    public void onBackPressed() {
        if (web != null && web.canGoBack()) {
            web.goBack();
            return;
        }
        new AlertDialog.Builder(this)
                .setTitle(R.string.exit_title)
                .setMessage(R.string.exit_message)
                .setPositiveButton(R.string.exit_yes, (dialog, which) -> finish())
                .setNegativeButton(R.string.exit_no, null)
                .show();
    }

    @Override
    protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        if (web != null) web.saveState(out);
    }

    @Override
    protected void onDestroy() {
        if (tts != null) tts.shutdown();
        if (web != null) {
            web.removeJavascriptInterface("KazzabAndroid");
            web.destroy();
            web = null;
        }
        super.onDestroy();
    }

    /** window.KazzabAndroid in the page. Public, so the WebView can reach its methods. */
    public final class Bridge {

        @JavascriptInterface
        public void share(String text) {
            runOnUiThread(() -> {
                Intent send = new Intent(Intent.ACTION_SEND);
                send.setType("text/plain");
                send.putExtra(Intent.EXTRA_TEXT, text);
                try {
                    startActivity(Intent.createChooser(send, getString(R.string.share_title)));
                } catch (ActivityNotFoundException ignored) {
                    // No app can share text; the code is still on screen.
                }
            });
        }

        @JavascriptInterface
        public boolean canSpeak() {
            return ttsReady;
        }

        @JavascriptInterface
        public void speak(String text) {
            if (ttsReady && text != null) tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, "kazzab");
        }

        @JavascriptInterface
        @SuppressWarnings("deprecation")
        public void vibrate(int ms) {
            Vibrator v = (Vibrator) getSystemService(Context.VIBRATOR_SERVICE);
            if (v == null || !v.hasVibrator()) return;
            long duration = Math.max(1, Math.min(ms, 1000));
            if (Build.VERSION.SDK_INT >= 26) {
                v.vibrate(VibrationEffect.createOneShot(duration, VibrationEffect.DEFAULT_AMPLITUDE));
            } else {
                v.vibrate(duration);
            }
        }
    }
}
