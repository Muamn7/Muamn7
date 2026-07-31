package com.muamn.ashen.render;

import com.badlogic.gdx.Gdx;
import com.badlogic.gdx.graphics.Camera;
import com.badlogic.gdx.graphics.Color;
import com.badlogic.gdx.graphics.GL20;
import com.badlogic.gdx.graphics.Pixmap;
import com.badlogic.gdx.graphics.Texture;
import com.badlogic.gdx.graphics.g3d.Attributes;
import com.badlogic.gdx.graphics.g3d.Renderable;
import com.badlogic.gdx.graphics.g3d.Shader;
import com.badlogic.gdx.graphics.g3d.attributes.BlendingAttribute;
import com.badlogic.gdx.graphics.g3d.attributes.ColorAttribute;
import com.badlogic.gdx.graphics.g3d.attributes.FloatAttribute;
import com.badlogic.gdx.graphics.g3d.attributes.IntAttribute;
import com.badlogic.gdx.graphics.g3d.attributes.TextureAttribute;
import com.badlogic.gdx.graphics.g3d.utils.RenderContext;
import com.badlogic.gdx.graphics.glutils.ShaderProgram;
import com.badlogic.gdx.math.Vector3;
import com.badlogic.gdx.utils.GdxRuntimeException;

import com.muamn.ashen.Config;

/**
 * The one and only shader the 3D scene uses. Written by hand rather than derived
 * from {@code DefaultShader} because every effect that sells the PS2 look
 * (vertex snapping, affine texturing, per-vertex fog, 5-bit dither) needs to sit
 * in specific places in the pipeline.
 */
public class RetroShader implements Shader {

    /** Scene-wide state, owned by the renderer and read at {@link #begin}. */
    public static class Environment {
        public final Vector3 lightDir = new Vector3(-0.45f, -0.82f, -0.35f).nor();
        public final Color lightColor = new Color(0.85f, 0.80f, 0.70f, 1f);
        public final Color ambient = new Color(0.30f, 0.31f, 0.38f, 1f);
        public final Color fogColor = new Color(0.42f, 0.44f, 0.46f, 1f);
        public float fogNear = Config.FOG_NEAR;
        public float fogFar = Config.FOG_FAR;
        public float snap = Config.VERTEX_SNAP;
        public float affine = Config.AFFINE_AMOUNT;
        public float colorLevels = Config.COLOR_LEVELS;
    }

    private static final Color TMP_COLOR = new Color();

    private final Environment env;
    private ShaderProgram program;
    private RenderContext context;
    private Camera camera;
    private Texture white;
    /** Currently bound mesh; rebinding per draw call is what a shader must avoid. */
    private com.badlogic.gdx.graphics.Mesh currentMesh;

    private int uProjTrans, uWorldTrans, uTexture, uAmbient, uLightDir, uLightColor;
    private int uDiffuseColor, uEmissive, uFogColor, uFogNear, uFogFar;
    private int uSnap, uAffine, uColorLevels, uAlphaTest;

    public RetroShader(Environment env) {
        this.env = env;
    }

    @Override
    public void init() {
        String vert = Gdx.files.internal("shaders/retro.vert").readString();
        String frag = Gdx.files.internal("shaders/retro.frag").readString();
        program = new ShaderProgram(vert, frag);
        if (!program.isCompiled()) {
            throw new GdxRuntimeException("retro shader failed to compile:\n" + program.getLog());
        }
        if (program.getLog() != null && !program.getLog().trim().isEmpty()) {
            Gdx.app.log("RetroShader", program.getLog().trim());
        }

        uProjTrans = program.getUniformLocation("u_projTrans");
        uWorldTrans = program.getUniformLocation("u_worldTrans");
        uTexture = program.getUniformLocation("u_texture");
        uAmbient = program.getUniformLocation("u_ambient");
        uLightDir = program.getUniformLocation("u_lightDir");
        uLightColor = program.getUniformLocation("u_lightColor");
        uDiffuseColor = program.getUniformLocation("u_diffuseColor");
        uEmissive = program.getUniformLocation("u_emissive");
        uFogColor = program.getUniformLocation("u_fogColor");
        uFogNear = program.getUniformLocation("u_fogNear");
        uFogFar = program.getUniformLocation("u_fogFar");
        uSnap = program.getUniformLocation("u_snap");
        uAffine = program.getUniformLocation("u_affine");
        uColorLevels = program.getUniformLocation("u_colorLevels");
        uAlphaTest = program.getUniformLocation("u_alphaTest");

        // Untextured materials still go through the sampler, so give them a
        // 1x1 white texture rather than branching in the fragment shader.
        Pixmap px = new Pixmap(1, 1, Pixmap.Format.RGBA8888);
        px.setColor(Color.WHITE);
        px.fill();
        white = new Texture(px);
        px.dispose();
    }

