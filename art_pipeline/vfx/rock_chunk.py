"""
岩膚聚到身上的碎石，輸出 assets/vfx/rock_chunk.png，一塊不規則的多邊形石塊
2026-09-26 使用者：岩膚的特效很醜、不符合技能；原本套特效包的泡泡護盾，改成碎石往身上聚
光從左上來：左上的面亮、右下的面暗，深色描邊，和場景的石頭同一個受光方向
用法：python art_pipeline/vfx/rock_chunk.py
"""
import math
import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "assets", "vfx", "rock_chunk.png")
SIZE = 64
SS = 4
EDGE = (46, 38, 32, 255)
LIT = (176, 162, 140, 255)
MID = (128, 114, 96, 255)
DARK = (84, 72, 60, 255)


def main():
    n = SIZE * SS
    image = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    c = n / 2
    # 不規則的七角形外框
    radii = [0.42, 0.36, 0.44, 0.33, 0.40, 0.37, 0.43]
    outline = []
    for i, r in enumerate(radii):
        a = 2 * math.pi * i / len(radii) + 0.3
        outline.append((c + math.cos(a) * r * n, c + math.sin(a) * r * n))
    grown = [(c + (x - c) * 1.1, c + (y - c) * 1.1) for x, y in outline]
    draw.polygon(grown, fill=EDGE)
    draw.polygon(outline, fill=MID)
    # 左上受光面、右下背光面，中間一條稜線
    ridge = (c + 0.04 * n, c - 0.02 * n)
    draw.polygon([outline[3], outline[4], outline[5], outline[6], ridge], fill=LIT)
    draw.polygon([outline[0], outline[1], outline[2], ridge], fill=DARK)
    draw.line([outline[2], ridge, outline[6]], fill=EDGE, width=SS * 2)
    image.resize((SIZE, SIZE), Image.LANCZOS).save(OUT)
    print("[vfx/rock_chunk] 輸出", OUT)


if __name__ == "__main__":
    main()
