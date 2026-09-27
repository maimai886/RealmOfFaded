shader_type spatial;
render_mode unshaded, cull_disabled;

uniform float effect_amount : hint_range(0.0, 1.0, 0.05) = 1.0;

group_uniforms Color;
uniform vec3 primary_color : source_color = vec3(1.0,0.8,0.2);
uniform vec3 secondary_color : source_color = vec3(1.0,0.4,0.1);
uniform float emission = 2.0;
uniform float color_curve = 1.0;

group_uniforms Shape;
uniform sampler2D noise_texture;
uniform vec2 noise_scale = vec2(0.5);
uniform vec2 noise_scroll = vec2(0.0, 0.1);

group_uniforms Displacement;
uniform float offset = 0.02;

varying vec3 world_pos;
varying vec3 world_normal;

float overlay(float base, float blend){
	float limit = step(0.5, base);
	return mix(2.0 * base * blend, 1.0 - 2.0 * (1.0 - base) * (1.0 - blend), limit);
}

void vertex() {
	VERTEX += NORMAL * offset;
	
	world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	world_normal = MODEL_NORMAL_MATRIX * NORMAL;
}

void fragment() {
	float fresnel = dot(NORMAL, VIEW);
	float rim = 1.0 - fresnel;
	
	float value = max(rim, -world_normal.y);
	
	float noise_xy = texture(noise_texture, world_pos.xy * noise_scale - (noise_scroll * TIME)).r;
	float noise_zy = texture(noise_texture, world_pos.zy * noise_scale - (noise_scroll * TIME)).r;
	
	float noise = mix(noise_xy, noise_zy, abs(world_normal.x));
	
	value = overlay(value, noise);
	
	vec3 color = mix(secondary_color, primary_color, pow(rim, color_curve));
	float alpha = value;
	
	if(!FRONT_FACING){
		color = primary_color;
		alpha = 1.0;
	}
	
	ALBEDO = color;
	ALPHA = alpha * effect_amount;
}

//void light() {
//	// Called for every pixel for every light affecting the material.
//	// Uncomment to replace the default light processing function with this one.
//}
