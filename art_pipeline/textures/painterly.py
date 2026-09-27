"""
城鎮和室內的手繪可平鋪貼圖：Flux 2 Klein 拿 Provencal 參考圖畫，平移半張補接縫。
輸出在 art_source/textures/painterly/<名字>_<種子>.png，挑好的那張縮到尺寸放進 assets/generated/textures。
會把陽光斜射畫進去的要重畫，光影畫死在貼圖上一鋪開就一條一條的。

用法：python art_pipeline/textures/painterly.py <名字> [種子 ...]
"""
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from comfy import flux  # noqa: E402

OUT = os.path.join(flux.PROJECT_ROOT, "art_source", "textures", "painterly")

STYLE = ("Seamless tileable flat texture, viewed straight on, filling the whole frame edge to edge, "
         "hand-painted background art in the style of the reference painting: soft gouache brush strokes, "
         "warm sunlight colours, painterly, no perspective, no objects, no border, no text. ")
PROMPTS = {
    "plaster": "Stylized whitewashed lime plaster wall, smooth warm off-white with very soft uneven hand-painted "
               "brush texture, faint pale grey patches, one or two tiny spots where a grey stone shows through, "
               "no block pattern, even lighting.",
    "roof_tiles": "Stylized terracotta barrel roof tiles in neat overlapping rows, muted burnt orange with soft darker "
                  "gaps, a little moss, painterly, even lighting.",
    "wood": "Stylized weathered wooden planks, dark greyish brown, vertical boards with soft painted grain and "
            "slightly lighter worn edges, even lighting.",
    "stone_wall": "Stylized light grey limestone blocks, large rectangular stones with rounded soft edges and "
                  "pale mortar, painterly, cool grey with slight warm tint, even lighting.",
    "cobblestone": "Top-down view of a stylized village square paved with large flat pale grey-beige stones, rounded "
                   "soft edges, sandy gaps, painterly, even lighting.",
    "blue_wood": "Stylized old wooden planks painted in faded cornflower blue, vertical boards, paint slightly worn "
                 "at the edges showing grey wood, soft painterly strokes, even lighting.",
    "sand": "Top-down view of pale warm beach sand, soft ripples, a few tiny shells and pebbles, painterly, even lighting.",
    "wet_mud": "Top-down view of dark wet marsh mud with small puddle highlights, a few reeds stubs and wet grass blades, painterly, even lighting.",
    "keep_flagstone": "Top-down view of a fortress courtyard paved with large rough grey limestone slabs, irregular shapes, dark gaps, worn edges, painterly, even lighting.",
    "forest_floor": "Top-down view of a forest floor with moss patches, fallen leaves, small twigs and dark soil, painterly, even lighting.",
    "raked_gravel": "Top-down view of a Japanese zen garden of light grey-white raked gravel with parallel wavy rake lines, painterly, even lighting.",
    "moss_ground": "Top-down view of a soft Japanese moss garden, lush green cushion moss with a few tiny ferns and pebbles, painterly, even lighting.",
    "autumn_leaves": "Top-down view of ground covered in fallen red and orange Japanese maple leaves over dark soil, painterly, even lighting.",
    "wood_floor": "Top-down view of warm honey brown wooden floor planks, long boards in neat rows, soft worn texture, painterly, even lighting.",
    "stone_floor": "Top-down view of an indoor floor of square pale grey stone tiles with thin mortar lines, slightly worn, painterly, even lighting. Completely flat uniform lighting, no cast shadows, no sun rays, no light streaks.",
    "tatami": "Top-down view of Japanese tatami mats with dark cloth borders, woven straw texture, pale green-gold, painterly, even lighting.",
    "rug": "Top-down view of a woven wool rug with a simple deep red and cream geometric border pattern, painterly, even lighting.",
    "wood_panel": "Interior wall of dark wooden vertical panels with a horizontal rail, warm brown, painterly, even lighting. Completely flat uniform lighting, no cast shadows, no sun rays, no light streaks.",
    "shoji": "Japanese shoji sliding door wall, white translucent paper in a thin dark wooden grid lattice, painterly, even lighting.",
    "slate_roof": "Stylized dark grey-blue slate roof shingles in overlapping rows, soft painterly strokes, even lighting.",
    "kawara_roof": "Stylized grey-blue Japanese kawara clay roof tiles in neat vertical rows with rounded caps, painterly, even lighting.",
    "thatch": "Stylized straw thatched roof, golden bundles of straw in layered rows, painterly, even lighting.",
    "mossy_shingle": "Stylized old wooden roof shingles covered in patches of green moss, painterly, even lighting.",
    "water": "Top-down view of calm clear shallow water, soft blue-teal with gentle light caustic ripples and highlights, painterly, even lighting.",
    "dirt": "Top-down view of a stylized sandy dirt path, pale warm sand colour, soft painterly strokes, "
            "a few tiny pebbles, even lighting.",
}


def seamless(img):
    """平移半張讓接縫跑到中間，再用羽化的十字把中間那條縫蓋回原圖；四邊自然接得起來"""
    a = np.asarray(img).astype(np.float32)
    h, w, _ = a.shape
    shifted = np.roll(np.roll(a, h // 2, axis=0), w // 2, axis=1)
    y = np.abs(np.arange(h) - h / 2) / (h / 2)
    x = np.abs(np.arange(w) - w / 2) / (w / 2)
    # 靠邊權重給平移版，中間給原圖
    edge = np.maximum(y[:, None], x[None, :])
    weight = np.clip((edge - 0.55) / 0.35, 0.0, 1.0)[..., None]
    out = a * (1 - weight) + shifted * weight
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    kind = sys.argv[1]
    seeds = [int(s) for s in sys.argv[2:]] or [1]
    ref = flux.upload(flux.STYLE_REF)
    for seed in seeds:
        img = flux.run(flux.graph(STYLE + PROMPTS[kind], ref, seed))
        img.save(os.path.join(OUT, "%s_raw_%d.png" % (kind, seed)))
        tile = seamless(img)
        tile.save(os.path.join(OUT, "%s_%d.png" % (kind, seed)))
        # 2x2 平鋪預覽，看得出接縫和重複感
        prev = Image.new("RGB", (tile.width * 2, tile.height * 2))
        for i in range(2):
            for j in range(2):
                prev.paste(tile, (i * tile.width, j * tile.height))
        prev.resize((1024, 1024), Image.LANCZOS).save(os.path.join(OUT, "%s_%d_tiled.png" % (kind, seed)))
        print(kind, seed, "ok")
