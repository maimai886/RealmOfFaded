shader_type spatial;
render_mode unshaded, cull_disabled, blend_add;

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

float overlay(float base, float blend){
	float limit = step(0.5, base);
	return mix(2.0 * base * blend, 1.0 - 2.0 * (1.0 - base) * (1.0 - blend), limit);
}

void fragment() {
	float radius = length(UV * 2.0 - 1.0);
	
	float wave1 = sin(UV.y * wave_frequency - TIME * 2.0);
	float wave2 = sin(UV.y * (wave_frequency / 5.0 * 9.0) - TIME * 2.0);
	float wave = wave1 + wave2;
	
	vec2 noise_uv = (UV * 0.3 + COLOR.r) + noise_scroll * 0.5 * TIME * speed_scale;
	noise_uv.x += wave * 0.1 * wave_strength;
	noise_uv *= noise_scale;
	float noise = texture(noise_texture, noise_uv).r;
	noise = pow(noise, noise_shape);
	
	float value = noise - radius;
	value = max(value - (1.0 - COLOR.a), 0.0);
	value += pow(value, 2.0);
	value = max(value - edge_position, 0.0);
	
	float color_value = mix(value, floor(value * 2.0) / 2.0, edge_hardness);
	vec3 color = mix(secondary_color, primary_color, color_value);
	
	ALBEDO = color * emission;
	
	float alpha = clamp(value / (1.0 - edge_hardness), 0.0, 1.0);
	
	ALPHA = alpha;
}

//void light() {
//	// Called for every pixel for every light affecting the material.
//	// Uncomment to replace the default light processing function with this one.
//}
