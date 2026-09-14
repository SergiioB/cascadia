"""Qualify process-affinity wrapper after storage probes084/086 have exited."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

import psutil

ROOT = Path('C:/Users/devcloud/inkling-autolab')


def active_full():
    return any((p.info['name'] or '').startswith('full-')
               and (p.info['exe'] or '').lower().startswith(str(ROOT).lower())
               for p in psutil.process_iter(['name', 'exe']))


def state(status, **fields):
    path = ROOT / 'affinity-qualification-state.json'
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(dict(status=status, pid=os.getpid(), unix=time.time(), **fields), indent=2))
    temporary.replace(path)


def qualify():
    report = ROOT / '088-affinity-qualification.json'
    assert not report.exists()
    source = json.loads((ROOT / 'affinity-source.json').read_text())
    binary = ROOT / 'bin/full-cache-decay.exe'
    previous, candidate = ROOT / 'run-full.ps1', ROOT / 'run-full-affinity.ps1'
    for path, key in ((binary, 'binary_sha256'), (previous, 'previous_wrapper_sha256'), (candidate, 'candidate_wrapper_sha256')):
        assert hashlib.sha256(path.read_bytes()).hexdigest() == source[key], path
    records = []
    for mode in source['modes']:
        assert not active_full()
        mask, threads = mode['mask'], mode['threads']
        out = ROOT / f'088-fixture-affinity-{mask}-{threads}.json'
        log = out.with_suffix('.log')
        assert not out.exists() and not log.exists()
        command = ['powershell', '-NoProfile', '-File', str(candidate), '-Model',
                   str(ROOT / 'repo/crates/cascadia-engine-sparse-moe/tests/fixtures/inkling_export'),
                   '-Cases', str(ROOT / 'fixture-cases.json'), '-AllowFixture',
                   '-Binary', binary.name, '-Threads', str(threads), '-AffinityMask', str(mask),
                   '-Reads', '0', '-Bf16Rows', '2', '-Int4Rows', '4', '-MmapEmbed', '1',
                   '-ReuseBuffers', '1', '-SkipBulkPrefetch', '1', '-OwnShared', '1',
                   '-UncachedReads', '1', '-PipelineReads', '1', '-ExpertCacheMiB', '1',
                   '-PrefillReads', '1', '-CacheResetHistory', '1', '-CacheDecayRequests', '32',
                   '-Tokens', '8', '-Samples', '3', '-Out', str(out), '-Log', str(log)]
        run = subprocess.run(command, capture_output=True, text=True, timeout=120)
        if run.returncode:
            raise RuntimeError(f'affinity{mask}/{threads}: {run.stdout[-3000:]} {run.stderr[-3000:]}')
        assert f'processor_affinity={mask}' in run.stdout and f'rayon_threads={threads}' in run.stdout
        data = json.loads(out.read_text())
        assert data['scope'] == 'fixture_model_decode' and data['correctness_verified']
        assert data['output_hash'] == '1f7cd0eb14a22662' and len(data['samples']) == 3
        assert data['expert_cache']['history_resets'] == 9 and data['expert_cache']['frequency_decays'] == 0
        assert data['expert_cache']['hits'] == 110 and data['expert_cache']['misses'] == 16
        assert data['prefill_read_experts'] == 63 and data['prefill_uncached_read_fallbacks'] == 63
        assert {s['repetition'] for s in data['samples']} == {0, 1, 2}
        assert all(s['generated_ids'] == [28, 48, 106, 84, 28, 48, 106, 84] for s in data['samples'])
        records.append(dict(**mode, output_hash=data['output_hash'],
                            artifacts=[dict(name=p.name, sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in (out, log)]))
    for path, key in ((binary, 'binary_sha256'), (previous, 'previous_wrapper_sha256'), (candidate, 'candidate_wrapper_sha256')):
        assert hashlib.sha256(path.read_bytes()).hexdigest() == source[key], path
    previous.write_bytes(candidate.read_bytes())
    assert hashlib.sha256(previous.read_bytes()).hexdigest() == source['candidate_wrapper_sha256']
    result = dict(status='qualified', unix=time.time(), binary_sha256=source['binary_sha256'],
                  wrapper_sha256=source['candidate_wrapper_sha256'], modes=records,
                  measured_full_model_speedup=False)
    with report.open('x') as f:
        json.dump(result, f, indent=2)
    return result


def main():
    import msvcrt
    with (ROOT / 'affinity-qualification.lock').open('a+b') as owner:
        owner.seek(0)
        msvcrt.locking(owner.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            state('waiting_for_storage_probes')
            deadline = time.monotonic() + 7200
            names = ['compressed-read-probe-state.json', 'file-extents-probe-state.json']
            while True:
                states = [json.loads((ROOT / n).read_text()) if (ROOT / n).exists() else {} for n in names]
                if all(s.get('status') in ('complete', 'failed') and not psutil.pid_exists(s['pid']) for s in states) and not active_full():
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError('Storage probes did not exit')
                time.sleep(15)
            with (ROOT / 'baseline-queue.lock').open('a+b') as slot:
                slot.seek(0)
                msvcrt.locking(slot.fileno(), msvcrt.LK_NBLCK, 1)
                assert not active_full()
                state('qualifying')
                result = qualify()
            state('qualified', modes=len(result['modes']))
        except BaseException as error:
            state('failed', error=str(error))
            raise


if __name__ == '__main__':
    main()
