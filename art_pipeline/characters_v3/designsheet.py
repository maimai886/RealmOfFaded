"""量一張設定圖的比例，並且把它正規化到標準比例

為什麼要有這一支：使用者畫設定圖的時候只想管長相，不想管比例。
他自己講的原話是「不可能每次都這麼剛好」——下一張圖不會剛好又是 4.07 頭身。
所以管線不能綁死在「設定圖必須畫到某個比例」上，要反過來由工具把圖調到標準。

這一支同時是骨架參數的來源。整條路是：

    設定圖 → 這一支量測 → 比例參數 → rigspec 產生器 → 骨架

量出來的比例參數丟給 `rigspec.RigSpec`，骨架就長成那張圖的樣子。
正規化那一半留著是因為十四具身體必須共用同一副骨架，標準只能有一份，
所以其他設定圖要往標準那一份靠。

用法：

    python3 art_pipeline/characters_v3/designsheet.py measure 設定圖.png
    python3 art_pipeline/characters_v3/designsheet.py spec 設定圖.png
    python3 art_pipeline/characters_v3/designsheet.py cut 設定圖.png 輸出前綴
    python3 art_pipeline/characters_v3/designsheet.py normalize 設定圖.png 出.png --ratio 4.07

這支不匯入 bpy，也不需要 Blender，用系統的 python3 跑，只要有 Pillow。
"""

import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import rigspec  # noqa: E402

# 背景的判斷條件：很亮而且幾乎沒有飽和度。
#
# 兩個條件缺一不可。只看亮度的話，角色身上那件米白色的上衣會被當成背景整片挖掉，
# 實測那塊是明度 0.96、飽和度 0.18，比紙的白只差一點點。
# 只看飽和度的話，深灰的描邊和黑色的瞳孔也會中。
# 使用者那張圖腳下還有一圈灰色投影，明度 0.82、飽和度 0.005，這兩條同時擋得住
BG_VALUE = 0.72
BG_SATURATION = 0.10
# 還要「碰得到畫面邊緣」或「和最大那一片差不多大」才算背景。
#
# 這一條是為了保護包在角色裡面的淺色：衣服的高光、眼白、靴子上的金屬扣
# 都可能同時很亮又沒什麼顏色，但它們只有幾十格，紙是好幾萬格。
#
# 兩個條件都要，缺一個就會出事：
# 只看「碰得到邊緣」的話，使用者的設定圖外面有一圈裝飾框，框線本身不是背景色，
# 它把紙封在裡面，從邊緣只淹得掉框線外面那七格。
# 只看大小的話，門檻要寫成佔整張圖的比例，小圖上一塊高光就會超過門檻被挖掉
BG_RELATIVE = 0.25
# 切角色的時候，高度不到最高那一具這個比例的就丟掉。
# 設定圖上的標題字和零星雜點都比角色矮很多
FIGURE_MIN_HEIGHT = 0.40
# 外框的判斷：某一邊幾乎橫跨整張圖，另一邊卻只有幾格寬，那就是一條框線不是角色。
# 使用者那張設定圖外面有一圈裝飾框，去背之後裂成上下左右四條，
# 每一條都比角色還長，只靠高度篩會把它們當成最高的那一具
FRAME_SPAN = 0.85
FRAME_THIN = 0.06
# 找脖子只在上面這麼多比例的高度裡找。兩頭身的角色頭就佔一半，所以要留到五成五
NECK_SEARCH = 0.55
# 脖子上下都要有比它寬這麼多倍的地方，上面是頭、下面是肩膀。
# 這一條同時擋掉兩種誤判：翹出去那撮呆毛的上面沒有頭，腰的下面沒有比它寬 1.8 倍的臀
NECK_SHOULDER_RATIO = 1.8
# 找肩膀的時候往下看這麼多比例的全高。再往下就看到手肘了
NECK_LOOK_DOWN = 0.20
# 量頭寬之前先做一次開運算，半徑是頭高的這個比例。
# 這一條照 docs/美術風格指南.md 第 2.1 節：不先把翹出去的一兩撮髮尖磨掉，
# 量到的是髮尖的外接框不是頭，上一版的比例表就是這樣量錯的。
# 使用者這張圖的頭高 135 格、原生像素格是四格，
# 所以頭高大約 34 個原生像素，半徑 2 個原生像素換算回來就是 8 格，也就是 0.06 個頭高。
# 這個數字不是隨便取的，但也要知道它不是唯一解：這顆頭的髮尖不是一兩根刺而是一圈碎髮，
# 半徑愈大量到的頭愈窄，radius 6 到 12 之間量到 1.15 到 1.07。
# 定在 0.06 是因為它對得上風格指南那條「半徑 2」的規矩，換一張圖也還是同一個定義
HEAD_OPEN_RATIO = 0.06
# 量腿寬和站距用小腿那一段，位置是「胯部到腳底」的這兩個比例之間。
# 取中間偏下：再上去是膝蓋和下襬，再下去是靴子的尖端
LEG_BAND = (0.55, 0.80)
# 指尖的判斷：剪影還有全身最寬這個比例的最後一列。
# 手垂在身側的時候，全身最寬的地方就是兩隻手，手一結束剪影就收窄
ARM_TIP_SHARE = 0.95
# 正規化縮完之後，不透明度到這個值就算是有東西。
# 比量剪影用的 128 低很多，理由寫在 normalize 裡：救一格寬的髮尖
THIN_ALPHA_FLOOR = 40
# 胯部大約在「下巴以下那一段」的這個位置。
#
# 為什麼需要這一條：衣服會把胯部蓋住。使用者這張圖的上衣下襬垂到大腿中段、
# 褲管又寬，剪影上兩條腿要到 0.294 個全高才分得開，實際的胯部在 0.37 左右。
# 照 0.294 去建骨架，腿只有 0.46 公尺、軀幹 0.72 公尺，做出來是一個蹲著的矮胖子。
#
# **遮住只會讓看到的分岔往下跑，不會往上跑**，所以量到的分岔是下限，
# 取它和這個估計值裡比較高的那一個。這個 0.49 是從兩版角色反推的：
# 四頭身的設定圖是 0.369、上一版兩頭身的骨架是 0.301，
# 除以各自的「下巴以下有多高」都落在 0.49 附近
CROTCH_PER_BODY = 0.49


