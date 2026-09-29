"""玩家角色的 3D 算圖圖集：一個綁好骨架的角色，算出八個方向、全部動作的像素圖集

為什麼走這條路：2D 生成八方向試了九種做法（Pulsar、gpt-image、Qwen 多角度、Wan 影片、
Qwen 逐格改姿勢、OpenPose 骨架、Aether 畫格、Flux Klein 兩格接龍九宮格、VACE 關鍵格），
病根都一樣，每一格都是模型重新猜一次，方向之間和格與格之間的一致性靠提示詞求不來，
而且俯角完全補不了。3D 算圖的八方向和每一格都是同一個模型從同一顆相機算出來的，
一致是構造出來的，不是求來的。怪物那條 mstatic 已經證明這件事。

輸入有兩種，擇一：
  --source  <路徑.glb>   本機圖轉 3D 產的模型（art_pipeline/comfy/views_to_mesh.py 的輸出）。
                         會先扭到標準比例、綁到 characters 的標準人形骨架，動作直接沿用。
  --rigged  <路徑.glb>   已經綁好標準骨架、帶動作的模型，例如 assets/generated/models/characters_real/ 那批。

輸出到 assets/generated/sprites/characters/body/<名稱>/：sheet.png、mask.png、meta.json 和 .import，
格式照 docs/精靈圖規格.md「像素角色圖集」：176×232 的畫格、錨點 (88, 208)、96 像素一公尺、
角色 180 像素高、限 48 色、邊緣全有全無、最近點取樣。方向預設八個真方向都算，
--directions 5 只算五個讓引擎鏡射另外三個。相機仰角照遊戲鏡頭的 45 度。

用法：
  blender -b --factory-startup --python-exit-code 1 -P art_pipeline/characters/cbuild.py -- \
      <名稱> --source art_source/characters/<名稱>/mesh.glb [--job novice] [--directions 8] [--preview]
  --preview 只算八個方向的站姿排成一張檢查圖，不算整套動作，先看再決定要不要跑全部
  --candidate 整套算好但放到 placeholder 那個不出貨的資料夾，--body=<名稱> 在遊戲裡看得到；使用者點頭再不加這個參數正式輸出
  --layer 名稱=路徑.glb@掛點[*倍率] 裝備或裝飾的圖層，可以重複給。網格掛到骨架的掛點（hand_r、hand_l、head、back、body），
      用同一顆相機在每一格單獨算成 characters/layers/<名稱>/ 那一份圖集，畫格錨點動作全部和身體一樣，
      引擎把同一格直接疊上去。meta 的 order 記每一格圖層在身體前面還是後面
  --keep-rig 把綁好骨架的模型另存到 assets/generated/models/characters/<名稱>.glb，可以在 Blender 裡檢查
  --elevation 30 產圖俯角，預設 45；矮頭身的臉在 45 度會跑到球底下，30 度看得到臉
  --head-lift 25 綁骨前把頭往後仰幾度讓臉朝鏡頭，預設 25，0 就不動

ComfyUI 在產圖的時候不要跑這支，兩邊共用顯示記憶體。
"""

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PIPELINE_DIR = os.path.dirname(HERE)
PROJECT_ROOT = os.path.dirname(PIPELINE_DIR)
for path in (HERE, os.path.join(PIPELINE_DIR, "common"), os.path.join(PIPELINE_DIR, "monsters"), PIPELINE_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import blenv  # noqa: E402  characters 那一份
import mimg  # noqa: E402  monsters 的完稿處理
from common import atlas  # noqa: E402
from common import sheet_output  # noqa: E402

OUT_ROOT = os.path.join(PROJECT_ROOT, "assets", "generated", "sprites", "characters", "body")
# 還沒給使用者看過的候選圖集放這裡：引擎的搜尋路徑找得到（--body=名稱 看得到），
# 但這個資料夾不進版本庫也不出貨，記憶體測試也不會把它算進出貨的圖集裡
CANDIDATE_ROOT = os.path.join(PROJECT_ROOT, "assets", "generated", "sprites", "placeholder", "characters", "body")
RIG_OUT = os.path.join(PROJECT_ROOT, "assets", "generated", "models", "characters")
WORK = os.environ.get("CHARACTER_WORK") or os.path.join(PIPELINE_DIR, "_build", "characters")
APPEARANCES = os.path.join(PROJECT_ROOT, "data", "appearances.json")

# 畫格契約，出處 docs/精靈圖規格.md
FRAME_SIZE = (176, 232)
ANCHOR = (88, 208)
PIXELS_PER_METER = 96.0
CHARACTER_HEIGHT_PX = 180
CHARACTER_HEIGHT_M = CHARACTER_HEIGHT_PX / PIXELS_PER_METER
MAX_COLORS = 48
# 產圖的俯角。遊戲鏡頭是 45 度（docs/美術技術框架.md 第 2 節），但 2.8 頭身的角色眼睛長在頭高的八成處，
# 接近球的底部，真的用 45 度算整張臉會跑到球的底下看不到（2026-09-23 實測，45 度那張只看得到頭頂）。
# RO 自己的角色圖也是比地面淺的角度畫的。所以角色圖用 30 度，配上 HEAD_LIFT_DEG 的抬頭，
# 臉看得到、頭頂和肩膀的頂面也還在。用 --elevation 蓋掉可以比別的角度
CAMERA_ELEVATION_DEG = 30.0

# 抬頭的角度。定裝圖的眼睛長在頭高的八成處，接近球的底部；真的做成 3D 之後那塊面朝下，
# 從上面看下去整張臉被壓成一條。RO 的畫法是把臉當成正對玩家的平面來畫，等於頭往上抬。
# 這裡在綁骨之前把脖子以上的網格繞脖子往後仰這麼多度，之後每一個動作的頭都是抬起來的。
# 用 --head-lift 蓋掉，0 就是不動
HEAD_LIFT_DEG = 25.0

# 定裝圖的比例，2026-09-23 用 designsheet.py measure 量男初心者正面卡片得到的。
# 所有角色共用這一組，骨架才是同一副，之後裝備圖層一件只要出一份。
# 沒列的參數沿用 rigspec.STANDARD。手臂長那一項卡片上量不準（手貼著身體），沿用標準
CARD_SPEC = {
    "head_ratio": 2.83,
    "head_width_per_head": 0.99,
    "shoulder_per_head_width": 1.085,
    "shoulder_per_height": 0.556,
    "crotch_per_height": 0.317,
    "stance_per_head_width": 0.595,
    "leg_width_per_head_width": 0.323,
}
SUPERSAMPLE = 2
# 遮罩縮到圖集的八分之一，引擎允許的最小尺寸；全黑代表整隻不換色
MASK_DIVISOR = 8

# 方向照 src/world/facing.gd 的順序：0 下、1 左下、2 左、3 左上、4 上、5 右上、6 右、7 右下
DIRECTIONS_8 = ["s", "sw", "w", "nw", "n", "ne", "e", "se"]
DIRECTIONS_5 = DIRECTIONS_8[:5]

# 動作表照 docs/精靈圖規格.md 的像素角色那一節；source 是骨架上的動作名稱，
# 攻擊和施法每個職業不一樣，從 data/appearances.json 讀，這裡的是退路
# 一個方向 30 格：五方向 150 格的 176×232 圖集是 1408×4408，配置器保留停在 32 MB 那一階，
# test_vram_budget 的城鎮和石谷記的是 32；idle 4 格、pickup 4 格、die 5 格是 170 格會跳到 64 MB
ACTIONS = [
    dict(name="idle", source="Idle", frames=3, fps=5, loop=True),
    dict(name="walk", source="Walking_A", frames=8, fps=12, loop=True),
    # 攻擊不是等距取格：times 是每一格取 KayKit 那段動作的哪個時間點。量過 1H_Melee_Attack_Stab 的手：
    # 0.17 拉到最後面、0.33 到 0.50 刺到最前面、之後收回。第 0 格取半拉回，引擎等出手時間時停在這一格就是蓄力，
    # 接著全拉回、揮到一半、命中滿伸，再兩格收勢。這就是預備、爆發、收勢
    dict(name="attack", source="1H_Melee_Attack_Stab", frames=6, fps=14, loop=False, hit_frame=3,
         times=[0.10, 0.17, 0.27, 0.36, 0.55, 0.85]),
    dict(name="cast", source="Spellcasting", frames=4, fps=8, loop=True),
    # 受擊、死亡、撿東西也照量過的時間點取：Hit_A 0.25 退到最後面；Death_A 0.15 站不穩、0.55 倒到一半、0.8 躺平，
    # 等距取的話後兩格都是躺平的；PickUp 0.42 手到最低
    dict(name="hit", source="Hit_A", frames=2, fps=10, loop=False, times=[0.25, 0.6]),
    # Death_A 在 0.35 到 0.5 之間整個人被打飛到最高，頭會超出畫格頂，跳過那一段
    dict(name="die", source="Death_A", frames=4, fps=7, loop=False, times=[0.12, 0.25, 0.62, 0.85]),
    dict(name="sit", source="Sit_Floor_Idle", frames=1, fps=1, loop=True),
    # PickUp 彎到 0.42 頭會超出畫格的邊，取 0.26 就好
    dict(name="pickup", source="PickUp", frames=2, fps=8, loop=False, times=[0.12, 0.26]),
]

# 三段明暗的色階：陰影、中間調、亮部各乘多少。docs/美術風格指南.md 1.3 說要三段，
# 暗部偏紫是 1.4 的規矩，所以陰影那一段略帶藍紫
SHADE_BANDS = [(0.00, (0.58, 0.55, 0.66)), (0.40, (0.84, 0.83, 0.86)), (0.72, (1.0, 1.0, 1.0))]
# 平塗：不算明暗，顏色就是貼圖本身。定裝圖投影上去的貼圖已經帶著畫裡的線和淡淡的陰影，再套三段明暗會把網格的凹凸算成斑
FLAT_BANDS = [(0.00, (1.0, 1.0, 1.0))]
FLAT_SHADING = False
# 主光從左上前方來，和 docs/美術風格指南.md 1.6 一致；補光靠世界的環境光
KEY_LIGHT_DIRECTION = (-0.45, -0.60, 0.66)
AMBIENT = 0.25
# 描邊：最外圈壓成該處顏色的深色，和 mimg.outline 同一套，強度略高於怪物因為畫格小
OUTLINE_STRENGTH = 0.42
# 描邊：Freestyle 只畫外輪廓、邊界和材質交界，粗細是成品像素，算圖時乘上超取樣倍率。
# 摺線不畫，生成的網格表面有細皺紋，摺線會把每條皺紋都畫成線；反向外殼也試過，殼從肩關節戳出來變黑斑，2026-09-23
INK_PX = 1.0
INK_COLOR = (0.09, 0.07, 0.09)
# 藏頭時從脖子根部再往上留幾公分，肩膀不被切到，脖子那一小截由頭圖層蓋
HEAD_CUT_ABOVE_NECK_M = 0.02


def _log(text):
    print("[cbuild] " + text, flush=True)


# ---------- 匯入與綁骨 ----------

def _import_rigged(path):
    """匯入已經綁好標準骨架的 glb，回傳 (骨架, 網格清單)"""
    before = set(bpy.context.scene.objects)
    with blenv.ui():
        bpy.ops.import_scene.gltf(filepath=path)
    fresh = [o for o in bpy.context.scene.objects if o not in before]
    armatures = [o for o in fresh if o.type == "ARMATURE"]
    # 小碎塊丟掉：Meshy 那批身體檔裡夾著一顆 42 個頂點、半徑一公尺的 Icosphere，
    # 算進身高會把角色量成 2.5 公尺，整隻縮成一半（2026-09-23 踩到）。真正的零件都是上千頂點
    meshes = [o for o in fresh if o.type == "MESH" and len(o.data.vertices) >= 200 and not o.hide_render]
    for obj in fresh:
        if obj.type == "MESH" and obj not in meshes:
            _log("丟掉雜物 %s（%d 頂點）" % (obj.name, len(obj.data.vertices)))
            bpy.data.objects.remove(obj, do_unlink=True)
    if not armatures:
        raise RuntimeError("%s 裡沒有骨架，要用 --source 走綁骨那條路" % path)
    if not meshes:
        raise RuntimeError("%s 裡沒有夠大的網格" % path)
    armature = armatures[0]
    # glTF 匯入器會把每個動作放進 NLA 軌，播其中一個時其他軌會混進來，全部清掉，動作照名字自己選
    if armature.animation_data:
        for track in list(armature.animation_data.nla_tracks):
            armature.animation_data.nla_tracks.remove(track)
        armature.animation_data.action = None
    armature.rotation_mode = "XYZ"
    return armature, meshes


def _bind_source(path, gender):
    """本機圖轉 3D 的網格扭到定裝圖的比例、綁到那副比例的標準骨架，回傳 (骨架, 網格, 報告)

    骨架和網格用同一組比例參數（CARD_SPEC），所以骨頭一定落在網格裡面；
    比例是定裝圖那種 2.8 頭身，不是 characters 那副 4.07 頭身的標準，
    不然 3 頭身的網格會被拉成長腿，長相就不是使用者畫的那個了
    """
    import dodge_anim
    import proportions
    import rehome_meshy
    import rig_humanoid
    import rigspec
    spec = rigspec.RigSpec(**CARD_SPEC)
    body_shape = proportions.Body(gender, spec)
    armature = rig_humanoid.build(gender, body_shape)
    dodge_anim.build_all(armature)
    rig_humanoid.rest_pose(armature)
    body = rehome_meshy._import_body(path)
    rehome_meshy._fit_and_apply(body, proportions.HEIGHT)
    triangles = rehome_meshy._decimate(body)
    before = rehome_meshy.normalize_to_spec(body, spec)
    _lift_head(body, spec.chin_z, HEAD_LIFT_DEG)
    rehome_meshy._bind(body, armature, body_shape)
    report = rehome_meshy.weight_report(body)
    report["triangles"] = triangles
    report["head_ratio_before"] = before.get("head_ratio")
    if report["bound"] == 0:
        raise RuntimeError("綁定失敗：沒有任何頂點的權重大於 %.1f" % rehome_meshy.WEIGHT_FLOOR)
    stray = rehome_meshy.arm_stray_ratio(body)
    report["arm_stray"] = stray
    _log("綁到 %d / %d 個頂點，面 %d，手臂綁歪 %.1f 個百分比，頭身比 %s"
         % (report["bound"], report["vertices"], triangles, stray * 100, report["head_ratio_before"]))
    if stray > rehome_meshy.ARM_STRAY_CEILING:
        _log("警告：手臂區有 %.0f 個百分比的頂點綁在脖子和頭上，動起來可能扁成薄板" % (stray * 100))
    return armature, [body], report


def _lift_head(obj, neck_z, degrees):
    """脖子以上的網格繞著脖子那一點往後仰，臉才會朝向鏡頭而不是朝地面。

    脖子附近用 smoothstep 混過去，不然脖子那一圈會被扯出一個台階（和 normalize_to_spec 同一個做法）。
    臉在 -Y 那一側，繞 X 軸轉負角度臉才往上抬（正角度是低頭，第一次就轉錯邊）；
    樞軸在脖子高度、身體前後中心
    """
    if abs(degrees) < 1e-3:
        return
    blend_m = 0.06
    ys = [v.co.y for v in obj.data.vertices if v.co.z > neck_z]
    pivot_y = (max(ys) + min(ys)) / 2.0 if ys else 0.0
    turn = Matrix.Rotation(math.radians(-degrees), 4, "X")
    for vertex in obj.data.vertices:
        point = vertex.co
        blend = min(1.0, max(0.0, (point.z - (neck_z - blend_m)) / (2.0 * blend_m)))
        blend = blend * blend * (3.0 - 2.0 * blend)
        if blend <= 0.0:
            continue
        local = Vector((point.x, point.y - pivot_y, point.z - neck_z))
        turned = turn @ local
        vertex.co = point.lerp(Vector((turned.x, turned.y + pivot_y, turned.z + neck_z)), blend)
    obj.data.update()


def _parse_layer(text):
    """名稱=路徑.glb@掛點[*倍率] → (名稱, 路徑, 掛點, 倍率)"""
    if "=" not in text or "@" not in text:
        raise SystemExit("--layer 要寫成 名稱=路徑.glb@掛點，收到 " + text)
    name, rest = text.split("=", 1)
    path, socket = rest.rsplit("@", 1)
    factor = 1.0
    if "*" in socket:
        socket, factor = socket.split("*", 1)
        factor = float(factor)
    return name.strip(), os.path.abspath(path.strip()), socket.strip(), factor


def _attach_layer(armature, spec):
    """匯入一件裝備或裝飾的網格，掛到骨架的掛點上，回傳那個物件

    掛在骨頭上的物件原點會落在骨頭的尾端，掛點骨頭是從關節往前伸 0.06 公尺的一小截，
    所以要把物件沿骨頭退回頭端，原點才是關節本身。方向另外照 LAYER_ROTATION_DEG 補
    """
    name, path, socket, factor = spec
    if socket not in armature.data.bones:
        raise SystemExit("骨架上沒有 %s 這個掛點，有的是 hand_r、hand_l、head、back、body" % socket)
    before = set(bpy.context.scene.objects)
    with blenv.ui():
        bpy.ops.import_scene.gltf(filepath=path)
    fresh = [o for o in bpy.context.scene.objects if o not in before]
    meshes = [o for o in fresh if o.type == "MESH"]
    if not meshes:
        raise SystemExit("%s 裡沒有網格" % path)
    for obj in fresh:
        if obj.type != "MESH":
            bpy.data.objects.remove(obj, do_unlink=True)
    if len(meshes) > 1:
        with blenv.ui():
            blenv.select_only(meshes)
            bpy.context.view_layer.objects.active = meshes[0]
            bpy.ops.object.join()
    obj = meshes[0]
    obj.name = "layer_" + name
    for modifier in list(obj.modifiers):
        obj.modifiers.remove(modifier)
    bone = armature.data.bones[socket]
    obj.parent = armature
    obj.parent_type = "BONE"
    obj.parent_bone = socket
    obj.matrix_parent_inverse = Matrix.Identity(4)
    obj.rotation_mode = "XYZ"
    obj.location = (0.0, -bone.length, 0.0)
    obj.rotation_euler = tuple(math.radians(v) for v in LAYER_ROTATION_DEG.get(socket, (0.0, 0.0, 0.0)))
    obj.scale = (factor, factor, factor)
    return obj


def _depth_from_camera(camera, point):
    """世界座標的點離鏡頭多近，越大越靠近鏡頭"""
    return (camera.matrix_world.inverted() @ Vector(point)).z


def _export_rig(name, armature, meshes):
    import rig_humanoid
    rig_humanoid.set_action(armature, "Idle")
    bpy.context.view_layer.update()
    os.makedirs(RIG_OUT, exist_ok=True)
    path = os.path.join(RIG_OUT, name + ".glb")
    with blenv.ui():
        blenv.select_only([armature] + list(meshes))
        bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True,
                                  export_animations=True, export_apply=False,
                                  export_yup=True, export_skins=True)
    _log("綁好的模型存到 " + path)
    return path


