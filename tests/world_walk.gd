extends SceneTree
## 照玩法走一遍草原：滑鼠掃過地面、點樹後面繞過去、邊走邊換目標和按住拖著走，量有沒有被拉回、幀率多少
## godot --path . --script res://tests/world_walk.gd -- --server=127.0.0.1:7812 --dev-login=帳號:密碼 --dev-character=名字 --shot-dir=資料夾
## 要用新帳號，角色才在出生點；視窗別蓋住自己的滑鼠，真的滑鼠會蓋掉假的；加 --watch=秒 只站著看別人，每 3 秒截一張

const SPEED := 3.5
const SPAWN := Vector3(4, 0, -39)
# 樹在 meadow.json 的 [-2.87, -34.19]，擋路半邊 0.76 × 1.08 × 0.8862
const TREE := Vector2(-2.87, -34.19)
const TREE_HALF := 0.727
const BEHIND_TREE := Vector3(-4.24, 0, -33.23)
const RETARGETS := [Vector3(1, 0, -30), Vector3(4, 0, -28.5), Vector3(6, 0, -25)]
const DRAG_FROM := Vector3(6, 0, -25)
const DRAG_TO := Vector3(2, 0, -21)
const FAR := Vector3(-10, 0, 0)

var _args := {}
var _world: Node
var _me: Node3D
var _failures := 0
var _track: Array = []


func _initialize() -> void:
	for arg in OS.get_cmdline_user_args():
		var pair := arg.trim_prefix("--").split("=", true, 1)
		_args[pair[0]] = pair[1] if pair.size() > 1 else ""
	_run.call_deferred()


func _run() -> void:
	var waited := 0.0
	while (current_scene == null or current_scene.scene_file_path != "res://scenes/world.tscn") and waited < 20.0:
		await create_timer(0.1).timeout
		waited += 0.1
	if waited >= 20.0:
		return _finish("20 秒內沒有進草原")
	_world = current_scene
	await create_timer(2.0).timeout
	_me = _actors()[0]
	if _args.has("watch"):
		for i in int(_args["watch"]) / 3:
			await create_timer(3.0).timeout
			await _shot("watch_%d" % i)
			print("看到別人 ", _actors().size() - 1, " 個：", _actors().slice(1).map(func(a): return a.position))
		return _finish("")
	if _me.position.distance_to(SPAWN) > 0.5:
		return _finish("角色不在出生點，換一個新帳號")
	await _hover_sweep()
	await _walk_around_tree()
	await _retarget_while_walking()
	await _measure("站著", func(): pass)
	await _measure("走路", func(): _click(FAR))
	print("看到別人 ", _actors().size() - 1, " 個")
	_finish("")


func _actors() -> Array:
	return _world.get_children().filter(func(n): return n.get_class() == "Actor")


## 滑鼠一幀一格掃過玩家周圍的地面，游標格子每換一格世界就問一次能不能走
func _hover_sweep() -> void:
	for i in 120:
		var angle := i * TAU / 60.0
		_move_mouse(_me.position + Vector3(cos(angle), 0, sin(angle)) * (1.0 + i * 0.06))
		await process_frame
	_move_mouse(Vector3(TREE.x, 0, TREE.y))
	await create_timer(0.3).timeout
	await _shot("07_hover_blocked_tree")


func _walk_around_tree() -> void:
	_click(BEHIND_TREE)
	await _follow(0.8)
	await _shot("08_walking_around_tree")
	await _follow(6.0, true)
	await _shot("09_behind_tree")
	var inside := _track.filter(func(p): return absf(p.x - TREE.x) < TREE_HALF and absf(p.z - TREE.y) < TREE_HALF)
	var end: Vector3 = _me.position
	print("繞樹：終點 ", end, " 離目標 ", end.distance_to(BEHIND_TREE), " 公尺，穿進樹裡 ", inside.size(), " 幀")
	if not inside.is_empty() or end.distance_to(BEHIND_TREE) > 0.3:
		_failures += 1
		push_error("繞樹失敗")


