"""Offline prefix-only n-gram opportunity, not an inference benchmark.

Input: {cases: [{name, prompt_ids}], samples: [{case, generated_ids, ...}]}.
Recorded future tokens are used only by the offline verifier. They are never
passed to the drafter. A hypothetical target call emits accepted draft tokens
and one correction/bonus token; we count its input rows separately because a
multi-row verification generally costs more than one ordinary decode step.
"""
import argparse
import json
from pathlib import Path


def draft(prefix, minimum, maximum, budget):
    """Extend from prior suffix matches, using only observed/proposed tokens."""
    history = list(prefix)
    proposed = []
    while len(proposed) < budget:
        continuation = []
        for n in range(min(maximum, len(history) - 1), minimum - 1, -1):
            suffix = history[-n:]
            for start in range(len(history) - n - 1, -1, -1):
                if history[start:start + n] == suffix:
                    continuation = history[start + n:start + n + budget - len(proposed)]
                    break
            if continuation:
                break
        if not continuation:
            break
        proposed.extend(continuation)
        history.extend(continuation)
    return proposed


def simulate(prompt, generated, minimum, maximum, budget):
    assert len(generated) >= 2
    position = 1  # first generated token was produced by prefill
    calls = drafted = accepted = verify_rows = speculative_calls = 0
    while position < len(generated):
        remaining = len(generated) - position
        # Prefix ends at the token whose logits the next target call computes.
        proposal = draft(prompt + generated[:position], minimum, maximum,
                         min(budget, remaining - 1))
        calls += 1
        drafted += len(proposal)
        verify_rows += 1 + len(proposal)
        speculative_calls += bool(proposal)
        matched = 0
        for expected, actual in zip(proposal, generated[position:]):
            if expected != actual:
                break
            matched += 1
        accepted += matched
        position += matched + 1  # accepted prefix plus correction/bonus
    assert position == len(generated)
    return {
        'decode_tokens': len(generated) - 1, 'target_calls': calls,
        'speculative_calls': speculative_calls, 'drafted_tokens': drafted,
        'accepted_draft_tokens': accepted, 'target_input_rows': verify_rows,
        'draft_acceptance': accepted / drafted if drafted else None,
        'optimistic_call_reduction_factor': (len(generated) - 1) / calls,
        'target_input_row_ratio': verify_rows / (len(generated) - 1),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    source = json.loads(args.input.read_text())
    prompts = {c['name']: c['prompt_ids'] for c in source['cases']}
    # Repeated deterministic outputs are not independent additional text.
    samples = [s for s in source['samples'] if s['repetition'] == 0]
    assert samples and len({s['case'] for s in samples}) == len(samples)
    results = []
    for minimum in (1, 2, 3):
        for budget in (2, 4, 8):
            results.append({'minimum_ngram': minimum, 'maximum_ngram': 6,
                            'draft_budget': budget, 'cases': [
                {'case': s['case'], **simulate(prompts[s['case']], s['generated_ids'],
                                             minimum, 6, budget)} for s in samples]})
    report = {'scope': 'offline_ngram_opportunity', 'measured_tokens_per_s': None,
              'prefix_only_drafter': True, 'results': results,
              'limitations': ['Short first-repetition text samples only.',
                              'Call reduction assumes a free drafter and equally costly target calls.',
                              'Actual multi-row verification, rejected work, snapshots and paging can erase the benefit.',
                              'No full-model performance run or target attainment is claimed.']}
    with args.out.open('x') as f:
        json.dump(report, f, indent=2)
        f.write('\n')
    for row in results:
        print(json.dumps(row))


if __name__ == '__main__':
    main()
