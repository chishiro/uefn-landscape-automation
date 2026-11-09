import math
import random

import pytest

from shore_distance import euclidean_distance_to_land, squared_distance_1d


def test_exact_diagonal_distance():
    land = [[False] * 5 for _ in range(5)]
    land[0][0] = True
    result = euclidean_distance_to_land(land, 1.0, 1.0)
    assert result[1][2] == pytest.approx(math.sqrt(5))
    assert result[4][4] == pytest.approx(math.sqrt(32))


def test_anisotropic_pixel_scale():
    land = [[False] * 4 for _ in range(4)]
    land[1][0] = True
    result = euclidean_distance_to_land(land, 2.0, 3.0)
    assert result[2][2] == pytest.approx(math.sqrt(4**2 + 3**2))


@pytest.mark.parametrize('step_x,step_y', [(1, 1), (1.5, 3), (0.8, 2.25)])
def test_bruteforce_reference_multiple_land_positions(step_x, step_y):
    rng = random.Random(42)
    land = [[rng.random() < 0.21 for _ in range(11)] for _ in range(9)]
    land[0][0] = True
    result = euclidean_distance_to_land(land, step_x, step_y)
    sites = [(x, y) for y, row in enumerate(land) for x, cell in enumerate(row) if cell]
    for y, row in enumerate(result):
        for x, val in enumerate(row):
            true_value = min(math.hypot((x-u)*step_x, (y-v)*step_y) for u, v in sites)
            assert val == pytest.approx(true_value, abs=1e-8)


def test_no_land_rejected():
    with pytest.raises(ValueError, match='No land pixels'):
        euclidean_distance_to_land([[False] * 4 for _ in range(3)], 1, 1)


def test_sparse_1d():
    c = [float('inf'), 4.0, float('inf'), 0.0, float('inf')]
    assert squared_distance_1d(c, 2) == pytest.approx([8, 4, 4, 0, 4])
