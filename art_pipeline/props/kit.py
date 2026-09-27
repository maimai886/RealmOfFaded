"""
場景建模的共用零件：方塊、稜柱、圓柱、圓錐、斜面板，每一塊在自己的座標系裡先算好貼圖座標再擺位置，
所以屋頂的瓦片會順著斜面排、牆上的木紋是直的。建築和地標都用這裡的零件拼，拼完一次烘環境遮蔽再輸出 glTF。
材質分兩種：貼手繪圖的用 assets/generated/textures 的貼圖，小面積的金屬、玻璃、布用平塗，顏色一樣過 RO 色階。
單位是公尺，Blender 的 Z 是高度，匯出時轉成 Godot 的 Y 朝上
"""
import math
import os

import bpy
import numpy as np
from mathutils import Vector

import config
from props import foliage
from textures import tileable

# 每種貼圖一張對應幾公尺，和 town_retex.TILE_METRES 一致，同一面牆換模型也接得起來
TILE_METRES = {
    "plaster": 1.8, "wood": 1.6, "roof_tiles": 2.0, "stone_wall": 2.4, "rock": 2.4, "bark": 1.2,
    "cliff_rock": 4.5,
    "cobblestone": 1.6, "dirt": 2.0, "grass": 2.0, "cave_rock": 2.4, "dungeon_floor": 2.8,
}

_parts = []

# 小面積的金屬、玻璃、布、花這些平塗顏色全部畫在同一張調色盤貼圖上，一個模型的平塗面共用一個材質，
# 不然一棟房子會變成二十幾次繪製。順序固定，改動時整批重建；PALETTE_GLOW 的格子會發光
PALETTE = [
    "#3C4E63", "#8C5A3C", "#6B4630", "#4A2F20", "#C9A227", "#D9584F", "#F2E3C4", "#5BA8D9",
    "#8FBF63", "#E8738C", "#F2C14E", "#C77FBF", "#5B4A52", "#4B4038", "#2F2A33", "#241C22",
    "#5C5560", "#3E3A42", "#4B4E57", "#C8B48A", "#4E8C46", "#5FA84E", "#C4483F", "#B8863B",
    "#4E7F8C", "#7FC6D9", "#9BD7E6", "#1B1622", "#5C8C4A", "#8FB86A", "#A8B0BA", "#7A6A5C",
]
PALETTE_GLOW = ["FFD98A", "FFC46B", "FF8A3D", "AEE8B0", "BFF0B8", "7FE6D9", "9B6BE6", "FF9A45"]
PALETTE_COLUMNS = 8
PALETTE_CELL = 32
PALETTE_TEXTURE = "palette"


def _palette_uv(color_hex, glow):
    """color_hex 不含井字號；查不到的顏色直接報錯，免得漏加進調色盤"""
    table = [c.lstrip("#").upper() for c in (PALETTE_GLOW if glow else PALETTE)]
    key = color_hex.lstrip("#").upper()
    if key not in table:
        raise KeyError("顏色 %s 不在調色盤裡，先加進 kit.PALETTE" % key)
    index = table.index(key) + (len(PALETTE) if glow else 0)
    row, column = divmod(index, PALETTE_COLUMNS)
    return ((column + 0.5) / PALETTE_COLUMNS, 1.0 - (row + 0.5) / _palette_rows())


def _palette_rows():
    total = len(PALETTE) + len(PALETTE_GLOW)
    return (total + PALETTE_COLUMNS - 1) // PALETTE_COLUMNS


