#version 440
// Game View upscaler, pass 2: contrast-adaptive sharpening (the idea of AMD CAS): soft areas get sharper,
// edges that are already strong are left alone, so nothing rings.
layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;
layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec2 outSize;      // this pass's size in pixels
    float sharpness;   // 0 .. 1
};
layout(binding = 1) uniform sampler2D source;

void main() {
    vec2 px = 1.0 / outSize;
    vec3 e = texture(source, qt_TexCoord0).rgb;
    vec3 b = texture(source, qt_TexCoord0 + vec2(0.0, -px.y)).rgb;
    vec3 d = texture(source, qt_TexCoord0 + vec2(-px.x, 0.0)).rgb;
    vec3 f = texture(source, qt_TexCoord0 + vec2(px.x, 0.0)).rgb;
    vec3 h = texture(source, qt_TexCoord0 + vec2(0.0, px.y)).rgb;
    vec3 mn = min(min(min(b, d), min(f, h)), e);
    vec3 mx = max(max(max(b, d), max(f, h)), e);
    vec3 amp = sqrt(clamp(min(mn, 1.0 - mx) / max(mx, vec3(1e-4)), 0.0, 1.0));
    vec3 w = amp * (-1.0 / mix(8.0, 5.0, clamp(sharpness, 0.0, 1.0)));
    vec3 c = (e + (b + d + f + h) * w) / (1.0 + 4.0 * w);
    fragColor = vec4(clamp(c, 0.0, 1.0), 1.0) * qt_Opacity;
}
