"""After the verified direct trial exits, build/test the read-buffer candidate.

Finite, restart-visible native job. Never starts a full performance trial.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path('C:/Users/devcloud/inkling-autolab')
STATE = ROOT / 'read-buffers-qualification-state.json'
FROZEN = {
    'full-decode.exe': 'f0bf021af04edd76f6fec5b77d8571225ba38f8f2315cbaac2bed189c04fc77a',
    'full-mmap-embed.exe': '95f664c6a4af52f5dcdaf5fe6d12886cb45c6bb70edecb79a65d8b52daf5ec6d',
}


def state(status, **fields):
    temp = STATE.with_suffix('.tmp')
    temp.write_text(json.dumps(dict(status=status, pid=os.getpid(), unix=time.time(), **fields), indent=2))
    temp.replace(STATE)


def check_frozen():
    for name, expected in FROZEN.items():
        assert hashlib.sha256((ROOT / 'bin' / name).read_bytes()).hexdigest() == expected, name


def active_full_processes():
    import psutil
    prefix = str((ROOT / 'bin').resolve()).lower() + '\\'
    return [p.pid for p in psutil.process_iter(['exe', 'name'])
            if (p.info['exe'] or '').lower().startswith(prefix)
            and (p.info['name'] or '').lower().startswith('full-')]


def main():
    import msvcrt
    with (ROOT / 'read-buffers-qualification.lock').open('a+b') as owner:
        owner.seek(0)
        msvcrt.locking(owner.fileno(), msvcrt.LK_NBLCK, 1)
        state('waiting_for_direct_trial')
        with (ROOT / 'baseline-queue.lock').open('a+b') as slot:
            deadline = time.monotonic() + 90 * 60
            while True:
                report = ROOT / '034-direct.json'
                if report.exists() and not active_full_processes():
                    result = json.loads(report.read_text())
                    assert result['scope'] == 'full_large_model_decode'
                    assert result['correctness_verified']
                    assert result['output_hash'] == 'ce0fbb9a116d3d09'
                    assert len(result['samples']) == 3
                    slot.seek(0)
                    try:
                        msvcrt.locking(slot.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        pass
                if time.monotonic() >= deadline:
                    raise TimeoutError('No verified direct trial within 90 minutes')
                time.sleep(15)
            check_frozen()
            candidate = ROOT / 'bin/full-read-buffers.exe'
            assert not candidate.exists(), 'Inspect existing candidate before rebuilding'
            assert not active_full_processes(), 'Another full benchmark started'
            with (ROOT / 'test-read-buffers.log').open('x', encoding='utf-8') as log:
                process = subprocess.Popen(['cmd.exe', '/c', str(ROOT / 'test-read-buffers.bat')],
                                           stdout=log, stderr=subprocess.STDOUT)
                state('building_and_testing', launcher_pid=process.pid)
                try:
                    if process.wait(timeout=3600):
                        raise RuntimeError('Native qualification failed; inspect test-read-buffers.log')
                finally:
                    if process.poll() is None:
                        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], check=False)
                        process.wait()
            for mode in ('baseline', 'reuse', 'nohint', 'mapped'):
                result = json.loads((ROOT / f'fixture-read-buffers-{mode}.json').read_text())
                assert result['scope'] == 'fixture_model_decode' and result['correctness_verified']
                assert result['output_hash'] == '1f7cd0eb14a22662'
                assert len(result['samples']) == 3
                assert result['embedding_mapped'] == (mode == 'mapped')
            check_frozen()
            state('qualified_needs_full_trial', fixture_hash='1f7cd0eb14a22662',
                  binary_sha256=hashlib.sha256(candidate.read_bytes()).hexdigest(),
                  full_model_speedup_measured=False)


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        if STATE.exists() and json.loads(STATE.read_text()).get('pid') == os.getpid():
            state('failed', error=str(error))
        raise
