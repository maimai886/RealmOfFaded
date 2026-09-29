"""技能特效的 2D 序列圖與單張形狀貼圖

skill_effects.gd 現在吃的是 ART 表裡每個形狀一張白色帶透明的貼圖，顏色由 modulate 決定，
動畫是程式縮放位移。所以每個形狀輸出兩種東西：
- texture.png：白色帶透明的單張，直接填進 ART 表就會換掉程式畫的佔位圖
- sheet.png + meta.json：5~8 格的彩色序列，格式比照精靈圖，給之後改成播序列時用
"""

import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for sub in ("common", "monsters", "icons"):
    path = os.path.join(ROOT, sub)
    if path not in sys.path:
        sys.path.insert(0, path)

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import blenv  # noqa: E402
import glyphs as g  # noqa: E402
import meshkit as mk  # noqa: E402
import palette as cpalette  # noqa: E402
import pixels  # noqa: E402
import sheets  # noqa: E402
import shot  # noqa: E402

FX = 96
SUPER = 2
OUT_ROOT = os.path.join(blenv.PROJECT_ROOT, "assets", "generated", "sprites", "effects")

# 形狀 -> (frames, fps, 屬性色)。white 給 ART 用的單張
EFFECTS = {
    "arc": dict(frames=6, fps=24, color="#fff3d6"),
    "bolt": dict(frames=6, fps=18, color="#fff0d6"),
    "bolt_fire": dict(frames=6, fps=18, color="#ff9447", shape="bolt"),
    "bolt_ice": dict(frames=6, fps=18, color="#94d1ff", shape="bolt"),
    "bolt_lightning": dict(frames=6, fps=18, color="#e8f78a", shape="bolt"),
    "burst": dict(frames=6, fps=20, color="#fff0c0"),
    "ring": dict(frames=6, fps=12, color="#c8f0a0"),
    "disc": dict(frames=5, fps=10, color="#ffe6a8"),
    "trap": dict(frames=6, fps=8, color="#d9b070"),
    "flame": dict(frames=8, fps=14, color="#ff9447"),
    "star": dict(frames=6, fps=12, color="#ffe66b"),
    "snow": dict(frames=6, fps=10, color="#bfe9ff"),
    "aura": dict(frames=8, fps=10, color="#9ff2b8"),
    "meteor": dict(frames=8, fps=16, color="#ff9447"),
}
ART_SHAPES = ["arc", "bolt", "burst", "ring", "disc", "trap", "flame", "star", "snow", "aura"]


def _emissive(name, hex_color, strength=1.0):
    material = cpalette._new(name)
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    output = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = cpalette.srgb(hex_color)
    emission.inputs["Strength"].default_value = strength
    links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return material


