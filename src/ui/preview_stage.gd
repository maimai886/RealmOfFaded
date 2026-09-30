extends PanelContainer
## 選角和捏角的角色預覽：自己一個 3D 世界，角色用擴充的 Actor；可以拖的舞台每拖一段轉 45 度，和 RO 的八方向一樣

const UiTheme := preload("res://src/ui/ui_theme.gd")
const DRAG_PIXELS := 42.0
# 長焦看全身；看身體中段偏下，腳底和頭頂在格子裡各留一點空
const CAMERA_FOV := 24.0
const LOOK_HEIGHT := 0.85
# 過了轉身門檻、不到走路門檻，站著面向那一方
const FACING_SPEED := 0.1

var _viewport := SubViewport.new()
var _actor: Node3D
var _key := ""
var _facing := 0
var _drag_x := 0.0
var _dragging := false


func _init(stage_size: Vector2, frame_height := 2.0, rotatable := false) -> void:
	custom_minimum_size = stage_size
	add_theme_stylebox_override("panel", UiTheme.stage_style())
	mouse_filter = Control.MOUSE_FILTER_STOP if rotatable else Control.MOUSE_FILTER_IGNORE
	var container := SubViewportContainer.new()
	container.stretch = true
	container.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(container)
	_viewport.own_world_3d = true
	_viewport.transparent_bg = true
	_viewport.msaa_3d = Viewport.MSAA_2X
	container.add_child(_viewport)
	var camera := Camera3D.new()
	camera.fov = CAMERA_FOV
	camera.position = Vector3(0, LOOK_HEIGHT, frame_height * 0.5 / tan(deg_to_rad(CAMERA_FOV) * 0.5))
	_viewport.add_child(camera)


func show_character(gender: String, appearance: Dictionary, job := "novice") -> void:
	var key := gender + job + JSON.stringify(appearance)
	if key == _key:
		return
	_key = key
	if _actor:
		_actor.queue_free()
	_actor = Actor.new()
	_viewport.add_child(_actor)
	_actor.setup(gender, job, appearance)
	_face()


func _face() -> void:
	var angle := -_facing * PI / 4.0
	_actor.set_motion(Vector2(sin(angle), cos(angle)) * FACING_SPEED, 0.0)


func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
		_dragging = event.pressed
		_drag_x = event.position.x
	elif event is InputEventMouseMotion and _dragging and absf(event.position.x - _drag_x) >= DRAG_PIXELS:
		_facing += 1 if event.position.x > _drag_x else -1
		_drag_x = event.position.x
		if _actor:
			_face()
