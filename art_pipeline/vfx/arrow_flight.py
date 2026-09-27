"""
飛行中的箭，七種箭矢各一列，輸出 assets/vfx/arrow_flight.png 和它的尺寸說明 arrow_flight.json，
src/effects/arrow_flight.gd 播；箭是側面看的一支，飛的時候貼片繞著箭桿轉向鏡頭，永遠看到側面，和 RO 一樣是一張圖轉方向

第 2 版，照 Nora 的審查改成「細、快、尖」，RO 的箭細長、箭頭尖、沒有花樣：
- 箭頭一律鋼色，長 36、寬 14 像素，長寬比 2.5 比 1 以上，後面兩個倒鉤尖角
- 尾羽高 14、長 56 像素，後緣斜切成直線不是圓瓣，每片一條 1 像素的羽軸線
- 箭桿含描邊 8 像素；屬性色只在尾羽，光暈、尾跡、光點由著色器和粒子畫
- 配色：尾羽照道具圖示 art_pipeline/ui/arrow_icons.py 的 ARROWS，背包裡的箭和飛出去的箭是同一支
- 風格照 docs/美術風格指南.md：兩段受光、上半亮下半暗、描邊是各部位的底色乘 (0.30, 0.22, 0.24)、
  陰影那一側的線粗 1.45 倍
- 全長 0.85 公尺，是角色身高 1.875 公尺的 0.45 倍

密度和取樣跟著角色圖集走：讀角色的 meta.json 的 filter，linear 是每公尺 192 像素、平滑縮小、開多級縮圖；
nearest 是每公尺 96 像素、不抗鋸齒、關多級縮圖，就是像素畫風那一版，之後切畫風時不用改這支程式。
上面寫的像素數都是 192 那一版；尺寸全部用公尺寫，兩種密度同一套形狀

用法：python art_pipeline/vfx/arrow_flight.py，只需要 Pillow；檢查不過不寫檔
"""
import json
import os
import re
import sys

from PIL import Image, ImageChops, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "assets", "vfx", "arrow_flight.png")
OUT_META = os.path.join(ROOT, "assets", "vfx", "arrow_flight.json")
OUT_IMPORT = OUT + ".import"
CHARACTER_META = os.path.join(ROOT, "assets", "generated", "sprites", "characters", "body", "male_novice", "meta.json")
sys.path.insert(0, os.path.join(ROOT, "art_pipeline", "ui"))
import arrow_icons  # noqa: E402

## 兩種畫風的密度和超取樣
MODES = {"linear": {"px_per_m": 192.0, "ss": 6}, "nearest": {"px_per_m": 96.0, "ss": 1}}
## 格子和箭的尺寸，公尺
CELL_W_M = 1.0
CELL_H_M = 0.1875
TIP_M = 184.0 / 192.0
LENGTH_M = 0.85
## 以下是 192 那一版的像素，換算成公尺用；描邊受光側 1.4 像素，陰影側乘 1.45
REF_PX = 192.0
LINE_PX = 1.4
LINE_SHADOW_RATIO = 1.45
SHAFT_HALF_PX = 2.3
HEAD_LENGTH_PX = 34.0
HEAD_HALF_PX = 5.5
BARB_BACK_PX = 11.0
FEATHER_LENGTH_PX = 56.0
FEATHER_HALF_PX = 5.5
## 描邊顏色是底色乘這個，照風格指南 1.8
INK = (0.30, 0.22, 0.24)

## 列的順序，src/effects/arrow_flight.gd 讀 arrow_flight.json 的 rows
ROWS = ["neutral", "fire", "water", "wind", "earth", "light", "dark"]
## 屬性對應背包裡的哪一支箭，data/items.json
ITEM_OF = {"neutral": "arrow", "fire": "fire_arrow", "water": "crystal_arrow", "wind": "wind_arrow",
           "earth": "stone_arrow", "light": "silver_arrow", "dark": "shadow_arrow"}

SHAFT_LIT = arrow_icons.SHAFT_LIT[:3]
## 木頭的暗部往紫偏一點，風格指南 1.4 的暗部不用中性色
SHAFT_SHADOW = (122, 78, 66)
## 箭頭：鋼，亮面、暗面、一小條硬高光
STEEL_LIT = (206, 212, 222)
STEEL_DARK = (104, 108, 124)
STEEL_SHINE = (248, 250, 255)
## 箭頭後面綁線的皮繩
WRAP_LIT = (132, 86, 62)
WRAP_SHADOW = (84, 52, 48)


