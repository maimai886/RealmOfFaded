# -*- coding: utf-8 -*-
"""紙偶的 2D 姿勢庫：每個動作每一格的骨頭角度直接在畫面上定，不從 3D 動作投影。

為什麼不用 3D 投影：刺向鏡頭的手在正面只是縮短，畫面上看不出在做什麼；使用者 2026-09-24 說「動作都只有調整姿勢」。
剪紙人偶的動作本來就是在畫面上設計的：正面攻擊是手臂舉高橫劈過身體，側面攻擊是身體後仰蓄力再往前撲，
坐下是大腿轉到水平、屁股落到膝蓋的高度。每個動作都有預備、爆發、收勢三段。

角度的正負：畫面座標 y 往下，正角度是順時針。側面（w、sw、nw）角色面向左，正角度把手腳往前甩；
正面和背面用「往外」「往內」講：零件在畫面左半邊往外是正，在右半邊往外是負，程式照零件的位置自己換算。
長度是縮放倍率：正面走路往前踏的那條小腿縮到 0.72 就是往鏡頭伸出去。

骨架的父子：軀幹繞髖轉、頭和上臂跟著軀幹、前臂跟著上臂、大腿繞髖、小腿跟大腿、腳跟小腿；短褲跟著髖不跟軀幹。
"""

import math

PARENT = {"torso": "root", "pelvis": "root", "head": "torso", "upper_arm_l": "torso", "upper_arm_r": "torso",
          "forearm_l": "upper_arm_l", "forearm_r": "upper_arm_r", "thigh_l": "root", "thigh_r": "root",
          "shin_l": "thigh_l", "shin_r": "thigh_r", "foot_l": "shin_l", "foot_r": "shin_r"}
ORDER = ["torso", "pelvis", "head", "upper_arm_l", "upper_arm_r", "forearm_l", "forearm_r",
         "thigh_l", "thigh_r", "shin_l", "shin_r", "foot_l", "foot_r"]
FACING = {"s": "front", "n": "back", "w": "side", "sw": "diag", "nw": "diag"}
# 斜向看到的擺幅比側面小
DIAG_SCALE = 0.75
# 斜向走路兩條腿的髖往中間收幾成
DIAG_LEG_GATHER = 0.6
# 走路大腿前後各擺幾度：側面兩腳最開 0.47 個身高，和 RO 初心者走路量到的一樣
WALK_THIGH_DEG = 30.0
# 和 rig2d.CAMERA_ELEVATION_DEG 同一個，骨架是照這個俯角投影的
CAMERA_ELEVATION_DEG = 30.0


def _rot(theta_deg, vx, vy):
    t = math.radians(theta_deg)
    c, s = math.cos(t), math.sin(t)
    return c * vx - s * vy, s * vx + c * vy


def apply_pose(rest, pose):
    """rest 是 rig.json 的 rest[方向]，pose 是 {"dx","dy","rot":{零件:度},"len":{零件:倍率}}；回傳同格式的骨頭列"""
    rot = pose.get("rot", {})
    length = pose.get("len", {})
    depth_override = pose.get("depth", {})
    shift = pose.get("shift", {})
    dx, dy = pose.get("dx", 0.0), pose.get("dy", 0.0)
    transforms = {"root": (0.0, (0.0, 0.0), (dx, dy))}
    rows = {}
    for name in ORDER:
        if name not in rest:
            continue
        ax, ay, bx, by, depth = rest[name]
        parent_theta, parent_rest_start, parent_new_start = transforms[PARENT[name]]
        # 起點跟著父零件走
        rx, ry = _rot(parent_theta, ax - parent_rest_start[0], ay - parent_rest_start[1])
        sx, sy = parent_new_start[0] + rx + shift.get(name, 0.0), parent_new_start[1] + ry
        theta = parent_theta + rot.get(name, 0.0)
        vx, vy = _rot(theta, bx - ax, by - ay)
        scale = length.get(name, 1.0)
        ex, ey = sx + vx * scale, sy + vy * scale
        rows[name] = [round(sx, 2), round(sy, 2), round(ex, 2), round(ey, 2), depth + depth_override.get(name, 0.0)]
        transforms[name] = (theta, (ax, ay), (sx, sy))
    if "head_circle" in rest and "head" in rows:
        _, _, r = rest["head_circle"]
        rows["head_circle"] = [rows["head"][2], rows["head"][3], r]
    if "bbox" in rest:
        rows["bbox"] = rest["bbox"]
    return rows


