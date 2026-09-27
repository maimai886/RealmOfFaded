"""把 KayKit 骨架改成 Q 版比例，動畫直接沿用

為什麼可以直接沿用：檢查過 KayKit 那 76 個動作，會變形的骨頭裡只有 root、hips、
upperarm、upperleg 有位移軌，其餘全是旋轉和縮放軌。旋轉和縮放是無單位的，
只要每根骨頭的方向向量和 roll 不變，換成任何長度的骨架都會擺出同一個姿勢。
所以做法是：保留骨頭名稱、階層、方向、roll，只改每根骨頭的起點和長度，
位移軌再依整體身高比例縮一下就好，不需要真正的動作重定向。
"""

import os

import bpy
from mathutils import Vector

import blenv
import proportions

KAYKIT = os.path.join(blenv.PROJECT_ROOT, "assets/vendor/kaykit/characters/Knight.glb")
# KayKit 原始身高，量自骨架頂端
KAYKIT_HEIGHT = 1.492

# 精靈圖只用得到這幾個動作，其他的刪掉讓 Blender 跑快一點
KEEP_ACTIONS = {
    "Idle", "Walking_A", "Running_A",
    "1H_Melee_Attack_Stab", "1H_Melee_Attack_Slice_Diagonal", "2H_Melee_Attack_Chop",
    "Spellcast_Shoot", "Spellcasting", "2H_Ranged_Shoot", "2H_Ranged_Aiming",
    "Hit_A", "Death_A", "Sit_Floor_Idle", "PickUp", "T-Pose", "Unarmed_Idle",
    "Unarmed_Melee_Attack_Punch_A", "2H_Ranged_Aiming", "Interact",
    # 閃避翻滾四個方向，操作規格在 docs/打擊感規格.md
    # 這幾個是後來才加的，已經產好的模型檔裡沒有，客戶端會在載入時從 KayKit 範本借，
    # 見 src/world/actors/anim_library.gd；重產過之後就直接烤在模型裡，那段借用會自動跳過
    "Dodge_Forward", "Dodge_Backward", "Dodge_Left", "Dodge_Right",
}

# 有位移軌而且真的會影響外觀的骨頭，位移量要跟著身高縮放
LOCATION_SCALED_BONES = {"root", "hips", "upperarm.l", "upperarm.r", "upperleg.l", "upperleg.r"}


def fcurves(action):
    """Blender 5 的動作分層存放，把所有 fcurve 攤平出來"""
    out = []
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                out.extend(bag.fcurves)
    return out


TEMPLATE_NAME = "Rig_template"


def import_source():
    """匯入 KayKit 骨架當範本，丟掉它的網格，只留骨架和要用的動作

    一個場景只匯入一次，之後每個性別都從這個範本複製，動作資料共用，
    重複匯入會讓動作被改名成 Idle.001 之類的而對不上。
    """
    existing = bpy.data.objects.get(TEMPLATE_NAME)
    if existing is not None:
        return existing
    before = set(bpy.context.scene.objects)
    with blenv.ui():
        bpy.ops.import_scene.gltf(filepath=KAYKIT)
    imported = [o for o in bpy.context.scene.objects if o not in before]
    armature = next(o for o in imported if o.type == "ARMATURE")
    for obj in imported:
        if obj is not armature:
            bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in list(bpy.data.meshes):
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    for action in list(bpy.data.actions):
        if action.name not in KEEP_ACTIONS:
            bpy.data.actions.remove(action)
    armature.name = TEMPLATE_NAME
    armature.data.name = TEMPLATE_NAME
    armature.rotation_euler = (0, 0, 0)
    armature.scale = (1, 1, 1)
    armature.location = (0, 0, 0)
    # 位移軌只縮放一次，動作是所有性別共用的
    scale_locations(proportions.HEIGHT / KAYKIT_HEIGHT)
    armature.hide_set(True)
    return armature


