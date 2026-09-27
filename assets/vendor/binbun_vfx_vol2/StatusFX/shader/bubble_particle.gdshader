shader_type spatial;
render_mode unshaded;

group_uniforms Color;
uniform vec3 primary_color : source_color = vec3(1.0,0.8,0.2);
uniform vec3 secondary_color : source_color = vec3(1.0,0.4,0.1);
uniform vec3 tertiary_color : source_color = vec3(0.6,0.1,0.05);
uniform float emission = 2.0;
uniform float color_curve = 1.0;
uniform float hue_variation = 0.1;
uniform float bubble_warp = 0.03;

group_uniforms Transparency;
uniform float edge_hardness : hint_range(0.0, 1.0, 0.01) = 0.0;
uniform float edge_position : hint_range(0.0, 1.0, 0.01) = 0.2;
uniform bool proximity_fade = false;
uniform float proximity_fade_distance : hint_range(0.0, 4096.0, 0.01);
uniform sampler2D depth_texture : hint_depth_texture, repeat_disable, filter_nearest;

varying flat int id;

vec3 shift_hue(vec3 color, float shift) {
	vec3 gray = vec3(0.57735);
	vec3 projection = gray * dot(gray, color.rgb);
	vec3 U = color.rgb - projection;
	vec3 V = cross(gray, U);
	vec3 shifted = U * cos(shift * 2.0 * PI) + V * sin(shift * 2.0 * PI) + projection;
	return shifted;
}

void vertex() {
	id = INSTANCE_ID;
}

void fragment() {
	vec2 centered_uv = UV - 0.5;
	float angle = atan(centered_uv.x, centered_uv.y);
	
	float rand1 = floor(COLOR.r * 4.0);
	float rand2 = float(id % 4);
	
	float wave = cos((angle + TIME * 1.0) * (3.0 + rand1)) + sin((angle - TIME * 1.0) * (3.0 + rand2));
	
	float r = length(UV * 2.0 - 1.0);
	float shaped_r = r + (wave * bubble_warp * r);
	float shape = (0.2 + (pow(shaped_r, 4.0) / 0.8) * 0.8) * step(shaped_r, 0.8) - (1.0 - COLOR.a);
	shape = max(shape, 0.0);
	
	float shine = max(1.0 - (length(UV * 2.0 - 0.7) + 0.8) - (1.0 - COLOR.a), 0.0);
	shine = pow(shine, 0.5) * step(shaped_r, 0.8);
	
	shape = shape + shine;
	
	vec3 color = mix(secondary_color, primary_color, shape);
	color = shift_hue(color, (COLOR.r - 0.5) * hue_variation) * (0.5 + COLOR.r * 0.5);
	
	ALBEDO = color * emission;
	ALPHA = shape;
	
	// Proximity Fade: Enabled
	if(proximity_fade){
		float proximity_depth_tex = textureLod(depth_texture, SCREEN_UV, 0.0).r;
#if CURRENT_RENDERER == RENDERER_COMPATIBILITY
		vec4 ndc = vec4(vec3(SCREEN_UV, proximity_depth_tex) * 2.0 - 1.0, 1.0);
#else
		vec4 ndc = vec4(SCREEN_UV * 2.0 - 1.0, proximity_depth_tex, 1.0);
#endif
		vec4 proximity_view_pos = INV_PROJECTION_MATRIX * ndc;
		proximity_view_pos.xyz /= proximity_view_pos.w;
		ALPHA *= clamp(1.0 - smoothstep(proximity_view_pos.z + proximity_fade_distance, proximity_view_pos.z, VERTEX.z), 0.0, 1.0);
	}
	
	ALPHA = clamp((ALPHA - edge_position) / (1.0 - edge_hardness), 0.0, 1.0);
}