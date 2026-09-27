// 雲影：很大很軟的暗斑慢慢飄過，地面、草和樹用同一張雜訊一起暗，白天的草地才不會整片一樣亮
uniform sampler2D cloud_noise : repeat_enable, filter_linear_mipmap;
uniform float cloud_strength = 0.0;

vec3 cloud_shade(vec2 xz) {
	float cloud = smoothstep(0.42, 0.66, textureLod(cloud_noise, xz * 0.0065 + vec2(TIME * 0.0045, TIME * 0.0028), 0.0).r);
	return mix(vec3(1.0), vec3(1.0 - cloud_strength) * vec3(0.94, 0.97, 1.06), cloud);
}