# ---------- 材質：貼圖乘三段明暗，變成自發光 ----------

def _toonify(meshes):
    """每個材質改成「底色貼圖 × 三段明暗」的自發光。

    算圖不吃色彩管理的曲線，也不做柔和漸層：三段是風格指南 1.3 的要求。
    明暗由一盞主光加環境光算出來，再用色階切成三段，所以任何方向的面都只會落在三種亮度上。
    """
    for obj in meshes:
        for slot in obj.material_slots:
            material = slot.material
            if material is None:
                continue
            if not material.use_nodes:
                material.use_nodes = True
            nodes = material.node_tree.nodes
            links = material.node_tree.links
            principled = next((n for n in nodes if n.type == "BSDF_PRINCIPLED"), None)
            base_socket = None
            base_value = (0.6, 0.6, 0.6, 1.0)
            if principled is not None:
                base = principled.inputs["Base Color"]
                if base.is_linked:
                    base_socket = base.links[0].from_socket
                else:
                    base_value = tuple(base.default_value)
            output = next((n for n in nodes if n.type == "OUTPUT_MATERIAL"), None) or nodes.new("ShaderNodeOutputMaterial")
            diffuse = nodes.new("ShaderNodeBsdfDiffuse")
            diffuse.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
            to_rgb = nodes.new("ShaderNodeShaderToRGB")
            to_bw = nodes.new("ShaderNodeRGBToBW")
            ramp = nodes.new("ShaderNodeValToRGB")
            ramp.color_ramp.interpolation = "CONSTANT"
            elements = ramp.color_ramp.elements
            while len(elements) > 1:
                elements.remove(elements[-1])
            bands = FLAT_BANDS if FLAT_SHADING else SHADE_BANDS
            elements[0].position = bands[0][0]
            elements[0].color = bands[0][1] + (1.0,)
            for position, color in bands[1:]:
                element = elements.new(position)
                element.color = color + (1.0,)
            multiply = nodes.new("ShaderNodeMix")
            multiply.data_type = "RGBA"
            multiply.blend_type = "MULTIPLY"
            multiply.inputs["Factor"].default_value = 1.0
            emission = nodes.new("ShaderNodeEmission")
            links.new(diffuse.outputs["BSDF"], to_rgb.inputs["Shader"])
            links.new(to_rgb.outputs["Color"], to_bw.inputs["Color"])
            links.new(to_bw.outputs["Val"], ramp.inputs["Fac"])
            if base_socket is not None:
                links.new(base_socket, multiply.inputs[6])
            else:
                multiply.inputs[6].default_value = base_value
            links.new(ramp.outputs["Color"], multiply.inputs[7])
            links.new(multiply.outputs[2], emission.inputs["Color"])
            for link in list(output.inputs["Surface"].links):
                links.remove(link)
            links.new(emission.outputs["Emission"], output.inputs["Surface"])
            if hasattr(material, "blend_method"):
                material.blend_method = "OPAQUE"