def build_palette():
    """把調色盤畫成一張貼圖，每格一個顏色，顏色先過 RO 色階；模型的平塗面把貼圖座標釘在格子中心"""
    from common import atlas
    rows = _palette_rows()
    sheet = np.zeros((rows * PALETTE_CELL, PALETTE_COLUMNS * PALETTE_CELL, 4), dtype=np.float32)
    colors = [c.lstrip("#") for c in PALETTE] + list(PALETTE_GLOW)
    for index, color_hex in enumerate(colors):
        rgb = np.array([[[int(color_hex[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]]], dtype=np.float32)
        graded = tileable.grade(rgb, warm=0.25, lift=0.32)[0, 0]
        row, column = divmod(index, PALETTE_COLUMNS)
        sheet[row * PALETTE_CELL:(row + 1) * PALETTE_CELL,
              column * PALETTE_CELL:(column + 1) * PALETTE_CELL, :3] = graded
        sheet[row * PALETTE_CELL:(row + 1) * PALETTE_CELL,
              column * PALETTE_CELL:(column + 1) * PALETTE_CELL, 3] = 1.0
    path = os.path.join(config.PROJECT_ROOT, "assets", "generated", "textures", PALETTE_TEXTURE + ".png")
    atlas.save_png(np.clip(sheet, 0.0, 1.0), path)
    tileable.write_import(path, compressed=False)
    print("[kit] %s" % os.path.relpath(path, config.PROJECT_ROOT))
    return [path]


def reset():
    """開一個空場景，開始拼下一個模型"""
    from common import scene
    scene.reset_scene()
    _parts.clear()


def textured(kind):
    return foliage._material(kind, kind)


def flat(name, color_hex):
    """平塗材質，顏色先過 RO 色階，不會出現純黑或螢光色"""
    existing = bpy.data.materials.get(name)
    if existing:
        return existing
    rgb = np.array([[[int(color_hex[i:i + 2], 16) / 255.0 for i in (1, 3, 5)]]], dtype=np.float32)
    graded = tileable.grade(rgb, warm=0.25, lift=0.32)[0, 0]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in graded]
    bsdf.inputs["Base Color"].default_value = (linear[0], linear[1], linear[2], 1.0)
    bsdf.inputs["Roughness"].default_value = 1.0
    bsdf.inputs["Metallic"].default_value = 0.0
    return mat


def glowing(name, color_hex, strength=1.6):
    """會發光的材質，燈籠和水晶用；Godot 那邊泛光只吃亮度超過 1 的地方"""
    existing = bpy.data.materials.get(name)
    if existing:
        return existing
    mat = flat(name, color_hex)
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    base = bsdf.inputs["Base Color"].default_value
    bsdf.inputs["Emission Color"].default_value = base
    bsdf.inputs["Emission Strength"].default_value = strength
    return mat


def palette_material(glow):
    """調色盤材質，一個模型裡所有平塗面共用；發光的那一份多接一條自發光"""
    name = "palette_glow" if glow else "palette"
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
    texture.image = foliage._image(PALETTE_TEXTURE)
    texture.interpolation = 'Closest'
    mat.node_tree.links.new(texture.outputs["Color"], bsdf.inputs["Base Color"])
    if glow:
        mat.node_tree.links.new(texture.outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = 1.6
    return mat


def _material_of(kind):
    if kind.startswith("#"):
        return palette_material(False)
    if kind.startswith("glow:"):
        return palette_material(True)
    return textured(kind)


def _uv_metres(kind):
    return TILE_METRES.get(kind, 1.8)


def _local_box_uv(mesh, metres, flip_axis=None):
    """在零件自己的座標系裡依面的主要法線做箱型投影，所以旋轉之後貼圖跟著斜面走"""
    uv_layer = mesh.uv_layers[0] if mesh.uv_layers else mesh.uv_layers.new(name="UVMap")
    factor = 1.0 / max(metres, 0.01)
    for polygon in mesh.polygons:
        normal = polygon.normal
        axis = max(range(3), key=lambda i: abs(normal[i]))
        if flip_axis is not None:
            axis = flip_axis
        for loop_index in polygon.loop_indices:
            co = mesh.vertices[mesh.loops[loop_index].vertex_index].co
            if axis == 0:
                uv = (co.y, co.z)
            elif axis == 1:
                uv = (co.x, co.z)
            else:
                uv = (co.x, co.y)
            uv_layer.data[loop_index].uv = (uv[0] * factor, uv[1] * factor)


def _place(obj, kind, loc, rot, smooth=False, uv_scale=None, uv_axis=None):
    mesh = obj.data
    if not mesh.uv_layers:
        mesh.uv_layers.new(name="UVMap")
    if kind.startswith("#") or kind.startswith("glow:"):
        uv = _palette_uv(kind[5:] if kind.startswith("glow:") else kind[1:], kind.startswith("glow:"))
        for loop in mesh.uv_layers[0].data:
            loop.uv = uv
    else:
        _local_box_uv(mesh, uv_scale if uv_scale else _uv_metres(kind), uv_axis)
    mesh.materials.append(_material_of(kind))
    for polygon in mesh.polygons:
        polygon.use_smooth = smooth
    obj.rotation_euler = tuple(math.radians(r) for r in rot)
    obj.location = tuple(loc)
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    mesh.update()
    _parts.append(obj)
    return obj


def box(name, size, loc=(0, 0, 0), rot=(0, 0, 0), kind="plaster", uv_scale=None, uv_axis=None):
    """中心在 loc 的方塊，size 是三軸長度"""
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 0))
    obj = bpy.context.object
    obj.name = name
    obj.scale = tuple(size)
    bpy.ops.object.transform_apply(scale=True)
    return _place(obj, kind, loc, rot, uv_scale=uv_scale, uv_axis=uv_axis)


