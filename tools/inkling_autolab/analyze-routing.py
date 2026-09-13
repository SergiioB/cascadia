#!/usr/bin/env python3
"""Analyze measured expert routes; report working sets and a whole-expert LRU model.

Cache budgets cover routed experts only. Shared experts, fixed weights, KV,
allocator overhead and other processes need additional memory. This reports
storage traffic estimates, never measured decode speed or target attainment.
"""
import argparse
from collections import Counter, OrderedDict
import json
import math
from pathlib import Path
import statistics


def partition_read_bound(accesses, budget, expert_bytes, max_segment=64):
    """Offline lower bound for the WHOLE trace, allowing any initial cache.

    Each disjoint segment must fetch at least union_bytes - budget. Maximize
    the sum over partitions; future routes are used only for this lower bound.
    Unlike a worst-window average, this bounds total decode traffic.
    """
    best = [0] * (len(accesses) + 1)
    previous = [None] * len(best)
    for end in range(1, len(best)):
        union = set()
        for start in range(end - 1, max(-1, end - max_segment - 1), -1):
            union.update(accesses[start])
            missing = max(0, len(union) * expert_bytes - budget)
            candidate = best[start] + missing
            if previous[end] is None or candidate > best[end]:
                best[end] = candidate
                previous[end] = (start, missing)
    segments = []
    end = len(accesses)
    while end:
        start, missing = previous[end]
        segments.append({'start': start, 'end': end, 'minimum_read_bytes': missing})
        end = start
    return {'offline_partition_minimum_decode_read_bytes': best[-1],
            'offline_partition_minimum_read_bytes_per_token': best[-1] / len(accesses),
            'offline_partition_max_segment_tokens': max_segment,
            'offline_partition_segments': list(reversed(segments))}


def simulate_group_cache(groups, capacity, layer_ids, per_layer=False, frequency=False):
    """Online admission from completed/current route groups, with no future IDs.

    Hits are checked for the complete selected set before admission/eviction.
    Ties prefer the current group's supplied order. Prefill uses per-layer
    unique-expert visits, matching the existing LRU warming approximation.
    """
    local_capacity = capacity // len(layer_ids) if per_layer else capacity
    caches, counts, recency = {}, Counter(), {}
    misses = accesses = 0
    for tick, (decode, keys) in enumerate(groups):
        scope = keys[0][0] if per_layer else None
        cache = caches.setdefault(scope, set())
        if decode:
            accesses += len(keys)
            misses += sum(key not in cache for key in keys)
        if not local_capacity:
            continue
        counts.update(keys)
        recency.update({key: (tick, -rank) for rank, key in enumerate(keys)})
        candidates = cache.union(keys)
        order = lambda key: ((counts[key],) if frequency else ()) + recency[key]
        caches[scope] = set(sorted(candidates, key=order, reverse=True)[:local_capacity])
    return {'decode_accesses': accesses, 'decode_misses': misses,
            'decode_hit_fraction': 1 - misses / accesses,
            'allocated_expert_slots': local_capacity * (len(layer_ids) if per_layer else 1),
            'uses_future_routes': False,
            'admission': 'completed_or_current_route_group',
            'prefill_warming': 'per_layer_unique_expert_visits'}


