"""
全彩爆發甩到地上的顏料濺痕，輸出 assets/vfx/paint_splat.png，白色的，遊戲裡照八種屬性色上色
2026-09-27 使用者說全彩爆發的特效好廉價；這一招是把全身的顏色一口氣放出去、四周的線稿變回彩色，
所以爆開時八色顏料往外甩、濺在地上。形狀：中間一團不規則的圓，邊上幾個鼓起的瓣，外面甩出幾顆小滴，
中心稍微亮、邊緣一圈稍微深，看起來是濕的顏料不是平的色塊
用法：python art_pipeline/vfx/paint_splat.py
"""
import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "assets", "vfx", "paint_splat.png")
SIZE = 256
SS = 3
rng = np.random.default_rng(20260927)


def main():
    n = SIZE * SS
    mask = Image.new("L", (n, n), 0)
    draw = ImageDraw.Draw(mask)
    c = n / 2
    # 中間的主體：半徑隨角度起伏的一團
    points = []
    lobes = rng.uniform(0.0, 1.0, 9)
    for i in range(180):
        a = 2 * math.pi * i / 180
        r = 0.27
        for k, phase in enumerate(lobes):
            r += 0.035 * math.sin((k + 2) * a + phase * 6.28) / (1 + k * 0.4)
        points.append((c + math.cos(a) * r * n, c + math.sin(a) * r * n))
    draw.polygon(points, fill=255)
    # 往外甩的小滴，越遠越小
    for _ in range(14):
        a = rng.uniform(0, 2 * math.pi)
        d = rng.uniform(0.3, 0.46)
        r = (0.05 - (d - 0.3) * 0.2) * rng.uniform(0.5, 1.0)
        x, y = c + math.cos(a) * d * n, c + math.sin(a) * d * n
        draw.ellipse([x - r * n, y - r * n, x + r * n, y + r * n], fill=255)
        # 小滴和主體之間拖一條細尾巴
        mid = (c + math.cos(a) * (d - 0.07) * n, c + math.sin(a) * (d - 0.07) * n)
        draw.line([mid, (x, y)], fill=255, width=int(r * n * 0.9))
    mask = mask.filter(ImageFilter.GaussianBlur(1.2 * SS))
    alpha = np.asarray(mask, dtype=float) / 255.0
    # 邊緣一圈稍微深、中心稍微亮：用模糊過的遮罩當距離
    inner = np.asarray(mask.filter(ImageFilter.GaussianBlur(10 * SS)), dtype=float) / 255.0
    shade = 0.78 + 0.22 * np.clip(inner * 1.4, 0, 1)
    rgb = np.dstack([shade * 255] * 3)
    rgba = np.dstack([rgb, alpha * 255]).clip(0, 255).astype(np.uint8)
    Image.fromarray(rgba, "RGBA").resize((SIZE, SIZE), Image.LANCZOS).save(OUT)
    print("[vfx/paint_splat] 輸出", OUT)


if __name__ == "__main__":
    main()
