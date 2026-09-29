"""怪物的表面：色階、painted 貼圖、邊光與環境回彈，以及換色遮罩和材質編號

和角色那一版的差別是這裡不再平塗。一個表面由三件事組成：

1. 色階：法線和固定光向量的內積分成六階，查一條六格的色階。色階照 docs/調查/RO配色參考.md 的
   幾何推：暗端飽和帶紫、沿途往暖色轉、最亮一格全部收在 #ffeecb
2. 貼圖：mtex.py 產的細節貼圖，用物件座標做三軸投影所以不用拆 UV。
   貼圖只提供表面起伏和局部色偏，顏色主體仍然是色階
3. 邊光與回彈：受光側的輪廓抬到奶油色，背光側從斜下方補一點暖色，
   這樣暗部不會死掉，剪影也會從背景跳出來

算圖分三套材質跑三次：彩色、換色遮罩、材質編號。三套的槽位順序一樣，形狀完全對得起來。
"""

import os

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
TEX_DIR = os.path.join(os.path.dirname(os.path.dirname(HERE)), "art_source", "monsters",
                       "tex", "out")

# 所有色階共用的最亮一格
HIGHLIGHT = "#ffeecb"
# 描邊色，RO 沒有純黑
OUTLINE = "#242424"
# 背光側的環境回彈色，暖但不亮
BOUNCE = "#7a5a4a"

# 遮罩通道對怪物來說是染色變體：R 主體、G 次要、B 點綴
MASK_MAIN = "main"
MASK_SECOND = "second"
MASK_ACCENT = "accent"

# 六格色階，暗到亮。每一條的最亮一格都收在共用的暖奶油色
RAMPS = {
    # 植物與史萊姆
    "dewgel": ["#2d4f6b", "#3d7f96", "#57aeb8", "#8ed6cf", "#c9eedd", "#ffeecb"],
    "dewcore": ["#31607f", "#3f8ca6", "#5fb9c6", "#98dcd6", "#d2f0e2", "#ffeecb"],
    "moss": ["#2c4626", "#456a33", "#688f43", "#93b45a", "#c6d789", "#ffeecb"],
    # 苔苔站在草地上，主色要離草的黃綠遠一點，往藍綠走才分得開
    "moss_teal": ["#1e3a38", "#2d5a52", "#3f8073", "#5ba896", "#93cdb8", "#ffeecb"],
    "leaf": ["#264628", "#3b6b3c", "#5d9552", "#8dbb72", "#c2dc9e", "#ffeecb"],
    "bark": ["#3a2a26", "#57433a", "#7a6050", "#a1836a", "#cdb18d", "#ffeecb"],
    "deadwood": ["#3b3030", "#5a4a44", "#7d6a5c", "#a08b76", "#cbb595", "#ffeecb"],
    "shroomcap": ["#26404f", "#3a6072", "#537f8f", "#7ba6ae", "#b2cfcd", "#ffeecb"],
    "shroomstem": ["#5a4c46", "#7d6c60", "#9d8a79", "#bfab94", "#e0cdae", "#ffeecb"],
    # 昆蟲與岩石
    "chitin_fern": ["#2e3f22", "#4a5c2e", "#6d7f3c", "#96a455", "#c6cb8a", "#ffeecb"],
    "chitin_rock": ["#4a3a26", "#6b5433", "#8e7343", "#b19459", "#d6bd8c", "#ffeecb"],
    "stone": ["#3b343f", "#584e54", "#786a67", "#9a8b7c", "#c0b09a", "#ffeecb"],
    # 毛皮與羽毛
    "fur_ash": ["#332c3e", "#4f4658", "#736876", "#9a8d90", "#c4b6a8", "#ffeecb"],
    "fur_rat": ["#3d2f2a", "#5d483c", "#826751", "#a88a6b", "#cfb492", "#ffeecb"],
    "feather": ["#3a2c26", "#5a4534", "#806448", "#a78a62", "#cfb48d", "#ffeecb"],
    "membrane": ["#38283c", "#553f57", "#775d73", "#9b8290", "#c3aeb2", "#ffeecb"],
    "hide_pale": ["#6a4f48", "#8c6c5d", "#ac8b73", "#c9a98d", "#e2c9a8", "#ffeecb"],
    # 骨與腐肉
    "bone": ["#63504d", "#8b7469", "#b39c87", "#d3c0a5", "#eddfc2", "#ffeecb"],
    "ashbone": ["#403c4a", "#615c6c", "#867f8b", "#aaa3a6", "#cec7bc", "#ffeecb"],
    "rot": ["#3c4a33", "#586946", "#79895d", "#9ba87c", "#c3cba3", "#ffeecb"],
    "rag": ["#262518", "#3d3a28", "#575238", "#766f4e", "#9d9470", "#d6cba4"],
    # 金屬與礦
    "iron": ["#333440", "#4f5260", "#71747f", "#94969b", "#bcbcb6", "#ffeecb"],
    "rust": ["#472418", "#6b3b24", "#925634", "#b87a4c", "#dca878", "#ffeecb"],
    "brass": ["#503118", "#754c24", "#9c7033", "#c2974d", "#e2bd79", "#ffeecb"],
    "claw": ["#2f2a30", "#4a4248", "#69605f", "#8b8076", "#b3a793", "#ffeecb"],
    # 暗色與發光
    "gloom": ["#1b1526", "#2a2039", "#3d3250", "#564a6a", "#776a8a", "#a294ac"],
    "glow_cyan": ["#2f6e86", "#3f9ab4", "#63c4d6", "#9ce2e6", "#d3f4f0", "#ffffff"],
    "glow_ember": ["#7a2f1a", "#b0452a", "#e0703a", "#ff9d4a", "#ffc97a", "#ffeecb"],
    "glow_gloom": ["#3a2060", "#57308c", "#7a48b8", "#a070d8", "#c9a6ec", "#f0e0ff"],
    "glow_moss": ["#2f5a2a", "#468441", "#63b05c", "#93d986", "#c8f0b4", "#ffffe0"],
    # 眼睛
    "sclera": ["#c0b2ae", "#d5c7c0", "#e6d8cf", "#f1e6dc", "#fbf2e6", "#ffffff"],
    "pupil": ["#101014", "#141419", "#1a1820", "#201e26", "#26242c", "#2c2a32"],
    "iris": ["#2a3f2c", "#3d5c3c", "#557a4f", "#74996a", "#9cba8c", "#c8d8b0"],
}

