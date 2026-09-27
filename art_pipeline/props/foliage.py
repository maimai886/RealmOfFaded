"""
手繪葉片卡片組成的樹、灌木，加上貼手繪岩石材質的石頭與崖壁，各自輸出一個 .gltf 到 assets/generated/models/。
做法照仙境傳說：樹幹是貼樹皮的圓柱，樹冠是幾片交叉的葉團卡片。
卡片的法線一律指向樹冠中心的外側，受光才會像一顆蓬鬆的球而不是一片片紙；
環境遮蔽直接算進頂點色，底部暗、頂端亮，Godot 匯入時會自動把頂點色乘進材質。
輸出用 .gltf 分離格式並引用 assets/generated/textures 的圖，好幾種模型共用同一張貼圖，不重複佔記憶體。
卡片材質的 alpha 裁切和雙面顯示由匯出後直接改 .gltf 的 JSON 保證，不靠 Blender 版本相關的材質設定
"""
import json
import math
import os
import random

import bpy
from mathutils import Vector

import config

TEXTURES_DIR = os.path.join(config.PROJECT_ROOT, "assets", "generated", "textures")

# 頂點色的環境遮蔽範圍：底部乘這麼多，頂端 1.0
AO_FLOOR = 0.55


class MeshBuilder:
    """收集四邊形，最後一次建成一個網格；每個頂點自帶法線和顏色，每個面自帶貼圖座標與材質編號"""

    def __init__(self):
        self.verts = []
        self.normals = []
        self.colors = []
        self.faces = []
        self.face_uvs = []
        self.face_materials = []

    def quad(self, corners, uvs, normals, colors, material):
        start = len(self.verts)
        self.verts.extend(corners)
        self.normals.extend(normals)
        self.colors.extend(colors)
        self.faces.append((start, start + 1, start + 2, start + 3))
        self.face_uvs.append(uvs)
        self.face_materials.append(material)

    def triangle(self, corners, uvs, normals, colors, material):
        start = len(self.verts)
        self.verts.extend(corners)
        self.normals.extend(normals)
        self.colors.extend(colors)
        self.faces.append((start, start + 1, start + 2))
        self.face_uvs.append(uvs)
        self.face_materials.append(material)

    def build(self, name, materials, smooth=True):
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata([tuple(v) for v in self.verts], [], self.faces)
        for material in materials:
            mesh.materials.append(material)
        uv_layer = mesh.uv_layers.new(name="UVMap")
        for polygon in mesh.polygons:
            polygon.material_index = self.face_materials[polygon.index]
            polygon.use_smooth = smooth
            for k, loop_index in enumerate(polygon.loop_indices):
                uv_layer.data[loop_index].uv = self.face_uvs[polygon.index][k]
        color_layer = mesh.color_attributes.new(name="Color", type='FLOAT_COLOR', domain='POINT')
        for index, color in enumerate(self.colors):
            color_layer.data[index].color = (color, color, color, 1.0)
        mesh.color_attributes.active_color = color_layer
        mesh.normals_split_custom_set_from_vertices([Vector(n).normalized() for n in self.normals])
        mesh.update()
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.scene.collection.objects.link(obj)
        return obj


def _image(name):
    path = os.path.join(TEXTURES_DIR, name + ".png")
    image = bpy.data.images.load(path, check_existing=True)
    return image


def _material(name, image_name, cutout=False):
    existing = bpy.data.materials.get(name)
    if existing:
        return existing
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    bsdf.inputs["Roughness"].default_value = 1.0
    bsdf.inputs["Metallic"].default_value = 0.0
    texture = nodes.new('ShaderNodeTexImage')
    texture.image = _image(image_name)
    mat.node_tree.links.new(texture.outputs["Color"], bsdf.inputs["Base Color"])
    if cutout:
        mat.node_tree.links.new(texture.outputs["Alpha"], bsdf.inputs["Alpha"])
        mat.use_backface_culling = False
    mat["cutout"] = cutout
    return mat


def _ao(z, bottom, top):
    t = max(0.0, min(1.0, (z - bottom) / max(top - bottom, 0.001)))
    return AO_FLOOR + (1.0 - AO_FLOOR) * (t ** 0.8)


