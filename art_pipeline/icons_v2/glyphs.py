"""圖示用的小零件：瓶子、刀劍、葉子、殼、火焰、閃電這些

道具圖示和技能圖示都是用這裡的零件在 Blender 裡堆出來，正交相機拍一張，縮到 40 px。
材質槽沿用怪物的十個槽位，色階每個圖示自己指定。
"""

import math

from mathutils import Vector

import meshkit as mk
from mpalette import SLOT_INDEX

MAIN = SLOT_INDEX["Main"]
SECOND = SLOT_INDEX["Second"]
ACCENT = SLOT_INDEX["Accent"]
BONE = SLOT_INDEX["Bone"]
DARK = SLOT_INDEX["Dark"]
METAL = SLOT_INDEX["Metal"]
WHITE = SLOT_INDEX["EyeWhite"]
PUPIL = SLOT_INDEX["Pupil"]
GLOW = SLOT_INDEX["Glow"]
WOOD = SLOT_INDEX["Wood"]

UP = Vector((0, 0, 1))
FWD = Vector((0, 1, 0))


def bottle(b, liquid=MAIN, glass=WHITE, size=1.0):
    """圓肚藥水瓶：肚子、瓶頸、木塞，液體那一格用 liquid 的顏色"""
    mk.blob(b, (0, 0, -0.10 * size), (0.30 * size, 0.30 * size, 0.30 * size), mat=liquid, segments=14, rings_count=8)
    mk.sweep(b, [(0, 0, 0.14 * size), (0, 0, 0.34 * size)], [0.11 * size, 0.11 * size], 10, mat=glass, up=FWD)
    mk.loft(b, [mk.ring((0, 0, 0.32 * size), 0.14 * size, 0.14 * size, 10), mk.ring((0, 0, 0.36 * size), 0.14 * size, 0.14 * size, 10)],
            mat=glass, cap_bottom=False)
    mk.blob(b, (0, 0, 0.42 * size), (0.09 * size, 0.09 * size, 0.07 * size), mat=WOOD, segments=8, rings_count=4)
    mk.blob(b, (-0.11 * size, -0.20 * size, 0.0), (0.06 * size, 0.04 * size, 0.09 * size), mat=WHITE, segments=6, rings_count=3)


def blade(b, length, width, hilt=WOOD, guard=True, rusty=False, two_hand=False):
    """斜放的刀劍：從左下到右上"""
    d = Vector((0.6, 0, 0.8)).normalized()
    start = -d * length * 0.5
    grip = 0.16 if not two_hand else 0.26
    mk.sweep(b, [start, start + d * grip], [0.045, 0.045], 6, mat=hilt, up=FWD)
    mk.blob(b, start, (0.06, 0.05, 0.06), mat=METAL, segments=6, rings_count=3)
    if guard:
        g = start + d * grip
        side = Vector((0.8, 0, -0.6))
        mk.sweep(b, [g - side * width * 1.6, g + side * width * 1.6], [0.035, 0.035], 6, mat=METAL, up=FWD)
    tip = start + d * length
    mk.sweep(b, [start + d * (grip + 0.02), start + d * (length * 0.8), tip],
             [width, width * 0.9, 0.004], 6, mat=(ACCENT if rusty else METAL), up=FWD, squash=[0.25, 0.25, 0.25])


def leaf(b, center, size, mat=MAIN, tilt=0.4):
    c = Vector(center)
    mk.sweep(b, [c - Vector((size * 0.5, 0, -size * tilt * 0.5)), c, c + Vector((size * 0.5, 0, size * tilt * 0.5))],
             [0.02, size * 0.28, 0.01], 6, mat=mat, up=FWD, squash=[0.2, 0.2, 0.2])


def orb(b, center, radius, mat=MAIN, glow=True):
    mk.blob(b, center, (radius, radius, radius), mat=mat, segments=14, rings_count=8)
    if glow:
        mk.blob(b, Vector(center) + Vector((-radius * 0.35, -radius * 0.5, radius * 0.35)),
                (radius * 0.28, radius * 0.18, radius * 0.22), mat=WHITE, segments=6, rings_count=3)


def flame(b, center, height, width, mat=MAIN, inner=GLOW):
    c = Vector(center)
    mk.sweep(b, [c, c + Vector((0.04, 0, height * 0.5)), c + Vector((-0.02, 0, height * 0.82)), c + Vector((0.03, 0, height))],
             [width, width * 0.8, width * 0.4, 0.01], 8, mat=mat, up=FWD)
    mk.sweep(b, [c + Vector((0, -0.01, 0.02)), c + Vector((0.02, -0.01, height * 0.4)), c + Vector((0.0, -0.01, height * 0.62))],
             [width * 0.55, width * 0.45, 0.01], 6, mat=inner, up=FWD)


