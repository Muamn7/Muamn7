package com.muamn.ashen.render;

import com.badlogic.gdx.Gdx;
import com.badlogic.gdx.graphics.Camera;
import com.badlogic.gdx.graphics.GL20;
import com.badlogic.gdx.graphics.Pixmap;
import com.badlogic.gdx.graphics.Texture;
import com.badlogic.gdx.graphics.g2d.SpriteBatch;
import com.badlogic.gdx.graphics.g2d.TextureRegion;
import com.badlogic.gdx.graphics.g3d.ModelBatch;
import com.badlogic.gdx.graphics.g3d.ModelInstance;
import com.badlogic.gdx.graphics.g3d.Renderable;
import com.badlogic.gdx.graphics.g3d.Shader;
import com.badlogic.gdx.graphics.g3d.utils.ShaderProvider;
import com.badlogic.gdx.graphics.glutils.FrameBuffer;
import com.badlogic.gdx.utils.Disposable;
import com.badlogic.gdx.utils.ScreenUtils;

import com.muamn.ashen.Config;

/**
 * Draws the 3D scene into a small offscreen buffer and point-upscales it to the
 * display. The low internal resolution is what makes the dithering, the chunky
 * texel grid and the vertex jitter read as a PS2 image instead of noise, and it
 * is also why the game holds 60fps on weak phone GPUs - fragment cost is fixed
 * no matter how many pixels the panel has.
 */
public class RetroRenderer implements Disposable {

    private final RetroShader.Environment environment = new RetroShader.Environment();
    private final RetroShader shader;
    private final ModelBatch modelBatch;
    private final SpriteBatch blit;

    /**
     * Colour formats to try for the offscreen buffer, best first.
     *
     * RGBA8888 is the one format GLES2 and desktop GL both guarantee is
     * colour-renderable. RGB888 is not on that list, and a driver is within its
     * rights to refuse it - which on a phone shows up as a game that runs, plays
     * its sounds and draws nothing.
     */
    private static final Pixmap.Format[] FBO_FORMATS = {
            Pixmap.Format.RGBA8888, Pixmap.Format.RGB565, Pixmap.Format.RGB888,
    };

    private FrameBuffer fbo;
    private TextureRegion fboRegion;
    private Pixmap.Format fboFormat;
    private int targetWidth, targetHeight;

    /**
     * Set once the device has refused every offscreen format. The scene then goes
     * straight to the display: no downscale, so the dither grid is finer and the
     * fill cost is higher, but the game is playable instead of black.
     */
    private boolean directToScreen;

    /** Letterbox offsets, so UI hit-testing can map screen space to the buffer. */
    private int viewX, viewY, viewW, viewH;

    public RetroRenderer() {
        this(false);
    }

    /**
     * @param forceDirect skip the offscreen buffer entirely. This is the path a
     *                    device falls back to when no framebuffer format works,
     *                    and the only reason it can be asked for by hand is that
     *                    an untested fallback is not a fallback.
     */
    public RetroRenderer(boolean forceDirect) {
        directToScreen = forceDirect;
        shader = new RetroShader(environment);
        // ModelBatch never calls init() itself - that is the provider's job.
        shader.init();
        modelBatch = new ModelBatch(new ShaderProvider() {
            @Override
            public Shader getShader(Renderable renderable) {
                return shader;
            }

            @Override
            public void dispose() {
                shader.dispose();
            }
        });
        blit = new SpriteBatch();
        resizeTarget(Config.RENDER_WIDTH, Config.RENDER_HEIGHT);
    }

    public RetroShader.Environment env() {
        return environment;
    }

    /** Rebuilds the offscreen buffer. Safe to call with the current size (no-op). */
    public void resizeTarget(int width, int height) {
        if (directToScreen) {
            targetWidth = Math.max(64, Gdx.graphics.getWidth());
            targetHeight = Math.max(64, Gdx.graphics.getHeight());
            return;
        }
        int w = Math.max(64, width);
        int h = Math.max(64, height);
        if (fbo != null && w == targetWidth && h == targetHeight) return;
        if (fbo != null) fbo.dispose();
        fbo = null;
        targetWidth = w;
        targetHeight = h;

        for (Pixmap.Format format : FBO_FORMATS) {
            try {
                fbo = new FrameBuffer(format, targetWidth, targetHeight, true);
                fboFormat = format;
                break;
            } catch (Throwable t) {
                // Throwable: an incomplete attachment arrives as IllegalStateException,
                // but a driver that dislikes the format can also take the native call
                // down. Either way the next format gets a turn.
                Gdx.app.error("Ashen", "offscreen buffer refused " + format + " ("
                        + t.getMessage() + ")");
            }
        }

        if (fbo == null) {
            directToScreen = true;
            fboRegion = null;
            fboFormat = null;
            Gdx.app.error("Ashen", "no offscreen buffer on this device"
                    + " - drawing the scene straight to the display");
            resizeTarget(width, height);
            return;
        }

        Texture tex = fbo.getColorBufferTexture();
        tex.setFilter(Texture.TextureFilter.Nearest, Texture.TextureFilter.Nearest);
        fboRegion = new TextureRegion(tex);
        fboRegion.flip(false, true); // FBOs are bottom-up.
        Gdx.app.log("Ashen", "offscreen buffer " + targetWidth + "x" + targetHeight
                + " " + fboFormat);
    }