def _trunk(builder, material, height, radius_bottom, radius_top, rng, segments=8, rings=4, flare=1.5, lean=0.0):
    """樹幹：底部外張，往上漸細，頂點微微隨機讓輪廓不像圓柱，u 繞一圈 v 沿高度"""
    ring_points = []
    for ring in range(rings + 1):
        t = ring / rings
        z = height * t
        radius = radius_bottom + (radius_top - radius_bottom) * t
        if ring == 0:
            radius *= flare
        elif ring == 1:
            radius *= 1.0 + (flare - 1.0) * 0.3
        offset = Vector((lean * t * t, 0.0, 0.0))
        points = []
        for seg in range(segments):
            angle = seg / segments * math.tau
            wobble = 1.0 + rng.uniform(-0.08, 0.08) if 0 < ring < rings else 1.0
            points.append(Vector((math.cos(angle) * radius * wobble, math.sin(angle) * radius * wobble, z)) + offset)
        ring_points.append(points)
    for ring in range(rings):
        for seg in range(segments):
            nxt = (seg + 1) % segments
            a = ring_points[ring][seg]
            b = ring_points[ring][nxt]
            c = ring_points[ring + 1][nxt]
            d = ring_points[ring + 1][seg]
            u0 = seg / segments * 1.5
            u1 = (seg + 1) / segments * 1.5
            v0 = ring / rings * height * 0.8
            v1 = (ring + 1) / rings * height * 0.8
            normals = [Vector((p.x, p.y, 0.0)) for p in (a, b, c, d)]
            colors = [_ao(p.z, 0.0, height * 1.6) for p in (a, b, c, d)]
            builder.quad([a, b, c, d], [(u0, v0), (u1, v0), (u1, v1), (u0, v1)], normals, colors, material)
    # 頂端封起來，不然從俯角會看進中空的樹幹，看到底下被照亮的地面變成一道白光
    top = ring_points[rings]
    center = sum(top, Vector((0.0, 0.0, 0.0))) / len(top)
    for seg in range(segments):
        a = top[seg]
        b = top[(seg + 1) % segments]
        up = Vector((0.0, 0.0, 1.0))
        builder.triangle([a, b, center], [(0.05, 0.05), (0.15, 0.05), (0.1, 0.15)], [up, up, up],
                         [_ao(height, 0.0, height * 1.6)] * 3, material)


def _card(builder, material, center, width, height, yaw, tilt, ao_bottom, ao_top, normal_center, bottom_anchored=False):
    """
    一片直立卡片，繞 Z 轉 yaw、再繞自己的橫軸傾斜 tilt。
    法線不用卡片的面法線，改用頂點到樹冠中心的方向，整棵樹的卡片受光才會連成一團
    """
    right = Vector((math.cos(yaw), math.sin(yaw), 0.0))
    up = Vector((0.0, 0.0, 1.0))
    if tilt:
        forward = right.cross(up)
        up = (up * math.cos(tilt) + forward * math.sin(tilt)).normalized()
    base = Vector(center) - (up * 0 if bottom_anchored else up * height * 0.5)
    corners = [base - right * width * 0.5, base + right * width * 0.5,
               base + right * width * 0.5 + up * height, base - right * width * 0.5 + up * height]
    normals = [(p - Vector(normal_center)) for p in corners]
    colors = [_ao(p.z, ao_bottom, ao_top) for p in corners]
    builder.quad(corners, [(0, 0), (1, 0), (1, 1), (0, 1)], normals, colors, material)


def _flat_card(builder, material, center, size, yaw, ao):
    """平躺的卡片蓋在樹冠頂上，從俯角看樹冠才不會露出十字交叉的縫"""
    right = Vector((math.cos(yaw), math.sin(yaw), 0.0))
    forward = Vector((-math.sin(yaw), math.cos(yaw), 0.0))
    c = Vector(center)
    corners = [c - right * size * 0.5 - forward * size * 0.5, c + right * size * 0.5 - forward * size * 0.5,
               c + right * size * 0.5 + forward * size * 0.5, c - right * size * 0.5 + forward * size * 0.5]
    normals = [Vector((0.0, 0.0, 1.0)) for _ in corners]
    builder.quad(corners, [(0, 0), (1, 0), (1, 1), (0, 1)], normals, [ao] * 4, material)


