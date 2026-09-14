"""Repeat the promising whole-file async comparison on matched expert cohorts.

Alternating order, same buffers/files per pair, mapped oracle only after both
arms. Wait for cache-decay trials071/072 before read-only component work.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import hashlib
import importlib.util
import json
import mmap
import os
from pathlib import Path
import random
import statistics
import time

spec=importlib.util.spec_from_file_location('async_probe',Path(__file__).with_name('async-read-probe.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def run(args):
    native=module.AsyncIO();assert module.canary(native,args.root)
    trace=json.loads((args.root/'064-threads-16-routes.json').read_text())
    assert trace['full_model'] and trace['correctness_verified'] and trace['output_hash']=='ce0fbb9a116d3d09'
    excluded={(layer['layer'],e) for sample in trace['samples'] for layer in sample['layers']
              for row in layer['routed_experts_per_position'] for e in row}
    prior=json.loads((args.root/'069-async-read-probe.json').read_text())
    old_paths={str(Path(a['path'])) for s in prior['samples'] for a in s['artifacts']}
    paths=[args.root/f'model/experts/layer_{layer:02}/expert_{expert:03}.bin'
           for layer in range(2,66) for expert in range(256) if (layer,expert) not in excluded
           and str(Path(f'model/experts/layer_{layer:02}/expert_{expert:03}.bin')) not in old_paths]
    random.Random(730914).shuffle(paths);assert len(paths)>=120
    samples=[];position=0
    with ExitStack() as stack:
        buffers=[stack.enter_context(native.buffer(31850496)) for _ in range(6)]
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(lambda _:None,range(6)))
            for block in range(10):
                for files in (2,4,6):
                    assert not module.base.active_full(args.root)
                    cohort=paths[position:position+files];position+=files
                    order=['sync','async_whole'] if block%2==0 else ['async_whole','sync']
                    results={};hashes={}
                    for mode in order:
                        start=time.perf_counter()
                        if mode=='sync':list(pool.map(lambda p:native.read(p[0],p[1],True),zip(cohort,buffers[:files])))
                        else:native.batch(cohort,buffers[:files],0)
                        results[mode]=time.perf_counter()-start
                        hashes[mode]=[hashlib.sha256(b).hexdigest() for b in buffers[:files]]
                    oracle=[]
                    for path in cohort:
                        with path.open('rb') as source,mmap.mmap(source.fileno(),0,access=mmap.ACCESS_READ) as mapping:
                            oracle.append(hashlib.sha256(mapping).hexdigest())
                    assert hashes['sync']==hashes['async_whole']==oracle
                    sample=dict(block=block,files=files,order=order,seconds=results,
                                sync_over_async_ratio=results['sync']/results['async_whole'],sha256_verified=True,
                                artifacts=[dict(path=str(p.relative_to(args.root)),sha256=h) for p,h in zip(cohort,oracle)])
                    samples.append(sample);print(json.dumps(sample),flush=True)
    summaries=[]
    for files in (2,4,6):
        group=[s for s in samples if s['files']==files]
        summaries.append(dict(files=files,pairs=len(group),async_wins=sum(s['sync_over_async_ratio']>1 for s in group),
                              median_pair_speedup=statistics.median(s['sync_over_async_ratio'] for s in group),
                              median_seconds={mode:statistics.median(s['seconds'][mode] for s in group) for mode in ('sync','async_whole')},
                              median_pair_speedup_by_first_mode={mode:statistics.median(s['sync_over_async_ratio'] for s in group if s['order'][0]==mode) for mode in ('sync','async_whole')}))
    report=dict(scope='paired_windows_uncached_async_component',full_model_speedup_measured=False,
                canary_verified=True,excludes_full_routes_and_previous_probe=True,pairs=samples,summaries=summaries,
                caveats=['Hardware caches remain uncontrolled; matched pairs alternate order.','Mapped oracle runs after both arms. Hashing and oracle are outside read timing.','Component gains require separate full-model validation.'])
    with args.out.open('x') as f:json.dump(report,f,indent=2)
    return summaries


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path('C:/Users/devcloud/inkling-autolab'));p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.out.exists():p.error('refusing to overwrite report')
    import msvcrt
    state_path=a.root/'paired-async-read-probe-state.json'
    def state(status,**fields):
        tmp=state_path.with_suffix('.tmp');tmp.write_text(json.dumps(dict(status=status,pid=os.getpid(),unix=time.time(),**fields),indent=2));tmp.replace(state_path)
    with (a.root/'paired-async-read-probe.lock').open('a+b') as owner:
        owner.seek(0);msvcrt.locking(owner.fileno(),msvcrt.LK_NBLCK,1)
        try:
            state('waiting_for_cache_decay');deadline=time.monotonic()+7200
            reports=[a.root/'071-decay-4096.json',a.root/'072-decay-32.json']
            while module.base.active_full(a.root) or not all(p.exists() for p in reports):
                if time.monotonic()>=deadline:raise TimeoutError('Cache-decay trials did not finish')
                time.sleep(15)
            for report in reports:
                d=json.loads(report.read_text());assert d['scope']=='full_large_model_decode' and d['correctness_verified'] and d['output_hash']=='ce0fbb9a116d3d09' and len(d['samples'])==3
            with (a.root/'baseline-queue.lock').open('a+b') as slot:
                slot.seek(0);msvcrt.locking(slot.fileno(),msvcrt.LK_NBLCK,1)
                assert not module.base.active_full(a.root)
                state('probing');summaries=run(a)
            state('complete',summaries=summaries,full_model_speedup_measured=False)
        except BaseException as e:state('failed',error=str(e));raise


if __name__=='__main__':main()
