"""精靈圖的像素後製，全部是 numpy，陣列格式為 (高, 寬, 4) 的直接 alpha

流程：兩倍解析度算圖 → 依 alpha 加權縮小 → 材質交界補內線 → 外圈補描邊。
不做任何像素化，也不把 alpha 二值化，縮完就是乾淨的手繪感 2D。
描邊的粗細跟著受光方向變，背光側兩格、受光側一格淡的，線條才有輕重不是機器畫的等寬線。
換色遮罩走另一條路，縮小時取覆蓋率最高的通道而不是平均，才不會在邊緣混出灰色。
"""

import numpy as np

import bpy


def load_png(path):
    """讀 PNG 成由上往下的陣列。Blender 的像素是由下往上存的，所以要翻轉"""
    image = bpy.data.images.load(path)
    width, height = image.size
    flat = np.empty(width * height * 4, dtype=np.float32)
    image.pixels.foreach_get(flat)
    bpy.data.images.remove(image)
    return np.flipud(flat.reshape(height, width, 4)).copy()


def save_png(array, path, non_color=False):
    height, width = array.shape[:2]
    image = bpy.data.images.new("v2_out", width, height, alpha=True)
    if non_color:
        image.colorspace_settings.name = "Non-Color"
    image.pixels.foreach_set(np.flipud(array).astype(np.float32).ravel())
    image.filepath_raw = path
    image.file_format = "PNG"
    image.save()
    bpy.data.images.remove(image)


def downsample(image, factor):
    """用 alpha 加權平均縮小，透明像素的顏色才不會把邊緣染黑"""
    height, width = image.shape[0] // factor, image.shape[1] // factor
    blocks = image[:height * factor, :width * factor].reshape(height, factor, width, factor, 4)
    alpha = blocks[..., 3].mean(axis=(1, 3))
    weighted = (blocks[..., :3] * blocks[..., 3:4]).mean(axis=(1, 3))
    color = np.where(alpha[..., None] > 1e-6, weighted / np.maximum(alpha[..., None], 1e-6), 0.0)
    return np.concatenate([color, alpha[..., None]], axis=2).astype(np.float32)


SOLID = 0.35
# 光從畫面左上方來，所以描邊在右下方最重、左上方最輕。這是畫面空間的方向，(往右, 往上)
LIGHT_SCREEN = (-0.45, 0.53)
# 受光側和背光側的外緣濃度。這個畫風不畫描邊，所以兩個都壓得很低，
# 受光側幾乎是 0，讓邊緣光留得住；背光側也只是輕輕壓暗幫忙和背景分開
OUTLINE_LIT = 0.04
OUTLINE_SHADE = 0.26


def _shrink_mask(mask):
    """八個方向都被實心包住的像素"""
    padded = np.pad(mask, 1, constant_values=False)
    return (padded[:-2, 1:-1] & padded[2:, 1:-1] & padded[1:-1, :-2] & padded[1:-1, 2:]
            & padded[:-2, :-2] & padded[:-2, 2:] & padded[2:, :-2] & padded[2:, 2:])


def _lit_amount(alpha):
    """每個像素的外法線有多朝向光源，1 是正對光、0 是完全背光

    alpha 的梯度指向形狀內部，所以外法線是梯度的反方向，再和畫面空間的光向量做內積。
    """
    gy, gx = np.gradient(alpha.astype(np.float32))
    # 外法線 (往右, 往上) 是 (-gx, gy)
    facing = (-gx) * LIGHT_SCREEN[0] + gy * LIGHT_SCREEN[1]
    scale = np.maximum(np.sqrt(gx * gx + gy * gy), 1e-5)
    return np.clip(facing / scale / 0.7 * 0.5 + 0.5, 0.0, 1.0)


def outline(image, line_color, width=1):
    """最外圈壓一層很淡的暗色，只是幫角色和背景分開，不是描邊

    2026-09-16 改版，照 docs/美術風格指南.md：這個畫風不畫黑色描邊，靠形體和明暗分離背景。
    所以這裡從原本的兩格濃描邊改成一格很淡、而且只壓在背光側；受光側幾乎不壓，
    邊緣光才留得住。完全不壓的話角色在亮背景上會糊掉，所以留一點點。
    """
    alpha = image[..., 3]
    solid = alpha > SOLID
    lit = _lit_amount(alpha)
    result = image.copy()
    line = np.asarray(line_color[:3], dtype=np.float32)

    rings, current = [], solid
    for _ in range(max(1, width)):
        inner = _shrink_mask(current)
        rings.append(current & ~inner)
        current = inner

    for ring in rings:
        strength = OUTLINE_SHADE + (OUTLINE_LIT - OUTLINE_SHADE) * lit
        weight = (ring * strength)[..., None]
        result[..., :3] = result[..., :3] * (1.0 - weight) + line * weight

    # 半透明的鋸齒邊稍微壓一點，角色外圍才不會浮出一圈亮邊
    fringe = (alpha > 0.04) & ~solid
    edge_weight = (fringe * (0.06 + 0.12 * (1.0 - lit)))[..., None]
    result[..., :3] = result[..., :3] * (1.0 - edge_weight) + line * edge_weight
    return result