def _hsv(r, g, b):
    """回傳飽和度和明度，色相用不到就不算"""
    high = max(r, g, b)
    low = min(r, g, b)
    value = high / 255.0
    saturation = 0.0 if high == 0 else (high - low) / float(high)
    return saturation, value


def strip_background(image):
    """去背。白紙和腳下那圈灰色投影一起去掉，回傳 RGBA

    去掉的是「很亮、幾乎沒有飽和度、而且連成一大片或碰得到畫面邊緣」的那些地方。
    前兩個條件挑出紙和影子，後面那個條件保住角色身上同樣淺的一小塊。
    """
    image = image.convert("RGBA")
    width, height = image.size
    pixels = image.load()
    # 先標出所有看起來像背景的格子，再看哪幾片夠大或碰得到邊緣
    candidate = bytearray(width * height)
    for y in range(height):
        row = y * width
        for x in range(width):
            r, g, b, a = pixels[x, y]
            if a == 0:
                candidate[row + x] = 1
                continue
            saturation, value = _hsv(r, g, b)
            if value >= BG_VALUE and saturation <= BG_SATURATION:
                candidate[row + x] = 1
    blobs = []
    seen = bytearray(width * height)
    for start in range(width * height):
        if not candidate[start] or seen[start]:
            continue
        stack = [start]
        seen[start] = 1
        blob = []
        edge = False
        while stack:
            index = stack.pop()
            blob.append(index)
            y, x = divmod(index, width)
            if x == 0 or y == 0 or x + 1 == width or y + 1 == height:
                edge = True
            for step, ok in ((-1, x > 0), (1, x + 1 < width),
                             (-width, y > 0), (width, y + 1 < height)):
                near = index + step
                if ok and candidate[near] and not seen[near]:
                    seen[near] = 1
                    stack.append(near)
        blobs.append((blob, edge))
    background = bytearray(width * height)
    largest = max((len(blob) for blob, _ in blobs), default=0)
    for blob, edge in blobs:
        if edge or len(blob) >= largest * BG_RELATIVE:
            for index in blob:
                background[index] = 1
    out = image.copy()
    target = out.load()
    for y in range(height):
        row = y * width
        for x in range(width):
            if background[row + x]:
                target[x, y] = (0, 0, 0, 0)
    return out


