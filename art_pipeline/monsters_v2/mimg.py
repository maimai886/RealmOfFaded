"""怪物精靈圖的影像處理，全部是 numpy，陣列是 (高, 寬, 4) 的直接 alpha

和 96 像素那一版最大的差別：192 像素下不再追求像素感。
縮圖用面積平均、邊緣保留抗鋸齒、描邊約兩像素而且有粗細變化，
出來要像手繪完稿的 2D 圖，不是放大的像素圖。

PNG 的讀寫借 Blender 的影像系統，這樣這份檔案在背景 Blender 裡就能跑，
不必依賴系統 Python 有沒有裝 Pillow。
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


def load_srgb(path):
    """讀進來的數值就是 PNG 裡的位元組除以 255，也就是 sRGB 顯示值

    Blender 的 image.pixels 在背景模式讀寫八位元 PNG 時不做色彩管理，
    量測過：寫 0.214 進去存出來就是位元組 55。所以整套影像處理都在 sRGB 顯示空間做，
    算圖那一端也一樣：材質的自發光色是線性值，經過 Standard 顯示轉換寫成 PNG 之後
    位元組剛好等於色階表裡寫的那個十六進位值。
    """
    return load_png(path)


def save_png(array, path, non_color=False):
    import os
    os.makedirs(os.path.dirname(path), exist_ok=True)
    height, width = array.shape[:2]
    image = bpy.data.images.new("mv3_out", width, height, alpha=True)
    if non_color:
        image.colorspace_settings.name = "Non-Color"
    image.pixels.foreach_set(np.flipud(np.clip(array, 0.0, 1.0)).astype(np.float32).ravel())
    image.filepath_raw = path
    image.file_format = "PNG"
    image.save()
    bpy.data.images.remove(image)
    return path


def save_srgb(array, path):
    """處理完的 sRGB 數值存回 PNG，存進去的位元組就是這個數值乘以 255"""
    return save_png(array, path)


def srgb_to_linear(value):
    value = np.clip(value, 0.0, 1.0)
    return np.where(value <= 0.04045, value / 12.92, ((value + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(value):
    out = value.copy()
    rgb = np.clip(out[..., :3], 0.0, 1.0)
    out[..., :3] = np.where(rgb <= 0.0031308, rgb * 12.92, 1.055 * rgb ** (1 / 2.4) - 0.055)
    return out


def hex_rgb(hex_color):
    hex_color = hex_color.lstrip("#")
    return np.array([int(hex_color[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], dtype=np.float32)


# 影像運算


def downsample(image, factor):
    """依 alpha 加權的面積平均，透明像素的顏色不會把邊緣染黑"""
    height, width = image.shape[0] // factor, image.shape[1] // factor
    blocks = image[:height * factor, :width * factor].reshape(height, factor, width, factor, 4)
    alpha = blocks[..., 3].mean(axis=(1, 3))
    weighted = (blocks[..., :3] * blocks[..., 3:4]).mean(axis=(1, 3))
    color = np.where(alpha[..., None] > 1e-6, weighted / np.maximum(alpha[..., None], 1e-6), 0.0)
    return np.concatenate([color, alpha[..., None]], axis=2).astype(np.float32)


def resize_box(image, width, height):
    """整數倍或非整數倍都可用的面積縮放，只給檢查圖和貼圖用"""
    src_h, src_w = image.shape[:2]
    rows = (np.arange(height) * (src_h / height)).astype(np.int32)
    cols = (np.arange(width) * (src_w / width)).astype(np.int32)
    if src_h % height == 0 and src_w % width == 0 and src_h // height == src_w // width:
        return downsample(image, src_h // height)
    return image[rows][:, cols]


def blur(channel, radius):
    """可分離的方框模糊跑三次，近似高斯，邊界用複製"""
    out = channel.astype(np.float32)
    for _ in range(3):
        out = _box1d(out, radius, axis=0)
        out = _box1d(out, radius, axis=1)
    return out


def _box1d(data, radius, axis):
    if radius < 1:
        return data
    padded = np.pad(data, [(radius, radius) if a == axis else (0, 0)
                           for a in range(data.ndim)], mode="edge")
    cumulative = np.cumsum(padded, axis=axis)
    zero_shape = list(cumulative.shape)
    zero_shape[axis] = 1
    cumulative = np.concatenate([np.zeros(zero_shape, dtype=np.float32), cumulative], axis=axis)
    size = 2 * radius + 1
    upper = np.take(cumulative, np.arange(size, size + data.shape[axis]), axis=axis)
    lower = np.take(cumulative, np.arange(0, data.shape[axis]), axis=axis)
    return (upper - lower) / size


def wrap_blur(channel, radius):
    """會繞回去的模糊，做可平鋪貼圖時用"""
    out = channel.astype(np.float32)
    for _ in range(3):
        out = _wrap1d(out, radius, axis=0)
        out = _wrap1d(out, radius, axis=1)
    return out


def _wrap1d(data, radius, axis):
    if radius < 1:
        return data
    padded = np.concatenate([np.take(data, np.arange(-radius, 0), axis=axis, mode="wrap"), data,
                             np.take(data, np.arange(0, radius), axis=axis, mode="wrap")], axis=axis)
    cumulative = np.cumsum(padded, axis=axis)
    zero_shape = list(cumulative.shape)
    zero_shape[axis] = 1
    cumulative = np.concatenate([np.zeros(zero_shape, dtype=np.float32), cumulative], axis=axis)
    size = 2 * radius + 1
    upper = np.take(cumulative, np.arange(size, size + data.shape[axis]), axis=axis)
    lower = np.take(cumulative, np.arange(0, data.shape[axis]), axis=axis)
    return (upper - lower) / size


def luminance(rgb):
    return rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722


# 精靈圖的完稿處理

# alpha 大於這個值就算實心，描邊和內線都只在實心區域上算
SOLID = 0.45
# 光從畫面左上前方來，和著色器裡的 LIGHT_DIR 投影到畫面上的方向一致
SCREEN_LIGHT = np.array([-0.55, -0.84], dtype=np.float32)


def _erode(mask):
    padded = np.pad(mask, 1, constant_values=False)
    return (padded[:-2, 1:-1] & padded[2:, 1:-1] & padded[1:-1, :-2] & padded[1:-1, 2:]
            & padded[:-2, :-2] & padded[:-2, 2:] & padded[2:, :-2] & padded[2:, 2:])


def outline(image, line_color, base_strength=0.34, scale=2.0):
    """外輪廓壓一圈很淡的暗色，幫忙和背景分開

    2026-09-16 照 docs/美術風格指南.md 拿掉黑色硬描邊：不再畫線，只把最外圈壓暗一點點，
    而且受光側幾乎不壓、背光側壓得多一些，看起來像形體自己暗下去而不是描了一條邊。
    scale 是相對於 96 像素的倍率，192 給 2.0。
    """
    solid = image[..., 3] > SOLID
    inner1 = _erode(solid)
    ring1 = solid & ~inner1
    result = image.copy()
    line = np.asarray(line_color[:3], dtype=np.float32)

    # 外輪廓的朝外方向：實心遮罩模糊後的梯度反向
    field = blur(solid.astype(np.float32), max(1, int(round(scale))))
    grad_y, grad_x = np.gradient(field)
    length = np.sqrt(grad_x ** 2 + grad_y ** 2) + 1e-6
    # 朝外是亮度下降的方向
    facing = (-grad_x / length) * SCREEN_LIGHT[0] + (-grad_y / length) * SCREEN_LIGHT[1]

    rings = [ring1]
    layer = inner1
    for _ in range(int(round(scale)) - 1):
        nxt = _erode(layer)
        rings.append(layer & ~nxt)
        layer = nxt

    for index, ring in enumerate(rings):
        if index == 0:
            # 受光側幾乎不壓，背光側才壓得明顯，暗緣因此是有厚薄的不是一條等寬的線
            lean = 0.30 + 0.70 * np.clip(-facing, 0.0, 1.0)
            strength = np.where(ring, base_strength * lean, 0.0)
        else:
            fade = np.clip(-facing, 0.0, 1.0) ** 1.2
            strength = np.where(ring, base_strength * fade * 0.55, 0.0)
        strength = strength[..., None]
        result[..., :3] = result[..., :3] * (1.0 - strength) + line * strength

    # 半透明的抗鋸齒邊只壓一點點，壓重了外圍會糊出黑暈
    fringe = (image[..., 3] > 0.03) & (image[..., 3] <= SOLID)
    blend = np.where(fringe, 0.18, 0.0)[..., None]
    result[..., :3] = result[..., :3] * (1.0 - blend) + line * blend
    return result


def inner_lines(image, ids, line_color, opacity=0.16):
    """材質交界壓一像素很淡的暗色

    風格指南說不補內部線條，分區靠色塊和明暗。但怪物身上有爪、牙、眼睛這種
    很小又很重要的分區，縮到一半大小會糊在一起，所以只留極淡的一層幫忙分開，
    淡到單看不覺得有線

    每條邊只畫在上方或左方那一格，線維持一像素。
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


