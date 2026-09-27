@tool
extends VFXEmitterBB

@export_group("Color")

## The primary color of this effect.
@export var primary_color : Color:
	set(v):
		primary_color = v
		_set_shader_param("primary_color", primary_color)

## The secondary color of this effect.
@export var secondary_color : Color:
	set(v):
		secondary_color = v
		_set_shader_param("secondary_color", secondary_color)

## The secondary color of this effect.
@export var tertiary_color : Color:
	set(v):
		tertiary_color = v
		_set_shader_param("tertiary_color", tertiary_color)

## Emission of the effect. Higher values make it glowy.
@export var emission : float = 2.0:
	set(v):
		emission = v
		_set_shader_param("emission", emission)

## Controls the curve of the transition from [code]primary_color[/code] to [code]secondary_color[/code]
@export_exp_easing("inout") var color_curve : float = 1.0:
	set(v):
		color_curve = v
		_set_shader_param("color_curve", color_curve)

## Variation in hue on the colors of this effect
@export var hue_variation : float = 0.1:
	set(v):
		hue_variation = v
		_set_shader_param("hue_variation", hue_variation)


@export_group("Shape")

## The noise texture that's used for the shape of this effect.
@export var noise_texture : Texture2D:
	set(v):
		noise_texture = v
		_set_shader_param("noise_texture", noise_texture)

## Value used to scale the [code]noise_texture[/code]. Higher values make the noise more zoomed out.
## [br][br]
## Note that scales smaller than 1.0 can have hard edges
@export var noise_scale : Vector2 = Vector2(0.5,0.5):
	set(v):
		noise_scale = v
		_set_shader_param("noise_scale", noise_scale)

## The speed at which the [code]noise_texture[/code] moves.
@export var noise_scroll : Vector2 = Vector2(0.0,0.1):
	set(v):
		noise_scroll = v
		_set_shader_param("noise_scroll", noise_scroll)

## The exponent used on the noise shape
@export_exp_easing("inout") var shape_curve : float = 2.0:
	set(v):
		shape_curve = v
		_set_shader_param("shape_curve", shape_curve)

## Waviness of the effects aura
@export_range(0.0, 1.0, 0.01) var waviness : float = 0.2:
	set(v):
		waviness = v
		_set_shader_param("waviness", waviness)


@export_group("Particles")

## Amount of particles used by this effect.
@export var particles_amount : int = 32:
	set(v):
		particles_amount = v
		_set_particle_param("amount", particles_amount)

## Lifetime of the flame particles.
## [br][br]
## Increasing this will make the flames go higher.
@export var lifetime : float = 2.0:
	set(v):
		lifetime = v
		_set_particle_param("lifetime", lifetime)

## Explosiveness of the flame particles.
@export_range(0.0, 1.0, 0.01) var explosiveness : float = 0.0:
	set(v):
		explosiveness = v
		_set_shader_param("explosiveness", explosiveness)

## Scale of the emission shape of the particles
@export var emission_shape : Vector3 = Vector3(0.5, 1.0, 0.5):
	set(v):
		emission_shape = v
		for p in particles:
			p.process_material.emission_shape_scale = emission_shape

@export_custom(PROPERTY_HINT_NONE, "suffix:FPS") var particles_fps : int = 60:
	set(v):
		particles_fps = v
		_set_particle_param("fixed_fps", particles_fps)

## Orbital velocity of the particles
@export var particles_orbit : float = 0.3:
	set(v):
		particles_orbit = v
		for p in particles:
			p.process_material.orbit_velocity = Vector2(-particles_orbit, particles_orbit)

## Radial acceleration of the particles
@export var particles_radial : float  = 0.2:
	set(v):
		particles_radial = v
		for p in particles:
			p.process_material.radial_accel = Vector2(particles_radial, particles_radial)

## Vertical acceleration of the particles
@export var particles_vertical : float = 0.4:
	set(v):
		particles_vertical = v
		for p in particles:
			p.process_material.gravity = Vector3(0.0, particles_vertical, 0.0)





@export_group("Transparency")

## Hardness of the edges of each part of this effect
@export_range(0.0, 1.0, 0.01) var edge_hardness : float = 0.0:
	set(v):
		edge_hardness = v
		_set_shader_param("edge_hardness", edge_hardness)

## Cutoff of the hard edges
@export_range(0.0, 1.0, 0.01) var edge_position : float = 0.0:
	set(v):
		edge_position = v
		_set_shader_param("edge_position", edge_position)

@export var proximity_fade : bool = true:
	set(v):
		proximity_fade = v
		_set_shader_param("proximity_fade", proximity_fade)

@export var proximity_fade_distance : float = 1.0:
	set(v):
		proximity_fade_distance = v
		_set_shader_param("proximity_fade_distance", proximity_fade_distance)
