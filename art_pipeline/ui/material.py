"""
介面素材的共用處理：把 AI 產的原圖變成可以直接用的材質、去背的painted零件和圖示。
只靠 Pillow。skin.py 和 icons.py 都從這裡取工具。

三件事：
- grade：把任何一張原圖的明暗重新對應到指定的深色和亮色之間，所以木頭、皮革、青銅
  最後都落在同一套色階上，畫面不會東一塊西一塊
- seamless_tile：用鏡射做出接得起來的小塊材質，九宮格中間鋪磚時不會有接縫
- key_flat_background：把畫在單一底色上的圖去背，AI 有時不給透明度就靠這個
"""
import os

PIPELINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(PIPELINE_DIR)
SOURCE_DIR = os.path.join(PROJECT_ROOT, "art_source", "ui")

_cache = {}


def _pil():
    from PIL import Image, ImageChops, ImageFilter, ImageOps
    return Image, ImageChops, ImageFilter, ImageOps


def load_source(name):
    """讀 art_source/ui 的原圖，讀過的留在記憶體裡，一次產製只讀一次"""
    from PIL import Image
    if name not in _cache:
        path = os.path.join(SOURCE_DIR, name)
        _cache[name] = Image.open(path).convert("RGBA") if os.path.exists(path) else None
    return _cache[name]


def _levels(gray, low_pct=2.0, high_pct=98.0):
    """把灰階拉到 0～255，避開最亮和最暗的極端值，各種原圖的對比才會一致"""
    from PIL import Image
    histogram = gray.histogram()
    total = sum(histogram)
    low_target = total * low_pct / 100.0
    high_target = total * high_pct / 100.0
    running = 0
    low = 0
    high = 255
    for value, count in enumerate(histogram):
        running += count
        if running <= low_target:
            low = value
        if running <= high_target:
            high = value
    if high <= low:
        return gray
    scale = 255.0 / (high - low)
    return gray.point(lambda v: max(0, min(255, int((v - low) * scale))))


def grade(image, dark, light, gamma=1.0, contrast=1.0):
    """把一張圖的明暗重新對應到 dark 到 light 之間；contrast 小於 1 會把材質壓平"""
    Image, _, _, _ = _pil()
    gray = _levels(image.convert("L"))
    if contrast != 1.0:
        gray = gray.point(lambda v: int(128 + (v - 128) * contrast))
    if gamma != 1.0:
        gray = gray.point(lambda v: int(255 * ((v / 255.0) ** gamma)))
    lut = []
    for channel in range(3):
        lut += [max(0, min(255, int(dark[channel] + (light[channel] - dark[channel]) * (v / 255.0))))
                for v in range(256)]
    return Image.merge("RGB", (gray, gray, gray)).point(lut)


