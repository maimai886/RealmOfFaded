extends RefCounted
## 全遊戲共用的介面主題：視窗和 HUD 同一塊深色半透明玻璃、近白字、細邊、圓角，強調色只有送出鈕那個藍
## 字型只用 jf open 粉圓，視窗標題用源雲明體、Logo 用 Cinzel；字級只用下面四種

const FONTS := "res://assets/vendor/fonts/"
const SKIN := "res://assets/ui/skin/"
const FONT_SMALL := 12
const FONT_BODY := 13
const FONT_HEAD := 15
const FONT_TITLE := 18
const PAD := 10
const GAP := 6
const FADE_IN := 0.12
# 視窗從上緣一條扁線往下展開
const UNFOLD_START_Y := 0.03
const UNFOLD_START_X := 0.92
const UNFOLD_TIME := 0.26

# 數字照 HUD 的聊天框和快捷列格子，2026-09-26 定案，不另外發明配色
const WINDOW_BG := Color(0.21, 0.23, 0.26, 0.86)
const INSET_BG := Color(0.0, 0.0, 0.0, 0.16)
const INSET_ALT := Color(0.0, 0.0, 0.0, 0.26)
const BORDER := Color(0.99, 0.96, 0.89, 0.22)
const BORDER_LIGHT := Color(0.99, 0.96, 0.89, 0.11)
const SELECT_BG := Color(1.0, 1.0, 1.0, 0.14)
const ACCENT := Color("5d81a8")
const ACCENT_SOFT := Color("a9c3dd")
const INK := Color("f3f1ea")
const INK_DIM := Color("b9bcc2")
const INK_ACCENT := Color("ffd98a")
const INK_GOOD := Color("9fdc92")
const INK_BAD := Color("ff8f7e")
const INK_WARN := Color("f5b56a")
const TITLE_INK := Color("fbfbf5")
const ORNAMENT := Color(0.86, 0.72, 0.42, 0.9)
# 直接疊在 3D 畫面上的字和主要按鈕上的字
const TEXT_BODY := Color("fdf4e2")
const OUTLINE := Color(0.05, 0.04, 0.03, 0.9)
# 按鈕連框一起透一點，再低字的對比會掉出 5 比 1
const BUTTON_ALPHA := 0.92
const BUTTON_ALPHA_HOVER := 0.97

static var _theme: Theme
static var _fonts := {}
static var _styles := {}


## kind：body 內文、window_title 視窗標題、logo 標誌
static func font(kind: String) -> Font:
	if _fonts.has(kind):
		return _fonts[kind]
	var body: FontFile = load(FONTS + "jf-openhuninn-2.1.ttf")
	var variation := FontVariation.new()
	variation.base_font = body
	variation.fallbacks = [load(FONTS + "NotoSansTC-wght.ttf")]
	if kind == "window_title":
		variation.base_font = load(FONTS + "GenWanMin2TW-SB.otf")
		variation.fallbacks = [body]
	elif kind == "logo":
		variation.base_font = load(FONTS + "Cinzel-wght.ttf")
		variation.variation_opentype = {"wght": 700}
		variation.fallbacks = [body]
	_fonts[kind] = variation
	return variation


static func window_theme() -> Theme:
	if _theme:
		return _theme
	var theme := Theme.new()
	theme.default_font = font("body")
	theme.default_font_size = FONT_BODY
	theme.set_stylebox("panel", "PanelContainer", style("window"))
	theme.set_color("font_color", "Label", INK)
	theme.set_constant("line_spacing", "Label", 1)
	for state in ["normal", "hover", "pressed", "hover_pressed", "disabled"]:
		var kind: String = {"normal": "button", "hover_pressed": "button_pressed"}.get(state, "button_" + state)
		var opacity := BUTTON_ALPHA if state in ["normal", "disabled"] else BUTTON_ALPHA_HOVER
		theme.set_stylebox(state, "Button", _faded(style(kind), opacity))
	theme.set_stylebox("focus", "Button", StyleBoxEmpty.new())
	for state in ["font_color", "font_hover_color", "font_pressed_color", "font_hover_pressed_color", "font_focus_color"]:
		theme.set_color(state, "Button", INK)
	theme.set_color("font_disabled_color", "Button", Color(INK_DIM, 0.55))
	theme.set_stylebox("normal", "LineEdit", style("input"))
	theme.set_stylebox("focus", "LineEdit", style("input_focus"))
	theme.set_color("font_color", "LineEdit", INK)
	theme.set_color("font_placeholder_color", "LineEdit", Color(INK_DIM, 0.75))
	theme.set_color("caret_color", "LineEdit", ACCENT)
	theme.set_color("selection_color", "LineEdit", Color(ACCENT_SOFT, 0.75))
	# 勾選框是一顆菱形，方形勾選框是系統對話框的東西
	# 沒勾的空心菱形：深色芯加近白細邊，手機縮小後才看得到
	var check_off := diamond_texture(14, Color(0, 0, 0, 0.3), Color(INK, 0.85))
	var check_on := diamond_texture(14, ORNAMENT, Color(INK, 0.7))
	for state in ["normal", "hover", "pressed", "hover_pressed", "focus"]:
		theme.set_stylebox(state, "CheckBox", StyleBoxEmpty.new())
	for state in ["font_color", "font_hover_color", "font_pressed_color", "font_hover_pressed_color", "font_focus_color"]:
		theme.set_color(state, "CheckBox", INK)
	theme.set_icon("unchecked", "CheckBox", check_off)
	theme.set_icon("checked", "CheckBox", check_on)
	for type in ["VScrollBar", "HScrollBar"]:
		theme.set_stylebox("scroll", type, _flat(INSET_ALT, INSET_ALT, 0, 3, 3))
		theme.set_stylebox("grabber", type, _flat(Color(INK_DIM, 0.35), Color(INK_DIM, 0.35), 0, 3, 3))
	_theme = theme
	return theme


