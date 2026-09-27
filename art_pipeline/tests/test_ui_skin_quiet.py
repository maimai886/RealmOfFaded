"""quiet 介面皮膚的質感門檻。

使用者看了第一版的回覆是「配色是對了 但是沒有質感」，指出來的八件事各自都量得到：
標題列沒有漸層、面板沒有紙紋、格子不凹、落影看不見、圓角太小、按鈕平的。
這裡把每一項變成一個數字擋住，之後有人把層次調掉會直接紅。

量的是 assets/ui/skin 產出來的實際像素，不是看縮圖猜的。
跑法和其他美術管線測試一樣：blender -b --factory-startup --python-exit-code 1 -P art_pipeline/tests/run.py
"""
import os

# Blender 內建的 Python 沒有 Pillow，run.py 看到這個旗標會改叫系統的 python3 跑
NEEDS_PILLOW = True

PIPELINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(PIPELINE_DIR)
SKIN_DIR = os.path.join(PROJECT_ROOT, "assets", "ui", "skin")


def _open(name):
    from PIL import Image
    return Image.open(os.path.join(SKIN_DIR, name + ".png")).convert("RGBA")


def _lum(pixel):
    return 0.2126 * pixel[0] + 0.7152 * pixel[1] + 0.0722 * pixel[2]


