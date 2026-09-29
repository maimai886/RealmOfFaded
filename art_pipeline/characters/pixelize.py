# -*- coding: utf-8 -*-
"""紙娃娃每一層共用的像素化：身體、頭髮、頭飾、武器、盾、披風都走這一支，同一組步驟同一套調色盤。

一格的流程，順序不能換：
1. 工作畫布是目標的整數倍 k，面積平均縮小，透明像素的顏色不算進去
2. 透明度 0.5 切成全有全無，沒有半透明
3. 鎖調色盤：每個像素換成 ramps.json 裡最近的那個顏色，在 OKLab 裡量距離；整批共用一套，不每格各自量化、不抖色
4. 清孤立點：四周沒有同色、八個鄰居有五個以上同一色的單顆像素換成那個顏色；四邊都沒有鄰居的不透明單點拿掉，
   四邊都被包住的透明單點補上
5. 一格寬的帶色描邊：剪影最外一圈換成那個材質的墨色，墨色是色階中間那一階乘 (0.30, 0.22, 0.24)，
   和 docs/美術風格指南.md 1.8 的線色同一個算法；外圈本來就是畫的墨線時，材質照往內兩格裡最多的那一條色階算

染色：鎖完調色盤之後每個像素都是某條色階的第幾階，換色就是換成另一條色階的同一階，見 docs/精靈圖規格.md「紙娃娃圖層」。
"""

import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
RAMPS_PATH = os.path.join(PROJECT_ROOT, "assets", "generated", "sprites", "characters", "ramps.json")
INK_FACTOR = (0.30, 0.22, 0.24)
ALPHA_CUT = 0.5


def _hex(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _srgb_to_linear(c):
    c = np.asarray(c, dtype=np.float64) / 255.0
    return np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)


def oklab(rgb):
    """sRGB 0 到 255 → OKLab，最後一維是 3"""
    lin = _srgb_to_linear(rgb)
    r, g, b = lin[..., 0], lin[..., 1], lin[..., 2]
    l_ = np.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b)
    m_ = np.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
    s_ = np.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
    return np.stack([0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
                     1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
                     0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_], axis=-1)


