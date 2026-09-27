import bpy

import config


def srgb(hex_color):
    """把 #RRGGBB 轉成 Blender 用的線性色值，直接填 0~1 會變得很淡"""
    hex_color = hex_color.lstrip("#")
    channels = [int(hex_color[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return (linear[0], linear[1], linear[2], 1.0)


def toon_material(name, color, rim=0.18, flat=False):
    """
    三階明暗加輪廓亮邊的卡通材質，color 是線性色值。
    暗面帶一點紫色，看起來比純灰的暗面乾淨；flat 為真時不受光，用在眼睛高光和腮紅
    """
    existing = bpy.data.materials.get(name)
    if existing:
        return existing
    mat = bpy.data.materials.new(name)
    # 描邊要用這個顏色的深色版本，先記在材質上
    mat["base_color"] = list(color)
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    output = nodes.new('ShaderNodeOutputMaterial')
    emission = nodes.new('ShaderNodeEmission')
    links.new(emission.outputs["Emission"], output.inputs["Surface"])
    if flat:
        emission.inputs["Color"].default_value = color
        return mat

    diffuse = nodes.new('ShaderNodeBsdfDiffuse')
    to_rgb = nodes.new('ShaderNodeShaderToRGB')
    bands = nodes.new('ShaderNodeValToRGB')
    tint = nodes.new('ShaderNodeMix')
    layer_weight = nodes.new('ShaderNodeLayerWeight')
    rim_ramp = nodes.new('ShaderNodeValToRGB')
    add_rim = nodes.new('ShaderNodeMix')

    bands.color_ramp.interpolation = 'CONSTANT'
    bands.color_ramp.elements[0].position = 0.0
    bands.color_ramp.elements[0].color = (0.5, 0.45, 0.66, 1)
    bands.color_ramp.elements[1].position = 0.62
    bands.color_ramp.elements[1].color = (1, 1, 1, 1)
    middle = bands.color_ramp.elements.new(0.3)
    middle.color = (0.8, 0.76, 0.88, 1)

    tint.data_type = 'RGBA'
    tint.blend_type = 'MULTIPLY'
    tint.inputs[0].default_value = 1.0
    tint.inputs[7].default_value = color

    layer_weight.inputs["Blend"].default_value = 0.35
    rim_ramp.color_ramp.interpolation = 'CONSTANT'
    rim_ramp.color_ramp.elements[0].color = (0, 0, 0, 1)
    rim_ramp.color_ramp.elements[1].position = 0.7
    rim_ramp.color_ramp.elements[1].color = (rim, rim * 0.95, rim * 0.85, 1)

    add_rim.data_type = 'RGBA'
    add_rim.blend_type = 'ADD'
    add_rim.inputs[0].default_value = 1.0

    links.new(diffuse.outputs["BSDF"], to_rgb.inputs["Shader"])
    links.new(to_rgb.outputs["Color"], bands.inputs["Fac"])
    links.new(bands.outputs["Color"], tint.inputs[6])
    links.new(layer_weight.outputs["Facing"], rim_ramp.inputs["Fac"])
    links.new(tint.outputs[2], add_rim.inputs[6])
    links.new(rim_ramp.outputs["Color"], add_rim.inputs[7])
    links.new(add_rim.outputs[2], emission.inputs["Color"])
    return mat


def outline_material(color=None, darkness=0.3):
    """color 為 None 時是共用的黑色描邊，否則用 color 壓暗後的同色系描邊"""
    if color is None:
        name, line_color = "outline", config.OUTLINE_COLOR
    else:
        line_color = (color[0] * darkness, color[1] * darkness * 0.9, color[2] * darkness, 1.0)
        name = "outline_%.3f_%.3f_%.3f" % line_color[:3]
    existing = bpy.data.materials.get(name)
    if existing:
        return existing
    mat = bpy.data.materials.new(name)
    nodes = mat.node_tree.nodes
    nodes.clear()
    output = nodes.new('ShaderNodeOutputMaterial')
    emission = nodes.new('ShaderNodeEmission')
    emission.inputs["Color"].default_value = line_color
    mat.node_tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
    mat.use_backface_culling = True
    return mat


def add_outline(obj, thickness=config.OUTLINE_THICKNESS):
    """
    反轉外殼描邊：往外長一層翻轉法線的殼，只看得到輪廓邊緣。
    每個材質各配一個同色系的深色描邊，外殼的材質編號剛好往後平移材質數量
    """
    base_materials = list(obj.data.materials)
    if not base_materials:
        obj.data.materials.append(outline_material())
        base_materials = []
    for base in base_materials:
        color = base.get("base_color") if base is not None else None
        obj.data.materials.append(outline_material(list(color) if color is not None else None))
    modifier = obj.modifiers.new("outline", 'SOLIDIFY')
    modifier.thickness = thickness
    modifier.offset = 1.0
    modifier.use_flip_normals = True
    modifier.use_rim = False
    modifier.material_offset = max(1, len(base_materials))
    return modifier


def outline_all(objects):
    """物件名稱以 fx_ 開頭的不描邊，例如眼睛高光和腮紅"""
    for obj in objects:
        if obj.type == 'MESH' and not obj.name.startswith("fx_"):
            add_outline(obj)
