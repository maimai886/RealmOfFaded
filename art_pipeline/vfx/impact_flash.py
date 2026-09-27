"""
衝擊閃光的八格序列圖，輸出 assets/vfx/impact_flash.png，src/effects/impact_flash.gd 播
做法和數字在暫存的做法第 2 版第 7 節，第 2 版照 Nora、Felix 對送審第 1 版的意見改：
- 參考 RO 的命中光 EF_HIT2：光絲成簇、一開始寬而短、邊拉長邊變細、各自錯開消失；
  roBrowserLegacy 的 EffectTable.js 和重製版 new_armscannon 只看了做法和數字，沒有拿任何一張圖
- 白芯只在前四格：中心幾個像素滿亮往外指數衰減，外緣幾根短刺成不規則星形，每一格輪廓不同，不是平平的一塊
- 光絲是紡錘形：最寬處在離根部三成左右，末端削到一個像素；中線用主色、兩側用邊色
- 光絲各自活 200 到 330 毫秒，主導的兩三條活最久；第 3 格起從根部斷開，只留外段的碎片越來越細越淡
- 柔光暈只在前兩格，第 3 格歸零；深邊在光暈外面，和光不重疊
- 整張圖的縮放從頭到尾固定，不做放大淡出
通道：R 光的亮度、G 白芯、B 深邊、A 主色的比重；顏色全部在著色器上
每格 256 像素對 2.4 公尺，八格橫排 2048×256；內容半徑不超過 120 像素，相鄰兩格的內容至少空 16 像素
每一格的時間：前四格各 33 毫秒，後四格各 50 毫秒，全長 333 毫秒，和 src/effects/impact_flash.gd 的 FRAME_START_MS 一樣
用法：python art_pipeline/vfx/impact_flash.py，只需要 numpy 和 Pillow；檢查不過不寫檔
"""
import math
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "assets", "vfx", "impact_flash.png")

