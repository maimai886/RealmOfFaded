import numpy as np

from common import pixel


def test_downsample_ignores_color_of_transparent_pixels():
    image = np.zeros((2, 2, 4), dtype=np.float32)
    image[0, 0] = (1.0, 0.5, 0.0, 1.0)
    result = pixel.downsample(image, 2)
    assert result.shape == (1, 1, 4)
    assert np.allclose(result[0, 0, :3], (1.0, 0.5, 0.0))
    assert np.isclose(result[0, 0, 3], 0.25)


def test_harden_alpha_is_binary():
    image = np.zeros((1, 3, 4), dtype=np.float32)
    image[0, :, 3] = (0.2, 0.5, 0.9)
    image[0, :, 0] = 1.0
    result = pixel.harden_alpha(image)
    assert list(result[0, :, 3]) == [0.0, 1.0, 1.0]
    assert result[0, 0, 0] == 0.0


def test_outline_darkens_only_border_pixels():
    image = np.zeros((5, 5, 4), dtype=np.float32)
    image[1:4, 1:4] = (1.0, 1.0, 1.0, 1.0)
    result = pixel.outline_inner_edge(image, darken=0.5)
    assert np.allclose(result[2, 2, :3], 1.0)
    assert np.allclose(result[1, 2, :3], 0.5)
    assert result[0, 0, 3] == 0.0
