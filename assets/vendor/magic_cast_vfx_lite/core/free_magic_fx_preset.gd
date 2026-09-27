@tool
class_name FreeMagicFxPreset
extends Resource

## Full recipe for one spell-cast effect: colour palette, textured layers, and
## the support layers (flash, ring, motes, light).
## Colour components can exceed 1.0 (HDR) — that's what feeds the glow.

@export var fx_name: String = ""
@export var color_core: Color = Color(2.6, 2.3, 1.9)
@export var color_main: Color = Color(0.9, 0.7, 2.4)
@export var color_accent: Color = Color(0.4, 0.2, 1.6)
@export var duration: float = 0.9
@export var layers: Array[FreeMagicFxLayer] = []
@export var flash_size: float = 1.0
@export var ring_size: float = 0.0
@export var ring_lifetime: float = 0.45
@export var sparks_amount: int = 0
## Optional glint texture for the motes. Null falls back to the round spot.
@export var spark_texture: Texture2D
@export var spark_speed: float = 5.0
@export var spark_lifetime: float = 0.6
## Vertical accel on the motes. Negative falls (embers), positive rises (magic).
@export var spark_gravity: float = -3.5
@export var light_energy: float = 6.0
@export var light_range: float = 5.0
