"""把 Meshy 產的角色身體換綁到現在這副標準骨架上

為什麼需要這一步：`assets/generated/models/characters_meshy/` 那批身體是上一輪做的，
綁的是 KayKit 命名的舊骨架、身高 1.387 公尺、而且**沒有翻滾動作**。
現在的基準骨架是 `humanoid.py` 那副 Mixamo 命名的，身高 1.57 公尺，翻滾烤在裡面。
不換綁的話，換成 Meshy 角色就等於把閃避翻滾丟掉，那是不能接受的。

這支程式只做「換骨架」，不動網格的材質槽和臉的 UV。
那兩樣是 `art_pipeline/meshy/assemble.py` 已經做好的：
它把烘死的貼圖用顏色分群切成 Cloth、Leather、Skin、Face 四個槽，
臉那一塊的 UV 重新展進表情圖集的第 0 格。所以換骨架之後表情和染色都還在。

照 docs/美術風格指南.md 第 7.4 節那幾個坑做：

1. **不要用 Blender 的自動權重**，headless 下會安靜地失敗。用 meshkit 的距離權重，
   綁完一定要數權重大於 0.3 的頂點有幾個，是零就是失敗
2. **綁之前先把縮放烘進頂點**，不然權重會算在還沒縮放的座標上
3. **面數要先減**。這裡的身體是 assemble 時就減過的，所以只在超過上限時才動
"""

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import bmesh  # noqa: E402
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402
from mathutils import bvhtree  # noqa: E402

import blenv  # noqa: E402
import dodge_anim
import humanoid
import meshkit
import proportions
import rig_humanoid
import rigspec

SOURCE_DIR = os.path.join(blenv.PROJECT_ROOT, "assets", "generated", "models",
                          "characters_meshy")
OUT_ROOT = os.path.join(blenv.PROJECT_ROOT, "assets", "generated", "models",
                        "characters_real")
# 超過這個面數才減面。每一格動畫都要重算骨架變形，面數直接換成算圖時間
TRIANGLE_CAP = 9000
# 權重大於這個值才算「真的有綁到」，用來擋自動權重那種安靜的失敗
WEIGHT_FLOOR = 0.3


def _import_body(path):
    """匯入一個組好的身體，只留網格，骨架和動作都丟掉"""
    before = set(bpy.context.scene.objects)
    actions_before = set(bpy.data.actions)
    with blenv.ui():
        bpy.ops.import_scene.gltf(filepath=path)
    # 這份檔案裡的動作綁的是舊骨架，骨頭名字也是舊的，留著只有壞處：
    # 和標準骨架的同名動作撞名之後會被改成 Idle.001 跟著一起匯出，
    # 引擎那邊就看到四十個動作而不是二十二個，多出來的一半是永遠不會動的死資料
    for action in list(bpy.data.actions):
        if action not in actions_before:
            bpy.data.actions.remove(action)
    imported = [o for o in bpy.context.scene.objects if o not in before]
    meshes = [o for o in imported if o.type == "MESH"]
    for obj in imported:
        if obj.type != "MESH":
            bpy.data.objects.remove(obj, do_unlink=True)
    if not meshes:
        raise RuntimeError("沒有網格 " + path)
    body = meshes[0]
    for extra in meshes[1:]:
        bpy.data.objects.remove(extra, do_unlink=True)
    # 舊骨架的修改器要拿掉，不然新骨架綁上去會有兩層
    for modifier in list(body.modifiers):
        body.modifiers.remove(modifier)
    # 舊骨架的頂點群組也要清掉。留著的話新舊兩套權重會同時存在，
    # 而且同名的群組會被改成 head.001 這種名字，看起來綁好了其實有一半的權重是死的
    for group in list(body.vertex_groups):
        body.vertex_groups.remove(group)
    body.parent = None
    return body


def _measure_height(obj):
    world = obj.matrix_world
    zs = [(world @ v.co).z for v in obj.data.vertices]
    return max(zs) - min(zs), min(zs)


def _fit_and_apply(obj, target_height):
    """對齊身高並把縮放和位移烘進頂點

    第 7.4 節第 2 個坑：縮放留在物件上的話，權重會算在還沒縮放的座標上，整個歪掉。
    """
    height, bottom = _measure_height(obj)
    if height <= 1e-6:
        raise RuntimeError("量不到身高")
    scale = target_height / height
    obj.scale = (scale, scale, scale)
    obj.location = (0.0, 0.0, -bottom * scale)
    with blenv.ui():
        blenv.select_only(obj)
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return scale


def _decimate(obj, cap=TRIANGLE_CAP):
    triangles = sum(len(p.vertices) - 2 for p in obj.data.polygons)
    if triangles <= cap:
        return triangles
    modifier = obj.modifiers.new("Decimate", "DECIMATE")
    modifier.ratio = cap / float(triangles)
    with blenv.ui():
        blenv.select_only(obj)
        bpy.ops.object.modifier_apply(modifier=modifier.name)
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


# 手臂區不放鎖骨。鎖骨是軀幹裡的一小截，把它放進來的話整條手臂的頂點會黏在鎖骨上，
# 手臂變成從肩膀整根硬轉，看起來是兩片折起來的薄板
ARM = {"Left": "LeftArm,LeftForeArm,LeftForeArmTwist,LeftHand",
       "Right": "RightArm,RightForeArm,RightForeArmTwist,RightHand"}
LEG = {"Left": "Hips,LeftUpLeg,LeftLeg,LeftFoot,LeftToeBase",
       "Right": "Hips,RightUpLeg,RightLeg,RightFoot,RightToeBase"}
HEAD = "Head,Neck"
NECK = "Neck,Head,Spine2"
TORSO = "Hips,Spine,Spine1,Spine2"