def _shape(builder, shape, t):
    """在 t 從 0 到 1 的階段畫出形狀，材質 0 是主色、1 是核心亮色"""
    s = 0.5 + 0.5 * t
    if shape == "arc":
        a0 = -70 + 100 * t
        g.arc_slash(builder, 0.42, 0.10 * (1 - t * 0.5), 0, a0 - 40, a0 + 40, 9)
        g.arc_slash(builder, 0.42, 0.045 * (1 - t * 0.5), 1, a0 - 30, a0 + 30, 7)
    elif shape == "bolt":
        length = 0.34 + 0.12 * math.sin(t * math.pi)
        mk.sweep(builder, [(-length, 0, 0), (length * 0.6, 0, 0), (length, 0, 0)], [0.12, 0.09, 0.01], 8, mat=0, up=g.UP)
        mk.sweep(builder, [(-length * 0.6, 0, 0), (length * 0.8, 0, 0)], [0.05, 0.02], 6, mat=1, up=g.UP)
        for k in range(3):
            y = (k - 1) * 0.12
            mk.sweep(builder, [(-length * (0.9 + 0.2 * k), y, 0), (-length * 0.4, y * 0.5, 0)], [0.02, 0.005], 4, mat=0, up=g.UP)
    elif shape == "burst":
        r = 0.15 + 0.35 * t
        g.star(builder, (0, 0, 0), r, 8, 0, 0.06 * (1 - t * 0.6))
        g.orb(builder, (0, 0, 0), r * 0.35 * (1 - t * 0.5), 1, glow=False)
    elif shape == "ring":
        g.ring(builder, 0.2 + 0.28 * t, 0.06 * (1 - t * 0.5), 0, 0.0, 1.0)
        g.ring(builder, 0.2 + 0.28 * t, 0.025 * (1 - t * 0.5), 1, 0.0, 1.0)
    elif shape == "disc":
        mk.blob(builder, (0, 0, 0), (0.45, 0.45, 0.02), mat=0, segments=24, rings_count=6)
        mk.blob(builder, (0, 0, 0.01), (0.32 * (0.9 + 0.1 * math.sin(t * math.tau)), 0.32, 0.02), mat=1, segments=20, rings_count=5)
    elif shape == "trap":
        g.ring(builder, 0.42, 0.035, 0, 0.0, 1.0)
        for a in (0.6, 2.2):
            mk.sweep(builder, [(math.cos(a) * 0.4, math.sin(a) * 0.4, 0), (-math.cos(a) * 0.4, -math.sin(a) * 0.4, 0)], [0.03, 0.03], 4, mat=0, up=g.UP)
        pulse = 0.08 + 0.05 * math.sin(t * math.tau)
        mk.blob(builder, (0, 0, 0.02), (pulse, pulse, 0.02), mat=1, segments=10, rings_count=4)
    elif shape == "flame":
        h = 0.8 + 0.15 * math.sin(t * math.tau)
        for x, k in ((-0.16, 0.7), (0.0, 1.0), (0.16, 0.8)):
            g.flame(builder, (x, 0, -0.45), h * k, 0.16 * k, 0, 1)
    elif shape == "star":
        g.star(builder, (0, 0, 0), 0.42, 4, 0, 0.09)
        g.star(builder, (0, 0, 0), 0.26, 4, 1, 0.05)
        builder.verts = [Vector((v.x * math.cos(t * math.pi) - v.z * math.sin(t * math.pi), v.y,
                                 v.x * math.sin(t * math.pi) + v.z * math.cos(t * math.pi))) for v in builder.verts]
    elif shape == "snow":
        g.star(builder, (0, 0, 0), 0.42, 6, 0, 0.045)
        for i in range(6):
            a = 2 * math.pi * i / 6
            c = Vector((math.cos(a), 0, math.sin(a))) * 0.26
            for sgn in (1, -1):
                tip = c + Vector((math.cos(a + sgn * 1.0), 0, math.sin(a + sgn * 1.0))) * 0.12
                mk.sweep(builder, [c, tip], [0.03, 0.005], 4, mat=0, up=g.FWD)
        g.orb(builder, (0, 0, 0), 0.08, 1, glow=False)
        builder.verts = [Vector((v.x * math.cos(t * 0.5) - v.z * math.sin(t * 0.5), v.y, v.x * math.sin(t * 0.5) + v.z * math.cos(t * 0.5))) for v in builder.verts]
    elif shape == "aura":
        for k in range(3):
            phase = (t + k / 3.0) % 1.0
            g.ring(builder, 0.18 + 0.28 * phase, 0.03 * (1 - phase), 0 if k else 1, phase * 0.15, 0.55)
    elif shape == "meteor":
        if t < 0.5:
            k = t / 0.5
            g.orb(builder, (0.3 - 0.6 * k, 0, 0.45 - 0.7 * k), 0.16, 0, glow=False)
            g.flame(builder, (0.3 - 0.6 * k + 0.05, 0.02, 0.45 - 0.7 * k), 0.4, 0.1, 0, 1)
        else:
            k = (t - 0.5) / 0.5
            g.star(builder, (-0.3, 0, -0.25), 0.15 + 0.4 * k, 8, 0, 0.06 * (1 - k * 0.7))
            g.ring(builder, 0.15 + 0.35 * k, 0.04 * (1 - k * 0.5), 1, -0.3, 0.45)


def _camera(flat):
    shot.setup_scene(transparent=True)
    camera = shot.make_camera("fx_cam")
    shot.aim(camera, (0, 0, 0), 1.1, 90.0 if flat else 0.0, 0.0)
    scene = bpy.context.scene
    scene.render.resolution_x = FX * SUPER
    scene.render.resolution_y = FX * SUPER
    return camera


FLAT = {"ring", "disc", "trap", "aura"}


def _frame(effect_id, shape, t, main_hex, core_hex):
    blenv.clear_scene()
    materials = [_emissive("fx_main", main_hex), _emissive("fx_core", core_hex)]
    b = mk.Builder()
    _shape(b, shape, t)
    obj = b.to_object("Fx_" + effect_id, materials)
    mk.shade(obj)
    _camera(shape in FLAT)
    work = os.path.join(blenv.SHOT_DIR, "_fx")
    os.makedirs(work, exist_ok=True)
    raw = pixels.load_png(shot.render_to(os.path.join(work, "%s_%.2f.png" % (effect_id, t))))
    return pixels.downsample(raw, SUPER)


def render(effect_id):
    spec = EFFECTS[effect_id]
    shape = spec.get("shape", effect_id)
    frames = [_frame(effect_id, shape, i / max(1, spec["frames"] - 1), spec["color"], "#fffaf0")
              for i in range(spec["frames"])]
    out_dir = os.path.join(OUT_ROOT, effect_id)
    os.makedirs(out_dir, exist_ok=True)
    sheet_path = os.path.join(out_dir, "sheet.png")
    pixels.save_png(pixels.pack_grid([frames], FX, spec["frames"]), sheet_path)
    sheets.write_import(sheet_path)
    meta = {"frame_size": [FX, FX], "columns": spec["frames"], "pixels_per_meter": 64.0,
            "anchor": [FX / 2.0, FX / 2.0], "directions": ["s"],
            "actions": {"play": {"row": 0, "frames": spec["frames"], "fps": spec["fps"], "loop": effect_id in ("flame", "aura", "trap", "disc", "ring")}}}
    with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as handle:
        json.dump(meta, handle, ensure_ascii=False, indent=2)
    if shape in ART_SHAPES and effect_id == shape:
        # ART 表用的單張：白色帶透明，顏色交給 modulate
        white = _frame(effect_id, shape, 0.35, "#ffffff", "#ffffff")
        white[..., :3] = 1.0
        art_path = os.path.join(out_dir, "texture.png")
        pixels.save_png(white, art_path)
        sheets.write_import(art_path)
    return out_dir


def render_all(ids=None):
    return [render(effect_id) for effect_id in (ids or list(EFFECTS))]
