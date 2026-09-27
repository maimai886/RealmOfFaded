"""
每張地圖的地標和邊界大件：森林的千年大樹與苔蘚神龕、碎石谷的層疊崖壁、岩拱和洞口、地窟的刻紋石柱、
崩塌的大廳和 Boss 台座。輸出 .gltf 到 assets/generated/models/landmarks/。
地標的規矩：一眼認得出剪影、比周圍高兩倍以上、佔地不擋走路的主要路線，擋路的範圍要同步寫進地圖檔的 blockers
"""
import math
import os
import random

import config
from props import kit

OUT_DIR = os.path.join(config.MODELS_OUT, "landmarks")


# 森林

def ancient_tree():
    """
    千年大樹：14 公尺高的粗樹幹加板根，樹冠是六片交錯的葉團卡片加兩片平躺頂片，樹幹上有苔和垂下的藤。
    卡片樹不烘 Cycles 環境遮蔽，用高度梯度就好
    """
    rng = random.Random("ancient")
    trunk_height = 6.2
    kit.cylinder("trunk_low", 1.55, 2.4, (0, 0, 1.2), kind="bark", sides=12, uv_scale=2.2)
    kit.cylinder("trunk_mid", 1.15, 2.6, (0, 0, 3.3), kind="bark", sides=12, uv_scale=2.2)
    kit.cylinder("trunk_top", 0.85, 2.4, (0.2, 0, 5.6), (0, 4, 0), kind="bark", sides=12, uv_scale=2.2)
    # 板根：六片往外撐開的厚楔形，底部圓一點才不像木板
    for i in range(6):
        angle = i * math.tau / 6 + 0.2
        length = rng.uniform(1.8, 2.6)
        kit.prism("root_%d" % i, [(0.0, 0.0), (length, 0.0), (length * 0.35, 0.6), (0.0, 1.8)], 1.15,
                  (math.cos(angle) * 1.2, math.sin(angle) * 1.2, 0.0), (0, 0, math.degrees(angle)), "bark",
                  uv_scale=1.8)
        kit.rock_lump("root_foot_%d" % i, 0.6, (1.6, 0.9, 0.5), "root%d" % i,
                      (math.cos(angle) * (1.2 + length * 0.7), math.sin(angle) * (1.2 + length * 0.7), 0.1),
                      (0, 0, math.degrees(angle)), kind="bark", uv_scale=1.4)
    # 主枝
    for i, (angle, tilt, length) in enumerate(((0.4, 34, 3.4), (2.3, 40, 3.0), (4.3, 30, 3.6))):
        x, y = math.cos(angle), math.sin(angle)
        kit.cylinder("branch_%d" % i, 0.32, length, (x * length * 0.32, y * length * 0.32, 5.9 + length * 0.22),
                     (tilt * y, -tilt * x, 0), kind="bark", sides=8, uv_scale=1.4)
    # 樹冠：六片直立卡片加兩片平躺頂片
    for i in range(6):
        yaw = i * 180.0 / 6 + 12.0
        kit.card("canopy_%d" % i, (9.5, 7.6), (rng.uniform(-0.5, 0.5), rng.uniform(-0.5, 0.5), trunk_height + 3.4),
                 (90, rng.uniform(-8, 8), yaw), "leaf_dark")
    for i, (x, y, z, size) in enumerate(((0.0, 0.0, 12.4, 8.4), (1.6, -1.2, 11.0, 5.6))):
        kit.card("top_%d" % i, (size, size), (x, y, z), (0, 0, 24 * i), "leaf_dark")
    # 樹幹上的苔和垂藤
    # 從枝條垂下來的藤，掛在樹冠底下才像藤不像貼在樹幹上的補丁
    for i in range(4):
        angle = rng.uniform(0, math.tau)
        kit.card("vine_%d" % i, (2.6, 4.2), (math.cos(angle) * 2.6, math.sin(angle) * 2.6, 7.4),
                 (90, 0, math.degrees(angle) + 90), "leaves")
    for i in range(5):
        angle = rng.uniform(0, math.tau)
        z = rng.uniform(0.6, 2.6)
        kit.sphere("moss_%d" % i, rng.uniform(0.22, 0.34), (math.cos(angle) * 1.55, math.sin(angle) * 1.55, z),
                   kind="#4E8C46", scale=(0.5, 0.5, 1.6))
    return "ancient_tree", ["leaf_dark", "leaves"], False


