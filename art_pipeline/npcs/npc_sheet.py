# -*- coding: utf-8 -*-
"""NPC 的場景圖集：一張正面 Q 版站姿去背圖做成 idle 和 talk 兩個動作，五個方向都用同一張，NPC 是立牌。

用法：python art_pipeline/npcs/npc_sheet.py <npc_id> <去背好的 png> [--height-px 165]

為什麼只用一張正面：NPC 站著不走，轉身只在講話時轉向玩家，左右由引擎鏡射；
2026-09-24 使用者要 NPC 改 2D，舊的 npcs 圖集是 3D 算圖縮小的，太粗糙清掉了。
畫格、錨點、像素密度和玩家的 male_novice 一樣，站在一起才是同一個比例。
"""
import argparse
import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from common import sheet_output  # noqa: E402

PROJECT_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
SHIP_ROOT = os.path.join(PROJECT_ROOT, "assets", "generated", "sprites", "npcs")
FRAME = (176, 232)
ANCHOR = (88, 208)
PIXELS_PER_METER = 96
DIRECTIONS = ["s", "sw", "w", "nw", "n"]
COLUMNS = 8
# 預設身高和玩家素體在畫格裡量到的 169 像素差不多，NPC 可以用 --height-px 調高矮
DEFAULT_HEIGHT_PX = 165
MAX_WIDTH_PX = FRAME[0] - 6
# 待機是呼吸：身體縱向壓一點點、橫向撐一點點，腳底不動
IDLE = {"frames": 4, "fps": 4, "loop": True, "scale": [(1.0, 1.0), (1.006, 0.99), (1.01, 0.982), (1.006, 0.99)], "lift": [0, 0, 0, 0]}
# 講話是小小的點頭彈跳
TALK = {"frames": 4, "fps": 8, "loop": True, "scale": [(1.0, 1.0), (0.99, 1.012), (1.0, 1.0), (1.012, 0.985)], "lift": [0, 2, 0, 0]}
# 生成的 Q 版圖常自帶一圈貼紙白邊，玩家是深色描邊，留著白邊 NPC 在場景裡像貼上去的。
# 從外面一圈一圈剝掉「亮而且不太有顏色」的像素，剝到黑線稿就停，白邊再寬都剝得乾淨；
# 白邊外面有時還有一條淺藍的光暈線，所以亮度和彩度的門檻放得比較寬
# 原圖約一千像素高時白邊大約 30 像素寬；剝太多圈會吃進沒描邊的白袖子和光頭
EDGE_PASSES = 34
EDGE_WHITE = 160
EDGE_MAX_CHROMA = 100


def strip_white_edge(image):
    arr = np.asarray(image.convert("RGBA")).copy()
    alpha = arr[..., 3].astype(np.float32)
    rgb = arr[..., :3].astype(np.int32)
    whiteish = (rgb.min(axis=2) > EDGE_WHITE) & ((rgb.max(axis=2) - rgb.min(axis=2)) < EDGE_MAX_CHROMA)
    for _ in range(EDGE_PASSES):
        solid = alpha > 128
        outside = np.asarray(Image.fromarray(((~solid) * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3))) > 0
        kill = solid & outside & whiteish
        if not kill.any():
            break
        alpha[kill] = 0
    alpha[(alpha <= 128)] = 0
    arr[..., 3] = alpha.astype(np.uint8)
    out = Image.fromarray(arr, "RGBA")
    return out.crop(out.getchannel("A").point(lambda v: 255 if v > 20 else 0).getbbox())


def fit(figure, height_px):
    scale = height_px / float(figure.height)
    if figure.width * scale > MAX_WIDTH_PX:
        scale = MAX_WIDTH_PX / float(figure.width)
    size = (max(1, int(round(figure.width * scale))), max(1, int(round(figure.height * scale))))
    return figure.resize(size, Image.LANCZOS)


def frame(figure, sx, sy, lift):
    """腳底中點貼在錨點，縮放以腳底為中心"""
    w = max(1, int(round(figure.width * sx)))
    h = max(1, int(round(figure.height * sy)))
    body = figure.resize((w, h), Image.LANCZOS)
    canvas = Image.new("RGBA", FRAME, (0, 0, 0, 0))
    left = int(round(ANCHOR[0] - w / 2.0))
    top = int(round(ANCHOR[1] - h - lift))
    canvas.alpha_composite(body, (left, top))
    return canvas


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("npc_id")
    parser.add_argument("image")
    parser.add_argument("--height-px", type=float, default=DEFAULT_HEIGHT_PX)
    args = parser.parse_args()
    figure = fit(strip_white_edge(Image.open(args.image)), args.height_px)
    cells, actions = [], {}
    for name, spec in (("idle", IDLE), ("talk", TALK)):
        actions[name] = {"start": len(cells), "frames": spec["frames"], "fps": spec["fps"], "loop": spec["loop"]}
        for _direction in DIRECTIONS:
            for index in range(spec["frames"]):
                sx, sy = spec["scale"][index]
                cells.append(frame(figure, sx, sy, spec["lift"][index]))
    rows = -(-len(cells) // COLUMNS)
    sheet = Image.new("RGBA", (COLUMNS * FRAME[0], rows * FRAME[1]), (0, 0, 0, 0))
    for index, cell in enumerate(cells):
        sheet.alpha_composite(cell, (index % COLUMNS * FRAME[0], index // COLUMNS * FRAME[1]))
    out_dir = os.path.join(SHIP_ROOT, args.npc_id)
    os.makedirs(out_dir, exist_ok=True)
    sheet_path = os.path.join(out_dir, "sheet.png")
    sheet.save(sheet_path)
    sheet_output.write_import(sheet_path, PROJECT_ROOT, pixel=False)
    mask_path = os.path.join(out_dir, "mask.png")
    Image.new("RGB", (max(1, sheet.width // 8), max(1, sheet.height // 8)), (0, 0, 0)).save(mask_path)
    sheet_output.write_import(mask_path, PROJECT_ROOT, pixel=False)
    meta = {"frame_size": list(FRAME), "columns": COLUMNS, "pixels_per_meter": PIXELS_PER_METER, "anchor": list(ANCHOR),
            "directions": DIRECTIONS, "filter": "linear", "layout": "packed", "head_layer": False, "head_width": 0,
            "actions": actions,
            "source": {"pipeline": "art_pipeline/npcs/npc_sheet.py", "image": os.path.relpath(os.path.abspath(args.image), PROJECT_ROOT).replace("\\", "/"),
                       "height_px": args.height_px}}
    with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as handle:
        json.dump(meta, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print("%d 格、%s -> %s" % (len(cells), sheet.size, out_dir))


if __name__ == "__main__":
    main()
