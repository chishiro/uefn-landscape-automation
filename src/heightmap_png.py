"""Small dependency-free PNG reader/writer for 16-bit grayscale heightmaps.

Supports non-interlaced PNGs (color type 0, bit depth 16) with PNG filters 0-4.
Fails closed on unsupported modes or corrupt input. Also writes 8-bit RGB previews.
"""
from __future__ import annotations

import binascii
import hashlib
from pathlib import Path
import struct
import zlib

SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _chunk(kind: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + kind + data
            + struct.pack(">I", binascii.crc32(kind + data) & 0xFFFFFFFF))


def _chunks(blob: bytes):
    if not blob.startswith(SIGNATURE):
        raise ValueError("Input is not a PNG file")
    index = len(SIGNATURE)
    found_end = False
    while index < len(blob):
        if index + 12 > len(blob):
            raise ValueError("Truncated PNG chunk header")
        size = struct.unpack_from(">I", blob, index)[0]
        end = index + 12 + size
        if end > len(blob):
            raise ValueError("Truncated PNG chunk data")
        kind = blob[index + 4:index + 8]
        payload = blob[index + 8:index + 8 + size]
        crc = struct.unpack_from(">I", blob, index + 8 + size)[0]
        if binascii.crc32(kind + payload) & 0xFFFFFFFF != crc:
            raise ValueError("PNG CRC mismatch in " + kind.decode("ascii", "replace"))
        yield kind, payload
        index = end
        if kind == b"IEND":
            found_end = True
            if index != len(blob):
                raise ValueError("Unexpected data after PNG IEND")
            break
    if not found_end:
        raise ValueError("Missing PNG IEND")


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def read_heightmap(path: str | Path) -> tuple[list[list[int]], str]:
    """Return 2D uint16 samples and SHA-256 of the original file."""
    blob = Path(path).read_bytes()
    chunks = list(_chunks(blob))
    if not chunks or chunks[0][0] != b"IHDR" or len(chunks[0][1]) != 13:
        raise ValueError("PNG must begin with a valid IHDR")
    width, height, depth, colour, compression, filtering, interlace = struct.unpack(
        ">IIBBBBB", chunks[0][1]
    )
    if (depth, colour, compression, filtering, interlace) != (16, 0, 0, 0, 0):
        raise ValueError("Expected non-interlaced, 16-bit, single-channel grayscale PNG")
    if width < 2 or height < 2 or width * height > 50_000_000:
        raise ValueError("Heightmap dimensions must be at least 2x2 and <= 50M pixels")
    idat = b"".join(payload for kind, payload in chunks if kind == b"IDAT")
    if not idat:
        raise ValueError("PNG has no IDAT data")
    try:
        raw = zlib.decompress(idat)
    except zlib.error as exc:
        raise ValueError("Could not decompress PNG image") from exc
    stride = width * 2
    if len(raw) != height * (stride + 1):
        raise ValueError("Unexpected decompressed PNG scanline length")
    result = []
    prior = bytearray(stride)
    offset = 0
    for _ in range(height):
        mode = raw[offset]
        offset += 1
        row = bytearray(raw[offset:offset + stride])
        offset += stride
        if mode > 4:
            raise ValueError(f"Unsupported PNG filter: {mode}")
        for i in range(stride):
            a = row[i-2] if i >= 2 else 0
            b = prior[i]
            c = prior[i-2] if i >= 2 else 0
            if mode == 1:
                row[i] = (row[i] + a) & 255
            elif mode == 2:
                row[i] = (row[i] + b) & 255
            elif mode == 3:
                row[i] = (row[i] + (a+b)//2) & 255
            elif mode == 4:
                row[i] = (row[i] + _paeth(a, b, c)) & 255
        result.append(list(struct.unpack(f">{width}H", row)))
        prior = row
    return result, hashlib.sha256(blob).hexdigest()


def _write_png(path: str | Path, width: int, height: int, bit_depth: int,
               colour_type: int, rows: list[bytes]) -> None:
    if len(rows) != height:
        raise ValueError("Row count does not match image height")
    channels = 3 if colour_type == 2 else 1
    stride = width * channels * (bit_depth // 8)
    if any(len(row) != stride for row in rows):
        raise ValueError("Invalid PNG row length")
    ihdr = struct.pack(">IIBBBBB", width, height, bit_depth, colour_type, 0, 0, 0)
    payload = b"".join(b"\x00" + row for row in rows)
    png = (SIGNATURE + _chunk(b"IHDR", ihdr)
           + _chunk(b"IDAT", zlib.compress(payload, 6))
           + _chunk(b"IEND", b""))
    Path(path).write_bytes(png)


def write_heightmap(path: str | Path, data: list[list[int]]) -> None:
    height = len(data)
    width = len(data[0]) if height else 0
    if width < 2 or height < 2 or any(len(row) != width for row in data):
        raise ValueError("Heightmap rows must have identical size (>= 2x2)")
    if any(not 0 <= value <= 65535 for row in data for value in row):
        raise ValueError("Height samples must be unsigned 16-bit integers")
    rows = [struct.pack(f">{width}H", *row) for row in data]
    _write_png(path, width, height, 16, 0, rows)


def write_rgb(path: str | Path, rows: list[bytes], width: int) -> None:
    _write_png(path, width, len(rows), 8, 2, rows)
