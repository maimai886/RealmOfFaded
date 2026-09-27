# -*- coding: utf-8 -*-
"""紙偶骨架，不用 Blender：照 cbuild 同一組比例和同一顆 30 度正交相機，把站直的標準骨架投影到畫格上，寫成 rig.json。

puppet_rig.py 要在 Blender 裡跑，輸出放在沒進版本庫的 art_pipeline/_build；沒有 Blender 的機器接不下去。
動作早就改由 puppet_poses.py 在畫面上設計，骨架只剩兩個用途：切零件的參考姿勢、每個方向的站姿，
兩個都是站直手垂下，用比例算得出來，不需要 KayKit 的動作檔。

跟 puppet_rig.py 的差別：
- rest 和 reference 是同一份。站姿第 0 格本來就是使用者的原圖，rest 只是動作的起點
- 頭的圓和視圖放在哪裡照使用者的視圖量，不照人偶：視圖等比縮到 figure_height，兩腳腳底的中點對到錨點，
  軀幹中線對到畫格中線；頭頂到脖子最窄那一列量出頭的圓
- 骨架先照比例投影，再上下拉到視圖的頭頂和錨點，頭用量到的圓

用法：
  python art_pipeline/characters_v5/rig2d.py <視圖資料夾> <輸出資料夾> [--figure-height 180] [--body-meta 身體 meta.json]
輸出資料夾裡是 rig.json，格式和 puppet_rig.py 一樣，多一個 head_circle_fitted。
"""

import argparse
import json
import math
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "characters_v3"))
sys.path.insert(0, HERE)
import aether_sheet  # noqa: E402
import proportions  # noqa: E402
import rigspec  # noqa: E402

FRAME_SIZE = (176, 232)
ANCHOR = (88, 208)
PIXELS_PER_METER = 96.0
CAMERA_ELEVATION_DEG = 30.0
DIRECTIONS = ["s", "sw", "w", "nw", "n"]
# 和 cbuild.CARD_SPEC 同一組：定裝卡量出來的 2.83 頭身
CARD_SPEC = {"head_ratio": 2.83, "head_width_per_head": 0.99, "shoulder_per_head_width": 1.085,
             "shoulder_per_height": 0.556, "crotch_per_height": 0.317, "stance_per_head_width": 0.595,
             "leg_width_per_head_width": 0.323}
# 手臂垂下時往外張一點，和 puppet_rig.REFERENCE_AIM 一樣
ARM_AIM = (0.10, 0.0, -1.0)
FOREARM_AIM = (0.04, 0.0, -1.0)
PELVIS_FRACTION = 0.55
# 動作表照現在出貨的身體圖集，引擎讀 meta，格數要和它一樣
DEFAULT_ACTIONS = {
    "idle": {"frames": 3, "fps": 5, "loop": True},
    "walk": {"frames": 8, "fps": 12, "loop": True},
    "attack": {"frames": 6, "fps": 14, "loop": False, "hit_frame": 3},
    "cast": {"frames": 4, "fps": 8, "loop": True},
    "hit": {"frames": 2, "fps": 10, "loop": False},
    "die": {"frames": 4, "fps": 7, "loop": False},
    "sit": {"frames": 1, "fps": 1, "loop": True},
    "pickup": {"frames": 2, "fps": 8, "loop": False},
}


def _norm(v):
    length = math.sqrt(sum(c * c for c in v))
    return tuple(c / length for c in v)


