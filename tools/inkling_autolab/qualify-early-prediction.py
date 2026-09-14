"""After113/114 exit, qualify an isolated one-layer-early diagnostic binary."""
import hashlib,json,os,re,subprocess,tarfile,time
from pathlib import Path
import psutil
ROOT=Path('C:/Users/devcloud/inkling-autolab')
STATE=ROOT/'early-prediction-qualification-state.json'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def state(status,**fields):
 tmp=STATE.with_suffix('.tmp');tmp.write_text(json.dumps(dict(status=status,pid=os.getpid(),created_unix=psutil.Process().create_time(),unix=time.time(),**fields),indent=2));tmp.replace(STATE)
def active_full():return [p.pid for p in psutil.process_iter(['name']) if (p.info['name'] or '').startswith('full-')]
def qualify(source):
 def unchanged():
  for name,expected in source['frozen_binaries'].items():assert sha(ROOT/'bin'/name)==expected,name
  assert sha(ROOT/'run-full.ps1')==source['previous_wrapper_sha256']
  assert sha(ROOT/'run-full-early-prediction.ps1')==source['candidate_wrapper_sha256']
 unchanged();candidate=ROOT/'bin/full-early-prediction.exe';assert not candidate.exists() and not active_full()
 for item in source['files']:assert sha(ROOT/'repo'/item['path'])==item['previous_sha256'],item['path']
 assert sha(ROOT/'early-prediction-source.tar')==source['archive_sha256']
 with tarfile.open(ROOT/'early-prediction-source.tar') as archive:
  assert sorted(archive.getnames())==sorted(x['path'] for x in source['files'])
  contents={item['path']:archive.extractfile(item['path']).read() for item in source['files']}
 for item in source['files']:assert hashlib.sha256(contents[item['path']]).hexdigest()==item['candidate_sha256']
 for name,raw in contents.items():(ROOT/'repo'/name).write_bytes(raw)
 log=ROOT/'116-early-prediction-tests.log'
 with log.open('x',encoding='utf-8') as f:
  proc=subprocess.Popen(['cmd.exe','/c',str(ROOT/'test-early-prediction.bat')],stdout=f,stderr=subprocess.STDOUT);state('building_and_testing',launcher_pid=proc.pid,launcher_created_unix=psutil.Process(proc.pid).create_time())
  try:assert proc.wait(timeout=3600)==0,'Native tests/build failed'
  finally:
   if proc.poll() is None:
    subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],check=False);proc.wait()
 counts=[int(n) for n in re.findall(r'test result: ok\. (\d+) passed;',log.read_text())];assert len(counts)==13 and sum(counts)==254,counts
 modes=[]
 for name,lead,predict in [('off',None,0),('current',0,0),('previous',1,0),('prefetch',0,1)]:
  assert not active_full();stem='116-fixture-'+name
  out,log,routes,predicted=[ROOT/(stem+suffix) for suffix in ['.json','.log','-routes.json','-predicted.json']]
  assert not any(p.exists() for p in (out,log,routes,predicted))
  command=['powershell','-NoProfile','-File',str(ROOT/'run-full-early-prediction.ps1'),'-Model',str(ROOT/'repo/crates/cascadia-engine-sparse-moe/tests/fixtures/inkling_export'),'-Cases',str(ROOT/'fixture-cases.json'),'-AllowFixture','-Binary',candidate.name,'-Threads','16','-AffinityMask','65535','-Reads','0','-Bf16Rows','2','-Int4Rows','4','-MmapEmbed','1','-ReuseBuffers','1','-SkipBulkPrefetch','1','-OwnShared','1','-UncachedReads','1','-PipelineReads','1','-ExpertCacheMiB','1','-PrefillReads','1','-CacheResetHistory','1','-CacheDecayRequests','32','-CacheRecentTies','1','-PredictReads',str(predict),'-Tokens','8','-Samples','3','-Out',str(out),'-Log',str(log),'-RouteTrace',str(routes)]
  if lead is not None:command+=['-PredictionTrace',str(predicted),'-PredictionLeadLayers',str(lead)]
  run=subprocess.run(command,text=True,capture_output=True,timeout=120);assert run.returncode==0,run.stdout[-3000:]+run.stderr[-3000:]
  assert f'cache_recent_ties=1 predict_reads={predict} prediction_lead_layers={lead or 0}' in run.stdout
  assert 'processor_affinity=65535' in run.stdout and 'rayon_threads=16' in run.stdout
  result=json.loads(out.read_text());old=json.loads((ROOT/f'109-fixture-recent1-read{predict}.json').read_text());actual=json.loads(routes.read_text());oldactual=json.loads((ROOT/f'109-fixture-recent1-read{predict}-routes.json').read_text())
  assert result['scope']=='fixture_model_decode' and result['correctness_verified'] and result['output_hash']==old['output_hash']=='1f7cd0eb14a22662'
  assert len(result['samples'])==3 and {s['repetition'] for s in result['samples']}=={0,1,2}
  assert all(s['generated_ids']==[28,48,106,84,28,48,106,84] for s in result['samples'])
  for key in ['expert_cache','prediction_reads','uncached_read_bytes','uncached_read_fallbacks','prefill_read_experts','prefill_uncached_read_fallbacks']:assert result[key]==old[key],key
  assert actual['samples']==oldactual['samples'] and actual['output_hash']==result['output_hash']
  artifacts=[out,log,routes]
  if lead is not None:
   prediction=json.loads(predicted.read_text());assert prediction['prediction_lead_layers']==lead and prediction['prefetch_performed'] is bool(predict) and prediction['actual_routing_changed'] is False
   assert prediction['correctness_verified'] and prediction['output_hash']==result['output_hash']
   if lead==0:assert prediction['samples']==json.loads((ROOT/'109-fixture-recent1-read0-predicted.json').read_text())['samples']
   else:
    assert prediction['scope']=='previous_layer_route_prediction_diagnostics'
    assert len(prediction['samples'])==3 and all(s['prefill_positions']==0 and s['decode_positions']==7 and len(s['layers'])==3 and all(len(l['routed_experts_per_position'])==7 for l in s['layers']) for s in prediction['samples'])
   artifacts.append(predicted)
  modes.append(dict(mode=name,lead_layers=lead,predict_reads=predict,output_hash=result['output_hash'],expert_cache=result['expert_cache'],prediction_reads=result['prediction_reads'],artifacts=[dict(name=p.name,sha256=sha(p)) for p in artifacts]))
 unchanged()
 report=dict(status='qualified',source_commit=source['source_commit'],native_tests=sum(counts),binary_sha256=sha(candidate),wrapper_sha256=source['candidate_wrapper_sha256'],modes=modes,full_model_prediction_accuracy_measured=False)
 with (ROOT/'116-early-prediction-qualification.json').open('x') as f:json.dump(report,f,indent=2)
 (ROOT/'run-full.ps1').write_bytes((ROOT/'run-full-early-prediction.ps1').read_bytes());assert sha(ROOT/'run-full.ps1')==source['candidate_wrapper_sha256']
 return report

