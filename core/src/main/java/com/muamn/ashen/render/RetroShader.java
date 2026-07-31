package com.muamn.ashen.render;

import com.badlogic.gdx.Gdx;
import com.badlogic.gdx.graphics.Camera;
import com.badlogic.gdx.graphics.Color;
import com.badlogic.gdx.graphics.GL20;
import com.badlogic.gdx.graphics.Mesh;
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
import com.badlogic.gdx.math.Matrix4;
import com.badlogic.gdx.math.Vector3;
import com.badlogic.gdx.utils.GdxRuntimeException;

import com.muamn.ashen.Config;

/**
 * The one and only shader the 3D scene uses. Written by hand rather than derived
 * from {@code DefaultShader} because every effect that sells the PS2 look
 * (vertex snapping, affine texturing, per-vertex fog, 5-bit dither) needs to sit
 * in specific places in the pipeline.
 *
 * Compiled in two variants - plain and skinned - and switched per renderable.
 * One program with skinning always on would mean every wall paid for bone
 * uniforms it never uses.
 */
public class RetroShader implements Shader {

    /**
     * Bone matrices available to one draw call.
     *
     * GLES2 only guarantees 128 uniform vectors in the vertex stage, and 24
     * matrices is 96 of them. Characters with more joints than this are split
     * into several mesh parts by the import tool, each with its own palette.
     */
    public static final int MAX_BONES = 24;

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

    /** One compiled variant, with its uniform locations resolved once. */
    private static class Variant {
        final ShaderProgram program;
        final int projTrans, worldTrans, texture, ambient, lightDir, lightColor;
        final int diffuseColor, emissive, fogColor, fogNear, fogFar;
        final int snap, affine, colorLevels, alphaTest, bones;

        Variant(String vert, String frag, String prefix, boolean skinning) {
            program = new ShaderProgram(prefix + vert, prefix + frag);
            if (!program.isCompiled()) {
                throw new GdxRuntimeException("retro shader failed to compile:\n"
                        + program.getLog());
            }
            projTrans = program.getUniformLocation("u_projTrans");
            worldTrans = program.getUniformLocation("u_worldTrans");
            texture = program.getUniformLocation("u_texture");
            ambient = program.getUniformLocation("u_ambient");
            lightDir = program.getUniformLocation("u_lightDir");
            lightColor = program.getUniformLocation("u_lightColor");
            diffuseColor = program.getUniformLocation("u_diffuseColor");
            emissive = program.getUniformLocation("u_emissive");
            fogColor = program.getUniformLocation("u_fogColor");
            fogNear = program.getUniformLocation("u_fogNear");
            fogFar = program.getUniformLocation("u_fogFar");
            snap = program.getUniformLocation("u_snap");
            affine = program.getUniformLocation("u_affine");
            colorLevels = program.getUniformLocation("u_colorLevels");
            alphaTest = program.getUniformLocation("u_alphaTest");
            bones = skinning ? locateArray(program, "u_bones") : -1;
        }

        /**
         * Finds an array uniform's location.
         *
         * libGDX builds its uniform table from whatever names the driver reports
         * for active uniforms, and drivers disagree about arrays: some say
         * "u_bones", others "u_bones[0]". Asking for the wrong one returns -1,
         * the bone matrices never get uploaded, and every skinned vertex collapses
         * onto a zero matrix - so this is a hard error, not something to skip.
         */
        private static int locateArray(ShaderProgram program, String name) {
            int location = program.getUniformLocation(name + "[0]");
            if (location < 0) location = program.getUniformLocation(name);
            if (location < 0) {
                throw new GdxRuntimeException("skinned shader has no '" + name + "' uniform");
            }
            return location;
        }
    }

    private static final Color TMP_COLOR = new Color();
    private static final Matrix4 IDENTITY = new Matrix4();

    private final Environment env;
    private Variant plain;
    private Variant skinned;
    private Variant active;

    private RenderContext context;
    private Camera camera;
    private Texture white;
    private Mesh currentMesh;

    /** Flattened bone matrices, uploaded per skinned draw call. */
    private final float[] boneData = new float[MAX_BONES * 16];

    public RetroShader(Environment env) {
        this.env = env;
    }

    @Override
    public void init() {
        String vert = Gdx.files.internal("shaders/retro.vert").readString();
        String frag = Gdx.files.internal("shaders/retro.frag").readString();

        plain = new Variant(vert, frag, "", false);
        skinned = new Variant(vert, frag,
                "#define SKINNED\n#define NUM_BONES " + MAX_BONES + "\n", true);

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
        active = null;

        context.setDepthTest(GL20.GL_LEQUAL, camera.near, camera.far);
        context.setDepthMask(true);
    }

