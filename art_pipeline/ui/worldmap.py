"""
產生世界地圖視窗的羊皮紙素材，輸出到 assets/ui/worldmap/。
只靠 Pillow，不需要 Blender，作法和 art_pipeline/ui/skin.py 同一套：
原圖放 art_source/worldmap/raw/，這裡去背、統一色階、縮尺寸、自己寫 .import。

風格參考救世者之樹的世界地圖：一張攤開的舊紙，地點是有框的彩繪徽章，
名字寫在小緞帶上，路是虛線，紙的四角有捲草花紋。
版面不在這裡決定，地點擺在哪由 src/core/world_map.gd 從傳送點算出來，
這裡只負責畫紙、徽章、緞帶、花紋這些零件。

三層明暗是刻意的，玩家一眼就分得出哪裡去過
  彩色徽章   去過的地圖，整顆是上了色的畫
  墨色徽章   沒去過的地圖，同一張畫只留墨線和紙色，像還沒上色的草稿
  淡墨地形   山、樹、丘、水，純裝飾，透明度壓到最低，不會被當成有東西的地方

規則
- 徽章的檔名對應地圖檔的 scene 欄位，多一張 scene 是 forest 的地圖就自動拿到森林徽章，
  對不到就用 emblem_default，不用改程式也不用改這支腳本
- 地形和沒去過的徽章都重新上色成同一套墨色，AI 產圖那層奶油色底光和雜訊會在這裡被洗掉
- 每張圖一併寫 .import：介面貼圖無損、不做 mipmap、不用 VRAM 壓縮

用法：python3 art_pipeline/ui/worldmap.py
"""
import hashlib
import os

from PIL import Image

PIPELINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(PIPELINE_DIR)
RAW_DIR = os.path.join(PROJECT_ROOT, "art_source", "worldmap", "raw")
OUT_DIR = os.path.join(PROJECT_ROOT, "assets", "ui", "worldmap")

# ---- 墨色 ----
# 和 src/ui/ui_theme.gd 的 PAPER_INK 同一個色系，畫在紙上和下半部的字看起來是同一支筆
INK_DARK = (74, 54, 32)
INK_MID = (108, 82, 48)
# 墨色徽章的亮部收在紙色，不用純白，不然會在暖色的紙上浮出來
PAPER_CREAM = (226, 206, 168)

# 把明暗換算成墨色濃度時，比這個亮的完全當成紙，比這個暗的完全當成墨
INK_PAPER_LEVEL = 0.86
INK_SOLID_LEVEL = 0.30

# 地形只是紙上的裝飾，濃度壓到這裡，站在它上面的徽章和字才不會被干擾
TERRAIN_OPACITY = 0.34
# 沒去過的徽章：墨線還看得清楚，但明顯不如上了色的那幾顆
UNVISITED_OPACITY = 0.82
# 線稿的中間調提亮多少，小於 1 就是往紙色收，填色的地方退掉只留線
SKETCH_GAMMA = 0.55

# ---- 每張圖的輸出尺寸 ----
# 紙會被拉成畫布的大小，本來就不是等比例貼上去，所以只要夠大不要糊
PARCHMENT_SIZE = (1024, 682)
CORNER_BOX = 208
COMPASS_BOX = 176
# 緞帶會左右三段拉伸，寬度是設計寬度，兩端的燕尾各佔 BANNER_CAP，中間那段才是寫得下字的平面
BANNER_SIZE = (320, 92)
BANNER_CAP = 66
EMBLEM_BOX = 192
TERRAIN_BOX = 288

# 地形圖章，檔名就是遊戲那邊認得的名字
TERRAIN_NAMES = ["peaks", "woods", "hills", "water"]


def _luminance(pixel):
    return (0.299 * pixel[0] + 0.587 * pixel[1] + 0.114 * pixel[2]) / 255.0


def _lerp(low, high, amount):
    return tuple(int(round(low[i] + (high[i] - low[i]) * amount)) for i in range(3))


def load_raw(name):
    path = os.path.join(RAW_DIR, name + ".png")
    if not os.path.exists(path):
        raise SystemExit("[ui/worldmap] 找不到原圖 %s，先用產圖工具照這支腳本開頭的描述產一張" % path)
    return Image.open(path).convert("RGBA")


def trim(image, floor=8):
    """把四周透明的部分切掉，只留有東西的那一塊"""
    alpha = image.getchannel("A").point(lambda value: 255 if value > floor else 0)
    box = alpha.getbbox()
    return image.crop(box) if box else image


def fit(image, box):
    """等比例縮進一個正方形，長的那一邊剛好是 box"""
    scale = box / float(max(image.size))
    size = (max(1, int(round(image.width * scale))), max(1, int(round(image.height * scale))))
    return image.resize(size, Image.LANCZOS)


