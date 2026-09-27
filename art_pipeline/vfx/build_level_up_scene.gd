extends SceneTree
## 把升級翅膀的節點存成特效場景 assets/vfx/level_up_wings.tscn，之後在編輯器裡打開就能調
## 節點由 src/effects/angel_wings.gd 的 build_nodes 做，改了那裡要重跑這支
## 用法：godot --headless --path . --script res://art_pipeline/vfx/build_level_up_scene.gd

const AngelWings := preload("res://src/effects/angel_wings.gd")


func _init() -> void:
	var root: Node3D = AngelWings.new()
	root.name = "LevelUpWings"
	root.build_nodes()
	for child in root.get_children():
		child.owner = root
	var scene := PackedScene.new()
	var packed := scene.pack(root)
	if packed != OK:
		push_error("打包失敗 %s" % packed)
		quit(1)
		return
	var saved := ResourceSaver.save(scene, AngelWings.SCENE_PATH)
	print("[vfx] 存到 %s，結果 %s" % [AngelWings.SCENE_PATH, saved])
	root.free()
	quit(0 if saved == OK else 1)