def _side_of(rest, name):
    """正面背面用：零件在畫面左半邊回 +1，右半邊回 -1，乘上去就是「往外」"""
    hips_x = rest["torso"][0]
    return 1.0 if rest[name][0] < hips_x else -1.0


def _sine(t, offset=0.0):
    return math.sin((t + offset) * math.tau)


# ── 側面 ─────────────────────────────────────────────────────────────

def side_idle(frames):
    out = []
    for f in range(frames):
        t = f / float(frames)
        out.append({"dy": 1.2 * _sine(t), "rot": {"upper_arm_l": 3.0 * _sine(t), "upper_arm_r": 3.0 * _sine(t), "torso": 1.0 * _sine(t)}})
    return out


def _hip_drop(rest, s):
    """兩腳前後張開時髖往下沉，伸直的那隻腳才踩得到地：RO 初心者走路頭的錨點在兩腳最開那格最低、交錯那格最高，差 3 像素"""
    return _leg_length(rest) * (1.0 - math.cos(math.radians(WALK_THIGH_DEG * abs(s))))


def _toward_camera(theta_deg):
    """腿往鏡頭前後擺 theta 度，畫面上的長度倍率：30 度俯角看，往前伸變長、往後收變短"""
    e = math.radians(CAMERA_ELEVATION_DEG)
    return math.cos(math.radians(theta_deg) - e) / math.cos(e)


def side_walk(rest, frames):
    out = []
    for f in range(frames):
        t = f / float(frames)
        s = _sine(t)
        back_l = max(0.0, -s)
        back_r = max(0.0, s)
        out.append({"dy": _hip_drop(rest, s), "rot": {
            "torso": -4.0,
            "thigh_l": WALK_THIGH_DEG * s, "shin_l": -45.0 * back_l, "foot_l": -10.0 * back_l,
            "thigh_r": -WALK_THIGH_DEG * s, "shin_r": -45.0 * back_r, "foot_r": -10.0 * back_r,
            "upper_arm_l": -22.0 * s, "forearm_l": 18.0,
            "upper_arm_r": 22.0 * s, "forearm_r": 18.0}})
    return out


def side_attack(frames):
    # 預備兩格：後仰、近鏡頭那隻手舉到後上方；爆發：撲出去、手掄下來到水平；收勢兩格。_n 是近臂近腿、_f 是遠的
    keys = [
        # 第 0 格是起手：手才抬到肩膀高、身體剛開始往後坐；第 1 格才拉滿。以前兩格差不到十度，斜向再縮成 0.75 倍看起來是同一張
        {"dx": 2, "rot": {"torso": 5, "head": -2, "upper_arm_n": -85, "forearm_n": -45, "upper_arm_f": 6, "thigh_f": -5, "thigh_n": 5, "shin_n": -6}},
        {"dx": 7, "rot": {"torso": 18, "head": -8, "upper_arm_n": -168, "forearm_n": -40, "upper_arm_f": 16, "thigh_f": -14, "thigh_n": 12, "shin_n": -16}},
        {"dx": -4, "rot": {"torso": -8, "head": 4, "upper_arm_n": -40, "forearm_n": -10, "upper_arm_f": -6, "thigh_f": -8, "thigh_n": 20, "shin_n": -14}},
        {"dx": -12, "rot": {"torso": -16, "head": 8, "upper_arm_n": 82, "forearm_n": 0, "upper_arm_f": -16, "thigh_f": -18, "thigh_n": 30, "shin_n": -24, "foot_f": 22}},
        {"dx": -7, "rot": {"torso": -12, "head": 4, "upper_arm_n": 65, "forearm_n": 20, "upper_arm_f": -8, "thigh_f": -10, "thigh_n": 18, "shin_n": -14}},
        {"dx": -2, "rot": {"torso": -3, "upper_arm_n": 15, "forearm_n": 15, "thigh_f": -4, "thigh_n": 6}},
    ]
    return _resample(keys, frames)


