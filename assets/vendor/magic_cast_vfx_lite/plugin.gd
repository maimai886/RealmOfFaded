@tool
extends EditorPlugin

## Content pack — the effect works as a plain scene, so there's no editor UI to
## register. This just lists the pack under Project > Plugins; nothing depends
## on it being enabled.

func _enter_tree() -> void:
	pass


func _exit_tree() -> void:
	pass
