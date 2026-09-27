"""
野外場景物件：樹、灌木、石頭、花、草叢、柵欄、蘑菇，各自輸出一個 .glb。
描邊用反轉外殼直接烘進模型，glTF 預設背面剔除，所以進 Godot 一樣看得到輪廓
"""
import math
import os
import random

import bpy

import config
from common import scene
from common.toon import srgb

OUTLINE = 0.025
# 地圖物件走手繪貼圖風格，預設不描邊，只有角色和怪物描邊
USE_OUTLINE = False


def _material(name, color):
    existing = bpy.data.materials.get(name)
    if existing:
        return existing
    mat = bpy.data.materials.new(name)
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = 1.0
    return mat


def _outline_material():
    mat = _material("outline", srgb("#2A1F1C"))
    mat.use_backface_culling = True
    return mat


def _finish(obj, color_name, color, outline=USE_OUTLINE, flat=False):
    obj.data.materials.append(_material(color_name, color))
    if flat:
        bpy.ops.object.shade_flat()
    if outline:
        obj.data.materials.append(_outline_material())
        modifier = obj.modifiers.new("outline", 'SOLIDIFY')
        modifier.thickness = OUTLINE
        modifier.offset = 1.0
        modifier.use_flip_normals = True
        modifier.use_rim = False
        modifier.material_offset = 1
    return obj


def _blob(name, location, radius, rng, bumpiness=0.12, subdivisions=2):
    """表面隨機起伏的圓球，拿來做樹冠、灌木、石頭"""
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=subdivisions, radius=radius, location=location)
    obj = bpy.context.object
    obj.name = name
    for vertex in obj.data.vertices:
        vertex.co *= 1.0 + rng.uniform(-bumpiness, bumpiness)
    bpy.ops.object.shade_smooth()
    return obj


def _cone(name, location, radius_bottom, radius_top, depth, rotation=(0, 0, 0), vertices=10):
    bpy.ops.mesh.primitive_cone_add(vertices=vertices, radius1=radius_bottom, radius2=radius_top, depth=depth,
                                    location=location, rotation=tuple(math.radians(r) for r in rotation))
    obj = bpy.context.object
    obj.name = name
    bpy.ops.object.shade_smooth()
    return obj


def _export(name):
    """先把描邊套用進網格再合併成單一物件，Godot 才能直接拿來做 MultiMesh"""
    objects = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
    for obj in objects:
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        for modifier in list(obj.modifiers):
            bpy.ops.object.modifier_apply(modifier=modifier.name)
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.join()
    merged = bpy.context.view_layer.objects.active
    merged.name = name
    os.makedirs(config.MODELS_OUT, exist_ok=True)
    path = os.path.join(config.MODELS_OUT, name + ".glb")
    bpy.ops.export_scene.gltf(filepath=path, export_format='GLB', use_selection=True, export_apply=True)
    return path


def tree_round():
    rng = random.Random("tree_round")
    _finish(_cone("trunk", (0, 0, 0.6), 0.2, 0.12, 1.2), "bark", srgb("#8A5A3B"))
    # 下層樹冠顏色較深、上層較亮，由下往上堆出層次
    for index, (x, y, z, r, color) in enumerate((
            (0.5, 0.25, 1.35, 0.5, "#3F8A3A"), (-0.5, 0.1, 1.4, 0.52, "#3F8A3A"),
            (0.05, -0.45, 1.35, 0.5, "#46943F"), (0.1, 0.4, 1.5, 0.55, "#46943F"),
            (0, 0, 1.8, 0.75, "#56A94A"), (0.35, -0.2, 2.15, 0.5, "#67BC55"),
            (-0.3, 0.15, 2.2, 0.5, "#67BC55"), (0, 0, 2.5, 0.42, "#7ACB62"))):
        _finish(_blob("leaves_%d" % index, (x, y, z), r, rng, bumpiness=0.08, subdivisions=3),
                "leaves_%s" % color, srgb(color))


def tree_pine():
    _finish(_cone("trunk", (0, 0, 0.35), 0.15, 0.1, 0.7), "bark", srgb("#7A4F35"))
    for index, (z, r, depth, color) in enumerate(((1.0, 0.95, 1.1, "#3F8F55"), (1.7, 0.72, 0.95, "#4A9D5E"),
                                                  (2.3, 0.48, 0.8, "#56AA66"))):
        _finish(_cone("needles_%d" % index, (0, 0, z), r, 0.0, depth, vertices=12), "needles_%d" % index, srgb(color))


