import math

import bpy
from mathutils import Vector

import config
from common import projection


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.film_transparent = True
    scene.view_settings.view_transform = 'Standard'
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    return scene


def add_lights():
    scene = bpy.context.scene
    sun = bpy.data.objects.new("key_light", bpy.data.lights.new("key_light", 'SUN'))
    sun.data.energy = 3.0
    # 卡通明暗只看法線方向，投射陰影會在曲面上產生塊狀髒斑
    sun.data.use_shadow = False
    sun.rotation_euler = (math.radians(50), 0, math.radians(-35))
    scene.collection.objects.link(sun)
    world = bpy.data.worlds.new("world")
    scene.world = world
    background = world.node_tree.nodes.get("Background")
    if background:
        background.inputs["Color"].default_value = (0.25, 0.25, 0.28, 1)
        background.inputs["Strength"].default_value = 1.0


def setup_sprite_camera(frame_px, target_height, supersample=1):
    """建立正交相機，回傳腳底原點在畫格中的像素座標，座標以縮小後的畫格為準"""
    scene = bpy.context.scene
    scene.render.resolution_x = frame_px * supersample
    scene.render.resolution_y = frame_px * supersample
    scene.render.resolution_percentage = 100
    cam_data = bpy.data.cameras.new("sprite_cam")
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = frame_px / config.PX_PER_M
    cam = bpy.data.objects.new("sprite_cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    elevation = math.radians(config.CAMERA_ELEVATION_DEG)
    distance = 20.0
    target = Vector((0, 0, target_height))
    cam.location = target + Vector((0, -math.cos(elevation) * distance, math.sin(elevation) * distance))
    cam.rotation_euler = (math.pi / 2 - elevation, 0, 0)
    return projection.feet_pixel(frame_px, target_height, config.PX_PER_M, config.CAMERA_ELEVATION_DEG)


def add_empty(name, parent=None, location=(0, 0, 0)):
    empty = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(empty)
    empty.parent = parent
    empty.location = location
    return empty


def add_sphere(name, parent, location, scale, material, segments=32, rings=16, rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings, radius=1.0)
    return _finish_part(name, parent, location, scale, material, rotation)


def add_cylinder(name, parent, location, radius, depth, material, vertices=20, rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth)
    return _finish_part(name, parent, location, (1, 1, 1), material, rotation)


def add_cone(name, parent, location, radius_bottom, radius_top, depth, material, vertices=20, rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_cone_add(vertices=vertices, radius1=radius_bottom, radius2=radius_top, depth=depth)
    return _finish_part(name, parent, location, (1, 1, 1), material, rotation)


def add_torus(name, parent, location, major_radius, minor_radius, scale, material, rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_torus_add(major_segments=32, minor_segments=12,
                                     major_radius=major_radius, minor_radius=minor_radius)
    return _finish_part(name, parent, location, scale, material, rotation)


def _finish_part(name, parent, location, scale, material, rotation=(0, 0, 0)):
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bpy.ops.object.shade_smooth()
    obj.parent = parent
    obj.location = location
    obj.rotation_euler = tuple(math.radians(r) for r in rotation)
    obj.data.materials.append(material)
    return obj
