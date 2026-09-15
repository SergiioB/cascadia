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
from pathlib import Path, PureWindowsPath
import re
import time

from inkling_ep_lan_control import HOSTS, ROOT, PYTHON, remote

PORT = 29475
RULE = 'InklingEP-Full-20260915'


def qualification(driver, workers, inventories, fused, recording=False):
    """Fail closed on missing numerical, backend, coverage or service evidence."""
    failures, backends = [], {}
    if not inventories or set(workers) != set(inventories):
        failures.append('worker evidence does not match the deployment')
    report = (driver or {}).get('report') or {}
    if recording:
        if (report.get('full_model') is not True or report.get('reference_comparison') is not False
                or report.get('teacher_forced') is not False or report.get('tensor_errors') != []
                or not report.get('generated_ids')
                or any(len(ids) != report.get('tokens_per_case') for ids in report['generated_ids'])):
            failures.append('full-model reference recording did not complete')
    elif not all(report.get(k) is True for k in ['full_model', 'reference_comparison', 'greedy_match', 'numerical_match', 'correctness_verified']):
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
            if inventories[host].get('ordered_replies_required') and stats.get('ordered_replies', 0) <= 0:
                failures.append(host+': ordered per-expert GPU replies were not verified')
            shards = inventories[host].get('fused_shards')
            if shards is not None and stats.get('up_scale_exponent') != {
                    layer:meta.get('up_scale_exponent') or 0 for layer,meta in shards.items()}:
                failures.append(host+': runtime IR scaling differs from deployment evidence')
        elif backend.get('cpu_calls', 0) <= 0 or backend.get('fused') is not None:
            failures.append(host+': CPU reference backend evidence is invalid')
        elif status.get('job', {}).get('env', {}).get('CASCADIA_INKLING_UNCACHED_READS') == '1':
            if backend.get('uncached_read_bytes', 0) <= 0 or backend.get('uncached_read_fallbacks') != 0:
                failures.append(host+': required direct expert reads were not verified')
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
 log=log.read_text(encoding='utf-8',errors='replace') if log.exists() else '',
 report=json.loads(report.read_text(encoding='utf-8')) if report.exists() else None)))
