#!/usr/bin/env python3
"""Short-lived, IP-restricted HTTP source for one existing expert layer.

Read-only: serves named .bin files and a SHA256 index, with no directory listing.
"""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import shutil
import threading
from urllib.parse import unquote


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--directory", type=Path, required=True)
    p.add_argument("--bind", required=True)
    p.add_argument("--port", type=int, required=True)
    p.add_argument("--allowed", required=True)
    p.add_argument("--seconds", type=int, default=600)
    a = p.parse_args()
    if not 1 <= a.seconds <= 1800:
        p.error("lease must be 1..1800 seconds")
    allowed = set(a.allowed.split(","))
    paths = {x.name: x for x in a.directory.iterdir() if x.is_file() and
             re.fullmatch(r"expert_(?:[0-9]{3}|shared[0-9]+)\.bin", x.name)}
    index = {}
    for name, path in sorted(paths.items()):
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(2**20), b""):
                h.update(chunk)
        index[name] = dict(bytes=path.stat().st_size, sha256=h.hexdigest())
    encoded = json.dumps(index).encode()
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.client_address[0] not in allowed:
                self.send_error(403)
                return
            name = unquote(self.path).removeprefix("/")
            if name != "index.json" and name not in paths:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(encoded) if name == "index.json" else index[name]["bytes"]))
            self.end_headers()
            if name == "index.json":
                self.wfile.write(encoded)
            else:
                with paths[name].open("rb") as f:
                    shutil.copyfileobj(f, self.wfile, 2**20)
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer((a.bind, a.port), Handler)
    server.daemon_threads = True
    timer = threading.Timer(a.seconds, server.shutdown)
    timer.daemon = True
    timer.start()
    print(json.dumps(dict(state="ready", bind=a.bind, port=a.port, files=len(index),
                          bytes=sum(v["bytes"] for v in index.values()), lease_seconds=a.seconds)), flush=True)
    try:
        server.serve_forever()
    finally:
        timer.cancel()
        server.server_close()


if __name__ == "__main__":
    main()
