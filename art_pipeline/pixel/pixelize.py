# -*- coding: utf-8 -*-
"""紙偶在高解析度算動作，每一格再轉成像素畫。用系統的 python 跑，要有 Pillow、numpy、opencv。

驗證用的第一版：拿 art_pipeline/characters_v5 的紙偶在四倍解析度組出每一格，八個高解析像素併成一格，
人約 90 格高，和使用者 2026-09-27 給的像素立繪量到的 79 到 95 格同一級。

轉像素的每一步和為什麼：
  1. 整段動畫共用一套調色盤，從所有畫格的高解析像素一次量出來，每一格只准用這套顏色，不會一格一格閃
  2. 一格要不要畫看這八乘八裡有多少不透明，過半才畫；透明度只有全有全無
  3. 一格是什麼顏色用投票：八乘八裡每個像素先對到調色盤最近的顏色，票最多的贏。
     不取平均，平均會混出調色盤外的中間色，縮小後整張看起來是糊的；這是 RotSprite 縮回原尺寸時用的做法
  4. 使用者的黑線不拿去投票：線只有五六個高解析像素寬，縮八倍剩不到一格，投票會讓線時有時無。
     改成把線細化成一個像素寬的中心線，中心線穿過的格子畫成一格寬的線；剪影最外那圈線丟掉，另外重畫
  5. 眼睛這種整塊的深色用開運算從線裡分出來，當成一塊顏色處理，不細化
  6. 內部線照 Aseprite 的 pixel perfect 規則拿掉 L 形轉角多出來的那一格，斜線才是一格寬的階梯不會變粗
  7. 剪影最外一圈重畫成描邊，顏色是那一格底色乘 (0.30, 0.22, 0.24)，照 docs/美術風格指南.md 1.8，
     所以白衣服的邊是深藕色、皮膚的邊是深紅棕，沒有純黑
  8. 清雜點：只剩斜角相連的孤立格拿掉、一格大的透明洞補起來、周圍八格沒有同色的底色格改成周圍最多的顏色

參考過的做法：
  RotSprite，Xenowhirl 2007：放大後旋轉再用多數決縮回，不產生新顏色；這裡的旋轉在紙偶的高解析度就做完了，只借多數決
  Gerstner 等人，Pixelated Image Abstraction，NPAR 2012：整張圖先定一套調色盤再分配格子
  Kopf 等人，Content-Adaptive Image Downscaling，SIGGRAPH Asia 2013：細線縮小時要特別保住，不能只做面積平均
  Aseprite 的 pixel perfect 筆刷：一格寬的線拿掉 L 形轉角
  Zhang 和 Suen 1984 的細化演算法：拿中心線

用法：
  python art_pipeline/pixel/pixelize.py <視圖資料夾> <rig 資料夾> <輸出資料夾> [--sheet <圖集資料夾>] [--compare walk:s,attack:sw]
不寫 --sheet 就只轉 --compare 列的那幾段；寫了就把 rig 裡所有動作和方向轉成一份遊戲讀得動的圖集。
"""

import argparse
import json
import math
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
PIPELINE = os.path.join(HERE, "..")
sys.path.insert(0, PIPELINE)
sys.path.insert(0, os.path.join(PIPELINE, "characters_v5"))
import puppet_poses  # noqa: E402
import puppet_sheet as ps  # noqa: E402
from common import sheet_output  # noqa: E402