def _assign_regions(obj, body):
    """照位置把每個頂點分到身體的哪一區

    外面產的網格沒有分區資訊，`meshkit.bind` 只好在所有骨頭裡找最近的線段。
    這在人形上會錯得很明顯：頭骨那根骨頭是中線上的一小截，
    頭兩側的頂點離手臂骨頭反而比較近，結果整顆頭被手臂拉開變成一片薄餅。
    分好區之後每個頂點只在自己那一區裡找骨頭，就不會跨區亂黏。
    """
    chin = proportions.CHIN
    crotch = body.crotch_z
    # 手臂的門檻要從**網格自己**量，不能用骨架的數字。
    # 外面產的身體不見得和我們的比例一樣寬：這一具的肩膀比骨架窄了快三成，
    # 照骨架的肩寬去切，手臂的內半截會被歸到軀幹，綁完手臂就扁掉。
    # 臀部那一圈沒有手臂經過，拿它的半寬當「軀幹有多寬」最準
    hip_half = 0.0
    for vertex in obj.data.vertices:
        if abs(vertex.co.z - body.hip_z) < 0.05:
            hip_half = max(hip_half, abs(vertex.co.x))
    if hip_half <= 1e-6:
        hip_half = body.hip[0]
    arm_threshold = hip_half * 0.92
    arm_floor = body.chest_z - 0.05
    # 手臂在哪一段高度也要量。手臂是一根橫躺的圓管，管心大約在肩高，
    # 所以管子的上半一定高過肩線，Q 版比例下還會頂到下巴。
    # 只有整根管子都分在同一區，綁出來才是一根有厚度的手臂
    tip = max(abs(vertex.co.x) for vertex in obj.data.vertices)
    outer = [vertex.co.z for vertex in obj.data.vertices
             if abs(vertex.co.x) > tip * 0.62]
    arm_low, arm_high = (min(outer), max(outer)) if outer else (arm_floor, chin)
    arm_low = max(min(arm_low - 0.02, arm_floor), crotch)
    arm_high = min(arm_high + 0.02, chin + 0.02)
    regions = []
    for vertex in obj.data.vertices:
        x, _, z = vertex.co
        side = "Left" if x >= 0.0 else "Right"
        # 手臂要在下巴和肩膀那兩條水平線之前判斷。
        # 反過來先照高度切的話，同一截手臂的上半會被歸到脖子和頭、下半跟著手臂骨頭走，
        # 動起來整根圓管被撕開攤平，看到的就是「手臂像兩塊板子」。
        # 這是實際量到的：修之前男英雄手臂區有 29 個百分比、女法師有 52 個百分比的頂點
        # 綁在 Neck、Head、Spine2 上
        if z < crotch:
            regions.append(LEG[side])
        elif arm_low <= z <= arm_high and abs(x) > arm_threshold:
            regions.append(ARM[side])
        elif z >= chin:
            regions.append(HEAD)
        elif z >= body.shoulder_z:
            regions.append(NECK)
        else:
            regions.append(TORSO)
    obj["regions"] = regions
    return regions


def measure_mesh(obj):
    """量一具網格的手腳長在哪裡，回傳正規化要用的四個數字

    只量不動任何東西。量出來的數字拿去和 `rigspec` 算出來的目標比，
    差多少就把網格扭多少。
    """
    xs = [v.co.x for v in obj.data.vertices]
    zs = [v.co.z for v in obj.data.vertices]
    tip = max(abs(min(xs)), abs(max(xs)))
    # 手臂在哪個高度也要量。只調橫向不調高度的話，骨頭會從手臂底下穿過去，
    # 手臂就被往下拉成兩片薄板。取「比頭還寬」那一段的平均高度，那一定是手臂
    outer = [v.co.z for v in obj.data.vertices if abs(v.co.x) > tip * 0.62]
    arm_z = sum(outer) / len(outer) if outer else None
    # 軀幹有多寬：在腋下到胸口之間掃過好幾圈，取**最窄**的那一圈。
    # 只量一圈會踩兩個坑：量在肩膀那個高度會量到手臂，
    # 量在下面一點又可能量到外擴的下襬。最窄的那一圈一定是軀幹本身
    torso_half = 0.0
    if arm_z is not None:
        widths = []
        for step in range(7):
            level = arm_z - 0.06 - step * 0.025
            band = [abs(v.co.x) for v in obj.data.vertices if abs(v.co.z - level) < 0.018]
            if band:
                widths.append(max(band))
        torso_half = min(widths) if widths else 0.0
    if torso_half <= 1e-6:
        torso_half = tip * 0.34
    # 腿的寬度要在腳踝量，不能在膝蓋量：裙襬蓋到膝蓋，量到的會是裙子的寬度，
    # 腿骨就被推到裙襬邊上去了。腳踝那一段只有靴子，不會有別的東西
    ankle_z = min(zs) + (max(zs) - min(zs)) * 0.055
    leg_x = 0.0
    for vertex in obj.data.vertices:
        if abs(vertex.co.z - ankle_z) < 0.025:
            leg_x = max(leg_x, abs(vertex.co.x))
    bottom, top = min(zs), max(zs)
    height = top - bottom
    # 脖子是肩膀和頭之間最窄的一圈，掃一整段取最窄的。
    # 只量一圈會量到肩膀或下巴，那是 docs/美術風格指南.md 第 7.4 節第 5 點記過的坑
    neck_z = None
    narrowest = None
    for step in range(int(NECK_BAND[0] * 100), int(NECK_BAND[1] * 100) + 1):
        level = bottom + height * step / 100.0
        ring = [abs(v.co.x) for v in obj.data.vertices if abs(v.co.z - level) < height * 0.010]
        if len(ring) < 6:
            continue
        width = max(ring)
        if narrowest is None or width < narrowest:
            narrowest = width
            neck_z = level
    # 胯部：從腳底往上找，兩條腿之間那個洞第一次被填起來的高度。
    # 長袍和喇叭裙會把洞整個蓋掉，找出來的值會落在腳踝附近，所以一定要夾範圍。
    # 夾住之後那幾具用的是範圍的下限，剪影本來就沒有胯部，夾錯也看不出來
    crotch_z = None
    for step in range(20, 61):
        level = bottom + height * step / 100.0
        if any(abs(v.co.x) < height * 0.02 and abs(v.co.z - level) < height * 0.012
               for v in obj.data.vertices):
            crotch_z = level
            break
    low = bottom + height * CROTCH_RANGE[0]
    high = bottom + height * CROTCH_RANGE[1]
    crotch_z = min(max(crotch_z if crotch_z is not None else low, low), high)
    return {"arm_tip": tip, "arm_z": arm_z if arm_z is not None else 0.0,
            "torso_half": torso_half, "leg_x": leg_x,
            "bottom": bottom, "top": top, "neck_z": neck_z if neck_z is not None else top,
            "crotch_z": crotch_z,
            "head_ratio": height / max(1e-6, top - (neck_z if neck_z is not None else top))}


# 十四具身體共用的比例，整組由 rigspec 的參數算出來。
#
# **方向和上一版相反：現在是網格被扭到骨架這邊，不是骨架被搬去遷就網格。**
#
# 上一版是每一具各量各的，量到什麼就把骨架搬到哪裡，結果十四副骨架彼此不一樣，
# 手臂骨頭最多差 0.243 公尺、握持掛點差 0.134 公尺，一件裝備要出十四份。
# 接著那一版改成全體共用一組**量出來的中位數**，骨架統一了，
# 但骨架的形狀變成由「這批網格剛好長什麼樣」決定，換一批網格就要重量一次，
# 而且使用者想改頭身比的時候沒有一個數字可以改。
#
# 現在這一版：`rigspec.STANDARD` 同時決定骨架和網格該被正規化成什麼形狀。
# 「Meshy 的網格手臂比設計稿長 0.076 公尺、握持掛點會落在前臂裡面」那個坑
# 就是這樣解掉的——手臂被縮到參數說的長度，掛點當然在手裡面。
SPEC = rigspec.STANDARD
STANDARD_FIT = SPEC.mesh_targets()
# 正規化之後還差超過這麼多公尺就印出來提醒。不擋，只是讓人知道哪一具最勉強
FIT_WARN = 0.02
# 找脖子只在這一段高度裡找，值是佔全高的比例
NECK_BAND = (0.52, 0.80)
# 胯部只能落在這一段高度裡。長袍和喇叭裙沒有胯部，量出來會掉到腳踝，一定要夾住
CROTCH_RANGE = (0.26, 0.50)
# 脖子上下各留這麼多公尺把「頭的縮小」和「身體的拉長」混起來。
# 不混的話兩種縮放在脖子那一圈直接對撞，網格會被扯出一個台階
BLEND_M = 0.06


