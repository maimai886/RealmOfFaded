"""人體模型的標準骨架：骨頭名稱、階層和位置

這副骨架是全專案的基準。之後所有動作、所有裝備都是照著它做的，
換成正式角色時骨架不能變，不然動作和裝備全部要重做。完整說明在 docs/美術替換指南.md。

命名照 Mixamo 也就是 Unity Humanoid 那一套，不加 mixamorig 前綴。
用這一套的理由：市面上的動作包幾乎都用這組名字，之後買動作或用 Mixamo 產動作，
不用手動對應每一根骨頭就能直接套。

階層重點：
- Root 和 Hips 是分開的兩根。Root 在地板上，動作裡的位移和翻滾的翻轉都打在 Root，
  角色才會真的往前滾出去而不是原地轉圈
- 脊椎是 Spine、Spine1、Spine2 三段再接 Neck、Head，不是一根樹幹
- 手臂前面有鎖骨 Shoulder，手掌後面有拇指加三根手指各三節
- 腳有 ToeBase 和 ToeEnd，腳掌滾動和蹲姿才做得出來
- 另外掛四根裝備掛點 hand_r、hand_l、back、body 和一根 head，名字沿用 data/items.json 的舊名，
  裝備資料不用跟著骨架改名
- 四根 IK 目標骨頭放在 Root 底下，不參與變形，給需要 IK 的動作包用

座標約定和 proportions.py 一樣：+X 是角色的左手邊，-Y 是角色面向的方向，+Z 是上。
"""

import proportions

# 舊的 KayKit 骨頭名對到新名字。既有的 76 個動作是用左邊那組名字做的，
# 重新命名時把動作的軌道路徑一起改掉，動作就能原封不動繼續播
KAYKIT_RENAME = {
    "root": "Root",
    "hips": "Hips",
    "spine": "Spine",
    "chest": "Spine2",
    "head": "Head",
    "upperarm.l": "LeftArm",
    "lowerarm.l": "LeftForeArm",
    "wrist.l": "LeftForeArmTwist",
    "hand.l": "LeftHand",
    "upperarm.r": "RightArm",
    "lowerarm.r": "RightForeArm",
    "wrist.r": "RightForeArmTwist",
    "hand.r": "RightHand",
    "upperleg.l": "LeftUpLeg",
    "lowerleg.l": "LeftLeg",
    "foot.l": "LeftFoot",
    "toes.l": "LeftToeBase",
    "upperleg.r": "RightUpLeg",
    "lowerleg.r": "RightLeg",
    "foot.r": "RightFoot",
    "toes.r": "RightToeBase",
}

# KayKit 有但這副骨架不要的骨頭，全部是不參與變形的控制骨，刪掉換成自己的 IK 目標
KAYKIT_DROP_PREFIXES = ("kneeIK", "elbowIK", "handIK", "heelIK", "IK-foot", "IK-toe",
                        "control-toe-roll", "control-heel-roll", "control-foot-roll",
                        "handslot")

# 動作包常見但 KayKit 沒有的骨頭，補在既有階層中間當成不動的傳遞骨。
# 有這幾根，動作包打在 Spine1、Neck、Shoulder 上的軌道才不會整段失效
# 每一項是 (骨頭名, 父骨頭, 插在誰上面)。插在誰上面的意思是那根骨頭改認新骨頭當父親
INSERTED = [
    ("Spine1", "Spine", "Spine2"),
    ("Neck", "Spine2", "Head"),
    ("LeftShoulder", "Spine2", "LeftArm"),
    ("RightShoulder", "Spine2", "RightArm"),
]

# 手指：拇指加食指、中指、無名指各三節。連指手套幾乎不會變形，
# 但動作包只要有手指軌道就一定要找得到同名骨頭，不然整個綁定會失敗
FINGERS = [("Thumb", 0.62, 0.34), ("Index", 0.28, 0.06),
           ("Middle", 0.00, 0.02), ("Ring", -0.28, 0.04)]
