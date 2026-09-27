"""設定圖量測和正規化的測試

用畫出來的假人測，不吃專案裡的圖檔。假人刻意做成會踩到每一個坑的樣子：
白底、腳下一圈灰影、頭上翹一根一像素寬的呆毛、衣服上有一塊很亮的白。
"""
import os
import sys

# Blender 內建的 Python 沒有 Pillow，run.py 看到這個旗標會改叫系統的 python3 跑。
# 所以這個檔案的頂層不能 import PIL，不然在 Blender 裡光是載入就會爆掉
NEEDS_PILLOW = True

HERE = os.path.dirname(os.path.abspath(__file__))
CHARACTERS = os.path.join(os.path.dirname(HERE), "characters_v3")
if CHARACTERS not in sys.path:
    sys.path.insert(0, CHARACTERS)

# 假人的尺寸，格。呆毛 8、頭 40、身體 120，量出來的頭身比是 (8+40+120)/(8+40)=3.5
SPIKE = 8
HEAD = 40
BODY = 120
RATIO = (SPIKE + HEAD + BODY) / float(SPIKE + HEAD)
MID = 60
TOP = 10
NECK = TOP + HEAD


def _pil():
    from PIL import Image, ImageDraw
    return Image, ImageDraw


def _ds():
    """designsheet 自己要 Pillow，所以也不能在頂層匯入"""
    import designsheet
    return designsheet


def dummy(highlight=True, hem=0):
    """畫一個假人，白底加腳下的灰影

    刻意做成會踩到每一個坑：一格寬的呆毛、亮到接近紙的高光、腳下的灰影。
    脖子畫成真的一小截細的，因為量法找的就是「頭和肩膀之間最窄的一列」
    """
    Image, ImageDraw = _pil()
    width = 120
    height = TOP + HEAD + BODY + 30
    image = Image.new("RGB", (width, height), (254, 254, 254))
    draw = ImageDraw.Draw(image)
    # 腳下的灰影，明度 0.82 幾乎沒有飽和度，和背景一樣要被去掉
    draw.ellipse((20, height - 22, 100, height - 6), fill=(209, 209, 209))
    # 一格寬的呆毛。不處理的話它會被當成最窄的一列，頭高就只剩兩格
    draw.line((MID, TOP - SPIKE, MID, TOP), fill=(120, 80, 50))
    draw.ellipse((MID - 18, TOP, MID + 18, NECK), fill=(160, 110, 70))
    draw.rectangle((MID - 5, NECK, MID + 5, NECK + 5), fill=(200, 160, 130))
    draw.rectangle((MID - 26, NECK + 5, MID + 26, NECK + 55), fill=(90, 120, 90))
    if highlight:
        # 衣服上的高光，很亮又幾乎沒有飽和度，但四面被角色包住，不能被當成背景挖掉
        draw.rectangle((MID - 6, NECK + 20, MID + 6, NECK + 32), fill=(250, 250, 250))
    # 手臂垂在身側
    for side in (-1, 1):
        draw.rectangle((MID + side * 34 - 6, NECK + 8, MID + side * 34 + 6, NECK + 62),
                       fill=(200, 160, 130))
    # 兩條腿，中間留縫
    for side in (-1, 1):
        draw.rectangle((MID + side * 14 - 8, NECK + 55, MID + side * 14 + 8, NECK + BODY),
                       fill=(70, 60, 55))
    if hem:
        # 蓋到大腿的下襬，剪影上兩條腿要更下面才分得開
        draw.rectangle((MID - 26, NECK + 55, MID + 26, NECK + 55 + hem), fill=(90, 120, 90))
    return image


def figure():
    return _ds().figures(dummy())[0]


def test_去背會把白紙和腳下的灰影一起去掉():
    stripped = _ds().strip_background(dummy())
    pixels = stripped.load()
    assert pixels[2, 2][3] == 0, "角落的白紙沒有去掉"
    assert pixels[60, stripped.size[1] - 14][3] == 0, "腳下的灰影沒有去掉"


def test_去背不會把角色身上那塊亮色挖掉():
    stripped = _ds().strip_background(dummy())
    pixels = stripped.load()
    assert pixels[MID, NECK + 26][3] > 0, "衣服上的高光被當成背景挖掉了"


def test_翹起來那根呆毛不會被當成脖子():
    marks = _ds().landmarks(figure())
    head = marks["neck"] - marks["top"] + 1
    assert head > HEAD * 0.8, "頭只量到 %d 格，呆毛把脖子騙走了" % head


def test_量到的頭身比就是畫出來的那個():
    reading = _ds().measure(figure())
    assert abs(reading["head_ratio"] - RATIO) / RATIO < 0.06, reading["head_ratio"]


def test_正規化之後量到的頭身比就是指定的那個():
    source = figure()
    for ratio in (3.0, 4.07, 5.0):
        out = _ds().normalize(source, ratio)
        got = _ds().measure(out)["head_ratio"]
        assert abs(got - ratio) / ratio < 0.06, (ratio, got)


def test_正規化不會改全高():
    source = figure()
    before = _ds().measure(source)["total_px"]
    for ratio in (3.0, 5.0):
        after = _ds().measure(_ds().normalize(source, ratio))["total_px"]
        assert abs(after - before) <= 1, (ratio, before, after)


def test_衣服蓋住胯部的時候會照下巴以下的比例推回去():
    """下襬遮住只會讓看到的分岔往下跑，所以量到的分岔是下限不是答案"""
    reading = _ds().measure(_ds().figures(dummy(hem=40))[0])
    assert reading["crotch_covered"], "沒有認出胯部被蓋住"
    assert reading["crotch_per_height"] > reading["crotch_split_per_height"]


def test_切圖會丟掉外框和標題字():
    Image, ImageDraw = _pil()
    sheet = Image.new("RGB", (400, 300), (254, 254, 254))
    draw = ImageDraw.Draw(sheet)
    draw.rectangle((6, 4, 393, 295), outline=(150, 150, 150), width=2)
    draw.rectangle((30, 20, 90, 40), fill=(20, 20, 20))
    person = dummy()
    sheet.paste(person, (150, 60))
    found = _ds().figures(sheet)
    assert len(found) == 1, "切出來 %d 個，外框或標題字沒有丟掉" % len(found)


def test_一張圖裡兩個角色會由左到右切出來():
    Image, _ = _pil()
    sheet = Image.new("RGB", (400, 260), (254, 254, 254))
    person = dummy()
    sheet.paste(person, (40, 20))
    sheet.paste(person, (240, 20))
    found = _ds().figures(sheet)
    assert len(found) == 2, len(found)


def test_量到的比例可以直接變成骨架參數():
    spec = _ds().to_spec(_ds().measure(figure()))
    assert spec.head_ratio > 1.0
    assert 0.0 < spec.crotch_per_height < 1.0
    assert len(spec.joints()) == 62