def slab(name, size, loc, rot, kind, uv_scale=None):
    """斜面板，貼圖在旋轉前就沿著板子的面算好，屋頂瓦片才會順著斜面排"""
    return box(name, size, loc, rot, kind, uv_scale=uv_scale, uv_axis=2)


def prism(name, profile, depth, loc=(0, 0, 0), rot=(0, 0, 0), kind="plaster", uv_scale=None):
    """把 (x, z) 的多邊形沿 y 拉出 depth 的厚度，山牆和階梯用"""
    half = depth * 0.5
    verts = [(x, -half, z) for x, z in profile] + [(x, half, z) for x, z in profile]
    count = len(profile)
    faces = [tuple(range(count - 1, -1, -1)), tuple(range(count, count * 2))]
    for i in range(count):
        j = (i + 1) % count
        faces.append((i, j, j + count, i + count))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return _place(obj, kind, loc, rot, uv_scale=uv_scale)


def cylinder(name, radius, height, loc=(0, 0, 0), rot=(0, 0, 0), kind="wood", sides=10, uv_scale=None, smooth=False):
    bpy.ops.mesh.primitive_cylinder_add(vertices=sides, radius=radius, depth=height, location=(0, 0, 0))
    obj = bpy.context.object
    obj.name = name
    return _place(obj, kind, loc, rot, smooth=smooth, uv_scale=uv_scale)


def cone(name, bottom, top, height, loc=(0, 0, 0), rot=(0, 0, 0), kind="roof_tiles", sides=10, uv_scale=None,
         smooth=False):
    bpy.ops.mesh.primitive_cone_add(vertices=sides, radius1=bottom, radius2=top, depth=height, location=(0, 0, 0))
    obj = bpy.context.object
    obj.name = name
    return _place(obj, kind, loc, rot, smooth=smooth, uv_scale=uv_scale)


def sphere(name, radius, loc=(0, 0, 0), kind="#8FB86A", rings=6, segments=10, scale=(1, 1, 1), smooth=True):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings, radius=radius, location=(0, 0, 0))
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(scale=True)
    return _place(obj, kind, loc, (0, 0, 0), smooth=smooth)


def rock_lump(name, radius, scale, seed, loc=(0, 0, 0), rot=(0, 0, 0), kind="rock", bumpiness=0.16, subdivisions=2,
              flatten_bottom=True, uv_scale=None, smooth=True):
    """圓潤的卵石，底部壓平坐在地上；風格指南要圓石不要碎塊，所以預設平滑著色"""
    import random
    rng = random.Random(seed)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=subdivisions, radius=radius, location=(0, 0, 0))
    obj = bpy.context.object
    obj.name = name
    for vertex in obj.data.vertices:
        vertex.co.x *= scale[0] * (1.0 + rng.uniform(-bumpiness, bumpiness))
        vertex.co.y *= scale[1] * (1.0 + rng.uniform(-bumpiness, bumpiness))
        vertex.co.z *= scale[2] * (1.0 + rng.uniform(-bumpiness, bumpiness))
        if flatten_bottom:
            vertex.co.z = max(vertex.co.z, -radius * scale[2] * 0.12)
    obj.data.update()
    return _place(obj, kind, loc, rot, smooth=smooth, uv_scale=uv_scale or 2.0)


