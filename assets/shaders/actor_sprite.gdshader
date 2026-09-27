shader_type spatial;
render_mode unshaded, cull_disabled, shadows_disabled;

// 平滑的圖集，meta 的 filter 是 linear
uniform sampler2D sheet : source_color, filter_linear_mipmap_anisotropic, repeat_disable;

#include "res://assets/shaders/actor_sprite.gdshaderinc"
