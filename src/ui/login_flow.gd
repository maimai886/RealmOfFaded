extends Node3D
## 進遊戲前的四頁：登入、伺服器列表、選角、建角；只透過 autoload Rof 講話，進地圖後由 Rof 換場景

const UiTheme := preload("res://src/ui/ui_theme.gd")
const Texts := preload("res://src/ui/texts.gd")
const PreviewStage := preload("res://src/ui/preview_stage.gd")
const GameCursor := preload("res://src/ui/game_cursor.gd")

const DEFAULT_HOST := "127.0.0.1"
const DEFAULT_PORT := 7780
const LOGIN_CONFIG := "user://login.cfg"
const ORBIT_SPEED := 0.03
# 伺服器每個帳號每台三格，見 docs/M1舊行為.md 第 2 節
const SLOTS := 3
const START_JOB := "novice"
const JOB_ICON_SIZE := 16
const STATUS_COLORS := {"smooth": UiTheme.INK_GOOD, "busy": UiTheme.INK_WARN, "full": UiTheme.INK_BAD}
const SERVER_COLUMNS := [["name", 0], ["population", 108], ["status", 64], ["latency", 64], ["characters", 52]]
const GROWS := [Control.GROW_DIRECTION_END, Control.GROW_DIRECTION_BOTH, Control.GROW_DIRECTION_BEGIN]
# 每一塊的 [貼齊的位置 0 到 1, 大小, 位移]，桌機和手機各一組；手機邏輯畫面約 866×400
const BOXES := {
	"login": [[[Vector2(0.5, 0.5), Vector2(360, 240), Vector2(0, 40)]],
		[[Vector2(0.5, 0.5), Vector2(360, 240), Vector2(0, 12)]]],
	"servers": [[[Vector2(0.5, 0.5), Vector2(520, 330), Vector2(0, 30)]],
		[[Vector2(0.5, 0.5), Vector2(520, 330), Vector2.ZERO]]],
	"characters": [[[Vector2(0.5, 0.5), Vector2(700, 496), Vector2.ZERO]],
		[[Vector2(0.5, 0.5), Vector2(720, 384), Vector2.ZERO]]],
	"create": [
		[[Vector2(0.5, 0), Vector2(384, 434), Vector2(40, 66)], [Vector2(0, 0.5), Vector2(330, 392), Vector2(36, -14)],
			[Vector2(0.5, 1), Vector2(660, 112), Vector2(0, -24)]],
		[[Vector2(1, 0), Vector2(232, 200), Vector2(-12, 10)], [Vector2(0, 0.5), Vector2(288, 336), Vector2(12, -8)],
			[Vector2(1, 1), Vector2(516, 176), Vector2(-12, -10)]]],
}

@onready var _rof: Node = get_node_or_null("/root/Rof")
var _options: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/appearances.json"))["options"]
var _jobs: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/jobs.json"))
var _phone := false
var _ui: Control
var _pages := {}
var _current := ""
var _logo: Control
var _version: Label
var _pending := {}
var _login_after_connect := false
var _online := false
var _servers: Array = []
var _server_id := ""
var _latency_ms := -1
var _characters: Array = []
var _selected := -1
var _gender := "female"
var _appearance := {}

var _account_edit: LineEdit
var _password_edit: LineEdit
var _remember_check: CheckBox
var _login_message: Label
var _server_account: Label
var _server_rows: VBoxContainer
var _server_message: Label
var _slot_row: HBoxContainer
var _select_buttons: Array = []
var _character_info: GridContainer
var _character_message: Label
var _enter_button: Button
var _create_stage: PreviewStage
var _gender_buttons := {}
var _create_options: VBoxContainer
var _option_values := {}
var _name_edit: LineEdit
var _name_message: Label


func _ready() -> void:
	GameCursor.install()
	_fit_window()
	_build_ui()
	if _rof:
		_rof.connected.connect(_on_connected)
		_rof.disconnected.connect(_on_disconnected)
		_rof.replied.connect(_on_replied)
	var config := ConfigFile.new()
	if config.load(LOGIN_CONFIG) == OK and String(config.get_value("login", "account", "")) != "":
		_account_edit.text = config.get_value("login", "account")
		_remember_check.button_pressed = true
	_show_page("login", false)


