"""把 KayKit 骨架改造成 humanoid.py 那副標準骨架，動作一起改名沿用

做法分四步：
1. 匯入 KayKit 骨架和那批動作
2. 依 humanoid.KAYKIT_RENAME 改骨頭名，同時把每個動作的軌道路徑改成新名字。
   軌道路徑裡的骨頭名字改對了，動作就完全不用重做
3. 刪掉 KayKit 那批控制骨，補上脊椎、脖子、鎖骨、手指、腳尖和裝備掛點
4. 把每根骨頭搬到 proportions.py 的 Q 版位置

為什麼改名不會弄壞動作：動作裡會變形的骨頭只有旋轉和縮放軌，
那兩種是無單位的，骨頭的方向和 roll 不變就會擺出同一個姿勢。
真的有位移軌的只有 root、hips 和四根大骨，位移量照身高比例縮一次就好。
"""

import bpy
from mathutils import Vector

import blenv
import humanoid
import proportions
import rig as kaykit

TEMPLATE_NAME = "Humanoid_template"


def _rename_actions(mapping):
    """把所有動作的軌道路徑裡的骨頭名字換掉"""
    for action in bpy.data.actions:
        for curve in kaykit.fcurves(action):
            path = curve.data_path
            if '"' not in path:
                continue
            parts = path.split('"')
            if parts[1] in mapping:
                parts[1] = mapping[parts[1]]
                curve.data_path = '"'.join(parts)


def _drop_control_bones(armature):
    blenv.select_only(armature)
    with blenv.ui():
        bpy.ops.object.mode_set(mode="EDIT")
    edit_bones = armature.data.edit_bones
    for bone in list(edit_bones):
        if bone.name.startswith(humanoid.KAYKIT_DROP_PREFIXES):
            edit_bones.remove(bone)
    with blenv.ui():
        bpy.ops.object.mode_set(mode="OBJECT")


def _rename_bones(armature):
    blenv.select_only(armature)
    with blenv.ui():
        bpy.ops.object.mode_set(mode="EDIT")
    edit_bones = armature.data.edit_bones
    for old, new in humanoid.KAYKIT_RENAME.items():
        bone = edit_bones.get(old)
        if bone is not None:
            bone.name = new
    with blenv.ui():
        bpy.ops.object.mode_set(mode="OBJECT")


def _insert_and_add(armature, points):
    """補上中間的傳遞骨、手指、腳尖、掛點和 IK 目標"""
    blenv.select_only(armature)
    with blenv.ui():
        bpy.ops.object.mode_set(mode="EDIT")
    edit_bones = armature.data.edit_bones

    def make(name, parent_name, head, tail):
        bone = edit_bones.get(name)
        if bone is None:
            bone = edit_bones.new(name)
        bone.head = Vector(head)
        bone.tail = Vector(tail)
        bone.use_connect = False
        bone.parent = edit_bones.get(parent_name)
        return bone

    # 插在中間的骨頭：先建好，再把原本的孩子改認它當父親
    for name, parent_name, child_name in humanoid.INSERTED:
        child = edit_bones.get(child_name)
        head = Vector(points[name])
        tail = Vector(points[child_name]) if child_name in points else head + Vector((0, 0, 0.04))
        if (tail - head).length < 1e-4:
            tail = head + Vector((0, 0, 0.04))
        bone = make(name, parent_name, head, tail)
        if child is not None:
            child.parent = bone

    for name, parent_name in humanoid.EXTRA_BONES:
        head = Vector(points[name])
        make(name, parent_name, head, head + Vector((0.0, -0.03, 0.0)))

    # 手指：每根三節接成一串，最後一節往外指
    for side, sign in (("Left", 1), ("Right", -1)):
        for finger, _, _ in humanoid.FINGERS:
            parent_name = side + "Hand"
            for joint in range(1, humanoid.FINGER_JOINTS + 1):
                name = "%sHand%s%d" % (side, finger, joint)
                head = Vector(points[name])
                next_name = "%sHand%s%d" % (side, finger, joint + 1)
                tail = (Vector(points[next_name]) if next_name in points
                        else head + Vector((0.016 * sign, 0.0, 0.0)))
                make(name, parent_name, head, tail)
                parent_name = name

    for name, parent_name in humanoid.SOCKET_PARENTS.items():
        head = Vector(points[name])
        make(name, parent_name, head, head + Vector((0.0, -0.06, 0.0)))

    for name in humanoid.IK_TARGETS:
        head = Vector(points[name])
        make(name, "Root", head, head + Vector((0.0, -0.05, 0.0)))

    with blenv.ui():
        bpy.ops.object.mode_set(mode="OBJECT")


