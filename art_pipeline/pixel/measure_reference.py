# -*- coding: utf-8 -*-
"""量像素畫參考圖：格子大小、角色幾格高、調色盤幾色、描邊怎麼上色、明暗分幾階、有沒有網點抖色。

參考圖是有損壓縮過的 webp，一格不是整數個影像像素，所以每一項都是統計量，不是逐格讀出來的。
用法：
  python art_pipeline/pixel/measure_reference.py 參考圖.webp 輸出資料夾
角色的大概範圍寫在 CHARACTERS，去背用 OpenCV 的 grabCut，量完會存一張去背疊圖給人核對。
"""

import json
import os
import sys

import cv2
import numpy as np
from PIL import Image

# 使用者 2026-09-27 給的六職業立繪，1280×1554，兩欄三列；框是角色大概在哪，grabCut 從這個框往內收
CHARACTERS = {
    "assassin": (90, 100, 440, 420),
    "alchemist": (840, 110, 240, 410),
    "priest": (80, 590, 330, 440),
    "dark_knight": (770, 600, 340, 440),
    "blacksmith": (50, 1120, 440, 434),
    "magic_swordsman": (760, 1100, 420, 454),
}
# 只拿去背乾淨的三隻量調色盤和描邊，另外三隻的遮罩吃進太多背景
CLEAN = ("alchemist", "priest", "magic_swordsman")


def edge_gap_histogram(rgb, box):
    """每一列找顏色跳變的位置，兩個跳變之間的距離就是色塊寬；最常見的最小寬度就是一格的大小"""
    x0, y0, x1, y1 = box
    crop = rgb[y0:y1, x0:x1].astype(np.float32)
    diff = np.abs(np.diff(crop, axis=1)).sum(2)
    gaps = []
    for row in diff:
        edges = np.nonzero(row > 60)[0]
        groups = []
        for value in edges:
            if groups and value - groups[-1][-1] <= 1:
                groups[-1].append(value)
            else:
                groups.append([value])
        centers = [float(np.mean(group)) for group in groups]
        gaps.extend(np.diff(centers).tolist())
    counts, _ = np.histogram(gaps, bins=np.arange(1.5, 16.5, 1.0))
    return {int(w): int(c) for w, c in zip(range(2, 17), counts)}


def comb_score(profile, period):
    """格線對齊度：在這個週期的格線上取梯度平均，除以全部的平均；1 表示格線上沒有比較多邊"""
    n = len(profile)
    best = 0.0
    for phase in np.arange(0.0, period, 0.1):
        pos = np.arange(phase, n - 1, period)
        i = np.floor(pos).astype(int)
        f = pos - i
        value = (profile[i] * (1 - f) + profile[np.minimum(i + 1, n - 1)] * f).mean()
        best = max(best, value)
    return best / profile.mean()


def segment(bgr, rect):
    mask = np.zeros(bgr.shape[:2], np.uint8)
    cv2.grabCut(bgr, mask, rect, np.zeros((1, 65)), np.zeros((1, 65)), 6, cv2.GC_INIT_WITH_RECT)
    fg = ((mask == 1) | (mask == 3)).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(fg)
    biggest = 1 + int(np.argmax(stats[1:, 4]))
    return labels == biggest


