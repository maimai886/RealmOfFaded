# -*- coding: utf-8 -*-
"""紙娃娃的圖層：一張畫好的武器或頭飾，照紙偶骨架每一格的接點疊成和身體同畫格同錨點的圖集。
換裝只換這一層，身體不用重做；引擎看 meta 的 order 決定每一格圖層在身體前面還是後面。

用系統的 python 跑，要有 Pillow 和 numpy。

用法：
  python art_pipeline/characters_v5/puppet_layer.py <rig 資料夾> <身體圖集資料夾> <圖.png> <名稱> \\
      [--socket hand_r] [--grip 0.5,0.92] [--axis -90] [--length 0.35] [--angle 0] [--candidate]

  rig 資料夾   puppet_rig.py 輸出的那個，裡面有 rig.json，男女各一份，圖層要照身體那一份的骨架做
  身體圖集     assets/generated/sprites/characters/body/male_novice 這種，畫格、動作、排法全部照它
  圖           一個資料夾，裡面 s、sw、w、nw、n 五張各自畫（正面看的刀是窄的、側面是整片，一張圖轉角度做不到，
               使用者 2026-09-24 退回過）；資料夾裡可以放 layer.json，每個方向各自給 grip、axis、angle、length。
               也可以只給一張 png，那是暫用：正面背面把寬度壓到 45%、斜向 70% 假裝是窄的那一面
               白底或透明底都可以，畫的時候讓它站直：刀尖朝上、握把在下，--axis 說明畫裡的刀尖朝哪
  名稱         輸出到 assets/generated/sprites/characters/layers/<名稱>/，引擎照 model_attachment 找，
               同一件裝備男女骨架不同，名稱後面接 _male、_female 引擎會先找那一份
  --socket     掛在哪個接點：hand_r、hand_l 是前臂末端也就是手，head 是頭球中心
  --grip       握把在圖裡的位置，寬高的比例；這一點會貼在接點上
  --axis       圖裡從握把指向刀尖的方向，度數，右邊是 0、上面是 -90；照畫的圖填
  --length     圖的高度在世界裡幾公尺，照身體的像素密度換算
  --angle      刀尖相對前臂方向再轉幾度，0 就是順著前臂往外指
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
from common import sheet_output  # noqa: E402
import aether_sheet  # noqa: E402
import puppet_poses  # noqa: E402

PROJECT_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
SHIP_ROOT = os.path.join(PROJECT_ROOT, "assets", "generated", "sprites", "characters", "layers")
CANDIDATE_ROOT = os.path.join(PROJECT_ROOT, "assets", "generated", "sprites", "placeholder", "characters", "layers")
WORK_SCALE = 2
# 接點在哪根骨頭的哪一端：(零件名, 起點或終點)
SOCKETS = {"hand_r": ("forearm_r", "end"), "hand_l": ("forearm_l", "end"), "head": ("head", "end")}
# 側面和斜向的武器一律拿在近鏡頭那隻手：面向左邊時右手在身體後面，掛右手整把刀被身體擋住，
# 而且側面攻擊揮的就是近的那隻手。鏡射成面向右邊時刀會換到右手，RO 也是這樣
NEAR_HAND_DIRECTIONS = ("w", "sw", "nw")
# 只有一張圖時每個方向把寬度壓到多少：正面背面看到的是刀刃的側面，很窄
SINGLE_IMAGE_SQUEEZE = {"s": 0.45, "n": 0.45, "sw": 0.7, "nw": 0.7, "w": 1.0}
# 手比軀幹中心遠這麼多公尺以內都算在身體前面。手掛在身側時和軀幹中心幾乎等深，
# 面對鏡頭的方向手在身體前面，容許值放寬；背對鏡頭的方向手在身體後面，要明顯比軀幹近才算前面。和 RO 的做法一樣
FRONT_TOLERANCE_M = {"s": 0.15, "sw": 0.10, "w": 0.0, "nw": -0.05, "n": -0.10}
# 身體整張剛體動的動作：死亡是整個人倒下、坐下是整個人蹲，骨架算的手位置對不上，這幾個動作武器不畫
RIGID_ACTIONS = ("die", "sit")
# 殘影：命中那一格在上一格和這一格之間多畫幾個半透明的武器，動畫的 smear frame，一格就看得出揮的速度
SMEAR_GHOSTS = 3
SMEAR_ALPHA = (0.42, 0.26, 0.12)


def load_image(path):
    """畫好的圖：透明底直接用，白底就淹水去背，然後切到外框"""
    image = Image.open(path)
    if image.mode == "RGBA" and np.asarray(image)[..., 3].min() == 0:
        figure = image
    else:
        figure = aether_sheet.cut(image.convert("RGB"))
    return aether_sheet.trim(figure)


def load_views(path, directions, defaults):
    """回傳 {方向: (圖, 設定)}。path 是資料夾就每個方向一張，缺的方向用 s 或 w 補；是單張 png 就每個方向壓窄當暫用"""
    settings = {}
    if os.path.isdir(path):
        config_path = os.path.join(path, "layer.json")
        config = {}
        if os.path.exists(config_path):
            with open(config_path, encoding="utf-8") as handle:
                config = json.load(handle)
        images = {}
        for direction in directions:
            file_path = os.path.join(path, direction + ".png")
            if os.path.exists(file_path):
                images[direction] = load_image(file_path)
        if not images:
            raise SystemExit("資料夾裡沒有任何方向的圖：" + path)
        out = {}
        for direction in directions:
            image = images.get(direction) or images.get("w") or images.get("s") or next(iter(images.values()))
            merged = dict(defaults)
            merged.update(config.get("*", {}))
            merged.update(config.get(direction, {}))
            out[direction] = (image, merged)
        return out
    single = load_image(path)
    print("只有一張圖，正面背面壓窄當暫用；正式的武器每個方向要各畫一張")
    out = {}
    for direction in directions:
        squeeze = SINGLE_IMAGE_SQUEEZE.get(direction, 1.0)
        image = single if squeeze >= 0.999 else single.resize((max(1, int(round(single.width * squeeze))), single.height), Image.LANCZOS)
        out[direction] = (image, dict(defaults))
    return out


def socket_for(socket, direction, rest):
    """側面和斜向把手的接點換成近鏡頭那隻手；rest 裡深度小的那隻臂比較近"""
    if socket in ("hand_r", "hand_l") and direction in NEAR_HAND_DIRECTIONS and rest:
        near_left = rest["upper_arm_l"][4] <= rest["upper_arm_r"][4]
        return "hand_l" if near_left else "hand_r"
    return socket


def socket_of(row, socket):
    """這一格接點的位置、朝外的方向、深度"""
    part, end = SOCKETS[socket]
    ax, ay, bx, by, depth = row[part]
    if end == "end":
        point, direction = (bx, by), math.atan2(by - ay, bx - ax)
    else:
        point, direction = (ax, ay), math.atan2(ay - by, ax - bx)
    return point, direction, depth


def place(canvas, figure, grip, axis_deg, scale, point, angle):
    """圖的握把貼到接點，圖的軸轉到 angle 那個方向；全部在工作解析度上"""
    gx, gy = grip[0] * figure.width, grip[1] * figure.height
    theta = angle - math.radians(axis_deg)
    cos, sin = math.cos(theta), math.sin(theta)
    # 目的地座標對回圖的像素：減接點、反轉、除縮放、加握把
    a, b = cos / scale, sin / scale
    d, e = -sin / scale, cos / scale
    px, py = point[0] * WORK_SCALE, point[1] * WORK_SCALE
    c = gx - (a * px + b * py)
    f = gy - (d * px + e * py)
    moved = figure.transform(canvas.size, Image.AFFINE, (a, b, c, d, e, f), resample=Image.BICUBIC)
    canvas.alpha_composite(moved)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("rig")
    parser.add_argument("body")
    parser.add_argument("image")
    parser.add_argument("name")
    parser.add_argument("--socket", default="hand_r", choices=sorted(SOCKETS))
    parser.add_argument("--grip", default="0.5,0.92")
    parser.add_argument("--axis", type=float, default=-90.0)
    parser.add_argument("--length", type=float, default=0.35)
    parser.add_argument("--angle", type=float, default=0.0)
    parser.add_argument("--candidate", action="store_true")
    parser.add_argument("--no-smear", action="store_true", help="命中那一格不畫殘影")
    args = parser.parse_args()
    with open(os.path.join(args.rig, "rig.json"), encoding="utf-8") as handle:
        rig = json.load(handle)
    with open(os.path.join(args.body, "meta.json"), encoding="utf-8") as handle:
        body = json.load(handle)
    frame_size = tuple(body["frame_size"])
    columns = int(body["columns"])
    ppm = float(body["pixels_per_meter"])
    directions = list(body["directions"])
    defaults = {"grip": [float(v) for v in args.grip.split(",")], "axis": args.axis, "angle": args.angle, "length": args.length}
    views = load_views(args.image, directions, defaults)
    cells = {}
    order = {}
    for action, info in body["actions"].items():
        block = rig["actions"].get(action)
        if block is None or int(block["frames"]) != int(info["frames"]):
            raise SystemExit("骨架的 %s 和身體圖集的格數對不上，rig 要和身體用同一份" % action)
        order[action] = {}
        for index, direction in enumerate(directions):
            figure, setting = views[direction]
            grip = tuple(float(v) for v in setting["grip"])
            axis, extra_angle, length = float(setting["axis"]), float(setting["angle"]), float(setting["length"])
            scale = length * ppm * WORK_SCALE / float(figure.height)
            rows = block["dirs"][direction]
            # 手的位置要和身體同一套姿勢：puppet_sheet 用 puppet_poses 定的，這裡也用
            rest_posed = rig.get("rest", {}).get(direction)
            if rest_posed:
                designed = puppet_poses.rows_for(rest_posed, action, int(block["frames"]), direction)
                if designed is not None:
                    rows = designed
            order[action][direction] = []
            socket = socket_for(args.socket, direction, rest_posed)
            for frame in range(int(info["frames"])):
                row = rows[frame]
                point, direction_angle, depth = socket_of(row, socket)
                in_front = depth <= row["torso"][4] + FRONT_TOLERANCE_M.get(direction, 0.0)
                order[action][direction].append(1 if in_front else -1)
                canvas = Image.new("RGBA", (frame_size[0] * WORK_SCALE, frame_size[1] * WORK_SCALE), (0, 0, 0, 0))
                if action in RIGID_ACTIONS:
                    cells[int(info["start"]) + index * int(info["frames"]) + frame] = canvas.resize(frame_size, Image.LANCZOS)
                    continue
                hit_frame = info.get("hit_frame")
                if not args.no_smear and hit_frame is not None and frame == int(hit_frame) and frame > 0:
                    # 殘影：從上一格的位置和角度插到這一格，越接近上一格越淡
                    before, before_angle, _ = socket_of(rows[frame - 1], socket)
                    turn = (direction_angle - before_angle + math.pi) % (2.0 * math.pi) - math.pi
                    for ghost in range(SMEAR_GHOSTS):
                        u = (ghost + 1) / float(SMEAR_GHOSTS + 1)
                        ghost_point = (before[0] + (point[0] - before[0]) * u, before[1] + (point[1] - before[1]) * u)
                        ghost_angle = before_angle + turn * u
                        layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
                        place(layer, figure, grip, axis, scale, ghost_point, ghost_angle + math.radians(extra_angle))
                        alpha = layer.getchannel("A").point(lambda v, k=SMEAR_ALPHA[ghost]: int(v * k))
                        layer.putalpha(alpha)
                        canvas.alpha_composite(layer)
                place(canvas, figure, grip, axis, scale, point, direction_angle + math.radians(extra_angle))
                cell = canvas.resize(frame_size, Image.LANCZOS)
                cells[int(info["start"]) + index * int(info["frames"]) + frame] = aether_sheet.draw_outline(cell)
    total = max(cells) + 1
    rows_count = -(-total // columns)
    pad = aether_sheet.OUTLINE_PX
    sheet = Image.new("RGBA", (columns * frame_size[0], rows_count * frame_size[1]), (0, 0, 0, 0))
    for index, cell in cells.items():
        trimmed = cell.crop((pad, pad, pad + frame_size[0], pad + frame_size[1]))
        sheet.alpha_composite(trimmed, (index % columns * frame_size[0], index // columns * frame_size[1]))
    out_dir = os.path.join(CANDIDATE_ROOT if args.candidate else SHIP_ROOT, args.name)
    os.makedirs(out_dir, exist_ok=True)
    sheet_path = os.path.join(out_dir, "sheet.png")
    sheet.save(sheet_path)
    pixel = str(body.get("filter", "")) == "nearest"
    sheet_output.write_import(sheet_path, PROJECT_ROOT, pixel=pixel)
    meta = {"frame_size": list(frame_size), "columns": columns, "pixels_per_meter": ppm, "anchor": list(body["anchor"]),
            "directions": directions, "layout": "packed", "filter": body.get("filter", "linear"), "head_layer": False,
            "actions": {name: dict(info) for name, info in body["actions"].items()}, "order": order,
            "source": {"pipeline": "art_pipeline/characters_v5/puppet_layer.py", "image": os.path.abspath(args.image),
                       "rig": os.path.abspath(args.rig), "body": os.path.abspath(args.body), "socket": args.socket,
                       "per_direction_views": os.path.isdir(args.image), "defaults": defaults}}
    with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as handle:
        json.dump(meta, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    front = sum(1 for action in order.values() for lane in action.values() for value in lane if value > 0)
    print("%d 格、%s，%d 格在身體前面 -> %s" % (total, sheet.size, front, out_dir))


if __name__ == "__main__":
    main()
