#!/usr/bin/env python3
"""Maintain this task's two loopback SSH forwards until verified PTL deployment.

Source HTTP stays on miner localhost. No private key leaves the controller.
The client reaches PTL localhost:18868 through the authorized Intel jump host.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, default=Path('/private/tmp/inkling-jump-transfer'))
    parser.add_argument('--hours', type=float, default=96)
    parser.add_argument('--port', type=int, default=18868, help='first remote PTL loopback port')
    parser.add_argument('--ptl-tunnels', type=int, default=1)
    parser.add_argument('--source-port', type=int, default=18868)
    parser.add_argument('--no-source-tunnel', action='store_true', help='reuse the existing miner forward')
    args = parser.parse_args()
    if args.hours <= 0:
        parser.error('hours must be positive')
    if not 1 <= args.ptl_tunnels <= 8 or not 1 <= args.port <= 65536 - args.ptl_tunnels or not 1 <= args.source_port <= 65535:
        parser.error('invalid port or tunnel count (maximum eight)')
    args.state_dir.mkdir(parents=True, exist_ok=True)
    lock = (args.state_dir / 'tunnels.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    stopped = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stopped.set())
    common = ['ssh', '-N', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
              '-o', 'ExitOnForwardFailure=yes', '-o', 'ServerAliveInterval=15',
              '-o', 'ServerAliveCountMax=3']
    commands = {f'ptl{i}': [*common, '-R', f'127.0.0.1:{args.port + i}:127.0.0.1:{args.source_port}',
                            'inkling-ptl-direct'] for i in range(args.ptl_tunnels)}
    if not args.no_source_tunnel:
        commands['miner'] = [*common, '-L', f'127.0.0.1:{args.source_port}:127.0.0.1:18868', 'miner']
    children = {}
    logs = {name: (args.state_dir / (name + '-tunnel.log')).open('a') for name in commands}
    deadline, check_at = time.monotonic() + args.hours * 3600, 0
    try:
        while not stopped.is_set() and time.monotonic() < deadline:
            for name, command in commands.items():
                if name not in children or children[name].poll() is not None:
                    children[name] = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                                       stdout=logs[name], stderr=logs[name], start_new_session=True)
            state = {'pid': os.getpid(), 'tunnel_pids': {k: p.pid for k, p in children.items()},
                     'updated_unix': time.time(), 'status': 'forwarding'}
            temporary = args.state_dir / 'tunnels-state.tmp'
            temporary.write_text(json.dumps(state, indent=2) + '\n')
            temporary.replace(args.state_dir / 'tunnels-state.json')
            if time.monotonic() >= check_at:
                try:
                    probe = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
                                            'inkling-ptl-direct',
                                            'if (Test-Path C:/Users/devcloud/inkling-autolab/model-ready.json) { Write-Output READY }'],
                                           capture_output=True, text=True, timeout=30)
                    if probe.returncode == 0 and probe.stdout.strip() == 'READY':
                        break
                except subprocess.TimeoutExpired:
                    pass
                check_at = time.monotonic() + 60
            stopped.wait(5)
    finally:
        for child in children.values():
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
                child.wait(timeout=10)
        for log in logs.values():
            log.close()
        (args.state_dir / 'tunnels-state.json').write_text(json.dumps({'pid': os.getpid(), 'status': 'stopped'}) + '\n')


if __name__ == '__main__':
    main()
