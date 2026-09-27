shader_type spatial;
render_mode unshaded, cull_disabled, shadows_disabled;

// 手繪像素圖集，meta 的 filter 是 nearest；匯入要產 mipmap、開 fix_alpha_border，透明像素才不會把邊緣混黑
#define SHARP_BILINEAR
uniform sampler2D sheet : source_color, filter_linear_mipmap, repeat_disable;

#include "res://assets/shaders/actor_sprite.gdshaderinc"