def _smoothstep(low, high, value):
    t = min(max((value - low) / (high - low), 0.0), 1.0)
    return t * t * (3.0 - 2.0 * t)


def _height_map(fit, spec):
    """把舊的高度對到新的高度，分段線性

    控制點有五個：地板、胯部、手臂管心、下巴、頭頂。
    只用一個縮放不行：頭身比一改，身體整段拉長 1.4 倍，
    手臂會跟著被抬到 1.07 公尺，比參數說的 1.00 高了 4 個像素，
    腿也會長到胯部落在 0.63，比參數說的 0.46 多出 10 個像素。
    每一段各自對準之後，腿是腿的長度、手臂在手臂該在的高度
    """
    targets = spec.mesh_targets()
    pairs = [(fit["bottom"], 0.0),
             (fit["crotch_z"], spec.crotch_z),
             (fit["arm_z"], targets["arm_z"]),
             (fit["neck_z"], spec.chin_z),
             (fit["top"], spec.height_m)]
    # 控制點一定要嚴格遞增，不然分段線性會反折。
    # 寬袍子那幾具量到的胯部會被夾到下限，夾完有可能和別的控制點撞在一起
    clean = [pairs[0]]
    for source, target in pairs[1:]:
        if source > clean[-1][0] + 1e-4 and target > clean[-1][1] + 1e-4:
            clean.append((source, target))

    def convert(z):
        if z <= clean[0][0]:
            return clean[0][1] + (z - clean[0][0])
        for index in range(1, len(clean)):
            low_s, low_t = clean[index - 1]
            high_s, high_t = clean[index]
            if z <= high_s:
                ratio = (z - low_s) / (high_s - low_s)
                return low_t + (high_t - low_t) * ratio
        last_s, last_t = clean[-1]
        before_s, before_t = clean[-2]
        slope = (last_t - before_t) / (last_s - before_s)
        return last_t + (z - last_s) * slope

    return convert


def _width_map(fit, spec):
    """把舊的橫向座標對到新的，軀幹和手臂分兩段

    手臂鏈用仿射對應不用等比縮。等比縮會把肩關節也一起縮，
    可是肩關節該落在軀幹表面上，那個位置和手的位置沒有固定比例。
    兩端各自對準、中間照原本的間距分配，手肘才會落在手肘該在的地方
    """
    targets = spec.mesh_targets()
    torso_source = max(fit["torso_half"], 1e-4)
    torso_target = targets["torso_half"]
    tip_source = max(fit["arm_tip"], torso_source + 1e-4)
    tip_target = max(targets["arm_tip"], torso_target + 1e-4)
    arm_span = (tip_target - torso_target) / (tip_source - torso_source)

    def convert(x):
        sign = 1.0 if x >= 0.0 else -1.0
        value = abs(x)
        if value <= torso_source:
            return sign * value * (torso_target / torso_source)
        return sign * (torso_target + (value - torso_source) * arm_span)

    return convert


def normalize_to_spec(obj, spec=None, fit=None):
    """把一具網格扭到標準比例，回傳扭之前量到的數字

    做的是一次空間扭曲，不重建網格也不動 uv，所以表情、染色和材質槽都還在。
    頭和身體在脖子那一圈用 smoothstep 混過去，不然會被扯出一個台階。
    """
    spec = spec or SPEC
    fit = fit or measure_mesh(obj)
    height = _height_map(fit, spec)
    width = _width_map(fit, spec)
    neck = fit["neck_z"]
    head_scale = spec.head_height / max(1e-6, fit["top"] - neck)
    # 頭要繞自己的前後中心縮，不然臉那一塊會往後陷進頭裡
    head_points = [v.co.y for v in obj.data.vertices if v.co.z > neck]
    head_y = ((max(head_points) + min(head_points)) / 2.0) if head_points else 0.0
    torso_ratio = spec.mesh_targets()["torso_half"] / max(1e-4, fit["torso_half"])
    for vertex in obj.data.vertices:
        point = vertex.co
        blend = _smoothstep(neck - BLEND_M, neck + BLEND_M, point.z)
        # 頭整顆等比縮，身體只照軀幹的倍率縮，中間混過去
        side = width(point.x) * (1.0 - blend) + point.x * head_scale * blend
        depth_scale = torso_ratio * (1.0 - blend) + head_scale * blend
        pivot = head_y * blend
        vertex.co = Vector((side, pivot + (point.y - pivot) * depth_scale,
                            height(point.z)))
    obj.data.update()
    return fit


def _bind(obj, armature, body):
    """距離權重。只綁會變形的骨頭，掛點和 IK 目標不參與"""
    _assign_regions(obj, body)
    # Root 不參與變形。它是從地板拉到髖部的一根長骨，距離權重會讓腳附近的頂點黏到它，
    # 腳就不跟著小腿走了。Root 的工作是整個人的位移和翻滾，不是皮膚
    allowed = set(humanoid.deform_bones()) - {"Root"}
    keep = {}
    for bone in list(armature.data.bones):
        if bone.name not in allowed:
            keep[bone.name] = bone
    # meshkit.bind 會對骨架上每一根骨頭都開一個頂點群組，
    # 掛點和 IK 目標也會拿到權重，那會讓武器掛點跟著皮膚動。先擋掉
    blocked = [name for name in keep]
    # 外面產的網格接縫多，權重要軟一點才不會在手肘和膝蓋擠出稜線
    meshkit.bind(obj, armature, falloff=2.4, max_bones=3)
    for name in blocked:
        group = obj.vertex_groups.get(name)
        if group is not None:
            obj.vertex_groups.remove(group)
    return obj


def weight_report(obj):
    """有幾個頂點真的被綁到，以及每根骨頭吃到幾個頂點

    第 7.4 節第 1 個坑就是靠這個擋下來的：自動權重會建好所有頂點群組但權重全是零，
    看起來完全正常，模型卻一動也不動。
    """
    names = {group.index: group.name for group in obj.vertex_groups}
    per_bone = {}
    bound = 0
    for vertex in obj.data.vertices:
        best = 0.0
        for element in vertex.groups:
            if element.weight > best:
                best = element.weight
            if element.weight >= WEIGHT_FLOOR:
                name = names.get(element.group, "?")
                per_bone[name] = per_bone.get(name, 0) + 1
        if best >= WEIGHT_FLOOR:
            bound += 1
    return {"vertices": len(obj.data.vertices), "bound": bound, "per_bone": per_bone}


# 骨架一律用中性身體建，男女不分開。
#
# 男女分開建只差兩根骨頭：鎖骨橫向差 0.0038 公尺、背後掛點前後差 0.0155 公尺。
# 那兩個數字小到畫面上看不出來，卻足以讓男女兩套骨架不相等，
# 於是背後的披風和箭袋要男女各出一份。差 0.0155 公尺換成像素是一個像素，
# 為了一個像素多出一倍的圖是划不來的。
# 網格本身的男女差異在網格裡，不在骨架裡，這樣就夠了
RIG_GENDER = "neutral"


