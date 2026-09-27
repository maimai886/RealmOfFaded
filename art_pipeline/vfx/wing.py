"""
升級時背後展開的白色翅膀，輸出 assets/vfx/wing.png 一張右翼、assets/vfx/feather.png 一根飄落的羽毛、halo.png 頭上的光環，
左翼在遊戲裡左右翻
2026-09-26 使用者：升級特效可以是展開白色翅膀嗎。一根一根從同一點攤開的版本說沒有翅膀感，
膠囊圓瓣的版本說太醜，葉子形加描邊的版本說太像卡通、不夠莊嚴。
這一版照宗教畫裡天使的翅膀：前緣從肩膀往上高高拱起，翅尖超過頭頂，飛羽又長又細、尖端收尖往下垂，
上面疊三排越來越小的覆羽；每根羽毛有羽軸和斜斜的細羽枝，互相投很淡的暖色影子，
根部是實的白、尖端慢慢透明，外面不描邊，只有兩層金白色的光暈，看起來是光做的
用法：python art_pipeline/vfx/wing.py，會印出肩膀在圖上的像素位置，要和 src/effects/angel_wings.gd 的 SHOULDER_PX 一樣
"""
import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_DIR = os.path.join(ROOT, "assets", "vfx")
SIZE = 1024
SS = 3
# 設計用的畫布，畫完再縮進 SIZE，外面留一圈給光暈
DESIGN = 720
MARGIN = 60
SHOULDER = (70.0, 470.0)
BEND = (110.0, 110.0)
TIP = (380.0, 40.0)
WHITE = (255, 252, 246, 255)
ROOT_COLOUR = np.array([255.0, 254.0, 250.0])
TIP_COLOUR = np.array([240.0, 236.0, 226.0])
SHAFT_COLOUR = np.array([226.0, 218.0, 202.0])
BARB_COLOUR = np.array([232.0, 226.0, 212.0])
SHADOW_COLOUR = np.array([222.0, 212.0, 194.0])
# 光從左上來，影子往右下落
SHADOW_OFFSET = (2.0, 4.0)
# 尖端剩多少不透明度，越往尖越像光散掉
TIP_ALPHA = 0.78


def edge(s):
    x = (1 - s) ** 2 * SHOULDER[0] + 2 * (1 - s) * s * BEND[0] + s * s * TIP[0]
    y = (1 - s) ** 2 * SHOULDER[1] + 2 * (1 - s) * s * BEND[1] + s * s * TIP[1]
    return x, y


def angle_at(s):
    """羽毛的方向，影像座標 90 度是正下方：靠身體的朝下偏內，翅尖的斜斜朝外往下垂"""
    return 100.0 - 58.0 * s ** 1.2


def width_at(t):
    """羽毛沿長度的寬度：根部收窄、前四分之一最寬、之後慢慢收成尖"""
    if t < 0.25:
        return 0.6 + 0.4 * math.sin(math.pi * 0.5 * t / 0.25)
    u = (t - 0.25) / 0.75
    return max(0.0, 1.0 - u ** 2.4) ** 0.55


rng = np.random.default_rng(20260927)
# 光從左上照過來的方向，影像座標
LIGHT = np.array([-0.6, -0.8])


def feather_polygon(root, angle_deg, length, width, bend, notches=()):
    a = math.radians(angle_deg)
    dx, dy = math.cos(a), math.sin(a)
    nx, ny = -dy, dx
    left, right = [], []
    steps = 90
    for i in range(steps + 1):
        t = i / steps
        cx = root[0] + dx * length * t + nx * bend * length * t * t
        cy = root[1] + dy * length * t + ny * bend * length * t * t
        w = width * width_at(t)
        # 羽片邊緣的裂口：真的羽毛羽枝會分開，邊上有幾個小小的 V
        outer = w
        for tn, depth in notches:
            outer *= 1.0 - depth * max(0.0, 1.0 - abs(t - tn) / 0.025)
        # 外側的羽片寬、內側的窄，真的飛羽是不對稱的
        left.append(((cx + nx * outer) * SS, (cy + ny * outer) * SS))
        right.append(((cx - nx * w * 0.7) * SS, (cy - ny * w * 0.7) * SS))
    return left + right[::-1]