def _components(image, alpha_floor=128):
    """把不透明的部分分成一塊一塊，回傳每一塊的包圍盒和格數"""
    width, height = image.size
    pixels = image.load()
    solid = bytearray(width * height)
    for y in range(height):
        row = y * width
        for x in range(width):
            if pixels[x, y][3] >= alpha_floor:
                solid[row + x] = 1
    seen = bytearray(width * height)
    out = []
    for start in range(width * height):
        if not solid[start] or seen[start]:
            continue
        stack = [start]
        seen[start] = 1
        x0 = x1 = start % width
        y0 = y1 = start // width
        count = 0
        while stack:
            index = stack.pop()
            count += 1
            y, x = divmod(index, width)
            if x < x0:
                x0 = x
            if x > x1:
                x1 = x
            if y < y0:
                y0 = y
            if y > y1:
                y1 = y
            for step, ok in ((-1, x > 0), (1, x + 1 < width),
                             (-width, y > 0), (width, y + 1 < height)):
                near = index + step
                if ok and solid[near] and not seen[near]:
                    seen[near] = 1
                    stack.append(near)
        out.append({"box": (x0, y0, x1 + 1, y1 + 1), "count": count})
    return out


def figures(image, already_stripped=False):
    """從一張設定圖裡切出每一個角色，由左到右

    設定圖上除了角色還有標題字和一圈裝飾外框，兩種都要丟掉。
    外框靠「一邊很長一邊很細」認出來，標題字靠高度認出來。
    """
    stripped = image if already_stripped else strip_background(image)
    width, height = stripped.size
    blobs = []
    for blob in _components(stripped):
        x0, y0, x1, y1 = blob["box"]
        span_x = (x1 - x0) / float(width)
        span_y = (y1 - y0) / float(height)
        if span_x >= FRAME_SPAN and span_y <= FRAME_THIN:
            continue
        if span_y >= FRAME_SPAN and span_x <= FRAME_THIN:
            continue
        blobs.append(blob)
    if not blobs:
        return []
    tallest = max(blob["box"][3] - blob["box"][1] for blob in blobs)
    keep = [blob for blob in blobs
            if (blob["box"][3] - blob["box"][1]) >= tallest * FIGURE_MIN_HEIGHT]
    keep.sort(key=lambda blob: blob["box"][0])
    # 同一具角色可能被分成好幾塊，例如翹起來那撮頭髮沒有連到頭上。
    # 橫向有重疊的就併成同一具
    merged = []
    for blob in keep:
        x0, y0, x1, y1 = blob["box"]
        if merged and x0 < merged[-1][2]:
            px0, py0, px1, py1 = merged[-1]
            merged[-1] = (min(px0, x0), min(py0, y0), max(px1, x1), max(py1, y1))
        else:
            merged.append((x0, y0, x1, y1))
    out = []
    for box in merged:
        crop = stripped.crop(box)
        bbox = crop.getbbox()
        out.append(crop.crop(bbox) if bbox else crop)
    return out


def row_widths(image, alpha_floor=128):
    """每一列有多寬，以及那一列最左最右在哪。全空的列回傳 0"""
    width, height = image.size
    pixels = image.load()
    out = []
    for y in range(height):
        left = None
        right = None
        for x in range(width):
            if pixels[x, y][3] >= alpha_floor:
                if left is None:
                    left = x
                right = x
        if left is None:
            out.append((0, 0, 0))
        else:
            out.append((right - left + 1, left, right))
    return out


