# Magic Cast VFX Lite (Godot 4)

A free, fully working sample from the **Magic Cast VFX** pack: one multi-layered
arcane **rune-circle** cast effect, complete with source. Open this project and
press **Play**, or copy `addons/magic_cast_vfx_lite/` into your own project and
drag `scenes/cast_rune_circle.tscn` into a scene. It plays in the editor and in
game. No autoloads, no dependencies.

This is the exact system the full pack uses: a smoke volume, the hero shape, a
cast ring, sparks and a light, all HDR-tuned for glow. Three colours in the
preset turn the arcane circle into fire, frost or gold.

## Install
Copy `addons/magic_cast_vfx_lite/` into your project's `res://addons/`. Enabling
the plugin under Project → Plugins is optional. The effect works either way.

## Requirements
- Godot 4.x (built and tested on 4.7), Forward Plus recommended
- Glow enabled in your `WorldEnvironment` (glow_hdr_threshold ≈ 1.5, ACES
  tonemap). Copy the environment from `demo/dragdrop_example.tscn`.

## Docs
- [Quick start](docs/quick-start.md)
- [Upgrading to the full pack](docs/upgrade.md)

## Upgrade
The full **Magic Cast VFX** pack adds five more effects: arcane nova, frost
bloom, holy flash, poison puff and heal halo, plus 10 reusable shape textures,
on the same store account.

## License
MIT, see [LICENSE](LICENSE). Use in unlimited personal and commercial projects.