def test_titlebar_is_a_light_blue_band():
    """標題列是一整片淺藍，而且要是「好看的淺藍」

    這條門檻改過三次，因為需求本身變了：
    最早是不透明的淡藍帶子，被嫌像兩塊拼起來；砍成一條線又太弱；
    現在使用者要淡藍回來，但要淡、要乾淨、要和暖白的內容區搭得起來。
    所以這裡擋的是色相在藍、飽和壓得夠低、明度夠高，三個條件同時成立。
    太飽和會變成幼稚的水藍，太灰會變回死板的藍灰，兩邊都擋。
    """
    import colorsys
    bar = _open("titlebar")
    width, height = bar.size
    column = width // 2
    inside = bar.getpixel((column, height // 2))
    assert inside[3] == 255, "標題列中間應該是實心的，實際透明度 %d" % inside[3]
    hue, saturation, value = colorsys.rgb_to_hsv(*[v / 255.0 for v in inside[:3]])
    assert 195 <= hue * 360 <= 235, "標題列的色相 %.0f 不在藍色範圍" % (hue * 360)
    assert 0.03 <= saturation <= 0.16, "標題列的飽和 %.1f%% 不在 3 到 16 之間" % (saturation * 100)
    assert value >= 0.85, "標題列的明度 %.1f%% 太低，不是淺藍" % (value * 100)


def test_titlebar_keeps_its_highlight_gradient_and_separator():
    """加了藍色也不能把前幾輪做對的東西拆掉：上緣亮線、往下收的漸層、底下的分隔線"""
    bar = _open("titlebar")
    width, height = bar.size
    column = width // 2
    lit = _lum(bar.getpixel((column, 0)))
    near = _lum(bar.getpixel((column, 3)))
    assert lit - near >= 4.0, "上緣亮線只比下面亮 %.2f" % (lit - near)
    band_top = _lum(bar.getpixel((column, 3)))
    band_low = _lum(bar.getpixel((column, height - 4)))
    assert band_top - band_low >= 6.0, "標題列上下只差 %.2f，漸層太平" % (band_top - band_low)
    separator = bar.getpixel((column, height - 1))
    assert 10 <= separator[3] <= 60, "分隔線的不透明度 %d 不在 10 到 60 之間" % separator[3]
    assert _lum(separator) <= 80, "分隔線要是深色的，實際亮度 %.1f" % _lum(separator)


def test_titlebar_top_corners_fit_inside_the_window_radius():
    """填色之後上面兩角一定要收圓，不然會在視窗的圓角外面露出方角"""
    from ui import skin
    bar = _open("titlebar")
    assert bar.getpixel((0, 0))[3] < 40, "標題列左上角應該是空的，圓角沒收"
    assert bar.getpixel((bar.size[0] - 1, 0))[3] < 40, "標題列右上角應該是空的，圓角沒收"
    # 圓角要塞得進上切邊，跨過去會被拉伸糊掉
    margin_top = skin.SKIN["titlebar"]["margin"][1]
    assert margin_top >= 10, "上切邊 %d 裝不下標題列的圓角" % margin_top


def test_panel_has_measurable_paper_grain():
    """面板要有真的紙紋：相鄰像素有差、峰谷差看得到，但不能大到變成雜點"""
    window = _open("window")
    patch = [window.getpixel((x, y)) for y in range(52, 76) for x in range(52, 76)]
    values = [_lum(p) for p in patch]
    mean = sum(values) / len(values)
    deviation = (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5
    spread = max(values) - min(values)
    neighbour = []
    for y in range(52, 76):
        for x in range(52, 75):
            neighbour.append(abs(_lum(window.getpixel((x, y))) - _lum(window.getpixel((x + 1, y)))))
    average = sum(neighbour) / len(neighbour)
    assert average >= 0.5, "相鄰像素差只有 %.3f，紙紋等於被縮圖平均掉了" % average
    assert 0.8 <= deviation <= 2.2, "紙紋標準差 %.3f 不在 0.8 到 2.2 之間" % deviation
    assert 4.0 <= spread <= 10.0, "紙紋峰谷差 %.2f 不在 4 到 10 之間" % spread


def test_panel_grain_tiles_without_a_seam():
    """九宮格中段會鋪磚，接縫處的落差要和一般相鄰像素一樣，不然會看到格線"""
    window = _open("window")
    rows = range(48, 80)
    interior = []
    for y in rows:
        for x in range(48, 79):
            interior.append(abs(_lum(window.getpixel((x, y))) - _lum(window.getpixel((x + 1, y)))))
    average = sum(interior) / len(interior)
    wrap = [abs(_lum(window.getpixel((79, y))) - _lum(window.getpixel((48, y)))) for y in rows]
    seam = sum(wrap) / len(wrap)
    assert seam <= average * 1.6 + 0.5, "橫向接縫落差 %.3f 比一般相鄰差 %.3f 大太多" % (seam, average)


def _window_rect():
    """視窗本體在圖上的範圍，切邊表改了這裡跟著改"""
    from ui import skin
    spec = skin.SKIN["window"]
    pad = spec["expand"]
    return pad[0], pad[1], spec["size"][0] - pad[2], spec["size"][1] - pad[3]


def test_window_shadow_is_large_and_soft():
    """影子要大而淡不是小而深，視窗才像浮在畫面上而不是貼上去的

    量兩件事：本體外面最濃的那一點不能太黑，以及影子往外鋪得夠遠。
    """
    window = _open("window")
    left, top, right, bottom = _window_rect()
    middle = (top + bottom) // 2
    side = [window.getpixel((x, middle))[3] for x in range(0, left)]
    below = [window.getpixel(((left + right) // 2, y))[3] for y in range(bottom, window.size[1])]
    assert max(side) <= 70, "側邊影子最濃 %d，太深了" % max(side)
    assert max(below) <= 90, "下方影子最濃 %d，太深了" % max(below)
    reach_side = sum(1 for v in side if v >= 6)
    reach_below = sum(1 for v in below if v >= 6)
    assert reach_side >= 10, "側邊影子只鋪得開 %d 格" % reach_side
    assert reach_below >= 14, "下方影子只鋪得開 %d 格" % reach_below


def test_window_edge_is_a_translucent_hairline():
    """邊界是一層很薄的深色，不是一條不透明的灰線

    不透明的線壓在草地上和壓在暗場裡都是同一條，看起來像畫上去的；
    半透明的邊界會跟著底下的東西走，那才是 macOS 的樣子。
    """
    window = _open("window")
    left, top, right, bottom = _window_rect()
    middle = (top + bottom) // 2
    edge = window.getpixel((left, middle))
    body = window.getpixel((left + 6, middle))
    assert 20 <= edge[3] <= 60, "邊界的不透明度 %d 不在 20 到 60 之間" % edge[3]
    assert _lum(edge) <= 60, "邊界要是深色的，實際亮度 %.1f" % _lum(edge)
    assert body[3] >= 230, "本體應該幾乎不透明，實際 %d" % body[3]


def test_window_is_lit_from_the_top_only():
    """上緣內側一條近白的亮線，下緣和左右都沒有，光才是從上面來的

    面板上鋪了正負三階的紙紋，單獨抓一個像素比會被顆粒帶著跑，所以兩邊都取一段的平均。
    """
    window = _open("window")
    left, top, right, bottom = _window_rect()
    columns = range(left + 20, right - 20)

    def band(rows):
        values = [_lum(window.getpixel((x, y))) for y in rows for x in columns]
        return sum(values) / len(values)

    rim = band([top + 1])
    body = band(range(top + 4, top + 10))
    foot = band(range(bottom - 7, bottom - 1))
    side = sum(_lum(window.getpixel((left + 1, y)))
               for y in range(top + 20, bottom - 20)) / len(range(top + 20, bottom - 20))
    assert rim - body >= 5.0, "上緣亮線只比本體亮 %.2f" % (rim - body)
    assert abs(side - body) <= 6.0, "左緣不該有亮線或暗線，差了 %.2f" % (side - body)
    assert foot - body <= 5.0, "下緣不該比本體亮，差了 %.2f" % (foot - body)


def test_window_corners_are_soft():
    """圓角要夠大，越大越像現代系統視窗，越小越像遊戲對話框

    量法是走左上角的對角線，找第幾格開始是不透明的面板。
    圓心在角落往內 r 格的地方，所以弧線和對角線的交點離角落是 r 乘以 0.293。
    最外一圈是半透明的 hairline，所以門檻放在 150 而不是 200。
    """
    window = _open("window")
    left, top, right, bottom = _window_rect()
    crossing = None
    for step in range(0, 20):
        if window.getpixel((left + step, top + step))[3] > 150:
            crossing = step
            break
    assert crossing is not None, "左上角找不到面板"
    radius = crossing / 0.293
    assert crossing >= 3, "對角線第 %d 格就進面板了，圓角大約只有 %.1f，太小" % (crossing, radius)


def test_corners_and_shadows_stay_inside_the_slice():
    """圓角加影子都要塞得進九宮格的切邊，跨過去就會被拉伸糊掉"""
    from ui import skin
    for name, radius in (("window", 11), ("dialogue", 11), ("hud", 7), ("tooltip", 8)):
        spec = skin.SKIN[name]
        for index in range(4):
            reach = spec["expand"][index] + radius
            assert reach <= spec["margin"][index], \
                "%s 第 %d 邊：影子加圓角 %d 超過切邊 %d" % (name, index, reach, spec["margin"][index])


def test_slot_is_recessed():
    """格子要往內凹：上緣比中央暗、下緣比中央亮"""
    slot = _open("slot")
    width, height = slot.size
    centre = _lum(slot.getpixel((width // 2, height // 2)))
    top = _lum(slot.getpixel((width // 2, 6)))
    bottom = _lum(slot.getpixel((width // 2, height - 7)))
    assert centre - top >= 10.0, "格子上緣只比中央暗 %.2f" % (centre - top)
    assert bottom - centre >= 5.0, "格子下緣只比中央亮 %.2f" % (bottom - centre)


def test_buttons_read_as_raised_and_pressed():
    """浮起的上緣比下緣亮，按下的反過來，兩者差距要拉得開"""
    raised = _open("button")
    pressed = _open("button_pressed")
    def span(image):
        width, height = image.size
        return _lum(image.getpixel((width // 2, 5))) - _lum(image.getpixel((width // 2, height - 8)))
    up = span(raised)
    down = span(pressed)
    assert up >= 10.0, "浮起的按鈕上下只差 %.2f" % up
    assert down <= -14.0, "按下的按鈕上下差 %.2f，看不出陷下去" % down


def test_bar_track_is_a_groove():
    """數值條的溝也要凹，不是一條灰色"""
    track = _open("bar_track")
    width, height = track.size
    centre = _lum(track.getpixel((width // 2, height // 2)))
    top = _lum(track.getpixel((width // 2, 1)))
    bottom = _lum(track.getpixel((width // 2, height - 2)))
    assert centre - top >= 8.0, "溝的上緣只比中央暗 %.2f" % (centre - top)
    assert bottom - centre >= 4.0, "溝的下緣只比中央亮 %.2f" % (bottom - centre)


def test_every_window_glyph_exists_and_is_distinct():
    """每個視窗一顆自己的記號，而且彼此的形狀真的不一樣"""
    from ui import skin
    shapes = {}
    for name in skin.QUIET_EMBLEMS:
        image = _open("emblem_" + name)
        wanted = skin.EMBLEM_LOGICAL * skin.EMBLEM_SCALE
        assert image.size == (wanted, wanted), "%s 不是 %d×%d" % (name, wanted, wanted)
        alpha = image.getchannel("A")
        filled = sum(1 for v in alpha.getdata() if v > 64)
        assert filled >= 24 * skin.EMBLEM_SCALE * skin.EMBLEM_SCALE, \
            "%s 只有 %d 個實心像素，太空了" % (name, filled)
        shapes[name] = tuple(1 if v > 64 else 0 for v in alpha.getdata())
    for name, shape in shapes.items():
        same = [other for other, value in shapes.items() if other != name and value == shape]
        assert not same, "%s 和 %s 長得一模一樣" % (name, same)


def test_grained_pieces_tile_on_the_grain_period():
    """有鋪紙紋的九宮格，中段長寬都要是紙紋週期的整數倍

    不然每鋪一次就換一個相位，面板上會每隔一段冒出一條橫線或直線。
    第一版就是在道具欄的內框看到這種橫線才發現的。
    """
    from ui import skin
    grained = ["window", "dialogue", "inset", "input", "input_focus", "select",
               "choice", "choice_hover", "choice_on", "slot", "slot_hover",
               "button", "button_hover", "button_pressed", "button_disabled",
               "button_accent", "button_accent_hover", "button_accent_pressed", "tooltip", "page"]
    period = skin.GRAIN_PERIOD
    for name in grained:
        spec = skin.SKIN[name]
        middle_x = spec["size"][0] - spec["margin"][0] - spec["margin"][2]
        middle_y = spec["size"][1] - spec["margin"][1] - spec["margin"][3]
        assert middle_x % period == 0, "%s 的中段寬 %d 不是 %d 的整數倍" % (name, middle_x, period)
        assert middle_y % period == 0, "%s 的中段高 %d 不是 %d 的整數倍" % (name, middle_y, period)


def test_tiled_middles_have_no_vertical_banding():
    """會鋪磚的中段不能自己帶垂直漸層

    帶了的話每鋪一次就重來一次，面板上會出現一排等距的橫帶。
    量的是中段每一列的平均亮度，起伏只能是紙紋的雜訊，不能是一路往下的斜坡。
    """
    for name, margin in (("window", (47, 49)), ("inset", (8, 8)), ("button", (11, 13)),
                         ("select", (8, 8)), ("tooltip", (15, 17))):
        image = _open(name)
        width, height = image.size
        columns = range(margin[0], width - margin[0])
        rows = []
        for y in range(margin[0], height - margin[1]):
            rows.append(sum(_lum(image.getpixel((x, y))) for x in columns) / len(list(columns)))
        spread = max(rows) - min(rows)
        assert spread <= 2.0, "%s 中段每列的平均亮度差 %.2f，會看到橫帶" % (name, spread)


def test_every_button_state_keeps_the_text_readable():
    """按鈕的每一種狀態都要和深色字拉得開

    2026-09-18 滑過去的底色是 255 幾乎純白，比面板還白，
    使用者滑到按鈕上字就整顆不見了。這條守的是「不准用更白的白表示滑過」：
    每一種狀態對深色字的對比至少 3:1，而且滑過的底不可以比一般狀態更亮。
    """
    from ui import skin

    def luminance(image):
        width, height = image.size
        pixels = [image.getpixel((x, y)) for y in range(height // 2 - 2, height // 2 + 3)
                  for x in range(width // 2 - 4, width // 2 + 5)]
        opaque = [p for p in pixels if p[3] > 240]
        assert opaque, "按鈕中央不該是透明的"
        return sum(_lum(p) for p in opaque) / len(opaque)

    ink = _lum(tuple(skin.P["ink"]) + (255,)) if "ink" in skin.P else _lum((60, 58, 53, 255))
    states = {}
    for name in ("button", "button_hover", "button_pressed", "button_disabled"):
        states[name] = luminance(_open(name))
        contrast = (max(states[name], ink) + 5) / (min(states[name], ink) + 5)
        assert contrast >= 3.0, "%s 的底和深色字只差 %.1f 比 1，字會看不清楚" % (name, contrast)
    assert states["button_hover"] <= states["button"], \
        "滑過的底比一般狀態還亮 %.1f 階，那是用更白的白表示滑過" % (states["button_hover"] - states["button"])
