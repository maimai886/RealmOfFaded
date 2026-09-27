"""
晨曦鎮的建築與街道擺設，全部用 kit.py 的零件拼出來，輸出 .gltf 到 assets/generated/models/townkit/。
每一棟房子都有石造基座、灰泥或石牆、木柱橫樑、有窗框百葉窗台的窗、有門框門階的門、挑出的屋簷和封簷板，
依用途再加煙囪、招牌、遮陽棚、欄杆、貨箱，所以商店、鐵匠、旅店、倉庫從鏡頭上看得出差別。
座標系：x 是面寬、y 是進深、z 是高度，門一律開在 -y 那一面，擺進地圖時用 rotation_y 轉向。
比例參考仙境傳說的普隆德拉民房：角色高 1.7 公尺、一層樓牆高約 3.2 公尺、門高 2.1 公尺
"""
import math
import os

import config
from props import kit

OUT_DIR = os.path.join(config.MODELS_OUT, "townkit")


def _base(width, depth, height=0.36, overhang=0.18):
    """石造基座，比牆略寬，房子才不是直接插在地上"""
    kit.box("base", (width + overhang, depth + overhang, height), (0, 0, height * 0.5), kind="stone_wall", uv_scale=1.6)


def _walls(width, depth, base_height, wall_top, kind="plaster"):
    height = wall_top - base_height
    kit.box("wall", (width, depth, height), (0, 0, base_height + height * 0.5), kind=kind, uv_scale=1.6)


def house_a():
    """民房：紅瓦人字屋頂、灰泥牆配木柱、兩扇窗加花箱、一支煙囪"""
    width, depth, wall_top = 5.2, 4.4, 3.3
    _base(width, depth)
    _walls(width, depth, 0.36, wall_top)
    kit.timber_frame(width, depth, wall_top, 0.36)
    kit.roof_gable(width, depth, wall_top, 1.9)
    kit.door((0.0, -depth * 0.5, 0.36), (1.1, 2.1))
    for x in (-1.65, 1.65):
        kit.window((x, -depth * 0.5, 2.05), (0.85, 1.0))
        kit.box("flowerbox", (1.05, 0.34, 0.26), (x, -depth * 0.5 - 0.26, 1.42), kind="wood", uv_scale=0.6)
        for k in (-1, 0, 1):
            kit.sphere("bloom", 0.16, (x + k * 0.32, -depth * 0.5 - 0.26, 1.62), kind="#8FBF63", scale=(1, 1, 0.7))
            kit.sphere("petal", 0.09, (x + k * 0.32, -depth * 0.5 - 0.3, 1.72),
                       kind="#E8738C" if k % 2 == 0 else "#F2C14E")
    for x in (-1.5, 1.5):
        kit.window((x, depth * 0.5, 2.05), (0.8, 0.95), wall_normal=(0, 1), plain=True)
    kit.chimney(width * 0.5 - 0.7, 0.9, wall_top + 1.2, height=1.5)
    kit.lantern(0.95, -depth * 0.5 - 0.12, 2.5)
    return "house_a"


def house_b():
    """民房另一款：屋脊轉向、屋簷下有木製陽台、牆是石材加灰泥兩段"""
    width, depth, wall_top = 4.4, 5.4, 3.9
    _base(width, depth)
    kit.box("wall_stone", (width, depth, 1.1), (0, 0, 0.36 + 0.55), kind="stone_wall", uv_scale=1.8)
    kit.box("wall_plaster", (width - 0.06, depth - 0.06, wall_top - 1.46), (0, 0, 1.46 + (wall_top - 1.46) * 0.5),
            kind="plaster", uv_scale=1.6)
    kit.timber_frame(width, depth, wall_top, 1.46)
    kit.roof_gable(depth, width, wall_top, 1.7, turn=90)  # 屋脊沿 y，山牆在前後兩面
    kit.door((0.0, -depth * 0.5, 0.36), (1.05, 2.05))
    kit.window((-1.35, -depth * 0.5, 2.2), (0.7, 0.9))
    kit.window((1.35, -depth * 0.5, 2.2), (0.7, 0.9))
    kit.window((-1.35, -depth * 0.5, 3.3), (0.6, 0.7), plain=True)
    kit.window((1.35, -depth * 0.5, 3.3), (0.6, 0.7), plain=True)
    for y in (-1.4, 1.4):
        kit.window((width * 0.5, y, 2.2), (0.7, 0.9), wall_normal=(1, 0), plain=True)
    kit.chimney(-width * 0.5 + 0.6, -1.4, wall_top + 1.0, height=1.5)
    return "house_b"