    @Override
    public void begin(Camera camera, RenderContext context) {
        this.camera = camera;
        this.context = context;
        currentMesh = null;
        program.bind();

        setM4(uProjTrans, camera.combined);
        setF3(uAmbient, env.ambient);
        setF3(uLightColor, env.lightColor);
        setF3(uFogColor, env.fogColor);
        if (uLightDir >= 0) program.setUniformf(uLightDir, env.lightDir);
        setF(uFogNear, env.fogNear);
        setF(uFogFar, env.fogFar);
        setF(uSnap, env.snap);
        setF(uAffine, env.affine);
        setF(uColorLevels, env.colorLevels);

        context.setDepthTest(GL20.GL_LEQUAL, camera.near, camera.far);
        context.setDepthMask(true);
    }

    @Override
    public void render(Renderable renderable) {
        Attributes mat = renderable.material;

        // Texture.
        TextureAttribute tex = (TextureAttribute) mat.get(TextureAttribute.Diffuse);
        Texture bound = tex != null ? tex.textureDescription.texture : white;
        // TextureBinder picks the unit, so the sampler uniform follows it rather
        // than assuming unit 0.
        int unit = context.textureBinder.bind(bound);
        if (uTexture >= 0) program.setUniformi(uTexture, unit);

        // Base colour.
        ColorAttribute diffuse = (ColorAttribute) mat.get(ColorAttribute.Diffuse);
        TMP_COLOR.set(diffuse != null ? diffuse.color : Color.WHITE);
        BlendingAttribute blend = (BlendingAttribute) mat.get(BlendingAttribute.Type);
        if (blend != null) {
            context.setBlending(blend.blended, blend.sourceFunction, blend.destFunction);
            TMP_COLOR.a *= blend.opacity;
        } else {
            context.setBlending(false, GL20.GL_SRC_ALPHA, GL20.GL_ONE_MINUS_SRC_ALPHA);
        }
        if (uDiffuseColor >= 0) {
            program.setUniformf(uDiffuseColor, TMP_COLOR.r, TMP_COLOR.g, TMP_COLOR.b, TMP_COLOR.a);
        }

        // Emissive is used as a plain "ignore lighting" amount, not a colour.
        ColorAttribute emissive = (ColorAttribute) mat.get(ColorAttribute.Emissive);
        setF(uEmissive, emissive != null ? emissive.color.r : 0f);

        FloatAttribute alphaTest = (FloatAttribute) mat.get(FloatAttribute.AlphaTest);
        setF(uAlphaTest, alphaTest != null ? alphaTest.value : 0f);

        IntAttribute cull = (IntAttribute) mat.get(IntAttribute.CullFace);
        context.setCullFace(cull != null ? cull.value : GL20.GL_BACK);

        setM4(uWorldTrans, renderable.worldTransform);

        // Bind vertex attributes only when the mesh actually changes. Passing
        // autoBind=false to render() without doing this leaves the attribute
        // pointers stale, which the driver turns into an out-of-range read.
        com.badlogic.gdx.graphics.Mesh mesh = renderable.meshPart.mesh;
        if (mesh != currentMesh) {
            if (currentMesh != null) currentMesh.unbind(program);
            currentMesh = mesh;
            currentMesh.bind(program);
        }
        renderable.meshPart.render(program, false);
    }

    @Override
    public void end() {
        if (currentMesh != null) {
            currentMesh.unbind(program);
            currentMesh = null;
        }
    }

    /** Every renderable in this game goes through this shader. */
    @Override
    public boolean canRender(Renderable instance) {
        return true;
    }

    @Override
    public int compareTo(Shader other) {
        return 0;
    }

    @Override
    public void dispose() {
        if (program != null) program.dispose();
        if (white != null) white.dispose();
    }

    public Camera getCamera() {
        return camera;
    }

    // Uniform helpers that quietly skip locations the driver optimised away.

    private void setF(int loc, float v) {
        if (loc >= 0) program.setUniformf(loc, v);
    }

    private void setF3(int loc, Color c) {
        if (loc >= 0) program.setUniformf(loc, c.r, c.g, c.b);
    }

    private void setM4(int loc, com.badlogic.gdx.math.Matrix4 m) {
        if (loc >= 0) program.setUniformMatrix(loc, m);
    }
}
