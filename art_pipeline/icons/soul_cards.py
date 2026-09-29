"""色魄的道具圖示：一張小卡片，卡面是那隻怪，40x40，透明背景

色魄在設計上就是 RO 的卡片，docs/奪色世界規劃書.md 第 5.1 節和第 12 節寫了卡面直接用怪物圖。
怪物圖取遊戲裡的怪物圖集朝正面那一格，那是使用者畫的圖切出來的，不另外畫。
卡框是黃銅、卡面的底色是那隻怪的代表色，四張擺在一起一眼分得出是哪一隻。
先在四倍大小畫好再縮到 40，外圈補一格深褐色描邊，和其他道具圖示一樣。

不需要 Blender，一般的 Python 加 Pillow、numpy 就能跑：
    python art_pipeline/icons/soul_cards.py [--out=資料夾] [id ...]
"""

import json
import os
import re
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(HERE))
ITEM_DIR = os.path.join(PROJECT, "assets", "ui", "icons", "items")
MONSTER_DIR = os.path.join(PROJECT, "assets", "generated", "sprites", "monsters")

ICON_PX = 40
SUPER = 4
N = ICON_PX * SUPER

# 卡片在 160 格畫布上的位置：左上、右下、圓角
CARD = (22, 6, 138, 154)
RADIUS = 14
BORDER = 8
# 卡面的圖框和下面那塊卡紙
WINDOW = (CARD[0] + BORDER + 2, CARD[1] + BORDER + 2, CARD[2] - BORDER - 2, 116)
PLATE = (CARD[0] + BORDER + 2, 122, CARD[2] - BORDER - 2, CARD[3] - BORDER - 2)

BRASS_LIGHT = (236, 200, 128)
BRASS_DARK = (150, 104, 48)
PAPER = (246, 234, 206)
PAPER_DARK = (222, 204, 166)
EDGE = (43, 28, 20)
EDGE_ALPHA = 0.85

# 色魄 id -> (怪物圖集, 卡面上半的底色, 卡面下半的底色)
SOULS = {
    "soul_horn_slime": ("horn_slime", (198, 226, 240), (126, 176, 208)),
    "soul_leaf_sprout": ("leaf_sprout", (214, 236, 188), (138, 186, 110)),
    "soul_crystal_bunny": ("crystal_bunny", (214, 226, 246), (140, 158, 210)),
    "soul_stump_king": ("stump_king", (246, 218, 170), (184, 124, 70)),
}


def _frame(sheet):
    """怪物圖集朝正面待機的第一格，裁掉透明的邊"""
    folder = os.path.join(MONSTER_DIR, sheet)
    text = open(os.path.join(folder, "meta.json"), encoding="utf-8").read()
    width, height = (int(v) for v in re.search(r'"frame_size":\s*\[\s*(\d+),\s*(\d+)', text).groups())
    image = Image.open(os.path.join(folder, "sheet.png")).convert("RGBA").crop((0, 0, width, height))
    return image.crop(image.getbbox())


def _gradient(size, top, bottom):
    w, h = size
    t = np.linspace(0.0, 1.0, h)[:, None, None]
    colors = np.array(top, dtype=np.float32) * (1 - t) + np.array(bottom, dtype=np.float32) * t
    return Image.fromarray(np.broadcast_to(colors, (h, w, 3)).astype(np.uint8), "RGB").convert("RGBA")


def _rounded(box, radius, fill):
    layer = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle(box, radius, fill=fill)
    return layer


def _paste_in(canvas, image, box, radius):
    """image 貼進 box，超出圓角的部分裁掉"""
    mask = Image.new("L", (N, N), 0)
    ImageDraw.Draw(mask).rounded_rectangle(box, radius, fill=255)
    layer = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    layer.alpha_composite(image, (box[0], box[1]))
    layer.putalpha(Image.fromarray(np.minimum(np.array(layer.getchannel("A")), np.array(mask))))
    canvas.alpha_composite(layer)


