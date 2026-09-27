# Free Hit VFX - Slash Crimson (Godot 4)

A free, fully working sample from the Hit VFX Pack: one stylized crimson slash
impact effect, complete with source. Drag the scene into your level and it
plays, in the editor viewport and in game. No plugins, no autoloads.

This is the exact system used by the full pack, which contains 30 effects
built from 10 hand-drawn textures. If this one fits your game, the full pack
gives you the rest.

## Folder structure

```
FreeHitVfx/
├── README.md
├── scenes/hit_slash_crimson.tscn    drag and drop scene (main entry point)
├── presets/hit_slash_crimson.tres   all effect settings, Inspector-editable
├── core/                            the system
│   ├── free_hit_fx.gd               FreeHitFx node: builds and plays the effect
│   ├── free_hit_fx_preset.gd        preset resource (colors, layers, support FX)
│   ├── free_hit_fx_layer.gd         one texture layer definition
│   ├── hit_burst.gdshader           billboard burst shader (commented)
│   ├── impact_ring.gdshader         expanding shockwave ring shader
│   └── noise/spot textures          shared procedural resources
├── textures/t_stylizedhit_1.png     the hand-drawn slash texture (2K)
└── demo/dragdrop_example.tscn       the effect dropped into a lit scene
```

## Requirements

- Godot 4.x (built and tested on 4.7), Forward Plus renderer recommended
- Glow enabled in your WorldEnvironment for the intended look.
  The demo scene includes a pre-configured environment you can copy.
  Recommended: glow_hdr_threshold 1.5, glow_intensity 0.8, ACES tonemap.

## Quick start

Drag and drop: drop `scenes/hit_slash_crimson.tscn` into your scene.
It plays immediately and repeats. Inspector properties on the node:

- preset: the effect definition
- auto_play: play when the node enters the scene (default on)
- loop: replay after finishing (default on, great for previews)
- loop_rest: pause in seconds between repeats

One-shot at a hit point in gameplay:

```gdscript
var fx: FreeHitFx = preload("res://assets/vendor/free_hit_vfx/scenes/hit_slash_crimson.tscn").instantiate()
fx.loop = false
fx.one_shot_free = true
fx.position = hit_position
add_child(fx)
```

Or keep one node around and call `fx.play()` whenever you need it.

## Make it yours

Open `presets/hit_slash_crimson.tres` in the Inspector:

- color_core, color_main, color_accent: the full palette. Values above 1.0
  are intentional, they feed the glow. Change three colors and the crimson
  slash becomes frost, poison or gold.
- duration, flash_size, light_energy: overall feel
- layers: the slash layer itself. size, lifetime, spin, overshoot (pop
  punchiness), dissolve_amount, distortion, stretch, emission_energy.
  Keep emission_energy around 0.6 to 1.0; higher gets blown out by glow.

Any white-on-black texture works in the texture slot, so you can use your
own drawings with the same system.

## License

- Use in unlimited personal and commercial projects
- Modify freely, no attribution required
- Do not resell or redistribute the files themselves as an asset pack
- No NFT use, no use as training data for generative models

The full pack with all 30 effects is on the same store page account.
