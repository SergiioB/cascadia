#!/usr/bin/env python3
"""Validate the saved fused GPU evidence and summarize all timed observations."""
import argparse
import json
from pathlib import Path
import statistics


def summary(values):
    ordered = sorted(values)
    return dict(count=len(values), mean=statistics.mean(values), median=statistics.median(values),
                p95=ordered[int(.95*(len(ordered)-1))], maximum=max(values))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--artifacts', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    read = lambda name: json.loads((a.artifacts/name).read_text())
    experiments = ['v2b', 'compact-v4', 'raw-v4', 'compact-repeat-v4', 'raw-repeat-v4',
                   'batch-compact-v4', 'split-batch-compact-v4', 'split-batch-padded-v5',
                   'split-batch-rows32-v6', 'compact-final-v7', 'raw-final-v7',
                   'batch-final-v7', 'split-batch-final-v7']
    records = {}
    peaks, reserves = [], []
    for name in experiments:
        result = read('lan-'+name+'-result.json')
        assert result['full_model_inference'] is False
        assert result['reference_verified'] and result['self_consistency_verified']
        assert result['reference_comparison']['relative_rms'] <= .005
        assert result['samples'] == 3 and result['warm_passes'] == 2
        assert len(result['timings']) == result['frames']*3
        cases = read('split-batch-frames.json' if name.startswith('split-') else
                     'batch-frames.json' if name.startswith('batch-') else 'decode-frames.json')
        nonzero = sum(sum(w != 0 for w in row.get('weights', [1]*len(row['ids'])))
                      for f in cases for row in [f]+f.get('extra_rows', []))*5
        backend_rows = 0
        for i, host in enumerate(['alpha','beta','charlie']):
            worker = read(f'{host}-fused-{name}-worker-{i}.json')
            s = worker['status']
            assert worker['returncode'] == s['returncode'] == 0 and s['stop_reason'] is None
            assert s['protected_processes_unchanged'] and s['minimum_available_gib'] >= 12
            peaks.append(s['peak_rss_gib']); reserves.append(s['minimum_available_gib'])
            backend = json.loads(next(line.split('=',1)[1] for line in worker['log'].splitlines() if line.startswith('backend_final=')))
            assert backend['cpu_calls'] == backend['ov_fallbacks'] == 0
            if name.startswith('raw'):
                assert backend['device'] == 'GPU' and backend['gpu_required']
                backend_rows += backend['ov_successful_calls']
            else:
                fused = backend['fused']
                assert fused['device'] == 'GPU' and fused['fused_required'] and fused['errors'] == 0
                assert fused['cached_ir_bytes'] <= fused['ir_cache_budget_bytes']
                assert all('MOECompressed\tocl::moe::moe_3gemm_' in profile for profile in fused['fusion_profiles'].values())
                assert fused['fusion_profiles']
                if name != 'v2b':
                    assert fused['graph_k'] == {'2':1}
                    backend_rows += fused.get('selected_expert_rows', fused['rows'])
        if name != 'v2b':
            assert backend_rows == nonzero, (name, backend_rows, nonzero)
        driver = read(f'alpha-fused-{name}-driver.json')
        assert driver['returncode'] == 0 and driver['status']['stop_reason'] is None
        assert driver['status']['protected_processes_unchanged']
        records[name] = dict(milliseconds=summary([t['milliseconds'] for t in result['timings']]),
                             reference_comparison=result['reference_comparison'])
    raw = [t['milliseconds'] for name in ['raw-v4','raw-repeat-v4'] for t in read('lan-'+name+'-result.json')['timings']]
    fused = [t['milliseconds'] for name in ['compact-v4','compact-repeat-v4'] for t in read('lan-'+name+'-result.json')['timings']]
    identities = []
    for host in ['alpha','beta','charlie']:
        audit = read(host+'-audit.json')
        assert audit['task_processes_absent'] and audit['firewall_absent']
        assert audit['health'] == {'live':200,'ready':200}
        previous = read(f'{host}-fused-compact-v4-worker-'+str(['alpha','beta','charlie'].index(host))+'.json')['status']['protected_before']
        assert audit['processes'] == previous
        identities.append(audit['binaries'])
    assert identities[0] == identities[1] == identities[2]
    result = dict(scope='one resident MoE layer, synthetic inputs; not full-model token generation',
                  current_per_expert_ms=summary(raw), compact_fused_ms=summary(fused),
                  ratio_of_means=statistics.mean(raw)/statistics.mean(fused),
                  worker_peak_rss_gib=max(peaks), worker_minimum_available_gib=min(reserves),
                  final_native_check=dict(compact_ms=records['compact-final-v7']['milliseconds'],
                    per_expert_ms=records['raw-final-v7']['milliseconds'],
                    ratio=records['raw-final-v7']['milliseconds']['mean']/records['compact-final-v7']['milliseconds']['mean']),
                  experiments=records, all_checks_passed=True)
    a.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