PROJECT_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
# 紙偶在四倍算：rig 的一倍是 176×232、人約 180 高，四倍人約 720 高，接近使用者畫的 1024 視圖原本的細度
HI_SCALE = 4
# 八個高解析像素併成一格：人約 90 格高，每公尺 48 格；1080p 預設基準距離 42.73 時一格剛好兩個螢幕像素
CELL = 8
PIXELS_PER_METER = 96.0 * HI_SCALE / CELL
# 深於這個亮度的像素當成使用者畫的墨線；皮膚約 218、白衣約 245、衣服上的淡灰摺線約 200
INK_LUMA = 110
# 眼睛這種整塊的深色：開運算用的圓直徑，線寬約五六個高解析像素，比它粗兩倍的才算一塊
BLOB_KERNEL = 11
# 剪影往內這麼多高解析像素裡的墨線是外框，丟掉另外重畫描邊；比線寬多留一點，
# 不然外框線靠內那半邊會被當成內部線，變成兩層邊
OUTER_BAND = 9
# 中心線在一格裡至少要有幾個像素才畫這一格，擦過格子角落的不算
LINE_MIN_PIXELS = 3
# 一格有多少比例是眼睛那種整塊深色，就整格畫成那個顏色
BLOB_MIN_SHARE = 0.35
# 調色盤：底色幾群、差多少以內併成一個顏色
FILL_CLUSTERS = 8
FILL_MERGE_DE = 10.0
# 描邊和內部線的顏色：底色乘這個，照風格指南 1.8；內部線比描邊淺，只把兩塊分開，不要搶剪影
OUTLINE_MUL = (0.30, 0.22, 0.24)
INNER_LINE_MUL = (0.58, 0.47, 0.50)
# 眼睛這種整塊深色不用純黑，用帶紫的深色
BLOB_COLOR = (46, 32, 48)


# ---------------------------------------------------------------- 高解析度的紙偶

def compose_hi(parts, posed, frame_size):
    """和 puppet_sheet.compose_frame 一樣，只是不在最後縮回一倍"""
    canvas = Image.new("RGBA", (frame_size[0] * HI_SCALE, frame_size[1] * HI_SCALE), (0, 0, 0, 0))
    affines, ends, forwards = {}, {}, {}
    names = [name for name in ps.CHAIN_ORDER if name in parts and name in posed]
    names += [name for name in parts if name in posed and name not in names]
    for name in names:
        parent = ps.CHAIN_PARENT.get(name)
        override = ends.get(parent) if parent else None
        if override is None and parent and parent.startswith("upper_arm") and parent not in parts and "torso" in forwards:
            elbow = parts[name]["start"]
            override = forwards["torso"](elbow[0], elbow[1])
        affines[name], ends[name], forwards[name] = ps.transform_for(parts[name], posed[name], override)
    sequence = [name for name in ps.layer_sequence(posed) if name in affines]
    leftovers = sorted((name for name in affines if name not in sequence), key=lambda n: -posed[n][4])
    for name in leftovers + sequence:
        ps.place(canvas, parts[name], affines[name])
    return canvas


def render_hires(views, rig, wanted):
    """wanted 是 [(動作, 方向)]；回傳 {(動作, 方向): [高解析 RGBA 畫格]}"""
    ps.WORK_SCALE = HI_SCALE
    ps.RESAMPLE = Image.BICUBIC
    ps.VIEW_RESAMPLE = Image.LANCZOS
    frame_size = tuple(rig["frame_size"])
    anchor_hi = (rig["anchor"][0] * HI_SCALE, rig["anchor"][1] * HI_SCALE)
    out = {}
    for direction in sorted({d for _, d in wanted}, key=rig["directions"].index):
        reference = rig["reference"][direction]
        canvas = ps.cut_view(os.path.join(views, direction + ".png"), reference["bbox"], frame_size)
        rest = rig.get("rest", {}).get(direction)
        merged = ps.segment(canvas, reference, rig.get("radii", {}), rest, merge_arms=direction in ps.ARM_MERGED_DIRECTIONS)
        split = ps.segment(canvas, reference, rig.get("radii", {}), rest) if direction in ps.ARM_MERGED_DIRECTIONS else merged
        rest_frame = compose_hi(merged, rest, frame_size) if rest else None
        for action, want_dir in wanted:
            if want_dir != direction:
                continue
            block = rig["actions"][action]
            parts_now = split if action in ps.ARM_SPLIT_ACTIONS else merged
            rows = block["dirs"][direction]
            if ps.POSE_MODE and rest:
                designed = puppet_poses.rows_for(rest, action, block["frames"], direction)
                if designed is not None:
                    rows = designed
            frames = []
            for index, posed in enumerate(rows):
                if action == "die" and rest_frame is not None:
                    frames.append(ps.rigid_action(action, index, block["frames"], direction, rest_frame, anchor_hi))
                else:
                    frames.append(compose_hi(parts_now, posed, frame_size))
            out[(action, direction)] = frames
            print("高解析 %s %s：%d 格" % (action, direction, len(frames)))
    return out


