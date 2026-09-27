// Tek seferlik patlama halkası: script'in progress uniform'u ile sürdüğü, kameraya dönük genişleyen halka + merkez flaşı.
shader_type spatial;
render_mode blend_add, depth_draw_never, cull_disabled, unshaded, shadows_disabled, fog_disabled;

uniform sampler2D noise_tex : hint_default_black, repeat_enable, filter_linear_mipmap;
uniform vec4 ring_color : source_color = vec4(0.7, 0.3, 1.0, 1.0);
uniform vec4 hot_color : source_color = vec4(1.0, 0.85, 1.0, 1.0);
uniform float intensity_mult = 1.0;
uniform float emission_energy : hint_range(0.0, 8.0) = 2.6;
uniform float progress : hint_range(0.0, 1.0) = 0.0;
uniform float ring_width = 0.12;

void vertex() {
	// kameraya dönük billboard, node ölçeğini koruyarak
	MODELVIEW_MATRIX = VIEW_MATRIX * mat4(INV_VIEW_MATRIX[0], INV_VIEW_MATRIX[1], INV_VIEW_MATRIX[2], MODEL_MATRIX[3]);
	MODELVIEW_MATRIX = MODELVIEW_MATRIX * mat4(
			vec4(length(MODEL_MATRIX[0].xyz), 0.0, 0.0, 0.0),
			vec4(0.0, length(MODEL_MATRIX[1].xyz), 0.0, 0.0),
			vec4(0.0, 0.0, length(MODEL_MATRIX[2].xyz), 0.0),
			vec4(0.0, 0.0, 0.0, 1.0));
	MODELVIEW_NORMAL_MATRIX = mat3(MODELVIEW_MATRIX);
}

void fragment() {
	vec2 c = UV - 0.5;
	float dist = length(c) * 2.0;
	float angle = atan(c.y, c.x) / TAU + 0.5;

	float n = texture(noise_tex, vec2(angle * 3.0, 0.13)).r;

	float lead = progress * (0.85 + 0.15 * n);
	float w = ring_width * (0.5 + progress);
	float band = smoothstep(lead - w, lead, dist) * (1.0 - smoothstep(lead, lead + w * 0.5, dist));

	// patlama anındaki merkez flaşı
	float flash = pow(clamp(1.0 - dist * 1.6, 0.0, 1.0), 2.0) * pow(clamp(1.0 - progress * 2.2, 0.0, 1.0), 1.5);

	float fade = pow(clamp(1.0 - progress, 0.0, 1.0), 1.4);
	float a = (band * (0.55 + 0.45 * n) + flash) * fade * intensity_mult;

	vec3 col = mix(ring_color.rgb, hot_color.rgb, clamp(flash + band * 0.3 * (1.0 - progress), 0.0, 1.0));
	ALBEDO = col * emission_energy;
	ALPHA = clamp(a, 0.0, 1.0);
}
