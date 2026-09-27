"""
產生遊戲自己的滑鼠游標，輸出到 assets/ui/cursors/。
只靠 Pillow，不需要 Blender，作法和 art_pipeline/ui/skin.py 同一套：
同一份 PALETTES["dark"] 配色、同樣的超取樣、同樣自己寫 .import。

為什麼每一種狀態都是同一支箭頭配一個小徽章：
熱點固定在箭尖 (1, 1)，狀態換掉的時候指到的那一點不會跳，
地上的格子游標也就不會跟著跳一格。箭身順便染成那個狀態的顏色，餘光就分得出來。

徽章的意思
  pointer  沒有徽章，介面上用這一支
  walk     一個菱形格子，點下去會走到那一格
  attack   一把斜著的劍
  talk     對話框
  pickup   一個袋口張開的小袋子
  portal   傳送點的符文環
  blocked  進不去的圓圈斜槓
  target   放指定技挑目標時的選取框：四個角的方框加中心一點，熱點在正中間，照 RO 放指定技的準星
           2026-09-26 使用者：指定技能游標要變成選取框

用法：python3 art_pipeline/ui/cursors.py
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui import skin  # noqa: E402

PIPELINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(PIPELINE_DIR)
OUT_DIR = os.path.join(PROJECT_ROOT, "assets", "ui", "cursors")

# 圖是照 32 格的座標設計的，輸出放大 OUT 倍；遊戲裡照畫面大小用平滑取樣往下縮，
# 2026-09-26 使用者嫌游標小、放大之後又說失真：以前只輸出 32，遊戲裡用最近點放大 1.5 倍，線條粗細不一
SIZE = 32
OUT = 3
# 超取樣倍率，斜邊和圓角先放大畫再縮小；輸出放大了，超取樣跟著放大
SS = 4 * OUT
# 熱點固定在箭尖，所有狀態共用，換狀態時指到的位置不會位移；座標是輸出圖的像素
HOTSPOT = (1 * OUT, 1 * OUT)

# 箭頭的輪廓，順時針，座標就是 32 像素畫布上的像素
ARROW = [(1, 1), (1, 20), (6, 15.5), (9.5, 23), (13, 21.4), (9.6, 14.2), (15, 14.2)]
# 徽章畫在右下角這一塊；底盤和描邊還會往外各長一點，留到 31 才不會被畫布切掉
BADGE_BOX = (18, 18, 30, 30)

# 各狀態的箭身顏色和徽章顏色，取自 skin.py 的 dark 配色和遊戲裡既有的色票
# 箭身一律是亮色配深描邊，草地和石板上都讀得到
STATES = {
    "pointer": {"body": "metal_light", "badge": None, "ink": None},
    "walk": {"body": "metal_light", "badge": "cell", "ink": (244, 228, 186)},
    "attack": {"body": "metal_light", "badge": "sword", "ink": (240, 122, 96)},
    "talk": {"body": "metal_light", "badge": "bubble", "ink": (250, 214, 130)},
    "pickup": {"body": "metal_light", "badge": "pouch", "ink": (150, 226, 154)},
    "portal": {"body": "metal_light", "badge": "ring", "ink": (140, 236, 252)},
    "blocked": {"body": "metal_light", "badge": "deny", "ink": (236, 104, 88)},
    "target": {"body": None, "badge": None, "ink": (255, 136, 96), "reticle": True},
}
# 選取框的熱點在正中間，框住的就是點下去的那一點
RETICLE_CENTER = (16, 16)


def _pil():
    from PIL import Image, ImageDraw, ImageFilter
    return Image, ImageDraw, ImageFilter


def _blank(mode="RGBA", value=(0, 0, 0, 0)):
    Image, _, _ = _pil()
    return Image.new(mode, (SIZE * OUT, SIZE * OUT), value)


def _big():
    Image, ImageDraw, _ = _pil()
    mask = Image.new("L", (SIZE * SS, SIZE * SS), 0)
    return mask, ImageDraw.Draw(mask)


def _shrink(mask):
    Image, _, _ = _pil()
    return mask.resize((SIZE * OUT, SIZE * OUT), Image.LANCZOS)


def _scaled(points):
    return [(x * SS, y * SS) for x, y in points]


def _outline(mask, width=1):
    """比形狀往外胖一圈的遮罩，拿來當描邊；描邊放在形狀底下疊"""
    from PIL import ImageChops, ImageFilter
    grown = mask.filter(ImageFilter.MaxFilter(1 + width * OUT * 2))
    return ImageChops.subtract(grown, mask)


def _tint(mask, color, alpha=1.0):
    Image, _, _ = _pil()
    layer = Image.new("RGBA", mask.size, tuple(color) + (0,))
    layer.putalpha(mask.point(lambda v: int(v * alpha)))
    return layer


def _over(base, layer):
    from PIL import Image
    return Image.alpha_composite(base, layer)


def _shade(mask, color, alpha, keep):
    """在形狀內部壓一塊陰影，keep 是只留下遮罩的哪一半"""
    from PIL import ImageChops
    return _tint(ImageChops.multiply(mask, keep), color, alpha)


# ---- 箭頭 ----

def arrow_masks():
    """回傳箭頭的實心遮罩和它的暗面遮罩"""
    Image, _, _ = _pil()
    mask, draw = _big()
    draw.polygon(_scaled(ARROW), fill=255)
    body = _shrink(mask)
    # 暗面：箭身右下那一半，讓平面的箭頭有一點厚度
    shade, shade_draw = _big()
    shade_draw.polygon(_scaled([(5.6, 0), (15, 9.4), (15, 23), (9.5, 23), (6, 15.5), (5.6, 15.5)]), fill=255)
    return body, _shrink(shade)


def draw_arrow(out, ink):
    """把箭頭畫進 out：深色描邊、亮色箭身、右下暗面、左上一條受光"""
    body, shade = arrow_masks()
    palette = skin.PALETTES["dark"]
    out = _over(out, _tint(_outline(body, 1), palette["edge"], 1.0))
    out = _over(out, _tint(body, ink, 1.0))
    out = _over(out, _shade(body, palette["metal_dark"], 0.55, shade))
    # 左邊那條受光，箭頭在暗背景上也切得開
    _, draw_big = _big()
    lit, lit_draw = _big()
    lit_draw.line(_scaled([(1.6, 2.0), (1.6, 18.0)]), fill=255, width=SS)
    out = _over(out, _tint(_shrink(lit), palette["inner_light"], 0.7))
    return out


# ---- 徽章 ----

def badge_mask(kind):
    """徽章的形狀遮罩，畫在 BADGE_BOX 裡"""
    mask, draw = _big()
    left, top, right, bottom = BADGE_BOX
    width = right - left
    center = ((left + right) / 2.0, (top + bottom) / 2.0)

    def box(pad):
        return _scaled([(left + pad, top + pad)])[0] + _scaled([(right - pad, bottom - pad)])[0]

    if kind == "cell":
        # 俯視的一格，畫成菱形才像躺在地上
        half_x = width * 0.5
        half_y = width * 0.32
        points = [(center[0] - half_x, center[1]), (center[0], center[1] - half_y),
                  (center[0] + half_x, center[1]), (center[0], center[1] + half_y)]
        draw.polygon(_scaled(points), fill=255)
        hole = [(center[0] - half_x + 2.4, center[1]), (center[0], center[1] - half_y + 1.5),
                (center[0] + half_x - 2.4, center[1]), (center[0], center[1] + half_y - 1.5)]
        draw.polygon(_scaled(hole), fill=0)
    elif kind == "sword":
        # 一把斜著的劍：刀身、護手、握把、圓劍首，比交叉的兩把刀好認，也不會和禁止的斜槓撞在一起
        # 刀身從右上斜到左下，收成尖端
        draw.polygon(_scaled([(right - 0.6, top + 0.6), (right - 3.2, top + 1.2),
                              (left + 4.2, bottom - 4.4), (left + 5.4, bottom - 3.2)]), fill=255)
        # 護手和刀身垂直，握把順著刀身往左下延伸，末端一顆圓劍首
        draw.line(_scaled([(left + 1.8, bottom - 5.6), (left + 6.4, bottom - 1.0)]), fill=255,
                  width=int(1.6 * SS))
        draw.line(_scaled([(left + 4.2, bottom - 3.4), (left + 2.2, bottom - 1.4)]), fill=255,
                  width=int(1.8 * SS))
        draw.ellipse(_scaled([(left + 0.8, bottom - 2.4)])[0] + _scaled([(left + 2.8, bottom - 0.4)])[0],
                     fill=255)
    elif kind == "bubble":
        draw.rounded_rectangle(box(0.6), radius=int(3.2 * SS), fill=255)
        draw.polygon(_scaled([(left + 3.0, bottom - 2.4), (left + 1.0, bottom + 1.4),
                              (left + 7.0, bottom - 2.4)]), fill=255)
        for index in range(3):
            dot_x = left + 3.6 + index * 3.4
            dot_y = center[1] - 0.6
            draw.ellipse(_scaled([(dot_x - 0.9, dot_y - 0.9)])[0] + _scaled([(dot_x + 0.9, dot_y + 0.9)])[0],
                         fill=0)
    elif kind == "pouch":
        draw.rounded_rectangle(_scaled([(left + 1.6, top + 4.4)])[0] + _scaled([(right - 1.6, bottom - 1.0)])[0],
                               radius=int(2.4 * SS), fill=255)
        # 袋口的束帶
        draw.arc(_scaled([(left + 3.4, top + 0.6)])[0] + _scaled([(right - 3.4, top + 8.0)])[0],
                 start=180, end=360, fill=255, width=int(1.8 * SS))
        draw.line(_scaled([(left + 1.6, top + 6.0), (right - 1.6, top + 6.0)]), fill=0, width=int(1.2 * SS))
    elif kind == "ring":
        draw.ellipse(box(0.8), outline=255, width=int(2.0 * SS))
        draw.ellipse(_scaled([(center[0] - 1.6, center[1] - 1.6)])[0]
                     + _scaled([(center[0] + 1.6, center[1] + 1.6)])[0], fill=255)
    elif kind == "deny":
        draw.ellipse(box(0.8), outline=255, width=int(2.2 * SS))
        draw.line(_scaled([(left + 3.4, bottom - 3.4), (right - 3.4, top + 3.4)]), fill=255,
                  width=int(2.2 * SS))
    return _shrink(mask)


def draw_badge(out, kind, ink):
    palette = skin.PALETTES["dark"]
    mask = badge_mask(kind)
    # 徽章底下先鋪一塊深色，草地和雪地上也不會糊掉
    plate, plate_draw = _big()
    left, top, right, bottom = BADGE_BOX
    plate_draw.ellipse(_scaled([(left - 0.6, top - 0.6)])[0] + _scaled([(right + 0.6, bottom + 0.6)])[0],
                       fill=255)
    plate_mask = _shrink(plate)
    out = _over(out, _tint(_outline(plate_mask, 1), palette["edge"], 1.0))
    out = _over(out, _tint(plate_mask, palette["panel_bottom"], 0.94))
    out = _over(out, _tint(_outline(mask, 1), palette["edge"], 0.9))
    out = _over(out, _tint(mask, ink, 1.0))
    return out


# ---- 輸出 ----

IMPORT_TEMPLATE = """[remap]