def card(name, size, loc, rot, texture):
    """一片會被裁切的貼圖卡片，葉團和藤蔓用；texture 是 assets/generated/textures 的檔名"""
    bpy.ops.mesh.primitive_plane_add(size=1.0, location=(0, 0, 0))
    obj = bpy.context.object
    obj.name = name
    obj.scale = (size[0], size[1], 1.0)
    bpy.ops.object.transform_apply(scale=True)
    mesh = obj.data
    uv_layer = mesh.uv_layers[0] if mesh.uv_layers else mesh.uv_layers.new(name="UVMap")
    corners = {}
    for polygon in mesh.polygons:
        for loop_index in polygon.loop_indices:
            co = mesh.vertices[mesh.loops[loop_index].vertex_index].co
            uv_layer.data[loop_index].uv = (co.x / size[0] + 0.5, co.y / size[1] + 0.5)
        polygon.use_smooth = False
    mesh.materials.append(foliage._material(texture, texture, cutout=True))
    obj.rotation_euler = tuple(math.radians(r) for r in rot)
    obj.location = tuple(loc)
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    _parts.append(obj)
    corners.clear()
    return obj


def bevel(obj, width=0.035, segments=1, angle=50.0):
    """
    每一條邊都倒角再依角度平滑，剪影和轉折就不會是硬邊。
    風格指南第 4、5 節：一切都是圓的，倒角面上會出現一條柔和的漸層
    """
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    modifier = obj.modifiers.new("bevel", 'BEVEL')
    modifier.width = width
    modifier.segments = segments
    modifier.limit_method = 'ANGLE'
    # 只有接近直角的邊才倒角，圓柱和球本來就是圓的，倒了只會多出一堆面
    modifier.angle_limit = math.radians(55.0)
    modifier.miter_outer = 'MITER_ARC'
    modifier.harden_normals = False
    bpy.ops.object.modifier_apply(modifier="bevel")
    bpy.ops.object.shade_auto_smooth(angle=math.radians(angle))


def finish(name, out_dir, cutouts=(), ao_floor=0.62, ao_band=0.25, samples=16, bake=True, bevel_width=0.035,
           bevel_segments=1):
    """
    把所有零件併成一個網格、倒角平滑、烘環境遮蔽、輸出 .gltf。
    bake 為 False 時只用高度梯度當環境遮蔽，葉片卡片用這個，不然卡片會互相遮成一團黑
    """
    bpy.ops.object.select_all(action='DESELECT')
    for part in _parts:
        part.select_set(True)
    bpy.context.view_layer.objects.active = _parts[0]
    bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    obj.name = name
    if bevel_width > 0.0:
        bevel(obj, bevel_width, bevel_segments)
    if bake:
        foliage.bake_vertex_ao(obj, floor=ao_floor, ground_band=ao_band, samples=samples)
    else:
        for existing in list(obj.data.color_attributes):
            obj.data.color_attributes.remove(existing)
        heights = [v.co.z for v in obj.data.vertices]
        foliage._vertex_ao(obj.data, min(heights), max(heights))
    os.makedirs(out_dir, exist_ok=True)
    path = foliage._export(obj, name, list(cutouts), out_dir=out_dir)
    print("[kit] %s" % os.path.relpath(path, config.PROJECT_ROOT))
    return path


# 常用的組件

def _turned(loc, rot, turn):
    """把一個零件連同位置整組繞 Z 轉 turn 度，屋頂換方向時用；零件本身只繞 x 或 y 轉，所以直接加在 z 的尤拉角上"""
    if not turn:
        return tuple(loc), tuple(rot)
    radians = math.radians(turn)
    x, y, z = loc
    return ((x * math.cos(radians) - y * math.sin(radians), x * math.sin(radians) + y * math.cos(radians), z),
            (rot[0], rot[1], rot[2] + turn))