# ---------------------------------------------------------------- 顏色

def _to_lab(rgb):
    arr = np.asarray(rgb, dtype=np.uint8).reshape(-1, 1, 3)
    lab = cv2.cvtColor(arr, cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32)
    lab[:, 0] *= 100.0 / 255.0
    lab[:, 1:] -= 128.0
    return lab


def _luma(arr):
    return arr[..., 0] * 0.299 + arr[..., 1] * 0.587 + arr[..., 2] * 0.114


def ink_masks(arr):
    """回傳 (墨線, 整塊深色, 內部墨線)，都是高解析度的布林圖"""
    alpha = arr[..., 3] >= 128
    ink = (_luma(arr) < INK_LUMA) & alpha
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (BLOB_KERNEL, BLOB_KERNEL))
    blob = cv2.morphologyEx(ink.astype(np.uint8), cv2.MORPH_OPEN, kernel).astype(bool)
    line = ink & ~blob
    inside = cv2.distanceTransform(alpha.astype(np.uint8), cv2.DIST_L2, 3)
    inner_line = line & (inside > OUTER_BAND)
    return ink, blob, inner_line


def build_palette(frames):
    """所有畫格的不透明、不靠近墨線的像素一起分群，得到整段動畫共用的底色"""
    samples = []
    for frame in frames:
        arr = np.asarray(frame).astype(np.float32)
        ink, _, _ = ink_masks(arr)
        near_ink = cv2.dilate(ink.astype(np.uint8), np.ones((7, 7), np.uint8)).astype(bool)
        solid = (arr[..., 3] >= 250) & ~near_ink
        picked = arr[..., :3][solid][::7]
        samples.append(picked)
    data = np.concatenate(samples).astype(np.uint8)
    lab = _to_lab(data)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 60, 0.2)
    _, labels, centers = cv2.kmeans(lab, FILL_CLUSTERS, None, criteria, 4, cv2.KMEANS_PP_CENTERS)
    labels = labels.ravel()
    groups = []
    order = np.argsort(-np.bincount(labels, minlength=FILL_CLUSTERS))
    for index in order:
        share = float((labels == index).mean())
        if share < 0.004:
            continue
        for group in groups:
            if np.linalg.norm(centers[group[0]] - centers[index]) < FILL_MERGE_DE:
                group.append(index)
                break
        else:
            groups.append([index])
    fills = []
    for group in groups:
        members = np.isin(labels, group)
        # 用那一群真正的像素的中位數，不用群中心，群中心是平均會偏灰
        fills.append(tuple(int(v) for v in np.median(data[members], axis=0)))
    return fills


def derived_colors(fills):
    outline = [tuple(int(round(c * m)) for c, m in zip(fill, OUTLINE_MUL)) for fill in fills]
    inner = [tuple(int(round(c * m)) for c, m in zip(fill, INNER_LINE_MUL)) for fill in fills]
    return outline, inner


# ---------------------------------------------------------------- 一格一格決定

def _blocks(values):
    """(H, W, ...) 切成 (h, w, CELL*CELL, ...)"""
    h, w = values.shape[0] // CELL, values.shape[1] // CELL
    rest = values.shape[2:]
    return values[:h * CELL, :w * CELL].reshape(h, CELL, w, CELL, *rest).swapaxes(1, 2).reshape(h, w, CELL * CELL, *rest)


