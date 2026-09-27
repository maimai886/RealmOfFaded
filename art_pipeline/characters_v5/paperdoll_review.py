# -*- coding: utf-8 -*-
"""紙娃娃送審圖和對齊報表：吃 paperdoll.py 的輸出資料夾，畫給 Nora、Felix 和使用者看的對照圖。

  python art_pipeline/characters_v5/paperdoll_review.py <180 的輸出> <90 的輸出> <送審圖資料夾> --stone 石板.png --grass 草地.png

出的東西：
  1_dressup_石板.png、1_dressup_草地.png         正面和左前各一排：素體、加頭髮、加帽子、拿刀；上面原尺寸，下面四倍最近點
  2_walk_sw_x4.png、2_walk_sw.gif               左前走路 8 格三層全穿，四倍；GIF 一格 125 毫秒，8 格剛好一秒
  3_pixelize.png                                同一格：轉像素前、180 高一比一、90 高放大兩倍，四倍放大
  review_hat_diff.png                           帽子 A 換 B 逐像素差異：紅是變了的像素，其他地方應該一顆都沒變
  review_slot_flips.png                         武器前後換邊的那幾格，換邊前一格和換邊那一格並排
  review_report.json、review_report.md          每格對齊報表
背景是遊戲截圖裡切下來的一塊亮石板、一塊草地，重複鋪滿。
"""

import argparse
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import paperdoll  # noqa: E402

FONT_PATH = os.path.join(HERE, "..", "..", "assets", "vendor", "fonts", "jf-openhuninn-2.1.ttf")
try:
    FONT = ImageFont.truetype(FONT_PATH, 14)
except OSError:
    FONT = None
_text = ImageDraw.ImageDraw.text


def _cjk_text(self, xy, text, fill=None, font=None, **kwargs):
    return _text(self, xy, text, fill=fill, font=font or FONT, **kwargs)


ImageDraw.ImageDraw.text = _cjk_text

WEAR_STEPS = [("素體", []), ("加頭髮", ["hair_back", "hair_front"]), ("加帽子", ["hair_back", "hair_front", "hat_a"]),
              ("拿刀", ["hair_back", "hair_front", "hat_a", "knife"])]


def tile(background, size):
    """背景一塊來回鏡射鋪滿，接縫比較不明顯"""
    bg = Image.open(background).convert("RGBA")
    w, h = bg.size
    block = Image.new("RGBA", (w * 2, h * 2))
    block.paste(bg, (0, 0))
    block.paste(bg.transpose(Image.FLIP_LEFT_RIGHT), (w, 0))
    block.paste(bg.transpose(Image.FLIP_TOP_BOTTOM), (0, h))
    block.paste(bg.transpose(Image.ROTATE_180), (w, h))
    out = Image.new("RGBA", size)
    for y in range(0, size[1], h * 2):
        for x in range(0, size[0], w * 2):
            out.paste(block, (x, y))
    return out


class Set:
    def __init__(self, folder):
        self.folder = folder
        self.body = paperdoll.Atlas(os.path.join(folder, "body"))
        self.layers = {}
        layer_root = os.path.join(folder, "layers")
        for name in sorted(os.listdir(layer_root)):
            self.layers[name] = paperdoll.Atlas(os.path.join(layer_root, name))
        self.frame = tuple(self.body.meta["frame_size"])
        self.anchor = tuple(self.body.meta["anchor"])

    def frame_image(self, wear, action, direction, frame, pad=(0, 0, 0, 0)):
        """pad 是 (左, 上, 右, 下) 多留的邊，頭飾和刀可以超出畫格"""
        size = (self.frame[0] + pad[0] + pad[2], self.frame[1] + pad[1] + pad[3])
        atlases = [self.body] + [self.layers[name] for name in wear]
        return paperdoll.composite(atlases, action, direction, frame, size, (self.anchor[0] + pad[0], self.anchor[1] + pad[1]))


def _font_row(image, texts, cell_w, y, scale=1):
    pen = ImageDraw.Draw(image)
    for i, text in enumerate(texts):
        pen.text((i * cell_w + 6, y), text, fill=(20, 20, 20, 255))


# 角色在 180 畫格裡佔的範圍，裁掉上下左右的空白，放大圖才不會太大
CROP_180 = (24, 4, 152, 224)


