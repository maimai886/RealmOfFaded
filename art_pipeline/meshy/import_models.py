"""
把 Meshy 生的模型整理成遊戲用的擺設：腳底貼地、水平置中、照 models.json 縮到公尺高度、小件的貼圖縮小，
輸出到 assets/generated/models/towns/<城鎮>/<名字>.glb，量到的佔地半徑和高度寫回 models.json 的 measured。
模型的來源和做法見 docs/城鎮建築產線.md。

用法：blender -b --factory-startup --python-exit-code 1 -P art_pipeline/meshy/import_models.py -- <原始資料夾> [城鎮/名字 ...]
原始資料夾底下是 <城鎮>/<名字>/model.glb，由 art_pipeline/meshy/generate.py 下載
"""
import json
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(HERE))
TABLE = os.path.join(HERE, "models.json")
OUT_ROOT = os.path.join(PROJECT_ROOT, "assets", "generated", "models", "towns")


def import_one(raw_root, key, spec):
    town, name = key.split("/")
    src = os.path.join(raw_root, town, name, "model.glb")
    if not os.path.exists(src):
        print("[meshy] 沒有 %s" % src)
        return None
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=src)
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    bpy.ops.object.select_all(action="DESELECT")
    for obj in meshes:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    obj.name = name
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    xs = [v.co.x for v in obj.data.vertices]
    ys = [v.co.y for v in obj.data.vertices]
    zs = [v.co.z for v in obj.data.vertices]
    height = max(zs) - min(zs)
    factor = float(spec["height_m"]) / max(height, 1e-6)
    cx, cy, low = (min(xs) + max(xs)) * 0.5, (min(ys) + max(ys)) * 0.5, min(zs)
    for v in obj.data.vertices:
        v.co.x = (v.co.x - cx) * factor
        v.co.y = (v.co.y - cy) * factor
        v.co.z = (v.co.z - low) * factor
    obj.data.update()
    # 貼圖縮小：小件在畫面上只有幾十個像素，2K 貼圖是浪費
    limit = int(spec.get("texture_px", 2048))
    for image in bpy.data.images:
        if image.size[0] > limit:
            image.scale(limit, limit)
    out_dir = os.path.join(OUT_ROOT, town)
    os.makedirs(out_dir, exist_ok=True)
    dst = os.path.join(out_dir, name + ".glb")
    bpy.ops.export_scene.gltf(filepath=dst, export_format="GLB", export_image_format="JPEG", export_jpeg_quality=88)
    half_x = (max(xs) - min(xs)) * 0.5 * factor
    half_y = (max(ys) - min(ys)) * 0.5 * factor
    faces = len(obj.data.polygons)
    print("[meshy] %s 高 %.2f 公尺，佔地半寬 %.2f x %.2f，%d 面" % (key, spec["height_m"], half_x, half_y, faces))
    # Blender 的 y 是 glTF 和 Godot 的 -z，佔地記成遊戲的 [x, z]
    return {"half": [round(half_x, 2), round(half_y, 2)], "faces": faces}


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    raw_root = args[0]
    table = json.load(open(TABLE, encoding="utf-8"))
    keys = args[1:] or list(table["models"])
    for key in keys:
        measured = import_one(raw_root, key, table["models"][key])
        if measured:
            table["models"][key]["measured"] = measured
    with open(TABLE, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(table, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


main()
