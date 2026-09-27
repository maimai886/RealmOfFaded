shader_type spatial;
render_mode unshaded, blend_add;

uniform float effect_decay : hint_range(0.0, 1.0, 0.01) = 0.0;

group_uniforms Color;
uniform vec3 primary_color : source_color;
uniform vec3 secondary_color : source_color;
uniform float emission = 2.0;

group_uniforms Noise;
uniform sampler2D noise_texture;
uniform vec2 noise_scale = vec2(1.0);
uniform vec2 noise_scroll = vec2(0.0, 0.2);
uniform float noise_shape : hint_range(0.0, 8.0, 0.1) = 1.0;

group_uniforms Wave;
uniform float wave_strength : hint_range(0.0, 1.0, 0.05) = 0.5;
uniform float wave_frequency = 5.0;

group_uniforms Transparency;
uniform float edge_position : hint_range(0.0, 1.0, 0.05) = 0.0;
uniform float edge_hardness : hint_range(0.0, 1.0, 0.05) = 0.0;

uniform float speed_scale = 1.0;

void vertex() {
	// Called for every vertex the material is visible on.
}

void fragment() {
	float y = UV.y * 2.0;
	
	float wave = sin(y * TAU * (wave_frequency / 2.0) - TIME * 1.0) * (1.0 - y);
	
	vec2 noise_uv = UV + (vec2(wave, 0.0) * 0.1 * wave_strength) + noise_scroll * TIME * speed_scale;
	float noise = texture(noise_texture, noise_uv * noise_scale).r;
	noise = pow(noise, noise_shape);
	
	float value = clamp(noise * y + pow(y, 4.0), 0.0, 1.5) / 1.5;
	value = max((value - edge_position), 0.0);
	value = pow(value, 2.0);
	value = clamp(value - effect_decay, 0.0, 1.0);
	
	float color_value = mix(value, floor(value * 4.0) / 4.0, edge_hardness);
	vec3 color = mix(secondary_color, primary_color, color_value);
	
	ALBEDO = color * emission;
	
	float alpha = clamp(value / (1.0 - edge_hardness), 0.0, 1.0);
	ALPHA = alpha;
}