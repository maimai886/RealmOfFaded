# Quick start

Open the project and press Play, or open `res://demo/dragdrop_example.tscn` and hit F6.

Drag `addons/buff_pickup_vfx_lite/scenes/buff_levelup.tscn` into your scene. It plays
and loops. One-shot on a level-up / buff:
```gdscript
var fx: FreeBuffFx = preload("res://assets/vendor/buff_pickup_vfx_lite/scenes/buff_levelup.tscn").instantiate()
fx.loop = false
fx.one_shot_free = true
fx.position = unit_position
add_child(fx)
```

Enable Glow in your `WorldEnvironment` (`glow_hdr_threshold ≈ 1.5`, ACES), Forward Plus.
Edit `presets/buff_levelup.tres` . Three HDR colours reskin it. Any white-on-black
texture works in a layer slot.