def skeleton_3d(height_m):
    """站直手垂下的骨架，角色座標：+X 左手邊、-Y 面向、+Z 上，原點在腳底"""
    spec = rigspec.RigSpec(height_m=height_m, **CARD_SPEC)
    body = proportions.Body("male", spec)
    joints = {}
    for side, sign in (("l", 1.0), ("r", -1.0)):
        shoulder = (spec.arm_x * sign, 0.0, spec.arm_z)
        aim = _norm((ARM_AIM[0] * sign, ARM_AIM[1], ARM_AIM[2]))
        elbow = tuple(shoulder[i] + aim[i] * spec.upperarm for i in range(3))
        aim2 = _norm((FOREARM_AIM[0] * sign, FOREARM_AIM[1], FOREARM_AIM[2]))
        hand = tuple(elbow[i] + aim2[i] * (spec.lowerarm + spec.hand_length) for i in range(3))
        hip = (spec.leg_x * sign, 0.0, spec.crotch_z)
        knee = (spec.leg_x * sign, -0.005, spec.crotch_z - spec.upperleg)
        ankle = (spec.leg_x * sign, 0.010, spec.crotch_z - spec.upperleg - spec.lowerleg)
        toe = (spec.leg_x * sign, -spec.foot_forward, 0.014)
        joints.update({"shoulder_" + side: shoulder, "elbow_" + side: elbow, "hand_" + side: hand,
                       "hip_" + side: hip, "knee_" + side: knee, "ankle_" + side: ankle, "toe_" + side: toe})
    hips = (0.0, 0.0, spec.crotch_z * 1.042)
    knees = tuple((joints["knee_l"][i] + joints["knee_r"][i]) / 2.0 for i in range(3))
    joints["hips"] = hips
    # 骨盆段只到褲管下緣，胯往下一成二：照膝蓋的 55% 會一路伸到小腿，整條腿被當成短褲切進軀幹，腿就不會動
    joints["pelvis_end"] = (0.0, 0.0, spec.crotch_z * 0.88)
    joints["neck"] = (0.0, 0.0, spec.neck_z)
    joints["head_centre"] = (0.0, 0.0, spec.head_centre_z)
    joints["head_top"] = (0.0, 0.0, height_m)
    radii = {"torso": body.shoulder[0] * 0.72, "pelvis": body.hip[0] * 0.95, "upper_arm": body.arm_radius[0],
             "forearm": body.hand_radius, "thigh": body.leg_radius[0], "shin": body.leg_radius[0], "foot": body.leg_radius[0] * 1.1}
    return joints, radii, spec


def project(point, yaw_deg):
    """角色轉 yaw 度之後，正交相機 30 度俯角看過去：回傳 (畫面右, 畫面上, 深度)，單位公尺，深度大的比較遠"""
    yaw = math.radians(yaw_deg)
    c, s = math.cos(yaw), math.sin(yaw)
    x, y, z = point
    rx, ry = c * x - s * y, s * x + c * y
    e = math.radians(CAMERA_ELEVATION_DEG)
    up = ry * math.sin(e) + z * math.cos(e)
    depth = ry * math.cos(e) - z * math.sin(e)
    return rx, up, depth


PARTS = [
    ("torso", "hips", "neck"), ("pelvis", "hips", "pelvis_end"),
    ("upper_arm_l", "shoulder_l", "elbow_l"), ("forearm_l", "elbow_l", "hand_l"),
    ("upper_arm_r", "shoulder_r", "elbow_r"), ("forearm_r", "elbow_r", "hand_r"),
    ("thigh_l", "hip_l", "knee_l"), ("shin_l", "knee_l", "ankle_l"), ("foot_l", "ankle_l", "toe_l"),
    ("thigh_r", "hip_r", "knee_r"), ("shin_r", "knee_r", "ankle_r"), ("foot_r", "ankle_r", "toe_r"),
]


