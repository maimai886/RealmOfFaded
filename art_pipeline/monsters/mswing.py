# -*- coding: utf-8 -*-
"""怪物部位的執行期甩動，mpuppet.py --swing 用。

部位不畫進動作格：照視圖資料夾裡的 swing_parts.json 把芽、葉子手這些部位從使用者畫的原圖切出來，
身體被拿掉的地方只補平塗色和描邊，每個部位預先轉好一排角度放在圖集最後面，
遊戲裡 src/world/actors/part_swing.gd 照身體真正的加速度算擺錘、換格子。
紙片在著色器裡轉向鏡頭，節點的旋轉轉不了圖，所以角度要預先轉好。

swing_parts.json 的欄位說明寫在檔案自己的 _說明，做法和參數的來源在 docs/美術產線接手紀錄.md 2.0c。
"""

import json
import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

SPEC_FILE = "swing_parts.json"
# 部位編號：同一片葉子在每個方向用同一個號碼，轉方向時擺的狀態接得下去；左右兩片翻轉時對調
SLOT_NAMES = ["sprout", "arm_left", "arm_right"]
MIRROR_NAMES = {"sprout": "sprout", "arm_left": "arm_right", "arm_right": "arm_left"}
# 預先轉好的角度：擺動常用的正負 48 度每 3 度一張；死掉時身體倒 84 度、部位再垂下去，外面每 12 度一張補到正負 180
FINE_LIMIT = 48
FINE_STEP = 3
COARSE_START = 60
COARSE_STEP = 12
LIMIT = 180
# 小圖在圖集裡：每張外框對齊 8 的倍數、彼此隔 8 像素、框內再留 2 像素透明邊。
# 鏡頭拉遠走 mipmap，縫太窄會吃到隔壁那張，Felix 量過 4 像素的縫在 mip2 最多滲 6%、mip3 最多 27%
GAP_PX = 8
ALIGN_PX = 8
BORDER_PX = 2
# 補身體時，四周這麼寬的一圈當取色的樣本
FILL_RING_PX = 10
# 比這個暗的是描邊，不當成平塗色的樣本
INK_LUMA = 90.0

# 擺的物理參數寫進 meta，遊戲端照這裡的值算，換怪不用改程式；每個數字的來源寫在 docs/美術產線接手紀錄.md 2.0c
PARAMS = {
    # 擺長等於身高 15% 時 4.25 Hz，擺越長越軟，頻率和擺長的平方根成反比
    "hz": 4.25,
    "reference_ratio": 0.15,
    # 阻尼比 0.45：甩過頭剩兩成，0.5 秒內收到 5 度以內
    "damping": 0.45,
    # 30 度以後彈簧變 4 倍硬，40 度只是保險
    "soft_deg": 30.0,
    "soft_stiffness": 4.0,
    "max_deg": 40.0,
    # 世界移動那一路：怪物本身的位移和擊退，6 Hz 濾波；增益照急停 25 到 32 度調的
    "world_filter_hz": 6.0,
    "world_gain": 2.4,
    # 動作姿勢那一路：每格接點和身體的旋轉，兩格之間內插，3 Hz 濾波，增益 0.35
    "pose_filter_hz": 3.0,
    "pose_gain": 0.35,
    # 風阻：走動時部位平均往後拖，每公尺每秒拖約 5 度
    "drag": 6.0,
    # 被打：輕擊、重擊、暴擊的甩動峰值，度；照命中停頓的毫秒數分，40、60、80
    "hit_peak_deg": [21.0, 28.0, 35.0],
    "hit_stop_ms": [40.0, 60.0, 80.0],
    # 畫面每秒 60 格取樣會錯過真正的峰值，受擊動作格回彈也吃掉一些，量過補回來
    "hit_boost": 1.2,
    # 轉身時部位慢半拍：公尺每秒，乘上面向在畫面左右的變化量
    "turn_kick": 0.35,
    # 死掉肌肉放鬆：彈簧剩這個比例，重力把部位拉下垂，公尺每秒平方
    "dead_stiffness": 0.15,
    "gravity": 9.8,
}


