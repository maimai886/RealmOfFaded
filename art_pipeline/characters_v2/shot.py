"""算圖用的場景設定與檢查圖

彩色圖和遮罩圖都從這裡出，精靈圖和品管檢查圖共用同一套相機與燈光，
檢查圖看到的樣子才等於實際會進遊戲的樣子。
"""

import math
import os

import bpy
from mathutils import Vector

import blenv

# 2026-09-16 解析度加倍：一格 192 px、密度 128 px/m，角色在畫格裡約 162 px 高
# 格子和密度一起加倍，所以 pixel_size 還是 1/128 對應同一個世界尺寸，角色在遊戲裡不會變大變小
# 96 px 那一版刻意壓成像素感，臉糊成一團，現在不做像素化，靠解析度和手繪筆觸撐質感
PIXELS_PER_METER = 128.0
CAMERA_ELEVATION_DEG = 25.0
FRAME_PX = 192
# 腳底在畫格中的像素位置，頭上留 24 px 給武器和帽子
ANCHOR = (96.0, 184.0)
# 頭部圖層的脖子接點在畫格中的像素位置，上面留空間給髮量、下面留給長髮
HEAD_ANCHOR = (96.0, 152.0)
# 脖子接點的世界高度，身體圖層的 head_attach 和頭部圖層的 anchor 指的是同一個點
NECK_Z = 1.024


def engine_name():
    items = bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items.keys()
    for candidate in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        if candidate in items:
            return candidate
    return items[0]


def setup_scene(transparent=True, samples=48):
    scene = bpy.context.scene
    scene.render.engine = engine_name()
    scene.render.film_transparent = transparent
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    # 兩倍解析度算圖再面積縮小，縮完就是乾淨的手繪感 2D，不做任何像素化。
    # 濾鏡半徑壓在 1 個算圖像素以內，縮圖之後細節才留得住；描邊留到縮圖之後才補
    scene.render.filter_size = 0.9
    scene.render.use_border = False
    eevee = scene.eevee
    # 柔和漸層要靠真實打光，所以陰影要開；泛光和螢幕空間反射不要，會把乾淨的色塊弄髒
    for attr, value in (("taa_render_samples", samples), ("use_raytracing", False),
                        ("use_shadows", True), ("use_bloom", False),
                        ("use_gtao", False), ("use_ssr", False)):
        if hasattr(eevee, attr):
            try:
                setattr(eevee, attr, value)
            except Exception:
                pass
    return scene


# 三盞燈，照 docs/美術風格指南.md 的「像商品照」：
# 主光偏暖從左上前方、補光偏冷從右下前方、頂光從上後方負責頭髮的弧形高光帶。
# 每一盞是 (名稱, 光從哪個方向照過來, 顏色, 亮度, 角直徑)。方向是「從表面看向光源」的向量
LIGHTS = [
    ("key", (-0.45, -0.72, 0.53), (1.0, 0.945, 0.855), 2.9, 0.34),
    ("fill", (0.62, -0.42, -0.38), (0.72, 0.80, 1.0), 0.95, 0.9),
    ("rim", (0.10, 0.52, 0.85), (1.0, 0.975, 0.92), 1.7, 0.16),
]
# 環境光取偏冷的天空色，暗部才不是死黑而是帶一點環境反光
AMBIENT_COLOR = (0.40, 0.45, 0.56, 1.0)
AMBIENT_STRENGTH = 0.22


def _aim_sun(sun, direction):
    """太陽燈預設往 -Z 照，把它轉成從 direction 照過來"""
    sun.rotation_mode = "QUATERNION"
    sun.rotation_quaternion = Vector(direction).normalized().to_track_quat("Z", "Y")
    return sun


def add_lights(world_strength=AMBIENT_STRENGTH):
    """主光加補光加頂光，柔和漸層和高光都由這三盞算出來

    之前那版材質自己拿法線查色階、完全不吃燈光，做出來永遠是一塊一塊的平塗。
    現在改成真的用 Principled 材質受光，所以這三盞的方向、顏色、亮度就是整個畫風的來源。
    投影打開但把太陽的角直徑開大，陰影邊緣柔，不會在圓面上留下塊狀髒斑。
    """
    for obj in list(bpy.context.scene.objects):
        if obj.type == "LIGHT":
            bpy.data.objects.remove(obj, do_unlink=True)
    made = []
    for name, direction, color, energy, angle in LIGHTS:
        light = bpy.data.lights.new(name, "SUN")
        light.energy = energy
        light.color = color
        light.angle = angle
        # 只有主光投影，補光和頂光投影會讓暗部出現互相打架的髒斑
        light.use_shadow = name == "key"
        sun = bpy.data.objects.new(name, light)
        blenv.link(sun)
        _aim_sun(sun, direction)
        made.append(sun)
    world = bpy.data.worlds.get("v2world") or bpy.data.worlds.new("v2world")
    bpy.context.scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    if background:
        background.inputs["Color"].default_value = AMBIENT_COLOR
        background.inputs["Strength"].default_value = world_strength
    return made[0]


