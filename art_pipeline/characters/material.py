"""角色的材質槽和配色

照 docs/角色系統規格.md 和 docs/美術風格指南.md：乾淨的單色底加柔和漸層，不畫描邊、不做雜訊紋路。
這裡只負責把每個槽位的底色寫進 Blender 的 Principled 材質，明暗和邊緣光由遊戲端的卡通材質算，
所以同一份模型在 Blender 裡看到的和遊戲裡看到的顏色一致。

底色取自 docs/調查/RO配色參考.md 每條色階的受光底色那一格，整體是偏暖的粉彩。
可染色的部位靠遊戲端的色階參數換色，不換貼圖，所以這裡填的是預設色。
"""

import bpy

# 材質槽的順序就是網格的材質索引，改順序等於改所有模型，不要動
# Neutral、NeutralDark、NeutralSkin 是灰白人體模型用的，排在最後面，不影響既有模型的材質索引
# Neutral 是「有穿衣服的部位」會跟著 NPC 的身分色染色
# NeutralSkin 是「露出來的皮膚」也就是頭和手，永遠保持中性灰，顏色才讀得出是穿在身上的
SLOTS = ["Skin", "Hair", "Cloth", "ClothLight", "ClothTrim", "Accent", "Leather",
         "Metal", "Face", "Wood", "Glow", "Neutral", "NeutralDark", "NeutralSkin"]
SLOT_INDEX = {name: index for index, name in enumerate(SLOTS)}

# 可染色的部位對應到遊戲端的哪一組色階，沒寫的就是不染色
# hair 用髮色、skin 用膚色、cloth 用服裝色，和 data/appearances.json 的欄位同名
DYE_GROUP = {
    "Skin": "skin",
    "Face": "skin",
    "Hair": "hair",
    "Cloth": "cloth",
    "ClothLight": "cloth",
    "Accent": "cloth",
}

# 每個槽的預設底色和表面性質：(顏色, 粗糙度, 金屬度)
# 頭髮和金屬的粗糙度壓低，遊戲端的頂光才打得出一條明顯的高光帶
BASE = {
    "Skin": ("#ffc6b2", 0.78, 0.0),
    "Hair": ("#da9773", 0.32, 0.0),
    "Cloth": ("#d38c6e", 0.88, 0.0),
    "ClothLight": ("#e8c7a5", 0.88, 0.0),
    "ClothTrim": ("#eedfd7", 0.80, 0.0),
    "Accent": ("#b8747c", 0.88, 0.0),
    "Leather": ("#9e5c66", 0.58, 0.0),
    "Metal": ("#c9974d", 0.26, 0.85),
    # 臉只是一張貼圖的載體，底色要是白的。
    # 填膚色的話等於把貼圖再乘一次膚色，臉會整片偏紅
    "Face": ("#ffffff", 0.78, 0.0),
    "Wood": ("#ab7a52", 0.68, 0.0),
    "Glow": ("#9abf94", 0.40, 0.0),
    # 人體模型：一個乾淨的灰白，短褲深一階。不染色，所以不列進 DYE_GROUP
    "Neutral": ("#d8d6d2", 0.72, 0.0),
    "NeutralDark": ("#a9a7a4", 0.74, 0.0),
    "NeutralSkin": ("#dedbd6", 0.70, 0.0),
}

# 每個職業的識別色，同職業的男女用同一組，一眼看得出是同一個職業
# (主布料, 次要布料, 配件)
JOB_COLORS = {
    "novice": ("#d38c6e", "#b8747c", "#eedfd7"),
    "swordman": ("#9e5c66", "#7e4151", "#c9974d"),
    "mage": ("#7a6f8c", "#958ba7", "#e3ba74"),
    "archer": ("#668674", "#4c6864", "#d1b094"),
    "hero": ("#b24651", "#6e252d", "#ffdeac"),
    "elementalist": ("#5c576e", "#aba3bf", "#b8d8a5"),
    "hunter": ("#4c6864", "#314a54", "#e8c7a5"),
}


def srgb(hex_color):
    """#RRGGBB 轉成 Blender 用的線性色值"""
    hex_color = hex_color.lstrip("#")
    channels = [int(hex_color[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return (linear[0], linear[1], linear[2], 1.0)


def _new(name):
    old = bpy.data.materials.get(name)
    if old:
        bpy.data.materials.remove(old)
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    material.node_tree.nodes.clear()
    return material


def _principled(name, color, roughness, metallic, texture=None):
    material = _new(name)
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Metallic"].default_value = metallic
    if texture is not None:
        image_node = nodes.new("ShaderNodeTexImage")
        image_node.image = texture
        image_node.interpolation = "Linear"
        image_node.extension = "CLIP"
        links.new(image_node.outputs["Color"], shader.inputs["Base Color"])
    else:
        shader.inputs["Base Color"].default_value = srgb(color)
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    return material


def build(job="novice", face_texture=None, suffix=""):
    """做出一整套材質槽，順序和 SLOTS 一樣

    job 決定可染色部位的預設顏色，同職業男女拿到同一組。
    face_texture 是表情圖集，貼在 Face 槽上。
    """
    main, second, trim = JOB_COLORS.get(job, JOB_COLORS["novice"])
    override = {"Cloth": main, "Accent": second, "ClothTrim": trim}
    materials = []
    for slot in SLOTS:
        color, roughness, metallic = BASE[slot]
        color = override.get(slot, color)
        texture = face_texture if slot == "Face" else None
        materials.append(_principled("v3_%s%s" % (slot, suffix), color, roughness, metallic,
                                     texture))
    return materials


def apply(obj, materials):
    for material in materials:
        obj.data.materials.append(material)
    return obj
