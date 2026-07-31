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

    private FrameBuffer fbo;
    private TextureRegion fboRegion;
    private int targetWidth, targetHeight;

    /** Letterbox offsets, so UI hit-testing can map screen space to the buffer. */
    private int viewX, viewY, viewW, viewH;

    public RetroRenderer() {
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
        if (fbo != null && width == targetWidth && height == targetHeight) return;
        if (fbo != null) fbo.dispose();
        targetWidth = Math.max(64, width);
        targetHeight = Math.max(64, height);
        fbo = new FrameBuffer(Pixmap.Format.RGB888, targetWidth, targetHeight, true);
        Texture tex = fbo.getColorBufferTexture();
        tex.setFilter(Texture.TextureFilter.Nearest, Texture.TextureFilter.Nearest);
        fboRegion = new TextureRegion(tex);
        fboRegion.flip(false, true); // FBOs are bottom-up.
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
        fbo.begin();
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
        fbo.end();
    }

    /** Point-upscales the buffer to the display, preserving aspect with pillarboxes. */
    public void present() {
        int sw = Gdx.graphics.getWidth();
        int sh = Gdx.graphics.getHeight();
        Gdx.gl.glViewport(0, 0, sw, sh);
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
