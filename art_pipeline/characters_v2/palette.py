"""角色的顏色與材質

2026-09-16 改版，照 docs/美術風格指南.md：不再用九階色階查表做平塗，改成乾淨的單色底加真實打光
算出來的柔和漸層。同一個面上從亮到暗是平滑過渡，暗部帶冷色補光，頭髮和金屬有一條明顯的高光帶。
之前的色階查表做出來永遠是一塊一塊的平塗，那是像素風的做法，和參考的公仔質感差太遠。

底色仍然取自 docs/調查/RO配色參考.md 的色階，取每條色階的「受光底色」那一格，
所以整體配色還是偏暖的粉彩，遊戲端換色用的色階表也還是同一份，換色結果對得起來。

分兩套材質：一套是算彩色圖用的 Principled 材質，一套是算換色遮罩用的純色自發光材質。
兩套用同一批物件同一批槽位，算完彩色圖整批換掉再算一次，形狀完全對得起來。
"""

import bpy

# 遮罩通道：R 是頭髮、G 是皮膚、B 是主要布料，其他部位不換色
MASK_HAIR = "hair"
MASK_SKIN = "skin"
MASK_CLOTH = "cloth"

# 所有色階共用的最亮一格，這是 RO 感最強的特徵
HIGHLIGHT = "#ffeecb"
# 描邊色，RO 沒有純黑
OUTLINE = "#242424"

RAMPS = {
    # 皮膚 5 階，整條只差 26 個明度，臉的深色感來自描邊不是皮膚陰影
    "skin": ["#bd736b", "#dc9084", "#f6ae9f", "#ffc6b2", "#ffe1b6"],
    # 預設沙金髮 8 階
    "hair_sand": ["#673429", "#91514e", "#ab6957", "#c57a60", "#da9773", "#eeb385",
                  "#fde3b2", "#ffffcb"],
    # 可染色主布料 10 階：衣服、褲子、手套、披布、靴頭
    "cloth_main": ["#55251a", "#733d2f", "#9e5e49", "#b37259", "#d38c6e", "#e6aa86",
                   "#e8c7a5", "#f3c89e", "#fff4bc", "#ffe5b5"],
    # 可染色副色 7 階：靴子、女生的粉外套與短褲、男生的玫瑰棕背心
    "cloth_second": ["#5c253b", "#7e4151", "#9e5c66", "#b8747c", "#d8a6a2", "#eccac6", "#ffe1cf"],
    # 不染色的白色胸甲與領子 6 階
    "white_armor": ["#967b7b", "#b8a39b", "#cab7af", "#dccbc3", "#eedfd7", "#ffffcb"],
    # 不染色的手套綁帶 5 階
    "glove_wrap": ["#a38171", "#ba9983", "#d1b094", "#e8c7a5", "#ffe1b6"],
    # 木頭和黃銅，照同樣的色階幾何推的
    "wood": ["#4a2f1d", "#6b452b", "#8a5c3a", "#ab7a52", "#d3ab7c", "#ffeecb"],
    "brass": ["#5a3a1c", "#7d5527", "#a37436", "#c9974d", "#e3ba74", "#ffeecb"],
}

# 每個材質槽：(色階名稱, 取哪三格當暗中亮, 遮罩通道)
# 同樣掛 B 通道的 Cloth、ClothLight、Accent 落在色階的不同段，遊戲端依亮度查色階就會一起正確換色，
# RO 本來就是這樣做的：整件可染色區域共用一條色階，不同部位只是落在不同格。
# RO 其實有主色和副色兩組可染色布料，但精靈圖規格只有三個遮罩通道，
# 所以兩組都掛在 B 通道；白胸甲、領子、靴子、綁帶照 RO 本來就不可染色，維持不掛通道
SLOTS = ["Skin", "Hair", "Cloth", "ClothLight", "ClothTrim", "Accent", "Leather",
         "Metal", "Face", "Wood", "Wrap"]