def dressup(set180, background, out_path):
    x0, y0, x1, y1 = CROP_180
    cw, ch = x1 - x0, y1 - y0
    rows = ["s", "sw"]
    small = Image.new("RGBA", (cw * 4, ch * 2))
    big = Image.new("RGBA", (cw * 4 * 4, ch * 2 * 4))
    for r, direction in enumerate(rows):
        for c, (_, wear) in enumerate(WEAR_STEPS):
            img = set180.frame_image(wear, "idle", direction, 0).crop(CROP_180)
            small.alpha_composite(img, (c * cw, r * ch))
            big.alpha_composite(img.resize((cw * 4, ch * 4), Image.NEAREST), (c * cw * 4, r * ch * 4))
    label_h = 18
    sheet = Image.new("RGBA", (big.width, label_h + small.height + label_h + big.height), (240, 238, 232, 255))
    bg_small = tile(background, small.size)
    bg_small.alpha_composite(small)
    bg_big = tile(background, big.size)
    bg_big.alpha_composite(big)
    sheet.paste(bg_small, (0, label_h))
    pen = ImageDraw.Draw(sheet)
    pen.text((6, 3), "原尺寸 1:1（180 高）  上排正面 s、下排左前 sw；由左到右：" + "、".join(n for n, _ in WEAR_STEPS), fill=(20, 20, 20, 255))
    pen.text((6, label_h + small.height + 3), "同一張放大四倍，最近點", fill=(20, 20, 20, 255))
    sheet.paste(bg_big, (0, label_h * 2 + small.height))
    sheet.save(out_path)


def walk(set180, background, png_path, gif_path):
    x0, y0, x1, y1 = CROP_180
    cw, ch = x1 - x0, y1 - y0
    wear = ["hair_back", "hair_front", "hat_a", "knife"]
    frames = [set180.frame_image(wear, "walk", "sw", f).crop(CROP_180) for f in range(8)]
    strip = tile(background, (cw * 4 * 8, ch * 4))
    for i, img in enumerate(frames):
        strip.alpha_composite(img.resize((cw * 4, ch * 4), Image.NEAREST), (i * cw * 4, 0))
    strip.save(png_path)
    gif_frames = []
    for img in frames:
        bg = tile(background, (cw * 4, ch * 4))
        bg.alpha_composite(img.resize((cw * 4, ch * 4), Image.NEAREST))
        gif_frames.append(bg.convert("RGB").quantize(colors=255, method=Image.MEDIANCUT, dither=Image.NONE))
    gif_frames[0].save(gif_path, save_all=True, append_images=gif_frames[1:], duration=125, loop=0, disposal=1)


def pixelize_compare(set180, set90, rig, background, out_path):
    """同一格左前站姿三層全穿：工作解析度直接平滑縮成 180（舊做法），180 像素化，90 像素化放大兩倍"""
    wear = ["hair_back", "hair_front", "hat_a", "knife"]
    doll = paperdoll.Doll(rig, paperdoll.DEFAULT_VIEWS, 180)
    posed = rig["rest"]["sw"]
    work, info = doll.compose("idle", "sw", posed)
    specs = [paperdoll.LAYER_LIBRARY[name] for name in wear]
    stack = []
    for spec in specs:
        source = doll.layer_source(spec, "sw")
        if spec.kind == "head":
            stack.append((paperdoll.SLOTS[spec.slot_key]["sw"], doll.place_head_layer(source, info)))
        else:
            img, _, front = doll.place_hand_layer(source, info, "sw", posed)
            stack.append((paperdoll.HAND_SLOTS[spec.slot_key][1 if front else 0], img))
    stack.append((0, work))
    stack.sort(key=lambda item: item[0])
    merged = Image.new("RGBA", work.size, (0, 0, 0, 0))
    for _, img in stack:
        merged.alpha_composite(img)
    smooth = merged.resize(doll.frame, Image.LANCZOS)
    after = set180.frame_image(wear, "idle", "sw", 0)
    half = set90.frame_image(wear, "idle", "sw", 0).resize(set180.frame, Image.NEAREST)
    x0, y0, x1, y1 = CROP_180
    cw, ch = x1 - x0, y1 - y0
    panels = [("轉像素前：平滑縮小，半透明 %d 顆" % int(((np.asarray(smooth)[..., 3] > 0) & (np.asarray(smooth)[..., 3] < 255)).sum()), smooth),
              ("180 高 1:1 像素化", after), ("90 高像素化，放大兩倍", half)]
    label_h = 18
    sheet = Image.new("RGBA", (cw * 4 * 3 + 20, label_h + ch * 4), (240, 238, 232, 255))
    pen = ImageDraw.Draw(sheet)
    for i, (text, img) in enumerate(panels):
        bg = tile(background, (cw * 4, ch * 4))
        bg.alpha_composite(img.crop(CROP_180).resize((cw * 4, ch * 4), Image.NEAREST))
        sheet.paste(bg, (i * (cw * 4 + 10), label_h))
        pen.text((i * (cw * 4 + 10) + 6, 3), text, fill=(20, 20, 20, 255))
    sheet.save(out_path)


