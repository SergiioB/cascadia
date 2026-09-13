import copy
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('routing_analysis', Path(__file__).with_name('analyze-routing.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def sample_trace():
    return {'scope': 'routing_diagnostics', 'full_model': False, 'correctness_verified': True,
            'output_hash': 'fixture',
            'manifest': {'layers': 1, 'routed_experts': 4, 'shared_experts': 2,
                         'top_k': 1, 'hidden': 32, 'intermediate': 32},
            'samples': [{'case': 'cycle', 'repetition': 0, 'prefill_positions': 1,
                         'decode_positions': 4, 'layers': [
                             {'layer': 0, 'routed_experts_per_position': [[0], [0], [1], [0], [2]]}]}]}


def test_windows_prefill_warming_and_lru_eviction():
    trace = sample_trace()
    expert_bytes = 1728
    report = module.analyze(trace, {'one': expert_bytes, 'all': 4 * expert_bytes})
    case = report['cases'][0]
    assert case['windows']['1']['max_routed_bytes'] == expert_bytes
    assert case['windows']['2']['max_routed_bytes'] == 2 * expert_bytes
    assert case['windows']['4']['max_routed_bytes'] == 3 * expert_bytes
    assert case['cache_models']['one']['simulated_lru_decode_misses'] == 3
    assert case['cache_models']['all']['simulated_lru_decode_misses'] == 2
    assert case['cache_models']['one']['max_window_miss_lower_bound_bytes_per_token'] == expert_bytes / 2
    assert report['shared_expert_bytes'] == 2 * expert_bytes


def test_layer_identity_and_repetition_validation():
    trace = sample_trace()
    layer = copy.deepcopy(trace['samples'][0]['layers'][0])
    layer['layer'] = 1
    trace['samples'][0]['layers'].append(layer)
    repeat = copy.deepcopy(trace['samples'][0])
    repeat['repetition'] = 1
    trace['samples'].append(repeat)
    report = module.analyze(trace, {'none': 0})
    assert report['distinct_cases'] == 1
    assert report['cases'][0]['windows']['1']['max_routed_bytes'] == 3456
    trace['samples'][1]['layers'][0]['routed_experts_per_position'][1] = [3]
    with pytest.raises(ValueError, match='differ across repetitions'):
        module.analyze(trace, {'none': 0})


def test_partial_trace_cannot_be_labeled_full_model():
    trace = sample_trace()
    trace['full_model'] = True
    with pytest.raises(ValueError, match='Incomplete large-model'):
        module.analyze(trace, {'none': 0})