static func _flat(bg: Color, border: Color, border_width: int, radius: int, content: int) -> StyleBoxFlat:
	var box := StyleBoxFlat.new()
	box.bg_color = bg
	box.border_color = border
	box.set_border_width_all(border_width)
	box.set_corner_radius_all(radius)
	box.set_content_margin_all(content)
	box.anti_aliasing = radius > 0
	return box


static func _faded(box: StyleBoxFlat, opacity: float) -> StyleBoxFlat:
	var copy := box.duplicate()
	copy.bg_color.a *= opacity
	return copy


## 回傳共用的實體，要改屬性先 duplicate
static func style(kind: String) -> StyleBoxFlat:
	if not _styles.has(kind):
		_styles[kind] = _make_style(kind)
	return _styles[kind]


static func _make_style(kind: String) -> StyleBoxFlat:
	match kind:
		"window":
			var window := _flat(WINDOW_BG, BORDER, 1, 10, PAD)
			window.shadow_color = Color(0.0, 0.0, 0.0, 0.28)
			window.shadow_size = 14
			window.shadow_offset = Vector2(0, 5)
			return window
		"inset":
			return _flat(INSET_BG, BORDER_LIGHT, 1, 6, 6)
		"input":
			return _flat(Color(0.0, 0.0, 0.0, 0.28), BORDER, 1, 6, 6)
		"input_focus":
			return _flat(Color(0.0, 0.0, 0.0, 0.36), ACCENT_SOFT, 1, 6, 6)
		"slot":
			return _flat(Color(0.18, 0.20, 0.23, 0.66), Color(0.98, 0.98, 0.96, 0.22), 1, 6, 4)
		"select":
			return _flat(SELECT_BG, Color(ACCENT, 0.6), 1, 5, 4)
		"button":
			return _button_box(Color(0.30, 0.33, 0.36, 0.78), Color(0.99, 0.96, 0.89, 0.30))
		"button_hover":
			return _button_box(Color(0.38, 0.41, 0.45, 0.92), Color(0.99, 0.96, 0.89, 0.55))
		"button_pressed":
			return _button_box(Color(0.20, 0.22, 0.25, 0.95), Color(0.99, 0.96, 0.89, 0.30), 1)
		"button_disabled":
			return _button_box(Color(0.30, 0.33, 0.36, 0.35), BORDER_LIGHT)
		"button_accent":
			return _button_box(Color(0.40, 0.55, 0.72, 0.95), Color(0.26, 0.38, 0.52, 1.0))
		"button_accent_hover":
			return _button_box(Color(0.46, 0.61, 0.78, 1.0), Color(0.26, 0.38, 0.52, 1.0))
		"button_accent_pressed":
			return _button_box(Color(0.32, 0.46, 0.62, 1.0), Color(0.22, 0.32, 0.44, 1.0), 1)
	push_error("沒有這種樣式 " + kind)
	return style("window")


## 底邊厚一像素當厚度；按下時字往下移 1 像素
static func _button_box(fill: Color, border: Color, sink := 0) -> StyleBoxFlat:
	var box := _flat(fill, border, 1, 3, 0)
	box.border_width_bottom = 2
	box.content_margin_left = 12
	box.content_margin_right = 12
	box.content_margin_top = 4 + sink
	box.content_margin_bottom = 4 - sink
	return box


