"""Exact Euclidean distance to land pixels, in metres, in O(width*height).

The separable squared distance transform uses lower envelopes of parabolas,
with independent pixel spacings on X and Y. A shoreline is defined as the
nearest *land pixel centre*, not as the contour between land and water.
"""
from __future__ import annotations

import math

INF = float("inf")


def squared_distance_1d(costs: list[float], spacing_m: float) -> list[float]:
    """Compute min_j(costs[j] + ((i-j)*spacing_m)^2)."""
    if spacing_m <= 0 or not math.isfinite(spacing_m):
        raise ValueError("Pixel spacing must be a positive finite number")
    n = len(costs)
    sites = [i for i, cost in enumerate(costs) if math.isfinite(cost)]
    if not sites:
        return [INF] * n
    a = spacing_m * spacing_m
    v = [0] * len(sites)
    z = [0.0] * (len(sites) + 1)
    k = 0
    v[0] = sites[0]
    z[0] = -INF
    z[1] = INF
    for q in sites[1:]:
        s = ((costs[q] + a*q*q) - (costs[v[k]] + a*v[k]*v[k])) / (2*a*(q-v[k]))
        while s <= z[k]:
            k -= 1
            s = ((costs[q] + a*q*q) - (costs[v[k]] + a*v[k]*v[k])) / (2*a*(q-v[k]))
        k += 1
        v[k] = q
        z[k] = s
        z[k+1] = INF
    out = []
    k = 0
    for i in range(n):
        while z[k+1] < i:
            k += 1
        out.append(a*(i-v[k])**2 + costs[v[k]])
    return out


def euclidean_distance_to_land(land: list[list[bool]], step_x_m: float,
                               step_y_m: float) -> list[list[float]]:
    """Return true Euclidean distance to nearest True pixel, in metres."""
    height = len(land)
    width = len(land[0]) if height else 0
    if width < 2 or height < 2 or any(len(row) != width for row in land):
        raise ValueError("Land mask must be rectangular and at least 2x2")
    if not any(any(row) for row in land):
        raise ValueError("No land pixels found above configured water cutoff")
    horizontal = [squared_distance_1d([0.0 if cell else INF for cell in row], step_x_m)
                  for row in land]
    squared = [[0.0] * width for _ in range(height)]
    for u in range(width):
        column = squared_distance_1d([horizontal[v][u] for v in range(height)], step_y_m)
        for v in range(height):
            squared[v][u] = math.sqrt(column[v])
    return squared
