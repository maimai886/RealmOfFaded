shader_type spatial;
render_mode unshaded, cull_disabled, shadows_disabled;

// 紙片角色：整張正對鏡頭，顏色先收進場景再抵銷色調映射，做法見 docs/精靈圖顯示校正.md
uniform sampler2D sheet : source_color, filter_linear_mipmap_anisotropic, repeat_disable;
// 公尺；腳底那幾排像素在地面下，往鏡頭推才不會被地面蓋掉
uniform float depth_nudge = 0.12;
uniform int grading_enabled = 0;
// 反查表排成 2D：x 是 r + cube × b、y 是 g，一片裡用雙線性、兩片之間再混一次
uniform sampler2D grading_lut : filter_linear, repeat_disable;
uniform float grading_cube = 21.0;
// 原圖全彩全對比放進有空氣感的場景很搶戲，先收一點飽和、把暗部往霧色提，霧色是 sRGB
uniform float blend_saturation = 0.82;
uniform float blend_lift = 0.08;
uniform vec3 blend_haze = vec3(0.86, 0.88, 0.84);
varying vec2 depth_clip;

vec3 srgb_to_linear(vec3 c) {
	return mix(pow((c + 0.055) / 1.055, vec3(2.4)), c / 12.92, lessThan(c, vec3(0.04045)));
}

vec3 linear_to_srgb(vec3 c) {
	c = max(c, vec3(0.0));
	return mix(1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055, c * 12.92, lessThan(c, vec3(0.0031308)));
}

// 相容渲染器整條管線在 sRGB，貼圖取進來不轉線性、ALBEDO 也不編碼，要自己轉，不然整個發白
vec3 as_linear(vec3 c) {
#if CURRENT_RENDERER == RENDERER_COMPATIBILITY
	return srgb_to_linear(c);
#else
	return c;
#endif
}

vec3 to_output(vec3 c) {
#if CURRENT_RENDERER == RENDERER_COMPATIBILITY
	return linear_to_srgb(c);
#else
	return c;
#endif
}

// 相容渲染器的裁切空間 z 是 −1 到 1，要換成 0 到 1
float clip_to_depth(vec2 clip_zw) {
	float ndc_z = clip_zw.x / max(clip_zw.y, 0.0001);
#if CURRENT_RENDERER == RENDERER_COMPATIBILITY
	return ndc_z * 0.5 + 0.5;
#else
	return ndc_z;
#endif
}

vec3 compensate(vec3 t) {
	float n = grading_cube;
	float zf = clamp(t.b, 0.0, 1.0) * (n - 1.0);
	float z0 = floor(zf);
	float z1 = min(z0 + 1.0, n - 1.0);
	vec2 texel = clamp(t.rg, 0.0, 1.0) * (n - 1.0) + 0.5;
	vec2 size = vec2(n * n, n);
	vec3 low = texture(grading_lut, vec2(texel.x + z0 * n, texel.y) / size).rgb;
	vec3 high = texture(grading_lut, vec2(texel.x + z1 * n, texel.y) / size).rgb;
	return max(mix(low, high, zf - z0), vec3(0.0));
}

void vertex() {
	vec3 scale = vec3(length(MODEL_MATRIX[0].xyz), length(MODEL_MATRIX[1].xyz), length(MODEL_MATRIX[2].xyz));
	mat4 billboard = mat4(INV_VIEW_MATRIX[0], INV_VIEW_MATRIX[1], INV_VIEW_MATRIX[2], MODEL_MATRIX[3]);
	MODELVIEW_MATRIX = VIEW_MATRIX * billboard * mat4(vec4(scale.x, 0.0, 0.0, 0.0), vec4(0.0, scale.y, 0.0, 0.0),
			vec4(0.0, 0.0, scale.z, 0.0), vec4(0.0, 0.0, 0.0, 1.0));
	MODELVIEW_NORMAL_MATRIX = mat3(MODELVIEW_MATRIX);
	VERTEX.z += depth_nudge / max(scale.z, 0.001);
	// 深度照一片站直、只繞 Y 軸面向鏡頭的平面寫，後仰的紙片頭才不會插進身後的台階和牆
	vec3 toward = normalize(INV_VIEW_MATRIX[2].xyz);
	vec3 right = cross(vec3(0.0, 1.0, 0.0), toward);
	right = dot(right, right) < 0.0001 ? INV_VIEW_MATRIX[0].xyz : normalize(right);
	vec3 plane_point = MODEL_MATRIX[3].xyz + right * (VERTEX.x * scale.x)
			+ vec3(0.0, VERTEX.y * scale.y, 0.0) + toward * depth_nudge;
	depth_clip = (PROJECTION_MATRIX * VIEW_MATRIX * vec4(plane_point, 1.0)).zw;
}

void fragment() {
	vec4 tex = texture(sheet, UV);
	vec3 target = linear_to_srgb(as_linear(tex.rgb));
	float grey = dot(target, vec3(0.299, 0.587, 0.114));
	target = mix(vec3(grey), target, blend_saturation);
	target = mix(blend_haze, target, 1.0 - blend_lift * (1.0 - grey));
	ALBEDO = grading_enabled == 1 ? compensate(target) : to_output(srgb_to_linear(target));
	ALPHA = tex.a;
	ALPHA_SCISSOR_THRESHOLD = 0.5;
	DEPTH = clip_to_depth(depth_clip);
}
