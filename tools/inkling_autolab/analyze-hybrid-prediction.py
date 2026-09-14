"""Causal forecast of earlier prediction plus current-layer correction."""
import argparse,gzip,hashlib,importlib.util,json
from collections import defaultdict
from pathlib import Path

def read(path):
 raw=path.read_bytes();return json.loads(gzip.decompress(raw) if path.suffix=='.gz' else raw),hashlib.sha256(raw).hexdigest()
def module(name,file):
 spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def analyze(actual,current,early,benchmark):
 validation=module('predictions','analyze-route-prediction.py')
 assert validation.analyze(actual,current,benchmark,1)['prediction_lead_layers']==0
 assert validation.analyze(actual,early,benchmark,1)['prediction_lead_layers']==1
 def mapping(trace):return {(s['case'],s['repetition'],l['layer'],i):row for s in trace['samples'] for l in s['layers'] for i,row in enumerate(l['routed_experts_per_position'])}
 current_map,early_map=mapping(current),mapping(early);groups=defaultdict(lambda:dict(visits=0,actual_misses=0,early_reads=0,early_useful=0,early_unused=0,current_reads=0,current_useful=0,current_unused=0,first_predictions_agree=0))
 def observe(case,rep,layer,position,cohort,entries):
  key=(case,rep,layer,position);ranked=[(i,e) for i,e in enumerate(current_map[key]) if e not in entries];prior=next((e for e in early_map.get(key,[]) if e not in entries),None)
  for ceiling in [0,1,2,3,5]:
   selected=[] if prior is None else [('early',prior)]
   if ranked:
    if ranked[0][1]!=prior:selected.append(('current',ranked[0][1]))
    elif len(ranked)>1 and ranked[1][0]<=ceiling:selected.append(('current',ranked[1][1]))
   assert len(selected)<=2 and len({e for _,e in selected})==len(selected)
   # All selections above use only the declared causal predictions and cache.
   for group in ['all',case]:
    stats=groups[group,ceiling];stats['visits']+=1;stats['actual_misses']+=sum(e not in entries for e in cohort);stats['first_predictions_agree']+=bool(ranked and ranked[0][1]==prior)
    for kind,expert in selected:
     stats[kind+'_reads']+=1;stats[kind+('_useful' if expert in cohort else '_unused')]+=1
 cache=module('recency','analyze-cache-recency.py').replay(actual,8,32,'ceil','recent',observe)
 for k in ['hits','misses','admissions','evictions','recent_tie_admissions']:assert cache[k]==benchmark['expert_cache'][k]
 rows=[]
 for (group,ceiling),stats in sorted(groups.items()):
  reads=stats['early_reads']+stats['current_reads'];useful=stats['early_useful']+stats['current_useful'];unused=stats['early_unused']+stats['current_unused']
  rows.append(dict(group=group,second_rank_ceiling=ceiling,**stats,predicted_reads=reads,useful_reads=useful,unused_reads=unused,precision=useful/reads,miss_coverage=useful/stats['actual_misses'],extra_reads_over_actual_misses=unused/stats['actual_misses']))
 return dict(scope='causal_hybrid_prediction_forecast',selection_uses_actual_routes=False,actual_cache_replay_verified=True,results=rows,full_model_speedup_measured=False,caveats=['No runtime hybrid scheduling has been implemented.','At most two reads are selected for a current layer; a future overlap design would separately bound a next-layer pending request.','When no earlier request exists, select only current first; no second is claimed.','Accuracy, service contention, completion timing and extra buffer costs need native qualification and matched trials.'])
def main():
 p=argparse.ArgumentParser(description=__doc__)
 for n in ['trace','current','early','benchmark','out']:p.add_argument('--'+n,type=Path,required=True)
 a=p.parse_args();assert not a.out.exists();actual,ah=read(a.trace);current,ch=read(a.current);early,eh=read(a.early);benchmark,bh=read(a.benchmark)
 report=analyze(actual,current,early,benchmark);report['source_sha256']=dict(actual=ah,current=ch,early=eh,benchmark=bh)
 with a.out.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
 print(json.dumps([r for r in report['results'] if r['group']=='all'],indent=2))
if __name__=='__main__':main()