def palette_curve(lab_pixels, ks):
    """k 個顏色重建全部像素的平均色差；曲線變平的地方就是實際用了幾色"""
    data = lab_pixels.astype(np.float32)
    out = {}
    for k in ks:
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, 0.5)
        _, labels, centers = cv2.kmeans(data, k, None, criteria, 3, cv2.KMEANS_PP_CENTERS)
        err = np.linalg.norm(data - centers[labels.ravel()], axis=1).mean()
        out[k] = round(float(err), 2)
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    src, out_dir = sys.argv[1], sys.argv[2]
    os.makedirs(out_dir, exist_ok=True)
    rgb = np.asarray(Image.open(src).convert("RGB"))
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    lab[..., 0] *= 100.0 / 255.0
    lab[..., 1:] -= 128.0
    gray = rgb.astype(np.float32).mean(2)
    report = {"image_size": [rgb.shape[1], rgb.shape[0]]}

    # 一、格子：全圖的梯度剖面對每個候選週期打分；再看色塊寬度的直方圖
    dx = np.abs(np.diff(gray, axis=1)).mean(0)
    dy = np.abs(np.diff(gray, axis=0)).mean(1)
    report["grid_comb_score"] = {
        axis: {str(round(p, 2)): round(float(comb_score(prof, p)), 3) for p in (4.0, 4.3, 4.57, 4.8, 5.0, 5.5, 6.0)}
        for axis, prof in (("x", dx), ("y", dy))}
    masks = {}
    report["characters"] = {}
    overlay = bgr.copy()
    for name, rect in CHARACTERS.items():
        mask = segment(bgr, rect)
        masks[name] = mask
        ys, xs = np.nonzero(mask)
        box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
        report["characters"][name] = {"bbox": box, "height_px": box[3] - box[1],
                                      "edge_gap_histogram": edge_gap_histogram(rgb, box)}
        overlay[mask] = (overlay[mask] * 0.5 + np.array([255, 0, 255]) * 0.5).astype(np.uint8)
        cv2.rectangle(overlay, box[:2], (box[2], box[3]), (0, 255, 0), 2)
    cv2.imwrite(os.path.join(out_dir, "ref_segmentation.png"), overlay)
    # 最小色塊寬度：各角色直方圖加總，取 3 到 6 之間的眾數附近加權平均當一格
    total = {}
    for entry in report["characters"].values():
        for w, c in entry["edge_gap_histogram"].items():
            total[w] = total.get(w, 0) + c
    # 格子大小取梯度剖面在 4.2 到 5.2 之間對齊度最高的週期；4.0 是 webp 壓縮區塊的邊，不算
    scan = {}
    for p in np.arange(4.2, 5.2, 0.01):
        scan[round(float(p), 2)] = comb_score(dx, p) + comb_score(dy, p)
    cell = max(scan, key=scan.get)
    report["cell_px_estimate"] = cell
    report["cell_scan_top"] = sorted(((k, round(v / 2, 3)) for k, v in scan.items()), key=lambda t: -t[1])[:5]
    report["edge_gap_histogram_all"] = total
    for name, entry in report["characters"].items():
        entry["height_cells"] = round(entry["height_px"] / cell, 1)

    # 二、調色盤：乾淨的三隻各自量 k 色重建誤差曲線
    report["palette"] = {}
    for name in CLEAN:
        eroded = cv2.erode(masks[name].astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
        report["palette"][name] = palette_curve(lab[eroded], (4, 8, 12, 16, 24, 32, 48, 64))

    # 二之二：照格子中心取樣回原本的像素格，再數相差 6 以上的顏色有幾個；壓縮和縮放混出來的中間色大多會被格子取樣避開
    report["palette_on_grid"] = {}
    for name in CLEAN:
        x0, y0, x1, y1 = report["characters"][name]["bbox"]
        xs = np.arange(x0 + cell / 2, x1, cell).astype(int)
        ys = np.arange(y0 + cell / 2, y1, cell).astype(int)
        blurred = cv2.medianBlur(rgb, 3)
        grid_rgb = blurred[np.ix_(ys, xs)]
        grid_lab = lab[np.ix_(ys, xs)]
        inside = cv2.erode(masks[name].astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool)[np.ix_(ys, xs)]
        samples = grid_lab[inside]
        kept = []
        for c in samples[np.argsort(-np.bincount(np.zeros(len(samples), int)))] if False else samples:
            if not kept or np.min(np.linalg.norm(np.array(kept) - c, axis=1)) >= 6:
                kept.append(c)
        report["palette_on_grid"][name] = {"cells": int(inside.sum()), "distinct_de6": len(kept),
                                           "kmeans_error": palette_curve(samples, (8, 16, 24, 32, 48))}
        Image.fromarray(grid_rgb.astype(np.uint8)).resize((grid_rgb.shape[1] * 6, grid_rgb.shape[0] * 6), Image.NEAREST).save(
            os.path.join(out_dir, "grid_%s.png" % name))

    # 三、描邊：剪影最外一格和往內三格的顏色比較
    report["outline"] = {}
    for name in CLEAN:
        m = masks[name].astype(np.uint8)
        k = np.ones((3, 3), np.uint8)
        ring = m & ~cv2.erode(m, k, iterations=4)
        inner = cv2.erode(m, k, iterations=6) & ~cv2.erode(m, k, iterations=12)
        ring_lab = lab[ring.astype(bool)]
        inner_lab = lab[inner.astype(bool)]
        ring_c = np.hypot(ring_lab[:, 1], ring_lab[:, 2])
        inner_c = np.hypot(inner_lab[:, 1], inner_lab[:, 2])
        dark = ring_lab[ring_lab[:, 0] < np.percentile(ring_lab[:, 0], 40)]
        hue = np.degrees(np.arctan2(dark[:, 2], dark[:, 1])) % 360
        report["outline"][name] = {
            "ring_L_median": round(float(np.median(ring_lab[:, 0])), 1),
            "inner_L_median": round(float(np.median(inner_lab[:, 0])), 1),
            "ring_dark40_L_median": round(float(np.median(dark[:, 0])), 1),
            "ring_dark40_chroma_median": round(float(np.median(np.hypot(dark[:, 1], dark[:, 2]))), 1),
            "ring_dark40_hue_median_deg": round(float(np.median(hue)), 0),
            "ring_chroma_median": round(float(np.median(ring_c)), 1),
            "inner_chroma_median": round(float(np.median(inner_c)), 1),
            "ring_pure_black_share": round(float((ring_lab[:, 0] < 8).mean()), 3),
        }

    # 四、明暗階數：乾淨的三隻取 32 色，照色相分組，每組數有幾個明度相差 6 以上的階
    report["shade_steps"] = {}
    for name in CLEAN:
        eroded = cv2.erode(masks[name].astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
        data = lab[eroded].astype(np.float32)
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, 0.5)
        _, labels, centers = cv2.kmeans(data, 32, None, criteria, 3, cv2.KMEANS_PP_CENTERS)
        share = np.bincount(labels.ravel(), minlength=32) / float(len(labels))
        families = {}
        for center, s in zip(centers, share):
            if s < 0.005:
                continue
            chroma = float(np.hypot(center[1], center[2]))
            key = "neutral" if chroma < 8 else str(int(((np.degrees(np.arctan2(center[2], center[1])) % 360) + 15) // 30 * 30 % 360))
            families.setdefault(key, []).append(round(float(center[0]), 1))
        steps = {}
        for key, ls in families.items():
            ls = sorted(ls)
            merged = [ls[0]]
            for v in ls[1:]:
                if v - merged[-1] >= 6:
                    merged.append(v)
            steps[key] = merged
        report["shade_steps"][name] = steps

    # 五、網點抖色：用估出來的格子大小在格子中心取樣，數 2×2 棋盤格的比例
    report["dither"] = {}
    for name in CLEAN:
        x0, y0, x1, y1 = report["characters"][name]["bbox"]
        best = None
        for phase in (0.0, cell / 3, 2 * cell / 3):
            xs = np.arange(x0 + phase + cell / 2, x1, cell).astype(int)
            ys = np.arange(y0 + phase + cell / 2, y1, cell).astype(int)
            grid = lab[np.ix_(ys, xs)]
            inside = masks[name][np.ix_(ys, xs)]
            a, b, c, d = grid[:-1, :-1], grid[:-1, 1:], grid[1:, :-1], grid[1:, 1:]
            ok = inside[:-1, :-1] & inside[:-1, 1:] & inside[1:, :-1] & inside[1:, 1:]
            same_ad = np.linalg.norm(a - d, axis=2) < 6
            same_bc = np.linalg.norm(b - c, axis=2) < 6
            diff_ab = np.linalg.norm(a - b, axis=2) > 12
            checker = same_ad & same_bc & diff_ab & ok
            rate = float(checker.sum()) / max(1, int(ok.sum()))
            if best is None or rate > best:
                best = rate
        report["dither"][name] = round(best, 4)

    with open(os.path.join(out_dir, "reference_measure.json"), "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=1)
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