# 材質槽位，順序固定，每隻怪照這個順序給十二個表面
SLOT_NAMES = ["Main", "Second", "Accent", "Bone", "Dark", "Metal", "EyeWhite", "Pupil",
              "Glow", "Wood", "Claw", "Belly"]
SLOT_INDEX = {name: index for index, name in enumerate(SLOT_NAMES)}

# 色階上六個顏色各自落在內積的哪個位置。
# 2026-09-16 照 docs/美術風格指南.md 改成柔和漸層：色階用內插不是階梯，
# 所以這裡是漸層的控制點不是分界。位置不是平均分佈的：相機固定，
# 正對鏡頭那一片的內積大約是 0.92，所以主色要壓在 0.845，那一格才是「看起來的顏色」；
# 最亮的奶油色只留給離光向量十度以內的一小塊高光，不然整隻會白掉
BAND_STOPS = [0.0, 0.40, 0.66, 0.845, 0.945, 0.982]

# 光從畫面的左上前方來，相機固定所以世界空間方向等於畫面空間方向，
# 每個朝向算出來的明暗在螢幕上都一致，和 RO 逐方向手繪的結果一樣
LIGHT_DIR = (-0.38, -0.80, 0.46)
# 邊光的方向：比主光再偏左偏上一點，打在剪影的左上緣
RIM_DIR = (-0.62, -0.30, 0.72)
# 回彈光從右下前方來，補背光側的暗部
BOUNCE_DIR = (0.40, -0.55, -0.73)

FULL = (0, 1, 2, 3, 4, 5)
LIFT = (1, 2, 3, 4, 5, 5)
SINK = (0, 0, 1, 2, 3, 4)


def surface(ramp, picks=FULL, mask=None, tex=None, scale=6.0, strength=1.0, chroma=1.0,
            rim=0.55, bounce=0.35, breakup=0.16):
    """一個表面的定義

    ramp 是色階名稱，picks 是六段各取色階的哪一格，mask 是換色通道，
    tex 是細節貼圖名稱，scale 是每公尺重複幾次，strength 是紋理起伏強度，
    chroma 是局部色偏強度，rim 是邊光強度，bounce 是背光側回彈強度。

    breakup 是讓紋理去擾動明暗分階的界線。沒有它的話分階界線是一條乾淨的弧線，
    整個表面就會讀成平塗的色塊；有了它界線會沿著毛流、甲片、樹皮的紋理走，
    表面才會讀成材質而不是塗了顏色的幾何體。這是這一版最關鍵的一個參數。
    """
    return dict(ramp=ramp, picks=picks, mask=mask, tex=tex, scale=scale, strength=strength,
                chroma=chroma, rim=rim, bounce=bounce, breakup=breakup)


