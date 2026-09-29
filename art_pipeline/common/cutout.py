"""白底手繪圖的去背、裁邊和重畫描邊，紙偶身體、換裝圖層和怪物共用。"""

import os

import numpy as np
from PIL import Image, ImageFilter

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
SHIP_ROOT = os.path.join(PROJECT_ROOT, "assets", "generated", "sprites", "characters", "body")
CANDIDATE_ROOT = os.path.join(PROJECT_ROOT, "assets", "generated", "sprites", "placeholder", "characters", "body")
OUTLINE_COLOR = (54, 45, 40)
OUTLINE_PX = 2
WHITE = 238
# 去背邊緣反算用的墨線和紙的亮度，和 monsters/mpuppet.cut_on_white 同一組
INK_LUMA = 60.0
PAPER_LUMA = 250.0
CUT_RING_PX = 4


def cut(image):
    """從邊緣往內淹水去背，只有和邊緣連通的白才是背景，白衣服才留得住。"""
    patch = np.asarray(image.convert("RGB")).astype(int)
    light = patch.min(2) > WHITE
    background = np.zeros_like(light)
    background[0, :] = light[0, :]
    background[-1, :] = light[-1, :]
    background[:, 0] = light[:, 0]
    background[:, -1] = light[:, -1]
    while True:
        grown = background.copy()
        grown[1:, :] |= background[:-1, :]
        grown[:-1, :] |= background[1:, :]
        grown[:, 1:] |= background[:, :-1]
        grown[:, :-1] |= background[:, 1:]
        grown &= light
        if np.array_equal(grown, background):
            break
        background = grown
    alpha = np.where(background, 0.0, 1.0)
    ring = (np.asarray(Image.fromarray((background * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(CUT_RING_PX * 2 + 1))) > 0) & ~background
    # 邊緣是墨線混白紙，照混色反算透明度和墨色，只調淡會在描邊內側留一圈淡粉白
    luma = patch @ np.array([0.299, 0.587, 0.114])
    mix = np.clip((PAPER_LUMA - luma) / (PAPER_LUMA - INK_LUMA), 0.0, 1.0)
    alpha = np.where(ring, np.minimum(alpha, mix), alpha)
    safe = np.maximum(alpha, 1e-3)[..., None]
    unmixed = np.clip((patch - PAPER_LUMA * (1.0 - safe)) / safe, 0.0, 255.0)
    rgb = np.where((ring & (alpha < 1.0))[..., None], unmixed, patch)
    alpha = np.where(alpha < 0.08, 0.0, alpha)
    return Image.fromarray(np.dstack([rgb, alpha * 255.0]).round().astype(np.uint8), "RGBA")


def trim(figure):
    opaque = np.asarray(figure)[..., 3] > 8
    ys, xs = np.nonzero(opaque)
    return figure.crop((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))


def draw_outline(figure):
    """剝掉剪影最外一圈半透明的像素，再用描邊色蓋回去。"""
    pad = OUTLINE_PX
    canvas = Image.new("RGBA", (figure.width + pad * 2, figure.height + pad * 2), (0, 0, 0, 0))
    canvas.alpha_composite(figure, (pad, pad))
    out = np.asarray(canvas).copy()
    solid = out[..., 3] > 40
    core = np.asarray(Image.fromarray((solid * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(3))) > 0
    out[..., 3] = np.where(core, out[..., 3], 0)
    grown = np.asarray(Image.fromarray((core * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(pad * 2 + 1))) > 0
    ring = grown & ~core
    out[ring, 0], out[ring, 1], out[ring, 2] = OUTLINE_COLOR
    soft = np.asarray(Image.fromarray((grown * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.6)))
    out[..., 3] = np.maximum(out[..., 3], np.where(ring, soft, 0))
    return Image.fromarray(out, "RGBA")