def angles():
    fine = list(range(-FINE_LIMIT, FINE_LIMIT + 1, FINE_STEP))
    coarse = list(range(COARSE_START, LIMIT + 1, COARSE_STEP))
    return sorted([-angle for angle in coarse] + fine + coarse)


def load_spec(views):
    path = os.path.join(views, SPEC_FILE)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _polygon_mask(size, points):
    image = Image.new("L", size, 0)
    ImageDraw.Draw(image).polygon([tuple(point) for point in points], fill=255)
    return np.asarray(image) > 0


def _grow(mask, pixels):
    if pixels <= 0:
        return mask
    image = Image.fromarray((mask * 255).astype(np.uint8))
    return np.asarray(image.filter(ImageFilter.MaxFilter(2 * pixels + 1))) > 0


def _luma(rgb):
    return rgb[..., :3].astype(np.float64) @ np.array([0.299, 0.587, 0.114])


def fill_flat(rgba, region, lit_only=True):
    """region 裡補一個平塗色，顏色取四周一圈的中位數；lit_only 時只取比較亮的那六成：
    身體前面的葉子底下常有它投下的陰影，全部拿來平均補出來會是一塊比身體暗的剪影。只有平塗色，描邊之後由 draw_outline 沿剪影畫。
    回傳補好的 rgba"""
    if not region.any():
        return rgba
    out = rgba.copy()
    alpha = rgba[..., 3] > 200
    luma = _luma(rgba)
    ring = _grow(region, FILL_RING_PX) & ~region & alpha & (luma >= INK_LUMA)
    if not ring.any():
        return out
    if lit_only:
        ring = ring & (luma >= np.percentile(luma[ring], 40))
    color = np.median(rgba[ring][:, :3], 0).round().astype(np.uint8)
    out[region, :3] = color
    out[region, 3] = 255
    return out


def fill_rows(rgba, region, reach=24):
    """芽底下那一塊帽子：每一列拿左右兩邊最近的帽子顏色線性接起來，再上下抹一下。
    不加任何紋路，只是讓兩邊的明暗接得上，不會是一塊方的平塗色"""
    out = rgba.copy().astype(np.float64)
    alpha = rgba[..., 3] > 200
    luma = _luma(rgba)
    usable = alpha & ~region & (luma >= INK_LUMA)
    for y in np.unique(np.nonzero(region)[0]):
        xs = np.nonzero(region[y])[0]
        left, right = int(xs.min()), int(xs.max())
        lx = next((x for x in range(left - 1, max(-1, left - reach), -1) if usable[y, x]), None)
        rx = next((x for x in range(right + 1, min(rgba.shape[1], right + reach)) if usable[y, x]), None)
        if lx is None and rx is None:
            continue
        lc = out[y, lx, :3] if lx is not None else out[y, rx, :3]
        rc = out[y, rx, :3] if rx is not None else lc
        span = float(max(1, (rx if rx is not None else right) - (lx if lx is not None else left)))
        for x in xs:
            t = (x - (lx if lx is not None else left)) / span
            out[y, x, :3] = lc * (1.0 - t) + rc * t
        out[y, xs, 3] = 255
    blurred = np.asarray(Image.fromarray(out.round().astype(np.uint8), "RGBA").filter(ImageFilter.BoxBlur(3))).astype(np.float64)
    out[region, :3] = blurred[region, :3]
    return out.round().astype(np.uint8)


def _drop_islands(rgba, keep_ratio=0.02):
    """部位切掉之後，身體旁邊剩下的小碎片，例如葉子描邊沒被圈到的一小段，整塊拿掉"""
    from mpuppet import _components
    alpha = rgba[..., 3] > 8
    labels, count = _components(alpha)
    if count <= 1:
        return rgba
    areas = np.bincount(labels.ravel(), minlength=count + 1)
    areas[0] = 0
    small = areas < areas.max() * keep_ratio
    out = rgba.copy()
    out[..., 3] = np.where(small[labels] & alpha, 0, out[..., 3])
    return out


