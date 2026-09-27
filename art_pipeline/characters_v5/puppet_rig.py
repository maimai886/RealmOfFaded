# -*- coding: utf-8 -*-
"""紙偶動畫的骨架資料：把標準骨架每一格的每根骨頭投影到畫格上，寫成 rig.json 給 puppet_sheet.py 用。在 Blender 裡跑。

紙偶的做法：使用者畫的視圖切成零件（頭、軀幹、上臂、前臂、大腿、小腿），零件跟著骨架的 2D 投影走。
這裡只負責骨架：相機和 cbuild 同一顆（30 度俯角、正交），所以零件的位置和引擎的畫格、錨點、掛點全部一致。

輸出 rig.json：
  frame_size、anchor、directions
  reference[方向]：切零件用的骨架，站直、手臂垂下，和使用者的視圖一樣；每個零件 [起點x, 起點y, 終點x, 終點y, 深度]，
                  畫格像素，加 head_circle [x, y, 半徑] 和 bbox [x0, y0, x1, y1] 人偶剪影的外框
  rest[方向]：Idle 第 0 格的骨架。零件的動作是「相對 rest 的變化」，所以 Idle 第 0 格就是使用者的圖原封不動，
              骨架本身手臂微張的偏差不會跑進圖裡
  actions[動作][方向] = 每一格一份同樣的零件表

用法：
  blender -b --factory-startup --python-exit-code 1 -P art_pipeline/characters_v5/puppet_rig.py -- <輸出資料夾> [--job novice] [--gender male] [--directions s,sw,w,nw,n] [--actions idle,walk,...]
"""

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cbuild  # noqa: E402
import chibi_body  # noqa: E402

import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import mimg  # noqa: E402

# 零件：名稱、起點骨頭、終點骨頭、終點取骨頭的尾端還是起點。骨頭名稱是 KayKit 那套
PARTS = [
    ("torso", "Hips", "Neck", "head"),
    ("pelvis", "Hips", "Hips", "head"),
    ("upper_arm_l", "LeftArm", "LeftForeArm", "head"),
    ("forearm_l", "LeftForeArm", "LeftHand", "tail"),
    ("upper_arm_r", "RightArm", "RightForeArm", "head"),
    ("forearm_r", "RightForeArm", "RightHand", "tail"),
    ("thigh_l", "LeftUpLeg", "LeftLeg", "head"),
    ("shin_l", "LeftLeg", "LeftFoot", "head"),
    ("foot_l", "LeftFoot", "LeftFoot", "tail"),
    ("thigh_r", "RightUpLeg", "RightLeg", "head"),
    ("shin_r", "RightLeg", "RightFoot", "head"),
    ("foot_r", "RightFoot", "RightFoot", "tail"),
]
DEFAULT_DIRECTIONS = "s,sw,w,nw,n"
PELVIS_FRACTION = 0.55
# KayKit 的動作套在這副骨架上手臂會往外張約 40 度，肩膀是 T 姿勢的關係；每一格都把上臂往身體收回來這麼多度。
# 攻擊那類動作也一起收，不然出拳的手也會歪到外面
ARM_ADDUCT_DEG = 32.0


# 參考姿勢：使用者的視圖是站直、手臂貼著身體垂下的，骨架的 Idle 是手肘微彎、腳微開，切零件會切歪。
# 每根骨頭指定它在參考姿勢裡的方向（骨架座標，+X 是角色左手邊、+Z 是上），從 Idle 第 0 格出發轉過去
REFERENCE_AIM = [
    ("LeftArm", (0.10, 0.0, -1.0)), ("LeftForeArm", (0.04, 0.0, -1.0)),
    ("RightArm", (-0.10, 0.0, -1.0)), ("RightForeArm", (-0.04, 0.0, -1.0)),
    ("LeftUpLeg", (0.0, 0.0, -1.0)), ("LeftLeg", (0.0, 0.0, -1.0)),
    ("RightUpLeg", (0.0, 0.0, -1.0)), ("RightLeg", (0.0, 0.0, -1.0)),
]


def _aim(armature, name, direction):
    """把一根骨頭在骨架座標裡轉到指定方向，子骨頭跟著轉"""
    pose_bone = armature.pose.bones.get(name)
    if pose_bone is None:
        return
    current = (pose_bone.tail - pose_bone.head).normalized()
    rotation = current.rotation_difference(Vector(direction).normalized()).to_matrix().to_4x4()
    head = pose_bone.head.copy()
    pose_bone.matrix = Matrix.Translation(head) @ rotation @ Matrix.Translation(-head) @ pose_bone.matrix
    bpy.context.view_layer.update()


def _reference_pose(armature):
    for name, direction in REFERENCE_AIM:
        _aim(armature, name, direction)