def build(source_name):
    """換綁一個身體，回傳 (網格, 骨架, 權重報告)"""
    blenv.clear_scene()
    armature = rig_humanoid.build(RIG_GENDER)
    dodge_anim.build_all(armature)
    rig_humanoid.rest_pose(armature)
    body = _import_body(os.path.join(SOURCE_DIR, source_name + ".glb"))
    _fit_and_apply(body, proportions.HEIGHT)
    triangles = _decimate(body)
    # 先把網格扭到參數說的比例，再綁骨。順序不能反：
    # 綁完再扭的話權重是照舊比例算的，手臂會從新的骨頭旁邊滑過去
    before = normalize_to_spec(body, SPEC)
    after = measure_mesh(body)
    _bind(body, armature, proportions.BODIES[RIG_GENDER])
    report = weight_report(body)
    report["fit"] = before
    report["fit_after"] = after
    report["fit_off"] = {key: after[key] - value
                         for key, value in STANDARD_FIT.items()}
    report["head_ratio"] = (before["head_ratio"], after["head_ratio"])
    report["triangles"] = triangles
    return body, armature, report


# 頭髮的底色。比皮膚深很多，剪影和明暗才分得出頭髮和頭皮
HAIR_BASE = (0.20, 0.118, 0.086, 1.0)


def _set_base_colour(mat, colour):
    if not mat.use_nodes:
        mat.diffuse_color = colour
        return
    for node in mat.node_tree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            node.inputs["Base Color"].default_value = colour


def body_transform(source_name):
    """量出身體被縮放搬移了多少，髮型要套一模一樣的一份才會還在頭上

    髮型是獨立的網格，和身體同一個座標系。身體對齊身高的時候縮了也搬了，
    髮型不跟著套同一份就會浮在頭上或穿進去。
    """
    body = _import_body(os.path.join(SOURCE_DIR, source_name + ".glb"))
    height, bottom = _measure_height(body)
    bpy.data.objects.remove(body, do_unlink=True)
    scale = proportions.HEIGHT / height
    return scale, -bottom * scale


# 頭髮的頂點要比頭頂高這麼多。太小會和頭皮打架閃爍，太大會看得出一頂帽子浮著。
# 寫成頭半徑的倍數不寫死公尺：頭身比一改頭就變小，留一樣的絕對間隙看起來會是浮的
HAIR_CROWN_MARGIN = proportions.HEAD_RADIUS * 0.033
# 頭髮要比頭殼寬這麼多倍，剛好罩在外面
HAIR_WIDTH_MARGIN = 1.06
# 縮放的安全範圍。超出這個範圍代表來源的髮型根本不是給這顆頭用的，
# 硬縮只會做出一頂安全帽，寧可原樣輸出讓人看得出不對。
# 下限本來是 0.70，那是頭佔全高 47 個百分比那一版的數字。
# 頭身比改成 4.07 之後頭只剩原來的一半大，這批髮型真正要的倍率掉到 0.45 上下，
# 0.70 會把每一頂都夾在下限，做出五頂比頭大一倍的香菇。
# 卡在邊界比放寬更糟：卡住了不會報錯，只會安靜地做出一頂不對的頭髮
HAIR_SCALE_RANGE = (0.30, 2.60)
# 量頭殼寬度用頭頂這一段，佔「下巴到頭頂」的比例。
# 量整顆頭會被耳朵和臉頰撐大，量到的不是髮型真正要罩住的那一圈
CROWN_BAND = (0.75, 0.95)
# 量頭殼的參考身體。髮型是全職業共用的，所以要對**所有會戴它的頭**一起量，
# 每個方向取最外面的那一顆，這樣十四具身體都罩得住。
#
# 只對灰白人體模型量是不夠的，這一條是踩到才知道的：本來寫著「正式身體的頭都在
# 人體模型的正負一成以內」，實際量下來正式身體的上半頭殼最多凸出 0.051 公尺，
# 比留的餘裕還大。畫面上就是後腦杓破出一塊膚色的島，而且所有數字都說覆蓋率是滿的，
# 因為量的是另一顆頭。
#
# 所以髮型一定要在身體之後才做，build_all 的順序不能反
HEAD_REFERENCE_DIR = OUT_ROOT
HEAD_REFERENCE_FALLBACK = os.path.join(blenv.PROJECT_ROOT, "assets", "generated", "models",
                                       "characters_mannequin", "body.glb")


def _reference_bodies(gender=""):
    """會戴這批髮型的身體。給性別就只取那個性別的，一具都沒有時退回灰白人體模型"""
    out = []
    if os.path.isdir(HEAD_REFERENCE_DIR):
        for name in sorted(os.listdir(HEAD_REFERENCE_DIR)):
            if not (name.startswith("body_") and name.endswith(".glb")):
                continue
            if gender and ("_%s_" % gender) not in name:
                continue
            out.append(os.path.join(HEAD_REFERENCE_DIR, name))
    return out or [HEAD_REFERENCE_FALLBACK]


# 五官在表情圖集第 0 格裡佔哪一塊 uv，量自 `face_male_e0.png` 和 `face_female_e0.png`：
# 把第 0 格裡和皮膚底色差很多的像素框起來，就是眼睛、眉毛、嘴巴實際畫到的範圍。
# 這一塊對到身體網格上是 80 片左右的面，高度落在 1.00 到 1.29 公尺，也就是嘴巴到眉毛
FEATURE_UV_BOX = (0.020, 0.230, 0.110, 0.386)


def _feature_polygons(path):
    """一具身體上真的畫著五官的那些面，回傳頂點座標和面

    為什麼要靠 uv 挑，不能直接拿 `Face` 材質槽：`Face` 那一塊是整個前半顆頭，
    左右各到 0.34 公尺、上下 0.88 到 1.41，連耳朵旁邊都算進去。
    拿它當「不能被遮住的地方」的話，頭髮蓋住鬢角也會被判成蓋住臉。
    真正不能被遮的是圖上畫了眼睛眉毛嘴巴的那一小塊
    """
    before = set(bpy.context.scene.objects)
    obj = _import_body(path)
    matrix = obj.matrix_world
    names = [slot.name if slot else "" for slot in obj.data.materials]
    layer = obj.data.uv_layers.active
    verts = [matrix @ vertex.co for vertex in obj.data.vertices]
    polys = []
    if layer is not None:
        for poly in obj.data.polygons:
            slot = names[poly.material_index] if poly.material_index < len(names) else ""
            if "Face" not in slot:
                continue
            # glTF 的 v 原點在左上，Blender 匯進來會翻過來，所以要翻回去才對得上圖
            us = [layer.data[i].uv.x for i in poly.loop_indices]
            vs = [1.0 - layer.data[i].uv.y for i in poly.loop_indices]
            u = sum(us) / len(us)
            v = sum(vs) / len(vs)
            if (FEATURE_UV_BOX[0] <= u <= FEATURE_UV_BOX[1]
                    and FEATURE_UV_BOX[2] <= v <= FEATURE_UV_BOX[3]):
                polys.append(tuple(poly.vertices))
    for obj2 in list(bpy.context.scene.objects):
        if obj2 not in before:
            bpy.data.objects.remove(obj2, do_unlink=True)
    return verts, polys


