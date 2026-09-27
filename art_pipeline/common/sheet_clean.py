# -*- coding: utf-8 -*-
"""量圖集每一格剪影外面的髒東西。用法：python art_pipeline/common/sheet_clean.py <sheet.png> [--json] [--mark 輸出.png]

三種都算髒：
  離島：和最大那塊不相連的不透明像素，腳邊的黑點、肩上的灰點
  霧：半透明又淡的像素，白底去背沒去乾淨的殘渣；或離實心像素超過一格的半透明像素
  亮邊：剪影最外一圈不是墨線的顏色，描邊外面還掛著一片沒描邊的膚色或白
"""

import argparse
import json
import os

import numpy as np
from PIL import Image, ImageFilter

SOLID = 128
# 描邊 (54, 45, 40) 和背景混色後最亮到這裡；超過就是沒被描到的填色
EDGE_LUMA = 120


def _grow(mask, px):
    return np.asarray(Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(px * 2 + 1))) > 0


def _largest(mask):
    """8 連通最大的那塊"""
    from collections import deque
    label = np.zeros(mask.shape, dtype=np.int32)
    best, best_size, current = 0, 0, 0
    h, w = mask.shape
    for y0, x0 in zip(*np.nonzero(mask)):
        if label[y0, x0]:
            continue
        current += 1
        label[y0, x0] = current
        queue, size = deque([(y0, x0)]), 0
        while queue:
            y, x = queue.popleft()
            size += 1
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not label[ny, nx]:
                        label[ny, nx] = current
                        queue.append((ny, nx))
        if size > best_size:
            best, best_size = current, size
    return label == best if best else mask


def cell_dirt(cell):
    """回傳 (離島, 霧, 亮邊) 三個布林遮罩"""
    arr = np.asarray(cell.convert("RGBA")).astype(np.int32)
    alpha = arr[..., 3]
    seen = alpha > 0
    islands = seen & ~_largest(seen)
    solid = alpha >= SOLID
    luma = arr[..., :3] @ np.array([299, 587, 114]) // 1000
    # 描邊的抗鋸齒是半透明的深色，半透明又亮的只可能是白底殘渣
    haze = seen & ~islands & ((~solid & ~_grow(solid, 1)) | ((alpha < 230) & (luma > 150)))
    edge = solid & _grow(~solid, 1)
    light_edge = edge & (luma > EDGE_LUMA) & ~islands
    return islands, haze, light_edge


def sheet_report(path, frame_size=None):
    folder = os.path.dirname(path)
    if frame_size is None:
        with open(os.path.join(folder, "meta.json"), encoding="utf-8") as handle:
            frame_size = json.load(handle)["frame_size"]
    fw, fh = frame_size
    sheet = Image.open(path).convert("RGBA")
    cells = []
    for index in range((sheet.width // fw) * (sheet.height // fh)):
        r, c = divmod(index, sheet.width // fw)
        cell = sheet.crop((c * fw, r * fh, (c + 1) * fw, (r + 1) * fh))
        if not np.asarray(cell)[..., 3].any():
            continue
        islands, haze, light = cell_dirt(cell)
        cells.append({"cell": index, "islands": int(islands.sum()), "haze": int(haze.sum()), "light_edge": int(light.sum())})
    total = {key: sum(c[key] for c in cells) for key in ("islands", "haze", "light_edge")}
    dirty = [c for c in cells if c["islands"] or c["haze"] or c["light_edge"]]
    return {"cells": len(cells), "dirty_cells": len(dirty), "total": total,
            "worst": sorted(dirty, key=lambda c: -(c["islands"] + c["haze"] + c["light_edge"]))[:8]}


def mark(path, out, frame_size):
    """髒像素塗紅，給人看是哪裡"""
    fw, fh = frame_size
    sheet = Image.open(path).convert("RGBA")
    arr = np.asarray(sheet).copy()
    for r in range(sheet.height // fh):
        for c in range(sheet.width // fw):
            box = (slice(r * fh, (r + 1) * fh), slice(c * fw, (c + 1) * fw))
            islands, haze, light = cell_dirt(Image.fromarray(arr[box]))
            bad = islands | haze | light
            arr[box][bad] = (255, 0, 0, 255)
    back = Image.new("RGBA", sheet.size, (40, 44, 56, 255))
    back.alpha_composite(Image.fromarray(arr))
    back.save(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sheet")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--mark", default="")
    args = parser.parse_args()
    report = sheet_report(args.sheet)
    if args.mark:
        with open(os.path.join(os.path.dirname(args.sheet), "meta.json"), encoding="utf-8") as handle:
            mark(args.sheet, args.mark, json.load(handle)["frame_size"])
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
    else:
        print("%(cells)d 格，髒的 %(dirty_cells)d 格" % report, report["total"])


if __name__ == "__main__":
    main()
