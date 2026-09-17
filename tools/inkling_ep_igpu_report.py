#!/usr/bin/env python3
"""Validate actual GPU execution and summarize the two saved LAN experiments."""
import argparse
import json
from pathlib import Path

from inkling_ep_lan_report import distribution, require


def summarize(root):
    def read(name):
        return json.loads((root/name).read_text())

    def gpu(stats):
        require(stats['gpu_required'] and stats['device'] == 'GPU' and
                'iGPU' in stats['gpu_name'], 'missing concrete iGPU identity')
        require(stats['cpu_calls'] == 0 and stats['ov_fallbacks'] == 0 and
                stats['ov_successful_calls'] > 0, 'CPU fallback or missing GPU execution')

    runs = []
    for suffix, warm in [('', 1), ('-warm2', 2)]:
        local, remote = (read('alpha/gpu-'+mode+suffix+'.json') for mode in ['local', 'ep'])
        gpu(local['local_backend'])
        require(local['reference_verified'] and remote['reference_verified'], 'missing numerical check')
        require(remote['reference_comparison']['bit_exact'], 'distributed GPU outputs differ from local GPU')
        stats = []
        for i, host in enumerate(['alpha', 'beta', 'charlie']):
            lines = (root/host/('gpu-layer-worker-'+str(i)+suffix+'.log')).read_text().splitlines()
            matches = [json.loads(line.split('=', 1)[1]) for line in lines if line.startswith('backend_final=')]
            require(len(matches) == 1, 'missing final worker counters')
            gpu(matches[0])
            stats.append(matches[0])
        expected_calls = 8*local['frames']*(local['samples']+warm)
        require(sum(s['ov_successful_calls'] for s in stats) == expected_calls and
                local['local_backend']['ov_successful_calls'] == expected_calls,
                'GPU counters do not cover every selected expert')
        distributions = []
        for result in [local, remote]:
            require(result['full_model_inference'] is False and result['self_consistency_verified'], 'wrong scope or unstable output')
            require(result['hidden'] == 6144 and result['intermediate'] == 3072, 'wrong expert dimensions')
            require(result.get('warm_passes', 1) == warm, 'unexpected warm-up protocol')
            require(len(result['timings']) == result['frames']*result['samples'], 'incomplete timings')
            distributions.append(distribution([v['milliseconds'] for v in result['timings']]))
        a, b = distributions
        runs.append(dict(warm_passes=warm, local_gpu_ms=a, distributed_gpu_ms=b,
                         mean_speedup=a['mean']/b['mean'], median_speedup=a['median']/b['median'],
                         cpu_reference_comparison=local['reference_comparison'],
                         distributed_matches_local_gpu_bits=True, worker_counters=stats))
    audits = {}
    expected_binaries = read('alpha/gpu-binaries-warm2.json')
    for host in ['alpha', 'beta', 'charlie']:
        a = read(host+'/gpu-audit-after-warm2.json')
        require(read(host+'/gpu-binaries-warm2.json') == expected_binaries,
                'GPU deployment artifacts differ between hosts')
        require(all(meta == expected_binaries[name] for name, meta in a['binaries'].items()),
                'audited executables differ from the benchmark build')
        require(a['ovms_health'] == {'live': 200, 'ready': 200} and not a['own_processes'] and
                not a['own_listening_ports'] and a['task_firewall_rule_removed'], 'cleanup/health failed')
        for p in (root/host).glob('gpu-*.status.json'):
            s = json.loads(p.read_text())
            require(s['state'] == 'finished' and s['returncode'] == 0 and s['stop_reason'] is None,
                    'job failed or was preempted')
            require(s['protected_processes_unchanged'] and s['protected_after'] == a['protected'],
                    'protected process identity changed')
        audits[host] = dict(ovms_health=a['ovms_health'], task_processes_and_rules_removed=True,
                           protected_processes_unchanged=True, free_memory_gib=a['free_memory_gib'],
                           free_disk_gib=a['free_disk_gib'])
    return dict(scope='one_resident_MoE_layer_per_expert_OpenVINO_iGPU_routing',
                full_model_inference=False, fused_MoE_sharding=False, experiments=runs, audits=audits)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--artifacts', required=True, type=Path)
    p.add_argument('--out', required=True, type=Path)
    a = p.parse_args()
    result = summarize(a.artifacts)
    a.out.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))