def _export(obj, name, cutout_materials, out_dir=None):
    """匯出 .gltf 分離格式，貼圖引用原檔；再把卡片材質改成 alpha 裁切、雙面"""
    out_dir = out_dir or config.MODELS_OUT
    os.makedirs(out_dir, exist_ok=True)
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    path = os.path.join(out_dir, name + ".gltf")
    bpy.ops.export_scene.gltf(filepath=path, export_format='GLTF_SEPARATE', export_keep_originals=True,
                              use_selection=True, export_apply=True, export_vertex_color='ACTIVE',
                              export_normals=True, export_yup=True)
    patch_gltf(path, cutout_materials)
    return path


def patch_gltf(path, cutout_materials, image_prefix=None):
    """
    直接改 glTF 的 JSON：卡片材質 alphaMode MASK、alphaCutoff 0.5、doubleSided；全部材質關掉高光。
    貼圖路徑改成相對於模型資料夾指向 assets/generated/textures，Godot 會直接用已匯入的貼圖
    """
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    for material in data.get("materials", []):
        pbr = material.setdefault("pbrMetallicRoughness", {})
        pbr["metallicFactor"] = 0.0
        pbr["roughnessFactor"] = 1.0
        if material.get("name") in cutout_materials:
            material["alphaMode"] = "MASK"
            material["alphaCutoff"] = 0.5
            material["doubleSided"] = True
        material.pop("extensions", None)
    if "extensionsUsed" in data:
        data["extensionsUsed"] = [e for e in data["extensionsUsed"] if e != "KHR_materials_specular"]
        if not data["extensionsUsed"]:
            data.pop("extensionsUsed")
    model_dir = os.path.dirname(os.path.abspath(path))
    for image in data.get("images", []):
        uri = image.get("uri", "")
        name = os.path.basename(uri)
        if name:
            target = os.path.join(TEXTURES_DIR, name)
            image["uri"] = os.path.relpath(target, model_dir).replace(os.sep, "/")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, separators=(",", ":"))


def tree_broadleaf():
    """草原的闊葉樹：四片交叉直立卡片加頂上一片平躺卡片，兩片小卡片打散輪廓"""
    return _broadleaf("tree_broadleaf", "leaf_bright")


def tree_broadleaf_dark():
    """森林的闊葉樹：同樣的樹形，換成深綠帶青的葉團"""
    return _broadleaf("tree_broadleaf_dark", "leaf_dark")


def _broadleaf(name, leaf_name):
    rng = random.Random("broadleaf")
    bark = _material("bark", "bark")
    leaf = _material(leaf_name, leaf_name, cutout=True)
    builder = MeshBuilder()
    trunk_height = 2.6
    _trunk(builder, 0, trunk_height, 0.24, 0.15, rng, lean=0.12)
    canopy = (0.1, 0.0, 3.5)
    normal_center = (0.1, 0.0, 2.6)
    # 四片直立卡片每 45 度一片，交替往前後傾，從俯角看才不會露出兩片平面交叉的十字
    for index in range(4):
        yaw = index * math.pi / 4 + 0.2
        tilt = 0.2 if index % 2 == 0 else -0.16
        _card(builder, 1, canopy, 3.8, 3.2, yaw, tilt, 1.6, 5.2, normal_center)
    _flat_card(builder, 1, (0.1, 0.0, 4.4), 3.2, 0.4, 1.0)
    _card(builder, 1, (1.1, 0.6, 3.0), 2.2, 1.9, 0.9, 0.25, 1.6, 5.0, normal_center)
    _card(builder, 1, (-1.0, -0.5, 3.2), 2.0, 1.8, 2.3, -0.2, 1.6, 5.0, normal_center)
    obj = builder.build(name, [bark, leaf])
    return obj, [leaf_name]


def tree_conifer():
    """森林的針葉樹：三層越上越小的針葉層，每層兩片交叉卡片，層與層錯開角度"""
    rng = random.Random("pine")
    bark = _material("bark", "bark")
    needles = _material("pine_tier", "pine_tier", cutout=True)
    builder = MeshBuilder()
    _trunk(builder, 0, 5.2, 0.22, 0.06, rng, rings=5, flare=1.4)
    tiers = [(1.4, 3.6, 3.0), (2.9, 2.9, 2.6), (4.2, 2.1, 2.2)]
    for index, (z, width, height) in enumerate(tiers):
        for k in range(2):
            yaw = index * 0.55 + k * math.pi / 2
            _card(builder, 1, (0.0, 0.0, z), width, height, yaw, 0.0, 0.8, 6.4, (0.0, 0.0, z - 0.6), bottom_anchored=True)
    obj = builder.build("tree_conifer", [bark, needles])
    return obj, ["pine_tier"]


