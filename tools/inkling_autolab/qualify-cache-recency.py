"""Wait for094/095, then build and qualify opt-in cache recency admission."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tarfile
import time

import psutil

ROOT=Path('C:/Users/devcloud/inkling-autolab')
STATE=ROOT/'cache-recency-qualification-state.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def state(status, **fields):
    temp=STATE.with_suffix('.tmp')
    temp.write_text(json.dumps(dict(status=status,pid=os.getpid(),unix=time.time(),**fields),indent=2))
    temp.replace(STATE)


def active_full():
    prefix=str(ROOT/'bin').lower()+'\\'
    return [p.pid for p in psutil.process_iter(['exe','name']) if (p.info['exe'] or '').lower().startswith(prefix) and (p.info['name'] or '').startswith('full-')]


def qualify(source):
    frozen=source['frozen_binaries']
    def unchanged():
        for name, expected in frozen.items(): assert sha(ROOT/'bin'/name)==expected,name
        assert sha(ROOT/'run-full.ps1')==source['previous_wrapper_sha256']
        assert sha(ROOT/'run-full-cache-recency.ps1')==source['candidate_wrapper_sha256']
    unchanged()
    candidate=ROOT/'bin/full-cache-recency.exe'
    assert not candidate.exists()
    assert not active_full()
    for item in source['files']:
        assert sha(ROOT/'repo'/item['path'])==item['previous_sha256'],item['path']
    with tarfile.open(ROOT/'cache-recency-source.tar') as archive:
        assert sorted(archive.getnames())==sorted(x['path'] for x in source['files'])
        contents={item['path']:archive.extractfile(item['path']).read() for item in source['files']}
    for item in source['files']:
        assert hashlib.sha256(contents[item['path']]).hexdigest()==item['candidate_sha256']
    for name,data in contents.items(): (ROOT/'repo'/name).write_bytes(data)
    with (ROOT/'098-cache-recency-tests.log').open('x',encoding='utf-8') as log:
        process=subprocess.Popen(['cmd.exe','/c',str(ROOT/'test-cache-recency.bat')],stdout=log,stderr=subprocess.STDOUT)
        state('building_and_testing',launcher_pid=process.pid)
        try:
            assert process.wait(timeout=3600)==0,'Native tests/build failed; inspect098 log'
        finally:
            if process.poll() is None:
                subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],check=False)
                process.wait()
    modes=[]
    for rows,recent,capacity,reset in ((4,0,1,1),(4,1,1,1),(2,1,1,1),(4,0,0,0),(4,1,1,0)):
        assert not active_full()
        name=f'098-fixture-rows{rows}-recent{recent}-cache{capacity}-reset{reset}'
        out=ROOT/(name+'.json');log=ROOT/(name+'.log')
        assert not out.exists() and not log.exists()
        command=['powershell','-NoProfile','-File',str(ROOT/'run-full-cache-recency.ps1'),'-Model',str(ROOT/'repo/crates/cascadia-engine-sparse-moe/tests/fixtures/inkling_export'),'-Cases',str(ROOT/'fixture-cases.json'),'-AllowFixture','-Binary',candidate.name,'-Threads','16','-AffinityMask','65535','-Reads','0','-Bf16Rows','2','-Int4Rows',str(rows),'-MmapEmbed','1','-ReuseBuffers','1','-SkipBulkPrefetch','1','-OwnShared','1','-UncachedReads','1','-PipelineReads','1','-ExpertCacheMiB',str(capacity),'-PrefillReads','1','-CacheResetHistory',str(reset),'-CacheDecayRequests',str(32 if capacity else 4096),'-CacheRecentTies',str(recent),'-Tokens','8','-Samples','3','-Out',str(out),'-Log',str(log)]
        run=subprocess.run(command,text=True,capture_output=True,timeout=120)
        assert run.returncode==0,run.stdout[-3000:]+run.stderr[-3000:]
        assert f'bf16_rows=2 int4_rows={rows}' in run.stdout and f'cache_recent_ties={recent}' in run.stdout
        assert 'processor_affinity=65535' in run.stdout and 'rayon_threads=16' in run.stdout
        result=json.loads(out.read_text());cache=result['expert_cache']
        assert result['scope']=='fixture_model_decode' and result['correctness_verified'] and result['output_hash']=='1f7cd0eb14a22662'
        assert len(result['samples'])==3 and {s['repetition'] for s in result['samples']}=={0,1,2}
        assert all(s['generated_ids']==[28,48,106,84,28,48,106,84] for s in result['samples'])
        assert cache['capacity_bytes']==capacity*3145728 and cache['history_resets']==(9 if reset else 0)
        assert cache['hits']==(110 if capacity else 0) and cache['misses']==(16 if capacity else 0)
        assert cache['recent_tie_admissions']==0 # This tiny model's full expert set fits; unit tests force evictions.
        assert cache['frequency_decays']==(3 if capacity and not reset else 0)
        assert result['prefill_read_experts']==63 and result['prefill_uncached_read_fallbacks']==63
        modes.append(dict(rows=rows,recent=recent,capacity=capacity,reset=reset,output_hash=result['output_hash'],expert_cache=cache,artifacts=[dict(name=p.name,sha256=sha(p)) for p in (out,log)]))
    unchanged()
    report=dict(status='qualified',source_commit=source['source_commit'],binary_sha256=sha(candidate),wrapper_sha256=source['candidate_wrapper_sha256'],modes=modes,full_model_speedup_measured=False)
    with (ROOT/'098-cache-recency-qualification.json').open('x') as f:json.dump(report,f,indent=2)
    (ROOT/'run-full.ps1').write_bytes((ROOT/'run-full-cache-recency.ps1').read_bytes())
    assert sha(ROOT/'run-full.ps1')==source['candidate_wrapper_sha256']
    return report


def main():
    import msvcrt
    with (ROOT/'cache-recency-qualification.lock').open('a+b') as owner:
        owner.seek(0);msvcrt.locking(owner.fileno(),msvcrt.LK_NBLCK,1)
        try:
            state('waiting_for_repeated_rows')
            deadline=time.monotonic()+7200
            reports=[ROOT/f'{n:03}-rows-repeated-{label}.json' for n,label in ((94,'control'),(95,'candidate'))]
            while not all(p.exists() for p in reports) or active_full():
                if time.monotonic()>deadline:raise TimeoutError('094/095 did not complete')
                time.sleep(15)
            for p in reports:
                d=json.loads(p.read_text());assert d['scope']=='full_large_model_decode' and d['correctness_verified'] and d['output_hash']=='ce0fbb9a116d3d09' and len(d['samples'])==9
            with (ROOT/'baseline-queue.lock').open('a+b') as slot:
                slot.seek(0);msvcrt.locking(slot.fileno(),msvcrt.LK_NBLCK,1)
                assert not active_full()
                source=json.loads((ROOT/'cache-recency-source.json').read_text())
                result=qualify(source)
            state('qualified',binary_sha256=result['binary_sha256'],modes=len(result['modes']))
        except BaseException as error:
            state('failed',error=str(error));raise


if __name__=='__main__':main()