def forest_shrine():
    """苔蘚神龕：三塊立石撐起的石門、階梯台座、中間一顆會發光的種子石、四周長滿苔"""
    kit.cylinder("base", 2.6, 0.26, (0, 0, 0.13), kind="rock", sides=8, uv_scale=1.8)
    kit.cylinder("base_2", 2.1, 0.24, (0, 0, 0.38), kind="rock", sides=8, uv_scale=1.6)
    for side in (-1, 1):
        kit.box("upright_%d" % side, (0.7, 0.8, 3.0), (side * 1.35, 0, 1.9), (0, side * 2.5, 0), kind="rock",
                uv_scale=2.0)
    kit.box("lintel", (3.9, 0.9, 0.6), (0, 0, 3.55), (0, 1.5, 0), kind="rock", uv_scale=2.0)
    kit.box("lintel_top", (3.2, 0.7, 0.3), (0, 0, 3.95), kind="rock", uv_scale=1.6)
    kit.box("altar", (1.2, 0.9, 0.7), (0, 0, 0.85), kind="rock", uv_scale=1.0)
    kit.sphere("seed", 0.4, (0, 0, 1.55), kind="glow:BFF0B8", scale=(0.8, 0.8, 1.1))
    kit.cone("seed_cap", 0.3, 0.0, 0.5, (0, 0, 1.95), kind="glow:AEE8B0", sides=8)
    for i in range(10):
        angle = i * math.tau / 10 + 0.3
        radius = 1.6 + (i % 3) * 0.5
        kit.sphere("moss_%d" % i, 0.34 + (i % 4) * 0.06, (math.cos(angle) * radius, math.sin(angle) * radius, 0.15),
                   kind="#4E8C46" if i % 2 else "#5FA84E", scale=(1.2, 1.0, 0.45))
    for i, (x, y) in enumerate(((-2.2, 1.6), (2.4, -1.4))):
        kit.rock_lump("stone_%d" % i, 0.7, (1.2, 1.0, 0.8), "shrine%d" % i, (x, y, 0.3), kind="cliff_rock")
    return "forest_shrine", [], True


# 碎石谷

def cliff_wall():
    """
    崖壁：8 公尺寬、7 公尺高，由三層圓潤的大岩體堆成，每層往後退並露出岩棚。
    照風格指南走圓潤路線，剪影是一顆顆飽滿的大石頭，不是方塊牆
    """
    rng = random.Random("cliff_wall")
    tiers = ((0.0, 2.4, 2.3, 3), (0.9, 4.4, 1.9, 3), (2.0, 5.9, 1.5, 2))
    for tier, (back, top, radius, count) in enumerate(tiers):
        for i in range(count):
            x = (i - (count - 1) * 0.5) * (7.4 / max(count, 1))
            kit.rock_lump("tier_%d_%d" % (tier, i), radius, (1.5, 1.05, 1.15), "cw%d%d" % (tier, i),
                          (x + rng.uniform(-0.4, 0.4), back + rng.uniform(-0.3, 0.3), top - radius * 1.15),
                          (0, 0, rng.uniform(0, 360)), kind="cliff_rock", bumpiness=0.13,
                          flatten_bottom=False)
        # 每層前緣壓一塊扁的岩棚
        kit.rock_lump("ledge_%d" % tier, radius * 0.9, (2.6, 1.1, 0.34), "cwl%d" % tier,
                      (rng.uniform(-0.5, 0.5), back - radius * 0.55, top - 0.3), kind="cliff_rock",
                      bumpiness=0.1, flatten_bottom=False)
    # 腳下的碎石堆
    for i in range(4):
        kit.rock_lump("scree_%d" % i, rng.uniform(0.6, 1.0), (1.4, 1.1, 0.7), "cws%d" % i,
                      (rng.uniform(-3.4, 3.4), -1.5 + rng.uniform(-0.5, 0.5), 0.2), kind="cliff_rock")
    return "cliff_wall", [], True