def _adduct_arms(armature):
    """上臂繞著角色的前後軸往身體收：左臂繞 +Y 軸轉負角度，右臂轉正角度，前臂和手跟著"""
    # 左臂朝 +X，繞 +Y 轉正角度會往 -Z 也就是往下收；右臂相反
    for name, sign in (("LeftArm", 1.0), ("RightArm", -1.0)):
        pose_bone = armature.pose.bones.get(name)
        if pose_bone is None:
            continue
        rotation = Matrix.Rotation(math.radians(ARM_ADDUCT_DEG) * sign, 4, "Y")
        head = pose_bone.head.copy()
        pose_bone.matrix = Matrix.Translation(head) @ rotation @ Matrix.Translation(-head) @ pose_bone.matrix
        bpy.context.view_layer.update()


def _radii(armature):
    """零件的半寬，畫格像素：切零件時軀幹先把自己那一圈吃掉，手臂只拿身體外面的"""
    import proportions
    body = proportions.BODIES["card"]
    ppm = cbuild.PIXELS_PER_METER * armature.matrix_world.to_scale().x
    return {"torso": round(body.shoulder[0] * 0.72 * ppm, 2), "pelvis": round(body.hip[0] * 0.95 * ppm, 2),
            "upper_arm": round(body.arm_radius[0] * ppm, 2),
            "forearm": round(body.hand_radius * ppm, 2), "thigh": round(body.leg_radius[0] * ppm, 2),
            "shin": round(body.leg_radius[1] * ppm, 2), "foot": round(body.leg_radius[1] * 1.1 * ppm, 2)}


# 走路和站立的手臂不用 KayKit 的：那套走路是手肘彎九十度提在身前的慢跑姿，切成紙偶就是一根根棒子飛在身體外面。
# 改成鐘擺：上臂在前後平面裡擺，角度跟同側的腿反向，腿由骨架的動作決定，所以自然同步
LOCOMOTION = ("walk", "idle", "run")
ARM_SWING_RATIO = 0.9
ARM_SWING_MAX = math.radians(35.0)
ARM_OUT = 0.10
FOREARM_BEND = math.radians(15.0)


def _leg_forward_angle(armature, upper, lower):
    a = armature.pose.bones[upper].head
    b = armature.pose.bones[lower].head
    d = (b - a).normalized()
    # 角色面向 -Y：大腿往前踢時 d.y 變負
    return math.atan2(-d.y, -d.z)


def _swing_arms(armature, spec):
    if spec["name"] not in LOCOMOTION:
        return
    for arm, fore, upper, lower, sign in (("LeftArm", "LeftForeArm", "LeftUpLeg", "LeftLeg", 1.0),
                                          ("RightArm", "RightForeArm", "RightUpLeg", "RightLeg", -1.0)):
        if arm not in armature.pose.bones or upper not in armature.pose.bones:
            continue
        swing = -ARM_SWING_RATIO * _leg_forward_angle(armature, upper, lower)
        swing = max(-ARM_SWING_MAX, min(ARM_SWING_MAX, swing))
        _aim(armature, arm, (sign * ARM_OUT, -math.sin(swing), -math.cos(swing)))
        bend = swing + FOREARM_BEND
        _aim(armature, fore, (sign * ARM_OUT * 0.5, -math.sin(bend), -math.cos(bend)))


def _point(armature, bone, end):
    pose_bone = armature.pose.bones[bone]
    return armature.matrix_world @ (pose_bone.head if end == "head" else pose_bone.tail)


def _project(camera, point):
    x, y = cbuild._world_to_pixel(camera, point)
    depth = (camera.matrix_world.inverted() @ point).z
    return x, y, -depth


def _parts_2d(armature, camera):
    out = {}
    for name, start_bone, end_bone, end in PARTS:
        if start_bone not in armature.pose.bones or end_bone not in armature.pose.bones:
            continue
        a = _point(armature, start_bone, "head")
        b = _point(armature, end_bone, end)
        if name == "pelvis":
            # 骨盆段：從髖骨中心往下到兩個膝蓋中點的 55%，短褲蓋到的地方
            knees = (_point(armature, "LeftLeg", "head") + _point(armature, "RightLeg", "head")) / 2.0
            b = a + (knees - a) * PELVIS_FRACTION
        ax, ay, az = _project(camera, a)
        bx, by, bz = _project(camera, b)
        out[name] = [round(ax, 2), round(ay, 2), round(bx, 2), round(by, 2), round((az + bz) / 2, 4)]
    # 頭：從脖子頂往上到頭球中心，再往上到頭頂；零件轉動照這一段
    head = armature.pose.bones["Head"]
    up = (head.tail - head.head).normalized()
    centre_local = head.head + up * (chibi_body.mannequin.HEAD_CENTER_Z - head.head.z)
    centre = armature.matrix_world @ centre_local
    neck_top = armature.matrix_world @ head.head
    ax, ay, az = _project(camera, neck_top)
    cx, cy, cz = _project(camera, centre)
    out["head"] = [round(ax, 2), round(ay, 2), round(cx, 2), round(cy, 2), round(cz, 4)]
    radius_world = chibi_body.mannequin.HEAD_RADIUS * armature.matrix_world.to_scale().x
    edge = armature.matrix_world @ (centre_local + Vector((radius_world / armature.matrix_world.to_scale().x, 0.0, 0.0)))
    ex, ey, _ = _project(camera, edge)
    out["head_circle"] = [round(cx, 2), round(cy, 2), round(math.hypot(ex - cx, ey - cy), 2)]
    return out


