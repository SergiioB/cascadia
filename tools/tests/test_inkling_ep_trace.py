"""Negative controls for archived full-model correctness evidence."""
import copy
import contextlib
import gzip
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

TOOLS=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(TOOLS))
from inkling_ep_trace_slice import slice_case
from inkling_ep_topology_report import tensor_evidence
import inkling_ep_topology_report as topology_report


def tensor_report(cases, tokens):
    """Generate metadata only; no model execution or captured float payload."""
    tensors = [dict(case=case['name'], step=step, layer=layer,
                    rows=len(case['prompt_ids']) if step == 0 and layer is not None else 1,
                    width=6144 if layer is not None else 200058)
               for case in cases for step in range(tokens) for layer in [*range(66), None]]
    return dict(tensor_errors=[dict(tensor=t, passed=True, different_bits=0,
                                   relative_rms=0., max_abs=0.) for t in tensors])


def archive_fixture(root):
    """Synthetic archive schema for auditor tests, independent of LAN results.

    Hashes model the captured-payload attestations; no real model weights,
    tensors, service identities or experiment files are required by these tests.
    """
    cases = [dict(name=name, prompt_ids=list(range(i+2)))
             for i, name in enumerate(['alpha', 'beta', 'gamma'])]
    hosts = ['alpha', 'beta', 'charlie']
    labels = ['fixture-'+c['name'] for c in cases]
    sha = lambda text: hashlib.sha256(text.encode()).hexdigest()
    def write(name, value):
        data = json.dumps(value).encode()
        (root/name).write_bytes(gzip.compress(data) if name.endswith('.gz') else data)
    write('full-cases.json', cases)
    write('final-audit.json', {h:dict(health=dict(live=200, ready=200), protected=[],
          task_processes_absent=True, firewall_absent=True, task_listeners_absent=True,
          free_gib=100) for h in hosts})
    exe = {n:sha(n) for n in ['inkling_ep_worker.exe', 'inkling_ep_validate.exe']}
    write('fixture-build.json', dict(executable_sha256={'bin-full/'+k:v for k,v in exe.items()}))
    write('run-builds.json', {label:'fixture-build.json' for label in ['fixture-base', *labels]})
    shards = {str(li):dict(up_scale_exponent=4, hardlinks_verified=True, view_expert_ids=[0])
              for li in range(2,66)}
    inventory = dict(model_manifest=dict(test_fixture=True), executable_sha256=exe,
                     owned_layers=list(range(2,66)), fused_shards=shards)
    status = dict(returncode=0, stop_reason=None, protected_processes_unchanged=True,
                  minimum_available_gib=20, peak_rss_gib=1, job=dict(max_rss_gib=3),
                  protected_before=[], protected_after=[])
    def bundle(label, selected, children, recording):
        inventories = {h if children == 1 else f'{h}-{c}': inventory
                       for h in hosts for c in range(children)}
        numerical = tensor_report(selected,8)
        tensors = [e['tensor'] for e in numerical['tensor_errors']]
        report = dict(full_model=True, reference_comparison=not recording,
                      teacher_forced=not recording, stops_at_eos=False,
                      correctness_verified=not recording, greedy_match=True, numerical_match=True,
                      relative_rms_tolerance=0, tokens_per_case=8, workers=list(inventories),
                      generated_ids=[[10+cases.index(c)]*8 for c in selected],
                      generated_text=['synthetic '+c['name'] for c in selected],
                      tensor_errors=[] if recording else numerical['tensor_errors'])
        trace = dict(model_manifest=inventory['model_manifest'], cases=selected,
                     generated_ids=report['generated_ids'], tensors=tensors,
                     payload_bytes=sum(t['rows']*t['width']*4 for t in tensors))
        raw = {'trace.json':json.dumps(trace), 'report.json':json.dumps(report)}
        hashes = {name:sha(text) for name,text in raw.items()}
        hashes['tensors.f32'] = sha('synthetic payload '+label)
        result = {'trace.json':trace, 'raw_json':raw, 'sha256.json':hashes,
                  'charlie-'+label+'.json':dict(returncode=0,status=status,report=report),
                  'preflight.json':{h:inventory for h in hosts},
                  'cleanup.json':{key:{} for key in inventories}}
        if children != 1:
            result['topology.json'] = dict(physical_hosts=3, logical_workers=12, inventories=inventories)
        total_rows = sum(len(c['prompt_ids'])+7 for c in selected)*64*8
        rows, extra = divmod(total_rows, len(inventories))
        for wi, key in enumerate(inventories):
            backend = dict(cpu_calls=0, ov_fallbacks=0, cpu_f16_reference=False,
                           wire_f16_replies=1, wire_f32_replies=0,
                           wire_tensor_bytes=24, wire_f32_equivalent_bytes=48,
                           fused=dict(errors=0, fused_required=True, streaming=True, calls=1,
                               device='GPU', ordered_replies=1, bf16_output=False,
                               f32_output_weighting=True, selected_expert_rows=rows+(wi<extra),
                               fusion_profiles={li:'MOECompressed' for li in shards},
                               up_scale_exponent={li:4 for li in shards}, graph_k={li:1 for li in shards}))
            result[f'{key.split("-")[0]}-{label}-worker-{wi}.json'] = dict(
                returncode=0, status=status, log='backend_final='+json.dumps(backend))
        return result
    baseline = bundle('fixture-base',cases,1,True)
    write('fixture-base.json.gz',baseline)
    for label, case in zip(labels,cases):
        candidate = bundle(label,[case],4,False)
        offset, ranges = 0, []
        for t in baseline['trace.json']['tensors']:
            end = offset+t['rows']*t['width']*4
            if t['case'] == case['name']: ranges.append([offset,end])
            offset = end
        candidate['reference-slice-provenance.json'] = dict(case=case['name'],
            source_sha256=baseline['sha256.json'], selected_byte_ranges=ranges,
            tensor_values_recomputed=False, output_sha256=candidate['sha256.json'].copy())
        write(label+'.json.gz',candidate)
    return ['inkling_ep_topology_report','--artifacts',str(root),'--baseline','fixture-base',
            '--candidate',*labels,'--out',str(root/'result.json')]