FINGER_JOINTS = 3

# 直接掛在既有骨頭底下的新骨頭，不插在中間，所以既有動作完全不受影響。
# 大腿的扭轉骨和腳尖末端是動作包常見的骨頭，有總比沒有好
EXTRA_BONES = [("LeftUpLegTwist", "LeftUpLeg"), ("RightUpLegTwist", "RightUpLeg"),
               ("LeftToeEnd", "LeftToeBase"), ("RightToeEnd", "RightToeBase")]

# 裝備掛點：名字沿用 data/items.json 認的那五個，值是掛在哪一根骨頭上
SOCKET_PARENTS = {
    "hand_r": "RightHand",
    "hand_l": "LeftHand",
    "head": "Head",
    "back": "Spine2",
    "body": "Spine2",
}

# IK 目標，不參與變形，全部掛在 Root 底下
IK_TARGETS = {
    "LeftHandIK": "LeftHand",
    "RightHandIK": "RightHand",
    "LeftFootIK": "LeftFoot",
    "RightFootIK": "RightFoot",
}


# 主鏈上每根骨頭的「下一根」，骨頭長度照這個算，骨架看起來才是一條一條接好的
CHAIN = {
    "Root": "Hips", "Hips": "Spine", "Spine": "Spine1", "Spine1": "Spine2",
    "Spine2": "Neck", "Neck": "Head",
}
for _side in ("Left", "Right"):
    CHAIN.update({
        _side + "Shoulder": _side + "Arm",
        _side + "Arm": _side + "ForeArm",
        _side + "ForeArm": _side + "ForeArmTwist",
        _side + "ForeArmTwist": _side + "Hand",
        _side + "UpLeg": _side + "Leg",
        _side + "Leg": _side + "Foot",
        _side + "Foot": _side + "ToeBase",
        _side + "ToeBase": _side + "ToeEnd",
    })


def joints(body):
    """每根骨頭的起點世界座標，值是給 rig 用的

    body 是 proportions.Body，它自己的尺寸由 rigspec 的比例參數算出來。
    回傳的字典同時含變形骨、掛點和 IK 目標。

    **小位移一律寫成身體某個尺寸的倍數，不寫死成公尺。**
    寫死的話改一次頭身比就要有人把它們一個一個重推，
    漏掉一個不會報錯，只會讓武器握在手掌外面幾公分的地方。
    真正小到不用跟著縮的只有腳尖那兩個高度，它們是靴底的厚度
    """
    out = {}
    reach = body.upperarm + body.lowerarm
    hand = body.hand
    for side, sign in (("Left", 1), ("Right", -1)):
        x = body.arm_x * sign
        out.update({
            side + "Shoulder": (x * 0.34, 0.0, body.shoulder_z - hand * 0.062),
            side + "Arm": (x, 0.0, body.arm_z),
            side + "ForeArm": (x + body.upperarm * sign, 0.0, body.arm_z),
            side + "ForeArmTwist": (x + (body.upperarm + body.lowerarm * 0.55) * sign,
                                    0.0, body.arm_z),
            side + "Hand": (x + reach * sign, 0.0, body.arm_z),
            side + "UpLeg": (body.leg_x * sign, 0.0, body.crotch_z),
            side + "Leg": (body.leg_x * sign, -0.005, body.crotch_z - body.upperleg),
            side + "UpLegTwist": (body.leg_x * sign, 0.0, body.crotch_z - body.upperleg * 0.45),
            side + "Foot": (body.leg_x * sign, 0.010,
                            body.crotch_z - body.upperleg - body.lowerleg),
            side + "ToeBase": (body.leg_x * sign, -body.foot_forward * 0.55,
                               body.foot_z * 0.385),
            side + "ToeEnd": (body.leg_x * sign, -body.foot_forward, body.foot_z * 0.347),
        })
        # 手指從手掌往外排開。連指手套裡看不到，位置合理就好
        hand_x = x + reach * sign
        for name, across, forward in FINGERS:
            root = (hand_x + body.hand * 0.42 * sign,
                    -body.hand_radius * forward,
                    body.arm_z + body.hand_radius * across * 0.5)
            step = body.hand * 0.22 * sign
            for joint in range(1, FINGER_JOINTS + 1):
                out["%sHand%s%d" % (side, name, joint)] = (
                    root[0] + step * (joint - 1), root[1], root[2])
    out.update({
        "Root": (0.0, 0.0, 0.0),
        "Hips": (0.0, 0.0, body.crotch_z * 1.042),
        "Spine": (0.0, 0.0, body.waist_z),
        "Spine1": (0.0, 0.0, (body.waist_z + body.chest_z) / 2.0),
        "Spine2": (0.0, 0.0, body.chest_z),
        "Neck": (0.0, 0.0, body.shoulder_z + hand * 0.186),
        "Head": (0.0, 0.0, proportions.NECK_Z),
        "hand_r": (-(body.arm_x + reach + hand * 0.52), 0.0, body.arm_z - hand * 0.35),
        # 左手掛點比右手再往外往前推一點：弓是橫著拿的，長度和角色差不多，
        # 掛在手心正中央的話弓身會直接穿過軀幹
        "hand_l": (body.arm_x + reach + hand * 0.95, -hand * 0.54, body.arm_z - hand * 0.35),
        # 頭飾掛點和 Head 骨頭同一個位置。名字是小寫的 head，因為 data/items.json 認這個名字
        "head": (0.0, 0.0, proportions.NECK_Z),
        "back": (0.0, body.chest[1] * 0.92, body.chest_z + body.chest[0] * 0.23),
        "body": (0.0, 0.0, body.chest_z),
    })
    for name, follows in IK_TARGETS.items():
        out[name] = out[follows]
    return out