class Palette:
    """ramps.json 攤平成一張表：每個顏色記它屬於哪條色階、第幾階；每條色階另外有一個墨色"""

    def __init__(self, path=RAMPS_PATH):
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        colours, ramp_of, step_of = [], [], []
        self.ramps = {}
        self.ink = {}
        for name, steps in data["ramps"].items():
            rgb = [_hex(v) for v in steps]
            self.ramps[name] = rgb
            for index, colour in enumerate(rgb):
                colours.append(colour)
                ramp_of.append(name)
                step_of.append(index)
            mid = rgb[len(rgb) // 2]
            ink = tuple(int(round(mid[i] * INK_FACTOR[i])) for i in range(3))
            self.ink[name] = ink
        self.ink_base = len(colours)
        for name in sorted(self.ink):
            ink = self.ink[name]
            colours.append(ink)
            ramp_of.append(name)
            step_of.append(-1)
        # 全域的深色：眼睛、畫的墨線縮下來的顏色
        self.outline = _hex(data.get("outline", "#242424"))
        colours.append(self.outline)
        ramp_of.append("")
        step_of.append(-1)
        self.colours = np.array(colours, dtype=np.uint8)
        self.lab = oklab(self.colours.astype(np.float64))
        self.ramp_of = ramp_of
        self.step_of = np.array(step_of)
        self.ramp_names = sorted(self.ramps)
        self.ramp_code = np.array([self.ramp_names.index(r) if r else -1 for r in ramp_of])
        self.ink_rgb = np.array([self.ink[name] for name in self.ramp_names], dtype=np.uint8)

    def nearest(self, rgb):
        """每個像素最近的調色盤索引"""
        lab = oklab(rgb.astype(np.float64))
        flat = lab.reshape(-1, 3)
        best = np.empty(len(flat), dtype=np.int32)
        for start in range(0, len(flat), 65536):
            chunk = flat[start:start + 65536]
            d = ((chunk[:, None, :] - self.lab[None, :, :]) ** 2).sum(-1)
            best[start:start + 65536] = d.argmin(1)
        return best.reshape(rgb.shape[:-1])

    def ramp_colours(self, name):
        return self.ramps[name]


# 鎖色分兩步：先照整張調色盤找最近，離某個顏色夠近的算「確定」；每一顆的材質是附近確定的像素裡最多的那條色階，
# 再只在那條色階、它的墨色和全域深色裡找最近。只做第一步的話，墨線和皮膚混出來的褐色會鎖到木頭、黃銅那幾條，
# 身體上的線變成一段褐一段橘的虛線（2026-09-27 第一版放大看到的）
CONFIDENT = 0.035
MATERIAL_RADIUS = 3


def _box_sum(mask, radius):
    padded = np.pad(mask.astype(np.int32), radius)
    c = padded.cumsum(0).cumsum(1)
    c = np.pad(c, ((1, 0), (1, 0)))
    size = 2 * radius + 1
    return c[size:, size:] - c[:-size, size:] - c[size:, :-size] + c[:-size, :-size]


def lock_to_materials(rgb, solid, palette):
    """rgb 是 0 到 255 的浮點，回傳每一格的調色盤索引"""
    lab = oklab(rgb)
    flat = lab[solid]
    d = ((flat[:, None, :] - palette.lab[None, :, :]) ** 2).sum(-1)
    first = d.argmin(1)
    best = np.sqrt(d[np.arange(len(first)), first])
    code_map = np.full(solid.shape, -1, dtype=np.int32)
    code_map[solid] = np.where((palette.step_of[first] >= 0) & (best < CONFIDENT), palette.ramp_code[first], -1)
    counts = np.stack([_box_sum(code_map == c, MATERIAL_RADIUS) for c in range(len(palette.ramp_names))], axis=0)
    material = np.where(counts.max(0) > 0, counts.argmax(0), -1)
    index = np.zeros(solid.shape, dtype=np.int32)
    index[solid] = first
    mat = material[solid]
    result = first.copy()
    outline_index = len(palette.colours) - 1
    for code, name in enumerate(palette.ramp_names):
        rows = mat == code
        if not rows.any():
            continue
        allowed = [i for i, r in enumerate(palette.ramp_of) if r == name] + [outline_index]
        sub = d[rows][:, allowed]
        result[rows] = np.array(allowed)[sub.argmin(1)]
    index[solid] = result
    return index


def area_downsample(rgba, k):
    """uint8 或 0 到 1 的 RGBA，k×k 一塊面積平均；顏色用透明度加權，透明的顏色不混進來。回傳 0 到 1 的浮點"""
    arr = rgba.astype(np.float64)
    if arr.max() > 1.0:
        arr = arr / 255.0
    h, w = arr.shape[0] // k, arr.shape[1] // k
    blocks = arr[:h * k, :w * k].reshape(h, k, w, k, 4)
    alpha = blocks[..., 3].mean(axis=(1, 3))
    weighted = (blocks[..., :3] * blocks[..., 3:4]).mean(axis=(1, 3))
    colour = np.where(alpha[..., None] > 1e-6, weighted / np.maximum(alpha[..., None], 1e-6), 0.0)
    return np.concatenate([colour, alpha[..., None]], axis=2)


def _neighbours4(mask):
    p = np.pad(mask, 1, constant_values=False)
    return [p[:-2, 1:-1], p[2:, 1:-1], p[1:-1, :-2], p[1:-1, 2:]]


def _shift(arr, dy, dx, fill):
    out = np.full_like(arr, fill)
    h, w = arr.shape[:2]
    ys = slice(max(0, dy), h + min(0, dy))
    yd = slice(max(0, -dy), h + min(0, -dy))
    xs = slice(max(0, dx), w + min(0, dx))
    xd = slice(max(0, -dx), w + min(0, -dx))
    out[ys, xs] = arr[yd, xd]
    return out


def _line_class(index, step_of):
    """墨色和全域深色算同一類：畫的墨線縮下來是一串深色輪流出現，逐色看每一顆都是孤立點，一清就變虛線"""
    return np.where(step_of[np.maximum(index, 0)] < 0, LINE_CLASS, index)


LINE_CLASS = 10_000


def despeckle(index, solid, palette_lab, step_of):
    """清孤立點，回傳 (index, solid, 改了幾顆)。墨線那一類不動"""
    changed = 0
    # 透明度：四邊都沒有鄰居的不透明單點拿掉；四邊都被包住的透明單點補上
    n4 = _neighbours4(solid)
    lone = solid & ~(n4[0] | n4[1] | n4[2] | n4[3])
    hole = ~solid & n4[0] & n4[1] & n4[2] & n4[3]
    changed += int(lone.sum()) + int(hole.sum())
    solid = (solid & ~lone) | hole
    # 顏色：自己和八個鄰居都不同色、而鄰居裡有五顆以上同一色，換成那一色
    offsets = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    neigh = np.stack([_shift(np.where(solid, index, -1), dy, dx, -1) for dy, dx in offsets], axis=0)
    cls = _line_class(index, step_of)
    neigh_cls = np.where(neigh >= 0, _line_class(neigh, step_of), -1)
    same = (neigh_cls == cls[None]).any(0) | (cls == LINE_CLASS)
    fill_idx = index.copy()
    for y, x in zip(*np.nonzero(hole)):
        values = neigh[:, y, x]
        values = values[values >= 0]
        if len(values):
            fill_idx[y, x] = np.bincount(values).argmax()
    index = fill_idx
    candidates = solid & ~same & ~hole
    for y, x in zip(*np.nonzero(candidates)):
        values = neigh[:, y, x]
        values = values[values >= 0]
        if len(values) < 3:
            continue
        counts = np.bincount(values)
        if counts.max() >= 3:
            # 鄰居有三顆以上同色：換成那一色
            index[y, x] = counts.argmax()
        else:
            # 鄰居各不相同：換成鄰居裡顏色最接近自己的那一個，孤立點融回去，不會跳出一個新顏色
            choices = np.unique(values)
            lab = palette_lab[choices]
            index[y, x] = choices[((lab - palette_lab[index[y, x]]) ** 2).sum(-1).argmin()]
        changed += 1
    return index, solid, changed


def count_speckles(index, solid, step_of):
    """量雜點數：不透明、八個鄰居沒有一顆同色的單顆像素；墨線那一類算同一色"""
    offsets = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    neigh = np.stack([_shift(np.where(solid, index, -1), dy, dx, -1) for dy, dx in offsets], axis=0)
    cls = _line_class(index, step_of)
    neigh_cls = np.where(neigh >= 0, _line_class(neigh, step_of), -1)
    same = (neigh_cls == cls[None]).any(0)
    return int((solid & ~same).sum())


ISLAND_MAX = 4


def remove_islands(solid, largest_keep=True, max_size=ISLAND_MAX):
    """八連通分團，不大於 max_size 顆、又不是最大那一團的拿掉：剪影外面飄著的孤立點。回傳 (solid, 拿掉幾顆)"""
    height, width = solid.shape
    label = np.zeros(solid.shape, dtype=np.int32)
    sizes = [0]
    current = 0
    for y0, x0 in zip(*np.nonzero(solid)):
        if label[y0, x0]:
            continue
        current += 1
        stack = [(y0, x0)]
        label[y0, x0] = current
        count = 0
        while stack:
            y, x = stack.pop()
            count += 1
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < height and 0 <= nx < width and solid[ny, nx] and not label[ny, nx]:
                        label[ny, nx] = current
                        stack.append((ny, nx))
        sizes.append(count)
    if current <= 1:
        return solid, 0
    sizes = np.array(sizes)
    biggest = int(sizes[1:].argmax()) + 1
    small = (sizes <= max_size)
    small[0] = False
    small[biggest] = False
    drop = small[label] & solid
    return solid & ~drop, int(drop.sum())


def speckle_classes(index, palette):
    """孤立點分三類：故意的（眼睛高光：暗色包圍的一顆亮點；墨色本身算線不算點）、衣服色塊裡的髒點、其他髒點。
    孤立的定義和 count_speckles 一樣：八個鄰居沒有同一類的"""
    solid = index >= 0
    offsets = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    neigh = np.stack([_shift(np.where(solid, index, -1), dy, dx, -1) for dy, dx in offsets], axis=0)
    cls = _line_class(np.where(solid, index, 0), palette.step_of)
    neigh_cls = np.where(neigh >= 0, _line_class(np.maximum(neigh, 0), palette.step_of), -1)
    lonely = solid & ~(neigh_cls == cls[None]).any(0)
    dark_neighbours = (neigh_cls == LINE_CLASS).sum(0)
    cloth_code = palette.ramp_names.index("cloth_white") if "cloth_white" in palette.ramp_names else -2
    neigh_code = np.where(neigh >= 0, palette.ramp_code[np.maximum(neigh, 0)], -1)
    neigh_step = np.where(neigh >= 0, palette.step_of[np.maximum(neigh, 0)], -1)
    cloth_neighbours = ((neigh_code == cloth_code) & (neigh_step >= 0)).sum(0)
    own_code = np.where(solid, palette.ramp_code[np.maximum(index, 0)], -1)
    intentional = lonely & (dark_neighbours >= 5)
    in_cloth = lonely & ~intentional & (cloth_neighbours >= 5) & (own_code != cloth_code)
    other = lonely & ~intentional & ~in_cloth
    return {"speckle_intentional": int(intentional.sum()), "speckle_in_cloth": int(in_cloth.sum()),
            "speckle_other": int(other.sum())}


def outline(index, solid, palette):
    """剪影最外一圈換成材質的墨色索引。材質是這一顆自己的色階；自己就是墨色或全域深色時，往內兩格找最多的色階"""
    n4 = _neighbours4(solid)
    edge = solid & ~(n4[0] & n4[1] & n4[2] & n4[3])
    code = np.where(solid, palette.ramp_code[index], -1)
    step = np.where(solid, palette.step_of[index], -1)
    material = np.where(step >= 0, code, -1)
    ink_base = palette.ink_base
    result = index.copy()
    for y, x in zip(*np.nonzero(edge)):
        m = material[y, x]
        if m < 0:
            window = material[max(0, y - 2):y + 3, max(0, x - 2):x + 3]
            window = window[window >= 0]
            if not len(window):
                continue
            m = np.bincount(window).argmax()
        result[y, x] = ink_base + m
    return result


def pixelize(work, k, palette, *, draw_outline=True, clean=True):
    """工作畫布 → 目標像素。回傳 (RGBA uint8, 調色盤索引, 統計)。統計量的是鎖調色盤之前和之後的差"""
    small = area_downsample(np.asarray(work), k)
    semi_before = int(((small[..., 3] > 1e-3) & (small[..., 3] < 1 - 1e-3)).sum())
    solid = small[..., 3] >= ALPHA_CUT
    index = np.zeros(solid.shape, dtype=np.int32)
    if solid.any():
        index = lock_to_materials(small[..., :3] * 255.0, solid, palette)
    speckles_before = count_speckles(index, solid, palette.step_of)
    changed = 0
    if clean:
        index, solid, changed = despeckle(index, solid, palette.lab, palette.step_of)
    solid, islands = remove_islands(solid)
    changed += islands
    if draw_outline:
        index = outline(index, solid, palette)
    rgba = np.zeros(solid.shape + (4,), dtype=np.uint8)
    rgba[solid, :3] = palette.colours[index[solid]]
    rgba[solid, 3] = 255
    stats = {"semi_before": semi_before, "semi_after": int(((rgba[..., 3] > 0) & (rgba[..., 3] < 255)).sum()),
             "colours": int(len(np.unique(index[solid]))) if solid.any() else 0,
             "islands_removed": islands, "speckles_before": speckles_before, "speckles_after": count_speckles(index, solid, palette.step_of), "cleaned": changed}
    return rgba, np.where(solid, index, -1), stats
