# -*- coding: utf-8 -*-
"""把 AetherAI 生成、使用者挑好的動畫畫格組成遊戲用的身體圖集。用系統的 python 跑，要有 Pillow。

來源全部在 art_source/characters/base_anim/，說明見那裡的 說明.md：
  walk/<方向>/walk_<方向>_f*.png   走路，一個方向一個資料夾，檔名排序就是播放順序
  attack/<方向>/attack_<方向>_f*.png  攻擊，36 格整段放著也行，會自己抽 6 格
  cast/<方向>/cast_<方向>_f*.png      施法
  idle/idle_r<列>_c<欄>.png         站姿轉身圖切出來的格子，IDLE_CELL 說哪一格是哪個方向
方向有 s、sw、w、nw、n 五個，另外三個引擎鏡射。

**每個動作各自量縮放。** 走路那批是放大過的 480x736、攻擊是 88x172 的原始裁切、站姿是 640x360 的格子，
三種來源的像素尺寸差五倍；拿走路量到的縮放套到全部，走路格會放大到只剩腿（2026-09-23 進遊戲看到的就是這樣）。
每個動作用自己正面那批格子的最高點到最低點當身高，縮到 BODY_HEIGHT；五個方向共用同一個縮放，
轉向時角色才不會一格大一格小。

用法：
  python art_pipeline/characters_v5/aether_sheet.py <名稱> [--candidate]
輸出到 assets/generated/sprites/characters/body/<名稱>/；--candidate 放到 placeholder 底下，遊戲用 --body=<名稱> 看。
"""

import argparse
import json
import os
import sys

import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from common import sheet_output  # noqa: E402

PROJECT_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
SOURCE = os.path.join(PROJECT_ROOT, "art_source", "characters", "base_anim")
SHIP_ROOT = os.path.join(PROJECT_ROOT, "assets", "generated", "sprites", "characters", "body")
CANDIDATE_ROOT = os.path.join(PROJECT_ROOT, "assets", "generated", "sprites", "placeholder", "characters", "body")
DIRS = ["s", "sw", "w", "nw", "n"]
FRAME = (176, 232)
ANCHOR = (88, 208)
BODY_HEIGHT = 180
# 站姿轉身圖的列對方向：列 5 正面、列 0 微左轉、列 1 左轉更多、列 2 轉過側面、列 3 正背面；量法見 說明.md
IDLE_CELL = {"s": "idle_r5_c0", "sw": "idle_r0_c0", "w": "idle_r1_c0", "nw": "idle_r2_c0", "n": "idle_r3_c0"}
# 動作、播放參數、要抽幾格。資料夾裡的張數比要抽的多時，從第一格靜止的起手段之後開始等距抽：
# 攻擊那段 AetherAI 給 36 格，前面幾格是站著不動的，用「和第 0 格的差異」找出真正在動的區間再抽
ACTIONS = [
    ("walk", {"fps": 8, "loop": True}, 8),
    ("attack", {"fps": 14, "loop": False, "hit_frame": 3}, 6),
    ("cast", {"fps": 8, "loop": True}, 6),
]
ACTIVE_FLOOR = 0.25
# 指定要哪幾格的動作，覆蓋自動抽。攻擊那段是量出來的：正面剪影的寬度在第 6 格（第一拳伸直）和第 14 格
# （第二拳伸直）兩個高峰，之後是舉拳防禦到 28 格再放下；抽 4 起手、6 第一拳、9 收拳、14 第二拳、18 防禦、26 放下，
# 第二拳落在 hit_frame 3
PICK = {"attack": [4, 6, 9, 14, 18, 26]}
# 沿著剪影重畫的描邊：來源放大過的輪廓只有一兩個像素細、去背後會斷，從 alpha 生成的粗細和顏色才一致
OUTLINE_COLOR = (54, 45, 40)
OUTLINE_PX = 2
WHITE = 238
# 去背邊緣反算用的墨線和紙的亮度，和 monsters_v2/mpuppet.cut_on_white 同一組
INK_LUMA = 60.0
PAPER_LUMA = 250.0
CUT_RING_PX = 4


