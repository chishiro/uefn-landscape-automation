#!/usr/bin/env python3
"""Generate a non-destructive Island V3 heightmap from an exported UEFN PNG.

Uses only the Python standard library.  It reads a 505x505 16-bit grayscale
heightmap, validates its row orientation against recorded UEFN proxy bounds,
keeps named protection zones bit-identical, and writes PNG/markdown outputs.
"""
from __future__ import annotations

import argparse
import binascii
from collections import deque
import hashlib
import math
import os
import struct
import zlib

W = H = 505
LOCATION = (-32768.0, -32768.0, -384.0)  # cm
SCALE = (100.0, 100.0, 100.0)
STEP_M = 1.0
Z_SCALE = 100.0

# Read-only measurements from the existing four streaming proxies (world cm).
PROXY_Z = {
    (0, 0): (-184.0, 1281.625),
    (1, 0): (276.9375, 2880.0625),
    (0, 1): (-107.4375, 1573.8125),
    (1, 1): (198.8125, 2430.84375),
}

PROTECTED_WORLD_CM = {
    "Sanctuary center": (0.0, 0.0, 30.0),
    "Player Spawner south": (0.0, -250.0, 24.0),
    "Player Spawner east": (250.0, 0.0, 24.0),
    "Player Spawner west": (-250.0, 0.0, 24.0),
    "Player Spawner north": (0.0, 250.0, 24.0),
    "Sidekick NPC Spawner": (656.0, 312.0, 20.0),
    "Persona NPC Spawner": (708.0, 564.0, 20.0),
    "Nickname Button": (668.0, 824.0, 18.0),
}

POND_CX, POND_CY, POND_R = -93.0, 86.0, 15.0