def main():
 import msvcrt
 with (ROOT/'early-prediction-qualification.lock').open('a+b') as owner:
  owner.seek(0);msvcrt.locking(owner.fileno(),msvcrt.LK_NBLCK,1);assert not STATE.exists()
  try:
   state('waiting_for_heldout_prefetch_comparison');deadline=time.monotonic()+7200
   reports=[ROOT/n for n in ('113-heldout-prefetch-control.json','114-heldout-prefetch-prefetch.json')]
   while not all(p.exists() for p in reports) or active_full():
    if time.monotonic()>deadline:raise TimeoutError('113/114 did not complete')
    time.sleep(15)
   for path in reports:
    report=json.loads(path.read_text());assert report['correctness_verified'] and report['output_hash']=='e396cc533e658e44'
    assert report['scope']=='full_large_model_decode' and len(report['samples'])==3 and all(s['decode_steps']==127 for s in report['samples'])
   with (ROOT/'baseline-queue.lock').open('a+b') as slot:
    slot.seek(0);msvcrt.locking(slot.fileno(),msvcrt.LK_NBLCK,1);assert not active_full();result=qualify(json.loads((ROOT/'early-prediction-source.json').read_text()))
   state('qualified',binary_sha256=result['binary_sha256'],modes=len(result['modes']))
  except BaseException as error:state('failed',error=str(error));raise
if __name__=='__main__':main()