def to_ink(image, opacity, paper_level=INK_PAPER_LEVEL):
    """只留墨線：越暗的地方越不透明，紙色的地方整個透掉，顏色重新上成墨色

    AI 產圖的去背只切到外框，框裡那層奶油色底光還在，
    直接貼在紙上會是一塊淺色的雲；改成拿明暗當濃度，留下來的就只有筆畫
    """
    source = image.load()
    out = Image.new("RGBA", image.size, (0, 0, 0, 0))
    target = out.load()
    span = paper_level - INK_SOLID_LEVEL
    for y in range(image.height):
        for x in range(image.width):
            pixel = source[x, y]
            if pixel[3] == 0:
                continue
            strength = (paper_level - _luminance(pixel)) / span
            strength = min(1.0, max(0.0, strength))
            if strength <= 0.0:
                continue
            color = _lerp(INK_MID, INK_DARK, strength)
            alpha = int(round(pixel[3] * strength * opacity))
            target[x, y] = color + (alpha,)
    return out


def to_sepia(image, opacity):
    """整張畫換成墨色和紙色的兩色調，形狀和去背都照原圖

    沒去過的地圖用這一版：同一顆徽章，只是還沒上色

    直接把明暗換成兩色調會糊成一坨，深綠的森林和深灰的洞窟本來就沒幾階明暗；
    所以先把這張圖自己的明暗拉滿整個範圍，再把中間調提亮，
    留下來的深色就只剩線稿，填色的地方退成紙色
    """
    source = image.load()
    levels = []
    for y in range(image.height):
        for x in range(image.width):
            pixel = source[x, y]
            if pixel[3] > 0:
                levels.append(_luminance(pixel))
    if not levels:
        return image
    levels.sort()
    low = levels[int(len(levels) * 0.02)]
    high = levels[int(len(levels) * 0.98)]
    span = max(0.05, high - low)
    out = Image.new("RGBA", image.size, (0, 0, 0, 0))
    target = out.load()
    for y in range(image.height):
        for x in range(image.width):
            pixel = source[x, y]
            if pixel[3] == 0:
                continue
            level = min(1.0, max(0.0, (_luminance(pixel) - low) / span)) ** SKETCH_GAMMA
            target[x, y] = _lerp(INK_DARK, PAPER_CREAM, level) + (int(round(pixel[3] * opacity)),)
    return out


def _hash(name):
    return hashlib.md5(("ui_worldmap/" + name).encode()).hexdigest()


def _uid(name):
    """照 Godot 的 base31 字母做一個固定的 uid，重跑不會變"""
    letters = "abcdefghijklmnopqrstuvwxyz0123456789"
    value = int(_hash(name)[:12], 16)
    out = ""
    for _ in range(12):
        out += letters[value % len(letters)]
        value //= len(letters)
    return "c" + out


IMPORT_TEMPLATE = """[remap]

importer="texture"
type="CompressedTexture2D"
uid="uid://%s"
path="res://.godot/imported/%s.png-%s.ctex"
metadata={
"vram_texture": false
}

[deps]

source_file="res://assets/ui/worldmap/%s.png"
dest_files=["res://.godot/imported/%s.png-%s.ctex"]

[params]

compress/mode=0
compress/high_quality=false
compress/lossy_quality=0.7
compress/hdr_compression=1
compress/normal_map=0
compress/channel_pack=0
mipmaps/generate=false
mipmaps/limit=-1
roughness/mode=0
roughness/src_normal=""
process/channel_remap/red=0
process/channel_remap/green=1
process/channel_remap/blue=2
process/channel_remap/alpha=3
process/fix_alpha_border=true
process/premult_alpha=false
process/normal_map_invert_y=false
process/hdr_as_srgb=false
process/hdr_clamp_exposure=false
process/size_limit=0
detect_3d/compress_to=0
"""


def save(image, name):
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, name + ".png")
    image.save(path)
    digest = _hash(name)
    with open(path + ".import", "w", encoding="utf-8") as handle:
        handle.write(IMPORT_TEMPLATE % (_uid(name), name, digest, name, name, digest))
    print("[ui/worldmap] %s %dx%d" % (name, image.width, image.height))
    return path


def emblem_names():
    """原圖資料夾裡有哪幾顆徽章，檔名對應地圖檔的 scene"""
    names = []
    for file_name in sorted(os.listdir(RAW_DIR)):
        if file_name.startswith("emblem_") and file_name.endswith(".png"):
            names.append(file_name[:-4])
    return names


def build():
    save(load_raw("parchment").convert("RGB").resize(PARCHMENT_SIZE, Image.LANCZOS), "parchment")
    save(fit(trim(load_raw("corner")), CORNER_BOX), "corner")
    save(fit(trim(load_raw("compass")), COMPASS_BOX), "compass")
    # 緞帶是唯一會被拉伸的零件，中間那段本來就是平的，所以直接壓成設計尺寸不等比例
    save(trim(load_raw("banner")).resize(BANNER_SIZE, Image.LANCZOS), "banner")

    for name in emblem_names():
        colored = fit(trim(load_raw(name)), EMBLEM_BOX)
        save(colored, name)
        save(to_sepia(colored, UNVISITED_OPACITY), name + "_ink")

    for name in TERRAIN_NAMES:
        raw = trim(load_raw("terrain_" + name))
        save(to_ink(fit(raw, TERRAIN_BOX), TERRAIN_OPACITY), "terrain_" + name)


if __name__ == "__main__":
    build()