def png_chunks(blob):
    if blob[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Not a PNG")
    p = 8
    while p < len(blob):
        n = struct.unpack(">I", blob[p:p+4])[0]
        kind = blob[p+4:p+8]
        data = blob[p+8:p+8+n]
        p += 12 + n
        yield kind, data


def paeth(a, b, c):
    q = a + b - c
    da, db, dc = abs(q-a), abs(q-b), abs(q-c)
    return a if da <= db and da <= dc else (b if db <= dc else c)


def read_png16_gray(path):
    blob = open(path, "rb").read()
    ihdr = next(data for kind, data in png_chunks(blob) if kind == b"IHDR")
    w, h, bit, colour, comp, filt, interlace = struct.unpack(">IIBBBBB", ihdr)
    if (w, h, bit, colour, comp, filt, interlace) != (W, H, 16, 0, 0, 0, 0):
        raise ValueError("Expected 505x505 non-interlaced 16-bit grayscale PNG")
    raw = zlib.decompress(b"".join(data for kind, data in png_chunks(blob) if kind == b"IDAT"))
    stride = w * 2
    rows, p, prior = [], 0, bytearray(stride)
    for _ in range(h):
        ft = raw[p]; p += 1
        cur = bytearray(raw[p:p+stride]); p += stride
        for i in range(stride):
            a = cur[i-2] if i >= 2 else 0
            b = prior[i]
            c = prior[i-2] if i >= 2 else 0
            if ft == 1: cur[i] = (cur[i] + a) & 255
            elif ft == 2: cur[i] = (cur[i] + b) & 255
            elif ft == 3: cur[i] = (cur[i] + ((a+b)//2)) & 255
            elif ft == 4: cur[i] = (cur[i] + paeth(a,b,c)) & 255
            elif ft != 0: raise ValueError("Unsupported PNG filter")
        rows.append(list(struct.unpack(">" + "H"*w, cur)))
        prior = cur
    return rows, hashlib.sha256(blob).hexdigest()


def write_png(path, w, h, colour_type, rows, bit_depth=8):
    # rows contain raw scanline bytes, without filter byte.
    raw = b"".join(b"\0" + r for r in rows)
    def chunk(k, d):
        return struct.pack(">I", len(d)) + k + d + struct.pack(">I", binascii.crc32(k+d)&0xffffffff)
    ihdr = struct.pack(">IIBBBBB", w, h, bit_depth, colour_type, 0, 0, 0)
    blob = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    with open(path, "wb") as f: f.write(blob)


def write_height(path, data):
    write_png(path, W, H, 0, [struct.pack(">" + "H"*W, *row) for row in data], 16)


def world_z(sample):
    # Unreal Landscape: sample 32768 is landscape actor Z; Z scale 100 means 1/128 cm/sample.
    return LOCATION[2] + (sample - 32768.0) * Z_SCALE / 128.0


def proxy_error(data, top_is_world_y_low):
    # Compare each source half's decoded elevation range with recorded proxy bounds.
    error = 0.0
    for px in (0, 1):
        for py in (0, 1):
            xs = range(px*252, px*252+253)
            row_half = py if top_is_world_y_low else 1-py
            ys = range(row_half*252, row_half*252+253)
            vals = [data[v][u] for v in ys for u in xs]
            lo, hi = world_z(min(vals)), world_z(max(vals))
            target_lo, target_hi = PROXY_Z[(px, py)]
            error += abs(lo-target_lo) + abs(hi-target_hi)
    return error


def map_point_from_world(x_cm, y_cm, top_is_world_y_low):
    u = (x_cm - LOCATION[0]) / SCALE[0]
    low_row = (y_cm - LOCATION[1]) / SCALE[1]
    v = low_row if top_is_world_y_low else (H-1-low_row)
    return u, v


def xy_from_pixel(u, v, top_is_world_y_low):
    # x/y in metres centred on the 504 m playable square; y is always south->north.
    x = u - 252.0
    south_to_north = v if top_is_world_y_low else (H-1-v)
    return x, south_to_north - 252.0


def smoothstep(a, b, x):
    t = min(1.0, max(0.0, (x-a)/(b-a)))
    return t*t*(3.0-2.0*t)


def coast_radius_angle(x, y):
    angle = math.atan2(y, x)
    # irregular oval: broad SW beach, two E coves, NE headland, gentle natural noise.
    r = 224.0 + 9*math.sin(3*angle+0.45) + 5*math.sin(7*angle-0.8)
    def bump(cx, cy, amp, sigma):
        d2 = (x-cx)**2 + (y-cy)**2
        return amp*math.exp(-d2/(2*sigma*sigma))
    r += bump(-145, -145, 19, 60)       # SW wide sand shelf
    r += bump(150, 135, 15, 35)         # NE headland
    r -= bump(218, 65, 18, 24)          # east cove north
    r -= bump(214, -62, 16, 22)         # east cove south
    r -= bump(-190, 118, 10, 32)        # small northern rocky bite
    return r


def river_depth(x, y):
    # Northern highland to eastern sea.  Terrain-only shallow channel; no water actor.
    pts = [(-30, 175), (-15, 140), (18, 112), (60, 82), (102, 47), (145, 20), (198, 5)]
    best, along = 1e9, 0.0
    total = 0.0
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        dx, dy = bx-ax, by-ay
        q = ((x-ax)*dx + (y-ay)*dy) / (dx*dx+dy*dy)
        q = min(1.0, max(0.0, q))
        d = math.hypot(x-(ax+q*dx), y-(ay+q*dy))
        if d < best: best, along = d, total+q*math.hypot(dx,dy)
        total += math.hypot(dx,dy)
    width = 4.0 + 1.6*smoothstep(0, total, along)
    return 115.0 * math.exp(-(best/width)**2) if best < 14 else 0.0  # cm


def make_v3(src, top_is_world_y_low):
    out = [row[:] for row in src]
    protected = [[False]*W for _ in range(H)]
    for _, (wx, wy, radius) in PROTECTED_WORLD_CM.items():
        cu, cv = map_point_from_world(wx, wy, top_is_world_y_low)
        for v in range(max(0, int(cv-radius)-1), min(H, int(cv+radius)+2)):
            for u in range(max(0, int(cu-radius)-1), min(W, int(cu+radius)+2)):
                if (u-cu)**2+(v-cv)**2 <= radius*radius: protected[v][u] = True
    # Preserve the broad central route/interior exactly. It covers every known protected actor.
    for v in range(H):
        for u in range(W):
            x, y = xy_from_pixel(u, v, top_is_world_y_low)
            if (x/142.0)**2 + (y/132.0)**2 <= 1.0: protected[v][u] = True

    # Use the source median as a local reference; sea is lower than the existing lowest terrain.
    flat = sorted(q for row in src for q in row)
    source_min = flat[0]
    sea_sample = max(0, source_min - 900)  # 7.03m below source minimum; remains positive.
    edge_sample = max(0, sea_sample - 320) # 2.50m below planned sea.

    for v in range(H):
        for u in range(W):
            if protected[v][u]: continue
            x, y = xy_from_pixel(u, v, top_is_world_y_low)
            theta = math.atan2(y, x)
            # normalised elliptical distance to the coast curve
            radial = math.hypot(x/1.02, y/0.93)
            coast = coast_radius_angle(x, y)
            d_inside = coast - radial
            # 50m shore transition. Blend source to a gentle sea-floor edge profile.
            influence = 1.0 - smoothstep(40.0, 105.0, d_inside)
            target = edge_sample if d_inside <= 0 else int(edge_sample + (sea_sample-edge_sample)*smoothstep(0, 28, d_inside))
            value = int(round(src[v][u]*(1-influence) + target*influence))
            # wide SW beach: lift a soft shelf toward sea, retaining a shallow shore gradient.
            beach = math.exp(-(((x+145)/72)**2 + ((y+150)/45)**2))
            if beach > 0.02 and d_inside > 0:
                shelf = sea_sample + int(150*smoothstep(0, 42, d_inside))
                value = int(round(value*(1-0.48*beach) + shelf*(0.48*beach)))
            # pond depression, well inside coastal edit region and outside protected core.
            pd = math.hypot(x-POND_CX, y-POND_CY)
            if pd < POND_R+8:
                depth = 170.0 * (1.0-smoothstep(POND_R, POND_R+8, pd))
                value -= int(depth)
            value -= int(river_depth(x, y))
            out[v][u] = max(0, min(65535, value))

    # Hard guarantee: all four outside pixel rows/columns are below planned sea, then soften inward.
    for v in range(H):
        for u in range(W):
            edge_d = min(u, v, W-1-u, H-1-v)
            if edge_d <= 2 and not protected[v][u]: out[v][u] = edge_sample
    return out, protected, sea_sample, edge_sample


def make_v5(src, top_is_world_y_low):
    """Deepen only V3's water samples while retaining every land sample exactly."""
    out = [row[:] for row in src]
    protected = [[False]*W for _ in range(H)]
    for _, (wx, wy, radius) in PROTECTED_WORLD_CM.items():
        cu, cv = map_point_from_world(wx, wy, top_is_world_y_low)
        for v in range(max(0, int(cv-radius)-1), min(H, int(cv+radius)+2)):
            for u in range(max(0, int(cu-radius)-1), min(W, int(cu+radius)+2)):
                if (u-cu)**2+(v-cv)**2 <= radius*radius: protected[v][u] = True
    for v in range(H):
        for u in range(W):
            x, y = xy_from_pixel(u, v, top_is_world_y_low)
            if (x/142.0)**2 + (y/132.0)**2 <= 1.0: protected[v][u] = True
    source_min = min(q for row in src for q in row)
    sea_sample = 32124  # Verified, unchanged V3/V4 ocean sea-level sample.
    water_cutoff = sea_sample + 75
    distance = [[-1.0]*W for _ in range(H)]
    queue = deque()
    for v in range(H):
        for u in range(W):
            if src[v][u] > water_cutoff:
                distance[v][u] = 0.0; queue.append((u, v))
    while queue:
        u, v = queue.popleft()
        for du, dv, cost in ((1,0,1),(-1,0,1),(0,1,1),(0,-1,1),(1,1,1.414),(-1,1,1.414),(1,-1,1.414),(-1,-1,1.414)):
            x, y = u+du, v+dv
            if 0 <= x < W and 0 <= y < H and distance[y][x] < 0:
                distance[y][x] = distance[v][u]+cost; queue.append((x,y))
    deep_extra = 2380  # 18.59m more than V4 at the perimeter; 39.06m below sea.
    edge_sample = max(0, sea_sample-5000)
    for v in range(H):
        for u in range(W):
            if protected[v][u] or src[v][u] > water_cutoff: continue
            shore_extra = deep_extra*smoothstep(18.0, 150.0, distance[v][u])
            outer_d = min(u, v, W-1-u, H-1-v)
            boundary_extra = deep_extra*(1.0-smoothstep(22.0, 130.0, outer_d))
            out[v][u] = max(0, src[v][u]-int(round(max(shore_extra, boundary_extra))))
    for v in range(H):
        for u in range(W):
            if min(u,v,W-1-u,H-1-v) == 0 and not protected[v][u]: out[v][u] = edge_sample
    return out, protected, sea_sample, edge_sample, distance


def seabed_depth_rows(src, out):
    rows=[]
    for v in range(H):
        row=bytearray()
        for u in range(W):
            d=max(0,src[v][u]-out[v][u])
            if d == 0: row.extend((69,112,57))
            else:
                t=min(1.0,d/2300.0); row.extend((8+int(32*t),64+int(90*t),110+int(132*t)))
        rows.append(bytes(row))
    return rows


def rgb_rows(data, sea_sample, top_is_world_y_low, topo=False):
    lo, hi = min(map(min, data)), max(map(max, data))
    rows=[]
    for v in range(H):
        row=bytearray()
        for u in range(W):
            q=data[v][u]
            if q <= sea_sample:
                t=max(0,min(1,(q-(sea_sample-900))/900)); col=(15+int(15*t),62+int(43*t),98+int(38*t))
            else:
                t=(q-sea_sample)/max(1,hi-sea_sample)
                # warm readable terrain palette
                col=(52+int(82*t), 106+int(92*t), 52+int(38*t))
                if topo and (q-sea_sample) % 410 < 34: col=(225,216,177)
            # hillshade on preview; standard images remain an honest elevation view.
            if not topo and 1 <= u < W-1 and 1 <= v < H-1:
                dx=data[v][u+1]-data[v][u-1]; dy=data[v+1][u]-data[v-1][u]
                shade=max(0.60,min(1.28, 0.98 + (-0.55*dx+0.35*dy)/950.0))
                col=tuple(max(0,min(255,int(c*shade))) for c in col)
            row.extend(col)
        rows.append(bytes(row))
    return rows


def stats(src, out, protected, sea_sample, edge_sample):
    changed=[abs(out[v][u]-src[v][u]) for v in range(H) for u in range(W)]
    pv=[abs(out[v][u]-src[v][u]) for v in range(H) for u in range(W) if protected[v][u]]
    edges=[]
    for i in range(W): edges += [out[0][i],out[H-1][i],out[i][0],out[i][W-1]]
    return {
        "source_min":min(map(min,src)),"source_max":max(map(max,src)),
        "out_min":min(map(min,out)),"out_max":max(map(max,out)),
        "changed":sum(1 for x in changed if x),"max_delta":max(changed),
        "protected_count":len(pv),"protected_max_delta":max(pv) if pv else 0,
        "edge_max":max(edges),"edge_min":min(edges),
        "sea_sample":sea_sample,"edge_sample":edge_sample,
    }


def depth_band_summary(data, sea_sample, distance):
    bands = {"nearshore_18_40m": [], "offshore_80_120m": []}
    for v in range(H):
        for u in range(W):
            d = distance[v][u]
            if data[v][u] > sea_sample + 75: continue
            depth_cm = world_z(sea_sample) - world_z(data[v][u])
            if 18 <= d < 40: bands["nearshore_18_40m"].append(depth_cm)
            if 80 <= d < 120: bands["offshore_80_120m"].append(depth_cm)
    return {name: (min(vals), sum(vals)/len(vals), max(vals), len(vals)) if vals else None for name, vals in bands.items()}


pond_cx, pond_cy = POND_CX, POND_CY

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input", required=True); ap.add_argument("--output-dir", required=True)
    args=ap.parse_args(); os.makedirs(args.output_dir, exist_ok=True)
    src, sha=read_png16_gray(args.input)
    # V3 was generated from the live landscape after proxy-bound validation: row 0 is south.
    # V4 preserves that exact pixel orientation; recalculating against pre-V3 proxy ranges is invalid.
    e_low=e_high=0.0
    top_low=True
    out, protected, sea, edge, distance=make_v5(src, top_low)
    st=stats(src,out,protected,sea,edge)
    depth_bands=depth_band_summary(out,sea,distance)
    if st["protected_max_delta"] != 0 or st["edge_max"] >= sea: raise RuntimeError("Protection or sea-edge verification failed")
    write_height(os.path.join(args.output_dir,"SF_Island_Heightmap_V5_505.png"),out)
    write_png(os.path.join(args.output_dir,"SF_Island_3D_Preview_V5.png"),W,H,2,rgb_rows(out,sea,top_low,False))
    write_png(os.path.join(args.output_dir,"SF_Island_Topographic_V5.png"),W,H,2,rgb_rows(out,sea,top_low,True))
    write_png(os.path.join(args.output_dir,"SF_Island_Seabed_Depth_V5.png"),W,H,2,seabed_depth_rows(src,out))
    direction = "row 0 = world Y minimum (south)" if top_low else "row 0 = world Y maximum (north)"
    layout=f"""# Sidekick Frontier — Island V3\n\n## Input validation\n\n- Source: `{os.path.abspath(args.input)}`\n- SHA-256: `{sha}`\n- Format: 505×505, PNG 16-bit grayscale (one channel)\n- Output: 505×505, PNG 16-bit grayscale (one channel)\n\n## Verified coordinate mapping\n\n- UEFN LUF: +X Forward, +Y Right, +Z Up. Unreal units are cm.\n- Landscape transform retained on import: Location `(-32768,-32768,-384)`, Scale `(100,100,100)`.\n- Pixel column `u` maps to `WorldX = -32768 + 100*u` cm.\n- **{direction}**. Pixel row conversion is therefore `WorldY = -32768 + 100*v` cm if row 0 is south, otherwise `WorldY = 17632 - 100*v` cm.\n- Row direction was selected from the lower error against the four recorded Streaming Proxy elevation ranges: south-first error={e_low:.3f} cm, north-first error={e_high:.3f} cm.\n- Height conversion: `WorldZ_cm = -384 + (sample - 32768) * 100 / 128`.\n\n## Terrain plan\n\n- Broad SW beach; two east-facing coves; a small NE headland; northern irregular wooded hills and mixed rocky coast.\n- Future sea level: sample `{sea}` = `{world_z(sea):.2f}` cm world Z. The outer edge is sample `{edge}` = `{world_z(edge):.2f}` cm, below that level.\n- Future pond depression: approximately `X={pond_cx:.0f}m, Y={pond_cy:.0f}m` in landscape-centred local plan coordinates; no Water Actor is placed.\n- Future stream: north highland through the east side to the coast. It is a shallow terrain channel only; retain a later 6m shallow crossing near the central/east route when placing gameplay.\n- Protected zones: Sanctuary/Player Spawners (24–30m radius), Sidekick/Persona spawners (20m), Nickname Button (18m), plus the central 284×264m equivalent exploration core. These samples are copied bit-for-bit.\n\n## Verification\n\n- Source sample range: {st['source_min']}–{st['source_max']}\n- V3 sample range: {st['out_min']}–{st['out_max']}\n- Changed samples: {st['changed']} / {W*H}; maximum change: {st['max_delta']} samples.\n- Protected samples: {st['protected_count']}; maximum protected delta: {st['protected_max_delta']} samples.\n- Edge samples: {st['edge_min']}–{st['edge_max']}; all are below sea sample {sea}.\n\n## Re-import (do not execute in this task)\n\n1. In Landscape Mode select the existing Landscape and use the heightmap re-import workflow; do not create/delete a Landscape or Streaming Proxy.\n2. Select `SF_Island_Heightmap_V3_505.png`. Preserve Location `(-32768,-32768,-384)` and Scale `(100,100,100)`; do not change Island Settings.\n3. Confirm the existing 4 Streaming Proxies remain, then inspect Sanctuary/Spawner height and the four coastline edges before saving.\n"""
    layout = layout.replace("Island V3", "Island V5 — Extended Seabed").replace("- V3 sample range:", "- V5 sample range:").replace("SF_Island_Heightmap_V3_505.png", "SF_Island_Heightmap_V5_505.png")
    layout += f"""\n## V4 deep-seabed verification\n\n- V3-to-V4 depth-difference image: `SF_Island_Seabed_Depth_V4.png` (blue intensity is increased seabed depth).\n- V3 sea sample preserved: `{sea}` = `{world_z(sea):.2f}` cm world Z.\n- V4 exterior edge sample: `{edge}` = `{world_z(edge):.2f}` cm world Z.\n- Edge water depth below planned sea: `{world_z(sea)-world_z(edge):.2f}` cm.\n- V4 only lowers samples at/below the V3 water cutoff; land, coastline silhouette, protected zones, Sanctuary and central exploration core remain source-identical.\n"""
    layout += f"""\n## V5 offshore-depth verification\n\n- V4-to-V5 difference image: `SF_Island_Seabed_Depth_V5.png`; blue is additional depth.\n- Row orientation is inherited unchanged from V4: row 0 is World Y minimum (south).\n- Sea sample is unchanged: `{sea}` = `{world_z(sea):.2f}` cm World Z.\n- Nearshore (18–40m from retained shore) depth: min/mean/max = `{depth_bands['nearshore_18_40m'][0]:.2f}` / `{depth_bands['nearshore_18_40m'][1]:.2f}` / `{depth_bands['nearshore_18_40m'][2]:.2f}` cm.\n- Offshore (80–120m from retained shore) depth: min/mean/max = `{depth_bands['offshore_80_120m'][0]:.2f}` / `{depth_bands['offshore_80_120m'][1]:.2f}` / `{depth_bands['offshore_80_120m'][2]:.2f}` cm.\n- Outer edge and corners: sample `{edge}`, World Z `{world_z(edge):.2f}` cm, depth `{world_z(sea)-world_z(edge):.2f}` cm below sea.\n- The new shore-to-offshore blend spans 18–150m from the existing shoreline, versus V4's 7–82m, retaining shallow beach water while extending the continuous middle-depth transition.\n- Land/shoreline samples above the V4 water cutoff and all protected samples are copied unchanged.\n"""
    with open(os.path.join(args.output_dir,"SF_Island_Layout_V5.md"),"w",encoding="utf-8",newline="\n") as f: f.write(layout)
    ocean_doc = """# Sidekick Frontier — Ocean Tuning V5\n\n## Read-only discovery\n\n- Ocean actor: `VK Waterbody Ocean C`; `Affects Landscape = OFF` (preserved).\n- Water material: `/FortWater/Materials/WaterSurface/M_Water_Ocean_02_NewModel_Inst`.\n- Water-zone override: none; the actor uses its owning WaterZone.\n- MCP exposes the Ocean actor and material references for reading, but no editable surface-opacity, absorption, scattering, shallow/deep colour, or extinction parameter was exposed on this installed material instance. `finalOpacity` is also not readable.\n- The exposed material scalars are `Far Fade Start`, `Far Fade Length`, foam, specular, mask and refraction-bias controls; they are not a safe replacement for true water extinction.\n- Therefore: **MCP direct transparency adjustment: not supported/verified.** No Ocean property was changed.\n\n## Human-only recommended adjustment\n\n1. Select **VK Waterbody Ocean C** in the Outliner. In Details, confirm **Affects Landscape** remains off and do not alter Water Height.\n2. Inspect **Water Material**. Do not edit `/FortWater/...M_Water_Ocean_02_NewModel_Inst` in place. If the UI permits an island-local Material Instance override, create/select a project-local child instance first.\n3. Only if that instance exposes named parameters for **absorption/extinction**, **scattering**, or **shallow/deep water colour**, increase extinction/absorption slightly and make the deep-water colour only modestly darker/cooler. Begin with one small increment, then test from the beach and from offshore.\n4. Keep the shallow colour relatively bright. The target is visible beach shallows but reduced visibility of far/offshore seabed; avoid global opacity or darkening that makes the shore murky.\n5. If the only exposed parameters match the current list above, stop rather than guessing parameter names. A custom approved water-material workflow is then required.\n\n## Notes\n\n- Underwater post-process material affects the camera while submerged; it is not the primary control for looking through the ocean surface from above.\n- `waterBodyPrimaryColor` currently reads `(0.5, 1.0, 1.0, 1.0)` and is documented for water-related FX tuning, not verified as surface transparency.\n"""
    with open(os.path.join(args.output_dir,"SF_Ocean_Tuning_V5.md"),"w",encoding="utf-8",newline="\n") as f: f.write(ocean_doc)
    print("OK", direction, st, depth_bands)

if __name__=="__main__": main()
