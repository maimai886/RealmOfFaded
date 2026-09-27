# Quick start

## Run it
Open the project and press Play, or open `res://demo/dragdrop_example.tscn` and
hit F6.

## Use it in your game
Drag `addons/elemental_impacts_lite/scenes/elem_fire.tscn` into your scene. It
plays immediately and loops. Node properties: `preset`, `auto_play`, `loop`,
`loop_rest`.

One-shot at impact:
```gdscript
var fx: FreeElementalFx = preload("res://assets/vendor/elemental_impacts_lite/scenes/elem_fire.tscn").instantiate()
fx.loop = false
fx.one_shot_free = true
fx.position = hit_position
add_child(fx)
```

## The look
Enable Glow in your `WorldEnvironment` (`glow_hdr_threshold ≈ 1.5`, ACES
tonemap), Forward Plus renderer. The demo scene has a ready-made environment.

## Make it yours
Open `addons/elemental_impacts_lite/presets/elem_fire.tres` and change
`color_core` / `color_main` / `color_accent`, or edit the layer stack. Any
white-on-black texture works in a layer's texture slot.