def analyze(trace, budgets, fixed_bytes=None, compare_policies=False):
    if trace['scope'] != 'routing_diagnostics' or not trace['samples']:
        raise ValueError('Expected a nonempty routing trace')
    if fixed_bytes is not None and (type(fixed_bytes) is not int or fixed_bytes < 0):
        raise ValueError('Fixed model bytes must be nonnegative')
    manifest = trace['manifest']
    hidden, intermediate = manifest['hidden'], manifest['intermediate']
    if min(hidden, intermediate) <= 0 or hidden % 32 or intermediate % 32:
        raise ValueError('Expected group-32 expert dimensions')
    expert_bytes = 3 * hidden * intermediate * 9 // 16
    cases = {}
    reports = []
    expected_layers = None
    for sample in trace['samples']:
        prefill, decode = sample['prefill_positions'], sample['decode_positions']
        layers = sorted(sample['layers'], key=lambda layer: layer['layer'])
        layer_ids = [layer['layer'] for layer in layers]
        if not layer_ids or len(set(layer_ids)) != len(layer_ids):
            raise ValueError('Missing or duplicated MoE layer')
        if expected_layers is None:
            expected_layers = layer_ids
        if layer_ids != expected_layers or prefill < 1 or decode < 1:
            raise ValueError('Inconsistent trace shape')
        if trace['full_model'] and (manifest['layers'] != 66 or layer_ids != list(range(2, 66))
                                    or manifest['routed_experts'] != 256 or manifest['top_k'] != 6
                                    or manifest['shared_experts'] != 2 or hidden != 6144 or intermediate != 3072):
            raise ValueError('Incomplete large-model routing trace')
        for layer in layers:
            rows = layer['routed_experts_per_position']
            if len(rows) != prefill + decode:
                raise ValueError('Routing position count differs from generation')
            for row in rows:
                if (len(row) != manifest['top_k'] or len(set(row)) != len(row)
                        or any(type(e) is not int or not 0 <= e < manifest['routed_experts'] for e in row)):
                    raise ValueError('Invalid routed expert selection')
        signature = (prefill, decode, layers)
        if sample['case'] in cases:
            if cases[sample['case']] != signature:
                raise ValueError('Routes differ across repetitions')
            continue
        cases[sample['case']] = signature
        accesses = [[(layer['layer'], expert) for layer in layers
                     for expert in layer['routed_experts_per_position'][prefill + position]]
                    for position in range(decode)]
        groups = []
        if compare_policies:
            for layer in layers:
                rows = layer['routed_experts_per_position']
                for lo in range(0, prefill, 128):
                    keys = sorted({e for row in rows[lo:min(lo + 128, prefill)] for e in row})
                    groups.append((False, [(layer['layer'], expert) for expert in keys]))
            for selection in accesses:
                k = manifest['top_k']
                groups.extend((True, selection[lo:lo + k]) for lo in range(0, len(selection), k))
        window_reports = {}
        for window in (1, 2, 4, 8, 16, 32, 64):
            if window > decode:
                continue
            counts = Counter()
            sizes = []
            for position, selection in enumerate(accesses):
                counts.update(selection)
                if position >= window:
                    for key in accesses[position - window]:
                        counts[key] -= 1
                        if counts[key] == 0:
                            del counts[key]
                if position + 1 >= window:
                    sizes.append(len(counts) * expert_bytes)
            window_reports[str(window)] = {'max_routed_bytes': max(sizes),
                                            'median_routed_bytes': statistics.median(sizes)}
            if fixed_bytes is not None:
                window_reports[str(window)]['max_model_file_working_set_bytes'] = (
                    fixed_bytes + len(layers) * manifest['shared_experts'] * expert_bytes + max(sizes))
        cache_reports = {}
        for label, budget in budgets.items():
            if type(budget) is not int or budget < 0:
                raise ValueError('Cache budgets must be nonnegative integer bytes')
            capacity = budget // expert_bytes
            cache = OrderedDict()

            def access(key):
                hit = key in cache
                if hit:
                    cache.move_to_end(key)
                elif capacity:
                    cache[key] = None
                    if len(cache) > capacity:
                        cache.popitem(last=False)
                return not hit

            # Approximate prefill visitation: per-layer unions in 128-row blocks.
            # Actual parallel completion order and OS page replacement can differ.
            for layer in layers:
                rows = layer['routed_experts_per_position']
                for lo in range(0, prefill, 128):
                    for expert in sorted({e for row in rows[lo:min(lo + 128, prefill)] for e in row}):
                        access((layer['layer'], expert))
            misses = sum(access(key) for selection in accesses for key in selection)
            # Even an ideal initial cache cannot hold more than budget bytes of
            # each observed window's union. This assumes the current full-matrix
            # expert implementation, and excludes fixed/shared weight traffic.
            window_bound = max(max(0, stats['max_routed_bytes'] - budget) / int(window)
                               for window, stats in window_reports.items())
            cache_reports[label] = {'routed_budget_bytes': budget, 'whole_expert_capacity': capacity,
                                    'simulated_lru_decode_misses': misses,
                                    'simulated_lru_miss_bytes_per_decode_token': misses * expert_bytes / decode,
                                    'max_window_miss_lower_bound_bytes_per_token': window_bound}
            if compare_policies:
                cache_reports[label].update(partition_read_bound(accesses, budget, expert_bytes))
                policies = {}
                for name, local, frequency in [('global_group_lru', False, False),
                                                ('global_group_lfu', False, True),
                                                ('per_layer_group_lru', True, False),
                                                ('per_layer_group_lfu', True, True)]:
                    policy = simulate_group_cache(groups, capacity, layer_ids, local, frequency)
                    policy['simulated_read_bytes_per_token'] = policy['decode_misses'] * expert_bytes / decode
                    policy['allocated_routed_bytes'] = policy['allocated_expert_slots'] * expert_bytes
                    policies[name] = policy
                cache_reports[label]['online_policy_models'] = policies
        reports.append({'case': sample['case'], 'decode_positions': decode,
                        'windows': window_reports, 'cache_models': cache_reports})
    return {'scope': 'routing_storage_analysis', 'full_model': trace['full_model'],
            'correctness_verified': trace['correctness_verified'], 'output_hash': trace['output_hash'],
            'routed_expert_bytes': expert_bytes, 'fixed_nonexpert_file_bytes': fixed_bytes,
            'shared_expert_bytes': len(expected_layers) * manifest['shared_experts'] * expert_bytes,
            'source_samples': len(trace['samples']), 'distinct_cases': len(reports),
            'cases': reports, 'measured_decode_throughput': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trace', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--routed-cache-gib', type=float, nargs='+', default=[8, 12, 16, 24, 32])
    parser.add_argument('--fixed-model-bytes', type=int)
    parser.add_argument('--require-full', action='store_true')
    parser.add_argument('--compare-policies', action='store_true')
    args = parser.parse_args()
    if args.out.exists():
        parser.error('refusing to overwrite report')
    if any(not math.isfinite(gib) or gib < 0 for gib in args.routed_cache_gib):
        parser.error('cache budgets must be finite and nonnegative')
    trace = json.loads(args.trace.read_text())
    if args.require_full and (not trace['full_model'] or not trace['correctness_verified']):
        parser.error('a correctness-verified full-model trace is required')
    report = analyze(trace, {f'{gib:g}GiB': int(gib * 1024**3) for gib in args.routed_cache_gib},
                     args.fixed_model_bytes, args.compare_policies)
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'cases': report['distinct_cases'], 'full_model': report['full_model'],
                      'routed_expert_bytes': report['routed_expert_bytes']}))


if __name__ == '__main__':
    main()
