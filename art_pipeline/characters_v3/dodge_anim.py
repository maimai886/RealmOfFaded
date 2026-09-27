"""四個方向的閃避翻滾，直接做在標準骨架上

第二版。第一版被使用者評為「翻滾動作很鳥」，把分鏡拉出來看，問題很具體：

1. 轉軸在髖部，可是這個角色的重量幾乎全在那顆大頭上，
   所以整個人是繞著一個不在自己身上的點甩，看起來像被丟出去不是在滾
2. 身體從頭到尾是硬的。腿有彎但軀幹沒捲、頭沒低下來，剪影一直是一個站姿的人在旋轉，
   從來沒有變成一個輪子
3. 手臂還張在 T 姿勢的高度，只往前收沒有放下來，所以一路在外面揮
4. 轉速幾乎是等速，沒有「起步慢、中段快、落地慢」
5. 最後是直接彈回站姿，沒有腳踩地再站起來

這一版的做法：

- **轉軸跟著縮起來的身體走**。每一格先把姿勢擺好，量出這個姿勢的重心，
  繞那個重心轉，人才是在原地滾而不是繞著別的點甩
- **翻滾中段重心離地的高度等於縮起來那團的半徑**，所以那團剛好貼著地面滾
- 每一格是一個獨立的姿勢，不是同一個姿勢乘一個係數。
  預備、縮身、翻滾、踩地、起身各有自己的樣子
- 轉角是手寫的表，起步兩格只轉 18 度、中段三格轉 238 度、最後三格收尾

位移：整段結束時 Root 回到原點。2.4 公尺的位移是伺服器算的、客戶端再預測一次，
動作裡再帶位移就會變成走兩倍。

時間：戰鬥端的閃避窗是 travel 300 毫秒加 recovery 120 毫秒，合計 420 毫秒。
24 格每秒之下 10 格是 0.4167 秒，播放速度就是 1。踩地那一格落在第 8 格也就是八成，
剛好是 travel 結束、recovery 開始的位置。

座標：Blender 裡 -Y 是角色面向的方向、+Z 是上。
繞 +X 轉正角度會把頭往 -Y 帶，那就是往前滾；繞 +Y 轉正角度會往 +X 也就是角色的左邊滾。

骨頭的轉軸是量出來的，不是猜的：
脊椎和頭繞自己的 +X 是往前捲；大腿繞 -X 是膝蓋往前抬；小腿繞 +X 是腳跟往後收；
上臂繞 -X 是往下放，左臂繞 -Z、右臂繞 +Z 是往身體前面收。
"""

import math

import bpy
from mathutils import Matrix, Quaternion, Vector

import proportions

FPS = 24
FRAMES = 10
NAMES = {
    "Dodge_Forward": ("X", 1.0),
    "Dodge_Backward": ("X", -1.0),
    "Dodge_Left": ("Y", 1.0),
    "Dodge_Right": ("Y", -1.0),
}

# 五種姿勢。每一項是 骨頭 -> [(軸, 角度)]，角度是度
STAND = {}

# 預備：重心往下沉，膝蓋彎、上身微前傾、手臂放下來
CROUCH = {
    "Spine": [("X", 14.0)], "Spine1": [("X", 10.0)], "Spine2": [("X", 8.0)],
    "Neck": [("X", 6.0)], "Head": [("X", 4.0)],
    "LeftUpLeg": [("X", -34.0)], "RightUpLeg": [("X", -34.0)],
    "LeftLeg": [("X", 52.0)], "RightLeg": [("X", 52.0)],
    "LeftFoot": [("X", -18.0)], "RightFoot": [("X", -18.0)],
    "LeftArm": [("X", -58.0), ("Z", -26.0)], "RightArm": [("X", -58.0), ("Z", 26.0)],
    "LeftForeArm": [("Z", -38.0)], "RightForeArm": [("Z", 38.0)],
}