def thin(mask):
    """Zhang-Suen 細化，回傳一個像素寬的中心線"""
    img = mask.astype(np.uint8).copy()
    while True:
        changed = False
        for step in (0, 1):
            p = np.pad(img, 1)
            p2, p3, p4 = p[:-2, 1:-1], p[:-2, 2:], p[1:-1, 2:]
            p5, p6, p7 = p[2:, 2:], p[2:, 1:-1], p[2:, :-2]
            p8, p9 = p[1:-1, :-2], p[:-2, :-2]
            ring = [p2, p3, p4, p5, p6, p7, p8, p9, p2]
            count = p2 + p3 + p4 + p5 + p6 + p7 + p8 + p9
            trans = sum(((ring[i] == 0) & (ring[i + 1] == 1)).astype(np.uint8) for i in range(8))
            if step == 0:
                c1, c2 = (p2 * p4 * p6) == 0, (p4 * p6 * p8) == 0
            else:
                c1, c2 = (p2 * p4 * p8) == 0, (p2 * p6 * p8) == 0
            kill = (img == 1) & (count >= 2) & (count <= 6) & (trans == 1) & c1 & c2
            if kill.any():
                img[kill] = 0
                changed = True
        if not changed:
            return img.astype(bool)


def _neighbors8(grid, y, x):
    h, w = grid.shape
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w:
                yield ny, nx


def pixel_perfect(line):
    """一格寬的線拿掉 L 形轉角：這一格只連著一個橫的鄰居和一個直的鄰居，那兩個本來就斜著相連，拿掉不會斷"""
    line = line.copy()
    h, w = line.shape
    for y in range(h):
        for x in range(w):
            if not line[y, x]:
                continue
            around = [(ny, nx) for ny, nx in _neighbors8(line, y, x) if line[ny, nx]]
            if len(around) != 2:
                continue
            horizontal = [p for p in around if p[0] == y]
            vertical = [p for p in around if p[1] == x]
            if len(horizontal) == 1 and len(vertical) == 1:
                line[y, x] = False
    return line


def clean_alpha(solid):
    """一格大的透明洞補起來；只剩斜角相連、或周圍不到兩格的孤立格拿掉"""
    solid = solid.copy()
    p = np.pad(solid, 1)
    up, down, left, right = p[:-2, 1:-1], p[2:, 1:-1], p[1:-1, :-2], p[1:-1, 2:]
    solid |= (~solid) & up & down & left & right
    p = np.pad(solid, 1)
    four = p[:-2, 1:-1].astype(int) + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:]
    solid &= four >= 1
    p = np.pad(solid, 1)
    eight = sum(p[1 + dy:p.shape[0] - 1 + dy, 1 + dx:p.shape[1] - 1 + dx].astype(int)
                for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx)
    solid &= eight >= 2
    return solid


def spread_labels(labels, solid):
    """沒有底色票的不透明格，拿周圍已經有顏色的格一圈圈長進去"""
    labels = labels.copy()
    for _ in range(12):
        missing = solid & (labels < 0)
        if not missing.any():
            break
        p = np.pad(labels, 1, constant_values=-1)
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)):
            neighbor = p[1 + dy:p.shape[0] - 1 + dy, 1 + dx:p.shape[1] - 1 + dx]
            take = missing & (labels < 0) & (neighbor >= 0)
            labels[take] = neighbor[take]
    labels[solid & (labels < 0)] = 0
    return labels


def remove_orphans(labels, solid):
    """周圍八格沒有同色的底色格，改成周圍最多的那個顏色"""
    labels = labels.copy()
    h, w = labels.shape
    for y in range(h):
        for x in range(w):
            if not solid[y, x]:
                continue
            around = [labels[ny, nx] for ny, nx in _neighbors8(labels, y, x) if solid[ny, nx]]
            if not around or labels[y, x] in around:
                continue
            values, counts = np.unique(around, return_counts=True)
            labels[y, x] = values[np.argmax(counts)]
    return labels


