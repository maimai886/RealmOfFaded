"""信徒與神職者的技能圖示：40x40，透明背景，1 px 描邊，暖色高光

為什麼另外一個檔案而不是加進 icons.py：icons.py 現在引用的 mpalette.slot_specs 已經不存在，
整個模組 import 就會炸，那是美術管線搬家搬到一半的狀態，不該由這裡順手改掉。
這個檔案只做新職業那十一個圖示，用的是同一套零件、同一組色階槽、同一條後製流程
（正交相機拍四倍大小 → 依 alpha 加權縮到 40 px → 補 1 px 描邊），
所以出來的樣子和既有的圖示是同一種質感。

用法：
    blender -b --factory-startup --python-exit-code 1 -P art_pipeline/icons_v2/faith_icons.py
"""

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# common 是用套件名稱 import 的，所以 art_pipeline 本身也要在路徑上
for sub in ("", "characters_v2", "monsters_v2", "icons_v2"):
    path = os.path.join(ROOT, sub) if sub else ROOT
    if path not in sys.path:
        sys.path.insert(0, path)

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import blenv  # noqa: E402
import glyphs as g  # noqa: E402
import meshkit as mk  # noqa: E402
import mpalette  # noqa: E402
import palette as cpalette  # noqa: E402
import pixels  # noqa: E402
import sheets  # noqa: E402
import shot  # noqa: E402

ICON_PX = 40
SUPER = 4
SKILL_DIR = os.path.join(blenv.PROJECT_ROOT, "assets", "ui", "icons", "skills")

UP = Vector((0, 0, 1))
FWD = Vector((0, 1, 0))


def _slots(main, second, accent, glow):
    """這個圖示要用的四個主要槽位，其他槽位沿用預設"""
    return mpalette.slots(
        Main=mpalette.surface(main, mask=mpalette.MASK_MAIN),
        Second=mpalette.surface(second, mask=mpalette.MASK_SECOND),
        Accent=mpalette.surface(accent, mask=mpalette.MASK_ACCENT),
        Glow=mpalette.surface(glow, picks=(2, 3, 4, 4, 5, 5), rim=0.0, bounce=0.0,
                              strength=0.35, chroma=0.5),
    )


# 信徒系的配色：黃銅的爐、骨白的布、暖光。全部用既有的色階，沒有新增色階
FAITH = ("brass", "bone", "hide_pale", "glow_ember")
# 淨化與解厄那幾個用冷一點的光，和治療分得開
CLEAR = ("bone", "brass", "hide_pale", "glow_cyan")


# 重要：mk.ring 做的是「水平面上」的一圈，mk.loft 沿著 Z 往上接，所以那組零件堆出來是立體的桶子。
# 正面看得懂的平面圖案要用 mk.box（薄板）、mk.blob（圓塊）、mk.sweep 加 squash（扁的筆觸），
# 再配 glyphs 裡的 orb、star、ring、arc_slash、flame。這裡全部照後面這一組來做


def _censer(b, scale=1.0):
    """提爐：一段鏈子吊著一顆有蓋的爐，爐口冒一點光"""
    r = 0.34 * scale
    cx, cz = 0.04, -0.10
    # 鏈子從左上垂到爐頂，做粗一點，縮到 40 px 才看得見
    mk.sweep(b, [(-0.40, 0, 0.56), (-0.20, 0, 0.44), (cx - 0.02, 0, cz + r * 1.05)],
             [0.045, 0.034, 0.028], 6, mat=g.METAL, up=FWD, squash=[0.6, 0.6, 0.6])
    mk.blob(b, (cx, 0, cz), (r, r * 0.80, r * 0.92), mat=g.MAIN, segments=14, rings_count=8)
    # 爐蓋：一片扁的亮色壓在爐頂
    mk.blob(b, (cx, -0.03, cz + r * 0.78), (r * 0.80, r * 0.56, r * 0.24), mat=g.SECOND,
            segments=14, rings_count=5)
    g.orb(b, (cx, -0.12, cz + r * 0.30), r * 0.30, g.GLOW)


