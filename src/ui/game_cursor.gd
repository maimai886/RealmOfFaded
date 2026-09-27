extends RefCounted
## 遊戲的滑鼠游標：每個狀態佔一個 Godot 游標形狀，換狀態只換形狀；點地由擴充的 GroundPicker 換成 walk 或 blocked
## 用硬體游標，場景裡畫的圖一定慢半拍；圖和熱點由 art_pipeline/ui/cursors.py 產生

const DIR := "res://assets/ui/cursors/"
# 介面上的 Control 一律是箭頭，所以 pointer 放在 ARROW，滑到視窗上自動換回來
const SHAPES := {"pointer": Input.CURSOR_ARROW, "walk": Input.CURSOR_MOVE, "blocked": Input.CURSOR_FORBIDDEN}
# 2026-09-26 使用者說游標太小，介面倍率之外再放大 1.5 倍
const SIZE_BOOST := 1.5
const DESIGN_SIZE := 32.0
# 每 0.5 一階，拖視窗邊框時才不會每幀重傳圖；Godot 硬體游標上限 256 像素
const SCALE_STEP := 0.5
const SCALE_MAX := 4.0

static var _applied_scale := 0.0


static func install() -> void:
	if DisplayServer.get_name() == "headless":
		return
	var window := (Engine.get_main_loop() as SceneTree).root
	if not window.size_changed.is_connected(_refresh):
		window.size_changed.connect(_refresh)
	_refresh()


## 硬體游標不跟著 canvas_items 縮放，照介面實際倍率放大；macOS 自己會乘 Retina 倍率，要除回去
static func _refresh() -> void:
	var window := (Engine.get_main_loop() as SceneTree).root
	var ratio := Vector2(window.size) / Vector2(window.content_scale_size)
	var ui_scale := minf(ratio.x, ratio.y)
	ui_scale *= SIZE_BOOST / maxf(DisplayServer.screen_get_scale(window.current_screen), 1.0)
	var scale := clampf(snappedf(ui_scale, SCALE_STEP), 1.0, SCALE_MAX)
	if is_equal_approx(scale, _applied_scale):
		return
	_applied_scale = scale
	var table: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(DIR + "cursors.json"))
	for state in SHAPES:
		var image: Image = load(DIR + state + ".png").get_image()
		var factor := scale * DESIGN_SIZE / image.get_width()
		image.resize(roundi(image.get_width() * factor), roundi(image.get_height() * factor), Image.INTERPOLATE_LANCZOS)
		var hotspot: Array = table[state]["hotspot"]
		Input.set_custom_mouse_cursor(ImageTexture.create_from_image(image), SHAPES[state],
				Vector2(hotspot[0], hotspot[1]) * factor)
