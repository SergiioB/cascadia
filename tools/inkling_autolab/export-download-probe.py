#!/usr/bin/env python3
"""Measure parallel bounded HF ranges without storing checkpoint shards."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import statistics
import time
from urllib.parse import quote
from urllib.request import Request, urlopen

REVISION = '828496eeae4c243ff1a22f7f28ff83694f2f7bc9'
BASE = 'https://huggingface.co/thinkingmachines/Inkling/resolve/' + REVISION + '/'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error('refusing to overwrite report')
    with urlopen(BASE + 'model.safetensors.index.json', timeout=120) as response:
        index = json.load(response)
    shards = sorted(set(index['weight_map'].values()))
    samples = []
    count = 128 * 1024**2

    def fetch(task):
        repetition, lane = task
        lo, hi = (repetition + 1) * count, (repetition + 2) * count - 1
        url = BASE + quote(shards[lane]) + f'?export_parallel_range={lo}-{hi}'
        request = Request(url, headers={'Range': f'bytes={lo}-{hi}', 'Accept-Encoding': 'identity'})
        with urlopen(request, timeout=120) as response:
            if response.status != 206 or not response.headers.get('Content-Range', '').startswith(f'bytes {lo}-{hi}/'):
                raise RuntimeError('Server did not honor the bounded range')
            received = 0
            while block := response.read(4 * 1024**2):
                received += len(block)
                if received > count:
                    raise RuntimeError('Range too large')
        assert received == count
        return received

    for repetition in range(2):
        for workers in ([4, 8, 16] if repetition == 0 else [16, 8, 4]):
            start = time.monotonic()
            with ThreadPoolExecutor(max_workers=workers) as pool:
                received = sum(pool.map(fetch, [(repetition, lane) for lane in range(workers)]))
            seconds = time.monotonic() - start
            sample = {'workers': workers, 'repetition': repetition, 'bytes': received,
                      'seconds': seconds, 'bytes_per_second': received / seconds}
            samples.append(sample)
            print(json.dumps(sample), flush=True)
    report = {'scope': 'parallel_bounded_http_ranges_discarded', 'full_download_measured': False,
              'revision': REVISION, 'source_bytes': index['metadata']['total_size'], 'samples': samples,
              'median_bytes_per_second': {str(n): statistics.median(s['bytes_per_second'] for s in samples if s['workers'] == n)
                                          for n in [4, 8, 16]}}
    args.out.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