def rock_arch():
    """岩拱：跨距 7 公尺、頂高 8 公尺的天然拱，由一顆顆圓岩堆成，碎石谷從遠處就看得到的剪影"""
    rng = random.Random("arch")
    span = 7.0
    for side in (-1, 1):
        for i, (radius, z, scale) in enumerate(((1.7, 0.9, (1.15, 1.2, 1.0)), (1.5, 2.6, (1.0, 1.05, 1.0)),
                                                (1.3, 4.0, (0.95, 1.0, 0.95)))):
            kit.rock_lump("pier_%d_%d" % (side, i), radius, scale, "arch%d%d" % (side, i),
                          (side * span * 0.5 + rng.uniform(-0.25, 0.25), rng.uniform(-0.25, 0.25), z),
                          (0, 0, rng.uniform(0, 360)), kind="cliff_rock", bumpiness=0.12,
                          flatten_bottom=i == 0)
    segments = 7
    for i in range(segments):
        t = (i + 0.5) / segments
        angle = math.pi * t
        kit.rock_lump("arch_%d" % i, 1.25, (1.0, 1.05, 0.85), "archtop%d" % i,
                      (math.cos(angle) * span * 0.5, rng.uniform(-0.2, 0.2), 4.6 + math.sin(angle) * 2.9),
                      (0, math.degrees(-angle) + 90, rng.uniform(0, 360)), kind="cliff_rock", bumpiness=0.12,
                      flatten_bottom=False)
    for i in range(4):
        kit.rock_lump("rubble_%d" % i, 0.55, (1.2, 1.0, 0.7), "arch_r%d" % i,
                      (-2.6 + i * 1.7, -2.4 + (i % 2) * 0.9, 0.2), kind="cliff_rock")
    return "rock_arch", [], True


def cave_mouth():
    """
    地窟入口：一整面圓潤的岩壁中間裂開一個黑洞口，洞口有岩框和塌落的碎石，兩側插著火把。
    洞口朝 -y，擺進地圖時把傳送點放在洞口前
    """
    rng = random.Random("mouth")
    for side in (-1, 1):
        for i, (radius, z) in enumerate(((2.6, 2.2), (2.2, 5.0))):
            kit.rock_lump("face_%d_%d" % (side, i), radius, (1.25, 1.2, 1.15), "cm%d%d" % (side, i),
                          (side * (3.4 + i * 0.3), 0.4 + rng.uniform(-0.3, 0.3), z),
                          (0, 0, rng.uniform(0, 360)), kind="cliff_rock", bumpiness=0.12, flatten_bottom=i == 0)
    for i in range(3):
        kit.rock_lump("brow_%d" % i, 2.0, (1.3, 1.2, 0.8), "cmb%d" % i,
                      ((i - 1) * 2.2, 0.5, 6.0 + rng.uniform(-0.3, 0.3)), (0, 0, rng.uniform(0, 360)),
                      kind="cliff_rock", bumpiness=0.12, flatten_bottom=False)
    kit.rock_lump("back", 3.9, (1.7, 0.6, 1.3), "cmback", (0.0, 2.5, 3.0), kind="cliff_rock", bumpiness=0.1,
                  flatten_bottom=False)
    # 洞口內的黑暗
    kit.box("dark", (3.0, 1.4, 4.4), (0, 1.3, 2.2), kind="#1B1622")
    for i in range(5):
        kit.rock_lump("fall_%d" % i, 0.5 + (i % 3) * 0.12, (1.2, 1.0, 0.7), "cmr%d" % i,
                      (-3.2 + i * 1.6, -1.9 - (i % 2) * 0.7, 0.2), kind="cliff_rock")
    for side in (-1, 1):
        kit.cylinder("torch_%d" % side, 0.1, 1.8, (side * 2.9, -1.4, 1.7), (0, side * 8, 0), kind="wood", sides=6)
        kit.sphere("flame_%d" % side, 0.32, (side * 3.0, -1.4, 2.6), kind="glow:FF9A45", scale=(0.8, 0.8, 1.4))
    return "cave_mouth", [], True


def stone_stack():
    """谷地路邊的疊石堆，三到四塊越往上越小，當路標"""
    heights = ((1.0, 0.0), (0.72, 0.95), (0.5, 1.6), (0.32, 2.05))
    for i, (radius, z) in enumerate(heights):
        kit.rock_lump("stack_%d" % i, radius, (1.2, 1.0, 0.55), "stack%d" % i, (0, 0, z), (0, 0, i * 27),
                      kind="cliff_rock", flatten_bottom=False)
    return "stone_stack", [], True


