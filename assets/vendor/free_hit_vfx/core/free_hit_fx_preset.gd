@tool
class_name FreeHitFxPreset
extends Resource

## Bir vuruş efektinin komple tarifi: renk paleti, texture katmanları ve
## destek katmanları (flash, halka, kıvılcım, ışık).
## Renk bileşenleri 1.0'ı aşabilir (HDR) — glow'u besler.

@export var fx_name: String = ""
@export var color_core: Color = Color(2.6, 2.3, 1.9)
@export var color_main: Color = Color(2.0, 0.9, 0.4)
@export var color_accent: Color = Color(1.3, 0.35, 0.2)
@export var duration: float = 0.9
@export var layers: Array[FreeHitFxLayer] = []
@export var flash_size: float = 1.0
@export var ring_size: float = 0.0
@export var ring_lifetime: float = 0.45
@export var sparks_amount: int = 0
@export var spark_speed: float = 5.0
@export var spark_lifetime: float = 0.6
@export var light_energy: float = 6.0
@export var light_range: float = 5.0