def _lights():
    for obj in list(bpy.context.scene.objects):
        if obj.type == "LIGHT":
            bpy.data.objects.remove(obj, do_unlink=True)
    light = bpy.data.lights.new("key", "SUN")
    light.energy = 1.0
    light.angle = 0.2
    light.use_shadow = True
    sun = bpy.data.objects.new("key", light)
    bpy.context.view_layer.active_layer_collection.collection.objects.link(sun)
    sun.rotation_mode = "QUATERNION"
    sun.rotation_quaternion = Vector(KEY_LIGHT_DIRECTION).normalized().to_track_quat("Z", "Y")
    world = bpy.data.worlds.get("v5world") or bpy.data.worlds.new("v5world")
    bpy.context.scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    if background:
        background.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
        background.inputs["Strength"].default_value = AMBIENT


# ---------- 場景、相機 ----------

def _engine_name():
    items = bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items.keys()
    for candidate in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        if candidate in items:
            return candidate
    return items[0]


def _setup_scene(samples=24):
    scene = bpy.context.scene
    scene.render.engine = _engine_name()
    scene.render.film_transparent = True
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.render.filter_size = 1.0
    scene.render.resolution_x = FRAME_SIZE[0] * SUPERSAMPLE
    scene.render.resolution_y = FRAME_SIZE[1] * SUPERSAMPLE
    scene.render.resolution_percentage = 100
    eevee = scene.eevee
    for attr, value in (("taa_render_samples", samples), ("use_raytracing", False),
                        ("use_shadows", True), ("use_bloom", False),
                        ("use_gtao", False), ("use_ssr", False)):
        if hasattr(eevee, attr):
            try:
                setattr(eevee, attr, value)
            except Exception:
                pass
    return scene


