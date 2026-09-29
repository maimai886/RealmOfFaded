"""奪色的道具圖示：顏料、濃顏料、色種，40x40，透明背景，和既有道具圖示同一套零件和後製

為什麼另外一個檔案而不是加進 icons.py：icons.py 引用的 mpalette.slot_specs 已經不存在，
整個模組 import 就會炸，理由和 faith_icons.py 一樣。色魄是卡片，卡面用怪物圖，
不經過 Blender，在 soul_cards.py。

用法：
    blender -b --factory-startup --python-exit-code 1 -P art_pipeline/icons/colour_icons.py -- [id ...]
"""

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for sub in ("", "common", "monsters", "icons"):
    path = os.path.join(ROOT, sub) if sub else ROOT
    if path not in sys.path:
        sys.path.insert(0, path)

import bpy  # noqa: E402
import numpy as np  # noqa: E402
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
ITEM_DIR = os.path.join(blenv.PROJECT_ROOT, "assets", "ui", "icons", "items")

UP = Vector((0, 0, 1))
FWD = Vector((0, 1, 0))

# 既有的道具圖示外圈有一格深褐色的描邊，pixels.outline 改版後很淡，這裡自己補回來才和旁邊的圖示一樣
EDGE = np.array([0.17, 0.11, 0.08], dtype=np.float32)
EDGE_ALPHA = 0.85


def _slots(main, second, accent, glow):
    """這個圖示要用的四個主要槽位，其他槽位沿用預設"""
    return mpalette.slots(
        Main=mpalette.surface(main, mask=mpalette.MASK_MAIN),
        Second=mpalette.surface(second, mask=mpalette.MASK_SECOND),
        Accent=mpalette.surface(accent, mask=mpalette.MASK_ACCENT),
        Glow=mpalette.surface(glow, picks=(2, 3, 4, 4, 5, 5), rim=0.0, bounce=0.0,
                              strength=0.35, chroma=0.5),
    )


# 顏料要一眼看得出顏色，既有的綠、藍色階亮部會退成淡薄荷色，另外給兩條飽和的色階，只在這個檔案裡加
mpalette.RAMPS.setdefault("paint_green", ["#173d17", "#246022", "#33852c", "#4ea83c", "#7fcb5a", "#c9eea0"])
mpalette.RAMPS.setdefault("paint_blue", ["#132a52", "#1c4480", "#2862ad", "#3f86d2", "#78b6ee", "#cfe6ff"])
# 術士考試的溶液：黃、紅兩條，藍的沿用顏料的藍
mpalette.RAMPS.setdefault("solution_yellow", ["#5a3d0c", "#8a6214", "#b98d1e", "#dfb83a", "#f3dc7a", "#fff6cf"])
mpalette.RAMPS.setdefault("solution_red", ["#4a1016", "#7a1a22", "#a82a30", "#d0483f", "#ec8a72", "#ffd6c8"])


def _jar(b, rich=False):
    """顏料罐：矮胖的陶罐開著口，顏料滿到罐口堆起來一坨，前面一道流下來的滴痕。
    濃的罐子換成黃銅、顏料會發光、旁邊一顆亮點，和普通的一眼分得開"""
    body = g.SECOND
    mk.loft(b, [mk.ring((0, 0, -0.30), 0.30, 0.30, 16), mk.ring((0, 0, -0.24), 0.38, 0.38, 16),
                mk.ring((0, 0, -0.06), 0.42, 0.42, 16), mk.ring((0, 0, 0.08), 0.38, 0.38, 16),
                mk.ring((0, 0, 0.12), 0.40, 0.40, 16), mk.ring((0, 0, 0.17), 0.39, 0.39, 16)],
            mat=body, cap_top=False)
    paint = g.MAIN
    # 罐口滿出來的顏料，扁圓一大坨再疊一小坨尖，看起來是濃稠的
    mk.blob(b, (0, 0, 0.18), (0.37, 0.37, 0.11), mat=paint, segments=16, rings_count=6)
    mk.blob(b, (0.02, -0.02, 0.27), (0.20, 0.19, 0.10), mat=paint, segments=12, rings_count=5)
    mk.sweep(b, [(0.03, -0.03, 0.34), (0.08, -0.05, 0.43)], [0.06, 0.005], 5, mat=paint, up=FWD)
    # 從罐口往下流的兩道滴痕，尾巴一顆圓珠
    for x, low in ((0.16, -0.14), (-0.14, 0.0)):
        mk.sweep(b, [(x, -0.33, 0.16), (x + 0.01, -0.40, 0.05), (x + 0.01, -0.41, low)],
                 [0.075, 0.06, 0.055], 6, mat=paint, up=UP)
        mk.blob(b, (x + 0.01, -0.41, low - 0.04), (0.07, 0.06, 0.075), mat=paint, segments=8, rings_count=4)
    if rich:
        # 濃的：罐身一圈深色的帶子，顏料上一顆會發光的亮點，右上角一顆星
        mk.loft(b, [mk.ring((0, 0, -0.16), 0.415, 0.415, 16), mk.ring((0, 0, -0.08), 0.42, 0.42, 16)],
                mat=g.ACCENT, cap_bottom=False, cap_top=False)
        g.orb(b, (-0.10, -0.12, 0.30), 0.08, g.GLOW)
        g.star(b, (-0.36, -0.30, 0.40), 0.17, 4, g.GLOW, 0.035)


