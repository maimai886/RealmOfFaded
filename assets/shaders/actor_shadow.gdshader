shader_type spatial;
render_mode unshaded, cull_disabled;

// 紙片角色的影子替身：只在陰影那一趟畫，永遠側身朝太陽站直，投出來才是整個人形，不是一條線
uniform sampler2D sheet : source_color, filter_linear_mipmap, repeat_disable;

void vertex() {
	vec3 scale = vec3(length(MODEL_MATRIX[0].xyz), length(MODEL_MATRIX[1].xyz), length(MODEL_MATRIX[2].xyz));
	// 陰影那一趟的鏡頭就是太陽，它的 Z 軸指向太陽
	vec3 toward_sun = vec3(INV_VIEW_MATRIX[2].x, 0.0, INV_VIEW_MATRIX[2].z);
	toward_sun = dot(toward_sun, toward_sun) < 0.0001 ? vec3(0.0, 0.0, 1.0) : normalize(toward_sun);
	vec3 right = normalize(cross(vec3(0.0, 1.0, 0.0), toward_sun));
	mat4 facing = mat4(vec4(right * scale.x, 0.0), vec4(0.0, scale.y, 0.0, 0.0),
			vec4(toward_sun * scale.z, 0.0), MODEL_MATRIX[3]);
	MODELVIEW_MATRIX = VIEW_MATRIX * facing;
	MODELVIEW_NORMAL_MATRIX = mat3(MODELVIEW_MATRIX);
}

void fragment() {
	// 用 discard 不寫 ALPHA：寫了會變半透明，影子改用抖動取捨，一顆一顆漏光
	if (texture(sheet, UV).a < 0.5) {
		discard;
	}
	ALBEDO = vec3(0.0);
}