def roof_gable(width, depth, wall_top, ridge_height, eave=0.45, thickness=0.16, kind="roof_tiles", gable_kind="plaster",
               trim="wood", turn=0.0, gable_window=True):
    """
    人字屋頂：兩片斜板加屋脊，屋簷往外挑出 eave，屋脊兩端是三角形山牆，山牆有木架和一扇小窗。
    width 是屋脊方向的面寬，depth 是屋頂往兩側斜下去的進深，wall_top 是牆頂高度，ridge_height 是屋脊比牆頂高多少。
    turn 是 90 時整個屋頂連同山牆轉 90 度，屋脊改成沿 y，同一套零件就能做出街上方向不同的房子
    """
    def put(maker, name, size, loc, rot, part_kind, **extra):
        loc, rot = _turned(loc, rot, turn)
        return maker(name, size, loc, rot, part_kind, **extra)

    half_depth = depth * 0.5 + eave
    slope_length = math.hypot(half_depth, ridge_height)
    angle = math.degrees(math.atan2(ridge_height, half_depth))
    for sign in (-1, 1):
        # 斜板從屋脊往外往下斜，所以繞 x 轉的方向和它在哪一側相反
        put(slab, "roof_%d" % sign, (width + eave * 2.0, slope_length, thickness),
            (0.0, sign * half_depth * 0.5, wall_top + ridge_height * 0.5), (-sign * angle, 0, 0), kind)
    put(box, "ridge", (width + eave * 2.0 + 0.08, 0.22, 0.2), (0, 0, wall_top + ridge_height + 0.02), (0, 0, 0), trim)
    # 山牆在屋脊的兩端，三角形的底是進深、頂點在屋脊
    for sign in (-1, 1):
        profile = [(-depth * 0.5, 0.0), (depth * 0.5, 0.0), (0.0, ridge_height)]
        loc, rot = _turned((sign * width * 0.5, 0.0, wall_top), (0, 0, 90), turn)
        prism("gable_%d" % sign, profile, 0.18, loc, rot, gable_kind)
        # 山牆上的木架：中柱加兩根斜撐，再加一扇小窗，山牆才不是一整片平塗
        put(box, "king_post_%d" % sign, (0.2, 0.18, ridge_height * 0.9),
            (sign * (width * 0.5 + 0.02), 0.0, wall_top + ridge_height * 0.45), (0, 0, 0), trim)
        for side in (-1, 1):
            brace = math.hypot(depth * 0.44, ridge_height * 0.55)
            tilt = math.degrees(math.atan2(ridge_height * 0.55, depth * 0.44))
            put(box, "gable_brace_%d_%d" % (sign, side), (0.16, brace, 0.12),
                (sign * (width * 0.5 + 0.04), side * depth * 0.22, wall_top + ridge_height * 0.28),
                (-side * tilt, 0, 0), trim)
        if gable_window:
            put(box, "gable_window_%d" % sign, (0.1, 0.52, 0.52),
                (sign * (width * 0.5 + 0.05), 0.0, wall_top + ridge_height * 0.5), (0, 0, 0), "#3C4E63")
            put(box, "gable_window_frame_%d" % sign, (0.08, 0.68, 0.14),
                (sign * (width * 0.5 + 0.06), 0.0, wall_top + ridge_height * 0.5 + 0.3), (0, 0, 0), trim)
        # 封簷板沿著山牆的斜邊釘一條，屋簷下才有一道深色的邊
        for side in (-1, 1):
            put(slab, "barge_%d_%d" % (sign, side), (0.2, slope_length, 0.14),
                (sign * (width * 0.5 + 0.12), side * half_depth * 0.5, wall_top + ridge_height * 0.5 + 0.1),
                (-side * angle, 0, 0), trim)


