@tool
class_name FreeMagicFxLayer
extends Resource

## One textured billboard layer of a cast effect. All the per-layer knobs the
## burst shader reads: which shape, how big, when, how it grows and dissolves.

@export var texture: Texture2D
@export var size: float = 1.6
@export var delay: float = 0.0
@export var lifetime: float = 0.5
@export var spin: float = 0.0
@export var random_angle: bool = true
@export var scale_from: float = 0.4
@export var scale_to: float = 1.0
@export var overshoot: float = 1.7
@export var use_hot_start: bool = true
@export_range(0.0, 1.0) var dissolve_amount: float = 1.0
@export_range(0.0, 0.6) var distortion: float = 0.0
@export var stretch: Vector2 = Vector2.ONE
@export var emission_energy: float = 2.6
