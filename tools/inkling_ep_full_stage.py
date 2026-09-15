#!/usr/bin/env python3
"""Stage immutable full-model shards, with checksums and resumable progress.

The source serves an explicit allowlist to specified LAN addresses. The client
only writes below a marked deployment directory, preserves 80 GiB of disk and
12 GiB of available memory, and yields to existing inference/CI activity.
"""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path, PurePosixPath
import threading
import time
from urllib.parse import unquote, quote
import urllib.request


def safe_name(name):
    p = PurePosixPath(name)
    if not isinstance(name, str) or not name or p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name or str(p) != name:
        raise ValueError('unsafe relative model path')
    return name


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def source(args):
    root = args.root.resolve()
    names = {safe_name(n) for n in json.loads(args.files.read_text())}
    paths = {n: (root / n).resolve() for n in names}
    if any(not p.is_relative_to(root) or not p.is_file() for p in paths.values()):
        raise ValueError('source file is missing or outside export')
    allowed = set(args.allowed.split(','))
    index = {n: dict(bytes=p.stat().st_size) for n, p in paths.items()}
    encoded = json.dumps(index).encode()
    hashes, lock = {}, threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.client_address[0] not in allowed:
                self.send_error(403)
                return
            name = unquote(self.path).removeprefix('/')
            if name == 'index.json':
                self.send_response(200)
                self.send_header('Content-Length', str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
                return
            if name not in paths:
                self.send_error(404)
                return
            path = paths[name]
            stat = path.stat()
            identity = (stat.st_size, stat.st_mtime_ns)
            with lock:
                cached = hashes.get(name)
            sha = cached[1] if cached and cached[0] == identity else digest(path)
            after = path.stat()
            if (after.st_size, after.st_mtime_ns) != identity or stat.st_size != index[name]['bytes']:
                self.send_error(409, 'source changed')
                return
            with lock:
                hashes[name] = (identity, sha)
            self.send_response(200)
            self.send_header('Content-Length', str(stat.st_size))
            self.send_header('X-Content-SHA256', sha)
            self.end_headers()
            try:
                with path.open('rb') as f:
                    while chunk := f.read(2**20):
                        self.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer((args.bind, args.port), Handler)
    server.daemon_threads = True
    timer = threading.Timer(args.seconds, server.shutdown)
    timer.daemon = True
    timer.start()
    print(json.dumps(dict(state='ready', files=len(paths), bytes=sum(v['bytes'] for v in index.values()), lease_seconds=args.seconds)), flush=True)
    try:
        server.serve_forever()
    finally:
        timer.cancel()
        server.server_close()


def stage(args):
    import psutil
    from inkling_ep_guard import ci_active, protected
    root = args.root.resolve()
    if not (root / '.inkling_ep_deployment').is_file():
        raise ValueError('requires marked isolated deployment root')
    names = [safe_name(n) for n in json.loads(args.files.read_text())]
    if len(set(names)) != len(names):
        raise ValueError('duplicate files')
    target = root / 'full'
    target.mkdir(exist_ok=True)
    proc = psutil.Process()
    proc.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    proc.cpu_affinity([6, 7])
    before = protected()
    watched = [psutil.Process(p['pid']) for p in before if p['name'].lower() in {'ovms.exe', 'cascadia-node.exe'}]
    for p in watched:
        p.cpu_percent()
    started, sample_at = time.monotonic(), time.monotonic() + 1
    journal = root / 'full-stage-journal.json'
    verified = json.loads(journal.read_text()) if journal.exists() else {}
    transferred, complete = 0, 0
    pause_count, paused_seconds = 0, 0.0

    def check():
        nonlocal sample_at, pause_count, paused_seconds
        now = time.monotonic()
        if now - started > args.seconds:
            raise RuntimeError('transfer lease expired; safe to resume')
        if now < sample_at:
            return
        sample_at = now + 1
        if ci_active() or psutil.virtual_memory().available < 12 * 2**30:
            raise RuntimeError('CI active or memory below reserve; safe to resume')
        if psutil.disk_usage(str(root)).free < 80 * 2**30:
            raise RuntimeError('disk reserve reached during transfer; safe to resume')
        values = [p.cpu_percent() for p in watched if p.is_running()]
        if any(v > 20 for v in values):
            paused, quiet = time.monotonic(), 0
            pause_count += 1
            while quiet < 2:
                time.sleep(0.5)
                if time.monotonic()-paused > 60 or time.monotonic()-started > args.seconds:
                    raise RuntimeError('service remained busy or lease expired; safe to resume')
                if ci_active() or psutil.virtual_memory().available < 12*2**30 or psutil.disk_usage(str(root)).free < 80*2**30:
                    raise RuntimeError('CI/reserve limit while transfer paused; safe to resume')
                values = [p.cpu_percent() for p in watched if p.is_running()]
                quiet = 0 if any(v > 20 for v in values) else quiet + 0.5
            paused_seconds += time.monotonic()-paused
            sample_at = time.monotonic()+1

    def report(state, error=None):
        result = dict(state=state, files_complete=complete, files_total=len(names), transferred_bytes=transferred,
                      elapsed_seconds=time.monotonic()-started, error=error, protected_before=before,
                      service_pause_count=pause_count, service_pause_seconds=paused_seconds,
                      protected_after=protected(), source=args.source)
        tmp = root / 'full-stage-status.json.tmp'
        tmp.write_text(json.dumps(result, indent=2)+'\n')
        tmp.replace(root / 'full-stage-status.json')

    def save():
        tmp = journal.with_suffix('.tmp')
        tmp.write_text(json.dumps(verified)+'\n')
        tmp.replace(journal)
        report('running')

    if ci_active() or psutil.virtual_memory().available < 12 * 2**30:
        raise RuntimeError('host busy before transfer')
    with urllib.request.urlopen(args.source+'/index.json', timeout=60) as r:
        index = json.load(r)
    try:
        for name in names:
            check()
            dest = target / name
            if not dest.resolve().is_relative_to(target.resolve()):
                raise ValueError('destination escaped model root')
            meta = index[name]
            previous = verified.get(name)
            if dest.exists() and previous:
                st = dest.stat()
                if st.st_size == meta['bytes'] == previous['bytes'] and st.st_mtime_ns == previous['mtime_ns']:
                    complete += 1
                    continue
            if psutil.disk_usage(str(root)).free - meta['bytes'] < 80 * 2**30:
                raise RuntimeError('preserving 80 GiB free disk')
            dest.parent.mkdir(parents=True, exist_ok=True)
            with urllib.request.urlopen(args.source+'/'+quote(name, safe='/'), timeout=180) as response:
                sha = response.headers.get('X-Content-SHA256', '')
                if len(sha) != 64 or int(response.headers['Content-Length']) != meta['bytes']:
                    raise ValueError('missing checksum or source size mismatch')
                if dest.exists():
                    if dest.stat().st_size != meta['bytes'] or digest(dest) != sha:
                        raise RuntimeError('existing file differs; refusing replacement: '+name)
                else:
                    partial = dest.with_name(dest.name+'.part')
                    count, h, file_started = 0, hashlib.sha256(), time.monotonic()
                    with partial.open('wb') as f:
                        while chunk := response.read(2**20):
                            check()
                            f.write(chunk)
                            h.update(chunk)
                            count += len(chunk)
                            transferred += len(chunk)
                            while (delay := count/(args.mib_per_second * 2**20)-(time.monotonic()-file_started)) > 0:
                                time.sleep(min(delay, 0.1))
                    if count != meta['bytes'] or h.hexdigest() != sha:
                        raise RuntimeError('download checksum mismatch: '+name)
                    partial.replace(dest)
                verified[name] = dict(bytes=meta['bytes'], sha256=sha, mtime_ns=dest.stat().st_mtime_ns)
            complete += 1
            if complete % 16 == 0:
                save()
        save()
        report('complete')
    except Exception as e:
        save()
        report('paused', str(e))
        raise
    print(json.dumps(dict(state='complete', files=complete, transferred_bytes=transferred)), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['source', 'stage'])
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--files', type=Path, required=True)
    p.add_argument('--seconds', type=int, default=7200)
    p.add_argument('--bind')
    p.add_argument('--port', type=int, default=29484)
    p.add_argument('--allowed')
    p.add_argument('--source')
    p.add_argument('--mib-per-second', type=float, default=48)
    args = p.parse_args()
    if not 1 <= args.seconds <= 14400 or not 0 < args.mib_per_second <= 96:
        p.error('lease must be 1..14400 seconds and rate 0..96 MiB/s')
    if args.mode == 'source' and (not args.allowed or not args.bind):
        p.error('source needs --bind and --allowed')
    if args.mode == 'stage' and not args.source:
        p.error('stage needs --source')
    (source if args.mode == 'source' else stage)(args)


if __name__ == '__main__':
    main()
