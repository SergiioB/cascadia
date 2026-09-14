"""Qualify two bounded concurrent predicted reads with a frozen rank ceiling."""
import hashlib,json,os,re,subprocess,tarfile,time
from pathlib import Path
import psutil
ROOT=Path('C:/Users/devcloud/inkling-autolab')
STATE=ROOT/'second-prefetch-qualification-state.json'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def state(status,**fields):
 tmp=STATE.with_suffix('.tmp');tmp.write_text(json.dumps(dict(status=status,pid=os.getpid(),created_unix=psutil.Process().create_time(),unix=time.time(),**fields),indent=2));tmp.replace(STATE)
def active_full():return [p.pid for p in psutil.process_iter(['name']) if (p.info['name'] or '').startswith('full-')]
def qualify(source):
 def unchanged():
  for name,expected in source['frozen_binaries'].items():assert sha(ROOT/'bin'/name)==expected,name
  assert sha(ROOT/'run-full.ps1')==source['previous_wrapper_sha256']
  assert sha(ROOT/'run-full-second-prefetch.ps1')==source['candidate_wrapper_sha256']
 unchanged();candidate=ROOT/'bin/full-second-prefetch.exe';assert not candidate.exists() and not active_full()
 for item in source['files']:assert sha(ROOT/'repo'/item['path'])==item['previous_sha256'],item['path']
 assert sha(ROOT/'second-prefetch-source.tar')==source['archive_sha256']
 with tarfile.open(ROOT/'second-prefetch-source.tar') as archive:
  assert sorted(archive.getnames())==sorted(x['path'] for x in source['files'])
  contents={item['path']:archive.extractfile(item['path']).read() for item in source['files']}
 for item in source['files']:assert hashlib.sha256(contents[item['path']]).hexdigest()==item['candidate_sha256']
 for name,raw in contents.items():(ROOT/'repo'/name).write_bytes(raw)
 log=ROOT/'126-second-prefetch-tests.log'
 with log.open('x',encoding='utf-8') as f:
  proc=subprocess.Popen(['cmd.exe','/c',str(ROOT/'test-second-prefetch.bat')],stdout=f,stderr=subprocess.STDOUT);state('building_and_testing',launcher_pid=proc.pid,launcher_created_unix=psutil.Process(proc.pid).create_time())
  try:assert proc.wait(timeout=3600)==0,'Native tests/build failed'
  finally:
   if proc.poll() is None:
    subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],check=False);proc.wait()
 counts=[int(n) for n in re.findall(r'test result: ok\. (\d+) passed;',log.read_text())];assert len(counts)==13 and sum(counts)==257,counts
 modes=[]
 for name,lead,predict,early,second in [('off',None,0,0,0),('current',0,1,0,0),('second',0,1,0,1),('early',1,1,1,0),('previous',1,0,0,0)]:
  assert not active_full();stem='126-fixture-'+name
  out,log,routes,predicted=[ROOT/(stem+suffix) for suffix in ['.json','.log','-routes.json','-predicted.json']]
  assert not any(p.exists() for p in (out,log,routes,predicted))
  command=['powershell','-NoProfile','-File',str(ROOT/'run-full-second-prefetch.ps1'),'-Model',str(ROOT/'repo/crates/cascadia-engine-sparse-moe/tests/fixtures/inkling_export'),'-Cases',str(ROOT/'fixture-cases.json'),'-AllowFixture','-Binary',candidate.name,'-Threads','16','-AffinityMask','65535','-Reads','0','-Bf16Rows','2','-Int4Rows','4','-MmapEmbed','1','-ReuseBuffers','1','-SkipBulkPrefetch','1','-OwnShared','1','-UncachedReads','1','-PipelineReads','1','-ExpertCacheMiB','1','-PrefillReads','1','-CacheResetHistory','1','-CacheDecayRequests','32','-CacheRecentTies','1','-PredictReads',str(predict),'-EarlyPredictReads',str(early),'-SecondPredictReads',str(second),'-Tokens','8','-Samples','3','-Out',str(out),'-Log',str(log),'-RouteTrace',str(routes)]
  if lead is not None:command+=['-PredictionTrace',str(predicted),'-PredictionLeadLayers',str(lead)]
  run=subprocess.run(command,text=True,capture_output=True,timeout=126);assert run.returncode==0,run.stdout[-3000:]+run.stderr[-3000:]
  assert f'cache_recent_ties=1 predict_reads={predict} prediction_lead_layers={lead or 0} early_predict_reads={early} second_predict_reads={second}' in run.stdout
  assert 'processor_affinity=65535' in run.stdout and 'rayon_threads=16' in run.stdout
  result=json.loads(out.read_text());old=json.loads((ROOT/f'109-fixture-recent1-read{predict}.json').read_text());actual=json.loads(routes.read_text());oldactual=json.loads((ROOT/f'109-fixture-recent1-read{predict}-routes.json').read_text())
  assert result['scope']=='fixture_model_decode' and result['correctness_verified'] and result['output_hash']==old['output_hash']=='1f7cd0eb14a22662'
  assert len(result['samples'])==3 and {s['repetition'] for s in result['samples']}=={0,1,2}
  assert all(s['generated_ids']==[28,48,106,84,28,48,106,84] for s in result['samples'])
  for key in ['expert_cache','prefill_read_experts','prefill_uncached_read_fallbacks']:assert result[key]==old[key],key
  expected=dict(scheduled=16,successful=16,useful=10,unused=6,read_failures=0,worker_failures=0,dispatch_failures=0,useful_bytes=34560,unused_bytes=20736) if early else old['prediction_reads']
  if second:expected=dict(scheduled=19,successful=19,useful=16,unused=3,read_failures=0,worker_failures=0,dispatch_failures=0,useful_bytes=55296,unused_bytes=10368)
  second_expected=dict(scheduled=6,successful=6,useful=5,unused=1,read_failures=0,worker_failures=0,dispatch_failures=0,useful_bytes=17280,unused_bytes=3456) if second else {k:0 for k in expected}
  assert result['second_prediction_reads']==second_expected and result['second_prediction_reads_effective'] is bool(second)
  assert result['prediction_read_workers']==(2 if second else int(bool(predict)))
  assert result['prediction_reads']==expected and result['early_prediction_reads_effective'] is bool(early)
  assert result['uncached_read_bytes']==0 and result['uncached_read_fallbacks']==(22 if early else 19 if second else old['uncached_read_fallbacks'])
  assert actual['samples']==oldactual['samples'] and actual['output_hash']==result['output_hash']
  artifacts=[out,log,routes]
  if lead is not None:
   prediction=json.loads(predicted.read_text());assert prediction['prediction_lead_layers']==lead and prediction['prefetch_performed'] is bool(predict) and prediction['actual_routing_changed'] is False
   assert prediction['correctness_verified'] and prediction['output_hash']==result['output_hash']
   if lead==0:assert prediction['samples']==json.loads((ROOT/'109-fixture-recent1-read0-predicted.json').read_text())['samples']
   else:
    assert prediction['scope']=='previous_layer_route_prediction_diagnostics'
    assert prediction['samples']==json.loads((ROOT/'116-fixture-previous-predicted.json').read_text())['samples']
    assert len(prediction['samples'])==3 and all(s['prefill_positions']==0 and s['decode_positions']==7 and len(s['layers'])==3 and all(len(l['routed_experts_per_position'])==7 for l in s['layers']) for s in prediction['samples'])
   artifacts.append(predicted)
  modes.append(dict(mode=name,lead_layers=lead,predict_reads=predict,early_predict_reads=early,second_predict_reads=second,second_prediction_reads=result['second_prediction_reads'],prediction_read_workers=result['prediction_read_workers'],output_hash=result['output_hash'],expert_cache=result['expert_cache'],prediction_reads=result['prediction_reads'],artifacts=[dict(name=p.name,sha256=sha(p)) for p in artifacts]))
 for early,predict,second,message in [(1,0,0,'Early prefetch requires'),(0,0,1,'Selective second prefetch requires'),(1,1,1,'Selective second prefetch requires')]:
  invalid=command.copy()
  for flag,value in [('-EarlyPredictReads',early),('-PredictReads',predict),('-SecondPredictReads',second)]:invalid[invalid.index(flag)+1]=str(value)
  rejected=subprocess.run(invalid,text=True,capture_output=True,timeout=30);assert rejected.returncode!=0 and message in rejected.stdout+rejected.stderr and not active_full()
 unchanged()
 report=dict(status='qualified',source_commit=source['source_commit'],native_tests=sum(counts),binary_sha256=sha(candidate),wrapper_sha256=source['candidate_wrapper_sha256'],modes=modes,full_model_prediction_accuracy_measured=False,full_model_speedup_measured=False,invalid_dependencies_rejected=3)
 with (ROOT/'126-second-prefetch-qualification.json').open('x') as f:json.dump(report,f,indent=2)
 (ROOT/'run-full.ps1').write_bytes((ROOT/'run-full-second-prefetch.ps1').read_bytes());assert sha(ROOT/'run-full.ps1')==source['candidate_wrapper_sha256']
 return report

def main():
 import msvcrt
 with (ROOT/'second-prefetch-qualification.lock').open('a+b') as owner:
  owner.seek(0);msvcrt.locking(owner.fileno(),msvcrt.LK_NBLCK,1);assert not STATE.exists()
  try:
   state('starting');assert not active_full()
   with (ROOT/'baseline-queue.lock').open('a+b') as slot:
    slot.seek(0);msvcrt.locking(slot.fileno(),msvcrt.LK_NBLCK,1);assert not active_full();result=qualify(json.loads((ROOT/'second-prefetch-source.json').read_text()))
   state('qualified',binary_sha256=result['binary_sha256'],modes=len(result['modes']))
  except BaseException as error:state('failed',error=str(error));raise
if __name__=='__main__':main()
