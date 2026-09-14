"""Qualify 16/14/12 compute workers with the frozen two-reader pipeline."""
from pathlib import Path
import hashlib,json,subprocess,time,psutil,msvcrt
ROOT=Path('C:/Users/devcloud/inkling-autolab')
def active():
 return any((p.info['name'] or '').startswith('full-') for p in psutil.process_iter(['name']))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 report=ROOT/'145-prefetch-workers-qualification.json';assert not report.exists()
 binary=ROOT/'bin/full-third-prefetch.exe';wrapper=ROOT/'run-full.ps1'
 expected={binary:'f91e4e0e7002e0aa54a496d2ae24d1f706ed9b38003a568956bd1ae8d647cd03',wrapper:'c18b8446bf4eb7c8fafadebe510bf6de81480c2b0122e524479d15257ce385bc',ROOT/'ptl-profile.ps1':'28d023fce8a3bd27360917a5be4bd55f38bbcb24e4d05904f302f48b63a7741f'}
 for p,h in expected.items():assert digest(p)==h,str(p)
 baseline=json.loads((ROOT/'140-fixture-rank2.json').read_text());routes=json.loads((ROOT/'140-fixture-rank2-routes.json').read_text())
 modes=[]
 with (ROOT/'baseline-queue.lock').open('a+b') as lock:
  lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1);assert not active()
  for threads in [16,14,12]:
   out=ROOT/f'145-fixture-workers-{threads}.json';route=ROOT/f'145-fixture-workers-{threads}-routes.json';log=out.with_suffix('.log')
   assert not any(p.exists() for p in [out,route,log])
   cmd=['powershell','-NoProfile','-File',str(wrapper),'-Model',str(ROOT/'repo/crates/cascadia-engine-sparse-moe/tests/fixtures/inkling_export'),'-Cases',str(ROOT/'fixture-cases.json'),'-AllowFixture','-Binary',binary.name,'-Threads',str(threads),'-AffinityMask','65535','-Reads','0','-Bf16Rows','2','-Int4Rows','4','-MmapEmbed','1','-ReuseBuffers','1','-SkipBulkPrefetch','1','-OwnShared','1','-UncachedReads','1','-PipelineReads','1','-ExpertCacheMiB','1','-PrefillReads','1','-CacheResetHistory','1','-CacheDecayRequests','32','-CacheRecentTies','1','-PredictReads','1','-SecondPredictReads','1','-SecondPredictRank','2','-ThirdPredictReads','0','-EarlyPredictReads','0','-Tokens','8','-Samples','3','-Out',str(out),'-RouteTrace',str(route),'-Log',str(log)]
   run=subprocess.run(cmd,text=True,capture_output=True,timeout=120)
   if run.returncode:raise RuntimeError(run.stdout[-3000:]+run.stderr[-3000:])
   assert f'rayon_threads={threads}' in run.stdout and 'processor_affinity=65535' in run.stdout
   data=json.loads(out.read_text());actual=json.loads(route.read_text())
   assert data['correctness_verified'] and data['output_hash']=='1f7cd0eb14a22662' and len(data['samples'])==3
   assert actual['samples']==routes['samples']
   for key in ['expert_cache','prediction_reads','second_prediction_reads','third_prediction_reads','prediction_read_workers','read_buffer_idle_limit_bytes','uncached_read_bytes','uncached_read_fallbacks','owned_shared_bytes','prefill_read_experts','prefill_uncached_read_bytes','prefill_uncached_read_fallbacks','pipelined_read_layers']:
    assert data[key]==baseline[key],(threads,key,data[key],baseline[key])
   assert [(s['case'],s['repetition'],s['generated_ids']) for s in data['samples']]==[(s['case'],s['repetition'],s['generated_ids']) for s in baseline['samples']]
   modes.append(dict(threads=threads,output_hash=data['output_hash'],all_routes_cache_reads_exact=True,artifacts=[dict(name=p.name,sha256=digest(p)) for p in [out,route,log]]))
  for p,h in expected.items():assert digest(p)==h
  assert not active()
 result=dict(status='qualified',unix=time.time(),binary_sha256=digest(binary),wrapper_sha256=digest(wrapper),modes=modes,full_model_speedup_measured=False)
 with report.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
 return result
if __name__=='__main__':print(json.dumps(main()))