def default_slots():
    """沒有特別指定時每個槽位的表面，怪物自己只要蓋掉用得到的那幾個"""
    return {
        "Main": surface("moss", mask=MASK_MAIN, tex="moss"),
        "Second": surface("stone", mask=MASK_SECOND, tex="rock"),
        "Accent": surface("leaf", mask=MASK_ACCENT, tex="leaf"),
        "Bone": surface("bone", tex="bone", scale=7.0),
        "Dark": surface("gloom", tex="rag", scale=8.0, strength=0.7, rim=0.25, bounce=0.15),
        "Metal": surface("iron", tex="plate", scale=5.0, rim=0.85),
        "EyeWhite": surface("sclera", picks=(2, 3, 3, 4, 5, 5), rim=0.2, bounce=0.0,
                            strength=0.0, chroma=0.0),
        "Pupil": surface("pupil", rim=0.0, bounce=0.0, strength=0.0, chroma=0.0),
        "Glow": surface("glow_cyan", picks=(2, 3, 4, 4, 5, 5), rim=0.0, bounce=0.0,
                        strength=0.35, chroma=0.5),
        "Wood": surface("deadwood", tex="bark", scale=5.0),
        "Claw": surface("claw", tex="bone", scale=10.0, rim=0.9),
        "Belly": surface("hide_pale", tex="fur_short", scale=8.0),
    }


def slots(**overrides):
    """照 default_slots 開一份再蓋掉指定的槽位"""
    table = default_slots()
    for name, value in overrides.items():
        if name not in table:
            raise KeyError("沒有這個材質槽 " + name)
        table[name] = value
    return table


