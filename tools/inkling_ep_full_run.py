#!/usr/bin/env python3
"""Guarded full-model correctness run on the three authorized LAN NUCs.

Charlie holds the decoder and reference. All workers must have their complete
shards before launch. The temporary listener admits Charlie only. Existing
services are never restarted; cleanup verifies our process identity.
"""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import re
import time

from inkling_ep_lan_control import HOSTS, ROOT, PYTHON, remote

PORT = 29475
RULE = 'InklingEP-Full-20260915'


def qualification(driver, workers, inventories, fused):
    """Fail closed on missing numerical, backend, coverage or service evidence."""
    failures, backends = [], {}
    if not inventories or set(workers) != set(inventories):
        failures.append('worker evidence does not match the deployment')
    report = (driver or {}).get('report') or {}
    if not all(report.get(k) is True for k in ['full_model', 'reference_comparison', 'greedy_match', 'numerical_match', 'correctness_verified']):
        failures.append('full-model output comparison did not pass')
    for host, result in [('driver', driver), *workers.items()]:
        status = (result or {}).get('status') or {}
        if not result or result.get('returncode') != 0 or status.get('returncode') != 0 or status.get('stop_reason') or status.get('protected_processes_unchanged') is not True:
            failures.append(host+': job failed or service preservation was not verified')
        if host == 'driver' or not result:
            continue
        lines = [line.removeprefix('backend_final=') for line in result.get('log', '').splitlines() if line.startswith('backend_final=')]
        if len(lines) != 1:
            failures.append(host+': missing final backend evidence')
            continue
        backend = backends[host] = json.loads(lines[0])
        if fused:
            stats = backend.get('fused') or {}
            expected = {str(n) for n in inventories[host]['owned_layers']}
            profiles = stats.get('fusion_profiles') or {}
            if (backend.get('cpu_calls') != 0 or backend.get('ov_fallbacks') != 0
                    or stats.get('errors') != 0 or stats.get('fused_required') is not True
                    or stats.get('streaming') is not True or stats.get('calls', 0) <= 0
                    or not str(stats.get('device', '')).startswith('GPU')
                    or set(profiles) != expected
                    or any('MOECompressed' not in value for value in profiles.values())):
                failures.append(host+': incomplete GPU fusion/coverage or fallback detected')
        elif backend.get('cpu_calls', 0) <= 0 or backend.get('fused') is not None:
            failures.append(host+': CPU reference backend evidence is invalid')
    return dict(completed=not failures, failures=failures, backends=backends)


def run_job(host, job, out):
    script = '''from pathlib import Path
import json,subprocess
root=Path(ROOT);job=JOB
path=root/(job['label']+'.job.json')
with path.open('x') as f: json.dump(job,f)
r=subprocess.run([PYTHON,str(root/'inkling_ep_guard.py'),'--root',str(root),'--job',str(path)],capture_output=True,text=True,timeout=job['seconds']+40)
status=root/(job['label']+'.status.json');log=root/(job['label']+'.log')
report=root/job['label']/'report.json'
print(json.dumps(dict(returncode=r.returncode,guard_stdout=r.stdout,guard_stderr=r.stderr,
 status=json.loads(status.read_text()) if status.exists() else None,
 log=log.read_text() if log.exists() else '',report=json.loads(report.read_text()) if report.exists() else None)))
'''.replace('ROOT', repr(ROOT)).replace('JOB', repr(job)).replace('PYTHON', repr(PYTHON))
    result = json.loads(remote(host, script, job['seconds']+80))
    (out/(host+'-'+job['label']+'.json')).write_text(json.dumps(result, indent=2)+'\n')
    return result


def firewall(host, add):
    if add:
        script = f"""$ErrorActionPreference='Stop'
if (Get-NetFirewallRule -Name '{RULE}' -ErrorAction SilentlyContinue) {{ throw 'Task rule already exists' }}
New-NetFirewallRule -Name '{RULE}' -DisplayName '{RULE}' -Direction Inbound -Action Allow -Profile Any -Protocol TCP -LocalPort {PORT} -RemoteAddress {HOSTS['charlie']} -Program '{ROOT}/bin-full/inkling_ep_worker.exe' | Out-Null
"""
    else:
        script = f"Get-NetFirewallRule -Name '{RULE}' -ErrorAction SilentlyContinue | Remove-NetFirewallRule"
    return remote(host, "import subprocess; subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',"+repr(script)+"],check=True); print('ok')", 40)


def cleanup_worker(host, job):
    script = '''from pathlib import Path
import json,psutil
root=Path(ROOT);path=root/(LABEL+'.status.json');stopped=False
if path.exists():
 status=json.loads(path.read_text())
 if status.get('state')=='running':
  try:
   p=psutil.Process(status['pid'])
   if Path(p.exe()).resolve() != (root/'bin-full/inkling_ep_worker.exe').resolve(): raise RuntimeError('worker executable identity changed')
   if p.create_time()!=status['create_time']: raise RuntimeError('worker PID was reused')
   p.terminate();stopped=True
  except psutil.NoSuchProcess: pass
print(json.dumps(dict(stopped_own_worker=stopped)))
'''.replace('ROOT', repr(ROOT)).replace('LABEL', repr(job['label']))
    return json.loads(remote(host, script, 30))


