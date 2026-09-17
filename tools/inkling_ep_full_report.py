#!/usr/bin/env python3
"""Audit saved full-model CPU/GPU qualification, independently of its verdict flags.

Large float payloads are retained remotely under their recorded hashes. This
checks the complete numerical reports, execution evidence and deployment audits.
Instrumented timings include trace/comparison overhead and are not record runs.
"""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import statistics

from inkling_ep_full_run import qualification


def read(path):
    data = path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix == '.gz' else data)


def inspect_run(root, label, fused, cases, expected_ids, audit):
    files = read(root/(label+'.json.gz'))
    inventory = files['preflight.json']
    driver = files['charlie-'+label+'.json']
    workers = {h:files[f'{h}-{label}-worker-{i}.json'] for i,h in enumerate(['alpha','beta','charlie'])}
    gate = qualification(driver, workers, inventory, fused)
    assert gate['completed'], gate['failures']
    report = driver['report']
    assert report['tokens_per_case'] == 16 and report['generated_ids'] == expected_ids
    assert report['teacher_forced'] and not report['stops_at_eos']
    assert len(report['workers']) == 3
    limit = .005 if fused else 0.
    assert report['relative_rms_tolerance'] == limit
    errors = iter(report['tensor_errors'])
    count, maximum_rms, changed = 0, 0., 0
    for case in cases:
        for step in range(16):
            for layer in [*range(66), None]:
                e = next(errors)
                expected = dict(case=case['name'],step=step,layer=layer,
                    rows=len(case['prompt_ids']) if step == 0 and layer is not None else 1,
                    width=6144 if layer is not None else 200058)
                assert e['tensor'] == expected, (e['tensor'], expected)
                assert math.isfinite(e['relative_rms']) and math.isfinite(e['max_abs'])
                assert e['relative_rms'] <= limit and e['passed']
                assert fused or e['different_bits'] == 0
                maximum_rms = max(maximum_rms,e['relative_rms'])
                changed += e['different_bits'];count += 1
    assert next(errors,None) is None and count == 3216
    peaks = {}
    for host,worker in workers.items():
        status = worker['status']
        assert status['minimum_available_gib'] >= 12
        assert status['peak_rss_gib'] <= status['job']['max_rss_gib']
        assert audit[host]['protected'] == status['protected_before'] == status['protected_after']
        peaks[host] = status['peak_rss_gib']
    assert driver['status']['minimum_available_gib'] >= 12
    assert driver['status']['peak_rss_gib'] <= driver['status']['job']['max_rss_gib']
    assert audit['charlie']['protected'] == driver['status']['protected_before']
    assert set(files['cleanup.json']) == set(workers)
    rows = sum(len(c['prompt_ids'])+15 for c in cases)
    if not fused:
        assert sum(b['cpu_calls'] for b in gate['backends'].values()) == rows*64*8
    identities = [v['executable_sha256'] for v in inventory.values()]
    assert identities[0] == identities[1] == identities[2]
    builds = read(root/'run-builds.json')
    build_name = builds[label]
    assert Path(build_name).name == build_name
    build = read(root/build_name)
    for name in ['inkling_ep_worker.exe','inkling_ep_validate.exe']:
        assert identities[0][name] == build['executable_sha256']['bin-full/'+name]
    points = re.findall(r'case=(\S+) step=(\d+) token=(\d+) elapsed_seconds=([\d.]+)',driver['log'])
    assert len(points) == 48
    intervals = []
    for ci,case in enumerate(cases):
        sequence = points[ci*16:(ci+1)*16]
        assert all(name==case['name'] and int(step)==i and int(token)==expected_ids[ci][i]
                   for i,(name,step,token,_) in enumerate(sequence))
        times = [float(p[3]) for p in sequence]
        intervals.extend(b-a for a,b in zip(times,times[1:]))
    assert all(t>0 for t in intervals) and len(intervals)==45
    return dict(label=label,full_model=True,matched_tokens=48,matched_tensors=count,
        maximum_relative_rms=maximum_rms,different_float_bits=changed,
        driver_peak_rss_gib=driver['status']['peak_rss_gib'],worker_peak_rss_gib=peaks,
        fused_gpu_calls={h:b['fused']['calls'] for h,b in gate['backends'].items()} if fused else None,
        fused_selected_expert_rows={h:b['fused']['selected_expert_rows'] for h,b in gate['backends'].items()} if fused else None,
        instrumented_decode=dict(intervals_seconds=intervals,mean_seconds=statistics.mean(intervals),
            median_seconds=statistics.median(intervals),tokens_per_second=45/sum(intervals),
            scope='Full-model generation with tensor capture/comparison and service guards; not a benchmark record'))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--artifacts',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--cpu',default='full-cpu-v7')
    p.add_argument('--gpu',default='full-gpu-v10')
    a=p.parse_args();root=a.artifacts
    cases=read(root/'full-cases.json')
    baseline=Path(__file__).resolve().parent/'inkling_autolab/results/033_large-cases.baseline-reference.json'
    original=read(baseline);saved=read(root/'historical-reference-check.json')
    assert hashlib.sha256(baseline.read_bytes()).hexdigest()==saved['historical_sha256']
    assert cases==[dict(name=c['name'],prompt_ids=c['prompt_ids']) for c in original]
    expected=[c['greedy_ids'][:16] for c in original]
    audit=read(root/'final-audit.json')
    for host in ['alpha','beta','charlie']:
        assert audit[host]['health']==dict(live=200,ready=200)
        assert audit[host]['task_processes_absent'] and audit[host]['firewall_absent']
        assert audit[host]['task_listeners_absent']
        assert audit[host]['free_gib']>=80
    cleanup=read(root/'miner-source-cleanup.json')
    assert cleanup['temporary_rules_remaining']==0 and cleanup['other_firewall_rules_unchanged']
    deployment=read(root/'deployment-summary.json')
    assert deployment['full_model_coverage'] and deployment['replicated_file_checksums_agree']
    assert deployment['unique_source_bytes']==548985140942
    result=dict(all_checks_passed=True,physical_workers=3,twelve_physical_workers_tested=False,
        cpu=inspect_run(root,a.cpu,False,cases,expected,audit),
        gpu=inspect_run(root,a.gpu,True,cases,expected,audit))
    a.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ['cpu','gpu']}))


if __name__=='__main__': main()