def card(soul_id):
    sheet, top, bottom = SOULS[soul_id]
    canvas = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    # 黃銅外框：上亮下暗的漸層，外緣一圈深色
    frame = _gradient((N, N), BRASS_LIGHT, BRASS_DARK)
    mask = _rounded(CARD, RADIUS, (255, 255, 255, 255)).getchannel("A")
    frame.putalpha(mask)
    canvas.alpha_composite(frame)
    inner = (CARD[0] + 3, CARD[1] + 3, CARD[2] - 3, CARD[3] - 3)
    ImageDraw.Draw(canvas).rounded_rectangle(inner, RADIUS - 3, outline=(255, 236, 190, 150), width=2)
    # 卡面：那隻怪的代表色，上淺下深，中間一圈淡淡的光
    w, h = WINDOW[2] - WINDOW[0], WINDOW[3] - WINDOW[1]
    face = _gradient((w, h), top, bottom)
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((w * 0.1, h * 0.05, w * 0.9, h * 0.85), fill=(255, 252, 236, 110))
    face.alpha_composite(glow.filter(ImageFilter.GaussianBlur(10)))
    # 怪物：塞滿圖框，腳底貼著圖框下緣，身體可以稍微蓋到框外一點點看起來比較有精神
    monster = _frame(sheet)
    scale = min((w - 6) / monster.width, (h - 4) / monster.height)
    monster = monster.resize((max(1, round(monster.width * scale)), max(1, round(monster.height * scale))), Image.LANCZOS)
    face.alpha_composite(monster, ((w - monster.width) // 2, h - monster.height - 2))
    _paste_in(canvas, face, WINDOW, 6)
    ImageDraw.Draw(canvas).rounded_rectangle(WINDOW, 6, outline=(96, 64, 30, 255), width=3)
    # 下面的卡紙：紙色漸層，中間一顆那隻怪代表色的小寶石
    pw, ph = PLATE[2] - PLATE[0], PLATE[3] - PLATE[1]
    _paste_in(canvas, _gradient((pw, ph), PAPER, PAPER_DARK), PLATE, 5)
    ImageDraw.Draw(canvas).rounded_rectangle(PLATE, 5, outline=(96, 64, 30, 255), width=3)
    cx, cy, r = (PLATE[0] + PLATE[2]) // 2, (PLATE[1] + PLATE[3]) // 2, 7
    draw = ImageDraw.Draw(canvas)
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=bottom + (255,), outline=(96, 64, 30, 255), width=2)
    draw.ellipse((cx - r + 3, cy - r + 3, cx - 1, cy - 1), fill=(255, 255, 255, 170))
    small = canvas.resize((ICON_PX, ICON_PX), Image.LANCZOS)
    return _edge(small)


def _edge(image):
    """外圈補一格深褐色描邊，和 colour_icons.py 的 edge 一樣"""
    rgba = np.asarray(image, dtype=np.float32) / 255.0
    solid = rgba[..., 3] > 0.5
    padded = np.pad(solid, 1, constant_values=False)
    near = padded[:-2, 1:-1] | padded[2:, 1:-1] | padded[1:-1, :-2] | padded[1:-1, 2:]
    ring = (near & ~solid)[..., None]
    keep = rgba[..., 3:4]
    add = ring * EDGE_ALPHA
    total = keep + add * (1.0 - keep)
    line = np.array(EDGE, dtype=np.float32) / 255.0
    color = np.where(total > 1e-6, (rgba[..., :3] * keep + line * add * (1.0 - keep)) / np.maximum(total, 1e-6),
                     rgba[..., :3])
    out = np.concatenate([color, total], axis=2)
    return Image.fromarray((np.clip(out, 0, 1) * 255).round().astype(np.uint8), "RGBA")


def render_all(ids=None, out_dir=ITEM_DIR):
    os.makedirs(out_dir, exist_ok=True)
    made = []
    for soul_id in (ids or list(SOULS)):
        path = os.path.join(out_dir, soul_id + ".png")
        card(soul_id).save(path)
        made.append(path)
    return made


if __name__ == "__main__":
    args = sys.argv[1:]
    out = ITEM_DIR
    if args and args[0].startswith("--out="):
        out = args.pop(0)[len("--out="):]
    for made in render_all(args or None, out):
        print("[soul_cards] " + made)
