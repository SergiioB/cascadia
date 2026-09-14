"""Replay causal cache admission against saved routes; this is not a speed result.

Keep weight entries across requests, with optional admission-history reset. Only
past and current decode routes enter decisions. Prefill never admits weights.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path


def replay(trace, slots, reset_history):
    states = {}
    totals = dict(hits=0, misses=0, admissions=0, evictions=0)
    cases = []
    for sample in trace['samples']:
        before = totals.copy()
        for layer in sample['layers']:
            state = states.setdefault(layer['layer'], dict(freq=[0]*256, last=[0]*256, clock=0, entries=[]))
            if reset_history:
                state.update(freq=[0]*256, last=[0]*256, clock=0)
            routes = layer['routed_experts_per_position'][sample['prefill_positions']:]
            assert len(routes) == sample['decode_positions']
            for cohort in routes:
                missing = []
                for expert in cohort:
                    state['clock'] += 1
                    if state['clock'] % 4096 == 0:
                        state['freq'] = [(x+1)//2 for x in state['freq']]
                    state['freq'][expert] += 1
                    state['last'][expert] = state['clock']
                    if expert in state['entries']:
                        totals['hits'] += 1
                    else:
                        totals['misses'] += 1
                        missing.append(expert)
                # Runtime releases all read leases before gate-order admission.
                for expert in missing:
                    if expert in state['entries']:
                        continue
                    if len(state['entries']) == slots:
                        victim = min(range(slots), key=lambda i: (state['freq'][state['entries'][i]], state['last'][state['entries'][i]]))
                        if state['freq'][expert] <= state['freq'][state['entries'][victim]]:
                            continue
                        state['entries'][victim] = state['entries'][-1]
                        state['entries'].pop()
                        totals['evictions'] += 1
                    state['entries'].append(expert)
                    totals['admissions'] += 1
        cases.append(dict(case=sample['case'], repetition=sample['repetition'], **{k: totals[k]-before[k] for k in totals}))
    return dict(slots_per_layer=slots, reset_history=reset_history, **totals, cases=cases)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--trace',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if a.out.exists():p.error('refusing to overwrite analysis')
    raw=a.trace.read_bytes();data=gzip.decompress(raw) if a.trace.suffix=='.gz' else raw
    trace=json.loads(data)
    assert trace['full_model'] and trace['correctness_verified']
    assert trace['manifest']['routed_experts']==256
    result=dict(scope='causal_admission_simulation_not_measured_throughput',source_sha256=hashlib.sha256(raw).hexdigest(),output_hash=trace['output_hash'],results=[replay(trace,slots,reset) for slots in (2,4,8) for reset in (False,True)])
    a.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__=='__main__':main()