## 主要按鈕：藍面白字
static func make_accent(button: Button) -> void:
	button.add_theme_stylebox_override("normal", _faded(style("button_accent"), BUTTON_ALPHA_HOVER))
	button.add_theme_stylebox_override("hover", style("button_accent_hover"))
	button.add_theme_stylebox_override("pressed", style("button_accent_pressed"))
	button.add_theme_stylebox_override("hover_pressed", style("button_accent_pressed"))
	for state in ["font_color", "font_hover_color", "font_pressed_color", "font_hover_pressed_color", "font_focus_color"]:
		button.add_theme_color_override(state, TEXT_BODY)


## 標題列：透明底，下緣的細線由 draw_title_rule 畫
static func title_bar_style() -> StyleBoxFlat:
	var bar := _flat(Color(0, 0, 0, 0), Color(0, 0, 0, 0), 0, 0, 4)
	bar.content_margin_left = 10
	bar.content_margin_right = 8
	bar.content_margin_bottom = 7
	return bar


## 標題列底下一條淡金細線，兩端各一顆小菱形
static func draw_title_rule(bar: Control) -> void:
	var y := bar.size.y - 1.5
	var x0 := 10.0
	var x1 := bar.size.x - 10.0
	bar.draw_line(Vector2(x0 + 4, y), Vector2(x1 - 4, y), Color(ORNAMENT, 0.5), 1.0, true)
	for x in [x0, x1]:
		bar.draw_colored_polygon(PackedVector2Array([Vector2(x, y - 3), Vector2(x + 3, y), Vector2(x, y + 3),
				Vector2(x - 3, y)]), ORNAMENT)


## 角色預覽舞台的底：上淺下深，白色素體站上去輪廓最清楚
static func stage_style() -> StyleBoxTexture:
	var gradient := GradientTexture2D.new()
	gradient.gradient = Gradient.new()
	gradient.gradient.colors = PackedColorArray([Color("48505c"), Color("262a31")])
	gradient.fill_to = Vector2(0, 1)
	gradient.width = 4
	gradient.height = 32
	var box := StyleBoxTexture.new()
	box.texture = gradient
	return box


static func skin_texture(name: String) -> Texture2D:
	return load(SKIN + name + ".png")


static func diamond_texture(size: int, fill: Color, outline: Color) -> Texture2D:
	# 畫四倍大再縮下來，邊才不會是鋸齒
	var big := size * 4
	var image := Image.create(big, big, false, Image.FORMAT_RGBA8)
	var half := big / 2.0 - 2.0
	for y in big:
		for x in big:
			var d := absf(x + 0.5 - big / 2.0) + absf(y + 0.5 - big / 2.0)
			if d <= half:
				image.set_pixel(x, y, fill if d <= half - 6.0 else outline)
	image.resize(size, size, Image.INTERPOLATE_LANCZOS)
	return ImageTexture.create_from_image(image)


## 直接疊在 3D 畫面上的字：白字加深色細描邊
static func overlay_settings(size := FONT_BODY, color := TEXT_BODY) -> LabelSettings:
	var settings := LabelSettings.new()
	settings.font = font("body")
	settings.font_size = size
	settings.font_color = color
	settings.outline_size = 3
	settings.outline_color = OUTLINE
	return settings


static func motion_enabled() -> bool:
	return DisplayServer.get_name() != "headless"


## 視窗打開：從上緣一條扁線往下展開；還沒排版時 size 是 0，等一幀
static func unfold(control: Control) -> void:
	if not motion_enabled() or not control.is_inside_tree():
		return
	control.modulate.a = 0.0
	await control.get_tree().process_frame
	if not is_instance_valid(control) or not control.visible:
		return
	control.pivot_offset = Vector2(control.size.x * 0.5, 0.0)
	control.scale = Vector2(UNFOLD_START_X, UNFOLD_START_Y)
	var tween := control.create_tween().set_parallel(true).set_ease(Tween.EASE_OUT)
	tween.tween_property(control, "modulate:a", 1.0, UNFOLD_TIME * 0.35)
	tween.tween_property(control, "scale:x", 1.0, UNFOLD_TIME * 0.45).set_trans(Tween.TRANS_CUBIC)
	tween.tween_property(control, "scale:y", 1.0, UNFOLD_TIME).set_trans(Tween.TRANS_BACK)


static func fade_in(control: Control) -> void:
	if not motion_enabled():
		return
	control.modulate.a = 0.0
	control.create_tween().tween_property(control, "modulate:a", 1.0, FADE_IN)
