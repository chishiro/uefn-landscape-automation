import struct

import pytest

from heightmap_png import read_heightmap, write_heightmap


def test_png16_round_trip_and_sha(tmp_path):
    source = [[0, 1, 32768, 65535], [10, 11, 12, 13], [64500, 32000, 120, 400]]
    path = tmp_path / 'height.png'
    write_heightmap(path, source)
    decoded, digest = read_heightmap(path)
    assert decoded == source
    assert len(digest) == 64
    assert path.read_bytes()[:8] == b'\x89PNG\r\n\x1a\n'


def test_png_crc_failure(tmp_path):
    path = tmp_path / 'height.png'
    write_heightmap(path, [[1, 2], [3, 4]])
    payload = bytearray(path.read_bytes())
    payload[20] ^= 0x01
    path.write_bytes(payload)
    with pytest.raises(ValueError, match='CRC'):
        read_heightmap(path)


def test_reject_wrong_png_bit_depth(tmp_path):
    path = tmp_path / 'height.png'
    write_heightmap(path, [[1, 2], [3, 4]])
    data = bytearray(path.read_bytes())
    # Intentionally modify the bit-depth field and fix the IHDR CRC to verify format validation.
    data[24] = 8
    import binascii
    crc = binascii.crc32(data[12:29]) & 0xFFFFFFFF
    data[29:33] = struct.pack('>I', crc)
    path.write_bytes(data)
    with pytest.raises(ValueError, match='16-bit'):
        read_heightmap(path)


def test_reject_out_of_range_heightmap(tmp_path):
    with pytest.raises(ValueError, match='unsigned 16-bit'):
        write_heightmap(tmp_path / 'x.png', [[-1, 2], [4, 65536]])