def side_cast(frames):
    keys = [
        {"rot": {"torso": -5, "upper_arm_l": 60, "forearm_l": 30, "upper_arm_r": 70, "forearm_r": 30}},
        {"dy": -2, "rot": {"torso": -7, "upper_arm_l": 80, "forearm_l": 10, "upper_arm_r": 90, "forearm_r": 10}},
        {"dy": -3, "rot": {"torso": -8, "upper_arm_l": 95, "forearm_l": 0, "upper_arm_r": 100, "forearm_r": 0}},
        {"dy": -1, "rot": {"torso": -6, "upper_arm_l": 75, "forearm_l": 15, "upper_arm_r": 82, "forearm_r": 15}},
    ]
    return _resample(keys, frames)


def side_hit(frames):
    keys = [
        {"dx": 5, "rot": {"torso": 18, "head": 12, "upper_arm_l": 30, "upper_arm_r": 30, "forearm_l": -20, "forearm_r": -20, "thigh_l": 8, "thigh_r": -12, "shin_r": -10}},
        {"dx": 2, "rot": {"torso": 8, "head": 4, "upper_arm_l": 12, "upper_arm_r": 12, "thigh_l": 3, "thigh_r": -5}},
    ]
    return _resample(keys, frames)


def side_pickup(rest, frames):
    # 蹲下去撿：腿縮短代替整個人下沉，腳才留在地上；身體往右挪一點，彎下去的頭才不會出畫格左邊
    leg = _leg_length(rest)
    keys = [
        {"dx": 5, "dy": 0.16 * leg, "rot": {"torso": -38, "head": -12, "upper_arm_n": 70, "forearm_n": 30, "upper_arm_f": 40, "forearm_f": 20},
         "len": {"thigh_l": 0.84, "thigh_r": 0.84, "shin_l": 0.84, "shin_r": 0.84}},
        {"dx": 12, "dy": 0.22 * leg, "rot": {"torso": -46, "head": -16, "upper_arm_n": 110, "forearm_n": 20, "upper_arm_f": 60, "forearm_f": 20},
         "len": {"thigh_l": 0.76, "thigh_r": 0.76, "shin_l": 0.76, "shin_r": 0.76}},
    ]
    return _resample(keys, frames)


def side_sit(rest, frames):
    # 大腿轉到接近水平、小腿垂直，屁股落到膝蓋的高度；下沉的量照大腿轉過去少掉的垂直長度算，腳留在地上
    ax, ay, bx, by, _ = rest["thigh_l"]
    thigh_len = math.hypot(bx - ax, by - ay)
    angle = 80.0
    pose = {"dy": thigh_len * (1.0 - math.cos(math.radians(angle))), "rot": {"torso": -5, "head": -3, "thigh_l": angle, "shin_l": -angle, "thigh_r": angle, "shin_r": -angle,
                                             "upper_arm_l": 20, "forearm_l": 40, "upper_arm_r": 24, "forearm_r": 40}}
    return [pose] * frames


def _leg_length(rest):
    total = 0.0
    for name in ("thigh_l", "shin_l"):
        ax, ay, bx, by, _ = rest[name]
        total += math.hypot(bx - ax, by - ay)
    return total


# ── 正面和背面 ────────────────────────────────────────────────────────

def front_idle(rest, frames):
    out = []
    for f in range(frames):
        t = f / float(frames)
        out.append({"dy": 1.2 * _sine(t), "rot": {"upper_arm_l": 2.0 * _sine(t) * _side_of(rest, "upper_arm_l"),
                                                  "upper_arm_r": 2.0 * _sine(t) * _side_of(rest, "upper_arm_r")}})
    return out


def front_walk(rest, frames, toward=1.0):
    """正面往前踏的腳往鏡頭伸，畫面上往下、變長；後腳往後收、變短。以前把前腳的小腿縮短，腳反而往上抬，像原地踏步。
    toward 是 1 正面、-1 背面，背面往前踏是離鏡頭遠、變短"""
    out = []
    for f in range(frames):
        t = f / float(frames)
        s = _sine(t)
        ratio_l = _toward_camera(toward * WALK_THIGH_DEG * s)
        ratio_r = _toward_camera(-toward * WALK_THIGH_DEG * s)
        out.append({"dy": _hip_drop(rest, s), "rot": {
            "upper_arm_l": 9.0 * s * _side_of(rest, "upper_arm_l"), "upper_arm_r": -9.0 * s * _side_of(rest, "upper_arm_r"),
            "forearm_l": 8.0, "forearm_r": 8.0},
            "len": {"thigh_l": ratio_l, "shin_l": ratio_l, "thigh_r": ratio_r, "shin_r": ratio_r}})
    return out