def _open_binary(image, radius, alpha_floor=128):
    """二值開運算：先侵蝕再膨脹，磨掉比半徑細的突起

    用來把翹出去的髮尖磨掉再量頭寬，照 docs/美術風格指南.md 第 2.1 節。
    只回傳一張遮罩不回傳圖，量寬度用得到的只有遮罩
    """
    width, height = image.size
    pixels = image.load()
    mask = bytearray(width * height)
    for y in range(height):
        row = y * width
        for x in range(width):
            if pixels[x, y][3] >= alpha_floor:
                mask[row + x] = 1
    if radius <= 0:
        return mask
    return _sweep(_sweep(mask, width, height, radius, False), width, height, radius, True)


def _sweep(source, width, height, radius, dilate):
    """方形結構元素的一次侵蝕或膨脹

    方形可以拆成先橫掃一次再直掃一次，兩次都是一維的。
    直接掃方形是半徑平方的成本，拆開之後是半徑的兩倍
    """
    middle = bytearray(width * height)
    for y in range(height):
        row = y * width
        for x in range(width):
            low = max(0, x - radius)
            high = min(width - 1, x + radius)
            run = [source[row + i] for i in range(low, high + 1)]
            hit = any(run) if dilate else (all(run) and high - low == radius * 2)
            middle[row + x] = 1 if hit else 0
    out = bytearray(width * height)
    for y in range(height):
        row = y * width
        low = max(0, y - radius)
        high = min(height - 1, y + radius)
        for x in range(width):
            run = [middle[j * width + x] for j in range(low, high + 1)]
            hit = any(run) if dilate else (all(run) and high - low == radius * 2)
            out[row + x] = 1 if hit else 0
    return out


def landmarks(image, alpha_floor=128):
    """量出頭頂、脖子、腳底在第幾列

    脖子是頭和肩膀之間**最窄**的那一列，而且只在「頭最寬的那一列以下、
    全高的四成以上」這一段裡找。兩個限制都是踩到才加的：

    - 不從頭頂開始找，因為翹出去那撮呆毛只有一兩格寬，它一定是最窄的一列。
      使用者這張圖照那樣量到的頭高是 2 格，頭身比 274
    - 不找到全身最窄，因為有些角色的腰比脖子還窄
    """
    widths = row_widths(image, alpha_floor)
    rows = [y for y, (w, _, _) in enumerate(widths) if w > 0]
    if not rows:
        raise ValueError("這張圖是空的，量不到任何東西")
    top, bottom = rows[0], rows[-1]
    total = bottom - top + 1
    limit = min(bottom, top + max(2, int(total * NECK_SEARCH)))
    look = max(2, int(total * NECK_LOOK_DOWN))
    neck = None
    best = None
    widest_above = 0
    for y in range(top, limit):
        width = widths[y][0]
        below = max(widths[j][0] for j in range(y + 1, min(bottom, y + look) + 1))
        if (width > 0 and widest_above >= width * NECK_SHOULDER_RATIO
                and below >= width * NECK_SHOULDER_RATIO
                and (best is None or width < best)):
            best = width
            neck = y
        if width > widest_above:
            widest_above = width
    if neck is None:
        raise ValueError("找不到脖子，這張圖的形狀不像一個人")
    return {"top": top, "neck": neck, "bottom": bottom, "widths": widths}


def _median(values):
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _runs(image, y, alpha_floor=128):
    """某一列上不透明的區段，回傳每段的起迄"""
    width = image.size[0]
    pixels = image.load()
    out = []
    start = None
    for x in range(width):
        solid = pixels[x, y][3] >= alpha_floor
        if solid and start is None:
            start = x
        elif not solid and start is not None:
            out.append((start, x - 1))
            start = None
    if start is not None:
        out.append((start, width - 1))
    return out