def _awning(x, y, z, width, depth, stripe_a="#D9584F", stripe_b="#F2E3C4"):
    """條紋遮陽棚，前低後高，俯視的鏡頭要看得出是斜的屋頂而不是一面招牌"""
    slope = 30.0
    strips = max(int(width / 0.42), 3)
    step = width / strips
    for i in range(strips):
        color = stripe_a if i % 2 == 0 else stripe_b
        kit.slab("awning_%d" % i, (step * 0.98, depth, 0.07), (x - width * 0.5 + step * (i + 0.5), y, z),
                 (-slope, 0, 0), color)
    for side in (-1, 1):
        kit.cylinder("awning_post", 0.07, z - 0.12, (x + side * (width * 0.5 - 0.1), y - depth * 0.5 + 0.1,
                                                     (z - 0.12) * 0.5), kind="wood", sides=8)
    kit.box("awning_rail", (width, 0.1, 0.1), (x, y - depth * 0.5 + 0.1, z - 0.2), kind="wood", uv_scale=0.8)


def _sign(x, y, z, text_color, width=1.0, height=0.62):
    """吊招牌：鐵架加木牌，牌面畫一個彩色圖形代表賣什麼"""
    kit.box("sign_arm", (0.09, 0.9, 0.09), (x, y - 0.45, z + 0.5), kind="#4B4038")
    kit.box("sign_brace", (0.08, 0.5, 0.08), (x, y - 0.22, z + 0.72), (40, 0, 0), kind="#4B4038")
    kit.box("sign_chain", (0.05, 0.05, 0.22), (x, y - 0.82, z + 0.38), kind="#4B4038")
    kit.box("sign_board", (width, 0.09, height), (x, y - 0.82, z), kind="wood", uv_scale=0.7)
    kit.box("sign_frame", (width + 0.1, 0.06, height + 0.1), (x, y - 0.86, z), kind="#4B4038")
    kit.box("sign_mark", (width * 0.45, 0.05, height * 0.45), (x, y - 0.89, z), kind=text_color)


def shop():
    """道具商店：整面的店頭窗台、條紋遮陽棚、吊招牌、門口的木箱與酒桶"""
    width, depth, wall_top = 5.8, 4.6, 3.4
    _base(width, depth)
    _walls(width, depth, 0.36, wall_top)
    kit.timber_frame(width, depth, wall_top, 0.36)
    kit.roof_gable(width, depth, wall_top, 1.8)
    # 店頭：左邊是門，右邊是開放的櫃台窗口
    kit.door((-1.7, -depth * 0.5, 0.36), (1.1, 2.1))
    counter_x = 1.2
    kit.box("counter_gap", (2.6, 0.5, 1.5), (counter_x, -depth * 0.5 + 0.1, 1.9), kind="#2F2A33")
    kit.box("counter_top", (3.0, 0.7, 0.16), (counter_x, -depth * 0.5 - 0.1, 1.2), kind="wood", uv_scale=0.8)
    kit.box("counter_front", (2.7, 0.14, 0.86), (counter_x, -depth * 0.5 - 0.3, 0.73), kind="#8C5A3C", uv_scale=0.6)
    for side in (-1, 1):
        kit.box("counter_post", (0.16, 0.5, 1.6), (counter_x + side * 1.35, -depth * 0.5 + 0.1, 1.9), kind="wood",
                uv_scale=0.8)
    kit.box("counter_head", (3.0, 0.5, 0.2), (counter_x, -depth * 0.5 + 0.1, 2.7), kind="wood", uv_scale=0.8)
    # 櫃台上擺兩瓶藥水
    for k, color in ((-0.8, "#D9584F"), (-0.4, "#5BA8D9"), (0.9, "#8FBF63")):
        kit.cylinder("bottle", 0.09, 0.28, (counter_x + k, -depth * 0.5 - 0.1, 1.42), kind=color, sides=8)
    _awning(counter_x, -depth * 0.5 - 0.7, 2.95, 3.4, 1.5)
    _sign(-1.7, -depth * 0.5 - 0.2, 2.65, "#5BA8D9", 1.0, 0.6)
    kit.window((2.2, depth * 0.5, 2.1), (0.8, 0.95), wall_normal=(0, 1), plain=True)
    kit.window((-2.0, depth * 0.5, 2.1), (0.8, 0.95), wall_normal=(0, 1), plain=True)
    kit.chimney(-width * 0.5 + 0.7, 1.2, wall_top + 1.1, height=1.4)
    return "shop"


