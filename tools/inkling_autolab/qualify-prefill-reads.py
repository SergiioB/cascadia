"""After049/050/051 finish, build/test bounded prefill expert reads.

Finite, restart-visible native job. Never starts a full performance trial.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import tarfile

ROOT = Path('C:/Users/devcloud/inkling-autolab')
STATE = ROOT / 'prefill-read-qualification-state.json'
FROZEN = {
    'full-expert-cache.exe': 'fe913c6844813bfa48b380e886c477224b77b3462f5e0b4c752345f8b2f61e88',
    'full-pipeline.exe': '8305491ebbc4bacc09fdb3aeccbe331b153e0fd79d34a273baef2ddb5d593e8b',
    'full-uncached.exe': '9aa189f74b797679d91603fc6d3dfd34dc6ad3bde94ebdae95ef5526b58e81a2',
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
    with (ROOT / 'prefill-read-qualification.lock').open('a+b') as owner:
        owner.seek(0)
        msvcrt.locking(owner.fileno(), msvcrt.LK_NBLCK, 1)
        state('waiting_for_cache_comparison')
        with (ROOT / 'baseline-queue.lock').open('a+b') as slot:
            deadline = time.monotonic() + 120 * 60
            while True:
                reports = [ROOT / name for name in ('049-cache-0.json', '050-cache-64.json', '051-cache-128.json')]
                if all(p.exists() for p in reports) and not active_full_processes():
                    for report, mib in zip(reports, (0, 64, 128)):
                        result = json.loads(report.read_text())
                        assert result['scope'] == 'full_large_model_decode'
                        assert result['correctness_verified'] and result['output_hash'] == 'ce0fbb9a116d3d09'
                        assert len(result['samples']) == 3 and result['owned_shared_bytes'] == 4076863488
                        assert result['uncached_read_effective'] and result['uncached_read_fallbacks'] == 0
                        assert result['expert_cache']['capacity_bytes'] == mib * 64 * 1024 * 1024
                    slot.seek(0)
                    try:
                        msvcrt.locking(slot.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        pass
                if time.monotonic() >= deadline:
                    raise TimeoutError('No completed cache comparison within120 minutes')
                time.sleep(15)
            check_frozen()
            candidate = ROOT / 'bin/full-prefill-reads.exe'
            assert not candidate.exists(), 'Inspect existing candidate before rebuilding'
            assert not active_full_processes(), 'Another full benchmark started'
            manifest = json.loads((ROOT / 'prefill-read-source.json').read_text())
            for item in manifest:
                target = ROOT / 'repo' / item['path']
                if item['previous_sha256'] is None:
                    assert not target.exists(), item['path']
                else:
                    assert hashlib.sha256(target.read_bytes()).hexdigest() == item['previous_sha256'], item['path']
            with tarfile.open(ROOT / 'prefill-read-source.tar') as archive:
                assert sorted(archive.getnames()) == sorted(item['path'] for item in manifest)
                for item in manifest:
                    data = archive.extractfile(item['path']).read()
                    assert hashlib.sha256(data).hexdigest() == item['candidate_sha256']
                    (ROOT / 'repo' / item['path']).write_bytes(data)
            with (ROOT / 'test-prefill-reads.log').open('x', encoding='utf-8') as log:
                process = subprocess.Popen(['cmd.exe', '/c', str(ROOT / 'test-prefill-reads.bat')],
                                           stdout=log, stderr=subprocess.STDOUT)
                state('building_and_testing', launcher_pid=process.pid)
                try:
                    if process.wait(timeout=3600):
                        raise RuntimeError('Native qualification failed; inspect test-prefill-reads.log')
                finally:
                    if process.poll() is None:
                        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], check=False)
                        process.wait()
            for mode in ('off', 'on', 'uncached', 'cache_off', 'pipeline_off', 'direct', 'history_reset'):
                result = json.loads((ROOT / f'fixture-prefill-reads-{mode}.json').read_text())
                assert result['scope'] == 'fixture_model_decode' and result['correctness_verified']
                assert result['output_hash'] == '1f7cd0eb14a22662' and len(result['samples']) == 3
                assert result['embedding_mapped'] and result['owned_shared_bytes'] == 20736
                enabled = mode not in ('off', 'direct')
                assert result['prefill_read_experts'] == (63 if enabled else 0)
                assert result['prefill_uncached_read_fallbacks'] == (63 if mode in ('uncached', 'history_reset') else 0)
                assert (result['expert_cache']['hits'] > 0) == (mode not in ('cache_off', 'pipeline_off', 'direct'))
                assert result['expert_cache']['history_resets'] == (9 if mode == 'history_reset' else 0)
                for sample in result['samples']:
                    assert sample['prefill_started_unix'] <= sample['prefill_ended_unix'] <= sample['decode_started_unix'] <= sample['decode_ended_unix']
                    assert sample['generated_ids'] == [28, 48, 106, 84, 28, 48, 106, 84]
            check_frozen()
            assert hashlib.sha256((ROOT / 'run-full.ps1').read_bytes()).hexdigest() == 'ad240b6679ad63bc0bcd2d3ba563a0cbc4dedd0ff49db6d9225d04df4e484f24', 'Wrapper changed; inspect before replacing'
            (ROOT / 'run-full.ps1').write_bytes((ROOT / 'run-full-prefill-reads.ps1').read_bytes())
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
