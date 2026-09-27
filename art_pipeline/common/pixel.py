"""
像素風 sprite 後製，都是純 numpy，陣列格式為 (高, 寬, 4) 的直接 alpha。
流程：高解析度算圖 → 縮小 → alpha 二值化 → 輪廓內圈加深成同色系描邊
"""
import numpy as np


def downsample(image, factor):
    """用 alpha 加權平均縮小，透明像素的顏色才不會把邊緣染黑"""
    height, width = image.shape[0] // factor, image.shape[1] // factor
    blocks = image[:height * factor, :width * factor].reshape(height, factor, width, factor, 4)
    alpha = blocks[..., 3].mean(axis=(1, 3))
    weighted = (blocks[..., :3] * blocks[..., 3:4]).mean(axis=(1, 3))
    color = np.where(alpha[..., None] > 1e-6, weighted / np.maximum(alpha[..., None], 1e-6), 0.0)
    return np.concatenate([color, alpha[..., None]], axis=2).astype(np.float32)


def harden_alpha(image, threshold=0.5):
    result = image.copy()
    result[..., 3] = (image[..., 3] >= threshold).astype(np.float32)
    result[result[..., 3] == 0, :3] = 0.0
    return result


def outline_inner_edge(image, darken=0.5):
    """不透明且上下左右任一邊是透明的像素，顏色乘上 (1 - darken)"""
    solid = image[..., 3] > 0.5
    padded = np.pad(solid, 1, constant_values=False)
    neighbors_solid = (padded[:-2, 1:-1] & padded[2:, 1:-1] & padded[1:-1, :-2] & padded[1:-1, 2:])
    edge = solid & ~neighbors_solid
    result = image.copy()
    result[edge, :3] *= (1.0 - darken)
    return result


def pixelate(image, factor, darken=0.5):
    return outline_inner_edge(harden_alpha(downsample(image, factor)), darken)