def smithy():
    """鐵匠鋪：石牆、深色金屬屋頂、側邊開放的鍛造爐和大煙囪、門口的鐵砧與工具架"""
    width, depth, wall_top = 6.0, 5.0, 3.2
    _base(width, depth, height=0.4, overhang=0.24)
    kit.box("wall", (width, depth, wall_top - 0.4), (0, 0, 0.4 + (wall_top - 0.4) * 0.5), kind="stone_wall",
            uv_scale=2.0)
    kit.timber_frame(width, depth, wall_top, 0.4)
    kit.roof_gable(width, depth, wall_top, 1.5, kind="#5C5560", gable_kind="wood", trim="#3E3A42")
    kit.door((-1.4, -depth * 0.5, 0.4), (1.3, 2.2), panel="#4A2F20")
    # 開放的爐口
    kit.box("forge_gap", (2.2, 0.5, 1.6), (1.6, -depth * 0.5 + 0.1, 1.55), kind="#241C22")
    kit.box("forge_fire", (1.5, 0.3, 0.5), (1.6, -depth * 0.5 - 0.05, 1.0), kind="glow:FF8A3D")
    kit.box("forge_lintel", (2.6, 0.6, 0.3), (1.6, -depth * 0.5 + 0.1, 2.5), kind="stone_wall", uv_scale=1.2)
    kit.box("forge_hood", (2.4, 1.0, 0.9), (1.6, -depth * 0.5 + 0.3, 3.1), (18, 0, 0), kind="#5C5560")
    kit.box("chimney_big", (1.1, 1.1, 3.2), (1.6, -depth * 0.5 + 0.9, 4.2), kind="stone_wall", uv_scale=1.6)
    kit.box("chimney_cap", (1.4, 1.4, 0.2), (1.6, -depth * 0.5 + 0.9, 5.85), kind="#3E3A42")
    # 鐵砧、水槽、工具架
    kit.box("anvil_stump", (0.6, 0.6, 0.5), (-2.6, -depth * 0.5 - 1.1, 0.25), kind="bark", uv_scale=0.6)
    kit.box("anvil_body", (0.66, 0.3, 0.22), (-2.6, -depth * 0.5 - 1.1, 0.61), kind="#4B4E57")
    kit.box("anvil_horn", (0.34, 0.2, 0.12), (-2.95, -depth * 0.5 - 1.1, 0.68), kind="#4B4E57")
    kit.box("tool_rack", (1.6, 0.14, 1.3), (-1.4, depth * 0.5 + 0.08, 1.05), kind="wood", uv_scale=0.7)
    for k in (-0.5, 0.0, 0.5):
        kit.box("tool", (0.1, 0.1, 0.8), (-1.4 + k, depth * 0.5 + 0.18, 1.2), kind="#4B4E57")
    kit.window((-2.0, depth * 0.5, 2.1), (0.8, 0.9), wall_normal=(0, 1), plain=True)
    _sign(-1.4, -depth * 0.5 - 0.2, 2.55, "#B8863B", 1.0, 0.6)
    return "smithy"


def inn():
    """旅店：兩層樓、二樓木造挑出、有欄杆的陽台、屋簷下一排燈籠、大招牌"""
    width, depth = 7.0, 5.4
    first, second = 3.3, 6.2
    _base(width, depth, height=0.4)
    kit.box("wall_1", (width, depth, first - 0.4), (0, 0, 0.4 + (first - 0.4) * 0.5), kind="stone_wall", uv_scale=2.0)
    # 二樓往外挑出，下面有斜撐
    kit.box("wall_2", (width + 0.5, depth + 0.5, second - first), (0, 0, first + (second - first) * 0.5),
            kind="plaster", uv_scale=1.6)
    kit.timber_frame(width + 0.5, depth + 0.5, second, first)
    for x in (-2.4, 0.0, 2.4):
        kit.box("bracket", (0.18, 0.5, 0.5), (x, -depth * 0.5 - 0.1, first - 0.1), (45, 0, 0), kind="wood",
                uv_scale=0.6)
    kit.roof_gable(width + 0.5, depth + 0.5, second, 2.0, eave=0.55)
    kit.door((-1.9, -depth * 0.5, 0.4), (1.3, 2.3))
    kit.window((1.1, -depth * 0.5, 2.0), (1.1, 1.2))
    kit.window((3.0, -depth * 0.5, 2.0), (0.8, 1.1))
    # 陽台
    balcony_z = first + 0.1
    kit.box("balcony_floor", (4.4, 1.2, 0.16), (0.4, -depth * 0.5 - 0.85, balcony_z), kind="wood", uv_scale=0.9)
    for x in (-1.7, 0.4, 2.5):
        kit.box("balcony_post", (0.12, 0.12, 0.9), (x, -depth * 0.5 - 1.4, balcony_z + 0.5), kind="wood", uv_scale=0.5)
    kit.box("balcony_rail", (4.4, 0.12, 0.12), (0.4, -depth * 0.5 - 1.4, balcony_z + 0.95), kind="wood", uv_scale=0.8)
    kit.box("balcony_rail_low", (4.4, 0.1, 0.1), (0.4, -depth * 0.5 - 1.4, balcony_z + 0.5), kind="wood", uv_scale=0.8)
    for x in (-1.4, -0.6, 1.2, 2.0):
        kit.window((x, -depth * 0.5 - 0.25, 4.6), (0.7, 1.0), plain=True)
    for x in (-2.6, 2.6):
        kit.window((x, -depth * 0.5 - 0.25, 4.6), (0.7, 1.0))
    for y in (-1.4, 1.4):
        kit.window((width * 0.5 + 0.25, y, 4.6), (0.7, 1.0), wall_normal=(1, 0), plain=True)
        kit.window((-width * 0.5 - 0.25, y, 4.6), (0.7, 1.0), wall_normal=(-1, 0), plain=True)
    for x in (-2.8, -1.0, 0.8, 2.6):
        kit.lantern(x, -depth * 0.5 - 0.95, first - 0.35, "FFC46B", 0.2)
    _sign(-1.9, -depth * 0.5 - 0.3, 2.7, "#C9A227", 1.2, 0.7)
    kit.chimney(width * 0.5 - 0.8, 1.6, second + 1.4, height=1.6, width=0.8)
    return "inn"