func _process(delta: float) -> void:
	$Pivot.rotation.y += ORBIT_SPEED * delta


## 手機版面把邏輯高度縮到約 400，字和按鈕在小螢幕上才夠大
func _fit_window() -> void:
	var window := get_window()
	var size := Vector2(window.size)
	_phone = size.x < 900 or (OS.has_feature("mobile") and size.x / size.y > 16.0 / 9.0 + 0.02)
	if _phone:
		var logical := size / minf(size.x / window.content_scale_size.x, size.y / window.content_scale_size.y)
		window.content_scale_factor = minf(clampf(logical.y / 400.0, 1.0, 3.0), minf(logical.x / 560.0, logical.y / 320.0))


# ---- 連線 ----

func _send(type: String, data: Dictionary, done: Callable) -> void:
	if not _pending.is_empty():
		return
	var id: int = _rof.request(type, data) if _rof else 0
	if id <= 0:
		done.call(false, "not_connected", {})
		return
	_pending[id] = done


func _on_replied(id: int, ok: bool, reason: String, data: Dictionary) -> void:
	var done: Callable = _pending.get(id, Callable())
	_pending.erase(id)
	if done.is_valid():
		done.call(ok, reason, data)


func _on_connected() -> void:
	_online = true
	if _login_after_connect:
		_login_after_connect = false
		_do_login()


## 連不上只顯示原因，連上之後斷的才說連線中斷，自己登出的不顯示
func _on_disconnected(reason: String) -> void:
	var text := _reason(reason) if _login_after_connect else Texts.text("login.disconnected", {"reason": _reason(reason)})
	_show_message(_login_message, text if _online or _login_after_connect else "", UiTheme.INK_BAD)
	_pending.clear()
	_online = false
	_login_after_connect = false
	_show_page("login")


static func _reason(code: String) -> String:
	var key := "login.reason_" + code
	return Texts.text(key) if Texts.has(key) else Texts.text("login.reason_unknown", {"code": code})


func _server_address() -> Array:
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--server="):
			var parts := arg.trim_prefix("--server=").rsplit(":", true, 1)
			return [parts[0], int(parts[1])]
	return [DEFAULT_HOST, DEFAULT_PORT]


# ---- 共用元件 ----

func _build_ui() -> void:
	var layer := CanvasLayer.new()
	add_child(layer)
	_ui = Control.new()
	_ui.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_ui.theme = UiTheme.window_theme()
	_ui.mouse_filter = Control.MOUSE_FILTER_IGNORE
	layer.add_child(_ui)
	if OS.has_feature("mobile"):
		var safe := Rect2(DisplayServer.get_display_safe_area())
		var pixels := get_window().size.y / get_viewport().get_visible_rect().size.y
		_ui.offset_left = safe.position.x / pixels
		_ui.offset_top = safe.position.y / pixels
		_ui.offset_right = (safe.end.x - get_window().size.x) / pixels
		_ui.offset_bottom = (safe.end.y - get_window().size.y) / pixels
	# 草原壓一層暗色再壓暗角，視窗和文字才夠對比
	var dim := ColorRect.new()
	dim.color = Color(0.03, 0.04, 0.07, 0.34)
	var vignette := TextureRect.new()
	vignette.texture = UiTheme.skin_texture("vignette")
	vignette.stretch_mode = TextureRect.STRETCH_SCALE
	for cover: Control in [dim, vignette]:
		cover.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		cover.mouse_filter = Control.MOUSE_FILTER_IGNORE
		_ui.add_child(cover)
	_build_logo()
	_pages["login"] = _build_login_page()
	_pages["servers"] = _build_server_page()
	_pages["characters"] = _build_character_page()
	_pages["create"] = _build_create_page()
	_version = Label.new()
	_version.text = Texts.text("login.version", {"version": RofInfo.version()})
	_version.label_settings = UiTheme.overlay_settings(UiTheme.FONT_SMALL)
	_version.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	_version.set_anchors_preset(Control.PRESET_BOTTOM_RIGHT)
	_version.offset_left = -180
	_version.offset_top = -34
	_version.offset_right = -14
	_version.offset_bottom = -12
	_ui.add_child(_version)


