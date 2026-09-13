"""Finite PTL baseline job. Wait for the verified export; never promote a result."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path('C:/Users/devcloud/inkling-autolab')
MODEL = ROOT / 'model'
BINARY_SHA256 = 'f0bf021af04edd76f6fec5b77d8571225ba38f8f2315cbaac2bed189c04fc77a'
EXPECTED_EXPORT_BYTES = 548985140942
EXPECTED_EXPORT_FILES = 16654
OWNS_STATE = False
PROMPTS = [
    ('water_cycle', 'Explain the water cycle in six numbered steps. Write two complete sentences for each step.'),
    ('binary_search', 'Explain how binary search works, including its assumptions, a worked example, and its time complexity.'),
    ('short_story', 'Write a 200-word story about a lighthouse keeper who discovers a message in a bottle.'),
]


def save(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2), encoding='utf-8')
    temporary.replace(path)


def state(status, **details):
    save(ROOT / 'baseline-queue-state.json', {
        'status': status, 'pid': os.getpid(), 'updated_unix': time.time(),
        'target_reached': False, **details,
    })


def prepare():
    from transformers import PreTrainedTokenizerFast
    tokenizer = PreTrainedTokenizerFast(tokenizer_file=str(MODEL / 'tokenizer.json'))
    tokenizer.chat_template = (MODEL / 'chat_template.jinja').read_text(encoding='utf-8')

    def case(name, text):
        ids = tokenizer.apply_chat_template(
            [{'role': 'user', 'content': text}], tokenize=True,
            add_generation_prompt=True, reasoning_effort='none', tools=[], return_dict=True,
        )
        return {'name': name, 'prompt_ids': ids['input_ids']}

    smoke = case('paris', 'What is the capital of France? Answer in one word.')
    assert len(smoke['prompt_ids']) == 25, 'Tokenizer framing differs from documented smoke test'
    cases = [case(name, prompt) for name, prompt in PROMPTS]
    save(ROOT / 'large-smoke-cases.json', [smoke])
    save(ROOT / 'large-cases.json', cases)
    save(ROOT / 'large-prompts.json', {
        'reasoning_effort': 'none', 'prompts': dict(PROMPTS),
        'smoke_reference': 'docs/architectures/inkling.md: capital of France -> Paris',
        'tokenizer_sha256': hashlib.sha256((MODEL / 'tokenizer.json').read_bytes()).hexdigest(),
        'template_sha256': hashlib.sha256((MODEL / 'chat_template.jinja').read_bytes()).hexdigest(),
    })
    print(json.dumps({'prompt_lengths': {c['name']: len(c['prompt_ids']) for c in [smoke, *cases]}}), flush=True)
    return tokenizer, cases


def run(name, cases, tokens, samples, timeout):
    output = ROOT / (name + '.json')
    if output.exists():
        raise RuntimeError(f'Refusing to overwrite an existing baseline: {output}')
    cmd = ['powershell.exe', '-NoProfile', '-File', str(ROOT / 'run-full.ps1'),
           '-Model', str(MODEL), '-Cases', str(cases), '-Reads', '0',
           '-Bf16Rows', '1', '-Int4Rows', '1', '-Tokens', str(tokens),
           '-Samples', str(samples), '-Out', str(output)]
    with (ROOT / (name + '.log')).open('w', encoding='utf-8') as log:
        process = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
        state('running_' + name, launcher_pid=process.pid)
        try:
            result = process.wait(timeout=timeout)
            if result != 0:
                raise RuntimeError(f'{name} exited {result}; see {name}.log')
        finally:
            if process.poll() is None:
                # Stop only this launcher and its benchmark child after timeout/error.
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], check=False)
                process.wait()
    report = json.loads(output.read_text(encoding='utf-8'))
    assert report['scope'] == 'full_large_model_decode'
    return report


def main():
    global OWNS_STATE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    if args.prepare_only:
        prepare()
        return
    import msvcrt
    with (ROOT / 'baseline-queue.lock').open('a+b') as lock:
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        OWNS_STATE = True
        deadline = time.monotonic() + 96 * 3600
        state('waiting_for_verified_transfer')
        while not (ROOT / 'model-ready.json').exists():
            status_path = ROOT / 'transfer-state.json'
            if status_path.exists():
                transfer = json.loads(status_path.read_text())
                if not transfer.get('probe') and transfer.get('status') == 'failed':
                    raise RuntimeError('Checkpoint transfer failed; baseline was not started')
            if time.monotonic() >= deadline:
                raise TimeoutError('Checkpoint was not verified within 96 hours')
            time.sleep(30)
        ready = json.loads((ROOT / 'model-ready.json').read_text())
        assert ready['bytes'] == EXPECTED_EXPORT_BYTES
        assert len(ready['files']) == EXPECTED_EXPORT_FILES
        assert sum(r['size'] for r in ready['files'].values()) == EXPECTED_EXPORT_BYTES
        assert hashlib.sha256((ROOT / 'bin/full-decode.exe').read_bytes()).hexdigest() == BINARY_SHA256
        tokenizer, cases = prepare()
        smoke = run('large-smoke', ROOT / 'large-smoke-cases.json', 8, 1, 3600)
        text = tokenizer.decode(smoke['samples'][0]['generated_ids'], skip_special_tokens=True).strip()
        save(ROOT / 'large-smoke-text.json', {'text': text, 'expected': 'Paris', 'passed': text == 'Paris'})
        assert text == 'Paris', 'Full-model smoke output differs from documented answer'
        baseline = run('large-baseline', ROOT / 'large-cases.json', 64, 3, 24 * 3600)
        assert len(baseline['samples']) == len(cases) * 3
        assert all(s['decode_steps'] >= 32 for s in baseline['samples']), 'Completion too short for target gate'
        rendered = []
        for case in cases:
            samples = [s for s in baseline['samples'] if s['case'] == case['name']]
            assert len(samples) == 3 and {s['repetition'] for s in samples} == {0, 1, 2}
            assert all(s['generated_ids'] == samples[0]['generated_ids'] for s in samples)
            case['greedy_ids'] = samples[0]['generated_ids']
            rendered.append({'case': case['name'], 'text': tokenizer.decode(case['greedy_ids'], skip_special_tokens=True)})
        save(ROOT / 'large-cases.baseline-reference.json', cases)
        save(ROOT / 'large-baseline-text.json', rendered)
        state('baseline_recorded_needs_review',
              decode_tokens_per_s=baseline['slowest_case_decode_tokens_per_s'],
              output_hash=baseline['output_hash'], correctness_verified=False,
              next_action='Review baseline text, then use reference IDs/hash in the next full-model Autolab campaign.')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        if OWNS_STATE:
            state('failed', error=str(error))
        raise
