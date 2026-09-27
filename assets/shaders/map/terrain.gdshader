shader_type spatial;
render_mode diffuse_lambert, specular_disabled;
#include "cloud.gdshaderinc"

// 四層手繪地面：草為底、乾草成片混入、泥土路和石板照路徑折線和圓形區域在 GPU 算距離
const int MAX_POINTS = 48;
const int MAX_PATHS = 8;
const int MAX_AREAS = 12;

uniform sampler2D grass_tex : source_color, repeat_enable, filter_linear_mipmap_anisotropic;
uniform sampler2D dry_tex : source_color, repeat_enable, filter_linear_mipmap_anisotropic;
uniform sampler2D dirt_tex : source_color, repeat_enable, filter_linear_mipmap_anisotropic;
uniform sampler2D stone_tex : source_color, repeat_enable, filter_linear_mipmap_anisotropic;
uniform sampler2D noise_tex : repeat_enable, filter_linear_mipmap;
// 每公尺幾張貼圖；石板一顆約半公尺才像 RO 的石板路
uniform vec4 layer_scale = vec4(0.14, 0.12, 0.2, 0.55);
uniform vec3 grass_tint : source_color = vec3(1.0);
uniform vec3 dry_tint : source_color = vec3(1.0);
uniform vec3 dirt_tint : source_color = vec3(1.0);
uniform vec3 stone_tint : source_color = vec3(1.0);
uniform float dry_amount = 0.0;
uniform float macro_strength = 0.14;
uniform float clump_strength = 0.0;
// paths 每條是 (起點索引, 點數, 半寬, 圖層)；areas 是圓 (中心 x, 中心 z, 半徑, 邊緣寬)、area_layer 是圖層
uniform vec2 path_points[MAX_POINTS];
uniform vec4 paths[MAX_PATHS];
uniform int path_count = 0;
uniform vec4 areas[MAX_AREAS];
uniform int area_layer[MAX_AREAS];
uniform int area_count = 0;
uniform float edge_soft = 0.7;
// walk_mask 每格是離可行走範圍幾公尺除以 walk_mask_range；walk_fade 從幾公尺開始暗到幾公尺全黑
uniform sampler2D walk_mask : filter_linear, repeat_disable, hint_default_black;
uniform vec4 walk_rect = vec4(0.0, 0.0, 1.0, 1.0);
uniform float walk_mask_range = 8.0;
uniform vec2 walk_fade = vec2(0.8, 3.0);

varying vec3 world_pos;

void vertex() {
	world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

float distance_to_segment(vec2 p, vec2 a, vec2 b) {
	vec2 ab = b - a;
	float t = clamp(dot(p - a, ab) / max(dot(ab, ab), 0.0001), 0.0, 1.0);
	return length(p - (a + ab * t));
}

// 同一張貼圖取兩種尺寸依雜訊交錯，重複感才不明顯；a 是亮度
vec4 sample_layer(sampler2D tex, vec2 xz, float scale, float variation) {
	vec3 a = texture(tex, xz * scale).rgb;
	vec3 b = texture(tex, xz * scale * 0.53 + vec2(0.37, 0.71)).rgb;
	vec3 color = mix(a, b, smoothstep(0.3, 0.7, variation));
	return vec4(color, dot(color, vec3(0.299, 0.587, 0.114)));
}

// 權重過半才換層、亮的筆觸先露出來，交界才像手繪
float height_blend(float weight, float top_luma, float base_luma, float sharpness) {
	if (weight < 0.02) {
		return 0.0;
	}
	return clamp((weight - 0.5) * sharpness + (top_luma - base_luma) * 0.6 + 0.5, 0.0, 1.0);
}

void fragment() {
	vec2 xz = world_pos.xz;
	float macro = texture(noise_tex, xz * 0.017).r;
	float mid = texture(noise_tex, xz * 0.06 + vec2(3.1, 5.3)).r;
	float grit = texture(noise_tex, xz * 0.28 + vec2(7.7, 1.9)).r;
	vec4 grass = sample_layer(grass_tex, xz, layer_scale.x, macro);
	vec4 dry = sample_layer(dry_tex, xz, layer_scale.y, mid);
	vec4 dirt = sample_layer(dirt_tex, xz, layer_scale.z, macro);
	vec4 stone = sample_layer(stone_tex, xz, layer_scale.w, mid);
	grass.rgb *= grass_tint;
	dry.rgb *= dry_tint;
	dirt.rgb *= dirt_tint;
	stone.rgb *= stone_tint;

	float weights[4] = float[4](0.0, smoothstep(0.42, 0.78, mix(macro, mid, 0.4) + (grit - 0.5) * 0.15) * dry_amount, 0.0, 0.0);
	float breakup = (grit - 0.5) * edge_soft * 1.6;
	for (int i = 0; i < path_count; i++) {
		int start = int(paths[i].x);
		float best = 1e6;
		for (int j = 0; j < int(paths[i].y) - 1; j++) {
			best = min(best, distance_to_segment(xz, path_points[start + j], path_points[start + j + 1]));
		}
		int layer = int(paths[i].w);
		weights[layer] = max(weights[layer], 1.0 - smoothstep(paths[i].z - edge_soft, paths[i].z + edge_soft, best + breakup));
	}
	for (int i = 0; i < area_count; i++) {
		float edge = max(areas[i].w, 0.05);
		float outside = length(xz - areas[i].xy) - areas[i].z;
		weights[area_layer[i]] = max(weights[area_layer[i]], 1.0 - smoothstep(-edge, edge, outside + breakup * 0.6));
	}

	vec3 color = grass.rgb;
	float luma = grass.a;
	float w = height_blend(weights[1], dry.a, luma, 1.3);
	color = mix(color, dry.rgb, w);
	luma = mix(luma, dry.a, w);
	w = height_blend(weights[2], dirt.a, luma, 2.2);
	color = mix(color, dirt.rgb, w);
	luma = mix(luma, dirt.a, w);
	color = mix(color, stone.rgb, height_blend(weights[3], stone.a, luma, 2.2));

	color *= 1.0 + (macro - 0.5) * macro_strength * 2.0;
	color = mix(color, color * vec3(1.06, 1.0, 0.9), (mid - 0.5) * macro_strength * 2.0);
	float clump = (1.0 - smoothstep(0.25, 0.55, mix(macro, grit, 0.25))) * clump_strength * (1.0 - max(weights[2], weights[3]));
	color = mix(color, color * vec3(0.62, 0.8, 0.7), clump);

	color *= cloud_shade(xz);

	vec2 muv = (xz - walk_rect.xy) / walk_rect.zw;
	float away = walk_mask_range;
	if (all(greaterThanEqual(muv, vec2(0.0))) && all(lessThanEqual(muv, vec2(1.0)))) {
		away = texture(walk_mask, muv).r * walk_mask_range;
	}
	color *= 1.0 - smoothstep(walk_fade.x, walk_fade.y, away + (grit - 0.5) * 0.8);

	ALBEDO = color;
	ROUGHNESS = 1.0;
}
