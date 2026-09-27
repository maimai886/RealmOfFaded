@tool
class_name FreeMagicFx
extends Node3D

## Spell-cast effect. Two ways to use it:
##
## 1) DRAG & DROP: drag a .tscn from addons/magic_cast_vfx_lite/scenes/ into your scene.
##    Plays automatically in the editor and in game, repeats when done (loop).
##    auto_play / loop / loop_rest are set in the Inspector.
##
## 2) FROM CODE (one-shot at cast time):
##    FreeMagicFx.spawn(preset, parent, pos)
##    or instantiate the scene and set `one_shot_free = true` — it plays once
##    and frees itself.

const BURST_SHADER := preload("res://assets/vendor/magic_cast_vfx_lite/core/magic_burst.gdshader")
const RING_SHADER := preload("res://assets/vendor/magic_cast_vfx_lite/core/magic_ring.gdshader")
const NOISE_FBM := preload("res://assets/vendor/magic_cast_vfx_lite/core/noise_fbm.tres")
const NOISE_SOFT := preload("res://assets/vendor/magic_cast_vfx_lite/core/noise_soft.tres")
const SPOT_TEX := preload("res://assets/vendor/magic_cast_vfx_lite/core/spot_texture.tres")

@export var preset: FreeMagicFxPreset
@export var auto_play := true
@export var loop := true
@export_range(0.0, 5.0) var loop_rest := 0.6

## When true, plays once then frees itself (spawn() turns this on).
var one_shot_free := false

var _t := 0.0
var _playing := false
var _rest_left := 0.0
var _bursts: Array[Dictionary] = []
var _built: Array[Node] = []
var _ring_mat: ShaderMaterial
var _light: OmniLight3D


static func spawn(p: FreeMagicFxPreset, parent: Node, pos: Vector3) -> FreeMagicFx:
	var fx := FreeMagicFx.new()
	fx.preset = p
	fx.auto_play = true
	fx.loop = false
	fx.one_shot_free = true
	parent.add_child(fx)
	# pos is a world position. That is what the docs pass it (hit_position)
	# and what every caller means. Setting `position` before add_child made
	# it local instead, so an effect spawned under anything that wasn't
	# sitting at the origin landed off by the parent's transform, and
	# spawn(p, enemy, enemy.global_position) landed at double the distance.
	fx.global_position = pos
	return fx


func _ready() -> void:
	if auto_play and preset:
		play()


## (Re)plays the effect. Layers are rebuilt each call; random angles make every
## repeat look a little different.
func play() -> void:
	if preset == null:
		return
	_clear_all()
	_build()
	_t = 0.0
	_rest_left = 0.0
	_playing = true


func _process(delta: float) -> void:
	if not _playing:
		if _rest_left > 0.0:
			_rest_left -= delta
			if _rest_left <= 0.0:
				play()
		return

	_t += delta
	for b in _bursts:
		var p: float = clampf((_t - b.delay) / b.life, 0.0, 1.0)
		var mat: ShaderMaterial = b.mat
		mat.set_shader_parameter("progress", p)
		var node: MeshInstance3D = b.node
		node.visible = _t >= b.delay
		var s: float = lerpf(b.from, b.to, _ease_pop(p, b.pop))
		node.scale = Vector3.ONE * maxf(s, 0.01)
	if _ring_mat:
		_ring_mat.set_shader_parameter("progress", clampf(_t / preset.ring_lifetime, 0.0, 1.0))
	if _light:
		_light.light_energy = preset.light_energy * 0.38 * exp(-_t * 8.0)

	if _t >= preset.duration + 0.4:
		_playing = false
		if one_shot_free and not Engine.is_editor_hint():
			queue_free()
		elif loop or Engine.is_editor_hint():
			_clear_all()
			_rest_left = maxf(loop_rest, 0.05)
		else:
			_clear_all()


func _clear_all() -> void:
	for n in _built:
		if is_instance_valid(n):
			n.queue_free()
	_built.clear()
	_bursts.clear()
	_ring_mat = null
	_light = null


func _build() -> void:
	if preset.flash_size > 0.0:
		var flash := FreeMagicFxLayer.new()
		flash.texture = SPOT_TEX
		flash.size = preset.flash_size * 0.65
		flash.lifetime = 0.11
		flash.scale_from = 0.5
		flash.scale_to = 1.1
		flash.overshoot = 0.0
		flash.dissolve_amount = 0.0
		flash.emission_energy = 0.9
		flash.random_angle = false
		_add_burst(flash)

	for l in preset.layers:
		_add_burst(l)

	if preset.ring_size > 0.0:
		_add_ring()
	if preset.sparks_amount > 0:
		_add_sparks()
	if preset.light_energy > 0.0:
		_light = OmniLight3D.new()
		var c := preset.color_main
		var mx: float = maxf(c.r, maxf(c.g, c.b))
		_light.light_color = Color(c.r / mx, c.g / mx, c.b / mx) if mx > 0.0 else Color.WHITE
		_light.light_energy = preset.light_energy * 0.38
		_light.omni_range = preset.light_range
		_light.omni_attenuation = 1.4
		_light.light_volumetric_fog_energy = 1.2
		add_child(_light)
		_built.append(_light)


