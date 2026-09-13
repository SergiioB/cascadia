"""Exercise configurable transfer endpoints and integrity through the public CLI."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pytest


def test_configurable_transfer_auth_resume_repair_and_ready_marker(tmp_path):
    scripts = Path(__file__).resolve().parent
    source, server_state, target = [tmp_path / name for name in ('source', 'server', 'target')]
    for path in (source, server_state, target):
        path.mkdir()
    payloads = {'partial.bin': os.urandom(65536), 'repair.bin': os.urandom(8192), 'empty.bin': b''}
    for name, payload in payloads.items():
        (source / name).write_bytes(payload)
    token = secrets.token_urlsafe(32)
    (server_state / 'token').write_text(token)
    (target / 'transfer-token').write_text(token)
    model = target / 'model'
    model.mkdir()
    (model / 'partial.bin.inkling-partial').write_bytes(payloads['partial.bin'][:1024])
    (model / 'repair.bin').write_bytes(b'x' * len(payloads['repair.bin']))
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    url = f'http://127.0.0.1:{port}'
    server = subprocess.Popen([sys.executable, str(scripts / 'transfer-server.py'),
                               '--root', str(source), '--state-dir', str(server_state),
                               '--bind', '127.0.0.1', '--client', '127.0.0.1', '--port', str(port)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    try:
        for _ in range(100):
            try:
                with urlopen(url + '/manifest', timeout=1):
                    pytest.fail('Unauthenticated request accepted')
            except HTTPError as error:
                assert error.code == 403
                break
            except URLError:
                assert server.poll() is None, 'Server exited during startup'
                time.sleep(.05)
        else:
            pytest.fail('Server did not start')
        with pytest.raises(HTTPError) as error:
            urlopen(Request(url + '/manifest', headers={'Authorization': 'Bearer wrong'}), timeout=2)
        assert error.value.code == 403
        with pytest.raises(HTTPError) as error:
            urlopen(Request(url + '/file/%2e%2e/secret', headers={'Authorization': 'Bearer ' + token}), timeout=2)
        assert error.value.code == 404
        run = subprocess.run([sys.executable, str(scripts / 'transfer-client.py'), '--root', str(target),
                              '--workers', '32', '--base-url', url, '--base-url', url],
                             capture_output=True, text=True, timeout=20)
        assert run.returncode == 0, run.stdout + run.stderr
        ready = json.loads((target / 'model-ready.json').read_text())
        assert ready['bytes'] == sum(map(len, payloads.values()))
        assert set(ready['files']) == set(payloads)
        for name, payload in payloads.items():
            assert (model / name).read_bytes() == payload
            assert ready['files'][name]['sha256'] == hashlib.sha256(payload).hexdigest()
        assert not list(model.glob('*.inkling-partial'))
        assert not (target / 'transfer-token').exists()
        assert json.loads((target / 'transfer-state.json').read_text())['status'] == 'verified'
        assert server.wait(timeout=5) == 0
        assert not (server_state / 'token').exists()
    finally:
        if server.poll() is None:
            server.terminate()
            server.wait(timeout=5)