def finish_mask(image, factor, alpha_from):
    """遮罩縮小時取覆蓋最多的通道，邊緣不會混出灰色"""
    height, width = image.shape[0] // factor, image.shape[1] // factor
    blocks = image[:height * factor, :width * factor].reshape(height, factor, width, factor, 4)
    weight = blocks[..., 3:4]
    totals = (blocks[..., :3] * weight).sum(axis=(1, 3))
    coverage = weight.sum(axis=(1, 3))
    strength = totals / np.maximum(coverage, 1e-6)
    best = strength.argmax(axis=2)
    strongest = strength.max(axis=2)
    result = np.zeros((height, width, 4), dtype=np.float32)
    visible = alpha_from[..., 3] > 0.04
    for channel in range(3):
        hit = visible & (best == channel) & (strongest > 0.30)
        result[hit, channel] = 1.0
    result[..., 3] = alpha_from[..., 3]
    return result


def finish_ids(image, factor):
    """材質編號圖縮小：每個通道取覆蓋最多的值再四捨五入回三檔，算出編號"""
    height, width = image.shape[0] // factor, image.shape[1] // factor
    blocks = image[:height * factor, :width * factor].reshape(height, factor, width, factor, 4)
    weight = blocks[..., 3:4]
    coverage = np.maximum(weight.sum(axis=(1, 3)), 1e-6)
    mean = (blocks[..., :3] * weight).sum(axis=(1, 3)) / coverage
    levels = np.rint(mean * 2.0).astype(np.int32)
    return levels[..., 0] + levels[..., 1] * 3 + levels[..., 2] * 9


def pack_grid(rows, frame_px, columns):
    """固定格子的網格圖集，短的列右邊留透明"""
    sheet = np.zeros((frame_px * len(rows), frame_px * columns, 4), dtype=np.float32)
    for row_index, row in enumerate(rows):
        for col_index, frame in enumerate(row):
            sheet[row_index * frame_px:(row_index + 1) * frame_px,
                  col_index * frame_px:(col_index + 1) * frame_px] = frame
    return sheet


def over(image, background):
    """透明背景的圖疊到底色上，檢查圖才看得清楚邊緣"""
    alpha = image[..., 3:4]
    rgb = image[..., :3] * alpha + np.asarray(background, dtype=np.float32) * (1.0 - alpha)
    return np.concatenate([rgb, np.ones_like(alpha)], axis=2)
