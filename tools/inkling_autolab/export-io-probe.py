#!/usr/bin/env python3
"""Bounded cold-I/O and pinned-checkpoint download probes for export cost estimates.

Writes 1 GiB of disposable random data with four workers and Linux O_DIRECT,
then reads it with O_DIRECT. Downloads three 256 MiB ranges without storing
them. These short probes are not a timed full-model export or download.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import mmap
import os
from pathlib import Path
import statistics
import tempfile
import time
from urllib.parse import quote
from urllib.request import Request, urlopen

REVISION = '828496eeae4c243ff1a22f7f28ff83694f2f7bc9'
BASE = 'https://huggingface.co/thinkingmachines/Inkling/resolve/' + REVISION + '/'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error('refusing to overwrite report')
    args.work_dir.mkdir(parents=True, exist_ok=True)
    with urlopen(BASE + 'model.safetensors.index.json', timeout=120) as response:
        index = json.load(response)
    report = {'revision': REVISION, 'source_bytes': index.get('metadata', {}).get('total_size'),
              'scope': 'short_direct_io_and_http_range_probes', 'full_export_measured': False}
    total, piece = 1024**3, 16 * 1024**2
    source = mmap.mmap(-1, total)
    for offset in range(0, total, piece):
        source[offset:offset + piece] = os.urandom(piece)
    with tempfile.TemporaryDirectory(prefix='export-io-', dir=args.work_dir) as temp:
        paths = [Path(temp) / f'probe-{i}' for i in range(4)]

        def write_file(i):
            fd = os.open(paths[i], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_DIRECT, 0o600)
            view = memoryview(source)
            try:
                for offset in range(i * total // 4, (i + 1) * total // 4, piece):
                    assert os.write(fd, view[offset:offset + piece]) == piece
                os.fsync(fd)
            finally:
                view.release()
                os.close(fd)

        def read_file(i):
            fd = os.open(paths[i], os.O_RDONLY | os.O_DIRECT)
            buffer = mmap.mmap(-1, piece)
            try:
                for offset in range(i * total // 4, (i + 1) * total // 4, piece):
                    assert os.readv(fd, [buffer]) == piece
                    # Sample the returned data without including full SHA cost in throughput.
                    assert buffer[:64] == source[offset:offset + 64]
            finally:
                buffer.close()
                os.close(fd)

        for name, fn in [('write', write_file), ('read', read_file)]:
            start = time.monotonic()
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(fn, range(4)))
            seconds = time.monotonic() - start
            report['direct_' + name] = {'bytes': total, 'seconds': seconds,
                                       'bytes_per_second': total / seconds, 'workers': 4}
            print(name, report['direct_' + name], flush=True)
    source.close()
    shard = sorted(set(index['weight_map'].values()))[0]
    samples = []
    for repetition in range(3):
        count = 256 * 1024**2
        lo, hi = repetition * count, (repetition + 1) * count - 1
        url = BASE + quote(shard) + f'?export_io_range={lo}-{hi}'
        request = Request(url, headers={'Range': f'bytes={lo}-{hi}', 'Accept-Encoding': 'identity'})
        start = time.monotonic()
        with urlopen(request, timeout=120) as response:
            if response.status != 206 or not response.headers.get('Content-Range', '').startswith(f'bytes {lo}-{hi}/'):
                raise RuntimeError('Server did not honor the bounded byte range')
            received = 0
            while block := response.read(4 * 1024**2):
                received += len(block)
                if received > count:
                    raise RuntimeError('Download exceeded requested range')
        assert received == count
        seconds = time.monotonic() - start
        samples.append({'bytes': count, 'seconds': seconds, 'bytes_per_second': count / seconds})
        print('download', samples[-1], flush=True)
    report['http_range_samples'] = samples
    report['http_range_median_bytes_per_second'] = statistics.median(s['bytes_per_second'] for s in samples)
    args.out.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
