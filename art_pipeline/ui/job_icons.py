"""把使用者畫的職業圖標總表切成 21 個單檔。

來源 art_source/ui/job_icons_raw.png 是白色線稿壓在深灰棋盤格上，
棋盤格是畫進圖裡的不是真透明，所以先用亮度反推透明度再切。
總表的排法就是職業樹：第一列初心者，第二列四個一轉，第三列八個二轉，第四列八個三轉，
每列由左到右對應下面 ORDER 的順序。

輸出 assets/ui/icons/jobs/<職業代號>.png，64x64 白色 RGBA，和其他介面圖示同規格。

用法：python3 art_pipeline/ui/job_icons.py
"""
import os

from PIL import Image

PIPELINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(PIPELINE_DIR)
SOURCE = os.path.join(PROJECT_ROOT, "art_source", "ui", "job_icons_raw.png")
OUT_DIR = os.path.join(PROJECT_ROOT, "assets", "ui", "icons", "jobs")

SIZE = 64
# 圖標本體佔的邊長，四周留白讓圓盤裡不會頂到邊
GLYPH = 54
# 亮度低於這個算底，高於這個算全白，中間漸變當抗鋸齒
DARK = 90
LIGHT = 210

ORDER = [
    ["novice"],
    ["squire", "sorcerer", "scout", "devout"],
    ["holyblade", "bladesman", "wizard", "thaumaturge",
     "hunter", "assassin", "clergy", "ascetic"],
    ["champion", "blademaster", "archsage", "onmyoji",
     "sniper", "ninja", "oracle", "warsaint"],
]


def keyed(image):
    """亮度轉透明度，回傳純白 RGBA。"""
    rgb = image.convert("RGB")
    width, height = rgb.size
    out = Image.new("RGBA", (width, height))
    src = rgb.load()
    dst = out.load()
    span = LIGHT - DARK
    for y in range(height):
        for x in range(width):
            r, g, b = src[x, y]
            lum = (r * 299 + g * 587 + b * 114) // 1000
            alpha = max(0, min(255, (lum - DARK) * 255 // span))
            dst[x, y] = (255, 255, 255, alpha)
    return out


def _runs(values, min_len):
    runs = []
    start = None
    for index, value in enumerate(values):
        if value and start is None:
            start = index
        elif not value and start is not None:
            if index - start >= min_len:
                runs.append([start, index])
            start = None
    if start is not None and len(values) - start >= min_len:
        runs.append([start, len(values)])
    return runs


def row_bands(image):
    """找出每一列圖標佔的縱向範圍，相鄰不到 40 像素的算同一列。"""
    width, height = image.size
    px = image.load()
    filled = [any(px[x, y][3] > 128 for x in range(width)) for y in range(height)]
    bands = []
    for run in _runs(filled, 4):
        if bands and run[0] - bands[-1][1] < 40:
            bands[-1][1] = run[1]
        else:
            bands.append(run)
    return [band for band in bands if band[1] - band[0] > 20]


def row_cells(image, band, count):
    """一列裡切出 count 格。先切出所有不連續的段，再一直把最近的兩段合併到剛好 count 段。
    圖標內部常有斷開的筆畫，用固定間隙門檻切不準，收斂到已知個數最穩。"""
    width = image.size[0]
    px = image.load()
    y0, y1 = band
    filled = [any(px[x, y][3] > 128 for y in range(y0, y1)) for x in range(width)]
    segments = _runs(filled, 4)
    if len(segments) < count:
        raise SystemExit("第 %d~%d 列只找到 %d 段，少於預期的 %d" % (y0, y1, len(segments), count))
    while len(segments) > count:
        gaps = [segments[i + 1][0] - segments[i][1] for i in range(len(segments) - 1)]
        i = gaps.index(min(gaps))
        segments[i][1] = segments[i + 1][1]
        del segments[i + 1]
    return [(x0, y0, x1, y1) for x0, x1 in segments]


def normalize(cell):
    """裁到內容、等比縮到 GLYPH、置中放進 SIZE 的正方形。"""
    cell = cell.crop(cell.getbbox())
    w, h = cell.size
    scale = GLYPH / max(w, h)
    cell = cell.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
    out = Image.new("RGBA", (SIZE, SIZE))
    out.alpha_composite(cell, ((SIZE - cell.size[0]) // 2, (SIZE - cell.size[1]) // 2))
    return out


def build():
    sheet = keyed(Image.open(SOURCE))
    bands = row_bands(sheet)
    if len(bands) != len(ORDER):
        raise SystemExit("總表找到 %d 列，預期 %d 列" % (len(bands), len(ORDER)))
    os.makedirs(OUT_DIR, exist_ok=True)
    written = []
    for band, keys in zip(bands, ORDER):
        for box, key in zip(row_cells(sheet, band, len(keys)), keys):
            path = os.path.join(OUT_DIR, key + ".png")
            normalize(sheet.crop(box)).save(path)
            written.append(path)
    return written


if __name__ == "__main__":
    for path in build():
        print(os.path.relpath(path, PROJECT_ROOT))