    /** One line describing the render path, for the on-screen boot readout. */
    public String diagnostics() {
        return (directToScreen ? "direct" : String.valueOf(fboFormat))
                + " " + targetWidth + "x" + targetHeight;
    }

    /**
     * Keeps the internal buffer at a fixed height but matches the display's
     * aspect ratio, so ultrawide phones see more of the world rather than a
     * stretched image.
     */
    public void onDisplayResize(int screenWidth, int screenHeight) {
        if (screenWidth <= 0 || screenHeight <= 0) return;
        float aspect = screenWidth / (float) screenHeight;
        int h = Config.RENDER_HEIGHT;
        int w = Math.round(h * aspect);
        w = Math.max(160, Math.min(1024, (w / 2) * 2)); // even width keeps the dither grid stable
        resizeTarget(w, h);
    }

    public float aspectRatio() {
        return targetWidth / (float) targetHeight;
    }

    public void beginScene(float r, float g, float b) {
        if (fbo != null) fbo.begin();
        Gdx.gl.glViewport(0, 0, targetWidth, targetHeight);
        ScreenUtils.clear(r, g, b, 1f, true);
    }

    public void renderScene(Camera camera, Iterable<ModelInstance> instances) {
        modelBatch.begin(camera);
        for (ModelInstance instance : instances) modelBatch.render(instance);
        modelBatch.end();
    }

    public void renderScene(Camera camera, ModelInstance instance) {
        modelBatch.begin(camera);
        modelBatch.render(instance);
        modelBatch.end();
    }

    public void endScene() {
        if (fbo != null) fbo.end();
    }

    /** Point-upscales the buffer to the display, preserving aspect with pillarboxes. */
    public void present() {
        int sw = Gdx.graphics.getWidth();
        int sh = Gdx.graphics.getHeight();
        Gdx.gl.glViewport(0, 0, sw, sh);

        // Everything the HUD and this blit draw goes to the display, and any of
        // these left enabled by the 3D pass would silently reject it. A rejected
        // full-screen quad looks exactly like a broken game.
        Gdx.gl.glDisable(GL20.GL_DEPTH_TEST);
        Gdx.gl.glDisable(GL20.GL_SCISSOR_TEST);
        Gdx.gl.glDisable(GL20.GL_CULL_FACE);
        Gdx.gl.glDepthMask(false);
        Gdx.gl.glColorMask(true, true, true, true);

        if (fbo == null) {
            // Already drawn where it belongs; only the letterbox bookkeeping is left.
            viewX = 0;
            viewY = 0;
            viewW = sw;
            viewH = sh;
            return;
        }
        ScreenUtils.clear(0f, 0f, 0f, 1f);

        float scale = Math.min(sw / (float) targetWidth, sh / (float) targetHeight);
        viewW = Math.round(targetWidth * scale);
        viewH = Math.round(targetHeight * scale);
        viewX = (sw - viewW) / 2;
        viewY = (sh - viewH) / 2;

        blit.getProjectionMatrix().setToOrtho2D(0, 0, sw, sh);
        blit.disableBlending();
        blit.begin();
        blit.draw(fboRegion, viewX, viewY, viewW, viewH);
        blit.end();
        blit.enableBlending();
    }

    /** Grabs the current display contents. Caller owns the returned pixmap. */
    public Pixmap screenshot() {
        return Pixmap.createFromFrameBuffer(0, 0, Gdx.graphics.getBackBufferWidth(),
                Gdx.graphics.getBackBufferHeight());
    }

    public int getTargetWidth() {
        return targetWidth;
    }

    public int getTargetHeight() {
        return targetHeight;
    }

    @Override
    public void dispose() {
        modelBatch.dispose(); // disposes the shader through the provider
        blit.dispose();
        if (fbo != null) fbo.dispose();
    }

    /** Depth buffer is on; make sure nothing left it disabled. */
    public static void resetGlState() {
        Gdx.gl.glEnable(GL20.GL_DEPTH_TEST);
        Gdx.gl.glDepthFunc(GL20.GL_LEQUAL);
        Gdx.gl.glDepthMask(true);
    }
}