def _ring_seed(b):
    """年輪色種：一顆飽滿的木頭種子，正面切開一片露出一圈一圈的年輪，和木樁王的樹樁同一個樣子；
    頂端冒兩片新芽，右下角一顆土色的亮點"""
    mk.blob(b, (0, 0.02, -0.04), (0.34, 0.30, 0.38), mat=g.MAIN, segments=16, rings_count=10)
    # 截面：幾片薄圓片一片比一片小、一片比一片前面，深淺交錯就是年輪
    for k, (r, mat) in enumerate(((0.27, g.SECOND), (0.215, g.MAIN), (0.17, g.SECOND), (0.115, g.MAIN),
                                  (0.07, g.SECOND), (0.03, g.MAIN))):
        mk.blob(b, (0.0, -0.27 - 0.012 * k, -0.06), (r, 0.03, r * 1.05), mat=mat, segments=18, rings_count=4)
    mk.sweep(b, [(0, 0, 0.30), (0.03, 0, 0.44)], [0.04, 0.028], 5, mat=g.ACCENT, up=FWD)
    g.leaf(b, (0.15, -0.02, 0.46), 0.22, g.ACCENT)
    g.leaf(b, (-0.11, -0.02, 0.42), 0.17, g.ACCENT, tilt=-0.4)
    g.star(b, (0.34, -0.30, -0.34), 0.14, 4, g.GLOW, 0.03)


def _twig(b, bend=0.0, knot=False):
    """斥候考試的嫩枝：從左下斜到右上的一根細枝，尾端一片新葉；bend 越大越彎，knot 在中間打一個結"""
    points = []
    for i in range(7):
        t = i / 6.0
        x = -0.42 + 0.84 * t
        z = -0.42 + 0.84 * t
        # 彎的往畫面右下凸，S 形用正弦
        offset = bend * math.sin(math.pi * t * (2.0 if bend > 0.25 else 1.0))
        points.append((x + offset * 0.7, 0, z - offset * 0.7))
    mk.sweep(b, points, [0.06, 0.055, 0.05, 0.045, 0.04, 0.035, 0.03], 6, mat=g.MAIN, up=FWD)
    if knot:
        g.ring(b, 0.17, 0.06, g.MAIN, 0.0, 1.0)
        mk.blob(b, (0.0, -0.03, 0.0), (0.13, 0.11, 0.13), mat=g.SECOND, segments=10, rings_count=5)
    tip = points[-1]
    g.leaf(b, (tip[0] - 0.02, -0.02, tip[2] + 0.02), 0.2, g.ACCENT)
    g.leaf(b, (points[3][0] - 0.1, -0.02, points[3][2] + 0.1), 0.13, g.ACCENT, tilt=-0.5)


def _solution(b, sparkle=False, smoke=False):
    """術士考試的溶液：圓肚瓶；四號多一顆亮點，失敗的冒一團黑煙"""
    g.bottle(b)
    if sparkle:
        g.star(b, (0.30, -0.25, 0.32), 0.15, 4, g.GLOW, 0.035)
    if smoke:
        for x, z, r in ((0.02, 0.52, 0.11), (0.12, 0.64, 0.09), (-0.04, 0.72, 0.07)):
            mk.blob(b, (x, 0, z), (r, r * 0.8, r), mat=g.DARK, segments=8, rings_count=4)