def storage():
    """倉庫：寬矮的坡屋頂、雙開大門、貨物斜坡、外牆靠著木箱和酒桶"""
    width, depth, wall_top = 6.6, 5.2, 3.0
    _base(width, depth, height=0.44, overhang=0.3)
    kit.box("wall", (width, depth, wall_top - 0.44), (0, 0, 0.44 + (wall_top - 0.44) * 0.5), kind="wood", uv_scale=2.0)
    kit.timber_frame(width, depth, wall_top, 0.44)
    kit.roof_gable(width, depth, wall_top, 1.2, eave=0.6, gable_kind="wood")
    # 雙開大門
    kit.box("gate_frame_top", (3.4, 0.2, 0.26), (0, -depth * 0.5 - 0.02, 2.75), kind="wood", uv_scale=0.9)
    for side in (-1, 1):
        kit.box("gate_side", (0.2, 0.2, 2.3), (side * 1.6, -depth * 0.5 - 0.02, 1.59), kind="wood", uv_scale=0.9)
        kit.box("gate_panel", (1.4, 0.1, 2.2), (side * 0.75, -depth * 0.5 - 0.1, 1.54), kind="#6B4630", uv_scale=0.8)
        for k in (-0.4, 0.0, 0.4):
            kit.box("gate_plank", (0.08, 0.06, 2.1), (side * 0.75 + k, -depth * 0.5 - 0.17, 1.54), kind="#4A2F20")
        kit.box("gate_brace", (1.3, 0.06, 0.12), (side * 0.75, -depth * 0.5 - 0.17, 2.3), (0, side * 12, 0),
                kind="#4A2F20")
    kit.box("ramp", (3.6, 1.2, 0.16), (0, -depth * 0.5 - 0.6, 0.34), (-9, 0, 0), kind="wood", uv_scale=1.0)
    kit.window((-2.4, -depth * 0.5, 2.3), (0.7, 0.7), plain=True)
    kit.window((2.4, -depth * 0.5, 2.3), (0.7, 0.7), plain=True)
    # 靠牆的貨物
    for k, (x, y, z, s) in enumerate(((-2.9, depth * 0.5 + 0.5, 0.0, 0.8), (-2.1, depth * 0.5 + 0.55, 0.0, 0.7),
                                      (-2.6, depth * 0.5 + 0.5, 0.8, 0.62))):
        kit.box("crate_%d" % k, (s, s, s), (x, y, z + s * 0.5), (0, 0, 12 * k), kind="wood", uv_scale=0.5)
        kit.box("crate_band_%d" % k, (s + 0.04, s + 0.04, 0.07), (x, y, z + s * 0.75), (0, 0, 12 * k), kind="#4A2F20")
    _sign(0.0, -depth * 0.5 - 0.3, 3.0, "#8FBF63", 1.1, 0.6)
    return "storage"