def pixelize_frame(frame, fills, outline, inner, blob_color=BLOB_COLOR, debug=None):
    arr = np.asarray(frame).astype(np.float32)
    h, w = arr.shape[0] // CELL, arr.shape[1] // CELL
    alpha = arr[..., 3]
    ink, blob, inner_ink = ink_masks(arr)

    # 透明度：過半才畫
    coverage = _blocks(alpha).mean(axis=2) / 255.0
    solid = clean_alpha(coverage >= 0.5)

    # 底色投票：不是墨線、夠不透明的像素對到最近的底色
    fill_lab = _to_lab(fills)
    rgb = arr[..., :3].clip(0, 255).astype(np.uint8)
    lab = _to_lab(rgb.reshape(-1, 3)).reshape(arr.shape[0], arr.shape[1], 3)
    dist = np.linalg.norm(lab[:, :, None, :] - fill_lab[None, None, :, :], axis=3)
    nearest = np.argmin(dist, axis=2)
    voter = (alpha >= 128) & ~ink
    votes = np.zeros((h, w, len(fills)), np.int32)
    nearest_b = _blocks(nearest)
    voter_b = _blocks(voter)
    for index in range(len(fills)):
        votes[..., index] = ((nearest_b == index) & voter_b).sum(axis=2)
    labels = np.where(votes.sum(axis=2) > 0, np.argmax(votes, axis=2), -1)
    labels = spread_labels(labels, solid)
    labels = remove_orphans(labels, solid)

    # 整塊深色，例如眼睛
    blob_cell = (_blocks(blob).mean(axis=2) >= BLOB_MIN_SHARE) & solid

    # 內部線：中心線穿過的格子
    skeleton = thin(inner_ink)
    line_cell = (_blocks(skeleton).sum(axis=2) >= LINE_MIN_PIXELS) & solid & ~blob_cell

    # 剪影最外一圈是描邊
    p = np.pad(solid, 1)
    ring = solid & ~(p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:])
    line_cell &= ~ring
    line_cell = pixel_perfect(line_cell)

    out = np.zeros((h, w, 4), np.uint8)
    fills_arr = np.array(fills, np.uint8)
    out[..., :3] = fills_arr[np.clip(labels, 0, len(fills) - 1)]
    out[..., :3][line_cell] = np.array(inner, np.uint8)[labels[line_cell]]
    out[..., :3][blob_cell] = blob_color
    out[..., :3][ring] = np.array(outline, np.uint8)[labels[ring]]
    out[..., 3] = np.where(solid, 255, 0)
    if debug is not None:
        debug["skeleton"] = skeleton
        debug["inner_ink"] = inner_ink
    return Image.fromarray(out, "RGBA")


