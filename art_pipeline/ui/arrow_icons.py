"""
箭矢的道具圖示，輸出到 assets/ui/icons/items/<箭矢代號>.png，40×40
2026-09-27 加箭矢系統時做的：其他道具圖示是從 art_source/ui/icons_*_raw.png 的手繪大圖切出來的，
箭矢不在那幾張裡，所以照同一套風格用程式畫：左下往右上斜放、深棕描邊、左上受光、底下一層落影
箭桿是木頭，箭頭和尾羽照屬性上色，一眼分得出是哪一種箭
用法：python art_pipeline/ui/arrow_icons.py
"""
import math
import os

from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_DIR = os.path.join(ROOT, "assets", "ui", "icons", "items")
SIZE = 40
SS = 8
OUTLINE = (52, 32, 22, 255)
SHAFT = (176, 120, 70, 255)
SHAFT_LIT = (222, 172, 112, 255)
SHAFT_DARK = (120, 76, 42, 255)

# 每一種箭：箭頭的暗色、亮色，尾羽的暗色、亮色，有沒有光暈
ARROWS = {
    "arrow": ((96, 100, 108), (196, 202, 210), (196, 190, 178), (246, 242, 232), None),
    "fire_arrow": ((178, 52, 30), (255, 170, 70), (200, 60, 40), (255, 150, 90), (255, 120, 40)),
    "crystal_arrow": ((40, 120, 170), (170, 236, 255), (70, 150, 200), (190, 236, 255), (120, 210, 255)),
    "wind_arrow": ((52, 132, 70), (170, 240, 150), (70, 160, 90), (190, 246, 170), None),
    "stone_arrow": ((96, 82, 66), (176, 158, 132), (140, 112, 80), (206, 176, 136), None),
    "silver_arrow": ((150, 156, 170), (255, 255, 246), (206, 200, 170), (255, 248, 214), (255, 240, 170)),
    "shadow_arrow": ((46, 30, 64), (140, 100, 190), (60, 40, 84), (150, 120, 200), (110, 60, 170)),
}


def _pt(x, y):
    return (x * SS, y * SS)


## 箭本身是在 40 格裡畫的，轉斜之後再放大這麼多倍，從格子左下角斜到右上角，和弓差不多大
SCALE = 1.28


def _rotate(points, angle, cx, cy):
    c, s = math.cos(angle), math.sin(angle)
    return [(cx + ((x - cx) * c - (y - cy) * s) * SCALE, cy + ((x - cx) * s + (y - cy) * c) * SCALE)
            for x, y in points]


def draw_arrow(head_dark, head_lit, feather_dark, feather_lit, glow):
    """先在水平方向畫一支箭，再轉 45 度成左下往右上"""
    n = SIZE * SS
    layer = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    cx = cy = SIZE / 2
    angle = -math.pi / 4

    def poly(points, fill, outline=True):
        rotated = _rotate(points, angle, cx, cy)
        scaled = [_pt(x, y) for x, y in rotated]
        if outline:
            draw.polygon(scaled, fill=OUTLINE)
            # 描邊：往外撐一點再畫本體
            grown = _rotate([(x, y) for x, y in points], angle, cx, cy)
        draw.polygon(scaled, fill=fill)

    def thick(points, width, fill):
        rotated = _rotate(points, angle, cx, cy)
        draw.line([_pt(x, y) for x, y in rotated], fill=fill, width=int(width * SS), joint="curve")

    # 箭桿：先畫粗的描邊再畫木頭，上緣一條亮線
    thick([(6, 20), (31, 20)], 3.2, OUTLINE)
    thick([(6, 20), (31, 20)], 1.8, SHAFT)
    thick([(8, 19.55), (30, 19.55)], 0.6, SHAFT_LIT)
    thick([(8, 20.5), (30, 20.5)], 0.5, SHAFT_DARK)
    # 尾羽：上下各一片
    for sign in (-1, 1):
        outer = [(4, 20), (6.5, 20 + sign * 4.4), (13, 20 + sign * 4.4), (11.5, 20)]
        inner = [(5.2, 20 + sign * 0.6), (7.0, 20 + sign * 3.5), (12.0, 20 + sign * 3.5), (10.8, 20 + sign * 0.6)]
        rotated = [_pt(x, y) for x, y in _rotate(outer, angle, cx, cy)]
        draw.polygon(rotated, fill=OUTLINE)
        rotated_inner = [_pt(x, y) for x, y in _rotate(inner, angle, cx, cy)]
        draw.polygon(rotated_inner, fill=tuple(feather_lit) + (255,) if sign < 0 else tuple(feather_dark) + (255,))
    # 箭頭：菱形，左上半亮、右下半暗
    head = [(29, 20), (32, 16.6), (37.5, 20), (32, 23.4)]
    draw.polygon([_pt(x, y) for x, y in _rotate([(28, 20), (32, 15.6), (38.8, 20), (32, 24.4)], angle, cx, cy)],
                 fill=OUTLINE)
    draw.polygon([_pt(x, y) for x, y in _rotate(head, angle, cx, cy)], fill=tuple(head_dark) + (255,))
    draw.polygon([_pt(x, y) for x, y in _rotate([(29, 20), (32, 16.6), (37.5, 20)], angle, cx, cy)],
                 fill=tuple(head_lit) + (255,))
    small = layer.resize((SIZE, SIZE), Image.LANCZOS)
    out = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    if glow:
        halo = Image.new("RGBA", (SIZE, SIZE), tuple(glow) + (0,))
        halo.putalpha(small.getchannel("A").filter(ImageFilter.GaussianBlur(2.2)).point(lambda v: int(v * 0.8)))
        out = Image.alpha_composite(out, halo)
    # 落影：和其他圖示一樣往右下偏一點的淡黑
    shadow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    shadow_alpha = small.getchannel("A").filter(ImageFilter.GaussianBlur(1.0)).point(lambda v: int(v * 0.35))
    shadow.putalpha(shadow_alpha)
    moved = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    moved.paste(shadow, (1, 1))
    out = Image.alpha_composite(out, moved)
    return Image.alpha_composite(out, small)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for name, spec in ARROWS.items():
        draw_arrow(*spec).save(os.path.join(OUT_DIR, name + ".png"))
    print("[ui/arrow_icons] 輸出 %d 張" % len(ARROWS))


if __name__ == "__main__":
    main()
