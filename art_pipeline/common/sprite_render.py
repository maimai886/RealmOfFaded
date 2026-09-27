import json
import math
import os

import bpy

import config
from common import atlas, pixel, projection, scene


def render_sprite_set(name, facing, poser, animations, frame_px, target_height, supersample=4):
    """
    算出 5 方向 × 每個動作的所有畫格，打包成圖集 PNG 和 meta JSON。
    facing：整個模型的最上層物件，靠它繞 Z 軸轉向
    poser：poser(動作名稱, t) 依 0~1 的時間擺姿勢
    animations：[{"name": "walk", "frames": 8, "fps": 12, "loop": True}, ...]
    supersample：先用幾倍解析度算圖，再縮小做成像素風
    """
    origin = scene.setup_sprite_camera(frame_px, target_height, supersample)
    work_dir = os.path.join(config.BUILD_DIR, name)
    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(config.SPRITES_OUT, exist_ok=True)

    rows = []
    meta_animations = {}
    for anim in animations:
        meta_animations[anim["name"]] = {
            "row": len(rows),
            "frames": anim["frames"],
            "fps": anim["fps"],
            "loop": anim["loop"],
        }
        for direction_index in range(len(config.RENDER_DIRECTIONS)):
            facing.rotation_euler = (0, 0, math.radians(projection.facing_angle_deg(direction_index)))
            row = []
            for frame in range(anim["frames"]):
                poser(anim["name"], _frame_time(anim, frame))
                path = os.path.join(work_dir, "%s_%d_%02d.png" % (anim["name"], direction_index, frame))
                bpy.context.scene.render.filepath = path
                bpy.ops.render.render(write_still=True)
                row.append(pixel.pixelate(atlas.load_png(path), supersample))
            rows.append(row)

    atlas_name = name + ".png"
    atlas.save_png(atlas.pack_grid(rows), os.path.join(config.SPRITES_OUT, atlas_name))
    meta = {
        "name": name,
        "atlas": atlas_name,
        "frame_size": [frame_px, frame_px],
        "origin": origin,
        "px_per_m": config.PX_PER_M,
        "pixel_art": True,
        "directions": config.RENDER_DIRECTIONS,
        "animations": meta_animations,
    }
    with open(os.path.join(config.SPRITES_OUT, name + ".json"), "w") as f:
        json.dump(meta, f, indent=2)
    return meta


def _frame_time(anim, frame):
    # 循環動作最後一格不能等於第一格，單次動作最後一格要停在結束姿勢
    if anim["loop"]:
        return frame / anim["frames"]
    return frame / max(1, anim["frames"] - 1)
