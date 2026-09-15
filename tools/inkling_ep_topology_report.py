#!/usr/bin/env python3
"""Independently audit full-model GPU output parity across worker topologies.

Input bundles are the unmodified JSON files from inkling_ep_full_run, including
native trace metadata and SHA256 manifests retrieved after each completed run.
A GPU baseline certifies topology parity, not equivalence to BF16 CPU arithmetic.
"""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path

from inkling_ep_full_run import qualification
from inkling_ep_full_report import read


def tensor_evidence(report, cases, tokens):
    errors = iter(report['tensor_errors'])
    count = changed = 0
    for case in cases:
        for step in range(tokens):
            for layer in [*range(66), None]:
                error = next(errors, None)
                expected = dict(case=case['name'], step=step, layer=layer,
                                rows=len(case['prompt_ids']) if step == 0 and layer is not None else 1,
                                width=6144 if layer is not None else 200058)
                assert error is not None and error['tensor'] == expected, (error, expected)
                assert error['passed'] is True
                assert error['different_bits'] == 0
                assert all(math.isfinite(error[k]) and error[k] == 0 for k in ['relative_rms', 'max_abs'])
                count += 1
                changed += error['different_bits']
    assert next(errors, None) is None
    return dict(matched_tensors=count, different_float_bits=changed, maximum_relative_rms=0.)