def _below_silhouette(alpha, cover):
    """cover 那塊的左右兩邊外面各取剪影最上面那一點，連成一條略往上拱的弧，弧下面才補。
    芽拿掉之後帽頂的輪廓照兩邊接回去，不會多出一塊方的"""
    xs = [point[0] for point in cover]
    left, right = int(min(xs)) - 3, int(max(xs)) + 3
    ys_cover = [point[1] for point in cover]
    low, high = int(min(ys_cover)) - 40, int(max(ys_cover))

    def top(x):
        column = np.nonzero(alpha[low:high, x])[0]
        return low + int(column[0]) if len(column) else low
    y_left, y_right = top(left), top(right)
    height, width = alpha.shape
    grid_y, grid_x = np.mgrid[0:height, 0:width]
    t = np.clip((grid_x - left) / float(max(1, right - left)), 0.0, 1.0)
    line = y_left + (y_right - y_left) * t - 4.0 * (1.0 - (2.0 * t - 1.0) ** 2)
    return grid_y >= line


def cut_direction(source, spec_parts):
    """照 swing_parts.json 一個方向的部位，把原圖切成身體和部位。source 是去背後的原圖 RGBA 陣列。
    回傳 (身體 RGBA 陣列, [{name, slot_name, member, pivot, joint, bend, layer}])，座標都是原圖像素"""
    height, width = source.shape[:2]
    alpha = source[..., 3] > 8
    luma = _luma(source)
    parts = []
    removed = np.zeros(alpha.shape, dtype=bool)
    for spec in spec_parts:
        member = _polygon_mask((width, height), spec["polygon"]) & alpha
        if spec.get("leaf_only"):
            # 身體前面的葉子：只拿綠色的葉子和它的墨線，底下的身體不拿
            rgb = source[..., :3].astype(np.float64)
            green = (rgb[..., 1] > rgb[..., 0] + 8) & (rgb[..., 1] > rgb[..., 2])
            member &= green | (luma < INK_LUMA)
            member = _grow(member, 1) & _polygon_mask((width, height), spec["polygon"]) & alpha
        removed |= member
        parts.append({"name": spec["name"], "slot_name": spec.get("slot_as", spec["name"]), "member": member,
                      "pivot": tuple(float(v) for v in spec["pivot"]),
                      "joint": tuple(float(v) for v in spec["joint"]) if "joint" in spec else None,
                      "bend": float(spec.get("bend", 1.0)), "layer": spec.get("layer", "front"),
                      "fill": spec.get("fill", "none"), "cover": spec.get("cover"),
                      "cover_top": spec.get("cover_top")})
    body = source.copy()
    body[..., 3] = np.where(removed, 0, body[..., 3])
    body = _drop_islands(body)
    for part in parts:
        region = np.zeros(alpha.shape, dtype=bool)
        if part["fill"] == "cover":
            region = _polygon_mask((width, height), part["cover"])
            if part.get("cover_top") == "silhouette":
                region &= _below_silhouette(body[..., 3] > 8, part["cover"])
        elif part["fill"] == "member":
            region = part["member"].copy()
        if region.any():
            target = region & (~(body[..., 3] > 200) | part["member"])
            if part.get("cover_top") == "silhouette":
                body = fill_rows(body, target)
            else:
                body = fill_flat(body, target, part["fill"] == "member")
    return body, parts


