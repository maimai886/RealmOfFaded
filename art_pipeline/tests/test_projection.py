import math

from common import projection


def test_feet_pixel_is_below_center_by_projected_height():
    origin = projection.feet_pixel(frame_px=128, target_height=1.0, px_per_m=64.0, elevation_deg=60.0)
    assert origin[0] == 64.0
    assert math.isclose(origin[1], 64.0 + 32.0)


def test_facing_angle_turns_clockwise_45_degrees_per_direction():
    assert projection.facing_angle_deg(0) == 0.0
    assert projection.facing_angle_deg(2) == -90.0
    assert projection.facing_angle_deg(4) == -180.0
