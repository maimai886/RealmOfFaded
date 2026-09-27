shader_type spatial;
render_mode unshaded , cull_disabled;

uniform float effect_decay : hint_range(0.0, 1.0, 0.01) = 0.0;

group_uniforms Displacement;
uniform float displacement_frequency : hint_range(0.0, 8.0, 0.05) = 2.0;
uniform float displacement_amount : hint_range(0.0, 2.0, 0.05) = 0.5;

uniform float speed_scale = 1.0;

void vertex() {
	float wobble = sin(UV.x * TAU * displacement_frequency - TIME * 4.0 * speed_scale) * sin(UV.y * TAU * displacement_frequency + TIME * 4.0 * speed_scale);
	
	float mask = pow(sin(UV.y * PI), 0.5);
	
	VERTEX += NORMAL * wobble * 0.1 * displacement_amount * mask;
}

void fragment() {
	float fresnel = max(dot(VIEW, NORMAL), 0.0);
	
	ALPHA = max(fresnel - effect_decay, 0.0);
	
	ALBEDO = vec3(0.0);
}

//void light() {
//	// Called for every pixel for every light affecting the material.
//	// Uncomment to replace the default light processing function with this one.
//}
