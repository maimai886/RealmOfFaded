# Elemental Impact VFX Lite (Godot 4)

A free, fully working sample from the **Elemental Impact VFX** pack: one
multi-layered **fire impact** effect, complete with source. Open this project
and press **Play**, or copy `addons/elemental_impacts_lite/` into your own
project and drag `scenes/elem_fire.tscn` into a scene. It plays in the editor
and in game. No autoloads, no dependencies.

This is the exact system the full pack uses: a smoke volume, the hero shape, an
impact ring, sparks and a light, all HDR-tuned for glow. Three colours in the
preset turn fire into ice, poison or gold.

## Install
Copy `addons/elemental_impacts_lite/` into your project's `res://addons/`.

## Requirements
- Godot 4.x (built and tested on 4.7), Forward Plus recommended
- Glow enabled in your `WorldEnvironment` (glow_hdr_threshold ≈ 1.5, ACES
  tonemap). Copy the environment from `demo/dragdrop_example.tscn`.

## Docs
- [Quick start](docs/quick-start.md)
- [Upgrading to the full pack](docs/upgrade.md)

## Upgrade
The full **Elemental Impact VFX** pack adds five more elements: ice, lightning,
earth, wind and water, plus 10 reusable shape textures, on the same store
account.

## License
MIT, see [LICENSE](LICENSE).