def prepare(path, spec_parts, scale, cut):
    """讀一張五方向圖，切部位，縮到工作大小。cut 是去背函式。
    回傳 (整隻 figure, 身體 figure, 部位清單)，部位多了 image 和縮好的 member、pivot、joint、lever，座標是工作大小的像素"""
    source = np.asarray(cut(Image.open(path).convert("RGB")))
    body, parts = cut_direction(source, spec_parts)
    ys, xs = np.nonzero(source[..., 3] > 8)
    box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    size = (max(1, int(round((box[2] - box[0]) * scale))), max(1, int(round((box[3] - box[1]) * scale))))
    figure = Image.fromarray(source, "RGBA").crop(box).resize(size, Image.LANCZOS)
    body_image = Image.fromarray(body, "RGBA").crop(box).resize(size, Image.LANCZOS)
    full = np.asarray(figure)
    ratio_x, ratio_y = size[0] / float(box[2] - box[0]), size[1] / float(box[3] - box[1])

    def place(point):
        return ((point[0] - box[0]) * ratio_x, (point[1] - box[1]) * ratio_y)

    for part in parts:
        mask = Image.fromarray((part["member"] * 255).astype(np.uint8)).crop(box).resize(size, Image.BILINEAR)
        member = np.asarray(mask) > 127
        piece = full.copy()
        piece[..., 3] = np.where(member, piece[..., 3], 0)
        part["member"] = member
        part["image"] = Image.fromarray(piece, "RGBA")
        part["pivot"] = place(part["pivot"])
        part["joint"] = place(part["joint"]) if part["joint"] else None
        my, mx = np.nonzero(member)
        part["lever"] = (float(mx.mean()) + 0.5 - part["pivot"][0], float(my.mean()) + 0.5 - part["pivot"][1])
    return figure, body_image, parts


