#!/usr/bin/env python3
"""Run future Inkling exports on the configured 8xA100 host.

Pass exporter arguments after --. Model/output paths are on the remote host.
The default profile uses eight independent CUDA processes. Pass --processes 1
after -- for the original streaming or diagnostic modes. A host-local lock
prevents overlapping invocations of this launcher.
"""
import argparse
import json
from pathlib import Path, PurePosixPath
import shlex
import subprocess


def main():
    config = json.loads(Path(__file__).with_name('export-host.json').read_text())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default=config['host'])
    parser.add_argument('--identity-file', default=config['identity_file'])
    parser.add_argument('--remote-root', default=config['remote_root'])
    parser.add_argument('--print-command', action='store_true', help='show the command without connecting')
    parser.add_argument('exporter_args', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    forwarded = args.exporter_args
    if forwarded[:1] == ['--']:
        forwarded = forwarded[1:]
    if not forwarded:
        parser.error('pass exporter arguments after -- (model/output paths are remote)')
    root = PurePosixPath(args.remote_root)
    if not root.is_absolute():
        parser.error('--remote-root must be absolute')
    remote = [
        'flock', '-n', str(root / '.export.lock'),
        str(root / 'venv/bin/python'), '-u', str(root / 'repo/tools/export_inkling.py'),
        '--device', config['device'], '--workers', str(config['workers']),
        '--processes', str(config.get('processes', 1)),
        '--cuda-chunk-mib', str(config['cuda_chunk_mib']), *forwarded,
    ]
    command = [
        'ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
        '-o', 'IdentitiesOnly=yes', '-i', str(Path(args.identity_file).expanduser()),
        '--', args.host, shlex.join(remote),
    ]
    if args.print_command:
        print(shlex.join(command))
        return 0
    return subprocess.call(command)


if __name__ == '__main__':
    raise SystemExit(main())