def tree_dead():
    """碎石谷的枯樹：短樹幹接兩片交叉的枯枝卡片"""
    rng = random.Random("dead")
    bark = _material("bark", "bark")
    branches = _material("dead_branches", "dead_branches", cutout=True)
    builder = MeshBuilder()
    _trunk(builder, 0, 0.9, 0.3, 0.26, rng, rings=2, flare=1.6)
    for k in range(2):
        _card(builder, 1, (0.0, 0.0, 0.75), 3.6, 3.8, k * math.pi / 2 + 0.4, 0.0, 0.3, 4.6, (0.0, 0.0, 1.8), bottom_anchored=True)
    obj = builder.build("tree_dead", [bark, branches])
    return obj, ["dead_branches"]


def shrub():
    """灌木：三片交叉卡片，用原本的葉團圖"""
    leaf = _material("leaves", "leaves", cutout=True)
    builder = MeshBuilder()
    for index in range(3):
        yaw = index * math.tau / 3
        _card(builder, 0, (0.0, 0.0, 0.0), 1.5, 1.25, yaw, 0.0, -0.4, 1.4, (0.0, 0.0, 0.2), bottom_anchored=True)
    _flat_card(builder, 0, (0.0, 0.0, 0.9), 1.2, 0.5, 1.0)
    obj = builder.build("shrub", [leaf])
    return obj, ["leaves"]


def _box_uv(mesh, scale):
    """依每個面的主要法線方向做箱型投影，岩石貼圖才不會拉伸"""
    uv_layer = mesh.uv_layers.new(name="UVMap") if not mesh.uv_layers else mesh.uv_layers[0]
    for polygon in mesh.polygons:
        normal = polygon.normal
        axis = max(range(3), key=lambda i: abs(normal[i]))
        for loop_index in polygon.loop_indices:
            co = mesh.vertices[mesh.loops[loop_index].vertex_index].co
            if axis == 0:
                uv = (co.y, co.z)
            elif axis == 1:
                uv = (co.x, co.z)
            else:
                uv = (co.x, co.y)
            uv_layer.data[loop_index].uv = (uv[0] * scale, uv[1] * scale)


def _vertex_ao(mesh, bottom, top):
    color_layer = mesh.color_attributes.new(name="Color", type='FLOAT_COLOR', domain='POINT')
    for index, vertex in enumerate(mesh.vertices):
        value = _ao(vertex.co.z, bottom, top)
        color_layer.data[index].color = (value, value, value, 1.0)
    mesh.color_attributes.active_color = color_layer


def bake_vertex_ao(obj, floor=0.6, ground_band=0.2, samples=24):
    """
    用 Cycles 把環境遮蔽烘進頂點色：凹處和屋簷下真的會暗，再乘上靠近地面的梯度當接地感。
    floor 是最暗能到多少，ground_band 是底部多少比例的高度內再壓暗；卡片樹不用這個，卡片會互相遮成一團黑
    """
    mesh = obj.data
    for existing in list(mesh.color_attributes):
        mesh.color_attributes.remove(existing)
    color_layer = mesh.color_attributes.new(name="Color", type='FLOAT_COLOR', domain='POINT')
    mesh.color_attributes.active_color = color_layer
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = samples
    scene.cycles.device = 'CPU'
    scene.render.bake.target = 'VERTEX_COLORS'
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.bake(type='AO')
    heights = [(obj.matrix_world @ v.co).z for v in mesh.vertices]
    z_min, z_max = min(heights), max(heights)
    band = max((z_max - z_min) * ground_band, 1e-4)
    for index, vertex in enumerate(mesh.vertices):
        baked = color_layer.data[index].color[0]
        ao = floor + (1.0 - floor) * min(max(baked, 0.0), 1.0) ** 0.7
        ground = 0.8 + 0.2 * min(max((heights[index] - z_min) / band, 0.0), 1.0)
        value = ao * ground
        color_layer.data[index].color = (value, value, value, 1.0)
    mesh.update()