# 縮身：整個人捲成一團，但**不能捲到消失**。
# 第二版捲太死，膝蓋和手肘全部縮進頭的輪廓裡，遊戲鏡頭上有一半的格子是一顆光禿禿的灰球，
# 看不出是人在翻。膝蓋和小臂要留在頭的輪廓外面當成輪子上的凸起，
# 眼睛靠那兩個凸起才看得出這團東西正在轉
TUCK = {
    # 骨盆跟著捲，但捲得比第二版少，下半身才不會整個躲進頭底下
    "Hips": [("X", 18.0)],
    "Spine": [("X", 30.0)], "Spine1": [("X", 26.0)], "Spine2": [("X", 22.0)],
    "Neck": [("X", 16.0)], "Head": [("X", 14.0)],
    "LeftUpLeg": [("X", -104.0), ("Z", 10.0)], "RightUpLeg": [("X", -104.0), ("Z", -10.0)],
    "LeftLeg": [("X", 112.0)], "RightLeg": [("X", 112.0)],
    "LeftFoot": [("X", 30.0)], "RightFoot": [("X", 30.0)],
    "LeftArm": [("X", -70.0), ("Z", -44.0)], "RightArm": [("X", -70.0), ("Z", 44.0)],
    "LeftForeArm": [("Z", -82.0)], "RightForeArm": [("Z", 82.0)],
    # 手指抓著小腿。連指手套看不出來，但骨頭有在動，換成有手指的身體就看得到
    "LeftHandIndex1": [("X", -40.0)], "RightHandIndex1": [("X", -40.0)],
    "LeftHandMiddle1": [("X", -40.0)], "RightHandMiddle1": [("X", -40.0)],
    "LeftHandThumb1": [("X", -30.0)], "RightHandThumb1": [("X", -30.0)],
}

# 伸腳：腳先出去，身體還在轉。踩地之前要先看到腳伸出來，落地才不是憑空站起來
REACH = {
    "Hips": [("X", 10.0)],
    "Spine": [("X", 26.0)], "Spine1": [("X", 21.0)], "Spine2": [("X", 18.0)],
    "Neck": [("X", 13.0)], "Head": [("X", 10.0)],
    "LeftUpLeg": [("X", -86.0)], "LeftLeg": [("X", 70.0)], "LeftFoot": [("X", -6.0)],
    "RightUpLeg": [("X", -100.0)], "RightLeg": [("X", 104.0)], "RightFoot": [("X", 26.0)],
    # 手張開保持平衡。落地前後從遊戲鏡頭看只剩一顆球在轉，
    # 手甩出去才有東西突出輪廓，看得出這個人正在收勢
    "LeftArm": [("X", -30.0), ("Z", 26.0)], "RightArm": [("X", -34.0), ("Z", -20.0)],
    "LeftForeArm": [("Z", -24.0)], "RightForeArm": [("Z", 30.0)],
}

# 踩地：一腳往前伸出去踩住，另一腳還收著，上身還是捲的
PLANT = {
    "Spine": [("X", 30.0)], "Spine1": [("X", 24.0)], "Spine2": [("X", 20.0)],
    "Neck": [("X", 14.0)], "Head": [("X", 10.0)],
    # 前腳伸出去踩地
    "LeftUpLeg": [("X", -74.0)], "LeftLeg": [("X", 44.0)], "LeftFoot": [("X", -26.0)],
    # 後腳還收在身體底下
    "RightUpLeg": [("X", -96.0)], "RightLeg": [("X", 116.0)], "RightFoot": [("X", 20.0)],
    # 一手往外撐住地面，一手還收著，剪影上兩邊不一樣才看得出是在收勢不是站著
    "LeftArm": [("X", -18.0), ("Z", 40.0)], "RightArm": [("X", -52.0), ("Z", 34.0)],
    "LeftForeArm": [("Z", -10.0)], "RightForeArm": [("Z", 64.0)],
}