class TraceTests(unittest.TestCase):
    def source(self,root):
        source=root/'recording';source.mkdir()
        data=struct.pack('<6f',1.,2.,3.,4.,5.,6.)
        cases=[dict(name=n,prompt_ids=[1]) for n in ['alpha','beta']]
        tensors=[dict(case=n,step=0,layer=li,rows=1,width=2) for n,li in [('alpha',0),('beta',0),('beta',None)]]
        trace=dict(cases=cases,generated_ids=[[2],[3]],tokens=1,tensors=tensors,payload_bytes=len(data))
        report=dict(generated_ids=[[2],[3]],generated_text=['a','b'],reference_comparison=False,teacher_forced=False,tensor_errors=[])
        (source/'tensors.f32').write_bytes(data)
        (source/'trace.json').write_text(json.dumps(trace))
        (source/'report.json').write_text(json.dumps(report))
        hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()}
        hp=root/'hashes.json';hp.write_text(json.dumps(hashes))
        return source,hp,data

    def test_case_slice_copies_exact_bytes_and_binds_to_parent_hash(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source,hp,data=self.source(root);out=root/'beta'
            proof=slice_case(source,hp,'beta',out)
            self.assertEqual((out/'tensors.f32').read_bytes(),data[8:])
            self.assertEqual(proof['selected_byte_ranges'],[[8,16],[16,24]])
            trace=json.loads((out/'trace.json').read_text())
            self.assertEqual(trace['generated_ids'],[[3]])
            value=0xcbf29ce484222325
            for b in data[8:]:value=((value^b)*0x100000001b3)&0xffffffffffffffff
            self.assertEqual(trace['payload_fnv1a64'],f'{value:016x}')
            self.assertFalse(proof['tensor_values_recomputed'])
            self.assertEqual(proof['source_sha256'],json.loads(hp.read_text()))

    def test_corrupt_source_never_publishes_a_loadable_reference(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source,hp,data=self.source(root)
            (source/'tensors.f32').write_bytes(data[:-1]+bytes([data[-1]^1]))
            out=root/'bad'
            with self.assertRaisesRegex(ValueError,'checksum'):slice_case(source,hp,'beta',out)
            self.assertFalse((out/'trace.json').exists())
            self.assertFalse((out/'tensors.f32').exists())

    def test_missing_layer_changed_bits_and_nonfinite_metrics_fail_audit(self):
        cases=[dict(name=f'fixture-{i}',prompt_ids=[1,2,3]) for i in range(3)]
        report=tensor_report(cases,16)
        self.assertEqual(tensor_evidence(report,cases,16)['matched_tensors'],3216)
        bad=copy.deepcopy(report);bad['tensor_errors'].pop(100)
        with self.assertRaises(AssertionError):tensor_evidence(bad,cases,16)
        for field,value in [('different_bits',1),('relative_rms',float('nan')),('max_abs',.01)]:
            bad=copy.deepcopy(report);bad['tensor_errors'][0][field]=value
            with self.assertRaises(AssertionError):tensor_evidence(bad,cases,16)

    def test_complete_synthetic_archive_passes_the_full_auditor(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);argv=archive_fixture(root)
            with patch.object(sys,'argv',argv), contextlib.redirect_stdout(io.StringIO()):
                topology_report.main()
            result=json.loads((root/'result.json').read_text())
            self.assertTrue(result['topology_correctness_verified'])
            self.assertEqual(result['generated_tokens'],24)
            self.assertEqual(result['matched_tensors'],1608)
            self.assertEqual(result['different_float_bits'],0)

    def test_changed_payload_hash_cannot_publish_a_pass_from_unchanged_native_reports(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);argv=archive_fixture(root)
            path=root/'fixture-beta.json.gz'
            value=json.loads(gzip.decompress(path.read_bytes()))
            # Leave every successful native verdict and metric intact.
            digest=value['sha256.json']['tensors.f32']
            value['sha256.json']['tensors.f32']=('0' if digest[0]!='0' else '1')+digest[1:]
            path.write_bytes(gzip.compress(json.dumps(value).encode()))
            with patch.object(sys,'argv',argv):
                with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(AssertionError):
                    topology_report.main()
            self.assertFalse((root/'result.json').exists())

    def test_omitting_a_prompt_cannot_publish_a_full_corpus_pass(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);argv=archive_fixture(root)
            argv.remove('fixture-gamma')
            with patch.object(sys,'argv',argv):
                with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(AssertionError):
                    topology_report.main()
            self.assertFalse((root/'result.json').exists())


if __name__=='__main__':unittest.main()