def _crown_band(points):
    """落在頭頂那一段高度裡的點"""
    span = proportions.HEAD_TOP - proportions.CHIN
    low = proportions.CHIN + span * CROWN_BAND[0]
    high = proportions.CHIN + span * CROWN_BAND[1]
    return [p for p in points if low <= p[2] <= high]


def _crown_centre(points):
    """頭頂那一段的水平中心，也就是這顆頭殼或這頂頭髮的軸心在哪裡

    取第五和第九十五百分位的中點，不取包圍盒中點。
    包圍盒會被一撮翹起來的瀏海或一根馬尾整個拉歪，中間那段才是頭殼本身
    """
    band = _crown_band(points)
    if len(band) < 12:
        return None
    out = []
    for axis in (0, 1):
        values = sorted(p[axis] for p in band)
        low = values[int(len(values) * 0.05)]
        high = values[min(len(values) - 1, int(len(values) * 0.95))]
        out.append((low + high) / 2.0)
    return tuple(out)


def _crown_radius(points, centre=(0.0, 0.0), pct=0.9):
    """頭頂那一段的半徑，繞 centre 這根軸量

    半徑一定要繞自己的軸心量。繞原點量的話，一頂往前偏掉的頭髮會被量成比實際寬，
    寬度校正跟著把它縮小，於是「偏掉」和「太小」互相加乘：
    現況就是這樣做出一頂半徑 0.24、中心往前 0.13 的小碗，
    扣在半徑 0.37 的頭上只蓋得住前額和頭頂，後腦杓整片露出來
    """
    band = _crown_band(points)
    if len(band) < 12:
        return None
    radii = sorted(((p[0] - centre[0]) ** 2 + (p[1] - centre[1]) ** 2) ** 0.5 for p in band)
    return radii[min(len(radii) - 1, int(len(radii) * pct))]


## 量過的頭殼留著重複用。十四具身體每做一頂頭髮要量三次，
## 每次都重新匯入的話光量頭就佔掉大半的時間
_HEAD_CACHE = {}


def _reference_head():
    """量所有參考身體的頭：頭頂那一段的軸心和半徑，外加每一顆頭殼的 BVH

    半徑取所有身體裡最大的那一個，射線也是每一顆頭都打一次取最遠的，
    髮型才罩得住十四具身體裡頭最大的那一具。

    BVH 只收下巴以上的面。收整具身體的話，往下打的射線會打到肩膀和軀幹，
    髮尾就會被推到肩膀外面去
    """
    paths = tuple(_reference_bodies())
    if paths in _HEAD_CACHE:
        return _HEAD_CACHE[paths]
    before = set(bpy.context.scene.objects)
    centres = []
    radius = 0.0
    trees = []
    for path in paths:
        body = _import_body(path)
        points = [tuple(body.matrix_world @ v.co) for v in body.data.vertices]
        one = _crown_centre(points)
        if one is not None:
            centres.append(one)
        measured = _crown_radius(points, one or (0.0, 0.0))
        if measured is not None:
            radius = max(radius, measured)
        verts = [body.matrix_world @ v.co for v in body.data.vertices]
        polys = [tuple(poly.vertices) for poly in body.data.polygons
                 if (body.matrix_world @ poly.center).z >= proportions.CHIN]
        if polys:
            trees.append(bvhtree.BVHTree.FromPolygons(verts, polys))
        bpy.data.objects.remove(body, do_unlink=True)
    centre = ((sum(c[0] for c in centres) / len(centres),
               sum(c[1] for c in centres) / len(centres)) if centres else (0.0, 0.0))
    for obj in list(bpy.context.scene.objects):
        if obj not in before:
            bpy.data.objects.remove(obj, do_unlink=True)
    _HEAD_CACHE[paths] = (centre, radius, trees)
    return centre, radius, trees


# 聯集最多可以比中位數大這麼多公尺。超過就當成耳朵，不追。
#
# 這個數字是量出來的：四百個方向裡，「最遠那一顆頭」比中位數大多少，
# 中位是 0.018、p90 是 0.037，但在正側方那幾個方向會跳到 0.093。
# 那幾個方向就是耳朵，而且每一具的耳朵大小差很多。
# 不設上限的話，頭髮為了罩住最大的那隻耳朵，會在十四具身上都鼓出九公分，
# 畫面上是太陽穴附近兩塊多出來的量體和幾根刺。
# 耳朵本來就該露在頭髮外面，見美術風格指南第 1.5 節，所以這裡不追它。
# 那一次是在頭佔全高 47 個百分比的頭上量的，所以寫成頭半徑的倍數，頭一縮小它跟著縮
SKULL_SPREAD_ALLOWANCE = proportions.HEAD_RADIUS * 0.095