CELL = 256
FRAMES = 8
CORE_FRAMES = 4
CENTER = CELL / 2.0
## 一格 2.4 公尺，每公尺約 107 像素；52 公尺 1080p 下一個貼圖像素約 0.74 個螢幕像素
PX_PER_M = CELL / 2.4
SCREEN_PER_TEXEL = 79.0 / PX_PER_M
## 內容最遠只到這個半徑，著色器在 0.47 以外不取樣
CONTENT_RADIUS = 120.0
## 最長的光絲伸到離中心幾像素：隨機放大一成時 52 公尺 1080p 下 94 像素
LONGEST_REACH = 116.0
## 光絲從這個半徑長出來，埋在白芯裡
ROOT_RADIUS = 6.0
## 每一格開始和中間的時間，毫秒；光絲照中間的時間決定長相
FRAME_START_MS = [0, 33, 67, 100, 133, 183, 233, 283]
FRAME_END_MS = 333
FRAME_MID_MS = [(a + b) / 2.0 for a, b in zip(FRAME_START_MS, FRAME_START_MS[1:] + [FRAME_END_MS])]
## 光絲長到滿長要多久；第 1 格約六成
GROW_MS = 33.0
FIRST_REACH = 0.55
## 光絲從這個時間起斷開成碎片
BREAK_MS = 83.0
## 光絲最寬處：第 1 格最長那條 15 像素、最短那條約 11；第 2 格縮成七成二
WIDTH_FIRST_MAX = 13.5
WIDTH_FIRST_MIN = 10.0
WIDTH_SECOND_RATIO = 0.72
## 碎片一開始 3.5 像素寬、亮度一半，到死掉時剩 1.4 像素、亮度兩成
FRAGMENT_WIDTH = 3.5
FRAGMENT_WIDTH_END = 1.4
FRAGMENT_LIGHT = 0.42
FRAGMENT_LIGHT_END = 0.2
## 白芯每一格：中心滿亮的半徑、往外衰減的長度、亮度；第 4 格以後沒有白芯
CORE_PLATEAU = [3.5, 3.0, 2.0, 1.0]
CORE_FALLOFF = [6.0, 5.0, 3.5, 3.0]
CORE_PEAK = [1.0, 1.0, 1.0, 0.8]
## 白芯外緣的短刺：每格 3 到 5 根，長 10 到 18 像素
CORE_SPIKES = [(4, 16.0), (5, 14.0), (3, 11.0), (3, 8.0)]
## 柔光暈：半徑 0.35 公尺，第 1 格滿、第 2 格剩四成五、第 3 格歸零；亮度由著色器的 HALO_GAIN 調
HALO_RADIUS = 0.35 * PX_PER_M
HALO_FRAMES = [1.0, 0.45, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
HALO_PEAK = 0.35
## 深邊：只在光外面，光的亮度 0.1 以下才有；高斯柔邊寬度，像素
RIM_SIGMA = 4.0
RIM_ROOT_PART = 0.4
## 深邊逐格的透明度，著色器 impact_flash.gdshader 的 RIM_ALPHA 要一樣
RIM_ALPHA = [0.6, 0.35, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0]
## 超取樣倍數，畫完再縮回來，光絲的邊才平滑
SS = 4
SEED = 20260927


def _rng():
    return np.random.default_rng(SEED)


def streak_plan(rng):
    """決定這一組光絲：角度成簇、長度差很多、最長的兩三條主導也活最久、沒有兩條一樣長"""
    count = 9
    # 三簇，簇裡相鄰兩條隔 25 度左右，寬的光絲才分得開；簇和簇之間的空隙大於平均間隔的兩倍
    cluster_centers = [rng.uniform(0, 360)]
    cluster_centers.append(cluster_centers[0] + rng.uniform(150, 152))
    cluster_centers.append(cluster_centers[0] + rng.uniform(275, 277))
    sizes = [4, 3, 2]
    angles = []
    for center, size in zip(cluster_centers, sizes):
        for i in range(size):
            offset = (i - (size - 1) / 2.0) * 25.0 + rng.uniform(-2.5, 2.5)
            angles.append((center + offset) % 360.0)
    angles = sorted(angles)[:count]
    reach_max = LONGEST_REACH - ROOT_RADIUS
    fractions = [1.0, 0.88] + list(np.linspace(0.64, 0.31, count - 2) * rng.uniform(0.98, 1.02, size=count - 2))
    # 活多久照長短排：最長的三條 330、320、300 毫秒，其他 200 到 280
    order_by_length = np.argsort(fractions)[::-1]
    lives = np.zeros(count)
    for rank, index in enumerate(order_by_length):
        lives[index] = [330.0, 320.0, 300.0][rank] if rank < 3 else 280.0 - (rank - 3) * (80.0 / (count - 4))
    order = rng.permutation(count)
    plan = []
    for slot, index in enumerate(order):
        fraction = fractions[index]
        phases = rng.uniform(0, math.tau, size=3)
        freqs = rng.uniform(1.2, 3.4, size=3)
        plan.append({
            "angle": angles[slot],
            "length": reach_max * fraction,
            "width": WIDTH_FIRST_MIN + (WIDTH_FIRST_MAX - WIDTH_FIRST_MIN) * (fraction - 0.31) / 0.69,
            "peak_at": rng.uniform(0.27, 0.33),
            "life": float(lives[index]),
            "gaps": sorted(rng.uniform(0.55, 0.9, size=2)),
            "wobble": (phases, freqs),
        })
    return plan


def core_shapes(rng):
    """前四格白芯各自的輪廓：橢圓的方向和長短、短刺的角度和長度都不一樣"""
    shapes = []
    for count, spike_len in CORE_SPIKES:
        shapes.append({
            "tilt": rng.uniform(0, 180),
            "aspect": rng.uniform(1.15, 1.3),
            "spikes": [(rng.uniform(0, 360), spike_len * rng.uniform(0.7, 1.0)) for _ in range(count)],
        })
    return shapes


def _grid(size):
    ys, xs = np.mgrid[0:size, 0:size].astype(np.float64)
    return xs, ys


def _streak_width(t, peak_at, widest):
    """紡錘形：根部四成五寬，到 peak_at 最寬，再直線收到末端一個像素"""
    rising = 0.45 * widest + (widest - 0.45 * widest) * np.clip(t / peak_at, 0.0, 1.0)
    # 過了最寬處往末端收，越接近末端收得越快，末端一個像素
    u = np.clip((t - peak_at) / (1.0 - peak_at), 0.0, 1.0)
    falling = 1.0 + (widest - 1.0) * (1.0 - u) ** 1.7
    return np.where(t < peak_at, rising, falling)


def render_frame(frame, plan, cores, ss=SS):
    size = CELL * ss
    xs, ys = _grid(size)
    cx = cy = CENTER * ss
    dx = (xs + 0.5 - cx) / ss
    dy = (ys + 0.5 - cy) / ss
    radius = np.hypot(dx, dy)
    theta = np.degrees(np.arctan2(dy, dx)) % 360.0
    now = FRAME_MID_MS[frame]
    started = FRAME_START_MS[frame]
    light = np.zeros_like(radius)
    main_weight = np.zeros_like(radius)
    rim_src = np.zeros_like(radius)
    reach = FIRST_REACH + (1.0 - FIRST_REACH) * min(1.0, started / GROW_MS)
    for streak in plan:
        if now >= streak["life"]:
            continue
        length = streak["length"] * reach
        a = math.radians(streak["angle"])
        ux, uy = math.cos(a), math.sin(a)
        along = dx * ux + dy * uy - ROOT_RADIUS
        across = np.abs(-dx * uy + dy * ux)
        t = along / max(length, 1e-6)
        inside = (t >= 0.0) & (t <= 1.0)
        phases, freqs = streak["wobble"]
        mod = 1.0 + 0.3 * sum(np.sin(math.tau * f * t + p) for p, f in zip(phases, freqs)) / 1.6
        falloff = 1.0 - 0.25 * np.clip(t, 0, 1)
        segment = np.ones_like(t)
        brightness = 1.0
        if now < BREAK_MS:
            widest = streak["width"] * (1.0 if frame == 0 else WIDTH_SECOND_RATIO)
            width = _streak_width(t, streak["peak_at"], widest)
        else:
            # 碎片：根部先斷，越到後面斷得越多，外段再切出一兩個缺口；越來越細越淡
            age = (now - BREAK_MS) / max(streak["life"] - BREAK_MS, 1.0)
            gone = 0.3 + 0.55 * age
            segment = (t > gone).astype(np.float64)
            for gap in streak["gaps"]:
                if gap > gone:
                    segment *= (np.abs(t - gap) > 0.045).astype(np.float64)
            frag = FRAGMENT_WIDTH + (FRAGMENT_WIDTH_END - FRAGMENT_WIDTH) * age
            width = frag + (1.0 - frag) * np.clip((t - 0.7) / 0.3, 0.0, 1.0)
            brightness = FRAGMENT_LIGHT + (FRAGMENT_LIGHT_END - FRAGMENT_LIGHT) * age
        # 斷面：中間一半是滿的，外面一半往外收掉，看起來是光不是一片貼紙
        half = width * 0.5
        edge = np.clip((half + 0.3 - across) / np.maximum(half * 0.5, 0.6), 0.0, 1.0)
        tip_taper = np.clip((1.0 - t) / 0.06, 0.0, 1.0)
        value = np.where(inside, edge * tip_taper * mod * falloff * segment * brightness, 0.0)
        light = np.maximum(light, value)
        # 熱芯：中線一兩個像素用主色，兩側用邊色
        centre = np.clip((1.5 - across) / 0.75, 0.0, 1.0)
        main_weight = np.maximum(main_weight, np.where(inside & (value > 0.02), centre, 0.0))
        if now < BREAK_MS:
            root_part = inside & (t <= RIM_ROOT_PART)
            rim_src = np.maximum(rim_src, np.where(root_part, edge, 0.0))
    light = np.clip(light, 0.0, 1.0)
    core = np.zeros_like(radius)
    if frame < CORE_FRAMES:
        shape = cores[frame]
        tilt = math.radians(shape["tilt"])
        ex = (dx * math.cos(tilt) + dy * math.sin(tilt))
        ey = (-dx * math.sin(tilt) + dy * math.cos(tilt)) * shape["aspect"]
        r_ellipse = np.hypot(ex, ey)
        plateau = CORE_PLATEAU[frame]
        falloff_len = CORE_FALLOFF[frame]
        # 中心滿亮，往外指數衰減：半高的半徑約是看得到的外緣的三成五，不是一塊平台
        core = np.exp(-np.clip(r_ellipse - plateau, 0.0, None) / falloff_len)
        # 外緣的短刺：沿刺的方向衰減得慢，刺兩邊很快收掉，輪廓成不規則的星形；沿著射線一路變暗
        for angle, spike_len in shape["spikes"]:
            diff = np.radians((theta - angle + 180.0) % 360.0 - 180.0)
            half_width = 1.6 / np.maximum(radius, 1.0)
            angular = np.exp(-(diff / half_width) ** 2)
            spike = np.exp(-np.clip(radius - plateau, 0.0, None) / (spike_len / 2.2)) * angular
            core = np.maximum(core, spike)
        core = core * CORE_PEAK[frame]
        rim_src = np.maximum(rim_src, (core > 0.1).astype(np.float64))
    halo_amount = HALO_FRAMES[frame]
    halo = np.zeros_like(radius)
    if halo_amount > 0.0:
        sigma = HALO_RADIUS / 2.2
        halo = np.exp(-(radius / sigma) ** 2) * HALO_PEAK * halo_amount
        rim_src = np.maximum(rim_src, (halo > 0.1).astype(np.float64))
    total_light = np.maximum(np.maximum(light, halo), core)
    # 白芯和光暈那一圈用主色
    main_weight = np.maximum(main_weight, np.clip(1.0 - radius / (HALO_RADIUS * 0.8), 0.0, 1.0))
    rim = np.zeros_like(radius)
    if RIM_ALPHA[frame] > 0.0:
        # 深邊從白芯、光暈和光絲根部往外暈開，只留光的亮度 0.1 以下的地方，和光不重疊
        # 深邊是一條窄帶：貼著白芯、光暈和光絲根部的外緣往外約十個像素，光先往外撐兩個像素再當遮罩，
        # 縮回貼圖大小時邊上才不會混到光
        source = _dilate((rim_src > 0.1).astype(np.float64), 2 * ss)
        blurred = np.clip(_blur(source, RIM_SIGMA * ss) * 2.0, 0.0, 1.0)
        outside = np.clip((0.05 - _dilate(total_light, 2 * ss)) / 0.04, 0.0, 1.0)
        rim = blurred * outside * (1.0 - source)
    fence = np.clip((CONTENT_RADIUS - radius) / 2.0, 0.0, 1.0)
    return (_down(total_light * fence, ss), _down(core * fence, ss), _down(rim * fence, ss),
            _down(main_weight * fence, ss))


def _blur(img, sigma):
    """可分離的高斯模糊，只用 numpy"""
    r = int(math.ceil(sigma * 3))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    padded = np.pad(img, r, mode="constant")
    tmp = np.apply_along_axis(lambda row: np.convolve(row, k, mode="valid"), 1, padded)
    return np.apply_along_axis(lambda col: np.convolve(col, k, mode="valid"), 0, tmp)


def _dilate(img, r):
    """方形的最大值濾波，只用 numpy"""
    out = img.copy()
    for shift in range(1, r + 1):
        out[:, shift:] = np.maximum(out[:, shift:], img[:, :-shift])
        out[:, :-shift] = np.maximum(out[:, :-shift], img[:, shift:])
    wide = out.copy()
    for shift in range(1, r + 1):
        out[shift:, :] = np.maximum(out[shift:, :], wide[:-shift, :])
        out[:-shift, :] = np.maximum(out[:-shift, :], wide[shift:, :])
    return out


def _down(img, ss):
    size = img.shape[0] // ss
    return img.reshape(size, ss, size, ss).mean(axis=(1, 3))


def build():
    rng = _rng()
    plan = streak_plan(rng)
    cores = core_shapes(rng)
    atlas = np.zeros((CELL, CELL * FRAMES, 4))
    for frame in range(FRAMES):
        channels = list(render_frame(frame, plan, cores))
        # 深邊縮回貼圖大小之後再撐滿，最深的地方就是 1，透明度由著色器逐格決定
        if channels[2].max() > 0:
            channels[2] = np.clip(channels[2] / channels[2].max(), 0.0, 1.0)
        for index, channel in enumerate(channels):
            atlas[:, frame * CELL:(frame + 1) * CELL, index] = channel
    return np.clip(np.round(atlas * 255.0), 0, 255).astype(np.uint8), plan


# ---- 檢查：量圖本身，不信產生時的參數 ----

def _polar(channel, radii, angles):
    """把一格照極座標取樣，雙線性"""
    rr, aa = np.meshgrid(radii, np.radians(angles), indexing="ij")
    x = CENTER - 0.5 + rr * np.cos(aa)
    y = CENTER - 0.5 + rr * np.sin(aa)
    x0 = np.clip(np.floor(x).astype(int), 0, CELL - 2)
    y0 = np.clip(np.floor(y).astype(int), 0, CELL - 2)
    fx = x - x0
    fy = y - y0
    c = channel
    return (c[y0, x0] * (1 - fx) * (1 - fy) + c[y0, x0 + 1] * fx * (1 - fy)
            + c[y0 + 1, x0] * (1 - fx) * fy + c[y0 + 1, x0 + 1] * fx * fy)


def _sample(channel, xs, ys):
    x0 = np.clip(np.floor(xs).astype(int), 0, CELL - 2)
    y0 = np.clip(np.floor(ys).astype(int), 0, CELL - 2)
    fx = xs - x0
    fy = ys - y0
    c = channel
    return (c[y0, x0] * (1 - fx) * (1 - fy) + c[y0, x0 + 1] * fx * (1 - fy)
            + c[y0 + 1, x0] * (1 - fx) * fy + c[y0 + 1, x0 + 1] * fx * fy)


PROBE_RADIUS = 22.0


def measure_streaks(light):
    """找出一格裡的光絲：先扣掉每一圈半徑上的中位數，白芯和光暈那種繞一圈都差不多亮的東西就不見了；
    再把每個角度從根部到外緣加起來，光絲是這條曲線上的山峰，寬的光絲在根部黏在一起也分得開；
    回傳每條的角度、長度、每個半徑的寬、末端寬、亮度起伏"""
    angles = np.arange(0.0, 360.0, 0.25)
    radii = np.arange(ROOT_RADIUS, CELL / 2.0, 0.5)
    polar = _polar(light, radii, angles)
    above = np.clip(polar - np.median(polar, axis=1, keepdims=True), 0.0, None)
    total = above[radii >= 12.0].sum(axis=0)
    kernel = np.exp(-0.5 * (np.arange(-8, 9) / 4.0) ** 2)
    kernel /= kernel.sum()
    padded = np.concatenate([total[-8:], total, total[:8]])
    smooth = np.convolve(padded, kernel, mode="valid")
    streaks = []
    floor = 0.08 * smooth.max()
    n = len(smooth)
    for i in range(n):
        v = smooth[i]
        if v < floor or v < smooth[i - 1] or v < smooth[(i + 1) % n]:
            continue
        # 山峰兩邊都要掉到它自己的六成以下才算一條，不然是同一條上的起伏
        left = min(smooth[(i - k) % n] for k in range(1, 40))
        right = min(smooth[(i + k) % n] for k in range(1, 40))
        if max(left, right) > 0.6 * v:
            continue
        if streaks and (angles[i] - streaks[-1]["angle"]) % 360.0 < 8.0:
            continue
        streaks.append({"angle": float(angles[i]), "column": i})
    for streak in streaks:
        cols = [(streak["column"] + k) % len(angles) for k in (-2, -1, 0, 1, 2)]
        line = above[:, cols].max(axis=1)
        lit = np.nonzero(line > 0.04)[0]
        end = radii[lit[-1]] if len(lit) else PROBE_RADIUS
        streak["reach_px"] = float(end)
        streak["length_px"] = float(end - ROOT_RADIUS)
        # 沿軸每 1 像素量一次垂直斷面的寬：亮度過 0.3 的長度
        a = math.radians(streak["angle"])
        ux, uy = math.cos(a), math.sin(a)
        offsets = np.arange(-12.0, 12.25, 0.25)
        middle = len(offsets) // 2
        widths = []
        for r in np.arange(PROBE_RADIUS, end, 1.0):
            px = CENTER - 0.5 + r * ux - offsets * uy
            py = CENTER - 0.5 + r * uy + offsets * ux
            profile = _sample(light, px, py)
            base = np.median(_polar(light, np.array([r]), angles)[0])
            on = (profile - base) > 0.3
            # 只算連著中線的那一段，旁邊隔壁的光絲不算進來
            count = 0
            if on[middle]:
                k = middle
                while k >= 0 and on[k]:
                    k -= 1
                j = middle
                while j < len(on) and on[j]:
                    j += 1
                count = j - k - 1
            widths.append((r, float(count * 0.25)))
        streak["widths"] = widths
        streak["max_width_px"] = max((w for _, w in widths), default=0.0)
        # 末端寬：離末端兩個像素那裡的垂直斷面
        near_tip = [w for r, w in widths if end - 3.0 <= r <= end - 1.0]
        streak["tip_px"] = float(max(near_tip)) if near_tip else 0.0
        body = line[(radii > PROBE_RADIUS + 4) & (radii < end - 8)]
        if len(body) > 8:
            trend = np.polyval(np.polyfit(np.arange(len(body)), body, 1), np.arange(len(body)))
            ratio = body / np.maximum(trend, 1e-3)
            streak["wobble"] = float((ratio.max() - ratio.min()) / 2.0)
        else:
            streak["wobble"] = 0.0
    return streaks


def core_profile(core, angles=np.arange(0.0, 360.0, 2.0)):
    """白芯沿每一條射線的亮度，從中心往外"""
    radii = np.arange(0.0, 40.0, 0.5)
    return radii, _polar(core, radii, angles)


def check_core(core, frame):
    """防平台：滿亮的面積不能太大、沿射線一路變暗、半高的半徑不到外緣的四成"""
    problems = []
    lit = (core > 0.05).sum()
    full = (core >= 0.95).sum()
    if lit == 0:
        return ["第 %d 格沒有白芯" % (frame + 1)]
    if full > 0.2 * lit:
        problems.append("第 %d 格白芯滿亮的面積佔 %.0f%%，要 20%% 以內" % (frame + 1, 100.0 * full / lit))
    radii, profile = core_profile(core)
    rises = np.diff(profile, axis=0)
    if rises.max() > 3.0 / 255.0:
        problems.append("第 %d 格白芯沿射線有變亮的地方，升了 %.3f" % (frame + 1, rises.max()))
    peak = profile[0].mean()
    halves = []
    outers = []
    for column in profile.T:
        below_half = np.nonzero(column < 0.5 * peak)[0]
        below_edge = np.nonzero(column < 0.05)[0]
        if len(below_half) and len(below_edge):
            halves.append(radii[below_half[0]])
            outers.append(radii[below_edge[0]])
    if halves and np.median(halves) > 0.4 * np.median(outers):
        problems.append("第 %d 格白芯半高半徑 %.1f，超過外緣 %.1f 的四成" % (frame + 1, np.median(halves), np.median(outers)))
    return problems


def core_outline(core):
    """白芯亮度 0.3 那條輪廓在每個角度的半徑，除掉平均，比形狀用"""
    radii, profile = core_profile(core, np.arange(0.0, 360.0, 3.0))
    edges = []
    for column in profile.T:
        below = np.nonzero(column < 0.3)[0]
        edges.append(radii[below[0]] if len(below) else radii[-1])
    edges = np.array(edges)
    return edges / edges.mean()


def check(atlas):
    """回傳不及格的項目；空的就是全部及格"""
    problems = []
    data = atlas.astype(np.float64) / 255.0
    if data.shape != (CELL, CELL * FRAMES, 4):
        return ["尺寸不對 %s" % (data.shape,)]
    cells = [data[:, f * CELL:(f + 1) * CELL] for f in range(FRAMES)]
    any_channel = data[..., :3].max(axis=2)
    for frame in range(FRAMES):
        cell = any_channel[:, frame * CELL:(frame + 1) * CELL]
        ys, xs = np.nonzero(cell > 1.0 / 255.0)
        if len(xs):
            r = np.hypot(xs + 0.5 - CENTER, ys + 0.5 - CENTER).max()
            if r > CONTENT_RADIUS + 1.0:
                problems.append("第 %d 格內容半徑 %.1f 超過 %.0f" % (frame + 1, r, CONTENT_RADIUS))
        if cell[0, :].max() > 0 or cell[-1, :].max() > 0 or cell[:, 0].max() > 0 or cell[:, -1].max() > 0:
            problems.append("第 %d 格碰到格子邊" % (frame + 1))
    for boundary in range(1, FRAMES):
        if any_channel[:, boundary * CELL - 8:boundary * CELL + 8].max() > 0:
            problems.append("第 %d 和 %d 格之間沒有空 16 像素" % (boundary, boundary + 1))
    # 光絲：前兩格的條數、成簇、長短、主導、寬度、末端、起伏
    lengths_by_frame = []
    widest_by_frame = []
    for frame in (0, 1):
        streaks = measure_streaks(cells[frame][..., 0])
        n = len(streaks)
        if not 7 <= n <= 11:
            problems.append("第 %d 格光絲 %d 條，要 7 到 11" % (frame + 1, n))
            continue
        angles = sorted(s["angle"] for s in streaks)
        gaps = [(angles[(i + 1) % n] - angles[i]) % 360.0 for i in range(n)]
        if sum(1 for g in gaps if g > 2.0 * 360.0 / n) < 2:
            problems.append("第 %d 格光絲沒有成簇：大於平均兩倍的間隔不到 2 個" % (frame + 1))
        ordered = sorted(streaks, key=lambda s: -s["length_px"])
        lengths = [s["length_px"] for s in ordered]
        lengths_by_frame.append(lengths)
        widest_by_frame.append(max(s["max_width_px"] for s in streaks))
        if frame == 1:
            if lengths[0] / max(lengths[-1], 1e-6) < 3.0:
                problems.append("第 2 格最長最短只差 %.2f 倍" % (lengths[0] / lengths[-1]))
            for a, b in zip(lengths, lengths[1:]):
                if a / max(b, 1e-6) < 1.05:
                    problems.append("第 2 格有兩條光絲一樣長：%.1f 和 %.1f" % (a, b))
            if lengths[2] > 0.8 * lengths[0] and lengths[3] > 0.8 * lengths[0]:
                problems.append("第 2 格沒有兩三條主導的長光絲")
        for s in streaks:
            if s["length_px"] >= 25.0 and s["tip_px"] > 2.5:
                problems.append("第 %d 格光絲末端 %.1f 像素，要削尖到約 1" % (frame + 1, s["tip_px"]))
        for s in ordered[:2]:
            widths = s["widths"]
            if not widths:
                continue
            if frame == 1:
                # 主導的兩三條在長滿的第 2 格量最寬處：離根部 25 到 35%，第 1 格太短、最寬處埋在白芯裡量不到
                r_peak = max(widths, key=lambda item: item[1])[0]
                t_peak = (r_peak - ROOT_RADIUS) / max(s["length_px"], 1e-6)
                if not 0.2 <= t_peak <= 0.4:
                    problems.append("第 2 格主導光絲最寬處在 %.2f，要在離根部 25 到 35%%" % t_peak)
            else:
                # 第 1 格：從白芯外面開始算，四個像素以上的實心佔六成長度，剛離開白芯的地方不超過 12 像素
                solid = sum(1 for _, w in widths if w >= 4.0)
                visible = s["length_px"] - (PROBE_RADIUS - ROOT_RADIUS)
                if solid < 0.6 * visible:
                    problems.append("第 1 格主導光絲四像素以上的實心只有 %d 像素，全長 %.0f" % (solid, visible))
                if widths[0][1] > 12.0 / SCREEN_PER_TEXEL:
                    problems.append("第 1 格主導光絲離開白芯處 %.1f 像素，52 公尺 1080p 超過 12" % widths[0][1])
        long_ones = [s for s in streaks if s["length_px"] > 50]
        if long_ones and max(s["wobble"] for s in long_ones) < 0.2:
            problems.append("第 %d 格光絲沿長度沒有亮度起伏" % (frame + 1))
    if len(widest_by_frame) == 2:
        if not 12.0 <= widest_by_frame[0] <= 16.5:
            problems.append("第 1 格光絲最寬 %.1f 像素，要 12 到 16" % widest_by_frame[0])
        if widest_by_frame[0] * SCREEN_PER_TEXEL > 12.0:
            problems.append("第 1 格光絲最寬在 52 公尺 1080p 是 %.1f 像素，超過 12" % (widest_by_frame[0] * SCREEN_PER_TEXEL))
        if not 7.5 <= widest_by_frame[1] <= 10.5:
            problems.append("第 2 格光絲最寬 %.1f 像素，要 8 到 10" % widest_by_frame[1])
    if len(lengths_by_frame) == 2 and lengths_by_frame[0][0] > 0.7 * lengths_by_frame[1][0]:
        problems.append("第 1 格光絲沒有比第 2 格短，要約六成")
    # 白芯：只在前四格、防平台、前三格輪廓各不相同
    for frame in range(FRAMES):
        core = cells[frame][..., 1]
        if frame < CORE_FRAMES:
            problems += check_core(core, frame)
        elif core.max() > 1.0 / 255.0:
            problems.append("第 %d 格還有白芯" % (frame + 1))
    outlines = [core_outline(cells[f][..., 1]) for f in range(3)]
    for a, b in ((0, 1), (1, 2), (0, 2)):
        similarity = float(np.corrcoef(outlines[a], outlines[b])[0, 1])
        if similarity > 0.9:
            problems.append("第 %d 格和第 %d 格白芯輪廓一樣，相關 %.2f" % (a + 1, b + 1, similarity))
    # 光絲錯開消失：碎片從第 3 格開始，一格比一格少，最後一格還有主導的碎片、而且很淡
    lit_pixels = [(cells[f][..., 0] > 0.08).sum() for f in range(2, FRAMES)]
    if any(b > a * 1.05 for a, b in zip(lit_pixels, lit_pixels[1:])):
        problems.append("光絲碎片沒有一格比一格少：%s" % lit_pixels)
    last_peak = cells[-1][..., 0].max()
    if last_peak <= 0.02:
        problems.append("最後一格已經沒有光絲，主導的要活到 330 毫秒")
    if last_peak > 0.26:
        problems.append("最後一格亮度 %.2f，要淡到四分之一以下" % last_peak)
    third_peak = cells[2][..., 0][np.hypot(*np.mgrid[0:CELL, 0:CELL] - CENTER + 0.5) > 30].max()
    if third_peak > 0.55:
        problems.append("第 3 格光絲碎片亮度 %.2f，要約一半" % third_peak)
    # 光暈第 3 格歸零：白芯外面、光絲之間的地方沒有光
    yy, xx = np.mgrid[0:CELL, 0:CELL]
    ring = (np.hypot(xx + 0.5 - CENTER, yy + 0.5 - CENTER) > 18) & (np.hypot(xx + 0.5 - CENTER, yy + 0.5 - CENTER) < 30)
    if np.median(cells[2][..., 0][ring]) > 0.02:
        problems.append("第 3 格光暈沒有歸零")
    if np.median(cells[0][..., 0][ring]) < 0.05:
        problems.append("第 1 格沒有光暈")
    # 深邊：前三格才有，峰值是滿的，和光不重疊，乘上逐格透明度後一格比一格少
    for frame in range(FRAMES):
        rim = cells[frame][..., 2]
        if RIM_ALPHA[frame] <= 0.0:
            if rim.max() > 0:
                problems.append("第 %d 格還有深邊" % (frame + 1))
            continue
        if rim.max() < 0.98:
            problems.append("第 %d 格深邊最深只有 %.2f" % (frame + 1, rim.max()))
        overlap = rim[cells[frame][..., 0] > 0.1]
        if len(overlap) and overlap.max() > 0.05:
            problems.append("第 %d 格深邊和光重疊，重疊處深邊 %.2f" % (frame + 1, overlap.max()))
    weighted = [cells[f][..., 2].max() * RIM_ALPHA[f] for f in range(3)]
    if not weighted[0] > weighted[1] > weighted[2]:
        problems.append("深邊最深處沒有逐格變淡：%s" % [round(w, 2) for w in weighted])
    return problems


def main():
    from PIL import Image
    atlas, _ = build()
    problems = check(atlas)
    if problems:
        for problem in problems:
            print("不及格：" + problem)
        sys.exit(1)
    Image.fromarray(atlas, "RGBA").save(OUT)
    print("寫出 %s" % OUT)


if __name__ == "__main__":
    main()
