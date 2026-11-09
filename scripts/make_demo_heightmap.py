#!/usr/bin/env python3
"""Create reproducible fictional terrain; no Fortnite or project assets are used."""
from __future__ import annotations

import argparse
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from heightmap_png import write_heightmap


def smoothstep(lo, hi, x):
    t = max(0.0, min(1.0, (x-lo)/(hi-lo)))
    return t*t*(3-2*t)


def make(size=505):
    middle = (size - 1)/2.0
    samples = []
    for v in range(size):
        row = []
        for u in range(size):
            x, y = u-middle, v-middle
            radial = math.hypot(x/1.03, y/0.91)
            coast = 163 + 7*math.sin(math.atan2(y, x)*5)
            inland = 1 - smoothstep(coast - 12, coast + 15, radial)
            terrain = 3000 + 570*math.sin(x/43)*math.cos(y/55)
            height = round(28600 + inland*terrain + 50*math.sin(x/17)*math.sin(y/29))
            row.append(max(0, min(65535, height)))
        samples.append(row)
    return samples


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="demo_heightmap_505.png")
    args = ap.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    write_heightmap(output, make())
    print(f"Created synthetic 505x505 PNG: {output}")


if __name__ == "__main__":
    main()