def _skull_radius(trees, origin, direction):
    """所有參考頭殼裡這個方向有多遠，取聯集但夾在中位數加一點點以內

    取聯集是為了讓十四具身體都罩得住；夾上限是為了不去追耳朵。
    都沒打到回傳 None
    """
    hits = []
    for tree in trees:
        hit = tree.ray_cast(origin, direction)
        if hit[0] is not None:
            hits.append((hit[0] - origin).length)
    if not hits:
        return None
    hits.sort()
    middle = hits[len(hits) // 2]
    return min(hits[-1], middle + SKULL_SPREAD_ALLOWANCE)


# 髮面要留在頭皮外面這麼多公尺。太小會閃爍，太大會看得出頭髮浮在頭上。
# 只留幾公釐不夠：髮殼一面三角形跨過的弧長比頭殼的曲率大，兩個角推到頭皮外面，
# 中間那一片照樣往內凹進頭殼裡，畫面上還是一塊一塊的膚色斑點。
# 要留得比那一片的下垂量大，在半徑 0.37 公尺的頭上實測兩公分剛好。
# 同樣寫成頭半徑的倍數，頭一縮小間隙跟著縮，不然頭髮會整頂浮起來
HAIR_SKULL_CLEARANCE = proportions.HEAD_RADIUS * 0.054


# 五官外面要再多留這麼多度的空白。
# 不留的話會有兩個問題：一是射線點對點比對，髮面的中心剛好落在兩片五官之間就漏掉，
# 實測用純射線判定挖完還有 37 個百分比的五官被蓋住；
# 二是髮面擦著眉毛邊緣過去，在有描邊的材質下讀起來還是蓋住了。
# 這個角度是照髮面本身的角尺寸訂的，一片髮面在半徑 0.4 公尺處大約四度，留八度是兩片
FACE_CONE_MARGIN_DEG = 8.0


## 量過的五官位置留著重複用，理由和 _HEAD_CACHE 一樣
_FACE_CACHE = {}


def _face_cone(gender):
    """五官佔住的那些方向，每個方向記著那片五官離頭心多遠

    做成方向的集合不做成射線判定，理由寫在 FACE_CONE_MARGIN_DEG 上面：
    射線是點對點，打在兩片五官中間就漏掉，漏掉的那一片頭髮就留在臉上。

    同性別所有身體的五官都要收進來。只避開一具的話，換一具頭型稍微不同的就又蓋回去了
    """
    paths = tuple(_reference_bodies(gender))
    if paths in _FACE_CACHE:
        return _FACE_CACHE[paths]
    origin = Vector((0.0, 0.0, proportions.HEAD_CENTER_Z))
    out = []
    for path in paths:
        verts, polys = _feature_polygons(path)
        for poly in polys:
            centre = sum((verts[i] for i in poly), Vector()) / len(poly)
            radial = centre - origin
            distance = radial.length
            if distance > 1e-6:
                out.append((radial / distance, distance))
    _FACE_CACHE[paths] = out
    return out


def _in_face_cone(cone, origin, direction, distance, margin_cos):
    """這個方向、這個距離的東西是不是擋在五官前面或貼著五官的邊"""
    for face_direction, face_distance in cone:
        if distance <= face_distance:
            continue
        if direction.dot(face_direction) >= margin_cos:
            return True
    return False


def _wrap_hair_over_skull(hair, centre, trees, cone=None):
    """把陷進頭殼裡的髮面推到頭皮外面，回傳被搬過的頂點編號

    只縮放對不起來：來源的髮殼是照別顆頭做的，形狀和我們這顆頭不一樣，
    等比縮放只能對上平均半徑，對不上的方向照樣讓頭皮穿出來。
    實測光靠縮放，一百一十五個頭殼方向裡有五十幾個是頭皮在外面頭髮在裡面，
    畫面上就是後腦杓一塊一塊的膚色斑點。

    只推「朝外的那一面」。髮殼是一塊封閉的實體，內壁的法線朝著頭心，
    把內壁一起推出去的話內外壁會疊在同一個位置，變成互相閃爍的兩層面。
    下巴以下的長髮也不碰，那是垂下來的髮尾不是扣在頭上的部分。

    **五官正前方的髮面一律不推。**這一條是踩到才補的：來源的髮殼是一顆封閉的圓頂，
    連臉的前面都有面，只是以前髮殼太小整片埋在頭殼裡面，被頭自己的表面擋住看不到。
    推出去之後那些面就跑到臉前面，變成一頂連臉一起蓋住的大安全帽。
    量到的是五官有 7 到 100 個百分比被蓋住，而且從背面看完全正常，只有正面看得出來
    """
    if not trees:
        return []
    origin = Vector((centre[0], centre[1], proportions.HEAD_CENTER_Z))
    margin_cos = math.cos(math.radians(FACE_CONE_MARGIN_DEG))
    normals = [vertex.normal.copy() for vertex in hair.data.vertices]
    matrix = hair.matrix_world
    inverse = matrix.inverted()
    moved = []
    for index, vertex in enumerate(hair.data.vertices):
        world = matrix @ vertex.co
        if world.z < proportions.CHIN:
            continue
        radial = world - origin
        distance = radial.length
        if distance < 1e-6:
            continue
        direction = radial / distance
        if normals[index].dot(direction) <= 0.1:
            continue
        reach = _skull_radius(trees, origin, direction)
        if reach is None:
            continue
        skull = reach + HAIR_SKULL_CLEARANCE
        if distance >= skull:
            continue
        if cone and _in_face_cone(cone, origin, direction, skull, margin_cos):
            continue
        vertex.co = inverse @ (origin + direction * skull)
        moved.append(index)
    hair.data.update()
    return moved


# 試過在推出去之後加一道平滑修改器抹掉折角，結果反而變差：
# 拉普拉斯平滑會整體縮，抹完有三成八的後腦杓又縮回頭殼裡面，
# 再推一次也救不回來，因為凹的是三角面的中間不是頂點。
# 髮面上那些疙瘩是來源網格本來就有的，要解決是重畫髮型，不是在這裡抹


def _carve_face_opening(hair, cone):
    """把擋在五官前面的髮面整片刪掉，開出臉的洞，回傳刪了幾片

    來源的髮殼是一顆封閉的圓頂，臉的前面本來就有面。
    不刪的話不管怎麼縮怎麼推，臉都會被蓋住一塊。
    髮型要有瀏海底下的開口不是靠縮放縮出來的，是要真的把那塊挖掉。

    內外壁一起刪。只刪外壁的話會露出背面朝著鏡頭的內壁，
    在卡通材質下是一塊死黑。整塊挖掉留下來的是髮殼本身的厚度，
    那個斷面讀起來剛好就是髮際線
    """
    if not cone:
        return 0
    origin = Vector((0.0, 0.0, proportions.HEAD_CENTER_Z))
    margin_cos = math.cos(math.radians(FACE_CONE_MARGIN_DEG))
    matrix = hair.matrix_world
    doomed = []
    for poly in hair.data.polygons:
        points = [matrix @ poly.center]
        points.extend(matrix @ hair.data.vertices[i].co for i in poly.vertices)
        for point in points:
            radial = point - origin
            distance = radial.length
            if distance < 1e-6:
                continue
            if _in_face_cone(cone, origin, radial / distance, distance, margin_cos):
                doomed.append(poly.index)
                break
    if not doomed:
        return 0
    mesh = bmesh.new()
    mesh.from_mesh(hair.data)
    mesh.faces.ensure_lookup_table()
    bmesh.ops.delete(mesh, geom=[mesh.faces[i] for i in doomed], context="FACES")
    mesh.to_mesh(hair.data)
    mesh.free()
    hair.data.update()
    return len(doomed)


def face_occlusion(hair, gender):
    """五官有幾成被頭髮擋住。這是「頭髮蓋住臉」唯一擋得住的量法

    量覆蓋率只看得到後腦杓露不露頭皮，那個數字滿分的時候臉可以是全黑的。
    這裡反過來從頭心往每一片五官打一條射線，頭髮擋在前面就算一片
    """
    origin = Vector((0.0, 0.0, proportions.HEAD_CENTER_Z))
    matrix = hair.matrix_world
    verts = [matrix @ v.co for v in hair.data.vertices]
    polys = [tuple(p.vertices) for p in hair.data.polygons]
    if not polys:
        return 0.0
    shell = bvhtree.BVHTree.FromPolygons(verts, polys)
    total = blocked = 0
    for path in _reference_bodies(gender):
        body_verts, feature_polys = _feature_polygons(path)
        for poly in feature_polys:
            centre = sum((body_verts[i] for i in poly), Vector()) / len(poly)
            radial = centre - origin
            distance = radial.length
            if distance < 1e-6:
                continue
            direction = radial / distance
            total += 1
            # 射線要從這片五官**往外**打，不能從外面往回打。
            # 從外面往回打的話，臉前面挖空之後射線會穿過整顆頭，
            # 打到後腦杓的頭髮，那一片在數字上就變成「擋住臉」。
            # 實測這個錯誤讓挖乾淨的髮型照樣報 40 個百分比，
            # 而且怎麼挖都降不下去，因為擋住的東西根本不在臉這一邊
            if shell.ray_cast(origin + direction * (distance + 0.002), direction)[0] is not None:
                blocked += 1
    return blocked / total if total else 0.0


def _seat_hair_on_head(hair):
    """把髮型罩到頭上，回傳實際縮放倍數

    只照身高等比例縮是不夠的：概念圖那顆頭和我們這副骨架的頭不一樣大，
    換算完的髮型常常整頂陷進頭殼裡，遊戲裡看起來就是禿頭再加一撮毛。

    對寬度不對高度：讓髮型頭頂那一圈剛好比頭殼大一點點。
    改成讓最高點碰到頭頂會出事，長髮的最高點本來就在頭頂附近，
    照那樣縮會把整頭長髮一起放大成一朵香菇。高度用搬的不用縮，
    搬只搬上去不搬下去，這樣短髮會被抬到蓋住頭皮，長髮的長度不受影響。

    水平方向也要對正，這是這一輪補的。來源的髮殼整頂往前偏了 0.13 公尺，
    只縮不搬的話它就停在頭的前半邊，後腦杓整片是光的，而遊戲大多從背後看。
    偏掉還會反過來騙寬度校正：繞原點量到的半徑被偏移撐大，校正就把髮型縮小，
    結果是一頂又小又偏的碗。所以先把軸心對上頭殼的軸心，再繞那根軸量寬度。
    """
    head_centre, reference, _trees = _reference_head()
    points = [tuple(hair.matrix_world @ v.co) for v in hair.data.vertices]
    centre_z = (proportions.CHIN + proportions.HEAD_TOP) / 2.0
    top = max(p[2] for p in points)
    target = (reference or 0.0) * HAIR_WIDTH_MARGIN

    def place(scale, shift):
        """縮放、水平對正、抬高之後的座標。抬高只抬不壓，長髮的長度不會被動到"""
        rise = max(0.0, proportions.HEAD_TOP + HAIR_CROWN_MARGIN
                   - (centre_z + (top - centre_z) * scale))
        moved = [(p[0] * scale + shift[0], p[1] * scale + shift[1],
                  centre_z + (p[2] - centre_z) * scale + rise) for p in points]
        return moved, rise

    # 一次算不準：縮放會把原本在頭頂那一段以外的頂點搬進來，量到的寬度和軸心跟著變。
    # 所以量完再縮、縮完再量，對正和縮放輪流跑幾輪就收斂了
    factor, lift = 1.0, 0.0
    shift = [0.0, 0.0]
    if target > 1e-4:
        for _ in range(10):
            moved, lift = place(factor, shift)
            centre = _crown_centre(moved)
            if centre is not None:
                shift[0] += head_centre[0] - centre[0]
                shift[1] += head_centre[1] - centre[1]
                moved, lift = place(factor, shift)
            measured = _crown_radius(moved, head_centre)
            if measured is None or measured < 1e-4:
                break
            if abs(measured - target) / target < 0.03:
                break
            factor = min(max(factor * target / measured, HAIR_SCALE_RANGE[0]),
                         HAIR_SCALE_RANGE[1])
        _, lift = place(factor, shift)
    hair.scale = (factor, factor, factor)
    hair.location = (shift[0], shift[1], centre_z * (1.0 - factor) + lift)
    with blenv.ui():
        blenv.select_only(hair)
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return factor


def export_hair(source_name, body_name, out_name=None):
    """把髮型搬到新的身高。髮型不綁骨架，遊戲端掛在 head 掛點上"""
    blenv.clear_scene()
    scale, lift = body_transform(body_name)
    hair = _import_body(os.path.join(SOURCE_DIR, source_name + ".glb"))
    # 概念圖上那頂頭髮是淺金色，分群之後 v3_Hair 的底色幾乎和皮膚一樣，
    # 在遊戲裡就看不見，角色讀起來是禿的。底色一律換成明顯比皮膚深的棕色，
    # 玩家選的髮色還是照色階染上去，只是起點不再和皮膚撞色
    for slot in hair.data.materials:
        if slot is not None and "Hair" in slot.name:
            _set_base_colour(slot, HAIR_BASE)
    hair.scale = (scale, scale, scale)
    hair.location = (0.0, 0.0, lift)
    with blenv.ui():
        blenv.select_only(hair)
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    fitted = _seat_hair_on_head(hair)
    gender = "female" if "_female" in source_name else "male"
    cone = _face_cone(gender)
    head_centre, _radius, trees = _reference_head()
    wrapped = len(_wrap_hair_over_skull(hair, head_centre, trees, cone))
    carved = _carve_face_opening(hair, cone)
    path = os.path.join(OUT_ROOT, (out_name or source_name) + ".glb")
    os.makedirs(OUT_ROOT, exist_ok=True)
    with blenv.ui():
        blenv.select_only([hair])
        bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True,
                                  export_animations=False, export_apply=False,
                                  export_yup=True, export_skins=False)
    top = max((hair.matrix_world @ v.co).z for v in hair.data.vertices)
    report = {"scale": scale, "lift": lift, "top": top, "seat": fitted,
              "wrapped": wrapped, "carved": carved}
    report.update(hair_coverage(hair))
    report["face"] = face_occlusion(hair, gender)
    return path, report


