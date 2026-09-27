# Upgrading to the full pack

This lite pack is one effect (rune circle). The full **Magic Cast VFX** pack is
the same system with six effects and the full texture set.

| | Lite (this) | Magic Cast VFX |
|---|---|---|
| Effects | 1 (rune circle) | 6 (rune circle, arcane nova, frost bloom, holy flash, poison puff, heal halo) |
| Shape textures | 3 | 10 |
| System (shaders, ring, sparks, light) | ✓ | ✓ |
| Full source & presets | ✓ | ✓ |

## Moving up
The full pack ships under `addons/magic_cast_vfx/` (this one is
`addons/magic_cast_vfx_lite/`), so you can install both side by side without
class-name clashes. The lite classes are `FreeMagicFx*`, the full ones are
`MagicFx*`. When you're ready, just swap your scene references to the full pack's
`cast_*.tscn` scenes.

Get it on the same store account.
