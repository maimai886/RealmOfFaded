"""把模型算成精靈圖集，格式照 docs/精靈圖規格.md

身體和頭分成兩個圖層各自一張圖集，身體的 meta 會記每一格頭部接點的像素位置，
引擎再把頭貼上去。每張圖集旁邊都有同尺寸的換色遮罩，做法是整批換成純色自發光材質重算一次。
"""

import json
import math
import os

import bpy

import blenv
import palette
import pixels
import shot
from common import sheet_output

# 用兩倍解析度算圖再面積縮小，照 docs/美術方向.md 的做法
SUPERSAMPLE = 2
DIRECTIONS = ["s", "sw", "w", "nw", "n"]
OUT_ROOT = os.path.join(blenv.PROJECT_ROOT, "assets", "generated", "sprites", "characters")
WORK = os.path.join(blenv.SHOT_DIR, "_frames")

# 動作表照規格書；source 是要用的 KayKit 動作名稱
ACTIONS = [
    dict(name="idle", source="Idle", frames=4, fps=6, loop=True),
    dict(name="walk", source="Walking_A", frames=8, fps=12, loop=True),
    dict(name="attack", source=None, frames=6, fps=12, loop=False, hit_frame=3),
    dict(name="cast", source="Spellcasting", frames=4, fps=8, loop=True),
    dict(name="hit", source="Hit_A", frames=3, fps=12, loop=False),
    dict(name="die", source="Death_A", frames=6, fps=10, loop=False),
    dict(name="sit", source="Sit_Floor_Idle", frames=1, fps=1, loop=True),
    dict(name="pickup", source="PickUp", frames=4, fps=12, loop=False),
]

# 這些動作頭保持水平：脖子點取胸口起點加固定高度，不跟著胸口前傾。
# 倒地、坐下、撿東西身體真的彎下去，才用真正的頭骨位置
UPRIGHT_HEAD_ACTIONS = {"idle", "walk", "cast", "attack", "hit"}

# 每個職業的攻擊動作要配合武器
ATTACK_BY_JOB = {
    "novice": "1H_Melee_Attack_Stab",
    "swordman": "1H_Melee_Attack_Slice_Diagonal",
    "mage": "Spellcast_Shoot",
    "archer": "2H_Ranged_Shoot",
}


def facing_angle_deg(direction_index):
    """模型預設面向 -Y 也就是面向鏡頭，每往下一個方向順時針轉 45 度

    跟 art_pipeline/common/projection.py 的算法一致，角色和怪物的方向才對得起來
    """
    return -45.0 * direction_index


def _fcurve_range(action):
    lo, hi = None, None
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for curve in bag.fcurves:
                    for key in curve.keyframe_points:
                        frame = key.co[0]
                        lo = frame if lo is None else min(lo, frame)
                        hi = frame if hi is None else max(hi, frame)
    return (lo or 0.0, hi or 1.0)


def _set_time(action, t):
    """把動作裡 0~1 的相對時間換成場景幀數，用小數幀取樣才夠平順"""
    start, end = _fcurve_range(action)
    exact = start + (end - start) * t
    whole = math.floor(exact)
    bpy.context.scene.frame_set(int(whole), subframe=float(exact - whole))


def _frame_time(spec, index):
    # 循環動作最後一格不能等於第一格，單次動作最後一格要停在結束姿勢
    if spec["loop"]:
        return index / spec["frames"]
    return index / max(1, spec["frames"] - 1)


_ID_MATS = None


def _id_mats():
    """材質編號材質，清場景之後舊的參照會失效，失效就重建"""
    global _ID_MATS
    try:
        valid = _ID_MATS is not None and all(m.name in bpy.data.materials for m in _ID_MATS)
    except ReferenceError:
        valid = False
    if not valid:
        _ID_MATS = palette.build_id_materials()
    return _ID_MATS


