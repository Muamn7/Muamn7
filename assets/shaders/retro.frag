// Ashen - PS1/PS2 era fragment shader.
// Flat texture lookup, per-vertex fog, then an ordered-dither quantisation down
// to a 5-bit-per-channel framebuffer.

#ifdef GL_ES
precision mediump float;
#endif

uniform sampler2D u_texture;
uniform vec3 u_fogColor;
uniform float u_colorLevels;
uniform float u_alphaTest;

varying vec3 v_uvw;
varying vec4 v_color;
varying float v_fog;

// Compact Bayer 4x4 ordered dither, in [0,1).
float bayer2(vec2 a) {
    a = floor(a);
    return fract(a.x * 0.5 + a.y * a.y * 0.75);
}

float bayer4(vec2 a) {
    return bayer2(0.5 * a) * 0.25 + bayer2(a);
}

void main() {
    vec2 uv = v_uvw.xy / v_uvw.z;
    vec4 tex = texture2D(u_texture, uv);

    float alpha = tex.a * v_color.a;
    if (alpha < u_alphaTest) discard;

    vec3 c = tex.rgb * v_color.rgb;
    c = mix(u_fogColor, c, v_fog);

    if (u_colorLevels > 0.0) {
        float d = (bayer4(gl_FragCoord.xy) - 0.5) / u_colorLevels;
        c = floor(clamp(c + d, 0.0, 1.0) * u_colorLevels + 0.5) / u_colorLevels;
    }

    gl_FragColor = vec4(c, alpha);
}