def export_rig(path=None, gender="neutral"):
    """把骨架的關節位置寫成一份 json，給外面產模型的人照著建 T 姿勢模型

    做法和怪物那條路一樣，見 docs/美術風格指南.md 第 7.4 節：
    契約是關節位置，不是「大概像個人」。外面產的網格如果比例對不上，
    重新綁骨的時候手臂和腿會落在骨頭外面，動起來就會扁掉，
    那不是權重調得好不好的問題，是來源幾何本來就不對。
    """
    import json
    import os

    body = proportions.BODIES[gender]
    points = joints(body)
    data = {
        "_comment": "標準人形骨架的關節位置，單位公尺，原點在腳底。"
                    "外面產的角色要照這個位置建 T 姿勢模型，見 docs/美術風格指南.md 第 7.4 節",
        "height": proportions.HEIGHT,
        "head_ratio": proportions.HEAD_RATIO,
        "chin_z": proportions.CHIN,
        "shoulder_half_width": body.shoulder[0],
        "arm_z": body.arm_z,
        "crotch_z": body.crotch_z,
        "bones": {name: [round(value, 4) for value in position]
                  for name, position in sorted(points.items())},
        "deform_bones": deform_bones(),
        "sockets": sorted(SOCKET_PARENTS),
    }
    if path is None:
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        path = os.path.join(root, "art_source", "characters_v3", "humanoid_rig.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return path


def deform_bones():
    """會影響網格的骨頭名稱，順序是由上到下方便看

    掛點和 IK 目標不在裡面，它們不綁權重。
    """
    names = ["Root", "Hips", "Spine", "Spine1", "Spine2", "Neck", "Head"]
    for side in ("Left", "Right"):
        names += [side + part for part in
                  ("Shoulder", "Arm", "ForeArm", "ForeArmTwist", "Hand")]
        for finger, _, _ in FINGERS:
            names += ["%sHand%s%d" % (side, finger, j) for j in range(1, FINGER_JOINTS + 1)]
        names += [side + part for part in ("UpLeg", "UpLegTwist", "Leg", "Foot", "ToeBase")]
    return names
