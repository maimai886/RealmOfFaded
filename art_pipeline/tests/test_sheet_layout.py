# -*- coding: utf-8 -*-
"""緊密排的契約：圖怎麼排、meta 怎麼寫，兩邊要對得起來

引擎那一半的測試在 tests/test_sprite_sheet.gd，換算方式在 docs/精靈圖規格.md。
"""
import numpy as np

from common import atlas, sheet_output


DIRECTIONS = ["s", "sw", "w", "nw", "n"]


def _frame(value, size=2):
    frame = np.zeros((size, size, 4), dtype=np.float32)
    frame[..., :] = value
    return frame


def _actions():
    return [
        ("idle", [[_frame(0.1)] * 4] * 5),
        ("walk", [[_frame(0.2)] * 8] * 5),
        ("attack", [[_frame(0.3)] * 6] * 5),
    ]


def test_packed_meta_records_where_each_action_starts():
    _, starts, _ = atlas.pack_actions(_actions(), 5, 8)
    meta = {
        "frame_size": [96, 96],
        "columns": 8,
        "directions": DIRECTIONS,
        "actions": {
            "idle": {"row": 0, "frames": 4, "fps": 6, "loop": True},
            "walk": {"row": 1, "frames": 8, "fps": 12, "loop": True},
            "attack": {"row": 2, "frames": 6, "fps": 12, "loop": False},
        },
    }
    packed = sheet_output.packed_meta(meta, starts, 8)
    assert packed["layout"] == "packed"
    assert packed["actions"]["idle"]["start"] == 0
    assert packed["actions"]["walk"]["start"] == 20
    assert packed["actions"]["attack"]["start"] == 60
    # 緊密排不看 row，留著只會和 start 互相矛盾
    assert "row" not in packed["actions"]["walk"]
    assert packed["actions"]["walk"]["fps"] == 12
    # 原本那一份不能被改到
    assert "layout" not in meta and meta["actions"]["walk"]["row"] == 1


def test_packed_meta_rows_match_the_image_height():
    image, starts, rows = atlas.pack_actions(_actions(), 5, 8)
    meta = sheet_output.packed_meta(
        {"columns": 8, "actions": {name: {"frames": frames}
                                   for name, frames in [("idle", 4), ("walk", 8), ("attack", 6)]}},
        starts, 8)
    assert sheet_output.sheet_rows(meta["actions"], 5, 8) == rows
    assert image.shape[0] == rows * 2


def test_packed_meta_refuses_a_mismatched_action_list():
    _, starts, _ = atlas.pack_actions(_actions(), 5, 8)
    try:
        sheet_output.packed_meta({"columns": 8, "actions": {"idle": {"frames": 4}}}, starts, 8)
    except ValueError as error:
        assert "對不起來" in str(error)
    else:
        raise AssertionError("動作對不起來應該要擋下來")