def inspect(root, label, recording, audit):
    files = read(root/(label+'.json.gz'))
    report_result = files['charlie-'+label+'.json']
    report = report_result['report']
    topology = files.get('topology.json')
    inventory = topology['inventories'] if topology else files['preflight.json']
    per_host = len(inventory)//3
    assert per_host in [1, 4]
    workers = {h if per_host == 1 else h+'-'+str(c): files[f'{h}-{label}-worker-{pi*per_host+c}.json']
               for pi,h in enumerate(['alpha','beta','charlie']) for c in range(per_host)}
    result = qualification(report_result, workers, inventory, True, recording)
    assert result['completed'], result['failures']
    assert len(report['workers']) == len(workers)
    assert report['teacher_forced'] is (not recording)
    assert report['stops_at_eos'] is False
    assert report['relative_rms_tolerance'] == 0
    assert report['correctness_verified'] is (not recording)
    trace = files['trace.json']
    assert trace['model_manifest'] == files['preflight.json']['charlie']['model_manifest']
    assert trace['generated_ids'] == report['generated_ids']
    hashes = files['sha256.json']
    assert set(hashes) >= {'trace.json','tensors.f32','report.json'}
    assert all(len(h) == 64 and all(c in '0123456789abcdef' for c in h) for h in hashes.values())
    # The exact bytes for JSON evidence accompany the parsed copies; large
    # tensor payloads remain in the isolated deployment under the saved hashes.
    for name in ['trace.json','report.json']:
        raw = files['raw_json'][name].encode()
        assert hashlib.sha256(raw).hexdigest() == hashes[name]
        assert json.loads(raw) == (trace if name == 'trace.json' else report)
    all_jobs = [('charlie', report_result), *[(key.split('-')[0], value) for key,value in workers.items()]]
    for host, value in all_jobs:
        status = value['status']
        assert status['minimum_available_gib'] >= 12
        assert status['peak_rss_gib'] <= status['job']['max_rss_gib']
        assert status['protected_before'] == status['protected_after'] == audit[host]['protected']
    assert set(files['cleanup.json']) == set(workers)
    assert all('cleanup_error' not in r for r in files['cleanup.json'].values())
    build = read(root/read(root/'run-builds.json')[label])
    for host in inventory:
        for name in ['inkling_ep_worker.exe','inkling_ep_validate.exe']:
            assert inventory[host]['executable_sha256'][name] == build['executable_sha256']['bin-full/'+name]
        stats = result['backends'][host]['fused']
        assert stats['ordered_replies'] > 0
        assert stats['bf16_output'] is False and stats['f32_output_weighting'] is True
        assert set(stats['graph_k'].values()) == {1}
        assert result['backends'][host]['cpu_f16_reference'] is False
    if topology:
        assert topology['physical_hosts'] == 3 and topology['logical_workers'] == 12
        for host in inventory:
            assert all(s['hardlinks_verified'] and s['view_expert_ids'] for s in inventory[host]['fused_shards'].values())
    return report, trace, result['backends']


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--artifacts', type=Path, required=True)
    p.add_argument('--baseline', required=True)
    p.add_argument('--candidate', required=True, nargs='+')
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    audit = read(a.artifacts/'final-audit.json')
    for host in ['alpha','beta','charlie']:
        proof = audit[host]
        assert proof['health'] == dict(live=200,ready=200)
        assert proof['task_processes_absent'] and proof['firewall_absent'] and proof['task_listeners_absent']
        assert proof['free_gib'] >= 80
    base, bt, bb = inspect(a.artifacts, a.baseline, True, audit)
    cases = read(a.artifacts/'full-cases.json')
    tokens = base['tokens_per_case']
    assert tokens >= 8 and bt['cases'] == cases
    expected_rows = sum(len(c['prompt_ids'])+tokens-1 for c in cases)*64*8
    assert sum(b['fused']['selected_expert_rows'] for b in bb.values()) == expected_rows
    baseline_files = read(a.artifacts/(a.baseline+'.json.gz'))
    counts, seen, text, total_expert_rows = [], set(), {}, 0
    wire_bytes = wire_equivalent = compact_replies = 0
    for label in a.candidate:
        candidate, ct, cb = inspect(a.artifacts, label, False, audit)
        assert candidate['tokens_per_case'] == tokens
        subset = ct['cases']
        indices = [cases.index(case) for case in subset]
        assert all(case['name'] not in seen for case in subset)
        seen.update(case['name'] for case in subset)
        assert candidate['generated_ids'] == [base['generated_ids'][i] for i in indices]
        assert all(len(ids) == tokens for ids in candidate['generated_ids'])
        tensors = [t for t in bt['tensors'] if t['case'] in {c['name'] for c in subset}]
        assert ct['tensors'] == tensors
        numerical = tensor_evidence(candidate,subset,tokens)
        expected = sum(len(c['prompt_ids'])+tokens-1 for c in subset)*64*8
        assert sum(b['fused']['selected_expert_rows'] for b in cb.values()) == expected
        total_expert_rows += expected
        for backend in cb.values():
            assert backend.get('wire_f16_replies',0)>0 and backend.get('wire_f32_replies')==0
            assert backend.get('wire_tensor_bytes',0)*2==backend.get('wire_f32_equivalent_bytes')
            compact_replies += backend['wire_f16_replies']
            wire_bytes += backend['wire_tensor_bytes']
            wire_equivalent += backend['wire_f32_equivalent_bytes']
        if subset != cases:
            proof = read(a.artifacts/(label+'.json.gz'))['reference-slice-provenance.json']
            assert len(subset) == 1 and proof['case'] == subset[0]['name']
            assert proof['source_sha256'] == baseline_files['sha256.json']
            offset, ranges = 0, []
            for tensor in bt['tensors']:
                size = tensor['rows']*tensor['width']*4
                if tensor['case'] == subset[0]['name']:ranges.append([offset,offset+size])
                offset += size
            assert proof['selected_byte_ranges'] == ranges
            assert proof['tensor_values_recomputed'] is False
        text.update(zip([c['name'] for c in subset],candidate['generated_text']))
        counts.append(dict(label=label,candidate_workers=len(cb),generated_tokens=tokens*len(subset),**numerical))
    assert seen == {c['name'] for c in cases} and total_expert_rows == expected_rows
    result = dict(topology_correctness_verified=True,full_model=True,
                  physical_hosts=3,baseline_workers=len(bb),candidate_workers=sorted({c['candidate_workers'] for c in counts}),
                  twelve_physical_hosts_tested=False,cpu_gpu_numerical_parity_established=False,
                  generated_tokens=tokens*len(cases),selected_expert_rows_per_run=expected_rows,
                  matched_tensors=sum(c['matched_tensors'] for c in counts),different_float_bits=0,
                  maximum_relative_rms=0.,wire_tensor_bytes=wire_bytes,wire_f32_equivalent_bytes=wire_equivalent,
                  lossless_compact_replies=compact_replies,wire_scale_header_bytes=compact_replies,baseline=a.baseline,candidates=counts,generated_text=text)
    with a.out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