def _shield(b, size=1.0, boss=True):
    """盾：上面方、下面收成尖的一片薄板，中間一顆凸起

    用 box 加 taper 做上半，下半用扁掉的 sweep 收尖，和 _heart 同一套做法。
    不用 mk.ring 加 loft，那一組是水平的環，堆起來會變成一個桶子
    """
    mk.box(b, (0, 0, 0.16 * size), (0.72 * size, 0.16 * size, 0.46 * size), mat=g.MAIN,
           taper=(0.94, 1.0))
    mk.sweep(b, [(-0.36 * size, 0, -0.06 * size), (0, 0, -0.52 * size), (0.36 * size, 0, -0.06 * size)],
             [0.20 * size, 0.06 * size, 0.20 * size], 6, mat=g.MAIN, up=FWD, squash=[0.42, 0.42, 0.42])
    if boss:
        mk.blob(b, (0, -0.11 * size, 0.08 * size), (0.15 * size, 0.06 * size, 0.15 * size),
                mat=g.GLOW, segments=10, rings_count=5)


def _beam(b, width=0.075):
    """斜斜打下來的一道光：左上一顆星，一條往右下收細的光刃

    直上直下的光柱縮到 40 px 會變成一支路燈，斜的才看得出是一道光
    """
    g.star(b, (-0.34, -0.10, 0.40), 0.34, 4, g.GLOW, 0.045)
    mk.sweep(b, [(-0.30, 0, 0.36), (0.02, 0, -0.04), (0.26, 0, -0.34)],
             [width * 1.6, width, width * 0.25], 6, mat=g.GLOW, up=FWD, squash=[0.4, 0.4, 0.4])
    mk.sweep(b, [(-0.04, 0, 0.44), (0.20, 0, 0.14)], [width * 0.7, width * 0.2], 5, mat=g.SECOND,
             up=FWD, squash=[0.4, 0.4])


def _heart(b):
    """心：兩顆圓球加下面一個尖，形狀照 icons.py 的 _glyph_heart"""
    for x in (-0.14, 0.14):
        mk.blob(b, (x, 0, 0.12), (0.24, 0.2, 0.22), mat=g.MAIN, segments=10, rings_count=5)
    mk.sweep(b, [(-0.32, 0, 0.0), (0, 0, -0.4), (0.32, 0, 0.0)], [0.2, 0.06, 0.2], 6, mat=g.MAIN,
             up=FWD, squash=[0.8, 0.8, 0.8])
    # 心上面一個十字，一眼看得出是治療不是愛心
    mk.box(b, (0, -0.22, 0.08), (0.30, 0.06, 0.09), mat=g.GLOW)
    mk.box(b, (0, -0.22, 0.08), (0.09, 0.06, 0.30), mat=g.GLOW)


def _arcs(b, radii, mat, start=-52, end=52):
    for r in radii:
        g.arc_slash(b, r, 0.035, mat, start, end, 9)


def _broken_link(b):
    """斷開的鎖環：一個環從中間斷成兩半往上下拉開，缺口中間一顆光

    兩半要離得夠開，貼在一起縮圖之後會糊成一個完整的圓，看起來像月亮
    """
    for offset, start, end in ((0.14, 20, 160), (-0.14, 200, 340)):
        pts = []
        radii = []
        for i in range(9):
            t = i / 8.0
            angle = math.radians(start + (end - start) * t)
            pts.append((math.cos(angle) * 0.40, 0, math.sin(angle) * 0.34 + offset))
            radii.append(0.075)
        mk.sweep(b, pts, radii, 6, mat=g.MAIN, up=FWD, squash=[0.45] * 9)
    g.star(b, (0.0, -0.16, 0.0), 0.30, 4, g.GLOW, 0.042)


def _dome(b):
    """罩住整隊的一層殼：兩道同心弧蓋在一顆圓上，下面一條地面線

    只有弧線的話縮圖之後像彩虹，底下要有被罩住的東西才看得出是護罩
    """
    _arcs(b, (0.40, 0.52), g.MAIN, -74, 74)
    g.arc_slash(b, 0.60, 0.030, g.GLOW, -74, 74, 9)
    g.orb(b, (0, -0.08, -0.14), 0.19, g.SECOND)
    mk.box(b, (0, 0, -0.44), (0.96, 0.14, 0.070), mat=g.SECOND)