class Canvas:
    """一格的畫布，座標用 192 那一版的像素寫，畫的時候換成這一版的密度再乘超取樣"""

    def __init__(self, mode):
        self.px_per_m = MODES[mode]["px_per_m"]
        self.ss = MODES[mode]["ss"]
        self.scale = self.px_per_m / REF_PX * self.ss
        self.w = int(round(CELL_W_M * self.px_per_m))
        self.h = int(round(CELL_H_M * self.px_per_m))
        self.mid = CELL_H_M * REF_PX / 2.0

    def mask(self):
        return Image.new("L", (self.w * self.ss, self.h * self.ss), 0)

    def poly(self, points):
        mask = self.mask()
        ImageDraw.Draw(mask).polygon([(x * self.scale, y * self.scale) for x, y in points], fill=255)
        return mask

    def ellipse(self, box):
        mask = self.mask()
        x0, y0, x1, y1 = box
        ImageDraw.Draw(mask).ellipse((x0 * self.scale, y0 * self.scale, x1 * self.scale, y1 * self.scale), fill=255)
        return mask

    def line(self, points, width_px):
        mask = self.mask()
        ImageDraw.Draw(mask).line([(x * self.scale, y * self.scale) for x, y in points],
                                  fill=255, width=max(1, int(round(width_px * self.scale))))
        return mask

    def upper(self, mask, split_y):
        cut = self.mask()
        ImageDraw.Draw(cut).rectangle((0, 0, self.w * self.ss, split_y * self.scale), fill=255)
        return ImageChops.multiply(mask, cut)

    def outline(self, mask):
        """往外撐出描邊：上緣 LINE_PX，下緣粗 1.45 倍"""
        up = LINE_PX * self.scale
        down = LINE_PX * LINE_SHADOW_RATIO * self.scale
        grown = mask.copy()
        step = max(1, self.ss // 2)
        reach = int(round(down))
        for dy in range(-reach, reach + 1, step):
            ry = down if dy > 0 else up
            if ry <= 0 or abs(dy) > ry + 0.01:
                continue
            half = int(round(up * max(0.0, 1 - (dy / ry) ** 2) ** 0.5))
            for dx in range(-half, half + 1, step):
                grown = ImageChops.lighter(grown, ImageChops.offset(mask, dx, dy))
        return grown


def _ink(colour):
    return tuple(int(round(c * k)) for c, k in zip(colour, INK))


def _mix(a, b, t):
    return tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b))


def _fill(image, mask, colour):
    layer = Image.new("RGBA", image.size, tuple(colour) + (255,))
    layer.putalpha(mask)
    image.alpha_composite(layer)


def _parts(c):
    """每個部位的形狀，座標是 192 那一版的像素"""
    mid = c.mid
    tip = TIP_M * REF_PX
    nock = tip - LENGTH_M * REF_PX
    socket = tip - HEAD_LENGTH_PX
    shaft = c.poly([(nock + 2.5, mid - SHAFT_HALF_PX), (socket + 1.0, mid - SHAFT_HALF_PX),
                    (socket + 1.0, mid + SHAFT_HALF_PX), (nock + 2.5, mid + SHAFT_HALF_PX)])
    nock_mask = c.ellipse((nock - 0.5, mid - 2.9, nock + 5.5, mid + 2.9))
    # 箭頭：細長的菱形，最寬處在尾端往前 11 像素，後面兩個倒鉤往後勾，中間收回箭桿
    wide = socket + BARB_BACK_PX
    head = c.poly([(tip, mid), (wide, mid - HEAD_HALF_PX), (socket - 3.0, mid - HEAD_HALF_PX + 0.3),
                   (socket + 5.0, mid - 2.0), (socket + 5.0, mid + 2.0),
                   (socket - 3.0, mid + HEAD_HALF_PX - 0.3), (wide, mid + HEAD_HALF_PX)])
    # 尾羽：後緣是一條斜線，上緣平直，前端順著弧線收回箭桿
    feathers = []
    rachis = []
    rear = nock + 5.0
    front = rear + FEATHER_LENGTH_PX
    for sign in (-1, 1):
        top = mid + sign * FEATHER_HALF_PX
        base = mid + sign * SHAFT_HALF_PX * 0.6
        points = [(rear, base), (rear + 7.0, top), (front - 20.0, top)]
        # 前端收成弧線，拆幾段
        for i in range(1, 7):
            t = i / 6.0
            points.append((front - 20.0 + 20.0 * t, top + (base - top) * (t ** 0.7)))
        feathers.append(c.poly(points))
        # 羽軸線：羽毛根部往上一點的一條細線，從後緣斜線到前端
        y = mid + sign * (SHAFT_HALF_PX + 1.2)
        rachis.append(c.line([(rear + 3.0, y), (front - 6.0, y)], 1.0))
    wrap = c.poly([(socket - 5.0, mid - 2.9), (socket + 1.5, mid - 2.9), (socket + 1.5, mid + 2.9),
                   (socket - 5.0, mid + 2.9)])
    shine = c.poly([(tip - 26.0, mid - 3.2), (tip - 6.0, mid - 0.9), (tip - 7.0, mid - 0.2), (tip - 26.0, mid - 2.0)])
    return {"shaft": shaft, "nock": nock_mask, "feathers": feathers, "rachis": rachis, "head": head, "wrap": wrap,
            "shine": shine}


