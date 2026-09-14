"""Causal global-cache replay with the same total bytes as per-layer caches.

This measures route reuse only. It does not implement or benchmark a global
runtime cache. No future expert selection enters an admission decision.
"""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path


def replay(trace, slots_per_layer):
    layer_ids = [layer['layer'] for layer in trace['samples'][0]['layers']]
    capacity = slots_per_layer * len(layer_ids)
    frequency, last, entries = {}, {}, []
    totals = dict(hits=0, misses=0, admissions=0, evictions=0)
    cases = []
    for sample in trace['samples']:
        frequency.clear(); last.clear(); clock=0
        before=totals.copy()
        assert [layer['layer'] for layer in sample['layers']]==layer_ids
        for pos in range(sample['prefill_positions'], sample['prefill_positions']+sample['decode_positions']):
            for layer in sample['layers']:
                missing=[]
                for expert in layer['routed_experts_per_position'][pos]:
                    key=(layer['layer'],expert);clock+=1
                    frequency[key]=frequency.get(key,0)+1;last[key]=clock
                    if key in entries:totals['hits']+=1
                    else:totals['misses']+=1;missing.append(key)
                for key in missing:
                    if key in entries:continue
                    if len(entries)==capacity:
                        victim=min(range(capacity),key=lambda i:(frequency.get(entries[i],0),last.get(entries[i],0)))
                        if frequency[key]<=frequency.get(entries[victim],0):continue
                        entries[victim]=entries[-1];entries.pop();totals['evictions']+=1
                    entries.append(key);totals['admissions']+=1
        cases.append(dict(case=sample['case'],**{k:totals[k]-before[k] for k in totals}))
    return dict(scope='global_lfu_request_history_reset_simulation',equivalent_slots_per_layer=slots_per_layer,total_capacity_slots=capacity,**totals,cases=cases,final_slots_by_layer=dict(sorted(Counter(k[0] for k in entries).items())))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--trace',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.out.exists():p.error('refusing to overwrite analysis')
    raw=a.trace.read_bytes();trace=json.loads(gzip.decompress(raw) if a.trace.suffix=='.gz' else raw)
    assert trace['full_model'] and trace['correctness_verified']
    result=dict(scope='causal_global_cache_simulation_not_measured_speed',trace_sha256=hashlib.sha256(raw).hexdigest(),output_hash=trace['output_hash'],reset_history=True,frequency_decay='No decay within a request, matching4096 per-layer interval for these short continuations',results=[replay(trace,n) for n in (2,4,8)])
    a.out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
