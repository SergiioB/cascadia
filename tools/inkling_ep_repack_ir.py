#!/usr/bin/env python3
"""Reconstruct existing OV IR blobs from local packed bins, with exact SHA256.

The recipe contains original XML, offsets, tiny scalar constants and the source
IR blob hash. No OpenVINO install, export, dequantization or quantization occurs.
Only files under the isolated deployment root are created. Run on Windows.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import shutil
import time

import psutil
from inkling_ep_guard import ci_active


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', required=True, type=Path)
    p.add_argument('--recipe', required=True, type=Path)
    a = p.parse_args()
    root = a.root.resolve()
    if not (root/'.inkling_ep_deployment').is_file():
        raise ValueError('requires an isolated marked deployment root')
    proc = psutil.Process()
    proc.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    proc.cpu_affinity([6, 7])
    recipes = json.loads(a.recipe.read_text())
    files = json.loads((root/'stage-files.json').read_text())
    started = time.monotonic()
    written = 0
    for name in files:
        if Path(name).name != name or not name.endswith('.bin'):
            raise ValueError('unsafe expert filename')
        if ci_active() or psutil.virtual_memory().available < 12*2**30:
            raise RuntimeError('CI became active or memory reserve reached')
        recipe = recipes[name]
        source = (root/'layer/experts/layer_02'/name).read_bytes()
        blob = bytearray(recipe['bytes'])
        for c in recipe['constants']:
            value = source[c['source_offset']:c['source_offset']+c['size']] if 'source_offset' in c else bytes.fromhex(c['hex'])
            if len(value) != c['size'] or c['offset']+c['size'] > len(blob):
                raise ValueError('invalid constant range')
            blob[c['offset']:c['offset']+c['size']] = value
        if hashlib.sha256(blob).hexdigest() != recipe['sha256']:
            raise RuntimeError('repacked IR differs from original: '+name)
        dest = root/'layer/experts_ov/layer_02'/Path(name).stem
        dest.mkdir(parents=True, exist_ok=True)
        for filename, value in [('openvino_model.bin',blob),('openvino_model.xml',base64.b64decode(recipe['xml']))]:
            path = dest/filename
            if path.exists():
                if hashlib.sha256(path.read_bytes()).digest() != hashlib.sha256(value).digest():
                    raise RuntimeError('existing IR differs: '+str(path))
                continue
            if shutil.disk_usage(root).free-len(value) < 80*2**30:
                raise RuntimeError('preserving 80 GiB free disk')
            with path.open('xb') as f:
                f.write(value)
            written += len(value)
        delay = written/(48*2**20) - (time.monotonic()-started)
        if delay > 0:
            time.sleep(delay)
    report = dict(files=len(files), written_bytes=written, elapsed_seconds=time.monotonic()-started,
                  all_repacked_blobs_match_original_sha256=True)
    (root/'gpu-repack.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
