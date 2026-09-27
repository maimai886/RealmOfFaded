"""灰白人體模型的表情圖集

照 docs/角色系統規格.md：表情是一張圖集，遊戲端位移 UV 換格子，不換網格也不換材質。
圖集是 4 欄 2 列共八格，順序和 src/world/actors/expression.gd 的 NAMES 一樣。

**這張圖是照遊戲鏡頭的距離畫的，不是照特寫畫的。**
角色在 720p 下大約 120 像素高，頭大約 55 像素，臉那一塊只有 30 像素寬。
所以五官只能少、只能大、只能高對比：兩顆大黑眼睛、一張小嘴，
眉毛只有需要的表情才畫，而且是短而粗的一筆。畫細了在遊戲裡就是一團灰。

位置照 docs/美術風格指南.md 第 1.5 節那張表，用的單位是「佔頭寬幾成」和
「從頭頂往下佔頭高幾成」，不是像素，所以頭的尺寸改了這張圖不用重畫。

這個檔案不需要 Blender，直接跑：
    python3 art_pipeline/characters_v3/facesheet.py
"""

import math
import os
import sys

CELL = 256
COLUMNS = 4
ROWS = 2
EXPRESSIONS = ["normal", "blink", "happy", "angry", "hurt", "dead", "surprised", "talk"]

# 臉那塊面片在頭上涵蓋的範圍，和 mannequin.py 的 FACE_* 必須一致
# 臉在球上的位置要比「解剖學上的位置」高一截。
# 遊戲鏡頭是往下俯 38 度，貼在球正面的臉會被壓到畫面下半部而且整片被壓扁，
# 往上移之後臉才正對鏡頭。這是量出來的，不是照解剖畫的
FACE_HALF_ANGLE = 55.0
FACE_TOP_V = 0.08
FACE_BOTTOM_V = 0.74

# 五官的位置和大小，單位照第 1.5 節
# 眼睛比第 1.5 節那張表大一點。那張表是給看得到細節的距離用的，
# 遊戲裡臉只有 30 像素寬，照表畫的眼睛縮小之後是兩個灰點
EYE_CENTRE_X = 0.21
EYE_WIDTH = 0.30
EYE_HEIGHT = 0.28
EYE_V = 0.47
# 眉毛和眼睛之間一定要留出空白的額頭。貼著眼睛畫的話讀起來是眼皮不是眉毛，
# 表情就全靠眼睛的形狀撐，八個格子會塌成同一張臉
BROW_V = EYE_V - 0.225
MOUTH_V = 0.655
MOUTH_WIDTH = 0.19

SKIN = (222, 219, 214)
INK = (58, 52, 60)
EYE_WHITE = (252, 250, 248)
IRIS = (86, 122, 132)
BLUSH = (226, 168, 158)
MOUTH_INK = (96, 56, 60)


def _u_of_x(x_head_widths):
    """佔頭寬幾成的 x 換算成格子裡的 u

    頭是一顆球，面片照方位角均分，所以 x 和 u 之間要經過反正弦。
    直接線性對應的話眼睛會往兩邊飄。
    """
    ratio = max(-1.0, min(1.0, x_head_widths * 2.0))
    angle = math.degrees(math.asin(ratio))
    return 0.5 + angle / (2.0 * FACE_HALF_ANGLE)


def _v_of_head(v_head):
    """從頭頂往下佔頭高幾成，換算成格子裡的 v

    球面上高度和極角的關係也是三角函數，同樣要換算。
    """
    cos_polar = 1.0 - 2.0 * v_head
    polar = math.degrees(math.acos(max(-1.0, min(1.0, cos_polar))))
    top = math.degrees(math.acos(max(-1.0, min(1.0, 1.0 - 2.0 * FACE_TOP_V))))
    bottom = math.degrees(math.acos(max(-1.0, min(1.0, 1.0 - 2.0 * FACE_BOTTOM_V))))
    return (polar - top) / max(bottom - top, 1e-6)


def _px(u, v):
    return u * CELL, v * CELL