def _render_pair(color_objects, color_mats, mask_mats, tag):
    """同一個姿勢算彩色圖和遮罩圖各一張，回傳兩個 numpy 陣列

    2026-09-16 起不再算材質編號圖：那張只用來在材質交界補深色內部線條，
    而 docs/美術風格指南.md 這個畫風不畫線，靠形體和明暗分區塊。少一張也快三分之一。
    """
    os.makedirs(WORK, exist_ok=True)
    line = palette.srgb(palette.OUTLINE)
    palette.apply_slot_set(color_objects, color_mats)
    color_raw = pixels.load_png(shot.render_to(os.path.join(WORK, tag + "_c.png")))
    palette.apply_slot_set(color_objects, mask_mats)
    mask_raw = pixels.load_png(shot.render_to(os.path.join(WORK, tag + "_m.png")))
    palette.apply_slot_set(color_objects, color_mats)
    color = pixels.outline(pixels.downsample(color_raw, SUPERSAMPLE), line)
    mask = pixels.finish_mask(mask_raw, SUPERSAMPLE, color)
    return color, mask


# 匯入參數和遮罩要不要輸出都照 art_pipeline/common/sheet_output.py，那裡是三個產圖端的共同規則
# 契約在 docs/精靈圖規格.md，記憶體的數字在 docs/效能與記憶體.md


def write_import(png_path):
    """幫一張圖集寫好 Godot 的 .import，已經有的只改參數段保留 uid"""
    return sheet_output.write_import(png_path, blenv.PROJECT_ROOT)


def _write(out_dir, color_rows, mask_rows, meta, columns):
    os.makedirs(out_dir, exist_ok=True)
    sheet_path = os.path.join(out_dir, "sheet.png")
    sheet_image = pixels.pack_grid(color_rows, shot.FRAME_PX, columns)
    pixels.save_png(sheet_image, sheet_path)
    write_import(sheet_path)
    # 只用到一個通道的遮罩不輸出，引擎會當成整張都是主要區域；兩個以上的縮小再存
    sheet_output.emit_mask(out_dir, sheet_image,
                           pixels.pack_grid(mask_rows, shot.FRAME_PX, columns),
                           shot.FRAME_PX, pixels.save_png, blenv.PROJECT_ROOT)
    with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as handle:
        json.dump(meta, handle, ensure_ascii=False, indent=2)
    return out_dir


def render_body(gender, job, armature, objects, color_mats, mask_mats, rig_module):
    """算一張身體圖集：完整動作 × 5 方向，並記下每一格的頭部接點"""
    shot.setup_scene(transparent=True)
    shot.add_lights()
    camera = shot.make_camera("sprite_cam")
    scene = bpy.context.scene
    scene.render.resolution_x = shot.FRAME_PX * SUPERSAMPLE
    scene.render.resolution_y = shot.FRAME_PX * SUPERSAMPLE

    armature.location = (0, 0, 0)
    head_bone = armature.pose.bones["head"]
    chest_bone = armature.pose.bones["chest"]
    # 胸口骨頭起點到脖子點的垂直距離，走路時拿這個算脖子點，頭才不會跟著胸口前後點頭
    neck_rise = armature.data.bones["head"].head_local.z - armature.data.bones["chest"].head_local.z
    from mathutils import Vector

    color_rows, mask_rows = [], []
    meta_actions, head_attach = {}, {}
    columns = max(spec["frames"] for spec in ACTIONS)

    for spec in ACTIONS:
        source = spec["source"] or ATTACK_BY_JOB[job]
        action = rig_module.set_action(armature, source)
        if action is None:
            print("找不到動作", source, "跳過", spec["name"])
            continue
        entry = {"row": len(color_rows) // len(DIRECTIONS), "frames": spec["frames"],
                 "fps": spec["fps"], "loop": spec["loop"]}
        if "hit_frame" in spec:
            entry["hit_frame"] = spec["hit_frame"]
        meta_actions[spec["name"]] = entry
        head_attach[spec["name"]] = {}

        for direction_index, direction in enumerate(DIRECTIONS):
            armature.rotation_euler = (0, 0, math.radians(facing_angle_deg(direction_index)))
            shot.sprite_camera(camera)
            color_row, mask_row, attach_row = [], [], []
            for frame in range(spec["frames"]):
                _set_time(action, _frame_time(spec, frame))
                bpy.context.view_layer.update()
                tag = "%s_%s_%s_%d_%d" % (gender, job, spec["name"], direction_index, frame)
                color, mask = _render_pair(objects, color_mats, mask_mats, tag)
                color_row.append(color)
                mask_row.append(mask)
                if spec["name"] in UPRIGHT_HEAD_ACTIONS:
                    world = armature.matrix_world @ (chest_bone.head + Vector((0, 0, neck_rise)))
                else:
                    world = armature.matrix_world @ head_bone.head
                pixel = shot.world_to_pixel(camera, world)
                attach_row.append([round(pixel[0], 1), round(pixel[1], 1)])
            color_rows.append(color_row)
            mask_rows.append(mask_row)
            head_attach[spec["name"]][direction] = attach_row

    armature.rotation_euler = (0, 0, 0)
    rig_module.rest_pose(armature)
    meta = {
        "frame_size": [shot.FRAME_PX, shot.FRAME_PX],
        "columns": columns,
        "pixels_per_meter": shot.PIXELS_PER_METER,
        "anchor": [shot.ANCHOR[0], shot.ANCHOR[1]],
        "directions": DIRECTIONS,
        "actions": meta_actions,
        "head_attach": head_attach,
    }
    return _write(os.path.join(OUT_ROOT, "body", "%s_%s" % (gender, job)),
                  color_rows, mask_rows, meta, columns)


