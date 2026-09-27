# -*- coding: utf-8 -*-
"""圖集輸出的共同規則，契約在 docs/精靈圖規格.md，記憶體的數字在 docs/效能與記憶體.md

三個產圖端 monsters_v2、npcs_v2、characters_v2 都走這裡，規則才不會三份各寫各的。

匯入設定
    彩圖 sheet.png 走高品質 VRAM 壓縮，顯示記憶體變四分之一。
    2026-09-16 量過，桌機的 BC7 和手機的 ASTC 4x4 讓換色查到的色階平均只移動 0.05 格、
    最多 1 格，遊戲大小看不出來。舊規格說一律不准壓縮，那是照 BC3 和 ETC2 的結果訂的。
    遮罩 mask.png 維持無損：它是區域圖，0 和 255 中間沒有值可以壓。

遮罩
    不透明的地方只用到一個通道的遮罩沒有帶任何資訊，那張圖是整隻同一區，不要輸出。
    引擎看到資料夾裡沒有 mask.png 就當成整張都是主要區域，換色一樣有效。
    有兩個以上通道的遮罩縮成整數分之一再存，縮到一格剩 MIN_MASK_FRAME_PX 像素為止。

排版
    固定格子的排法（layout "grid"）一個動作一個方向佔一整列，短的動作右邊留空，浪費三成面積。
    緊密排（layout "packed"）把所有格子接成一條，動作各自記起始格號 start。
    圖用 common.atlas.pack_actions 排，meta 用這裡的 packed_meta 補 start，兩邊同一份來源。
"""

import os

import numpy


# meta 的 layout 欄位，和 src/world/sprite_sheet.gd 的 LAYOUT_* 一樣；沒寫就是 grid
LAYOUT_GRID = "grid"
LAYOUT_PACKED = "packed"


def packed_meta(meta, starts, columns):
    """把 common.atlas.pack_actions 算出來的起始格號寫進 meta，標成緊密排

    meta 是已經填好 frame_size、columns、actions 的字典，actions 每個動作已經有 frames、fps、loop。
    starts 是 pack_actions 回傳的 {名稱: 起始格號}，columns 是一列放幾格。
    回傳新的字典，不改原本那一份。

    起始格號的定義和 src/world/sprite_sheet.gd 的 frame_rect 一樣：
        格號 = start + 方向 × 格數 + 格，欄 = 格號 % columns，列 = 格號 // columns
    緊密排不用 row，所以這裡會把 row 拿掉，免得兩個欄位互相矛盾。
    """
    if set(starts) != set(meta.get("actions", {})):
        raise ValueError("starts 和 meta.actions 的動作對不起來：%s 對 %s"
                         % (sorted(starts), sorted(meta.get("actions", {}))))
    result = dict(meta)
    result["layout"] = LAYOUT_PACKED
    result["columns"] = columns
    result["actions"] = {}
    for name, action in meta["actions"].items():
        packed = {key: value for key, value in action.items() if key != "row"}
        packed["start"] = starts[name]
        result["actions"][name] = packed
    return result