def _blend(canvas, x, y, color, alpha):
    if alpha <= 0.0 or x < 0 or y < 0 or x >= CELL or y >= CELL:
        return
    index = (y * CELL + x) * 3
    for channel in range(3):
        old = canvas[index + channel]
        canvas[index + channel] = int(old + (color[channel] - old) * min(alpha, 1.0))


def _ellipse(canvas, cx, cy, rx, ry, color, softness=1.2, squash_top=1.0):
    """實心橢圓，邊緣有一點柔邊，不然在遊戲裡縮小之後會有鋸齒"""
    x0, x1 = int(cx - rx - 2), int(cx + rx + 3)
    y0, y1 = int(cy - ry - 2), int(cy + ry + 3)
    for y in range(max(y0, 0), min(y1, CELL)):
        for x in range(max(x0, 0), min(x1, CELL)):
            dx = (x + 0.5 - cx) / max(rx, 1e-6)
            dy = (y + 0.5 - cy) / max(ry, 1e-6)
            if dy < 0:
                dy /= max(squash_top, 1e-6)
            distance = math.sqrt(dx * dx + dy * dy)
            edge = softness / max(rx, ry)
            alpha = 1.0 if distance <= 1.0 - edge else max(0.0, (1.0 - distance) / edge)
            _blend(canvas, x, y, color, alpha)


def _stroke(canvas, points, thickness, color):
    """一筆粗線，用來畫眉毛和嘴巴"""
    for index in range(len(points) - 1):
        ax, ay = points[index]
        bx, by = points[index + 1]
        steps = max(int(math.hypot(bx - ax, by - ay)), 1)
        for step in range(steps + 1):
            t = step / steps
            _ellipse(canvas, ax + (bx - ax) * t, ay + (by - ay) * t,
                     thickness / 2.0, thickness / 2.0, color, softness=0.9)


def _eye(canvas, mirror, style, open_amount=1.0, lift=0.0, narrow=1.0, arc=-1.0):
    """一隻眼睛。open_amount 0 就是閉眼，畫成一條弧線

    arc 是閉眼那條弧往哪邊彎：-1 是往下彎的睡眼，+1 是往上彎的笑眼。
    這兩個一定要分開，不然眨眼和開心在畫面上是同一張臉。
    """
    x = -EYE_CENTRE_X if mirror else EYE_CENTRE_X
    cx, cy = _px(_u_of_x(x), _v_of_head(EYE_V + lift))
    rx = (CELL * (_u_of_x(EYE_WIDTH / 2.0) - 0.5)) * narrow
    ry = CELL * (_v_of_head(EYE_V + EYE_HEIGHT / 2.0) - _v_of_head(EYE_V)) * open_amount
    if open_amount < 0.25:
        # 閉眼：一條往下彎的弧，比畫一條直線好認
        width = rx * 1.05
        bend = width * 0.34 * arc
        points = [(cx - width, cy - bend * 0.7), (cx, cy + bend),
                  (cx + width, cy - bend * 0.7)]
        _stroke(canvas, points, max(CELL * 0.030, 4.0), INK)
        return
    # 一塊深色加一個高光就好。
    # 身體是一具沒有任何細節的灰白人偶，眼睛做得又亮又完整會和其他部位對不上，
    # 讀起來是詭異不是可愛。整張臉的細節程度要和身體一致：少、大、乾淨
    _ellipse(canvas, cx, cy, rx, ry, INK if style == 0 else (46, 44, 58), squash_top=1.0)
    _ellipse(canvas, cx - rx * 0.28, cy - ry * 0.30, rx * 0.30, ry * 0.30, EYE_WHITE)


def _cross_eye(canvas, mirror):
    """暈倒的叉叉眼"""
    x = -EYE_CENTRE_X if mirror else EYE_CENTRE_X
    cx, cy = _px(_u_of_x(x), _v_of_head(EYE_V))
    size = CELL * (_u_of_x(EYE_WIDTH / 2.0) - 0.5) * 0.95
    thickness = max(CELL * 0.024, 3.0)
    _stroke(canvas, [(cx - size, cy - size), (cx + size, cy + size)], thickness, INK)
    _stroke(canvas, [(cx - size, cy + size), (cx + size, cy - size)], thickness, INK)


