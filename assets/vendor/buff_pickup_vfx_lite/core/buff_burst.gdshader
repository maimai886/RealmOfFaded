// Cast burst layer: camera-facing, HDR-tinted, with dissolve + distortion + spin.
// The script drives the `progress` uniform 0..1 each frame; the envelope
// (fade in / out) lives in the shader.
shader_type spatial;
render_mode blend_add, depth_draw_never, cull_disabled, unshaded, shadows_disabled, fog_disabled;

uniform sampler2D tex : source_color, filter_linear_mipmap;
uniform sampler2D noise_tex : hint_default_black, repeat_enable, filter_linear_mipmap;

uniform vec4 color_a : source_color = vec4(1.0);
uniform vec4 color_b : source_color = vec4(1.0);
uniform vec4 dissolve_edge_color : source_color = vec4(2.0, 1.2, 0.6, 1.0);

uniform float progress : hint_range(0.0, 1.0) = 0.0;
uniform float emission_energy = 2.6;
uniform float fade_in : hint_range(0.005, 0.3) = 0.07;
uniform float dissolve_amount : hint_range(0.0, 1.0) = 1.0;
uniform float dissolve_edge_width = 0.12;
uniform float distortion : hint_range(0.0, 0.6) = 0.0;
uniform float noise_scale = 1.6;
uniform float spin = 0.0;
uniform float angle_offset = 0.0;
uniform vec2 stretch = vec2(1.0, 1.0);
// kills the not-quite-black background of hand-drawn textures under additive
uniform float black_cut : hint_range(0.0, 0.3) = 0.06;

void vertex() {
	// camera-facing billboard that keeps the node's scale
	MODELVIEW_MATRIX = VIEW_MATRIX * mat4(INV_VIEW_MATRIX[0], INV_VIEW_MATRIX[1], INV_VIEW_MATRIX[2], MODEL_MATRIX[3]);
	MODELVIEW_MATRIX = MODELVIEW_MATRIX * mat4(
			vec4(length(MODEL_MATRIX[0].xyz), 0.0, 0.0, 0.0),
			vec4(0.0, length(MODEL_MATRIX[1].xyz), 0.0, 0.0),
			vec4(0.0, 0.0, length(MODEL_MATRIX[2].xyz), 0.0),
			vec4(0.0, 0.0, 0.0, 1.0));
	MODELVIEW_NORMAL_MATRIX = mat3(MODELVIEW_MATRIX);
}

vec2 rotate_uv(vec2 uv, float a) {
	float s = sin(a);
	float c = cos(a);
	uv -= 0.5;
	return vec2(uv.x * c - uv.y * s, uv.x * s + uv.y * c) + 0.5;
}

void fragment() {
	float ang = angle_offset + spin * progress;
	vec2 uv = rotate_uv(UV, ang);
	uv = (uv - 0.5) / stretch + 0.5;

	// distortion kick that grows with the burst
	vec2 n = texture(noise_tex, uv * noise_scale + vec2(progress * 0.35, -progress * 0.2)).rg - 0.5;
	uv += n * distortion * progress;
	uv = clamp(uv, vec2(0.002), vec2(0.998));

	vec4 s = texture(tex, uv);
	float m = clamp((s.r - black_cut) / (1.0 - black_cut), 0.0, 1.0) * s.a;

	// envelope: very fast in, guaranteed zero at the end
	float env_in = smoothstep(0.0, fade_in, progress);
	float fade_out = 1.0 - smoothstep(0.6, 1.0, progress);

	// dissolve: as progress climbs it eats the noise threshold, edge glows
	float dn = texture(noise_tex, rotate_uv(UV, angle_offset) * noise_scale * 1.7).r;
	float diss_p = smoothstep(0.3, 1.0, progress) * dissolve_amount;
	float threshold = diss_p * (1.0 + dissolve_edge_width) - dissolve_edge_width * 0.5;
	float vis = smoothstep(threshold, threshold + 0.06, dn);
	float edge = (1.0 - smoothstep(threshold + 0.06, threshold + dissolve_edge_width, dn)) * vis * step(0.02, diss_p);

	float a = m * env_in * vis * fade_out;

	// keep the hot white phase short: the main colour takes over at ~25% of
	// life so texture detail doesn't get lost in the brightness
	vec3 col = mix(color_a.rgb, color_b.rgb, smoothstep(0.03, 0.26, progress));
	col += dissolve_edge_color.rgb * edge;
	ALBEDO = col * emission_energy;
	ALPHA = clamp(a, 0.0, 1.0);
}