def measure(image, alpha_floor=128):
    """量一具角色的全套比例，回傳的數字有的是格數有的是比值

    量法和 docs/美術風格指南.md 第 2.1 節同一套：
    剪影從 alpha 切出來、頭高從髮際輪廓最高點量到下巴、全高量到鞋底、
    量頭寬之前先做一次開運算把髮尖磨掉。
    """
    marks = landmarks(image, alpha_floor)
    top, neck, bottom = marks["top"], marks["neck"], marks["bottom"]
    widths = marks["widths"]
    total = bottom - top + 1
    head_height = neck - top + 1

    opened = _open_binary(image, max(1, int(round(head_height * HEAD_OPEN_RATIO))), alpha_floor)
    image_width = image.size[0]
    head_width = 0
    for y in range(top, neck + 1):
        row = y * image_width
        run = sum(1 for x in range(image_width) if opened[row + x])
        if run > head_width:
            head_width = run
    if head_width == 0:
        head_width = max(widths[y][0] for y in range(top, neck + 1))

    # 肩寬量脖子往下一小段裡最寬的一列。往下太多會量到手臂外側，
    # 往下太少會還在脖子上
    shoulder_band = (neck, min(bottom, neck + max(2, int(head_height * 0.45))))
    shoulder_width = max(widths[y][0] for y in range(shoulder_band[0], shoulder_band[1] + 1))
    # 肩線是脖子往下第一次寬到肩寬九成的那一列。
    # 不能拿脖子那一列當肩線，那一列量到的是下巴，換算出來永遠等於 1 減去頭身比的倒數，
    # 是一個看起來有量其實沒有量的數字
    shoulder_row = shoulder_band[1]
    for y in range(shoulder_band[0], shoulder_band[1] + 1):
        if widths[y][0] >= shoulder_width * 0.90:
            shoulder_row = y
            break
    # 整具最寬的一列，高寬比用它算。手臂垂著的時候這一列通常在手肘附近
    body_width = max(widths[y][0] for y in range(top, bottom + 1))

    # 胯部：脖子以下最長的一段「兩條腿分得開」的連續列，取它的最上面那一列。
    #
    # 不要只從腳底往上找第一個合不起來的地方。兩隻腳不會踩在同一條線上，
    # 最底下那幾列常常只有一隻靴子，那是一段不是兩段，照那樣找胯部會落在腳底。
    # 也不要從上往下找，腋下那個洞也是兩段
    split = [y for y in range(neck + 1, bottom + 1)
             if len(_runs(image, y, alpha_floor)) >= 2]
    block = []
    best_block = []
    previous = None
    for y in split:
        if previous is not None and y == previous + 1:
            block.append(y)
        else:
            block = [y]
        if len(block) > len(best_block):
            best_block = list(block)
        previous = y
    if best_block:
        crotch = best_block[0]
    else:
        crotch = neck + int((bottom - neck) * 0.52)
        best_block = list(range(crotch, bottom + 1))

    # 腿寬和站距量在小腿那一段，不量膝蓋也不量最下面那一列。
    # 膝蓋那一段可能被裙襬或下襬蓋住，量到的是衣服的寬度；
    # 最下面那幾列是靴子的尖端，一邊才剛開始出現，量到的是四格寬的一個角
    low = best_block[int(len(best_block) * LEG_BAND[0])]
    high = best_block[int(len(best_block) * LEG_BAND[1])]
    ankle = (low + high) // 2
    stances = []
    leg_widths = []
    for y in range(low, high + 1):
        runs = _runs(image, y, alpha_floor)
        if len(runs) < 2:
            continue
        left, right = runs[0], runs[-1]
        stances.append(((right[0] + right[1]) - (left[0] + left[1])) / 2.0)
        leg_widths.append(min(left[1] - left[0] + 1, right[1] - right[0] + 1))
    stance = _median(stances) if stances else widths[ankle][0] * 0.5
    leg_width = _median(leg_widths) if leg_widths else widths[ankle][0] * 0.45

    # 手臂長：手垂著的時候剪影在指尖那裡會明顯收窄，所以從肩關節那一列量到
    # 「還有九成五全身寬」的最後一列。
    # 起點取肩關節不取肩線：肩關節掛在肩線下面一截，從肩線量會多算那一截
    arm_band = rigspec.ARM_BAND
    split_h = (bottom - crotch) / float(total)
    # 下巴以下有多高，乘上 CROTCH_PER_BODY 就是胯部的估計值
    estimate = (1.0 - head_height / float(total)) * CROTCH_PER_BODY
    crotch_h = max(split_h, estimate)
    shoulder_h = (bottom - shoulder_row) / float(total)
    arm_root_h = crotch_h + (shoulder_h - crotch_h) * arm_band
    arm_root_row = int(round(bottom - arm_root_h * total))
    tip_row = None
    for y in range(max(arm_root_row, top + 1), crotch + 1):
        if widths[y][0] >= body_width * ARM_TIP_SHARE:
            tip_row = y
    arm_span = ((tip_row - arm_root_row) / float(total)) if tip_row else 0.0

    return {
        "total_px": total,
        "head_px": head_height,
        "head_width_px": head_width,
        "shoulder_px": shoulder_width,
        "body_width_px": body_width,
        "leg_width_px": leg_width,
        "stance_px": stance,
        "top": top,
        "neck": neck,
        "crotch": crotch,
        "ankle": ankle,
        "bottom": bottom,
        "shoulder_row": shoulder_row,
        "shoulder_per_height": shoulder_h,
        "arm_span_per_height": arm_span,
        "head_ratio": total / float(head_height),
        "head_width_per_head": head_width / float(head_height),
        "shoulder_per_head_width": shoulder_width / float(head_width),
        "leg_width_per_head_width": leg_width / float(head_width),
        "stance_per_head_width": stance / float(head_width),
        "crotch_per_height": crotch_h,
        "crotch_split_per_height": split_h,
        "crotch_covered": split_h < estimate,
        "aspect": total / float(body_width),
    }


