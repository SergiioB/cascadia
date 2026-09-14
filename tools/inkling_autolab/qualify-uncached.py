"""After040 finishes, build/test the optional uncached-read candidate.

Finite, restart-visible native job. Never starts a full performance trial.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path('C:/Users/devcloud/inkling-autolab')
STATE = ROOT / 'uncached-qualification-state.json'
FROZEN = {
    'full-owned-shared.exe': '0bd35a624e3fb7e5f0b78bfdf4202f548095ebb90b6f71137bb8d9683b7b96cb',
    'full-decode.exe': 'f0bf021af04edd76f6fec5b77d8571225ba38f8f2315cbaac2bed189c04fc77a',
    'full-read-buffers.exe': '497b4bc83802bb7a21ced260e68cad49353ba5b78f851b4bf982a5c9360ca861',
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
    with (ROOT / 'uncached-qualification.lock').open('a+b') as owner:
        owner.seek(0)
        msvcrt.locking(owner.fileno(), msvcrt.LK_NBLCK, 1)
        state('waiting_for_040')
        with (ROOT / 'baseline-queue.lock').open('a+b') as slot:
            deadline = time.monotonic() + 120 * 60
            while True:
                report = ROOT / '040-owned-shared.json'
                if report.exists() and not active_full_processes():
                    result = json.loads(report.read_text())
                    assert result['scope'] == 'full_large_model_decode'
                    assert result['correctness_verified']
                    assert result['output_hash'] == 'ce0fbb9a116d3d09'
                    assert len(result['samples']) == 3
                    assert result['owned_shared_bytes'] == 4076863488
                    slot.seek(0)
                    try:
                        msvcrt.locking(slot.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        pass
                if time.monotonic() >= deadline:
                    raise TimeoutError('No completed040 trial within120 minutes')
                time.sleep(15)
            check_frozen()
            candidate = ROOT / 'bin/full-uncached.exe'
            assert not candidate.exists(), 'Inspect existing candidate before rebuilding'
            assert not active_full_processes(), 'Another full benchmark started'
            with (ROOT / 'test-uncached.log').open('x', encoding='utf-8') as log:
                process = subprocess.Popen(['cmd.exe', '/c', str(ROOT / 'test-uncached.bat')],
                                           stdout=log, stderr=subprocess.STDOUT)
                state('building_and_testing', launcher_pid=process.pid)
                try:
                    if process.wait(timeout=3600):
                        raise RuntimeError('Native qualification failed; inspect test-uncached.log')
                finally:
                    if process.poll() is None:
                        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], check=False)
                        process.wait()
            for mode in ('plain', 'owned', 'uncached'):
                result = json.loads((ROOT / f'fixture-uncached-{mode}.json').read_text())
                assert result['scope'] == 'fixture_model_decode' and result['correctness_verified']
                assert result['output_hash'] == '1f7cd0eb14a22662'
                assert len(result['samples']) == 3
                assert result['embedding_mapped']
                assert result['owned_shared_bytes'] == (0 if mode == 'plain' else 20736)
            check_frozen()
            assert hashlib.sha256((ROOT / 'run-full.ps1').read_bytes()).hexdigest() == 'dab2d7f1edb84eba7bf3beaf9a3ef1f1255b0b06dafad386c2e0e5aca8e2aad6', 'Wrapper changed; inspect before replacing'
            wrapper = ROOT / 'run-full-uncached.ps1'
            (ROOT / 'run-full.ps1').write_bytes(wrapper.read_bytes())
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
