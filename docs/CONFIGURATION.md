# JSON configuration reference (schema_version 1)

Pass the path to `--config`. See `examples/demo_config.json` for a complete executable example. **All distances are metres unless the key contains `_cm`; all samples are integer 16-bit height values (0–65535).**

## Required settings

| Key | Meaning |
| --- | --- |
| `schema_version` | Must be `1`. |
| `name` | Optional human-readable job name. |
| `landscape.row_zero_world_y` | **Required**: `"min"` if image row 0 corresponds to the minimum world Y, `"max"` for maximum. Not auto-inferred. |
| `landscape.transform.origin_xy_cm` | `[world_x, world_y]` for the **minimum-X/minimum-Y pixel** (in cm), even if image row 0 is at maximum Y. Does not implicitly equal UEFN Landscape actor Location. |
| `landscape.transform.location_z_cm` | World Z offset of landscape (cm) for report conversion. |
| `landscape.transform.scale_xyz_cm` | `[step_x, step_y, scale_z]`: horizontal world centimetres between pixel centres; positive nonzero Z scale used in Unreal Landscape sample-to-Z formula. |
| `ocean.sea_level_sample` | Heightmap elevation sample representing desired sea surface. Set **explicitly** using your Landscape transform and intended ocean world Z, not a constant copied from another island. |
| `ocean.land_threshold_offset_samples` | A sample above `sea_level_sample + offset` is classified as land and copied unchanged. Default is *not* inferred: specify it. |
| `operation.type` | Must be `"deepen_seabed"` in this release. |
| `operation.shore_start_m` | At/inside this distance to land, extra shoreline deepening is zero. |
| `operation.shore_full_depth_m` | At or beyond this distance to land, shoreline deepening reaches full extra depth. Must exceed `shore_start_m`. |
| `operation.shore_extra_samples` | Maximum additional **samples** subtracted because of shoreline distance. |
| `operation.boundary_start_m` | Within this distance of an image edge, boundary deepening has its full amplitude. |
| `operation.boundary_end_m` | At/beyond this distance of an edge, boundary deepening is zero. Must exceed `boundary_start_m`. |
| `operation.boundary_extra_samples` | Maximum additional **samples** subtracted because of map-edge distance. |
| `operation.edge_target_sample` | A target ceiling for editable water pixels on the outermost image border. Only lowers; will never raise an already lower source sample. Must be below the sea level. |
| `protected_regions` | Optional array of shapes to preserve bit-exactly (see below). |
| `orientation_checks` | Optional control points to independently verify row orientation against measured world Z values (see below). |
| `validation.require_all_edges_below_sea` | `true` by default; if enabled, fail when even one border pixel is at/above the sea sample. No automatic rewriting of land/protected borders to force a pass. |

### Mapping sample values to world height

For Unreal Landscape using the configured Z scale:

```
world_z_cm = location_z_cm + (height_sample - 32768) * scale_z / 128
height_sample = 32768 + (world_z_cm - location_z_cm) * 128 / scale_z
```

Round a calculated input sea-level sample to a valid integer after checking the source landscape's transform. **A `sea_level_sample` is not a Water Body actor reading.** The ocean/water actor itself is not inspected or changed by the tool.

### Pixel coordinate mapping

Let width/height be the PNG dimensions and `u, v` the pixel column/row (0-indexed). Let `(ox, oy) = origin_xy_cm` and `(sx, sy) = scale_xyz_cm[:2]`.

```
world_x_cm = ox + u * sx
world_y_cm = oy + v * sy            # row_zero_world_y = "min"
world_y_cm = oy + (height-1-v) * sy # row_zero_world_y = "max"
```

A protected region's centre may be in **world centimetres** or **pixel coordinates**. The **radii are always metres** and calculated using the configured pixel dimensions. Correct XY scale is therefore essential.

### Protected regions

```json
"protected_regions": [
  {
    "name": "Central play zone",
    "shape": "ellipse",
    "coordinate_space": "pixel",
    "center": [252, 252],
    "radius_m": [45, 35]
  },
  {
    "name": "Important structure",
    "shape": "circle",
    "coordinate_space": "world_cm",
    "center": [0, 0],
    "radius_m": 20
  }
]
```

`circle` requires a positive numeric `radius_m`; `ellipse` requires a pair of positive `[radius_x_m, radius_y_m]`. Overlapping regions are merged. Pixels whose *centres* are inside a region are copied bit-for-bit, regardless of whether they are land or water.

### Optional orientation control points

```json
"orientation_checks": [
  {
    "world_xy_cm": [1000, 2000],
    "expected_z_cm": 125.0,
    "tolerance_cm": 5.0
  }
]
```

Each is a **known, independently measured source elevation** at a world XY coordinate, not a guessed coordinate. The tool samples the nearest pixel, converts it to world Z, and fails if its absolute difference from `expected_z_cm` is above `tolerance_cm`. It additionally reports the error for the opposite row direction as an aid; it never auto-flips an image. With no control points, report status is `configured_not_independently_verified`. If all supplied points also satisfy their tolerances under the opposite row direction, the result is `control_points_consistent_but_orientation_ambiguous`: both orientations remain plausible. Only when the supplied points distinguish the alternative is status `verified_against_supplied_control_points`. Even correctly distinguishing control points do not independently verify every UEFN actor, transform, or proxy.

## Detailed deepening algorithm

1. Classify original samples as `land = sample > sea_level_sample + land_threshold_offset_samples`. Land is permanently immutable.
2. Compute exact Euclidean distance of every pixel centre to the nearest source **land sample centre** using the configured physical X/Y step. Complexity is linear in total pixels using separable squared distance transforms.
3. For each editable (water and unprotected) pixel, compute `shore_extra_samples * smoothstep(shore_start_m, shore_full_depth_m, shore_distance_m)` and `boundary_extra_samples * (1 - smoothstep(boundary_start_m, boundary_end_m, boundary_distance_m))`.
4. Subtract the **maximum** of those two terms, rounded to the nearest sample; clamp to 0. At the outer border only, cap editable values to `edge_target_sample` without raising any pixel.
5. Verify land and protected samples are unchanged, no output value is raised, and (by default) every outermost sample lies below the configured sea sample. The separate `validate` CLI also re-runs the algorithm on the original PNG and requires exact pixel-for-pixel agreement with the candidate (`expected_mismatched_samples == 0`). On failure, exit nonzero without claiming success.

This operation **lowers** pre-existing water terrain; it does *not* expand the island, create beaches, replace collision meshes, paint layers, alter materials, or place/edit Water actors.

## Edge cases and troubleshooting

- **No land pixels above cutoff:** generation fails because shore distance cannot be defined. Inspect `sea_level_sample` and `land_threshold_offset_samples` rather than guessing.
- **Protected/land pixels on the border:** strict edge validation may fail. Review the geometry, whether an underwater border is intended, and whether you should preserve those border pixels. Disabling validation is an explicit last resort, not a recommended agent workaround.
- **Wrong row direction:** control points fail or preview appears flipped relative to the game. Correct the config and rerun from the original input; do not silently flip pixels.
- **Unexpected dark/flat output:** check whether you set the intended sea sample and pixel scales; look at `report.json` and difference preview.
- **Wrong pixel format:** export again as **non-interlaced, 16-bit, grayscale** PNG. A visually grayscale RGB PNG is not equivalent.
- **Output exists:** choose a new `--output-dir`, or explicitly use `--force` after review. The original `--input` cannot be overwritten.
