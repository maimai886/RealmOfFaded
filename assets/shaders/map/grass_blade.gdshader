shader_type spatial;
render_mode cull_disabled, diffuse_lambert_wrap, specular_disabled;

// 草毯：草根到草尖一個漸層，草根對齊地面貼圖的綠；法線朝上和地面同一個受光
uniform vec3 root_color : source_color = vec3(0.4, 0.62, 0.28);
uniform vec3 tip_color : source_color = vec3(0.7, 0.83, 0.46);
uniform sampler2D patch_noise : repeat_enable, filter_linear_mipmap;
uniform float sway_strength = 0.1;

varying vec3 blade_tint;

void vertex() {
	vec3 origin = MODEL_MATRIX[3].xyz;
	float patch = textureLod(patch_noise, origin.xz * 0.031 + vec2(0.4, 0.7), 0.0).r;
	float fine = fract(sin(dot(origin.xz, vec2(12.9898, 78.233))) * 43758.5453);
	VERTEX.y *= mix(0.65, 1.35, smoothstep(0.3, 0.7, patch)) * mix(0.85, 1.15, fine);
	float phase = origin.x * 0.35 + origin.z * 0.27;
	float sway = sin(TIME * 1.3 + phase) * 0.7 + sin(TIME * 2.9 + phase * 1.7) * 0.3;
	VERTEX.xz += vec2(1.0, 0.6) * sway * sway_strength * UV.y * UV.y;
	NORMAL = normalize((inverse(MODEL_MATRIX) * vec4(0.0, 1.0, 0.0, 0.0)).xyz);
	blade_tint = mix(vec3(0.9, 1.0, 1.0), vec3(1.12, 1.04, 0.8), smoothstep(0.35, 0.7, patch)) * mix(0.92, 1.08, fine);
}

void fragment() {
	ALBEDO = mix(root_color, tip_color, UV.y) * blade_tint;
	ROUGHNESS = 1.0;
}
