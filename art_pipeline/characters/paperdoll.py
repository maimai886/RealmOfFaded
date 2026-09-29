# -*- coding: utf-8 -*-
"""RO 式紙娃娃：身體和每一層換裝圖層一起算，同一格同一個姿勢、同一個錨點、同一個像素化函式。

一格怎麼做：
1. 身體照 puppet_sheet 的零件疊在工作解析度上，工作解析度是目標像素的整數倍 k
2. 頭上的圖層（前髮、後髮、頭飾上中下）照頭那個零件同一個變換放；手上的圖層（武器、盾）握點貼在前臂放好的末端，
   軸順著前臂轉；死亡是整張倒下，每一層跟身體用同一個旋轉和位移
3. 每一層各自走 pixelize.pixelize：面積平均縮小、透明度切半、鎖 ramps.json、清雜點、一格帶色描邊
4. 身體是整格排的圖集；其他層裁到內容外框，每格記 [x, y, 寬, 高, 左上角相對錨點的 x, y, 槽位]
5. 槽位是整數，身體 0，數字大的畫在前面；同一格兩層同槽位直接報錯

格式寫在 docs/精靈圖規格.md「紙娃娃圖層」，引擎照那一份讀。

用法：
  python art_pipeline/characters/paperdoll.py <輸出資料夾> [--height 180|90] [--views 視圖資料夾] [--rig rig.json]
      [--layers hair,hat_a,knife] [--actions idle,walk,...]
--height 180 是 1 比 1、畫格 176×232；90 是一半的像素、畫格 88×116，遊戲裡放大兩倍顯示。工作畫布兩種一樣大。
"""

import argparse
import json
import math
import os
import sys
import time

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import pixelize  # noqa: E402
import puppet_poses  # noqa: E402
import puppet_sheet  # noqa: E402
import rig2d  # noqa: E402
import testpieces  # noqa: E402
from common import sheet_output  # noqa: E402

PROJECT_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
DEFAULT_VIEWS = os.path.join(PROJECT_ROOT, "art_source", "characters", "male_base", "views")
# 工作解析度：180 高的畫格每一格拆成 WORK×WORK 個工作像素；90 高的目標就是每格 2×WORK
WORK = 4
BASE_FRAME = (176, 232)
BASE_ANCHOR = (88, 208)
BASE_PPM = 96.0
ORDER = ["idle", "walk", "attack", "cast", "hit", "die", "sit", "pickup"]

# 槽位表：身體 0，大的在前。每層每個方向一個數字；武器和盾每一格照手的深度在前後兩個數字之間換。
# 頭髮拆前後：前髮貼在頭上永遠在頭前面；後髮正面斜前在身體後面，側面以後蓋在後頸上。
# 披風正面在後、背面在前；下頭飾蓋臉、中頭飾在下頭飾前、上頭飾最前
SLOTS = {
    "cape": {"s": -30, "sw": -30, "w": -30, "nw": 5, "n": 5},
    "hair_back": {"s": -20, "sw": -20, "w": 10, "nw": 10, "n": 10},
    "hair_front": {"s": 20, "sw": 20, "w": 20, "nw": 20, "n": 20},
    "head_low": {"s": 30, "sw": 30, "w": 30, "nw": 30, "n": 30},
    "head_mid": {"s": 40, "sw": 40, "w": 40, "nw": 40, "n": 40},
    "head_top": {"s": 50, "sw": 50, "w": 50, "nw": 50, "n": 50},
}
HAND_SLOTS = {"weapon": (-10, 60), "shield": (-12, 55)}
# 手比軀幹近這麼多公尺以內算在身體前面，照 puppet_layer 的數字
FRONT_TOLERANCE_M = {"s": 0.15, "sw": 0.10, "w": 0.0, "nw": -0.05, "n": -0.10}
NEAR_HAND_DIRECTIONS = ("w", "sw", "nw")
# 武器順著前臂之外再轉幾度：站著手垂下時刀尖朝前下方，揮的時候跟著前臂
WEAPON_EXTRA_DEG = {"s": 20.0, "sw": 60.0, "w": 80.0, "nw": 60.0, "n": -20.0}
# 找不到手掌遮罩時的退路：握點落在前臂從手肘算起這個比例的位置
GRIP_ALONG = 0.85
# 手掌是前臂零件沿骨頭最後這一段的膚色像素
HAND_SHARE = 0.32
# 頭上每一層量對齊用的固定參考點，相對頭的圓心、以半徑為單位：帽簷中點、髮旋、後髮下緣中點
HEAD_REFERENCE = {"hair_front": (0.0, -1.0), "hair_back": (0.0, 0.75), "head_top": (0.0, -0.5),
                  "head_mid": (0.0, 0.0), "head_low": (0.0, 0.45)}