def make_camera(name="cam"):
    old = bpy.data.objects.get(name)
    if old:
        bpy.data.objects.remove(old, do_unlink=True)
    data = bpy.data.cameras.new(name)
    data.type = "ORTHO"
    camera = bpy.data.objects.new(name, data)
    blenv.link(camera)
    bpy.context.scene.camera = camera
    return camera


def aim(camera, target, ortho_height_m, elevation_deg=CAMERA_ELEVATION_DEG, azimuth_deg=0.0,
        distance=12.0):
    """正交相機看向 target，ortho_height_m 是畫面要涵蓋的世界高度"""
    elevation = math.radians(elevation_deg)
    azimuth = math.radians(azimuth_deg)
    camera.data.ortho_scale = ortho_height_m
    offset = Vector((math.sin(azimuth) * math.cos(elevation),
                     -math.cos(azimuth) * math.cos(elevation),
                     math.sin(elevation))) * distance
    camera.location = Vector(target) + offset
    camera.rotation_euler = (math.pi / 2 - elevation, 0, azimuth)
    return camera


def sprite_camera(camera, azimuth_deg=0.0):
    """精靈圖專用：畫格 192 px、密度 128 px/m、腳底落在 ANCHOR 指定的像素上

    正交相機下，地面原點到畫面中心的垂直像素距離等於 高度 × cos(仰角) × 密度，
    反推相機要看向地面上方多少公尺，腳底才會剛好落在 ANCHOR。
    """
    view_height = FRAME_PX / PIXELS_PER_METER
    below_center = ANCHOR[1] - FRAME_PX / 2.0
    target_z = below_center / (math.cos(math.radians(CAMERA_ELEVATION_DEG)) * PIXELS_PER_METER)
    return aim(camera, (0, 0, target_z), view_height, CAMERA_ELEVATION_DEG, azimuth_deg)


def head_camera(camera, azimuth_deg=0.0):
    """頭部圖層專用：跟身體同樣的密度和仰角，把脖子接點放到 HEAD_ANCHOR 那一格像素上

    兩張圖用同一組相機參數，引擎把頭貼到身體的 head_attach 上才會剛好接合
    """
    view_height = FRAME_PX / PIXELS_PER_METER
    below_center = HEAD_ANCHOR[1] - FRAME_PX / 2.0
    offset = below_center / (math.cos(math.radians(CAMERA_ELEVATION_DEG)) * PIXELS_PER_METER)
    return aim(camera, (0, 0, NECK_Z + offset), view_height, CAMERA_ELEVATION_DEG, azimuth_deg)


def world_to_pixel(camera, point, frame_px=FRAME_PX):
    """世界座標投影到畫格像素座標，左上角為原點，用來算頭部接點"""
    scene = bpy.context.scene
    from bpy_extras.object_utils import world_to_camera_view
    coords = world_to_camera_view(scene, camera, Vector(point))
    return (coords.x * frame_px, (1.0 - coords.y) * frame_px)


def render_to(path, resolution=None):
    scene = bpy.context.scene
    if resolution:
        scene.render.resolution_x, scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.filepath = path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with blenv.ui():
        bpy.ops.render.render(write_still=True)
    return path


VIEWS = [("front", 0.0), ("threequarter", -40.0), ("side", -90.0), ("back", 180.0)]


def check_shots(prefix, out_dir=None, elevation=12.0, size=768, height_m=1.62,
                target_z=0.72, views=VIEWS):
    """品管檢查圖：正面、四分之三、側面、背面，看得清楚臉和剪影"""
    out_dir = out_dir or blenv.SHOT_DIR
    setup_scene(transparent=False)
    add_lights()
    camera = make_camera("check_cam")
    paths = []
    for name, azimuth in views:
        aim(camera, (0, 0, target_z), height_m, elevation, azimuth)
        paths.append(render_to(os.path.join(out_dir, "%s_%s.png" % (prefix, name)), (size, size)))
    return paths


def contact_sheet(objects_by_label, path, elevation=12.0, size=360, height_m=1.62,
                  target_z=0.72, azimuth=-30.0, spacing=0.9):
    """把好幾個角色排成一排一起算，比較剪影和配色用"""
    setup_scene(transparent=False)
    add_lights()
    camera = make_camera("row_cam")
    count = len(objects_by_label)
    for index, (_, roots) in enumerate(objects_by_label):
        offset = (index - (count - 1) / 2.0) * spacing
        for root in roots:
            root.location.x = offset
    aim(camera, (0, 0, target_z), height_m * (count * spacing / height_m) * 0.62 + height_m * 0.2,
        elevation, azimuth)
    camera.data.ortho_scale = max(count * spacing * 1.15, height_m)
    return render_to(path, (size * count, size))