def bush():
    rng = random.Random("bush")
    for index, (x, y, z, r) in enumerate(((0, 0, 0.35, 0.45), (0.38, 0.1, 0.28, 0.33), (-0.36, -0.05, 0.27, 0.35))):
        _finish(_blob("bush_%d" % index, (x, y, z), r, rng), "bush_leaves", srgb("#5FAF4D"))
    for index in range(5):
        angle = rng.uniform(0, math.tau)
        location = (math.cos(angle) * 0.36, math.sin(angle) * 0.3, rng.uniform(0.35, 0.65))
        bpy.ops.mesh.primitive_uv_sphere_add(segments=8, ring_count=6, radius=0.06, location=location)
        _finish(bpy.context.object, "berry", srgb("#F2677A"), outline=False)


def rock():
    rng = random.Random("rock")
    obj = _blob("rock", (0, 0, 0.2), 0.5, rng, bumpiness=0.2, subdivisions=1)
    obj.scale = (1.0, 0.8, 0.6)
    _finish(obj, "rock", srgb("#9C9AA6"), flat=True)
    small = _blob("rock_small", (0.45, 0.25, 0.08), 0.22, rng, bumpiness=0.2, subdivisions=1)
    _finish(small, "rock", srgb("#9C9AA6"), flat=True)


def _flower(name, petal_color):
    _finish(_cone("stem", (0, 0, 0.12), 0.012, 0.012, 0.24, vertices=6), "stem", srgb("#4E9E3A"), outline=False)
    for index in range(5):
        angle = index * math.tau / 5
        bpy.ops.mesh.primitive_uv_sphere_add(segments=10, ring_count=6, radius=0.05,
                                             location=(math.cos(angle) * 0.055, math.sin(angle) * 0.055, 0.26))
        petal = bpy.context.object
        petal.scale = (1, 1, 0.45)
        _finish(petal, name + "_petal", srgb(petal_color), outline=False)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=10, ring_count=6, radius=0.035, location=(0, 0, 0.275))
    _finish(bpy.context.object, "flower_center", srgb("#FFD24D"), outline=False)


def flower_pink():
    _flower("pink", "#FF8FB8")


def flower_white():
    _flower("white", "#FFF7EC")


def flower_blue():
    _flower("blue", "#8DB4FF")


def grass_tuft():
    rng = random.Random("grass")
    for index in range(7):
        angle = index * math.tau / 7 + rng.uniform(-0.3, 0.3)
        lean = rng.uniform(15, 35)
        height = rng.uniform(0.22, 0.34)
        location = (math.cos(angle) * 0.05, math.sin(angle) * 0.05, height / 2)
        blade = _cone("blade_%d" % index, location, 0.025, 0.0, height, vertices=4,
                      rotation=(0, lean, math.degrees(angle)))
        _finish(blade, "grass_%d" % (index % 2), srgb("#7CC95A" if index % 2 else "#5FAE45"), outline=False)


def fence():
    for index, x in enumerate((-0.95, 0.95)):
        post = _cone("post_%d" % index, (x, 0, 0.4), 0.07, 0.07, 0.8, vertices=8)
        _finish(post, "wood", srgb("#B07F52"))
    for index, z in enumerate((0.35, 0.62)):
        bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, z))
        rail = bpy.context.object
        rail.scale = (1.95, 0.06, 0.1)
        bpy.ops.object.transform_apply(scale=True)
        _finish(rail, "wood", srgb("#B07F52"))


def mushroom():
    _finish(_cone("stem", (0, 0, 0.12), 0.07, 0.055, 0.24), "mushroom_stem", srgb("#F4E6C8"))
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, radius=0.2, location=(0, 0, 0.24))
    cap = bpy.context.object
    cap.scale = (1, 1, 0.6)
    bpy.ops.object.transform_apply(scale=True)
    bpy.ops.object.shade_smooth()
    _finish(cap, "mushroom_cap", srgb("#E8574F"))
    for index, (x, y, z) in enumerate(((0.08, -0.1, 0.33), (-0.1, -0.05, 0.34), (0.02, 0.1, 0.36), (-0.02, -0.16, 0.28))):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=8, ring_count=6, radius=0.03, location=(x, y, z))
        _finish(bpy.context.object, "mushroom_dot", srgb("#FFF8EE"), outline=False)


PROPS = [tree_round, tree_pine, bush, rock, flower_pink, flower_white, flower_blue, grass_tuft, fence, mushroom]


def build():
    paths = []
    for make in PROPS:
        scene.reset_scene()
        make()
        paths.append(_export(make.__name__))
    return paths
