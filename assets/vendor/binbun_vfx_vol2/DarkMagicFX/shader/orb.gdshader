shader_type spatial;
render_mode unshaded;

uniform sampler2D noise_texture;
uniform vec2 noise_scroll = vec2(0.1);

uniform sampler2D detail_texture;
uniform vec2 detail_scroll = vec2(0.05);

float sample_noise(vec2 uv) {
	vec2 noise_uv = uv * vec2(2.0, 1.0) + (TIME * noise_scroll);
	float noise = texture(noise_texture, noise_uv).r;
	return noise;
}

void vertex() {
	VERTEX += NORMAL * sample_noise(UV) * 0.05;
	
	float angle = TIME * 0.5;
	
	mat2 rotation = mat2(vec2(sin(angle), -cos(angle)),
						vec2(cos(angle), sin(angle)));
	
	VERTEX.xy *= rotation;
	
}

void fragment() {
	float noise = sample_noise(UV);
	
	vec2 detail_uv = UV * vec2(2.0, 1.0) + (TIME * detail_scroll);
	float detail = texture(detail_texture, detail_uv).r;
	
	float peak_mask = smoothstep(0.7, 1.0, abs(UV.y * 2.0 - 1.0)) * 0.7;
	
	float value = clamp((noise + detail - peak_mask) / 2.0, 0.0, 1.0);
	value = smoothstep(0.4, 1.0, value);
	
	ALBEDO = vec3(value);
	
	ALPHA = value;
}

//void light() {
//	// Called for every pixel for every light affecting the material.
//	// Uncomment to replace the default light processing function with this one.
//}
