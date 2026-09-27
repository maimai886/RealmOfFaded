@tool
extends VFXEmitterBB
class_name VFXDarkProjectileBB

var light : VFXOmniLightBB:
	get():
		if light:
			return light
		
		var result = get_node_or_null("VFXOmniLightBB")
		
		if !Engine.is_editor_hint():
			light = result
		
		return result

var audio_stream_player : AudioStreamPlayer3D:
	get():
		if audio_stream_player:
			return audio_stream_player
		
		var result = get_node_or_null("AudioStreamPlayer3D")
		
		if !Engine.is_editor_hint():
			audio_stream_player = result
		
		return result



@export_group("Color")

## Main color of this effect
@export var primary_color : Color:
	set(v):
		primary_color = v
		_set_shader_param("primary_color", primary_color)

## Secondary color of this effect. Essentially the color that [code]primary_color[/code] fades into.
@export var secondary_color : Color:
	set(v):
		secondary_color = v
		_set_shader_param("secondary_color", secondary_color)

@export var emission : float = 4.0:
	set(v):
		emission = v
		_set_shader_param("emission", emission)



@export_group("Light")

## Color of the emitted light of this effect
@export var light_color : Color:
	set(v):
		light_color = v
		if light: light.light_color = light_color

## Multiplier for the strength of the light
@export var light_energy : float = 4.0:
	set(v):
		light_energy = v
		if light: light.vfx_light_energy = light_energy

## Secondary multiplier for light_energy regarding indirect light
@export var light_indirect_energy : float = 1.0:
	set(v):
		light_indirect_energy = v
		if light: light.vfx_indirect_energy = light_indirect_energy

## Secondary multiplier for light_energy in volumetric fog
@export var light_volumetric_fog_energy : float = 1.0:
	set(v):
		light_volumetric_fog_energy = v
		if light: light.vfx_volumetric_fog_energy = light_volumetric_fog_energy



@export_group("Shape")

## Noise texture used in all the components of the effect
@export var noise_texture : Texture2D:
	set(v):
		noise_texture = v
		_set_shader_param("noise_texture", noise_texture)

## Multiplier used to scale the noise texture
@export var noise_scale : Vector2 = Vector2(1.0, 1.0):
	set(v):
		noise_scale = v
		_set_shader_param("noise_scale", noise_scale)

## Scroll direction and speed of the noise
@export var noise_scroll : Vector2 = Vector2(0.0, 0.2):
	set(v):
		noise_scroll = v
		_set_shader_param("noise_scroll", noise_scroll)

## Exponent used on the noise texture
@export_exp_easing("inout") var noise_shape : float = 1.0:
	set(v):
		noise_shape = v
		_set_shader_param("noise_shape", noise_shape)

## Strength of the wave effect applied to the noise texture
@export_range(0.0, 1.0, 0.05) var wave_strength : float = 0.5:
	set(v):
		wave_strength = v
		_set_shader_param("wave_strength", wave_strength)

## Frequency of the wave effect applied to the noise texture
@export var wave_frequency : float = 5.0:
	set(v):
		wave_frequency = v
		_set_shader_param("wave_frequency", wave_frequency)



@export_group("Transparency")

## Position of the transparency edge
@export_range(0.0, 1.0, 0.01) var edge_position : float = 0.05:
	set(v):
		edge_position = v
		_set_shader_param("edge_position", edge_position)

## Hardness of the edge of the transparency. Also affects hardness of the edges in colors
@export_range(0.0, 1.0, 0.01) var edge_hardness : float = 0.0:
	set(v):
		edge_hardness = v
		_set_shader_param("edge_hardness", edge_hardness)





@export_group("Audio")

## Audio stream used for the effect. Other audio related settings are the same as with AudioStreamPlayer3D
@export var audio_stream : AudioStream:
	set(v):
		audio_stream = v
		if audio_stream_player: audio_stream_player.stream = audio_stream

@export var attenuation_model : AudioStreamPlayer3D.AttenuationModel:
	set(v):
		attenuation_model = v
		if audio_stream_player: audio_stream_player.attenuation_model = attenuation_model

var volume_animation : float = 1.0:
	set(v):
		volume_animation = v
		if audio_stream_player: audio_stream_player.volume_db = lerpf(-24.0, volume_db, volume_animation)

## When enabled, will fade audio based on VFXEmitterBB parameter [code]emitting[/code]
## Does not affect [code]audio_playing[/code]
@export var animate_volume : bool = true

@export_range(-80.0, 80.0, 0.01, "suffix:dB") var volume_db : float = 0.0:
	set(v):
		volume_db = v
		if audio_stream_player: audio_stream_player.volume_db = lerpf(-24.0, volume_db, volume_animation)

@export_range(0.1, 100.0, 0.01) var unit_size : float = 10.0:
	set(v):
		unit_size = v
		if audio_stream_player: audio_stream_player.unit_size = unit_size

@export_range(-24.0, 6.0, 0.01, "suffix:dB") var max_db : float = 3.0:
	set(v):
		max_db = v
		if audio_stream_player: audio_stream_player.max_db = max_db

@export_range(0.01, 4.0, 0.01) var pitch_scale : float = 1.0:
	set(v):
		pitch_scale = v
		if audio_stream_player: audio_stream_player.pitch_scale = pitch_scale

@export var audio_playing : bool = false:
	set(v):
		audio_playing = v
		if audio_stream_player: audio_stream_player.playing = audio_playing

@export var autoplay : bool = false:
	set(v):
		autoplay = v
		if audio_stream_player: audio_stream_player.autoplay = autoplay

@export var stream_paused : bool = false:
	set(v):
		stream_paused = v
		if audio_stream_player: audio_stream_player.stream_paused = stream_paused

@export_range(0.0, 2000.0, 0.01, "suffix:m") var audio_max_distance : float = 3.0:
	set(v):
		audio_max_distance = v
		if audio_stream_player: audio_stream_player.max_distance = audio_max_distance

@export var max_polyphony : int = 1:
	set(v):
		max_polyphony = v
		if audio_stream_player: audio_stream_player.max_polyphony = max_polyphony

@export_range(0.0, 3.0, 0.01) var panning_strength : float = 1.0:
	set(v):
		panning_strength = v
		if audio_stream_player: audio_stream_player.panning_strength = panning_strength

@export var bus : StringName = &"Master":
	set(v):
		bus = v
		if audio_stream_player: audio_stream_player.bus = bus