def to_spec(reading, base=None):
    """把量到的比例填進骨架參數，量不到的項目沿用 base 那一份

    量得到的只有正視圖上看得出來的那幾項。前臂佔手臂多長、軀幹前後多厚
    這種要側視圖才量得到的，沿用 base。這一條刻意留著不猜，
    猜出來的數字會安靜地變成契約的一部分，之後沒有人知道它是猜的
    """
    base = base or rigspec.STANDARD
    return base.replace(
        head_ratio=reading["head_ratio"],
        head_width_per_head=reading["head_width_per_head"],
        shoulder_per_head_width=reading["shoulder_per_head_width"],
        leg_width_per_head_width=reading["leg_width_per_head_width"],
        stance_per_head_width=reading["stance_per_head_width"],
        crotch_per_height=reading["crotch_per_height"],
        shoulder_per_height=reading["shoulder_per_height"],
        arm_span_per_height=reading["arm_span_per_height"],
    )


def normalize(image, ratio=None, alpha_floor=128):
    """把一張設定圖調到指定的頭身比，全高不變

    做法是把頭和身體兩段各自縮放再接回去。全高不變這一點很重要：
    角色在遊戲裡是 1.57 公尺、貼圖 100 像素高，那是骨架契約的一部分，
    設定圖的比例可以變，佔的高度不能變。

    頭是連寬度一起縮的，身體只改高度不改寬度。頭要保持自己的長寬比，
    不然縮完是一顆壓扁的頭；身體加寬會讓人變胖，那不是頭身比要解決的事。
    """
    spec_ratio = ratio if ratio is not None else rigspec.STANDARD.head_ratio
    marks = landmarks(image, alpha_floor)
    top, neck, bottom = marks["top"], marks["neck"], marks["bottom"]
    total = bottom - top + 1
    head_height = neck - top + 1
    width = image.size[0]

    new_head = max(1, int(round(total / spec_ratio)))
    new_body = total - new_head
    if new_body < 1:
        raise ValueError("頭身比 %.2f 太小，身體會沒有高度" % spec_ratio)
    head = image.crop((0, top, width, neck + 1))
    head = head.resize((max(1, int(round(width * new_head / float(head_height)))), new_head),
                       Image.LANCZOS)
    body = image.crop((0, neck + 1, width, bottom + 1)).resize((width, new_body), Image.LANCZOS)

    # 頭縮完寬度變了，要對齊脖子那一列的中心再貼回去，不然頭會往一邊飄
    run = _runs(image, neck, alpha_floor)
    if run:
        neck_centre = (run[0][0] + run[-1][1] + 1) / 2.0
    else:
        neck_centre = width / 2.0
    offset = int(round(neck_centre - head.size[0] * (neck_centre / float(width))))

    out = Image.new("RGBA", (width, image.size[1]), (0, 0, 0, 0))
    out.paste(head, (offset, top), head)
    out.paste(body, (0, top + new_head), body)
    # 縮完的邊緣是半透明的，一定要再切回全有全無。
    # 門檻刻意抓得比量剪影的低很多：一格寬的髮尖縮完只剩三成不透明度，
    # 照 128 去切它會整根消失，全高跟著少幾格，正規化的「全高不變」當場破功。
    # 代價是剪影四周可能胖一格，那比少掉一根髮尖好
    alpha = out.getchannel("A").point(lambda v: 255 if v >= THIN_ALPHA_FLOOR else 0)
    out.putalpha(alpha)
    return out