# 後腦杓那一片頭皮最多可以有這個比例露在頭髮外面。
# 遊戲大多從角色背後看，背面露頭皮是一定會被看到的，所以這條抓得比正面嚴
BACK_BARE_CEILING = 0.06
# 整顆頭殼最多可以有這個比例露在頭髮外面。臉本來就要露出來，所以整體比背面寬鬆
BARE_CEILING = 0.45
# 五官最多可以有這個比例被頭髮擋住。實際上要求是零，留一點是給射線取樣的誤差。
#
# 這條是補上來的，補的理由值得寫下來：上面那兩條只看「頭皮有沒有露出來」，
# 所以一頂把整顆頭連臉一起包起來的安全帽會拿到滿分。實際發生的就是這樣，
# 背面八個方位全部漂亮，正面五官被蓋住 7 到 100 個百分比，而且沒有任何數字說話。
# **一個只會往一個方向錯的指標，等於沒有指標。**蓋不夠和蓋太多要各有一條線
FACE_OCCLUSION_CEILING = 0.02
# 量覆蓋率用幾條射線。夠密才看得出一塊一塊的斑點，太密只是變慢
COVER_RAYS = 400


def _dome_directions(count=COVER_RAYS):
    """頭殼上半部的均勻取樣方向，費氏球面取樣

    取到水平線下面一點點，因為耳朵那一圈也算頭殼
    """
    out = []
    golden = math.pi * (3.0 - math.sqrt(5.0))
    for index in range(count):
        height = 1.0 - (index + 0.5) / count * 1.25
        if height < -0.25:
            break
        radius = math.sqrt(max(0.0, 1.0 - height * height))
        angle = golden * index
        out.append(Vector((math.cos(angle) * radius, math.sin(angle) * radius, height)))
    return out


