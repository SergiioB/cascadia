"""Summarize adjacent sampler intervals for one exact process lifetime.

These are sampled lifetime statistics, including load and prefill. Disk counters
are machine-wide; page faults include soft faults. Neither is model disk traffic.
"""
import argparse
import hashlib
import json
from pathlib import Path


def analyze(rows, pid, created_unix):
    def process(row):
        matches = [p for p in row['processes']
                   if p['pid'] == pid and p['created_unix'] == created_unix]
        if len(matches) > 1:
            raise ValueError('duplicate process identity')
        return matches[0] if matches else None

    samples = [(r, process(r)) for r in rows]
    selected = [(r, p) for r, p in samples if p is not None]
    if len(selected) < 2:
        raise ValueError('at least two samples of the exact process are required')
    totals = dict(seconds=0., user=0., kernel=0., faults=0, disk_read=0, process_read=0)
    count = 0
    for (a, pa), (b, pb) in zip(samples, samples[1:]):
        if pa is None or pb is None:
            continue
        delta = {
            'seconds': b['monotonic'] - a['monotonic'],
            'user': pb['cpu_seconds']['user'] - pa['cpu_seconds']['user'],
            'kernel': pb['cpu_seconds']['system'] - pa['cpu_seconds']['system'],
            'faults': pb['memory_info']['num_page_faults'] - pa['memory_info']['num_page_faults'],
            'disk_read': b['machine_disk_io_cumulative']['read_bytes'] - a['machine_disk_io_cumulative']['read_bytes'],
            'process_read': pb['io_cumulative']['read_bytes'] - pa['io_cumulative']['read_bytes'],
        }
        if delta['seconds'] <= 0 or any(v < 0 for v in delta.values()):
            raise ValueError('unordered samples or counter reset')
        for key, value in delta.items():
            totals[key] += value
        count += 1
    if not count:
        raise ValueError('no adjacent intervals for the selected process')
    cpu = totals['user'] + totals['kernel']
    seconds = totals['seconds']
    return {
        'scope': 'full_process_lifetime_sampled_resources',
        'includes_load_prefill_decode': True,
        'pid': pid, 'created_unix': created_unix,
        'executable': selected[0][1]['executable'],
        'intervals': count, 'sampled_seconds': seconds,
        'cpu_core_equivalents': cpu / seconds,
        'kernel_fraction': totals['kernel'] / cpu if cpu else None,
        'faults_per_second_includes_soft': totals['faults'] / seconds,
        'machine_disk_read_bytes_per_second': totals['disk_read'] / seconds,
        'process_read_bytes_per_second': totals['process_read'] / seconds,
        'min_available_RAM_bytes': min(r['memory']['available'] for r, _ in selected),
        'max_private_bytes': max(p['memory_info']['private'] for _, p in selected),
        'max_rss_bytes': max(p['memory_info']['rss'] for _, p in selected),
        'max_machine_swap_used_bytes': max(r['swap']['used'] for r, _ in selected),
        'caveats': [
            'Disk counters are machine-wide and cannot be exclusively attributed to the model.',
            'Page faults include soft faults; they are not all storage reads.',
            'Sampled lifetime includes loading and prefills; this is not decode-only.',
            'Only adjacent snapshots containing the same PID and creation time contribute rates.',
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples', type=Path, required=True)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--created-unix', type=float, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error('refusing to overwrite analysis')
    source = args.samples.read_bytes()
    result = analyze([json.loads(line) for line in source.splitlines()], args.pid, args.created_unix)
    result['source_sha256'] = hashlib.sha256(source).hexdigest()
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