def _print_measure(path):
    image = Image.open(path)
    found = figures(image)
    if not found:
        print("%s 裡面找不到角色" % path)
        return
    for index, figure in enumerate(found):
        reading = measure(figure)
        print("[%s 第 %d 具] %d x %d 格" % (os.path.basename(path), index,
                                            figure.size[0], reading["total_px"]))
        print("  頭身比 %.2f，頭高 %d 格、全高 %d 格"
              % (reading["head_ratio"], reading["head_px"], reading["total_px"]))
        print("  頭寬 %.3f 個頭高、肩寬 %.3f 個頭寬、單腿寬 %.3f 個頭寬、站距 %.3f 個頭寬"
              % (reading["head_width_per_head"], reading["shoulder_per_head_width"],
                 reading["leg_width_per_head_width"], reading["stance_per_head_width"]))
        print("  胯高佔全高 %.3f%s、肩線高佔全高 %.3f、手臂長佔全高 %.3f、全身高寬比 %.2f"
              % (reading["crotch_per_height"],
                 ("，剪影分岔在 %.3f 被衣服蓋住" % reading["crotch_split_per_height"]
                  if reading["crotch_covered"] else ""),
                 reading["shoulder_per_height"],
                 reading["arm_span_per_height"], reading["aspect"]))


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    command = args[0]
    if command == "measure":
        _print_measure(args[1])
    elif command == "spec":
        image = Image.open(args[1])
        found = figures(image)
        if not found:
            raise SystemExit("找不到角色")
        spec = to_spec(measure(found[0]))
        print(spec.table())
    elif command == "cut":
        image = Image.open(args[1])
        prefix = args[2]
        for index, figure in enumerate(figures(image)):
            out = "%s_%d.png" % (prefix, index)
            figure.save(out)
            print("%s  %d x %d" % (out, figure.size[0], figure.size[1]))
    elif command == "normalize":
        ratio = None
        if "--ratio" in args:
            ratio = float(args[args.index("--ratio") + 1])
        image = Image.open(args[1])
        found = figures(image)
        source = found[0] if found else image.convert("RGBA")
        before = measure(source)
        out = normalize(source, ratio)
        after = measure(out)
        out.save(args[2])
        print("%s  頭身比 %.2f → %.2f，全高 %d → %d 格"
              % (args[2], before["head_ratio"], after["head_ratio"],
                 before["total_px"], after["total_px"]))
    else:
        raise SystemExit("不認得的指令 %s" % command)


if __name__ == "__main__":
    main()
