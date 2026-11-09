import copy
import json
from pathlib import Path

import pytest

from heightmap_png import read_heightmap, write_heightmap
from landscape_tool import (
    analyze, generate, load_config, main, protection_mask,
    validate, verify_orientation,
)


ROOT = Path(__file__).resolve().parents[1]


def config_for(size=33):
    cfg = json.loads((ROOT / 'examples/demo_config.json').read_text())
    cfg['landscape']['transform']['origin_xy_cm'] = [-(size//2)*100, -(size//2)*100]
    cfg['protected_regions'] = [
        {'name': 'Water protector', 'shape': 'circle', 'coordinate_space': 'pixel',
         'center': [5, 5], 'radius_m': 3}
    ]
    cfg['operation']['shore_start_m'] = 2
    cfg['operation']['shore_full_depth_m'] = 15
    cfg['operation']['boundary_start_m'] = 1
    cfg['operation']['boundary_end_m'] = 10
    cfg['operation']['edge_target_sample'] = 27000
    return cfg


def sample_map(size=33):
    # Land near centre and one protected underwater ring near top left.
    return [[32000 if (u-16)**2 + (v-16)**2 < 7**2 else 29000
             for u in range(size)] for v in range(size)]


def test_preserves_protected_and_land():
    source = sample_map()
    config = config_for()
    land, distance, mask = analyze(source, config)
    result = generate(source, config, land, distance, mask)
    statistics = validate(source, result, config, land, mask)
    assert statistics['passed']
    assert statistics['protected_changed_samples'] == 0
    assert statistics['land_changed_samples'] == 0
    assert statistics['raised_samples'] == 0
    assert statistics['edges_below_sea']
    assert statistics['changed_samples'] > 0
    assert all(result[y][x] == source[y][x]
               for y in range(33) for x in range(33)
               if land[y][x] or mask[y][x])


def test_detects_corrupted_protected_pixel():
    source = sample_map()
    cfg = config_for()
    land, distance, mask = analyze(source, cfg)
    result = generate(source, cfg, land, distance, mask)
    result[5][5] -= 1
    metrics = validate(source, result, cfg, land, mask)
    assert not metrics['passed']
    assert metrics['protected_changed_samples'] == 1


def test_detects_land_change_and_raise():
    source = sample_map()
    cfg = config_for()
    land, distance, mask = analyze(source, cfg)
    result = generate(source, cfg, land, distance, mask)
    result[16][16] += 1
    metrics = validate(source, result, cfg, land, mask)
    assert metrics['land_changed_samples'] == 1
    assert metrics['raised_samples'] == 1
    assert not metrics['passed']


def test_orientation_not_falsely_verified():
    assert verify_orientation(sample_map(), config_for()) == {
        'status': 'configured_not_independently_verified', 'checks': 0
    }


def test_orientation_using_real_control_point():
    source = [[32768 for _ in range(5)] for _ in range(5)]
    source[0][1] = 33100
    cfg = config_for(size=5)
    cfg['orientation_checks'] = [{
        'world_xy_cm': [-100, -200],
        'expected_z_cm': (33100 - 32768)*100/128,
        'tolerance_cm': 0.1,
    }]
    # Coordinates chosen so they map to u=1,v=0 when row zero is min.
    assert verify_orientation(source, cfg)['status'] == 'verified_against_supplied_control_points'
    cfg['landscape']['row_zero_world_y'] = 'max'
    with pytest.raises(ValueError, match='Orientation check failed'):
        verify_orientation(source, cfg)


def test_strict_edges_fail_if_land_touches_boundary():
    source = sample_map()
    source[0][0] = 32000
    cfg = config_for()
    land, distance, mask = analyze(source, cfg)
    result = generate(source, cfg, land, distance, mask)
    metrics = validate(source, result, cfg, land, mask)
    assert not metrics['passed']
    assert 'one or more boundary pixels' in metrics['failures'][0]


def test_generated_outputs_and_validate_cli(tmp_path, capsys):
    source_path = tmp_path / 'original.png'
    cfg_path = tmp_path / 'config.json'
    target = tmp_path / 'new'
    source = sample_map()
    write_heightmap(source_path, source)
    cfg_path.write_text(json.dumps(config_for()), encoding='utf-8')
    assert main(['generate', '--input', str(source_path), '--config', str(cfg_path),
                 '--dry-run']) == 0
    assert not target.exists()
    assert main(['generate', '--input', str(source_path), '--config', str(cfg_path),
                 '--output-dir', str(target)]) == 0
    assert {p.name for p in target.iterdir()} == {
        'heightmap.png', 'preview.png', 'difference.png', 'report.json', 'report.md'
    }
    assert read_heightmap(source_path)[0] == source
    assert read_heightmap(target / 'heightmap.png')[0] != source
    assert main(['validate', '--input', str(source_path), '--config', str(cfg_path),
                 '--candidate', str(target / 'heightmap.png')]) == 0
    assert main(['generate', '--input', str(source_path), '--config', str(cfg_path),
                 '--output-dir', str(target)]) == 1  # refuse overwrites
    report = json.loads((target / 'report.json').read_text(encoding='utf-8'))
    assert report['statistics']['passed']
    assert report['orientation']['status'] == 'configured_not_independently_verified'
    assert 'configured_not_independently_verified' in (target / 'report.md').read_text()


def test_no_source_file_overwrite_even_with_force(tmp_path):
    cfg_path = tmp_path / 'config.json'
    cfg_path.write_text(json.dumps(config_for()))
    source = tmp_path / 'heightmap.png'
    write_heightmap(source, sample_map())
    before = source.read_bytes()
    assert main(['generate', '--input', str(source), '--config', str(cfg_path),
                 '--output-dir', str(tmp_path), '--force']) == 1
    assert source.read_bytes() == before


def test_invalid_radius_and_schema_fail(tmp_path):
    cfg = config_for()
    cfg['protected_regions'][0]['radius_m'] = 0
    f = tmp_path / 'config.json'
    f.write_text(json.dumps(cfg))
    with pytest.raises(ValueError, match='radius_m'):
        load_config(f)
    cfg['protected_regions'][0]['radius_m'] = 5
    cfg['schema_version'] = 5
    f.write_text(json.dumps(cfg))
    with pytest.raises(ValueError, match='schema_version'):
        load_config(f)


def test_ambiguous_orientation_is_not_claimed_verified():
    source = [[32768] * 5 for _ in range(5)]
    cfg = config_for(size=5)
    cfg['orientation_checks'] = [{
        'world_xy_cm': [0, 0],
        'expected_z_cm': 0,
        'tolerance_cm': 1,
    }]
    result = verify_orientation(source, cfg)
    assert result['status'] == 'control_points_consistent_but_orientation_ambiguous'


def test_validate_cli_rejects_candidate_with_extra_deepening(tmp_path, capsys):
    source = sample_map()
    cfg = config_for()
    input_path = tmp_path / 'input.png'
    config_path = tmp_path / 'config.json'
    output_dir = tmp_path / 'generated'
    write_heightmap(input_path, source)
    config_path.write_text(json.dumps(cfg), encoding='utf-8')
    assert main(['generate', '--input', str(input_path), '--config', str(config_path),
                 '--output-dir', str(output_dir)]) == 0
    candidate, _ = read_heightmap(output_dir / 'heightmap.png')
    candidate[10][4] -= 1  # Water change: still safe to lower, but not what was generated.
    changed_path = tmp_path / 'unexpected.png'
    write_heightmap(changed_path, candidate)
    assert main(['validate', '--input', str(input_path), '--config', str(config_path),
                 '--candidate', str(changed_path)]) == 1
    captured = capsys.readouterr()
    assert 'expected_mismatched_samples' in captured.out
    assert 'samples differ from the expected' in captured.err


def test_all_water_protected_fails_validation():
    source = sample_map()
    cfg = config_for()
    cfg['protected_regions'] = [{
        'shape': 'ellipse', 'coordinate_space': 'pixel',
        'center': [16, 16], 'radius_m': [100, 100],
    }]
    land, distance, mask = analyze(source, cfg)
    result = generate(source, cfg, land, distance, mask)
    assert 'no editable water pixels found' in validate(source, result, cfg, land, mask)['failures']
