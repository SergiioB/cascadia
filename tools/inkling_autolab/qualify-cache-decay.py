"""After055/056/057 finish, qualify optional shorter cache-frequency history.

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
STATE = ROOT / 'cache-decay-qualification-state.json'
FROZEN = {
    'full-prefill-reads.exe': 'bb44392b9a4d3f29b845e115c4e01a724477a374cc56de10043712509e5aaf82',
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
    with (ROOT / 'cache-decay-qualification.lock').open('a+b') as owner:
        owner.seek(0)
        msvcrt.locking(owner.fileno(), msvcrt.LK_NBLCK, 1)
        state('waiting_for_cache_comparison')
        with (ROOT / 'baseline-queue.lock').open('a+b') as slot:
            deadline = time.monotonic() + 120 * 60
            while True:
                reports = [ROOT / name for name in ('055-history-64.json', '056-history-128.json', '057-history-256.json')]
                if all(p.exists() for p in reports) and not active_full_processes():
                    for report, mib in zip(reports, (64, 128, 256)):
                        result = json.loads(report.read_text())
                        assert result['scope'] == 'full_large_model_decode'
                        assert result['correctness_verified'] and result['output_hash'] == 'ce0fbb9a116d3d09'
                        assert len(result['samples']) == 3 and result['owned_shared_bytes'] == 4076863488
                        assert result['uncached_read_effective'] and result['uncached_read_fallbacks'] == 0
                        assert result['expert_cache']['capacity_bytes'] == mib * 64 * 1024 * 1024
                        assert result['expert_cache']['history_resets'] == 192
                        assert result['prefill_read_experts'] == 13635
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
            candidate = ROOT / 'bin/full-cache-decay.exe'
            assert not candidate.exists(), 'Inspect existing candidate before rebuilding'
            assert not active_full_processes(), 'Another full benchmark started'
            manifest = json.loads((ROOT / 'cache-decay-source.json').read_text())
            for item in manifest:
                target = ROOT / 'repo' / item['path']
                if item['previous_sha256'] is None:
                    assert not target.exists(), item['path']
                else:
                    assert hashlib.sha256(target.read_bytes()).hexdigest() == item['previous_sha256'], item['path']
            with tarfile.open(ROOT / 'cache-decay-source.tar') as archive:
                assert sorted(archive.getnames()) == sorted(item['path'] for item in manifest)
                for item in manifest:
                    data = archive.extractfile(item['path']).read()
                    assert hashlib.sha256(data).hexdigest() == item['candidate_sha256']
                    (ROOT / 'repo' / item['path']).write_bytes(data)
            with (ROOT / 'test-cache-decay.log').open('x', encoding='utf-8') as log:
                process = subprocess.Popen(['cmd.exe', '/c', str(ROOT / 'test-cache-decay.bat')],
                                           stdout=log, stderr=subprocess.STDOUT)
                state('building_and_testing', launcher_pid=process.pid)
                try:
                    if process.wait(timeout=3600):
                        raise RuntimeError('Native qualification failed; inspect test-cache-decay.log')
                finally:
                    if process.poll() is None:
                        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], check=False)
                        process.wait()
            modes = []
            for mode, decays, resets, capacity in (
                ('default', 0, 9, 3145728), ('short', 27, 9, 3145728),
                ('continued', 3, 0, 3145728), ('disabled', 0, 0, 0),
                ('invalid', 0, 9, 3145728),
            ):
                result = json.loads((ROOT / f'fixture-cache-decay-{mode}.json').read_text())
                assert result['scope'] == 'fixture_model_decode' and result['correctness_verified']
                assert result['output_hash'] == '1f7cd0eb14a22662' and len(result['samples']) == 3
                cache = result['expert_cache']
                assert cache['frequency_decays'] == decays
                assert cache['history_resets'] == resets and cache['capacity_bytes'] == capacity
                assert cache['hits'] == (110 if capacity else 0)
                assert result['prefill_read_experts'] == 63
                assert result['prefill_uncached_read_fallbacks'] == 63
                for sample in result['samples']:
                    assert sample['generated_ids'] == [28, 48, 106, 84, 28, 48, 106, 84]
                modes.append(dict(mode=mode, output_hash=result['output_hash'], expert_cache=cache))
            check_frozen()
            assert hashlib.sha256((ROOT / 'run-full.ps1').read_bytes()).hexdigest() == '5e0a29a4a3ec041ad1c93a44cfcf942e1df2db8dbce6c2a795ec86b5600a259b', 'Wrapper changed; inspect before replacing'
            wrapper_command = ['powershell', '-NoProfile', '-File', str(ROOT / 'run-full-cache-decay.ps1'),
                '-Model', str(ROOT / 'repo/crates/cascadia-engine-sparse-moe/tests/fixtures/inkling_export'),
                '-Cases', str(ROOT / 'fixture-cases.json'), '-AllowFixture', '-Binary', 'full-cache-decay.exe',
                '-Reads', '0', '-Bf16Rows', '2', '-Int4Rows', '4', '-MmapEmbed', '1', '-ReuseBuffers', '1',
                '-SkipBulkPrefetch', '1', '-OwnShared', '1', '-UncachedReads', '1', '-PipelineReads', '1',
                '-ExpertCacheMiB', '1', '-PrefillReads', '1', '-CacheResetHistory', '1', '-CacheDecayRequests', '4',
                '-Tokens', '8', '-Samples', '3', '-Out', str(ROOT / 'fixture-cache-decay-wrapper.json'),
                '-Log', str(ROOT / 'fixture-cache-decay-wrapper.log')]
            subprocess.run(wrapper_command, check=True, timeout=120)
            wrapper_result = json.loads((ROOT / 'fixture-cache-decay-wrapper.json').read_text())
            assert wrapper_result['correctness_verified'] and wrapper_result['output_hash'] == '1f7cd0eb14a22662'
            assert wrapper_result['expert_cache']['frequency_decays'] == 27
            (ROOT / 'run-full.ps1').write_bytes((ROOT / 'run-full-cache-decay.ps1').read_bytes())
            state('qualified_needs_full_trial', fixture_hash='1f7cd0eb14a22662',
                  binary_sha256=hashlib.sha256(candidate.read_bytes()).hexdigest(),
                  full_model_speedup_measured=False, fixture_modes=modes, production_wrapper_verified=True)


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        if STATE.exists() and json.loads(STATE.read_text()).get('pid') == os.getpid():
            state('failed', error=str(error))
        raise
