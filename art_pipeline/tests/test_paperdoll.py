"""紙娃娃換裝產圖端的規矩：像素化不留半透明、顏色都在調色盤裡、槽位不撞、裁切的圖層疊回去位置對。

跑法和其他美術管線測試一樣：blender -b --factory-startup --python-exit-code 1 -P art_pipeline/tests/run.py
"""
import os
import sys

# Blender 內建的 Python 沒有 Pillow，run.py 看到這個旗標會改叫系統的 python3 跑
NEEDS_PILLOW = True

PIPELINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PIPELINE_DIR, "characters_v5"))


def _palette():
    import pixelize
    return pixelize.Palette()


def test_pixelize_leaves_no_half_transparent_pixel_and_only_palette_colours():
    import numpy as np
    import pixelize
    palette = _palette()
    work = np.zeros((64, 64, 4), dtype=np.uint8)
    yy, xx = np.mgrid[0:64, 0:64]
    disc = (xx - 30) ** 2 + (yy - 34) ** 2 < 22 ** 2
    work[disc] = (200, 120, 90, 255)
    # 邊緣一圈半透明，模擬抗鋸齒
    ring = ((xx - 30) ** 2 + (yy - 34) ** 2 >= 22 ** 2) & ((xx - 30) ** 2 + (yy - 34) ** 2 < 24 ** 2)
    work[ring] = (200, 120, 90, 90)
    rgba, index, stats = pixelize.pixelize(work, 4, palette)
    alpha = rgba[..., 3]
    assert set(np.unique(alpha)) <= {0, 255}
    colours = {tuple(c) for c in palette.colours.tolist()}
    used = {tuple(c) for c in rgba[alpha > 0][:, :3].tolist()}
    assert used <= colours
    assert stats["semi_after"] == 0


def test_outline_is_the_ink_of_the_material_not_one_black():
    import numpy as np
    import pixelize
    palette = _palette()
    skin = palette.ramps["skin_base"][2]
    cloth = palette.ramps["cloth_white"][2]
    work = np.zeros((40, 80, 4), dtype=np.uint8)
    work[8:32, 8:36] = skin + (255,)
    work[8:32, 44:72] = cloth + (255,)
    rgba, _, _ = pixelize.pixelize(work, 4, palette)
    left_edge = tuple(rgba[5, 2, :3])
    right_edge = tuple(rgba[5, 11, :3])
    assert left_edge == palette.ink["skin_base"]
    assert right_edge == palette.ink["cloth_white"]
    assert left_edge != right_edge


def test_despeckle_keeps_ink_lines_whole():
    import numpy as np
    import pixelize
    palette = _palette()
    ink_a = palette.ink_base
    ink_b = palette.ink_base + 1
    base = palette.ramp_names.index("cloth_white")
    cloth = [i for i, r in enumerate(palette.ramp_of) if r == "cloth_white" and palette.step_of[i] == 2][0]
    index = np.full((9, 9), cloth)
    # 一條斜的墨線，兩種墨色輪流出現
    for i in range(9):
        index[i, i] = ink_a if i % 2 else ink_b
    solid = np.ones((9, 9), dtype=bool)
    out, _, _ = pixelize.despeckle(index.copy(), solid, palette.lab, palette.step_of)
    assert all(palette.step_of[out[i, i]] < 0 for i in range(9)), base


def test_slots_do_not_collide_between_parts():
    import paperdoll
    for direction in ("s", "sw", "w", "nw", "n"):
        seen = {}
        for key, table in paperdoll.SLOTS.items():
            value = table[direction]
            assert value != 0, key
            assert value not in seen, (direction, key, seen.get(value))
            seen[value] = key
        for key, (back, front) in paperdoll.HAND_SLOTS.items():
            for value in (back, front):
                assert value != 0 and value not in seen, (direction, key, value)
                seen[value] = key


def test_cape_and_back_hair_swap_sides_between_front_and_back_views():
    import paperdoll
    assert paperdoll.SLOTS["cape"]["s"] < 0 < paperdoll.SLOTS["cape"]["n"]
    assert paperdoll.SLOTS["hair_back"]["s"] < 0 < paperdoll.SLOTS["hair_back"]["n"]
    for direction in ("s", "sw", "w", "nw", "n"):
        assert paperdoll.SLOTS["head_top"][direction] > paperdoll.SLOTS["hair_front"][direction]
        assert paperdoll.SLOTS["head_low"][direction] > paperdoll.SLOTS["hair_front"][direction]


def test_shelf_pack_keeps_gap_between_pieces():
    import numpy as np
    import paperdoll
    rng = np.random.default_rng(3)
    cells = {i: np.zeros((int(rng.integers(3, 60)), int(rng.integers(3, 90)), 4), dtype=np.uint8) for i in range(80)}
    (width, height), places = paperdoll.shelf_pack(cells, width=256)
    used = np.zeros((height, width), dtype=int)
    for key, (x, y) in places.items():
        h, w = cells[key].shape[:2]
        assert x + w <= width and y + h <= height
        # 往右下多算間距那麼寬，互相碰到就是間距不夠，mipmap 會吃到隔壁
        used[y:y + h + paperdoll.SHELF_GAP_PX, x:x + w + paperdoll.SHELF_GAP_PX] += 1
    assert used.max() == 1


def test_composite_draws_higher_slots_on_top():
    import numpy as np
    import paperdoll

    class Fake:
        def __init__(self, colour, slot, offset):
            self.colour, self.slot, self.offset = colour, slot, offset

        def cell(self, action, direction, frame):
            rgba = np.zeros((4, 4, 4), dtype=np.uint8)
            rgba[...] = self.colour + (255,)
            return rgba, self.offset, self.slot

    back = Fake((255, 0, 0), -20, (-2, -2))
    body = Fake((0, 255, 0), 0, (-2, -2))
    front = Fake((0, 0, 255), 20, (-1, -1))
    image = np.asarray(paperdoll.composite([front, body, back], "idle", "s", 0, (8, 8), (4, 4)))
    assert tuple(image[3, 3, :3]) == (0, 0, 255)
    assert tuple(image[2, 2, :3]) == (0, 255, 0)
