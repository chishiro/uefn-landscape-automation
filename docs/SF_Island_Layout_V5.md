# Sidekick Frontier — Island V5 — Extended Seabed

## Input validation

- Source: `assets/input/base_heightmap_505.png`
- SHA-256: `9019eb4a2d0e0f35a74770da4cb836f20857fe4c4d3cdb01bf549dff673820ec`
- Format: 505×505, PNG 16-bit grayscale (one channel)
- Output: 505×505, PNG 16-bit grayscale (one channel)

## Verified coordinate mapping

- UEFN LUF: +X Forward, +Y Right, +Z Up. Unreal units are cm.
- Landscape transform retained on import: Location `(-32768,-32768,-384)`, Scale `(100,100,100)`.
- Pixel column `u` maps to `WorldX = -32768 + 100*u` cm.
- **row 0 = world Y minimum (south)**. Pixel row conversion is therefore `WorldY = -32768 + 100*v` cm if row 0 is south, otherwise `WorldY = 17632 - 100*v` cm.
- Row direction was selected from the lower error against the four recorded Streaming Proxy elevation ranges: south-first error=0.000 cm, north-first error=0.000 cm.
- Height conversion: `WorldZ_cm = -384 + (sample - 32768) * 100 / 128`.

## Terrain plan

- Broad SW beach; two east-facing coves; a small NE headland; northern irregular wooded hills and mixed rocky coast.
- Future sea level: sample `32124` = `-887.12` cm world Z. The outer edge is sample `27124` = `-4793.38` cm, below that level.
- Future pond depression: approximately `X=-93m, Y=86m` in landscape-centred local plan coordinates; no Water Actor is placed.
- Future stream: north highland through the east side to the coast. It is a shallow terrain channel only; retain a later 6m shallow crossing near the central/east route when placing gameplay.
- Protected zones: Sanctuary/Player Spawners (24–30m radius), Sidekick/Persona spawners (20m), Nickname Button (18m), plus the central 284×264m equivalent exploration core. These samples are copied bit-for-bit.

## Verification

- Source sample range: 29504–36371
- V5 sample range: 27124–36371
- Changed samples: 159224 / 255025; maximum change: 2380 samples.
- Protected samples: 58855; maximum protected delta: 0 samples.
- Edge samples: 27124–27124; all are below sea sample 32124.

## Re-import (do not execute in this task)

1. In Landscape Mode select the existing Landscape and use the heightmap re-import workflow; do not create/delete a Landscape or Streaming Proxy.
2. Select the generated `SF_Island_Heightmap_V5_505.png`. Preserve Location `(-32768,-32768,-384)` and Scale `(100,100,100)`; do not change Island Settings.
3. Confirm the existing 4 Streaming Proxies remain, then inspect Sanctuary/Spawner height and the four coastline edges before saving.

## V4 deep-seabed verification

- V3-to-V4 depth-difference image: `SF_Island_Seabed_Depth_V4.png` (blue intensity is increased seabed depth).
- V3 sea sample preserved: `32124` = `-887.12` cm world Z.
- V4 exterior edge sample: `27124` = `-4793.38` cm world Z.
- Edge water depth below planned sea: `3906.25` cm.
- V4 only lowers samples at/below the V3 water cutoff; land, coastline silhouette, protected zones, Sanctuary and central exploration core remain source-identical.

## V5 offshore-depth verification

- V4-to-V5 difference image: `SF_Island_Seabed_Depth_V5.png`; blue is additional depth.
- Row orientation is inherited unchanged from V4: row 0 is World Y minimum (south).
- Sea sample is unchanged: `32124` = `-887.12` cm World Z.
- Nearshore (18–40m from retained shore) depth: min/mean/max = `141.41` / `1542.31` / `3604.69` cm.
- Offshore (80–120m from retained shore) depth: min/mean/max = `2896.09` / `3828.24` / `3906.25` cm.
- Outer edge and corners: sample `27124`, World Z `-4793.38` cm, depth `3906.25` cm below sea.
- The new shore-to-offshore blend spans 18–150m from the existing shoreline, versus V4's 7–82m, retaining shallow beach water while extending the continuous middle-depth transition.
- Land/shoreline samples above the V4 water cutoff and all protected samples are copied unchanged.

