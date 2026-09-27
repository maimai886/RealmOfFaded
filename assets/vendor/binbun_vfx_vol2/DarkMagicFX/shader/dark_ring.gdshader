shader_type spatial;
render_mode blend_add;

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


group_uniforms Transparency;
uniform float edge_position : hint_range(0.0, 1.0, 0.05) = 0.05;
uniform float edge_hardness : hint_range(0.0, 1.0, 0.05) = 0.0;

uniform float speed_scale = 1.0;

float overlay(float base, float blend){
	float limit = step(0.5, base);
	return mix(2.0 * base * blend, 1.0 - 2.0 * (1.0 - base) * (1.0 - blend), limit);
}

void vertex() {
	// Called for every vertex the material is visible on.
}

void fragment() {
	vec2 centered_uv = UV * 2.0 - 1.0;
	float radius = length(centered_uv);
	float angle = atan(centered_uv.x, centered_uv.y);
	
	vec2 noise_uv = vec2(angle / TAU, radius * 0.5) * noise_scale - noise_scroll * TIME * speed_scale;
	float noise = texture(noise_texture, noise_uv).r;
	noise = pow(noise, noise_shape);
	
	float mask = pow(1.0 - min(abs(radius * 2.0 - 1.0), 1.0), 8.0);
	
	float value = overlay(mask, noise);
	value = max((value - edge_position), 0.0);
	value = clamp(value - effect_decay, 0.0, 1.0);
	
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