def _reshape(armature, points):
    """把每根骨頭搬到 Q 版位置，方向和 roll 保持原樣

    和 rig.py 的 reshape 同一套做法，差別只在骨頭名稱和關節表換成了 humanoid 這一份。
    """
    blenv.select_only(armature)
    with blenv.ui():
        bpy.ops.object.mode_set(mode="EDIT")
    edit_bones = armature.data.edit_bones
    original = {}
    for bone in edit_bones:
        direction = bone.tail - bone.head
        length = direction.length
        original[bone.name] = (direction.normalized() if length > 1e-6 else Vector((0, 0, 1)),
                               length, bone.roll, bone.head.copy())
    for bone in edit_bones:
        bone.use_connect = False
    scale = proportions.HEIGHT / kaykit.KAYKIT_HEIGHT
    for bone in edit_bones:
        direction, length, roll, old_head = original[bone.name]
        if bone.name in points:
            head = Vector(points[bone.name])
            preferred = humanoid.CHAIN.get(bone.name)
            children = [c.name for c in bone.children if c.name in points]
            if preferred in points:
                children = [preferred]
            if children:
                child = Vector(points[children[0]])
                new_length = max((child - head).length, 0.02)
            else:
                new_length = max(length * scale, 0.02)
        else:
            head = old_head * scale
            new_length = max(length * scale, 0.02)
        bone.head = head
        bone.tail = head + direction * new_length
        bone.roll = roll
    with blenv.ui():
        bpy.ops.object.mode_set(mode="OBJECT")


def import_template():
    """匯入並改造一次，之後重複呼叫直接回傳同一副

    動作資料是全場景共用的，改名只能做一次，所以這裡一定要擋住重複執行。
    """
    existing = bpy.data.objects.get(TEMPLATE_NAME)
    if existing is not None:
        return existing
    source = kaykit.import_source()
    source.hide_set(False)
    source.name = TEMPLATE_NAME
    source.data.name = TEMPLATE_NAME
    source.rotation_mode = "XYZ"
    source.rotation_euler = (0, 0, 0)
    _drop_control_bones(source)
    _rename_bones(source)
    _rename_actions(humanoid.KAYKIT_RENAME)
    kaykit.LOCATION_SCALED_BONES.clear()
    kaykit.LOCATION_SCALED_BONES.update(
        {"Root", "Hips", "LeftArm", "RightArm", "LeftUpLeg", "RightUpLeg"})
    return source


def build(gender="neutral", body=None):
    """做出一副標準人形骨架，既有動作可以直接播

    body 不給就用 proportions.BODIES 那副 4.07 頭身的標準比例；
    給的話照那個 Body 的比例排骨頭，characters 用它做定裝圖那種 2.8 頭身的骨架
    """
    body = body or proportions.BODIES[gender]
    points = humanoid.joints(body)
    template = import_template()
    armature = template.copy()
    armature.data = template.data.copy()
    armature.animation_data_clear()
    blenv.link(armature)
    armature.hide_set(False)
    armature.name = "Rig_humanoid"
    armature.data.name = "Rig_humanoid"
    armature.rotation_mode = "XYZ"
    armature.rotation_euler = (0, 0, 0)
    _insert_and_add(armature, points)
    _reshape(armature, points)
    armature.show_in_front = True
    armature.data.display_type = "OCTAHEDRAL"
    return armature


def set_action(armature, name):
    return kaykit.set_action(armature, name)


def rest_pose(armature):
    return kaykit.rest_pose(armature)
