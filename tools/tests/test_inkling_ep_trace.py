"""Negative controls for archived full-model correctness evidence."""
import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

TOOLS=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(TOOLS))
from inkling_ep_trace_slice import slice_case
from inkling_ep_topology_report import tensor_evidence


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
        root=TOOLS.parent/'docs/perf/inkling-ep-full'
        bundle=json.loads(gzip.decompress((root/'full-cpu-v7.json.gz').read_bytes()))
        report=bundle['charlie-full-cpu-v7.json']['report']
        cases=json.loads((root/'full-cases.json').read_text())
        self.assertEqual(tensor_evidence(report,cases,16)['matched_tensors'],3216)
        bad=copy.deepcopy(report);bad['tensor_errors'].pop(100)
        with self.assertRaises(AssertionError):tensor_evidence(bad,cases,16)
        for field,value in [('different_bits',1),('relative_rms',float('nan')),('max_abs',.01)]:
            bad=copy.deepcopy(report);bad['tensor_errors'][0][field]=value
            with self.assertRaises(AssertionError):tensor_evidence(bad,cases,16)


if __name__=='__main__':unittest.main()