## 走到一半換目標三次，再按住左鍵拖著走；每幀記位置，往回跳或快過跑速就是被拉回
func _retarget_while_walking() -> void:
	_track.clear()
	for target in RETARGETS:
		_click(target)
		await _follow(0.45)
	await _follow(4.0, true)
	_press(DRAG_FROM, true)
	for i in 60:
		_move_mouse(DRAG_FROM.lerp(DRAG_TO, i / 59.0))
		await _follow(1.0 / 60.0)
	_press(DRAG_TO, false)
	await _follow(5.0, true)
	await _shot("10_after_retarget")
	var backward := 0
	var too_fast := 0
	var worst := 0.0
	for i in range(2, _track.size()):
		var step: Vector3 = _track[i] - _track[i - 1]
		var last: Vector3 = _track[i - 1] - _track[i - 2]
		if step.length() > 0.004 and last.length() > 0.004 and step.dot(last) < 0:
			backward += 1
			worst = maxf(worst, step.length())
		if step.length() > SPEED / 30.0:
			too_fast += 1
	print("換目標：%d 幀，往回跳 %d 幀、最大 %.3f 公尺，一幀走超過 %.3f 公尺 %d 幀" % [_track.size(), backward, worst, SPEED / 30.0, too_fast])
	if backward > 0 or too_fast > 0:
		_failures += 1
		push_error("走路被拉回")


## until_still 為真時等到連續 0.3 秒沒動才停
func _follow(seconds: float, until_still := false) -> void:
	var still := 0.0
	var time := 0.0
	while time < seconds:
		await process_frame
		var delta := get_root().get_process_delta_time()
		time += delta
		var moved: bool = _track.is_empty() or _track[-1].distance_to(_me.position) > 0.0005
		_track.append(_me.position)
		still = 0.0 if moved else still + delta
		if until_still and still > 0.3:
			return


func _measure(label: String, start: Callable) -> void:
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	var viewport := root.get_viewport_rid()
	RenderingServer.viewport_set_measure_render_time(viewport, true)
	start.call()
	await create_timer(0.5).timeout
	var frames: Array = []
	var gpu := 0.0
	var time := 0.0
	while time < 4.0:
		await process_frame
		var delta := root.get_process_delta_time()
		time += delta
		frames.append(delta * 1000.0)
		gpu += RenderingServer.viewport_get_measured_render_time_gpu(viewport)
	frames.sort()
	var average: float = frames.reduce(func(a, b): return a + b) / frames.size()
	print("%s：平均 %.0f fps、%.2f 毫秒，最慢 1%% %.2f 毫秒，GPU %.2f 毫秒，繪製呼叫 %d，腳本 %.2f 毫秒" % [label,
		1000.0 / average, average, frames[int(frames.size() * 0.99)], gpu / frames.size(),
		Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME),
		Performance.get_monitor(Performance.TIME_PROCESS) * 1000.0])
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_ENABLED)


func _screen(point: Vector3) -> Vector2:
	return root.get_viewport().get_camera_3d().unproject_position(point)


func _move_mouse(point: Vector3) -> void:
	var motion := InputEventMouseMotion.new()
	# Godot 換游標形狀時會用 global_position 補發一則移動，沒設會跳到左上角
	motion.position = _screen(point)
	motion.global_position = motion.position
	Input.parse_input_event(motion)


func _press(point: Vector3, down: bool) -> void:
	_move_mouse(point)
	var button := InputEventMouseButton.new()
	button.position = _screen(point)
	button.global_position = button.position
	button.button_index = MOUSE_BUTTON_LEFT
	button.pressed = down
	Input.parse_input_event(button)


func _click(point: Vector3) -> void:
	_press(point, true)
	await process_frame
	await process_frame
	_press(point, false)


func _shot(shot: String) -> void:
	await RenderingServer.frame_post_draw
	var path := "%s/%s%s.png" % [_args.get("shot-dir", "user://"), _args.get("shot-prefix", ""), shot]
	root.get_texture().get_image().save_png(path)
	print("截圖 ", path)


func _finish(error: String) -> void:
	if error != "":
		_failures += 1
		push_error(error)
	print("草原走一遍 " + ("通過" if _failures == 0 else "失敗 %d 條" % _failures))
	quit(1 if _failures > 0 else 0)
