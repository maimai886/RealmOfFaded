# -*- coding: utf-8 -*-
"""換裝驗證用的測試件：頭髮、兩頂帽子、一把刀，全部是單純的幾何形。**不是定稿長相，不准出貨**。

用途只有一個：驗證分層換裝的產圖端，錨點、前後、像素化、裁切、換色是不是對的。
顏色照 ramps.json 的色階，左上受光三段：亮、中、暗，和正式件同一套調色盤，像素化之後才看得出真的成品會怎麼落格。
每個方向各畫一張，照 RO 頭飾每個方向一到兩張的做法；位置照那個方向頭的圓，在工作解析度上畫。
"""

import math

import numpy as np
from PIL import Image

# 光從左上前方來，三維單位向量：畫面右、下、朝鏡頭
LIGHT = (-0.55, -0.62, 0.56)


def _grid(size):
    ys, xs = np.mgrid[0:size[1], 0:size[0]].astype(np.float32)
    return xs, ys


def _paint(size, mask, shade, ramp, steps):
    """mask 裡照 shade 分三段上色：shade > 0.35 亮、< -0.25 暗、中間是中；steps 是 (暗, 中, 亮) 在色階裡的第幾階"""
    out = np.zeros((size[1], size[0], 4), dtype=np.uint8)
    dark, mid, light = (ramp[i] for i in steps)
    colour = np.where((shade > 0.35)[..., None], light, np.where((shade < -0.25)[..., None], dark, mid))
    out[mask, :3] = colour[mask]
    out[mask, 3] = 255
    return out


def _sphere_shade(xs, ys, cx, cy, r):
    """把形狀當成半徑 r 的球面算受光，明暗交界是弧線不是直線；回傳約 -1 到 1，減掉 0.35 讓暗面佔右下三成左右"""
    nx = (xs - cx) / max(r, 1e-6)
    ny = (ys - cy) / max(r, 1e-6)
    nz = np.sqrt(np.clip(1.0 - nx * nx - ny * ny, 0.0, 1.0))
    return (nx * LIGHT[0] + ny * LIGHT[1] + nz * LIGHT[2]) * 1.4 - 0.55


def _rounded_rect(xs, ys, x0, y0, x1, y1, radius):
    cx = np.clip(xs, x0 + radius, x1 - radius)
    cy = np.clip(ys, y0 + radius, y1 - radius)
    return np.hypot(xs - cx, ys - cy) <= radius


# 髮際線：x 相對頭中心、以半徑為單位，分成兩段；前面那段是瀏海，後面那段垂到耳朵以下。臉朝左的方向臉在左邊
HAIRLINE = {
    "s": [(-0.62, 0.35), (0.62, -0.25), (9.0, 0.35)],
    "sw": [(0.25, -0.25), (9.0, 0.45)],
    "w": [(-0.2, -0.3), (9.0, 0.5)],
    "nw": [(-0.55, -0.2), (9.0, 0.6)],
    "n": [(9.0, 0.62)],
}
# 後髮：垂在後頸的一塊，左右上下的範圍，以半徑為單位
HAIR_BACK = {
    "s": (-0.95, 0.2, 0.95, 0.95), "sw": (-0.9, 0.25, 0.95, 0.95), "w": (0.05, 0.3, 0.95, 1.05),
    "nw": (-0.6, 0.4, 0.95, 1.05), "n": (-0.95, 0.45, 0.95, 1.05),
}
# 頭髮的外包絡：頭的圓放大這麼多倍，頭髮不可以畫出這個圓；帽子的帽身要蓋得住它在帽簷以上的部分
HAIR_ENVELOPE = 1.07


def hair_front(size, circle, direction, ramp):
    xs, ys = _grid(size)
    cx, cy, r = circle
    disc = np.hypot(xs - cx, ys - (cy - 0.03 * r)) <= HAIR_ENVELOPE * r
    line = np.full(xs.shape, 9e9, dtype=np.float32)
    rel = (xs - cx) / r
    lower = -9.0
    for upper, depth in HAIRLINE[direction]:
        band = (rel >= lower) & (rel < upper)
        line = np.where(band, cy + depth * r, line)
        lower = upper
    mask = disc & (ys < line)
    return _paint(size, mask, _sphere_shade(xs, ys, cx, cy - 0.1 * r, 1.1 * r), ramp, (2, 4, 6))


def hair_back(size, circle, direction, ramp):
    xs, ys = _grid(size)
    cx, cy, r = circle
    x0, y0, x1, y1 = HAIR_BACK[direction]
    mask = _rounded_rect(xs, ys, cx + x0 * r, cy + y0 * r, cx + x1 * r, cy + y1 * r, 0.35 * r)
    return _paint(size, mask, _sphere_shade(xs, ys, cx, cy + 0.2 * r, 1.25 * r) - 0.15, ramp, (2, 3, 5))


