"""
把 KayKit 的模型重新貼上手繪材質：幾何完全不動，地圖檔的 blockers 不用改。
做法：讀 KayKit 的模型，每個面用原本的貼圖座標去查調色盤顏色，依顏色和朝向分類成瓦片屋頂、灰泥牆、木頭、石材、
地窟石牆、地窟石板這些材質，再依面的朝向重算貼圖座標換成手繪貼圖，貼圖的密度用地圖檔裡的縮放換算成公尺；
其他顏色維持平塗但套上 RO 色階。環境遮蔽用 Cycles 烘進頂點色，再乘上靠近地面偏暗的梯度。
輸出到 assets/generated/models/<包>/<原名>.gltf，map_environment.place_prop 看到有重製版就自動換掉。
兩個包：town 是城鎮房屋和城牆，dungeon 是地窟的牆、地板、柱子、碎石。樹不在這裡處理，遊戲裡直接換成葉片卡片樹
"""
import colorsys
import json
import os

import bpy
import numpy as np

import config
from props import foliage
from textures import tileable

VENDOR_ROOT = os.path.join(config.PROJECT_ROOT, "assets", "vendor", "kaykit")
TOWN_JSON = os.path.join(config.PROJECT_ROOT, "data", "maps", "town.json")

# 城鎮：沒寫在地圖檔裡但之後很可能用到的零件，縮放照同類型的擺設
TOWN_EXTRA = {"wall_corner_A_outside": 3.2, "fence_wood_straight": 5.0, "building_windmill_red": 6.0}
SKIP_PREFIXES = ("tree", "trees")
# 地窟：cavern.gd 一格 3 公尺配 KayKit 4 單位的零件，縮放 0.75；碎石谷的拱門也是這一組
DUNGEON_SCALE = 0.75
DUNGEON_MODELS = ["wall", "wall_cracked", "wall_broken", "wall_corner", "wall_half", "wall_doorway", "wall_arched",
                  "wall_endcap", "wall_half_endcap", "wall_pillar", "wall_window_open", "pillar", "pillar_decorated",
                  "column", "floor_tile_large", "floor_dirt_large", "floor_tile_large_rocks", "floor_dirt_large_rocky",
                  "floor_tile_small", "floor_tile_small_broken_A", "floor_tile_small_weeds_A", "floor_dirt_small_A",
                  "rubble_large", "rubble_half", "stairs", "stairs_wide"]

# 每種材質一張貼圖對應幾公尺
TILE_METRES = {"roof_tiles": 2.0, "plaster": 1.8, "wood": 1.6, "stone_wall": 2.4, "cave_rock": 2.4, "dungeon_floor": 2.8}
# 底部這麼高的範圍內偏暗，單位是模型高度的比例
AO_BAND = 0.22
AO_FLOOR = 0.66
# 房子從這個高度比例以上的灰色牆面改成灰泥，以下是石材基座
PLASTER_BASE = 0.2


def classify_town(rgb, normal):
    """城鎮調色盤的分類，rgb 是 sRGB 0～1"""
    h, s, v = colorsys.rgb_to_hsv(*rgb)
    hue = h * 360.0
    if v < 0.22:
        return "flat"
    if s > 0.45 and (hue >= 340.0 or hue <= 18.0) and v > 0.4:
        return "roof_tiles"
    if 8.0 <= hue <= 40.0 and 0.3 <= s <= 0.8 and 0.3 <= v <= 0.82:
        return "wood"
    if s < 0.3 and v > 0.74:
        return "plaster"
    if s < 0.22 and 0.22 <= v <= 0.74:
        return "stone_wall"
    return "flat"


def classify_dungeon(rgb, normal):
    """地窟調色盤：藍灰是石牆，暖灰的水平面是石板地、直立面是石牆，青綠的苔和藤維持平塗"""
    h, s, v = colorsys.rgb_to_hsv(*rgb)
    hue = h * 360.0
    if v < 0.18:
        return "flat"
    if 170.0 <= hue <= 240.0 and s < 0.3:
        return "cave_rock"
    if 5.0 <= hue <= 50.0 and s < 0.36 and v < 0.8:
        return "dungeon_floor" if abs(normal.z) > 0.5 else "cave_rock"
    return "flat"


PACKS = {
    "town": {"classify": classify_town, "plaster_rule": True, "extension": ".gltf"},
    "dungeon": {"classify": classify_dungeon, "plaster_rule": False, "extension": ".glb"},
}


def _palette_pixels(image):
    width, height = image.size
    flat = np.empty(width * height * 4, dtype=np.float32)
    image.pixels.foreach_get(flat)
    return flat.reshape(height, width, 4), width, height


def _sample(pixels, width, height, uv):
    x = int(uv[0] % 1.0 * (width - 1))
    y = int(uv[1] % 1.0 * (height - 1))
    return pixels[y, x, :3]


def _flat_material(rgb):
    graded = tileable.grade(np.array([[rgb]], dtype=np.float32), warm=0.3, lift=0.35)[0, 0]
    name = "flat_%02x%02x%02x" % tuple(int(c * 255) for c in graded)
    existing = bpy.data.materials.get(name)
    if existing:
        return existing
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in graded]
    bsdf.inputs["Base Color"].default_value = (linear[0], linear[1], linear[2], 1.0)
    bsdf.inputs["Roughness"].default_value = 1.0
    bsdf.inputs["Metallic"].default_value = 0.0
    return mat


