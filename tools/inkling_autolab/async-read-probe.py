"""Compare synchronous and overlapped uncached reads at realistic miss counts.

Read-only component probe after the full worker sweep. All buffers and OVERLAPPED
objects remain alive until completion, including cancellation on error. This
changes no model files and does not claim an inference speedup.
Sources: https://learn.microsoft.com/en-us/windows/win32/fileio/synchronous-and-asynchronous-i-o
https://learn.microsoft.com/en-us/windows/win32/fileio/file-buffering
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
import ctypes as C
import hashlib
import importlib.util
import json
import mmap
import os
from pathlib import Path
import random
import statistics
import tempfile
import time
import psutil

spec=importlib.util.spec_from_file_location('native_uncached',Path(__file__).with_name('uncached-read-probe.py'))
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)


class Overlapped(C.Structure):
    _fields_=[('internal',C.c_size_t),('internal_high',C.c_size_t),
              ('offset',C.c_uint32),('offset_high',C.c_uint32),('event',C.c_void_p)]


class AsyncIO(base.NativeIO):
    def __init__(self):
        super().__init__()
        for name,result,args in (
            ('CreateEventW',C.c_void_p,[C.c_void_p,C.c_int,C.c_int,C.c_wchar_p]),
            ('GetOverlappedResult',C.c_int,[C.c_void_p,C.POINTER(Overlapped),C.POINTER(C.c_uint32),C.c_int]),
            ('CancelIoEx',C.c_int,[C.c_void_p,C.POINTER(Overlapped)]),
        ):
            fn=getattr(self.k,name);fn.restype=result;fn.argtypes=args
        assert C.sizeof(Overlapped)==32, 'This probe targets native64-bit Windows'

    @contextmanager
    def async_handle(self,path):
        handle=self.k.CreateFileW(str(path),0x80000000,7,None,3,0x80|0x20000000|0x40000000,None)
        if handle==C.c_void_p(-1).value:raise C.WinError(C.get_last_error())
        try:yield handle
        finally:
            if not self.k.CloseHandle(handle):raise C.WinError(C.get_last_error())

    def batch(self,paths,buffers,chunk_bytes):
        if not paths or len(paths)!=len(buffers):raise ValueError('mismatched batch')
        operations=[]
        with ExitStack() as handles:
            try:
                for path,buffer in zip(paths,buffers):
                    handle=handles.enter_context(self.async_handle(path))
                    size=C.c_int64()
                    if not self.k.GetFileSizeEx(handle,C.byref(size)):raise C.WinError(C.get_last_error())
                    if size.value!=len(buffer):raise ValueError('expert size differs from destination')
                    info=self.storage(handle)
                    alignment=max(info[k] for k in ('logical','physical_atomic','physical_performance','effective_physical'))
                    if not alignment or alignment&(alignment-1) or C.addressof(buffer)%alignment or len(buffer)%alignment:
                        raise ValueError('unsupported buffer alignment')
                    chunk=chunk_bytes or len(buffer)
                    if chunk%alignment:raise ValueError('unaligned chunk')
                    for offset in range(0,len(buffer),chunk):
                        count=min(chunk,len(buffer)-offset)
                        event=self.k.CreateEventW(None,True,False,None)
                        if not event:raise C.WinError(C.get_last_error())
                        operation=dict(handle=handle,event=event,overlap=Overlapped(offset=offset&0xffffffff,offset_high=offset>>32,event=event),size=count,issued=False,completed=False)
                        operations.append(operation)
                        ok=self.k.ReadFile(handle,C.addressof(buffer)+offset,count,None,C.byref(operation['overlap']))
                        error=C.get_last_error() if not ok else 0
                        if not ok and error!=997:raise C.WinError(error) # ERROR_IO_PENDING
                        operation['issued']=True
                for operation in operations:
                    copied=C.c_uint32()
                    if not self.k.GetOverlappedResult(operation['handle'],C.byref(operation['overlap']),C.byref(copied),True):
                        raise C.WinError(C.get_last_error())
                    operation['completed']=True
                    if copied.value!=operation['size']:raise EOFError('incomplete asynchronous chunk')
            finally:
                # Cancellation alone is not completion. Drain before closing
                # events/files or allowing caller-owned buffers to be reused.
                for operation in operations:
                    if operation['issued'] and not operation['completed']:
                        self.k.CancelIoEx(operation['handle'],C.byref(operation['overlap']))
                        copied=C.c_uint32()
                        self.k.GetOverlappedResult(operation['handle'],C.byref(operation['overlap']),C.byref(copied),True)
                for operation in operations:
                    self.k.CloseHandle(operation['event'])


def canary(native,root):
    with tempfile.TemporaryDirectory(prefix='async-canary-',dir=root) as name:
        path=Path(name)/'known.bin';expected=bytes(range(256))*256
        with path.open('wb') as f:f.write(expected);f.flush();os.fsync(f.fileno())
        with native.buffer(len(expected)) as buffer:
            for chunk in (0,4096,16384):
                native.batch([path],[buffer],chunk);assert bytes(buffer)==expected
            try:native.batch([path.with_name('missing.bin')],[buffer],0)
            except OSError:pass
            else:raise AssertionError('missing file accepted')
            try:native.batch([path],[buffer],4097)
            except ValueError:pass
            else:raise AssertionError('unaligned chunk accepted')
            short=path.with_name('short.bin');short.write_bytes(expected[:4096])
            # First operation may be pending when the second size check fails;
            # cancellation/drain must leave its buffer safe to reuse.
            with native.buffer(len(expected)) as second:
                try:native.batch([path,short],[buffer,second],4096)
                except ValueError:pass
                else:raise AssertionError('short file accepted')
                native.batch([path],[buffer],4096);assert bytes(buffer)==expected
    return True


def run(args):
    native=AsyncIO();assert canary(native,args.root)
    trace=json.loads((args.root/'064-threads-16-routes.json').read_text())
    assert trace['full_model'] and trace['correctness_verified'] and trace['output_hash']=='ce0fbb9a116d3d09'
    excluded={(layer['layer'],e) for sample in trace['samples'] for layer in sample['layers']
              for row in layer['routed_experts_per_position'] for e in row}
    paths=[args.root/f'model/experts/layer_{layer:02}/expert_{expert:03}.bin'
           for layer in range(2,66) for expert in range(256) if (layer,expert) not in excluded]
    random.Random(690914).shuffle(paths)
    modes=[('sync',0),('async_whole',0),('async_1mib',1<<20),('async_4mib',4<<20),('async_8mib',8<<20)]
    plan=[(block,files,mode,chunk) for block in range(5) for files in (2,4,6)
          for mode,chunk in (modes if block%2==0 else list(reversed(modes)))]
    assert len(paths)>=sum(item[1] for item in plan)
    samples=[];position=0;process=psutil.Process()
    with ExitStack() as stack:
        buffers=[stack.enter_context(native.buffer(31850496)) for _ in range(6)]
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(lambda _:None,range(6)))
            for block,files,mode,chunk in plan:
                assert not base.active_full(args.root), 'Full benchmark started during probe'
                cohort=paths[position:position+files];position+=files
                before_cpu=process.cpu_times();before_disk=psutil.disk_io_counters()
                start=time.perf_counter()
                if mode=='sync':
                    list(pool.map(lambda pair:native.read(pair[0],pair[1],True),zip(cohort,buffers[:files])))
                else:native.batch(cohort,buffers[:files],chunk)
                seconds=time.perf_counter()-start
                after_cpu=process.cpu_times();after_disk=psutil.disk_io_counters()
                hashes=[]
                for path,buffer in zip(cohort,buffers):
                    copied=hashlib.sha256(buffer).hexdigest()
                    with path.open('rb') as source,mmap.mmap(source.fileno(),0,access=mmap.ACCESS_READ) as mapping:
                        assert copied==hashlib.sha256(mapping).hexdigest(), 'Read bytes differ'
                    hashes.append(dict(path=str(path.relative_to(args.root)),sha256=copied))
                sample=dict(block=block,files=files,mode=mode,chunk_bytes=chunk,bytes=files*31850496,
                            seconds=seconds,bytes_per_second=files*31850496/seconds,
                            user_cpu_seconds=after_cpu.user-before_cpu.user,
                            kernel_cpu_seconds=after_cpu.system-before_cpu.system,
                            machine_disk_read_bytes=after_disk.read_bytes-before_disk.read_bytes,
                            sha256_verified=True,artifacts=hashes)
                samples.append(sample);print(json.dumps(sample),flush=True)
    medians=[dict(files=files,mode=mode,seconds=statistics.median(s['seconds'] for s in samples if s['files']==files and s['mode']==mode))
             for files in (2,4,6) for mode,_ in modes]
    report=dict(scope='windows_uncached_async_chunk_component',full_model_speedup_measured=False,
                canary_bytes_and_error_recovery_verified=True,excludes_observed_full_routes=True,
                cache_state='natural_mixed_no_flush',reusable_buffer_bytes=6*31850496,
                samples=samples,medians=medians,caveats=[
                    'Component timing includes handle/metadata/event setup and read completion, excludes hashing.',
                    'Disjoint experts and alternating mode order reduce cache/order bias; hardware caches remain uncontrolled.',
                    'No compute overlaps these reads. A component win requires subsequent full-model validation.',
                    'Both arms use the same uncached flag; all bytes are checked against a mapped read outside timing.',
                ])
    with args.out.open('x') as f:json.dump(report,f,indent=2)
    return medians


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path('C:/Users/devcloud/inkling-autolab'))
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--wait',action='store_true')
    a=p.parse_args()
    if a.out.exists():p.error('refusing to overwrite report')
    import msvcrt
    state_path=a.root/'async-read-probe-state.json'
    def state(status,**fields):
        tmp=state_path.with_suffix('.tmp');tmp.write_text(json.dumps(dict(status=status,pid=os.getpid(),unix=time.time(),**fields),indent=2));tmp.replace(state_path)
    with (a.root/'async-read-probe.lock').open('a+b') as owner:
        owner.seek(0);msvcrt.locking(owner.fileno(),msvcrt.LK_NBLCK,1)
        try:
            state('waiting_for_worker_sweep');deadline=time.monotonic()+7200
            reports=[a.root/f'{n}-threads-{threads}.json' for n,threads in [('064',16),('065',8),('066',12),('067',24),('068',32)]]
            while base.active_full(a.root) or not all(x.exists() for x in reports):
                if not a.wait or time.monotonic()>=deadline:raise RuntimeError('Worker sweep must finish before probe')
                time.sleep(15)
            for path in reports:
                report=json.loads(path.read_text());assert report['scope']=='full_large_model_decode'
                assert report['correctness_verified'] and report['output_hash']=='ce0fbb9a116d3d09' and len(report['samples'])==3
            with (a.root/'baseline-queue.lock').open('a+b') as slot:
                slot.seek(0);msvcrt.locking(slot.fileno(),msvcrt.LK_NBLCK,1)
                assert not base.active_full(a.root)
                state('probing');medians=run(a)
            state('complete',medians=medians,full_model_speedup_measured=False)
        except BaseException as error:
            state('failed',error=str(error));raise


if __name__=='__main__':main()
