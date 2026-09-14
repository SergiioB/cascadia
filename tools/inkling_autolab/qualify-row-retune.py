"""Qualify existing row tiles after the repeated cache confirmation exits."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

import psutil

ROOT = Path('C:/Users/devcloud/inkling-autolab')
BINARY_SHA = '3874c863852b036757069bbac207a473481dd5408c854c037c7a2a72f6a431e8'


def active_full():
    for process in psutil.process_iter(['name', 'exe']):
        if (process.info['name'] or '').startswith('full-'):
            if (process.info['exe'] or '').lower().startswith(str(ROOT).lower()):
                return True
    return False


def state(status, **fields):
    path = ROOT / 'row-retune-qualification-state.json'
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(dict(status=status, pid=os.getpid(), unix=time.time(), **fields), indent=2))
    temporary.replace(path)


def qualify():
    report = ROOT / '075-row-retune-qualification.json'
    assert not report.exists(), 'Qualification already recorded'
    binary = ROOT / 'bin/full-cache-decay.exe'
    wrapper = ROOT / 'run-full.ps1'
    assert hashlib.sha256(binary.read_bytes()).hexdigest() == BINARY_SHA
    wrapper_sha = hashlib.sha256(wrapper.read_bytes()).hexdigest()
    records = []
    for bf16, int4 in ((2, 4), (1, 4), (4, 4), (2, 1), (2, 2)):
        assert not active_full()
        out = ROOT / f'075-fixture-rows-{bf16}-{int4}.json'
        log = out.with_suffix('.log')
        assert not out.exists() and not log.exists()
        command = ['powershell', '-NoProfile', '-File', str(wrapper), '-Model',
                   str(ROOT / 'repo/crates/cascadia-engine-sparse-moe/tests/fixtures/inkling_export'),
                   '-Cases', str(ROOT / 'fixture-cases.json'), '-AllowFixture',
                   '-Binary', binary.name, '-Threads', '16', '-Reads', '0',
                   '-Bf16Rows', str(bf16), '-Int4Rows', str(int4), '-MmapEmbed', '1',
                   '-ReuseBuffers', '1', '-SkipBulkPrefetch', '1', '-OwnShared', '1',
                   '-UncachedReads', '1', '-PipelineReads', '1', '-ExpertCacheMiB', '1',
                   '-PrefillReads', '1', '-CacheResetHistory', '1', '-CacheDecayRequests', '32',
                   '-Tokens', '8', '-Samples', '3', '-Out', str(out), '-Log', str(log)]
        run = subprocess.run(command, capture_output=True, text=True, timeout=120)
        if run.returncode:
            raise RuntimeError(f'rows{bf16}/{int4}: {run.stdout[-3000:]} {run.stderr[-3000:]}')
        assert f'bf16_rows={bf16} int4_rows={int4}' in run.stdout
        data = json.loads(out.read_text())
        assert data['scope'] == 'fixture_model_decode' and data['correctness_verified']
        assert data['output_hash'] == '1f7cd0eb14a22662' and len(data['samples']) == 3
        assert data['expert_cache']['history_resets'] == 9
        assert data['expert_cache']['frequency_decays'] == 0
        assert data['expert_cache']['hits'] == 110 and data['expert_cache']['misses'] == 16
        assert data['prefill_read_experts'] == 63 and data['prefill_uncached_read_fallbacks'] == 63
        assert {s['repetition'] for s in data['samples']} == {0, 1, 2}
        for sample in data['samples']:
            assert sample['generated_ids'] == [28, 48, 106, 84, 28, 48, 106, 84]
        records.append(dict(bf16_rows=bf16, int4_rows=int4, output_hash=data['output_hash'],
                            artifacts=[dict(name=p.name, sha256=hashlib.sha256(p.read_bytes()).hexdigest())
                                       for p in (out, log)]))
    assert hashlib.sha256(binary.read_bytes()).hexdigest() == BINARY_SHA
    assert hashlib.sha256(wrapper.read_bytes()).hexdigest() == wrapper_sha
    result = dict(status='qualified', unix=time.time(), binary_sha256=BINARY_SHA,
                  wrapper_sha256=wrapper_sha, modes=records, measured_full_model_speedup=False)
    with report.open('x') as f:
        json.dump(result, f, indent=2)
    return result


def main():
    import msvcrt
    with (ROOT / 'row-retune-qualification.lock').open('a+b') as owner:
        owner.seek(0)
        msvcrt.locking(owner.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            state('waiting_for_074')
            deadline = time.monotonic() + 7200
            previous = ROOT / '074-cache-confirmation.json'
            while active_full() or not previous.exists():
                if time.monotonic() >= deadline:
                    raise TimeoutError('074 did not finish')
                time.sleep(15)
            data = json.loads(previous.read_text())
            assert data['correctness_verified'] and data['output_hash'] == 'ce0fbb9a116d3d09'
            assert data['scope'] == 'full_large_model_decode' and len(data['samples']) == 9
            with (ROOT / 'baseline-queue.lock').open('a+b') as slot:
                slot.seek(0)
                msvcrt.locking(slot.fileno(), msvcrt.LK_NBLCK, 1)
                assert not active_full()
                state('qualifying')
                result = qualify()
            state('qualified', modes=len(result['modes']), binary_sha256=BINARY_SHA)
        except BaseException as error:
            state('failed', error=str(error))
            raise


if __name__ == '__main__':
    main()