class Canvas:
    def __init__(self):
        n = DESIGN * SS
        self.n = n
        # 透明的地方也填白，縮圖時邊緣才不會混進黑色變成一圈灰邊
        self.rgb = np.ones((n, n, 3)) * ROOT_COLOUR
        self.alpha = np.zeros((n, n))

    def _window(self, polygon, pad):
        xs = [p[0] for p in polygon]
        ys = [p[1] for p in polygon]
        x0 = max(0, int(min(xs)) - pad)
        y0 = max(0, int(min(ys)) - pad)
        x1 = min(self.n, int(max(xs)) + pad)
        y1 = min(self.n, int(max(ys)) + pad)
        return x0, y0, x1, y1

    def feather(self, root, angle_deg, length, width, bend=0.1, shadow=0.35, detail=True, fade=True, notches=()):
        # 每根都有一點點不一樣，排起來才不像複製貼上
        length *= rng.uniform(0.95, 1.05)
        angle_deg += rng.uniform(-2.0, 2.0)
        width *= rng.uniform(0.93, 1.07)
        tone = rng.uniform(0.975, 1.01)
        polygon = feather_polygon(root, angle_deg, length, width, bend, notches)
        pad = int(14 * SS)
        x0, y0, x1, y1 = self._window(polygon, pad)
        local = [(px - x0, py - y0) for px, py in polygon]
        mask_image = Image.new("L", (x1 - x0, y1 - y0), 0)
        ImageDraw.Draw(mask_image).polygon(local, fill=255)
        mask_image = mask_image.filter(ImageFilter.GaussianBlur(0.5 * SS))
        m = np.asarray(mask_image, dtype=float) / 255.0
        rgb = self.rgb[y0:y1, x0:x1]
        alpha = self.alpha[y0:y1, x0:x1]
        # 蓋上去之前先在底下投一層很淡的暖影，光從左上來，影子往右下
        shifted = Image.new("L", mask_image.size, 0)
        shifted.paste(mask_image, (int(SHADOW_OFFSET[0] * SS), int(SHADOW_OFFSET[1] * SS)))
        soft = np.asarray(shifted.filter(ImageFilter.GaussianBlur(5 * SS)), dtype=float) / 255.0
        k = soft * shadow * np.clip(alpha, 0, 1) * (1.0 - m)
        rgb[:] = rgb * (1 - k[..., None]) + SHADOW_COLOUR * k[..., None]
        ys, xs = np.mgrid[y0:y1, x0:x1]
        a = math.radians(angle_deg)
        dx, dy = math.cos(a), math.sin(a)
        rx, ry = xs / SS - root[0], ys / SS - root[1]
        along = rx * dx + ry * dy
        t = np.clip(along / length, 0.0, 1.0)
        across = rx * -dy + ry * dx - bend * length * t * t
        across_n = np.clip(across / max(width, 1e-6), -1.0, 1.0)
        colour = ROOT_COLOUR + (TIP_COLOUR - ROOT_COLOUR) * (t ** 1.3)[..., None]
        # 羽片是微微拱起的：面向光的那半邊亮一點，兩邊往外緣慢慢暗
        facing = 1.0 if float(np.dot(np.array([-dy, dx]), LIGHT)) > 0 else -1.0
        shade = 1.0 + 0.045 * facing * across_n - 0.07 * across_n ** 2
        colour = colour * (shade * tone)[..., None]
        if detail:
            # 羽枝：從羽軸斜斜往尖端長出去的細線，很淡，近看才看得到
            barb = np.abs(np.sin((along - np.abs(across) * 1.5) * math.pi / 1.6)) ** 14
            k = barb * 0.28 * np.clip(np.abs(across_n) * 3.0, 0, 1) * m
            colour = colour * (1 - k[..., None]) + BARB_COLOUR * k[..., None]
            shaft = np.clip(1.0 - np.abs(across) / 0.8, 0, 1) * np.clip(1.0 - t / 0.92, 0, 1) * 0.75 * m
            colour = colour * (1 - shaft[..., None]) + SHAFT_COLOUR * shaft[..., None]
            # 羽軸旁邊一道亮光，像光滑的羽軸反光
            gleam = np.clip(1.0 - np.abs(across - 1.2 * facing) / 0.8, 0, 1) * np.clip(1.0 - t / 0.8, 0, 1) * 0.5 * m
            colour = colour * (1 - gleam[..., None]) + 255.0 * gleam[..., None]
        coverage = m * (1.0 - (1.0 - TIP_ALPHA) * t ** 2) if fade else m
        rgb[:] = rgb * (1 - coverage[..., None]) + colour * coverage[..., None]
        alpha[:] = alpha + coverage * (1.0 - alpha)

    def arm(self):
        """前緣：肩膀粗、往翅尖越來越細的一條圓滑厚邊，蓋住覆羽的根，上緣受光"""
        image = Image.new("L", (self.n, self.n), 0)
        draw = ImageDraw.Draw(image)
        for i in range(241):
            s = i / 240
            x, y = edge(s)
            r = (15 - 11 * s ** 1.4) * SS
            draw.ellipse([x * SS - r, y * SS - r, x * SS + r, y * SS + r], fill=255)
        image = image.filter(ImageFilter.GaussianBlur(0.8 * SS))
        m = np.asarray(image, dtype=float) / 255.0
        self.rgb = self.rgb * (1 - m[..., None]) + ROOT_COLOUR * m[..., None]
        self.alpha = np.maximum(self.alpha, m)

    def light(self):
        """整隻翅膀的明暗：靠身體和底部暗一點，前緣和上半部亮，像被頭頂的光照著"""
        n = self.n
        ys, xs = np.mgrid[0:n, 0:n]
        sx, sy = SHOULDER[0] * SS, SHOULDER[1] * SS
        near_body = np.exp(-np.hypot(xs - sx, ys - sy) / (170 * SS))
        height = np.clip((ys / SS - TIP[1]) / (SHOULDER[1] + 200 - TIP[1]), 0, 1)
        factor = 1.0 - 0.10 * near_body - 0.06 * height
        warm = np.clip(1.0 - height * 1.6, 0, 1) * 0.06
        self.rgb = self.rgb * factor[..., None]
        self.rgb[..., 0] += warm * 255 * 0.5
        self.rgb[..., 1] += warm * 255 * 0.35

    def image(self):
        rgba = np.dstack([self.rgb, self.alpha * 255.0]).clip(0, 255).astype(np.uint8)
        return Image.fromarray(rgba, "RGBA")