def _sunrise(b):
    """地平線上剛升起的半個太陽加幾道光芒"""
    mk.blob(b, (0, 0.04, -0.06), (0.36, 0.22, 0.36), mat=g.GLOW, segments=14, rings_count=8)
    mk.box(b, (0, -0.06, -0.26), (1.00, 0.12, 0.10), mat=g.MAIN)
    for k in range(5):
        angle = math.pi * (0.10 + 0.20 * k)
        inner = Vector((math.cos(angle) * 0.44, -0.02, math.sin(angle) * 0.44))
        outer = inner * 1.42
        mk.sweep(b, [tuple(inner), tuple(outer)], [0.045, 0.008], 5, mat=g.SECOND, up=FWD)


def _brazier(b):
    """爐火：一個矮爐加一叢不會熄的火"""
    mk.loft(b, [mk.ring((0, 0.05, -0.44), 0.14, 0.06, 12),
                mk.ring((0, 0.02, -0.30), 0.10, 0.06, 12),
                mk.ring((0, 0.00, -0.16), 0.34, 0.12, 12),
                mk.ring((0, -0.02, -0.06), 0.36, 0.09, 12)], mat=g.MAIN)
    g.flame(b, (0, -0.06, 0.02), 0.58, 0.26, g.MAIN, g.GLOW)


def _prayer_ring(b):
    """禱詞繞著一個人轉：一顆圓球外面兩圈禱詞的環，和曦盾詠唱的罩子分得開

    這個是掛在一個人身上的增益，所以中間是一個人形的圓塊，環是圍著他轉的不是蓋在上面的
    """
    mk.blob(b, (0, 0, -0.04), (0.24, 0.20, 0.30), mat=g.SECOND, segments=12, rings_count=7)
    mk.blob(b, (0, -0.04, 0.26), (0.17, 0.15, 0.17), mat=g.SECOND, segments=10, rings_count=6)
    g.ring(b, 0.46, 0.045, g.MAIN, 0.14, 0.42)
    g.ring(b, 0.46, 0.040, g.GLOW, -0.22, 0.42)


# id -> (零件函式, 色階組)
SKILLS = {
    "censer_mastery": (lambda b: _censer(b), FAITH),
    "faith_ward": (lambda b: (_shield(b), g.ring(b, 0.52, 0.035, g.GLOW, -0.42, 0.42)), FAITH),
    "dawn_ray": (lambda b: (_beam(b), g.ring(b, 0.36, 0.030, g.MAIN, -0.34, 0.40)), FAITH),
    "mend_wound": (lambda b: _heart(b), FAITH),
    "warding_hymn": (lambda b: _prayer_ring(b), FAITH),
    "cleanse_rite": (lambda b: _broken_link(b), CLEAR),
    "dawn_circle": (lambda b: (g.ring(b, 0.54, 0.060, g.MAIN, -0.20, 0.42),
                               g.ring(b, 0.34, 0.035, g.SECOND, -0.14, 0.42),
                               g.orb(b, (0, -0.06, 0.06), 0.20, g.GLOW),
                               g.star(b, (0, -0.16, 0.06), 0.42, 4, g.GLOW, 0.03)), FAITH),
    "aegis_chant": (lambda b: _dome(b), FAITH),
    "oath_of_dawn": (lambda b: _sunrise(b), FAITH),
    "dawn_judgement": (lambda b: (_beam(b, 0.085), g.ring(b, 0.52, 0.050, g.MAIN, -0.40, 0.42),
                                  g.ring(b, 0.34, 0.030, g.SECOND, -0.36, 0.42)), FAITH),
    "unbroken_faith": (lambda b: _brazier(b), FAITH),
    # 復活術是死亡流程那邊做的技能，職業歸神職者，圖示跟著這一組一起產才不會只有它是佔位方塊
    "resurrection": (lambda b: _raise_up(b), FAITH),
    # 2026-09-17 技能樹加大之後補的十二個
    "censer_swing": (lambda b: (g.arc_slash(b, 0.46, 0.075, g.SECOND, -70, 40, 9), _censer(b, 0.72)), FAITH),
    "sear_gloom": (lambda b: (g.star(b, (0.02, -0.12, 0.06), 0.46, 5, g.GLOW, 0.055),
                              g.orb(b, (0.02, -0.02, 0.06), 0.17, g.MAIN)), FAITH),
    "hallowed_ground": (lambda b: _glowing_patch(b), FAITH),
    "vigil_stance": (lambda b: _planted(b), FAITH),
    "radiant_lance": (lambda b: _lance(b), FAITH),
    "purge_gloom": (lambda b: _burst_through(b), FAITH),
    "grace_of_dawn": (lambda b: _chevrons(b), FAITH),
    "guardian_oath": (lambda b: (_shield(b, 0.86), g.arc_slash(b, 0.60, 0.032, g.GLOW, -64, 64, 9)), FAITH),
    "sanctuary": (lambda b: _pressing_dome(b), FAITH),
    "bell_of_waking": (lambda b: _bell(b), FAITH),
    "dawn_procession": (lambda b: _procession(b), FAITH),
    "last_light": (lambda b: (g.flame(b, (0, -0.04, -0.10), 0.44, 0.19, g.MAIN, g.GLOW),
                              g.ring(b, 0.50, 0.035, g.GLOW, -0.34, 0.42),
                              g.star(b, (0, -0.14, 0.34), 0.30, 4, g.GLOW, 0.035)), FAITH),
}


