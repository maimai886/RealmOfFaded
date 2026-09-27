"""
把 AI 產生的手繪原圖處理成遊戲用貼圖，整段在 Blender 的 Python 裡跑，只靠 numpy。
- 可平鋪材質：原圖平移半張得到邊緣本來就接得起來的版本，中央保留原圖、邊緣換成平移版，
  再統一成 RO 色階，縮到目標尺寸
- 葉團卡片：保留透明，裁到內容範圍再補成正方形
- 貼花：裁掉空白後拼成一張 4x2 的圖集，格子順序照 DECALS，程式端 map_environment.gd 用同樣的順序
每張輸出都一併寫 .import：3D 用的貼圖要有 mipmap，不然遠處會閃爍；不透明的用 VRAM 壓縮省手機記憶體，
有透明的維持無損，alpha scissor 的邊緣才乾淨
"""
import hashlib
import os
import re

import numpy as np

import config
from common import atlas

RAW_DIR = os.path.join(config.PROJECT_ROOT, "art_source", "textures", "raw")
TEXTURES_OUT = os.path.join(config.PROJECT_ROOT, "assets", "generated", "textures")

# RO 色階的共用高光和偏紫暗部，見 docs/調查/RO配色參考.md
CREAM = np.array([1.0, 0.933, 0.796], dtype=np.float32)
SHADOW = np.array([0.24, 0.16, 0.30], dtype=np.float32)
SATURATION_CAP = 0.72

# 可平鋪材質：輸出尺寸和色階微調。地面四層維持 1024，建築和岩石 512 就夠，鏡頭離得遠
TILES = {
    "grass": dict(size=1024, gain=0.96, saturation=0.92, warm=0.30),
    "grass_dry": dict(size=1024, gain=0.98, saturation=0.90, warm=0.30),
    "dirt": dict(size=1024, gain=1.0, saturation=0.95, warm=0.30),
    "cobblestone": dict(size=1024, gain=1.0, saturation=1.0, warm=0.30),
    "plaster": dict(size=512, gain=0.96, saturation=1.1, warm=0.20, contrast=1.6),
    "wood": dict(size=512, gain=0.92, saturation=0.88, warm=0.30),
    "roof_tiles": dict(size=512, gain=0.90, saturation=0.85, warm=0.35),
    "stone_wall": dict(size=512, gain=0.98, saturation=0.95, warm=0.30),
    "rock": dict(size=512, gain=0.95, saturation=0.92, warm=0.30),
    # 崖壁和大石頭用的圓石面，對比壓低才不會變成花花的圖案
    "cliff_rock": dict(size=512, gain=1.0, saturation=0.82, warm=0.32, contrast=0.85),
    "bark": dict(size=512, gain=0.92, saturation=0.85, warm=0.30),
    # 地窟：藍灰石牆和石板地，亮部不往奶油色收太多才保持冷色
    "cave_rock": dict(size=512, gain=1.0, saturation=0.95, warm=0.12, contrast=1.15),
    "dungeon_floor": dict(size=512, gain=0.98, saturation=0.9, warm=0.12, contrast=1.1),
}

# 葉團與枝幹卡片：align 是內容在正方形裡的對齊方式，樹冠置中、有根部的貼底
CARDS = {
    "leaf_bright": dict(size=512, align="center", gain=0.97, saturation=0.95),
    "leaf_dark": dict(size=512, align="center", gain=1.0, saturation=0.95),
    "pine_tier": dict(size=512, align="center", gain=1.0, saturation=0.95),
    "dead_branches": dict(size=512, align="bottom", gain=1.0, saturation=0.9),
    "leaves": dict(size=512, align="center", gain=0.95, saturation=0.95),
}

# 貼花圖集的格子順序，4 欄 3 列，每格 256；前八格是立起來的花草和平貼的碎石裂縫，
# 後四格是平貼在地上的細節：車轍、水窪、苔蘚、落葉
DECALS = ["flower_pink", "flower_white", "flower_blue", "grass_tuft", "pebbles", "fern", "rubble", "crack",
          "cart_track", "puddle", "moss", "leaf_litter"]
DECAL_ALIGN = {"pebbles": "center", "crack": "center", "cart_track": "center", "puddle": "center", "moss": "center",
               "leaf_litter": "center"}
# 個別貼花的色階微調：水窪和車轍原圖偏暗，放在石板路上會變成一個洞
DECAL_GRADE = {"puddle": dict(gain=1.3, saturation=0.7), "cart_track": dict(gain=1.2, saturation=0.7),
               "leaf_litter": dict(gain=1.18, saturation=0.8),
               "crack": dict(gain=1.35, saturation=0.6)}
DECAL_CELL = 256
DECAL_COLUMNS = 4
DECAL_ROWS = 3


