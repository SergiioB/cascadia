"""Forecast a fixed-budget global cache using past routing only, not speed."""
import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path


def module(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def replay(trace, predictions, shared):
    layer_ids = [layer['layer'] for layer in trace['samples'][0]['layers']]
    states = {layer: dict(entries=[], freq=[0]*256, last=[0]*256, clock=0) for layer in layer_ids}
    entries = []
    totals = Counter(dict(hits=0, misses=0, admissions=0, evictions=0,
                          recent_tie_admissions=0, first_reads=0, second_reads=0,
                          useful_reads=0, unused_reads=0))
    cases = []
    mapping = {(s['case'], s['repetition']): {l['layer']: l['routed_experts_per_position']
               for l in s['layers']} for s in predictions['samples']}
    for sample in trace['samples']:
        assert [layer['layer'] for layer in sample['layers']] == layer_ids
        before = totals.copy()
        for state in states.values():
            state.update(freq=[0]*256, last=[0]*256, clock=0)
        global_clock = 0
        predicted = mapping[sample['case'], sample['repetition']]
        for position in range(sample['decode_positions']):
            for layer in sample['layers']:
                lid = layer['layer']
                state = states[lid]
                cohort = layer['routed_experts_per_position'][sample['prefill_positions']+position]
                resident = {e for l, e in entries if l == lid} if shared else set(state['entries'])
                ranked = [(rank, e) for rank, e in enumerate(predicted[lid][position]) if e not in resident]
                chosen = ranked[:1]
                if len(ranked) > 1 and ranked[1][0] <= 2:
                    chosen.append(ranked[1])
                # This choice is frozen before actual routing scores its utility.
                totals['first_reads'] += bool(chosen)
                totals['second_reads'] += len(chosen) == 2
                totals['useful_reads'] += sum(e in cohort for _, e in chosen)
                totals['unused_reads'] += sum(e not in cohort for _, e in chosen)
                missing = []
                for expert in cohort:
                    global_clock += 1
                    state['clock'] += 1
                    if state['clock'] % 32 == 0:
                        state['freq'] = [(x+1)//2 for x in state['freq']]
                    state['freq'][expert] += 1
                    state['last'][expert] = global_clock
                    totals['hits' if expert in resident else 'misses'] += 1
                    if expert not in resident:
                        missing.append(expert)
                for expert in missing:
                    cache = entries if shared else state['entries']
                    key = (lid, expert) if shared else expert
                    capacity = 8*len(layer_ids) if shared else 8
                    def priority(item):
                        l, e = item if shared else (lid, item)
                        return states[l]['freq'][e], states[l]['last'][e]
                    if len(cache) == capacity:
                        victim = min(range(capacity), key=lambda i: priority(cache[i]))
                        incoming, old = priority(key), priority(cache[victim])
                        if incoming <= old:
                            continue
                        cache[victim] = cache[-1]
                        cache.pop()
                        totals['evictions'] += 1
                        totals['recent_tie_admissions'] += incoming[0] == old[0]
                    cache.append(key)
                    totals['admissions'] += 1
        case = dict(case=sample['case'], repetition=sample['repetition'],
                    **{k: totals[k]-before[k] for k in totals})
        case['completed_reads'] = case['misses']+case['unused_reads']
        cases.append(case)
    return dict(shared=shared, capacity_slots=8*len(layer_ids), **totals,
                completed_reads=totals['misses']+totals['unused_reads'], cases=cases,
                final_slots_by_layer=dict(sorted(Counter(l for l, e in entries).items())) if shared else {l: 8 for l in layer_ids})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['trace', 'predictions', 'benchmark', 'out']:
        p.add_argument('--'+name, type=Path, required=True)
    a = p.parse_args()
    assert not a.out.exists()
    validation = module('analyze-route-prediction')
    actual, ah = validation.read(a.trace)
    predicted, ph = validation.read(a.predictions)
    benchmark, bh = validation.read(a.benchmark)
    validation.analyze(actual, predicted, benchmark, 1)
    reference = module('analyze-cache-recency').replay(actual, 8, 32, 'ceil', 'recent')
    control = replay(actual, predicted, False)
    for key in ['hits', 'misses', 'admissions', 'evictions', 'recent_tie_admissions']:
        assert control[key] == reference[key] == benchmark['expert_cache'][key], key
        assert [c[key] for c in control['cases']] == [c[key] for c in reference['cases']], key
    second = module('analyze-second-prediction').analyze(actual, predicted, benchmark, [2])
    prior = next(x for x in second['results'] if x['group'] == 'all')
    for key in ['first_reads', 'second_reads', 'useful_reads', 'unused_reads']:
        assert control[key] == prior[key], key
    candidate = replay(actual, predicted, True)
    reductions = [dict(case=b['case'], reduction=1-b['completed_reads']/c['completed_reads'])
                  for b, c in zip(candidate['cases'], control['cases'], strict=True)]
    reduction = 1-candidate['completed_reads']/control['completed_reads']
    result = dict(scope='causal_shared_cache_forecast_not_throughput',
                  source_sha256=dict(actual=ah, predictions=ph, benchmark=bh),
                  control_matches_actual_and_independent_replay=True,
                  selection_uses_future_routes=False, fixed_total_budget=True,
                  control=control, candidate=candidate, read_reduction=reduction,
                  case_read_reductions=reductions,
                  priority_budget_passed=reduction >= .02 and all(x['reduction'] >= 0 for x in reductions),
                  caveats=['Per-layer decay32; global past-access recency. History resets retain entries.',
                           'Counts complete reads including unused two-reader predictions; no latency or allocation claim.',
                           'Runtime implementation and native qualification are required before any speed claim.'])
    with a.out.open('x') as f:
        json.dump(result, f, indent=2)
        f.write('\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('control', 'candidate')}, indent=2))


if __name__ == '__main__':
    main()