# 每個材質槽從色階上取九格，數字是色階的格數，可以是小數，小數會在兩格之間內插。
# 九格由暗到亮，第 6 格是「受光底色」，正面大部分面積都落在那一格，所以那一格決定這個部位看起來什麼顏色：
# 胸甲取 #eedfd7 才會讀成奶油白、褲子取 #d38c6e 才是棕褐、背心 #b8747c 才是玫瑰色。
# 第 7、8 格是高光，只有邊緣光和材質的反光打得到，正常受光打不到，
# 所以人物有亮部但不會整片泛白。九格取代原本的五格，圓面上的色階才夠多，不再是平塗
SLOT_SPEC = {
    "Skin": ("skin", (0, 0.4, 0.9, 1.4, 1.9, 2.4, 3.0, 3.6, 4.0), MASK_SKIN),
    "Hair": ("hair_sand", (0, 0.6, 1.2, 1.9, 2.6, 3.3, 4.0, 5.6, 7.0), MASK_HAIR),
    "Cloth": ("cloth_main", (0, 0.6, 1.2, 1.9, 2.5, 3.2, 4.0, 5.2, 8.0), MASK_CLOTH),
    "ClothLight": ("cloth_main", (2.0, 2.8, 3.4, 4.0, 4.6, 5.3, 6.0, 7.5, 8.6), MASK_CLOTH),
    "ClothTrim": ("white_armor", (0.3, 0.8, 1.3, 1.9, 2.5, 3.2, 4.0, 4.6, 5.0), None),
    "Accent": ("cloth_second", (0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.2, 5.6), MASK_CLOTH),
    "Leather": ("cloth_second", (0, 0.3, 0.6, 1.0, 1.4, 1.7, 2.0, 3.0, 4.4), None),
    "Metal": ("brass", (0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.3, 5.0), None),
    "Face": ("skin", (0, 0.4, 0.9, 1.4, 1.9, 2.4, 3.0, 3.6, 4.0), MASK_SKIN),
    "Wood": ("wood", (0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.2, 5.0), None),
    "Wrap": ("glove_wrap", (0, 0.4, 0.9, 1.4, 1.9, 2.4, 3.0, 3.6, 4.0), None),
}
SLOT_INDEX = {name: index for index, name in enumerate(SLOTS)}

# 底色取色階的第 6 格也就是「受光底色」，那一格決定這個部位看起來是什麼顏色。
# 明暗改由真實打光算，所以材質只要一個乾淨的底色加上表面性質
LIT_INDEX = 6

# 每個材質槽的表面性質：(粗糙度, 金屬度)
# 頭髮和金屬的粗糙度壓低，頂光才打得出一條明顯的弧形高光帶，這是風格指南要的重點
SURFACE = {
    "Skin": (0.78, 0.0),
    "Hair": (0.32, 0.0),
    "Cloth": (0.88, 0.0),
    "ClothLight": (0.88, 0.0),
    "ClothTrim": (0.80, 0.0),
    "Accent": (0.88, 0.0),
    "Leather": (0.58, 0.0),
    "Metal": (0.26, 0.85),
    "Face": (0.78, 0.0),
    "Wood": (0.68, 0.0),
    "Wrap": (0.74, 0.0),
}

# 臉部五官用色
FACE_OUTLINE = "#242424"
PUPIL = "#000000"
SCLERA = "#eedfd7"
IRIS = "#80a387"