def town_hall():
    """
    鎮公所：晨曦鎮最大的建築，也是廣場北邊的天際線。石砌下層、灰泥上層、雙開大門、圓窗、
    角落一座開放式鐘樓掛著銅鐘，屋簷下一排燈籠
    """
    width, depth, wall_top = 8.4, 6.2, 4.6
    _base(width, depth, height=0.5, overhang=0.3)
    kit.box("wall_stone", (width, depth, 1.5), (0, 0, 0.5 + 0.75), kind="stone_wall", uv_scale=2.2)
    kit.box("wall_plaster", (width - 0.1, depth - 0.1, wall_top - 2.0), (0, 0, 2.0 + (wall_top - 2.0) * 0.5),
            kind="plaster", uv_scale=1.8)
    kit.timber_frame(width, depth, wall_top, 2.0)
    kit.roof_gable(width, depth, wall_top, 2.4, eave=0.6)
    # 正面的門廊：四根柱子撐一片小屋頂，門是雙開的
    kit.door((0.0, -depth * 0.5, 0.5), (1.9, 2.6))
    for x in (-1.9, 1.9):
        kit.cylinder("porch_post", 0.18, 3.0, (x, -depth * 0.5 - 1.2, 1.5), kind="wood", sides=8, uv_scale=1.2)
    kit.slab("porch_roof", (4.6, 1.9, 0.18), (0, -depth * 0.5 - 0.75, 3.35), (-16, 0, 0), "roof_tiles")
    kit.box("porch_beam", (4.6, 0.22, 0.24), (0, -depth * 0.5 - 1.2, 3.0), kind="wood", uv_scale=1.2)
    kit.box("porch_step", (3.6, 1.2, 0.26), (0, -depth * 0.5 - 0.9, 0.25), kind="stone_wall", uv_scale=1.2)
    # 圓窗：用八角形疊出來
    kit.cylinder("rose_frame", 0.95, 0.16, (0, -depth * 0.5 - 0.02, 3.7), (90, 0, 0), kind="wood", sides=8,
                 uv_scale=0.8)
    kit.cylinder("rose_glass", 0.78, 0.1, (0, -depth * 0.5 - 0.06, 3.7), (90, 0, 0), kind="#5BA8D9", sides=8)
    for i in range(4):
        kit.box("rose_bar", (1.5, 0.08, 0.1), (0, -depth * 0.5 - 0.12, 3.7), (0, i * 45, 0), kind="wood")
    for x in (-2.9, 2.9):
        kit.window((x, -depth * 0.5, 3.3), (0.9, 1.3))
        kit.window((x, depth * 0.5, 3.3), (0.9, 1.3), wall_normal=(0, 1), plain=True)
    for y in (-1.6, 1.6):
        kit.window((width * 0.5, y, 3.3), (0.9, 1.3), wall_normal=(1, 0), plain=True)
        kit.window((-width * 0.5, y, 3.3), (0.9, 1.3), wall_normal=(-1, 0), plain=True)
    for x in (-3.2, -1.1, 1.1, 3.2):
        kit.lantern(x, -depth * 0.5 - 0.62, 2.9, "FFC46B", 0.2)
    # 鐘樓
    tower_x, tower_y = -width * 0.5 - 0.6, depth * 0.5 - 1.4
    kit.box("bell_base", (2.6, 2.6, 5.4), (tower_x, tower_y, 2.7), kind="stone_wall", uv_scale=2.2)
    kit.box("bell_band", (2.9, 2.9, 0.26), (tower_x, tower_y, 5.5), kind="stone_wall", uv_scale=1.2)
    for sx in (-1, 1):
        for sy in (-1, 1):
            kit.box("bell_post", (0.28, 0.28, 2.0), (tower_x + sx * 1.05, tower_y + sy * 1.05, 6.7), kind="wood",
                    uv_scale=1.0)
    kit.box("bell_beam", (2.4, 0.22, 0.22), (tower_x, tower_y, 7.55), kind="wood", uv_scale=1.0)
    kit.cone("bell_body", 0.52, 0.2, 0.9, (tower_x, tower_y, 6.95), kind="#C9A227", sides=10)
    kit.sphere("bell_top", 0.16, (tower_x, tower_y, 7.42), kind="#C9A227")
    kit.box("bell_floor", (2.8, 2.8, 0.2), (tower_x, tower_y, 5.75), kind="wood", uv_scale=1.2)
    kit.cone("bell_roof", 2.2, 0.0, 1.5, (tower_x, tower_y, 8.4), kind="roof_tiles", sides=4, uv_scale=1.4)
    kit.box("bell_finial", (0.16, 0.16, 0.6), (tower_x, tower_y, 9.35), kind="#4B4038")
    return "town_hall"


def _tower(x, height=8.2, radius=1.5):
    """城門旁的塔：石身、雉堞、錐形瓦頂、箭窗"""
    kit.cylinder("tower_base", radius + 0.24, 0.6, (x, 0, 0.3), kind="stone_wall", sides=10, uv_scale=2.0)
    kit.cylinder("tower_body", radius, height - 0.6, (x, 0, 0.6 + (height - 0.6) * 0.5), kind="stone_wall", sides=10,
                 uv_scale=2.4)
    kit.cylinder("tower_ring", radius + 0.22, 0.28, (x, 0, height - 0.5), kind="stone_wall", sides=10, uv_scale=1.4)
    for i in range(10):
        angle = i * math.tau / 10
        kit.box("merlon", (0.44, 0.34, 0.5), (x + math.cos(angle) * (radius + 0.05), math.sin(angle) * (radius + 0.05),
                                              height - 0.1), (0, 0, math.degrees(angle)), kind="stone_wall",
                uv_scale=0.9)
    kit.cone("tower_roof", radius + 0.55, 0.0, 2.2, (x, 0, height + 1.2), kind="roof_tiles", sides=12, uv_scale=1.4)
    kit.box("tower_finial", (0.16, 0.16, 0.5), (x, 0, height + 2.4), kind="#4B4038")
    for z in (2.6, 4.6, 6.4):
        for sign in (-1, 1):
            kit.box("arrow_slit", (0.22, 0.3, 0.9), (x + sign * 0.0, sign * (radius - 0.02), z), kind="#2F2A33")
    kit.lantern(x, -radius - 0.2, 3.4, "FFC46B", 0.22)