func _add_burst(l: FreeMagicFxLayer) -> void:
	var mat := ShaderMaterial.new()
	mat.shader = BURST_SHADER
	mat.set_shader_parameter("tex", l.texture)
	mat.set_shader_parameter("noise_tex", NOISE_FBM)
	var a := preset.color_core if l.use_hot_start else preset.color_main
	var b := preset.color_main if l.use_hot_start else preset.color_accent
	mat.set_shader_parameter("color_a", a)
	mat.set_shader_parameter("color_b", b)
	var acc := preset.color_accent
	mat.set_shader_parameter("dissolve_edge_color", Color(acc.r * 1.6, acc.g * 1.6, acc.b * 1.6))
	mat.set_shader_parameter("emission_energy", l.emission_energy)
	mat.set_shader_parameter("dissolve_amount", l.dissolve_amount)
	mat.set_shader_parameter("distortion", l.distortion)
	mat.set_shader_parameter("spin", l.spin)
	mat.set_shader_parameter("stretch", l.stretch)
	mat.set_shader_parameter("angle_offset", randf() * TAU if l.random_angle else 0.0)
	mat.set_shader_parameter("progress", 0.0)

	var mi := MeshInstance3D.new()
	var quad := QuadMesh.new()
	quad.size = Vector2.ONE * l.size
	mi.mesh = quad
	mi.material_override = mat
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	mi.scale = Vector3.ONE * maxf(l.scale_from, 0.01)
	mi.visible = l.delay <= 0.0
	add_child(mi)
	_built.append(mi)

	_bursts.append({
		"mat": mat, "node": mi, "delay": l.delay, "life": l.lifetime,
		"from": l.scale_from, "to": l.scale_to, "pop": l.overshoot,
	})


func _add_ring() -> void:
	_ring_mat = ShaderMaterial.new()
	_ring_mat.shader = RING_SHADER
	_ring_mat.set_shader_parameter("noise_tex", NOISE_SOFT)
	_ring_mat.set_shader_parameter("ring_color", preset.color_main)
	_ring_mat.set_shader_parameter("hot_color", preset.color_core)
	_ring_mat.set_shader_parameter("emission_energy", 1.3)
	_ring_mat.set_shader_parameter("progress", 0.0)
	var ring := MeshInstance3D.new()
	var quad := QuadMesh.new()
	quad.size = Vector2.ONE * preset.ring_size
	ring.mesh = quad
	ring.material_override = _ring_mat
	ring.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(ring)
	_built.append(ring)


func _add_sparks() -> void:
	var ppm := ParticleProcessMaterial.new()
	ppm.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_SPHERE
	ppm.emission_sphere_radius = 0.08
	ppm.direction = Vector3.UP
	ppm.spread = 180.0
	ppm.initial_velocity_min = preset.spark_speed * 0.45
	ppm.initial_velocity_max = preset.spark_speed
	ppm.gravity = Vector3(0, preset.spark_gravity, 0)
	ppm.damping_min = 1.0
	ppm.damping_max = 2.5
	ppm.scale_min = 0.35
	ppm.scale_max = 1.0
	ppm.lifetime_randomness = 0.45

	var curve := Curve.new()
	curve.add_point(Vector2(0.0, 1.0))
	curve.add_point(Vector2(1.0, 0.0))
	var ct := CurveTexture.new()
	ct.curve = curve
	ppm.scale_curve = ct

	var grad := Gradient.new()
	grad.set_color(0, preset.color_core)
	grad.set_color(1, Color(preset.color_accent.r, preset.color_accent.g, preset.color_accent.b, 0.0))
	grad.add_point(0.4, preset.color_main)
	var gt := GradientTexture1D.new()
	gt.gradient = grad
	gt.use_hdr = true
	ppm.color_ramp = gt

	var mat := StandardMaterial3D.new()
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mat.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.vertex_color_use_as_albedo = true
	mat.albedo_texture = preset.spark_texture if preset.spark_texture else SPOT_TEX
	mat.disable_receive_shadows = true
	mat.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
	mat.billboard_keep_scale = true

	var quad := QuadMesh.new()
	quad.size = Vector2(0.055, 0.055)
	quad.material = mat

	var p := GPUParticles3D.new()
	p.amount = preset.sparks_amount
	p.lifetime = preset.spark_lifetime
	p.one_shot = true
	p.explosiveness = 1.0
	p.process_material = ppm
	p.draw_pass_1 = quad
	p.visibility_aabb = AABB(Vector3(-4, -4, -4), Vector3(8, 8, 8))
	p.emitting = true
	add_child(p)
	_built.append(p)


func _ease_pop(p: float, overshoot: float) -> float:
	if overshoot <= 0.0:
		return 1.0 - pow(1.0 - p, 3.0)
	var c1 := overshoot
	var c3 := c1 + 1.0
	var x := p - 1.0
	return 1.0 + c3 * x * x * x + c1 * x * x