def dead_stump():
    """枯掉的樹樁，谷地和森林邊界的點綴"""
    kit.cylinder("stump", 0.75, 1.5, (0, 0, 0.75), (0, 3, 0), kind="bark", sides=10, uv_scale=1.4)
    kit.cylinder("stump_top", 0.78, 0.16, (0.05, 0, 1.52), kind="#6B4630", sides=10)
    for i, (angle, length, tilt) in enumerate(((0.6, 1.6, 55), (3.0, 1.2, 65))):
        kit.cylinder("branch_%d" % i, 0.16, length, (math.cos(angle) * 0.5, math.sin(angle) * 0.5, 1.5),
                     (tilt * math.sin(angle), -tilt * math.cos(angle), 0), kind="bark", sides=6)
    for i in range(3):
        angle = i * 2.1
        kit.rock_lump("root_%d" % i, 0.32, (1.6, 0.8, 0.5), "stump%d" % i,
                      (math.cos(angle) * 0.85, math.sin(angle) * 0.85, 0.1), (0, 0, math.degrees(angle)), kind="bark")
    return "dead_stump", [], True


# 地窟

def carved_pillar():
    """地窟的刻紋石柱：方形柱身、上下有線腳、四面刻著發光的紋路，比一般柱子高，撐出大廳的氣勢"""
    kit.box("plinth", (1.7, 1.7, 0.4), (0, 0, 0.2), kind="cave_rock", uv_scale=1.6)
    kit.box("plinth_2", (1.45, 1.45, 0.24), (0, 0, 0.52), kind="cave_rock", uv_scale=1.2)
    kit.cylinder("shaft", 0.62, 4.4, (0, 0, 2.84), kind="cave_rock", sides=8, uv_scale=2.2)
    for z in (1.4, 3.0, 4.4):
        kit.cylinder("band", 0.72, 0.18, (0, 0, z), kind="cave_rock", sides=8, uv_scale=0.8)
    for i in range(4):
        angle = i * 90.0
        kit.box("rune", (0.14, 0.1, 1.2), (math.cos(math.radians(angle)) * 0.6, math.sin(math.radians(angle)) * 0.6,
                                           2.2), (0, 0, angle), kind="glow:7FE6D9")
    kit.box("capital", (1.5, 1.5, 0.34), (0, 0, 5.2), kind="cave_rock", uv_scale=1.2)
    kit.box("capital_2", (1.8, 1.8, 0.22), (0, 0, 5.48), kind="cave_rock", uv_scale=1.2)
    return "carved_pillar", [], True


def broken_pillar():
    """崩塌的石柱：柱身斷在半空，旁邊躺著滾落的柱段"""
    kit.box("plinth", (1.6, 1.6, 0.36), (0, 0, 0.18), kind="cave_rock", uv_scale=1.6)
    kit.cylinder("shaft", 0.6, 2.2, (0, 0, 1.4), (0, 4, 0), kind="cave_rock", sides=8, uv_scale=2.0)
    kit.rock_lump("break", 0.7, (1.0, 1.0, 0.5), "brokenp", (0.1, 0, 2.5), kind="cave_rock", flatten_bottom=False)
    kit.cylinder("fallen", 0.58, 2.6, (2.2, 0.6, 0.58), (0, 90, 24), kind="cave_rock", sides=8, uv_scale=2.0)
    kit.cylinder("fallen_2", 0.5, 1.4, (-1.8, -1.0, 0.5), (0, 90, -40), kind="cave_rock", sides=8, uv_scale=2.0)
    for i in range(4):
        kit.rock_lump("rubble_%d" % i, 0.34, (1.2, 1.0, 0.6), "bp%d" % i,
                      (-1.4 + i * 1.1, -1.6 + (i % 2) * 2.4, 0.12), kind="cave_rock")
    return "broken_pillar", [], True