def hair_coverage(hair):
    """從頭心往外打一圈射線，數有幾個方向是頭皮在外面頭髮在裡面

    這是唯一擋得住「只蓋住頭頂」的量法。量包圍盒沒有用：
    一頂整個往前偏的髮殼包圍盒照樣有寬度，數字很正常，畫面上後腦杓卻是光的。
    每個方向都拿頭殼的半徑和頭髮的半徑直接比，比不過就是那一塊會露出頭皮
    """
    centre, reference, trees = _reference_head()
    if not trees:
        return {"bare": 1.0, "back_bare": 1.0, "reference": reference}
    origin = Vector((centre[0], centre[1], proportions.HEAD_CENTER_Z))
    verts = [hair.matrix_world @ v.co for v in hair.data.vertices]
    polys = [tuple(poly.vertices) for poly in hair.data.polygons]
    shell = bvhtree.BVHTree.FromPolygons(verts, polys)
    total = bare = back_total = back_bare = 0
    for direction in _dome_directions():
        skull_radius = _skull_radius(trees, origin, direction)
        if skull_radius is None:
            continue
        # 從頭皮往外打一條，打不到頭髮就是這一塊頭皮露在外面。
        # 不要從外面往回打：臉那邊挖空之後射線會穿過整顆頭打到另一邊的頭髮，
        # 量到的是別人的頭髮，數字會變成假的滿分
        skin = origin + direction * (skull_radius + 0.002)
        covered = shell.ray_cast(skin, direction)[0] is not None
        # Blender 的座標裡 -Y 是角色面向的方向，所以 +Y 那一側是後腦杓
        is_back = direction.y > 0.3
        total += 1
        back_total += 1 if is_back else 0
        if not covered:
            bare += 1
            back_bare += 1 if is_back else 0
    return {"bare": bare / total if total else 1.0,
            "back_bare": back_bare / back_total if back_total else 1.0,
            "reference": reference}


# 十四具身體，七個職業乘男女
BODY_NAMES = ["body_%s_%s" % (gender, job)
              for gender in ("male", "female")
              for job in ("novice", "swordman", "mage", "archer", "hunter",
                          "elementalist", "hero")]
# 五頂髮型，男二女三。第二個名字是拿哪一具身體量身高，同性別的身體高度一樣
HAIR_NAMES = [("hair_male_0", "body_male_novice"),
              ("hair_male_1", "body_male_novice"),
              ("hair_female_0", "body_female_novice"),
              ("hair_female_1", "body_female_novice"),
              ("hair_female_2", "body_female_novice")]


def export(source_name, out_name=None):
    body, armature, report = build(source_name)
    if report["bound"] == 0:
        raise RuntimeError("綁定失敗：沒有任何頂點的權重大於 %.1f" % WEIGHT_FLOOR)
    report["arm_stray"] = arm_stray_ratio(body)
    rig_humanoid.set_action(armature, "Idle")
    bpy.context.view_layer.update()
    path = os.path.join(OUT_ROOT, (out_name or source_name) + ".glb")
    os.makedirs(OUT_ROOT, exist_ok=True)
    with blenv.ui():
        blenv.select_only([armature, body])
        bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True,
                                  export_animations=True, export_apply=False,
                                  export_yup=True, export_skins=True)
    return path, report


# 手臂區被綁到脖子和頭上的頂點比例，超過這個就是手臂會被撕成薄板。
# 修之前實測男英雄 29 個百分比、女法師 52 個百分比，修好之後應該是零
ARM_STRAY_CEILING = 0.02
STRAY_BONES = ("Neck", "Head", "Spine2")


def arm_stray_ratio(obj):
    """手臂區有幾成的頂點綁在脖子和頭上，用來擋「手臂像兩塊板子」那種壞法"""
    regions = obj.get("regions")
    if not regions:
        return 0.0
    names = {group.index: group.name for group in obj.vertex_groups}
    arm_values = set(ARM.values())
    total = 0
    stray = 0
    for index, vertex in enumerate(obj.data.vertices):
        if regions[index] not in arm_values:
            continue
        total += 1
        best_name, best_weight = "", 0.0
        for element in vertex.groups:
            if element.weight > best_weight:
                best_weight = element.weight
                best_name = names.get(element.group, "")
        if best_name in STRAY_BONES:
            stray += 1
    return stray / total if total else 0.0


def build_all():
    """重跑整套 real：十四具身體加五頂髮型，每一項都當場驗一次

    用法：blender -b --factory-startup --python-exit-code 1 \
              -P art_pipeline/characters_v3/rehome_meshy.py -- [bodies|hair]
    驗不過就丟例外，不要讓壞掉的模型安靜地覆蓋掉好的
    """
    what = "all"
    if "--" in sys.argv:
        rest = sys.argv[sys.argv.index("--") + 1:]
        if rest:
            what = rest[0]
    if what in ("all", "bodies"):
        for name in BODY_NAMES:
            path, report = export(name)
            stray = report["arm_stray"]
            if stray > ARM_STRAY_CEILING:
                raise RuntimeError("%s 手臂區有 %.0f 個百分比的頂點綁在脖子和頭上，會扁成薄板"
                                   % (name, stray * 100))
            # 正規化之後這一具還離標準多遠。不擋，只報，讓人知道哪一具最勉強
            far = ["%s 差 %+.3f" % (key, value) for key, value in
                   sorted(report["fit_off"].items()) if abs(value) > FIT_WARN]
            print("[real] %s 綁到 %d / %d 個頂點，面 %d，手臂綁歪 %.1f 個百分比，"
                  "頭身比 %.2f → %.2f%s"
                  % (name, report["bound"], report["vertices"], report["triangles"],
                     stray * 100, report["head_ratio"][0], report["head_ratio"][1],
                     ("，離標準 " + "、".join(far)) if far else ""))
    if what in ("all", "hair"):
        for name, body_name in HAIR_NAMES:
            path, report = export_hair(name, body_name)
            if report["back_bare"] > BACK_BARE_CEILING:
                raise RuntimeError("%s 後腦杓有 %.0f 個百分比露出頭皮，從背後看是光頭"
                                   % (name, report["back_bare"] * 100))
            if report["bare"] > BARE_CEILING:
                raise RuntimeError("%s 整顆頭有 %.0f 個百分比露出頭皮"
                                   % (name, report["bare"] * 100))
            if report["face"] > FACE_OCCLUSION_CEILING:
                raise RuntimeError("%s 五官有 %.0f 個百分比被頭髮蓋住，臉看不到"
                                   % (name, report["face"] * 100))
            print("[real] %s 縮放 %.3f，推出 %d 點，挖掉 %d 面，"
                  "露頭皮 %.0f 背面 %.0f 蓋住五官 %.0f 個百分比"
                  % (name, report["seat"], report["wrapped"], report["carved"],
                     report["bare"] * 100, report["back_bare"] * 100, report["face"] * 100))
    print("[real] done")


if __name__ == "__main__":
    build_all()
