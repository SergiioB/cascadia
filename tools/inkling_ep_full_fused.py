#!/usr/bin/env python3
"""Build each full-model fused shard after its verified downloads complete.

Keeps the original packed weights for CPU parity. K=1 and K=8 graphs hardlink
the same GPU blob. Runs under the existing exporter memory/disk/service guard.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
import urllib.request

from inkling_ep_fused_export import build, compact, Guard


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--index', type=int, required=True)
    p.add_argument('--seconds', type=int, default=10800)
    p.add_argument('--source', default='http://192.168.0.235:29484')
    p.add_argument('--mib-per-second', type=float, default=48)
    a = p.parse_args()
    root = a.root.resolve()
    if not (root/'.inkling_ep_deployment').is_file() or not 1 <= a.seconds <= 14400:
        raise ValueError('requires isolated root and bounded lease')
    if not 0 < a.mib_per_second <= 96:
        raise ValueError('export rate must be 0..96 MiB/s')
    plan = json.loads((root/'full-placement.json').read_text())
    if not 0 <= a.index < len(plan['workers']):
        raise ValueError('worker index')
    guard = Guard(root, a.mib_per_second, 12, pause_for_service=True)
    model = root/'full'
    model.mkdir(exist_ok=True)
    # Charlie's sorted download list reaches the manifest after expert files.
    # Fetch only this small file early, preserving the source bytes exactly.
    manifest = model/'manifest.json'
    if not manifest.exists():
        with urllib.request.urlopen(a.source+'/manifest.json', timeout=30) as response:
            data = response.read()
            if hashlib.sha256(data).hexdigest() != response.headers['X-Content-SHA256']:
                raise ValueError('manifest checksum mismatch')
        with manifest.open('xb') as f:
            f.write(data)
    started = time.monotonic()
    completed = []
    for li, layer in enumerate(plan['layers']):
        ids = [i for i, owners in enumerate(layer) if a.index in owners]
        if not ids:
            continue
        paths = {i: f'experts/layer_{li:02}/'+(f'expert_{i:03}.bin' if i < plan['num_experts'] else f'expert_shared{i-plan["num_experts"]}.bin') for i in ids}
        while True:
            guard.check()
            if time.monotonic()-started > a.seconds:
                raise RuntimeError('export lease expired; safe to resume completed layers')
            journal = root/'full-stage-journal.json'
            verified = json.loads(journal.read_text()) if journal.exists() else {}
            if all(name in verified for name in paths.values()):
                break
            time.sleep(1)
        out = root/'full-fused'
        dest = out/f'layer_{li:02}'
        if not dest.exists():
            build(argparse.Namespace(recipe=root/'fused-recipe-v1.json', export=model,
                  placement=root/'full-placement.json', index=a.index, layer=li,
                  out=out, guarded=True, rate_mib=a.mib_per_second, reserve_gib=12, pause_for_service=True))
        meta = json.loads((dest/'shard.json').read_text())
        if meta['expert_ids'] != ids or meta['source_sha256'] != {str(i):verified[name]['sha256'] for i,name in paths.items()}:
            raise RuntimeError('fused shard does not match verified source/ownership')
        k1 = root/'full-fused-compact'/f'layer_{li:02}'
        if not k1.exists():
            compact(dest, k1)
        completed.append(li)
        status = dict(state='running', completed_layers=completed, elapsed_seconds=time.monotonic()-started)
        (root/'full-fused-status.json').write_text(json.dumps(status)+'\n')
    status['state'] = 'complete'
    (root/'full-fused-status.json').write_text(json.dumps(status)+'\n')


if __name__ == '__main__':
    main()
