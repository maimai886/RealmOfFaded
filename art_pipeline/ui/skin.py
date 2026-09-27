"""
產生介面皮膚的九宮格貼圖，輸出到 assets/ui/skin/。
全部都是程式畫的，只靠 Pillow，不需要 Blender；裝飾花紋的原圖在 art_source/ui/，
這裡只取它的透明度當遮罩，重新上色並對稱化，所以不會帶進 AI 產圖的雜訊。

採用的風格是 quiet：安靜的現代介面。面板是帶一點暖灰的近白色、透一點點底下的世界，
一條 1 像素的細框加一層柔和的落影把它從畫面上抬起來，標題列是淡藍灰，字是深灰褐。
區段之間靠留白和很淡的細線分開，不靠厚框；強調色只有一個柔和的藍，選取、焦點、勾選都用它。
面板本身不做凹槽也不做金屬，內容區只比面板深一階，淡到幾乎看不出來。

深色那一套青銅暖木留在 PALETTES["dark"] 和名字開頭是 build_ 的那些函式裡，
quiet 的零件是另一組 build_quiet_，兩套共用同一張切邊表所以隨時換得回去。
當初選深色的理由是淺色面板壓在明亮草原上分不出來，quiet 用三件事解掉：
夠高的不透明度讓面板不吃草地的顏色、一條真的框、一層真的影子。實拍比較寫在 docs/美術方向.md 第 5b 節。

規則：
- 每張圖都在 1 倍解析度畫，介面縮放交給 Godot 的 content_scale_factor，1.0 時是像素對齊的
- 邊線一律 1 像素，先用 4 倍超取樣畫圓角和陰影，再把 1 像素的線蓋回去，線才不會糊
- 面板和內框只鋪一層壓到幾乎看不見的手繪織紋，避免大片死平的色塊，但不干擾文字
- 每張圖一併寫 .import：介面貼圖無損、不做 mipmap、不用 VRAM 壓縮

九宮格邊界寫在 SKIN 這張表，src/ui/ui_theme.gd 的 SKIN_BOXES 要跟著一樣，
tests/test_ui_windows.gd 會比對圖檔尺寸擋住兩邊走鐘。
用法：python3 art_pipeline/ui/skin.py [quiet|dark|parchment]
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui import material as mat  # noqa: E402

PIPELINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(PIPELINE_DIR)
SOURCE_DIR = os.path.join(PROJECT_ROOT, "art_source", "ui")
OUT_DIR = os.path.join(PROJECT_ROOT, "assets", "ui", "skin")

# 超取樣倍率，圓角和陰影先放大畫再縮小
SS = 4

# ---- 配色 ----
# quiet 是採用的版本：近白色面板、細框、柔和落影、淡藍灰標題列、一個柔和的藍當強調色
# dark 是上一版的深色暖木配青銅，parchment 是更早比較用的羊皮紙，兩套都留著隨時換得回去
PALETTES = {
    "quiet": {
        # 2026-09-18 使用者看了實際畫面說「視窗要白色就好 不要黃黃的」，
        # 所以面板從暖白改成近乎中性的白：R 減 B 只剩三階、飽和 1%
        # 之前之所以要暖，是因為面板色中性時整片看起來發灰。那個灰的真正原因是
        # 背景權重 38% 太重，已經降到 7% 修掉了，所以現在中性也不會灰
        # 標題列的淡藍和強調色一個都沒動，使用者只嫌黃
        # 上下差九階，極淡但拿掉會覺得扁
        "panel_top": (248, 247, 245),
        "panel_bottom": (243, 242, 240),
        # 2026-09-18 使用者說介面「很像作業系統」，量出來除了藍按鈕全部擠在 228 到 248，
        # 只有二十階。作業系統的介面就是每一塊都差不多亮、靠細線分隔；
        # 遊戲介面是靠深淺分層的。凹陷的東西往下拉，浮起來的維持亮，把落差拉開
        "inset_top": (228, 227, 224),
        "inset_bottom": (220, 219, 216),
        # 框線：面板那一條和更淡的那一條
        "edge": (202, 201, 198),
        "edge_soft": (225, 224, 221),
        # 視窗邊界是一層很薄的深色，壓在什麼上面就跟著變，不是畫上去的灰線
        "hairline": (26, 28, 34),
        # 標題列本身不填色了，這幾個只剩名牌和沒有皮膚圖時的退路在用
        "title_light": (238, 244, 250),
        "title_top": (227, 234, 241),
        "title_bottom": (205, 217, 230),
        "title_edge": (178, 193, 209),
        # 唯一的強調色，選取、焦點、勾選、主要按鈕都用它
        "accent": (93, 129, 168),
        "accent_soft": (169, 195, 221),
        "accent_pale": (222, 233, 245),
        # 主要按鈕的藍面
        "accent_top": (109, 145, 184),
        "accent_bottom": (85, 119, 157),
        "accent_hover_top": (124, 159, 197),
        "accent_hover_bottom": (96, 131, 170),
        "accent_rim": (74, 105, 140),
        # 一般按鈕：比面板亮一階，靠細框和落影站出來
        # 2026-09-18 滑過去的底色本來是 255 幾乎純白，比面板的 244 還白，
        # 等於「用更白的白」表示滑過，而白底上只要字稍微淺一點就整顆消失。
        # 改成明確的淡藍，和主要按鈕同一支色系，深色字在上面對比很夠
        "btn_top": (255, 255, 254),
        "btn_bottom": (240, 239, 236),
        "btn_rim": (178, 177, 173),
        "btn_hover_top": (234, 242, 251),
        "btn_hover_bottom": (219, 232, 246),
        "btn_hover_rim": (146, 175, 205),
        "btn_press_top": (227, 234, 241),
        "btn_press_bottom": (238, 243, 248),
        "btn_dis_top": (244, 243, 241),
        "btn_dis_bottom": (238, 237, 235),
        "btn_dis_rim": (217, 216, 213),
        "btn_gloss": (255, 255, 255),
        # 選取的那一列
        "select_top": (223, 234, 246),
        "select_bottom": (212, 226, 242),
        # 格子往內凹：上面深下面亮，整體比面板深一階
        "slot_top": (203, 202, 198),
        "slot_bottom": (232, 231, 228),
        "slot_hover_top": (219, 231, 244),
        "slot_hover_bottom": (243, 248, 253),
        "slot_rim": (176, 175, 171),
        "slot_glow": (109, 152, 197),
        # 對話框跟著整套走，不再另外做紙面
        "paper_top": (248, 247, 245),
        "paper_bottom": (243, 242, 240),
        "row_top": (252, 247, 237),
        "row_bottom": (247, 242, 231),
        "row_hover_top": (240, 246, 251),
        "row_hover_bottom": (232, 240, 248),
        "row_on_top": (223, 234, 246),
        "row_on_bottom": (210, 225, 241),
        # 數值條的溝，上面深下面亮
        "track_top": (196, 193, 186),
        "track_bottom": (222, 220, 214),
        "track_rim": (168, 166, 160),
        # 提示框比面板再白一階，影子重一點，浮在最上面
        "tip_top": (255, 252, 244),
        "tip_bottom": (251, 246, 236),
        # 影子是冷灰不是黑，壓在草地上才不會髒
        "shadow": (64, 70, 82),
        # 上緣的亮線也要暖，純白壓在暖白面板上會看起來是一條冷線
        "inner_light": (255, 253, 247),
    },
    "dark": {
        # 面板本體，上亮下暗的暖棕
        "panel_top": (62, 52, 42),
        "panel_bottom": (36, 30, 24),
        # 文字區的平靜底板，比本體再深一階
        "inset_top": (29, 24, 19),
        "inset_bottom": (23, 19, 15),
        # 金屬框：最外一圈深線、中間青銅帶、內側亮邊
        "edge": (18, 13, 10),
        "metal_top": (165, 130, 74),
        "metal_bottom": (104, 78, 40),
        "metal_light": (216, 184, 120),
        "metal_dark": (74, 55, 28),
        # 標題列
        "title_top": (85, 65, 42),
        "title_bottom": (48, 37, 25),
        # 格子是凹下去的金屬槽
        "slot_top": (23, 19, 16),
        "slot_bottom": (38, 32, 26),
        "slot_rim": (122, 94, 52),
        "slot_glow": (255, 206, 120),
        # 按鈕
        "btn_top": (110, 88, 54),
        "btn_bottom": (66, 52, 31),
        "btn_light": (202, 167, 104),
        "btn_hover_top": (131, 106, 67),
        "btn_hover_bottom": (84, 67, 42),
        # 按下和被選中的分頁用同一張圖：往下凹但整體偏暖偏亮，一眼看得出是「選中的那個」
        "btn_press_top": (96, 72, 32),
        "btn_press_bottom": (134, 104, 48),
        "btn_dis_top": (58, 51, 43),
        "btn_dis_bottom": (43, 38, 32),
        "btn_dis_rim": (84, 75, 63),
        # 按鈕上半部那條玻璃高光帶的顏色，暖白不是純白
        "btn_gloss": (255, 244, 214),
        # 對話框的紙面：只有對話框用淺色，因為它整塊都是長句子，深底淺字在那個字級糊成一團
        "paper_top": (247, 235, 206),
        "paper_bottom": (226, 208, 172),
        "row_top": (238, 223, 190),
        "row_bottom": (226, 208, 172),
        "row_hover_top": (252, 243, 218),
        "row_hover_bottom": (240, 226, 194),
        "row_on_top": (246, 208, 132),
        "row_on_bottom": (223, 172, 86),
        "accent_top": (150, 112, 47),
        "accent_bottom": (90, 63, 20),
        "accent_hover_top": (176, 133, 60),
        "accent_hover_bottom": (108, 77, 26),
        "accent_rim": (240, 205, 130),
        # 選取
        "select_top": (88, 66, 34),
        "select_bottom": (60, 45, 24),
        # 數值條的金屬槽
        "track_top": (20, 16, 13),
        "track_bottom": (34, 27, 21),
        # 提示框，比面板亮一階才分得開
        "tip_top": (66, 54, 40),
        "tip_bottom": (44, 35, 26),
        "shadow": (12, 8, 6),
        "inner_light": (255, 240, 210),
    },
    "parchment": {
        "panel_top": (238, 224, 194),
        "panel_bottom": (214, 195, 158),
        "inset_top": (250, 241, 220),
        "inset_bottom": (240, 228, 200),
        "edge": (58, 42, 26),
        "metal_top": (165, 130, 74),
        "metal_bottom": (104, 78, 40),
        "metal_light": (232, 206, 152),
        "metal_dark": (88, 64, 32),
        "title_top": (120, 92, 56),
        "title_bottom": (78, 58, 34),
        "slot_top": (196, 176, 140),
        "slot_bottom": (232, 218, 190),
        "slot_rim": (122, 94, 52),
        "slot_glow": (255, 206, 120),
        "btn_top": (246, 234, 208),
        "btn_bottom": (214, 194, 158),
        "btn_light": (255, 250, 236),
        "btn_hover_top": (255, 246, 222),
        "btn_hover_bottom": (228, 208, 170),
        "btn_press_top": (196, 176, 142),
        "btn_press_bottom": (228, 212, 182),
        "btn_dis_top": (226, 218, 202),
        "btn_dis_bottom": (208, 199, 182),
        "btn_dis_rim": (160, 148, 128),
        "btn_gloss": (255, 252, 240),
        # 對話框的紙面：只有對話框用淺色，因為它整塊都是長句子，深底淺字在那個字級糊成一團
        "paper_top": (247, 235, 206),
        "paper_bottom": (226, 208, 172),
        "row_top": (238, 223, 190),
        "row_bottom": (226, 208, 172),
        "row_hover_top": (252, 243, 218),
        "row_hover_bottom": (240, 226, 194),
        "row_on_top": (246, 208, 132),
        "row_on_bottom": (223, 172, 86),
        "accent_top": (150, 112, 47),
        "accent_bottom": (90, 63, 20),
        "accent_hover_top": (176, 133, 60),
        "accent_hover_bottom": (108, 77, 26),
        "accent_rim": (240, 205, 130),
        "select_top": (240, 218, 168),
        "select_bottom": (224, 198, 142),
        "track_top": (20, 16, 13),
        "track_bottom": (34, 27, 21),
        "tip_top": (252, 244, 224),
        "tip_bottom": (240, 228, 198),
        "shadow": (28, 20, 12),
        "inner_light": (255, 252, 240),
    },
}
# 目前用哪一套，build() 可以覆蓋
P = PALETTES["quiet"]

# 每張圖的尺寸和九宮格邊界，margin 是九宮格切邊，expand 是畫到控制項外面的部分
# margin 的四個值是左上右下；這張表和 ui_theme.gd 的 SKIN_BOXES 一樣，改了要一起改
# 面板類的圖比以前大很多，因為中間是鋪磚不是拉伸，材質的顆粒才不會被拉糊
BUTTON_SPEC = {"size": (40, 40), "margin": (12, 11, 12, 13), "expand": (4, 3, 4, 5)}
SLOT_SPEC = {"size": (40, 40), "margin": (12, 12, 12, 12), "expand": (4, 4, 4, 4)}
# 切邊 8 是為了讓中段剛好 32 像素，是紙紋週期的整數倍，鋪磚時不會每隔一段冒出一條橫線
PLATE_SPEC = {"size": (48, 48), "margin": (8, 8, 8, 8), "expand": (0, 0, 0, 0)}

SKIN = {
    # expand 是畫到控制項外面的影子，macOS 那種大而淡的影子要這麼多空間才鋪得開
    # 切邊一定要大於 expand 加圓角，不然圓角會跨過切邊被拉伸糊掉
    "window": {"size": (128, 128), "margin": (48, 47, 48, 49), "expand": (18, 16, 18, 22)},
    # 標題列整片是空的只剩最下面一條分隔線，不再往外畫影子
    # 上切邊要大於標題列的圓角，填色之後上面兩角才收得進視窗的圓角裡
    "titlebar": {"size": (64, 48), "margin": (20, 13, 20, 10), "expand": (0, 0, 0, 0)},
    "hud": {"size": (56, 56), "margin": (16, 15, 16, 17), "expand": (6, 5, 6, 7)},
    "inset": dict(PLATE_SPEC),
    "input": dict(PLATE_SPEC),
    "input_focus": dict(PLATE_SPEC),
    "select": dict(PLATE_SPEC),
    "slot": dict(SLOT_SPEC),
    "slot_hover": dict(SLOT_SPEC),
    "button": dict(BUTTON_SPEC),
    "button_hover": dict(BUTTON_SPEC),
    "button_pressed": dict(BUTTON_SPEC),
    "button_disabled": dict(BUTTON_SPEC),
    "button_accent": dict(BUTTON_SPEC),
    "button_accent_hover": dict(BUTTON_SPEC),
    "button_accent_pressed": dict(BUTTON_SPEC),
    "bar_track": {"size": (24, 12), "margin": (7, 3, 7, 3), "expand": (0, 0, 0, 0)},
    "tooltip": {"size": (48, 48), "margin": (16, 15, 16, 17), "expand": (8, 7, 8, 9)},
    "tab_on": {"size": (32, 32), "margin": (10, 10, 10, 4), "expand": (0, 0, 0, 0)},
    "tab_off": {"size": (32, 32), "margin": (10, 10, 10, 4), "expand": (0, 0, 0, 0)},
    "divider": {"size": (64, 8), "margin": (20, 3, 20, 3), "expand": (0, 0, 0, 0)},
    # 手機全螢幕分頁的底，鋪滿畫面所以沒有框也沒有影子，只有面板色和紙紋
    # 切邊 16 讓中段剛好 16 像素，是紙紋週期的整數倍
    "page": {"size": (48, 48), "margin": (16, 16, 16, 16), "expand": (0, 0, 0, 0)},
    # 對話框自己一套：紙面板、名牌、三種狀態的選項列
    "dialogue": {"size": (128, 128), "margin": (48, 47, 48, 49), "expand": (18, 16, 18, 22)},
    "nameplate": {"size": (48, 40), "margin": (16, 14, 16, 16), "expand": (0, 0, 0, 3)},
    "choice": dict(PLATE_SPEC),
    "choice_hover": dict(PLATE_SPEC),
    "choice_on": dict(PLATE_SPEC),
}
# 不是九宮格的單張圖
PLAIN = {
    "check_off": (16, 16),
    "check_on": (16, 16),
    "emblem": (16, 16),
    "socket_mark": (28, 28),
    "vignette": (256, 256),
    "logo_flourish": (192, 20),
}


# ---- 繪圖工具 ----

def _pil():
    from PIL import Image, ImageDraw, ImageFilter
    return Image, ImageDraw, ImageFilter


def vgrad(size, top, bottom):
    """上下兩色的垂直漸層，回傳不透明的 RGB 圖"""
    Image, ImageDraw, _ = _pil()
    image = Image.new("RGB", size, top)
    draw = ImageDraw.Draw(image)
    height = max(1, size[1] - 1)
    for y in range(size[1]):
        t = y / height
        draw.line([(0, y), (size[0], y)],
                  fill=tuple(int(round(top[i] + (bottom[i] - top[i]) * t)) for i in range(3)))
    return image


def round_mask(size, radius, inset=0.0):
    """圓角矩形的遮罩，用超取樣畫出平滑的邊"""
    Image, ImageDraw, _ = _pil()
    mask = Image.new("L", (size[0] * SS, size[1] * SS), 0)
    draw = ImageDraw.Draw(mask)
    box = [inset * SS, inset * SS, (size[0] - inset) * SS - 1, (size[1] - inset) * SS - 1]
    draw.rounded_rectangle(box, radius=max(0.0, radius - inset) * SS, fill=255)
    return mask.resize(size, Image.LANCZOS)


def fill(size, mask, source):
    """用遮罩把顏色或漸層貼成一張帶透明度的圖"""
    Image, _, _ = _pil()
    layer = Image.new("RGB", size, source) if isinstance(source, tuple) else source
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    out.paste(layer, (0, 0), mask)
    return out


def over(base, layer):
    from PIL import Image
    return Image.alpha_composite(base, layer)


def shadow(size, mask, offset, blur, color, alpha):
    """遮罩形狀的柔和投影"""
    Image, _, ImageFilter = _pil()
    big = Image.new("L", size, 0)
    big.paste(mask, offset)
    big = big.filter(ImageFilter.GaussianBlur(blur))
    big = big.point(lambda v: int(v * alpha))
    return fill(size, big, color)


def tint(mask, color, alpha=1.0):
    """把灰階遮罩上色，alpha 再整體壓一次"""
    Image, _, _ = _pil()
    layer = Image.new("RGBA", mask.size, color + (0,))
    layer.putalpha(mask.point(lambda v: int(v * alpha)))
    return layer


def _stroke(image, paint, color, alpha):
    """在一張透明的暫存層上畫線再疊回去
    Pillow 對 RGBA 圖直接畫線是覆蓋不是混合，會把底下的材質連同透明度一起蓋掉，所以一定要走這裡"""
    Image, ImageDraw, _ = _pil()
    if alpha <= 0:
        return
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    paint(ImageDraw.Draw(layer), tuple(color) + (int(alpha),))
    image.alpha_composite(layer)


def hline(image, y, x0, x1, color, alpha=255):
    _stroke(image, lambda draw, ink: draw.line([(x0, y), (x1, y)], fill=ink), color, alpha)


def vline(image, x, y0, y1, color, alpha=255):
    _stroke(image, lambda draw, ink: draw.line([(x, y0), (x, y1)], fill=ink), color, alpha)


def frame_1px(image, box, radius, color, alpha=255):
    """1 像素的圓角外框，直接畫不超取樣，線才是實心的"""
    _stroke(image, lambda draw, ink: draw.rounded_rectangle(box, radius=radius, outline=ink, width=1),
            color, alpha)


def inner_shade(image, rect, depth, color, alpha):
    """從四邊往內漸弱的暗角，大面板中間才不會空得像一塊色板"""
    for step in range(depth):
        strength = int(alpha * (1.0 - step / float(depth)))
        if strength <= 0:
            continue
        hline(image, rect[1] + step, rect[0] + step, rect[2] - 1 - step, color, strength)
        hline(image, rect[3] - 1 - step, rect[0] + step, rect[2] - 1 - step, color, strength)
        vline(image, rect[0] + step, rect[1] + step, rect[3] - 1 - step, color, strength)
        vline(image, rect[2] - 1 - step, rect[1] + step, rect[3] - 1 - step, color, strength)


def metal_frame(image, rect, radius, thickness=3):
    """有厚度的金屬框：最外一圈深線、中間青銅帶、內側再一條深線
    上緣那一條偏亮、下緣偏暗，看起來是一圈有受光的金屬"""
    left, top, right, bottom = rect[0], rect[1], rect[2] - 1, rect[3] - 1
    frame_1px(image, [left, top, right, bottom], radius, P["edge"], 255)
    band = max(1, thickness - 1)
    for step in range(1, 1 + band):
        frame_1px(image, [left + step, top + step, right - step, bottom - step],
                  max(0, radius - step), P["metal_top"], 255)
    # 上緣受光、下緣背光，一圈金屬才有方向感
    hline(image, top + 1, left + 1 + radius, right - 1 - radius, P["metal_light"], 255)
    hline(image, bottom - 1, left + 1 + radius, right - 1 - radius, P["metal_dark"], 255)
    vline(image, left + 1, top + 1 + radius, bottom - 1 - radius, P["metal_light"], 170)
    vline(image, right - 1, top + 1 + radius, bottom - 1 - radius, P["metal_dark"], 200)
    # 金屬帶內側再壓一條深線，框和面板之間有交界
    frame_1px(image, [left + thickness, top + thickness, right - thickness, bottom - thickness],
              max(0, radius - thickness), P["edge"], 235)


def corner_plates(image, rect, length=10, thickness=5):
    """四個角的金屬角片：框在角落加厚一段，中間一顆小鉚釘，四角完全對稱"""
    _, ImageDraw, _ = _pil()
    draw = ImageDraw.Draw(image, "RGBA")
    for corner_x in (0, 1):
        for corner_y in (0, 1):
            x0 = rect[2] - thickness if corner_x else rect[0]
            y0 = rect[3] - thickness if corner_y else rect[1]
            arm_x = rect[2] - length if corner_x else rect[0]
            arm_y = rect[3] - length if corner_y else rect[1]
            draw.rectangle([arm_x, y0, arm_x + length - 1, y0 + thickness - 1], fill=P["metal_top"] + (255,))
            draw.rectangle([x0, arm_y, x0 + thickness - 1, arm_y + length - 1], fill=P["metal_top"] + (255,))
            # 角片本身的受光邊和背光邊，還有外圈的深色描邊
            lit = P["metal_light"] if not corner_y else P["metal_dark"]
            hline(image, y0 if not corner_y else y0 + thickness - 1, arm_x, arm_x + length - 1, lit, 255)
            lit_side = P["metal_light"] if not corner_x else P["metal_dark"]
            vline(image, x0 if not corner_x else x0 + thickness - 1, arm_y, arm_y + length - 1, lit_side, 210)
            # 內側收一條深線，角片和面板分得開
            inner_y = y0 + thickness if not corner_y else y0 - 1
            hline(image, inner_y, arm_x, arm_x + length - 1, P["edge"], 200)
            inner_x = x0 + thickness if not corner_x else x0 - 1
            vline(image, inner_x, arm_y, arm_y + length - 1, P["edge"], 200)
            # 鉚釘
            rivet = (x0 + thickness // 2, y0 + thickness // 2)
            draw.point(rivet, fill=P["metal_light"] + (255,))
            draw.point((rivet[0] + (1 if not corner_x else -1), rivet[1] + (1 if not corner_y else -1)),
                       fill=P["edge"] + (190,))


# ---- 裝飾花紋 ----

def _mask_from_source(name, size, symmetry="", threshold=0):
    """讀 art_source/ui 的原圖，只取透明度當形狀，裁到內容範圍、對稱化再縮到目標大小"""
    Image, _, _ = _pil()
    path = os.path.join(SOURCE_DIR, name)
    if not os.path.exists(path):
        return None
    source = Image.open(path).convert("RGBA").getchannel("A")
    # 原圖邊緣有很淡的光暈，先切掉低於門檻的部分，形狀才乾淨
    source = source.point(lambda v: 0 if v < 110 else min(255, int((v - 110) * 255 / 145)))
    box = source.getbbox()
    if box is None:
        return None
    source = source.crop(box)
    side = max(source.size)
    square = Image.new("L", (side, side), 0)
    square.paste(source, ((side - source.size[0]) // 2, (side - source.size[1]) // 2))
    from PIL import ImageChops
    if symmetry == "horizontal":
        square = ImageChops.lighter(square, square.transpose(Image.FLIP_LEFT_RIGHT))
    elif symmetry == "diagonal":
        square = ImageChops.lighter(square, square.transpose(Image.TRANSPOSE))
    small = square.resize(size, Image.LANCZOS)
    if threshold > 0:
        # 縮到只剩十幾個像素後灰邊會糊成一團，切成實心的形狀才看得出是花紋
        small = small.point(lambda v: 0 if v < threshold else 255)
    return small


# ---- 手繪材質 ----

## 哪一塊用哪一張手繪材質，以及要壓到什麼明暗之間
MATERIALS = {
    "panel": ("mat_leather_raw.png", "panel_bottom", "panel_top", 1.0, 0.85),
    "wood": ("mat_wood_raw.png", "title_bottom", "title_top", 1.0, 0.9),
    "bronze": ("mat_bronze_raw.png", "metal_bottom", "metal_light", 1.0, 1.35),
    "cloth": ("mat_cloth_raw.png", "inset_bottom", "inset_top", 1.0, 1.0),
}


def surface(kind, size, dark_key=None, light_key=None):
    """一塊上好色的手繪材質；dark_key、light_key 可以蓋掉預設的明暗，同一張圖就能做出不同部件"""
    name, dark, light, gamma, contrast = MATERIALS[kind]
    return mat.material(name, size, P[dark_key or dark], P[light_key or light], gamma, contrast)


def paste_surface(out, kind, rect, dark_key=None, light_key=None, mask=None):
    """把材質貼進 out 的某個範圍，mask 給了就只貼遮罩內的部分"""
    Image, _, _ = _pil()
    size = (max(1, rect[2] - rect[0]), max(1, rect[3] - rect[1]))
    patch = surface(kind, size, dark_key, light_key).convert("RGBA")
    if mask is None:
        out.paste(patch, (rect[0], rect[1]))
    else:
        out.paste(patch, (rect[0], rect[1]), mask.crop((rect[0], rect[1], rect[2], rect[3])))
    return out


def ornament(name, size, symmetry=""):
    """手繪的青銅零件：去背、裁到內容、縮到目標大小；symmetry 為 diagonal 時沿對角線對稱化"""
    Image, _, _ = _pil()
    source = mat.load_source(name)
    if source is None:
        return None
    piece = mat.trim(source)
    if symmetry == "diagonal":
        side = max(piece.size)
        square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        square.paste(piece, (0, 0))
        square = Image.alpha_composite(square, square.transpose(Image.TRANSPOSE))
        piece = square
    return piece.resize(size, Image.LANCZOS)


# ---- 各張皮膚 ----

def build_window(spec, ornament_corners=True, body_alpha=255, band=6, corner=22,
                 dark_key=None, light_key=None, shade_alpha=90):
    """視窗框：手繪皮革面板、內縮暗角、手繪青銅框帶、四角手繪捲葉花紋、外面一圈深投影"""
    Image, _, _ = _pil()
    size = spec["size"]
    pad_l, pad_t, pad_r, pad_b = spec["expand"]
    rect = (pad_l, pad_t, size[0] - pad_r, size[1] - pad_b)
    inner = (rect[2] - rect[0], rect[3] - rect[1])
    radius = 3

    body_mask = Image.new("L", size, 0)
    body_mask.paste(round_mask(inner, radius), (rect[0], rect[1]))
    out = shadow(size, body_mask, (0, 3), 3.2, P["shadow"], 0.60)

    face = Image.new("RGBA", size, (0, 0, 0, 0))
    paste_surface(face, "panel", rect, dark_key=dark_key, light_key=light_key, mask=body_mask)
    if body_alpha < 255:
        face.putalpha(face.getchannel("A").point(lambda v: int(v * body_alpha / 255)))
    out = over(out, face)
    # 面板內側一圈暗角，中間亮四周沉
    inner_shade(out, (rect[0] + band, rect[1] + band, rect[2] - band, rect[3] - band), 7, P["shadow"], shade_alpha)

    # 青銅框帶，四條邊各貼一塊材質再收邊
    band_mask = Image.new("L", size, 0)
    band_mask.paste(round_mask(inner, radius), (rect[0], rect[1]))
    hole = Image.new("L", size, 0)
    hole.paste(round_mask((inner[0] - band * 2, inner[1] - band * 2), max(0, radius - 1)),
               (rect[0] + band, rect[1] + band))
    from PIL import ImageChops
    band_mask = ImageChops.subtract(band_mask, hole)
    metal = Image.new("RGBA", size, (0, 0, 0, 0))
    paste_surface(metal, "bronze", rect, mask=band_mask)
    out = over(out, metal)
    # 上緣受光、下緣背光、內外各一條深線，金屬才有厚度
    hline(out, rect[1], rect[0] + radius, rect[2] - 1 - radius, P["metal_light"], 235)
    hline(out, rect[3] - 1, rect[0] + radius, rect[2] - 1 - radius, P["edge"], 235)
    frame_1px(out, [rect[0], rect[1], rect[2] - 1, rect[3] - 1], radius, P["edge"], 255)
    frame_1px(out, [rect[0] + 1, rect[1] + 1, rect[2] - 2, rect[3] - 2], radius - 1, P["metal_light"], 90)
    frame_1px(out, [rect[0] + band - 1, rect[1] + band - 1, rect[2] - band, rect[3] - band],
              max(0, radius - 1), P["edge"], 235)

    if ornament_corners:
        # 上面兩角會被標題列蓋住，所以畫在標題列那張圖上，視窗只放下面兩角
        piece = ornament("orn_filigree_raw.png", (corner,) * 2, "diagonal")
        if piece is not None:
            piece = piece.transpose(Image.FLIP_TOP_BOTTOM)
            for flip_x in (False, True):
                stamp = piece.transpose(Image.FLIP_LEFT_RIGHT) if flip_x else piece
                x = rect[2] - stamp.size[0] if flip_x else rect[0]
                layer = Image.new("RGBA", size, (0, 0, 0, 0))
                layer.paste(stamp, (x, rect[3] - stamp.size[1]))
                layer.putalpha(layer.getchannel("A").point(lambda v: int(v * 0.86)))
                out = over(out, layer)
    return out


def build_titlebar(spec):
    """標題列：手繪木頭的帶子、上緣受光、下面一條青銅細線，再往下一段內陰影落在面板上
    內陰影畫在 expand 的範圍裡，所以不會吃掉標題文字的空間"""
    Image, ImageDraw, _ = _pil()
    size = spec["size"]
    drop = spec["expand"][3]
    bottom = size[1] - drop
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    paste_surface(out, "wood", (0, 0, size[0], bottom))
    hline(out, 0, 0, size[0] - 1, P["metal_light"], 130)
    hline(out, 1, 0, size[0] - 1, P["metal_top"], 60)
    # 青銅材質的細裝飾線，上緣受光下緣壓深
    bar = Image.new("RGBA", size, (0, 0, 0, 0))
    bar_mask = Image.new("L", size, 0)
    ImageDraw.Draw(bar_mask).rectangle([0, bottom - 3, size[0] - 1, bottom - 1], fill=255)
    paste_surface(bar, "bronze", (0, bottom - 3, size[0], bottom), "metal_bottom", "metal_light",
                  mask=bar_mask)
    out = over(out, bar)
    hline(out, bottom - 4, 0, size[0] - 1, P["edge"], 220)
    hline(out, bottom - 3, 0, size[0] - 1, P["metal_light"], 200)
    # 兩端各一個手繪捲葉角花，和視窗下面兩角是同一個零件
    corner = min(spec["margin"][0] - 2, bottom - 4)
    piece = ornament("orn_filigree_raw.png", (corner,) * 2, "diagonal")
    if piece is not None:
        layer = Image.new("RGBA", size, (0, 0, 0, 0))
        layer.paste(piece, (0, 0))
        layer.paste(piece.transpose(Image.FLIP_LEFT_RIGHT), (size[0] - corner, 0))
        layer.putalpha(layer.getchannel("A").point(lambda v: int(v * 0.8)))
        out = over(out, layer)
    # 標題列下面一段往下漸弱的內陰影，看起來壓在面板上面
    for step in range(drop):
        hline(out, bottom + step, 0, size[0] - 1, P["shadow"], int(190 * (1.0 - step / float(drop))))
    return out


def build_button(spec, dark_key, light_key, pressed=False, drop=True, glow=None, rim=None,
                 kind="bronze", gloss=54):
    """按鈕：手繪金屬面、上緣一條受光、下緣壓深、外面一圈落影，上半部再加一條玻璃高光帶

    高光帶是「透明感」的來源：上半部亮、往下很快淡掉。
    配上 ui_theme 讓整顆按鈕透一點點，底下面板的木紋和世界的顏色會透上來，
    看起來是一塊有厚度的玻璃，不是貼在畫面上的實心色塊。
    按下去的那一張不加，凹下去的東西不會有這條高光。
    """
    Image, _, _ = _pil()
    size = spec["size"]
    pad_l, pad_t, pad_r, pad_b = spec["expand"]
    rect = (pad_l, pad_t, size[0] - pad_r, size[1] - pad_b)
    inner = (rect[2] - rect[0], rect[3] - rect[1])
    radius = 3

    body_mask = Image.new("L", size, 0)
    body_mask.paste(round_mask(inner, radius), (rect[0], rect[1]))
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    if glow:
        out = over(out, shadow(size, body_mask, (0, 0), 2.6, glow, 0.7))
    if drop:
        out = over(out, shadow(size, body_mask, (0, 2), 1.9, P["shadow"], 0.6))
    face = Image.new("RGBA", size, (0, 0, 0, 0))
    paste_surface(face, kind, rect, dark_key, light_key, mask=body_mask)
    out = over(out, face)
    # 面上再壓一層上亮下暗，金屬才有弧度
    for step in range(inner[1]):
        t = step / max(1, inner[1] - 1)
        if t < 0.5:
            hline(out, rect[1] + step, rect[0] + 1, rect[2] - 2, P["metal_light"], int(46 * (1.0 - t * 2.0)))
        else:
            hline(out, rect[1] + step, rect[0] + 1, rect[2] - 2, P["shadow"], int(52 * (t - 0.5) * 2.0))
    if pressed:
        for index, strength in enumerate((190, 110, 50)):
            hline(out, rect[1] + 1 + index, rect[0] + 1, rect[2] - 2, P["shadow"], strength)
        hline(out, rect[3] - 2, rect[0] + 1, rect[2] - 2, P["metal_light"], 110)
    else:
        # 上半部的玻璃高光帶，從第二列開始，往下用 1.7 次方淡掉，收得比線性快才不會糊成一片白
        band = max(int(round(inner[1] * 0.46)), 1)
        for step in range(band):
            t = step / max(1, band - 1)
            hline(out, rect[1] + 2 + step, rect[0] + 2, rect[2] - 3, P["btn_gloss"],
                  int(gloss * pow(1.0 - t, 1.7)))
        hline(out, rect[1] + 1, rect[0] + 1, rect[2] - 2, P["metal_light"], 225)
        hline(out, rect[3] - 2, rect[0] + 1, rect[2] - 2, P["edge"], 150)
    frame_1px(out, [rect[0], rect[1], rect[2] - 1, rect[3] - 1], radius, rim or P["metal_bottom"], 255)
    return out


def build_plate(spec, dark_key, light_key, rim, sunken=True, glow=None, kind="cloth"):
    """內框、輸入框、選取列這類平平的底板：手繪粗布底，文字就落在這上面，所以維持平靜"""
    Image, _, _ = _pil()
    size = spec["size"]
    radius = 2
    mask = round_mask(size, radius)
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    if glow:
        out = over(out, shadow(size, mask, (0, 0), 2.2, glow, 0.55))
    face = Image.new("RGBA", size, (0, 0, 0, 0))
    paste_surface(face, kind, (0, 0, size[0], size[1]), dark_key, light_key, mask=mask)
    out = over(out, face)
    if sunken:
        hline(out, 1, 1, size[0] - 2, P["shadow"], 170)
        hline(out, 2, 1, size[0] - 2, P["shadow"], 70)
        hline(out, size[1] - 2, 1, size[0] - 2, P["metal_light"], 70)
    frame_1px(out, [0, 0, size[0] - 1, size[1] - 1], radius, rim, 255)
    return out


def build_slot(spec, hover=False):
    """道具格：手繪粗布底的凹槽、三層上緣內陰影、下緣受光、一圈手繪青銅槽緣"""
    Image, _, _ = _pil()
    size = spec["size"]
    pad_l, pad_t, pad_r, pad_b = spec["expand"]
    rect = (pad_l, pad_t, size[0] - pad_r, size[1] - pad_b)
    inner = (rect[2] - rect[0], rect[3] - rect[1])
    radius = 2

    body_mask = Image.new("L", size, 0)
    body_mask.paste(round_mask(inner, radius), (rect[0], rect[1]))
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    if hover:
        out = over(out, shadow(size, body_mask, (0, 0), 3.0, P["slot_glow"], 1.0))
    face = Image.new("RGBA", size, (0, 0, 0, 0))
    paste_surface(face, "cloth", rect, mask=body_mask)
    out = over(out, face)
    for index, strength in enumerate((200, 120, 56)):
        hline(out, rect[1] + 1 + index, rect[0] + 1, rect[2] - 2, P["shadow"], strength)
    vline(out, rect[0] + 1, rect[1] + 1, rect[3] - 3, P["shadow"], 130)
    hline(out, rect[3] - 2, rect[0] + 1, rect[2] - 2, P["metal_light"], 95)
    # 槽緣是一圈手繪青銅
    from PIL import ImageChops
    rim_mask = Image.new("L", size, 0)
    rim_mask.paste(round_mask(inner, radius), (rect[0], rect[1]))
    hole = Image.new("L", size, 0)
    hole.paste(round_mask((inner[0] - 4, inner[1] - 4), max(0, radius - 1)), (rect[0] + 2, rect[1] + 2))
    rim_mask = ImageChops.subtract(rim_mask, hole)
    metal = Image.new("RGBA", size, (0, 0, 0, 0))
    paste_surface(metal, "bronze", rect, "slot_rim", "metal_light" if hover else "metal_top", mask=rim_mask)
    out = over(out, metal)
    hline(out, rect[1], rect[0] + radius, rect[2] - 1 - radius, P["metal_light"], 200 if hover else 120)
    frame_1px(out, [rect[0], rect[1], rect[2] - 1, rect[3] - 1], radius,
              P["accent_rim"] if hover else P["edge"], 255)
    return out


def build_bar_track(spec):
    """數值條的金屬槽：兩端各一段手繪青銅端帽，中間是深色的溝"""
    Image, _, _ = _pil()
    size = spec["size"]
    radius = 2
    mask = round_mask(size, radius)
    out = fill(size, mask, vgrad(size, P["track_top"], P["track_bottom"]))
    hline(out, 1, 1, size[0] - 2, P["shadow"], 210)
    hline(out, 2, 1, size[0] - 2, P["shadow"], 100)
    hline(out, size[1] - 2, 1, size[0] - 2, P["metal_top"], 120)
    cap = 4
    for side in (0, 1):
        x0 = size[0] - cap - 1 if side else 1
        patch = Image.new("RGBA", size, (0, 0, 0, 0))
        cap_mask = Image.new("L", size, 0)
        cap_mask.paste(mask.crop((x0, 0, x0 + cap, size[1])), (x0, 0))
        paste_surface(patch, "bronze", (x0, 1, x0 + cap, size[1] - 1), "metal_dark", "metal_light",
                      mask=cap_mask)
        out = over(out, patch)
    frame_1px(out, [0, 0, size[0] - 1, size[1] - 1], radius, P["edge"], 255)
    return out


def build_tooltip(spec):
    Image, _, _ = _pil()
    size = spec["size"]
    pad_l, pad_t, pad_r, pad_b = spec["expand"]
    rect = (pad_l, pad_t, size[0] - pad_r, size[1] - pad_b)
    inner = (rect[2] - rect[0], rect[3] - rect[1])
    radius = 2
    body_mask = Image.new("L", size, 0)
    body_mask.paste(round_mask(inner, radius), (rect[0], rect[1]))
    out = shadow(size, body_mask, (0, 2), 2.6, P["shadow"], 0.65)
    face = Image.new("RGBA", size, (0, 0, 0, 0))
    paste_surface(face, "panel", rect, "tip_bottom", "tip_top", mask=body_mask)
    out = over(out, face)
    inner_shade(out, (rect[0] + 2, rect[1] + 2, rect[2] - 2, rect[3] - 2), 4, P["shadow"], 60)
    hline(out, rect[1] + 1, rect[0] + 1, rect[2] - 2, P["metal_light"], 120)
    frame_1px(out, [rect[0], rect[1], rect[2] - 1, rect[3] - 1], radius, P["metal_top"], 255)
    frame_1px(out, [rect[0] - 1, rect[1] - 1, rect[2], rect[3]], radius + 1, P["edge"], 200)
    return out


def build_tab(spec, selected):
    Image, _, _ = _pil()
    size = spec["size"]
    radius = 2
    mask = round_mask((size[0], size[1] + radius), radius).crop((0, 0, size[0], size[1]))
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    if selected:
        paste_surface(out, "wood", (0, 0, size[0], size[1]), mask=mask)
    else:
        paste_surface(out, "panel", (0, 0, size[0], size[1]), "inset_bottom", "panel_bottom", mask=mask)
    frame_1px(out, [0, 0, size[0] - 1, size[1] + radius], radius, P["edge"], 255)
    if selected:
        hline(out, 0, 2, size[0] - 3, P["metal_top"], 255)
        hline(out, 1, 2, size[0] - 3, P["metal_light"], 170)
    else:
        hline(out, 0, 2, size[0] - 3, P["metal_dark"], 190)
        hline(out, size[1] - 1, 0, size[0] - 1, P["edge"], 255)
    return out


def build_nameplate(spec):
    """名牌：一塊青銅小牌子，上緣受光下緣壓深，掛在對話框上緣當說話者的名字底"""
    Image, _, _ = _pil()
    size = spec["size"]
    pad_l, pad_t, pad_r, pad_b = spec["expand"]
    rect = (pad_l, pad_t, size[0] - pad_r, size[1] - pad_b)
    inner = (rect[2] - rect[0], rect[3] - rect[1])
    radius = 3
    mask = Image.new("L", size, 0)
    mask.paste(round_mask(inner, radius), (rect[0], rect[1]))
    out = shadow(size, mask, (0, 2), 2.4, P["shadow"], 0.55)
    face = Image.new("RGBA", size, (0, 0, 0, 0))
    paste_surface(face, "bronze", rect, dark_key="title_bottom", light_key="title_top", mask=mask)
    out = over(out, face)
    hline(out, rect[1] + 1, rect[0] + radius, rect[2] - 1 - radius, P["metal_light"], 210)
    hline(out, rect[3] - 2, rect[0] + radius, rect[2] - 1 - radius, P["edge"], 170)
    frame_1px(out, [rect[0], rect[1], rect[2] - 1, rect[3] - 1], radius, P["metal_top"], 255)
    return out


def build_divider(spec):
    """段落之間的裝飾線：兩端是手繪青銅端頭，中間一條青銅細條，中間那段拉長端頭也不會變形"""
    Image, ImageDraw, _ = _pil()
    size = spec["size"]
    cap = spec["margin"][0]
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    mid = size[1] // 2
    bar = Image.new("RGBA", size, (0, 0, 0, 0))
    bar_mask = Image.new("L", size, 0)
    ImageDraw.Draw(bar_mask).rectangle([0, mid - 1, size[0] - 1, mid], fill=255)
    paste_surface(bar, "bronze", (0, mid - 1, size[0], mid + 1), "metal_bottom", "metal_light", mask=bar_mask)
    out = over(out, bar)
    hline(out, mid - 2, 0, size[0] - 1, P["edge"], 150)
    hline(out, mid + 1, 0, size[0] - 1, P["edge"], 190)
    # 手繪端頭：取原圖最左邊那一段，縮成端頭大小，右邊鏡射
    source = mat.load_source("orn_rule_raw.png")
    if source is not None:
        piece = mat.trim(source)
        end = piece.crop((0, 0, max(4, int(piece.size[0] * 0.10)), piece.size[1]))
        end = end.resize((cap, size[1]), Image.LANCZOS)
        layer = Image.new("RGBA", size, (0, 0, 0, 0))
        layer.paste(end, (0, 0))
        layer.paste(end.transpose(Image.FLIP_LEFT_RIGHT), (size[0] - cap, 0))
        out = over(out, layer)
    return out


def build_check(size, checked):
    """勾選框：凹下去的小金屬槽，打勾時是金色的勾"""
    Image, ImageDraw, _ = _pil()
    mask = round_mask(size, 2)
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    paste_surface(out, "cloth", (0, 0, size[0], size[1]), mask=mask)
    hline(out, 1, 1, size[0] - 2, P["shadow"], 200)
    hline(out, size[1] - 2, 1, size[0] - 2, P["metal_light"], 90)
    frame_1px(out, [0, 0, size[0] - 1, size[1] - 1], 2, P["slot_rim"], 255)
    if checked:
        big = Image.new("L", (size[0] * SS, size[1] * SS), 0)
        draw = ImageDraw.Draw(big)
        draw.line([(3.4 * SS, 8.0 * SS), (6.6 * SS, 11.2 * SS), (12.4 * SS, 4.2 * SS)], fill=255,
                  width=int(2.0 * SS), joint="curve")
        tick = big.resize(size, Image.LANCZOS)
        out = over(out, tint(tick, P["edge"], 0.6))
        out = over(out, tint(tick.point(lambda v: max(0, v - 60)), P["accent_rim"], 1.0))
    return out


def build_emblem(size):
    mask = _mask_from_source("emblem_sprout_raw.png", size, "horizontal", 110)
    if mask is None:
        return None
    return tint(mask, P["metal_light"], 0.98)


def build_socket_mark(size):
    """空格子中間的浮雕記號：只取手繪原圖的刻痕，不留整塊形狀"""
    source = mat.load_source("orn_socket_raw.png")
    if source is None:
        return None
    return mat.engraved(source, size, P["metal_top"], P["edge"], 1.1)


def build_vignette(size):
    """登入和選角背景的暗角，中間透明四角壓暗"""
    Image, _, ImageFilter = _pil()
    from PIL import ImageChops
    mask = Image.new("L", size, 255)
    inner = round_mask((int(size[0] * 0.80), int(size[1] * 0.80)), int(size[0] * 0.30))
    hole = Image.new("L", size, 0)
    hole.paste(inner, (int(size[0] * 0.10), int(size[1] * 0.10)))
    mask = ImageChops.subtract(mask, hole)
    mask = mask.filter(ImageFilter.GaussianBlur(size[0] * 0.09))
    mask = mask.point(lambda v: int(v * 0.52))
    return tint(mask, (14, 10, 8), 1.0)


def build_logo_flourish(size):
    """標誌下面那條裝飾線，用手繪的青銅線"""
    return ornament("orn_rule_raw.png", size)


# ---- 安靜的現代皮膚 ----
# 配色是對的，質感靠層次堆出來，不靠飽和度也不靠對比：
# 紙紋、內側暗角、真的落影、格子往內凹、按鈕有上下受光、標題列有漸層和上緣亮線。
# 每一項都用 art_pipeline/tests/test_ui_skin_quiet.py 量，不是用看的。

# 面板和按鈕鋪的紙紋，取手繪織布的高頻細節
QUIET_GRAIN = "mat_cloth_raw.png"
# 紙紋的重複週期，九宮格中段鋪磚時每一塊都接得起來
GRAIN_PERIOD = 16
_grain_cache = {}


def quiet_grain(size, amplitude):
    """一張紙紋圖，值是「這個像素要加減多少亮度」，128 代表不動

    上一版把材質縮小再半透明疊上去，LANCZOS 把 1 像素的顆粒全平均掉，
    量出來相鄰像素差 0.0、峰谷差 1.07，等於沒有紙紋。
    這一版原尺寸裁一塊、只取高頻、鏡射成 16 像素的週期，顆粒留得住，鋪磚也接得起來。
    """
    Image, _, ImageFilter = _pil()
    from PIL import ImageChops, ImageStat
    key = (tuple(size), amplitude)
    if key in _grain_cache:
        return _grain_cache[key]
    source = mat.load_source(QUIET_GRAIN)
    if source is None:
        return None
    half = GRAIN_PERIOD // 2
    gray = source.convert("L")
    centre = (gray.size[0] // 2, gray.size[1] // 2)
    patch = gray.crop((centre[0], centre[1], centre[0] + half, centre[1] + half))
    # 只留高頻：原圖減掉自己的模糊，剩下的就是織紋的顆粒
    high = ImageChops.subtract(patch, patch.filter(ImageFilter.GaussianBlur(1.1)), scale=1, offset=128)
    spread = max(1.0, ImageStat.Stat(high).stddev[0])
    gain = amplitude / spread
    # 尖峰壓在振幅的 2.2 倍以內，不然少數幾顆特別亮的會變成白底上的雜點
    cap = amplitude * 2.2
    high = high.point(lambda v: int(round(128 + max(-cap, min(cap, (v - 128) * gain)))))
    # 鏡射成一塊週期，上下左右接起來都連續
    tile = Image.new("L", (GRAIN_PERIOD, GRAIN_PERIOD), 128)
    tile.paste(high, (0, 0))
    tile.paste(high.transpose(Image.FLIP_LEFT_RIGHT), (half, 0))
    tile.paste(high.transpose(Image.FLIP_TOP_BOTTOM), (0, half))
    tile.paste(high.transpose(Image.ROTATE_180), (half, half))
    out = Image.new("L", size, 128)
    for y in range(0, size[1], GRAIN_PERIOD):
        for x in range(0, size[0], GRAIN_PERIOD):
            out.paste(tile, (x, y))
    _grain_cache[key] = out
    return out


def ramp_grad(size, top, bottom, top_rows, bottom_rows):
    """只在九宮格上下切邊裡面做漸層，中段維持同一個顏色

    直接用整張圖的垂直漸層會出事：中段是鋪磚的，每鋪一次就把那一段漸層重來一次，
    面板上會出現一排等距的橫向明暗帶。實拍在技能視窗的內框看得很清楚，
    量出來內框中段每一列的平均亮度從 +2.4 一路掉到 -2.1，那 4.5 階就是帶子的高度。
    改成上面一段往下收、下面一段往下收、中間完全平，鋪幾次都一樣。
    """
    Image, ImageDraw, _ = _pil()
    middle = tuple(int(round((top[index] + bottom[index]) / 2.0)) for index in range(3))
    image = Image.new("RGB", size, middle)
    draw = ImageDraw.Draw(image)
    flat_end = size[1] - bottom_rows
    for y in range(size[1]):
        if top_rows > 0 and y < top_rows:
            ratio = y / float(top_rows)
            colour = tuple(int(round(top[i] + (middle[i] - top[i]) * ratio)) for i in range(3))
        elif bottom_rows > 0 and y >= flat_end:
            ratio = (y - flat_end) / float(bottom_rows)
            colour = tuple(int(round(middle[i] + (bottom[i] - middle[i]) * ratio)) for i in range(3))
        else:
            continue
        draw.line([(0, y), (size[0], y)], fill=colour)
    return image


def quiet_face(size, top_key, bottom_key, grain=1.3, ramp=None):
    """一塊安靜的面：上下漸層加一層紙紋，grain 是紙紋的亮度振幅
    ramp 給九宮格的上下切邊時漸層只做在切邊裡面，中段是平的，鋪磚才不會出現橫帶"""
    Image, _, _ = _pil()
    from PIL import ImageChops
    if ramp is None:
        base = vgrad(size, P[top_key], P[bottom_key])
    else:
        base = ramp_grad(size, P[top_key], P[bottom_key], ramp[0], ramp[1])
    if grain <= 0:
        return base
    delta = quiet_grain(size, grain)
    if delta is None:
        return base
    return ImageChops.add(base, Image.merge("RGB", (delta, delta, delta)), 1.0, -128)


def hairline_ring(image, rect, radius, alpha):
    """把本體最外面一圈換成半透明的深色細線，不是在上面畫一條實心線

    macOS 的視窗邊界就是一層 8 到 15% 的黑，底下是什麼它就跟著變：
    壓在草地上是一條淡影，壓在暗場裡自己沉下去。畫一條不透明的灰線就永遠是那條灰線。
    所以這裡是「換掉」那一圈的像素連同透明度，不是疊上去。
    """
    Image, _, _ = _pil()
    from PIL import ImageChops
    size = image.size
    inner = (rect[2] - rect[0], rect[3] - rect[1])
    outer = Image.new("L", size, 0)
    outer.paste(round_mask(inner, radius), (rect[0], rect[1]))
    hole = Image.new("L", size, 0)
    hole.paste(round_mask((inner[0] - 2, inner[1] - 2), max(0.0, radius - 1)),
               (rect[0] + 1, rect[1] + 1))
    ring = ImageChops.subtract(outer, hole)
    image.paste(Image.new("RGBA", size, tuple(P["hairline"]) + (alpha,)), (0, 0), ring)


def _cut_out(layer, mask):
    """把本體範圍內的影子挖掉

    面板是半透明的，影子如果留在本體底下，透出來的就是自己的影子不是世界，
    面板會變得灰灰髒髒的，透明度也會對不上設定的數字。
    """
    from PIL import ImageChops
    layer.putalpha(ImageChops.multiply(layer.getchannel("A"), ImageChops.invert(mask)))
    return layer


def _quiet_body(size, rect, radius, top_key, bottom_key, body_alpha, grain=1.3,
                shadow_offset=(0, 6), shadow_blur=8.0, shadow_alpha=0.0, ramp=None,
                contact_alpha=0.0):
    """面板本體：大而淡的落影加一層貼地的短影，再蓋一塊半透明的面，回傳圖和本體遮罩

    影子分兩層是關鍵：只有一層大的會糊成一團看不出邊，只有一層小的又像貼紙。
    大的那層負責「浮在畫面上」，貼地那層負責「和底下的東西有接觸」。
    """
    Image, _, _ = _pil()
    inner = (rect[2] - rect[0], rect[3] - rect[1])
    mask = Image.new("L", size, 0)
    mask.paste(round_mask(inner, radius), (rect[0], rect[1]))
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    if shadow_alpha > 0:
        out = over(out, _cut_out(shadow(size, mask, shadow_offset, shadow_blur,
                                        P["shadow"], shadow_alpha), mask))
    if contact_alpha > 0:
        out = over(out, _cut_out(shadow(size, mask, (0, 1), 1.8, P["shadow"], contact_alpha), mask))
    face = fill(size, mask, quiet_face(size, top_key, bottom_key, grain, ramp))
    if body_alpha < 255:
        face.putalpha(face.getchannel("A").point(lambda v: int(v * body_alpha / 255)))
    return over(out, face), mask


def build_quiet_window(spec, body_alpha=252, radius=11, shadow_alpha=0.34, shadow_blur=8.0,
                       shadow_offset=(0, 6), contact_alpha=0.18, edge_alpha=40,
                       top_key="panel_top", bottom_key="panel_bottom",
                       rim_light=200, grain=1.3):
    """視窗：近白色的面、半透明的 hairline 邊界、上緣內側一條亮線、大而淡的落影

    照 macOS 的視窗做：邊界是一層很薄的黑不是一條灰線，圓角大，影子範圍大但很淡。
    上緣內側那一像素的近白是「有厚度、光從上面來」的來源，所以只有上緣有，下緣和左右都沒有。
    裡面是平的：以前四邊有一圈內側暗角，有了 hairline 和大影子之後那圈只會讓面板邊緣看起來髒。
    """
    size = spec["size"]
    pad_l, pad_t, pad_r, pad_b = spec["expand"]
    rect = (pad_l, pad_t, size[0] - pad_r, size[1] - pad_b)
    out, _ = _quiet_body(size, rect, radius, top_key, bottom_key, body_alpha, grain,
                         shadow_offset=shadow_offset, shadow_blur=shadow_blur,
                         shadow_alpha=shadow_alpha, contact_alpha=contact_alpha,
                         ramp=(spec["margin"][1], spec["margin"][3]))
    if rim_light:
        hline(out, rect[1] + 1, rect[0] + radius, rect[2] - 1 - radius, P["inner_light"], rim_light)
    hairline_ring(out, rect, radius, edge_alpha)
    return out


# 標題列的三個淺藍候選，都是低飽和的冷色，和內容區那條暖軸並排不打架
# soft 幾乎是白中帶藍，mid 中間，clear 稍微明確一點的粉藍
QUIET_TITLE_TONES = {
    "soft": {"top": (243, 247, 252), "bottom": (233, 240, 249), "edge": (206, 219, 234)},
    "mid": {"top": (235, 242, 251), "bottom": (219, 232, 246), "edge": (190, 208, 228)},
    "clear": {"top": (224, 236, 248), "bottom": (202, 222, 241), "edge": (172, 196, 221)},
    # 2026-09-18 面板從暖白改成中性白之後，藍和底色的色相差從 35 階掉到 25 階，
    # 藍看起來被洗掉了。藍本身沒動，是對比沒了，所以再補一個更深的候選
    "deep": {"top": (211, 229, 247), "bottom": (184, 211, 238), "edge": (150, 180, 212)},
}
# 2026-09-17 使用者從三個候選裡挑了 mid，這是定案不是暫定值。
# 2026-09-18 面板改成中性白之後使用者說「視窗上方藍色的部分勒」，以為藍不見了。
# 藍其實一個像素都沒動，是對比沒了：暖白底時藍和底差 35 階，中性白只剩 25 階。
# 又拿 mid、clear、deep 三個在白底下實機比一次，使用者還是選 mid，所以維持原值。
# 另外兩個留著隨時比得回來，跑 python3 art_pipeline/ui/skin.py quiet --title=soft
TITLE_TONE = "mid"


def build_quiet_titlebar(spec):
    """標題列：一整片淺藍，上面兩角跟著視窗圓角收，上緣一條亮線、往下收掉的漸層、底下一條分隔線

    前兩輪一路把填色砍掉，砍過頭了，變成只是視窗最上面一行字。
    使用者要的是那條淡藍回來，而且要好看：淡、乾淨、和暖白的內容區搭得起來。
    太飽和會變成幼稚的水藍，太灰會變回最早那版死板的藍灰，所以三個候選都壓在低飽和。
    上緣亮線、漸層、分隔線這幾樣是前幾輪做對的，加藍色不動它們。
    """
    Image, _, _ = _pil()
    tone = QUIET_TITLE_TONES[TITLE_TONE]
    size = spec["size"]
    bottom = size[1] - 1
    radius = 10
    # 上面兩角圓、下面兩角方：多畫一段再裁掉，下緣才不會跟著收圓
    corner = round_mask((size[0], bottom + radius * 2), radius).crop((0, 0, size[0], bottom))
    mask = Image.new("L", size, 0)
    mask.paste(corner, (0, 0))
    out = fill(size, mask, vgrad(size, tone["top"], tone["bottom"]))
    # 上緣一條亮線，藍帶子才有受光
    hline(out, 0, radius, size[0] - 1 - radius, P["inner_light"], 190)
    hline(out, 1, radius - 1, size[0] - radius, P["inner_light"], 80)
    # 下緣收一條同色深線當和內容區的交界。
    # 2026-09-18 標題列和面板只差八階，整條融在面板裡沒有份量，
    # 所以分隔線從一條加到三條往下散，讓標題列自己有一道厚度
    hline(out, bottom - 3, 0, size[0] - 1, tone["edge"], 110)
    hline(out, bottom - 2, 0, size[0] - 1, tone["edge"], 190)
    hline(out, bottom - 1, 0, size[0] - 1, tone["edge"], 255)
    # 最底那條維持很淡。厚度由上面三條同色深線負責，
    # 這一條變重會讓標題列下面出現一條硬黑線，test_titlebar_keeps_its_highlight... 守著這件事
    hline(out, bottom, 0, size[0] - 1, P["hairline"], 34)
    return out


def build_quiet_button(spec, top_key, bottom_key, rim_key, pressed=False, drop=True,
                       gloss=46, radius=4, grain=1.1):
    """按鈕：上亮下暗的面、上半部一條玻璃高光、下緣一條唇線、外面一圈落影

    浮起和按下的差別量得出來：浮起的上緣比下緣亮，按下的反過來而且上緣有三條內陰影，
    加上內距差一個像素，按下去真的會看到東西往下沉。
    """
    size = spec["size"]
    pad_l, pad_t, pad_r, pad_b = spec["expand"]
    rect = (pad_l, pad_t, size[0] - pad_r, size[1] - pad_b)
    inner = (rect[2] - rect[0], rect[3] - rect[1])
    out, _ = _quiet_body(size, rect, radius, top_key, bottom_key, 255, grain,
                         shadow_offset=(0, 1), shadow_blur=2.0,
                         shadow_alpha=0.42 if drop else 0.0,
                         ramp=(spec["margin"][1], spec["margin"][3]))
    if pressed:
        # 按下去：上緣三條內陰影往下收，下緣補一條亮線，整顆看起來陷進去
        for index, strength in enumerate((86, 44, 18)):
            hline(out, rect[1] + 1 + index, rect[0] + 1, rect[2] - 2, P["shadow"], strength)
        hline(out, rect[3] - 2, rect[0] + 1, rect[2] - 2, P["inner_light"], 120)
    else:
        if gloss > 0:
            band = max(int(round(inner[1] * 0.48)), 1)
            for step in range(band):
                t = step / max(1, band - 1)
                hline(out, rect[1] + 1 + step, rect[0] + 1, rect[2] - 2, P["btn_gloss"],
                      int(gloss * pow(1.0 - t, 1.5)))
        # 下緣一條唇線，按鈕才有厚度不是一塊貼上去的色片
        hline(out, rect[3] - 2, rect[0] + 1, rect[2] - 2, P["shadow"], 46)
    frame_1px(out, [rect[0], rect[1], rect[2] - 1, rect[3] - 1], radius, P[rim_key], 255)
    return out


def build_quiet_plate(spec, top_key, bottom_key, rim_key, radius=4, grain=1.2, glow=None,
                      top_shade=0):
    """內框、輸入框、選取列、選項列這類底板：一層很淡的面加一圈細框"""
    Image, _, _ = _pil()
    size = spec["size"]
    mask = round_mask(size, radius)
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    if glow:
        out = over(out, shadow(size, mask, (0, 0), 2.0, glow, 0.45))
    out = over(out, fill(size, mask, quiet_face(size, top_key, bottom_key, grain,
                                                (spec["margin"][1], spec["margin"][3]))))
    if top_shade:
        # 上緣往下收的內陰影，內容區真的比面板低一階。
        # 兩條太薄，讀起來只是一條線；四條散開來才像有厚度的凹陷
        for index, ratio in enumerate((1.0, 0.62, 0.34, 0.16)):
            hline(out, 1 + index, 1, size[0] - 2, P["shadow"], int(top_shade * ratio))
        hline(out, size[1] - 2, 1, size[0] - 2, P["inner_light"], 160)
    frame_1px(out, [0, 0, size[0] - 1, size[1] - 1], radius, P[rim_key], 255)
    return out


def build_quiet_slot(spec, hover=False):
    """道具格：真的往內凹的淺灰格，上緣三條內陰影、下緣一條受光、一圈細框

    上一版上緣只比中央暗 2.9 階、下緣只亮 1.1 階，等於一個白方框。
    RO 和參考圖的格子都是凹的，這一版把上緣壓到 12 階以上、下緣抬到 8 階以上。
    """
    Image, _, _ = _pil()
    size = spec["size"]
    pad_l, pad_t, pad_r, pad_b = spec["expand"]
    rect = (pad_l, pad_t, size[0] - pad_r, size[1] - pad_b)
    radius = 3
    mask = Image.new("L", size, 0)
    mask.paste(round_mask((rect[2] - rect[0], rect[3] - rect[1]), radius), (rect[0], rect[1]))
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    if hover:
        out = over(out, shadow(size, mask, (0, 0), 3.0, P["slot_glow"], 0.7))
    top_key = "slot_hover_top" if hover else "slot_top"
    bottom_key = "slot_hover_bottom" if hover else "slot_bottom"
    out = over(out, fill(size, mask, quiet_face(size, top_key, bottom_key, 1.4,
                                                (spec["margin"][1], spec["margin"][3]))))
    # 上緣和左緣往內收的陰影、下緣一條受光，格子是凹進去的
    # 2026-09-18 光把顏色壓深還是讀成「比較深的方塊」不是「凹下去的洞」，
    # 洞的關鍵是上緣那道往下散的內陰影要夠厚，所以三條加到五條而且加深一倍
    for index, strength in enumerate((88, 56, 32, 17, 8)):
        hline(out, rect[1] + 1 + index, rect[0] + 1, rect[2] - 2, P["shadow"], strength)
    for index, strength in enumerate((52, 26, 12)):
        vline(out, rect[0] + 1 + index, rect[1] + 1, rect[3] - 3, P["shadow"], strength)
    # 下緣和右緣受光，凹槽的另外半邊才立得起來
    hline(out, rect[3] - 2, rect[0] + 1, rect[2] - 2, P["inner_light"], 220)
    vline(out, rect[2] - 2, rect[1] + 3, rect[3] - 3, P["inner_light"], 120)
    frame_1px(out, [rect[0], rect[1], rect[2] - 1, rect[3] - 1], radius,
              P["accent"] if hover else P["slot_rim"], 255)
    return out


def build_quiet_bar_track(spec):
    """數值條的溝：上緣壓兩條內陰影、下緣一條受光，是一條真的凹槽不是一條灰色"""
    size = spec["size"]
    radius = 3
    mask = round_mask(size, radius)
    out = fill(size, mask, vgrad(size, P["track_top"], P["track_bottom"]))
    for index, strength in enumerate((104, 66, 36, 18)):
        hline(out, 1 + index, 1, size[0] - 2, P["shadow"], strength)
    hline(out, size[1] - 2, 1, size[0] - 2, P["inner_light"], 205)
    frame_1px(out, [0, 0, size[0] - 1, size[1] - 1], radius, P["track_rim"], 255)
    return out


def build_quiet_tooltip(spec):
    """提示框：比面板再白一階，浮在所有東西上面所以影子比視窗重一點"""
    return build_quiet_window(spec, body_alpha=248, radius=8, shadow_offset=(0, 4),
                              shadow_blur=4.6, shadow_alpha=0.46, contact_alpha=0.22,
                              top_key="tip_top", bottom_key="tip_bottom", rim_light=180)


def build_quiet_tab(spec, selected):
    """分頁：選中的是面板色加上緣一條藍線，沒選中的淡一階，下緣收一條細線"""
    Image, _, _ = _pil()
    size = spec["size"]
    radius = 3
    mask = round_mask((size[0], size[1] + radius * 2), radius).crop((0, 0, size[0], size[1]))
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    keys = ("panel_top", "panel_bottom") if selected else ("inset_bottom", "inset_top")
    out = over(out, fill(size, mask, quiet_face(size, keys[0], keys[1], 0,
                                                (spec["margin"][1], spec["margin"][3]))))
    frame_1px(out, [0, 0, size[0] - 1, size[1] + radius], radius, P["edge_soft"], 255)
    if selected:
        hline(out, 0, radius, size[0] - 1 - radius, P["accent"], 255)
        hline(out, 1, radius, size[0] - 1 - radius, P["accent"], 120)
    else:
        hline(out, size[1] - 1, 0, size[0] - 1, P["edge"], 255)
    return out


def build_quiet_page(spec):
    """手機全螢幕分頁的底：不透明的面板色加紙紋，沒有框也沒有影子"""
    size = spec["size"]
    return fill(size, round_mask(size, 0), quiet_face(size, "panel_top", "panel_bottom", 1.3,
                                                      (spec["margin"][1], spec["margin"][3])))


def build_quiet_divider(spec):
    """段落之間就是一條很淡的細線，區段主要靠留白分開"""
    Image, _, _ = _pil()
    size = spec["size"]
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    hline(out, size[1] // 2, 0, size[0] - 1, P["edge_soft"], 255)
    return out


def build_quiet_nameplate(spec):
    """說話者的名牌：一塊淡藍灰的小牌子，形狀跟標題列同一族"""
    size = spec["size"]
    pad_l, pad_t, pad_r, pad_b = spec["expand"]
    rect = (pad_l, pad_t, size[0] - pad_r, size[1] - pad_b)
    out, _ = _quiet_body(size, rect, 5, "title_light", "title_bottom", 255, 0,
                         shadow_offset=(0, 2), shadow_blur=2.8, shadow_alpha=0.45,
                         ramp=(spec["margin"][1], spec["margin"][3]))
    hline(out, rect[1] + 1, rect[0] + 5, rect[2] - 6, P["inner_light"], 190)
    frame_1px(out, [rect[0], rect[1], rect[2] - 1, rect[3] - 1], 5, P["title_edge"], 255)
    return out


def build_quiet_check(size, checked):
    """勾選框：沒勾是空白小方框，勾了整格是強調色配白勾"""
    Image, ImageDraw, _ = _pil()
    radius = 3
    mask = round_mask(size, radius)
    if checked:
        out = fill(size, mask, vgrad(size, P["accent_top"], P["accent_bottom"]))
        frame_1px(out, [0, 0, size[0] - 1, size[1] - 1], radius, P["accent_rim"], 255)
        big = Image.new("L", (size[0] * SS, size[1] * SS), 0)
        ImageDraw.Draw(big).line([(3.6 * SS, 8.2 * SS), (6.6 * SS, 11.0 * SS), (12.2 * SS, 4.6 * SS)],
                                 fill=255, width=int(2.0 * SS), joint="curve")
        return over(out, tint(big.resize(size, Image.LANCZOS), (255, 255, 255), 1.0))
    out = fill(size, mask, quiet_face(size, "inner_light", "inset_top", 0))
    frame_1px(out, [0, 0, size[0] - 1, size[1] - 1], radius, P["edge"], 255)
    return out


def build_quiet_socket_mark(size):
    """空格子中間的記號：同一個手繪萌芽，淡到只剩一層影子"""
    source = mat.load_source("orn_socket_raw.png")
    if source is None:
        return None
    return mat.engraved(source, size, P["inner_light"], P["edge"], 0.9)


def build_quiet_emblem(size):
    """標題列左邊那個小萌芽，實心的一小塊強調色；角色視窗和登入畫面用它

    和其他十五顆記號一樣存成邏輯大小的 EMBLEM_SCALE 倍，畫的時候再縮下去。
    這一顆本來漏掉，所以登入畫面那顆還是糊的
    """
    big = (size[0] * EMBLEM_SCALE, size[1] * EMBLEM_SCALE)
    mask = _mask_from_source("emblem_sprout_raw.png", big, "horizontal", 110)
    if mask is None:
        return None
    return tint(mask, P["accent"], 1.0)


# 標題列的小記號，每個視窗一顆自己的，不然每一個視窗都掛同一顆等於沒有資訊
# 16 像素只畫得下剪影，所以每一顆都是一個形狀，不做細節也不做內部花紋
# 名字和 ui_theme.gd 的 EMBLEMS 對照表一樣，改了要一起改
QUIET_EMBLEMS = ["shield", "bag", "vest", "star", "sliders", "frame", "duo", "heart",
                 "swap", "hammer", "flask", "globe", "coin", "crate", "bang"]


## 記號在介面上的邏輯大小，實際存檔是它的 EMBLEM_SCALE 倍
EMBLEM_LOGICAL = 16
## 存成幾倍大。介面是照 1280x720 畫好再拉伸到實際視窗，所以記號在 1080p 會被放大 1.5 倍，
## 存 16 像素的話那 1.5 倍是無中生有、只會糊。存大的再讓引擎縮下去，放大多少都還是脆的
EMBLEM_SCALE = 4


def _glyph(paint):
    """在更大的畫布上畫一個記號再縮到存檔尺寸，邊才不會鋸齒"""
    Image, ImageDraw, _ = _pil()
    out = EMBLEM_LOGICAL * EMBLEM_SCALE
    big = Image.new("L", (out * SS, out * SS), 0)
    paint(ImageDraw.Draw(big), float(SS * EMBLEM_SCALE))
    return big.resize((out, out), Image.LANCZOS)


def _poly(draw, k, points):
    draw.polygon([(x * k, y * k) for x, y in points], fill=255)


def _rect(draw, k, box, width=0):
    scaled = [box[0] * k, box[1] * k, box[2] * k - 1, box[3] * k - 1]
    if width:
        draw.rectangle(scaled, outline=255, width=int(width * k))
    else:
        draw.rectangle(scaled, fill=255)


def _ring(draw, k, centre, radius, width=0):
    box = [(centre[0] - radius) * k, (centre[1] - radius) * k,
           (centre[0] + radius) * k - 1, (centre[1] + radius) * k - 1]
    if width:
        draw.ellipse(box, outline=255, width=int(width * k))
    else:
        draw.ellipse(box, fill=255)


def _bar(draw, k, x0, x1, y, width):
    draw.line([(x0 * k, y * k), (x1 * k, y * k)], fill=255, width=int(width * k))


QUIET_EMBLEM_PAINT = {
    # 狀態：盾
    "shield": lambda d, k: _poly(d, k, [(3, 2), (13, 2), (13, 8), (8, 14.5), (3, 8)]),
    # 道具：束口袋加一條提帶
    "bag": lambda d, k: (_poly(d, k, [(3.5, 6), (12.5, 6), (13.5, 14), (2.5, 14)]),
                         d.arc([5 * k, 1.5 * k, 11 * k, 8 * k], 180, 360, fill=255, width=int(1.6 * k))),
    # 裝備：胸甲，肩膀寬腰收起來
    "vest": lambda d, k: _poly(d, k, [(4, 2.5), (6.5, 2.5), (8, 4.5), (9.5, 2.5), (12, 2.5),
                                      (12.5, 13.5), (3.5, 13.5)]),
    # 技能：四角星
    "star": lambda d, k: _poly(d, k, [(8, 1), (9.7, 6.3), (15, 8), (9.7, 9.7), (8, 15),
                                      (6.3, 9.7), (1, 8), (6.3, 6.3)]),
    # 設定：兩條滑桿，旋鈕在不同位置
    "sliders": lambda d, k: (_bar(d, k, 2, 14, 5.5, 1.4), _bar(d, k, 2, 14, 10.5, 1.4),
                             _ring(d, k, (11, 5.5), 2.4), _ring(d, k, (5, 10.5), 2.4)),
    # 系統：一個視窗，上面一條標題列
    "frame": lambda d, k: (_rect(d, k, (2, 3, 14, 13), 1.6), _rect(d, k, (2, 3, 14, 6.4))),
    # 隊伍：兩個人
    "duo": lambda d, k: (_ring(d, k, (5.5, 5.5), 3.0), _ring(d, k, (10.5, 5.5), 3.0),
                         _poly(d, k, [(1.5, 14), (3, 9.5), (13, 9.5), (14.5, 14)])),
    # 好友：心
    "heart": lambda d, k: (_ring(d, k, (5.6, 6), 3.3), _ring(d, k, (10.4, 6), 3.3),
                           _poly(d, k, [(2.4, 6.6), (13.6, 6.6), (8, 14.5)])),
    # 交易：一來一往兩支箭
    "swap": lambda d, k: (_bar(d, k, 3, 12, 5.5, 1.4), _poly(d, k, [(14, 5.5), (10, 2.8), (10, 8.2)]),
                          _bar(d, k, 4, 13, 10.5, 1.4), _poly(d, k, [(2, 10.5), (6, 7.8), (6, 13.2)])),
    # 精煉：鎚子
    "hammer": lambda d, k: (_rect(d, k, (2.5, 3, 13.5, 7)), _rect(d, k, (6.8, 7, 9.2, 14.5))),
    # 製作：燒瓶
    "flask": lambda d, k: (_poly(d, k, [(6.2, 2.5), (9.8, 2.5), (9.8, 6.2), (13.5, 14),
                                        (2.5, 14), (6.2, 6.2)]), _bar(d, k, 5.4, 10.6, 2.4, 1.4)),
    # 世界地圖：地球，一條赤道一條經線
    "globe": lambda d, k: (_ring(d, k, (8, 8), 6.2, 1.5), _bar(d, k, 2.2, 13.8, 8, 1.3),
                           d.ellipse([5 * k, 1.9 * k, 11 * k, 14.1 * k], outline=255,
                                     width=int(1.3 * k))),
    # 商店：錢幣
    "coin": lambda d, k: (_ring(d, k, (8, 8), 6.2, 1.6), _ring(d, k, (8, 8), 2.6, 1.4)),
    # 倉庫：木箱，一條蓋線中間一個扣
    "crate": lambda d, k: (_rect(d, k, (2, 4, 14, 13.5), 1.6), _bar(d, k, 2, 14, 7.4, 1.4),
                           _rect(d, k, (6.8, 4, 9.2, 7.4))),
    # 任務：驚嘆號
    "bang": lambda d, k: (_poly(d, k, [(6.6, 2), (9.4, 2), (8.9, 10.5), (7.1, 10.5)]),
                          _ring(d, k, (8, 13), 1.5)),
}


def build_quiet_emblem_set(out_dir=None):
    """每個視窗一顆記號，實心的強調色，存成 emblem_<名字>.png"""
    for name in QUIET_EMBLEMS:
        save(tint(_glyph(QUIET_EMBLEM_PAINT[name]), P["accent"], 1.0), "emblem_" + name, out_dir)
    return len(QUIET_EMBLEMS)


def build_quiet(built):
    """quiet 這一套的全部九宮格，名字和切邊都和深色那套一樣，換皮不換結構"""
    # 面板透一點點：使用者要「帶一點透明感一點點即可」
    # 草地的綠只透上來 7.5%、暗場的紫只透上來 6%，字的對比還在 9 比 1 以上，量在 docs/美術方向.md
    # 本體不靠透明度透出去了，透明感改由 panel_glass 那支著色器的背景模糊負責，
    # 所以貼圖這邊拉回幾乎不透明，著色器的本體判斷才穩定；沒有著色器的地方也不會變髒
    built["window"] = build_quiet_window(SKIN["window"], body_alpha=252)
    # hud 的中段是 24 像素，不是紙紋週期的整數倍，鋪了會有橫線；它本來就半透明，看不出差別
    # 它的 expand 只有 6 到 7，影子鋪不了視窗那麼開，所以自己一組比較收斂的數字
    built["hud"] = build_quiet_window(SKIN["hud"], body_alpha=222, radius=7, grain=0,
                                      shadow_offset=(0, 3), shadow_blur=3.4, shadow_alpha=0.38,
                                      contact_alpha=0.10, rim_light=170)
    built["titlebar"] = build_quiet_titlebar(SKIN["titlebar"])
    built["inset"] = build_quiet_plate(SKIN["inset"], "inset_top", "inset_bottom", "edge_soft",
                                       top_shade=72)
    built["input"] = build_quiet_plate(SKIN["input"], "inner_light", "inset_top", "edge",
                                       top_shade=30)
    built["input_focus"] = build_quiet_plate(SKIN["input_focus"], "inner_light", "accent_pale",
                                             "accent", glow=P["slot_glow"], top_shade=30)
    built["select"] = build_quiet_plate(SKIN["select"], "select_top", "select_bottom", "accent_soft")
    built["slot"] = build_quiet_slot(SKIN["slot"])
    built["slot_hover"] = build_quiet_slot(SKIN["slot_hover"], hover=True)
    built["button"] = build_quiet_button(SKIN["button"], "btn_top", "btn_bottom", "btn_rim")
    built["button_hover"] = build_quiet_button(SKIN["button_hover"], "btn_hover_top",
                                               "btn_hover_bottom", "btn_hover_rim", gloss=44)
    built["button_pressed"] = build_quiet_button(SKIN["button_pressed"], "btn_press_top",
                                                 "btn_press_bottom", "accent_soft",
                                                 pressed=True, drop=False)
    built["button_disabled"] = build_quiet_button(SKIN["button_disabled"], "btn_dis_top",
                                                  "btn_dis_bottom", "btn_dis_rim",
                                                  drop=False, gloss=0)
    built["button_accent"] = build_quiet_button(SKIN["button_accent"], "accent_top", "accent_bottom",
                                                "accent_rim", gloss=34)
    built["button_accent_hover"] = build_quiet_button(SKIN["button_accent_hover"], "accent_hover_top",
                                                      "accent_hover_bottom", "accent_rim", gloss=48)
    built["button_accent_pressed"] = build_quiet_button(SKIN["button_accent_pressed"], "accent_bottom",
                                                        "accent_top", "accent_rim",
                                                        pressed=True, drop=False)
    built["bar_track"] = build_quiet_bar_track(SKIN["bar_track"])
    built["tooltip"] = build_quiet_tooltip(SKIN["tooltip"])
    built["tab_on"] = build_quiet_tab(SKIN["tab_on"], True)
    built["tab_off"] = build_quiet_tab(SKIN["tab_off"], False)
    built["divider"] = build_quiet_divider(SKIN["divider"])
    built["page"] = build_quiet_page(SKIN["page"])
    # 對話框和其他視窗同一套，只是留白大一點，不再另外做一張紙
    built["dialogue"] = build_quiet_window(SKIN["dialogue"], body_alpha=244, shadow_alpha=0.38,
                                           shadow_blur=8.6, shadow_offset=(0, 7))
    built["nameplate"] = build_quiet_nameplate(SKIN["nameplate"])
    built["choice"] = build_quiet_plate(SKIN["choice"], "row_top", "row_bottom", "edge_soft")
    built["choice_hover"] = build_quiet_plate(SKIN["choice_hover"], "row_hover_top",
                                              "row_hover_bottom", "accent_soft")
    built["choice_on"] = build_quiet_plate(SKIN["choice_on"], "row_on_top", "row_on_bottom", "accent")
    return built


# ---- 輸出 ----

IMPORT_TEMPLATE = """[remap]

