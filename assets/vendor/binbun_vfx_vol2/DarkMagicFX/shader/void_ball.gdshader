shader_type spatial;
render_mode unshaded;

uniform float effect_decay : hint_range(0.0, 1.0, 0.01) = 0.0;

group_uniforms Color;
uniform vec3 primary_color : source_color;
uniform vec3 secondary_color : source_color;
uniform float emission = 2.0;

group_uniforms Displacement;
uniform float displacement_frequency : hint_range(0.0, 8.0, 0.05) = 2.0;
uniform float displacement_amount : hint_range(0.0, 2.0, 0.05) = 0.5;

group_uniforms Noise;
uniform sampler2D noise_texture;
uniform vec2 noise_scale = vec2(1.0);
uniform vec2 noise_scroll = vec2(0.0, 0.2);

uniform float speed_scale = 1.0;

void vertex() {
	float wobble = sin(UV.x * TAU * displacement_frequency - TIME * 4.0 * speed_scale);
	wobble *= sin(UV.y * TAU * displacement_frequency + TIME * 4.0 * speed_scale);
	wobble *= sin(UV.x * TAU * (displacement_frequency * 2.0) - TIME * speed_scale);
	wobble *= sin(UV.y * TAU * (displacement_frequency * 2.0) + TIME * speed_scale);
	
	float mask = pow(sin(UV.y * PI), 0.5);
	
	VERTEX += NORMAL * wobble * 0.5 * displacement_amount * mask;
}

void fragment() {
	float fresnel = max(dot(VIEW, NORMAL), 0.0);
	
	vec2 wave_uv = vec2(sin(TIME), cos(TIME)) * noise_scroll.y * speed_scale;
	vec2 noise_uv = (UV + wave_uv) * noise_scale;
	float noise = texture(noise_texture, UV + wave_uv).r;
	float mask = sin(UV.y * PI);
	
	float value = fresnel + pow(noise, 8.0) * 4.0 * mask;
	
	vec3 color = mix(secondary_color, primary_color, pow(value, 1.0));
	
	ALBEDO = color * emission;
	ALPHA = max(fresnel - effect_decay, 0.0);
}

//void light() {
//	// Called for every pixel for every light affecting the material.
//	// Uncomment to replace the default light processing function with this one.
//}