func _build_logo() -> void:
	_logo = VBoxContainer.new()
	_logo.position = Vector2(24, 12) if _phone else Vector2(36, 18)
	_logo.add_theme_constant_override("separation", 6)
	_logo.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_ui.add_child(_logo)
	var title := Label.new()
	title.text = Texts.text("login.logo")
	var settings := LabelSettings.new()
	settings.font = UiTheme.font("logo")
	settings.font_size = 30 if _phone else 44
	settings.font_color = Color(1.0, 0.95, 0.82)
	# 細暗描邊加落影，背景怎麼轉都讀得到
	settings.outline_size = 3 if _phone else 5
	settings.outline_color = Color(0.10, 0.08, 0.05, 0.75)
	settings.shadow_size = 6
	settings.shadow_color = Color(0, 0, 0, 0.6)
	settings.shadow_offset = Vector2(0, 3)
	title.label_settings = settings
	_logo.add_child(title)
	var flourish := TextureRect.new()
	flourish.texture = UiTheme.skin_texture("logo_flourish")
	flourish.stretch_mode = TextureRect.STRETCH_KEEP
	flourish.modulate = Color(1.0, 0.95, 0.86, 0.95)
	_logo.add_child(flourish)


## 標題列加內容的視窗，回傳 [視窗, 內容容器]
func _window(title_key: String, width: int) -> Array:
	var panel := PanelContainer.new()
	panel.custom_minimum_size.x = width
	var frame: StyleBoxFlat = UiTheme.style("window").duplicate()
	frame.set_content_margin_all(1)
	panel.add_theme_stylebox_override("panel", frame)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 0)
	panel.add_child(column)
	var bar := PanelContainer.new()
	bar.add_theme_stylebox_override("panel", UiTheme.title_bar_style())
	bar.draw.connect(func(): UiTheme.draw_title_rule(bar))
	column.add_child(bar)
	var bar_row := HBoxContainer.new()
	bar_row.add_theme_constant_override("separation", 6)
	bar.add_child(bar_row)
	bar_row.add_child(_icon(UiTheme.skin_texture("emblem"), 16, Color(UiTheme.ACCENT, 0.95)))
	var title := Label.new()
	title.text = Texts.text(title_key)
	title.label_settings = LabelSettings.new()
	title.label_settings.font = UiTheme.font("window_title")
	title.label_settings.font_size = UiTheme.FONT_HEAD
	title.label_settings.font_color = UiTheme.TITLE_INK
	bar_row.add_child(title)
	var margin := MarginContainer.new()
	for side in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, UiTheme.PAD)
	margin.size_flags_vertical = Control.SIZE_EXPAND_FILL
	column.add_child(margin)
	var body := VBoxContainer.new()
	body.add_theme_constant_override("separation", UiTheme.GAP)
	margin.add_child(body)
	return [panel, body]


## 照 BOXES 貼齊畫面的某一邊；內容比盒子大時往貼齊的反方向長
func _place(panel: Control, page: Control, index: int) -> void:
	var box: Array = BOXES[String(page.name)][1 if _phone else 0][index]
	var anchor: Vector2 = box[0]
	var start: Vector2 = box[2] - box[1] * anchor
	panel.anchor_left = anchor.x
	panel.anchor_right = anchor.x
	panel.anchor_top = anchor.y
	panel.anchor_bottom = anchor.y
	panel.offset_left = start.x
	panel.offset_top = start.y
	panel.offset_right = start.x + box[1].x
	panel.offset_bottom = start.y + box[1].y
	panel.grow_horizontal = GROWS[int(anchor.x * 2)]
	panel.grow_vertical = GROWS[int(anchor.y * 2)]
	page.add_child(panel)


func _page(page_name: String) -> Control:
	var page := Control.new()
	page.name = page_name
	page.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	page.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_ui.add_child(page)
	return page


func _text(text: String, size := UiTheme.FONT_BODY, color := UiTheme.INK) -> Label:
	var label := Label.new()
	label.text = text
	label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	label.add_theme_font_size_override("font_size", size)
	label.add_theme_color_override("font_color", color)
	return label


func _button(key: String, callback: Callable, width := 0, accent := false) -> Button:
	var button := Button.new()
	button.text = Texts.text(key)
	button.custom_minimum_size = Vector2(width, 30)
	button.pressed.connect(callback)
	if accent:
		UiTheme.make_accent(button)
		# 每一頁只有一顆主要鈕，加大一眼看得出要按哪個
		button.custom_minimum_size.y = 36
		button.add_theme_font_size_override("font_size", UiTheme.FONT_HEAD)
	return button