def lightning(b, start, end, width, mat=GLOW):
    s, e = Vector(start), Vector(end)
    d = e - s
    n = Vector((-d.z, 0, d.x)).normalized()
    pts = [s, s + d * 0.3 + n * 0.10, s + d * 0.5 - n * 0.08, s + d * 0.75 + n * 0.09, e]
    for a, c in zip(pts, pts[1:]):
        mk.sweep(b, [a, c], [width, width], 4, mat=mat, up=FWD)


def arc_slash(b, radius, thickness, mat=WHITE, start_deg=-60, end_deg=60, steps=9):
    pts, radii = [], []
    for i in range(steps):
        t = i / (steps - 1)
        a = math.radians(start_deg + (end_deg - start_deg) * t)
        pts.append((math.sin(a) * radius, 0, math.cos(a) * radius))
        radii.append(thickness * math.sin(t * math.pi) + 0.01)
    mk.sweep(b, pts, radii, 6, mat=mat, up=FWD, squash=[0.35] * steps)


def ring(b, radius, thickness, mat=MAIN, z=0.0, squash_y=0.45):
    """躺在地上的環，從斜上方看是橢圓"""
    n = 24
    pts = [(math.cos(2 * math.pi * i / n) * radius, math.sin(2 * math.pi * i / n) * radius * squash_y, z) for i in range(n + 1)]
    mk.sweep(b, pts, [thickness] * (n + 1), 6, mat=mat, up=UP)


def star(b, center, radius, points, mat=GLOW, width=0.05):
    c = Vector(center)
    for i in range(points):
        a = 2 * math.pi * i / points
        tip = c + Vector((math.cos(a), 0, math.sin(a))) * radius
        mk.sweep(b, [c, tip], [width, 0.004], 5, mat=mat, up=FWD)


def shard(b, center, size, mat=MAIN, rot=0.3):
    c = Vector(center)
    mk.sweep(b, [c + Vector((-size * 0.5, 0, -size * 0.3)), c, c + Vector((size * 0.5, 0, size * 0.55))],
             [0.01, size * 0.32, 0.01], 5, mat=mat, up=FWD, squash=[0.35, 0.35, 0.35])


def feather(b, center, length, mat=MAIN, spine=BONE):
    c = Vector(center)
    d = Vector((0.5, 0, 0.86))
    mk.sweep(b, [c - d * length * 0.5, c, c + d * length * 0.5], [0.02, length * 0.18, 0.01], 6, mat=mat, up=FWD,
             squash=[0.2, 0.2, 0.2])
    mk.sweep(b, [c - d * length * 0.55, c + d * length * 0.45], [0.012, 0.008], 4, mat=spine, up=FWD)


def bone(b, center, length, mat=BONE):
    c = Vector(center)
    d = Vector((0.7, 0, 0.7))
    mk.sweep(b, [c - d * length * 0.5, c + d * length * 0.5], [0.05, 0.05], 6, mat=mat, up=FWD)
    for end in (c - d * length * 0.5, c + d * length * 0.5):
        for off in (Vector((-0.05, 0, 0.05)), Vector((0.05, 0, -0.05))):
            mk.blob(b, end + off, (0.07, 0.06, 0.07), mat=mat, segments=6, rings_count=3)


def pile(b, center, size, mat=MAIN, count=5):
    c = Vector(center)
    for i in range(count):
        a = 2 * math.pi * i / count
        mk.blob(b, c + Vector((math.cos(a) * size * 0.35, math.sin(a) * size * 0.2, 0)), (size * 0.32, size * 0.26, size * 0.24),
                mat=mat, segments=8, rings_count=4)
    mk.blob(b, c + Vector((0, 0, size * 0.18)), (size * 0.38, size * 0.3, size * 0.3), mat=mat, segments=8, rings_count=4)


def shell(b, center, radius, mat=MAIN, ridge=DARK):
    """蝸牛殼：一顆球加幾道螺旋紋"""
    orb(b, center, radius, mat=mat, glow=False)
    c = Vector(center)
    for k in range(3):
        r = radius * (1.02 - k * 0.22)
        pts = [c + Vector((math.cos(a) * r, -math.sin(a) * r * 0.5 - radius * 0.3, math.sin(a) * r)) for a in
               [math.radians(20 + i * 30) for i in range(7)]]
        mk.sweep(b, pts, [0.045] * 7, 5, mat=ACCENT, up=FWD)


def cloth_square(b, center, size, mat=MAIN, fold=0.12):
    c = Vector(center)
    mk.box(b, c, (size, size * 0.15, size * 0.75), mat=mat, taper=(0.9, 1.0), shear=fold)
    mk.box(b, c + Vector((0, -size * 0.09, -size * 0.1)), (size * 0.75, size * 0.04, size * 0.5), mat=SECOND)
