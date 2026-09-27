shader_type spatial;
render_mode unshaded, blend_add;

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

void vertex() {
	// Called for every vertex the material is visible on.
}

void fragment() {
	float mask = pow(UV.y * 2.0, 0.5) * 2.0 - 1.0;
	mask = abs(mask);
	mask += 1.0 - dot(VIEW, NORMAL);
	
	
	float wave1 = sin(UV.y * wave_frequency * 2.0 - TIME * 2.0);
	float wave2 = sin(UV.y * (wave_frequency / 5.0 * 9.0) * 2.0 - TIME * 2.0);
	float wave = wave1 + wave2;
	
	vec2 noise_uv = (UV * vec2(1.0, 2.0));
	noise_uv -= noise_scroll * TIME * speed_scale;
	noise_uv.x += wave * 0.2 * wave_strength;
	float noise = texture(noise_texture, noise_uv).r;
	noise = pow(noise, noise_shape);
	
	float value = max(noise - mask, 0.0);
	value = max(value - effect_decay, 0.0);
	
	value = max(value - edge_position, 0.0);
	
	float color_value = mix(value, floor(value * 4.0) / 4.0, edge_hardness);
	vec3 color = mix(secondary_color, primary_color, color_value);
	
	ALBEDO = color * emission;
	
	float alpha = clamp(value / (1.0 - edge_hardness), 0.0, 1.0);
	
	ALPHA = alpha;
}

//void light() {
//	// Called for every pixel for every light affecting the material.
//	// Uncomment to replace the default light processing function with this one.
//}
