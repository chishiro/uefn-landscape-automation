#!/usr/bin/env python3
"""Create the tracked, fictional regression fixture used by pytest."""
from __future__ import annotations
import argparse
import math
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from heightmap_png import write_heightmap

def make(size: int = 33) -> list[list[int]]:
    middle = (size - 1) / 2
    rows = []
    for v in range(size):
        row = []
        for u in range(size):
            x, y = u - middle, v - middle
            radius = math.hypot(x / 1.2, y / 0.85)
            land = max(0.0, 1.0 - (radius - 5.5) / 6.5)
            detail = 140 * math.sin(x / 2.7) * math.cos(y / 3.4)
            row.append(round(28900 + 3300 * land + detail))
        rows.append(row)
    return rows

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("tests/fixtures"))
    parser.add_argument("--check", action="store_true",
                        help="compare a temporary regeneration without changing files")
    args = parser.parse_args()
    if args.check:
        with tempfile.TemporaryDirectory(prefix="uefn-fixture-") as temp_dir:
            candidate = Path(temp_dir) / "coastal_33.png"
            write_heightmap(candidate, make())
            expected = args.output_dir / "coastal_33.png"
            if not expected.exists():
                raise SystemExit(f"Missing tracked fixture: {expected}")
            if candidate.read_bytes() != expected.read_bytes():
                raise SystemExit("Fixture is stale; regenerate it with this script")
        print(f"Fixture is reproducible: {expected}")
        return
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_heightmap(args.output_dir / "coastal_33.png", make())
    print(f"Created deterministic fixture in {args.output_dir}")

if __name__ == "__main__":
    main()