func _icon(texture: Texture2D, size: int, color: Color) -> TextureRect:
	var rect := TextureRect.new()
	rect.texture = texture
	rect.custom_minimum_size = Vector2(size, size)
	rect.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	rect.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	rect.modulate = color
	rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return rect


func _spacer() -> Control:
	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	spacer.size_flags_vertical = Control.SIZE_EXPAND_FILL
	return spacer


func _row(parent: Control) -> HBoxContainer:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", UiTheme.GAP)
	parent.add_child(row)
	return row


func _clear(node: Node) -> void:
	for child in node.get_children():
		child.queue_free()


func _show_message(label: Label, text: String, color := UiTheme.INK_DIM) -> void:
	label.text = text
	label.add_theme_color_override("font_color", color)


func _show_page(page_name: String, animate := true) -> void:
	_current = page_name
	for key in _pages:
		_pages[key].visible = key == page_name
	# 手機畫面矮，標誌和版本號只在登入頁
	_logo.visible = not _phone or page_name == "login"
	_version.visible = _logo.visible
	if animate:
		UiTheme.fade_in(_pages[page_name])
		for panel in _pages[page_name].get_children():
			UiTheme.unfold(panel)
	if page_name == "login":
		(_password_edit if _account_edit.text != "" else _account_edit).grab_focus()


# ---- 登入 ----

func _build_login_page() -> Control:
	var page := _page("login")
	var parts := _window("login.title", 360)
	var body: VBoxContainer = parts[1]
	var fields := GridContainer.new()
	fields.columns = 2
	fields.add_theme_constant_override("h_separation", UiTheme.GAP)
	fields.add_theme_constant_override("v_separation", UiTheme.GAP)
	body.add_child(fields)
	_account_edit = _field(fields, "login.account", 16)
	_password_edit = _field(fields, "login.password", 64)
	_password_edit.secret = true
	_account_edit.text_submitted.connect(func(_text): _password_edit.grab_focus())
	_password_edit.text_submitted.connect(func(_text): _do_login())
	_remember_check = CheckBox.new()
	_remember_check.text = Texts.text("login.remember")
	_remember_check.add_theme_font_size_override("font_size", UiTheme.FONT_SMALL)
	body.add_child(_remember_check)
	_login_message = _text("", UiTheme.FONT_SMALL, UiTheme.INK_DIM)
	_login_message.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_login_message.custom_minimum_size.y = 32
	body.add_child(_login_message)
	var buttons := _row(body)
	buttons.add_child(_spacer())
	buttons.add_child(_button("login.submit", _do_login, 104, true))
	buttons.add_child(_button("login.quit", get_tree().quit, 64))
	_place(parts[0], page, 0)
	return page


func _field(grid: GridContainer, key: String, max_length: int) -> LineEdit:
	var label := _text(Texts.text(key))
	label.custom_minimum_size = Vector2(52, 28)
	grid.add_child(label)
	var edit := LineEdit.new()
	edit.max_length = max_length
	edit.custom_minimum_size = Vector2(250, 28)
	edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	grid.add_child(edit)
	return edit


func _do_login() -> void:
	if not _pending.is_empty() or _login_after_connect:
		return
	_show_message(_login_message, Texts.text("login.connecting"), UiTheme.INK_ACCENT)
	if _rof and not _online:
		_login_after_connect = true
		var address := _server_address()
		_rof.connect_server(address[0], address[1])
		return
	var account := _account_edit.text.strip_edges()
	_send("auth.login", {"account": account, "password": _password_edit.text}, func(ok, reason, data):
		if not ok:
			_show_message(_login_message, _reason(reason), UiTheme.INK_BAD)
			return
		var config := ConfigFile.new()
		config.set_value("login", "account", account if _remember_check.button_pressed else "")
		config.save(LOGIN_CONFIG)
		_show_message(_login_message, "")
		_server_account.text = Texts.text("server.account", {"account": data["account"]})
		_refresh_servers(func(): _show_page("servers")))


# ---- 伺服器列表 ----

