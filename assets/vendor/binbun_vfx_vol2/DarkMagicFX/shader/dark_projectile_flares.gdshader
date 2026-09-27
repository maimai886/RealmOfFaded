shader_type spatial;
render_mode unshaded, cull_disabled, blend_add;

uniform float effect_decay : hint_range(0.0, 1.0, 0.01) = 0.0;

group_uniforms Color;
uniform vec3 primary_color : source_color;
uniform vec3 secondary_color : source_color;
uniform float emission = 3.0;

group_uniforms Noise;
uniform sampler2D noise_texture;
uniform vec2 noise_scale = vec2(1.0);
uniform vec2 noise_scroll = vec2(0.0, 0.4);
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

void vertex() {
	vec2 noise_uv = UV * noise_scale - noise_scroll * TIME * speed_scale;
	//noise_uv.y += wave * 0.1 * wave_strength;
	float noise = texture(noise_texture, noise_uv).r;
	noise = pow(noise, noise_shape) * 2.0 - 1.0;
	
	VERTEX += NORMAL * 0.03 * noise;
}

void fragment() {
	
	float wave1 = sin(UV.y * wave_frequency * 2.0 - TIME * 2.0);
	float wave2 = sin(UV.y * (wave_frequency / 5.0 * 9.0) * 2.0 - TIME * 2.0);
	float wave = wave1 + wave2;
	
	vec2 noise_uv = UV * noise_scale - noise_scroll * TIME * speed_scale;
	noise_uv.x += wave * 0.2 * wave_strength;
	float noise = texture(noise_texture, noise_uv).r;
	noise = pow(noise, noise_shape);
	
	float value = overlay(noise * pow(1.0 - UV.y, 2.0), 1.0 - UV.y);
	value = smoothstep(0.2, 0.6, value);
	value = max(value - effect_decay, 0.0);
	
	value = max(value - edge_position, 0.0);
	
	float color_value = mix(value, floor(value * 3.0) / 3.0, edge_hardness);
	vec3 color = mix(secondary_color, primary_color, color_value);
	
	float alpha = clamp(value / (1.0 - edge_hardness), 0.0, 1.0);
	
	ALBEDO = color * emission;
	
	ALPHA = alpha;
}

//void light() {
//	// Called for every pixel for every light affecting the material.
//	// Uncomment to replace the default light processing function with this one.
//}
