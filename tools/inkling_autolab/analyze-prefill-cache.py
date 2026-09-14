"""Causal prefill-history/cache replay, not measured runtime throughput.

All prefill experts are already read by the streamed path. Count only current
block routes, then admit its expert buffers in ascending ID order as that path
visits them. No decode route is inspected until its decode step is reached.
"""
import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path


def replay(trace, slots, decay, mode):
    states = {}
    total = dict(hits=0, misses=0, admissions=0, evictions=0,
                 prefill_admissions=0, prefill_evictions=0)
    cases = []

    def observe(state, expert):
        state['clock'] += 1
        if state['clock'] % decay == 0:
            state['freq'] = [(x + 1) // 2 for x in state['freq']]
        state['freq'][expert] += 1
        state['last'][expert] = state['clock']

    def retain(state, expert, prefix=''):
        entries = state['entries']
        if expert in entries:
            return
        if len(entries) == slots:
            victim = min(range(slots), key=lambda i: (state['freq'][entries[i]], state['last'][entries[i]]))
            if state['freq'][expert] <= state['freq'][entries[victim]]:
                return
            entries[victim] = entries[-1]
            entries.pop()
            total[prefix + 'evictions'] += 1
        entries.append(expert)
        total[prefix + 'admissions'] += 1

    for sample in trace['samples']:
        before = total.copy()
        for layer in sample['layers']:
            state = states.setdefault(layer['layer'], dict(entries=[]))
            state.update(freq=[0] * 256, last=[0] * 256, clock=0)
            routes = layer['routed_experts_per_position']
            prefill = routes[:sample['prefill_positions']]
            decode = routes[sample['prefill_positions']:]
            assert len(decode) == sample['decode_positions']
            if mode != 'none':
                for lo in range(0, len(prefill), 128):
                    current = prefill[lo:lo + 128]
                    for cohort in current:
                        for expert in cohort:
                            observe(state, expert)
                    if mode == 'seed':
                        for expert in sorted({e for cohort in current for e in cohort}):
                            retain(state, expert, 'prefill_')
            for cohort in decode:
                missing = []
                for expert in cohort:
                    observe(state, expert)
                    if expert in state['entries']:
                        total['hits'] += 1
                    else:
                        total['misses'] += 1
                        missing.append(expert)
                for expert in missing:
                    retain(state, expert)
        cases.append(dict(case=sample['case'], repetition=sample['repetition'],
                          **{k: total[k] - before[k] for k in total}))
    return dict(slots=slots, decay_requests=decay, prefill_mode=mode, **total, cases=cases)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--trace', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        p.error('refusing to overwrite report')
    raw = a.trace.read_bytes()
    trace = json.loads(gzip.decompress(raw) if a.trace.suffix == '.gz' else raw)
    assert trace['full_model'] and trace['correctness_verified']
    assert trace['manifest']['routed_experts'] == 256
    spec = importlib.util.spec_from_file_location('admission', Path(__file__).with_name('analyze-cache-admission.py'))
    base = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(base)
    results = []
    for slots in (2, 4, 8):
        for decay in (32, 4096):
            reference = base.replay(trace, slots, True, decay)
            for mode in ('none', 'history', 'seed'):
                result = replay(trace, slots, decay, mode)
                if mode == 'none':
                    for key in ('hits', 'misses', 'admissions', 'evictions'):
                        assert result[key] == reference[key], (slots, decay, key)
                    for actual, expected in zip(result['cases'], reference['cases']):
                        assert all(actual[k] == v for k, v in expected.items())
                result['decode_read_reduction_vs_control'] = 1 - result['misses'] / reference['misses']
                results.append(result)
    report = dict(scope='causal_prefill_cache_prediction_not_measured_throughput',
                  source_sha256=hashlib.sha256(raw).hexdigest(), output_hash=trace['output_hash'],
                  controls_match_existing_replay=True, results=results,
                  caveats=['No runtime implementation or throughput measurement.',
                           'Existing streamed prefill reads every unique current-block expert; this assumes retaining those bytes with no extra reads.',
                           'Counts prefill routes in row/gate order and retains weights in existing ascending expert visit order.'])
    with a.out.open('x') as f:
        json.dump(report, f, indent=2)
    print(json.dumps([{k: v for k, v in r.items() if k != 'cases'} for r in results], indent=2))


if __name__ == '__main__':
    main()
