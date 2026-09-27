"""
崩岩落砸下去時地面的裂痕，輸出 assets/vfx/crack.png，平貼在地上，src/effects/ground_crack.gd 放
2026-09-27 使用者：崩岩落只要爆發特效，不要打完還一團黑黑的在那，好歹弄個地面裂縫特效
做法：中間一個淺坑，從坑往外長幾條會分岔的鋸齒裂縫，裂縫是深棕，左上那側的邊緣亮一點，
光從左上來，照美術風格指南的受光方向；外圈一層淡淡的塵土，全部在遊戲裡淡掉
用法：python art_pipeline/vfx/crack.py，只需要 numpy 和 Pillow
"""
import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "assets", "vfx", "crack.png")
SIZE = 512
SS = 2
CENTER = SIZE / 2
CRACK = (46, 32, 22, 255)
LIP = (214, 186, 140, 255)
rng = np.random.default_rng(20260927)


def branch(draw, lip, x, y, angle, length, width, depth):
    """一條鋸齒裂縫往外走，走一段就可能分岔；越往外越細"""
    steps = max(3, int(length / 14))
    for _ in range(steps):
        angle += rng.uniform(-0.45, 0.45)
        step = length / steps
        nx, ny = x + math.cos(angle) * step, y + math.sin(angle) * step
        w = max(1.0, width)
        draw.line([(x * SS, y * SS), (nx * SS, ny * SS)], fill=CRACK, width=int(w * SS))
        # 左上受光：裂縫往左上偏一點畫一條亮邊，看起來是往下凹的
        lip.line([((x - 2.5) * SS, (y - 2.5) * SS), ((nx - 2.5) * SS, (ny - 2.5) * SS)], fill=LIP,
                 width=max(1, int(w * 0.6 * SS)))
        if depth > 0 and rng.random() < 0.28:
            branch(draw, lip, nx, ny, angle + rng.choice([-1, 1]) * rng.uniform(0.5, 1.0),
                   length * 0.45, width * 0.6, depth - 1)
        x, y = nx, ny
        width *= 0.86


def main():
    n = SIZE * SS
    cracks = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    lips = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    draw = ImageDraw.Draw(cracks)
    lip = ImageDraw.Draw(lips)
    count = 9
    for i in range(count):
        angle = 2 * math.pi * i / count + rng.uniform(-0.25, 0.25)
        start = 30 + rng.uniform(0, 12)
        branch(draw, lip, CENTER + math.cos(angle) * start, CENTER + math.sin(angle) * start, angle,
               rng.uniform(150, 215), rng.uniform(13, 17), 2)
    # 中間的淺坑：深色的碗，左上緣亮
    r = 44
    pit = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    pd = ImageDraw.Draw(pit)
    pd.ellipse([(CENTER - r - 4) * SS, (CENTER - r - 4) * SS, (CENTER + r - 4) * SS, (CENTER + r - 4) * SS], fill=LIP)
    pd.ellipse([(CENTER - r) * SS, (CENTER - r) * SS, (CENTER + r) * SS, (CENTER + r) * SS], fill=(70, 50, 34, 255))
    pd.ellipse([(CENTER - r * 0.6) * SS, (CENTER - r * 0.5) * SS, (CENTER + r * 0.6) * SS, (CENTER + r * 0.7) * SS],
               fill=CRACK)
    # 外圈塵土：一圈很淡的土色，邊緣柔
    dust = Image.new("RGBA", (n, n), (150, 118, 80, 0))
    alpha = np.zeros((n, n))
    ys, xs = np.mgrid[0:n, 0:n]
    d = np.hypot(xs / SS - CENTER, ys / SS - CENTER) / (SIZE / 2)
    alpha = np.clip(1.0 - d, 0.0, 1.0) ** 1.5 * 110
    dust.putalpha(Image.fromarray(alpha.astype(np.uint8)))
    out = Image.alpha_composite(dust, lips)
    out = Image.alpha_composite(out, pit)
    out = Image.alpha_composite(out, cracks)
    out = out.resize((SIZE, SIZE), Image.LANCZOS)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    out.save(OUT)
    print("[vfx/crack] 輸出", OUT)


if __name__ == "__main__":
    main()
