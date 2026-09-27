import numpy as np

from textures import tileable


def test_edge_weight_is_zero_at_border_and_one_in_middle():
    weight = tileable.edge_weight(100)
    assert weight[0, 0] < 0.01
    assert weight[50, 50] > 0.99
    assert np.allclose(weight, weight.T)


def test_make_tileable_wraps_without_seam():
    rng = np.random.default_rng(1)
    image = rng.random((64, 64, 4)).astype(np.float32)
    result = tileable.make_tileable(image)
    # 最右一欄和最左一欄在原圖是相鄰的，接縫差距要跟圖內相鄰欄差不多小
    seam = np.abs(result[:, -1] - result[:, 0]).mean()
    inside = np.abs(image[:, 31] - image[:, 32]).mean()
    assert seam <= inside * 1.05


def test_grade_keeps_ro_palette_rules():
    # 純黑要被抬起來、純白要往奶油色收、螢光色的飽和度要被壓到上限以下
    black = tileable.grade(np.zeros((1, 1, 3), dtype=np.float32))
    assert black.min() > 0.02
    white = tileable.grade(np.ones((1, 1, 3), dtype=np.float32))
    assert white[0, 0, 0] > white[0, 0, 2]
    neon = tileable.grade(np.array([[[0.0, 1.0, 0.0]]], dtype=np.float32))
    top = neon.max()
    sat = (top - neon.min()) / top
    assert sat <= tileable.SATURATION_CAP + 1e-4


def test_fit_square_bottom_alignment_and_resize():
    # 寬扁的圖縮進正方形後貼底：下半有內容、上半透明、左右兩邊都到底
    image = np.zeros((20, 40, 4), dtype=np.float32)
    image[..., 3] = 1.0
    result = tileable.fit_square(image, 32, align="bottom")
    assert result.shape == (32, 32, 4)
    assert result[31, 16, 3] > 0.99
    assert result[31, 0, 3] > 0.99
    assert result[0, 16, 3] < 0.01
    assert result[12, 16, 3] < 0.01


def test_box_down_averages():
    image = np.arange(16, dtype=np.float32).reshape(4, 4, 1)
    small = tileable.box_down(image, 2)
    assert small.shape == (2, 2, 1)
    assert abs(small[0, 0, 0] - 2.5) < 1e-5
