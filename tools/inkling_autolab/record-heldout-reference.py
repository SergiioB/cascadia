"""Record an unseen-prompt reference with a frozen, qualified full-model runtime.

This initial reference has no supplied output oracle and cannot establish a
performance record. The subsequent candidate must match its IDs and logits.
Run only after campaign105 and its native process have exited.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path('C:/Users/devcloud/inkling-autolab')
MODEL = ROOT / 'model'
BINARY_SHA = 'a23289477c2d5ade1e838ccf92d27ec8b5d31b1cebc4d79bc7d74ec85d1daa40'
WRAPPER_SHA = 'b0af52ea911f1a46ffc14f2a0f3588689443987a17db8aa1d60a0cea84d0934c'


def save_new(name, value):
    with (ROOT / name).open('x', encoding='utf-8') as f:
        json.dump(value, f, indent=2)
        f.write('\n')


def state(status, **details):
    path = ROOT / 'heldout-reference-state.json'
    temporary = path.with_suffix('.tmp')
    details = {**(json.loads(path.read_text()) if path.exists() else {}), **details}
    details.update(status=status, pid=os.getpid(), unix=time.time(), record_eligible=False)
    temporary.write_text(json.dumps(details, indent=2), encoding='utf-8')
    temporary.replace(path)


def main():
    import msvcrt
    import psutil
    with (ROOT / 'baseline-queue.lock').open('a+b') as lock:
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        assert not (ROOT / 'heldout-reference-state.json').exists()
        assert not any((p.info['name'] or '').startswith('full-')
                       for p in psutil.process_iter(['name']))
        previous = json.loads((ROOT / '105-route-prediction.json').read_text())
        assert previous['correctness_verified']
        assert previous['output_hash'] == 'ce0fbb9a116d3d09'
        assert hashlib.sha256((ROOT / 'bin/full-cache-recency.exe').read_bytes()).hexdigest() == BINARY_SHA
        assert hashlib.sha256((ROOT / 'run-full.ps1').read_bytes()).hexdigest() == WRAPPER_SHA
        assert hashlib.sha256((ROOT / 'model-ready.json').read_bytes()).hexdigest() == '9e7f11b6131131e8c3db879a814e121cd6a4fde9c6987fa6de7e86a80cb46a20'
        for name in ['106-heldout-control.json', '106-heldout-control.log',
                     '106-heldout-control-routes.json', '106-heldout-control-layers.json',
                     '106-heldout-launcher.log', 'heldout-cases.json',
                     'heldout-cases.reference.json', '106-heldout-reference.json']:
            assert not (ROOT / name).exists(), name
        state('preparing')
        try:
            from transformers import PreTrainedTokenizerFast
            tokenizer = PreTrainedTokenizerFast(tokenizer_file=str(MODEL / 'tokenizer.json'))
            tokenizer.chat_template = (MODEL / 'chat_template.jinja').read_text(encoding='utf-8')
            config = json.loads((ROOT / 'heldout-prompts.json').read_text())
            assert config['record_eligible'] is False and config['generated_tokens'] == 128
            cases = []
            for prompt in config['prompts']:
                encoded = tokenizer.apply_chat_template(
                    [{'role': 'user', 'content': prompt['prompt']}], tokenize=True,
                    add_generation_prompt=True, reasoning_effort='none', tools=[], return_dict=True)
                cases.append(dict(name=prompt['name'], prompt_ids=encoded['input_ids']))
            assert len(cases) == len({c['name'] for c in cases}) == 3
            save_new('heldout-cases.json', cases)
            cmd = ['powershell.exe', '-NoProfile', '-File', str(ROOT / 'run-full.ps1'),
                   '-Model', str(MODEL), '-Cases', str(ROOT / 'heldout-cases.json'),
                   '-Binary', 'full-cache-recency.exe', '-Threads', '16', '-AffinityMask', '65535',
                   '-CacheDecayRequests', '32', '-CacheRecentTies', '0', '-Reads', '0',
                   '-Bf16Rows', '2', '-Int4Rows', '4', '-MmapEmbed', '1', '-ReuseBuffers', '1',
                   '-OwnShared', '1', '-UncachedReads', '1', '-PipelineReads', '1',
                   '-ExpertCacheMiB', '256', '-PrefillReads', '1', '-CacheResetHistory', '1',
                   '-SkipBulkPrefetch', '1', '-Tokens', '128', '-Samples', '1',
                   '-Out', str(ROOT / '106-heldout-control.json'),
                   '-RouteTrace', str(ROOT / '106-heldout-control-routes.json'),
                   '-LayerProfile', str(ROOT / '106-heldout-control-layers.json'),
                   '-Log', str(ROOT / '106-heldout-control.log')]
            with (ROOT / '106-heldout-launcher.log').open('x', encoding='utf-8') as log:
                process = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
                state('launching', launcher_pid=process.pid)
                try:
                    deadline = time.monotonic() + 20
                    native = None
                    while native is None and process.poll() is None and time.monotonic() < deadline:
                        children = psutil.Process(process.pid).children(recursive=True)
                        matches = [p for p in children if p.name() == 'full-cache-recency.exe']
                        assert len(matches) <= 1
                        if matches:
                            native = matches[0]
                            break
                        time.sleep(.2)
                    assert native is not None, 'No native benchmark child appeared'
                    state('running', launcher_pid=process.pid, native_pid=native.pid,
                          native_created=native.create_time())
                    assert process.wait(timeout=3600) == 0
                finally:
                    if process.poll() is None:
                        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], check=False)
                        process.wait()
            report = json.loads((ROOT / '106-heldout-control.json').read_text())
            assert report['scope'] == 'full_large_model_decode'
            assert report['correctness_verified'] is False
            assert len(report['samples']) == 3
            rendered = []
            for case, sample in zip(cases, report['samples'], strict=True):
                assert case['name'] == sample['case'] and sample['repetition'] == 0
                assert sample['decode_steps'] >= 63
                assert sample['decode_steps'] + 1 == len(sample['generated_ids'])
                case['greedy_ids'] = sample['generated_ids']
                rendered.append(dict(case=case['name'], text=tokenizer.decode(case['greedy_ids'], skip_special_tokens=True)))
            save_new('heldout-cases.reference.json', cases)
            save_new('106-heldout-reference.json', dict(
                scope='initial_reference_needs_candidate_comparison', record_eligible=False,
                output_hash=report['output_hash'], decoded_text=rendered, binary_sha256=BINARY_SHA,
                source_sha256={name:hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                               for name in ['heldout-prompts.json', 'heldout-cases.json',
                                            'heldout-cases.reference.json', '106-heldout-control.json']},
                tokenizer_sha256=hashlib.sha256((MODEL / 'tokenizer.json').read_bytes()).hexdigest(),
                template_sha256=hashlib.sha256((MODEL / 'chat_template.jinja').read_bytes()).hexdigest()))
            state('reference_recorded', output_hash=report['output_hash'], next_action='Review outputs and run107 with exact reference IDs/hash plus causal counter predictions.')
        except Exception as error:
            state('failed', error=str(error))
            raise


if __name__ == '__main__':
    main()