def _bbox_of_render(path):
    image = mimg.load_png(path)
    alpha = image[..., 3]
    ys, xs = alpha.nonzero() if hasattr(alpha, "nonzero") else ([], [])
    if len(xs) == 0:
        return None
    s = float(cbuild.SUPERSAMPLE)
    return [round(float(xs.min()) / s, 2), round(float(ys.min()) / s, 2), round(float(xs.max() + 1) / s, 2), round(float(ys.max() + 1) / s, 2)]


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if not argv:
        raise SystemExit(__doc__)
    out_dir = argv[0]
    options = {"--job": "novice", "--gender": "male", "--directions": DEFAULT_DIRECTIONS,
               "--actions": "idle,walk,attack,cast,hit,die,sit,pickup"}
    index = 1
    while index < len(argv):
        if argv[index] in options and index + 1 < len(argv):
            options[argv[index]] = argv[index + 1]
            index += 2
        else:
            raise SystemExit("看不懂的參數 " + argv[index])
    directions = options["--directions"].split(",")
    wanted = options["--actions"].split(",")
    os.makedirs(out_dir, exist_ok=True)

    armature, meshes = chibi_body.build(options["--gender"])
    scene = cbuild._setup_scene()
    cbuild._lights()
    cbuild._toonify(meshes)
    camera = cbuild._camera()
    height = cbuild._rig_height(armature, meshes)
    scale = cbuild.CHARACTER_HEIGHT_M / height if height > 1e-6 else 1.0
    armature.scale = (scale, scale, scale)

    specs = [spec for spec in cbuild._job_actions(options["--job"]) if spec["name"] in wanted]
    idle_spec = next(spec for spec in cbuild._job_actions(options["--job"]) if spec["name"] == "idle")
    idle_action = cbuild._find_action(idle_spec["source"])

    def pose(spec, action, frame, direction):
        t = cbuild._frame_time(spec, frame)
        cbuild._set_action(armature, action)
        cbuild._set_time(action, t)
        yaw = cbuild._die_yaw(spec, t, -45.0 * cbuild.DIRECTIONS_8.index(direction))
        armature.rotation_euler = (0.0, 0.0, math.radians(yaw))
        armature.location = (0.0, 0.0, 0.0)
        bpy.context.view_layer.update()
        _adduct_arms(armature)
        _swing_arms(armature, spec)
        if spec["name"] == "die":
            lift = -cbuild._lowest_z(meshes)
            if lift > 1e-4:
                armature.location = (0.0, 0.0, lift)
                bpy.context.view_layer.update()

    rig = {"frame_size": list(cbuild.FRAME_SIZE), "anchor": list(cbuild.ANCHOR), "directions": directions,
           "parts": [name for name, _, _, _ in PARTS] + ["head"], "radii": _radii(armature), "reference": {}, "actions": {}}
    rig["rest"] = {}
    for direction in directions:
        pose(idle_spec, idle_action, 0, direction)
        rig["rest"][direction] = _parts_2d(armature, camera)
        _reference_pose(armature)
        entry = _parts_2d(armature, camera)
        path = os.path.join(out_dir, "reference_%s.png" % direction)
        scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        entry["bbox"] = _bbox_of_render(path)
        rig["reference"][direction] = entry
    for spec in specs:
        action = cbuild._find_action(spec["source"])
        if action is None:
            raise SystemExit("骨架上找不到動作 %s" % spec["source"])
        block = {"frames": spec["frames"], "fps": spec["fps"], "loop": spec["loop"], "dirs": {}}
        if "hit_frame" in spec:
            block["hit_frame"] = spec["hit_frame"]
        for direction in directions:
            rows = []
            for frame in range(spec["frames"]):
                pose(spec, action, frame, direction)
                rows.append(_parts_2d(armature, camera))
            block["dirs"][direction] = rows
        rig["actions"][spec["name"]] = block
        cbuild._log("%s：%d 格 × %d 方向" % (spec["name"], spec["frames"], len(directions)))
    with open(os.path.join(out_dir, "rig.json"), "w", encoding="utf-8") as handle:
        json.dump(rig, handle, ensure_ascii=False)
    cbuild._log("rig.json 存到 %s" % out_dir)


if __name__ == "__main__":
    main()
