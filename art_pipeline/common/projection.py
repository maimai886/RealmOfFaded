import math


def feet_pixel(frame_px, target_height, px_per_m, elevation_deg):
    """相機看向原點上方 target_height 處時，地面原點落在畫格裡的像素座標，由左上角起算"""
    below_center = target_height * math.cos(math.radians(elevation_deg)) * px_per_m
    return [frame_px / 2.0, frame_px / 2.0 + below_center]


def facing_angle_deg(direction_index):
    """模型預設面向 -Y 也就是面向鏡頭，每往下一個方向順時針轉 45 度"""
    return -45.0 * direction_index