# 「看起來水平」的眉毛要畫成內側微微上揚。
# 直的一筆貼到球面上、再從俯角 38 度看，兩端會往下彎，讀起來就是皺著眉。
# 這是嘴巴那條直線變成哭臉的同一個問題，第三次踩到了。
# 量到的補償量是 16 度：先試 9 度還是偏兇，改到 16 度才讀成平的。
# 16 度還是稍微不足，外側仍然微微下垂，中性表情讀起來帶一點惆悵而不是全平。
# 這個殘差可以接受，比偏兇好太多，先不再往上加
LEVEL_BROW = -16.0


def _brow(canvas, mirror, angle, lift=0.0):
    """眉毛：短而粗的一筆。angle 正的是內側低也就是生氣"""
    x = -EYE_CENTRE_X if mirror else EYE_CENTRE_X
    cx, cy = _px(_u_of_x(x), _v_of_head(BROW_V - lift))
    half = CELL * (_u_of_x(EYE_WIDTH * 0.52) - 0.5)
    # 角度是正的代表「內側低」也就是生氣，負的是內側高也就是難過。
    # 內側是靠近中線那一端，非鏡像的那隻眼在圖的右邊，所以內側是 cx 減 half 那一端
    drop = half * math.tan(math.radians(angle)) * (1.0 if mirror else -1.0)
    # 眉毛要比看起來需要的粗。頭只有 40 像素高的時候，細筆第一個消失
    _stroke(canvas, [(cx - half, cy - drop), (cx + half, cy + drop)],
            max(CELL * 0.055, 6.0), INK)


def _mouth(canvas, kind):
    cx, cy = _px(0.5, _v_of_head(MOUTH_V))
    half = CELL * (_u_of_x(MOUTH_WIDTH / 2.0) - 0.5)
    thickness = max(CELL * 0.040, 5.0)
    if kind == "smile":
        points = [(cx - half, cy - half * 0.30), (cx, cy + half * 0.42),
                  (cx + half, cy - half * 0.30)]
        _stroke(canvas, points, thickness, MOUTH_INK)
    elif kind == "frown":
        points = [(cx - half, cy + half * 0.30), (cx, cy - half * 0.34),
                  (cx + half, cy + half * 0.30)]
        _stroke(canvas, points, thickness, MOUTH_INK)
    elif kind == "open":
        _ellipse(canvas, cx, cy, half * 0.62, half * 0.78, MOUTH_INK)
    elif kind == "grin":
        # 張開的笑：一塊半圓的深色，上緣是平的。開心要一眼看得出來，一條線不夠
        _ellipse(canvas, cx, cy + half * 0.10, half * 1.00, half * 0.70, MOUTH_INK)
        _ellipse(canvas, cx, cy - half * 0.52, half * 1.06, half * 0.46, SKIN)
    elif kind == "wide":
        _ellipse(canvas, cx, cy, half * 0.92, half * 0.58, MOUTH_INK)
    else:
        # 中性不是一條直線。臉是貼在球面上的，直線投影到畫面上會往下彎，
        # 讀起來是一張哭喪的臉。畫成微微上揚，看起來才是平的甚至有一點點笑意
        points = [(cx - half * 0.66, cy - half * 0.04), (cx, cy + half * 0.14),
                  (cx + half * 0.66, cy - half * 0.04)]
        _stroke(canvas, points, thickness, MOUTH_INK)


def _blush(canvas, strength=1.0):
    for mirror in (False, True):
        x = -0.34 if mirror else 0.34
        cx, cy = _px(_u_of_x(x), _v_of_head(EYE_V + 0.09))
        rx = CELL * 0.075
        for y in range(int(cy - rx * 1.4), int(cy + rx * 1.4)):
            for px_x in range(int(cx - rx * 1.6), int(cx + rx * 1.6)):
                dx = (px_x - cx) / (rx * 1.5)
                dy = (y - cy) / (rx * 0.95)
                distance = math.sqrt(dx * dx + dy * dy)
                if distance < 1.0:
                    _blend(canvas, px_x, y, BLUSH, (1.0 - distance) * 0.55 * strength)