def _glowing_patch(b):
    """地上一圈發亮的地面，往上飄幾點光"""
    g.ring(b, 0.56, 0.070, g.MAIN, -0.34, 0.40)
    g.ring(b, 0.34, 0.045, g.GLOW, -0.30, 0.40)
    for x, z in ((-0.22, 0.06), (0.05, 0.28), (0.26, 0.02)):
        g.orb(b, (x, -0.06, z), 0.072, g.GLOW)


def _planted(b):
    """站定不動：一面盾插在地上，下面一條厚地面線"""
    _shield(b, 0.80)
    mk.box(b, (0, 0, -0.46), (0.92, 0.16, 0.085), mat=g.SECOND)
    for x in (-0.34, 0.34):
        mk.sweep(b, [(x, 0, -0.38), (x, 0, -0.12)], [0.030, 0.012], 5, mat=g.GLOW, up=FWD,
                 squash=[0.45, 0.45])


def _lance(b):
    """一根斜插的光矛：長柄加一個尖頭"""
    mk.sweep(b, [(-0.46, 0, -0.46), (0.10, 0, 0.10)], [0.050, 0.044], 6, mat=g.SECOND, up=FWD,
             squash=[0.5, 0.5])
    mk.sweep(b, [(0.06, 0, 0.06), (0.50, 0, 0.50)], [0.135, 0.006], 6, mat=g.GLOW, up=FWD,
             squash=[0.42, 0.42])
    g.star(b, (0.46, -0.10, 0.46), 0.24, 4, g.GLOW, 0.032)


def _burst_through(b):
    """光炸開一團暗影：中間一顆暗球，外面往四面射出的光"""
    g.orb(b, (0, 0.04, -0.02), 0.26, g.SECOND, glow=False)
    for k in range(6):
        angle = math.pi * 2 * k / 6 + 0.25
        inner = Vector((math.cos(angle) * 0.24, -0.04, math.sin(angle) * 0.24))
        outer = inner * 2.1
        mk.sweep(b, [tuple(inner), tuple(outer)], [0.070, 0.006], 5, mat=g.GLOW, up=FWD,
                 squash=[0.45, 0.45])


def _chevrons(b):
    """三個往上的箭頭，越上面越亮，代表出手變快"""
    for k, z in enumerate((-0.36, -0.03, 0.30)):
        mat = g.SECOND if k == 0 else g.GLOW
        mk.sweep(b, [(-0.32, 0, z), (0, 0, z + 0.26), (0.32, 0, z)],
                 [0.055, 0.075, 0.055], 5, mat=mat, up=FWD, squash=[0.45, 0.45, 0.45])


def _pressing_dome(b):
    """從上往下壓的一層罩子，加三支往下的箭頭"""
    _arcs(b, (0.40, 0.52), g.MAIN, -74, 74)
    for x in (-0.26, 0.0, 0.26):
        mk.sweep(b, [(x, 0, 0.08), (x, 0, -0.34)], [0.050, 0.008], 5, mat=g.GLOW, up=FWD,
                 squash=[0.45, 0.45])
    mk.box(b, (0, 0, -0.46), (0.90, 0.14, 0.070), mat=g.SECOND)


