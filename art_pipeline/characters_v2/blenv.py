"""在正在開著的 Blender 裡執行時共用的小工具

透過 art_pipeline/live/bl.py 送進來的程式碼跑在 timer 回呼裡，那個 context 很受限，
bpy.context.object 之類的屬性都拿不到，所以呼叫 operator 前一律用 ui() 做 context override。
另外提供把視窗對準某個物件的 look_at，讓使用者看得到每一步在做什麼。
"""

import os

import bpy

# 專案根目錄從這個檔案的位置推，不寫死哪一台機器的絕對路徑；
# 檢查圖的暫存資料夾可以用環境變數 ROF_SHOT_DIR 蓋掉，預設放在不進版本庫的 _build 底下
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SHOT_DIR = os.environ.get("ROF_SHOT_DIR") or os.path.join(PROJECT_ROOT, "art_pipeline", "_build", "shots_v2")
SRC_DIR = os.path.join(PROJECT_ROOT, "art_source", "characters_v2")
OUT_DIR = os.path.join(PROJECT_ROOT, "assets", "generated", "characters_v2")


def view3d():
    """找出第一個 3D 視窗，回傳 window, area, region"""
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type != "VIEW_3D":
                continue
            for region in area.regions:
                if region.type == "WINDOW":
                    return window, area, region
    return None, None, None


def ui(**extra):
    """給 operator 用的 context override，補齊 window、area、region 和選取狀態"""
    window, area, region = view3d()
    override = {"window": window, "screen": window.screen if window else None,
                "area": area, "region": region,
                "scene": bpy.context.scene, "view_layer": bpy.context.view_layer,
                "collection": bpy.context.view_layer.active_layer_collection.collection,
                "blend_data": bpy.data}
    override = {k: v for k, v in override.items() if v is not None}
    override.update(extra)
    return bpy.context.temp_override(**override)


def run(op, *args, **kwargs):
    """在有效的 context 底下呼叫 operator"""
    with ui():
        return op(*args, **kwargs)


def clear_scene():
    """清空目前的場景資料，重跑腳本時不會留下舊東西"""
    with ui():
        bpy.ops.wm.read_homefile(use_empty=True)


def deselect():
    for obj in list(bpy.context.scene.objects):
        if obj is not None:
            obj.select_set(False)


def select_only(objs):
    """只選取指定物件並設成作用中，回傳第一個"""
    if not isinstance(objs, (list, tuple)):
        objs = [objs]
    deselect()
    for obj in objs:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    return objs[0]


def look_at(objs, shading="MATERIAL"):
    """把 3D 視窗對準這些物件，使用者才看得到目前做到哪一步"""
    window, area, region = view3d()
    if area is None:
        return
    select_only(objs)
    space = area.spaces.active
    space.shading.type = shading
    space.overlay.show_overlays = True
    with bpy.context.temp_override(window=window, screen=window.screen, area=area, region=region,
                                   scene=bpy.context.scene, view_layer=bpy.context.view_layer):
        bpy.ops.view3d.view_selected()
    area.tag_redraw()


def frame_all(shading="MATERIAL"):
    window, area, region = view3d()
    if area is None:
        return
    area.spaces.active.shading.type = shading
    with bpy.context.temp_override(window=window, screen=window.screen, area=area, region=region,
                                   scene=bpy.context.scene, view_layer=bpy.context.view_layer):
        bpy.ops.view3d.view_all()
    area.tag_redraw()


def link(obj):
    bpy.context.view_layer.active_layer_collection.collection.objects.link(obj)
    return obj


def tri_count(obj):
    """三角形數量，四邊形算兩個"""
    total = 0
    for poly in obj.data.polygons:
        total += max(len(poly.vertices) - 2, 1)
    return total