def _draw(name, style):
    """一格表情

    驗收標準是「把標籤蓋住還叫得出名字」。做得到靠的是眉毛：
    人臉的表情大半在眉毛上，眼睛形狀是次要的。
    所以每一格的眉毛角度和高度都不一樣，不是只改眼睛。
    """
    canvas = bytearray()
    for _ in range(CELL * CELL):
        canvas += bytes(SKIN)
    if name == "normal":
        # 平的眉毛、圓眼睛、一張微微上揚的小嘴
        for mirror in (False, True):
            _brow(canvas, mirror, LEVEL_BROW)
            _eye(canvas, mirror, style)
        _mouth(canvas, "flat")
    elif name == "blink":
        for mirror in (False, True):
            _brow(canvas, mirror, LEVEL_BROW)
            _eye(canvas, mirror, style, open_amount=0.0, arc=-1.0)
        _mouth(canvas, "flat")
    elif name == "happy":
        # 眉毛抬高、眼睛是往上彎的笑眼、嘴巴張開。三件一起才叫開心
        for mirror in (False, True):
            _brow(canvas, mirror, LEVEL_BROW - 10.0, lift=0.060)
            _eye(canvas, mirror, style, open_amount=0.0, arc=1.0)
        _mouth(canvas, "grin")
        _blush(canvas)
    elif name == "angry":
        # 眉毛往鼻梁壓下去，這就是生氣。眼睛只是跟著瞇一點
        for mirror in (False, True):
            _brow(canvas, mirror, 30.0, lift=-0.035)
            _eye(canvas, mirror, style, narrow=0.90, open_amount=0.78)
        _mouth(canvas, "frown")
    elif name == "hurt":
        # 眉毛內側抬高就是難過，和生氣剛好相反
        for mirror in (False, True):
            _brow(canvas, mirror, -26.0, lift=0.02)
            _eye(canvas, mirror, style, open_amount=0.0, arc=-1.0)
        _mouth(canvas, "open")
    elif name == "dead":
        for mirror in (False, True):
            _brow(canvas, mirror, -18.0)
            _cross_eye(canvas, mirror)
        _mouth(canvas, "wide")
    elif name == "surprised":
        # 眉毛拉到最高、眼睛睜到最大、嘴巴是一個小圓
        for mirror in (False, True):
            _brow(canvas, mirror, LEVEL_BROW, lift=0.075)
            _eye(canvas, mirror, style, open_amount=1.22, narrow=1.10)
        _mouth(canvas, "open")
    else:  # talk
        # 說話就是嘴巴在動，眼睛和眉毛維持中性，不要跟著變表情
        for mirror in (False, True):
            _brow(canvas, mirror, LEVEL_BROW)
            _eye(canvas, mirror, style)
        _mouth(canvas, "wide")
    return canvas


def build(style=0):
    """整張圖集，回傳 (寬, 高, RGB bytes)"""
    width, height = CELL * COLUMNS, CELL * ROWS
    sheet = bytearray(bytes(SKIN) * (width * height))
    for index, name in enumerate(EXPRESSIONS):
        cell = _draw(name, style)
        ox = (index % COLUMNS) * CELL
        oy = (index // COLUMNS) * CELL
        for y in range(CELL):
            src = y * CELL * 3
            dst = ((oy + y) * width + ox) * 3
            sheet[dst:dst + CELL * 3] = cell[src:src + CELL * 3]
    return width, height, bytes(sheet)


def save(path, style=0):
    from PIL import Image
    width, height, data = build(style)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.frombytes("RGB", (width, height), data).save(path)
    return path


OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "assets", "generated", "models", "characters_mannequin")


def export_all():
    """兩種眼型各一張。檔名照 character_parts.face_path 的規則"""
    made = [save(os.path.join(OUT_DIR, "face.png"), 0)]
    made.append(save(os.path.join(OUT_DIR, "face_e1.png"), 1))
    return made


if __name__ == "__main__":
    for path in export_all():
        print(path)
    sys.exit(0)