def srgb(hex_color):
    """把 #RRGGBB 轉成 Blender 用的線性色值"""
    hex_color = hex_color.lstrip("#")
    channels = [int(hex_color[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return (linear[0], linear[1], linear[2], 1.0)


def _sample_ramp(ramp, position):
    """色階上的小數位置，兩格之間在 sRGB 空間內插再轉線性，內插出來的顏色仍在原色階的走向上"""
    low = max(0, min(len(ramp) - 1, int(position)))
    high = min(len(ramp) - 1, low + 1)
    t = position - low
    a = [int(ramp[low].lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    b = [int(ramp[high].lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    mixed = [round(a[i] + (b[i] - a[i]) * t) for i in range(3)]
    return srgb("#%02x%02x%02x" % tuple(mixed))


def ramp_colors(slot):
    """某個槽位在色階上取的九個顏色，由深到亮"""
    ramp_name, picks, _ = SLOT_SPEC[slot]
    ramp = RAMPS[ramp_name]
    return [_sample_ramp(ramp, p) for p in picks]


def _new(name):
    old = bpy.data.materials.get(name)
    if old:
        bpy.data.materials.remove(old)
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    material.node_tree.nodes.clear()
    return material


def base_color(slot):
    """這個槽位的底色，也就是色階上的受光底色那一格"""
    return ramp_colors(slot)[LIT_INDEX]


def toon_material(name, slot, texture=None):
    """乾淨的單色底加表面性質，明暗完全交給場景的三盞燈算出柔和漸層

    照 docs/美術風格指南.md：不做色階查表、不做雜訊紋路，質感來自形體、打光和高光。
    texture 不為 None 時底色改成貼圖，臉部的五官就是這樣畫上去的。
    """
    material = _new(name)
    material["mask_channel"] = SLOT_SPEC[slot][2] or ""
    nodes = material.node_tree.nodes
    links = material.node_tree.links

    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    roughness, metallic = SURFACE[slot]
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Metallic"].default_value = metallic
    if texture is not None:
        image_node = nodes.new("ShaderNodeTexImage")
        image_node.image = texture
        image_node.interpolation = "Cubic"
        image_node.extension = "EXTEND"
        links.new(image_node.outputs["Color"], shader.inputs["Base Color"])
    else:
        shader.inputs["Base Color"].default_value = base_color(slot)
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    return material


def mask_material(name, mask, texture=None):
    """換色遮罩用的純色自發光材質

    texture 不為 None 時遮罩色直接來自貼圖，臉部用得到：眉毛算頭髮、皮膚算皮膚、
    眼睛和嘴巴是黑的代表不換色。
    """
    material = _new(name)
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    output = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    channel = {MASK_HAIR: (1.0, 0.0, 0.0, 1.0), MASK_SKIN: (0.0, 1.0, 0.0, 1.0),
               MASK_CLOTH: (0.0, 0.0, 1.0, 1.0)}.get(mask, (0.0, 0.0, 0.0, 1.0))
    if texture is not None:
        image_node = nodes.new("ShaderNodeTexImage")
        image_node.image = texture
        image_node.interpolation = "Linear"
        links.new(image_node.outputs["Color"], emission.inputs["Color"])
    else:
        emission.inputs["Color"].default_value = channel
    links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return material


# 材質交界要畫內部線條，但有幾組交界不該畫：
# 臉部曲面片只是貼在頭骨上的一層皮，兩邊都是皮膚色，畫線會在臉外圍框出一個明顯的方框
SAME_ID_AS = {"Face": "Skin"}


def id_color(index):
    """材質槽編號轉成三個通道各只有 0、0.5、1 的顏色，縮圖後還分得出來是哪一槽"""
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


def build_id_materials(suffix=""):
    """材質編號材質，SAME_ID_AS 裡的槽共用同一個編號，兩者的交界就不會被畫上內部線條"""
    return [id_material("v2i_" + slot + suffix,
                        SLOT_INDEX[SAME_ID_AS.get(slot, slot)])
            for slot in SLOTS]


def build_materials(face_texture=None, face_mask=None, suffix=""):
    """一次做好所有槽位的彩色材質和對應的遮罩材質，回傳兩份和 SLOTS 同順序的清單"""
    color_materials = []
    mask_materials = []
    for slot in SLOTS:
        mask = SLOT_SPEC[slot][2]
        if slot == "Face":
            color_materials.append(toon_material("v2_Face" + suffix, slot, texture=face_texture))
            mask_materials.append(mask_material("v2m_Face" + suffix, mask, texture=face_mask))
            continue
        color_materials.append(toon_material("v2_" + slot + suffix, slot))
        mask_materials.append(mask_material("v2m_" + slot + suffix, mask))
    return color_materials, mask_materials


def apply_slot_set(objects, materials):
    """把一批物件的材質槽整個換成指定的那一套，用來在彩色圖和遮罩之間切換"""
    for obj in objects:
        if obj.type != "MESH":
            continue
        for index, material in enumerate(materials):
            if index < len(obj.data.materials):
                obj.data.materials[index] = material


def export_ramps():
    """輸出給遊戲端換色用的色階表，換髮色是整條色階換掉不是色相位移"""
    return {"highlight": HIGHLIGHT, "outline": OUTLINE, "ramps": RAMPS,
            "slots": {name: {"ramp": SLOT_SPEC[name][0], "picks": list(SLOT_SPEC[name][1]),
                             "mask": SLOT_SPEC[name][2] or ""} for name in SLOTS}}
