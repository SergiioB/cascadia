"""Freeze a top_k3 tiny reference using a previously qualified binary.

Only a separate tiny manifest changes. Every weight file is copied and SHA
checked. This frozen-runtime I/O oracle supplements the original HF top_k2
fixture; it is not a new Hugging Face top_k3 accuracy claim.
"""
import argparse,hashlib,json,os,shutil,subprocess
from pathlib import Path

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def prepare(binary,source_fixture,cases,directory,expected_sha):
 assert sha(binary)==expected_sha and not directory.exists()
 directory.mkdir();fixture=directory/'model';shutil.copytree(source_fixture,fixture)
 source_manifest=json.loads((source_fixture/'manifest.json').read_text());assert source_manifest['top_k']==2 and source_manifest['num_experts']==8
 candidate=source_manifest.copy();candidate['top_k']=3;(fixture/'manifest.json').write_text(json.dumps(candidate,indent=2)+'\n')
 weights=[]
 for p in sorted(source_fixture.rglob('*')):
  if p.is_file() and p.name!='manifest.json':
   relative=p.relative_to(source_fixture);expected=sha(p);assert sha(fixture/relative)==expected;weights.append(dict(path=str(relative),sha256=expected))
 original=json.loads(cases.read_text());assert len(original)==1
 unchecked=[dict(name='tiny_top3_legacy',prompt_ids=original[0]['prompt_ids'])];unchecked_cases=directory/'cases-unchecked.json';unchecked_cases.write_text(json.dumps(unchecked,indent=2)+'\n')
 env=os.environ.copy();env.update(RAYON_NUM_THREADS='16',CASCADIA_INKLING_SERIAL_EXPERTS='0',CASCADIA_INKLING_SEQ_READS='0',CASCADIA_INKLING_PIN_EXPERTS='0',CASCADIA_BF16_GEMV_ROWS='2',CASCADIA_INT4_GEMV_ROWS='4',CASCADIA_INKLING_MMAP_EMBED='1',CASCADIA_INKLING_REUSE_READ_BUFFERS='1',CASCADIA_INKLING_SKIP_BULK_PREFETCH='1',CASCADIA_INKLING_OWN_SHARED='1',CASCADIA_INKLING_UNCACHED_READS='1',CASCADIA_INKLING_PIPELINE_READS='1',CASCADIA_INKLING_EXPERT_CACHE_MIB='1',CASCADIA_INKLING_PREFILL_READS='1',CASCADIA_INKLING_CACHE_RESET_HISTORY='1',CASCADIA_INKLING_CACHE_DECAY_REQUESTS='32',CASCADIA_INKLING_CACHE_RECENT_TIES='1',CASCADIA_INKLING_PREDICT_READS='0',CASCADIA_INKLING_EARLY_PREDICT_READS='0',CASCADIA_INKLING_SECOND_PREDICT_READS='0',CASCADIA_INKLING_SECOND_PREDICT_RANK='2',CASCADIA_INKLING_THIRD_PREDICT_READS='0')
 def run(name,case_file):
  out=directory/(name+'.json');routes=directory/(name+'-routes.json');prediction=directory/(name+'-predicted.json');log=directory/(name+'.log')
  cmd=[str(binary),'--export',str(fixture),'--cases',str(case_file),'--allow-fixture','--tokens','8','--samples','3','--out',str(out),'--route-trace',str(routes),'--prediction-trace',str(prediction)]
  with log.open('x') as f:subprocess.run(cmd,env=env,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=180)
  return json.loads(out.read_text())
 raw=run('reference-unchecked',unchecked_cases);assert raw['correctness_verified'] is False and raw['scope']=='fixture_model_decode' and len(raw['samples'])==3
 ids=raw['samples'][0]['generated_ids'];assert len(ids)==8 and all(s['generated_ids']==ids and s['decode_steps']==7 for s in raw['samples'])
 checked=[dict(**unchecked[0],greedy_ids=ids)];checked_cases=directory/'cases-reference.json';checked_cases.write_text(json.dumps(checked,indent=2)+'\n')
 verified=run('reference',checked_cases);assert verified['correctness_verified'] and verified['output_hash']==raw['output_hash'] and verified['expert_cache']==raw['expert_cache']
 actual=json.loads((directory/'reference-routes.json').read_text());prediction=json.loads((directory/'reference-predicted.json').read_text());assert actual['manifest']['top_k']==3 and not prediction['prefetch_performed']
 proof=dict(scope='tiny_top3_frozen_runtime_reference',binary_sha256=expected_sha,source_manifest_sha256=sha(source_fixture/'manifest.json'),variant_manifest_sha256=sha(fixture/'manifest.json'),manifest_only_change='top_k2 to3',all_weight_bytes_unchanged=True,weights=weights,output_hash=verified['output_hash'],generated_ids=ids,expert_cache=verified['expert_cache'],hf_top3_oracle=False,reference_binary_scope='previously qualified runtime before any third-read implementation',artifacts=[dict(path=p.name,sha256=sha(p)) for p in sorted(directory.iterdir()) if p.is_file()])
 with (directory/'preparation.json').open('x') as f:json.dump(proof,f,indent=2);f.write('\n')
 return {k:v for k,v in proof.items() if k not in ['weights','artifacts']}
def main():
 p=argparse.ArgumentParser(description=__doc__)
 for n in ['binary','source-fixture','cases','directory']:p.add_argument('--'+n,type=Path,required=True)
 p.add_argument('--expected-sha',required=True);a=p.parse_args();print(json.dumps(prepare(a.binary,a.source_fixture,a.cases,a.directory,a.expected_sha),indent=2))
if __name__=='__main__':main()
