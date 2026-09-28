# -*- coding: utf-8 -*-
"""紙偶動畫：把使用者畫的視圖切成零件，照 puppet_rig.py 的骨架動起來，組成身體圖集。用系統的 python 跑，要有 Pillow。

每一格都是使用者的線條，比例不會飄；八方向、所有動作、任何張數都從同一套零件出；換裝就是換零件的圖。
零件怎麼切：視圖對到參考姿勢的骨架後，每個像素歸給最近的那一段骨頭，頭是一個圓。
零件怎麼動：每一格拿參考骨頭到動作骨頭的 2D 相似變換（平移、旋轉、縮放），零件照深度由遠到近疊上去。

用法：
  python art_pipeline/characters_v5/puppet_sheet.py <視圖資料夾> <rig 資料夾> <名稱> [--candidate] [--debug 資料夾]
視圖資料夾裡要有 s、sw、w、nw、n 五張，白底，整個人都在圖裡；rig 資料夾是 puppet_rig.py 的輸出。
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
sys.path.insert(0, HERE)
from common import sheet_output  # noqa: E402
import aether_sheet  # noqa: E402
import puppet_poses  # noqa: E402

PROJECT_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
WORK_SCALE = 2
# 像素圖模式：來源是 176×232 那種一格一格畫的像素圖時，整條路都在 1 倍做、只用最近點取樣、不重畫描邊、
# 輸出標 nearest。放大兩倍再用 LANCZOS 縮回來會把硬邊糊成灰帶，遊戲裡放大看是鋸齒加模糊，
# 使用者 2026-09-24 看到創角畫面說「我啥時同意這種品質」。像素圖的描邊是畫在圖裡的，剝掉再重畫只會變粗
PIXEL_MODE = False
RESAMPLE = Image.BICUBIC
VIEW_RESAMPLE = Image.LANCZOS
# 使用者畫的頭比人偶的頭球大一圈，切頭的圓放大這麼多倍；零件邊緣往外多拿幾個像素，關節處才有重疊不會露縫
HEAD_CIRCLE_SCALE = 1.28
PART_OVERLAP_PX = 3
LIMB_SCALE_RANGE = (0.55, 1.45)
# 疊的順序照剪紙人偶的慣例固定，不照每個零件的深度排：遠的手臂最後面，接著遠的腿、近的腿、軀幹、近的手臂、頭。
# 同一條肢體是末端先畫、根部蓋在上面，關節處重疊的地方才藏得住。遠近每一格照骨頭的深度判斷。
# 以前照深度排，側面走路時大腿會蓋到短褲、遠的手臂跑到身體前面，看起來像壞掉的剪紙
LAYER_ORDER = ("far_arm", "far_leg", "near_leg", "torso", "near_arm", "head")
# 肢體零件往關節的根部多補一段圓頭：平常被上面那一層蓋住，肢體轉出去時那一段跟著轉，關節才不會露縫。
# 補的那段不拿原圖的像素，原圖那裡是短褲或衣服，轉出去會像撕下一塊布；改填肢體自己在關節附近的中位色，
# 大腿補出來是膚色的圓頭、上臂補出來是袖子的顏色。數字是半寬的倍數，腿補多一點、肩膀補少一點
JOINT_EXTEND_RATIO = {"thigh": 0.8, "shin": 0.8, "foot": 0.7, "upper_arm": 0.4, "forearm": 0.6}
# 圓頭離剪影邊緣至少這麼多個工作像素，邊緣的墨線才不會被膚色蓋掉
CAP_INSET_PX = 4
ORDER = ["idle", "walk", "attack", "cast", "hit", "die", "sit", "pickup"]


def cut_view(path, bbox_target, frame_size):
    """視圖去背、切到外框，縮到人偶剪影的外框大小，腳底對齊；回傳工作解析度的 RGBA 畫布"""
    image = Image.open(path).convert("RGB")
    cut = aether_sheet.cut(image)
    if PIXEL_MODE:
        # 像素圖的邊是一格墨線不是墨和白紙混色，反算會把邊上的膚色算成半透明的紅
        rgb = np.asarray(image)
        paper = (np.asarray(cut)[..., 3] == 0) & (rgb.min(2) > aether_sheet.WHITE)
        cut = Image.fromarray(np.dstack([rgb, np.where(paper, 0, 255).astype(np.uint8)]), "RGBA")
    figure = aether_sheet.trim(cut)
    x0, y0, x1, y1 = bbox_target
    target_h = (y1 - y0) * WORK_SCALE
    scale = target_h / float(figure.height)
    if PIXEL_MODE and abs(scale - 1.0) < 0.06:
        # 像素圖差幾個像素就不縮，縮了每個像素都糊
        scale = 1.0
    if abs(scale - 1.0) > 1e-6:
        figure = figure.resize((max(1, int(round(figure.width * scale))), max(1, int(round(figure.height * scale)))), VIEW_RESAMPLE)
    canvas = Image.new("RGBA", (frame_size[0] * WORK_SCALE, frame_size[1] * WORK_SCALE), (0, 0, 0, 0))
    cx = (x0 + x1) / 2.0 * WORK_SCALE
    left = int(round(cx - figure.width / 2.0))
    top = int(round(y1 * WORK_SCALE - figure.height))
    canvas.alpha_composite(figure, (left, top))
    return canvas


# 切零件時半寬照人偶的骨架再調：短褲在側面比骨盆寬，骨盆管子放大一點短褲才整件跟著軀幹；
# 上臂的管子縮一點，肩膀那塊袖子留給軀幹，手往後拉時不會帶走一整塊衣服
RADIUS_TUNE = {"pelvis": 1.25, "upper_arm": 0.62}
# 手臂和腿平常壓在軀幹上，那些像素歸肢體；肢體一動走，軀幹那裡就是洞。
# 軀幹管子裡被肢體佔掉的像素用旁邊軀幹的顏色一圈圈長進去補起來，平常被肢體蓋住看不到，肢體移開才露出來
UNDERPAINT_PASSES = 14
# 骨盆那段往膝蓋多延伸這麼多倍，短褲的下襬才在管子裡
PELVIS_STRETCH = 1.3
# 上臂切零件時從肩膀往下空這麼多比例再開始：肩膀那塊留給軀幹，手往後拉時不會帶走一整塊衣服；轉動還是繞肩膀
UPPER_ARM_TRIM = 0.3
NEAR_ARM_TRIM = 0.08
# 手臂的管子壓在身體上時，管子裡離骨頭超過這個比例的半寬、顏色又和手臂本身差很多的像素還給軀幹：
# 側面時前臂貼著白衣服，不這樣做前臂會帶走一塊衣服，手往後拉就多一塊白板
ARM_COLOR_CORE = 0.6
ARM_COLOR_DISTANCE = 90.0
# 零件相對參考方向最多轉幾度：骨頭是 3D 投影，膝蓋彎向鏡頭時投影會轉七八十度，平面的小腿跟著轉就變成腳橫著；
# 夾住角度、長度照投影縮短，看起來才像縮進去
# 骨頭在畫面上的方向變了，有兩種可能：真的在畫面裡轉，或是往鏡頭前縮、投影跟著偏。
# 分辨的依據是投影長度：真的轉長度不變，前縮長度會掉。長度剩八成五以上照轉，剩三成五以下完全不轉，中間按比例；
# 方向反過來超過 90 度一定是前縮過了鏡頭的軸，也不轉。腿往前伸、往後勾都是這種，以前硬夾在 60 度會把小腿轉到旁邊去
FORESHORTEN_FULL_TURN = 0.85
FORESHORTEN_NO_TURN = 0.35
# 之後再夾一個上限保險；腳自己一個零件，腳尖不會跟著小腿插進地裡
ROTATION_LIMIT_DEG = {"shin": 100.0, "thigh": 100.0, "foot": 45.0, "forearm": 120.0, "upper_arm": 120.0}
# 肢體是一條鏈：前臂接在上臂放好之後的末端、小腿接在大腿的末端、腳接在小腿的末端。
# 角度被夾住時上一節的末端不在骨頭算的位置，下一節照骨頭放就會脫節，接在上一節放好的地方才連得上
CHAIN_PARENT = {"forearm_l": "upper_arm_l", "forearm_r": "upper_arm_r", "shin_l": "thigh_l", "shin_r": "thigh_r",
                "foot_l": "shin_l", "foot_r": "shin_r"}
CHAIN_ORDER = ("torso", "pelvis", "head", "upper_arm_l", "upper_arm_r", "thigh_l", "thigh_r",
               "forearm_l", "forearm_r", "shin_l", "shin_r", "foot_l", "foot_r")
# 側面看的時候上臂壓在身體上，切出來一定帶一塊衣服，一動就撕衣服。這幾個方向上臂併進軀幹不動，
# 只有前臂從手肘以下動；手肘跟著軀幹的變換走，前臂才接得上
# 2026-09-27 第 2 輪起側面也不併：併進軀幹的上臂在前臂擺開時留一塊粉色，而且沒有袖子；手臂切開的邊補墨線，見 CUT_EDGE_INK
ARM_MERGED_DIRECTIONS = ()
# 第 2 輪的手臂和腿（袖子跟上臂、手臂自己描線、褲管照腿剪影分、遠臂衣服色還給軀幹）還沒做完，2026-09-27 使用者叫停時先關掉，
# 關掉就是第 1 輪送審的行為；接手從 docs/美術產線接手紀錄.md 0.5 節接
V2_LIMBS = False
if not V2_LIMBS:
    ARM_MERGED_DIRECTIONS = ("w",)
# 舉手時袖子的寬度，上臂半寬的倍數；手臂身上的墨線離手臂幾個工作像素以內才留
SLEEVE_WIDTH = 1.9
# 手臂自己描的線有幾個工作像素寬，工作解析度是目標的 4 倍，3 就是縮完四分之三格，鎖色時落到墨色
ARM_RING_PX = 3
# 手臂切開那一邊補的墨線顏色，和使用者畫的線同一個深度
CUT_EDGE_INK = (48, 38, 38)
# 手臂要大幅度動的動作在側面還是用切開的上臂，不然舉不起來；只有走路和待機把上臂併進軀幹
ARM_SPLIT_ACTIONS = ("attack", "cast", "hit", "pickup", "sit")
# 姿勢由 puppet_poses.py 在畫面上直接定，角度和長度照給的用，不做前縮判斷也不夾角度；die 還是拿 rig 的列做剛體倒下
POSE_MODE = True
# 死亡不用零件動：整個人繞腳底倒下去，正面背面往畫面左邊倒，側面往背後倒，和 RO 的死亡圖一樣一眼看得出來
DIE_FALL_DEG = 84.0
# 坐下照 puppet_poses 的坐姿：大腿轉到水平、屁股落到膝蓋的高度；這個數字只剩 rigid_action 的舊路在用
SIT_SQUASH = (1.06, 0.78)
FACING_X = {"s": 0.0, "sw": -0.7, "w": -1.0, "nw": -0.7, "n": 0.0}


def _radius_of(name, radii):
    for key in ("upper_arm", "forearm", "thigh", "shin", "foot", "torso", "pelvis"):
        if name.startswith(key):
            return radii.get(key, 0.0) * WORK_SCALE * RADIUS_TUNE.get(key, 1.0)
    return 0.0


# 分配的優先順序：頭的圓裡一定是頭；手臂的管子裡一定是手臂（側面時手臂壓在身體上，要留給手臂）；
# 軀幹和骨盆的管子裡一定是軀幹（短褲、衣襬不跟著腿動）；剩下的照「距離減半寬」找最近的
HARD_ORDER = ("head", "upper_arm_l", "upper_arm_r", "forearm_l", "forearm_r", "torso", "pelvis")


# 側面看的時候左右腿、左右臂疊在一起：使用者的視圖是平視畫的，遠的那條完全被近的擋住，
# 但骨架是 30 度俯角投影，遠的那條會高十幾個像素。所以只看水平距離，小於兩條半寬和的六成就算疊在一起：
# 整條給近的那一條，遠的那一條用同一張圖、放在同一個位置，動作照它自己的骨頭轉
MERGE_RATIO = 0.6
# 使用者畫的頭下巴比人偶的頭球低，圓往下多拉長這麼多倍
HEAD_CHIN_STRETCH = 1.18
# 左右上臂的深度差超過這麼多公尺，深的那隻算遠臂；正面背面兩隻一樣深，不算
FAR_ARM_DEPTH_M = 0.05
# rig2d.py 出的骨架頭的圓是照視圖量的，不用再放大
FITTED_HEAD_SCALE = 1.04
FITTED_CHIN_STRETCH = 1.0
# 只平移不轉不縮的零件，位移取整到這麼多個工作像素，也就是目標的一格：像素化時零件落在同一個格線上，不會一格清楚一格糊
SNAP_PX = 0
PAIRS = [("upper_arm_l", "upper_arm_r"), ("forearm_l", "forearm_r"), ("thigh_l", "thigh_r"), ("shin_l", "shin_r"),
         ("foot_l", "foot_r")]


def _cuff_fraction(skin, start, end, run=3):
    """沿骨頭中線從肩膀往下走，連續 run 個取樣點都是膚色的第一個位置就是袖口，回傳骨頭長度的比例；沒有膚色回傳 1"""
    steps = 40
    streak = 0
    for i in range(steps + 1):
        t = i / float(steps)
        x = int(round(start[0] + (end[0] - start[0]) * t))
        y = int(round(start[1] + (end[1] - start[1]) * t))
        if 0 <= y < skin.shape[0] and 0 <= x < skin.shape[1] and skin[y, x]:
            streak += 1
            if streak >= run:
                return max(0.0, t - (run - 1) / float(steps))
        else:
            streak = 0
    return 1.0


def _lowest(segments, name):
    (ax, ay), (bx, by), _ = segments[name]
    return max(ay, by)


def segment(canvas, reference, radii, rest=None, merge_arms=False, fitted=False, split=False):
    """每個不透明像素歸給最近的零件：距離是「到骨頭那一段的距離減零件半寬」，頭是一個圓。
    回傳 {零件: {image, offset, start, end}}，座標都是工作解析度"""
    arr = np.asarray(canvas).astype(np.float32)
    alpha = arr[..., 3]
    height, width = alpha.shape
    ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
    names = [n for n in reference if n not in ("head_circle", "bbox")]
    segments = {}
    for name in names:
        ax, ay, bx, by, depth = reference[name]
        if name == "pelvis":
            bx, by = ax + (bx - ax) * PELVIS_STRETCH, ay + (by - ay) * PELVIS_STRETCH
        segments[name] = ((ax * WORK_SCALE, ay * WORK_SCALE), (bx * WORK_SCALE, by * WORK_SCALE), depth)
    # 疊在一起的成對零件：後面那一個不參與分配，之後拿前面那一個的圖
    shadowed = {}
    for left, right in PAIRS:
        if left not in segments or right not in segments:
            continue
        (la, lb, ld), (ra, rb, rd) = segments[left], segments[right]
        apart = (abs(la[0] - ra[0]) + abs(lb[0] - rb[0])) / 2.0
        if apart < MERGE_RATIO * (_radius_of(left, radii) + _radius_of(right, radii)):
            near, far = (left, right) if ld <= rd else (right, left)
            shadowed[far] = near
    active = [n for n in names if n not in shadowed]
    far_arms = set()
    if "upper_arm_l" in segments and "upper_arm_r" in segments:
        dl, dr = segments["upper_arm_l"][2], segments["upper_arm_r"][2]
        if abs(dl - dr) > FAR_ARM_DEPTH_M:
            side = "l" if dl > dr else "r"
            far_arms = {"upper_arm_" + side, "forearm_" + side}
    distances = []
    for name in active:
        if name == "head":
            cx, cy, r = [v * WORK_SCALE for v in reference["head_circle"]]
            chin = FITTED_CHIN_STRETCH if fitted else HEAD_CHIN_STRETCH
            dy = np.where(ys > cy, (ys - cy) / chin, ys - cy)
            d = np.hypot(xs - cx, dy) - r * (FITTED_HEAD_SCALE if fitted else HEAD_CIRCLE_SCALE)
            distances.append(np.where(d < 0, -1e6, d))
            continue
        (ax, ay), (bx, by), _ = segments[name]
        if name.startswith("upper_arm"):
            # 遠臂和正面背面照舊空出肩膀；斜向近鏡頭那隻只空一點，舉手時整截袖子跟著走，肩上不會留一片袖子碎片
            trim = NEAR_ARM_TRIM if (far_arms and name not in far_arms) else UPPER_ARM_TRIM
            if V2_LIMBS and split and name not in far_arms:
                # 舉手的動作整截袖子跟著上臂走，肩上不留袖子碎片（2026-09-27 第 2 輪 n、nw、s 攻擊）
                trim = 0.0
            ax, ay = ax + (bx - ax) * trim, ay + (by - ay) * trim
        vx, vy = bx - ax, by - ay
        length2 = max(vx * vx + vy * vy, 1e-6)
        t = np.clip(((xs - ax) * vx + (ys - ay) * vy) / length2, 0.0, 1.0)
        px, py = ax + t * vx, ay + t * vy
        d = np.hypot(xs - px, ys - py) - _radius_of(name, radii)
        if name in ("torso", "pelvis"):
            # 軀幹和骨盆比腿粗很多，照「距離減半寬」算，胯下那一截腿會被短褲的管子搶走；那一段最低那一列以下不給它們
            d = np.where(ys > _lowest(segments, name), 1e6, d)
        distances.append(d)
    stack = np.stack(distances, axis=0)
    owner = np.argmin(stack, axis=0)
    # 斜向和側面遠的那隻手臂在畫裡多半被身體擋住，管子裡是衣服不是手臂；讓它優先，一擺手就帶走一塊白衣服，
    # 變成身體旁邊一片沒有描邊的白影（2026-09-27 Nora 審到的第二隻手臂白影）。遠臂不走硬規則，軀幹管子裡的一律歸軀幹
    # 硬規則：照 HARD_ORDER 由後往前蓋，排前面的最後蓋所以優先
    for name in reversed(HARD_ORDER):
        if name not in active or name in far_arms:
            continue
        index = active.index(name)
        inside = stack[index] <= 0
        if name in ("pelvis", "torso"):
            # 軀幹和骨盆的管子兩頭是圓的，底下那個半圓會蓋到大腿；硬規則只到那一段最低的那一列，再往下照最近的分
            inside &= ys <= _lowest(segments, name)
        owner = np.where(inside, index, owner)
    if "torso" in active:
        torso_index = active.index("torso")
        in_torso = stack[torso_index] <= 0
        rgb = arr[..., :3]
        cloth_colour = ((rgb[..., 0] - rgb[..., 2]) <= 12) & (rgb.mean(axis=2) > 110)
        for name in far_arms:
            if name in active:
                owner = np.where((owner == active.index(name)) & in_torso, torso_index, owner)
                # 遠臂身上衣服顏色的像素也還給軀幹：遠臂的袖子在畫裡貼著身體，一擺手就在肩膀外甩出一塊白
                if V2_LIMBS:
                    owner = np.where((owner == active.index(name)) & cloth_colour, torso_index, owner)
    # 手臂管子裡顏色不像手臂的外圈像素還給軀幹，見 ARM_COLOR_CORE
    if "torso" in active:
        torso_index = active.index("torso")
        for name in active:
            if not (name.startswith("upper_arm") or name.startswith("forearm")):
                continue
            index = active.index(name)
            radius = _radius_of(name, radii)
            inside = (owner == index) & (alpha > 200)
            core = inside & (stack[index] <= -radius * (1.0 - ARM_COLOR_CORE))
            if core.sum() < 8:
                continue
            limb_color = np.median(arr[core][:, :3], axis=0)
            colour_distance = np.abs(arr[..., :3] - limb_color).sum(axis=2)
            # 墨線留在手臂上：還給軀幹的話手一舉，原地留下一條手臂形狀的黑線
            give_back = inside & ~core & (colour_distance > ARM_COLOR_DISTANCE) & (arr[..., :3].mean(axis=2) > 110)
            owner = np.where(give_back, torso_index, owner)
    # 手臂只拿到袖口：上臂身上衣服顏色的像素只留袖口以上那一截，前臂一顆衣服色都不拿。
    # 正面看手臂垂在身體旁邊，骨頭那根管子會蓋到衣服側邊，第 1 輪舉手時一整條白色的衣服跟著手臂飛起來
    if V2_LIMBS and "torso" in active:
        torso_index = active.index("torso")
        rgb = arr[..., :3]
        cloth_colour = ((rgb[..., 0] - rgb[..., 2]) <= 12) & (rgb.mean(axis=2) > 110)
        skin_colour = ((rgb[..., 0] - rgb[..., 2]) > 12) & (rgb.mean(axis=2) > 110)
        for name in active:
            if name in far_arms or not name.startswith(("upper_arm", "forearm")):
                continue
            index = active.index(name)
            if name.startswith("forearm"):
                owner = np.where((owner == index) & cloth_colour, torso_index, owner)
                continue
            (ax, ay), (bx, by), _ = segments[name]
            cuff = _cuff_fraction(skin_colour, (ax, ay), (bx, by))
            vx, vy = bx - ax, by - ay
            t = ((xs - ax) * vx + (ys - ay) * vy) / max(vx * vx + vy * vy, 1e-6)
            owner = np.where((owner == index) & cloth_colour & (t > cuff), torso_index, owner)
            if split:
                # 舉手的動作：袖子整截是上臂的，從肩膀到袖口、手臂全寬再寬一點的範圍裡的衣服色都給上臂
                px_, py_ = ax + np.clip(t, 0.0, 1.0) * vx, ay + np.clip(t, 0.0, 1.0) * vy
                reach = radii.get("upper_arm", 0.0) * WORK_SCALE * SLEEVE_WIDTH
                sleeve = cloth_colour & (t >= -0.05) & (t <= cuff + 0.08) & (np.hypot(xs - px_, ys - py_) <= reach)
                owner = np.where(sleeve & ((owner == torso_index) | (owner == index)), index, owner)
    # 手臂只拿填色，不拿墨線：手臂四周畫的線全部拿掉，軀幹那邊用衣服色補底，手臂自己另外描一圈線（ARM_RING_PX）。
    # 以前手臂帶著線走，貼著衣服的那幾段線也被帶走，手一動就飄出一條條弧線；線留在軀幹上又是一條手臂形狀的鬼影
    arm_lines = np.zeros(owner.shape, dtype=bool)
    if V2_LIMBS and "torso" in active:
        dark = arr[..., :3].mean(axis=2) <= 90
        from PIL import ImageFilter as _filter
        arm_fill = np.zeros(owner.shape, dtype=bool)
        for name in active:
            if name.startswith(("upper_arm", "forearm")):
                arm_fill |= (owner == active.index(name)) & ~dark & (alpha > 200)
        reach = np.asarray(Image.fromarray((arm_fill * 255).astype(np.uint8)).filter(_filter.MaxFilter(ARM_RING_PX * 2 + 3))) > 0
        keep = np.zeros(owner.shape, dtype=bool)
        for name in ("head",):
            if name in active:
                keep |= owner == active.index(name)
        arm_lines = dark & reach & (alpha > 0) & ~keep
        # 手臂裡面的線（手指、袖口）留給手臂：四周七成以上是那隻手臂的填色就算裡面
        best_count = np.zeros(owner.shape, dtype=np.float32)
        best_index = np.full(owner.shape, -1, dtype=np.int64)
        window = 9
        for name in active:
            if not name.startswith(("upper_arm", "forearm")):
                continue
            index = active.index(name)
            fill_here = ((owner == index) & ~dark & (alpha > 200)).astype(np.float32)
            count = np.asarray(Image.fromarray((fill_here * 255).astype(np.uint8)).filter(_filter.BoxBlur(window // 2))).astype(np.float32) / 255.0
            better = count > best_count
            best_count = np.where(better, count, best_count)
            best_index = np.where(better, index, best_index)
        interior = arm_lines & (best_count >= 0.55)
        owner = np.where(interior, best_index, owner)
        arm_lines &= ~interior
        owner = np.where(arm_lines, -1, owner)
    # 大腿上半截是短褲的顏色時還給軀幹：短褲的褲管跟著腿走，一跨步就撕下一塊白布掛在腿上。
    # 腿的顏色取同一邊小腿的核心
    if "torso" in active:
        torso_index = active.index("torso")
        for side in ("l", "r"):
            thigh, shin = "thigh_" + side, "shin_" + side
            if thigh not in active or shin not in active:
                continue
            ti, si = active.index(thigh), active.index(shin)
            shin_core = (owner == si) & (alpha > 200) & (stack[si] <= -_radius_of(shin, radii) * 0.4)
            if shin_core.sum() < 8:
                continue
            leg_colour = np.median(arr[shin_core][:, :3], axis=0)
            colour_distance = np.abs(arr[..., :3] - leg_colour).sum(axis=2)
            (ax, ay), (bx, by), _ = segments[thigh]
            upper = ys < (ay + by) / 2.0 + abs(by - ay) * 0.25
            # 墨線留在腿上，不然腿的外框被一起拿走；小腿頂端壓到褲管下緣的也一樣還給軀幹
            cloth = (colour_distance > ARM_COLOR_DISTANCE) & (arr[..., :3].mean(axis=2) > 110)
            hem = ys < _lowest(segments, "pelvis") + abs(by - ay) * 0.35 if "pelvis" in segments else upper
            # 近的那條腿：褲管整截跟著大腿走，像褲子一樣；以前照顏色一顆一顆還給軀幹，跨步時褲管下緣留一排流蘇。
            # 只把壓到褲管下緣的小腿頂端還給大腿那一截，照腿的剪影分，不照顏色
            if V2_LIMBS:
                give = np.zeros_like(owner, dtype=bool)
                owner = np.where((owner == si) & hem & cloth, ti, owner)
            else:
                # 第 1 輪的做法：大腿上半和褲管下緣照顏色還給軀幹，眾數濾一次
                give = ((owner == ti) & upper | (owner == si) & hem) & cloth
                from PIL import ImageFilter as _filter
                give = np.asarray(Image.fromarray((give * 255).astype(np.uint8)).filter(_filter.ModeFilter(9))) > 127
                give &= (owner == ti) | (owner == si)
            other = "thigh_" + ("r" if side == "l" else "l")
            if other in segments and segments[thigh][2] - segments[other][2] > FAR_ARM_DEPTH_M:
                # 遠的那條腿在畫裡被近腿和褲管擋住大半，它身上凡是衣服的顏色都是褲管，全部留給軀幹
                give |= ((owner == ti) | (owner == si)) & cloth
            owner = np.where(give, torso_index, owner)
    # 肢體往根部的關節補一段圓頭：從起點往反方向延伸的一小段管子，填肢體自己在關節附近的中位色
    extensions = {}
    for name in active:
        ratio = JOINT_EXTEND_RATIO.get(name.rsplit("_", 1)[0], 0.0)
        if ratio <= 0.0:
            continue
        (ax, ay), (bx, by), _ = segments[name]
        radius = _radius_of(name, radii)
        length = math.hypot(bx - ax, by - ay)
        if length < 1e-6 or radius <= 0.0:
            continue
        ux, uy = (bx - ax) / length, (by - ay) / length
        reach = radius * ratio
        ex, ey = ax - ux * reach, ay - uy * reach
        vx, vy = ax - ex, ay - ey
        length2 = max(vx * vx + vy * vy, 1e-6)
        t = np.clip(((xs - ex) * vx + (ys - ey) * vy) / length2, 0.0, 1.0)
        px, py = ex + t * vx, ey + t * vy
        extensions[name] = np.hypot(xs - px, ys - py) <= radius
    parts = {}
    from PIL import ImageFilter
    grow = PART_OVERLAP_PX * WORK_SCALE * 2 + 1
    inner = np.asarray(Image.fromarray(((alpha >= 250) * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(CAP_INSET_PX * 2 + 1))) > 0
    for index, name in enumerate(active):
        mask = (owner == index) & (alpha > 0)
        if not mask.any():
            continue
        part = arr.copy()
        if name in extensions:
            # 關節附近這個零件自己的像素取中位色，圓頭那段全部填這個顏色、不透明
            (ax, ay), _, _ = segments[name]
            radius = _radius_of(name, radii)
            # 墨線不算：腳踝那一圈多半是描邊，拿進來中位色會是黑的，圓頭補出來是一團黑影
            bright = arr[..., :3].mean(axis=2) > 90
            near_joint = mask & (np.hypot(xs - ax, ys - ay) <= radius * 1.5) & (alpha > 200) & bright
            if near_joint.sum() >= 8:
                fill = np.median(arr[near_joint][:, :3], axis=0)
                # 圓頭只補在剪影裡面、離邊緣的墨線有一段距離的地方：以前用 alpha > 0，縮圖留下的淡邊被補成不透明的膚色，
                # 就是手臂腿旁邊的粉色毛邊；更早補到剪影外面，肩膀上多一塊灰
                cap = extensions[name] & ~mask & inner
                part[cap, 0] = fill[0]
                part[cap, 1] = fill[1]
                part[cap, 2] = fill[2]
                part[cap, 3] = 255.0
                alpha_here = np.where(cap, 255.0, alpha)
                mask = mask | cap
            else:
                alpha_here = alpha
        else:
            alpha_here = alpha
        # 往外長幾個像素，和鄰居重疊；重疊的像素兩邊都有，疊起來還是同一張圖
        if V2_LIMBS and name.startswith(("upper_arm", "forearm")):
            # 手臂：填色加自己描的一圈線；和同一條手臂的上一節、下一節相接的地方不描，不然手肘多一條橫線
            fill = mask & (part[..., :3].mean(axis=2) > 90)
            inner_lines = mask & ~fill
            partner = CHAIN_PARENT.get(name) or next((c for c, p_ in CHAIN_PARENT.items() if p_ == name), None)
            joint = np.zeros_like(fill)
            if partner in active:
                joint = np.asarray(Image.fromarray(((owner == active.index(partner)) * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(ARM_RING_PX * 2 + 1))) > 0
            ring = np.asarray(Image.fromarray((fill * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(ARM_RING_PX * 2 + 1))) > 0
            ring &= ~fill & ~joint & ~inner_lines
            part[ring, 0], part[ring, 1], part[ring, 2] = CUT_EDGE_INK
            fill = fill | inner_lines
            # 相接的那一頭照舊往外長一點，關節不露縫
            grown = np.asarray(Image.fromarray((fill * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(grow))) > 0
            seam = grown & joint & (alpha > 0) & ~ring
            mask = fill | ring | seam
            part[..., 3] = np.where(mask, 255.0, 0)
        else:
            grown = np.asarray(Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(grow))) > 0
            mask = grown & (alpha_here > 0)
            part[..., 3] = np.where(mask, alpha_here, 0)
        if not mask.any():
            continue
        ys_, xs_ = np.nonzero(mask)
        x0, y0, x1, y1 = xs_.min(), ys_.min(), xs_.max() + 1, ys_.max() + 1
        crop = Image.fromarray(part[y0:y1, x0:x1].astype(np.uint8), "RGBA")
        (ax, ay), (bx, by), _ = segments[name]
        parts[name] = {"image": crop, "offset": (x0, y0), "start": (ax, ay), "end": (bx, by),
                       "kind": name if name in ("head", "torso", "pelvis") else name.rsplit("_", 1)[0]}
    for far, near in shadowed.items():
        if near not in parts:
            continue
        source = parts[near]
        parts[far] = {"image": source["image"], "offset": source["offset"], "start": source["start"], "end": source["end"],
                      "twin": near, "kind": far.rsplit("_", 1)[0]}
    # 軀幹被肢體蓋住的地方補底色，見 UNDERPAINT_PASSES
    if "torso" in parts and "torso" in active:
        torso_index = active.index("torso")
        torso_radius = _radius_of("torso", radii)
        pelvis_radius = _radius_of("pelvis", radii) if "pelvis" in active else torso_radius
        body_zone = (stack[torso_index] <= torso_radius * 0.15) & (ys <= _lowest(segments, "torso"))
        if "pelvis" in active:
            # 骨盆的管子很寬，垂在褲子兩旁的手也在裡面；只補管子裡面那一圈，手移開露出來的是背景不是一塊灰
            body_zone |= (stack[active.index("pelvis")] <= -pelvis_radius * 0.25) & (ys <= _lowest(segments, "pelvis"))
        covered = arm_lines.copy()
        for index, name in enumerate(active):
            if name.startswith(("upper_arm", "forearm", "thigh", "shin", "foot")):
                covered |= (owner == index) & (alpha > 0)
        holes = covered & body_zone
        if holes.any():
            torso_part = parts["torso"]
            ox, oy = torso_part["offset"]
            base = np.asarray(torso_part["image"]).astype(np.float32)
            full = np.zeros((height, width, 4), dtype=np.float32)
            full[oy:oy + base.shape[0], ox:ox + base.shape[1]] = base
            filled = full[..., 3] > 0
            todo = holes & ~filled
            # 底色只從衣服長進來：墨線和併在軀幹裡的手臂膚色不當種子，不然手一擺開，衣服上留一塊粉紅或一條灰
            seed = filled & (full[..., :3].mean(axis=2) > 110)
            skin_core = np.zeros_like(filled)
            for index, name in enumerate(active):
                if name.startswith("forearm"):
                    skin_core |= (owner == index) & (alpha > 200) & (stack[index] <= -_radius_of(name, radii) * 0.4)
            if skin_core.sum() >= 8:
                skin = np.median(arr[skin_core][:, :3], axis=0)
                seed &= np.abs(full[..., :3] - skin).sum(axis=2) > ARM_COLOR_DISTANCE * 0.5
            for sources in (seed, filled):
                for _ in range(UNDERPAINT_PASSES):
                    if not todo.any():
                        break
                    total = np.zeros((height, width, 3), dtype=np.float32)
                    count = np.zeros((height, width), dtype=np.float32)
                    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        shifted = np.roll(sources, (dy, dx), axis=(0, 1))
                        colour = np.roll(full[..., :3], (dy, dx), axis=(0, 1))
                        total += colour * shifted[..., None]
                        count += shifted
                    grow = todo & (count > 0)
                    full[grow, :3] = total[grow] / count[grow][:, None]
                    full[grow, 3] = 255.0
                    sources |= grow
                    filled |= grow
                    todo &= ~grow
            ys_, xs_ = np.nonzero(full[..., 3] > 0)
            x0, y0, x1, y1 = xs_.min(), ys_.min(), xs_.max() + 1, ys_.max() + 1
            parts["torso"] = {"image": Image.fromarray(full[y0:y1, x0:x1].astype(np.uint8), "RGBA"), "offset": (x0, y0),
                              "start": torso_part["start"], "end": torso_part["end"], "kind": "torso"}
    # 骨盆併進軀幹：同一張圖、同一個起點終點
    if "pelvis" in parts and "torso" in parts:
        torso, pelvis = parts["torso"], parts["pelvis"]
        x0 = min(torso["offset"][0], pelvis["offset"][0]); y0 = min(torso["offset"][1], pelvis["offset"][1])
        x1 = max(torso["offset"][0] + torso["image"].width, pelvis["offset"][0] + pelvis["image"].width)
        y1 = max(torso["offset"][1] + torso["image"].height, pelvis["offset"][1] + pelvis["image"].height)
        merged = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
        merged.alpha_composite(pelvis["image"], (pelvis["offset"][0] - x0, pelvis["offset"][1] - y0))
        merged.alpha_composite(torso["image"], (torso["offset"][0] - x0, torso["offset"][1] - y0))
        parts["torso"] = {"image": merged, "offset": (x0, y0), "start": torso["start"], "end": torso["end"], "kind": "torso"}
        del parts["pelvis"]
    # 動作是相對 rest（Idle 第 0 格）的變化：零件的起點終點換成 rest 的，Idle 第 0 格就是原圖
    # 疊在一起的遠零件用近零件的起點終點，動作骨頭再平移過來，靜止時兩條完全重合
    # 側面：上臂併進軀幹，見 ARM_MERGED_DIRECTIONS
    if merge_arms and "torso" in parts:
        for name in ("upper_arm_l", "upper_arm_r"):
            arm = parts.pop(name, None)
            if arm is None or "twin" in arm:
                continue
            torso = parts["torso"]
            x0 = min(torso["offset"][0], arm["offset"][0]); y0 = min(torso["offset"][1], arm["offset"][1])
            x1 = max(torso["offset"][0] + torso["image"].width, arm["offset"][0] + arm["image"].width)
            y1 = max(torso["offset"][1] + torso["image"].height, arm["offset"][1] + arm["image"].height)
            merged = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
            merged.alpha_composite(torso["image"], (torso["offset"][0] - x0, torso["offset"][1] - y0))
            merged.alpha_composite(arm["image"], (arm["offset"][0] - x0, arm["offset"][1] - y0))
            parts["torso"] = {"image": merged, "offset": (x0, y0), "start": torso["start"], "end": torso["end"], "kind": "torso"}
        for name in ("upper_arm_l", "upper_arm_r"):
            parts.pop(name, None)
    if rest:
        for name, part in parts.items():
            key = part.get("twin", name)
            if key in rest:
                ax, ay, bx, by, _ = rest[key]
                part["start"] = (ax * WORK_SCALE, ay * WORK_SCALE)
                part["end"] = (bx * WORK_SCALE, by * WORK_SCALE)
            if "twin" in part and name in rest and key in rest:
                part["shift"] = ((rest[key][0] - rest[name][0]) * WORK_SCALE, (rest[key][1] - rest[name][1]) * WORK_SCALE)
    return parts


def transform_for(part, posed, start_override=None):
    """零件照參考骨頭到動作骨頭的變換：平移、旋轉，加沿骨頭方向的縮放。
    骨頭在畫面上變短是往鏡頭前縮，零件只沿骨頭方向壓扁、橫向不動，才不會整個變小；頭是球，不縮放。
    start_override 是上一節放好之後的末端，有給就把骨頭平移到那裡再算。
    回傳 (PIL 的 AFFINE 六個數, 零件參考末端放好之後落在哪)"""
    ax, ay, bx, by, _ = posed
    ax, ay, bx, by = ax * WORK_SCALE, ay * WORK_SCALE, bx * WORK_SCALE, by * WORK_SCALE
    sx_, sy_ = part.get("shift", (0.0, 0.0))
    ax, ay, bx, by = ax + sx_, ay + sy_, bx + sx_, by + sy_
    if start_override is not None:
        dx, dy = start_override[0] - ax, start_override[1] - ay
        ax, ay, bx, by = ax + dx, ay + dy, bx + dx, by + dy
    (rx, ry), (sx, sy) = part["start"], part["end"]
    ref_len = math.hypot(sx - rx, sy - ry)
    new_len = math.hypot(bx - ax, by - ay)
    kind = part.get("kind", "")
    scale = 1.0 if ref_len < 1e-6 or kind == "head" else min(LIMB_SCALE_RANGE[1], max(LIMB_SCALE_RANGE[0], new_len / ref_len))
    theta = math.atan2(by - ay, bx - ax) - math.atan2(sy - ry, sx - rx) if ref_len > 1e-6 else 0.0
    theta = (theta + math.pi) % (2.0 * math.pi) - math.pi
    if not POSE_MODE:
        ratio = new_len / ref_len if ref_len > 1e-6 else 1.0
        if abs(theta) > math.pi / 2.0:
            theta = 0.0
        else:
            turn = (ratio - FORESHORTEN_NO_TURN) / (FORESHORTEN_FULL_TURN - FORESHORTEN_NO_TURN)
            theta *= max(0.0, min(1.0, turn))
        limit = ROTATION_LIMIT_DEG.get(kind, 0.0)
        if limit > 0.0:
            theta = max(-math.radians(limit), min(math.radians(limit), theta))
    phi = math.atan2(sy - ry, sx - rx) if ref_len > 1e-6 else 0.0
    # 目的地像素對回零件圖的像素：減目標起點、轉回參考方向、沿骨頭方向除縮放、加參考起點，再減零件圖的偏移
    rot = np.array([[math.cos(-theta), -math.sin(-theta)], [math.sin(-theta), math.cos(-theta)]])
    axis = np.array([[math.cos(phi), -math.sin(phi)], [math.sin(phi), math.cos(phi)]])
    squash = axis @ np.diag([1.0 / scale, 1.0]) @ axis.T
    matrix = squash @ rot
    ox, oy = part["offset"]
    a, b = matrix[0, 0], matrix[0, 1]
    d, e = matrix[1, 0], matrix[1, 1]
    if SNAP_PX and abs(theta) < 1e-4 and abs(scale - 1.0) < 1e-4:
        # 純平移：位移取整到目標的格線
        ax = rx + round((ax - rx) / SNAP_PX) * SNAP_PX
        ay = ry + round((ay - ry) / SNAP_PX) * SNAP_PX
    c = rx - ox - (a * ax + b * ay)
    f = ry - oy - (d * ax + e * ay)
    # 參考末端正向變換過去：反矩陣乘參考向量
    forward = np.linalg.inv(matrix)
    end_vector = forward @ np.array([sx - rx, sy - ry])
    placed_end = (ax + end_vector[0], ay + end_vector[1])
    # 正向變換：參考座標的任何一點放好之後在哪，給併進軀幹的手肘用
    def forward_point(px, py, _forward=forward, _rx=rx, _ry=ry, _ax=ax, _ay=ay):
        v = _forward @ np.array([px - _rx, py - _ry])
        return (_ax + v[0], _ay + v[1])
    return (a, b, c, d, e, f), placed_end, forward_point


def place(canvas, part, affine):
    moved = part["image"].transform(canvas.size, Image.AFFINE, affine, resample=RESAMPLE)
    canvas.alpha_composite(moved)


def _far_near(posed, left, right):
    """回傳 (遠的那一側, 近的那一側) 的字尾，看骨頭的深度，深度大的遠"""
    left_depth = posed[left][4] if left in posed else 0.0
    right_depth = posed[right][4] if right in posed else 0.0
    return ("l", "r") if left_depth > right_depth else ("r", "l")


def layer_sequence(posed):
    """這一格零件由後往前的順序，見 LAYER_ORDER"""
    far_leg, near_leg = _far_near(posed, "thigh_l", "thigh_r")
    far_arm, near_arm = _far_near(posed, "upper_arm_l", "upper_arm_r")
    # 正面背面兩隻手一樣深，兩隻都畫在軀幹前面：當成一遠一近的話，遠的那隻被軀幹補的底色蓋掉，垂著的手上多一塊灰
    level_arms = ("upper_arm_l" in posed and "upper_arm_r" in posed
                  and abs(posed["upper_arm_l"][4] - posed["upper_arm_r"][4]) <= FAR_ARM_DEPTH_M)
    sequence = []
    for slot in LAYER_ORDER:
        if slot == "far_arm":
            if not level_arms:
                sequence += ["forearm_" + far_arm, "upper_arm_" + far_arm]
        elif slot == "far_leg":
            sequence += ["foot_" + far_leg, "shin_" + far_leg, "thigh_" + far_leg]
        elif slot == "near_leg":
            sequence += ["foot_" + near_leg, "shin_" + near_leg, "thigh_" + near_leg]
        elif slot == "torso":
            sequence += ["torso", "pelvis"]
        elif slot == "near_arm":
            if level_arms:
                sequence += ["forearm_" + far_arm, "upper_arm_" + far_arm]
            sequence += ["forearm_" + near_arm, "upper_arm_" + near_arm]
        elif slot == "head":
            sequence += ["head"]
    # 近臂的手舉到頭的高度以上時，手臂要畫在頭前面，不然舉起來的手被頭吃掉
    if "head_circle" in posed and ("forearm_" + near_arm) in posed:
        hand_y = posed["forearm_" + near_arm][3]
        if hand_y < posed["head_circle"][1]:
            for name in ("upper_arm_" + near_arm, "forearm_" + near_arm):
                if name in sequence:
                    sequence.remove(name)
                    sequence.append(name)
    return sequence


def _harden_alpha(frame):
    """像素圖：透明度只留 0 和 255，再包上描邊用的邊框，格子的排法才和描邊過的一樣"""
    pad = aether_sheet.OUTLINE_PX
    arr = np.asarray(frame).copy()
    arr[..., 3] = np.where(arr[..., 3] >= 128, 255, 0).astype(np.uint8)
    canvas = Image.new("RGBA", (frame.width + pad * 2, frame.height + pad * 2), (0, 0, 0, 0))
    canvas.alpha_composite(Image.fromarray(arr, "RGBA"), (pad, pad))
    return canvas


def compose_frame(parts, posed, frame_size, info=None, keep_work=False):
    """疊一格。info 給一個 dict 就把每個零件的變換、放好的末端、正向變換填回去，圖層照同一套放；
    keep_work 是 True 就回傳工作解析度的畫布，不在這裡縮"""
    canvas = Image.new("RGBA", (frame_size[0] * WORK_SCALE, frame_size[1] * WORK_SCALE), (0, 0, 0, 0))
    # 先照鏈的順序算每個零件的變換，下一節接在上一節放好的末端；再照疊序畫
    affines, ends, forwards = {}, {}, {}
    names = [name for name in CHAIN_ORDER if name in parts and name in posed]
    names += [name for name in parts if name in posed and name not in names]
    for name in names:
        parent = CHAIN_PARENT.get(name)
        override = ends.get(parent) if parent else None
        if override is None and parent and parent.startswith("upper_arm") and parent not in parts and "torso" in forwards:
            # 上臂併進軀幹了：手肘就是 rest 的上臂末端經過軀幹的變換
            elbow = parts[name]["start"]
            override = forwards["torso"](elbow[0], elbow[1])
        affines[name], ends[name], forwards[name] = transform_for(parts[name], posed[name], override)
    sequence = [name for name in layer_sequence(posed) if name in affines]
    leftovers = sorted((name for name in affines if name not in sequence), key=lambda n: -posed[n][4])
    for name in leftovers + sequence:
        place(canvas, parts[name], affines[name])
    if info is not None:
        info.update({"affines": affines, "ends": ends, "forwards": forwards, "sequence": leftovers + sequence})
    if keep_work or canvas.size == tuple(frame_size):
        return canvas
    small = canvas.resize(frame_size, Image.LANCZOS)
    return small


def rigid_frame(rest_frame, anchor, rotation_deg, sx, sy):
    """整張圖繞腳底旋轉縮放；先畫到兩倍大的畫布再量外框挪回畫格裡，腳底貼著地。
    直接畫在畫格大小的畫布上，倒下去轉到外面的部分會先被切掉再挪回來"""
    W, H = rest_frame.size
    px, py = anchor
    pad_x, pad_y = W // 2, H // 2
    cos, sin = math.cos(math.radians(rotation_deg)), math.sin(math.radians(rotation_deg))
    a, b = cos / sx, sin / sx
    d, e = -sin / sy, cos / sy
    c = px - (a * (px + pad_x) + b * (py + pad_y))
    f = py - (d * (px + pad_x) + e * (py + pad_y))
    moved = rest_frame.transform((W * 2, H * 2), Image.AFFINE, (a, b, c, d, e, f),
                                 resample=Image.NEAREST if PIXEL_MODE else Image.BICUBIC)
    alpha = np.asarray(moved)[..., 3]
    ys, xs = np.nonzero(alpha > 8)
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if not len(ys):
        return canvas
    floor = py + pad_y
    shift_x, shift_y = 0, 0
    if ys.max() > floor:
        shift_y = int(floor - ys.max())
    if xs.min() < pad_x + 2:
        shift_x = pad_x + 2 - int(xs.min())
    elif xs.max() > pad_x + W - 3:
        shift_x = pad_x + W - 3 - int(xs.max())
    canvas.alpha_composite(moved, (shift_x - pad_x, shift_y - pad_y))
    return canvas


def rigid_action(action, frame, frames, direction, rest_frame, anchor):
    """die 和 sit 的每一格：回傳整張圖的變換結果"""
    if action == "die":
        t = frame / float(max(1, frames - 1))
        fall = t * t
        fx = FACING_X[direction]
        # 側面往背後倒：面向左就往右倒（順時針，畫面上頭往右）；正面背面往畫面左邊倒
        sign = 1.0 if fx < -0.3 else -1.0
        return rigid_frame(rest_frame, anchor, sign * DIE_FALL_DEG * fall, 1.0 + 0.05 * fall, 1.0 - 0.10 * fall)
    if action == "sit":
        return rigid_frame(rest_frame, anchor, 0.0, SIT_SQUASH[0], SIT_SQUASH[1])
    return rest_frame


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("views")
    parser.add_argument("rig")
    parser.add_argument("name")
    parser.add_argument("--candidate", action="store_true")
    parser.add_argument("--debug", default="", help="把切好的零件和每個方向的參考疊圖存到這裡")
    parser.add_argument("--skeleton", action="store_true", help="每一格畫上動作骨架的紅線，查零件跑掉用")
    parser.add_argument("--pixel", action="store_true", help="來源是像素圖：1 倍、最近點、不重畫描邊、輸出標 nearest")
    args = parser.parse_args()
    global PIXEL_MODE, WORK_SCALE, RESAMPLE, VIEW_RESAMPLE
    if args.pixel:
        PIXEL_MODE = True
        WORK_SCALE = 1
        RESAMPLE = Image.NEAREST
        VIEW_RESAMPLE = Image.NEAREST
    with open(os.path.join(args.rig, "rig.json"), encoding="utf-8") as handle:
        rig = json.load(handle)
    frame_size = tuple(rig["frame_size"])
    directions = rig["directions"]
    parts_by_dir = {}
    split_by_dir = {}
    for direction in directions:
        reference = rig["reference"][direction]
        canvas = cut_view(os.path.join(args.views, direction + ".png"), reference["bbox"], frame_size)
        parts_by_dir[direction] = segment(canvas, reference, rig.get("radii", {}), rig.get("rest", {}).get(direction),
                                          merge_arms=direction in ARM_MERGED_DIRECTIONS)
        # 側面另外切一套上臂分開的零件給攻擊用
        split_by_dir[direction] = segment(canvas, reference, rig.get("radii", {}), rig.get("rest", {}).get(direction))             if direction in ARM_MERGED_DIRECTIONS else parts_by_dir[direction]
        if args.debug:
            os.makedirs(args.debug, exist_ok=True)
            tinted = canvas.copy()
            from PIL import ImageDraw
            pen = ImageDraw.Draw(tinted)
            for name, part in parts_by_dir[direction].items():
                pen.line([part["start"], part["end"]], fill=(255, 0, 0, 255), width=3)
            tinted.save(os.path.join(args.debug, "cut_%s.png" % direction))
            for name, part in parts_by_dir[direction].items():
                part["image"].save(os.path.join(args.debug, "part_%s_%s.png" % (direction, name)))
        print("%s：切成 %d 個零件" % (direction, len(parts_by_dir[direction])))
    cells, actions = [], {}
    for action in ORDER:
        if action not in rig["actions"]:
            continue
        block = rig["actions"][action]
        actions[action] = {"start": len(cells), "frames": block["frames"], "fps": block["fps"], "loop": block["loop"]}
        if "hit_frame" in block:
            actions[action]["hit_frame"] = block["hit_frame"]
        for direction in directions:
            rest_posed = rig.get("rest", {}).get(direction)
            rest_frame = compose_frame(parts_by_dir[direction], rest_posed, frame_size) if rest_posed else None
            parts_now = split_by_dir[direction] if action in ARM_SPLIT_ACTIONS else parts_by_dir[direction]
            rows = block["dirs"][direction]
            if POSE_MODE and rest_posed:
                designed = puppet_poses.rows_for(rest_posed, action, block["frames"], direction)
                if designed is not None:
                    rows = designed
            for frame_index, posed in enumerate(rows):
                if action == "die" and rest_frame is not None:
                    frame = rigid_action(action, frame_index, block["frames"], direction, rest_frame, tuple(rig["anchor"]))
                else:
                    frame = compose_frame(parts_now, posed, frame_size)
                if PIXEL_MODE:
                    # 像素圖的描邊畫在圖裡；半透明的像素切成全透明或全不透明，放大看才是乾淨的格子
                    frame = _harden_alpha(frame)
                else:
                    frame = aether_sheet.draw_outline(frame)
                if args.skeleton:
                    from PIL import ImageDraw
                    pen = ImageDraw.Draw(frame)
                    pad = aether_sheet.OUTLINE_PX
                    for name, values in posed.items():
                        if name in ("head_circle", "bbox"):
                            continue
                        ax, ay, bx, by, _ = values
                        pen.line([(ax + pad, ay + pad), (bx + pad, by + pad)], fill=(255, 0, 0, 255), width=1)
                cells.append(frame)
        print("%s：%d 格 × %d 方向" % (action, block["frames"], len(directions)))
    columns = 8
    rows = -(-len(cells) // columns)
    pad = aether_sheet.OUTLINE_PX
    sheet = Image.new("RGBA", (columns * frame_size[0], rows * frame_size[1]), (0, 0, 0, 0))
    for index, cell in enumerate(cells):
        # 描邊會超出畫格一圈，只貼畫格裡的部分，不然腳碰到下緣時描邊會溢到下一列的格子頂上
        trimmed = cell.crop((pad, pad, pad + frame_size[0], pad + frame_size[1]))
        sheet.alpha_composite(trimmed, (index % columns * frame_size[0], index // columns * frame_size[1]))
    out_dir = os.path.abspath(os.path.join(aether_sheet.CANDIDATE_ROOT if args.candidate else aether_sheet.SHIP_ROOT, args.name))
    os.makedirs(out_dir, exist_ok=True)
    sheet_path = os.path.join(out_dir, "sheet.png")
    sheet.save(sheet_path)
    sheet_output.write_import(sheet_path, PROJECT_ROOT, pixel=PIXEL_MODE)
    mask_path = os.path.join(out_dir, "mask.png")
    Image.new("RGB", (max(1, sheet.width // 8), max(1, sheet.height // 8)), (0, 0, 0)).save(mask_path)
    sheet_output.write_import(mask_path, PROJECT_ROOT, pixel=PIXEL_MODE)
    head_attach = {action: {direction: [[row["head"][0], row["head"][1]] for row in rig["actions"][action]["dirs"][direction]]
                            for direction in directions} for action in actions}
    import paperdoll  # 它在檔頭 import 這支，放這裡才不會繞圈
    first = np.asarray(cells[actions["idle"]["start"]].crop((pad, pad, pad + frame_size[0], pad + frame_size[1])))
    first_rows = np.nonzero((first[..., 3] > 127).any(axis=1))[0]
    meta = {"frame_size": list(frame_size), "columns": columns, "pixels_per_meter": 96, "anchor": list(rig["anchor"]),
            "top_row": int(first_rows.min()), "luma_ranges": paperdoll.luma_ranges(first),
            "directions": directions, "filter": "nearest" if PIXEL_MODE else "linear", "layout": "packed", "head_layer": False, "head_width": 0,
            "actions": actions, "head_attach": head_attach,
            "source": {"pipeline": "art_pipeline/characters_v5/puppet_sheet.py", "views": os.path.relpath(args.views, PROJECT_ROOT).replace(os.sep, "/")}}
    with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as handle:
        json.dump(meta, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print("%d 格、%s -> %s" % (len(cells), sheet.size, out_dir))


if __name__ == "__main__":
    main()