def diag_walk(rest, frames, toward):
    """斜向往前是橫著走一半、往鏡頭前後一半：畫面上的擺角和長度變化各取一部分，兩腳前後才一樣開。
    以前只拿側面縮 0.75 倍，一半的步子兩腳疊在一起、另一半張到 0.5 個身高"""
    side = _resolve_near_far(rest, side_walk(rest, frames))
    # 斜向兩條腿在畫面上左右隔將近 30 像素，往前踏的那條會橫越另一條、疊成一條腿；RO 斜向兩腳幾乎從同一點出發，前腳每一步都在前面
    mid = (rest["thigh_l"][0] + rest["thigh_r"][0]) / 2.0
    gather = {k: (mid - rest[k][0]) * DIAG_LEG_GATHER for k in ("thigh_l", "thigh_r")}
    depth = front_walk(rest, frames, toward)
    out = []
    for a, b in zip(side, depth):
        pose = {"dx": 0.0, "dy": a["dy"], "rot": {k: v * DIAG_SCALE for k, v in a["rot"].items()}, "len": {}, "shift": gather}
        for k, v in b["len"].items():
            pose["len"][k] = 1.0 + (v - 1.0) * DIAG_SCALE
        out.append(pose)
    return out


def front_attack(rest, frames):
    # 慣用手（右手）舉到外上方，橫劈過身體到另一側；身體往劈的方向傾
    o = _side_of(rest, "upper_arm_r")
    keys = [
        {"dy": 2, "rot": {"upper_arm_r": 150 * o, "forearm_r": 20 * o, "torso": -8 * o, "upper_arm_l": 15 * _side_of(rest, "upper_arm_l")}},
        {"dy": 3, "rot": {"upper_arm_r": 165 * o, "forearm_r": 25 * o, "torso": -12 * o, "upper_arm_l": 20 * _side_of(rest, "upper_arm_l")}},
        {"dy": 0, "rot": {"upper_arm_r": 60 * o, "forearm_r": 0, "torso": 6 * o, "upper_arm_l": 5 * _side_of(rest, "upper_arm_l")}, "depth": {"upper_arm_r": -1.0, "forearm_r": -1.0}},
        {"dy": -2, "rot": {"upper_arm_r": -40 * o, "forearm_r": -20 * o, "torso": 14 * o, "head": 6 * o, "thigh_l": 6 * _side_of(rest, "thigh_l"), "thigh_r": 6 * _side_of(rest, "thigh_r")}, "depth": {"upper_arm_r": -1.0, "forearm_r": -1.0}},
        {"dy": -1, "rot": {"upper_arm_r": -15 * o, "forearm_r": -10 * o, "torso": 8 * o, "head": 3 * o}, "depth": {"upper_arm_r": -1.0, "forearm_r": -1.0}},
        {"dy": 0, "rot": {"upper_arm_r": 0, "torso": 2 * o}},
    ]
    return _resample(keys, frames)


def front_cast(rest, frames):
    ol, orr = _side_of(rest, "upper_arm_l"), _side_of(rest, "upper_arm_r")
    keys = [
        {"rot": {"upper_arm_l": 120 * ol, "forearm_l": -30 * ol, "upper_arm_r": 120 * orr, "forearm_r": -30 * orr}},
        {"dy": -2, "rot": {"upper_arm_l": 140 * ol, "forearm_l": -20 * ol, "upper_arm_r": 140 * orr, "forearm_r": -20 * orr}},
        {"dy": -3, "rot": {"upper_arm_l": 155 * ol, "forearm_l": -10 * ol, "upper_arm_r": 155 * orr, "forearm_r": -10 * orr}},
        {"dy": -1, "rot": {"upper_arm_l": 135 * ol, "forearm_l": -20 * ol, "upper_arm_r": 135 * orr, "forearm_r": -20 * orr}},
    ]
    return _resample(keys, frames)


