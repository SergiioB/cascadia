"""Score causal pre-attention predictions against actual routes/cache state."""
import argparse
from collections import defaultdict
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path


def read(path):
    raw=path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix=='.gz' else raw),hashlib.sha256(raw).hexdigest()


def analyze(actual, predictions, benchmark, recent):
    assert actual['correctness_verified'] and predictions['correctness_verified'] and benchmark['correctness_verified']
    assert actual['output_hash']==predictions['output_hash']==benchmark['output_hash']
    scopes = {
        'pre_attention_route_prediction_diagnostics': (0, 'current_layer_residual_before_attention_with_existing_mlp_norm_and_router'),
        'previous_layer_route_prediction_diagnostics': (1, 'previous_layer_residual_before_attention_with_target_layer_mlp_norm_and_router'),
    }
    assert predictions['scope'] in scopes
    lead, source = scopes[predictions['scope']]
    assert predictions.get('prediction_lead_layers', 0) == lead
    assert predictions['prediction_input'] == source
    assert predictions['actual_routing_changed'] is False and predictions['prefetch_performed'] is False
    spec=importlib.util.spec_from_file_location('recency',Path(__file__).with_name('analyze-cache-recency.py'))
    replay=importlib.util.module_from_spec(spec);spec.loader.exec_module(replay)
    mapping={}
    for sample in predictions['samples']:
        assert sample['prefill_positions']==0
        for layer in sample['layers']:
            rows=layer['routed_experts_per_position'];assert len(rows)==sample['decode_positions']
            for position,cohort in enumerate(rows):
                key=(sample['case'],sample['repetition'],layer['layer'],position)
                assert key not in mapping and len(cohort)==len(set(cohort))
                mapping[key]=cohort
    groups=defaultdict(lambda:dict(visits=0,actual_misses=0,predicted_reads=0,useful_reads=0,extra_reads=0))
    visited=set()
    def observe(case,rep,layer,position,cohort,entries):
        if lead == 1 and layer == 0:
            return  # No predecessor exists; no prediction is claimed for layer0.
        key=(case,rep,layer,position);assert key not in visited;visited.add(key)
        predicted=mapping[key]
        assert len(predicted)==len(cohort) and all(0<=x<actual['manifest']['routed_experts'] for x in predicted)
        # Choose only from predicted routes and current cache contents, before
        # evaluating precision against the actual upcoming selection.
        uncached_prediction=[e for e in predicted if e not in entries]
        actual_missing=sum(e not in entries for e in cohort)
        for limit in range(1,7):
            chosen=uncached_prediction[:limit]
            useful=sum(e in cohort for e in chosen)
            for group in ('all',case):
                stats=groups[(group,limit)];stats['visits']+=1;stats['actual_misses']+=actual_missing
                stats['predicted_reads']+=len(chosen);stats['useful_reads']+=useful;stats['extra_reads']+=len(chosen)-useful
    control=replay.replay(actual,8,32,'ceil','recent' if recent else 'strict',observe)
    assert visited==set(mapping), 'Prediction grid differs from actual decode grid'
    for key in ('hits','misses','admissions','evictions','recent_tie_admissions'):
        assert control[key]==benchmark['expert_cache'][key],key
    results=[]
    for (group,limit),stats in sorted(groups.items()):
        results.append(dict(group=group,prediction_limit=limit,**stats,
                            precision=stats['useful_reads']/stats['predicted_reads'] if stats['predicted_reads'] else None,
                            actual_miss_coverage=stats['useful_reads']/stats['actual_misses'] if stats['actual_misses'] else None,
                            read_amplification=1+stats['extra_reads']/stats['actual_misses'] if stats['actual_misses'] else None))
    return dict(scope='causal_prediction_precision_not_measured_prefetch_speedup',prediction_lead_layers=lead,prediction_input=source,visits=len(visited),cache_control_matches_actual=True,results=results,caveats=['No expert prefetch was performed; misses and cache state are the unmodified runtime behavior.', 'Predictions use the declared residual input and target layer MLP norm/router; no future route enters prediction.', 'Potential latency overlap, I/O contention, prediction overhead and unused-read cost require a separate runtime experiment.'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('trace','predictions','benchmark','out'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--recent-ties',type=int,choices=(0,1),required=True)
    a=p.parse_args()
    if a.out.exists():p.error('refusing to overwrite report')
    actual,ah=read(a.trace);predictions,ph=read(a.predictions);benchmark,bh=read(a.benchmark)
    result=analyze(actual,predictions,benchmark,a.recent_ties)
    result['source_sha256']=dict(actual=ah,predictions=ph,benchmark=bh)
    with a.out.open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps([r for r in result['results'] if r['group']=='all'],indent=2))


if __name__=='__main__':main()