func _build_server_page() -> Control:
	var page := _page("servers")
	var parts := _window("server.title", 520)
	var body: VBoxContainer = parts[1]
	_server_account = _text("", UiTheme.FONT_SMALL, UiTheme.INK_DIM)
	body.add_child(_server_account)
	# 標題和下面的列對齊，內框的邊框加內距是 5
	var header_margin := MarginContainer.new()
	header_margin.add_theme_constant_override("margin_left", 5)
	header_margin.add_theme_constant_override("margin_right", 5)
	body.add_child(header_margin)
	var header := _row(header_margin)
	for column in SERVER_COLUMNS:
		header.add_child(_column(Texts.text("server.column_" + column[0]), column[1], UiTheme.INK_DIM))
	var frame := PanelContainer.new()
	frame.add_theme_stylebox_override("panel", UiTheme.style("inset"))
	frame.custom_minimum_size.y = 140
	body.add_child(frame)
	_server_rows = VBoxContainer.new()
	_server_rows.add_theme_constant_override("separation", 2)
	frame.add_child(_server_rows)
	_server_message = _text("", UiTheme.FONT_SMALL, UiTheme.INK_DIM)
	_server_message.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_server_message.custom_minimum_size.y = 30
	body.add_child(_server_message)
	var buttons := _row(body)
	buttons.add_child(_button("server.refresh", _refresh_servers, 88))
	buttons.add_child(_spacer())
	buttons.add_child(_button("server.enter", _enter_server, 88, true))
	buttons.add_child(_button("server.logout", _logout, 64))
	_place(parts[0], page, 0)
	return page


## 延遲另外用 ping 量，列表本身要數人數，時間不準
func _refresh_servers(then := Callable()) -> void:
	_send("server.list", {}, func(ok, reason, data):
		_servers = data.get("servers", [])
		_show_message(_server_message, "" if ok else _reason(reason), UiTheme.INK_BAD)
		if _servers.all(func(server): return server["id"] != _server_id):
			_server_id = _servers[0]["id"] if not _servers.is_empty() else ""
		var started := Time.get_ticks_msec()
		_send("ping", {}, func(pinged, _reason_code, _data):
			_latency_ms = Time.get_ticks_msec() - started if pinged else -1
			_rebuild_server_rows()
			if then.is_valid():
				then.call()))


func _rebuild_server_rows() -> void:
	_clear(_server_rows)
	if _servers.is_empty():
		var empty := _text("　" + Texts.text("server.empty"), UiTheme.FONT_BODY, UiTheme.INK_DIM)
		empty.custom_minimum_size.y = 40
		_server_rows.add_child(empty)
	for server in _servers:
		var row := PanelContainer.new()
		row.custom_minimum_size.y = 34
		row.add_theme_stylebox_override("panel", UiTheme.style("select" if server["id"] == _server_id else "slot"))
		var line := _row(row)
		var status := String(server["status"])
		var latency_color := UiTheme.INK_GOOD if _latency_ms < 80 else UiTheme.INK_WARN if _latency_ms < 200 else UiTheme.INK_BAD
		line.add_child(_column(server["name"], 0, UiTheme.INK, UiTheme.FONT_BODY))
		line.add_child(_column(Texts.text("server.population", {"online": int(server["online"]), "capacity": int(server["capacity"])}), 108, UiTheme.INK))
		line.add_child(_column(Texts.text("server.status_" + status), 64, STATUS_COLORS.get(status, UiTheme.INK_DIM)))
		line.add_child(_column(Texts.text("server.latency", {"ms": _latency_ms}) if _latency_ms >= 0 else "—", 64,
				latency_color if _latency_ms >= 0 else UiTheme.INK_DIM))
		line.add_child(_column(Texts.text("server.characters", {"count": int(server["characters"])}), 52, UiTheme.INK_DIM))
		row.gui_input.connect(func(event: InputEvent):
			if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
				_server_id = server["id"]
				_rebuild_server_rows()
				if event.double_click:
					_enter_server())
		_server_rows.add_child(row)


## width 0 是吃掉剩下的寬度
func _column(text: String, width: int, color: Color, size := UiTheme.FONT_SMALL) -> Label:
	var label := _text(text, size, color)
	label.custom_minimum_size.x = width
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL if width == 0 else Control.SIZE_FILL
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return label


func _enter_server() -> void:
	if _server_id != "":
		_open_characters()