def boss_dais():
    """
    Boss 房的台座：貼在地板上的圓形法陣，只有一階很矮的邊，角色站上去不會陷進去。
    外圈四座火盆和四根斷柱把決戰的場地框出來
    """
    sides = 12
    kit.cylinder("rim", 5.5, 0.22, (0, 0, 0.11), kind="cave_rock", sides=sides, uv_scale=2.4)
    kit.cylinder("floor", 5.0, 0.16, (0, 0, 0.16), kind="dungeon_floor", sides=sides, uv_scale=2.4)
    kit.cylinder("inner", 3.0, 0.06, (0, 0, 0.25), kind="dungeon_floor", sides=sides, uv_scale=1.6)
    for i in range(sides):
        angle = i * math.tau / sides
        kit.box("rune", (0.8, 0.18, 0.05), (math.cos(angle) * 4.1, math.sin(angle) * 4.1, 0.26),
                (0, 0, math.degrees(angle) + 90), kind="glow:9B6BE6")
        kit.box("rune_inner", (0.5, 0.12, 0.05), (math.cos(angle + 0.26) * 2.6, math.sin(angle + 0.26) * 2.6, 0.29),
                (0, 0, math.degrees(angle) + 30), kind="glow:9B6BE6")
    for i in range(4):
        angle = math.tau * i / 4 + math.pi / 4
        x, y = math.cos(angle) * 6.3, math.sin(angle) * 6.3
        kit.cylinder("brazier_foot", 0.42, 0.22, (x, y, 0.11), kind="cave_rock", sides=8, uv_scale=0.8)
        kit.cylinder("brazier_leg", 0.2, 1.0, (x, y, 0.6), kind="cave_rock", sides=6, uv_scale=0.8)
        kit.cone("brazier_bowl", 0.62, 0.34, 0.46, (x, y, 1.28), kind="cave_rock", sides=8, uv_scale=0.8)
        kit.sphere("brazier_fire", 0.36, (x, y, 1.56), kind="glow:FF8A3D", scale=(1.0, 1.0, 1.2))
    return "boss_dais", [], True


def stalagmite_cluster():
    """地窟的石筍叢，三根高低不同，地上還有落石"""
    for i, (x, y, radius, height) in enumerate(((0.0, 0.0, 0.48, 2.6), (0.85, 0.4, 0.34, 1.7),
                                                (-0.6, 0.7, 0.28, 1.2))):
        kit.cone("spike_%d" % i, radius, 0.06, height, (x, y, height * 0.5), (2 * i, -3 * i, 0), kind="cave_rock",
                 sides=8, uv_scale=1.4)
    for i in range(3):
        kit.rock_lump("chip_%d" % i, 0.26, (1.2, 1.0, 0.6), "stal%d" % i,
                      (-1.0 + i * 0.9, -0.9 + (i % 2) * 1.6, 0.1), kind="cave_rock")
    return "stalagmite_cluster", [], True


def collapsed_arch():
    """崩塌的拱門：半邊還立著、半邊塌成一堆，地窟的大廳靠這個看出曾經是人造的"""
    kit.box("jamb", (1.3, 1.6, 4.0), (-2.4, 0, 2.0), kind="cave_rock", uv_scale=2.0)
    for i in range(4):
        angle = math.pi * (i + 0.5) / 8
        kit.box("arch_%d" % i, (0.9, 1.6, 0.7), (-math.cos(angle) * 2.4, 0, 4.0 + math.sin(angle) * 1.6),
                (0, math.degrees(angle) - 90, 0), kind="cave_rock", uv_scale=1.4)
    kit.box("stub", (1.3, 1.6, 1.8), (2.4, 0, 0.9), (0, 6, 0), kind="cave_rock", uv_scale=2.0)
    for i in range(5):
        kit.rock_lump("fall_%d" % i, 0.4 + (i % 3) * 0.14, (1.3, 1.1, 0.6), "carch%d" % i,
                      (1.2 + i * 0.7, -0.9 + (i % 3) * 0.9, 0.15), (0, 0, i * 31), kind="cave_rock")
    return "collapsed_arch", [], True


PROPS = [ancient_tree, forest_shrine, cliff_wall, rock_arch, cave_mouth, stone_stack, dead_stump,
         carved_pillar, broken_pillar, boss_dais, stalagmite_cluster, collapsed_arch]


def build():
    paths = []
    kit.build_palette()
    for make in PROPS:
        kit.reset()
        name, cutouts, bake = make()
        # 有葉片卡片的模型不倒角，卡片只是一片四邊形，倒角會把貼圖邊緣切掉
        paths.append(kit.finish(name, OUT_DIR, cutouts=cutouts, bake=bake,
                                bevel_width=0.0 if cutouts else 0.045, bevel_segments=2))
    return paths
