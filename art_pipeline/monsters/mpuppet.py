# -*- coding: utf-8 -*-
"""怪物的 2D 紙偶圖集：四張視圖直接當方向圖，動作用整張圖的傾斜、浮動、壓縮做，和 mstatic.py 同一套動作設計。
用系統的 python 跑，要有 Pillow。不轉 3D，臉和線條就是視圖上畫的。

視圖：front、left、back、right 四張，白底；s 用 front、w 用 left、n 用 back，sw 和 nw 拿 front 和 back 略縮一點寬度，
e、ne、se 由引擎鏡射。四張的大小照 front 的高度統一縮到 data/monsters.json 的 art.height。

用法：
  python art_pipeline/monsters/mpuppet.py <怪物代號> <視圖資料夾> [--candidate]
輸出到 assets/generated/sprites/monsters/<art.sheet>/，和 mbuild.py 的格式一樣。
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
sys.path.insert(0, os.path.join(HERE, "..", "characters"))
from common import sheet_output  # noqa: E402
from common import cutout  # noqa: E402
import mswing  # noqa: E402

PROJECT_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
SHIP_ROOT = os.path.join(PROJECT_ROOT, "assets", "generated", "sprites", "monsters")
CANDIDATE_ROOT = os.path.join(PROJECT_ROOT, "assets", "generated", "sprites", "placeholder", "monsters")
DIRECTIONS = ["s", "sw", "w", "nw", "n"]
# 每個方向用哪張視圖、寬度縮多少、面向在畫面上的方向（x 往右、y 往下）
VIEW_OF = {"s": ("front", 1.0, (0.0, 1.0)), "sw": ("front", 0.9, (-0.7, 0.7)), "w": ("left", 1.0, (-1.0, 0.0)),
           "nw": ("back", 0.9, (-0.7, -0.7)), "n": ("back", 1.0, (0.0, -1.0))}
ACTIONS = [
    dict(name="idle", frames=4, fps=6, loop=True),
    dict(name="walk", frames=8, fps=12, loop=True),
    dict(name="attack", frames=6, fps=12, loop=False, hit_frame=3),
    dict(name="hit", frames=3, fps=12, loop=False),
    dict(name="die", frames=6, fps=10, loop=False),
]
# 大隻的怪畫格大，135 格會超過 vram_report.gd 的 SHEET_PIXEL_CEILING，改用少幾格的動作表
SHEET_PIXEL_CEILING = 12582912
COMPACT_ACTIONS = [
    dict(name="idle", frames=4, fps=6, loop=True),
    dict(name="walk", frames=6, fps=12, loop=True),
    dict(name="attack", frames=6, fps=12, loop=False, hit_frame=3),
    dict(name="hit", frames=2, fps=12, loop=False),
    dict(name="die", frames=5, fps=10, loop=False),
]
# 走路的樣子由 data/monsters.json 的 art.motion 決定：hop 是彈跳，waddle 是左右搖著走，stomp 是重踏；沒寫就是 hop
MOTION_STYLES = ("hop", "waddle", "stomp")
WORK_SCALE = 2
BOTTOM_MARGIN_PX = 14
# ── 部位：耳朵、角、葉子這些突出的東西自己會動 ──────────────────────────
# 整隻的剪影做一次開運算，比這個半徑細的東西就是突出的部位；半徑是身高的比例
APPENDAGE_OPEN_RATIO = 0.12
# 部位至少要占整隻面積的這個比例，碎屑不算
APPENDAGE_MIN_AREA = 0.003
APPENDAGE_MAX_COUNT = 6
# 部位往身體多拿幾個像素，轉的時候接縫才不會露出來
APPENDAGE_OVERLAP_PX = 3
# 甩動是真的物理：每個部位是一根繞接點轉的擺，接點跟著身體走，身體加速部位就往反方向甩，
# 靠彈簧回到原本的方向、靠阻尼停下來。自然頻率和阻尼比照耳朵、葉子這類軟的東西，
# 參考 Nystrom 的擺錘公式和動畫十二法則的 follow-through：
# 角加速度 = -切向加速度 / 擺長 - ω² × 偏角 - 2ζω × 角速度
# 頻率是擺長等於身高 15% 時的值；擺越短越硬、擺幅越小，ω² 和擺長成反比，和真的擺一樣
APPENDAGE_HZ = 2.8
APPENDAGE_REFERENCE_LEVER = 0.15
APPENDAGE_DAMPING = 0.28
APPENDAGE_MAX_DEG = 35.0
# 模擬的時間步和週期動作先跑幾圈讓擺進入穩態
APPENDAGE_DT = 1.0 / 240.0
APPENDAGE_WARMUP_CYCLES = 3
# 動作曲線是一段一段接的，接點處速度會跳，直接差分出來的加速度是無限大的脈衝，擺會被打到極限來回翻。
# 接點的路徑先用這麼多秒的高斯核抹平再差分，肌肉和肉墊本來就吸掉這種瞬間
APPENDAGE_SMOOTH_S = 0.035


def _wave(t, offset=0.0):
    return math.sin((t + offset) * math.tau)


def _walk(style, t, fx, h):
    """走路一個週期。回傳 (旋轉, sx, sy, dx, dy)"""
    side = 1.0 if fx <= 0 else -1.0
    if style == "waddle":
        # 左右搖著走：一步偏左一步偏右，每一步身體抬一下，肚子跟著晃
        rot = _wave(t) * 10.0 * side
        lift = abs(_wave(t)) * h * 0.07
        wobble = _wave(t * 2.0) * 0.03
        return rot, 1.0 + wobble, 1.0 - wobble, _wave(t) * h * 0.02, -lift
    if style == "stomp":
        # 重踏：一個週期兩步，慢慢抬起、快速落地，落地那一下壓一點
        step = 1.0 if t < 0.5 else -1.0
        p = (t * 2.0) % 1.0
        if p < 0.6:
            lift = math.sin(p / 0.6 * math.pi) * h * 0.05
            squash = 0.0
        else:
            lift = 0.0
            squash = math.sin((p - 0.6) / 0.4 * math.pi) * 0.05
        return step * 4.0 * math.sin(p * math.pi), 1.0 + squash * 0.8, 1.0 - squash, step * h * 0.02 * math.sin(p * math.pi), -lift
    # 彈跳：先蹲下蓄力，彈起來離地，落地壓扁再站直
    if t < 0.25:
        u = t / 0.25
        squash = math.sin(u * math.pi) * 0.14
        return 0.0, 1.0 + squash * 0.7, 1.0 - squash, 0.0, 0.0
    if t < 0.75:
        u = (t - 0.25) / 0.5
        air = math.sin(u * math.pi)
        stretch = math.sin(u * math.pi) * (1.0 - u) * 0.10
        return fx * 8.0 * air * -1.0, 1.0 - stretch * 0.6, 1.0 + stretch, 0.0, -air * h * 0.22
    u = (t - 0.75) / 0.25
    squash = math.sin(u * math.pi) * 0.12
    return 0.0, 1.0 + squash * 0.7, 1.0 - squash, 0.0, 0.0


def motion(action, t, facing, height_px, style="hop"):
    """回傳 (旋轉度數, x 縮放, y 縮放, x 位移, y 位移)，位移是畫格像素，旋轉以腳底為中心。
    數字照 mstatic.poser_for：幅度照身高等比，動作刻意小"""
    fx, fy = facing
    if action == "idle":
        if style == "stomp":
            return _wave(t, 0.25) * 1.2, 1.0, 1.0 + _wave(t, 0.5) * 0.006, 0.0, 0.0
        squash = 1.0 + _wave(t, 0.5) * 0.012
        return _wave(t, 0.25) * 2.0, 1.0 / squash, squash, 0.0, 0.0
    if action == "walk":
        return _walk(style, t, fx, height_px)
    if action == "attack" and style == "stomp":
        # 重擊：先抬起來往後仰，接著往前砸下去，落地壓扁
        if t < 0.4:
            u = t / 0.4
            return -fx * 6.0 * u, 1.0, 1.0 + 0.06 * u, 0.0, -u * height_px * 0.12
        u = (t - 0.4) / 0.6
        drop = math.sin(min(u * 1.6, 1.0) * math.pi / 2.0)
        squash = math.sin(u * math.pi) * 0.09
        return fx * 8.0 * drop, 1.0 + squash, 1.0 - squash, fx * drop * height_px * 0.05, -(1.0 - drop) * height_px * 0.12
    if action == "attack":
        # 三段：蓄力（往後縮、壓扁）、撲（往前衝、拉長）、收（彈回來）。壓扁再拉長就是力道，動畫十二法則的 squash and stretch
        if t < 0.3:
            u = t / 0.3
            push, sx, sy = -0.25 * u, 1.0 + 0.08 * u, 1.0 - 0.12 * u
        elif t < 0.55:
            u = (t - 0.3) / 0.25
            push, sx, sy = -0.25 + 1.25 * u, 1.08 - 0.18 * u, 0.88 + 0.26 * u
        else:
            u = (t - 0.55) / 0.45
            push, sx, sy = 1.0 - u, 0.9 + 0.1 * u, 1.14 - 0.14 * u
        dx, dy = fx * push * height_px * 0.22, fy * push * height_px * 0.07
        if fx == 0.0:
            # 正面背面看不到往前衝，用放大縮小表現：撲向鏡頭變大、背向鏡頭變小
            grow = 1.0 + push * 0.08 * (1.0 if fy > 0 else -0.6)
            return 0.0, sx * grow, sy * grow, 0.0, dy
        return -push * 8.0 * fx, sx, sy, dx, dy
    if action == "hit":
        # 第 0 格就是被打到最深的那一下：往後彈、壓扁，之後兩格彈回來；以前第 0 格是靜止的，看不出被打
        u = 1.0 - t
        recoil = u * u
        return -12.0 * recoil * fx, 1.0 + 0.10 * recoil, 1.0 - 0.12 * recoil, -fx * recoil * height_px * 0.10, 0.0
    if action == "die":
        # 整隻繞腳底倒下去，和玩家角色的死亡一樣一眼看得出來；以前正面是壓成一片薄餅、側面縮到六成，看起來像消失不像死
        # 側面往背後倒（被打飛的方向），正面和背面往畫面左邊倒；只縮一點點，屍體的大小要和活著時差不多
        fall = t * t
        shrink = 1.0 - 0.08 * fall
        direction = -fx if abs(fx) > 0.3 else -1.0
        return 84.0 * fall * direction, shrink, shrink, 0.0, 0.0
    return 0.0, 1.0, 1.0, 0.0, 0.0


def _components(mask):
    """四鄰連通元件，回傳 (標籤陣列, 個數)；有 scipy 用 scipy，沒有就自己掃"""
    try:
        from scipy import ndimage
        labels, count = ndimage.label(mask)
        return labels, int(count)
    except ImportError:
        pass
    labels = np.zeros(mask.shape, dtype=np.int32)
    count = 0
    height, width = mask.shape
    for sy, sx in zip(*np.nonzero(mask)):
        if labels[sy, sx]:
            continue
        count += 1
        stack = [(sy, sx)]
        labels[sy, sx] = count
        while stack:
            y, x = stack.pop()
            for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= ny < height and 0 <= nx < width and mask[ny, nx] and not labels[ny, nx]:
                    labels[ny, nx] = count
                    stack.append((ny, nx))
    return labels, count


def split_parts(figure, keep_down=True):
    """把一張視圖切成身體和突出的部位。回傳 (身體 RGBA, 部位清單)，
    每個部位有 image、offset、pivot 接點、lever 從接點到部位重心的向量，全部是 figure 的像素座標。
    keep_down 是 False 時朝下的部位不算：樹樁王的根、重踏型的腳不該甩"""
    rgba = np.asarray(figure)
    alpha = rgba[..., 3] > 8
    radius = max(2, int(round(figure.height * APPENDAGE_OPEN_RATIO)))
    kernel = 2 * radius + 1
    mask_image = Image.fromarray((alpha * 255).astype(np.uint8))
    opened = np.asarray(mask_image.filter(ImageFilter.MinFilter(kernel)).filter(ImageFilter.MaxFilter(kernel))) > 0
    core = opened & alpha
    labels, count = _components(alpha & ~core)
    total = float(alpha.sum())
    overlap = APPENDAGE_OVERLAP_PX * WORK_SCALE
    candidates = []
    for index in range(1, count + 1):
        member = labels == index
        area = int(member.sum())
        if area < APPENDAGE_MIN_AREA * total:
            continue
        grown = np.asarray(Image.fromarray((member * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3))) > 0
        contact = grown & core
        if not contact.any():
            continue
        cys, cxs = np.nonzero(contact)
        pivot = (float(cxs.mean()), float(cys.mean()))
        pys, pxs = np.nonzero(member)
        lever = (float(pxs.mean()) - pivot[0], float(pys.mean()) - pivot[1])
        if math.hypot(*lever) < 2.0:
            continue
        if not keep_down and lever[1] > 0.0:
            continue
        take = np.asarray(Image.fromarray((member * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(2 * overlap + 1))) > 0
        take &= alpha
        ys, xs = np.nonzero(take)
        x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
        piece = rgba[y0:y1, x0:x1].copy()
        piece[..., 3] = np.where(take[y0:y1, x0:x1], piece[..., 3], 0)
        candidates.append({"area": area, "member": member, "image": Image.fromarray(piece, "RGBA"), "offset": (x0, y0),
                           "pivot": pivot, "lever": lever})
    candidates.sort(key=lambda part: -part["area"])
    parts = candidates[:APPENDAGE_MAX_COUNT]
    body = rgba.copy()
    for part in parts:
        body[..., 3] = np.where(part["member"], 0, body[..., 3])
        del part["member"]
    return Image.fromarray(body, "RGBA"), parts


def _pivot_world(figure_size, pivot, rotation, sx, sy, dx, dy):
    """部位的接點在畫格裡的位置：和 compose 同一套，先繞腳底縮放、再繞腳底轉、再位移。單位是 figure 的像素"""
    fx, fy = figure_size[0] / 2.0, float(figure_size[1])
    lx, ly = (pivot[0] - fx) * sx, (pivot[1] - fy) * sy
    cos, sin = math.cos(math.radians(rotation)), math.sin(math.radians(rotation))
    return (lx * cos - ly * sin + dx * WORK_SCALE, lx * sin + ly * cos + dy * WORK_SCALE)


def simulate_parts(parts, figure_size, action, frames, fps, loop, facing, height_px, style):
    """每個部位跑一次擺的模擬，回傳 [每一格的角度清單]，角度是繞接點轉幾度。
    接點的路徑由身體的動作算出來，部位只是被接點拖著走的擺"""
    if not parts:
        return [[] for _ in range(frames)]
    duration = frames / float(fps)
    cycles = APPENDAGE_WARMUP_CYCLES if loop else 1
    total = duration * cycles
    steps = int(math.ceil(total / APPENDAGE_DT))
    dt = total / steps
    reference_lever = max(8.0, APPENDAGE_REFERENCE_LEVER * figure_size[1])
    # 接點路徑先算好：每一步的位置，抹平之後再差分出加速度
    sigma = APPENDAGE_SMOOTH_S / dt
    radius = int(math.ceil(sigma * 3.0))
    kernel = np.exp(-0.5 * (np.arange(-radius, radius + 1) / sigma) ** 2)
    kernel /= kernel.sum()
    paths = []
    for part in parts:
        xs, ys = [], []
        for step in range(steps + 1):
            time = step * dt
            u = (time / duration) % 1.0 if loop else min(1.0, time / duration)
            rotation, sx, sy, dx, dy = motion(action, u, facing, height_px, style)
            px, py = _pivot_world(figure_size, part["pivot"], rotation, sx, sy, dx, dy)
            xs.append(px)
            ys.append(py)
        mode = "wrap" if loop else "edge"
        xs = np.convolve(np.pad(np.asarray(xs), radius, mode=mode), kernel, mode="valid")
        ys = np.convolve(np.pad(np.asarray(ys), radius, mode=mode), kernel, mode="valid")
        paths.append(list(zip(xs.tolist(), ys.tolist())))
    sample_times = [(frame / float(frames) if loop else frame / float(max(1, frames - 1))) * duration + (cycles - 1) * duration
                    for frame in range(frames)]
    angles_per_part = []
    for part, path in zip(parts, paths):
        lever = part["lever"]
        length = max(8.0, math.hypot(*lever))
        omega = 2.0 * math.pi * APPENDAGE_HZ * math.sqrt(reference_lever / length)
        # 擺的切線方向：擺長方向轉 90 度；沿這個方向的加速度才會把擺甩開
        tangent = (-lever[1] / length, lever[0] / length)
        theta, omega_t = 0.0, 0.0
        samples = []
        next_sample = 0
        for step in range(1, steps):
            before, here, after = path[step - 1], path[step], path[step + 1]
            ax = (after[0] - 2.0 * here[0] + before[0]) / (dt * dt)
            ay = (after[1] - 2.0 * here[1] + before[1]) / (dt * dt)
            forcing = -(ax * tangent[0] + ay * tangent[1]) / length
            accel = forcing - omega * omega * theta - 2.0 * APPENDAGE_DAMPING * omega * omega_t
            omega_t += accel * dt
            theta += omega_t * dt
            time = step * dt
            while next_sample < frames and sample_times[next_sample] <= time + dt * 0.5:
                samples.append(theta)
                next_sample += 1
        while len(samples) < frames:
            samples.append(theta)
        degrees = []
        for frame, value in enumerate(samples):
            angle = max(-APPENDAGE_MAX_DEG, min(APPENDAGE_MAX_DEG, math.degrees(value)))
            if action == "die":
                # 死掉部位垂下去：往正下方轉，轉 t 平方的比例，蓋過擺的角度
                u = frame / float(max(1, frames - 1))
                droop = math.degrees(math.atan2(1.0, 0.0) - math.atan2(lever[1], lever[0]))
                droop = (droop + 180.0) % 360.0 - 180.0
                angle = angle * (1.0 - u) + max(-APPENDAGE_MAX_DEG * 1.5, min(APPENDAGE_MAX_DEG * 1.5, droop)) * u * u
            degrees.append(angle)
        angles_per_part.append(degrees)
    return [[angles_per_part[index][frame] for index in range(len(parts))] for frame in range(frames)]


def assemble(body, parts, angles):
    """把部位照角度繞著各自的接點轉回身體上，回傳整隻的 RGBA"""
    canvas = body.copy()
    for part, angle in zip(parts, angles):
        if abs(angle) < 0.05:
            canvas.alpha_composite(part["image"], part["offset"])
            continue
        # 接點在部位圖裡的位置，繞它轉；expand 之後圖變大、左上角會跑，算接點轉完落在哪再放回原地
        px, py = part["pivot"][0] - part["offset"][0], part["pivot"][1] - part["offset"][1]
        source = part["image"]
        rotated = source.rotate(-angle, resample=Image.BICUBIC, center=(px, py), expand=True)
        cx, cy = source.width / 2.0, source.height / 2.0
        theta = math.radians(-angle)
        rx = cx + (px - cx) * math.cos(theta) + (py - cy) * math.sin(theta)
        ry = cy - (px - cx) * math.sin(theta) + (py - cy) * math.cos(theta)
        rx += (rotated.width - source.width) / 2.0
        ry += (rotated.height - source.height) / 2.0
        canvas.alpha_composite(rotated, (int(round(part["pivot"][0] - rx)), int(round(part["pivot"][1] - ry))))
    return canvas


def _grow(mask, pixels):
    if pixels <= 0:
        return mask
    image = Image.fromarray((mask * 255).astype(np.uint8))
    return np.asarray(image.filter(ImageFilter.MaxFilter(2 * pixels + 1))) > 0


def load_view(path, target_h, width_scale, scale=None):
    """讀一張視圖去背縮放。scale 沒給時整隻縮到 target_h 高；五方向圖要五張同一個比例，由呼叫的人照正面算好給進來"""
    image = Image.open(path).convert("RGB")
    figure = cutout.trim(cut_on_white(image) if path.lower().endswith(".jpg") else cutout.cut(image))
    if scale is None:
        scale = target_h / float(figure.height)
    size = (max(1, int(round(figure.width * scale * width_scale))), max(1, int(round(figure.height * scale))))
    return figure.resize(size, Image.LANCZOS)


# 白底 jpg 的去背：背景是 250 上下的白，壓縮雜訊讓它在 238 到 255 之間跳
BACKGROUND_MIN = 236
BACKGROUND_SPREAD = 14
# 描邊外側那圈照「墨線和白底混色」反算透明度和顏色，墨線的亮度取這個值；比它暗的整個不透明
INK_LUMA = 60.0
PAPER_LUMA = 250.0
EDGE_RING_PX = 4
# 被圍起來的白色區塊多大、多白才算背景
ENCLOSED_MIN_AREA = 40
ENCLOSED_MIN_WHITE = 242.0


def cut_on_white(image):
    """五方向圖是白底 jpg，沒有透明。從四邊往內淹水找背景，背景旁邊那一圈照混色公式把白反算掉：
    看到的顏色 = 墨色 × α + 白 × (1 - α)，所以 α = (白 - 亮度) / (白 - 墨)、墨色 = (看到的 - 白 × (1 - α)) / α。
    這樣描邊外面不會留一圈半透明的白或灰，cutout.cut 是把那圈直接調淡，顏色還是灰的"""
    rgb = np.asarray(image.convert("RGB")).astype(np.float64)
    light = (rgb.min(2) >= BACKGROUND_MIN) & (rgb.max(2) - rgb.min(2) <= BACKGROUND_SPREAD)
    seeds = np.zeros(light.shape, dtype=bool)
    seeds[0, :], seeds[-1, :], seeds[:, 0], seeds[:, -1] = light[0, :], light[-1, :], light[:, 0], light[:, -1]
    labels, count = _components(light)
    edge_labels = set(np.unique(labels[seeds]).tolist()) - {0}
    # 被圍起來的白也是背景：小樹苗背面帽簷、手、葉子中間夾著一塊 340 像素的白底。眼睛的反光這種白小得多，也不是紙的那種白
    keep = set(edge_labels)
    if count:
        areas = np.bincount(labels.ravel(), minlength=count + 1)
        whiteness = np.bincount(labels.ravel(), weights=rgb.min(2).ravel(), minlength=count + 1) / np.maximum(areas, 1)
        for label in range(1, count + 1):
            if areas[label] >= ENCLOSED_MIN_AREA and whiteness[label] >= ENCLOSED_MIN_WHITE:
                keep.add(label)
    edge_labels = keep
    background = np.isin(labels, list(edge_labels)) if edge_labels else np.zeros(light.shape, dtype=bool)
    ring = _grow(background, EDGE_RING_PX) & ~background
    luma = rgb @ np.array([0.299, 0.587, 0.114])
    alpha = np.where(background, 0.0, 1.0)
    mix = np.clip((PAPER_LUMA - luma) / (PAPER_LUMA - INK_LUMA), 0.0, 1.0)
    alpha = np.where(ring, np.minimum(alpha, mix), alpha)
    safe = np.maximum(alpha, 1e-3)[..., None]
    unmixed = np.clip((rgb - PAPER_LUMA * (1.0 - safe)) / safe, 0.0, 255.0)
    rgb = np.where((ring & (alpha < 1.0))[..., None], unmixed, rgb)
    # 太淡的就是背景的雜訊，不留
    alpha = np.where(alpha < 0.08, 0.0, alpha)
    return Image.fromarray(np.dstack([rgb, alpha * 255.0]).round().astype(np.uint8), "RGBA")


def view_paths(views):
    """視圖資料夾裡有 s、sw、w、nw、n 五張就一個方向一張，寬度不壓；沒有就用舊的 front、left、back 四視圖，斜向拿正背面壓窄頂替。
    回傳 {方向: (檔案路徑, 寬度倍率)} 和是不是五方向"""
    found = {}
    for direction in DIRECTIONS:
        for extension in (".png", ".jpg"):
            path = os.path.join(views, direction + extension)
            if os.path.exists(path):
                found[direction] = (path, 1.0)
                break
    if len(found) == len(DIRECTIONS):
        return found, True
    return {direction: (os.path.join(views, view + ".png"), width_scale)
            for direction, (view, width_scale, _) in VIEW_OF.items()}, False


def compose(figure, frame_px, anchor, rotation, sx, sy, dx, dy, _fitted=False, layers=(), points=()):
    """以腳底為中心：先縮放再旋轉再位移。
    拉長或放大後比畫格的頭頂空間還高就整隻等比縮到剛好塞得下，腳留在地上；不然頭頂會被畫格切成一條平的。
    先畫到兩倍大的畫布上再量外框挪回畫格裡：倒下去的身體會轉到畫格外面，直接畫在畫格大小的畫布上會先被切掉再挪回來，
    死亡的最後兩格就剩半隻（2026-09-24 量到的）

    layers 是和 figure 同大小的其他圖，照 figure 量出來的同一個擺法一起放進畫格；points 是 figure 上的點。
    有給其中一個就回傳 (畫格, [每一層的畫格], [每個點在畫格裡的位置], (實際的 x 縮放, 實際的 y 縮放))，
    執行期甩動要知道部位的接點每一格落在哪裡"""
    W = frame_px * WORK_SCALE
    big = W * 2
    pad = W // 2
    size = (max(1, int(round(figure.width * sx))), max(1, int(round(figure.height * sy))))
    scaled = figure.resize(size, Image.LANCZOS)
    pivot_x, pivot_y = anchor[0] * WORK_SCALE + dx * WORK_SCALE, anchor[1] * WORK_SCALE + dy * WORK_SCALE
    # 圖的腳底中點要落在 pivot，然後繞 pivot 轉；大畫布的座標比畫格多 pad
    cos, sin = math.cos(math.radians(rotation)), math.sin(math.radians(rotation))
    fx, fy = scaled.width / 2.0, float(scaled.height)
    a, b = cos, sin
    d, e = -sin, cos
    c = fx - (a * (pivot_x + pad) + b * (pivot_y + pad))
    f = fy - (d * (pivot_x + pad) + e * (pivot_y + pad))
    moved = scaled.transform((big, big), Image.AFFINE, (a, b, c, d, e, f), resample=Image.BICUBIC)
    alpha = np.asarray(moved)[..., 3]
    ys, xs = np.nonzero(alpha > 8)
    canvas = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    detailed = bool(layers) or bool(points)
    if not len(ys):
        empty = canvas.resize((frame_px, frame_px), Image.LANCZOS)
        return (empty, [empty.copy() for _ in layers], [(0.0, 0.0) for _ in points], (sx, sy)) if detailed else empty
    # 量最低點和左右邊，整張往上、往中間挪回畫格裡，腳底貼著地
    floor = int(round(anchor[1] * WORK_SCALE)) + pad
    margin = 2 * WORK_SCALE
    room = floor - pad - margin
    tall = int(ys.max()) - int(ys.min()) + 1
    if tall > room and not _fitted:
        fit = room / float(tall)
        return compose(figure, frame_px, anchor, rotation, sx * fit, sy * fit, dx, dy, _fitted=True, layers=layers, points=points)
    shift_x, shift_y = 0, 0
    # 頭頂出畫格就往下挪，腳底比地面低就往上挪；兩個都要時腳底貼地優先，上面已經確認整隻塞得下
    if ys.min() < pad + margin:
        shift_y = pad + margin - int(ys.min())
    if ys.max() + shift_y > floor:
        shift_y = floor - int(ys.max())
    if xs.min() + shift_x < pad + margin:
        shift_x = pad + margin - int(xs.min())
    elif xs.max() + shift_x > pad + W - 1 - margin:
        shift_x = pad + W - 1 - margin - int(xs.max())
    canvas.alpha_composite(moved, (shift_x - pad, shift_y - pad))
    cell = canvas.resize((frame_px, frame_px), Image.LANCZOS)
    if not detailed:
        return cell
    layer_cells = []
    for layer in layers:
        layer_moved = layer.resize(size, Image.LANCZOS).transform((big, big), Image.AFFINE, (a, b, c, d, e, f),
                                                                 resample=Image.BICUBIC)
        layer_canvas = Image.new("RGBA", (W, W), (0, 0, 0, 0))
        layer_canvas.alpha_composite(layer_moved, (shift_x - pad, shift_y - pad))
        layer_cells.append(layer_canvas.resize((frame_px, frame_px), Image.LANCZOS))
    # 點的正向換算：上面的仿射是畫格找原圖，這裡反過來，原圖的點縮放、繞腳底轉、挪回畫格、縮回畫格大小
    ratio_x, ratio_y = size[0] / float(figure.width), size[1] / float(figure.height)
    placed = []
    for px, py in points:
        du, dv = px * ratio_x - fx, py * ratio_y - fy
        big_x = pivot_x + pad + cos * du - sin * dv
        big_y = pivot_y + pad + sin * du + cos * dv
        placed.append(((big_x + shift_x - pad) / WORK_SCALE, (big_y + shift_y - pad) / WORK_SCALE))
    return cell, layer_cells, placed, (ratio_x, ratio_y)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("monster")
    parser.add_argument("views")
    parser.add_argument("--candidate", action="store_true")
    parser.add_argument("--swing", action="store_true",
                        help="部位不畫進動作格，改成遊戲裡照真正的加速度甩；要配合 src/world/actors/part_swing.gd")
    args = parser.parse_args()
    with open(os.path.join(PROJECT_ROOT, "data", "monsters.json"), encoding="utf-8") as handle:
        data = json.load(handle)[args.monster]
    art = data["art"]
    style = str(art.get("motion", "hop"))
    if style not in MOTION_STYLES:
        raise SystemExit("art.motion 只能是 %s，現在是 %s" % (", ".join(MOTION_STYLES), style))
    frame_px = int(art["frame_px"])
    view_m = float(art["view_m"])
    height_m = float(art["height"])
    ppm = frame_px / view_m
    height_px = height_m * ppm
    anchor = (frame_px / 2.0, float(frame_px - BOTTOM_MARGIN_PX))
    figures, bodies = {}, {}
    paths, five = view_paths(args.views)
    common_scale = None
    if five:
        # 五張是同一個比例畫的，側面的芽比正面高，一張一張各自縮到同高會把側面整隻縮小；全部照正面的比例縮
        front = cutout.trim(cut_on_white(Image.open(paths["s"][0]).convert("RGB"))
                                  if paths["s"][0].lower().endswith(".jpg") else cutout.cut(Image.open(paths["s"][0])))
        common_scale = height_px * WORK_SCALE / float(front.height)
        print("五方向圖，全部照正面的比例縮")
    swing = None
    if args.swing:
        spec = mswing.load_spec(args.views)
        if not five or spec is None:
            raise SystemExit("--swing 要五方向圖和 %s，見 art_pipeline/monsters/mswing.py" % mswing.SPEC_FILE)
        swing = {"parts": {}, "bodies": {}}
    for direction in DIRECTIONS:
        path, width_scale = paths[direction]
        if swing:
            figures[direction], swing["bodies"][direction], swing["parts"][direction] = mswing.prepare(
                path, spec[direction], common_scale, cut_on_white)
            bodies[direction] = (swing["bodies"][direction], [])
            print("%s：%d 個部位執行期甩動" % (direction, len(swing["parts"][direction])))
            continue
        figures[direction] = load_view(path, height_px * WORK_SCALE, width_scale, common_scale)
        bodies[direction] = split_parts(figures[direction], style != "stomp")
        print("%s：%d 個會動的部位" % (direction, len(bodies[direction][1])))
    cells, actions = [], {}
    swing_frames = {}
    action_specs = ACTIONS
    if frame_px * frame_px * sum(spec["frames"] for spec in ACTIONS) * len(DIRECTIONS) > SHEET_PIXEL_CEILING:
        action_specs = COMPACT_ACTIONS
        print("畫格 %d 太大，135 格會超過圖集上限，改用 %d 格的動作表" % (frame_px, sum(s["frames"] for s in COMPACT_ACTIONS) * len(DIRECTIONS)))
    for spec_action in action_specs:
        entry = {"frames": spec_action["frames"], "fps": spec_action["fps"], "loop": spec_action["loop"], "start": len(cells)}
        if "hit_frame" in spec_action:
            entry["hit_frame"] = spec_action["hit_frame"]
        actions[spec_action["name"]] = entry
        swing_frames[spec_action["name"]] = []
        for direction in DIRECTIONS:
            facing = VIEW_OF[direction][2]
            body, parts = bodies[direction]
            if swing:
                parts_here = swing["parts"][direction]
                pivots = [part["pivot"] for part in parts_here]
                rows_here = []
                for frame in range(spec_action["frames"]):
                    t = frame / float(spec_action["frames"]) if spec_action["loop"] else frame / float(max(1, spec_action["frames"] - 1))
                    pose = motion(spec_action["name"], t, facing, height_px, style)
                    # 身體這一格：部位已經拿掉、底下補好了，整隻描邊，部位另外疊
                    cell, _, placed, scale = compose(body, frame_px, anchor, *pose, points=pivots)
                    cells.append(cutout.draw_outline(cell))
                    row = [round(pose[0], 3), round(scale[0], 4), round(scale[1], 4)]
                    for x, y in placed:
                        row += [round(x, 2), round(y, 2)]
                    rows_here.append(row)
                swing_frames[spec_action["name"]].append(rows_here)
                continue
            swings = simulate_parts(parts, figures[direction].size, spec_action["name"], spec_action["frames"], spec_action["fps"], spec_action["loop"],
                                    facing, height_px, style)
            for frame in range(spec_action["frames"]):
                t = frame / float(spec_action["frames"]) if spec_action["loop"] else frame / float(max(1, spec_action["frames"] - 1))
                rotation, sx, sy, dx, dy = motion(spec_action["name"], t, facing, height_px, style)
                figure = assemble(body, parts, swings[frame]) if parts else figures[direction]
                cell = compose(figure, frame_px, anchor, rotation, sx, sy, dx, dy)
                cells.append(cutout.draw_outline(cell))
        print("%s：%d 格 × %d 方向" % (spec_action["name"], spec_action["frames"], len(DIRECTIONS)))
    columns = 8
    pad = cutout.OUTLINE_PX
    swing_meta, placements = None, []
    if swing:
        swing_meta, placements, reserved = build_swing_block(swing, frame_px, columns, len(cells), height_px)
        actions["swing"] = reserved
        total = reserved["start"] + reserved["frames"] * len(DIRECTIONS)
    else:
        total = len(cells)
    rows = -(-total // columns)
    sheet = Image.new("RGBA", (columns * frame_px, rows * frame_px), (0, 0, 0, 0))
    for index, cell in enumerate(cells):
        trimmed = cell.crop((pad, pad, pad + frame_px, pad + frame_px))
        sheet.alpha_composite(trimmed, (index % columns * frame_px, index // columns * frame_px))
    for image, (x, y) in placements:
        sheet.alpha_composite(image, (x, y))
    out_dir = os.path.join(CANDIDATE_ROOT if args.candidate else SHIP_ROOT, art["sheet"])
    os.makedirs(out_dir, exist_ok=True)
    sheet_path = os.path.join(out_dir, "sheet.png")
    sheet.save(sheet_path)
    # 怪物圖集和 mbuild 一樣走 VRAM 壓縮那組匯入參數，test_shipped_sheets_match_the_spec 守著
    sheet_output.write_import(sheet_path, PROJECT_ROOT)
    meta = {"frame_size": [frame_px, frame_px], "columns": columns, "pixels_per_meter": ppm, "anchor": list(anchor),
            "directions": DIRECTIONS, "layout": "packed", "actions": actions, "motion": style,
            "source": {"pipeline": "art_pipeline/monsters/mpuppet.py",
                       "views": os.path.relpath(os.path.abspath(args.views), PROJECT_ROOT).replace(os.sep, "/")}}
    if swing_meta:
        swing_meta["frames"] = swing_frames
        meta["swing"] = swing_meta
    with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as handle:
        json.dump(meta, handle, ensure_ascii=False, indent=1 if swing_meta else 2)
        handle.write("\n")
    print("%d 格、%s -> %s" % (len(cells), sheet.size, out_dir))


def build_swing_block(swing, frame_px, columns, used_cells, height_px):
    """每個方向每個部位轉好一排角度，塞進圖集最後面。回傳 (meta 的 swing 區塊, [(小圖, 貼到圖集的位置)], 保留格的動作項)。
    保留格用一個叫 swing 的動作佔住，圖集的長寬檢查和緊密排的格號才對得上；角色不會播這個動作"""
    turn_angles = mswing.angles()
    slots, mirror, slot_count = mswing.slots_for(swing["parts"])
    images, owners = [], []
    for direction in DIRECTIONS:
        for number, part in enumerate(swing["parts"][direction]):
            for turn, (image, pivot) in enumerate(mswing.variants(part, swing["bodies"][direction], turn_angles, WORK_SCALE,
                                                                  cutout.draw_outline, cutout.OUTLINE_PX)):
                images.append(image)
                owners.append((direction, number, pivot))
    start = -(-used_cells // columns) * columns
    spots, cells_needed = mswing.pack(images, frame_px, columns, start)
    reserved_frames = -(-cells_needed // len(DIRECTIONS))
    placements = [(images[index], spots[index]) for index in range(len(images))]
    parts_meta = []
    for direction in DIRECTIONS:
        entries = []
        for number, part in enumerate(swing["parts"][direction]):
            rects = []
            for index, owner in enumerate(owners):
                if owner[0] == direction and owner[1] == number:
                    x, y = spots[index]
                    rects.append([x, y, images[index].width, images[index].height, round(owner[2][0], 2), round(owner[2][1], 2)])
            lever = (part["lever"][0] / WORK_SCALE, part["lever"][1] / WORK_SCALE)
            entries.append({"slot": slots[direction][number], "name": part["name"], "layer": part["layer"],
                            "lever": [round(lever[0], 2), round(lever[1], 2)], "variants": rects})
        parts_meta.append(entries)
    params = dict(mswing.PARAMS)
    params["reference_lever_px"] = round(max(4.0, params["reference_ratio"] * height_px), 2)
    block = {"version": 2, "angles": turn_angles, "slots": slot_count, "mirror": mirror,
             "facing_x": [VIEW_OF[direction][2][0] for direction in DIRECTIONS], "params": params, "parts": parts_meta}
    print("甩動部位：%d 張轉好的小圖，用掉 %d 格，保留 %d 格" % (len(images), cells_needed, reserved_frames * len(DIRECTIONS)))
    return block, placements, {"frames": reserved_frames, "fps": 1, "loop": False, "start": start}


if __name__ == "__main__":
    main()