def edge_weight(size, blend_fraction=0.28):
    """回傳 (size, size) 的權重，離邊緣越遠越接近 1"""
    coords = np.arange(size, dtype=np.float32) + 0.5
    distance = np.minimum(coords, size - coords) / (size * blend_fraction)
    ramp = np.clip(distance, 0.0, 1.0)
    ramp = ramp * ramp * (3.0 - 2.0 * ramp)
    return np.outer(ramp, ramp)


def make_tileable(image):
    height, width = image.shape[:2]
    shifted = np.roll(np.roll(image, height // 2, axis=0), width // 2, axis=1)
    weight = edge_weight(height)[..., None]
    return image * weight + shifted * (1.0 - weight)


def grade(rgb, gain=1.0, saturation=1.0, warm=0.3, lift=0.35, cap=SATURATION_CAP, contrast=1.0):
    """
    統一成 RO 色階：亮部往奶油色收、暗部往紫色抬不留純黑、飽和度不超過上限。
    純黑會變成 RO 最深一階附近的 #150e1b，rgb 是 (..., 3) 的 sRGB 值 0～1。
    contrast 大於 1 時以整張的平均為中心拉開明暗，給灰泥這種原圖太平的材質用
    """
    rgb = rgb.astype(np.float32)
    if contrast != 1.0:
        mean = rgb.mean(axis=tuple(range(rgb.ndim - 1)), keepdims=True)
        rgb = np.clip(mean + (rgb - mean) * contrast, 0.0, 1.0)
    luma = rgb @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    to_cream = (warm * luma ** 4)[..., None]
    rgb = rgb * (1.0 - to_cream) + CREAM * to_cream
    to_shadow = (lift * (1.0 - luma) ** 3)[..., None]
    rgb = rgb * (1.0 - to_shadow) + SHADOW * to_shadow
    rgb = np.clip(rgb * gain, 0.0, 1.0)
    # 飽和度以最亮通道為軸縮放，明度不變
    top = rgb.max(axis=-1, keepdims=True)
    chroma = top - rgb.min(axis=-1, keepdims=True)
    sat = chroma / np.maximum(top, 1e-6)
    scale = np.full_like(sat, saturation)
    scaled = sat * scale
    scale = np.where(scaled > cap, cap / np.maximum(sat, 1e-6), scale)
    return np.clip(top - (top - rgb) * scale, 0.0, 1.0)


def box_down(image, factor):
    """整數倍面積縮小"""
    if factor <= 1:
        return image
    height, width = image.shape[:2]
    height -= height % factor
    width -= width % factor
    cropped = image[:height, :width]
    return cropped.reshape(height // factor, factor, width // factor, factor, -1).mean(axis=(1, 3))


def resize(image, out_height, out_width):
    """先整數倍面積縮小，剩下的用雙線性補，縮小時才不會出現鋸齒"""
    height, width = image.shape[:2]
    factor = int(min(height // out_height, width // out_width))
    image = box_down(image, max(factor, 1))
    height, width = image.shape[:2]
    ys = (np.arange(out_height, dtype=np.float32) + 0.5) * height / out_height - 0.5
    xs = (np.arange(out_width, dtype=np.float32) + 0.5) * width / out_width - 0.5
    y0 = np.clip(np.floor(ys), 0, height - 1).astype(int)
    x0 = np.clip(np.floor(xs), 0, width - 1).astype(int)
    y1 = np.clip(y0 + 1, 0, height - 1)
    x1 = np.clip(x0 + 1, 0, width - 1)
    fy = np.clip(ys - y0, 0.0, 1.0)[:, None, None]
    fx = np.clip(xs - x0, 0.0, 1.0)[None, :, None]
    top = image[y0][:, x0] * (1 - fx) + image[y0][:, x1] * fx
    bottom = image[y1][:, x0] * (1 - fx) + image[y1][:, x1] * fx
    return top * (1 - fy) + bottom * fy


def crop_to_content(image, margin=0.03, threshold=0.02):
    """裁到 alpha 有內容的範圍，四周留一點邊"""
    alpha = image[..., 3]
    rows = np.where(alpha.max(axis=1) > threshold)[0]
    cols = np.where(alpha.max(axis=0) > threshold)[0]
    if rows.size == 0 or cols.size == 0:
        return image
    height, width = image.shape[:2]
    pad_y = int(height * margin)
    pad_x = int(width * margin)
    top = max(rows[0] - pad_y, 0)
    bottom = min(rows[-1] + pad_y + 1, height)
    left = max(cols[0] - pad_x, 0)
    right = min(cols[-1] + pad_x + 1, width)
    return image[top:bottom, left:right]


def fit_square(image, size, align="center"):
    """縮放成 size 的正方形，內容依 align 置中或貼底，空白處透明"""
    height, width = image.shape[:2]
    scale = size / max(height, width)
    out_h = max(int(round(height * scale)), 1)
    out_w = max(int(round(width * scale)), 1)
    scaled = resize(image, out_h, out_w)
    result = np.zeros((size, size, 4), dtype=np.float32)
    left = (size - out_w) // 2
    top = size - out_h if align == "bottom" else (size - out_h) // 2
    result[top:top + out_h, left:left + out_w] = scaled
    return result


def grade_card(image, **settings):
    """有透明的卡片只調顏色通道，alpha 原樣保留"""
    result = image.copy()
    result[..., :3] = grade(image[..., :3], **settings)
    result[..., 3] = image[..., 3]
    return result


def write_import(png_path, compressed, mipmaps=True):
    """
    寫 Godot 的 .import。路徑雜湊照 Godot 的規則：res 路徑的 md5。
    既有檔案的 uid 保留，Godot 才不會覺得是新資源；沒有 uid 時 Godot 匯入會自己補
    """
    relative = os.path.relpath(png_path, config.PROJECT_ROOT).replace(os.sep, "/")
    res_path = "res://" + relative
    digest = hashlib.md5(res_path.encode("utf-8")).hexdigest()
    name = os.path.basename(png_path)
    import_path = png_path + ".import"
    uid_line = ""
    if os.path.exists(import_path):
        with open(import_path, "r", encoding="utf-8") as handle:
            match = re.search(r'^uid="(uid://[^"]+)"', handle.read(), re.MULTILINE)
        if match:
            uid_line = 'uid="%s"\n' % match.group(1)
    dest = "res://.godot/imported/%s-%s.ctex" % (name, digest)
    text = (
        "[remap]\n\n"
        'importer="texture"\n'
        'type="CompressedTexture2D"\n'
        "%s"
        'path="%s"\n'
        "metadata={\n"
        '"vram_texture": %s\n'
        "}\n\n"
        "[deps]\n\n"
        'source_file="%s"\n'
        'dest_files=["%s"]\n\n'
        "[params]\n\n"
        "compress/mode=%d\n"
        "compress/high_quality=false\n"
        "compress/lossy_quality=0.7\n"
        "compress/uastc_level=0\n"
        "compress/rdo_quality_loss=0.0\n"
        "compress/hdr_compression=1\n"
        "compress/normal_map=0\n"
        "compress/channel_pack=0\n"
        "mipmaps/generate=%s\n"
        "mipmaps/limit=-1\n"
        "roughness/mode=0\n"
        'roughness/src_normal=""\n'
        "process/channel_remap/red=0\n"
        "process/channel_remap/green=1\n"
        "process/channel_remap/blue=2\n"
        "process/channel_remap/alpha=3\n"
        "process/fix_alpha_border=true\n"
        "process/premult_alpha=false\n"
        "process/normal_map_invert_y=false\n"
        "process/hdr_as_srgb=false\n"
        "process/hdr_clamp_exposure=false\n"
        "process/size_limit=0\n"
        "detect_3d/compress_to=0\n"
    ) % (uid_line, dest, "true" if compressed else "false", res_path, dest,
         2 if compressed else 0, "true" if mipmaps else "false")
    with open(import_path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return import_path


def _save(image, name, compressed):
    path = os.path.join(TEXTURES_OUT, name + ".png")
    atlas.save_png(np.clip(image, 0.0, 1.0), path)
    write_import(path, compressed)
    return path


def build_tiles():
    outputs = []
    for name, spec in TILES.items():
        image = atlas.load_png(os.path.join(RAW_DIR, name + ".png"))
        result = make_tileable(image)
        result[..., :3] = grade(result[..., :3], gain=spec["gain"], saturation=spec["saturation"],
                                warm=spec["warm"], contrast=spec.get("contrast", 1.0))
        result[..., 3] = 1.0
        factor = result.shape[0] // spec["size"]
        outputs.append(_save(box_down(result, factor), name, compressed=True))
    return outputs


def build_cards():
    outputs = []
    for name, spec in CARDS.items():
        image = atlas.load_png(os.path.join(RAW_DIR, name + ".png"))
        result = fit_square(crop_to_content(image), spec["size"], spec["align"])
        result = grade_card(result, gain=spec["gain"], saturation=spec["saturation"])
        outputs.append(_save(result, name, compressed=False))
    return outputs


def build_decal_atlas():
    sheet = np.zeros((DECAL_CELL * DECAL_ROWS, DECAL_CELL * DECAL_COLUMNS, 4), dtype=np.float32)
    for index, name in enumerate(DECALS):
        image = atlas.load_png(os.path.join(RAW_DIR, "decal_" + name + ".png"))
        cell = fit_square(crop_to_content(image), DECAL_CELL, DECAL_ALIGN.get(name, "bottom"))
        cell = grade_card(cell, **DECAL_GRADE.get(name, dict(gain=1.0, saturation=0.95)))
        row, column = divmod(index, DECAL_COLUMNS)
        sheet[row * DECAL_CELL:(row + 1) * DECAL_CELL, column * DECAL_CELL:(column + 1) * DECAL_CELL] = cell
    return [_save(sheet, "decals", compressed=False)]


def build():
    os.makedirs(TEXTURES_OUT, exist_ok=True)
    return build_tiles() + build_cards() + build_decal_atlas()