def _setup_ink(scene):
    """Freestyle 墨線：外輪廓、邊界、材質交界，一條線集，深色細線"""
    scene.render.use_freestyle = True
    scene.render.line_thickness_mode = "ABSOLUTE"
    scene.render.line_thickness = INK_PX * SUPERSAMPLE
    view_layer = bpy.context.view_layer
    view_layer.use_freestyle = True
    settings = view_layer.freestyle_settings
    settings.as_render_pass = False
    settings.use_culling = True
    for lineset in list(settings.linesets):
        settings.linesets.remove(lineset)
    lineset = settings.linesets.new("ink")
    lineset.select_silhouette = True
    lineset.select_border = True
    lineset.select_crease = False
    lineset.select_edge_mark = False
    lineset.select_material_boundary = True
    lineset.select_by_visibility = True
    lineset.visibility = "VISIBLE"
    style = lineset.linestyle
    style.color = INK_COLOR
    style.thickness = INK_PX * SUPERSAMPLE
    style.alpha = 1.0
    _log("描邊：Freestyle 外輪廓加材質交界，%.1f 像素" % INK_PX)


def _hide_head(meshes, armature):
    """頭用另一層 2D 圖貼，身體算圖時把頭藏掉：Head 骨頭起點再往下一點以上的頂點全部不畫。
    用高度切而不是用權重切，權重在脖子附近是漸層，切出來是缺角的碗"""
    # 切在脖子根部：Neck 骨頭的起點就是肩膀上方；三頭身的頭是一顆大球，下巴貼在肩膀上，
    # 切在 Head 骨頭起點會留下一圈下巴
    bone = armature.data.bones.get("Neck") or armature.data.bones.get("Head")
    if bone is None:
        _log("藏頭：骨架沒有 Head 也沒有 Neck，跳過")
        return
    cut = bone.head_local.z + HEAD_CUT_ABOVE_NECK_M
    to_armature = armature.matrix_world.inverted()
    hidden = 0
    for obj in meshes:
        group = obj.vertex_groups.get("hide_head") or obj.vertex_groups.new(name="hide_head")
        above = [v.index for v in obj.data.vertices if (to_armature @ (obj.matrix_world @ v.co)).z > cut]
        if not above:
            continue
        group.add(above, 1.0, "REPLACE")
        modifier = obj.modifiers.new("hide_head", "MASK")
        modifier.vertex_group = "hide_head"
        modifier.invert_vertex_group = True
        modifier.threshold = 0.5
        # 切開的脖子口會看到身體內側，背面不畫就是一個透明的洞，頭圖層蓋在上面
        for slot in obj.material_slots:
            if slot.material is not None:
                slot.material.use_backface_culling = True
        # 遮罩排到最前面，在骨架變形之前就把頭拿掉
        obj.modifiers.move(len(obj.modifiers) - 1, 0)
        hidden += len(above)
    _log("藏頭：切在骨架高度 %.3f 公尺以上，藏了 %d 個頂點" % (cut, hidden))