DIE_FALL_DEG = puppet_sheet.DIE_FALL_DEG
SKIN_RAMPS = ("skin", "skin_base")


class LayerSpec:
    def __init__(self, name, kind, slot_key, ramp=None, dye=None, hat=None):
        self.name, self.kind, self.slot_key, self.ramp, self.dye, self.hat = name, kind, slot_key, ramp, dye, hat


LAYER_LIBRARY = {
    "hair_front": LayerSpec("hair_front", "head", "hair_front", ramp="hair_sand", dye="hair"),
    "hair_back": LayerSpec("hair_back", "head", "hair_back", ramp="hair_sand", dye="hair"),
    "hat_a": LayerSpec("hat_a", "head", "head_top", ramp="cloth_second", hat="A"),
    "hat_b": LayerSpec("hat_b", "head", "head_top", ramp="cloth_main", hat="B"),
    "knife": LayerSpec("knife", "hand", "weapon"),
}


def _near_hand(direction, rest):
    if direction in NEAR_HAND_DIRECTIONS:
        return "forearm_l" if rest["upper_arm_l"][4] <= rest["upper_arm_r"][4] else "forearm_r"
    return "forearm_r"


class Doll:
    def __init__(self, rig, views, height):
        self.rig = rig
        self.height = height
        self.k = WORK * int(round(180.0 / height))
        self.frame = (BASE_FRAME[0] * WORK // self.k, BASE_FRAME[1] * WORK // self.k)
        self.anchor = (BASE_ANCHOR[0] * WORK // self.k, BASE_ANCHOR[1] * WORK // self.k)
        self.ppm = BASE_PPM * WORK / self.k
        self.palette = pixelize.Palette()
        puppet_sheet.WORK_SCALE = WORK
        puppet_sheet.SNAP_PX = self.k
        puppet_sheet.RESAMPLE = Image.BICUBIC
        self.directions = rig["directions"]
        self.parts, self.split = {}, {}
        self.canvas = {}
        for d in self.directions:
            ref = rig["reference"][d]
            canvas = rig2d.cut_to_bbox(os.path.join(views, d + ".png"), ref["bbox"], WORK, BASE_FRAME)
            self.canvas[d] = canvas
            rest = rig["rest"][d]
            merged = d in puppet_sheet.ARM_MERGED_DIRECTIONS
            self.parts[d] = puppet_sheet.segment(canvas, ref, rig["radii"], rest, merge_arms=merged, fitted=True)
            # 舉手的動作另外切一套：整截袖子跟上臂走
            if puppet_sheet.V2_LIMBS or merged:
                self.split[d] = puppet_sheet.segment(canvas, ref, rig["radii"], rest, fitted=True, split=True)
            else:
                self.split[d] = self.parts[d]
        self.work_size = (BASE_FRAME[0] * WORK, BASE_FRAME[1] * WORK)

    # ── 圖層的來源圖，全部在 rest 的座標上 ─────────────────────────
    def layer_source(self, spec, direction):
        ref = self.rig["reference"][direction]
        cx, cy, r = (v * WORK for v in ref["head_circle"])
        ramps = self.palette.ramps
        if spec.name == "hair_front":
            return testpieces.hair_front(self.work_size, (cx, cy, r), direction, ramps[spec.ramp])
        if spec.name == "hair_back":
            return testpieces.hair_back(self.work_size, (cx, cy, r), direction, ramps[spec.ramp])
        if spec.hat:
            return testpieces.hat(self.work_size, (cx, cy, r), direction, spec.hat, ramps[spec.ramp])
        if spec.name == "knife":
            return testpieces.knife(direction, BASE_PPM * WORK, ramps)
        raise KeyError(spec.name)

    # ── 一格 ───────────────────────────────────────────────────
    def poses(self, action, frames, direction):
        rest = self.rig["rest"][direction]
        rows = puppet_poses.rows_for(rest, action, frames, direction)
        return rows if rows is not None else [rest] * frames

    def compose(self, action, direction, posed):
        parts = self.split[direction] if action in puppet_sheet.ARM_SPLIT_ACTIONS else self.parts[direction]
        info = {}
        work = puppet_sheet.compose_frame(parts, posed, BASE_FRAME, info=info, keep_work=True)
        head = dict(parts["head"], offset=(0, 0))
        head_affine, _, head_forward = puppet_sheet.transform_for(head, posed["head"])
        info["head_affine"] = head_affine
        info["head_forward"] = head_forward
        info["parts"] = parts
        return work, info

    def place_head_layer(self, source, info):
        return Image.fromarray(source, "RGBA").transform(self.work_size, Image.AFFINE, info["head_affine"], resample=Image.BICUBIC)

    def hand_mask(self, info, hand):
        """這一格手掌的遮罩，工作解析度：前臂零件放好之後，沿骨頭最後 HAND_SHARE 那一段、膚色的像素"""
        part = info["parts"][hand]
        moved = np.asarray(part["image"].transform(self.work_size, Image.AFFINE, info["affines"][hand], resample=Image.NEAREST))
        alpha = moved[..., 3] > 127
        rgb = moved[..., :3].astype(int)
        skin = alpha & ((rgb[..., 0] - rgb[..., 2]) > 12) & (rgb.mean(axis=2) > 110)
        start = info["forwards"][hand](*part["start"])
        end = info["ends"][hand]
        vx, vy = end[0] - start[0], end[1] - start[1]
        length2 = max(vx * vx + vy * vy, 1e-6)
        ys, xs = np.mgrid[0:self.work_size[1], 0:self.work_size[0]]
        t = ((xs - start[0]) * vx + (ys - start[1]) * vy) / length2
        return skin & (t >= 1.0 - HAND_SHARE), start, end

    def palm_point(self, mask):
        """握點：縮到目標像素之後，手掌佔滿的那些格子裡離整隻手重心最近的那一格的中心，工作解析度。
        直接拿重心的話手掌彎成弧形時重心會落在手外面，第 1 版有三成的格子握點不在手上"""
        if not mask.any():
            return None
        k = self.k
        cover = pixelize.area_downsample(np.dstack([np.zeros(mask.shape + (3,)), mask * 255.0]), k)[..., 3]
        ys, xs = np.nonzero(mask)
        cx, cy = xs.mean() / k, ys.mean() / k
        for level in (0.75, 0.5):
            cand = np.argwhere(cover >= level)
            if len(cand):
                d = (cand[:, 1] + 0.5 - cx) ** 2 + (cand[:, 0] + 0.5 - cy) ** 2
                j, i = cand[d.argmin()]
                return ((i + 0.5) * k, (j + 0.5) * k)
        return None

    def covered_after(self, info, name):
        """這個零件畫完之後，後面的零件蓋住哪裡，工作解析度"""
        sequence = info["sequence"]
        cover = np.zeros((self.work_size[1], self.work_size[0]), dtype=bool)
        if name not in sequence:
            return cover
        for later in sequence[sequence.index(name) + 1:]:
            part = info["parts"][later]
            moved = np.asarray(part["image"].getchannel("A").transform(self.work_size, Image.AFFINE, info["affines"][later], resample=Image.NEAREST))
            cover |= moved > 127
        return cover

    def place_hand_layer(self, source, info, direction, posed):
        """武器放到手上。回傳 dict：image 工作解析度的圖、grip 握點、front 在不在身體前面、hand 手掌遮罩、visible 手露出來的比例。
        握點是手掌遮罩的重心，所以一定落在手上；前後直接看身體這一格前臂畫在軀幹前面還是後面，手被軀幹擋住刀也在後面"""
        figure, grip_src, axis = source
        hand = _near_hand(direction, self.rig["rest"][direction])
        if hand not in info["parts"] or hand not in info["ends"]:
            raise SystemExit("%s 這一格找不到 %s" % (direction, hand))
        mask, start, end = self.hand_mask(info, hand)
        grip = self.palm_point(mask)
        if grip is None:
            grip = (start[0] + (end[0] - start[0]) * GRIP_ALONG, start[1] + (end[1] - start[1]) * GRIP_ALONG)
        angle = math.atan2(end[1] - start[1], end[0] - start[0]) + math.radians(WEAPON_EXTRA_DEG[direction])
        theta = angle - math.radians(axis)
        cos, sin = math.cos(theta), math.sin(theta)
        a, b, d, e = cos, sin, -sin, cos
        c = grip_src[0] - (a * grip[0] + b * grip[1])
        f = grip_src[1] - (d * grip[0] + e * grip[1])
        weapon = np.asarray(figure.transform(self.work_size, Image.AFFINE, (a, b, c, d, e, f), resample=Image.BICUBIC)).copy()
        sequence = info["sequence"]
        front = hand in sequence and "torso" in sequence and sequence.index(hand) > sequence.index("torso")
        hidden = self.covered_after(info, hand)
        visible_hand = mask & ~hidden
        visible = float(visible_hand.sum()) / float(max(1, mask.sum()))
        if front:
            # 手蓋住握把：在工作解析度挖掉，像素化之後武器的描邊會沿著手的邊緣繞，不會留下孤立的墨點
            weapon[visible_hand, 3] = 0
        return {"image": Image.fromarray(weapon, "RGBA"), "grip": grip, "front": bool(front), "hand": mask,
                "visible": visible, "hand_name": hand}

    def rigid(self, image, rotation_deg, sx, sy, shift):
        """整張繞錨點旋轉縮放再平移，工作解析度；shift 由身體那一張算，每層用同一個"""
        W, H = self.work_size
        px, py = BASE_ANCHOR[0] * WORK, BASE_ANCHOR[1] * WORK
        cos, sin = math.cos(math.radians(rotation_deg)), math.sin(math.radians(rotation_deg))
        a, b = cos / sx, sin / sx
        d, e = -sin / sy, cos / sy
        tx, ty = px + shift[0], py + shift[1]
        c = px - (a * tx + b * ty)
        f = py - (d * tx + e * ty)
        return image.transform((W, H), Image.AFFINE, (a, b, c, d, e, f), resample=Image.BICUBIC)

    def rigid_forward(self, rotation_deg, shift):
        """rigid 的正向：原圖的一點倒下去之後在哪，工作解析度"""
        px, py = BASE_ANCHOR[0] * WORK, BASE_ANCHOR[1] * WORK
        cos, sin = math.cos(math.radians(rotation_deg)), math.sin(math.radians(rotation_deg))
        inverse = np.array([[cos, sin], [-sin, cos]])
        forward = np.linalg.inv(inverse)

        def point(x, y):
            v = forward @ np.array([x - px, y - py])
            return (px + shift[0] + v[0], py + shift[1] + v[1])
        return point, math.degrees(math.atan2(forward[1, 0], forward[0, 0]))

    def die_params(self, frame, frames, direction, body_rest):
        t = frame / float(max(1, frames - 1))
        fall = t * t
        fx = puppet_sheet.FACING_X[direction]
        sign = 1.0 if fx < -0.3 else -1.0
        # 只轉不縮：縮放的話頭上的圖層和握點要多記兩個數字，head_attach 只記位置和角度
        rot, sx, sy = sign * DIE_FALL_DEG * fall, 1.0, 1.0
        moved = np.asarray(self.rigid(body_rest, rot, sx, sy, (0, 0)))[..., 3]
        ys, xs = np.nonzero(moved > 8)
        shift = [0, 0]
        W = self.work_size[0]
        floor = BASE_ANCHOR[1] * WORK
        if len(ys):
            if ys.max() > floor:
                shift[1] = floor - int(ys.max())
            margin = 2 * self.k
            if xs.min() < margin:
                shift[0] = margin - int(xs.min())
            elif xs.max() > W - margin:
                shift[0] = W - margin - int(xs.max())
        # 位移取整到目標格線
        shift = [int(round(v / self.k)) * self.k for v in shift]
        return rot, sx, sy, shift


def _crop(rgba):
    alpha = rgba[..., 3] > 0
    if not alpha.any():
        return None
    ys, xs = np.nonzero(alpha)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


# 圖層小圖彼此留幾個像素：鏡頭拉遠走 mipmap 時才不會吃到隔壁那張，和怪物部位的架子一樣
SHELF_GAP_PX = 4


def shelf_pack(cells, width=1024):
    """裁好的格子排進一張圖：照高度由高到低一列一列放。回傳 (圖的寬高, {鍵: (x, y)})"""
    order = sorted(cells, key=lambda key: -cells[key].shape[0])
    x = y = row_h = 0
    places = {}
    for key in order:
        h, w = cells[key].shape[:2]
        if x + w > width:
            x, y, row_h = 0, y + row_h + SHELF_GAP_PX, 0
        places[key] = (x, y)
        x += w + SHELF_GAP_PX
        row_h = max(row_h, h)
    height = y + row_h
    return (width, max(1, height)), places


def _marker(size, point, radius):
    """一顆實心小圓，量參考點跟著變換跑到哪用"""
    ys, xs = np.mgrid[0:size[1], 0:size[0]]
    arr = np.zeros((size[1], size[0], 4), dtype=np.uint8)
    arr[np.hypot(xs - point[0], ys - point[1]) <= radius] = 255
    return Image.fromarray(arr, "RGBA")


def _centroid(image, k):
    """縮到目標像素之後的重心，目標像素座標，格子中心是 0.5"""
    small = pixelize.area_downsample(np.asarray(image), k)[..., 3]
    total = small.sum()
    if total <= 1e-6:
        return None
    ys, xs = np.mgrid[0:small.shape[0], 0:small.shape[1]]
    return float((small * (xs + 0.5)).sum() / total), float((small * (ys + 0.5)).sum() / total)


def luma_ranges(rgba, mask=None, dye=None):
    """和 src/world/sprite_sheet.gd 的 analyze 同一個量法：idle 面向鏡頭第 0 格，遮罩每一區的亮度範圍"""
    solid = rgba[..., 3] >= 128
    luma = (rgba[..., 0] * 0.299 + rgba[..., 1] * 0.587 + rgba[..., 2] * 0.114) / 255.0
    out = {}
    for part, channel in (("hair", 0), ("skin", 1), ("cloth", 2)):
        if mask is None:
            region = solid if part == "cloth" else np.zeros_like(solid)
        else:
            region = solid & (mask[..., channel] > 127)
        if not region.any():
            out[part] = [0.0, 1.0]
            continue
        lo, hi = float(luma[region].min()), float(luma[region].max())
        if hi - lo < 0.02:
            out[part] = [round(lo - 0.3, 4), round(lo + 0.2, 4)]
        else:
            out[part] = [round(lo, 4), round(hi, 4)]
    return out


def body_columns(frame, cells, limit=4096):
    """整格排的欄數：寬高都在 limit 以內，欄數取 8 的倍數裡最小那個"""
    for columns in range(8, 65, 8):
        rows = -(-cells // columns)
        if columns * frame[0] <= limit and rows * frame[1] <= limit:
            return columns
    raise SystemExit("身體 %d 格排不進 %d" % (cells, limit))


def build(out_dir, height, views, rig, layer_names, actions_wanted=None, log=print, write_import_root=None):
    doll = Doll(rig, views, height)
    specs = [LAYER_LIBRARY[name] for name in layer_names]
    sources = {spec.name: {d: doll.layer_source(spec, d) for d in doll.directions} for spec in specs}
    frame, anchor, k = doll.frame, doll.anchor, doll.k
    body_cells, body_actions, head_attach = [], {}, {}
    layer_cells = {spec.name: {} for spec in specs}
    layer_index = {spec.name: {} for spec in specs}
    first_cells = {}
    report = {"height": height, "k": k, "frames": [], "layers": {}}
    actions = [a for a in ORDER if a in rig["actions"] and (not actions_wanted or a in actions_wanted)]
    marker_radius = 0.75 * k
    for action in actions:
        block = rig["actions"][action]
        frames = int(block["frames"])
        body_actions[action] = {"start": len(body_cells), "frames": frames, "fps": block["fps"], "loop": block["loop"]}
        if "hit_frame" in block:
            body_actions[action]["hit_frame"] = block["hit_frame"]
        head_attach[action] = {}
        for direction in doll.directions:
            rows = doll.poses(action, frames, direction)
            head_attach[action][direction] = []
            cx0, cy0, r0 = (v * WORK for v in rig["rest"][direction]["head_circle"])
            if action == "die":
                rest = rig["rest"][direction]
                rest_body, rest_info = doll.compose("idle", direction, rest)
                rest_layers = {}
                for spec in specs:
                    if spec.kind == "head":
                        rest_layers[spec.name] = {"image": doll.place_head_layer(sources[spec.name][direction], rest_info)}
                    else:
                        rest_layers[spec.name] = doll.place_hand_layer(sources[spec.name][direction], rest_info, direction, rest)
            for f in range(frames):
                posed = rows[f]
                if action == "die":
                    rot, sx, sy, shift = doll.die_params(f, frames, direction, rest_body)
                    body_work = doll.rigid(rest_body, rot, sx, sy, shift)
                    forward, head_angle = doll.rigid_forward(rot, shift)
                    head_pt = forward(*rest_info["head_forward"](cx0, cy0))
                    layers_work = {}
                    for name, layer in rest_layers.items():
                        moved = dict(layer)
                        moved["image"] = doll.rigid(layer["image"], rot, sx, sy, shift)
                        if "grip" in layer:
                            moved["grip"] = forward(*layer["grip"])
                            moved["hand"] = np.asarray(doll.rigid(Image.fromarray((layer["hand"] * 255).astype(np.uint8)), rot, sx, sy, shift)) > 127
                        layers_work[name] = moved
                    place_ref = lambda img, fw=forward, ri=rest_info: doll.rigid(doll.place_head_layer(np.asarray(img), ri), rot, sx, sy, shift)
                else:
                    body_work, info = doll.compose(action, direction, posed)
                    layers_work = {}
                    for spec in specs:
                        if spec.kind == "head":
                            layers_work[spec.name] = {"image": doll.place_head_layer(sources[spec.name][direction], info)}
                        else:
                            layers_work[spec.name] = doll.place_hand_layer(sources[spec.name][direction], info, direction, posed)
                    head_pt = info["head_forward"](cx0, cy0)
                    probe = info["head_forward"](cx0 + 100.0, cy0)
                    head_angle = math.degrees(math.atan2(probe[1] - head_pt[1], probe[0] - head_pt[0]))
                    place_ref = lambda img, i=info: doll.place_head_layer(np.asarray(img), i)
                hx, hy = head_pt[0] / k, head_pt[1] / k
                head_attach[action][direction].append([round(hx, 2), round(hy, 2), round(head_angle, 2)])
                body_rgba, body_idx, body_stats = pixelize.pixelize(body_work, k, doll.palette)
                body_stats.update(pixelize.speckle_classes(body_idx, doll.palette))
                body_cells.append(body_rgba)
                entry = {"action": action, "direction": direction, "frame": f, "body": body_stats, "layers": {}}
                slots_here = {"body": (0, "body")}
                for spec in specs:
                    layer = layers_work[spec.name]
                    rgba, idx, stats = pixelize.pixelize(layer["image"], k, doll.palette)
                    stats.update(pixelize.speckle_classes(idx, doll.palette))
                    if spec.kind == "hand":
                        slot = HAND_SLOTS[spec.slot_key][1 if layer["front"] else 0]
                        gx, gy = layer["grip"][0] / k, layer["grip"][1] / k
                        hand_small = pixelize.area_downsample(np.dstack([np.zeros(layer["hand"].shape + (3,)), layer["hand"] * 255.0]), k)[..., 3]
                        gi, gj = int(math.floor(gx)), int(math.floor(gy))
                        inside = 0 <= gj < hand_small.shape[0] and 0 <= gi < hand_small.shape[1]
                        on_palm = bool(inside and hand_small[gj, gi] >= 0.5)
                        reasons = []
                        if not layer["hand"].any():
                            reasons.append("這一格找不到手掌的膚色像素")
                        elif not on_palm:
                            reasons.append("握點那一格手掌只佔 %.0f%%" % (100.0 * (hand_small[gj, gi] if inside else 0.0)))
                        stats["grip"] = {"x": round(gx, 2), "y": round(gy, 2), "on_palm": on_palm, "front": layer["front"],
                                         "hand_visible": round(layer["visible"], 2), "hand": layer["hand_name"], "fail": reasons}
                    else:
                        slot = SLOTS[spec.slot_key][direction]
                        # 參考點：照 head_attach 的位置和角度轉過去算「應該在哪」，和實際畫出來的位置比
                        rx, ry = HEAD_REFERENCE[spec.slot_key]
                        marker = _marker(doll.work_size, (cx0 + rx * r0, cy0 + ry * r0), marker_radius)
                        actual = _centroid(place_ref(marker), k)
                        rad = math.radians(head_angle)
                        ox, oy = rx * r0 / k, ry * r0 / k
                        predicted = (hx + math.cos(rad) * ox - math.sin(rad) * oy, hy + math.sin(rad) * ox + math.cos(rad) * oy)
                        stats["reference"] = {"predicted": [round(predicted[0], 2), round(predicted[1], 2)],
                                              "actual": [round(actual[0], 2), round(actual[1], 2)] if actual else None,
                                              "error_px": round(math.hypot(actual[0] - predicted[0], actual[1] - predicted[1]), 3) if actual else None}
                    # 同一個槽位的鍵是互相替換的候選，例如帽子 A 和帽子 B，一次只會穿一頂；不同的鍵撞到同一個數字才是錯
                    for other, (value, other_key) in slots_here.items():
                        if value == slot and other_key != spec.slot_key:
                            raise SystemExit("%s %s 第 %d 格：%s 和 %s 同一個槽位 %d" % (action, direction, f, spec.name, other, slot))
                    slots_here[spec.name] = (slot, spec.slot_key)
                    box = _crop(rgba)
                    key = (action, direction, f)
                    if key == ("idle", doll.directions[0], 0):
                        first_cells[spec.name] = rgba
                    if box is None:
                        layer_index[spec.name][key] = [0, 0, 0, 0, 0, 0, slot]
                    else:
                        x0, y0, x1, y1 = box
                        layer_cells[spec.name][key] = rgba[y0:y1, x0:x1]
                        layer_index[spec.name][key] = [None, None, x1 - x0, y1 - y0, x0 - anchor[0], y0 - anchor[1], slot]
                    entry["layers"][spec.name] = stats
                entry["slots"] = {name: value for name, (value, _) in slots_here.items()}
                report["frames"].append(entry)
            log("%s %s：%d 格" % (action, direction, frames))
    os.makedirs(out_dir, exist_ok=True)
    # 身體：整格緊密排，欄數讓寬高都在 4096 以內
    columns = body_columns(frame, len(body_cells))
    rows_n = -(-len(body_cells) // columns)
    sheet = np.zeros((rows_n * frame[1], columns * frame[0], 4), dtype=np.uint8)
    for i, cell in enumerate(body_cells):
        x, y = i % columns * frame[0], i // columns * frame[1]
        sheet[y:y + frame[1], x:x + frame[0]] = cell
    body_dir = os.path.join(out_dir, "body")
    os.makedirs(body_dir, exist_ok=True)
    Image.fromarray(sheet, "RGBA").save(os.path.join(body_dir, "sheet.png"), optimize=True)
    first = body_cells[body_actions["idle"]["start"]] if "idle" in body_actions else body_cells[0]
    first_rows = np.nonzero((first[..., 3] > 127).any(axis=1))[0]
    body_meta = {"frame_size": list(frame), "columns": columns, "pixels_per_meter": doll.ppm, "anchor": list(anchor),
                 "directions": doll.directions, "filter": "nearest", "layout": "packed", "head_layer": False, "head_width": 0,
                 "paperdoll": 1, "display_scale": int(round(180.0 / height)),
                 "top_row": int(first_rows.min()) if len(first_rows) else frame[1], "luma_ranges": luma_ranges(first),
                 "actions": body_actions, "head_attach": head_attach,
                 "source": {"pipeline": "art_pipeline/characters/paperdoll.py", "rig": rig.get("source", {}),
                            "work_scale": k, "palette": "assets/generated/sprites/characters/ramps.json"}}
    with open(os.path.join(body_dir, "meta.json"), "w", encoding="utf-8") as handle:
        json.dump(body_meta, handle, ensure_ascii=False, indent=1)
    if write_import_root:
        sheet_output.write_import(os.path.join(body_dir, "sheet.png"), write_import_root, pixel=True)
    report["sizes"] = {"body": os.path.getsize(os.path.join(body_dir, "sheet.png"))}
    report["body_atlas"] = [int(sheet.shape[1]), int(sheet.shape[0])]
    for spec in specs:
        cells = layer_cells[spec.name]
        (w, h), places = shelf_pack(cells)
        atlas = np.zeros((h, w, 4), dtype=np.uint8)
        mask = np.zeros((h, w, 3), dtype=np.uint8)
        channel = {"hair": 0, "skin": 1, "cloth": 2}.get(spec.dye)
        for key, (x, y) in places.items():
            cell = cells[key]
            atlas[y:y + cell.shape[0], x:x + cell.shape[1]] = cell
            if channel is not None:
                mask[y:y + cell.shape[0], x:x + cell.shape[1], channel] = np.where(cell[..., 3] > 0, 255, 0)
            layer_index[spec.name][key][0], layer_index[spec.name][key][1] = x, y
        layer_dir = os.path.join(out_dir, "layers", spec.name)
        os.makedirs(layer_dir, exist_ok=True)
        Image.fromarray(atlas, "RGBA").save(os.path.join(layer_dir, "sheet.png"), optimize=True)
        first_cell = first_cells.get(spec.name, np.zeros((frame[1], frame[0], 4), dtype=np.uint8))
        first_mask = None
        if channel is not None:
            Image.fromarray(mask, "RGB").save(os.path.join(layer_dir, "mask.png"), optimize=True)
            first_mask = np.zeros(first_cell.shape[:2] + (3,), dtype=np.uint8)
            first_mask[..., channel] = np.where(first_cell[..., 3] > 0, 255, 0)
        cells_meta = {a: {d: [layer_index[spec.name][(a, d, f)] for f in range(int(rig["actions"][a]["frames"]))]
                          for d in doll.directions} for a in actions}
        meta = {"kind": "paperdoll_layer", "layer": spec.slot_key, "frame_size": list(frame), "pixels_per_meter": doll.ppm,
                "anchor": list(anchor), "directions": doll.directions, "filter": "nearest", "layout": "cropped",
                "display_scale": int(round(180.0 / height)),
                "actions": {a: {kk: vv for kk, vv in body_actions[a].items() if kk != "start"} for a in actions},
                "cells": cells_meta, "ramp": spec.ramp, "dye": spec.dye, "luma_ranges": luma_ranges(first_cell, first_mask),
                "hides_hair": False, "test_piece": True,
                "source": {"pipeline": "art_pipeline/characters/paperdoll.py", "piece": "testpieces.py %s" % spec.name}}
        with open(os.path.join(layer_dir, "meta.json"), "w", encoding="utf-8") as handle:
            json.dump(meta, handle, ensure_ascii=False, separators=(",", ":"))
        if write_import_root:
            sheet_output.write_import(os.path.join(layer_dir, "sheet.png"), write_import_root, pixel=True)
            if channel is not None:
                sheet_output.write_import(os.path.join(layer_dir, "mask.png"), write_import_root, pixel=True)
        report["sizes"][spec.name] = os.path.getsize(os.path.join(layer_dir, "sheet.png"))
        report["layers"][spec.name] = {"atlas": [w, h], "cells": len(cells)}
    with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False)
    return doll, report


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out")
    parser.add_argument("--height", type=int, default=180, choices=(180, 90))
    parser.add_argument("--views", default=DEFAULT_VIEWS)
    parser.add_argument("--rig", default="", help="rig.json；不給就用 rig2d 當場算")
    parser.add_argument("--layers", default="hair_front,hair_back,hat_a,knife")
    parser.add_argument("--actions", default="")
    parser.add_argument("--write-import", action="store_true", help="輸出在專案裡的時候順便寫 .import，進遊戲看用")
    args = parser.parse_args()
    if args.rig:
        with open(args.rig, encoding="utf-8") as handle:
            rig = json.load(handle)
    else:
        rig = rig2d.build(os.path.abspath(args.views))
    started = time.time()
    _, report = build(args.out, args.height, args.views, rig, [n for n in args.layers.split(",") if n],
                      [a for a in args.actions.split(",") if a] or None,
                      write_import_root=PROJECT_ROOT if args.write_import else None)
    print("做完 %.1f 秒，大小 %s" % (time.time() - started, report["sizes"]))


if __name__ == "__main__":
    main()


# ── 照引擎的規則把一格疊起來，預覽和審查用；引擎端的做法要和這一支一樣 ─────────

class Atlas:
    def __init__(self, folder):
        with open(os.path.join(folder, "meta.json"), encoding="utf-8") as handle:
            self.meta = json.load(handle)
        self.sheet = np.asarray(Image.open(os.path.join(folder, "sheet.png")).convert("RGBA"))

    def cell(self, action, direction, frame):
        """回傳 (RGBA, 左上角相對錨點, 槽位)"""
        meta = self.meta
        d = meta["directions"].index(direction)
        if meta.get("layout") == "cropped":
            x, y, w, h, ox, oy, slot = meta["cells"][action][direction][frame]
            if w == 0:
                return None, (0, 0), slot
            return self.sheet[y:y + h, x:x + w], (ox, oy), slot
        info = meta["actions"][action]
        index = info["start"] + d * info["frames"] + frame
        fw, fh = meta["frame_size"]
        col, row = index % meta["columns"], index // meta["columns"]
        ax, ay = meta["anchor"]
        return self.sheet[row * fh:(row + 1) * fh, col * fw:(col + 1) * fw], (-ax, -ay), 0


def composite(atlases, action, direction, frame, size, anchor):
    """每層照槽位由小到大疊，左上角放在錨點加偏移。size 是畫布大小，anchor 是錨點在畫布上的位置"""
    items = []
    for atlas in atlases:
        rgba, (ox, oy), slot = atlas.cell(action, direction, frame)
        if rgba is not None:
            items.append((slot, rgba, ox, oy))
    items.sort(key=lambda item: item[0])
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    for _, rgba, ox, oy in items:
        canvas.alpha_composite(Image.fromarray(np.ascontiguousarray(rgba), "RGBA"), (anchor[0] + ox, anchor[1] + oy))
    return canvas
