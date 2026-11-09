#!/usr/bin/env python3
"""Config-driven, non-destructive UEFN landscape heightmap automation.

Offline only. Does not connect to, edit, or launch UEFN/Unreal Editor.
Standard library only; supports arbitrary dimensions of 16-bit gray PNGs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any

from heightmap_png import read_heightmap, write_heightmap, write_rgb
from shore_distance import euclidean_distance_to_land

OUTPUT_NAMES = ("heightmap.png", "preview.png", "difference.png", "report.json", "report.md")


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object")
    return value


def _number(value: Any, name: str, minimum: float | None = None,
            maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if minimum is not None and value < minimum or maximum is not None and value > maximum:
        raise ValueError(f"{name} must be within {minimum}..{maximum}")
    return float(value)


def _pair(value: Any, name: str) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{name} must contain two numbers")
    return (_number(value[0], name + "[0]"), _number(value[1], name + "[1]"))


def _smoothstep(a: float, b: float, x: float) -> float:
    t = max(0.0, min(1.0, (x-a)/(b-a)))
    return t*t*(3.0 - 2.0*t)


def load_config(path: str | Path) -> dict[str, Any]:
    """Parse and validate an explicit JSON job configuration."""
    raw = _object(json.loads(Path(path).read_text(encoding="utf-8")), "config")
    if raw.get("schema_version") != 1:
        raise ValueError("schema_version must be 1")
    land = _object(raw.get("landscape"), "landscape")
    transform = _object(land.get("transform"), "landscape.transform")
    origin = transform.get("origin_xy_cm")
    scale = transform.get("scale_xyz_cm")
    _pair(origin, "origin_xy_cm")
    if not isinstance(scale, list) or len(scale) != 3:
        raise ValueError("scale_xyz_cm must contain three numbers")
    for index, entry in enumerate(scale):
        _number(entry, f"scale_xyz_cm[{index}]", minimum=0.00001)
    _number(transform.get("location_z_cm"), "location_z_cm")
    if land.get("row_zero_world_y") not in ("min", "max"):
        raise ValueError("row_zero_world_y must be explicitly set to 'min' or 'max'")
    ocean = _object(raw.get("ocean"), "ocean")
    _number(ocean.get("sea_level_sample"), "sea_level_sample", 0, 65535)
    _number(ocean.get("land_threshold_offset_samples"), "land_threshold_offset_samples", 0, 65535)
    operation = _object(raw.get("operation"), "operation")
    if operation.get("type") != "deepen_seabed":
        raise ValueError("Only operation.type='deepen_seabed' is currently implemented")
    for field in ("shore_start_m", "shore_full_depth_m", "boundary_start_m", "boundary_end_m"):
        _number(operation.get(field), field, 0)
    if operation["shore_full_depth_m"] <= operation["shore_start_m"]:
        raise ValueError("shore_full_depth_m must be > shore_start_m")
    if operation["boundary_end_m"] <= operation["boundary_start_m"]:
        raise ValueError("boundary_end_m must be > boundary_start_m")
    for field in ("shore_extra_samples", "boundary_extra_samples"):
        _number(operation.get(field), field, 0, 65535)
    _number(operation.get("edge_target_sample"), "edge_target_sample", 0, 65535)
    if operation["edge_target_sample"] >= ocean["sea_level_sample"]:
        raise ValueError("edge_target_sample must be below sea_level_sample")
    if ocean["sea_level_sample"] + ocean["land_threshold_offset_samples"] > 65535:
        raise ValueError("Sea cutoff exceeds maximum 16-bit sample")
    regions = raw.get("protected_regions", [])
    if not isinstance(regions, list):
        raise ValueError("protected_regions must be an array")
    for index, region in enumerate(regions):
        region = _object(region, f"protected_regions[{index}]")
        if region.get("shape") not in ("circle", "ellipse"):
            raise ValueError(f"protected_regions[{index}].shape must be circle or ellipse")
        if region.get("coordinate_space") not in ("world_cm", "pixel"):
            raise ValueError(f"protected_regions[{index}].coordinate_space must be world_cm or pixel")
        _pair(region.get("center"), f"protected_regions[{index}].center")
        radius = region.get("radius_m")
        if region["shape"] == "circle":
            _number(radius, f"protected_regions[{index}].radius_m", 0.00001)
        else:
            rx, ry = _pair(radius, f"protected_regions[{index}].radius_m")
            if rx <= 0 or ry <= 0:
                raise ValueError("Ellipse radii must be positive")
    check_list = raw.get("orientation_checks", [])
    if not isinstance(check_list, list):
        raise ValueError("orientation_checks must be an array")
    for index, check in enumerate(check_list):
        check = _object(check, f"orientation_checks[{index}]")
        _pair(check.get("world_xy_cm"), f"orientation_checks[{index}].world_xy_cm")
        _number(check.get("expected_z_cm"), "expected_z_cm")
        _number(check.get("tolerance_cm"), "tolerance_cm", minimum=0)
    validation = _object(raw.get("validation", {}), "validation")
    if not isinstance(validation.get("require_all_edges_below_sea", True), bool):
        raise ValueError("validation.require_all_edges_below_sea must be bool")
    return raw


def _world_to_pixel(x: float, y: float, config: dict[str, Any],
                    width: int, height: int, reverse: bool = False) -> tuple[float, float]:
    land = config["landscape"]
    trans = land["transform"]
    ox, oy = trans["origin_xy_cm"]
    sx, sy, _ = trans["scale_xyz_cm"]
    u = (x-ox)/sx
    low_row = (y-oy)/sy
    top_low = (land["row_zero_world_y"] == "min") != reverse
    return u, low_row if top_low else (height - 1 - low_row)


def _world_height(sample: int, config: dict[str, Any]) -> float:
    transform = config["landscape"]["transform"]
    return transform["location_z_cm"] + ((sample - 32768) * transform["scale_xyz_cm"][2] / 128.0)


def verify_orientation(source: list[list[int]], config: dict[str, Any]) -> dict[str, Any]:
    """Never claim row orientation was measured when no checks were supplied."""
    checks = config.get("orientation_checks", [])
    if not checks:
        return {"status": "configured_not_independently_verified", "checks": 0}
    width, height = len(source[0]), len(source)
    chosen_errors = []
    opposite_errors = []
    opposite_passes = []
    for check in checks:
        x, y = check["world_xy_cm"]
        for reverse, results in ((False, chosen_errors), (True, opposite_errors)):
            u, v = _world_to_pixel(x, y, config, width, height, reverse)
            ui, vi = round(u), round(v)
            if not (0 <= ui < width and 0 <= vi < height):
                raise ValueError("Orientation check position lies outside input heightmap")
            z_cm = _world_height(source[vi][ui], config)
            results.append(abs(z_cm - check["expected_z_cm"]))
        opposite_passes.append(opposite_errors[-1] <= check["tolerance_cm"])
        if chosen_errors[-1] > check["tolerance_cm"]:
            raise ValueError(f"Orientation check failed at ({x}, {y}) cm: error "
                             f"{chosen_errors[-1]:.3f} cm > {check['tolerance_cm']} cm")
    # Passing control points cannot distinguish row order if both directions fit.
    status = ("control_points_consistent_but_orientation_ambiguous"
              if all(opposite_passes) else "verified_against_supplied_control_points")
    return {"status": status, "checks": len(checks),
            "max_error_cm": max(chosen_errors),
            "opposite_orientation_max_error_cm": max(opposite_errors)}


def protection_mask(width: int, height: int, config: dict[str, Any]) -> list[list[bool]]:
    result = [[False] * width for _ in range(height)]
    trans = config["landscape"]["transform"]
    step_x, step_y = trans["scale_xyz_cm"][0] / 100.0, trans["scale_xyz_cm"][1] / 100.0
    for region in config.get("protected_regions", []):
        cx, cy = region["center"]
        if region["coordinate_space"] == "world_cm":
            cx, cy = _world_to_pixel(cx, cy, config, width, height)
        radii = (region["radius_m"], region["radius_m"]) if region["shape"] == "circle" else region["radius_m"]
        rx, ry = radii
        min_u = max(0, math.floor(cx - rx/step_x))
        max_u = min(width-1, math.ceil(cx + rx/step_x))
        min_v = max(0, math.floor(cy - ry/step_y))
        max_v = min(height-1, math.ceil(cy + ry/step_y))
        for v in range(min_v, max_v+1):
            for u in range(min_u, max_u+1):
                if (((u-cx)*step_x/rx)**2 + ((v-cy)*step_y/ry)**2) <= 1:
                    result[v][u] = True
    return result


def analyze(source: list[list[int]], config: dict[str, Any]):
    height, width = len(source), len(source[0])
    ocean = config["ocean"]
    threshold = ocean["sea_level_sample"] + ocean["land_threshold_offset_samples"]
    land = [[sample > threshold for sample in row] for row in source]
    sx, sy, _ = config["landscape"]["transform"]["scale_xyz_cm"]
    distance = euclidean_distance_to_land(land, sx/100.0, sy/100.0)
    mask = protection_mask(width, height, config)
    return land, distance, mask


def generate(source: list[list[int]], config: dict[str, Any], land, distance, mask):
    height, width = len(source), len(source[0])
    op = config["operation"]
    sx, sy, _ = config["landscape"]["transform"]["scale_xyz_cm"]
    output = [row[:] for row in source]
    for v in range(height):
        for u in range(width):
            if land[v][u] or mask[v][u]:
                continue
            shoreline = op["shore_extra_samples"] * _smoothstep(
                op["shore_start_m"], op["shore_full_depth_m"], distance[v][u]
            )
            boundary_distance = min(u*sx, (width-1-u)*sx, v*sy, (height-1-v)*sy)/100.0
            boundary = op["boundary_extra_samples"] * (1.0 - _smoothstep(
                op["boundary_start_m"], op["boundary_end_m"], boundary_distance
            ))
            extra = round(max(shoreline, boundary))
            output[v][u] = max(0, source[v][u] - extra)
            if u in (0, width-1) or v in (0, height-1):
                # Never raise a pixel, even if the requested edge target is higher.
                output[v][u] = min(output[v][u], int(op["edge_target_sample"]))
    return output


def validate(source: list[list[int]], output: list[list[int]], config, land, mask,
             expected: list[list[int]] | None = None) -> dict[str, Any]:
    height, width = len(source), len(source[0])
    if len(output) != height or any(len(row) != width for row in output):
        raise ValueError("Output dimensions do not match the original heightmap")
    if expected is not None and (len(expected) != height or any(len(row) != width for row in expected)):
        raise ValueError("Expected output dimensions do not match the original heightmap")
    changed = 0
    max_deepening = 0
    protected_count = 0
    water_count = 0
    editable_water_count = 0
    expected_errors = 0
    protected_errors = 0
    land_errors = 0
    raised_errors = 0
    for v in range(height):
        for u in range(width):
            before, after = source[v][u], output[v][u]
            if mask[v][u]:
                protected_count += 1
                protected_errors += before != after
            if land[v][u]:
                land_errors += before != after
            else:
                water_count += 1
                if not mask[v][u]:
                    editable_water_count += 1
            if expected is not None:
                expected_errors += after != expected[v][u]
            raised_errors += after > before
            if before != after:
                changed += 1
                max_deepening = max(max_deepening, before-after)
    sea = config["ocean"]["sea_level_sample"]
    edge_values = [output[v][u] for v in range(height) for u in range(width)
                   if v in (0, height-1) or u in (0, width-1)]
    report = {
        "width": width, "height": height,
        "source_range": [min(map(min, source)), max(map(max, source))],
        "output_range": [min(map(min, output)), max(map(max, output))],
        "changed_samples": changed, "water_source_samples": water_count,
        "editable_water_samples": editable_water_count,
        "protected_samples": protected_count, "max_deepening_samples": max_deepening,
        "protected_changed_samples": protected_errors,
        "land_changed_samples": land_errors, "raised_samples": raised_errors,
        "edge_sample_range": [min(edge_values), max(edge_values)],
        "edges_below_sea": max(edge_values) < sea,
        "sea_level_sample": sea,
    }
    failures = []
    if protected_errors:
        failures.append(f"{protected_errors} protected samples were changed")
    if land_errors:
        failures.append(f"{land_errors} land samples were changed")
    if raised_errors:
        failures.append(f"{raised_errors} samples were raised")
    if config.get("validation", {}).get("require_all_edges_below_sea", True) and not report["edges_below_sea"]:
        failures.append("one or more boundary pixels are at/above sea level")
    if not editable_water_count:
        failures.append("no editable water pixels found")
    if expected is not None:
        report["expected_mismatched_samples"] = expected_errors
        if expected_errors:
            failures.append(f"{expected_errors} samples differ from the expected generated heightmap")
    report["passed"] = not failures
    report["failures"] = failures
    return report


def _previews(source, output, sea):
    width = len(source[0])
    lower, upper = min(map(min, output)), max(map(max, output))
    delta_max = max(max(a-b for a, b in zip(old, new)) for old, new in zip(source, output))
    preview, diff = [], []
    for before_row, after_row in zip(source, output):
        a, b = bytearray(), bytearray()
        for before, after in zip(before_row, after_row):
            if after <= sea:
                t = (after-lower) / max(1, sea-lower)
                color = (int(16 + t*22), int(44 + t*65), int(86 + t*77))
            else:
                t = (after-sea) / max(1, upper-sea)
                color = (int(58 + t*100), int(112 + t*83), int(52 + t*77))
            a.extend(color)
            d = (before-after) / max(1, delta_max)
            b.extend((int(d*50), int(d*137), int(d*255)) if d else (15, 22, 28))
        preview.append(bytes(a))
        diff.append(bytes(b))
    return preview, diff, width


def _markdown_report(report: dict[str, Any], config: dict[str, Any]) -> str:
    s = report["statistics"]
    orient = report["orientation"]
    sea = config["ocean"]["sea_level_sample"]
    status = "PASS" if s["passed"] else "FAIL"
    failures = ", ".join(s["failures"]) if s["failures"] else "None"
    return (f"# Heightmap generation report\n\n"
            f"- Job: {config.get('name', 'Unnamed job')}\n"
            f"- Status: **{status}**\n"
            f"- Input SHA-256: `{report['input_sha256']}`\n"
            f"- Input dimensions: {s['width']} × {s['height']} (16-bit grayscale PNG)\n"
            f"- Output dimensions: {s['width']} × {s['height']} (16-bit grayscale PNG)\n"
            f"- Row-0 direction: **{config['landscape']['row_zero_world_y']} world Y**\n"
            f"- Orientation verification: **{orient['status']}** ({orient['checks']} checks)\n"
            f"- Sea level: sample {sea}; world Z {(_world_height(sea, config)):.3f} cm according to configured transform\n"
            f"- Input samples: {s['source_range']}\n"
            f"- Output samples: {s['output_range']}\n"
            f"- Changed samples: {s['changed_samples']}\n"
            f"- Editable water samples: {s['editable_water_samples']}\n"
            f"- Max deepening: {s['max_deepening_samples']} samples\n"
            f"- Protected samples: {s['protected_samples']}; changed: {s['protected_changed_samples']}\n"
            f"- Source land samples modified: {s['land_changed_samples']}\n"
            f"- Samples accidentally raised: {s['raised_samples']}\n"
            f"- Edge sample range: {s['edge_sample_range']}; strictly below sea: {s['edges_below_sea']}\n"
            f"- Failures: {failures}\n\n"
            "## Interpretation and limits\n\n"
            "- Euclidean shoreline distances are measured to nearest **land sample centre**, "
            "using the configured XY pixel scales.\n"
            "- If control points fit both directions, row orientation remains **ambiguous**.\n"
            "- Without orientation control points, row direction is **configured, not independently verified**.\n"
            "- This report verifies PNG samples, not live UEFN actors, proxies, materials, or water height.\n"
            "- Preview and difference files are for review only; import `heightmap.png`, not the RGB previews.\n"
            "- Back up the island and check dimensions, transform, protected areas, and coastline before manual re-import.\n")


def _get_context(input_path, config_path):
    config = load_config(config_path)
    source, digest = read_heightmap(input_path)
    orient = verify_orientation(source, config)
    land, distance, mask = analyze(source, config)
    return config, source, digest, orient, land, distance, mask


def _fail_on_invalid(report):
    if not report["passed"]:
        raise ValueError("Validation failed: " + "; ".join(report["failures"]))


def _run_generate(args):
    config, source, digest, orientation, land, distance, mask = _get_context(args.input, args.config)
    result = generate(source, config, land, distance, mask)
    statistics = validate(source, result, config, land, mask)
    _fail_on_invalid(statistics)
    report = {"input_sha256": digest, "orientation": orientation, "statistics": statistics,
              "operation": config["operation"], "row_zero_world_y": config["landscape"]["row_zero_world_y"]}
    if args.dry_run:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    if args.output_dir is None:
        raise ValueError("--output-dir is required unless --dry-run is used")
    output_dir = Path(args.output_dir)
    input_resolved = Path(args.input).resolve()
    paths = [output_dir / name for name in OUTPUT_NAMES]
    if any(p.resolve() == input_resolved for p in paths):
        raise ValueError("Output paths must never overwrite the input heightmap")
    existing = [p for p in paths if p.exists()]
    if existing and not args.force:
        raise ValueError("Outputs already exist; use a new --output-dir, or --force: "
                         + ", ".join(str(p) for p in existing))
    output_dir.mkdir(parents=True, exist_ok=True)
    write_heightmap(paths[0], result)
    preview, difference, width = _previews(source, result, config["ocean"]["sea_level_sample"])
    write_rgb(paths[1], preview, width)
    write_rgb(paths[2], difference, width)
    paths[3].write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    paths[4].write_text(_markdown_report(report, config), encoding="utf-8")
    print(json.dumps({"status": "PASS", "output_dir": str(output_dir),
                      "changed_samples": statistics["changed_samples"],
                      "orientation": orientation["status"]}, ensure_ascii=False))


def _run_validate(args):
    config, source, digest, orientation, land, distance, mask = _get_context(args.input, args.config)
    candidate, candidate_hash = read_heightmap(args.candidate)
    # Recompute the expected pixels from the unmodified input and job configuration.
    # Sample-invariant checks alone cannot catch an incorrectly deepened seabed.
    expected = generate(source, config, land, distance, mask)
    result = validate(source, candidate, config, land, mask, expected=expected)
    print(json.dumps({"input_sha256": digest, "candidate_sha256": candidate_hash,
                      "orientation": orientation, "statistics": result}, ensure_ascii=False, indent=2))
    _fail_on_invalid(result)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("generate", "validate"):
        cmd = commands.add_parser(name)
        cmd.add_argument("--input", required=True, help="Original UEFN-exported 16-bit grayscale PNG")
        cmd.add_argument("--config", required=True, help="JSON job config, with an explicit orientation")
        if name == "generate":
            cmd.add_argument("--output-dir", help="Directory for new outputs")
            cmd.add_argument("--dry-run", action="store_true", help="Validate and report without writing files")
            cmd.add_argument("--force", action="store_true", help="Overwrite generated outputs, never input")
        else:
            cmd.add_argument("--candidate", required=True, help="Previously generated heightmap.png")
    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            _run_generate(args)
        else:
            _run_validate(args)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