def gatehouse():
    """城門樓：中間是通行的拱門，兩側各一座塔，上面是有雉堞的連橋"""
    span = 4.6
    for side in (-1, 1):
        _tower(side * (span * 0.5 + 1.6))
    # 拱門的兩根門墩和上方的橫樑
    for side in (-1, 1):
        kit.box("jamb", (0.9, 3.2, 5.0), (side * (span * 0.5 + 0.45), 0, 2.5), kind="stone_wall", uv_scale=2.2)
    kit.box("arch_top", (span + 1.8, 3.2, 1.2), (0, 0, 5.6), kind="stone_wall", uv_scale=2.2)
    # 拱形：用幾段方塊堆出圓弧的內緣
    for i in range(7):
        angle = math.pi * (i + 0.5) / 7
        kit.box("arch_stone", (0.55, 3.3, 0.5),
                (math.cos(angle) * span * 0.5, 0, 4.7 + math.sin(angle) * 0.55),
                (0, math.degrees(-angle) + 90, 0), kind="stone_wall", uv_scale=1.0)
    kit.box("bridge", (span + 3.2, 2.6, 0.5), (0, 0, 6.45), kind="stone_wall", uv_scale=2.0)
    for i in range(-3, 4):
        for sign in (-1, 1):
            kit.box("bridge_merlon", (0.5, 0.36, 0.55), (i * 0.85, sign * 1.3, 6.95), kind="stone_wall", uv_scale=0.9)
    # 門洞上方的木製門扉和吊旗
    kit.box("portcullis", (span, 0.16, 1.0), (0, 0.9, 4.6), kind="#4B4038")
    for side in (-1, 1):
        kit.box("banner", (0.9, 0.08, 2.0), (side * (span * 0.5 + 0.45), -1.65, 3.6), kind="#C4483F")
        kit.box("banner_mark", (0.4, 0.05, 0.7), (side * (span * 0.5 + 0.45), -1.72, 3.8), kind="#F2E3C4")
        kit.box("banner_rod", (1.1, 0.1, 0.1), (side * (span * 0.5 + 0.45), -1.65, 4.65), kind="#4B4038")
    return "gatehouse"


def guard_tower():
    """城牆角的單塔，和城門樓同一套式樣"""
    _tower(0.0, height=7.0, radius=1.4)
    return "guard_tower"


def fountain():
    """廣場噴泉：八角石盆盛水、中央三層石柱往上收、水從上層落進盆裡；盆緣可以坐人"""
    sides = 8
    kit.cylinder("basin_outer", 2.5, 1.0, (0, 0, 0.5), kind="stone_wall", sides=sides, uv_scale=1.6)
    kit.cylinder("basin_rim", 2.68, 0.26, (0, 0, 1.03), kind="stone_wall", sides=sides, uv_scale=1.2)
    kit.cylinder("basin_water", 2.3, 0.12, (0, 0, 0.92), kind="#4E7F8C", sides=sides)
    kit.cylinder("pillar_base", 1.15, 0.5, (0, 0, 1.2), kind="stone_wall", sides=sides, uv_scale=1.2)
    kit.cylinder("stem_1", 0.42, 0.9, (0, 0, 1.8), kind="stone_wall", sides=sides, uv_scale=0.9)
    kit.cylinder("bowl_1", 1.25, 0.22, (0, 0, 2.3), kind="stone_wall", sides=sides, uv_scale=1.0)
    kit.cylinder("bowl_1_water", 1.05, 0.08, (0, 0, 2.43), kind="#7FC6D9", sides=sides)
    kit.cylinder("stem_2", 0.3, 0.9, (0, 0, 2.85), kind="stone_wall", sides=sides, uv_scale=0.9)
    kit.cylinder("bowl_2", 0.8, 0.18, (0, 0, 3.32), kind="stone_wall", sides=sides, uv_scale=0.9)
    kit.cone("finial", 0.34, 0.06, 0.7, (0, 0, 3.75), kind="stone_wall", sides=sides, uv_scale=0.8)
    # 水從上層的盤子漫出來，用一圈薄薄的亮色環表示，不做直立的水柱，不然遠看像柱子
    kit.cylinder("spill_top", 1.32, 0.07, (0, 0, 2.38), kind="#9BD7E6", sides=sides)
    kit.cylinder("spill_low", 0.86, 0.06, (0, 0, 3.4), kind="#9BD7E6", sides=sides)
    return "fountain"


def shrine_pedestal():
    """晨曦幼苗的台座：三階八角石台、四根刻紋矮柱、中間是種樹的土壇"""
    sides = 8
    for i, (radius, height, z) in enumerate(((2.3, 0.3, 0.15), (1.95, 0.3, 0.45), (1.65, 0.32, 0.76))):
        kit.cylinder("step_%d" % i, radius, height, (0, 0, z), kind="stone_wall", sides=sides, uv_scale=1.8)
    kit.cylinder("soil", 1.15, 0.26, (0, 0, 1.05), kind="dirt", sides=sides, uv_scale=1.2)
    kit.cylinder("soil_rim", 1.3, 0.2, (0, 0, 1.02), kind="stone_wall", sides=sides, uv_scale=1.0)
    for i in range(4):
        angle = math.tau * i / 4 + math.pi / 4
        x, y = math.cos(angle) * 1.72, math.sin(angle) * 1.72
        kit.box("post_base", (0.5, 0.5, 0.2), (x, y, 1.0), (0, 0, 45), kind="stone_wall", uv_scale=0.9)
        kit.box("post", (0.34, 0.34, 1.35), (x, y, 1.72), (0, 0, 45), kind="stone_wall", uv_scale=1.1)
        kit.box("post_cap", (0.46, 0.46, 0.16), (x, y, 2.44), (0, 0, 45), kind="stone_wall", uv_scale=0.8)
        kit.box("rune", (0.16, 0.16, 0.5), (x, y, 1.75), (0, 0, 45), kind="glow:AEE8B0")
        kit.lantern(x, y, 2.76, "BFF0B8", 0.16)
    return "shrine_pedestal"