def front_hit(rest, frames):
    # 軀幹不縮：短褲併在軀幹的圖裡，縮了褲頭的線會跑到胸口變成一條黑帶；受擊用整個人下沉加頭後仰加手張開
    ol, orr = _side_of(rest, "upper_arm_l"), _side_of(rest, "upper_arm_r")
    keys = [
        {"dy": 4, "rot": {"head": -8, "upper_arm_l": 35 * ol, "upper_arm_r": 35 * orr, "forearm_l": 30 * ol, "forearm_r": 30 * orr},
         "len": {"head": 0.92, "thigh_l": 0.92, "thigh_r": 0.92}},
        {"dy": 2, "rot": {"head": -3, "upper_arm_l": 15 * ol, "upper_arm_r": 15 * orr, "forearm_l": 10 * ol, "forearm_r": 10 * orr},
         "len": {"thigh_l": 0.96, "thigh_r": 0.96}},
    ]
    return _resample(keys, frames)


def front_pickup(rest, frames):
    ol, orr = _side_of(rest, "upper_arm_l"), _side_of(rest, "upper_arm_r")
    keys = [
        {"dy": 0.15 * _leg_length(rest), "rot": {"upper_arm_l": 20 * ol, "forearm_l": -35 * ol, "upper_arm_r": 20 * orr, "forearm_r": -35 * orr},
         "len": {"head": 0.9, "thigh_l": 0.85, "thigh_r": 0.85, "shin_l": 0.85, "shin_r": 0.85}},
        {"dy": 0.22 * _leg_length(rest), "rot": {"upper_arm_l": 25 * ol, "forearm_l": -45 * ol, "upper_arm_r": 25 * orr, "forearm_r": -45 * orr},
         "len": {"head": 0.85, "thigh_l": 0.78, "thigh_r": 0.78, "shin_l": 0.78, "shin_r": 0.78}},
    ]
    return _resample(keys, frames)


def front_sit(rest, frames):
    ax, ay, bx, by, _ = rest["thigh_l"]
    thigh_len = math.hypot(bx - ax, by - ay)
    sx, sy, ex, ey, _ = rest["shin_l"]
    shin_len = math.hypot(ex - sx, ey - sy)
    tl, tr = _side_of(rest, "thigh_l"), _side_of(rest, "thigh_r")
    ol, orr = _side_of(rest, "upper_arm_l"), _side_of(rest, "upper_arm_r")
    # 膝蓋往外張、小腿收回來；下沉的量等於腿在垂直方向少掉的長度，腳留在地上
    drop = thigh_len * (1.0 - 0.7 * math.cos(math.radians(45))) + shin_len * (1.0 - 0.9 * math.cos(math.radians(5)))
    pose = {"dy": drop, "rot": {"thigh_l": 45 * tl, "shin_l": -50 * tl, "thigh_r": 45 * tr, "shin_r": -50 * tr,
                                 "upper_arm_l": 25 * ol, "forearm_l": -40 * ol, "upper_arm_r": 25 * orr, "forearm_r": -40 * orr},
            "len": {"thigh_l": 0.7, "thigh_r": 0.7, "shin_l": 0.9, "shin_r": 0.9}}
    return [pose] * frames


# ── 共用 ─────────────────────────────────────────────────────────────

def _resample(keys, frames):
    """關鍵格數量和要的格數一樣就直接用，不一樣就線性插"""
    if len(keys) == frames:
        return keys
    out = []
    for f in range(frames):
        u = f / float(max(1, frames - 1)) * (len(keys) - 1)
        i = min(int(u), len(keys) - 2) if len(keys) > 1 else 0
        w = u - i
        a, b = keys[i], keys[min(i + 1, len(keys) - 1)]
        pose = {"dx": a.get("dx", 0) * (1 - w) + b.get("dx", 0) * w, "dy": a.get("dy", 0) * (1 - w) + b.get("dy", 0) * w, "rot": {}, "len": {},
                "depth": dict(a.get("depth", {}) if w < 0.5 else b.get("depth", {}))}
        for k in set(a.get("rot", {})) | set(b.get("rot", {})):
            pose["rot"][k] = a.get("rot", {}).get(k, 0) * (1 - w) + b.get("rot", {}).get(k, 0) * w
        for k in set(a.get("len", {})) | set(b.get("len", {})):
            pose["len"][k] = a.get("len", {}).get(k, 1) * (1 - w) + b.get("len", {}).get(k, 1) * w
        out.append(pose)
    return out


