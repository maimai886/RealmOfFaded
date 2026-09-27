extends Control
## 開機畫面，M1 換成登入；--shot=路徑 截圖後結束

const BACKGROUND := Color(0.07, 0.08, 0.1)
const TITLE_COLOR := Color(0.94, 0.93, 0.9)
const NOTE_COLOR := Color(0.62, 0.64, 0.68)


func _ready() -> void:
	var bg := ColorRect.new()
	bg.color = BACKGROUND
	bg.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(bg)

	var box := VBoxContainer.new()
	box.set_anchors_preset(Control.PRESET_CENTER)
	box.grow_horizontal = Control.GROW_DIRECTION_BOTH
	box.grow_vertical = Control.GROW_DIRECTION_BOTH
	box.add_theme_constant_override("separation", 12)
	add_child(box)

	var title := Label.new()
	title.text = "Realm of Faded"
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.add_theme_font_size_override("font_size", 48)
	title.add_theme_color_override("font_color", TITLE_COLOR)
	box.add_child(title)

	var note := Label.new()
	note.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	note.add_theme_font_size_override("font_size", 18)
	note.add_theme_color_override("font_color", NOTE_COLOR)
	if ClassDB.class_exists("RofInfo"):
		var info: RefCounted = ClassDB.instantiate("RofInfo")
		note.text = "rof-gdext %s　協定 %d　tick %d 毫秒" % [info.version(), info.protocol_version(), info.tick_ms()]
	else:
		note.text = "擴充沒有載進來"
	box.add_child(note)

	var shot := _arg("--shot=")
	if shot != "":
		_take_shot(shot)


func _take_shot(path: String) -> void:
	for i in 3:
		await get_tree().process_frame
	await RenderingServer.frame_post_draw
	var err := get_viewport().get_texture().get_image().save_png(path)
	print("截圖 ", path, " ", error_string(err))
	get_tree().quit(0 if err == OK else 1)


func _arg(prefix: String) -> String:
	for a in OS.get_cmdline_user_args() + OS.get_cmdline_args():
		if a.begins_with(prefix):
			return a.substr(prefix.length())
	return ""