def cut(image):
    """去背。這個角色穿白衣白褲，不能用「接近白就透明」：從邊緣往內淹水，只有和邊緣連通的白才是背景。
    邊界留一圈半透明，貼到深色背景上才不會有鋸齒白毛邊"""
    patch = np.asarray(image.convert("RGB")).astype(int)
    light = patch.min(2) > WHITE
    height, width = light.shape
    background = np.zeros_like(light)
    background[0, :] = light[0, :]
    background[-1, :] = light[-1, :]
    background[:, 0] = light[:, 0]
    background[:, -1] = light[:, -1]
    while True:
        grown = background.copy()
        grown[1:, :] |= background[:-1, :]
        grown[:-1, :] |= background[1:, :]
        grown[:, 1:] |= background[:, :-1]
        grown[:, :-1] |= background[:, 1:]
        grown &= light
        if np.array_equal(grown, background):
            break
        background = grown
    alpha = np.where(background, 0.0, 1.0)
    ring = (np.asarray(Image.fromarray((background * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(CUT_RING_PX * 2 + 1))) > 0) & ~background
    # 邊緣是墨線和白紙混出來的：照混色反算透明度和墨色，只調淡不改色會在描邊內側留一圈淡粉白，縮小後就是手臂腿旁邊的毛邊
    luma = patch @ np.array([0.299, 0.587, 0.114])
    mix = np.clip((PAPER_LUMA - luma) / (PAPER_LUMA - INK_LUMA), 0.0, 1.0)
    alpha = np.where(ring, np.minimum(alpha, mix), alpha)
    safe = np.maximum(alpha, 1e-3)[..., None]
    unmixed = np.clip((patch - PAPER_LUMA * (1.0 - safe)) / safe, 0.0, 255.0)
    rgb = np.where((ring & (alpha < 1.0))[..., None], unmixed, patch)
    alpha = np.where(alpha < 0.08, 0.0, alpha)
    return Image.fromarray(np.dstack([rgb, alpha * 255.0]).round().astype(np.uint8), "RGBA")


def trim(figure):
    opaque = np.asarray(figure)[..., 3] > 8
    ys, xs = np.nonzero(opaque)
    return figure.crop((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))


def draw_outline(figure):
    """剝掉剪影最外一圈（藏著純白的抗鋸齒像素），再用描邊蓋回去"""
    pad = OUTLINE_PX
    canvas = Image.new("RGBA", (figure.width + pad * 2, figure.height + pad * 2), (0, 0, 0, 0))
    canvas.alpha_composite(figure, (pad, pad))
    out = np.asarray(canvas).copy()
    solid = out[..., 3] > 40
    core = np.asarray(Image.fromarray((solid * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(3))) > 0
    out[..., 3] = np.where(core, out[..., 3], 0)
    grown = np.asarray(Image.fromarray((core * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(pad * 2 + 1))) > 0
    ring = grown & ~core
    out[ring, 0], out[ring, 1], out[ring, 2] = OUTLINE_COLOR
    soft = np.asarray(Image.fromarray((grown * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.6)))
    out[..., 3] = np.maximum(out[..., 3], np.where(ring, soft, 0))
    return Image.fromarray(out, "RGBA")


def load_frames(action, code):
    folder = os.path.join(SOURCE, action, code)
    files = sorted(f for f in os.listdir(folder) if f.startswith("%s_%s_f" % (action, code)) and f.endswith(".png"))
    if not files:
        raise SystemExit("%s 沒有畫格" % folder)
    return [trim(cut(Image.open(os.path.join(folder, f)))) for f in files]


def pick_indices(folder, wanted):
    """從一整段裡挑 wanted 格：算每一格和第 0 格的差異，差異超過最大值四分之一的算在動，
    在動的第一格到最後一格之間等距抽，頭尾都包含"""
    files = sorted(f for f in os.listdir(folder) if f.endswith(".png"))
    frames = [np.asarray(Image.open(os.path.join(folder, f)).convert("L")).astype(int) for f in files]
    diffs = [float(np.abs(frame - frames[0]).mean()) for frame in frames]
    floor = max(diffs) * ACTIVE_FLOOR
    active = [i for i, d in enumerate(diffs) if d > floor]
    if len(active) < wanted:
        active = list(range(len(frames)))
    first, last = active[0], active[-1]
    return [round(first + (last - first) * k / (wanted - 1)) for k in range(wanted)]


def place(figure, scale, cells):
    """縮放、描邊，最低點對到錨點、水平置中，放進一格"""
    width = max(1, round(figure.width * scale))
    height = max(1, round(figure.height * scale))
    figure = draw_outline(figure.resize((width, height), Image.LANCZOS))
    opaque = np.asarray(figure)[..., 3] > 8
    rows = np.nonzero(opaque.any(1))[0]
    cols = np.nonzero(opaque.any(0))[0]
    foot = int(rows.max()) + 1 if len(rows) else figure.height
    mid = int((cols.min() + cols.max()) // 2) if len(cols) else figure.width // 2
    cell = Image.new("RGBA", FRAME, (0, 0, 0, 0))
    cell.alpha_composite(figure, (ANCHOR[0] - mid, ANCHOR[1] - foot))
    if figure.height > FRAME[1] or figure.width > FRAME[0]:
        print("  警告：圖 %dx%d 超出畫格" % (figure.width, figure.height))
    cells.append(cell)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("name")
    parser.add_argument("--candidate", action="store_true")
    parser.add_argument("--source", default="", help="畫格資料夾，預設是素體的 base_anim；reskin.py 換好衣服的套用 art_source/characters/anim_<職業>")
    args = parser.parse_args()
    global SOURCE
    if args.source:
        SOURCE = os.path.abspath(args.source)
    cells, actions = [], {}
    # 站姿：一個方向一格，正面的身高就是 BODY_HEIGHT，其他方向共用這個縮放
    idle = {code: trim(cut(Image.open(os.path.join(SOURCE, "idle", IDLE_CELL[code] + ".png")))) for code in DIRS}
    scale = BODY_HEIGHT / float(idle["s"].height)
    actions["idle"] = {"start": len(cells), "frames": 1, "fps": 6, "loop": True}
    for code in DIRS:
        place(idle[code], scale, cells)
    print("站姿：正面 %d 像素高，縮放 %.3f" % (idle["s"].height, scale))
    for action, info, wanted in ACTIONS:
        frames = {code: load_frames(action, code) for code in DIRS}
        counts = {len(frames[code]) for code in DIRS}
        if len(counts) != 1:
            raise SystemExit("%s 各方向的張數不一樣 %s，要一致" % (action, sorted(counts)))
        if len(frames["s"]) > wanted:
            picked = PICK.get(action) or pick_indices(os.path.join(SOURCE, action, "s"), wanted)
            frames = {code: [frames[code][i] for i in picked] for code in DIRS}
            counts = {wanted}
            print("%s：%d 格裡抽 %s" % (action, len(picked) and max(picked) + 1, picked))
        # 這個動作自己的身高：正面那批格子的最高點到最低點
        height = max(f.height for f in frames["s"])
        action_scale = BODY_HEIGHT / float(height)
        actions[action] = dict({"start": len(cells), "frames": counts.pop()}, **info)
        for code in DIRS:
            for figure in frames[code]:
                place(figure, action_scale, cells)
        print("%s：每個方向 %d 格，正面 %d 像素高，縮放 %.3f" % (action, actions[action]["frames"], height, action_scale))
    columns = next(c for c in range(15, 4, -1) if len(cells) % c == 0)
    rows = len(cells) // columns
    sheet = Image.new("RGBA", (columns * FRAME[0], rows * FRAME[1]), (0, 0, 0, 0))
    for index, cell in enumerate(cells):
        sheet.alpha_composite(cell, (index % columns * FRAME[0], index // columns * FRAME[1]))
    out_dir = os.path.join(CANDIDATE_ROOT if args.candidate else SHIP_ROOT, args.name)
    os.makedirs(out_dir, exist_ok=True)
    sheet_path = os.path.join(out_dir, "sheet.png")
    sheet.save(sheet_path)
    sheet_output.write_import(sheet_path, PROJECT_ROOT, pixel=False)
    # 遮罩全黑代表沒有任何部位要換色，縮成八分之一就好，全尺寸會被當成最大的貼圖算進顯示記憶體
    mask_path = os.path.join(out_dir, "mask.png")
    Image.new("RGB", (max(1, sheet.width // 8), max(1, sheet.height // 8)), (0, 0, 0)).save(mask_path)
    sheet_output.write_import(mask_path, PROJECT_ROOT, pixel=False)
    meta = {"frame_size": list(FRAME), "columns": columns, "pixels_per_meter": 96, "anchor": list(ANCHOR),
            "directions": DIRS, "filter": "linear", "layout": "packed", "head_layer": False, "head_width": 0,
            "actions": actions,
            "source": {"pipeline": "art_pipeline/characters_v5/aether_sheet.py", "frames": "art_source/characters/base_anim"}}
    with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as handle:
        json.dump(meta, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print("%d 格、%d 欄、%s -> %s" % (len(cells), columns, sheet.size, out_dir))


if __name__ == "__main__":
    main()