def _components(mask):
    """四連通分團，回傳每一團的 (最低那一列 + 1, 像素數)"""
    seen = np.zeros_like(mask, dtype=bool)
    out = []
    height, width = mask.shape
    for y0, x0 in zip(*np.nonzero(mask)):
        if seen[y0, x0]:
            continue
        stack = [(y0, x0)]
        seen[y0, x0] = True
        low, count = y0, 0
        while stack:
            y, x = stack.pop()
            count += 1
            low = max(low, y)
            for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= ny < height and 0 <= nx < width and mask[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    stack.append((ny, nx))
        if count >= 6:
            out.append((int(low) + 1, count))
    return out


def measure_view(path, scale):
    """視圖去背、等比縮放之後量：外框、兩腳腳底中點、軀幹中線、頭的圓。座標是縮放後圖的像素"""
    figure = aether_sheet.trim(aether_sheet.cut(Image.open(path).convert("RGB")))
    w, h = max(1, int(round(figure.width * scale))), max(1, int(round(figure.height * scale)))
    small = figure.resize((w, h), Image.LANCZOS)
    alpha = np.asarray(small)[..., 3] > 128
    rows = np.nonzero(alpha.any(1))[0]
    top, bottom = int(rows.min()), int(rows.max()) + 1
    height = bottom - top
    # 腳：最下面一成五的剪影照連通分成幾團，最大的兩團各自最低的那一列取中點。
    # 斜向時兩隻腳在欄上會重疊，只照欄分會變成一團，中點就錯成近的那隻腳
    band_top = bottom - max(4, int(height * 0.15))
    lows = [low for low, _ in sorted(_components(alpha[band_top:bottom]), key=lambda item: -item[1])[:2]]
    lows = [band_top + low for low in lows]
    feet_mid = float(np.mean(lows)) if lows else float(bottom)
    # 軀幹中線：從上往下 45% 到 58% 那一段每一列剪影的中點取中位數
    mids = []
    for y in range(top + int(height * 0.45), top + int(height * 0.58)):
        xs = np.nonzero(alpha[y])[0]
        if len(xs):
            mids.append((xs.min() + xs.max()) / 2.0)
    torso_x = float(np.median(mids)) if mids else w / 2.0
    # 頭：頭頂到脖子最窄那一列，脖子在上面 28% 到 50% 之間找
    widths = []
    for y in range(top + int(height * 0.28), top + int(height * 0.50)):
        xs = np.nonzero(alpha[y])[0]
        widths.append((xs.max() - xs.min() + 1 if len(xs) else 1e9, y))
    neck_y = min(widths)[1]
    radius = (neck_y - top) / 2.0
    head_rows = [(np.nonzero(alpha[y])[0], y) for y in range(top, neck_y)]
    widest = max(head_rows, key=lambda item: (item[0].max() - item[0].min()) if len(item[0]) else 0)
    head_cx = (widest[0].min() + widest[0].max()) / 2.0
    return {"size": (w, h), "top": top, "feet_lows": sorted(lows), "bottom": bottom, "feet_mid": feet_mid, "torso_x": torso_x,
            "neck_y": neck_y, "head": (head_cx, top + radius, radius)}


def landmarks(views, scale, anchor=ANCHOR):
    """正面視圖量高度的地標，換成畫格座標：頭頂、脖子、肩線、胯、兩腳中點，和兩腿中心的半距。
    五張視圖同一個比例、腳底同一條地面，所以正面量到的高度每個方向都用"""
    m = measure_view(os.path.join(views, "s.png"), scale)
    figure = aether_sheet.trim(aether_sheet.cut(Image.open(os.path.join(views, "s.png")).convert("RGB")))
    small = figure.resize(m["size"], Image.LANCZOS)
    alpha = np.asarray(small)[..., 3] > 128
    top_shift = anchor[1] - m["feet_mid"]
    neck = m["neck_y"]
    # 胯：脖子以下，剪影在軀幹中線左右 12 像素內第一次出現空隙的那一列
    crotch = None
    centre = int(round(m["torso_x"]))
    for y in range(neck + 10, m["bottom"]):
        if not alpha[y, centre - 2:centre + 3].all():
            crotch = y
            break
    crotch = crotch if crotch is not None else int(neck + (m["bottom"] - neck) * 0.6)
    # 肩線：脖子以下第一列寬到「脖子到胯三成五那一列」九成二的那一列
    def width(y):
        xs = np.nonzero(alpha[y])[0]
        return xs.max() - xs.min() + 1 if len(xs) else 0
    ref = width(int(neck + (crotch - neck) * 0.35))
    shoulder = next((y for y in range(neck, crotch) if width(y) >= 0.92 * ref), int(neck + (crotch - neck) * 0.2))
    # 兩腿中心半距：胯和腳底中間那一段，兩團剪影的中心距一半，取中位數
    halves = []
    for y in range(crotch + 4, int(m["feet_mid"]) - 6):
        xs = np.nonzero(alpha[y])[0]
        runs = np.split(xs, np.nonzero(np.diff(xs) > 1)[0] + 1) if len(xs) else []
        if len(runs) == 2:
            halves.append(((runs[1].min() + runs[1].max()) - (runs[0].min() + runs[0].max())) / 4.0)
    return {"top": m["top"] + top_shift, "neck": neck + top_shift, "shoulder": shoulder + top_shift,
            "crotch": crotch + top_shift, "ground": float(anchor[1]),
            "leg_half": float(np.median(halves)) if halves else None}


# 手垂下時指尖落在肩線到胯之間的這個位置，量自使用者的正面視圖
HAND_REACH = 0.9


def build(views, figure_height=180.0, actions=None, frame_size=FRAME_SIZE, anchor=ANCHOR):
    joints, radii, spec = skeleton_3d(figure_height / PIXELS_PER_METER)
    first = aether_sheet.trim(aether_sheet.cut(Image.open(os.path.join(views, "s.png")).convert("RGB")))
    scale = figure_height / float(first.height)
    marks = landmarks(views, scale, anchor)
    # 高度照地標分段對：地面、胯、肩、脖子各自對到視圖量到的那一列，中間線性；比例和畫的圖不一樣時骨頭才落在圖的肢體裡
    z_keys = [0.0, spec.crotch_z, spec.arm_z, spec.neck_z, spec.height_m]
    y_keys = [marks["ground"], marks["crotch"], marks["shoulder"], marks["neck"], marks["top"]]
    hscale = marks["leg_half"] / (spec.leg_x * PIXELS_PER_METER) if marks["leg_half"] else 1.0
    arm_scale = ((marks["crotch"] - marks["shoulder"]) * HAND_REACH) / ((spec.arm_z - joints["hand_l"][2]) * PIXELS_PER_METER)

    def z_to_y(z):
        return float(np.interp(z, z_keys, y_keys))

    rig = {"frame_size": list(frame_size), "anchor": list(anchor), "directions": DIRECTIONS,
           "parts": [name for name, _, _ in PARTS] + ["head"], "radii": {k: round(v * PIXELS_PER_METER * hscale, 2) for k, v in radii.items()},
           "reference": {}, "rest": {}, "actions": {}, "head_circle_fitted": True, "view_scale": scale, "landmarks": marks,
           "source": {"pipeline": "art_pipeline/characters_v5/rig2d.py", "views": os.path.relpath(views, os.path.join(HERE, "..", ".."))}}
    arm_joints = ("elbow_l", "hand_l", "elbow_r", "hand_r")
    for index, direction in enumerate(DIRECTIONS):
        m = measure_view(os.path.join(views, direction + ".png"), scale)
        # 視圖放進畫格的位置：兩腳中點對到錨點那一列，軀幹中線對到錨點那一欄
        left = anchor[0] - m["torso_x"]
        top = anchor[1] - m["feet_mid"]
        bbox = [round(left, 2), round(top + m["top"], 2), round(left + m["size"][0], 2), round(top + m["bottom"], 2)]
        yaw = -45.0 * index
        e = math.radians(CAMERA_ELEVATION_DEG)
        # 前後的高低差照視圖量：斜向兩隻腳一前一後，畫的人踏得比骨架開，照兩腳腳底的高低差把深度造成的上下位移放大
        yaw_r = math.radians(yaw)
        model_gap = abs(2.0 * spec.leg_x * math.sin(yaw_r)) * math.sin(e) * PIXELS_PER_METER * hscale
        depth_gain = 1.0
        if model_gap > 3.0 and len(m["feet_lows"]) == 2:
            depth_gain = max(0.5, min(2.5, (m["feet_lows"][1] - m["feet_lows"][0]) / model_gap))

        def px(name):
            point = joints[name]
            if name in arm_joints:
                # 手臂照肩膀往下縮放到量到的長度
                side = name[-1]
                shoulder = joints["shoulder_" + side]
                point = tuple(shoulder[i] + (point[i] - shoulder[i]) * (arm_scale if i == 2 else 1.0) for i in range(3))
                z_y = z_to_y(shoulder[2]) - (point[2] - shoulder[2]) * PIXELS_PER_METER
            else:
                z_y = z_to_y(point[2])
            rx, _, depth = project(point, yaw)
            yaw_r = math.radians(yaw)
            ry = math.sin(yaw_r) * point[0] + math.cos(yaw_r) * point[1]
            return anchor[0] + rx * PIXELS_PER_METER * hscale, z_y - ry * math.sin(e) * PIXELS_PER_METER * hscale * depth_gain, depth

        entry = {}
        for name, a, b in PARTS:
            ax, ay, ad = px(a)
            bx, by, bd = px(b)
            entry[name] = [round(ax, 2), round(ay, 2), round(bx, 2), round(by, 2), round((ad + bd) / 2.0, 4)]
        hx, hy, radius = m["head"]
        cx, cy = left + hx, top + hy
        neck_y = top + m["neck_y"]
        _, _, head_depth = px("head_centre")
        entry["head"] = [float(anchor[0]), round(neck_y, 2), round(float(cx), 2), round(cy, 2), round(head_depth, 4)]
        entry["head_circle"] = [round(float(cx), 2), round(cy, 2), round(radius, 2)]
        rest = json.loads(json.dumps(entry))
        entry["bbox"] = bbox
        rig["reference"][direction] = entry
        rig["rest"][direction] = rest
    for action, info in (actions or DEFAULT_ACTIONS).items():
        block = dict(info)
        block["dirs"] = {d: [rig["rest"][d]] * int(info["frames"]) for d in DIRECTIONS}
        rig["actions"][action] = block
    return rig


def cut_to_bbox(path, bbox, work_scale, frame_size):
    """視圖放進工作解析度的畫布，位置和大小照 rig 的 bbox；取代 puppet_sheet.cut_view，那支會照 bbox 高度重算縮放"""
    image = Image.open(path).convert("RGB")
    figure = aether_sheet.trim(aether_sheet.cut(image))
    x0, y0, x1, y1 = bbox
    w, h = int(round((x1 - x0) * work_scale)), int(round((y1 - y0) * work_scale))
    figure = figure.resize((max(1, w), max(1, h)), Image.LANCZOS)
    canvas = Image.new("RGBA", (frame_size[0] * work_scale, frame_size[1] * work_scale), (0, 0, 0, 0))
    canvas.alpha_composite(figure, (int(round(x0 * work_scale)), int(round(y0 * work_scale))))
    return canvas


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("views")
    parser.add_argument("out")
    parser.add_argument("--figure-height", type=float, default=180.0)
    parser.add_argument("--body-meta", default="", help="動作表照這份 meta 的格數，預設是現在出貨的那一份的格數")
    args = parser.parse_args()
    actions = None
    if args.body_meta:
        with open(args.body_meta, encoding="utf-8") as handle:
            meta = json.load(handle)
        actions = {name: {k: v for k, v in info.items() if k in ("frames", "fps", "loop", "hit_frame")}
                   for name, info in meta["actions"].items()}
    rig = build(os.path.abspath(args.views), args.figure_height, actions)
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "rig.json"), "w", encoding="utf-8") as handle:
        json.dump(rig, handle, ensure_ascii=False)
    for direction in DIRECTIONS:
        print(direction, "bbox", rig["reference"][direction]["bbox"], "head", rig["reference"][direction]["head_circle"])


if __name__ == "__main__":
    main()
