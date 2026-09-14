"""Forecast a third read only when the three leading predictions are uncached."""
import argparse,gzip,hashlib,importlib.util,json
from collections import defaultdict
from pathlib import Path

def read(p):
 raw=p.read_bytes();return json.loads(gzip.decompress(raw) if p.suffix=='.gz' else raw),hashlib.sha256(raw).hexdigest()
def module(name,path):
 s=importlib.util.spec_from_file_location(name,Path(__file__).with_name(path));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def analyze(actual,predictions,benchmark):
 assert module('validation','analyze-route-prediction.py').analyze(actual,predictions,benchmark,1)['prediction_lead_layers']==0
 mapping={(s['case'],s['repetition'],l['layer'],i):row for s in predictions['samples'] for l in s['layers'] for i,row in enumerate(l['routed_experts_per_position'])}
 groups=defaultdict(lambda:dict(visits=0,actual_misses=0,first_reads=0,first_useful=0,first_unused=0,second_reads=0,second_useful=0,second_unused=0,third_reads=0,third_useful=0,third_unused=0))
 def observe(case,rep,layer,position,cohort,entries):
  ranked=[(i,e) for i,e in enumerate(mapping[case,rep,layer,position]) if e not in entries]
  for second_ceiling in [1,2,3,5]:
   selected=[('first',e) for _,e in ranked[:1]]
   if len(ranked)>1 and ranked[1][0]<=second_ceiling:selected.append(('second',ranked[1][1]))
   if len(ranked)>2 and ranked[2][0]<=2:
    assert len(selected)==2;selected.append(('third',ranked[2][1]))
   for group in ['all',case]:
    stats=groups[group,second_ceiling];stats['visits']+=1;stats['actual_misses']+=sum(e not in entries for e in cohort)
    for kind,expert in selected:
     stats[kind+'_reads']+=1;stats[kind+('_useful' if expert in cohort else '_unused')]+=1
 cache=module('cache','analyze-cache-recency.py').replay(actual,8,32,'ceil','recent',observe)
 for k in ['hits','misses','admissions','evictions','recent_tie_admissions']:assert cache[k]==benchmark['expert_cache'][k]
 rows=[]
 for (group,ceiling),stats in sorted(groups.items()):
  previous_useful=stats['first_useful']+stats['second_useful'];previous_unused=stats['first_unused']+stats['second_unused'];reads=sum(stats[k+'_reads'] for k in ['first','second','third']);useful=previous_useful+stats['third_useful'];unused=previous_unused+stats['third_unused'];extra=stats['third_unused']/(stats['actual_misses']+previous_unused);coverage_gain=stats['third_useful']/stats['actual_misses']
  rows.append(dict(group=group,second_rank_ceiling=ceiling,third_rank_ceiling=2,**stats,predicted_reads=reads,useful_reads=useful,unused_reads=unused,precision=useful/reads,miss_coverage=useful/stats['actual_misses'],additional_miss_coverage=coverage_gain,additional_reads_over_two=extra,forecast_budget_passes=extra<=.01 and coverage_gain>=.03))
 return dict(scope='causal_selective_third_read_forecast',selection_uses_actual_routes=False,actual_cache_replay_verified=True,full_model_speedup_measured=False,results=rows,caveats=['Third rank ceiling2 fixed before replay.','Only replay; worker overhead, memory bounds and contention are not measured.','Runtime must be separately qualified and preserve exact outputs/routes/cache admission.'])
def main():
 p=argparse.ArgumentParser(description=__doc__)
 for n in ['trace','predictions','benchmark','out']:p.add_argument('--'+n,type=Path,required=True)
 a=p.parse_args();assert not a.out.exists();actual,ah=read(a.trace);prediction,ph=read(a.predictions);benchmark,bh=read(a.benchmark);report=analyze(actual,prediction,benchmark);report['source_sha256']=dict(actual=ah,predictions=ph,benchmark=bh)
 with a.out.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
 print(json.dumps([x for x in report['results'] if x['group']=='all' and x['second_rank_ceiling']==2],indent=2))
if __name__=='__main__':main()