def window(center, size=(0.8, 1.0), depth=0.14, frame="wood", shutters=True, sill=True, wall_normal=(0, -1),
           glass="#3C4E63", plain=False):
    """
    窗：外框、深色玻璃、窗台、兩片百葉。wall_normal 是牆朝外的方向，只吃 (0,-1)、(0,1)、(-1,0)、(1,0)。
    plain 是簡化版，只有框、玻璃和窗台，背面和側面的窗用這個省面數
    """
    if plain:
        shutters = False
    x, y, z = center
    along = (1, 0) if abs(wall_normal[1]) > 0.5 else (0, 1)
    out = Vector((wall_normal[0], wall_normal[1], 0.0))
    width, height = size
    thickness = 0.1

    def offset(du, dv, dz):
        return (x + along[0] * du + out.x * dv, y + along[1] * du + out.y * dv, z + dz)

    frame_size = (width + 0.24, depth, 0.14) if along[0] else (depth, width + 0.24, 0.14)
    box("win_top", frame_size, offset(0, 0.02, height * 0.5 + 0.07), kind=frame, uv_scale=0.8)
    box("win_bottom", frame_size, offset(0, 0.02, -height * 0.5 - 0.07), kind=frame, uv_scale=0.8)
    side_size = (0.14, depth, height) if along[0] else (depth, 0.14, height)
    for side in (-1, 1):
        box("win_side", side_size, offset(side * (width * 0.5 + 0.07), 0.02, 0), kind=frame, uv_scale=0.8)
    glass_size = (width, 0.06, height) if along[0] else (0.06, width, height)
    box("win_glass", glass_size, offset(0, -0.01, 0), kind=glass)
    # 中間的窗櫺
    if not plain:
        bar = (0.07, 0.08, height) if along[0] else (0.08, 0.07, height)
        box("win_bar", bar, offset(0, 0.04, 0), kind=frame, uv_scale=0.6)
        bar_h = (width, 0.08, 0.07) if along[0] else (0.08, width, 0.07)
        box("win_bar_h", bar_h, offset(0, 0.04, 0), kind=frame, uv_scale=0.6)
    if sill:
        sill_size = (width + 0.4, depth + 0.16, 0.1) if along[0] else (depth + 0.16, width + 0.4, 0.1)
        box("win_sill", sill_size, offset(0, 0.06, -height * 0.5 - 0.16), kind="stone_wall", uv_scale=1.2)
    if shutters:
        for side in (-1, 1):
            leaf = width * 0.5
            shutter = (leaf, 0.07, height * 0.94) if along[0] else (0.07, leaf, height * 0.94)
            centre = side * (width * 0.5 + leaf * 0.5 + 0.08)
            box("shutter", shutter, offset(centre, 0.11, 0), kind="#8C5A3C", uv_scale=0.5)
            # 百葉的橫板，不然只是一塊深色方板
            for k in (-0.26, 0.26):
                slat = (leaf * 0.86, 0.05, height * 0.16) if along[0] else (0.05, leaf * 0.86, height * 0.16)
                box("slat", slat, offset(centre, 0.15, k * height), kind="#6B4630")


def door(center, size=(1.1, 2.1), depth=0.16, wall_normal=(0, -1), frame="wood", panel="#6B4630", step=True):
    """門：門框、門板、門把、石階；wall_normal 是牆朝外的方向"""
    x, y, z = center
    along = (1, 0) if abs(wall_normal[1]) > 0.5 else (0, 1)
    out = Vector((wall_normal[0], wall_normal[1], 0.0))
    width, height = size

    def offset(du, dv, dz):
        return (x + along[0] * du + out.x * dv, y + along[1] * du + out.y * dv, z + dz)

    top = (width + 0.34, depth, 0.2) if along[0] else (depth, width + 0.34, 0.2)
    box("door_top", top, offset(0, 0.03, height + 0.1), kind=frame, uv_scale=0.9)
    side_size = (0.17, depth, height) if along[0] else (depth, 0.17, height)
    for side in (-1, 1):
        box("door_side", side_size, offset(side * (width * 0.5 + 0.085), 0.03, height * 0.5), kind=frame, uv_scale=0.9)
    panel_size = (width, 0.08, height) if along[0] else (0.08, width, height)
    box("door_panel", panel_size, offset(0, -0.02, height * 0.5), kind=panel, uv_scale=0.7)
    for k in (-1, 1):
        plank = (0.06, 0.09, height * 0.92) if along[0] else (0.09, 0.06, height * 0.92)
        box("door_plank", plank, offset(k * width * 0.22, 0.03, height * 0.5), kind="#4A2F20")
    knob = 0.07
    sphere("door_knob", knob, offset(width * 0.32, 0.08, height * 0.5), kind="#C9A227")
    if step:
        step_size = (width + 0.6, 0.7, 0.14) if along[0] else (0.7, width + 0.6, 0.14)
        box("door_step", step_size, offset(0, 0.3, 0.07), kind="stone_wall", uv_scale=1.0)


