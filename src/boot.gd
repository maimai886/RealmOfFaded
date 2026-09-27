extends Control
## 開機畫面，M1 換成登入

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