def srgb(hex_color):
    """把 #RRGGBB 轉成 Blender 用的線性色值"""
    hex_color = hex_color.lstrip("#")
    channels = [int(hex_color[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return (linear[0], linear[1], linear[2], 1.0)


def bytes_rgb(hex_color):
    """十六進位色轉成 0 到 1 的 sRGB 數值，影像後製那一端用這個"""
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


_TEXTURE_CACHE = {}


def texture(name):
    if name is None:
        return None
    # 換場景時舊的 Image 會被整批刪掉，快取裡的參考就失效了，碰到就重新載
    cached = _TEXTURE_CACHE.get(name)
    try:
        if cached is not None and cached.name in bpy.data.images:
            return cached
    except ReferenceError:
        pass
    path = os.path.join(TEX_DIR, name + ".png")
    if not os.path.exists(path):
        return None
    image = bpy.data.images.load(path)
    image.colorspace_settings.name = "Non-Color"
    _TEXTURE_CACHE[name] = image
    return image


def _new(name):
    old = bpy.data.materials.get(name)
    if old:
        bpy.data.materials.remove(old)
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    material.node_tree.nodes.clear()
    return material


def _normalize(vector):
    length = sum(v * v for v in vector) ** 0.5
    return tuple(v / length for v in vector)


def _dot_node(nodes, links, normal_socket, direction):
    node = nodes.new("ShaderNodeVectorMath")
    node.operation = "DOT_PRODUCT"
    node.inputs[1].default_value = _normalize(direction)
    links.new(normal_socket, node.inputs[0])
    return node.outputs["Value"]


def _link_math(nodes, links, operation, a, b, clamp=False):
    node = nodes.new("ShaderNodeMath")
    node.operation = operation
    node.use_clamp = clamp
    for index, value in enumerate((a, b)):
        if isinstance(value, float):
            node.inputs[index].default_value = value
        else:
            links.new(value, node.inputs[index])
    return node.outputs["Value"]


def _mix_rgb(nodes, links, blend, factor, color_a, color_b):
    node = nodes.new("ShaderNodeMix")
    node.data_type = "RGBA"
    node.blend_type = blend
    if isinstance(factor, float):
        node.inputs[0].default_value = factor
    else:
        links.new(factor, node.inputs[0])
    for index, value in ((6, color_a), (7, color_b)):
        if isinstance(value, tuple):
            node.inputs[index].default_value = value
        else:
            links.new(value, node.inputs[index])
    return node.outputs[2]


def _band_ramp(nodes, colors):
    """色階查表，但用內插不用階梯

    2026-09-16 前這裡是 CONSTANT，出來是一塊一塊的平塗，也就是使用者說的那種平面感。
    改成 B_SPLINE 之後同一個面上是從亮到暗的平滑過渡，顏色仍然是 RO 色階上的那幾個，
    只是中間補上連續的過渡，符合 docs/美術風格指南.md 的「柔和漸層上色，不是平塗色階」。
    """
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "B_SPLINE"
    while len(ramp.color_ramp.elements) > 1:
        ramp.color_ramp.elements.remove(ramp.color_ramp.elements[-1])
    ramp.color_ramp.elements[0].position = BAND_STOPS[0]
    ramp.color_ramp.elements[0].color = colors[0]
    for stop, color in zip(BAND_STOPS[1:], colors[1:]):
        element = ramp.color_ramp.elements.new(stop)
        element.color = color
    return ramp


def _triplanar(nodes, links, image, scale):
    """用物件座標做三軸投影，不用拆 UV，任何形狀都貼得上"""
    coords = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (scale, scale, scale)
    links.new(coords.outputs["Object"], mapping.inputs["Vector"])
    node = nodes.new("ShaderNodeTexImage")
    node.image = image
    node.projection = "BOX"
    node.projection_blend = 0.35
    node.extension = "REPEAT"
    node.interpolation = "Cubic"
    links.new(mapping.outputs["Vector"], node.inputs["Vector"])
    return node.outputs["Color"]


def color_material(name, spec):
    """色階乘上細節貼圖，再加邊光和背光回彈"""
    material = _new(name)
    material["mask_channel"] = spec["mask"] or ""
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    output = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    geometry = nodes.new("ShaderNodeNewGeometry")
    normal = geometry.outputs["Normal"]

    key = _dot_node(nodes, links, normal, LIGHT_DIR)
    ramp = RAMPS[spec["ramp"]]
    colors = [srgb(ramp[i]) for i in spec["picks"]]

    image = texture(spec["tex"])
    tex = luma = None
    if image is not None and (spec["strength"] > 0.0 or spec["chroma"] > 0.0
                              or spec["breakup"] > 0.0):
        tex = _triplanar(nodes, links, image, spec["scale"])
        grey = nodes.new("ShaderNodeRGBToBW")
        links.new(tex, grey.inputs["Color"])
        luma = _link_math(nodes, links, "MAXIMUM", grey.outputs["Val"], 0.02)
    if luma is not None and spec["breakup"] > 0.0:
        # 紋理先擾動明暗的分階界線，界線才會沿著毛流和甲片走
        offset = _link_math(nodes, links, "SUBTRACT", luma, 0.5)
        offset = _link_math(nodes, links, "MULTIPLY", offset, spec["breakup"] * 2.0)
        key = _link_math(nodes, links, "ADD", key, offset)

    clamped = _link_math(nodes, links, "MAXIMUM", key, 0.0)
    base = _band_ramp(nodes, colors)
    links.new(clamped, base.inputs["Fac"])
    shaded = base.outputs["Color"]

    if tex is not None:
        if spec["strength"] > 0.0:
            # 貼圖平均亮度是 0.5，乘二之後平均剛好一，所以不會整體變暗或變亮
            detail = _link_math(nodes, links, "MULTIPLY", luma, 2.0)
            level = _link_math(nodes, links, "SUBTRACT", detail, 1.0)
            # 分階界線已經被 breakup 擾過了，這裡的相乘只負責補一層細碎的顆粒，
            # 所以只取一半的強度，不然暗部會整片糊掉
            level = _link_math(nodes, links, "MULTIPLY", level, spec["strength"] * 0.5)
            level = _link_math(nodes, links, "ADD", level, 1.0)
            level = _link_math(nodes, links, "MAXIMUM", level, 0.15)
            grey_color = nodes.new("ShaderNodeCombineColor")
            for index in range(3):
                links.new(level, grey_color.inputs[index])
            shaded = _mix_rgb(nodes, links, "MULTIPLY", 1.0, shaded, grey_color.outputs["Color"])
            # 紋理最亮的地方往共用奶油色收，符合 RO 亮部去飽和的規則
            over = _link_math(nodes, links, "SUBTRACT", level, 1.0)
            over = _link_math(nodes, links, "MULTIPLY", over, 0.55, clamp=True)
            shaded = _mix_rgb(nodes, links, "MIX", over, shaded, srgb(HIGHLIGHT))
        if spec["chroma"] > 0.0:
            grey_color = nodes.new("ShaderNodeCombineColor")
            for index in range(3):
                links.new(luma, grey_color.inputs[index])
            tint = _mix_rgb(nodes, links, "DIVIDE", 1.0, tex, grey_color.outputs["Color"])
            tint = _mix_rgb(nodes, links, "MIX", spec["chroma"], (1.0, 1.0, 1.0, 1.0), tint)
            shaded = _mix_rgb(nodes, links, "MULTIPLY", 1.0, shaded, tint)

    if spec["bounce"] > 0.0:
        # 背光側才補回彈，受光側加了會髒
        lift = _dot_node(nodes, links, normal, BOUNCE_DIR)
        lift = _link_math(nodes, links, "MAXIMUM", lift, 0.0)
        shade_side = _link_math(nodes, links, "SUBTRACT", 1.0, clamped, clamp=True)
        amount = _link_math(nodes, links, "MULTIPLY", lift, shade_side)
        amount = _link_math(nodes, links, "MULTIPLY", amount, spec["bounce"], clamp=True)
        shaded = _mix_rgb(nodes, links, "SCREEN", amount, shaded, srgb(BOUNCE))

    if spec["rim"] > 0.0:
        # 邊光：越接近剪影邊緣越亮，而且只打在朝向邊光方向的那一側。
        # Layer Weight 的 Facing 是「正對鏡頭為 1」，所以要反過來才是邊緣
        facing = nodes.new("ShaderNodeLayerWeight")
        facing.inputs["Blend"].default_value = 0.5
        links.new(normal, facing.inputs["Normal"])
        edge = _link_math(nodes, links, "SUBTRACT", 1.0, facing.outputs["Facing"])
        edge = _link_math(nodes, links, "POWER", edge, 2.6)
        side = _dot_node(nodes, links, normal, RIM_DIR)
        side = _link_math(nodes, links, "MAXIMUM", side, 0.0)
        side = _link_math(nodes, links, "POWER", side, 1.4)
        amount = _link_math(nodes, links, "MULTIPLY", edge, side)
        amount = _link_math(nodes, links, "MULTIPLY", amount, spec["rim"], clamp=True)
        shaded = _mix_rgb(nodes, links, "MIX", amount, shaded, srgb(HIGHLIGHT))

    links.new(shaded, emission.inputs["Color"])
    links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return material


def mask_material(name, mask):
    """換色遮罩用的純色自發光材質"""
    material = _new(name)
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    output = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = {
        MASK_MAIN: (1.0, 0.0, 0.0, 1.0), MASK_SECOND: (0.0, 1.0, 0.0, 1.0),
        MASK_ACCENT: (0.0, 0.0, 1.0, 1.0)}.get(mask, (0.0, 0.0, 0.0, 1.0))
    links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return material


def id_color(index):
    """材質槽編號轉成三通道各只有 0、0.5、1 的顏色，縮圖後還分得出來"""
    index += 1
    return ((index % 3) * 0.5, ((index // 3) % 3) * 0.5, ((index // 9) % 3) * 0.5, 1.0)


def id_material(name, index):
    material = _new(name)
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    output = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = id_color(index)
    links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return material


def build_materials(table, prefix):
    """照槽位表建三套材質：彩色、遮罩、材質編號，順序都是 SLOT_NAMES"""
    colors, masks, ids = [], [], []
    for index, slot in enumerate(SLOT_NAMES):
        spec = table[slot]
        colors.append(color_material("%s_%s" % (prefix, slot), spec))
        masks.append(mask_material("%sm_%s" % (prefix, slot), spec["mask"]))
        ids.append(id_material("%si_%s" % (prefix, slot), index))
    return colors, masks, ids


def apply_slot_set(objects, materials):
    """把一批物件的材質槽整個換成指定的那一套，用來在三套之間切換"""
    for obj in objects:
        if obj.type != "MESH":
            continue
        for index, material in enumerate(materials):
            if index < len(obj.data.materials):
                obj.data.materials[index] = material