# 起身：膝蓋還彎著、上身還沒完全直起來，下一格才回到站姿
RISE = {
    "Spine": [("X", 15.0)], "Spine1": [("X", 11.0)], "Spine2": [("X", 9.0)],
    "Neck": [("X", 6.0)], "Head": [("X", 4.0)],
    "LeftUpLeg": [("X", -26.0)], "RightUpLeg": [("X", -32.0)],
    "LeftLeg": [("X", 36.0)], "RightLeg": [("X", 46.0)],
    "LeftFoot": [("X", -12.0)], "RightFoot": [("X", -8.0)],
    "LeftArm": [("X", -34.0), ("Z", -20.0)], "RightArm": [("X", -38.0), ("Z", 24.0)],
    "LeftForeArm": [("Z", -26.0)], "RightForeArm": [("Z", 30.0)],
}


def _blend(pose_a, pose_b, t):
    """兩個姿勢之間的中間值，用來做過場的那幾格"""
    out = {}
    for name in set(pose_a) | set(pose_b):
        entries = {}
        for axis, degrees in pose_a.get(name, []):
            entries[axis] = entries.get(axis, 0.0) + degrees * (1.0 - t)
        for axis, degrees in pose_b.get(name, []):
            entries[axis] = entries.get(axis, 0.0) + degrees * t
        out[name] = [(axis, value) for axis, value in entries.items()]
    return out


def _keys():
    """關鍵影格：(格, 轉了幾度, 姿勢, 貼地程度)

    轉角是手寫的。起步兩格只走 18 度、中段三格走 238 度、收尾三格慢慢停，
    這就是「起步慢、中段快、落地慢」。

    貼地程度 0 是站著的高度、1 是縮成一團貼著地面滾。
    這一欄要手寫不能用公式算：起身那三格要一格一格爬起來，
    用對稱的公式算出來會變成前面沉得慢、後面一格彈起來，那就是使用者說的「彈回站姿」。
    """
    launch = _blend(CROUCH, TUCK, 0.55)
    opening = _blend(TUCK, REACH, 0.55)
    settle = _blend(PLANT, RISE, 0.5)
    almost = _blend(RISE, STAND, 0.55)
    # 只有三格停在最大縮身，其餘的格子分給預備和起身，
    # 因為看得懂的資訊都在那兩段：蹲下去代表要出招，站起來代表結束
    return [
        (0, 0.0, STAND, 0.00),
        (1, 6.0, CROUCH, 0.20),
        (2, 22.0, launch, 0.62),
        (3, 72.0, TUCK, 0.96),
        (4, 168.0, TUCK, 1.00),
        (5, 252.0, TUCK, 1.00),
        (6, 306.0, opening, 0.94),
        (7, 336.0, REACH, 0.80),
        (8, 354.0, PLANT, 0.50),
        (9, 360.0, settle, 0.20),
        (10, 360.0, almost, 0.04),
    ]


# 量不到縮起來那團的半徑時用這個當退路
FALLBACK_RADIUS = 0.55

AXES = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}

# 量重心用的取樣點：骨頭名稱對到權重。大頭佔的份量最重，所以 Head 給得很高
SAMPLE_WEIGHTS = {
    "Head": 6.0, "Neck": 0.5, "Spine2": 1.2, "Spine1": 0.8, "Spine": 0.8, "Hips": 1.0,
    "LeftUpLeg": 0.5, "RightUpLeg": 0.5, "LeftLeg": 0.4, "RightLeg": 0.4,
    "LeftFoot": 0.35, "RightFoot": 0.35, "LeftHand": 0.2, "RightHand": 0.2,
}
# 頭的球心在 Head 骨頭起點往骨頭方向多少公尺。Head 起點在脖子，球心在它上面
HEAD_BALL_OFFSET = proportions.HEAD_CENTER_Z - proportions.NECK_Z


def _clear(armature):
    for bone in armature.pose.bones:
        bone.rotation_mode = "QUATERNION"
        bone.location = (0.0, 0.0, 0.0)
        bone.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        bone.scale = (1.0, 1.0, 1.0)