def direct_nearest(frame):
    return frame.resize((frame.width // CELL, frame.height // CELL), Image.NEAREST)


def direct_smooth(frame):
    small = frame.convert("RGBa").resize((frame.width // CELL, frame.height // CELL), Image.LANCZOS)
    return small.convert("RGBA")


# ---------------------------------------------------------------- 對照圖

def _font(size):
    for path in ("C:/Windows/Fonts/msjh.ttc", "/System/Library/Fonts/PingFang.ttc"):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def union_box(frames, pad=2):
    box = None
    for frame in frames:
        b = frame.getbbox()
        if b is None:
            continue
        box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3]))
    x0, y0, x1, y1 = box
    return (max(0, x0 - pad), max(0, y0 - pad), x1 + pad, y1 + pad)


def comparison_sheet(rows, title, zoom, background):
    """rows 是 [(標題, [一格一格的小圖])]，每格放大 zoom 倍、最近點，排成一張"""
    all_frames = [f for _, frames in rows for f in frames]
    box = union_box(all_frames)
    cw, ch = (box[2] - box[0]) * zoom, (box[3] - box[1]) * zoom
    label_w, gap, head = 190, 6, 46
    columns = max(len(frames) for _, frames in rows)
    sheet = Image.new("RGB", (label_w + columns * (cw + gap), head + len(rows) * (ch + gap)), (34, 32, 38))
    pen = ImageDraw.Draw(sheet)
    pen.text((10, 8), title, fill=(236, 232, 224), font=_font(24))
    for r, (name, frames) in enumerate(rows):
        y = head + r * (ch + gap)
        pen.text((10, y + ch // 2 - 14), name, fill=(236, 232, 224), font=_font(22))
        for c, frame in enumerate(frames):
            tile = Image.new("RGBA", (box[2] - box[0], box[3] - box[1]), background + (255,))
            tile.alpha_composite(frame.crop(box))
            sheet.paste(tile.resize((cw, ch), Image.NEAREST).convert("RGB"), (label_w + c * (cw + gap), y))
    return sheet


def palette_swatch(fills, outline, inner, path):
    colors = [("底色", fills), ("描邊", outline), ("內部線", inner), ("整塊深色", [BLOB_COLOR])]
    sheet = Image.new("RGB", (120 + 60 * max(len(c) for _, c in colors), 70 * len(colors)), (34, 32, 38))
    pen = ImageDraw.Draw(sheet)
    for r, (name, row) in enumerate(colors):
        pen.text((8, r * 70 + 20), name, fill=(236, 232, 224), font=_font(20))
        for c, color in enumerate(row):
            pen.rectangle((120 + c * 60, r * 70 + 8, 120 + c * 60 + 52, r * 70 + 60), fill=tuple(color))
    sheet.save(path)


# ---------------------------------------------------------------- 遊戲讀得動的圖集

def write_sheet(rig, pixel_frames, out_dir):
    frame_w, frame_h = rig["frame_size"][0] * HI_SCALE // CELL, rig["frame_size"][1] * HI_SCALE // CELL
    anchor = [rig["anchor"][0] * HI_SCALE // CELL, rig["anchor"][1] * HI_SCALE // CELL]
    directions = rig["directions"]
    cells, actions = [], {}
    for action in ps.ORDER:
        if action not in rig["actions"]:
            continue
        block = rig["actions"][action]
        actions[action] = {"start": len(cells), "frames": block["frames"], "fps": block["fps"], "loop": block["loop"]}
        if "hit_frame" in block:
            actions[action]["hit_frame"] = block["hit_frame"]
        for direction in directions:
            cells.extend(pixel_frames[(action, direction)])
    columns = 8
    rows = -(-len(cells) // columns)
    sheet = Image.new("RGBA", (columns * frame_w, rows * frame_h), (0, 0, 0, 0))
    for index, cell in enumerate(cells):
        sheet.alpha_composite(cell, (index % columns * frame_w, index // columns * frame_h))
    os.makedirs(out_dir, exist_ok=True)
    sheet_path = os.path.join(out_dir, "sheet.png")
    sheet.save(sheet_path)
    sheet_output.write_import(sheet_path, PROJECT_ROOT, pixel=True)
    # 素體只有一個區，不出遮罩；引擎沒看到 mask.png 就當整張是主要區域，見 common/sheet_output.py
    ratio = HI_SCALE / float(CELL)
    head_attach = {action: {direction: [[row["head"][0] * ratio, row["head"][1] * ratio]
                                        for row in rig["actions"][action]["dirs"][direction]]
                            for direction in directions} for action in actions}
    meta = {"frame_size": [frame_w, frame_h], "columns": columns, "pixels_per_meter": PIXELS_PER_METER, "anchor": anchor,
            "directions": directions, "filter": "nearest", "layout": "packed", "head_layer": False, "head_width": 0,
            "actions": actions, "head_attach": head_attach,
            "source": {"pipeline": "art_pipeline/pixel/pixelize.py", "hi_scale": HI_SCALE, "cell": CELL}}
    with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as handle:
        json.dump(meta, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print("圖集 %d 格、%s -> %s" % (len(cells), sheet.size, out_dir))


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("views")
    parser.add_argument("rig")
    parser.add_argument("out")
    parser.add_argument("--sheet", default="")
    parser.add_argument("--compare", default="walk:s,walk:sw,attack:s,attack:sw")
    parser.add_argument("--zoom", type=int, default=6)
    args = parser.parse_args()
    with open(os.path.join(args.rig, "rig.json"), encoding="utf-8") as handle:
        rig = json.load(handle)
    compare = [tuple(item.split(":")) for item in args.compare.split(",") if item]
    wanted = list(compare)
    if args.sheet:
        wanted = [(a, d) for a in ps.ORDER if a in rig["actions"] for d in rig["directions"]]
    hires = render_hires(args.views, rig, wanted)
    os.makedirs(args.out, exist_ok=True)

    # 調色盤從比對的那幾段一起量，出圖集時從全部動作量；兩種都是整批一套
    palette_frames = [f for key in (wanted if args.sheet else compare) for f in hires[key]]
    fills = build_palette(palette_frames)
    outline, inner = derived_colors(fills)
    colors = set(fills) | set(outline) | set(inner) | {BLOB_COLOR}
    print("調色盤：底色 %d、描邊 %d、內部線 %d、整塊深色 1，共 %d 色" % (len(fills), len(outline), len(inner), len(colors)))
    with open(os.path.join(args.out, "palette.json"), "w", encoding="utf-8") as handle:
        json.dump({"fills": fills, "outline": outline, "inner_line": inner, "blob": BLOB_COLOR, "total": len(colors)},
                  handle, ensure_ascii=False, indent=1)
    palette_swatch(fills, outline, inner, os.path.join(args.out, "palette.png"))

    pixel_frames = {key: [pixelize_frame(f, fills, outline, inner) for f in frames] for key, frames in hires.items()}
    for key in compare:
        action, direction = key
        folder = os.path.join(args.out, "frames", "%s_%s" % key)
        os.makedirs(folder, exist_ok=True)
        near = [direct_nearest(f) for f in hires[key]]
        smooth = [direct_smooth(f) for f in hires[key]]
        mine = pixel_frames[key]
        for i, (hi, a, b, c) in enumerate(zip(hires[key], near, smooth, mine)):
            hi.save(os.path.join(folder, "hires_%d.png" % i))
            a.save(os.path.join(folder, "nearest_%d.png" % i))
            b.save(os.path.join(folder, "smooth_%d.png" % i))
            c.save(os.path.join(folder, "pixel_%d.png" % i))
        # 顏色數：直接縮小的兩種每格各自有多少色，轉像素整段一套
        stats = {
            "nearest_colors_per_frame": [len(set(map(tuple, np.asarray(f)[np.asarray(f)[..., 3] > 0][:, :3].tolist()))) for f in near],
            "smooth_colors_per_frame": [len(set(map(tuple, np.asarray(f)[np.asarray(f)[..., 3] > 0][:, :3].tolist()))) for f in smooth],
            "smooth_semi_transparent_px": [int(((np.asarray(f)[..., 3] > 0) & (np.asarray(f)[..., 3] < 255)).sum()) for f in smooth],
            "pixel_colors_whole_clip": len(set(tuple(v) for f in mine for v in np.asarray(f)[np.asarray(f)[..., 3] > 0][:, :3].tolist())),
            "height_cells": [int(f.getbbox()[3] - f.getbbox()[1]) for f in mine],
        }
        with open(os.path.join(folder, "stats.json"), "w", encoding="utf-8") as handle:
            json.dump(stats, handle, ensure_ascii=False, indent=1)
        title = "%s %s：同一段動作三種縮法，每格放大 %d 倍最近點" % (action, direction, args.zoom)
        for bg_name, bg in (("grass", (92, 124, 64)), ("floor", (206, 196, 172))):
            sheet = comparison_sheet([("直接最近點", near), ("直接平滑", smooth), ("轉像素流程", mine)], title, args.zoom, bg)
            sheet.save(os.path.join(args.out, "compare_%s_%s_%s.png" % (action, direction, bg_name)))
        print("%s %s 對照圖好了，%s" % (action, direction, json.dumps(stats, ensure_ascii=False)))
    if args.sheet:
        write_sheet(rig, pixel_frames, args.sheet)


if __name__ == "__main__":
    main()