'''.replace('ROOT', repr(ROOT)).replace('JOB', repr(job)).replace('PYTHON', repr(PYTHON))
    result = json.loads(remote(host, script, job['seconds']+80))
    (out/(host+'-'+job['label']+'.json')).write_text(json.dumps(result, indent=2)+'\n')
    return result


def firewall(host, add, ports=None):
    ports = ports or [PORT]
    if add:
        program = str(PureWindowsPath(ROOT) / 'bin-full' / 'inkling_ep_worker.exe')
        script = f"""$ErrorActionPreference='Stop'
if (Get-NetFirewallRule -Name '{RULE}' -ErrorAction SilentlyContinue) {{ throw 'Task rule already exists' }}
New-NetFirewallRule -Name '{RULE}' -DisplayName '{RULE}' -Direction Inbound -Action Allow -Profile Any -Protocol TCP -LocalPort {",".join(map(str, ports))} -RemoteAddress {HOSTS['charlie']} -Program '{program}' | Out-Null
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
expert_count=0;fused_shards={}
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
  if (root/'full-fused'/f'layer_{li:02}'/'.rebalance').exists(): raise RuntimeError('fused scale transaction incomplete')
  if not (meta['version']==1 and meta.get('up_scale_exponent',0)==0 or meta['version']==2 and 1<=meta.get('up_scale_exponent',0)<=8): raise RuntimeError('unsupported fused scale metadata')
  if meta['expert_ids']!=ids or meta['source_sha256']!=expected or meta['k']!=1 or meta['placement_sha256']!=PLAN_HASH: raise RuntimeError('fused shard provenance differs')
  if (d/'openvino_model.bin').stat().st_size!=meta['ir_bytes'] or hashlib.sha256((d/'openvino_model.xml').read_bytes()).hexdigest()!=meta['xml_sha256']: raise RuntimeError('fused IR size/XML changed')
  fused_shards[str(li)]={k:meta.get(k) for k in ['version','bin_sha256','up_scale_exponent','up_scale_relative_rms','unscaled_bin_sha256']}
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
print(json.dumps(dict(host=HOST,expert_count=expert_count,model_manifest=m,placement_sha256=PLAN_HASH,fused_shards=fused_shards,
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
    p.add_argument('--record', action='store_true', help='record a free-running GPU baseline; does not certify correctness')
    p.add_argument('--workers-per-host', type=int, choices=[1, 4], default=1)
    p.add_argument('--cache-mb-per-host', type=int, default=2400)
    p.add_argument('--seconds', type=int, default=3000)
    p.add_argument('--bf16-expert-output', action='store_true',
                   help='round each K=1 raw expert output to BF16 before f32 routing, matching the CPU projection boundary')
    a = p.parse_args()
    if any(not re.fullmatch(r'[a-zA-Z0-9_-]+', n) for n in [a.label, a.reference]):
        p.error('label/reference must be simple names')
    if Path(a.cases).name != a.cases or a.tokens < 1 or not 0 <= a.max_relative_rms <= 0.02:
        p.error('invalid cases/tokens/tolerance')
    if not 256 <= a.cache_mb_per_host <= 6000 or not 300 <= a.seconds <= 3400:
        p.error('invalid cache/lease')
    if a.workers_per_host > 1 and a.mode != 'fused-stream':
        p.error('multiple workers per host requires fused-stream')
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
    for inventory in inventories.values():
        inventory['ordered_replies_required'] = fused
    (a.out/'preflight.json').write_text(json.dumps(inventories, indent=2)+'\n')
    parent_inventories = inventories
    if a.workers_per_host > 1:
        from inkling_ep_topology import prepare_views
        deployment = prepare_views(a.placement, a.workers_per_host, parent_inventories)
        (a.out/'topology.json').write_text(json.dumps(deployment, indent=2)+'\n')
        plan_path = ROOT+'/full-topology-'+str(a.workers_per_host)+'.json'
        inventories = deployment['inventories']
    else:
        plan_path = ROOT+'/full-placement.json'
    jobs = []
    for pi, host in enumerate(HOSTS):
      for child in range(a.workers_per_host):
        wi = pi*a.workers_per_host+child
        key = host if a.workers_per_host == 1 else host+'-'+str(child)
        env = dict(CASCADIA_INKLING_EP_STREAM_CPU='1', CASCADIA_ACTIVATION_TIMEOUT_SECS='180', CASCADIA_FRAME_IDLE_CEILING_SECS='3600')
        if not fused and host == 'charlie':
            env['CASCADIA_INKLING_UNCACHED_READS'] = '1'
        if fused:
            fused_dir = ROOT+'/full-fused-compact' if a.workers_per_host == 1 else ROOT+'/full-views-'+str(a.workers_per_host)+'/worker-'+str(wi)
            env.update(CASCADIA_INKLING_EP_FUSED='1', CASCADIA_INKLING_EP_FUSED_STREAM='1', CASCADIA_INKLING_EP_FUSED_DIR=fused_dir,
                       CASCADIA_INKLING_EP_FUSED_CACHE_MB=str(a.cache_mb_per_host//a.workers_per_host), CASCADIA_INKLING_EP_REQUIRE_GPU='1', OV_GPU_MOE_BATCHED_GEMV_THRESHOLD='0')
            env['CASCADIA_INKLING_EP_DIAGNOSTICS_DIR'] = ROOT
            if a.bf16_expert_output:
                env['CASCADIA_INKLING_EP_FUSED_BF16_OUTPUT'] = '1'
        cores = ([4+child] if host=='charlie' else [child]) if a.workers_per_host > 1 else ([4,5] if fused and host=='charlie' else [0,1,2,3])
        job = dict(label=a.label+'-worker-'+str(wi), argv=[ROOT+'/bin-full/inkling_ep_worker.exe', '--export', ROOT+'/full', '--listen', HOSTS[host]+':'+str(PORT+child),
                   '--index', str(wi), '--count', str(3*a.workers_per_host), '--placement', plan_path], env=env,
                   cores=cores, seconds=a.seconds+150, min_available_gib=12,
                   max_rss_gib=3 if a.workers_per_host > 1 else (6 if host=='charlie' else 8), pause_for_service=True)
        jobs.append((host,key,job))
    added, futures, cleanup = [], [], {}
    driver_result, worker_results = None, []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        try:
            for host in HOSTS:
                firewall(host, True, list(range(PORT, PORT+a.workers_per_host)))
                added.append(host)
            futures = [pool.submit(run_job, host, job, a.out) for host,key,job in jobs]
            for host,key,job in jobs:
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
                       '--tokens',str(a.tokens),'--out',ROOT+'/'+a.label,*([] if a.record else ['--reference',ROOT+'/'+a.reference]),'--ep-workers',','.join(ip+':'+str(PORT+c) for ip in HOSTS.values() for c in range(a.workers_per_host)),
                       '--ep-placement',plan_path,'--max-relative-rms',str(a.max_relative_rms)], env=env,
                       cores=[0,1,2,3] if fused else [4,5],
                       seconds=a.seconds,min_available_gib=12,max_rss_gib=4,pause_for_service=True)
            driver_result = run_job('charlie',job,a.out)
            print('driver_returncode',driver_result['returncode'],flush=True)
            concurrent.futures.wait(futures,timeout=15)
        finally:
            for host,key,job in jobs:
                if host in added:
                    try:
                        cleanup[key]=cleanup_worker(host,job)
                    except Exception as error:
                        cleanup[key] = {'cleanup_error':str(error)}
            for host in added:
                firewall(host,False)
            (a.out/'cleanup.json').write_text(json.dumps(cleanup,indent=2)+'\n')
        worker_results = [f.result() for f in futures]
    result = qualification(driver_result, dict(zip([key for _,key,_ in jobs], worker_results)), inventories, fused, a.record)
    result.update(mode=a.mode,label=a.label,recording=a.record,physical_hosts=3,workers=3*a.workers_per_host)
    if a.record and result['completed']:
        # Publish checksums only after every backend and guard completed.
        script = "from pathlib import Path; import hashlib,json; p=Path("+repr(ROOT+'/'+a.label)+"); hashes={n:hashlib.file_digest((p/n).open('rb'),'sha256').hexdigest() for n in ['trace.json','tensors.f32','report.json']}; (p.parent/(p.name+'-sha256.json')).write_text(json.dumps(hashes,indent=2)); print(json.dumps(hashes))"
        result['recording_sha256'] = json.loads(remote('charlie',script,120))
    (a.out/'completion.json').write_text(json.dumps(result,indent=2)+'\n')
    if not result['completed']:
        raise SystemExit('full-model qualification failed; inspect retained artifacts')


if __name__=='__main__':
    main()