def _scaled(poses, factor):
    out = []
    for pose in poses:
        out.append({"dx": pose.get("dx", 0) * factor, "dy": pose.get("dy", 0),
                    "rot": {k: v * factor for k, v in pose.get("rot", {}).items()}, "len": dict(pose.get("len", {})),
                    "depth": dict(pose.get("depth", {}))})
    return out


def poses_for(rest, action, frames, direction):
    """這個動作這個方向每一格的姿勢；die 回 None，它是整張圖倒下不用零件"""
    kind = FACING[direction]
    if action == "die":
        return None
    if kind == "diag" and action == "walk":
        return _damp_far_arm(rest, diag_walk(rest, frames, 1.0 if direction == "sw" else -1.0))
    if kind in ("side", "diag"):
        table = {"idle": lambda: side_idle(frames), "walk": lambda: side_walk(rest, frames), "attack": lambda: side_attack(frames),
                 "cast": lambda: side_cast(frames), "hit": lambda: side_hit(frames), "pickup": lambda: side_pickup(rest, frames),
                 "sit": lambda: side_sit(rest, frames)}
        poses = _resolve_near_far(rest, table[action]())
        if kind == "diag" and action in ("walk", "idle"):
            poses = _damp_far_arm(rest, poses)
        # 斜向擺幅縮小只用在會動的動作；坐和撿的下沉量是照角度算的，縮了腳會掉到地下
        return _scaled(poses, DIAG_SCALE) if kind == "diag" and action not in ("sit", "pickup") else poses
    table = {"idle": lambda: front_idle(rest, frames), "walk": lambda: front_walk(rest, frames, 1.0 if direction == "s" else -1.0),
             "attack": lambda: front_attack(rest, frames),
             "cast": lambda: front_cast(rest, frames), "hit": lambda: front_hit(rest, frames), "pickup": lambda: front_pickup(rest, frames),
             "sit": lambda: front_sit(rest, frames)}
    return table[action]()


# 斜向走路時遠的那隻手臂只擺這麼多：它在畫裡大半藏在身體後面，只露一條，擺滿了那一條會像一根刺甩出身體外
FAR_ARM_SWING = 0.35


def _damp_far_arm(rest, poses):
    side = "r" if rest["upper_arm_l"][4] <= rest["upper_arm_r"][4] else "l"
    out = []
    for pose in poses:
        pose = dict(pose)
        pose["rot"] = {k: (v * FAR_ARM_SWING if k in ("upper_arm_" + side, "forearm_" + side) else v) for k, v in pose.get("rot", {}).items()}
        out.append(pose)
    return out


def _resolve_near_far(rest, poses):
    """側面姿勢裡寫 _n（近鏡頭）和 _f（遠）的零件，照 rest 的深度換成 _l 或 _r"""
    near_l = rest["upper_arm_l"][4] <= rest["upper_arm_r"][4]
    leg_near_l = rest["thigh_l"][4] <= rest["thigh_r"][4]

    def real(name):
        if name.endswith("_n") or name.endswith("_f"):
            base, tag = name[:-2], name[-1]
            near = leg_near_l if base in ("thigh", "shin", "foot") else near_l
            side = ("l" if near else "r") if tag == "n" else ("r" if near else "l")
            return "%s_%s" % (base, side)
        return name
    out = []
    for pose in poses:
        out.append({"dx": pose.get("dx", 0), "dy": pose.get("dy", 0),
                    "rot": {real(k): v for k, v in pose.get("rot", {}).items()},
                    "len": {real(k): v for k, v in pose.get("len", {}).items()},
                    "depth": {real(k): v for k, v in pose.get("depth", {}).items()}})
    return out


def rows_for(rest, action, frames, direction):
    """直接給 puppet_sheet 用：每一格的骨頭列；die 回 None"""
    poses = poses_for(rest, action, frames, direction)
    if poses is None:
        return None
    return [apply_pose(rest, pose) for pose in poses]