def plaza_step():
    """廣場外緣的一段石階，長 4 公尺，排成一圈就是有邊的廣場"""
    kit.box("step_low", (4.0, 1.0, 0.18), (0, 0, 0.09), kind="stone_wall", uv_scale=1.6)
    kit.box("step_high", (4.0, 0.52, 0.2), (0, 0.24, 0.28), kind="stone_wall", uv_scale=1.6)
    kit.box("kerb", (4.0, 0.22, 0.12), (0, -0.39, 0.24), kind="stone_wall", uv_scale=1.0)
    return "plaza_step"


def lamp_post():
    """街燈：石座、木柱、鐵臂吊一盞會發光的燈"""
    kit.cylinder("lamp_base", 0.3, 0.26, (0, 0, 0.13), kind="stone_wall", sides=8, uv_scale=0.8)
    kit.cylinder("lamp_pole", 0.11, 3.0, (0, 0, 1.6), kind="wood", sides=8, uv_scale=1.0)
    kit.box("lamp_arm", (0.08, 0.7, 0.08), (0, -0.3, 3.0), kind="#4B4038")
    kit.box("lamp_brace", (0.07, 0.4, 0.07), (0, -0.16, 2.78), (45, 0, 0), kind="#4B4038")
    kit.lantern(0.0, -0.6, 2.72, "FFC46B", 0.24)
    kit.cone("lamp_top", 0.16, 0.0, 0.26, (0, 0, 3.22), kind="#4B4038", sides=8)
    return "lamp_post"


def market_stall():
    """市集攤位：木架、條紋棚、擺滿蔬果的檯面"""
    kit.box("stall_top", (2.6, 1.4, 0.14), (0, 0, 1.0), kind="wood", uv_scale=0.8)
    kit.box("stall_front", (2.6, 0.12, 0.85), (0, -0.65, 0.5), kind="wood", uv_scale=0.6)
    for sx in (-1, 1):
        for sy in (-1, 1):
            kit.cylinder("stall_leg", 0.07, 0.95, (sx * 1.15, sy * 0.55, 0.48), kind="wood", sides=6)
            kit.cylinder("stall_post", 0.07, 1.3, (sx * 1.25, sy * 0.62, 1.7), kind="wood", sides=6)
    _awning(0.0, 0.0, 2.4, 2.9, 1.7)
    for i, color in enumerate(("#D9584F", "#F2C14E", "#8FBF63", "#C77FBF")):
        x = -0.95 + i * 0.63
        kit.box("tray", (0.52, 0.9, 0.1), (x, 0.0, 1.11), kind="wood", uv_scale=0.4)
        for k in (-0.22, 0.0, 0.22):
            kit.sphere("goods", 0.11, (x, k, 1.24), kind=color)
    return "market_stall"


def crate_stack():
    """堆起來的木箱，店門口和倉庫旁邊用"""
    for i, (x, y, z, s, turn) in enumerate(((0.0, 0.0, 0.0, 0.86, 0), (0.92, 0.12, 0.0, 0.66, 18),
                                            (0.1, 0.06, 0.86, 0.6, -14))):
        kit.box("crate_%d" % i, (s, s, s), (x, y, z + s * 0.5), (0, 0, turn), kind="wood", uv_scale=0.5)
        kit.box("band_a_%d" % i, (s + 0.04, s + 0.04, 0.07), (x, y, z + s * 0.78), (0, 0, turn), kind="#4A2F20")
        kit.box("band_b_%d" % i, (s + 0.04, s + 0.04, 0.07), (x, y, z + s * 0.22), (0, 0, turn), kind="#4A2F20")
    return "crate_stack"


def barrel_pair():
    """兩個酒桶加一個倒著的，桶身中間鼓、外面兩道鐵箍"""
    for i, (x, y, radius, height, tilt) in enumerate(((0.0, 0.0, 0.34, 0.86, 0), (0.78, 0.16, 0.3, 0.76, 0),
                                                      (0.36, -0.7, 0.3, 0.74, 90))):
        z = radius if tilt else height * 0.5
        kit.cylinder("barrel_%d" % i, radius, height, (x, y, z), (tilt, 0, 0), kind="wood", sides=10, uv_scale=0.6)
        kit.cylinder("belly_%d" % i, radius + 0.04, height * 0.45, (x, y, z), (tilt, 0, 0), kind="wood", sides=10,
                     uv_scale=0.6)
        for k in (-0.28, 0.28):
            kit.cylinder("hoop_%d_%d" % (i, int(k * 10)), radius + 0.05, 0.07,
                         (x, y - (k * height if tilt else 0.0), z + (0.0 if tilt else k * height)), (tilt, 0, 0),
                         kind="#4B4038", sides=10)
    return "barrel_pair"


