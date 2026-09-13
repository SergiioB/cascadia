"""Wait for the existing baseline, then qualify the mapped-embedding binary once.

This finite native job only builds/tests the candidate; it never starts a full
model performance run or promotes it. It holds the baseline queue's task lock
while building, retains logs and refuses to overwrite an existing candidate.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path('C:/Users/devcloud/inkling-autolab')
FROZEN_SHA256 = 'f0bf021af04edd76f6fec5b77d8571225ba38f8f2315cbaac2bed189c04fc77a'
FIXTURE_HASH = '1f7cd0eb14a22662'


def state(status, **fields):
    path = ROOT / 'mmap-qualification-state.json'
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(dict(status=status, pid=os.getpid(), unix=time.time(), **fields), indent=2), encoding='utf-8')
    temp.replace(path)


def main():
    import msvcrt
    import psutil

    # Own state only after excluding another copy of this qualification job.
    with (ROOT / 'mmap-qualification.lock').open('a+b') as owner:
        owner.seek(0)
        msvcrt.locking(owner.fileno(), msvcrt.LK_NBLCK, 1)
        state('waiting_for_baseline')
        with (ROOT / 'baseline-queue.lock').open('a+b') as slot:
            deadline = time.monotonic() + 24 * 3600
            while True:
                status = json.loads((ROOT / 'baseline-queue-state.json').read_text())
                if status['status'] == 'failed':
                    raise RuntimeError('Baseline failed; inspect it before building candidates')
                if status['status'] == 'baseline_recorded_needs_review':
                    slot.seek(0)
                    try:
                        msvcrt.locking(slot.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        pass
                if time.monotonic() >= deadline:
                    raise TimeoutError('Baseline did not finish within 24 hours')
                time.sleep(30)
            frozen = ROOT / 'bin/full-decode.exe'
            assert hashlib.sha256(frozen.read_bytes()).hexdigest() == FROZEN_SHA256
            assert not (ROOT / 'bin/full-mmap-embed.exe').exists(), 'Inspect existing candidate first'
            for process in psutil.process_iter(['pid', 'exe', 'name']):
                exe = process.info['exe'] or ''
                if exe.lower().startswith(str(ROOT / 'bin').lower() + '\\') and Path(exe).name.lower().startswith('full-'):
                    raise RuntimeError(f'Full benchmark still active: {process.pid}')
            with (ROOT / 'test-mmap-embed.log').open('x', encoding='utf-8') as log:
                process = subprocess.Popen(['cmd.exe', '/c', str(ROOT / 'test-mmap-embed.bat')], stdout=log, stderr=subprocess.STDOUT)
                state('building_and_testing', launcher_pid=process.pid)
                try:
                    code = process.wait(timeout=3600)
                    if code:
                        raise RuntimeError(f'Native qualification exited {code}; inspect test-mmap-embed.log')
                finally:
                    if process.poll() is None:
                        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], check=False)
                        process.wait()
            plain = json.loads((ROOT / 'fixture-mmap-embed-plain.json').read_text())
            mapped = json.loads((ROOT / 'fixture-mmap-embed-observed.json').read_text())
            assert plain['embedding_mapped'] is False and mapped['embedding_mapped'] is True
            for result in (plain, mapped):
                assert result['scope'] == 'fixture_model_decode' and result['correctness_verified']
                assert result['output_hash'] == FIXTURE_HASH
                assert len(result['samples']) == 3
            assert [s['generated_ids'] for s in plain['samples']] == [s['generated_ids'] for s in mapped['samples']]
            assert hashlib.sha256(frozen.read_bytes()).hexdigest() == FROZEN_SHA256
            state('qualified_needs_full_trial', fixture_hash=FIXTURE_HASH,
                  binary_sha256=hashlib.sha256((ROOT / 'bin/full-mmap-embed.exe').read_bytes()).hexdigest(),
                  full_model_speedup_measured=False)


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        # A duplicate cannot overwrite the active owner's state.
        path = ROOT / 'mmap-qualification-state.json'
        if path.exists() and json.loads(path.read_text()).get('pid') == os.getpid():
            state('failed', error=str(error))
        raise