def hat_diff(set180, out_path):
    """帽子 A 和 B 各疊一次，逐像素比：變了的地方塗紅；帽子以外只要有一顆變了就是錯"""
    wear = ["hair_back", "hair_front", "knife"]
    rows = []
    stats = {}
    for direction in ("s", "sw", "w", "nw", "n"):
        a = np.asarray(set180.frame_image(wear + ["hat_a"], "idle", direction, 0)).astype(int)
        b = np.asarray(set180.frame_image(wear + ["hat_b"], "idle", direction, 0)).astype(int)
        changed = np.abs(a - b).sum(axis=2) > 0
        hat_a = set180.layers["hat_a"].cell("idle", direction, 0)
        hat_b = set180.layers["hat_b"].cell("idle", direction, 0)
        allowed = np.zeros(changed.shape, dtype=bool)
        for rgba, (ox, oy), _ in (hat_a, hat_b):
            if rgba is None:
                continue
            x, y = set180.anchor[0] + ox, set180.anchor[1] + oy
            region = np.zeros(changed.shape, dtype=bool)
            h, w = rgba.shape[:2]
            ys, xs = np.nonzero(rgba[..., 3] > 0)
            region[np.clip(ys + y, 0, changed.shape[0] - 1), np.clip(xs + x, 0, changed.shape[1] - 1)] = True
            allowed |= region
        stats[direction] = {"changed": int(changed.sum()), "outside_hats": int((changed & ~allowed).sum())}
        vis = np.zeros(a.shape, dtype=np.uint8)
        vis[..., :3] = (a[..., :3] * 0.35 + 150).clip(0, 255).astype(np.uint8)
        vis[..., 3] = 255
        vis[changed] = (220, 30, 30, 255)
        vis[changed & ~allowed] = (20, 20, 255, 255)
        tiles = [Image.fromarray(a.astype(np.uint8), "RGBA"), Image.fromarray(b.astype(np.uint8), "RGBA"), Image.fromarray(vis, "RGBA")]
        row = Image.new("RGBA", (set180.frame[0] * 3 * 3, set180.frame[1] * 3), (200, 200, 200, 255))
        for i, t in enumerate(tiles):
            row.alpha_composite(t.resize((set180.frame[0] * 3, set180.frame[1] * 3), Image.NEAREST), (i * set180.frame[0] * 3, 0))
        rows.append(row)
    sheet = Image.new("RGBA", (rows[0].width, rows[0].height * len(rows) + 20), (240, 238, 232, 255))
    ImageDraw.Draw(sheet).text((6, 4), "每列一個方向：帽子 A、帽子 B、差異（紅是變了的像素，藍是帽子範圍外也變了，應該是 0）", fill=(20, 20, 20, 255))
    for i, row in enumerate(rows):
        sheet.paste(row, (0, 20 + i * row.height))
    sheet.save(out_path)
    return stats


def slot_flips(set180, report, out_path):
    """武器前後換邊的格子：同一個動作同一個方向，前一格和這一格槽位不一樣"""
    wear = ["hair_back", "hair_front", "hat_a", "knife"]
    by_key = {}
    for entry in report["frames"]:
        by_key[(entry["action"], entry["direction"], entry["frame"])] = entry["slots"].get("knife")
    flips = []
    for (action, direction, frame), slot in sorted(by_key.items()):
        if frame > 0 and by_key.get((action, direction, frame - 1)) not in (None, slot):
            flips.append((action, direction, frame, by_key[(action, direction, frame - 1)], slot))
    if not flips:
        return flips
    x0, y0, x1, y1 = CROP_180
    cw, ch = x1 - x0, y1 - y0
    sheet = Image.new("RGBA", (cw * 3 * 2 + 10, (ch * 3 + 18) * len(flips)), (240, 238, 232, 255))
    pen = ImageDraw.Draw(sheet)
    for i, (action, direction, frame, before, after) in enumerate(flips):
        for j, f in enumerate((frame - 1, frame)):
            img = set180.frame_image(wear, action, direction, f).crop(CROP_180).resize((cw * 3, ch * 3), Image.NEAREST)
            bg = Image.new("RGBA", img.size, (170, 180, 160, 255))
            bg.alpha_composite(img)
            sheet.paste(bg, (j * (cw * 3 + 10), i * (ch * 3 + 18) + 18))
        pen.text((6, i * (ch * 3 + 18) + 3), "%s %s 第 %d→%d 格：刀的槽位 %d → %d" % (action, direction, frame - 1, frame, before, after), fill=(20, 20, 20, 255))
    sheet.save(out_path)
    return flips