def draw_row(c, element):
    _head_dark, _head_lit, feather_dark, feather_lit, _glow = arrow_icons.ARROWS[ITEM_OF[element]]
    feather_dark = tuple(feather_dark)
    feather_lit = tuple(feather_lit)
    p = _parts(c)
    mid = c.mid
    image = Image.new("RGBA", (c.w * c.ss, c.h * c.ss), (0, 0, 0, 0))
    wood_base = _mix(SHAFT_LIT, SHAFT_SHADOW, 0.5)
    feather_base = _mix(feather_lit, feather_dark, 0.5)
    steel_base = _mix(STEEL_LIT, STEEL_DARK, 0.5)
    # 描邊先整支一起鋪在最底下，部位之間靠明度分開；箭頭最後另外再描一圈
    for mask, base in [(p["shaft"], wood_base), (p["nock"], wood_base), (p["wrap"], WRAP_SHADOW)] + \
            [(f, feather_base) for f in p["feathers"]]:
        _fill(image, c.outline(mask), _ink(base))
    # 尾羽：上面那片受光，下面那片背光；羽軸線比自己暗一階
    upper, lower = p["feathers"]
    _fill(image, upper, feather_lit)
    _fill(image, lower, _mix(feather_dark, feather_lit, 0.25))
    _fill(image, ImageChops.multiply(p["rachis"][0], upper), _mix(feather_lit, feather_dark, 0.55))
    _fill(image, ImageChops.multiply(p["rachis"][1], lower), _mix(feather_dark, (0, 0, 0), 0.25))
    # 箭桿：上半亮、下半暗，硬邊
    for mask in (p["shaft"], p["nock"]):
        _fill(image, mask, SHAFT_SHADOW)
        _fill(image, c.upper(mask, mid + 0.2), SHAFT_LIT)
    _fill(image, p["wrap"], WRAP_SHADOW)
    _fill(image, c.upper(p["wrap"], mid - 0.4), WRAP_LIT)
    # 箭頭：鋼色，先描自己一圈，上半亮下半暗，亮面上一小條硬高光
    _fill(image, c.outline(p["head"]), _ink(steel_base))
    _fill(image, p["head"], STEEL_DARK)
    _fill(image, c.upper(p["head"], mid + 0.2), STEEL_LIT)
    _fill(image, ImageChops.multiply(p["shine"], p["head"]), STEEL_SHINE)
    if c.ss > 1:
        image = image.resize((c.w, c.h), Image.LANCZOS)
    return image, _ink(wood_base)


def measure(atlas, c, row_pitch):
    """每一列實心部分的尺寸，192 那一版的像素"""
    alpha = atlas.getchannel("A").point(lambda v: 255 if v > 128 else 0)
    k = REF_PX / c.px_per_m
    tip = TIP_M * REF_PX
    out = []
    for index in range(len(ROWS)):
        top = index * row_pitch
        cell = alpha.crop((0, top, c.w, top + c.h))
        box = cell.getbbox()
        if box is None:
            out.append(None)
            continue
        head = cell.crop((int((tip - HEAD_LENGTH_PX - 3) / k), 0, c.w, c.h)).getbbox()
        rear = cell.crop((0, 0, int((tip - LENGTH_M * REF_PX + FEATHER_LENGTH_PX + 8) / k), c.h)).getbbox()
        out.append({"box": box, "length": (box[2] - box[0]) * k,
                    "head_w": (head[3] - head[1]) * k if head else 0,
                    "feather_h": (rear[3] - rear[1]) * k if rear else 0})
    return out


