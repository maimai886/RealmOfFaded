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

float overlay(float base, float blend){
	float limit = step(0.5, base);
	return mix(2.0 * base * blend, 1.0 - 2.0 * (1.0 - base) * (1.0 - blend), limit);
}

void vertex() {
	MODELVIEW_MATRIX = VIEW_MATRIX * mat4(
			MAIN_CAM_INV_VIEW_MATRIX[0],
			MAIN_CAM_INV_VIEW_MATRIX[1],
			MAIN_CAM_INV_VIEW_MATRIX[2],
			MODEL_MATRIX[3]);
	MODELVIEW_NORMAL_MATRIX = mat3(MODELVIEW_MATRIX);
}

void fragment() {
	vec2 centered_uv = UV * 2.0 - 1.0;
	float radius = length(centered_uv);
	float angle = atan(centered_uv.x, centered_uv.y);
	
	float wave1 = sin(radius * wave_frequency - TIME * 2.0);
	float wave2 = sin(radius * (wave_frequency / 5.0 * 9.0) - TIME * 2.0);
	float wave = wave1 + wave2;
	
	float streaks = sin(angle * 5.0 + TIME) * 0.5 + 0.5;
	
	vec2 noise_uv = vec2(radius * 0.5, angle / TAU) + vec2(noise_scroll.y, noise_scroll.x) * TIME * speed_scale;
	noise_uv.y += wave * 0.1 * wave_strength;
	noise_uv *= vec2(noise_scale.y, noise_scale.x);
	float noise = texture(noise_texture, noise_uv).r;
	noise = pow(noise, noise_shape);
	noise -= effect_decay * 2.0;
	
	float value = noise + pow(1.0 - radius, 4.0) * 1.5;
	value *= sqrt(max(1.0 - radius, 0.0));
	value -= streaks * 0.2;
	value = smoothstep(0.0, 1.0, value);
	value = overlay(value, pow(value, 2.0));
	
	value = max(value - edge_position, 0.0);
	
	float color_value = mix(value, floor(value * 2.0) / 2.0, edge_hardness);
	vec3 color = mix(secondary_color, primary_color, color_value);
	
	ALBEDO = color * 2.0 * emission;
	
	float alpha = clamp(value / (1.0 - edge_hardness), 0.0, 1.0);
	
	ALPHA = alpha;
}

//void light() {
//	// Called for every pixel for every light affecting the material.
//	// Uncomment to replace the default light processing function with this one.
//}