def sheet_rows(actions, direction_count, columns):
    """緊密排的圖集應該有幾列，用來對圖片高度；actions 是已經填好 start 和 frames 的字典"""
    last = 0
    for action in actions.values():
        last = max(last, int(action["start"]) + int(action["frames"]) * direction_count)
    return -(-last // max(columns, 1))


# 所有圖共用的匯入參數，彩圖再用 SHEET_PARAMS 蓋掉壓縮那兩個欄位
BASE_IMPORT_PARAMS = {
    "compress/mode": "0",
    "compress/high_quality": "false",
    "compress/lossy_quality": "0.7",
    "compress/uastc_level": "0",
    "compress/rdo_quality_loss": "0.0",
    "compress/hdr_compression": "1",
    "compress/normal_map": "0",
    "compress/channel_pack": "0",
    "mipmaps/generate": "true",
    "mipmaps/limit": "-1",
    "roughness/mode": "0",
    "roughness/src_normal": '""',
    "process/channel_remap/red": "0",
    "process/channel_remap/green": "1",
    "process/channel_remap/blue": "2",
    "process/channel_remap/alpha": "3",
    "process/fix_alpha_border": "false",
    "process/premult_alpha": "false",
    "process/normal_map_invert_y": "false",
    "process/hdr_as_srgb": "false",
    "process/hdr_clamp_exposure": "false",
    "process/size_limit": "0",
    "detect_3d/compress_to": "0",
}
# 彩圖蓋掉的欄位。high_quality 是 false 的話會退回 BC3 和 ETC2，色階誤差是這兩種的兩三倍
SHEET_PARAMS = {
    "compress/mode": "2",
    "compress/high_quality": "true",
}
SHEET_FILE = "sheet.png"
MASK_FILE = "mask.png"
# 遮罩縮到一格剩幾個像素就不再縮
MIN_MASK_FRAME_PX = 48
# 允許的縮小倍數，由大到小試
MASK_DIVISORS = (4, 2)


# 像素圖集的彩圖：無損、產 mipmap、補透明像素的顏色。壓縮會在硬邊上壓出色塊，所以一律無損；
# 著色器是銳利雙線性，縮到 0.5 倍以下才用 mipmap，雙線性會混到透明像素的顏色，不補邊輪廓外圈會發黑。
# 和 src/dev/fix_sprite_imports.gd 的 PIXEL_PARAMS、PIXEL_MASK_PARAMS 是同一組規則，meta.json 的 filter 是 nearest 的圖集走這條
PIXEL_PARAMS = {
    "compress/mode": "0",
    "compress/high_quality": "false",
    "mipmaps/generate": "true",
    "process/fix_alpha_border": "true",
}
# 像素圖集的遮罩：無損、不產 mipmap，著色器對它取最近點
PIXEL_MASK_PARAMS = {
    "compress/mode": "0",
    "compress/high_quality": "false",
    "mipmaps/generate": "false",
}


def import_params(png_path, pixel=False):
    """這張圖要用哪一組匯入參數：彩圖壓縮、遮罩無損；像素圖集彩圖無損加 mipmap 加補邊，遮罩無損不做 mipmap"""
    params = dict(BASE_IMPORT_PARAMS)
    is_sheet = os.path.basename(png_path) == SHEET_FILE
    if is_sheet:
        params.update(SHEET_PARAMS)
    if pixel:
        params.update(PIXEL_PARAMS if is_sheet else PIXEL_MASK_PARAMS)
    return params


def write_import(png_path, project_root, pixel=False):
    """幫一張圖寫好 Godot 的 .import

    已經有的話只改參數段，保留 Godot 自己填的 uid 和快取路徑，編輯器不會重新配 uid；
    沒有的話寫一份沒有 uid 的，Godot 第一次匯入時會自己補上。
    pixel 是 True 時走像素圖集那組參數，見 PIXEL_PARAMS
    """
    import_path = png_path + ".import"
    res_path = "res://" + os.path.relpath(png_path, project_root).replace(os.sep, "/")
    params_map = import_params(png_path, pixel)
    params = "\n".join("%s=%s" % item for item in params_map.items())
    vram = "true" if params_map["compress/mode"] == "2" else "false"
    if os.path.exists(import_path):
        with open(import_path, encoding="utf-8") as handle:
            text = handle.read()
        head, _, _ = text.partition("[params]")
        # metadata 要跟著壓縮設定走，不然 Godot 會以為快取還是無損的那一份
        head = head.replace('"vram_texture": false', '"vram_texture": %s' % vram)
        head = head.replace('"vram_texture": true', '"vram_texture": %s' % vram)
        rewritten = head + "[params]\n\n" + params + "\n"
        if rewritten != text:
            with open(import_path, "w", encoding="utf-8") as handle:
                handle.write(rewritten)
        return import_path
    with open(import_path, "w", encoding="utf-8") as handle:
        handle.write("[remap]\n\nimporter=\"texture\"\ntype=\"CompressedTexture2D\"\n"
                     "metadata={\n\"vram_texture\": %s\n}\n\n[deps]\n\n"
                     "source_file=\"%s\"\n\n[params]\n\n%s\n" % (vram, res_path, params))
    return import_path


def mask_channels_used(sheet, mask):
    """這張遮罩在彩圖不透明的地方真的用到哪幾個通道，回傳 0 到 2 的索引集合

    透明的地方遮罩值是垃圾，不能算進去
    """
    opaque = sheet[..., 3] > 0.5 if sheet.shape[-1] > 3 else numpy.ones(sheet.shape[:2], bool)
    used = set()
    for channel in range(3):
        if bool(numpy.any(mask[..., channel][opaque] > 0.5)):
            used.add(channel)
    return used


def shrink_mask(mask, divisor):
    """區域圖縮小：每個區塊取平均再判門檻，色塊邊界最多漂一兩個像素"""
    high, wide = mask.shape[0] // divisor, mask.shape[1] // divisor
    trimmed = mask[:high * divisor, :wide * divisor]
    blocks = trimmed.reshape(high, divisor, wide, divisor, mask.shape[-1])
    return blocks.mean(axis=(1, 3))


def mask_divisor(frame_px, mask_shape):
    """這張遮罩可以縮到幾分之一，不能縮回傳 1"""
    for divisor in MASK_DIVISORS:
        if frame_px // divisor < MIN_MASK_FRAME_PX:
            continue
        if mask_shape[0] % divisor or mask_shape[1] % divisor:
            continue
        return divisor
    return 1


def emit_mask(out_dir, sheet, mask, frame_px, save_png, project_root):
    """按規則輸出遮罩，回傳做了什麼：'skipped'、'full' 或 'shrunk/N'

    只用到一個通道就不輸出，順便把上一次留下來的舊檔清掉，
    不然舊的大遮罩會留在資料夾裡繼續佔記憶體
    """
    mask_path = os.path.join(out_dir, MASK_FILE)
    if len(mask_channels_used(sheet, mask)) <= 1:
        for stale in (mask_path, mask_path + ".import"):
            if os.path.exists(stale):
                os.remove(stale)
        return "skipped"
    divisor = mask_divisor(frame_px, mask.shape)
    if divisor > 1:
        mask = shrink_mask(mask, divisor)
    save_png(mask, mask_path, non_color=True)
    write_import(mask_path, project_root)
    return "full" if divisor == 1 else "shrunk/%d" % divisor