def _apply_pose(armature, pose):
    """把一個姿勢套到骨架上。角度是繞骨頭自己的軸轉，所以和骨頭長度無關"""
    _clear(armature)
    for name, entries in pose.items():
        bone = armature.pose.bones.get(name)
        if bone is None:
            continue
        rotation = Quaternion((1.0, 0.0, 0.0, 0.0))
        for axis, degrees in entries:
            rotation = rotation @ Quaternion(AXES[axis], math.radians(degrees))
        bone.rotation_quaternion = rotation
    bpy.context.view_layer.update()


def _centre_and_radius(armature):
    """目前姿勢的重心，和重心到最遠取樣點的距離

    半徑再加上一段頭的半徑，因為頭是一顆實心的球，球心到球面還有距離。
    """
    points = []
    for name, weight in SAMPLE_WEIGHTS.items():
        bone = armature.pose.bones.get(name)
        if bone is None:
            continue
        position = bone.head.copy()
        if name == "Head":
            # 頭是一顆球，重心在球心不在骨頭起點，所以沿著骨頭方向再推出去
            direction = bone.tail - bone.head
            if direction.length > 1e-6:
                position = position + direction.normalized() * HEAD_BALL_OFFSET
        points.append((position, weight))
    if not points:
        return Vector((0.0, 0.0, FALLBACK_RADIUS)), FALLBACK_RADIUS
    total = sum(weight for _, weight in points)
    centre = Vector((0.0, 0.0, 0.0))
    for position, weight in points:
        centre = centre + position * weight
    centre = centre / max(total, 1e-6)
    radius = max((position - centre).length for position, _ in points)
    return centre, radius + proportions.HEAD_RADIUS * 0.55


def _place_root(armature, axis, angle, centre, ground_height):
    """繞著 centre 轉 angle，再整個人上下搬，讓 centre 落在離地 ground_height

    轉軸和搬移都寫進 Root 的矩陣。pose 骨頭的 location 是骨頭自己的座標系，
    Root 轉過去之後那個方向早就不是上下了，所以不能事後改 location。
    """
    root = armature.pose.bones["Root"]
    rest = armature.data.bones["Root"].matrix_local
    rotation = Matrix.Rotation(angle, 4, axis)
    lift = Vector((0.0, 0.0, ground_height - centre.z))
    root.matrix = (Matrix.Translation(lift)
                   @ Matrix.Translation(centre) @ rotation @ Matrix.Translation(-centre) @ rest)


def _build_action(armature, name, axis, direction):
    action = bpy.data.actions.get(name)
    if action is not None:
        bpy.data.actions.remove(action)
    if armature.animation_data is None:
        armature.animation_data_create()
    action = bpy.data.actions.new(name)
    armature.animation_data.action = action
    slots = getattr(action, "slots", None)
    if slots is not None:
        try:
            armature.animation_data.action_slot = action.slots.new(id_type="OBJECT",
                                                                   name=armature.name)
        except Exception:
            if action.slots:
                armature.animation_data.action_slot = action.slots[0]

    # 先量一次縮起來那一團的半徑，翻滾中段就用它當離地高度
    _apply_pose(armature, TUCK)
    _, tuck_radius = _centre_and_radius(armature)

    scene = bpy.context.scene
    for frame, degrees, pose, lift in _keys():
        scene.frame_set(frame)
        _apply_pose(armature, pose)
        centre, _ = _centre_and_radius(armature)
        # 貼地程度 0 就是這個姿勢本來的重心高度，1 就是縮成一團貼著地面滾
        ground_height = centre.z + (tuck_radius - centre.z) * lift
        _place_root(armature, axis, math.radians(degrees) * direction, centre, ground_height)
        bpy.context.view_layer.update()
        for bone in armature.pose.bones:
            bone.keyframe_insert("rotation_quaternion", frame=frame)
            bone.keyframe_insert("location", frame=frame)
    action.frame_start = 0
    action.frame_end = FRAMES
    armature.animation_data.action = None
    return action


def build_all(armature):
    """做出四個方向的翻滾，回傳動作名稱清單"""
    made = []
    for name, (axis, direction) in NAMES.items():
        _build_action(armature, name, axis, direction)
        made.append(name)
    _clear(armature)
    bpy.context.scene.frame_set(0)
    return made