importer="texture"
type="CompressedTexture2D"
uid="uid://%s"
path="res://.godot/imported/%s.png-%s.ctex"
metadata={
"vram_texture": false
}

[deps]

source_file="res://assets/ui/skin/%s.png"
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
process/fix_alpha_border=true
process/premult_alpha=false
process/normal_map_invert_y=false
process/hdr_as_srgb=false
process/hdr_clamp_exposure=false
process/size_limit=0
detect_3d/compress_to=0
"""


def _hash(name):
    import hashlib
    return hashlib.md5(("ui_skin/" + name).encode()).hexdigest()


def _uid(name):
    """照 Godot 的 base31 字母做一個固定的 uid，重跑不會變"""
    letters = "abcdefghijklmnopqrstuvwxyz0123456789"
    value = int(_hash(name)[:12], 16)
    out = ""
    for _ in range(12):
        out += letters[value % len(letters)]
        value //= len(letters)
    return "c" + out


def save(image, name, out_dir=None):
    target = out_dir or OUT_DIR
    os.makedirs(target, exist_ok=True)
    path = os.path.join(target, name + ".png")
    image.save(path)
    digest = _hash(name)
    with open(path + ".import", "w", encoding="utf-8") as handle:
        handle.write(IMPORT_TEMPLATE % (_uid(name), name, digest, name, name, digest))
    return path


def build(variant="quiet", out_dir=None, title_tone=None):
    """產生全部介面皮膚；Blender 裡沒有 Pillow，改叫系統的 python3 跑同一個檔案"""
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("[ui/skin] 這個直譯器沒有 Pillow，改用系統的 python3")
        subprocess.run([_system_python(), os.path.abspath(__file__), variant], check=True)
        return

    global P, TITLE_TONE
    P = PALETTES[variant]
    if title_tone:
        TITLE_TONE = title_tone
    built = {}
    if variant == "quiet":
        built = build_quiet(built)
        _save_all(built, variant, out_dir, quiet=True)
        print("[ui/skin] quiet：另外做了 %d 顆視窗記號" % build_quiet_emblem_set(out_dir))
        return
    built["window"] = build_window(SKIN["window"])
    built["hud"] = build_window(SKIN["hud"], ornament_corners=False, body_alpha=238, band=4)
    built["titlebar"] = build_titlebar(SKIN["titlebar"])
    built["inset"] = build_plate(SKIN["inset"], "inset_bottom", "inset_top", P["metal_dark"])
    built["input"] = build_plate(SKIN["input"], "inset_bottom", "inset_top", P["metal_bottom"])
    built["input_focus"] = build_plate(SKIN["input_focus"], "inset_bottom", "inset_top",
                                       P["accent_rim"], glow=P["slot_glow"])
    built["select"] = build_plate(SKIN["select"], "select_bottom", "select_top", P["metal_top"],
                                  sunken=False, kind="wood")
    built["slot"] = build_slot(SKIN["slot"])
    built["slot_hover"] = build_slot(SKIN["slot_hover"], hover=True)
    built["button"] = build_button(SKIN["button"], "btn_bottom", "btn_top")
    built["button_hover"] = build_button(SKIN["button_hover"], "btn_hover_bottom", "btn_hover_top",
                                         glow=P["slot_glow"], rim=P["metal_top"], gloss=74)
    built["button_pressed"] = build_button(SKIN["button_pressed"], "btn_press_top", "btn_press_bottom",
                                           pressed=True, drop=False, rim=P["accent_rim"])
    built["button_disabled"] = build_button(SKIN["button_disabled"], "btn_dis_bottom", "btn_dis_top",
                                            drop=False, rim=P["btn_dis_rim"], kind="cloth", gloss=16)
    built["button_accent"] = build_button(SKIN["button_accent"], "accent_bottom", "accent_top",
                                          rim=P["accent_rim"], gloss=64)
    built["button_accent_hover"] = build_button(SKIN["button_accent_hover"], "accent_hover_bottom",
                                                "accent_hover_top", glow=P["slot_glow"],
                                                rim=P["accent_rim"], gloss=84)
    built["button_accent_pressed"] = build_button(SKIN["button_accent_pressed"], "accent_top",
                                                  "accent_hover_top", pressed=True, drop=False,
                                                  rim=P["accent_rim"])
    built["bar_track"] = build_bar_track(SKIN["bar_track"])
    built["tooltip"] = build_tooltip(SKIN["tooltip"])
    built["tab_on"] = build_tab(SKIN["tab_on"], True)
    built["tab_off"] = build_tab(SKIN["tab_off"], False)
    built["divider"] = build_divider(SKIN["divider"])
    built["page"] = build_plate(SKIN["page"], "panel_bottom", "panel_top", P["edge"], sunken=False)
    # 對話框：淺色紙面加青銅框，內側暗角收得比深色視窗淡，紙才不會看起來髒
    built["dialogue"] = build_window(SKIN["dialogue"], ornament_corners=True,
                                     dark_key="paper_bottom", light_key="paper_top", shade_alpha=42)
    built["nameplate"] = build_nameplate(SKIN["nameplate"])
    built["choice"] = build_plate(SKIN["choice"], "row_bottom", "row_top", P["metal_bottom"],
                                  sunken=False, kind="cloth")
    built["choice_hover"] = build_plate(SKIN["choice_hover"], "row_hover_bottom", "row_hover_top",
                                        P["metal_top"], sunken=False, kind="cloth")
    built["choice_on"] = build_plate(SKIN["choice_on"], "row_on_bottom", "row_on_top",
                                     P["accent_rim"], sunken=False, kind="wood")

    _save_all(built, variant, out_dir)


def _save_all(built, variant, out_dir, quiet=False):
    """檢查尺寸、存九宮格和單張圖、寫切邊表"""
    for name, image in built.items():
        want = SKIN[name]["size"]
        assert image.size == want, "%s 尺寸 %s 應該是 %s" % (name, image.size, want)
        save(image, name, out_dir)

    makers = {"emblem": build_emblem, "vignette": build_vignette, "logo_flourish": build_logo_flourish,
              "socket_mark": build_socket_mark,
              "check_off": lambda s: build_check(s, False), "check_on": lambda s: build_check(s, True)}
    if quiet:
        makers["emblem"] = build_quiet_emblem
        makers["socket_mark"] = build_quiet_socket_mark
        makers["check_off"] = lambda s: build_quiet_check(s, False)
        makers["check_on"] = lambda s: build_quiet_check(s, True)
    for name, size in PLAIN.items():
        image = makers[name](size)
        if image is None:
            print("[ui/skin] 跳過 %s，缺原圖" % name)
            continue
        save(image, name, out_dir)

    table = {name: {"size": list(spec["size"]), "margin": list(spec["margin"]),
                    "expand": list(spec["expand"])} for name, spec in SKIN.items()}
    with open(os.path.join(out_dir or OUT_DIR, "skin.json"), "w", encoding="utf-8") as handle:
        json.dump(table, handle, ensure_ascii=False, indent=1, sort_keys=True)
    print("[ui/skin] %s：完成 %d 張九宮格加 %d 張單圖" % (variant, len(built), len(PLAIN)))


def _system_python():
    """找一個真的裝了 Pillow 的 python3，Blender 內建的沒有"""
    import shutil
    candidates = ["/opt/homebrew/bin/python3", shutil.which("python3"), "/usr/local/bin/python3",
                  "/usr/bin/python3"]
    for candidate in candidates:
        if not candidate or not os.path.exists(candidate):
            continue
        if subprocess.run([candidate, "-c", "import PIL"], capture_output=True).returncode == 0:
            return candidate
    raise SystemExit("找不到裝了 Pillow 的 python3，先裝 Pillow 再跑 ui/skin")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    tone = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--title=")), None)
    build(args[0] if args else "quiet", title_tone=tone)