importer="texture"
type="CompressedTexture2D"
uid="uid://%s"
path="res://.godot/imported/%s.png-%s.ctex"
metadata={
"vram_texture": false
}

[deps]

source_file="res://assets/ui/cursors/%s.png"
dest_files=["res://.godot/imported/%s.png-%s.ctex"]

[params]

compress/mode=0
compress/high_quality=false
compress/lossy_quality=0.7
compress/hdr_compression=1
compress/normal_map=0
compress/channel_pack=0
mipmaps/generate=false
mipmaps/limit=-1
roughness/mode=0
roughness/src_normal=""
process/fix_alpha_border=false
process/premult_alpha=false
process/normal_map_invert_y=false
process/hdr_as_srgb=false
process/hdr_clamp_exposure=false
process/size_limit=0
detect_3d/compress_to=0
"""


def _hash(name):
    import hashlib
    return hashlib.md5(("ui_cursors/" + name).encode()).hexdigest()


def _uid(name):
    letters = "abcdefghijklmnopqrstuvwxyz0123456789"
    value = int(_hash(name)[:12], 16)
    out = ""
    for _ in range(12):
        out += letters[value % len(letters)]
        value //= len(letters)
    return "c" + out


def save(image, name, out_dir=None):
    target = out_dir or OUT_DIR
    os.makedirs(target, exist_ok=True)
    path = os.path.join(target, name + ".png")
    image.save(path)
    digest = _hash(name)
    with open(path + ".import", "w", encoding="utf-8") as handle:
        handle.write(IMPORT_TEMPLATE % (_uid(name), name, digest, name, name, digest))
    return path


def draw_reticle(out, ink):
    """四個角各一個 L 形的框，中間一個小點；深色描邊、亮色本體、左上受光，和箭頭同一套"""
    palette = skin.PALETTES["dark"]
    mask, draw = _big()
    cx, cy = RETICLE_CENTER
    half = 11.5
    arm = 5.0
    width = 2.2 * SS
    for sx in (-1, 1):
        for sy in (-1, 1):
            corner = (cx + sx * half, cy + sy * half)
            draw.line(_scaled([(corner[0], corner[1] - sy * arm), corner, (corner[0] - sx * arm, corner[1])]),
                      fill=255, width=int(width), joint="curve")
    r = 1.6
    draw.ellipse([(cx - r) * SS, (cy - r) * SS, (cx + r) * SS, (cy + r) * SS], fill=255)
    body = _shrink(mask)
    out = _over(out, _tint(_outline(body, 1), palette["edge"], 1.0))
    out = _over(out, _tint(body, ink, 1.0))
    # 左上那一半受光，暗背景上也看得出立體
    lit, lit_draw = _big()
    lit_draw.polygon(_scaled([(0, 0), (32, 0), (0, 32)]), fill=255)
    out = _over(out, _shade(body, palette["inner_light"], 0.35, _shrink(lit)))
    return out


def build_cursor(state):
    out = _blank()
    if state.get("reticle"):
        return draw_reticle(out, state["ink"])
    if state["badge"]:
        out = draw_badge(out, state["badge"], state["ink"])
    out = draw_arrow(out, skin.PALETTES["dark"][state["body"]])
    return out


def build(out_dir=None):
    """產生全部游標；Blender 裡沒有 Pillow，改叫系統的 python3 跑同一個檔案"""
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("[ui/cursors] 這個直譯器沒有 Pillow，改用系統的 python3")
        subprocess.run([skin._system_python(), os.path.abspath(__file__)], check=True)
        return

    table = {}
    for name, state in STATES.items():
        image = build_cursor(state)
        assert image.size == (SIZE * OUT, SIZE * OUT), "%s 尺寸 %s 不對" % (name, image.size)
        save(image, name, out_dir)
        hotspot = [RETICLE_CENTER[0] * OUT, RETICLE_CENTER[1] * OUT] if state.get("reticle") else list(HOTSPOT)
        table[name] = {"size": [SIZE * OUT, SIZE * OUT], "design": SIZE, "hotspot": hotspot}
    with open(os.path.join(out_dir or OUT_DIR, "cursors.json"), "w", encoding="utf-8") as handle:
        json.dump(table, handle, ensure_ascii=False, indent=1, sort_keys=True)
    print("[ui/cursors] 完成 %d 支游標" % len(table))


if __name__ == "__main__":
    build()
