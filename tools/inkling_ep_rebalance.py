#!/usr/bin/env python3
"""Transactionally attenuate fused up weights to prevent FP16 GEMM overflow.

Only private deployment IRs change. Packed model bins remain the CPU oracle.
A journal restores interrupted layers before retry; both hardlinked K graphs
are marked unusable during mutation. Requires all benchmark processes stopped.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import xml.etree.ElementTree as ET

from inkling_ep_fused_export import Guard, scale_fp16

CHUNK = 4*2**20


def digest(path, guard=None):
    h = hashlib.sha256()
    with path.open('rb') as f:
        while data := f.read(CHUNK):
            if guard:
                guard.check()
            h.update(data)
    return h.hexdigest()


def atomic_json(path, value):
    tmp = path.with_suffix(path.suffix+'.new')
    with tmp.open('w') as f:
        json.dump(value, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def restore(src, compact):
    backup = src/'.rebalance'
    if not (backup/'journal.json').exists():
        # No mutation starts until the complete backup and journal are durable.
        shutil.rmtree(backup)
        return
    journal = json.loads((backup/'journal.json').read_text())
    if digest(backup/'up-scales.bin') != journal['backup_sha256']:
        raise RuntimeError('incomplete rollback backup; refuse mutation')
    with (src/'openvino_model.bin').open('r+b') as f, (backup/'up-scales.bin').open('rb') as old:
        f.seek(journal['offset'])
        shutil.copyfileobj(old, f, CHUNK)
        f.flush()
        os.fsync(f.fileno())
    atomic_json(src/'shard.json', journal['original'])
    atomic_json(compact/'shard.json', journal['compact'])
    shutil.rmtree(backup)


def rebalance(src, compact, exponent, guard=None):
    if not os.path.samefile(src/'openvino_model.bin', compact/'openvino_model.bin'):
        raise ValueError('K=1/K=8 must share the same private blob')
    backup = src/'.rebalance'
    if backup.exists():
        restore(src, compact)
    meta = json.loads((src/'shard.json').read_text())
    cm = json.loads((compact/'shard.json').read_text())
    if meta.get('up_scale_exponent') == exponent and meta['version'] == 2:
        if cm.get('up_scale_exponent') != exponent or cm['bin_sha256'] != meta['bin_sha256']:
            raise ValueError('compact scaling differs')
        return dict(layer=meta['layer'], already_complete=True, **{k:meta[k] for k in ['bin_sha256','up_scale_exponent','up_scale_relative_rms']})
    if meta['version'] != 1 or cm['version'] != 1 or meta['bin_sha256'] != cm['bin_sha256']:
        raise ValueError('expected unchanged version-1 IRs')
    if not 1 <= exponent <= 8:
        raise ValueError('exponent must be 1..8')
    tree = ET.fromstring((src/'openvino_model.xml').read_bytes())
    scales = [n.find('data') for n in tree.findall("./layers/layer[@type='Const']")
              if n.find('data').get('element_type') == 'f16' and len(n.find('data').get('shape').split(',')) == 4]
    if len(scales) != 3:
        raise ValueError('expected gate/up/down scale constants')
    offset, size = int(scales[1].get('offset')), int(scales[1].get('size'))
    if offset+size > meta['ir_bytes'] or size != meta['padded_experts']*meta['hidden_size']*meta['moe_intermediate']//16:
        raise ValueError('invalid up scale range')
    backup.mkdir()
    try:
        with (src/'openvino_model.bin').open('rb') as f, (backup/'up-scales.bin').open('xb') as old:
            f.seek(offset)
            left = size
            while left:
                if guard:
                    guard.check()
                raw = f.read(min(CHUNK,left))
                if not raw:
                    raise ValueError('short scale backup')
                old.write(raw)
                left -= len(raw)
            old.flush()
            os.fsync(old.fileno())
        journal = dict(original=meta, compact=cm, offset=offset, size=size,
                       backup_sha256=digest(backup/'up-scales.bin'))
        atomic_json(backup/'journal.json', journal)
        # Old and new workers both reject version 0 throughout the transaction.
        atomic_json(src/'shard.json', dict(meta,version=0))
        atomic_json(compact/'shard.json', dict(cm,version=0))
        error, norm = 0., 0.
        with (src/'openvino_model.bin').open('r+b') as f, (backup/'up-scales.bin').open('rb') as old:
            f.seek(offset)
            while raw := old.read(CHUNK):
                if guard:
                    guard.check()
                scaled, e, n = scale_fp16(raw, exponent)
                error += e
                norm += n
                f.write(scaled)
            f.flush()
            os.fsync(f.fileno())
        sha = digest(src/'openvino_model.bin', guard)
        change = dict(version=2, up_scale_exponent=exponent,
                      up_scale_relative_rms=(error/max(norm,1e-30))**0.5,
                      unscaled_bin_sha256=meta['bin_sha256'], bin_sha256=sha)
        atomic_json(src/'shard.json', dict(meta, **change))
        atomic_json(compact/'shard.json', dict(cm, **change))
        shutil.rmtree(backup)
        return dict(layer=meta['layer'], scale_bytes=size, **change)
    except BaseException:
        if backup.exists():
            restore(src, compact)
        raise


def main():
    import psutil
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', required=True, type=Path)
    p.add_argument('--exponent', type=int, default=4)
    p.add_argument('--seconds', type=int, default=2400)
    a = p.parse_args()
    root = a.root.resolve()
    if not (root/'.inkling_ep_deployment').exists() or not 1 <= a.seconds <= 3600:
        raise ValueError('requires marked private deployment and bounded lease')
    for proc in psutil.process_iter(['exe']):
        exe = (proc.info['exe'] or '').lower()
        if exe.startswith(str(root).lower()):
            raise RuntimeError('benchmark process still active')
    guard = Guard(root, 96, 12, pause_for_service=True)
    start = time.monotonic()
    results = []
    for src in sorted((root/'full-fused').glob('layer_*')):
        if time.monotonic()-start > a.seconds:
            raise RuntimeError('lease expired; completed layers can be resumed')
        guard.check()
        result = rebalance(src, root/'full-fused-compact'/src.name, a.exponent, guard)
        results.append(result)
        atomic_json(root/'full-rebalance-status.json', dict(state='running', layers=results, elapsed_seconds=time.monotonic()-start))
        print(json.dumps(result), flush=True)
    atomic_json(root/'full-rebalance-status.json', dict(state='complete', layers=results, elapsed_seconds=time.monotonic()-start))


if __name__ == '__main__':
    main()