def flower_box():
    """路邊花槽：木槽加三叢花"""
    kit.box("trough", (1.5, 0.5, 0.36), (0, 0, 0.18), kind="wood", uv_scale=0.6)
    kit.box("trough_rim", (1.62, 0.6, 0.08), (0, 0, 0.38), kind="#8C5A3C")
    kit.box("soil", (1.3, 0.34, 0.08), (0, 0, 0.36), kind="dirt", uv_scale=0.5)
    for i, color in enumerate(("#E8738C", "#F2C14E", "#C77FBF")):
        x = -0.45 + i * 0.45
        kit.sphere("leafy", 0.22, (x, 0.0, 0.5), kind="#8FBF63", scale=(1.0, 0.8, 0.6))
        kit.sphere("bloom", 0.11, (x, 0.0, 0.66), kind=color)
    return "flower_box"


def bench():
    kit.box("seat", (1.8, 0.46, 0.1), (0, 0, 0.46), kind="wood", uv_scale=0.6)
    kit.box("back", (1.8, 0.1, 0.42), (0, 0.2, 0.72), (-12, 0, 0), kind="wood", uv_scale=0.6)
    for x in (-0.72, 0.72):
        kit.box("leg", (0.12, 0.44, 0.46), (x, 0, 0.23), kind="wood", uv_scale=0.4)
    return "bench"


def cart():
    """手推車：兩個輪子、木板車斗、擺著的麻袋，路上有車轍才有來由"""
    kit.box("bed", (1.9, 1.1, 0.16), (0, 0, 0.72), kind="wood", uv_scale=0.7)
    for y in (-0.55, 0.55):
        kit.box("side", (1.9, 0.1, 0.36), (0, y, 0.95), kind="wood", uv_scale=0.6)
    kit.box("back", (0.1, 1.1, 0.36), (0.95, 0, 0.95), kind="wood", uv_scale=0.6)
    for y in (-0.62, 0.62):
        kit.cylinder("wheel", 0.5, 0.12, (-0.3, y, 0.5), (0, 90, 0), kind="wood", sides=12, uv_scale=0.5)
        kit.cylinder("hub", 0.14, 0.18, (-0.3, y, 0.5), (0, 90, 0), kind="#4B4038", sides=8)
    kit.box("axle", (0.12, 1.3, 0.12), (-0.3, 0, 0.5), kind="#4B4038")
    for x in (-1.4, -1.55):
        kit.box("handle", (1.0, 0.1, 0.1), (x, 0.0, 0.76), (0, 8, 0), kind="wood", uv_scale=0.5)
    for i, (x, y) in enumerate(((0.3, 0.2), (0.55, -0.22))):
        kit.sphere("sack_%d" % i, 0.34, (x, y, 1.0), kind="#C8B48A", scale=(1.0, 0.9, 0.8))
    return "cart"


def hedge():
    """修過的樹籬，2 公尺一段，街區之間圍出邊界"""
    kit.box("hedge_body", (2.0, 0.7, 0.9), (0, 0, 0.45), kind="#4E8C46", uv_scale=0.6)
    for i in range(5):
        x = -0.8 + i * 0.4
        kit.sphere("puff", 0.32, (x, 0.0, 0.92), kind="#5FA84E", scale=(1.0, 0.85, 0.6))
    kit.box("hedge_soil", (2.1, 0.8, 0.16), (0, 0, 0.08), kind="dirt", uv_scale=0.6)
    return "hedge"


def signpost():
    """路口的指示牌：木柱加兩塊指向不同方向的木牌"""
    kit.cylinder("post", 0.1, 2.4, (0, 0, 1.2), kind="wood", sides=8, uv_scale=0.8)
    kit.box("cap", (0.26, 0.26, 0.14), (0, 0, 2.42), kind="#4B4038")
    for i, (z, turn, color) in enumerate(((2.05, 18, "#8FBF63"), (1.6, -150, "#5BA8D9"))):
        kit.box("plank_%d" % i, (1.15, 0.09, 0.34), (0.55, 0.0, z), (0, 0, turn), kind="wood", uv_scale=0.5)
        kit.box("mark_%d" % i, (0.3, 0.05, 0.16), (0.9, 0.0, z), (0, 0, turn), kind=color)
    return "signpost"


BUILDINGS = [house_a, house_b, shop, smithy, inn, storage, town_hall, gatehouse, guard_tower]
FURNITURE = [fountain, shrine_pedestal, plaza_step, lamp_post, market_stall, crate_stack, barrel_pair, flower_box,
             bench, cart, hedge, signpost]
PROPS = BUILDINGS + FURNITURE


def build():
    paths = kit.build_palette()
    for make in PROPS:
        kit.reset()
        name = make()
        # 建築的倒角小一點，屋簷和窗框才不會被吃掉；小件的擺設倒角大一點，剪影更圓潤
        building = make in BUILDINGS
        paths.append(kit.finish(name, OUT_DIR, bevel_width=0.035 if building else 0.05,
                                bevel_segments=1 if building else 2))
    return paths