def timber_frame(width, depth, wall_top, base_height, kind="wood"):
    """
    半木造的柱和樑：四角立柱、牆頂一圈橫樑，每一面牆中間再加一根中柱和兩根斜撐。
    牆面才不會出現整片沒有東西的灰泥，也是風格指南說的「細節放在建起來的東西上」
    """
    height = wall_top - base_height
    middle = base_height + height * 0.5
    for sx in (-1, 1):
        for sy in (-1, 1):
            box("post", (0.24, 0.24, height),
                (sx * (width * 0.5 - 0.1), sy * (depth * 0.5 - 0.1), middle), kind=kind, uv_scale=0.9)
    box("beam_x0", (width + 0.06, 0.2, 0.22), (0, -depth * 0.5, wall_top - 0.11), kind=kind, uv_scale=1.2)
    box("beam_x1", (width + 0.06, 0.2, 0.22), (0, depth * 0.5, wall_top - 0.11), kind=kind, uv_scale=1.2)
    box("beam_y0", (0.2, depth + 0.06, 0.22), (-width * 0.5, 0, wall_top - 0.11), kind=kind, uv_scale=1.2)
    box("beam_y1", (0.2, depth + 0.06, 0.22), (width * 0.5, 0, wall_top - 0.11), kind=kind, uv_scale=1.2)
    # 腰帶：牆的一半高度繞一圈，上下分成兩段
    box("belt_x0", (width + 0.04, 0.16, 0.18), (0, -depth * 0.5, middle), kind=kind, uv_scale=1.2)
    box("belt_x1", (width + 0.04, 0.16, 0.18), (0, depth * 0.5, middle), kind=kind, uv_scale=1.2)
    box("belt_y0", (0.16, depth + 0.04, 0.18), (-width * 0.5, 0, middle), kind=kind, uv_scale=1.2)
    box("belt_y1", (0.16, depth + 0.04, 0.18), (width * 0.5, 0, middle), kind=kind, uv_scale=1.2)
    # 兩側牆的中柱和斜撐，正面留給門窗所以只加中柱
    for sy in (-1, 1):
        box("mid_post", (0.2, 0.16, height), (0, sy * depth * 0.5, middle), kind=kind, uv_scale=0.9)
    for sx in (-1, 1):
        box("mid_post", (0.16, 0.2, height), (sx * width * 0.5, 0, middle), kind=kind, uv_scale=0.9)
        for k in (-1, 1):
            brace = math.hypot(depth * 0.22, height * 0.32)
            tilt = math.degrees(math.atan2(height * 0.32, depth * 0.22))
            box("brace", (0.14, brace, 0.14), (sx * width * 0.5, k * depth * 0.2, middle + height * 0.18),
                (-k * tilt, 0, 0), kind=kind, uv_scale=0.9)


def chimney(x, y, wall_top, height=1.6, width=0.7):
    box("chimney", (width, width, height), (x, y, wall_top + height * 0.5 - 0.3), kind="stone_wall", uv_scale=1.4)
    box("chimney_cap", (width + 0.24, width + 0.24, 0.16), (x, y, wall_top + height - 0.3), kind="#5B4A52")


def lantern(x, y, z, color="FFD98A", size=0.22):
    """掛燈：發光的燈罩加鐵頂，夜晚和屋簷下的暖點"""
    box("lantern_glass", (size, size, size * 1.2), (x, y, z), kind="glow:" + color)
    box("lantern_cap", (size + 0.1, size + 0.1, 0.07), (x, y, z + size * 0.65), kind="#4B4038")
    box("lantern_base", (size + 0.06, size + 0.06, 0.06), (x, y, z - size * 0.62), kind="#4B4038")