def row(canvas, count, s_from, s_to, drop, length_at, width_at_s, split=0.0, **kwargs):
    """一排羽毛從翅尖畫回肩膀，靠身體的蓋在上面；split 是羽片邊緣有裂口的機率"""
    for i in range(count - 1, -1, -1):
        s = s_from + (s_to - s_from) * i / (count - 1)
        x, y = edge(s)
        notches = []
        if rng.random() < split:
            for _ in range(rng.integers(1, 3)):
                notches.append((rng.uniform(0.4, 0.85), rng.uniform(0.25, 0.5)))
        canvas.feather((x, y + drop), angle_at(s), length_at(s), width_at_s(s), notches=notches, **kwargs)


def build_wing():
    canvas = Canvas()
    # 飛羽：又長又細，翅尖最長，最外面兩根短一點讓翅尖收成弧
    def flight_length(s):
        base = 170 + 210 * s ** 1.5
        return base * (0.86 if s > 0.97 else 0.95 if s > 0.9 else 1.0)
    row(canvas, 26, 0.05, 1.0, 34, flight_length, lambda s: 25 - 7 * s, bend=0.1, shadow=0.28, split=0.55)
    # 三級飛羽：靠身體那幾根長的蓋在次級飛羽上
    row(canvas, 6, 0.04, 0.2, 30, lambda s: 150 + 90 * s, lambda s: 25, bend=0.06, shadow=0.3, split=0.3)
    # 大覆羽
    row(canvas, 20, 0.05, 0.97, 22, lambda s: 105 + 55 * s, lambda s: 24 - 5 * s, bend=0.08, shadow=0.28, fade=False)
    # 中覆羽
    row(canvas, 18, 0.04, 0.93, 12, lambda s: 60 + 24 * s, lambda s: 21 - 4 * s, bend=0.06, shadow=0.28, fade=False)
    # 小覆羽：前緣底下一排細碎的小羽，不畫細節
    row(canvas, 24, 0.03, 0.88, 4, lambda s: 32 + 6 * s, lambda s: 14 - 3 * s, bend=0.0, shadow=0.2,
        detail=False, fade=False)
    canvas.arm()
    canvas.light()
    big = canvas.image()
    box = big.getbbox()
    crop = big.crop(box)
    inner = SIZE - MARGIN * 2
    k = inner / max(crop.size)
    small = crop.resize((max(1, round(crop.size[0] * k)), max(1, round(crop.size[1] * k))), Image.LANCZOS)
    out = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ox = MARGIN
    oy = MARGIN + (inner - small.size[1]) // 2
    out.alpha_composite(small, (ox, oy))
    shoulder = ((SHOULDER[0] * SS - box[0]) * k + ox, (SHOULDER[1] * SS - box[1]) * k + oy)
    print("[vfx/wing] 肩膀在 wing.png 的像素", round(shoulder[0]), round(shoulder[1]))
    # 兩層光暈：貼著羽毛的一層金白，外面一層很寬很淡的，像翅膀自己在發光
    alpha = out.getchannel("A")
    near = Image.new("RGBA", out.size, (255, 238, 196, 0))
    near.putalpha(alpha.filter(ImageFilter.GaussianBlur(16)).point(lambda v: int(v * 0.8)))
    wide = Image.new("RGBA", out.size, (255, 226, 160, 0))
    wide.putalpha(alpha.filter(ImageFilter.GaussianBlur(52)).point(lambda v: int(v * 0.55)))
    return Image.alpha_composite(Image.alpha_composite(wide, near), out)


