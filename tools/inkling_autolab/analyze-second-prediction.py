"""Causal replay of a second prefetch limited by its predicted expert rank."""
import argparse
from collections import defaultdict
import gzip,hashlib,importlib.util,json
from pathlib import Path

def read(path):
 raw=path.read_bytes();return json.loads(gzip.decompress(raw) if path.suffix=='.gz' else raw),hashlib.sha256(raw).hexdigest()
def analyze(actual,predictions,benchmark,ceilings):
 spec=importlib.util.spec_from_file_location('prediction',Path(__file__).with_name('analyze-route-prediction.py'));validation=importlib.util.module_from_spec(spec);spec.loader.exec_module(validation)
 validated=validation.analyze(actual,predictions,benchmark,1);assert validated['prediction_lead_layers']==0
 spec=importlib.util.spec_from_file_location('recency',Path(__file__).with_name('analyze-cache-recency.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 mapping={(s['case'],s['repetition'],l['layer'],i):row for s in predictions['samples'] for l in s['layers'] for i,row in enumerate(l['routed_experts_per_position'])}
 groups=defaultdict(lambda:dict(visits=0,actual_misses=0,first_reads=0,first_useful=0,first_unused=0,second_reads=0,second_useful=0,second_unused=0))
 def observe(case,rep,layer,position,cohort,entries):
  ranked=[(rank,e) for rank,e in enumerate(mapping[case,rep,layer,position]) if e not in entries]
  for ceiling in ceilings:
   chosen=ranked[:1]
   if len(ranked)>1 and ranked[1][0]<=ceiling:chosen.append(ranked[1])
   # Selection above uses only the prediction and preceding cache membership.
   # Actual routing below scores this frozen choice; it never selects a read.
   for group in ['all',case]:
    stats=groups[group,ceiling];stats['visits']+=1;stats['actual_misses']+=sum(e not in entries for e in cohort)
    for index,(_,expert) in enumerate(chosen):
     prefix='first' if index==0 else 'second';stats[prefix+'_reads']+=1;stats[prefix+('_useful' if expert in cohort else '_unused')]+=1
 cache=module.replay(actual,8,32,'ceil','recent',observe)
 for k in ['hits','misses','admissions','evictions','recent_tie_admissions']:assert cache[k]==benchmark['expert_cache'][k]
 rows=[]
 for (group,ceiling),stats in sorted(groups.items()):
  predicted=stats['first_reads']+stats['second_reads'];useful=stats['first_useful']+stats['second_useful'];unused=stats['first_unused']+stats['second_unused']
  rows.append(dict(group=group,second_rank_ceiling_zero_based=ceiling,**stats,predicted_reads=predicted,useful_reads=useful,unused_reads=unused,precision=useful/predicted if predicted else None,second_precision=stats['second_useful']/stats['second_reads'] if stats['second_reads'] else None,miss_coverage=useful/stats['actual_misses'],extra_reads_over_actual_misses=unused/stats['actual_misses'],additional_read_fraction_over_first_only=stats['second_unused']/(stats['actual_misses']+stats['first_unused'])))
 return dict(scope='causal_second_prediction_rank_analysis',selection_uses_actual_routes=False,actual_cache_replay_verified=True,results=rows,full_model_speedup_measured=False,caveats=['Rank is zero based in the predicted gate, before actual routing. First uncached prediction is unchanged.','Forecasts do not measure overlap, contention, host-memory effects or worker overhead.','A runtime experiment must verify all read counts, actual routes and output tokens.'])
def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ['trace','predictions','benchmark','out']:p.add_argument('--'+name,type=Path,required=True)
 p.add_argument('--rank-ceiling',type=int,choices=range(6));a=p.parse_args();assert not a.out.exists()
 actual,ah=read(a.trace);prediction,ph=read(a.predictions);benchmark,bh=read(a.benchmark)
 result=analyze(actual,prediction,benchmark,[a.rank_ceiling] if a.rank_ceiling is not None else range(6));result['source_sha256']=dict(actual=ah,predictions=ph,benchmark=bh)
 with a.out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
 print(json.dumps([r for r in result['results'] if r['group']=='all'],indent=2))
if __name__=='__main__':main()
