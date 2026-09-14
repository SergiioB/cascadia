"""Wait for100/101, then qualify causal pre-attention routing diagnostics."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
import time

import psutil

ROOT=Path('C:/Users/devcloud/inkling-autolab')
STATE=ROOT/'route-prediction-qualification-state.json'


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
        assert sha(ROOT/'run-full-prediction.ps1')==source['candidate_wrapper_sha256']
    unchanged()
    candidate=ROOT/'bin/full-route-prediction.exe'
    assert not candidate.exists()
    assert not active_full()
    for item in source['files']:
        assert sha(ROOT/'repo'/item['path'])==item['previous_sha256'],item['path']
    with tarfile.open(ROOT/'route-prediction-source.tar') as archive:
        assert sorted(archive.getnames())==sorted(x['path'] for x in source['files'])
        contents={item['path']:archive.extractfile(item['path']).read() for item in source['files']}
    for item in source['files']:
        assert hashlib.sha256(contents[item['path']]).hexdigest()==item['candidate_sha256']
    for name,data in contents.items(): (ROOT/'repo'/name).write_bytes(data)
    with (ROOT/'104-route-prediction-tests.log').open('x',encoding='utf-8') as log:
        process=subprocess.Popen(['cmd.exe','/c',str(ROOT/'test-route-prediction.bat')],stdout=log,stderr=subprocess.STDOUT)
        state('building_and_testing',launcher_pid=process.pid)
        try:
            assert process.wait(timeout=3600)==0,'Native tests/build failed; inspect104 log'
        finally:
            if process.poll() is None:
                subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],check=False)
                process.wait()
    modes=[]
    controls={}
    for recent,predict in ((0,0),(0,1),(1,0),(1,1)):
        rows,capacity,reset=4,1,1
        assert not active_full()
        name=f'104-fixture-recent{recent}-predict{predict}'
        out=ROOT/(name+'.json');log=ROOT/(name+'.log')
        assert not out.exists() and not log.exists()
        command=['powershell','-NoProfile','-File',str(ROOT/'run-full-prediction.ps1'),'-Model',str(ROOT/'repo/crates/cascadia-engine-sparse-moe/tests/fixtures/inkling_export'),'-Cases',str(ROOT/'fixture-cases.json'),'-AllowFixture','-Binary',candidate.name,'-Threads','16','-AffinityMask','65535','-Reads','0','-Bf16Rows','2','-Int4Rows',str(rows),'-MmapEmbed','1','-ReuseBuffers','1','-SkipBulkPrefetch','1','-OwnShared','1','-UncachedReads','1','-PipelineReads','1','-ExpertCacheMiB',str(capacity),'-PrefillReads','1','-CacheResetHistory',str(reset),'-CacheDecayRequests',str(32 if capacity else 4096),'-CacheRecentTies',str(recent),'-Tokens','8','-Samples','3','-Out',str(out),'-Log',str(log)]
        routes=ROOT/(name+'-routes.json');predicted=ROOT/(name+'-predicted.json')
        command+=['-RouteTrace',str(routes)]
        if predict:command+=['-PredictionTrace',str(predicted)]
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
        actual=json.loads(routes.read_text())
        assert actual['correctness_verified'] and actual['output_hash']=='1f7cd0eb14a22662'
        artifacts=[out,log,routes]
        if not predict:
            controls[recent]=(actual,cache)
        else:
            expected,expected_cache=controls[recent]
            assert actual==expected and cache==expected_cache
            prediction=json.loads(predicted.read_text())
            assert prediction['scope']=='pre_attention_route_prediction_diagnostics'
            assert prediction['correctness_verified'] and prediction['output_hash']=='1f7cd0eb14a22662'
            assert prediction['prefetch_performed'] is False and prediction['actual_routing_changed'] is False
            assert len(prediction['samples'])==3
            for sample in prediction['samples']:
                assert sample['prefill_positions']==0 and sample['decode_positions']==7
                assert len(sample['layers'])==3 and {l['layer'] for l in sample['layers']}=={1,2,3}
                for layer in sample['layers']:assert len(layer['routed_experts_per_position'])==7
            artifacts.append(predicted)
        modes.append(dict(recent=recent,prediction=predict,output_hash=result['output_hash'],expert_cache=cache,artifacts=[dict(name=p.name,sha256=sha(p)) for p in artifacts]))
    unchanged()
    report=dict(status='qualified',source_commit=source['source_commit'],binary_sha256=sha(candidate),wrapper_sha256=source['candidate_wrapper_sha256'],modes=modes,full_model_speedup_measured=False)
    with (ROOT/'104-route-prediction-qualification.json').open('x') as f:json.dump(report,f,indent=2)
    (ROOT/'run-full.ps1').write_bytes((ROOT/'run-full-prediction.ps1').read_bytes())
    assert sha(ROOT/'run-full.ps1')==source['candidate_wrapper_sha256']
    return report


def main():
    import msvcrt
    with (ROOT/'route-prediction-qualification.lock').open('a+b') as owner:
        owner.seek(0);msvcrt.locking(owner.fileno(),msvcrt.LK_NBLCK,1)
        try:
            state('waiting_for_recency_comparison')
            deadline=time.monotonic()+7200
            reports=[ROOT/f'{n:03}-cache-recency-{label}.json' for n,label in ((100,'control'),(101,'recent'))]
            while not all(p.exists() for p in reports) or active_full():
                if time.monotonic()>deadline:raise TimeoutError('100/101 did not complete')
                time.sleep(15)
            for p in reports:
                d=json.loads(p.read_text());assert d['scope']=='full_large_model_decode' and d['correctness_verified'] and d['output_hash']=='ce0fbb9a116d3d09' and len(d['samples'])==3
            with (ROOT/'baseline-queue.lock').open('a+b') as slot:
                slot.seek(0);msvcrt.locking(slot.fileno(),msvcrt.LK_NBLCK,1)
                assert not active_full()
                source=json.loads((ROOT/'route-prediction-source.json').read_text())
                result=qualify(source)
            state('qualified',binary_sha256=result['binary_sha256'],modes=len(result['modes']))
        except BaseException as error:
            state('failed',error=str(error));raise


if __name__=='__main__':main()
