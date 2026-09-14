"""Join causal cache misses with measured layer latency; correlation, not speedup."""
import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics


def read(path):
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == '.gz' else raw), hashlib.sha256(raw).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('trace', 'profile', 'benchmark', 'out'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--slots', type=int, required=True)
    p.add_argument('--decay', type=int, required=True)
    a = p.parse_args()
    if a.out.exists():
        p.error('refusing to overwrite report')
    trace, trace_sha = read(a.trace)
    profile, profile_sha = read(a.profile)
    benchmark, benchmark_sha = read(a.benchmark)
    assert trace['full_model'] and profile['full_model'] and benchmark['scope'] == 'full_large_model_decode'
    assert all(d['correctness_verified'] for d in (trace, profile, benchmark))
    assert trace['output_hash'] == profile['output_hash'] == benchmark['output_hash']
    timings = {}
    for sample in profile['samples']:
        for layer in sample['layers']:
            for position, event in enumerate(e for e in layer['events'] if not e['prefill']):
                assert event['rows'] == 1
                key = (sample['case'], sample['repetition'], layer['layer'], position)
                assert key not in timings
                timings[key] = event
    visits = []

    def observe(case, repetition, layer, position, misses):
        event = timings.pop((case, repetition, layer, position))
        visits.append(dict(misses=misses, mlp_seconds=event['mlp_seconds'], layer=layer))

    spec = importlib.util.spec_from_file_location('admission', Path(__file__).with_name('analyze-cache-admission.py'))
    base = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(base)
    replay = base.replay(trace, a.slots, True, a.decay, visit_observer=observe)
    for key in ('hits', 'misses', 'admissions', 'evictions'):
        assert replay[key] == benchmark['expert_cache'][key], (key, replay[key], benchmark['expert_cache'][key])
    assert len(visits) == sum(s['decode_steps'] for s in benchmark['samples']) * 64
    assert all(key[2] in (0, 1) for key in timings), 'unmatched sparse layer timing'
    groups = []
    for misses in range(7):
        values = [v['mlp_seconds'] for v in visits if v['misses'] == misses]
        if values:
            groups.append(dict(misses=misses, visits=len(values),
                               median_mlp_seconds=statistics.median(values),
                               mean_mlp_seconds=statistics.mean(values),
                               total_mlp_seconds=sum(values)))
    result = dict(scope='measured_latency_grouped_by_replayed_cache_misses',
                  output_hash=benchmark['output_hash'], replay_counters_match_actual=True,
                  decode_layer_visits=len(visits), groups=groups,
                  source_sha256=dict(trace=trace_sha, profile=profile_sha, benchmark=benchmark_sha),
                  caveats=['Cache misses are causal replay values, validated against actual aggregate counters.',
                           'MLP timings include compute and overlapped I/O; these groups are correlations across different layers and positions.',
                           'This does not isolate read time, prove a causal speedup, or predict full-model throughput.'])
    with a.out.open('x') as f:
        json.dump(result, f, indent=2)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