def render_head(gender, hair_style, eye_style, armature, head_objects, face_pairs,
                color_mats, mask_mats):
    """算一張頭部圖集：5 方向 × 2 格，第 0 格睜眼、第 1 格眨眼

    face_pairs 是 [(睜眼彩色, 睜眼遮罩), (眨眼彩色, 眨眼遮罩)]，換貼圖就換表情
    """
    shot.setup_scene(transparent=True)
    shot.add_lights()
    camera = shot.make_camera("sprite_cam")
    scene = bpy.context.scene
    scene.render.resolution_x = shot.FRAME_PX * SUPERSAMPLE
    scene.render.resolution_y = shot.FRAME_PX * SUPERSAMPLE
    armature.location = (0, 0, 0)

    face_material = color_mats[palette.SLOT_INDEX["Face"]]
    face_mask_material = mask_mats[palette.SLOT_INDEX["Face"]]
    face_node = next(n for n in face_material.node_tree.nodes if n.type == "TEX_IMAGE")
    mask_node = next(n for n in face_mask_material.node_tree.nodes if n.type == "TEX_IMAGE")

    color_rows, mask_rows = [], []
    for direction_index, direction in enumerate(DIRECTIONS):
        armature.rotation_euler = (0, 0, math.radians(facing_angle_deg(direction_index)))
        shot.head_camera(camera)
        bpy.context.view_layer.update()
        color_row, mask_row = [], []
        for frame, (face_color, face_mask) in enumerate(face_pairs):
            face_node.image = face_color
            mask_node.image = face_mask
            tag = "head_%s_h%d_e%d_%d_%d" % (gender, hair_style, eye_style, direction_index, frame)
            color, mask = _render_pair(head_objects, color_mats, mask_mats, tag)
            color_row.append(color)
            mask_row.append(mask)
        color_rows.append(color_row)
        mask_rows.append(mask_row)

    armature.rotation_euler = (0, 0, 0)
    meta = {
        "frame_size": [shot.FRAME_PX, shot.FRAME_PX],
        "columns": 2,
        "pixels_per_meter": shot.PIXELS_PER_METER,
        "anchor": [shot.HEAD_ANCHOR[0], shot.HEAD_ANCHOR[1]],
        "directions": DIRECTIONS,
        "actions": {"idle": {"row": 0, "frames": 2, "fps": 2, "loop": True}},
    }
    return _write(os.path.join(OUT_ROOT, "head", "%s_h%d_e%d" % (gender, hair_style, eye_style)),
                  color_rows, mask_rows, meta, 2)