def _project_uv(co, normal, scale, tile):
    """
    牆面和屋頂：u 沿著水平方向、v 沿高度，所以任何角度的牆都是水平一排排的磚和瓦
    平的面：直接用 x、y
    """
    if abs(normal.z) > 0.95:
        u, v = co.x, co.y
    else:
        horizontal = (normal.x, normal.y)
        length = max((horizontal[0] ** 2 + horizontal[1] ** 2) ** 0.5, 1e-6)
        perp = (-horizontal[1] / length, horizontal[0] / length)
        u = co.x * perp[0] + co.y * perp[1]
        v = co.z
    factor = scale / tile
    return (u * factor, v * factor)


def retexture_object(obj, pixels, width, height, scale, classify, plaster_above=None):
    """
    plaster_above 給房子用：KayKit 的房子牆面和石材同一個灰色，比這個高度高的灰色直立面改成灰泥，
    下面留石材當基座，屋頂、牆、基座三種材質才分得出來
    """
    mesh = obj.data
    if not mesh.uv_layers:
        return
    uv_layer = mesh.uv_layers[0]
    classes = []
    flat_colors = []
    for polygon in mesh.polygons:
        samples = [_sample(pixels, width, height, uv_layer.data[i].uv) for i in polygon.loop_indices]
        color = np.mean(samples, axis=0)
        kind = classify(tuple(float(c) for c in color), polygon.normal)
        if kind == "stone_wall" and plaster_above is not None and abs(polygon.normal.z) < 0.5:
            if polygon.center.z > plaster_above:
                kind = "plaster"
        classes.append(kind)
        flat_colors.append(tuple(float(c) for c in color))

    mesh.materials.clear()
    slot_of = {}

    def slot(key, material):
        if key not in slot_of:
            mesh.materials.append(material)
            slot_of[key] = len(mesh.materials) - 1
        return slot_of[key]

    for polygon in mesh.polygons:
        kind = classes[polygon.index]
        if kind == "flat":
            color = flat_colors[polygon.index]
            quantized = tuple(round(c * 24) / 24 for c in color)
            polygon.material_index = slot(("flat", quantized), _flat_material(quantized))
        else:
            polygon.material_index = slot(kind, foliage._material(kind, kind))
            for loop_index in polygon.loop_indices:
                co = mesh.vertices[mesh.loops[loop_index].vertex_index].co
                uv_layer.data[loop_index].uv = _project_uv(co, polygon.normal, scale, TILE_METRES[kind])
        polygon.use_smooth = False
    mesh.update()
    foliage.bake_vertex_ao(obj, floor=AO_FLOOR, ground_band=AO_BAND)


def _town_models():
    with open(TOWN_JSON, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    models = {}
    for prop in data.get("props", []):
        model = prop["model"]
        if not model.startswith("vendor/kaykit/town/"):
            continue
        name = model.split("/")[-1]
        if name.startswith(SKIP_PREFIXES):
            continue
        models.setdefault(name, []).append(float(prop.get("scale", 1.0)))
    result = {name: max(set(scales), key=scales.count) for name, scales in models.items()}
    for name, scale in TOWN_EXTRA.items():
        result.setdefault(name, scale)
    return result


def retexture_model(pack, name, scale):
    from common import scene
    settings = PACKS[pack]
    scene.reset_scene()
    bpy.ops.import_scene.gltf(filepath=os.path.join(VENDOR_ROOT, pack, name + settings["extension"]))
    objects = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
    palette = None
    for obj in objects:
        for material in obj.data.materials:
            if material and material.use_nodes:
                for node in material.node_tree.nodes:
                    if node.type == 'TEX_IMAGE' and node.image:
                        palette = node.image
    if palette is None:
        raise RuntimeError("%s 找不到調色盤貼圖" % name)
    pixels, width, height = _palette_pixels(palette)
    plaster_above = None
    if settings["plaster_rule"] and name.startswith("building_") and "tower" not in name:
        # 基座留模型高度的兩成當石材
        z_values = [obj.matrix_world @ v.co for obj in objects for v in obj.data.vertices]
        z_min = min(v.z for v in z_values)
        z_max = max(v.z for v in z_values)
        plaster_above = z_min + (z_max - z_min) * PLASTER_BASE
    for obj in objects:
        retexture_object(obj, pixels, width, height, scale, settings["classify"], plaster_above)
    out_dir = os.path.join(config.MODELS_OUT, pack)
    os.makedirs(out_dir, exist_ok=True)
    bpy.ops.object.select_all(action='DESELECT')
    for obj in bpy.context.scene.objects:
        obj.select_set(True)
    path = os.path.join(out_dir, name + ".gltf")
    bpy.ops.export_scene.gltf(filepath=path, export_format='GLTF_SEPARATE', export_keep_originals=True,
                              use_selection=True, export_apply=True, export_vertex_color='ACTIVE',
                              export_normals=True, export_yup=True)
    foliage.patch_gltf(path, [])
    return path


def build():
    paths = []
    for name, scale in sorted(_town_models().items()):
        paths.append(retexture_model("town", name, scale))
        print("[retex] town/%s" % name)
    return paths


def build_dungeon():
    paths = []
    for name in DUNGEON_MODELS:
        paths.append(retexture_model("dungeon", name, DUNGEON_SCALE))
        print("[retex] dungeon/%s" % name)
    return paths
