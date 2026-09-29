"""道具與技能圖示：40x40，RO 風，透明背景，1 px 描邊，暖色高光

每個圖示是幾個零件堆在原點附近，用正交相機從斜前上方拍一張 160 px，
面積縮小到 40 px 再補描邊。技能圖示另外在 numpy 裡墊一塊職業色的圓角底板。
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
import mpalette  # noqa: E402
import palette as cpalette  # noqa: E402
import pixels  # noqa: E402
import sheets  # noqa: E402
import shot  # noqa: E402

ICON_PX = 40
SUPER = 4
ITEM_DIR = os.path.join(blenv.PROJECT_ROOT, "assets", "ui", "icons", "items")
SKILL_DIR = os.path.join(blenv.PROJECT_ROOT, "assets", "ui", "icons", "skills")
SRC_DIR = os.path.join(blenv.PROJECT_ROOT, "art_source", "icons")

# 色階代號：主、次、點綴
R = mpalette.slot_specs

# 道具：id -> (零件函式, 色階)
ITEMS = {
    "red_potion": (lambda b: g.bottle(b), R("ember", "glow", "glow")),
    "orange_potion": (lambda b: g.bottle(b), R("honey", "glow", "glow")),
    "blue_potion": (lambda b: g.bottle(b), R("sky", "glow", "glow")),
    "green_potion": (lambda b: g.bottle(b), R("leaf", "glow", "glow")),
    "small_apple": (lambda b: (g.orb(b, (0, 0, 0), 0.34, g.MAIN), mk.sweep(b, [(0, 0, 0.3), (0.06, 0, 0.46)], [0.03, 0.02], 5, mat=g.WOOD, up=g.FWD), g.leaf(b, (0.12, -0.02, 0.44), 0.22, g.ACCENT)), R("ember", "leaf", "leaf")),
    "flower_honey": (lambda b: (mk.loft(b, [mk.ring((0, 0, -0.3), 0.3, 0.3, 12), mk.ring((0, 0, 0.18), 0.32, 0.32, 12), mk.ring((0, 0, 0.26), 0.22, 0.22, 12)], mat=g.MAIN), mk.blob(b, (0, 0, 0.3), (0.24, 0.24, 0.08), mat=g.WOOD, segments=10, rings_count=4), g.leaf(b, (0.2, -0.1, 0.2), 0.2, g.ACCENT)), R("honey", "honey", "leaf")),
    "dew_gel": (lambda b: (mk.blob(b, (0, 0, -0.05), (0.36, 0.3, 0.28), mat=g.MAIN, segments=14, rings_count=8), mk.blob(b, (-0.12, -0.2, 0.1), (0.08, 0.05, 0.1), mat=g.WHITE, segments=6, rings_count=3)), R("slime", "glow", "glow")),
    "clear_dewdrop": (lambda b: (mk.sweep(b, [(0, 0, 0.4), (0, 0, 0.1), (0, 0, -0.3)], [0.01, 0.22, 0.3], 12, mat=g.GLOW, up=g.FWD), mk.blob(b, (-0.1, -0.25, -0.05), (0.07, 0.04, 0.1), mat=g.WHITE, segments=6, rings_count=3)), R("glow", "glow", "glow", glow="glow")),
    "soft_moss": (lambda b: g.pile(b, (0, 0, -0.15), 0.7, g.MAIN, 6), R("moss", "leaf", "leaf")),
    "sprout_seed": (lambda b: (mk.blob(b, (0, 0, -0.15), (0.24, 0.2, 0.3), mat=g.SECOND, segments=10, rings_count=6), mk.sweep(b, [(0, 0, 0.1), (0.02, 0, 0.32)], [0.03, 0.02], 5, mat=g.ACCENT, up=g.FWD), g.leaf(b, (0.14, -0.02, 0.36), 0.2, g.MAIN), g.leaf(b, (-0.12, -0.02, 0.3), 0.18, g.MAIN, tilt=-0.4)), R("leaf", "fur_brown", "moss")),
    "bee_stinger": (lambda b: (mk.sweep(b, [(-0.3, 0, -0.3), (0.0, 0, 0.0), (0.32, 0, 0.32)], [0.09, 0.06, 0.005], 8, mat=g.MAIN, up=g.FWD), mk.blob(b, (-0.3, 0, -0.3), (0.12, 0.1, 0.12), mat=g.SECOND, segments=8, rings_count=4)), R("bone", "honey", "dark")),
    "brittle_bone": (lambda b: g.bone(b, (0, 0, 0), 0.7), R("bone", "bone", "bone")),
    "ash_dust": (lambda b: (g.pile(b, (0, 0, -0.2), 0.6, g.MAIN, 5), mk.blob(b, (0.15, -0.1, 0.2), (0.05, 0.05, 0.05), mat=g.SECOND, segments=6, rings_count=3)), R("ashbone", "dark", "dark")),
    "knife": (lambda b: g.blade(b, 0.7, 0.05, guard=False), R("iron", "iron", "rust")),
    "sword": (lambda b: g.blade(b, 0.9, 0.06), R("iron", "iron", "rust")),
    "rusty_blade": (lambda b: g.blade(b, 0.8, 0.06, rusty=True), R("rust", "rust", "rust")),
    "long_sword": (lambda b: g.blade(b, 1.05, 0.07, two_hand=True), R("iron", "iron", "rust")),
    "rod": (lambda b: (mk.sweep(b, [(-0.32, 0, -0.42), (0.22, 0, 0.3)], [0.04, 0.035], 6, mat=g.WOOD, up=g.FWD), g.orb(b, (0.28, 0, 0.38), 0.13, g.GLOW)), R("wood", "wood", "glow")),
    "bow": (lambda b: (mk.sweep(b, [(-0.02 + 0.12 * math.sin(math.pi * i / 8), 0, -0.45 + 0.9 * i / 8) for i in range(9)], [0.03 + 0.02 * math.sin(math.pi * i / 8) for i in range(9)], 6, mat=g.WOOD, up=g.FWD), mk.sweep(b, [(-0.02, 0, -0.44), (-0.02, 0, 0.44)], [0.008, 0.008], 4, mat=g.BONE, up=g.FWD)), R("wood", "wood", "bone")),
    "guard": (lambda b: (mk.loft(b, [mk.ring((0, 0.04, 0), 0.36, 0.42, 12), mk.ring((0, -0.02, 0), 0.34, 0.4, 12)], mat=g.MAIN), mk.blob(b, (0, -0.06, 0), (0.1, 0.05, 0.1), mat=g.METAL, segments=8, rings_count=4), mk.loft(b, [mk.ring((0, -0.03, 0), 0.36, 0.42, 12, ), mk.ring((0, -0.05, 0), 0.30, 0.36, 12)], mat=g.METAL, cap_bottom=False, cap_top=False)), R("wood", "wood", "iron")),
    "cotton_shirt": (lambda b: (mk.box(b, (0, 0, -0.05), (0.5, 0.14, 0.6), mat=g.MAIN, taper=(1.15, 1.0)), mk.box(b, (-0.35, 0, 0.18), (0.22, 0.13, 0.22), mat=g.MAIN), mk.box(b, (0.35, 0, 0.18), (0.22, 0.13, 0.22), mat=g.MAIN), mk.blob(b, (0, -0.06, 0.3), (0.12, 0.04, 0.06), mat=g.SECOND, segments=8, rings_count=3)), R("cream", "cloth_second", "cloth_main")),
    "sandals": (lambda b: [(mk.blob(b, (x, 0, -0.05), (0.2, 0.46, 0.09), mat=g.MAIN, segments=10, rings_count=5), mk.sweep(b, [(x - 0.18, -0.08, 0.0), (x, -0.14, 0.16), (x + 0.18, -0.08, 0.0)], [0.045, 0.045, 0.045], 5, mat=g.SECOND, up=g.UP)) for x in (-0.24, 0.24)], R("cloth_main", "rust", "rust")),
    "cap": (lambda b: (mk.blob(b, (0, 0, 0.05), (0.36, 0.34, 0.26), mat=g.MAIN, segments=14, rings_count=7), mk.loft(b, [mk.ring((0, 0, -0.12), 0.44, 0.42, 14), mk.ring((0, 0, -0.08), 0.42, 0.4, 14)], mat=g.SECOND, cap_bottom=False, cap_top=False)), R("cloth_second", "rust", "rust")),
    "beetle_shell": (lambda b: (mk.blob(b, (0, 0, -0.05), (0.34, 0.3, 0.16), mat=g.MAIN, segments=14, rings_count=7), *[g.shard(b, (0, -0.02, 0.1 + i * 0.0), 0.16, g.ACCENT) for i in range(1)]), R("leaf", "fur_brown", "moss")),
    "glow_spore_cap": (lambda b: (mk.blob(b, (0, 0, 0.0), (0.38, 0.36, 0.2), mat=g.MAIN, segments=14, rings_count=7), *[mk.blob(b, (math.cos(a) * 0.2, -0.15, 0.12 + math.sin(a) * 0.04), (0.05, 0.05, 0.03), mat=g.GLOW, segments=6, rings_count=3) for a in (0.3, 2.0, 4.2)]), R("glow", "bone", "slime")),
    "dry_branch": (lambda b: (mk.sweep(b, [(-0.4, 0, -0.35), (0, 0, 0), (0.4, 0, 0.35)], [0.05, 0.045, 0.03], 6, mat=g.MAIN, up=g.FWD), mk.sweep(b, [(0.05, 0, 0.05), (0.22, 0, 0.32)], [0.03, 0.01], 5, mat=g.MAIN, up=g.FWD)), R("fur_brown", "wood", "wood")),
    "wolf_fang": (lambda b: mk.sweep(b, [(-0.2, 0, -0.35), (0.0, 0, 0.05), (0.14, 0, 0.4)], [0.16, 0.1, 0.005], 8, mat=g.MAIN, up=g.FWD), R("bone", "bone", "bone")),
    "wolf_pelt": (lambda b: g.cloth_square(b, (0, 0, 0), 0.78, g.MAIN, 0.1), R("fur_grey", "ashbone", "dark")),
    "snail_shell": (lambda b: g.shell(b, (0, 0, -0.02), 0.36), R("rock", "moss", "fur_brown")),
    "flint_shard": (lambda b: (g.shard(b, (-0.08, 0, -0.06), 0.5, g.MAIN), g.shard(b, (0.14, 0.05, 0.1), 0.34, g.SECOND)), R("rock", "ashbone", "rock")),
    "rat_tail": (lambda b: mk.sweep(b, [(-0.38, 0, -0.3), (-0.1, 0, 0.1), (0.15, 0, -0.05), (0.38, 0, 0.3)], [0.07, 0.05, 0.04, 0.01], 6, mat=g.MAIN, up=g.FWD), R("skin", "fur_brown", "fur_brown")),
    "vulture_feather": (lambda b: g.feather(b, (0, 0, 0), 0.9), R("fur_brown", "dark", "bone")),
    "bird_meat": (lambda b: (mk.blob(b, (0.06, 0, 0.02), (0.3, 0.26, 0.24), mat=g.MAIN, segments=12, rings_count=6), mk.sweep(b, [(-0.15, 0, -0.15), (-0.4, 0, -0.36)], [0.06, 0.05], 6, mat=g.BONE, up=g.FWD)), R("cloth_second", "rust", "bone")),
    "bat_wing": (lambda b: g.wing_icon(b), R("dark", "fur_grey", "dark")),
    "rotten_cloth": (lambda b: g.cloth_square(b, (0, 0, 0), 0.74, g.MAIN, 0.16), R("rot", "dark", "dark")),
    "bone_arrowhead": (lambda b: (mk.sweep(b, [(-0.3, 0, -0.3), (0.05, 0, 0.05), (0.3, 0, 0.3)], [0.2, 0.12, 0.005], 6, mat=g.MAIN, up=g.FWD, squash=[0.3, 0.3, 0.3]), mk.sweep(b, [(-0.42, 0, -0.42), (-0.28, 0, -0.28)], [0.04, 0.04], 5, mat=g.WOOD, up=g.FWD)), R("bone", "bone", "wood")),
    "gloom_ember": (lambda b: (g.orb(b, (0, 0, -0.05), 0.26, g.DARK, glow=False), g.flame(b, (0, -0.02, 0.0), 0.5, 0.16, g.MAIN, g.GLOW)), R("ember", "ember", "ember", glow="ember")),
    "hollow_plate": (lambda b: mk.box(b, (0, 0, 0), (0.6, 0.12, 0.66), mat=g.MAIN, taper=(0.75, 1.0)), R("iron", "iron", "rust")),
    "ash_crown_shard": (lambda b: (mk.loft(b, [mk.ring((0, 0, -0.2), 0.32, 0.22, 10), mk.ring((0, 0, -0.05), 0.34, 0.24, 10)], mat=g.METAL, cap_bottom=False, cap_top=False), *[mk.sweep(b, [(math.sin(a) * 0.32, -math.cos(a) * 0.22, -0.05), (math.sin(a) * 0.36, -math.cos(a) * 0.24, 0.3)], [0.05, 0.005], 5, mat=g.METAL, up=g.UP) for a in (-1.0, 0.0, 1.0)]), R("brass", "brass", "brass", metal="brass")),
    "sovereign_core": (lambda b: (g.orb(b, (0, 0, 0), 0.3, g.MAIN), g.ring(b, 0.42, 0.03, g.GLOW, 0.0, 0.5), g.star(b, (0, -0.32, 0), 0.5, 4, g.GLOW, 0.03)), R("violet", "dark", "ember", glow="ember")),
}


def _wing_icon(b):
    r = Vector((-0.4, 0, -0.2))
    tip = Vector((0.45, 0, 0.35))
    mid = Vector((0.05, 0, 0.3))
    mk.sweep(b, [r, mid, tip], [0.05, 0.035, 0.01], 5, mat=g.SECOND, up=g.UP)
    base = b.add_verts([r, mid, tip, Vector((0.3, 0.02, -0.15)), Vector((-0.05, 0.02, -0.3))])
    b.add_face((base, base + 1, base + 2, base + 3, base + 4), mat=g.MAIN)
    b.add_face((base + 4, base + 3, base + 2, base + 1, base), mat=g.MAIN)


g.wing_icon = _wing_icon

# 職業色系：底板漸層的深色與亮色
JOB_COLORS = {
    "novice": ("#8a6a4e", "#e8c7a5"),
    "swordman": ("#7e2f2a", "#e8946a"),
    "mage": ("#3d3a7e", "#9c8fd8"),
    "archer": ("#2f5d33", "#9ccf6e"),
    "hero": ("#8a1f2a", "#f3a052"),
    "elementalist": ("#2c2f7e", "#7fb2ff"),
    "hunter": ("#1f5a3a", "#8fd88a"),
}

# 技能符號：id -> 零件函式；色階依屬性
def _glyph_slash(b):
    g.arc_slash(b, 0.4, 0.08, g.WHITE)
    g.blade(b, 0.7, 0.05, guard=True)


def _glyph_quake(b):
    g.blade(b, 0.6, 0.05)
    g.ring(b, 0.42, 0.035, g.MAIN, -0.3, 0.4)
    g.star(b, (0.25, -0.1, -0.28), 0.18, 4, g.GLOW, 0.03)


def _glyph_bolt(b):
    mk.sweep(b, [(-0.4, 0, -0.35), (0.1, 0, 0.1), (0.42, 0, 0.4)], [0.05, 0.05, 0.005], 6, mat=g.WOOD, up=g.FWD)
    mk.sweep(b, [(0.25, 0, 0.22), (0.45, 0, 0.44)], [0.1, 0.005], 6, mat=g.MAIN, up=g.FWD, squash=[0.3, 0.3])
    g.flame(b, (0.2, -0.03, 0.1), 0.35, 0.09, g.MAIN, g.GLOW)


def _glyph_orb(b):
    g.orb(b, (0, 0, 0), 0.32, g.MAIN)
    g.ring(b, 0.42, 0.025, g.GLOW, 0.0, 0.35)


def _glyph_wall(b):
    for x in (-0.28, 0.0, 0.28):
        g.flame(b, (x, 0.0, -0.35), 0.75, 0.15, g.MAIN, g.GLOW)


def _glyph_snow(b):
    g.star(b, (0, 0, 0), 0.42, 6, g.MAIN, 0.04)
    g.orb(b, (0, 0, 0), 0.1, g.GLOW, glow=False)


def _glyph_lightning(b):
    g.lightning(b, (-0.15, 0, 0.45), (0.15, 0, -0.45), 0.06, g.MAIN)


def _glyph_arrow(b):
    mk.sweep(b, [(-0.4, 0, -0.4), (0.3, 0, 0.3)], [0.03, 0.03], 5, mat=g.WOOD, up=g.FWD)
    mk.sweep(b, [(0.25, 0, 0.25), (0.45, 0, 0.45)], [0.09, 0.005], 5, mat=g.METAL, up=g.FWD, squash=[0.3, 0.3])
    g.feather(b, (-0.38, 0.0, -0.38), 0.24, g.MAIN)


def _glyph_double_arrow(b):
    for off in (-0.12, 0.12):
        mk.sweep(b, [(-0.4 + off, 0, -0.4 - off), (0.3 + off, 0, 0.3 - off)], [0.028, 0.028], 5, mat=g.WOOD, up=g.FWD)
        mk.sweep(b, [(0.25 + off, 0, 0.25 - off), (0.45 + off, 0, 0.45 - off)], [0.08, 0.005], 5, mat=g.METAL, up=g.FWD, squash=[0.3, 0.3])


def _glyph_rain(b):
    for x, z in ((-0.3, 0.3), (0.0, 0.42), (0.3, 0.25), (-0.12, 0.05), (0.18, -0.05)):
        mk.sweep(b, [(x, 0, z), (x + 0.04, 0, z - 0.35)], [0.03, 0.005], 4, mat=g.METAL, up=g.FWD)
    g.ring(b, 0.42, 0.03, g.MAIN, -0.4, 0.4)


def _glyph_shield(b):
    mk.loft(b, [mk.ring((0, 0.03, -0.3), 0.2, 0.25, 10), mk.ring((0, 0.0, 0.1), 0.36, 0.42, 10), mk.ring((0, -0.02, 0.35), 0.34, 0.4, 10)], mat=g.MAIN)
    mk.blob(b, (0, -0.06, 0.05), (0.12, 0.05, 0.12), mat=g.GLOW, segments=8, rings_count=4)


def _glyph_eye(b):
    mk.blob(b, (0, 0, 0), (0.44, 0.1, 0.24), mat=g.WHITE, segments=14, rings_count=6)
    g.orb(b, (0, -0.06, 0), 0.17, g.MAIN)
    mk.blob(b, (0, -0.2, 0), (0.08, 0.04, 0.08), mat=g.PUPIL, segments=6, rings_count=3)


def _glyph_heart(b):
    for x in (-0.14, 0.14):
        mk.blob(b, (x, 0, 0.12), (0.24, 0.2, 0.22), mat=g.MAIN, segments=10, rings_count=5)
    mk.sweep(b, [(-0.32, 0, 0.0), (0, 0, -0.4), (0.32, 0, 0.0)], [0.2, 0.06, 0.2], 6, mat=g.MAIN, up=g.FWD, squash=[0.8, 0.8, 0.8])
    g.star(b, (0.02, -0.25, 0.05), 0.2, 4, g.WHITE, 0.03)


def _glyph_roar(b):
    for r in (0.22, 0.34, 0.46):
        g.arc_slash(b, r, 0.03, g.MAIN, -45, 45, 7)
    g.orb(b, (0, 0, 0), 0.12, g.GLOW, glow=False)


def _glyph_boots(b):
    mk.blob(b, (-0.05, 0, -0.15), (0.3, 0.18, 0.14), mat=g.MAIN, segments=8, rings_count=4)
    mk.box(b, (-0.15, 0, 0.1), (0.2, 0.16, 0.4), mat=g.MAIN)
    for z in (0.05, 0.2, 0.35):
        mk.sweep(b, [(0.15, 0, z), (0.45, 0, z + 0.05)], [0.025, 0.005], 4, mat=g.GLOW, up=g.FWD)


def _glyph_trap(b):
    g.ring(b, 0.4, 0.035, g.MAIN, -0.2, 0.45)
    for a in (0.8, 2.3):
        d = Vector((math.cos(a), 0, 0))
        mk.sweep(b, [(math.cos(a) * 0.36, -math.sin(a) * 0.16, -0.2), (-math.cos(a) * 0.36, math.sin(a) * 0.16, -0.2)], [0.03, 0.03], 4, mat=g.SECOND, up=g.UP)
    g.orb(b, (0, 0, 0.0), 0.12, g.GLOW)


def _glyph_falcon(b):
    _wing_icon(b)
    mk.blob(b, (-0.4, 0, -0.15), (0.12, 0.1, 0.1), mat=g.SECOND, segments=8, rings_count=4)


def _glyph_meteor(b):
    g.orb(b, (0.12, 0, -0.12), 0.26, g.MAIN)
    for k in (0.0, 0.12):
        g.flame(b, (-0.2 - k, 0.02, 0.05 + k * 2), 0.45, 0.1, g.ACCENT, g.GLOW)
    g.ring(b, 0.42, 0.03, g.SECOND, -0.38, 0.4)


def _glyph_whirl(b):
    for start in (0, 120, 240):
        g.arc_slash(b, 0.4, 0.06, g.WHITE, start, start + 90, 7)
    g.blade(b, 0.5, 0.04)


def _glyph_pierce(b):
    g.blade(b, 1.0, 0.05, two_hand=True)
    g.star(b, (0.3, -0.1, 0.4), 0.2, 4, g.GLOW, 0.03)


def _glyph_mire(b):
    mk.blob(b, (0, 0, -0.3), (0.44, 0.3, 0.1), mat=g.MAIN, segments=14, rings_count=5)
    for x in (-0.18, 0.1, 0.25):
        mk.blob(b, (x, -0.05, -0.2), (0.07, 0.05, 0.05), mat=g.SECOND, segments=6, rings_count=3)


def _glyph_storm(b):
    g.ring(b, 0.42, 0.03, g.SECOND, -0.38, 0.4)
    g.lightning(b, (-0.1, 0, 0.45), (0.1, 0, -0.3), 0.06, g.MAIN)


def _glyph_book(b):
    mk.box(b, (0, 0, 0), (0.6, 0.14, 0.5), mat=g.MAIN)
    mk.box(b, (0, -0.02, 0), (0.56, 0.12, 0.46), mat=g.WHITE)
    mk.sweep(b, [(-0.2, -0.09, 0.1), (0.2, -0.09, 0.1)], [0.02, 0.02], 4, mat=g.SECOND, up=g.UP)


ELEMENT_RAMP = {"fire": "ember", "water": "glow", "wind": "honey", "earth": "rust", "ghost": "violet", "": "cream"}

SKILLS = {
    "novice_basic": (_glyph_book, "cream"), "first_aid": (_glyph_heart, "cloth_second"),
    "sword_mastery": (lambda b: g.blade(b, 0.9, 0.06), "iron"), "heavy_slash": (_glyph_slash, "cream"),
    "quake_slash": (_glyph_quake, "ember"), "endure": (_glyph_shield, "iron"), "hp_recovery": (_glyph_heart, "ember"),
    "war_roar": (_glyph_roar, "honey"),
    "fire_arrow": (_glyph_bolt, "ember"), "frost_arrow": (_glyph_snow, "glow"), "thunder_arrow": (_glyph_lightning, "honey"),
    "fire_orb": (_glyph_orb, "ember"), "sp_recovery": (_glyph_orb, "sky"), "napalm_beat": (_glyph_roar, "violet"),
    "flame_wall": (_glyph_wall, "ember"), "frost_bind": (_glyph_snow, "sky"),
    "keen_eye": (_glyph_eye, "leaf"), "hawk_eye": (_glyph_eye, "honey"), "double_shot": (_glyph_double_arrow, "leaf"),
    "arrow_rain": (_glyph_rain, "leaf"), "focus": (_glyph_eye, "moss"),
    "greatsword_mastery": (lambda b: g.blade(b, 1.05, 0.07, two_hand=True), "iron"), "pierce_thrust": (_glyph_pierce, "ember"),
    "battle_haste": (_glyph_boots, "honey"), "counter_stance": (_glyph_shield, "ember"), "whirl_slash": (_glyph_whirl, "ember"),
    "thunder_orb": (_glyph_orb, "honey"), "meteor_fall": (_glyph_meteor, "ember"), "blizzard_call": (_glyph_snow, "glow"),
    "mire_field": (_glyph_mire, "rust"), "storm_judgement": (_glyph_storm, "honey"),
    "beast_bane": (lambda b: mk.sweep(b, [(-0.2, 0, -0.35), (0.0, 0, 0.05), (0.14, 0, 0.4)], [0.16, 0.1, 0.005], 8, mat=g.MAIN, up=g.FWD), "bone"),
    "falcon_dive": (_glyph_falcon, "fur_brown"), "blast_trap": (_glyph_trap, "ember"), "snare_trap": (_glyph_trap, "rust"),
    "frost_trap": (_glyph_trap, "glow"),
}


def _setup_camera():
    shot.setup_scene(transparent=True)
    shot.add_lights()
    camera = shot.make_camera("icon_cam")
    shot.aim(camera, (0, 0, 0), 1.25, 22.0, 0.0)
    scene = bpy.context.scene
    scene.render.resolution_x = ICON_PX * SUPER
    scene.render.resolution_y = ICON_PX * SUPER
    return camera


def _render(objects, colors, masks, ids, tag):
    work = os.path.join(blenv.SHOT_DIR, "_icons")
    os.makedirs(work, exist_ok=True)
    line = cpalette.srgb(cpalette.OUTLINE)
    cpalette.apply_slot_set(objects, colors)
    color_raw = pixels.load_png(shot.render_to(os.path.join(work, tag + "_c.png")))
    cpalette.apply_slot_set(objects, ids)
    id_raw = pixels.load_png(shot.render_to(os.path.join(work, tag + "_i.png")))
    cpalette.apply_slot_set(objects, colors)
    color = pixels.downsample(color_raw, SUPER)
    color = pixels.inner_lines(color, pixels.finish_ids(id_raw, SUPER), line, opacity=0.5)
    return pixels.outline(color, line)


def _srgb(hex_color):
    return np.array(cpalette.srgb(hex_color)[:3], dtype=np.float32)


def skill_plate(image, job):
    """技能圖示墊一塊職業色的圓角底板加 1 px 深色框，亮部在左上"""
    dark, light = JOB_COLORS.get(job, JOB_COLORS["novice"])
    n = image.shape[0]
    ys, xs = np.mgrid[0:n, 0:n].astype(np.float32)
    t = np.clip((xs + ys) / (2 * n), 0, 1)[..., None]
    plate = _srgb(light) * (1 - t) + _srgb(dark) * t
    r = 5.0
    cx = np.clip(np.abs(xs - (n - 1) / 2) - ((n - 1) / 2 - r), 0, None)
    cy = np.clip(np.abs(ys - (n - 1) / 2) - ((n - 1) / 2 - r), 0, None)
    inside = (np.sqrt(cx * cx + cy * cy) <= r)
    border = inside & ~(np.sqrt(np.clip(cx + 1, 0, None) ** 2 + np.clip(cy + 1, 0, None) ** 2) <= r - 0.3)
    out = np.zeros_like(image)
    out[inside, :3] = plate[inside]
    out[inside, 3] = 1.0
    out[border, :3] = _srgb(dark) * 0.45
    alpha = image[..., 3:4]
    out[..., :3] = image[..., :3] * alpha + out[..., :3] * (1 - alpha)
    return out


def build_one(kind, icon_id):
    blenv.clear_scene()
    if kind == "item":
        builder_fn, specs = ITEMS[icon_id]
    else:
        glyph, ramp = SKILLS[icon_id]
        builder_fn, specs = glyph, R(ramp, "cream" if ramp != "cream" else "iron", ramp, glow=("ember" if ramp == "ember" else "glow"))
    colors, masks, ids = mpalette.build_materials(specs, "ic_" + icon_id)
    b = mk.Builder()
    builder_fn(b)
    obj = b.to_object("Icon_" + icon_id, colors)
    mk.shade(obj, angle=math.radians(50))
    blenv.look_at([obj])
    _setup_camera()
    return _render([obj], colors, masks, ids, icon_id)


def render_all(kind, ids=None, skills_json=None):
    table = ITEMS if kind == "item" else SKILLS
    out_dir = ITEM_DIR if kind == "item" else SKILL_DIR
    os.makedirs(out_dir, exist_ok=True)
    jobs = {}
    if kind == "skill":
        data = json.load(open(os.path.join(blenv.PROJECT_ROOT, "data", "skills.json")))["skills"]
        jobs = {k: v.get("job", "novice") for k, v in data.items()}
    made = []
    for icon_id in (ids or list(table)):
        image = build_one(kind, icon_id)
        if kind == "skill":
            image = skill_plate(image, jobs.get(icon_id, "novice"))
        path = os.path.join(out_dir, icon_id + ".png")
        pixels.save_png(image, path)
        sheets.write_import(path)
        made.append(path)
    return made