    /** Binds a variant and pushes the scene-wide uniforms it needs. */
    private void use(Variant variant) {
        if (variant == active) return;
        active = variant;
        currentMesh = null; // attribute locations differ between programs
        variant.program.bind();

        setM4(variant.projTrans, camera.combined);
        setF3(variant.ambient, env.ambient);
        setF3(variant.lightColor, env.lightColor);
        setF3(variant.fogColor, env.fogColor);
        if (variant.lightDir >= 0) variant.program.setUniformf(variant.lightDir, env.lightDir);
        setF(variant.fogNear, env.fogNear);
        setF(variant.fogFar, env.fogFar);
        setF(variant.snap, env.snap);
        setF(variant.affine, env.affine);
        setF(variant.colorLevels, env.colorLevels);
    }

    @Override
    public void render(Renderable renderable) {
        boolean isSkinned = renderable.bones != null && renderable.bones.length > 0;
        use(isSkinned ? skinned : plain);
        ShaderProgram program = active.program;
        Attributes mat = renderable.material;

        // Texture.
        TextureAttribute tex = (TextureAttribute) mat.get(TextureAttribute.Diffuse);
        Texture bound = tex != null ? tex.textureDescription.texture : white;
        int unit = context.textureBinder.bind(bound);
        if (active.texture >= 0) program.setUniformi(active.texture, unit);

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
        if (active.diffuseColor >= 0) {
            program.setUniformf(active.diffuseColor,
                    TMP_COLOR.r, TMP_COLOR.g, TMP_COLOR.b, TMP_COLOR.a);
        }

        // Emissive is used as a plain "ignore lighting" amount, not a colour.
        ColorAttribute emissive = (ColorAttribute) mat.get(ColorAttribute.Emissive);
        setF(active.emissive, emissive != null ? emissive.color.r : 0f);

        FloatAttribute alphaTest = (FloatAttribute) mat.get(FloatAttribute.AlphaTest);
        setF(active.alphaTest, alphaTest != null ? alphaTest.value : 0f);

        IntAttribute cull = (IntAttribute) mat.get(IntAttribute.CullFace);
        context.setCullFace(cull != null ? cull.value : GL20.GL_BACK);

        setM4(active.worldTrans, renderable.worldTransform);

        if (isSkinned && active.bones >= 0) {
            uploadBones(renderable);
        }

        // Bind vertex attributes only when the mesh actually changes. Passing
        // autoBind=false to render() without doing this leaves the attribute
        // pointers stale, which the driver turns into an out-of-range read.
        Mesh mesh = renderable.meshPart.mesh;
        if (mesh != currentMesh) {
            if (currentMesh != null) currentMesh.unbind(program);
            currentMesh = mesh;
            currentMesh.bind(program);
        }
        renderable.meshPart.render(program, false);
    }

    private void uploadBones(Renderable renderable) {
        int count = Math.min(renderable.bones.length, MAX_BONES);
        for (int i = 0; i < count; i++) {
            Matrix4 bone = renderable.bones[i] != null ? renderable.bones[i] : IDENTITY;
            System.arraycopy(bone.val, 0, boneData, i * 16, 16);
        }
        // Anything past the model's bone count must still be a valid matrix: a
        // vertex with a zero weight can name any slot, and an uninitialised one
        // would collapse its geometry to the origin.
        for (int i = count; i < MAX_BONES; i++) {
            System.arraycopy(IDENTITY.val, 0, boneData, i * 16, 16);
        }
        active.program.setUniformMatrix4fv(active.bones, boneData, 0, MAX_BONES * 16);
    }

    @Override
    public void end() {
        if (currentMesh != null && active != null) {
            currentMesh.unbind(active.program);
            currentMesh = null;
        }
        active = null;
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
        if (plain != null) plain.program.dispose();
        if (skinned != null) skinned.program.dispose();
        if (white != null) white.dispose();
    }

    public Camera getCamera() {
        return camera;
    }

    // Uniform helpers that quietly skip locations the driver optimised away.

    private void setF(int loc, float v) {
        if (loc >= 0) active.program.setUniformf(loc, v);
    }

    private void setF3(int loc, Color c) {
        if (loc >= 0) active.program.setUniformf(loc, c.r, c.g, c.b);
    }

    private void setM4(int loc, Matrix4 m) {
        if (loc >= 0) active.program.setUniformMatrix(loc, m);
    }
}
