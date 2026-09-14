"""Qualify worker-count changes against the frozen native tiny-model oracle.

Run only between full trials. A separate staged wrapper keeps the running
campaign's launcher unchanged until all modes pass. No build or export occurs.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import time
import psutil

ROOT = Path('C:/Users/devcloud/inkling-autolab')
BINARY_SHA = 'bb44392b9a4d3f29b845e115c4e01a724477a374cc56de10043712509e5aaf82'


def main():
    report = ROOT / 'threads-qualification.json'
    assert not report.exists(), 'Qualification already recorded'
    for p in psutil.process_iter(['exe', 'name']):
        if (p.info['name'] or '').startswith('full-'):
            assert not (p.info['exe'] or '').lower().startswith(str(ROOT).lower()), 'Full trial active'
    binary = ROOT / 'bin/full-prefill-reads.exe'
    assert hashlib.sha256(binary.read_bytes()).hexdigest() == BINARY_SHA
    previous = ROOT / 'run-full.ps1'
    candidate = ROOT / 'run-full-threads.ps1'
    previous_sha = hashlib.sha256(previous.read_bytes()).hexdigest()
    expected = json.loads((ROOT / 'threads-source.json').read_text())
    assert previous_sha == expected['previous_wrapper_sha256']
    assert hashlib.sha256(candidate.read_bytes()).hexdigest() == expected['candidate_wrapper_sha256']
    records = []
    for threads in (8, 12, 16, 24, 32):
        out = ROOT / f'fixture-threads-{threads}.json'
        log = ROOT / f'fixture-threads-{threads}.log'
        assert not out.exists() and not log.exists()
        command = ['powershell', '-NoProfile', '-File', str(candidate), '-Model',
                   str(ROOT / 'repo/crates/cascadia-engine-sparse-moe/tests/fixtures/inkling_export'),
                   '-Cases', str(ROOT / 'fixture-cases.json'), '-AllowFixture',
                   '-Binary', binary.name, '-Threads', str(threads), '-Reads', '0',
                   '-Bf16Rows', '2', '-Int4Rows', '4', '-MmapEmbed', '1',
                   '-ReuseBuffers', '1', '-SkipBulkPrefetch', '1', '-OwnShared', '1',
                   '-UncachedReads', '1', '-PipelineReads', '1', '-ExpertCacheMiB', '1',
                   '-PrefillReads', '1', '-CacheResetHistory', '1',
                   '-Tokens', '8', '-Samples', '3', '-Out', str(out), '-Log', str(log)]
        run = subprocess.run(command, capture_output=True, text=True, timeout=120, check=True)
        assert f'rayon_threads={threads}' in run.stdout
        data = json.loads(out.read_text())
        assert data['scope'] == 'fixture_model_decode' and data['correctness_verified']
        assert data['output_hash'] == '1f7cd0eb14a22662' and len(data['samples']) == 3
        assert data['expert_cache']['history_resets'] == 9
        assert data['expert_cache']['hits'] == 110 and data['expert_cache']['misses'] == 16
        assert data['prefill_read_experts'] == 63 and data['prefill_uncached_read_fallbacks'] == 63
        for sample in data['samples']:
            assert sample['generated_ids'] == [28, 48, 106, 84, 28, 48, 106, 84]
        records.append(dict(threads=threads, output_hash=data['output_hash'],
                            native_json_sha256=hashlib.sha256(out.read_bytes()).hexdigest()))
    assert hashlib.sha256(binary.read_bytes()).hexdigest() == BINARY_SHA
    assert hashlib.sha256(previous.read_bytes()).hexdigest() == previous_sha
    previous.write_bytes(candidate.read_bytes())
    report.write_text(json.dumps(dict(status='qualified', unix=time.time(), binary_sha256=BINARY_SHA,
                                    wrapper_sha256=expected['candidate_wrapper_sha256'], modes=records,
                                    measured_full_model_speedup=False), indent=2)+'\n')
    print(report.read_text())


if __name__ == '__main__':
    main()
