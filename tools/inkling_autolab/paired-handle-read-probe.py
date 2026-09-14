"""Read-only paired estimate of exclusive uncached handle reuse after117.

Sources: https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-setfilepointerex
https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getfilesizeex
No handle is shared between simultaneous operations; seek and read stay together.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import ctypes as C
import hashlib,importlib.util,json,mmap,os,random,statistics,tempfile,time
from pathlib import Path
import psutil
spec=importlib.util.spec_from_file_location('uncached',Path(__file__).with_name('uncached-read-probe.py'));base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)

class HandleIO(base.NativeIO):
 def __init__(self):
  super().__init__();self.k.SetFilePointerEx.restype=C.c_int;self.k.SetFilePointerEx.argtypes=[C.c_void_p,C.c_int64,C.POINTER(C.c_int64),C.c_uint32]
 def size_check(self,handle,expected):
  size=C.c_int64()
  if not self.k.GetFileSizeEx(handle,C.byref(size)):raise C.WinError(C.get_last_error())
  if size.value!=expected:raise ValueError('expert size differs from destination')
 def read_handle(self,handle,buffer,reset):
  pointer=C.addressof(buffer)
  if not len(buffer) or len(buffer)%4096 or pointer%4096:raise ValueError('unaligned buffer')
  if reset and not self.k.SetFilePointerEx(handle,0,None,0):raise C.WinError(C.get_last_error())
  self.size_check(handle,len(buffer));position=0
  while position<len(buffer):
   remaining=len(buffer)-position;copied=C.c_uint32()
   if remaining>0xffffffff or position%4096:raise ValueError('unaligned short read')
   if not self.k.ReadFile(handle,pointer+position,remaining,C.byref(copied),None):raise C.WinError(C.get_last_error())
   if not 0<copied.value<=remaining:raise EOFError('incomplete expert read')
   position+=copied.value
  self.size_check(handle,len(buffer))
 def fresh(self,path,buffer):
  with self.handle(path,True) as handle:self.read_handle(handle,buffer,False)

def canary(native,root):
 with tempfile.TemporaryDirectory(prefix='handle-canary-',dir=root) as directory:
  path=Path(directory)/'known.bin';expected=bytes(range(256))*256
  with path.open('wb') as f:f.write(expected);f.flush();os.fsync(f.fileno())
  with native.buffer(len(expected)) as buffer,native.handle(path,True) as handle:
   native.fresh(path,buffer);assert bytes(buffer)==expected
   for _ in range(3):native.read_handle(handle,buffer,True);assert bytes(buffer)==expected
   with native.buffer(len(expected)+4096) as large:
    try:native.read_handle(handle,large,True)
    except ValueError:pass
    else:raise AssertionError('wrong length accepted')
   native.read_handle(handle,buffer,True);assert bytes(buffer)==expected
  try:native.fresh(path.with_name('missing.bin'),None)
  except OSError:pass
  else:raise AssertionError('missing file accepted')
 return True

def run(args):
 native=HandleIO();assert canary(native,args.root);excluded=set()
 for name in ['064-threads-16-routes.json','106-heldout-control-routes.json']:
  trace=json.loads((args.root/name).read_text());assert trace['full_model']
  for s in trace['samples']:
   for l in s['layers']:
    for row in l['routed_experts_per_position']:excluded.update((l['layer'],e) for e in row)
 paths=[args.root/f'model/experts/layer_{layer:02}/expert_{expert:03}.bin' for layer in range(2,66) for expert in range(256) if (layer,expert) not in excluded]
 random.Random(1180914).shuffle(paths);assert len(paths)>=120
 samples=[];position=0
 with ExitStack() as stack:
  buffers=[stack.enter_context(native.buffer(31850496)) for _ in range(6)]
  with ThreadPoolExecutor(max_workers=6) as pool:
   list(pool.map(lambda _:None,range(6)))
   for block in range(10):
    for files in (2,4,6):
     assert not base.active_full(args.root)
     cohort=paths[position:position+files];position+=files
     with ExitStack() as retained:
      started=time.perf_counter();handles=[retained.enter_context(native.handle(p,True)) for p in cohort];open_seconds=time.perf_counter()-started
      for handle in handles:
       info=native.storage(handle);alignment=max(info[k] for k in ['logical','physical_atomic','physical_performance','effective_physical']);assert alignment and 4096%alignment==0
      order=['fresh','reused'] if block%2==0 else ['reused','fresh'];seconds={};hashes={}
      for mode in order:
       started=time.perf_counter()
       if mode=='fresh':list(pool.map(lambda pair:native.fresh(*pair),zip(cohort,buffers[:files])))
       else:list(pool.map(lambda pair:native.read_handle(*pair,True),zip(handles,buffers[:files])))
       seconds[mode]=time.perf_counter()-started;hashes[mode]=[hashlib.sha256(b).hexdigest() for b in buffers[:files]]
      oracle=[]
      for path in cohort:
       with path.open('rb') as source,mmap.mmap(source.fileno(),0,access=mmap.ACCESS_READ) as mapping:oracle.append(hashlib.sha256(mapping).hexdigest())
      assert hashes['fresh']==hashes['reused']==oracle
     sample=dict(block=block,files=files,order=order,seconds=seconds,retained_handle_open_seconds=open_seconds,fresh_over_reused_ratio=seconds['fresh']/seconds['reused'],sha256_verified=True,artifacts=[dict(path=str(p.relative_to(args.root)),sha256=h) for p,h in zip(cohort,oracle)])
     samples.append(sample);print(json.dumps(sample),flush=True)
 summaries=[]
 for files in (2,4,6):
  group=[s for s in samples if s['files']==files];summaries.append(dict(files=files,pairs=len(group),reuse_wins=sum(s['fresh_over_reused_ratio']>1 for s in group),median_pair_speedup=statistics.median(s['fresh_over_reused_ratio'] for s in group),median_seconds={m:statistics.median(s['seconds'][m] for s in group) for m in ['fresh','reused']},median_pair_speedup_by_first_mode={m:statistics.median(s['fresh_over_reused_ratio'] for s in group if s['order'][0]==m) for m in ['fresh','reused']}))
 report=dict(scope='paired_exclusive_uncached_handle_reuse_component',full_model_speedup_measured=False,canary_verified=True,pairs=samples,summaries=summaries,all_handles_and_buffers_released=True,caveats=['Each retained handle is exclusive to one operation; reset and read are not concurrent on a shared file cursor.','Retained handle initial opens are recorded separately and outside paired read timing; a real bounded cache must also pay misses and lookup costs.','Both arms check length before and after the complete read; no safety checks are removed.','Preopening may warm file metadata for both arms. Hardware caches are uncontrolled; balanced order results and all pairs are retained.','Python/Win32 component timing is not a Rust full-model speed claim. SHA oracles run after both arms.'])
 with args.out.open('x') as f:json.dump(report,f,indent=2)
 return summaries

def main():
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path('C:/Users/devcloud/inkling-autolab'));p.add_argument('--out',type=Path,required=True);a=p.parse_args();assert not a.out.exists()
 import msvcrt
 state_path=a.root/'handle-read-probe-state.json'
 def state(status,**fields):
  tmp=state_path.with_suffix('.tmp');tmp.write_text(json.dumps(dict(status=status,pid=os.getpid(),created_unix=psutil.Process().create_time(),unix=time.time(),**fields),indent=2));tmp.replace(state_path)
 with (a.root/'handle-read-probe.lock').open('a+b') as owner:
  owner.seek(0);msvcrt.locking(owner.fileno(),msvcrt.LK_NBLCK,1);assert not state_path.exists()
  try:
   state('waiting117');deadline=time.monotonic()+3600;path=a.root/'117-early-prediction.json'
   while not path.exists() or base.active_full(a.root):
    if time.monotonic()>deadline:raise TimeoutError('117 did not finish')
    time.sleep(15)
   d=json.loads(path.read_text());assert d['scope']=='full_large_model_decode' and d['correctness_verified'] and d['output_hash']=='ce0fbb9a116d3d09' and len(d['samples'])==3
   with (a.root/'baseline-queue.lock').open('a+b') as slot:
    slot.seek(0);msvcrt.locking(slot.fileno(),msvcrt.LK_NBLCK,1);assert not base.active_full(a.root);state('probing');summaries=run(a)
   state('complete',summaries=summaries)
  except BaseException as e:state('failed',error=str(e));raise
if __name__=='__main__':main()
