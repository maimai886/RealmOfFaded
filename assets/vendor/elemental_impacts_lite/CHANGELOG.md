# Changelog

## 1.2.1 (2026-09-09)

Housekeeping. No change to how anything behaves.

- **The bundled INSTALLING.txt is correct again.** Its note on renderers listed which
  demo projects used which one, and that list went stale when every pack in the
  catalogue moved to declaring its renderer outright. It now says what is true.

## 1.2.0 (2026-08-22)

- **`spawn()` now puts the effect where you asked for it.** It takes a world
  position, which is what the docs pass it and what every caller means, but it
  was setting the local position before the node entered the tree. An effect
  spawned under any parent that was not sitting at the origin landed off by
  exactly that parent's transform, and the natural
  `Fx.spawn(preset, enemy, enemy.global_position)` landed at double the distance
  from the origin. If your parent node sits at the origin, nothing changes.
- **The core script no longer describes itself as the Magic pack.** It called
  itself a "Spell-cast effect" and told you to drag a scene out of
  `MagicCastVfx/scenes/`, a folder you do not have. It names this pack's own
  folder now.

## 1.1.0 (2026-08-10)

Safe to drop into a project you're already working on.

- **The download now unpacks into a single folder named after the pack.** Before
  this it put a `project.godot` at the top of the zip, so extracting it straight
  into a game you were already building could overwrite that game's name, its
  start-up scene and the list of add-ons you had switched on. It can't reach any
  of that now.
- **The demo and the self-test moved into their own folders inside the zip**, so
  two of these packs can sit in the same project without treading on each other.
- **New START-HERE.txt** at the top of the folder: what's in the download, plus a
  two-minute install. Plain text, no markdown reader needed.
- No change to any effect. The visuals and the presets are exactly as they were.

## 1.0.0 (2026-08-03)

Initial release.

- Free **fire impact** effect with full source.
- The exact `FreeElementalFx` system from the full pack: multi-layer billboard
  burst (smoke + hero shape + spark accent), impact ring, textured sparks and a
  real-time light, HDR-tuned for glow.
- Inspector-editable preset: three HDR colours reskin it.
- Pre-lit demo scene with a glow-ready `WorldEnvironment`.
- Built and tested on Godot 4.7.
