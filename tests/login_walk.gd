extends SceneTree
## 照玩法走一遍登入四頁：真的伺服器、真的帳號，照玩家的順序填字按鈕，每一頁截一張，最後進草原
## godot --path . --script res://tests/login_walk.gd -- --server=127.0.0.1:7812 --login=帳號:密碼 --name=角色名 --shot-dir=資料夾

const Texts := preload("res://src/ui/texts.gd")
const PAGE_TIMEOUT := 15.0
# 頁面展開動畫跑完才截
const SETTLE := 1.2

var _args := {}
var _login: Node
var _failures := 0


func _initialize() -> void:
	for arg in OS.get_cmdline_user_args():
		var pair := arg.trim_prefix("--").split("=", true, 1)
		_args[pair[0]] = pair[1] if pair.size() > 1 else ""
	change_scene_to_file("res://scenes/login.tscn")
	_run.call_deferred()


func _run() -> void:
	await create_timer(3.0).timeout
	_login = current_scene
	var account: PackedStringArray = String(_args.get("login", "victor01:victor1234")).split(":")
	_login._account_edit.text = account[0]
	_login._password_edit.text = account[1]
	await _shot("01_login_filled")
	_press("login.submit")
	await _expect("servers", "02_servers")
	_press("server.enter")
	await _expect("characters", "03_characters")
	_press("character.create")
	await _expect("create", "04_create")
	_login._name_edit.text = _args.get("name", "驗收員")
	_press("create.submit")
	await _expect("characters", "05_characters_created")
	_press("character.enter")
	var waited := 0.0
	while current_scene.scene_file_path != "res://scenes/world.tscn" and waited < PAGE_TIMEOUT:
		await create_timer(0.1).timeout
		waited += 0.1
	if waited >= PAGE_TIMEOUT:
		_fail("按進入遊戲之後沒有進草原")
	else:
		await create_timer(6.0).timeout
		await _shot("06_world")
	print("登入四頁 " + ("通過" if _failures == 0 else "失敗 %d 條" % _failures))
	quit(1 if _failures > 0 else 0)


## 只按目前那一頁看得到的按鈕，和玩家看到的一樣
func _press(key: String) -> void:
	var page: Control = _login._pages[_login._current]
	for button in page.find_children("*", "Button", true, false):
		if button.is_visible_in_tree() and not button.disabled and button.text == Texts.text(key):
			button.pressed.emit()
			return
	_fail("%s 頁找不到能按的「%s」" % [_login._current, Texts.text(key)])


func _expect(page: String, shot: String) -> void:
	var waited := 0.0
	while _login._current != page and waited < PAGE_TIMEOUT:
		await create_timer(0.1).timeout
		waited += 0.1
	if _login._current != page:
		_fail("等不到 %s 頁，停在 %s" % [page, _login._current])
	await create_timer(SETTLE).timeout
	await _shot(shot)


func _shot(shot: String) -> void:
	await RenderingServer.frame_post_draw
	var path := "%s/%s.png" % [_args.get("shot-dir", "user://"), shot]
	root.get_texture().get_image().save_png(path)
	print("截圖 ", path)


func _fail(message: String) -> void:
	_failures += 1
	push_error(message)
