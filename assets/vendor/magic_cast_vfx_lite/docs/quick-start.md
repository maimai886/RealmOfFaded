# Quick start

## Run it
Open the project and press Play, or open `res://demo/dragdrop_example.tscn` and
hit F6.

## Use it in your game
Drag `addons/magic_cast_vfx_lite/scenes/cast_rune_circle.tscn` into your scene.
It plays immediately and loops. Node properties (Inspector): `preset`,
`auto_play`, `loop`, `loop_rest`.

One-shot at cast time:
```gdscript
var fx: FreeMagicFx = preload("res://assets/vendor/magic_cast_vfx_lite/scenes/cast_rune_circle.tscn").instantiate()
fx.loop = false
fx.one_shot_free = true
fx.position = cast_position
add_child(fx)
```

## The look
These are HDR/glow effects. Enable Glow in your `WorldEnvironment`
(`glow_hdr_threshold ≈ 1.5`, ACES tonemap), Forward Plus renderer. The demo
scene has a ready-made environment to copy.

## Make it yours
Open `addons/magic_cast_vfx_lite/presets/cast_rune_circle.tres`. Change
`color_core` / `color_main` / `color_accent` (values above 1.0 feed the glow),
or edit the layer stack: size, timing, spin, dissolve, sparks. Any
white-on-black texture works in a layer's texture slot.