func _logout() -> void:
	_online = false
	_rof.disconnect_server()
	_show_page("login")


# ---- 選角 ----

func _build_character_page() -> Control:
	var page := _page("characters")
	var parts := _window("character.title", 700)
	var body: VBoxContainer = parts[1]
	_slot_row = _row(body)
	_slot_row.alignment = BoxContainer.ALIGNMENT_CENTER
	# 手機版左右鈕擺在格子兩側，這一列收起來省高度
	var pager := _row(body)
	pager.alignment = BoxContainer.ALIGNMENT_CENTER
	pager.visible = not _phone
	_select_buttons = [_button("ui.previous", _step_selection.bind(-1), 36),
		_button("ui.next", _step_selection.bind(1), 36)]
	for button in _select_buttons:
		pager.add_child(button)
	var info_frame := PanelContainer.new()
	info_frame.add_theme_stylebox_override("panel", UiTheme.style("inset"))
	body.add_child(info_frame)
	_character_info = GridContainer.new()
	_character_info.add_theme_constant_override("h_separation", 10)
	_character_info.add_theme_constant_override("v_separation", 4)
	info_frame.add_child(_character_info)
	_character_message = _text("", UiTheme.FONT_SMALL, UiTheme.INK_DIM)
	body.add_child(_character_message)
	body.add_child(_spacer())
	var buttons := _row(body)
	buttons.add_child(_button("character.back", _show_page.bind("servers"), 128))
	buttons.add_child(_spacer())
	buttons.add_child(_button("character.create", _open_create, 88))
	_enter_button = _button("character.enter", _enter_game, 112, true)
	buttons.add_child(_enter_button)
	_place(parts[0], page, 0)
	return page


func _open_characters(select_id := "") -> void:
	_send("char.list", {"server_id": _server_id}, func(ok, reason, data):
		if not ok:
			_show_message(_server_message, _reason(reason), UiTheme.INK_BAD)
			return
		_characters = data["characters"]
		_selected = maxi(0, _characters.find_custom(func(summary): return summary["id"] == select_id))
		_refresh_characters()
		_show_page("characters"))


## 在已經有的角色之間切換，到頭繞回另一邊；空格子有自己的建立鈕
func _step_selection(direction: int) -> void:
	if _characters.size() >= 2:
		_selected = posmod(_selected + direction, _characters.size())
		_refresh_characters()


func _refresh_characters() -> void:
	_clear(_slot_row)
	for button in _select_buttons:
		button.disabled = _characters.size() < 2
	var slot_size := Vector2(160, 150) if _phone else Vector2(216, 232)
	if _phone:
		_slot_row.add_child(_side_button("ui.previous", -1, slot_size.y))
	for index in maxi(SLOTS, _characters.size()):
		_slot_row.add_child(_character_slot(index, slot_size))
	if _phone:
		_slot_row.add_child(_side_button("ui.next", 1, slot_size.y))
	_enter_button.disabled = _characters.is_empty()
	_refresh_character_info()


func _side_button(key: String, direction: int, height: float) -> Button:
	var button := _button(key, _step_selection.bind(direction), 44)
	button.custom_minimum_size.y = height
	button.disabled = _characters.size() < 2
	return button


func _character_slot(index: int, slot_size: Vector2) -> Control:
	var slot := PanelContainer.new()
	slot.custom_minimum_size = slot_size
	slot.add_theme_stylebox_override("panel", UiTheme.style("select" if index == _selected else "slot"))
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 4)
	slot.add_child(column)
	if index >= _characters.size():
		var empty := _text(Texts.text("character.empty_slot"), UiTheme.FONT_SMALL, UiTheme.INK_DIM)
		empty.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		empty.size_flags_vertical = Control.SIZE_EXPAND_FILL
		column.add_child(empty)
		column.add_child(_button("character.create_slot", _open_create))
		return slot
	var summary: Dictionary = _characters[index]
	var stage := PreviewStage.new(Vector2(140, 88) if _phone else Vector2(196, 160))
	column.add_child(stage)
	stage.show_character(summary["gender"], summary["appearance"])
	var name_label := _text(summary["name"])
	name_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	column.add_child(name_label)
	var level_row := _row(column)
	level_row.alignment = BoxContainer.ALIGNMENT_CENTER
	level_row.add_theme_constant_override("separation", 4)
	level_row.add_child(_job_icon(summary["job_id"], UiTheme.INK_DIM))
	level_row.add_child(_text(Texts.text("character.level", {"level": int(summary["base_level"]),
			"job": _job_name(summary["job_id"])}), UiTheme.FONT_SMALL, UiTheme.INK_DIM))
	slot.gui_input.connect(func(event: InputEvent):
		if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
			_selected = index
			_refresh_characters()
			if event.double_click:
				_enter_game())
	return slot


