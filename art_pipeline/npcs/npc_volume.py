"""
NPC 的場景立牌：拿 art_source/npcs/<id>.png 的舊圖當參考保留長相，重畫成斜側身、有受光和陰影面、深色描邊、
沒有白邊的樣子，照 RO 那種城鎮小人。使用者 2026-09-26 看過布隆說可以。
輸出 art_source/npcs/volume/_raw/<id>_<種子>.png，挑一張去背存成 art_source/npcs/volume/<id>.png，
再用 art_pipeline/npcs/npc_sheet.py 做成圖集。地上畫了影子的不要挑，遊戲裡有自己的影子

用法：python art_pipeline/npcs/npc_volume.py <npc_id> [種子 ...]
      python art_pipeline/npcs/npc_volume.py --cut <原圖> <npc_id>
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from comfy import flux  # noqa: E402

SRC = os.path.join(flux.PROJECT_ROOT, "art_source", "npcs")
OUT = os.path.join(SRC, "volume")
PROMPT = ("Redraw the exact same character from the reference image, same face, same outfit, same colours, same chibi "
          "proportions, as a classic 2D RPG town sprite like Ragnarok Online: full body standing, body turned to a "
          "three-quarter view facing toward the lower left, seen from slightly above. Strong two-tone cel shading that "
          "shows volume: light from the upper left, clear darker shadow on the right side of the body, under the arms, "
          "under the chin and on the lower legs. Dark brown line art, no white border, no sticker outline, plain white "
          "background, no ground, no text.")


def cut(src, dst):
    """白底去背：從四邊灌水把接近白的背景變透明，邊緣收一圈"""
    img = Image.open(src).convert("RGB")
    marked = img.copy()
    w, h = img.size
    for pt in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (w // 2, 0), (0, h // 2), (w - 1, h // 2)]:
        ImageDraw.floodfill(marked, pt, (255, 0, 255), thresh=28)
    arr = np.asarray(marked)
    background = (arr[..., 0] == 255) & (arr[..., 1] == 0) & (arr[..., 2] == 255)
    alpha = np.asarray(Image.fromarray((~background).astype(np.uint8) * 255).filter(ImageFilter.MinFilter(3)))
    out = Image.fromarray(np.dstack([np.asarray(img), alpha]), "RGBA")
    out.crop(out.getchannel("A").getbbox()).save(dst)


def main():
    if sys.argv[1] == "--cut":
        cut(sys.argv[2], os.path.join(OUT, sys.argv[3] + ".png"))
        return
    npc = sys.argv[1]
    seeds = [int(s) for s in sys.argv[2:]] or [1, 2, 3]
    raw = os.path.join(OUT, "_raw")
    os.makedirs(raw, exist_ok=True)
    ref = flux.upload(os.path.join(SRC, npc + ".png"))
    for seed in seeds:
        flux.run(flux.graph(PROMPT, ref, seed, size=1024)).save(os.path.join(raw, "%s_%d.png" % (npc, seed)))
        print(npc, seed, "ok", flush=True)


if __name__ == "__main__":
    main()