def build_feather():
    """一根飄落的小羽毛：彎彎的，一邊寬一邊窄，暖白"""
    size = 96
    big = Image.new("L", (size * SS, size * SS), 0)
    draw = ImageDraw.Draw(big)
    points_a = []
    points_b = []
    steps = 24
    for i in range(steps + 1):
        t = i / steps
        # 羽軸是一條彎弧
        x = 14 + 68 * t
        y = 70 - 44 * t - 16 * math.sin(math.pi * t)
        w = math.sin(math.pi * min(1.0, t * 1.1)) ** 0.8
        ang = math.atan2(-44 - 16 * math.pi * math.cos(math.pi * t), 68)
        nx, ny = -math.sin(ang), math.cos(ang)
        points_a.append(((x + nx * 11 * w) * SS, (y + ny * 11 * w) * SS))
        points_b.append(((x - nx * 6 * w) * SS, (y - ny * 6 * w) * SS))
    draw.polygon(points_a + points_b[::-1], fill=255)
    alpha = big.resize((size, size), Image.LANCZOS)
    color = Image.new("RGBA", (size, size), WHITE)
    color.putalpha(alpha)
    glow = Image.new("RGBA", (size, size), (255, 240, 200, 0))
    glow.putalpha(alpha.filter(ImageFilter.GaussianBlur(4)).point(lambda v: int(v * 0.6)))
    return Image.alpha_composite(glow, color)


def build_halo():
    """頭上的光環：斜看的一圈金白色細環，外面一層柔光"""
    w, h = 128, 48
    big = Image.new("L", (w * SS, h * SS), 0)
    draw = ImageDraw.Draw(big)
    draw.ellipse([10 * SS, 12 * SS, (w - 10) * SS, (h - 12) * SS], outline=255, width=5 * SS)
    alpha = big.resize((w, h), Image.LANCZOS)
    color = Image.new("RGBA", (w, h), (255, 244, 204, 255))
    color.putalpha(alpha)
    glow = Image.new("RGBA", (w, h), (255, 226, 150, 0))
    glow.putalpha(alpha.filter(ImageFilter.GaussianBlur(4)))
    return Image.alpha_composite(glow, color)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    build_wing().save(os.path.join(OUT_DIR, "wing.png"))
    build_feather().save(os.path.join(OUT_DIR, "feather.png"))
    build_halo().save(os.path.join(OUT_DIR, "halo.png"))
    print("[vfx/wing] 輸出 wing.png feather.png halo.png")


if __name__ == "__main__":
    main()