func _refresh_character_info() -> void:
	_clear(_character_info)
	_show_message(_character_message, "")
	if _characters.is_empty():
		_character_info.columns = 1
		_character_info.add_child(_text(Texts.text("character.none"), UiTheme.FONT_BODY, UiTheme.INK_DIM))
		return
	_character_info.columns = 4
	var summary: Dictionary = _characters[_selected]
	# HP、SP、能力值等 M2 伺服器有數值再加
	var cells := [
		"character.name", summary["name"], "character.job", _job_name(summary["job_id"]),
		"character.base_level", str(int(summary["base_level"])), "character.job_level", str(int(summary["job_level"])),
		"character.map", _map_name(summary["map"]),
	]
	for i in range(0, cells.size(), 2):
		_character_info.add_child(_text(Texts.text(cells[i]), UiTheme.FONT_SMALL, UiTheme.INK_DIM))
		_character_info.add_child(_text(cells[i + 1]))


## JSON 的數字讀進來都是小數，顯示和送出前轉整數
func _integers(source: Dictionary, keys: Array) -> Dictionary:
	var result := {}
	for key in keys:
		result[key] = int(source.get(key, 0))
	return result


func _job_name(job_id: String) -> String:
	return _jobs.get(job_id, {}).get("name", job_id)


func _job_icon(job_id: String, color: Color) -> TextureRect:
	return _icon(load("res://assets/ui/icons/jobs/%s.png" % job_id), JOB_ICON_SIZE, color)


func _map_name(map_id: String) -> String:
	var map = JSON.parse_string(FileAccess.get_file_as_string("res://data/maps/%s.json" % map_id))
	return map["name"] if map is Dictionary else map_id


## 伺服器收到之後由 Rof 換到世界場景
func _enter_game() -> void:
	if _characters.is_empty():
		return
	_send("char.enter", {"character_id": _characters[_selected]["id"]}, func(ok, reason, _data):
		if not ok:
			_show_message(_character_message, _reason(reason), UiTheme.INK_BAD))


# ---- 建角 ----

func _build_create_page() -> Control:
	var page := _page("create")
	var stage_frame := PanelContainer.new()
	stage_frame.add_theme_stylebox_override("panel", UiTheme.style("inset"))
	_create_stage = PreviewStage.new(Vector2(216, 184) if _phone else Vector2(368, 418), 2.25, true)
	stage_frame.add_child(_create_stage)
	# 舞台左上角標出建出來的職業
	var badge := MarginContainer.new()
	badge.add_theme_constant_override("margin_left", UiTheme.PAD)
	badge.add_theme_constant_override("margin_top", UiTheme.PAD)
	badge.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	badge.size_flags_vertical = Control.SIZE_SHRINK_BEGIN
	badge.mouse_filter = Control.MOUSE_FILTER_IGNORE
	stage_frame.add_child(badge)
	var badge_row := _row(badge)
	badge_row.add_theme_constant_override("separation", 4)
	badge_row.add_child(_job_icon(START_JOB, UiTheme.INK))
	badge_row.add_child(_text(_job_name(START_JOB), UiTheme.FONT_SMALL))
	_place(stage_frame, page, 0)

	var option_parts := _window("create.title", 288 if _phone else 330)
	var options: VBoxContainer = option_parts[1]
	options.add_child(_text(Texts.text("create.gender"), UiTheme.FONT_SMALL, UiTheme.INK_DIM))
	var gender_row := _row(options)
	for gender in ["female", "male"]:
		var button := _button("create." + gender, _set_gender.bind(gender))
		button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		gender_row.add_child(button)
		_gender_buttons[gender] = button
	_create_options = VBoxContainer.new()
	_create_options.add_theme_constant_override("separation", UiTheme.GAP)
	options.add_child(_create_options)
	options.add_child(_spacer())
	options.add_child(_button("create.random", _randomize_appearance))
	_place(option_parts[0], page, 1)

	var name_parts := _window("create.name_title", 516 if _phone else 660)
	var name_body: VBoxContainer = name_parts[1]
	var name_row := _row(name_body)
	var name_label := _text(Texts.text("create.name"))
	name_label.custom_minimum_size = Vector2(52, 28)
	name_row.add_child(name_label)
	_name_edit = LineEdit.new()
	_name_edit.custom_minimum_size = Vector2(170 if _phone else 220, 28)
	_name_edit.max_length = 12
	_name_edit.text_changed.connect(func(_text): _show_message(_name_message, ""))
	_name_edit.text_submitted.connect(func(_text): _do_create())
	name_row.add_child(_name_edit)
	name_row.add_child(_spacer())
	name_row.add_child(_button("create.cancel", _show_page.bind("characters"), 80))
	name_row.add_child(_button("create.submit", _do_create, 112, true))
	_name_message = _text("", UiTheme.FONT_SMALL, UiTheme.INK_DIM)
	_name_message.custom_minimum_size.y = 18
	name_body.add_child(_name_message)
	_place(name_parts[0], page, 2)
	return page