def _camera():
    old = bpy.data.objects.get("char_cam")
    if old:
        bpy.data.objects.remove(old, do_unlink=True)
    data = bpy.data.cameras.new("char_cam")
    data.type = "ORTHO"
    camera = bpy.data.objects.new("char_cam", data)
    bpy.context.view_layer.active_layer_collection.collection.objects.link(camera)
    bpy.context.scene.camera = camera
    # 正交相機：畫面高度等於畫格高度除以密度；腳底那個世界原點要落在錨點那一列，
    # 反推相機要看向地面上方多少公尺。俯角越深，同樣的像素距離對應的高度越大
    elevation = math.radians(CAMERA_ELEVATION_DEG)
    view_height = FRAME_SIZE[1] / PIXELS_PER_METER
    below_center = ANCHOR[1] - FRAME_SIZE[1] / 2.0
    target_z = below_center / (math.cos(elevation) * PIXELS_PER_METER)
    camera.data.ortho_scale = view_height * max(1.0, FRAME_SIZE[0] / float(FRAME_SIZE[1]))
    distance = 12.0
    camera.location = Vector((0.0, -math.cos(elevation) * distance, target_z + math.sin(elevation) * distance))
    camera.rotation_euler = (math.pi / 2 - elevation, 0.0, 0.0)
    return camera


def _world_to_pixel(camera, point):
    from bpy_extras.object_utils import world_to_camera_view
    coords = world_to_camera_view(bpy.context.scene, camera, Vector(point))
    return (coords.x * FRAME_SIZE[0], (1.0 - coords.y) * FRAME_SIZE[1])


# ---------- 姿勢 ----------

def _fcurve_range(action):
    lo, hi = None, None
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for curve in bag.fcurves:
                    for key in curve.keyframe_points:
                        frame = key.co[0]
                        lo = frame if lo is None else min(lo, frame)
                        hi = frame if hi is None else max(hi, frame)
    return (lo or 0.0, hi or 1.0)


def _set_time(action, t):
    start, end = _fcurve_range(action)
    exact = start + (end - start) * t
    whole = math.floor(exact)
    bpy.context.scene.frame_set(int(whole), subframe=float(exact - whole))


# data/appearances.json 寫的動作名稱在人偶的動作庫裡沒有時改用這個：人偶只帶 22 套 KayKit 動作
CLIP_ALIASES = {"1H_Melee_Attack_Chop": "2H_Melee_Attack_Chop"}
# 每種攻擊動作六格各取哪個時間點，都是量過手的位置定的：第 0、1 格蓄力、第 3 格命中、後兩格收勢。
# 2026-09-24 量的，方向 w、前臂末端的 x：斜劈是左手揮，0.33 拉到最後面、0.50 揮到最前面；
# 施法射出右手 0.17 舉起、0.33 伸到最前；射箭左手 0.25 推出去、右手 0.33 拉滿、0.42 放；雙手劈 0.33 舉到最高、0.50 劈下
ATTACK_TIMES = {
    "1H_Melee_Attack_Stab": [0.10, 0.17, 0.27, 0.36, 0.55, 0.85],
    "1H_Melee_Attack_Slice_Diagonal": [0.10, 0.25, 0.42, 0.50, 0.62, 0.83],
    "Spellcast_Shoot": [0.08, 0.17, 0.25, 0.33, 0.58, 0.85],
    "2H_Ranged_Shoot": [0.10, 0.20, 0.33, 0.42, 0.60, 0.85],
    "2H_Melee_Attack_Chop": [0.10, 0.25, 0.40, 0.50, 0.62, 0.85],
}


def _find_action(name):
    action = bpy.data.actions.get(name)
    if action is not None:
        return action
    # glTF 匯進來的動作名稱可能帶 .001 這種尾巴
    for candidate in bpy.data.actions:
        if candidate.name.split(".")[0] == name:
            return candidate
    alias = CLIP_ALIASES.get(name)
    if alias and alias != name:
        return _find_action(alias)
    return None


def _set_action(armature, action):
    if armature.animation_data is None:
        armature.animation_data_create()
    armature.animation_data.action = action
    slots = getattr(action, "slots", None)
    if slots:
        armature.animation_data.action_slot = slots[0]


def _frame_time(spec, index):
    if "times" in spec:
        return float(spec["times"][index])
    if spec["loop"]:
        return index / spec["frames"]
    return index / max(1, spec["frames"] - 1)


def _job_actions(job):
    """攻擊和施法照 data/appearances.json 那個職業的設定，沒寫就用預設"""
    specs = [dict(spec) for spec in ACTIONS]
    try:
        with open(APPEARANCES, encoding="utf-8") as handle:
            look = json.load(handle).get(job, {})
    except (OSError, ValueError):
        look = {}
    for spec in specs:
        if spec["name"] in ("attack", "cast", "idle") and look.get(spec["name"]):
            spec["source"] = look[spec["name"]]
        if spec["name"] == "attack":
            source = CLIP_ALIASES.get(spec["source"], spec["source"])
            spec["times"] = ATTACK_TIMES.get(source, ATTACK_TIMES["1H_Melee_Attack_Stab"])
    return specs


# 倒地時把朝向轉回鏡頭。KayKit 的 Death_A 是往後倒，面向鏡頭倒下去屍體就往畫面深處躺，
# 投影只剩身寬加俯角壓扁的身長，裝得進畫格（量過：面向鏡頭時最寬 145 像素，側著倒是 175 像素直接切邊）。
# 轉向要比倒下快：倒到一半身體已經橫了，那時朝向還沒轉完就會橫躺出去，第一版就是這樣 14 格被切到
DIE_YAW_DEG = 0.0
DIE_TURN_END = 0.35
# 碰到畫格底邊時每次往畫面深處挪多少公尺，見 render 裡的說明
BOTTOM_NUDGE_M = 0.12

# 圖層輸出的位置，正式版和候選版各一個，和身體圖集並排
LAYER_ROOT = os.path.join(PROJECT_ROOT, "assets", "generated", "sprites", "characters", "layers")
CANDIDATE_LAYER_ROOT = os.path.join(PROJECT_ROOT, "assets", "generated", "sprites", "placeholder",
                                    "characters", "layers")
