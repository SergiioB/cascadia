"""Resume and SHA256-verify the exact Inkling export from the miner to tate-07."""
import argparse, concurrent.futures, hashlib, json, os, threading, time
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request,build_opener,ProxyHandler
opener=build_opener(ProxyHandler({}))

ap=argparse.ArgumentParser();ap.add_argument('--probe',action='store_true');ap.add_argument('--workers',type=int,default=4);args=ap.parse_args()
if not 1 <= args.workers <= 8:ap.error('--workers must be between 1 and 8')
ROOT=Path('C:/Users/devcloud/inkling-autolab')
DEST=ROOT/'model';DEST.mkdir(exist_ok=True)
TOKEN=(ROOT/'transfer-token').read_text().strip()
BASE='http://100.103.4.77:18867'

def request(path,headers=None,method='GET'):
 return opener.open(Request(BASE+path,headers={'Authorization':'Bearer '+TOKEN,**(headers or {})},method=method),timeout=120)

def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
 return h.hexdigest()

with request('/manifest') as r:manifest=json.load(r)
records=manifest['files']
if args.probe:records=[next(r for r in records if r['path']=='experts/layer_02/expert_000.bin')]
verified={};errors=[];lock=threading.Lock();start=time.monotonic()
state_path=ROOT/'transfer-state.json'

def checkpoint(status):
 with lock:
  state={'status':status,'files_verified':len(verified),'files_total':len(records),
         'bytes_verified':sum(v['size'] for v in verified.values()),'bytes_total':sum(r['size'] for r in records),
         'elapsed_seconds':time.monotonic()-start,'errors':list(errors),'probe':args.probe,
         'pid':os.getpid(),'workers':args.workers}
  temp=state_path.with_suffix('.tmp');temp.write_text(json.dumps(state,indent=2));temp.replace(state_path)

# Periodic status updates do not alter the data-transfer schedule.
stop=threading.Event()
def progress():
 while not stop.wait(30):
  checkpoint('copying');print(state_path.read_text(),flush=True)
progress_thread=threading.Thread(target=progress,daemon=True);progress_thread.start()
failed=threading.Event()

def copy(r):
 if failed.is_set():raise concurrent.futures.CancelledError()
 name=r['path'];rel=Path(name)
 if rel.is_absolute() or '..' in rel.parts:raise ValueError('Unsafe manifest path')
 p=DEST/rel;p.parent.mkdir(parents=True,exist_ok=True)
 urlname=quote(name,safe='/')
 for attempt in range(5):
  if failed.is_set():raise concurrent.futures.CancelledError()
  try:
   with request('/sha256/'+urlname) as response:expected=response.read().decode()
   if len(expected)!=64:raise ValueError('Invalid digest')
   if p.exists() and p.stat().st_size==r['size'] and digest(p)==expected:
    with lock:verified[name]={'size':r['size'],'sha256':expected}
    return
   temp=p.with_name(p.name+'.inkling-partial')
   offset=temp.stat().st_size if temp.exists() else 0
   if offset>r['size']:temp.unlink();offset=0
   if offset<r['size']:
    headers={'Range':f'bytes={offset}-'} if offset else {}
    with request('/file/'+urlname,headers) as response:
     if offset and response.status!=206:raise ValueError('Range not honored')
     with temp.open('ab' if offset else 'wb') as f:
      while True:
       if failed.is_set():raise concurrent.futures.CancelledError()
       b=response.read(1024*1024)
       if not b:break
       f.write(b)
   elif not temp.exists():temp.touch()
   if temp.stat().st_size!=r['size']:raise ValueError('Incomplete file')
   if digest(temp)!=expected:temp.unlink();raise ValueError('SHA256 mismatch')
   temp.replace(p)
   with lock:verified[name]={'size':r['size'],'sha256':expected}
   if r['size']>100_000_000:print('VERIFIED '+name,flush=True)
   return
  except Exception:
   if attempt==4:raise
   time.sleep(min(2**attempt,16))

checkpoint('copying')
try:
 # Large files begin early; bounded concurrency keeps memory and disk use small.
 with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
  futures={pool.submit(copy,r):r['path'] for r in sorted(records,key=lambda r:r['size'],reverse=True)}
  for f in concurrent.futures.as_completed(futures):
   try:f.result()
   except concurrent.futures.CancelledError:pass
   except Exception as e:
    with lock:errors.append({'path':futures[f],'error':str(e)})
    failed.set()
    for pending in futures:pending.cancel()
 stop.set();progress_thread.join()
 if errors:checkpoint('failed');raise SystemExit(1)
 checkpoint('verified')
 if not args.probe:
  ready=ROOT/'model-ready.tmp'
  ready.write_text(json.dumps({'files':verified,'bytes':manifest['bytes']},indent=2))
  ready.replace(ROOT/'model-ready.json')
  try:
   with request('/shutdown',method='POST') as response:response.read()
  finally:(ROOT/'transfer-token').unlink(missing_ok=True)
 print('TRANSFER_VERIFIED_SECONDS='+str(time.monotonic()-start),flush=True)
finally:stop.set();progress_thread.join()
