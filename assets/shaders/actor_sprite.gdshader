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
// 紙片受光：圖上已經畫了明暗，只補一層時段的味道，數字由 Actor.light_from 照地圖的太陽和環境光寫進來
uniform float lit_amount = 0.0;
// 太陽照射的方向，世界座標
uniform vec3 sun_direction = vec3(0.0, -1.0, 0.0);
uniform vec3 sun_color : source_color = vec3(1.0);
uniform vec3 ambient_color : source_color = vec3(0.5);
// 法線取圓柱：左右圓潤，頭頂腳底不壓暗；人只佔畫格寬的 0.6，法線往上仰一點才吃得到高低差
uniform float bulge = 0.85;
uniform float figure_span = 0.6;
uniform float normal_tilt = 0.35;
// 向光邊：輪廓朝太陽那側一道亮邊，寬度是螢幕像素
uniform float rim_width = 2.5;
uniform float rim_strength = 0.35;
// 這一格在圖集裡的 UV 範圍，和水平翻轉時要把法線左右轉回來
instance uniform vec4 frame_uv = vec4(0.0, 0.0, 1.0, 1.0);
instance uniform float flip_sign = 1.0;
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

// 亮度開根號壓縮、顏色不壓，受光面才不會爆白；下限留著，夜裡可以暗但不能糊成一團
vec3 sprite_light(vec2 uv, mat4 inv_view) {
	vec2 inside = (uv - frame_uv.xy) / max(frame_uv.zw, vec2(1e-5));
	float across = clamp((inside.x * 2.0 - 1.0) / figure_span, -1.0, 1.0) * flip_sign;
	vec3 view_normal = normalize(vec3(across * bulge, normal_tilt, sqrt(max(1.0 - across * across, 0.04))));
	vec3 world_normal = normalize((inv_view * vec4(view_normal, 0.0)).xyz);
	// 半蘭伯特，背光面不死黑
	float lambert = smoothstep(0.05, 0.9, dot(world_normal, -normalize(sun_direction)) * 0.5 + 0.5);
	vec3 raw = as_linear(ambient_color) + as_linear(sun_color) * lambert;
	float level = max(dot(raw, vec3(0.299, 0.587, 0.114)), 0.02);
	return raw / level * clamp(sqrt(level), 0.45, 1.5);
}

// 往太陽的方向看過去是透明的就是邊；畫格外面是別格，也算透明
float sprite_rim(vec2 uv, mat4 view, vec2 footprint) {
	vec2 screen = (view * vec4(-normalize(sun_direction), 0.0)).xy;
	float strength = length(screen);
	if (strength < 0.05) {
		return 0.0;
	}
	vec2 probe = uv + vec2(screen.x * flip_sign, -screen.y) / strength * footprint * rim_width;
	vec2 inside = (probe - frame_uv.xy) / max(frame_uv.zw, vec2(1e-5));
	bool in_frame = all(greaterThanEqual(inside, vec2(0.0))) && all(lessThanEqual(inside, vec2(1.0)));
	float outside = in_frame ? 1.0 - texture(sheet, probe).a : 1.0;
	return outside * smoothstep(0.05, 0.4, strength);
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
	vec3 rgb = as_linear(tex.rgb);
	if (lit_amount > 0.0) {
		rgb *= mix(vec3(1.0), sprite_light(UV, INV_VIEW_MATRIX), lit_amount);
		float rim = sprite_rim(UV, VIEW_MATRIX, fwidth(UV)) * rim_strength * lit_amount;
		rgb = mix(rgb, max(rgb, vec3(0.0)) + as_linear(sun_color) * 0.6, clamp(rim, 0.0, 1.0));
	}
	vec3 target = linear_to_srgb(rgb);
	float grey = dot(target, vec3(0.299, 0.587, 0.114));
	target = mix(vec3(grey), target, blend_saturation);
	target = mix(blend_haze, target, 1.0 - blend_lift * (1.0 - grey));
	ALBEDO = grading_enabled == 1 ? compensate(target) : to_output(srgb_to_linear(target));
	ALPHA = tex.a;
	ALPHA_SCISSOR_THRESHOLD = 0.5;
	DEPTH = clip_to_depth(depth_clip);
}
