#!/usr/bin/env python3
"""Bundle immutable full-model run reports, exact trace metadata and SHA256s."""
import argparse
import gzip
import json
from pathlib import Path
import re

from inkling_ep_lan_control import ROOT, remote


def collect(run_dir, output):
    files={p.name:json.loads(p.read_text()) for p in Path(run_dir).glob('*.json')}
    label=files['completion.json']['label']
    if not re.fullmatch(r'[a-zA-Z0-9_-]+',label):raise ValueError('unsafe label')
    driver=files['charlie-'+label+'.json']
    if not driver.get('report'):raise ValueError('run has no completed native report')
    script='''from pathlib import Path
import hashlib,json
root=Path(ROOT);p=root/LABEL
hashes={}
for name in ['trace.json','report.json','tensors.f32']:
 with (p/name).open('rb') as f:hashes[name]=hashlib.file_digest(f,'sha256').hexdigest()
raw={name:(p/name).read_bytes().decode('utf-8') for name in ['trace.json','report.json']}
result={'trace.json':json.loads(raw['trace.json']),'sha256.json':hashes,'raw_json':raw}
argv=ARGV
if '--reference' in argv:
 ref=Path(argv[argv.index('--reference')+1]);proof=ref/'slice-provenance.json'
 if proof.exists():result['reference-slice-provenance.json']=json.loads(proof.read_text())
print(json.dumps(result))
'''.replace('ROOT',repr(ROOT)).replace('LABEL',repr(label)).replace('ARGV',repr(driver['status']['job']['argv']))
    result=json.loads(remote('charlie',script,180))
    if json.loads(result['raw_json']['report.json'])!=driver['report']:raise ValueError('native report changed since job completed')
    files.update(result)
    with Path(output).open('xb') as f:f.write(gzip.compress((json.dumps(files,indent=2)+'\n').encode(),mtime=0))
    return result['sha256.json']


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    print(json.dumps(collect(a.run,a.out)))


if __name__=='__main__':main()
