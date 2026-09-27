import numpy as np

from common import atlas


def _frame(value, size=2):
    frame = np.zeros((size, size, 4), dtype=np.float32)
    frame[..., :] = value
    return frame


def test_pack_grid_places_frames_by_row_and_column():
    rows = [[_frame(0.1), _frame(0.2)], [_frame(0.3), _frame(0.4)]]
    result = atlas.pack_grid(rows)
    assert result.shape == (4, 4, 4)
    assert np.allclose(result[0:2, 2:4], 0.2)
    assert np.allclose(result[2:4, 0:2], 0.3)


def test_pack_grid_leaves_short_rows_transparent():
    rows = [[_frame(1.0), _frame(1.0), _frame(1.0)], [_frame(0.5)]]
    result = atlas.pack_grid(rows)
    assert result.shape == (4, 6, 4)
    assert np.allclose(result[2:4, 2:6], 0.0)


def test_pack_actions_lays_frames_end_to_end():
    # idle 兩格、walk 三格，兩個方向，一列放四格
    actions = [
        ("idle", [[_frame(0.1), _frame(0.11)], [_frame(0.12), _frame(0.13)]]),
        ("walk", [[_frame(0.2), _frame(0.21), _frame(0.22)],
                  [_frame(0.23), _frame(0.24), _frame(0.25)]]),
    ]
    result, starts, rows = atlas.pack_actions(actions, 2, 4)
    assert starts == {"idle": 0, "walk": 4}
    assert rows == 3  # 4 + 6 = 10 格，一列四格
    assert result.shape == (6, 8, 4)
    # 第 0 格在左上角
    assert np.allclose(result[0:2, 0:2], 0.1)
    # walk 第二個方向第 0 格是第 7 格，也就是第 1 列第 3 欄
    assert np.allclose(result[2:4, 6:8], 0.23)
    # 最後一格是第 9 格，第 2 列第 1 欄；後面留白
    assert np.allclose(result[4:6, 2:4], 0.25)
    assert np.allclose(result[4:6, 4:8], 0.0)


def test_pack_actions_needs_the_same_frame_count_in_every_direction():
    actions = [("idle", [[_frame(0.1)], [_frame(0.2), _frame(0.3)]])]
    try:
        atlas.pack_actions(actions, 2, 4)
    except ValueError as error:
        assert "格數不一樣" in str(error)
    else:
        raise AssertionError("方向之間格數不一樣應該要擋下來")


def test_pack_actions_is_smaller_than_the_same_actions_on_a_grid():
    actions = [
        ("idle", [[_frame(0.1)] * 2] * 5),
        ("walk", [[_frame(0.2)] * 8] * 5),
        ("attack", [[_frame(0.3)] * 6] * 5),
    ]
    packed, _, rows = atlas.pack_actions(actions, 5, 8)
    grid = atlas.pack_grid([row for _, per_direction in actions for row in per_direction])
    assert rows == 10          # (2 + 8 + 6) × 5 = 80 格，一列八格
    assert grid.shape[0] // 2 == 15   # 3 個動作 × 5 個方向
    assert packed.size < grid.size
