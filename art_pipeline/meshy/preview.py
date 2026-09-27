"""
城鎮建築的總覽圖：每件用遊戲鏡頭的角度拍一張，俯角 38 度、從南邊看，拼成一張給人看。
還沒有地圖的城鎮用這個先過目。

用法：blender -b --factory-startup --python-exit-code 1 -P art_pipeline/meshy/preview.py -- <輸出 png> <城鎮> [城鎮 ...]
"""
import math
import os
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(HERE))
MODELS = os.path.join(PROJECT_ROOT, "assets", "generated", "models", "towns")
CELL = 512
PITCH = 38.0


def render_one(path, out_png):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = CELL
    scene.render.resolution_y = CELL
    scene.render.film_transparent = False
    scene.world = bpy.data.worlds.new("w")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs[0].default_value = (0.78, 0.84, 0.9, 1.0)
    scene.world.node_tree.nodes["Background"].inputs[1].default_value = 0.9
    scene.view_settings.view_transform = "Standard"
    bpy.ops.import_scene.gltf(filepath=path)
    meshes = [o for o in scene.objects if o.type == "MESH"]
    points = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
    low = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    high = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    centre = (low + high) * 0.5
    radius = (high - low).length * 0.5
    # 地面一塊淡綠，看得出貼地
    bpy.ops.mesh.primitive_plane_add(size=radius * 4, location=(centre.x, centre.y, 0.0))
    ground = bpy.context.object
    material = bpy.data.materials.new("ground")
    material.use_nodes = True
    material.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.42, 0.55, 0.3, 1)
    ground.data.materials.append(material)
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 3.2
    sun.rotation_euler = (math.radians(50), 0, math.radians(35))
    scene.collection.objects.link(sun)
    camera = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = radius * 2.3
    pitch = math.radians(PITCH)
    distance = radius * 6
    camera.location = centre + Vector((0, -math.cos(pitch) * distance, math.sin(pitch) * distance))
    camera.rotation_euler = (math.radians(90) - pitch, 0, 0)
    scene.collection.objects.link(camera)
    scene.camera = camera
    scene.render.filepath = out_png
    bpy.ops.render.render(write_still=True)


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    out, towns = args[0], args[1:]
    tmp = os.path.join(os.path.dirname(os.path.abspath(out)), "_cells")
    os.makedirs(tmp, exist_ok=True)
    cells = []
    for town in towns:
        folder = os.path.join(MODELS, town)
        for name in sorted(f for f in os.listdir(folder) if f.endswith(".glb")):
            png = os.path.join(tmp, "%s_%s.png" % (town, name[:-4]))
            render_one(os.path.join(folder, name), png)
            cells.append((town + "/" + name[:-4], png))
    columns = 4
    rows = (len(cells) + columns - 1) // columns
    sheet = bpy.data.images.new("sheet", CELL * columns, CELL * rows)
    pixels = [1.0] * (CELL * columns * CELL * rows * 4)
    for index, (_, png) in enumerate(cells):
        image = bpy.data.images.load(png)
        src = list(image.pixels)
        col, row = index % columns, rows - 1 - index // columns
        for y in range(CELL):
            start = ((row * CELL + y) * CELL * columns + col * CELL) * 4
            pixels[start:start + CELL * 4] = src[y * CELL * 4:(y + 1) * CELL * 4]
    sheet.pixels = pixels
    sheet.filepath_raw = out
    sheet.file_format = "PNG"
    sheet.save()
    print("[preview] %d 件 -> %s" % (len(cells), out))
    for index, (key, _) in enumerate(cells):
        print("  %d %s" % (index + 1, key))


main()