# 圖層網格掛到掛點之後要多轉的角度，每個掛點一組歐拉角（度）。
# characters 的武器是「原點在掛點、刀尖朝 +Y」做的；掛點骨頭從關節往角色前方伸，
# 掛上去之後刀尖的朝向由這裡補。值是拿 weapon_sword 對著站姿試出來的，換一批網格要重看
LAYER_ROTATION_DEG = {"hand_r": (0.0, 0.0, 0.0), "hand_l": (0.0, 0.0, 0.0), "head": (0.0, 0.0, 0.0),
                      "back": (0.0, 0.0, 0.0), "body": (0.0, 0.0, 0.0)}
# 圖層在身體前面還是後面，比的是掛點和這根骨頭離鏡頭的遠近
LAYER_DEPTH_REFERENCE_BONE = "Hips"


def _die_yaw(spec, t, facing_deg):
    """倒地時把朝向平滑轉到 DIE_YAW_DEG，走最短的那一邊，在 DIE_TURN_END 之前轉完；其他動作照原本的朝向"""
    if spec["name"] != "die":
        return facing_deg
    fall = min(1.0, max(0.0, t / DIE_TURN_END))
    smooth = fall * fall * (3.0 - 2.0 * fall)
    delta = ((DIE_YAW_DEG - facing_deg + 180.0) % 360.0) - 180.0
    return facing_deg + delta * smooth


def _lowest_z(meshes):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    lowest = 0.0
    for obj in meshes:
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        matrix = evaluated.matrix_world
        for vertex in mesh.vertices:
            lowest = min(lowest, (matrix @ vertex.co).z)
        evaluated.to_mesh_clear()
    return lowest


# ---------- 完稿：縮小、描邊、限色、硬邊 ----------

def _finish(raw):
    """算好的兩倍圖縮成畫格：面積平均縮小、外圈壓深、邊緣切成全有全無"""
    image = mimg.downsample(raw, SUPERSAMPLE)
    line = np.array([0.16, 0.10, 0.12], dtype=np.float32)
    image = mimg.outline(image, line, base_strength=OUTLINE_STRENGTH, scale=1.0)
    solid = image[..., 3] >= 0.5
    image[..., 3] = solid.astype(np.float32)
    image[~solid, :3] = 0.0
    return image


def _median_cut(colors, count, sample=200000):
    """中位切割分色，純 numpy。colors 是 (N, 3) 的 0 到 1 浮點數，回傳 (count, 3) 的色盤。

    Blender 內建的 Python 沒有 Pillow，所以自己寫。做法和 Pillow 的 MEDIANCUT 一樣：
    每次挑範圍最大的那一箱沿最寬的軸從中位數切開，切到夠多箱為止，每箱取平均當代表色。
    """
    rng = np.random.default_rng(7)
    if len(colors) > sample:
        colors = colors[rng.choice(len(colors), sample, replace=False)]
    boxes = [colors]
    while len(boxes) < count:
        spans = [(box.max(axis=0) - box.min(axis=0)).max() if len(box) > 1 else -1.0 for box in boxes]
        index = int(np.argmax(spans))
        if spans[index] <= 0.0:
            break
        box = boxes[index]
        axis = int((box.max(axis=0) - box.min(axis=0)).argmax())
        order = np.argsort(box[:, axis], kind="stable")
        half = len(order) // 2
        boxes[index:index + 1] = [box[order[:half]], box[order[half:]]]
    return np.array([box.mean(axis=0) for box in boxes], dtype=np.float32)


def _limit_colors(sheet):
    """整張圖集共用一組 48 色的色盤，方向和動作之間才不會色差。只拿不透明的像素分色"""
    alpha = sheet[..., 3] >= 0.5
    opaque = sheet[..., :3][alpha].astype(np.float32)
    if len(opaque) == 0:
        return sheet
    palette = _median_cut(opaque, MAX_COLORS)
    quantized = np.zeros_like(opaque)
    step = 65536
    for start in range(0, len(opaque), step):
        chunk = opaque[start:start + step]
        distances = ((chunk[:, None, :] - palette[None, :, :]) ** 2).sum(axis=2)
        quantized[start:start + step] = palette[distances.argmin(axis=1)]
    out = np.zeros_like(sheet)
    out[..., :3][alpha] = quantized
    out[..., 3] = alpha.astype(np.float32)
    return out


def _measure_head_width(frame):
    """正面站姿的頭寬：從頭頂往下四分之一身高內最寬的那一列，給之後疊髮型縮放用"""
    solid = frame[..., 3] >= 0.5
    rows = np.where(solid.any(axis=1))[0]
    if len(rows) == 0:
        return 0
    top = rows[0]
    band = solid[top:top + max(1, int(CHARACTER_HEIGHT_PX * 0.25))]
    widths = [int(np.where(row)[0].max() - np.where(row)[0].min() + 1) for row in band if row.any()]
    return max(widths) if widths else 0