def _bell(b):
    """鐘：上窄下寬的一片加鐘舌，兩側各兩道聲波"""
    mk.box(b, (0, 0, 0.08), (0.46, 0.20, 0.52), mat=g.MAIN, taper=(0.46, 1.0))
    mk.box(b, (0, 0, -0.22), (0.56, 0.22, 0.10), mat=g.MAIN)
    mk.blob(b, (0, -0.02, -0.36), (0.085, 0.075, 0.085), mat=g.SECOND, segments=10, rings_count=5)
    mk.blob(b, (0, -0.06, 0.38), (0.070, 0.060, 0.060), mat=g.GLOW, segments=8, rings_count=5)
    for r in (0.62, 0.74):
        g.arc_slash(b, r, 0.028, g.GLOW, 20, 70, 6)
        g.arc_slash(b, r, 0.028, g.GLOW, 110, 160, 6)


def _procession(b):
    """往前走：地上兩個腳印加一道往右的箭頭，上面一顆小太陽"""
    mk.blob(b, (0, 0.02, 0.36), (0.20, 0.13, 0.20), mat=g.GLOW, segments=12, rings_count=6)
    for x, z in ((-0.36, -0.24), (-0.04, -0.40)):
        mk.blob(b, (x, 0.0, z), (0.13, 0.09, 0.085), mat=g.SECOND, segments=10, rings_count=5)
    mk.sweep(b, [(-0.10, 0, 0.02), (0.34, 0, 0.02)], [0.055, 0.055], 5, mat=g.MAIN, up=FWD,
             squash=[0.45, 0.45])
    mk.sweep(b, [(0.26, 0, 0.02), (0.56, 0, 0.02)], [0.135, 0.006], 5, mat=g.MAIN, up=FWD,
             squash=[0.42, 0.42])


def _raise_up(b):
    """把人拉起來：下面一個躺著的圓塊，上面一道光和往上的箭頭"""
    mk.blob(b, (0, 0.02, -0.40), (0.38, 0.22, 0.13), mat=g.SECOND, segments=12, rings_count=6)
    mk.sweep(b, [(0, 0, -0.30), (0, 0, 0.26)], [0.10, 0.055], 6, mat=g.GLOW, up=FWD,
             squash=[0.45, 0.45])
    mk.sweep(b, [(-0.20, 0, 0.22), (0, 0, 0.48), (0.20, 0, 0.22)],
             [0.055, 0.075, 0.055], 5, mat=g.GLOW, up=FWD, squash=[0.45, 0.45, 0.45])
    g.star(b, (0, -0.12, 0.44), 0.26, 4, g.GLOW, 0.035)


def _setup_camera():
    shot.setup_scene(transparent=True)
    shot.add_lights()
    camera = shot.make_camera("icon_cam")
    shot.aim(camera, (0, 0, 0), 1.25, 22.0, 0.0)
    scene = bpy.context.scene
    scene.render.resolution_x = ICON_PX * SUPER
    scene.render.resolution_y = ICON_PX * SUPER
    return camera


def _render(objects, colors, masks, ids, tag):
    work = os.path.join(blenv.SHOT_DIR, "_icons")
    os.makedirs(work, exist_ok=True)
    line = cpalette.srgb(cpalette.OUTLINE)
    mpalette.apply_slot_set(objects, colors)
    color_raw = pixels.load_png(shot.render_to(os.path.join(work, tag + "_c.png")))
    mpalette.apply_slot_set(objects, ids)
    id_raw = pixels.load_png(shot.render_to(os.path.join(work, tag + "_i.png")))
    mpalette.apply_slot_set(objects, colors)
    color = pixels.downsample(color_raw, SUPER)
    color = pixels.inner_lines(color, pixels.finish_ids(id_raw, SUPER), line, opacity=0.5)
    return pixels.outline(color, line)


def build_one(icon_id):
    blenv.clear_scene()
    builder_fn, ramps = SKILLS[icon_id]
    colors, masks, ids = mpalette.build_materials(_slots(*ramps), "fi_" + icon_id)
    b = mk.Builder()
    builder_fn(b)
    obj = b.to_object("Icon_" + icon_id, colors)
    mk.shade(obj, angle=math.radians(50))
    blenv.look_at([obj])
    _setup_camera()
    return _render([obj], colors, masks, ids, icon_id)


def render_all(ids=None):
    os.makedirs(SKILL_DIR, exist_ok=True)
    made = []
    for icon_id in (ids or list(SKILLS)):
        image = build_one(icon_id)
        path = os.path.join(SKILL_DIR, icon_id + ".png")
        pixels.save_png(image, path)
        sheets.write_import(path)
        made.append(path)
    return made


if __name__ == "__main__":
    for made in render_all():
        print("[faith_icons] " + made)
