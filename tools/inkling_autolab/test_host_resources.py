"""Phase accounting must never bridge over a different phase or process lifetime."""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('host_resources', Path(__file__).with_name('analyze-host-resources.py'))
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)


def row(t, counter):
    return {
        'unix': 1000 + t, 'monotonic': t,
        'processes': [{'pid': 7, 'created_unix': 900, 'executable': 'full.exe',
                       'cpu_seconds': {'user': counter, 'system': 0},
                       'memory_info': {'num_page_faults': counter, 'private': 100, 'rss': 100},
                       'io_cumulative': {'read_bytes': counter}}],
        'machine_disk_io_cumulative': {'read_bytes': counter},
        'memory': {'available': 100}, 'swap': {'used': 0},
    }


def test_phase_intervals_do_not_bridge_prefill_or_cross_boundaries():
    rows = [row(t, c) for t, c in [(0, 0), (10, 100), (20, 110), (30, 1000), (40, 2000), (50, 2010)]]
    result = host.analyze(rows, 7, 900, [(1009, 1021), (1039, 1051)])
    assert result['intervals'] == 2
    assert result['sampled_seconds'] == 20
    assert result['process_read_bytes_per_second'] == 1
    assert result['cpu_core_equivalents'] == 1
    assert not result['includes_load_prefill_decode']
    with pytest.raises(ValueError):
        host.analyze(rows, 7, 901, [(1009, 1021)])


def test_phase_windows_reject_wall_clock_jump():
    benchmark = {'samples': [{'decode_started_unix': 1000, 'decode_ended_unix': 1010, 'decode_seconds': 9}]}
    with pytest.raises(ValueError, match='wall clock'):
        host.phase_windows(benchmark, 'decode')