def seamless_tile(image, size):
    """用鏡射做出接得起來的方塊：取左上四分之一再左右上下鏡射
    細顆粒的皮革和布用鏡射看不出來，比硬接縫可靠"""
    Image, _, _, _ = _pil()
    half_w = max(1, size[0] // 2)
    half_h = max(1, size[1] // 2)
    # 從原圖中央取一塊再縮到四分之一大小，避開 AI 原圖邊緣常有的暗角
    width, height = image.size
    box = (width // 6, height // 6, width * 5 // 6, height * 5 // 6)
    quarter = image.crop(box).resize((half_w, half_h), Image.LANCZOS)
    tile = Image.new(image.mode, (half_w * 2, half_h * 2))
    tile.paste(quarter, (0, 0))
    tile.paste(quarter.transpose(Image.FLIP_LEFT_RIGHT), (half_w, 0))
    tile.paste(quarter.transpose(Image.FLIP_TOP_BOTTOM), (0, half_h))
    tile.paste(quarter.transpose(Image.ROTATE_180), (half_w, half_h))
    return tile.resize(size, Image.LANCZOS) if tile.size != tuple(size) else tile


def material(name, size, dark, light, gamma=1.0, contrast=1.0, tile=True):
    """一塊上好色的材質，tile 為真時是接得起來的"""
    Image, _, _, _ = _pil()
    source = load_source(name)
    if source is None:
        return Image.new("RGB", size, dark)
    graded = grade(source.convert("RGB"), dark, light, gamma, contrast)
    if not tile:
        width, height = graded.size
        box = (width // 6, height // 6, width * 5 // 6, height * 5 // 6)
        return graded.crop(box).resize(size, Image.LANCZOS)
    return seamless_tile(graded, size)


def key_flat_background(image, tolerance=18, feather=1):
    """把畫在單一平底色上的圖去背：以四角的平均色當底色，相近的像素變透明
    再把邊緣往內收一點，去掉底色留下的灰邊"""
    Image, ImageChops, ImageFilter, _ = _pil()
    rgba = image.convert("RGBA")
    width, height = rgba.size
    corners = [rgba.getpixel(p) for p in ((2, 2), (width - 3, 2), (2, height - 3), (width - 3, height - 3))]
    base = tuple(sum(c[i] for c in corners) // len(corners) for i in range(3))
    pixels = rgba.load()
    alpha = Image.new("L", rgba.size, 255)
    alpha_pixels = alpha.load()
    for y in range(height):
        for x in range(width):
            pixel = pixels[x, y]
            distance = max(abs(pixel[0] - base[0]), abs(pixel[1] - base[1]), abs(pixel[2] - base[2]))
            if distance <= tolerance:
                alpha_pixels[x, y] = 0
            elif distance < tolerance * 2:
                alpha_pixels[x, y] = int(255 * (distance - tolerance) / float(tolerance))
    if feather:
        alpha = alpha.filter(ImageFilter.MinFilter(3))
        alpha = alpha.filter(ImageFilter.GaussianBlur(0.5))
    rgba.putalpha(alpha)
    return rgba


def drop_small_blobs(image, threshold=40, min_ratio=0.10):
    """丟掉零碎的小塊，只留下夠大的那幾團
    切格子時鄰居溢進來的碎片會被丟掉，但同一個圖示分成好幾塊的部分會留著，
    例如藥水瓶的玻璃和裡面的液體是分開的兩塊，只留最大一塊會把玻璃丟掉"""
    from PIL import Image, ImageChops
    alpha = image.getchannel("A")
    width, height = alpha.size
    data = list(alpha.point(lambda v: 1 if v > threshold else 0).getdata())
    label = [0] * (width * height)
    sizes = [0]
    current = 0
    for start in range(width * height):
        if data[start] == 0 or label[start]:
            continue
        current += 1
        stack = [start]
        label[start] = current
        size = 0
        while stack:
            index = stack.pop()
            size += 1
            x = index % width
            y = index // width
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if 0 <= nx < width and 0 <= ny < height:
                    neighbour = ny * width + nx
                    if data[neighbour] and not label[neighbour]:
                        label[neighbour] = current
                        stack.append(neighbour)
        sizes.append(size)
    if current == 0:
        return image
    limit = max(sizes) * min_ratio
    keep_ids = {index for index, size in enumerate(sizes) if index and size >= limit}
    keep = Image.new("L", alpha.size, 0)
    keep.putdata([255 if value in keep_ids else 0 for value in label])
    out = image.copy()
    out.putalpha(ImageChops.multiply(alpha, keep))
    return out


def trim(image, pad=0):
    """裁到有內容的範圍，四邊可以再留一點空白"""
    from PIL import Image
    box = image.getchannel("A").getbbox() if "A" in image.getbands() else image.getbbox()
    if box is None:
        return image
    box = (max(0, box[0] - pad), max(0, box[1] - pad),
           min(image.size[0], box[2] + pad), min(image.size[1], box[3] + pad))
    return image.crop(box)


def fit_into(image, size, margin=0):
    """等比例縮進指定大小並置中，不放大超過原尺寸"""
    from PIL import Image
    room = (max(1, size[0] - margin * 2), max(1, size[1] - margin * 2))
    scale = min(room[0] / image.size[0], room[1] / image.size[1])
    scaled = image.resize((max(1, int(image.size[0] * scale)), max(1, int(image.size[1] * scale))), Image.LANCZOS)
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    out.paste(scaled, ((size[0] - scaled.size[0]) // 2, (size[1] - scaled.size[1]) // 2))
    return out


def drop_shadow(image, offset=(0, 1), blur=1.2, alpha=0.5, color=(10, 7, 5)):
    """用圖自己的形狀在下面偏一點畫一層暗影，圖示才像躺在格子裡"""
    Image, _, ImageFilter, _ = _pil()
    shade = Image.new("RGBA", image.size, color + (0,))
    mask = Image.new("L", image.size, 0)
    mask.paste(image.getchannel("A"), offset)
    mask = mask.filter(ImageFilter.GaussianBlur(blur)).point(lambda v: int(v * alpha))
    shade.putalpha(mask)
    return Image.alpha_composite(shade, image)


def engraved(image, size, light, dark, strength=1.0):
    """把一張有立體感的原圖轉成刻在表面上的線：取高頻細節，凸起畫亮線凹下畫暗線
    放大和裁切都在原尺寸做完才縮小，不然細線會在縮圖時被平均掉
    用在空格子的浮雕記號，只留下刻痕不留下整塊形狀"""
    Image, ImageChops, ImageFilter, _ = _pil()
    rgba = image.convert("RGBA")
    shape = rgba.getchannel("A").point(lambda v: 255 if v > 128 else 0)
    gray = rgba.convert("L")
    radius = max(2.0, image.size[0] / 120.0)
    high = ImageChops.subtract(gray, gray.filter(ImageFilter.GaussianBlur(radius)), scale=1, offset=128)
    gain = 9.0 * strength
    up = high.point(lambda v: int(min(255, max(0, v - 130) * gain)))
    down = high.point(lambda v: int(min(255, max(0, 126 - v) * gain)))
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    for mask, color in ((down, dark), (up, light)):
        masked = ImageChops.multiply(mask, shape).resize(size, Image.LANCZOS)
        layer = Image.new("RGBA", size, color + (0,))
        layer.putalpha(masked)
        out = Image.alpha_composite(out, layer)
    return out