def alignment(set_, report):
    """每層每格：錨點和身體一樣、偏移是整數、頭上的圖層跟著頭走的誤差、握點、色數、半透明、雜點"""
    body_meta = set_.body.meta
    out = {"anchor_equal": {}, "integer_offsets": {}, "head_follow_px": {}, "grip": {}, "colours_max": {}, "semi": {},
           "speckles": {}, "atlas_bytes": {}, "frames_match": {}}
    for name, atlas in set_.layers.items():
        meta = atlas.meta
        out["anchor_equal"][name] = meta["anchor"] == body_meta["anchor"] and meta["frame_size"] == body_meta["frame_size"]
        out["frames_match"][name] = all(len(meta["cells"][a][d]) == body_meta["actions"][a]["frames"]
                                        for a in body_meta["actions"] for d in body_meta["directions"])
        out["integer_offsets"][name] = all(isinstance(v, int) for a in meta["cells"].values() for d in a.values() for c in d for v in c)
        out["atlas_bytes"][name] = os.path.getsize(os.path.join(set_.folder, "layers", name, "sheet.png"))
    out["atlas_bytes"]["body"] = os.path.getsize(os.path.join(set_.folder, "body", "sheet.png"))
    # 頭上圖層跟著頭：每一格圖層外框中心減掉頭的接點，和同方向站姿第 0 格比；頭沒有轉的格子應該差 0
    head_attach = body_meta["head_attach"]
    for name in ("hair_front", "hair_back", "hat_a", "hat_b"):
        if name not in set_.layers:
            continue
        meta = set_.layers[name].meta
        worst = 0.0
        for action, dirs in meta["cells"].items():
            for direction, cells in dirs.items():
                base = cells_centre(meta["cells"]["idle"][direction][0])
                bx, by, _ = head_attach["idle"][direction][0]
                for f, cell in enumerate(cells):
                    hx, hy, angle = head_attach[action][direction][f]
                    if abs(angle) > 0.5 or cell[2] == 0 or base is None:
                        continue
                    cx, cy = cells_centre(cell)
                    err = max(abs((cx - hx) - (base[0] - bx)), abs((cy - hy) - (base[1] - by)))
                    worst = max(worst, err)
        out["head_follow_px"][name] = round(worst, 2)
    grips = [e["layers"]["knife"]["grip"] for e in report["frames"] if "knife" in e["layers"]]
    if grips:
        out["grip"] = {"frames": len(grips), "near_skin": sum(g["near_skin"] for g in grips),
                       "on_body": sum(g["on_body"] for g in grips), "front": sum(g["front"] for g in grips)}
    for key in ["body"] + list(set_.layers):
        stats = [e["body"] if key == "body" else e["layers"].get(key) for e in report["frames"]]
        stats = [s for s in stats if s]
        if not stats:
            continue
        out["colours_max"][key] = max(s["colours"] for s in stats)
        out["semi"][key] = {"before": sum(s["semi_before"] for s in stats), "after": sum(s["semi_after"] for s in stats)}
        out["speckles"][key] = {"before": sum(s["speckles_before"] for s in stats), "after": sum(s["speckles_after"] for s in stats),
                                "cleaned": sum(s["cleaned"] for s in stats)}
    total_colours = set()
    for atlas in [set_.body] + list(set_.layers.values()):
        arr = atlas.sheet.reshape(-1, 4)
        arr = arr[arr[:, 3] > 0][:, :3]
        total_colours |= {tuple(c) for c in np.unique(arr, axis=0)}
    out["palette_colours_used"] = len(total_colours)
    return out


def cells_centre(cell):
    x, y, w, h, ox, oy, slot = cell
    if w == 0:
        return None
    return (ox + w / 2.0, oy + h / 2.0)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("set180")
    parser.add_argument("set90")
    parser.add_argument("out")
    parser.add_argument("--stone", required=True)
    parser.add_argument("--grass", required=True)
    parser.add_argument("--rig", required=True)
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)
    s180, s90 = Set(args.set180), Set(args.set90)
    with open(args.rig, encoding="utf-8") as handle:
        rig = json.load(handle)
    dressup(s180, args.stone, os.path.join(args.out, "1_dressup_石板.png"))
    dressup(s180, args.grass, os.path.join(args.out, "1_dressup_草地.png"))
    walk(s180, args.stone, os.path.join(args.out, "2_walk_sw_x4.png"), os.path.join(args.out, "2_walk_sw.gif"))
    pixelize_compare(s180, s90, rig, args.stone, os.path.join(args.out, "3_pixelize.png"))
    hat = hat_diff(s180, os.path.join(args.out, "review_hat_diff.png"))
    reports = {}
    for label, set_ in (("180", s180), ("90", s90)):
        with open(os.path.join(set_.folder, "report.json"), encoding="utf-8") as handle:
            report = json.load(handle)
        reports[label] = alignment(set_, report)
        if label == "180":
            reports[label]["slot_flips"] = slot_flips(set_, report, os.path.join(args.out, "review_slot_flips.png"))
    reports["hat_diff"] = hat
    with open(os.path.join(args.out, "review_report.json"), "w", encoding="utf-8") as handle:
        json.dump(reports, handle, ensure_ascii=False, indent=1)
    print(json.dumps(reports, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