def check(atlas, c, row_pitch):
    problems = []
    for index, m in enumerate(measure(atlas, c, row_pitch)):
        if m is None:
            problems.append("第 %d 列是空的" % index)
            continue
        box = m["box"]
        if box[0] == 0 or box[1] == 0 or box[2] == c.w or box[3] == c.h:
            problems.append("第 %d 列碰到格子邊 %s" % (index, box))
        if abs(m["length"] / REF_PX - LENGTH_M) > 0.05:
            problems.append("第 %d 列箭長 %.2f 公尺" % (index, m["length"] / REF_PX))
        if not 12.0 <= m["head_w"] <= 16.5:
            problems.append("第 %d 列箭頭寬 %.1f 像素，要 14 左右" % (index, m["head_w"]))
        if not 12.0 <= m["feather_h"] <= 16.5:
            problems.append("第 %d 列尾羽高 %.1f 像素，要 14 左右" % (index, m["feather_h"]))
        gap = atlas.getchannel("A").crop((0, index * row_pitch + c.h, c.w, (index + 1) * row_pitch)).getbbox()
        if gap is not None:
            problems.append("第 %d 列下面的空隙有東西" % index)
    return problems


def character_filter():
    try:
        with open(CHARACTER_META, encoding="utf-8") as f:
            value = json.load(f).get("filter", "linear")
    except OSError:
        value = "linear"
    return value if value in MODES else "linear"


def update_import(mode):
    """匯入設定跟著畫風：平滑版壓縮加多級縮圖，像素版無損、不縮圖"""
    if not os.path.exists(OUT_IMPORT):
        return
    with open(OUT_IMPORT, encoding="utf-8") as f:
        text = f.read()
    pixel = mode == "nearest"
    text = re.sub(r"compress/mode=\d", "compress/mode=%d" % (0 if pixel else 2), text)
    text = re.sub(r"mipmaps/generate=\w+", "mipmaps/generate=%s" % ("false" if pixel else "true"), text)
    with open(OUT_IMPORT, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in MODES else character_filter()
    c = Canvas(mode)
    row_pitch = c.h + 1
    # 高度進位到 4 的倍數，壓縮格式一塊是 4×4
    atlas_h = (row_pitch * len(ROWS) + 3) // 4 * 4
    atlas = Image.new("RGBA", (c.w, atlas_h), (0, 0, 0, 0))
    fringe = None
    for index, element in enumerate(ROWS):
        row, ink = draw_row(c, element)
        atlas.alpha_composite(row, (0, index * row_pitch))
        fringe = fringe or ink
    # 透明的地方填描邊色，縮圖和多級縮圖混到的邊才不會發白
    out = Image.new("RGBA", atlas.size, tuple(fringe) + (0,))
    out = Image.alpha_composite(out, atlas)
    problems = check(out, c, row_pitch)
    if problems:
        for line in problems:
            print("[vfx/arrow_flight] 不及格：" + line)
        sys.exit(1)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    out.save(OUT)
    meta = {"filter": mode, "pixels_per_meter": c.px_per_m, "cell": [c.w, c.h], "row_pitch": row_pitch,
            "atlas": [c.w, atlas_h], "tip_x": TIP_M * c.px_per_m, "length_m": LENGTH_M, "rows": ROWS}
    with open(OUT_META, "w", encoding="utf-8", newline="\n") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
        f.write("\n")
    update_import(mode)
    for index, m in enumerate(measure(out, c, row_pitch)):
        print("[vfx/arrow_flight] %s 長 %.0f 箭頭寬 %.1f 尾羽高 %.1f，都是 192 那一版的像素" % (
            ROWS[index], m["length"], m["head_w"], m["feather_h"]))
    print("[vfx/arrow_flight] 輸出 %s，%s，每公尺 %.0f 像素" % (OUT, mode, c.px_per_m))


if __name__ == "__main__":
    main()
