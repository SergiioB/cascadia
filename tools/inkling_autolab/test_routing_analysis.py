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


def test_partition_bound_adds_only_disjoint_windows():
    accesses = [[0], [1], [0], [2]]
    assert module.partition_read_bound(accesses, 0, 1)['offline_partition_minimum_decode_read_bytes'] == 4
    bound = module.partition_read_bound(accesses, 1, 1)
    assert bound['offline_partition_minimum_decode_read_bytes'] == 2
    assert bound['offline_partition_minimum_read_bytes_per_token'] == 0.5
    assert module.partition_read_bound(accesses, 3, 1)['offline_partition_minimum_decode_read_bytes'] == 0


def test_layer_quota_prevents_global_scan_thrashing():
    # One recurring expert per layer plus one-use experts: local LFU keeps the
    # two recurring experts, while a two-slot global LRU continually evicts them.
    groups = [(True, [(layer, 0), (layer, step + 1)])
              for step in range(4) for layer in range(2)]
    global_lru = module.simulate_group_cache(groups, 2, [0, 1])
    local_lfu = module.simulate_group_cache(groups, 2, [0, 1], True, True)
    assert global_lru['decode_misses'] == 16
    assert local_lfu['decode_misses'] == 10
    assert local_lfu['allocated_expert_slots'] == 2
    assert not local_lfu['uses_future_routes']


def test_atomic_route_group_counts_hits_before_admitting_misses():
    groups = [(False, [(0, 0), (0, 1)]), (True, [(0, 2), (0, 0), (0, 1)])]
    result = module.simulate_group_cache(groups, 2, [0])
    assert result['decode_accesses'] == 3 and result['decode_misses'] == 1


def test_offline_bound_never_exceeds_online_policy_reads():
    report = module.analyze(sample_trace(), {'none': 0, 'one': 1728, 'all': 4 * 1728},
                            compare_policies=True)
    for cache in report['cases'][0]['cache_models'].values():
        for policy in cache['online_policy_models'].values():
            assert policy['simulated_read_bytes_per_token'] >= cache['offline_partition_minimum_read_bytes_per_token']


def test_partition_bound_against_exhaustive_optimal_paging():
    from itertools import combinations, product

    universe = range(3)
    for trace in product(universe, repeat=4):
        for capacity in range(4):
            # An independent exhaustive oracle permits any initial cache and
            # every legal post-read retained set, including bypass admission.
            states = {frozenset(c): 0 for n in range(capacity + 1)
                      for c in combinations(universe, n)}
            for key in trace:
                following = {}
                for cache, cost in states.items():
                    cost += key not in cache
                    choices = cache | {key}
                    for n in range(min(capacity, len(choices)) + 1):
                        for kept in combinations(choices, n):
                            kept = frozenset(kept)
                            following[kept] = min(following.get(kept, cost), cost)
                states = following
            bound = module.partition_read_bound([[key] for key in trace], capacity, 1)
            assert bound['offline_partition_minimum_decode_read_bytes'] <= min(states.values())
