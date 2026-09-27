shader_type spatial;
render_mode unshaded, blend_add, cull_disabled;

uniform float effect_decay : hint_range(0.0, 1.0, 0.01) = 0.0;

group_uniforms Color;
uniform vec3 primary_color : source_color;
uniform float emission = 3.0;

void vertex() {
	// Called for every vertex the material is visible on.
}

void fragment() {
	float value = pow(1.0 - UV.y, 2.0);
	value = smoothstep(0.3, 0.6, value);
	
	value = max(value - effect_decay, 0.0);
	
	ALBEDO = primary_color * emission;
	
	ALPHA = value;
}

//void light() {
//	// Called for every pixel for every light affecting the material.
//	// Uncomment to replace the default light processing function with this one.
//}