func _open_create() -> void:
	_set_gender("female")
	_name_edit.text = ""
	_show_page("create")


## 換性別整組選項重建，男女的髮型和服裝不一樣
func _set_gender(gender: String) -> void:
	_gender = gender
	_appearance = _integers(_options["defaults"][gender], _options["keys"])
	for key in _gender_buttons:
		var button: Button = _gender_buttons[key]
		if key == gender:
			UiTheme.make_accent(button)
		else:
			for state in ["normal", "hover", "pressed", "hover_pressed"]:
				button.remove_theme_stylebox_override(state)
			for state in ["font_color", "font_hover_color", "font_pressed_color", "font_hover_pressed_color", "font_focus_color"]:
				button.remove_theme_color_override(state)
	_clear(_create_options)
	_option_values.clear()
	for key in _options["keys"]:
		if _option_names(key).size() <= 1:
			continue
		var row := _row(_create_options)
		var label := _text(_options["labels"][key], UiTheme.FONT_SMALL, UiTheme.INK_DIM)
		label.custom_minimum_size = Vector2(68, 28)
		row.add_child(label)
		row.add_child(_button("ui.previous", _step_option.bind(key, -1), 34))
		var value := _text("")
		value.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		value.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		row.add_child(value)
		row.add_child(_button("ui.next", _step_option.bind(key, 1), 34))
		_option_values[key] = value
	_refresh_create()


## 分性別的項目取該性別那組
func _option_names(key: String) -> Array:
	var list = _options[key]
	return (list[_gender] if list is Dictionary else list).map(func(option): return option["name"])


func _step_option(key: String, direction: int) -> void:
	_appearance[key] = posmod(_appearance[key] + direction, _option_names(key).size())
	_refresh_create()


func _randomize_appearance() -> void:
	for key in _option_values:
		_appearance[key] = randi() % _option_names(key).size()
	_refresh_create()


func _refresh_create() -> void:
	for key in _option_values:
		_option_values[key].text = _option_names(key)[_appearance[key]]
	_create_stage.show_character(_gender, _appearance)


## 名字合不合格、有沒有人用都由伺服器判斷
func _do_create() -> void:
	var data := {"server_id": _server_id, "name": _name_edit.text.strip_edges(), "gender": _gender,
		"appearance": _appearance.duplicate()}
	_send("char.create", data, func(ok, reason, reply):
		if not ok:
			_show_message(_name_message, _reason(reason), UiTheme.INK_BAD)
			return
		_open_characters(reply["character_id"]))


# ---- 鍵盤 ----

func _unhandled_key_input(event: InputEvent) -> void:
	var key := event as InputEventKey
	if not key.pressed or key.echo:
		return
	if _current == "characters" and key.keycode in [KEY_LEFT, KEY_RIGHT]:
		_step_selection(-1 if key.keycode == KEY_LEFT else 1)
	elif key.keycode in [KEY_ENTER, KEY_KP_ENTER]:
		{"login": _do_login, "servers": _enter_server, "characters": _enter_game, "create": _do_create}[_current].call()
	else:
		return
	get_viewport().set_input_as_handled()