def variants(part, body_image, turn_angles, work_scale, draw_outline, outline_px):
    """一個部位預先轉好的每一個角度，縮成畫格大小並描邊。有 joint 的是兩節：莖只轉 bend 倍，芽頭轉整個角度、跟著莖的末端走。
    描邊只描部位自己露在外面的邊，落在身體上的那一段拿掉，身體和部位交界不會多一條線。
    回傳 [(RGBA, (接點 x, 接點 y))]，接點是小圖裡的位置"""
    width, height = body_image.size
    pad = int(math.ceil(max(width, height) * 0.7 / work_scale)) * work_scale
    canvas = (width + 2 * pad + (width % work_scale), height + 2 * pad + (height % work_scale))
    small = (canvas[0] // work_scale, canvas[1] // work_scale)
    body_layer = Image.new("RGBA", canvas, (0, 0, 0, 0))
    body_layer.alpha_composite(body_image, (pad, pad))
    body_small = np.pad(np.asarray(body_layer.resize(small, Image.LANCZOS))[..., 3] > 64, outline_px)
    pivot = (part["pivot"][0] + pad, part["pivot"][1] + pad)
    image = np.asarray(part["image"])
    stem_image, head_image = part["image"], None
    if part["joint"]:
        joint = (part["joint"][0] + pad, part["joint"][1] + pad)
        axis = (joint[0] - pivot[0], joint[1] - pivot[1])
        length = math.hypot(*axis)
        ys, xs = np.mgrid[0:height, 0:width]
        along = ((xs + pad + 0.5 - pivot[0]) * axis[0] + (ys + pad + 0.5 - pivot[1]) * axis[1]) / max(length, 1.0)
        head = along >= length
        stem = image.copy()
        stem[..., 3] = np.where(head, 0, stem[..., 3])
        top = image.copy()
        top[..., 3] = np.where(head, top[..., 3], 0)
        stem_image, head_image = Image.fromarray(stem, "RGBA"), Image.fromarray(top, "RGBA")
    stem_layer = Image.new("RGBA", canvas, (0, 0, 0, 0))
    stem_layer.alpha_composite(stem_image, (pad, pad))
    head_layer = None
    if head_image is not None:
        head_layer = Image.new("RGBA", canvas, (0, 0, 0, 0))
        head_layer.alpha_composite(head_image, (pad, pad))
    results = []
    for angle in turn_angles:
        stem_angle = angle * part["bend"] if head_layer is not None else angle
        turned = stem_layer.rotate(-stem_angle, resample=Image.BICUBIC, center=pivot)
        if head_layer is not None:
            # 芽頭繞分界點轉整個角度，再搬到莖轉完之後分界點的位置
            theta = math.radians(stem_angle)
            dx, dy = joint[0] - pivot[0], joint[1] - pivot[1]
            moved = (pivot[0] + dx * math.cos(theta) - dy * math.sin(theta),
                     pivot[1] + dx * math.sin(theta) + dy * math.cos(theta))
            top_turned = head_layer.rotate(-angle, resample=Image.BICUBIC, center=joint,
                                           translate=(moved[0] - joint[0], moved[1] - joint[1]))
            turned.alpha_composite(top_turned)
        shrunk = turned.resize(small, Image.LANCZOS)
        original = np.pad(np.asarray(shrunk), ((outline_px, outline_px), (outline_px, outline_px), (0, 0)))
        solid = original[..., 3] > 40
        core = np.asarray(Image.fromarray((solid * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(3))) > 0
        outlined = np.asarray(draw_outline(shrunk)).copy()
        # draw_outline 把剪影最外一圈換成描邊色。落在身體上的那一段是部位和身體的接縫，不描：
        # 原本是部位的像素換回原色，原本是空的就留空
        seam = (outlined[..., 3] > 0) & ~core & body_small
        outlined[seam] = original[seam]
        ys, xs = np.nonzero(outlined[..., 3] > 0)
        x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
        crop = Image.fromarray(outlined[y0:y1, x0:x1], "RGBA")
        results.append((crop, (pivot[0] / work_scale + outline_px - x0, pivot[1] / work_scale + outline_px - y0)))
    return results


def pack(images, frame_px, columns, start_cell):
    """小圖排進圖集後面的保留格：外框對齊 ALIGN_PX、彼此隔 GAP_PX、框內留 BORDER_PX，不跨格。
    回傳 ({索引: (x, y)} 小圖本身在圖集的左上角, 用掉幾格)"""
    def up(value):
        return -(-value // ALIGN_PX) * ALIGN_PX
    order = sorted(range(len(images)), key=lambda index: -images[index].height)
    spots = {}
    cell, shelf_y, shelf_h, cursor_x = 0, GAP_PX, 0, GAP_PX
    for index in order:
        box_w = up(images[index].width + 2 * BORDER_PX)
        box_h = up(images[index].height + 2 * BORDER_PX)
        if box_w + 2 * GAP_PX > frame_px or box_h + 2 * GAP_PX > frame_px:
            raise SystemExit("部位轉好之後有 %dx%d，塞不進 %d 的格子" % (box_w, box_h, frame_px))
        if cursor_x + box_w + GAP_PX > frame_px:
            shelf_y, shelf_h, cursor_x = up(shelf_y + shelf_h + GAP_PX), 0, GAP_PX
        if shelf_y + box_h + GAP_PX > frame_px:
            cell, shelf_y, shelf_h, cursor_x = cell + 1, GAP_PX, 0, GAP_PX
        at = start_cell + cell
        spots[index] = ((at % columns) * frame_px + cursor_x + BORDER_PX, (at // columns) * frame_px + shelf_y + BORDER_PX)
        cursor_x = up(cursor_x + box_w + GAP_PX)
        shelf_h = max(shelf_h, box_h)
    return spots, cell + 1


def slots_for(parts_by_direction):
    """部位編號照名字：芽、左手、右手；spec 的 slot_as 可以指定當成哪一片。回傳 ({方向: [編號]}, 鏡射表, 編號數)"""
    slots = {direction: [SLOT_NAMES.index(part["slot_name"]) for part in parts]
             for direction, parts in parts_by_direction.items()}
    mirror = [SLOT_NAMES.index(MIRROR_NAMES[name]) for name in SLOT_NAMES]
    return slots, mirror, len(SLOT_NAMES)