def _write_pixel_mask(out_dir, sheet_shape):
    """全黑的小遮罩：整隻不換色。沒有這張圖的話引擎會把整隻當成布料，選到別的服裝色就整個人被染掉"""
    height, width = max(1, sheet_shape[0] // MASK_DIVISOR), max(1, sheet_shape[1] // MASK_DIVISOR)
    mask = np.zeros((height, width, 4), dtype=np.float32)
    mask[..., 3] = 1.0
    path = os.path.join(out_dir, "mask.png")
    mimg.save_png(mask, path, non_color=True)
    sheet_output.write_import(path, PROJECT_ROOT, pixel=True)


# ---------- 主流程 ----------

def render(name, armature, meshes, directions, job="novice", preview=False, candidate=False, layers=(),
           head_layer=False, ink=False):
    scene = _setup_scene()
    _lights()
    _toonify(meshes)
    camera = _camera()
    os.makedirs(WORK, exist_ok=True)
    layer_objects = [(spec[0], spec[2], _attach_layer(armature, spec)) for spec in layers]
    _toonify([obj for _, _, obj in layer_objects])

    # 骨架本來 1.57 公尺，遊戲裡角色是 180 像素也就是 1.875 公尺，整副等比放大；
    # 縮放留在骨架物件上，姿勢都是骨頭的旋轉，不受影響
    height = _rig_height(armature, meshes)
    scale = CHARACTER_HEIGHT_M / height if height > 1e-6 else 1.0
    armature.scale = (scale, scale, scale)
    armature.location = (0.0, 0.0, 0.0)
    _log("模型高 %.3f 公尺，放大 %.3f 倍到 %.3f 公尺" % (height, scale, CHARACTER_HEIGHT_M))
    if head_layer:
        _hide_head(meshes, armature)
    if ink:
        _setup_ink(scene)

    # 頭的接點：脖子根部往上一小段，和藏頭的切線同一個位置，頭圖層的錨點（脖子最窄那列）就貼在這裡
    neck = armature.pose.bones.get("Neck") or armature.pose.bones.get("Head")
    specs = _job_actions(job)
    if preview:
        specs = [dict(specs[0], frames=1)]
    missing = [spec["source"] for spec in specs if _find_action(spec["source"]) is None]
    if missing:
        raise RuntimeError("骨架上找不到這些動作：%s；有的動作：%s"
                           % (", ".join(missing), ", ".join(sorted(a.name for a in bpy.data.actions))))

    color_actions, meta_actions, head_attach = [], {}, {}
    # 每個圖層自己一份 [(動作, 每方向的格清單)] 和每一格在身體前面(1)還是後面(-1)
    layer_actions = {layer_name: [] for layer_name, _, _ in layer_objects}
    layer_orders = {layer_name: {} for layer_name, _, _ in layer_objects}
    reference_bone = armature.pose.bones.get(LAYER_DEPTH_REFERENCE_BONE)
    clipped = []
    columns = 8
    for spec in specs:
        entry = {"frames": spec["frames"], "fps": spec["fps"], "loop": spec["loop"]}
        if "hit_frame" in spec:
            entry["hit_frame"] = spec["hit_frame"]
        meta_actions[spec["name"]] = entry
        head_attach[spec["name"]] = {}
        per_direction = []
        layer_per_direction = {layer_name: [] for layer_name, _, _ in layer_objects}
        for layer_name in layer_orders:
            layer_orders[layer_name][spec["name"]] = {}
        for direction_index, direction in enumerate(directions):
            row, attach_row = [], []
            layer_rows = {layer_name: [] for layer_name, _, _ in layer_objects}
            layer_order_row = {layer_name: [] for layer_name, _, _ in layer_objects}
            for frame in range(spec["frames"]):
                t = _frame_time(spec, frame)
                action = _find_action(spec["source"])
                _set_action(armature, action)
                _set_time(action, t)
                yaw = _die_yaw(spec, t, -45.0 * direction_index)
                armature.rotation_euler = (0.0, 0.0, math.radians(yaw))
                armature.location = (0.0, 0.0, 0.0)
                bpy.context.view_layer.update()
                if spec["name"] == "die":
                    # 倒下去的身體會轉到地面以下，抬回來才不會被畫格底邊切平
                    lift = -_lowest_z(meshes)
                    if lift > 1e-4:
                        armature.location = (0.0, 0.0, lift)
                        bpy.context.view_layer.update()
                path = os.path.join(WORK, "%s_%s_%s_%d.png" % (name, spec["name"], direction, frame))
                scene.render.filepath = path
                for _, _, obj in layer_objects:
                    obj.hide_render = True
                bpy.ops.render.render(write_still=True)
                finished = _finish(mimg.load_png(path))
                edges = _touches_edge(finished)
                # 坐下這種往前伸腿的姿勢會投影到錨點下面那 24 像素以外，碰到底邊就把整隻往畫面深處挪一點再算，
                # 挪的是世界座標的 +Y，腳底錨點不變；最多試三次，還是碰到就記警告
                retries = 0
                while "下" in edges and retries < 3:
                    retries += 1
                    armature.location = (armature.location.x, armature.location.y + BOTTOM_NUDGE_M, armature.location.z)
                    bpy.context.view_layer.update()
                    bpy.ops.render.render(write_still=True)
                    finished = _finish(mimg.load_png(path))
                    edges = _touches_edge(finished)
                if edges:
                    clipped.append("%s %s 第 %d 格碰到%s邊" % (spec["name"], direction, frame, edges))
                row.append(finished)
                if neck is not None:
                    along = (neck.tail - neck.head).normalized() if (neck.tail - neck.head).length > 1e-6 else Vector((0.0, 0.0, 1.0))
                    point = armature.matrix_world @ (neck.head + along * HEAD_CUT_ABOVE_NECK_M)
                    px = _world_to_pixel(camera, point)
                    attach_row.append([round(px[0], 1), round(px[1], 1)])
                # 圖層：同一格、同一顆相機，只露出那一件，身體藏起來
                if layer_objects:
                    for mesh in meshes:
                        mesh.hide_render = True
                    body_depth = 0.0
                    if reference_bone is not None:
                        body_depth = _depth_from_camera(camera, armature.matrix_world @ reference_bone.head)
                    for layer_name, socket, obj in layer_objects:
                        obj.hide_render = False
                        layer_path = os.path.join(WORK, "%s_%s_%s_%s_%d.png"
                                                  % (name, layer_name, spec["name"], direction, frame))
                        scene.render.filepath = layer_path
                        bpy.ops.render.render(write_still=True)
                        layer_rows[layer_name].append(_finish(mimg.load_png(layer_path)))
                        socket_depth = _depth_from_camera(
                            camera, armature.matrix_world @ armature.pose.bones[socket].head)
                        layer_order_row[layer_name].append(1 if socket_depth >= body_depth else -1)
                        obj.hide_render = True
                    for mesh in meshes:
                        mesh.hide_render = False
            per_direction.append(row)
            head_attach[spec["name"]][direction] = attach_row
            for layer_name in layer_rows:
                layer_per_direction[layer_name].append(layer_rows[layer_name])
                layer_orders[layer_name][spec["name"]][direction] = layer_order_row[layer_name]
        color_actions.append((spec["name"], per_direction))
        for layer_name in layer_actions:
            layer_actions[layer_name].append((spec["name"], layer_per_direction[layer_name]))
        _log("%s 算完，%d 個方向 × %d 格%s" % (spec["name"], len(directions), spec["frames"],
                                          "，圖層 %d 份" % len(layer_objects) if layer_objects else ""))

    sheet, starts, _rows = atlas.pack_actions(color_actions, len(directions), columns)
    sheet = _limit_colors(sheet)
    if clipped:
        _log("警告：%d 格碰到畫格邊緣：%s" % (len(clipped), "、".join(clipped[:8])))

    # 預覽不進 assets，放在 _build 底下看完就丟；正式的才寫進出貨資料夾
    if preview:
        out_dir = os.path.join(WORK, "preview_%s_e%d" % (name, round(CAMERA_ELEVATION_DEG)))
    elif candidate:
        out_dir = os.path.join(CANDIDATE_ROOT, name)
    else:
        out_dir = os.path.join(OUT_ROOT, name)
    os.makedirs(out_dir, exist_ok=True)
    sheet_path = os.path.join(out_dir, "sheet.png")
    mimg.save_png(sheet, sheet_path)
    sheet_output.write_import(sheet_path, PROJECT_ROOT, pixel=True)
    _write_pixel_mask(out_dir, sheet.shape)
    front_idle = color_actions[0][1][0][0]
    meta = {
        "frame_size": list(FRAME_SIZE),
        "columns": columns,
        "pixels_per_meter": PIXELS_PER_METER,
        "anchor": list(ANCHOR),
        "directions": list(directions),
        "filter": "nearest",
        "head_layer": head_layer,
        "head_width": _measure_head_width(front_idle),
        "actions": meta_actions,
        "head_attach": head_attach,
        "source": {"pipeline": "art_pipeline/characters/cbuild.py", "camera_elevation_deg": CAMERA_ELEVATION_DEG,
                   "job": job},
    }
    meta = sheet_output.packed_meta(meta, starts, columns)
    with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as handle:
        json.dump(meta, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    _log("圖集 %dx%d 存到 %s" % (sheet.shape[1], sheet.shape[0], out_dir))
    for layer_name, socket, _obj in layer_objects:
        layer_sheet, layer_starts, _ = atlas.pack_actions(layer_actions[layer_name], len(directions), columns)
        layer_sheet = _limit_colors(layer_sheet)
        layer_dir = os.path.join(CANDIDATE_LAYER_ROOT if (candidate or preview) else LAYER_ROOT, layer_name)
        os.makedirs(layer_dir, exist_ok=True)
        layer_path = os.path.join(layer_dir, "sheet.png")
        mimg.save_png(layer_sheet, layer_path)
        sheet_output.write_import(layer_path, PROJECT_ROOT, pixel=True)
        _write_pixel_mask(layer_dir, layer_sheet.shape)
        layer_meta = {
            "frame_size": list(FRAME_SIZE),
            "columns": columns,
            "pixels_per_meter": PIXELS_PER_METER,
            "anchor": list(ANCHOR),
            "directions": list(directions),
            "filter": "nearest",
            "layer": layer_name,
            "socket": socket,
            "body": name,
            "actions": {key: dict(value) for key, value in meta_actions.items()},
            "order": layer_orders[layer_name],
        }
        layer_meta = sheet_output.packed_meta(layer_meta, layer_starts, columns)
        with open(os.path.join(layer_dir, "meta.json"), "w", encoding="utf-8") as handle:
            json.dump(layer_meta, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        _log("圖層 %s 存到 %s" % (layer_name, layer_dir))
        _contact_sheet(name + "_" + layer_name, layer_actions[layer_name], directions)
    _contact_sheet(name, color_actions, directions)
    return out_dir


def _touches_edge(frame):
    """回傳碰到畫格哪幾邊，沒碰到是空字串"""
    solid = frame[..., 3] >= 0.5
    sides = []
    if solid[0, :].any():
        sides.append("上")
    if solid[-1, :].any():
        sides.append("下")
    if solid[:, 0].any():
        sides.append("左")
    if solid[:, -1].any():
        sides.append("右")
    return "".join(sides)


def _rig_height(armature, meshes):
    """站姿下網格的真身高，量頂點不量骨頭：頭骨在下巴上面一點點，量骨頭會少一顆頭"""
    idle = _find_action("Idle")
    if idle is not None:
        _set_action(armature, idle)
        _set_time(idle, 0.0)
    armature.rotation_euler = (0.0, 0.0, 0.0)
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    lowest, highest = None, None
    for obj in meshes:
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        matrix = evaluated.matrix_world
        for vertex in mesh.vertices:
            z = (matrix @ vertex.co).z
            lowest = z if lowest is None else min(lowest, z)
            highest = z if highest is None else max(highest, z)
        evaluated.to_mesh_clear()
    return (highest - lowest) if lowest is not None else 0.0


def _contact_sheet(name, color_actions, directions):
    """檢查圖：每個動作一列，每個方向取中間那一格排成一排，放大兩倍用最近點，看得清楚像素"""
    cell_w, cell_h = FRAME_SIZE
    rows = len(color_actions)
    canvas = np.zeros((cell_h * rows, cell_w * len(directions), 4), dtype=np.float32)
    canvas[..., :3] = (0.27, 0.36, 0.24)
    canvas[..., 3] = 1.0
    for row, (_, per_direction) in enumerate(color_actions):
        for column, frames in enumerate(per_direction):
            frame = frames[len(frames) // 2] if len(frames) > 1 else frames[0]
            alpha = frame[..., 3:4]
            area = canvas[row * cell_h:(row + 1) * cell_h, column * cell_w:(column + 1) * cell_w]
            area[..., :3] = frame[..., :3] * alpha + area[..., :3] * (1.0 - alpha)
    big = np.repeat(np.repeat(canvas, 2, axis=0), 2, axis=1)
    path = os.path.join(WORK, "%s_e%d_contact.png" % (name, round(CAMERA_ELEVATION_DEG)))
    mimg.save_png(big, path)
    _log("檢查圖 " + path)
    return path


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if not argv:
        raise SystemExit(__doc__)
    name = argv[0]
    options = {"--source": None, "--rigged": None, "--job": "novice", "--directions": "8", "--gender": "male",
               "--elevation": None, "--head-lift": None}
    flags = set()
    layers = []
    index = 1
    while index < len(argv):
        token = argv[index]
        if token == "--layer" and index + 1 < len(argv):
            layers.append(_parse_layer(argv[index + 1]))
            index += 2
        elif token in options and index + 1 < len(argv):
            options[token] = argv[index + 1]
            index += 2
        elif token in ("--preview", "--keep-rig", "--candidate", "--head-layer", "--ink", "--flat"):
            flags.add(token)
            index += 1
        else:
            raise SystemExit("看不懂的參數 " + token)
    if not options["--source"] and not options["--rigged"]:
        raise SystemExit("要給 --source 或 --rigged")
    directions = DIRECTIONS_5 if options["--directions"] == "5" else DIRECTIONS_8
    global CAMERA_ELEVATION_DEG, HEAD_LIFT_DEG
    if options["--elevation"]:
        CAMERA_ELEVATION_DEG = float(options["--elevation"])
    if options["--head-lift"] is not None:
        HEAD_LIFT_DEG = float(options["--head-lift"])
    global FLAT_SHADING
    FLAT_SHADING = "--flat" in flags

    blenv.clear_scene()
    if options["--rigged"]:
        armature, meshes = _import_rigged(os.path.abspath(options["--rigged"]))
    else:
        armature, meshes, _report = _bind_source(os.path.abspath(options["--source"]), options["--gender"])
        if "--keep-rig" in flags:
            _export_rig(name, armature, meshes)
    render(name, armature, meshes, directions, job=options["--job"], preview="--preview" in flags,
           head_layer="--head-layer" in flags, ink="--ink" in flags,
           candidate="--candidate" in flags, layers=layers)
    _log("done")


if __name__ == "__main__":
    main()
