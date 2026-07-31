// Ashen - PS1/PS2 era vertex shader.
//
// Three period-accurate quirks live here:
//   1. Vertex snapping   - the PS1 GTE had no sub-pixel precision, so geometry
//                          jitters as it moves. Done after the perspective divide.
//   2. Affine texturing  - no per-pixel perspective correction, which makes
//                          textures swim across large triangles.
//   3. Gouraud lighting  - lighting is evaluated per vertex, never per pixel.
//
// Compiled twice: once plain, once with SKINNED defined for imported rigs.

attribute vec3 a_position;
attribute vec3 a_normal;
attribute vec2 a_texCoord0;

#ifdef SKINNED
// Each weight is (bone index, weight). Four is the usual export limit and is
// far more than a PS2-era character actually needed.
attribute vec2 a_boneWeight0;
attribute vec2 a_boneWeight1;
attribute vec2 a_boneWeight2;
attribute vec2 a_boneWeight3;
uniform mat4 u_bones[NUM_BONES];
#endif

uniform mat4 u_projTrans;
uniform mat4 u_worldTrans;

uniform vec3 u_ambient;
uniform vec3 u_lightDir;
uniform vec3 u_lightColor;
uniform vec4 u_diffuseColor;
uniform float u_emissive;

uniform float u_fogNear;
uniform float u_fogFar;
uniform float u_snap;
uniform float u_affine;

// xy = texcoord scaled into affine space, z = the matching divisor.
varying vec3 v_uvw;
varying vec4 v_color;
varying float v_fog;

void main() {
    vec4 local = vec4(a_position, 1.0);
    vec3 localNormal = a_normal;

#ifdef SKINNED
    mat4 skin = a_boneWeight0.y * u_bones[int(a_boneWeight0.x)];
    skin += a_boneWeight1.y * u_bones[int(a_boneWeight1.x)];
    skin += a_boneWeight2.y * u_bones[int(a_boneWeight2.x)];
    skin += a_boneWeight3.y * u_bones[int(a_boneWeight3.x)];
    local = skin * local;
    localNormal = mat3(skin[0].xyz, skin[1].xyz, skin[2].xyz) * a_normal;
#endif

    vec4 world = u_worldTrans * local;
    vec4 clip = u_projTrans * world;

    // Half-lambert keeps unlit faces readable instead of crushing them to black,
    // which is what the era's baked-in ambient term effectively did.
    //
    // mat3(mat4) needs GLSL 1.20; building it from columns works on desktop
    // GLSL 1.10 and GLSL ES 1.00 alike. Uniform scale only, which is all the
    // rigs use, so the inverse-transpose is unnecessary.
    mat3 rot = mat3(u_worldTrans[0].xyz, u_worldTrans[1].xyz, u_worldTrans[2].xyz);
    vec3 n = normalize(rot * localNormal);
    float ndl = dot(n, -u_lightDir) * 0.5 + 0.5;
    vec3 lit = u_ambient + u_lightColor * (ndl * ndl);
    lit = mix(lit, vec3(1.0), clamp(u_emissive, 0.0, 1.0));
    v_color = vec4(u_diffuseColor.rgb * lit, u_diffuseColor.a);

    // For a standard perspective matrix clip.w is the view-space depth, so it
    // doubles as the fog distance for free.
    float w = max(clip.w, 0.0001);
    v_fog = clamp((u_fogFar - w) / max(u_fogFar - u_fogNear, 0.0001), 0.0, 1.0);

    // The rasteriser interpolates varyings perspective-correctly. Pre-multiplying
    // the texcoord by w and dividing by an interpolated w in the fragment shader
    // cancels that out, leaving screen-linear (affine) interpolation.
    float k = mix(1.0, w, clamp(u_affine, 0.0, 1.0));
    v_uvw = vec3(a_texCoord0 * k, k);

    if (u_snap > 0.0) {
        vec2 ndc = clip.xy / w;
        clip.xy = floor(ndc * u_snap + 0.5) / u_snap * w;
    }

    gl_Position = clip;
}
