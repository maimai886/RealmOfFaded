shader_type spatial;
render_mode cull_disabled, diffuse_lambert_wrap, specular_disabled;

// 素材包的樹冠、草叢、花：alpha 裁切加輕輕隨風晃，法線換成從樹冠中心往外，整團葉子像一顆球受光
uniform sampler2D albedo_texture : source_color, filter_linear_mipmap, repeat_disable;
uniform float sway_strength = 0.05;
uniform float sphere_normals = 0.0;
uniform vec3 canopy_center = vec3(0.0, 3.0, 0.0);
// 素材沒有環境遮蔽，用樹冠由下到上的明暗漸層代替，範圍是模型座標
uniform float shade_bottom = 0.72;
uniform float shade_top = 1.12;
uniform float gradient_bottom = 0.5;
uniform float gradient_height = 5.0;
// 用每一棵的位置當亂數偏黃綠或偏藍綠，整片樹林才不會同一個綠
uniform float plant_variation = 0.0;
// 樹冠頂端被太陽照到的亮邊，加色不是乘色
uniform vec3 sun_kiss = vec3(0.0);
uniform float pastel = 0.0;

varying vec3 sphere_normal_view;
varying float canopy_height;
varying vec3 plant_tint;

void vertex() {
	vec3 world = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	float phase = world.x * 0.35 + world.z * 0.27;
	float sway = sin(TIME * 1.1 + phase) * 0.7 + sin(TIME * 2.53 + phase * 1.7) * 0.3;
	canopy_height = clamp((VERTEX.y - gradient_bottom) / max(gradient_height, 0.001), 0.0, 1.0);
	vec3 outward = normalize(VERTEX - canopy_center + vec3(0.0, 0.0001, 0.0));
	sphere_normal_view = (MODELVIEW_MATRIX * vec4(normalize(mix(NORMAL, outward, sphere_normals)), 0.0)).xyz;
	VERTEX.xz += vec2(1.0, 0.6) * sway * sway_strength * canopy_height * canopy_height;
	vec2 origin = MODEL_MATRIX[3].xz;
	float pick = fract(sin(dot(origin, vec2(12.9898, 78.233))) * 43758.5453);
	vec3 hue = mix(vec3(0.84, 1.0, 0.96), vec3(1.14, 1.04, 0.78), pick);
	plant_tint = mix(vec3(1.0), hue * mix(0.86, 1.1, fract(pick * 7.13)), plant_variation);
}

void fragment() {
	vec4 tex = texture(albedo_texture, UV);
	vec3 leaf = tex.rgb * mix(shade_bottom, shade_top, canopy_height) * plant_tint;
	leaf = mix(leaf, vec3(dot(leaf, vec3(0.299, 0.587, 0.114))), pastel * 0.22) * (1.0 + pastel * 0.35);
	ALBEDO = leaf + sun_kiss * canopy_height * canopy_height;
	ALPHA = tex.a;
	ALPHA_SCISSOR_THRESHOLD = 0.5;
	ROUGHNESS = 1.0;
	// 球形法線正反面都朝外，背面不翻
	NORMAL = normalize(sphere_normal_view);
	BACKLIGHT = vec3(0.3, 0.34, 0.12) * sphere_normals;
}
