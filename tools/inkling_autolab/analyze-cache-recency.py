"""Replay causal cache tie/aging rules; no throughput or future-route oracle."""
import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path


def replay(trace, slots, decay, rounding, ties):
    states = {}
    totals = dict(hits=0, misses=0, admissions=0, evictions=0, recent_tie_admissions=0)
    cases = []
    for sample in trace['samples']:
        before = totals.copy()
        for layer in sample['layers']:
            state = states.setdefault(layer['layer'], dict(entries=[]))
            state.update(freq=[0]*256, last=[0]*256, clock=0)
            routes = layer['routed_experts_per_position'][sample['prefill_positions']:]
            assert len(routes) == sample['decode_positions']
            for cohort in routes:
                missing = []
                # Runtime observes the complete current cohort before admission.
                for expert in cohort:
                    state['clock'] += 1
                    if state['clock'] % decay == 0:
                        state['freq'] = [(x + (rounding == 'ceil')) // 2 for x in state['freq']]
                    state['freq'][expert] += 1
                    state['last'][expert] = state['clock']
                    if expert in state['entries']:
                        totals['hits'] += 1
                    else:
                        totals['misses'] += 1
                        missing.append(expert)
                for expert in missing:
                    entries = state['entries']
                    assert expert not in entries
                    if len(entries) == slots:
                        victim = min(range(slots), key=lambda i: (state['freq'][entries[i]], state['last'][entries[i]]))
                        frequency, old_frequency = state['freq'][expert], state['freq'][entries[victim]]
                        if frequency < old_frequency or (frequency == old_frequency and (ties == 'strict' or state['last'][expert] <= state['last'][entries[victim]])):
                            continue
                        entries[victim] = entries[-1]
                        entries.pop()
                        totals['evictions'] += 1
                        totals['recent_tie_admissions'] += frequency == old_frequency
                    entries.append(expert)
                    totals['admissions'] += 1
        cases.append(dict(case=sample['case'], repetition=sample['repetition'], **{k:totals[k]-before[k] for k in totals}))
    return dict(slots=slots, decay=decay, rounding=rounding, ties=ties, **totals, cases=cases)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--trace', type=Path, required=True)
    p.add_argument('--benchmark', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a=p.parse_args()
    if a.out.exists(): p.error('refusing to overwrite report')
    raw=a.trace.read_bytes();trace=json.loads(gzip.decompress(raw) if a.trace.suffix=='.gz' else raw)
    benchmark=json.loads(a.benchmark.read_text())
    assert trace['full_model'] and trace['correctness_verified'] and trace['output_hash']==benchmark['output_hash']
    spec=importlib.util.spec_from_file_location('admission', Path(__file__).with_name('analyze-cache-admission.py'))
    base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
    control=replay(trace,8,32,'ceil','strict');reference=base.replay(trace,8,True,32)
    for key in ('hits','misses','admissions','evictions'):
        assert control[key]==reference[key]==benchmark['expert_cache'][key],key
    assert [{k:v for k,v in c.items() if k!='recent_tie_admissions'} for c in control['cases']]==reference['cases']
    results=[]
    for decay in (8,16,32,64,128):
        for rounding in ('ceil','floor'):
            for ties in ('strict','recent'):
                result=replay(trace,8,decay,rounding,ties)
                result['read_reduction_vs_control']=1-result['misses']/control['misses']
                result['case_read_reductions']=[dict(case=x['case'],repetition=x['repetition'],read_reduction=1-x['misses']/c['misses']) for x,c in zip(result['cases'],control['cases'])]
                results.append(result)
    report=dict(scope='causal_cache_aging_ties_simulation_not_throughput',source_sha256=hashlib.sha256(raw).hexdigest(),control_matches_actual_counters=True,results=results,caveats=['Only current and past decode cohorts enter decisions. Prefill routes do not enter the cache.', 'Retains bytes across requests but resets policy history, matching current runtime.', 'Different admission churn can affect compute and allocation cost; any candidate needs native qualification and full trials.'])
    with a.out.open('x') as f:json.dump(report,f,indent=2)
    print(json.dumps([{k:v for k,v in r.items() if k not in ('cases','case_read_reductions')} for r in sorted(results,key=lambda r:r['misses'])],indent=2))


if __name__=='__main__':main()
