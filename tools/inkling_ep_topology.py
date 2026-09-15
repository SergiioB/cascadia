#!/usr/bin/env python3
"""Split existing physical shards into logical workers without copying weights.

Each read-only view retains its parent's IR indices and hard-links the exact
same XML/bin. Ownership remains explicit and is enforced by the native worker.
This tests logical routing on three hosts; it is not a twelve-host benchmark.
"""
import concurrent.futures
import copy
import hashlib
import json
from pathlib import Path

from inkling_ep_lan_control import HOSTS, ROOT, remote


def split_plan(parent, children):
    if not 1 <= children <= 4 or len(parent['workers']) != 3:
        raise ValueError('expected three physical parents and 1..4 children')
    plan = copy.deepcopy(parent)
    plan['workers'] = [dict(w, name=w['name']+'-'+str(c), expert_capacity_bytes=0)
                       for w in parent['workers'] for c in range(children)]
    plan['layers'] = [[[pi*children+(eid % children) for pi in owners]
                       for eid, owners in enumerate(layer)] for layer in parent['layers']]
    for layer in plan['layers']:
        for owners in layer:
            for wi in owners:
                plan['workers'][wi]['expert_capacity_bytes'] += plan['expert_bytes']
    for pi, w in enumerate(parent['workers']):
        total = sum(c['expert_capacity_bytes'] for c in plan['workers'][pi*children:(pi+1)*children])
        if total > w['expert_capacity_bytes']:
            raise ValueError('children exceed parent storage budget')
    return plan


def prepare_views(parent_path, children, inventories):
    parent_bytes = Path(parent_path).read_bytes()
    parent_hash = hashlib.sha256(parent_bytes).hexdigest()
    plan = split_plan(json.loads(parent_bytes), children)
    plan_text = json.dumps(plan, indent=2)+'\n'
    plan_hash = hashlib.sha256(plan_text.encode()).hexdigest()
    script = r'''from pathlib import Path
import hashlib,json,os,psutil
root=Path(ROOT);plan_text=PLAN_TEXT;plan=json.loads(plan_text)
if hashlib.sha256((root/'full-placement.json').read_bytes()).hexdigest()!=PARENT_HASH: raise RuntimeError('parent placement changed')
if psutil.disk_usage(str(root)).free<80*2**30: raise RuntimeError('disk below reserve')
def exact_file(path,text):
 if path.exists():
  if path.read_text()!=text: raise RuntimeError('existing view metadata differs: '+str(path))
 else:
  with path.open('x',newline='\n') as f:f.write(text)
plan_path=root/('full-topology-'+str(CHILDREN)+'.json')
exact_file(plan_path,plan_text)
if hashlib.sha256(plan_path.read_bytes()).hexdigest()!=PLAN_HASH:raise RuntimeError('logical placement bytes differ')
result={}
for child in range(CHILDREN):
 wi=INDEX*CHILDREN+child;layers={}
 for li,layer in enumerate(plan['layers']):
  owned=[eid for eid,owners in enumerate(layer) if wi in owners]
  if not owned:continue
  parent=root/'full-fused-compact'/f'layer_{li:02}'
  meta=json.loads((parent/'shard.json').read_text())
  if meta['placement_sha256']!=PARENT_HASH or meta['k']!=1 or not set(owned)<=set(meta['expert_ids']):raise RuntimeError('view outside parent ownership')
  expected=INVENTORY['fused_shards'][str(li)]
  if any(meta.get(k)!=v for k,v in expected.items()):raise RuntimeError('parent changed after preflight')
  dest=root/('full-views-'+str(CHILDREN))/('worker-'+str(wi))/f'layer_{li:02}'
  dest.mkdir(parents=True,exist_ok=True)
  for name in ['openvino_model.xml','openvino_model.bin']:
   if not (dest/name).exists():os.link(parent/name,dest/name)
   if not os.path.samefile(parent/name,dest/name):raise RuntimeError('view is not the parent hardlink')
  view=dict(meta,view_expert_ids=owned,parent_shard_sha256=hashlib.sha256((parent/'shard.json').read_bytes()).hexdigest(),
            parent_placement_sha256=PARENT_HASH,placement_sha256=PLAN_HASH)
  exact_file(dest/'shard.json',json.dumps(view,indent=2)+'\n')
  layers[str(li)]=dict(expected,view_expert_ids=owned,parent_shard_sha256=view['parent_shard_sha256'],hardlinks_verified=True)
 result[HOST+'-'+str(child)]=dict(INVENTORY,owned_layers=[int(li) for li in layers],fused_shards=layers,
      placement_sha256=PLAN_HASH,parent_placement_sha256=PARENT_HASH,worker_index=wi,
      ordered_replies_required=True)
print(json.dumps(result))
'''
    def prepare(item):
        pi, host = item
        code = script
        for name, value in [('ROOT',ROOT),('PLAN_TEXT',plan_text),('PARENT_HASH',parent_hash),
                            ('CHILDREN',children),('INDEX',pi),('INVENTORY',inventories[host]),
                            ('PLAN_HASH',plan_hash),('HOST',host)]:
            code = code.replace(name,repr(value))
        compile(code, '<remote-view-preparation>', 'exec')
        return json.loads(remote(host,code,180))
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results=list(pool.map(prepare,enumerate(HOSTS)))
    return dict(placement=plan,placement_sha256=plan_hash,parent_placement_sha256=parent_hash,
                physical_hosts=3,logical_workers=3*children,
                inventories={k:v for result in results for k,v in result.items()})