def reshape(armature, body):
    """把每根骨頭搬到 Q 版比例的位置，方向和 roll 保持原樣"""
    joints = body.joints()
    blenv.select_only(armature)
    with blenv.ui():
        bpy.ops.object.mode_set(mode="EDIT")
    edit_bones = armature.data.edit_bones

    # 先記下原本的方向、長度和 roll，等一下逐根套用
    original = {}
    for bone in edit_bones:
        direction = (bone.tail - bone.head)
        length = direction.length
        original[bone.name] = (direction.normalized() if length > 1e-6 else Vector((0, 0, 1)),
                               length, bone.roll, bone.head.copy())

    # 連接狀態會鎖住起點，先全部斷開，階層和動畫都不受影響
    for bone in edit_bones:
        bone.use_connect = False

    scale = proportions.HEIGHT / KAYKIT_HEIGHT
    for bone in edit_bones:
        direction, length, roll, old_head = original[bone.name]
        if bone.name in joints:
            head = Vector(joints[bone.name])
            child_names = [c.name for c in bone.children if c.name in joints]
            if child_names:
                # 有子關節的骨頭，長度直接等於到子關節的距離，關節才會接得起來
                child = Vector(joints[child_names[0]])
                new_length = max((child - head).length, 0.02)
            else:
                new_length = max(length * scale, 0.02)
        else:
            # IK 和控制骨頭不參與變形，等比例縮放就好
            head = old_head * scale
            new_length = max(length * scale, 0.02)
        bone.head = head
        bone.tail = head + direction * new_length
        bone.roll = roll

    with blenv.ui():
        bpy.ops.object.mode_set(mode="OBJECT")
    return armature


def scale_locations(scale):
    """位移軌依身高比例縮放，只動真的會影響外觀的那幾根骨頭"""
    for action in bpy.data.actions:
        for curve in fcurves(action):
            path = curve.data_path
            if not path.endswith("location") or '"' not in path:
                continue
            if path.split('"')[1] not in LOCATION_SCALED_BONES:
                continue
            for key in curve.keyframe_points:
                key.co[1] *= scale
                key.handle_left[1] *= scale
                key.handle_right[1] *= scale
            curve.update()


# 裝備掛點的父骨頭，名稱和位置在 proportions.py，這裡只說掛在誰身上
SOCKET_PARENTS = {"hand_r": "hand.r", "hand_l": "hand.l", "back": "chest", "body": "chest"}


def add_sockets(armature, body):
    """加上 docs/角色系統規格.md 規定的四根裝備掛點骨頭

    武器、披風、身體外觀都掛在這幾根上，資料只認這幾個名字，
    所以之後換骨架也要有同名的骨頭，裝備資料才不用跟著改。
    頭飾掛在本來就有的 head 上，不另外加。
    """
    joints = body.joints()
    blenv.select_only(armature)
    with blenv.ui():
        bpy.ops.object.mode_set(mode="EDIT")
    edit_bones = armature.data.edit_bones
    for name, parent_name in SOCKET_PARENTS.items():
        if name in edit_bones:
            continue
        bone = edit_bones.new(name)
        head = Vector(joints[name])
        bone.head = head
        bone.tail = head + Vector((0.0, -0.06, 0.0))
        bone.use_connect = False
        bone.parent = edit_bones.get(parent_name)
    with blenv.ui():
        bpy.ops.object.mode_set(mode="OBJECT")
    return armature


def build(gender):
    """做出一副指定性別的 Q 版骨架，動作已經可以直接播"""
    body = proportions.BODIES[gender]
    template = import_source()
    armature = template.copy()
    armature.data = template.data.copy()
    armature.animation_data_clear()
    blenv.link(armature)
    armature.hide_set(False)
    armature.name = "Rig_" + gender
    armature.data.name = "Rig_" + gender
    # glTF 匯進來的物件是四元數旋轉模式，那時候設 rotation_euler 完全不會生效，
    # 算精靈圖要靠轉整個物件換方向，所以一定要改成尤拉角
    armature.rotation_mode = "XYZ"
    armature.rotation_euler = (0, 0, 0)
    reshape(armature, body)
    add_sockets(armature, body)
    armature.show_in_front = True
    armature.data.display_type = "OCTAHEDRAL"
    return armature


def set_action(armature, name):
    action = bpy.data.actions.get(name)
    if action is None:
        return None
    if armature.animation_data is None:
        armature.animation_data_create()
    armature.animation_data.action = action
    slots = getattr(action, "slots", None)
    if slots:
        armature.animation_data.action_slot = slots[0]
    return action


def rest_pose(armature):
    """回到綁定姿勢，建模時要在這個姿勢下做"""
    if armature.animation_data:
        armature.animation_data.action = None
    for bone in armature.pose.bones:
        bone.location = (0, 0, 0)
        bone.rotation_quaternion = (1, 0, 0, 0)
        bone.scale = (1, 1, 1)