def finish_color(image, factor, line_color):
    """兩倍解析度算圖，面積平均縮小，最後才補描邊，alpha 保持連續不做二值化"""
    return outline(downsample(image, factor), line_color)


def finish_mask(image, factor, alpha_from):
    """遮罩縮小時取覆蓋最多的通道，邊緣不會混出灰色

    形狀直接沿用彩色圖的 alpha，兩張圖的輪廓才會完全一致。
    只要有一點點不透明就要給通道，不然描邊那一圈會變成不換色的破洞。
    """
    height, width = image.shape[0] // factor, image.shape[1] // factor
    blocks = image[:height * factor, :width * factor].reshape(height, factor, width, factor, 4)
    weight = blocks[..., 3:4]
    totals = (blocks[..., :3] * weight).sum(axis=(1, 3))
    # 除以總覆蓋量換算回 0~1，不然門檻會跟著覆蓋面積跑
    coverage = weight.sum(axis=(1, 3))
    strength = totals / np.maximum(coverage, 1e-6)
    best = strength.argmax(axis=2)
    strongest = strength.max(axis=2)
    result = np.zeros((height, width, 4), dtype=np.float32)
    visible = alpha_from[..., 3] > 0.04
    for channel in range(3):
        # 門檻不能訂得太低：算圖存成 8 位元 PNG 之後，本來全黑的區域紅色通道會剩下 1/255，
        # 只比大小的話整片不換色的區域都會被判成頭髮
        hit = visible & (best == channel) & (strongest > 0.30)
        result[hit, channel] = 1.0
    result[..., 3] = alpha_from[..., 3]
    return result


def finish_ids(image, factor):
    """材質編號圖縮小：每個通道各自取覆蓋最多的值，再四捨五入回 0、1、2 三檔，算出編號"""
    height, width = image.shape[0] // factor, image.shape[1] // factor
    blocks = image[:height * factor, :width * factor].reshape(height, factor, width, factor, 4)
    weight = blocks[..., 3:4]
    coverage = np.maximum(weight.sum(axis=(1, 3)), 1e-6)
    mean = (blocks[..., :3] * weight).sum(axis=(1, 3)) / coverage
    levels = np.rint(mean * 2.0).astype(np.int32)
    return levels[..., 0] + levels[..., 1] * 3 + levels[..., 2] * 9


def inner_lines(image, ids, line_color, opacity=0.60):
    """材質交界處補一條 1 px 的深線，RO 精靈圖的俐落感就是這個

    只在兩邊都是不透明像素的地方畫，外輪廓交給 outline 處理。
    每條邊只畫在上方或左方那一格，線才會維持 1 px
    """
    solid = image[..., 3] > SOLID
    differ_right = (ids[:, :-1] != ids[:, 1:]) & solid[:, :-1] & solid[:, 1:]
    differ_down = (ids[:-1, :] != ids[1:, :]) & solid[:-1, :] & solid[1:, :]
    edge = np.zeros_like(solid)
    edge[:, :-1] |= differ_right
    edge[:-1, :] |= differ_down
    result = image.copy()
    line = np.asarray(line_color[:3], dtype=np.float32)
    result[edge, :3] = result[edge, :3] * (1.0 - opacity) + line * opacity
    return result


def pack_grid(rows, frame_px, columns):
    """固定格子的網格圖集，短的列右邊留透明"""
    sheet = np.zeros((frame_px * len(rows), frame_px * columns, 4), dtype=np.float32)
    for row_index, row in enumerate(rows):
        for col_index, frame in enumerate(row):
            sheet[row_index * frame_px:(row_index + 1) * frame_px,
                  col_index * frame_px:(col_index + 1) * frame_px] = frame
    return sheet


def over(image, background):
    """把透明背景的圖疊到底色上，檢查圖看得清楚邊緣"""
    alpha = image[..., 3:4]
    rgb = image[..., :3] * alpha + np.asarray(background, dtype=np.float32) * (1.0 - alpha)
    return np.concatenate([rgb, np.ones_like(alpha)], axis=2)