def _rock_shape(name, radius, scale, rng, subdivisions=2, bumpiness=0.22):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=subdivisions, radius=radius, location=(0, 0, 0))
    obj = bpy.context.object
    obj.name = name
    mesh = obj.data
    for vertex in mesh.vertices:
        vertex.co.x *= scale[0] * (1.0 + rng.uniform(-bumpiness, bumpiness))
        vertex.co.y *= scale[1] * (1.0 + rng.uniform(-bumpiness, bumpiness))
        vertex.co.z *= scale[2] * (1.0 + rng.uniform(-bumpiness, bumpiness))
        # 底部壓平，石頭才會坐在地上
        vertex.co.z = max(vertex.co.z, -radius * scale[2] * 0.15)
    for polygon in mesh.polygons:
        # 圓潤的卵石：平滑著色，剪影和表面都不留硬角
        polygon.use_smooth = True
    mesh.update()
    return obj


def boulder():
    rng = random.Random("boulder")
    material = _material("cliff_rock", "cliff_rock")
    obj = _rock_shape("boulder", 0.55, (1.2, 0.95, 0.75), rng, bumpiness=0.16)
    obj.data.materials.append(material)
    _box_uv(obj.data, 0.3)
    bake_vertex_ao(obj, floor=0.55, ground_band=0.3)
    return obj, []


def boulder_large():
    rng = random.Random("boulder_large")
    material = _material("cliff_rock", "cliff_rock")
    obj = _rock_shape("boulder_large", 1.3, (1.3, 1.0, 0.85), rng, subdivisions=3, bumpiness=0.12)
    obj.data.materials.append(material)
    _box_uv(obj.data, 0.22)
    bake_vertex_ao(obj, floor=0.55, ground_band=0.3)
    return obj, []


def cliff_block():
    """4 公尺寬、3 公尺高的崖壁塊，表面有層理，可以排成一整面崖"""
    rng = random.Random("cliff")
    material = _material("cliff_rock", "cliff_rock")
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 1.5))
    obj = bpy.context.object
    obj.name = "cliff_block"
    obj.scale = (4.0, 2.4, 3.0)
    bpy.ops.object.transform_apply(scale=True)
    modifier = obj.modifiers.new("cells", 'SUBSURF')
    modifier.subdivision_type = 'SIMPLE'
    modifier.levels = 2
    bpy.ops.object.modifier_apply(modifier="cells")
    mesh = obj.data
    for vertex in mesh.vertices:
        if vertex.co.z > 0.05:
            vertex.co.x += rng.uniform(-0.18, 0.18)
            vertex.co.y += rng.uniform(-0.22, 0.22)
            vertex.co.z += rng.uniform(-0.1, 0.1)
    for polygon in mesh.polygons:
        polygon.use_smooth = False
    mesh.update()
    mesh.materials.append(material)
    _box_uv(mesh, 0.22)
    bake_vertex_ao(obj, floor=0.55, ground_band=0.25)
    return obj, []


def fence_wood():
    """柵欄：兩根柱子加兩條橫桿，貼木頭材質"""
    wood = _material("wood", "wood")
    parts = []
    for x in (-0.95, 0.95):
        bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=0.07, depth=0.85, location=(x, 0, 0.42))
        parts.append(bpy.context.object)
    for z in (0.35, 0.62):
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, z))
        rail = bpy.context.object
        rail.scale = (1.95, 0.06, 0.1)
        bpy.ops.object.transform_apply(scale=True)
        parts.append(rail)
    bpy.ops.object.select_all(action='DESELECT')
    for part in parts:
        part.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    obj.name = "fence_wood"
    for polygon in obj.data.polygons:
        polygon.use_smooth = False
    obj.data.materials.append(wood)
    _box_uv(obj.data, 0.6)
    bake_vertex_ao(obj, floor=0.6, ground_band=0.4)
    return obj, []


# 名稱刻意和 nature.py 的舊模型錯開，舊的 .glb 還有地圖產生器在用
PROPS = [tree_broadleaf, tree_broadleaf_dark, tree_conifer, tree_dead, shrub, boulder, boulder_large, cliff_block,
         fence_wood]


def build():
    from common import scene
    paths = []
    for make in PROPS:
        scene.reset_scene()
        obj, cutouts = make()
        paths.append(_export(obj, make.__name__, cutouts))
    return paths