# 道具 id -> (零件函式, (主、次、點綴、光) 四個色階)
ITEMS = {
    "paint_green": (lambda b: _jar(b), ("paint_green", "bone", "leaf", "glow_moss")),
    "paint_blue": (lambda b: _jar(b), ("paint_blue", "bone", "dewgel", "glow_cyan")),
    "paint_green_rich": (lambda b: _jar(b, rich=True), ("paint_green", "brass", "rust", "glow_moss")),
    "paint_blue_rich": (lambda b: _jar(b, rich=True), ("paint_blue", "brass", "rust", "glow_cyan")),
    "seed_stump_king": (_ring_seed, ("rust", "brass", "leaf", "glow_ember")),
    "solution_1": (lambda b: _solution(b), ("solution_yellow", "bone", "brass", "glow_ember")),
    "solution_2": (lambda b: _solution(b), ("solution_red", "bone", "brass", "glow_ember")),
    "solution_3": (lambda b: _solution(b), ("paint_blue", "bone", "brass", "glow_cyan")),
    "solution_4": (lambda b: _solution(b, sparkle=True), ("dewcore", "bone", "brass", "glow_cyan")),
    "solution_failed": (lambda b: _solution(b, smoke=True), ("gloom", "bone", "brass", "glow_gloom")),
    "solution_mystery": (lambda b: _solution(b, sparkle=True), ("glow_gloom", "bone", "brass", "glow_gloom")),
    "twig_straight": (lambda b: _twig(b, 0.0), ("rust", "bark", "leaf", "glow_moss")),
    "twig_bent": (lambda b: _twig(b, 0.12), ("rust", "bark", "leaf", "glow_moss")),
    "twig_curly": (lambda b: _twig(b, 0.3), ("rust", "bark", "leaf", "glow_moss")),
    "twig_knotted": (lambda b: _twig(b, 0.05, knot=True), ("rust", "bark", "leaf", "glow_moss")),
}


ELEVATION = 22.0
# 物件佔畫面的比例，既有的道具圖示幾乎塞滿 40 格，留一點給描邊
FILL = 0.92


def _setup_camera(obj):
    """照物件在相機畫面上的外框取景，每個圖示都塞滿格子，不會有的大有的小"""
    shot.setup_scene(transparent=True)
    shot.add_lights()
    camera = shot.make_camera("icon_cam")
    e = math.radians(ELEVATION)
    up = Vector((0, math.sin(e), math.cos(e)))
    xs, ys = [], []
    for v in obj.data.vertices:
        w = obj.matrix_world @ v.co
        xs.append(w.x)
        ys.append(w.dot(up))
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    extent = max(max(xs) - min(xs), max(ys) - min(ys)) / FILL
    shot.aim(camera, Vector((cx, 0, 0)) + up * cy, extent, ELEVATION, 0.0)
    scene = bpy.context.scene
    scene.render.resolution_x = ICON_PX * SUPER
    scene.render.resolution_y = ICON_PX * SUPER
    return camera


def edge(image):
    """外圈補一格深褐色描邊：實心像素旁邊的透明像素塗成描邊色"""
    solid = image[..., 3] > 0.5
    padded = np.pad(solid, 1, constant_values=False)
    near = (padded[:-2, 1:-1] | padded[2:, 1:-1] | padded[1:-1, :-2] | padded[1:-1, 2:])
    ring = near & ~solid
    result = image.copy()
    keep = result[..., 3:4]
    add = (ring * EDGE_ALPHA)[..., None]
    total = keep + add * (1.0 - keep)
    result[..., :3] = np.where(total > 1e-6, (result[..., :3] * keep + EDGE * add * (1.0 - keep)) / np.maximum(total, 1e-6),
                               result[..., :3])
    result[..., 3:4] = total
    return result


def _render(objects, colors, ids, tag):
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
    return edge(pixels.outline(color, line))


def build_one(icon_id):
    blenv.clear_scene()
    builder_fn, ramps = ITEMS[icon_id]
    colors, masks, ids = mpalette.build_materials(_slots(*ramps), "ci_" + icon_id)
    b = mk.Builder()
    builder_fn(b)
    obj = b.to_object("Icon_" + icon_id, colors)
    mk.shade(obj, angle=math.radians(50))
    blenv.look_at([obj])
    _setup_camera(obj)
    return _render([obj], colors, ids, icon_id)


def render_all(ids=None, out_dir=ITEM_DIR):
    os.makedirs(out_dir, exist_ok=True)
    made = []
    for icon_id in (ids or list(ITEMS)):
        image = build_one(icon_id)
        path = os.path.join(out_dir, icon_id + ".png")
        pixels.save_png(image, path)
        if out_dir == ITEM_DIR:
            sheets.write_import(path)
        made.append(path)
    return made


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = ITEM_DIR
    if argv and argv[0].startswith("--out="):
        out = argv.pop(0)[len("--out="):]
    for made in render_all(argv or None, out):
        print("[colour_icons] " + made)