def preflight(host, index, plan_hash, fused, reference):
    script = '''from pathlib import Path
import json,hashlib,psutil,urllib.request
root=Path(ROOT);model=root/'full'
status=json.loads((root/'full-stage-status.json').read_text())
if status['state']!='complete': raise RuntimeError('full shard staging incomplete')
plan_bytes=(root/'full-placement.json').read_bytes()
if hashlib.sha256(plan_bytes).hexdigest()!=PLAN_HASH: raise RuntimeError('placement differs across workers')
plan=json.loads(plan_bytes);m=json.loads((model/'manifest.json').read_text());nr=m['num_experts']
if m['num_layers']!=66 or m['num_experts']!=256 or m['hidden_size']!=6144: raise RuntimeError('not the full architecture')
verified=json.loads((root/'full-stage-journal.json').read_text())
expert_count=0
for li,layer in enumerate(plan['layers']):
 ids=[i for i,owners in enumerate(layer) if INDEX in owners]
 expected={}
 for eid in ids:
  name=f'experts/layer_{li:02}/'+(f'expert_{eid:03}.bin' if eid<nr else f'expert_shared{eid-nr}.bin')
  p=model/name;v=verified[name];s=p.stat()
  if s.st_size!=plan['expert_bytes'] or s.st_size!=v['bytes'] or s.st_mtime_ns!=v['mtime_ns']: raise RuntimeError('packed expert changed after verification: '+name)
  expected[str(eid)]=v['sha256'];expert_count+=1
 if FUSED and ids:
  d=root/'full-fused-compact'/f'layer_{li:02}';meta=json.loads((d/'shard.json').read_text())
  if meta['expert_ids']!=ids or meta['source_sha256']!=expected or meta['k']!=1 or meta['placement_sha256']!=PLAN_HASH: raise RuntimeError('fused shard provenance differs')
  if (d/'openvino_model.bin').stat().st_size!=meta['ir_bytes'] or hashlib.sha256((d/'openvino_model.xml').read_bytes()).hexdigest()!=meta['xml_sha256']: raise RuntimeError('fused IR size/XML changed')
if INDEX==2:
 ref=root/REFERENCE
 if json.loads((ref/'trace.json').read_text())['model_manifest']!=m: raise RuntimeError('reference model differs')
 hashes=json.loads((root/(REFERENCE+'-sha256.json')).read_text())
 for name,sha in hashes.items():
  if Path(name).name!=name: raise RuntimeError('unsafe reference filename')
  with (ref/name).open('rb') as f:
   if hashlib.file_digest(f,'sha256').hexdigest()!=sha: raise RuntimeError('reference checksum changed: '+name)
 for name in ['embed.safetensors','head.safetensors']+[f'shells/layer_{li:02}.safetensors' for li in range(66)]+['experts/layer_00/dense.bin','experts/layer_01/dense.bin']:
  p=model/name;v=verified[name];s=p.stat()
  if s.st_size!=v['bytes'] or s.st_mtime_ns!=v['mtime_ns']: raise RuntimeError('driver file changed: '+name)
health={n:urllib.request.urlopen('http://127.0.0.1:9000/v2/health/'+n,timeout=3).status for n in ['live','ready']}
print(json.dumps(dict(host=HOST,expert_count=expert_count,model_manifest=m,placement_sha256=PLAN_HASH,
 owned_layers=[li for li,layer in enumerate(plan['layers']) if any(INDEX in owners for owners in layer)],
 executable_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [root/'bin-full'/'inkling_ep_worker.exe',root/'bin-full'/'inkling_ep_validate.exe',*sorted((root/'bin-full').glob('*.dll'))]},
 available_gib=psutil.virtual_memory().available/2**30,free_gib=psutil.disk_usage(str(root)).free/2**30,health=health)))
'''
    for name, value in [('ROOT', ROOT), ('PLAN_HASH', plan_hash), ('INDEX', index), ('FUSED', fused), ('REFERENCE', reference), ('HOST', host)]:
        script = script.replace(name, repr(value))
    return json.loads(remote(host, script, 180))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--label', required=True)
    p.add_argument('--mode', required=True, choices=['cpu', 'fused-stream'])
    p.add_argument('--placement', required=True, type=Path)
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--reference', default='full-reference-v2')
    p.add_argument('--cases', default='full-cases.json')
    p.add_argument('--tokens', type=int, default=4)
    p.add_argument('--max-relative-rms', type=float, default=0)
    a = p.parse_args()
    if any(not re.fullmatch(r'[a-zA-Z0-9_-]+', n) for n in [a.label, a.reference]):
        p.error('label/reference must be simple names')
    if Path(a.cases).name != a.cases or a.tokens < 1 or not 0 <= a.max_relative_rms <= 0.02:
        p.error('invalid cases/tokens/tolerance')
    a.out.mkdir(parents=True, exist_ok=False)
    plan_hash = hashlib.sha256(a.placement.read_bytes()).hexdigest()
    fused = a.mode == 'fused-stream'
    inventories = {}
    for wi, host in enumerate(HOSTS):
        inventories[host] = preflight(host, wi, plan_hash, fused, a.reference)
    if len({json.dumps(i['executable_sha256'], sort_keys=True) for i in inventories.values()}) != 1:
        raise RuntimeError('worker binaries or runtime DLLs differ')
    if len({json.dumps(i['model_manifest'], sort_keys=True) for i in inventories.values()}) != 1:
        raise RuntimeError('worker model manifests differ')
    (a.out/'preflight.json').write_text(json.dumps(inventories, indent=2)+'\n')
    jobs = []
    for wi, host in enumerate(HOSTS):
        env = dict(CASCADIA_INKLING_EP_STREAM_CPU='1', CASCADIA_ACTIVATION_TIMEOUT_SECS='180', CASCADIA_FRAME_IDLE_CEILING_SECS='3600')
        if fused:
            env.update(CASCADIA_INKLING_EP_FUSED='1', CASCADIA_INKLING_EP_FUSED_STREAM='1', CASCADIA_INKLING_EP_FUSED_DIR=ROOT+'/full-fused-compact',
                       CASCADIA_INKLING_EP_FUSED_CACHE_MB='6000', CASCADIA_INKLING_EP_REQUIRE_GPU='1', OV_GPU_MOE_BATCHED_GEMV_THRESHOLD='0')
        job = dict(label=a.label+'-worker-'+str(wi), argv=[ROOT+'/bin-full/inkling_ep_worker.exe', '--export', ROOT+'/full', '--listen', HOSTS[host]+':'+str(PORT),
                   '--index', str(wi), '--count', '3', '--placement', ROOT+'/full-placement.json'], env=env,
                   cores=[0,1,2,3], seconds=3000, min_available_gib=12, max_rss_gib=6 if host=='charlie' else 8, pause_for_service=True)
        jobs.append((host,job))
    added, futures, cleanup = [], [], {}
    driver_result, worker_results = None, []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        try:
            for host in HOSTS:
                firewall(host, True)
                added.append(host)
            futures = [pool.submit(run_job, host, job, a.out) for host,job in jobs]
            for host,job in jobs:
                deadline = time.monotonic()+180
                while True:
                    log = remote(host, "from pathlib import Path; p=Path("+repr(ROOT+'/'+job['label']+'.log')+"); print(p.read_text()[-2000:] if p.exists() else '')", 30)
                    if 'listening=' in log:
                        break
                    if time.monotonic()>deadline or 'Error:' in log:
                        raise RuntimeError(host+' worker failed to start: '+log)
                    time.sleep(1)
            env = dict(CASCADIA_INKLING_MMAP_EMBED='1', CASCADIA_INKLING_MMAP_SHELLS='1', CASCADIA_INKLING_MMAP_HEAD='1',
                       CASCADIA_ACTIVATION_TIMEOUT_SECS='180', CASCADIA_FRAME_IDLE_CEILING_SECS='3600')
            if fused:
                env['CASCADIA_INKLING_EP_FUSED']='1'
            job = dict(label=a.label, argv=[ROOT+'/bin-full/inkling_ep_validate.exe', '--export', ROOT+'/full', '--cases', ROOT+'/'+a.cases,
                       '--tokens',str(a.tokens),'--out',ROOT+'/'+a.label,'--reference',ROOT+'/'+a.reference,'--ep-workers',','.join(ip+':'+str(PORT) for ip in HOSTS.values()),
                       '--ep-placement',ROOT+'/full-placement.json','--max-relative-rms',str(a.max_relative_rms)], env=env,
                       cores=[4,5],seconds=2700,min_available_gib=12,max_rss_gib=4,pause_for_service=True)
            driver_result = run_job('charlie',job,a.out)
            print('driver_returncode',driver_result['returncode'],flush=True)
            concurrent.futures.wait(futures,timeout=15)
        finally:
            for host,job in jobs:
                if host in added:
                    try:
                        cleanup[host]=cleanup_worker(host,job)
                    finally:
                        firewall(host,False)
            (a.out/'cleanup.json').write_text(json.dumps(cleanup,indent=2)+'\n')
        worker_results = [f.result() for f in futures]
    result = qualification(driver_result, dict(zip(HOSTS, worker_results)), inventories, fused)
    result.update(mode=a.mode,label=a.label)
    (a.out/'completion.json').write_text(json.dumps(result,indent=2)+'\n')
    if not result['completed']:
        raise SystemExit('full-model qualification failed; inspect retained artifacts')


if __name__=='__main__':
    main()
