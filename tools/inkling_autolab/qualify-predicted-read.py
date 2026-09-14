"""After107 exits, qualify a separately frozen one-expert prefetch binary."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import time

import psutil

ROOT = Path('C:/Users/devcloud/inkling-autolab')
STATE = ROOT / 'predicted-read-qualification-state.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def state(status, **fields):
    tmp = STATE.with_suffix('.tmp')
    tmp.write_text(json.dumps(dict(status=status, pid=os.getpid(), unix=time.time(), **fields), indent=2))
    tmp.replace(STATE)


def active_full():
    return [p.pid for p in psutil.process_iter(['name']) if (p.info['name'] or '').startswith('full-')]


def qualify(source):
    def unchanged():
        for name, expected in source['frozen_binaries'].items():
            assert sha(ROOT / 'bin' / name) == expected, name
        assert sha(ROOT / 'run-full.ps1') == source['previous_wrapper_sha256']
        assert sha(ROOT / 'run-full-prefetch.ps1') == source['candidate_wrapper_sha256']
    unchanged()
    candidate = ROOT / 'bin/full-predicted-read.exe'
    assert not candidate.exists() and not active_full()
    for item in source['files']:
        path = ROOT / 'repo' / item['path']
        if item['previous_sha256'] is None:
            assert not path.exists(), item['path']
        else:
            assert sha(path) == item['previous_sha256'], item['path']
    with tarfile.open(ROOT / 'predicted-read-source.tar') as archive:
        assert sorted(archive.getnames()) == sorted(x['path'] for x in source['files'])
        contents = {item['path']: archive.extractfile(item['path']).read() for item in source['files']}
    for item in source['files']:
        assert hashlib.sha256(contents[item['path']]).hexdigest() == item['candidate_sha256']
    for name, raw in contents.items():
        (ROOT / 'repo' / name).write_bytes(raw)
    log = ROOT / '109-predicted-read-tests.log'
    with log.open('x', encoding='utf-8') as f:
        process = subprocess.Popen(['cmd.exe', '/c', str(ROOT / 'test-predicted-read.bat')], stdout=f, stderr=subprocess.STDOUT)
        state('building_and_testing', launcher_pid=process.pid)
        try:
            assert process.wait(timeout=3600) == 0, 'Native tests/build failed; inspect109 log'
        finally:
            if process.poll() is None:
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], check=False)
                process.wait()
    counts = [int(n) for n in re.findall(r'test result: ok\. (\d+) passed;', log.read_text())]
    assert len(counts) == 13 and sum(counts) == 252, counts
    controls = {}
    modes = []
    for recent, predict in ((0, 0), (0, 1), (1, 0), (1, 1)):
        assert not active_full()
        name = f'109-fixture-recent{recent}-read{predict}'
        out, log = ROOT / (name + '.json'), ROOT / (name + '.log')
        routes, predicted = ROOT / (name + '-routes.json'), ROOT / (name + '-predicted.json')
        assert not any(p.exists() for p in (out, log, routes, predicted))
        command = ['powershell', '-NoProfile', '-File', str(ROOT / 'run-full-prefetch.ps1'),
                   '-Model', str(ROOT / 'repo/crates/cascadia-engine-sparse-moe/tests/fixtures/inkling_export'),
                   '-Cases', str(ROOT / 'fixture-cases.json'), '-AllowFixture', '-Binary', candidate.name,
                   '-Threads', '16', '-AffinityMask', '65535', '-Reads', '0', '-Bf16Rows', '2', '-Int4Rows', '4',
                   '-MmapEmbed', '1', '-ReuseBuffers', '1', '-SkipBulkPrefetch', '1', '-OwnShared', '1',
                   '-UncachedReads', '1', '-PipelineReads', '1', '-ExpertCacheMiB', '1', '-PrefillReads', '1',
                   '-CacheResetHistory', '1', '-CacheDecayRequests', '32', '-CacheRecentTies', str(recent),
                   '-PredictReads', str(predict), '-Tokens', '8', '-Samples', '3', '-Out', str(out),
                   '-Log', str(log), '-RouteTrace', str(routes), '-PredictionTrace', str(predicted)]
        run = subprocess.run(command, text=True, capture_output=True, timeout=120)
        assert run.returncode == 0, run.stdout[-3000:] + run.stderr[-3000:]
        assert f'cache_recent_ties={recent} predict_reads={predict}' in run.stdout
        assert 'processor_affinity=65535' in run.stdout and 'rayon_threads=16' in run.stdout
        result = json.loads(out.read_text())
        assert result['scope'] == 'fixture_model_decode' and result['correctness_verified']
        assert result['output_hash'] == '1f7cd0eb14a22662'
        assert len(result['samples']) == 3 and {s['repetition'] for s in result['samples']} == {0, 1, 2}
        assert all(s['generated_ids'] == [28, 48, 106, 84, 28, 48, 106, 84] for s in result['samples'])
        cache = result['expert_cache']
        assert cache['capacity_bytes'] == 3145728 and cache['history_resets'] == 9
        assert cache['hits'] == 110 and cache['misses'] == 16
        assert cache['frequency_decays'] == cache['recent_tie_admissions'] == 0
        stats = result['prediction_reads']
        expected = dict(scheduled=13, successful=13, useful=11, unused=2, useful_bytes=38016, unused_bytes=6912,
                        read_failures=0, worker_failures=0, dispatch_failures=0)
        assert stats == ({k:0 for k in expected} if not predict else expected), stats
        assert result['uncached_read_fallbacks'] == (18 if predict else 16)
        assert result['prefill_read_experts'] == result['prefill_uncached_read_fallbacks'] == 63
        actual, prediction = json.loads(routes.read_text()), json.loads(predicted.read_text())
        assert actual['correctness_verified'] and actual['output_hash'] == result['output_hash']
        assert prediction['correctness_verified'] and prediction['output_hash'] == result['output_hash']
        assert prediction['prefetch_performed'] is bool(predict) and prediction['actual_routing_changed'] is False
        previous = json.loads((ROOT / f'104-fixture-recent{recent}-predict1-predicted.json').read_text())
        assert prediction['samples'] == previous['samples']
        if predict:
            assert (actual, cache) == controls[recent]
        else:
            controls[recent] = (actual, cache)
        modes.append(dict(recent=recent, predict_reads=predict, output_hash=result['output_hash'],
                          expert_cache=cache, prediction_reads=stats,
                          artifacts=[dict(name=p.name, sha256=sha(p)) for p in (out, log, routes, predicted)]))
    unchanged()
    report = dict(status='qualified', source_commit=source['source_commit'], native_tests=sum(counts),
                  binary_sha256=sha(candidate), wrapper_sha256=source['candidate_wrapper_sha256'],
                  modes=modes, full_model_speedup_measured=False)
    with (ROOT / '109-predicted-read-qualification.json').open('x') as f:
        json.dump(report, f, indent=2)
    (ROOT / 'run-full.ps1').write_bytes((ROOT / 'run-full-prefetch.ps1').read_bytes())
    assert sha(ROOT / 'run-full.ps1') == source['candidate_wrapper_sha256']
    return report


def main():
    import msvcrt
    with (ROOT / 'predicted-read-qualification.lock').open('a+b') as owner:
        owner.seek(0)
        msvcrt.locking(owner.fileno(), msvcrt.LK_NBLCK, 1)
        assert not STATE.exists()
        try:
            state('waiting_for_heldout_comparison')
            deadline = time.monotonic() + 7200
            reports = [ROOT / n for n in ('106-heldout-control.json', '107-heldout-prediction.json')]
            while not all(p.exists() for p in reports) or active_full():
                if time.monotonic() > deadline:
                    raise TimeoutError('106/107 did not complete')
                time.sleep(15)
            reference, candidate = [json.loads(p.read_text()) for p in reports]
            assert reference['correctness_verified'] is False and candidate['correctness_verified'] is True
            assert reference['output_hash'] == candidate['output_hash'] == 'e396cc533e658e44'
            for report in (reference, candidate):
                assert report['scope'] == 'full_large_model_decode' and len(report['samples']) == 3
                assert all(s['decode_steps'] == 127 for s in report['samples'])
            with (ROOT / 'baseline-queue.lock').open('a+b') as slot:
                slot.seek(0)
                msvcrt.locking(slot.fileno(), msvcrt.LK_NBLCK, 1)
                assert not active_full()
                result = qualify(json.loads((ROOT / 'predicted-read-source.json').read_text()))
            state('qualified', binary_sha256=result['binary_sha256'], modes=len(result['modes']))
        except BaseException as error:
            state('failed', error=str(error))
            raise


if __name__ == '__main__':
    main()