def hat(size, circle, direction, kind, ramp):
    """帽子 A 是平頂圓筒帽，B 是尖錐帽；帽簷中心在頭中心往上半個半徑，30 度俯角看下去帽簷是扁的橢圓"""
    xs, ys = _grid(size)
    cx, cy, r = circle
    by = cy - 0.5 * r
    brim = ((xs - cx) / (1.18 * r)) ** 2 + ((ys - by) / (0.38 * r)) ** 2 <= 1.0
    steps = (1, 3, 4) if kind == "A" else (2, 4, 6)
    band = (cx - xs) / (0.8 * r)
    layers = [(brim, band * 0.7 + 0.1)]
    if kind == "A":
        top_y = by - 0.75 * r
        crown = (np.abs(xs - cx) <= 0.8 * r) & (ys >= top_y) & (ys <= by)
        top = ((xs - cx) / (0.8 * r)) ** 2 + ((ys - top_y) / (0.26 * r)) ** 2 <= 1.0
        layers += [(crown, band * 0.7)]
        top_only = top
    else:
        apex = (cx + 0.1 * r, by - 1.55 * r)
        # 三角形：兩條邊從頂點到帽簷的左右兩端
        left = (cx - 0.78 * r, by)
        right = (cx + 0.78 * r, by)
        def side(p, q):
            return (q[0] - p[0]) * (ys - p[1]) - (q[1] - p[1]) * (xs - p[0])
        cone = (side(left, apex) <= 0) & (side(apex, right) <= 0) & (ys <= by + 0.15 * r)
        cone &= ~((ys > by) & (((xs - cx) / (0.78 * r)) ** 2 + ((ys - by) / (0.25 * r)) ** 2 > 1.0))
        layers += [(cone, band * 0.8)]
    out = np.zeros((size[1], size[0], 4), dtype=np.uint8)
    for mask, shade in layers:
        painted = _paint(size, mask, shade, ramp, steps)
        out[mask] = painted[mask]
    if kind == "A":
        # 平頂是最亮的一面，整片一個顏色，和帽身的直條分開
        out[top_only, :3] = ramp[min(len(ramp) - 1, steps[2] + 1)]
        out[top_only, 3] = 255
    return out


# 刀：刀尖朝上畫，握把中心是握點。寬度照方向：正面背面看到的是刀背，斜向七成，側面整片
KNIFE_WIDTH = {"s": 0.4, "n": 0.4, "sw": 0.7, "nw": 0.7, "w": 1.0}


def knife(direction, px_per_m, ramps):
    """回傳 (圖, 握點的圖內座標, 軸的角度)；軸是握點指向刀尖，畫面右邊 0 度、上面 -90 度"""
    length = 0.42 * px_per_m
    width = max(3.0, 0.075 * px_per_m * KNIFE_WIDTH[direction])
    w = int(math.ceil(max(width, 0.11 * px_per_m * max(0.5, KNIFE_WIDTH[direction])) + 4))
    h = int(math.ceil(length + 4))
    size = (w, h)
    xs, ys = _grid(size)
    cx = w / 2.0
    top = 2.0
    blade_end = top + length * 0.62
    guard_end = blade_end + length * 0.07
    tip = top + width * 1.2
    half = width / 2.0
    blade = (ys >= top) & (ys <= blade_end) & (np.abs(xs - cx) <= half * np.clip((ys - top) / max(tip - top, 1e-6), 0.0, 1.0))
    guard_half = max(half * 1.6, 0.05 * px_per_m * max(0.5, KNIFE_WIDTH[direction]))
    guard = (ys > blade_end) & (ys <= guard_end) & (np.abs(xs - cx) <= guard_half)
    handle = (ys > guard_end) & (ys <= top + length) & (np.abs(xs - cx) <= max(1.5, half * 0.75))
    shade = (cx - xs) / max(half, 1.0)
    out = np.zeros((h, w, 4), dtype=np.uint8)
    for mask, ramp, steps in ((blade, ramps["white_armor"], (1, 3, 5)), (guard, ramps["brass"], (2, 3, 4)),
                              (handle, ramps["wood"], (1, 2, 3))):
        painted = _paint(size, mask, shade, ramp, steps)
        out[mask] = painted[mask]
    grip = (cx, (guard_end + top + length) / 2.0)
    return Image.fromarray(out, "RGBA"), grip, -90.0
