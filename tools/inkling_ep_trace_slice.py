#!/usr/bin/env python3
"""Extract one complete prompt trajectory from a checksummed reference recording.

No tensors or token choices are recomputed. The selected bytes remain exact;
source SHA256, selected byte ranges and new checksums are retained as evidence.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path


def slice_case(source, hashes_path, case_name, destination):
    source, destination = Path(source), Path(destination)
    hashes = json.loads(Path(hashes_path).read_text())
    original = {}
    for name in ['trace.json', 'report.json']:
        data = (source/name).read_bytes()
        if hashlib.sha256(data).hexdigest() != hashes[name]:
            raise ValueError('source checksum differs: '+name)
        original[name] = json.loads(data)
    trace, report = original['trace.json'], original['report.json']
    if report['reference_comparison'] or report['teacher_forced']:
        raise ValueError('slicing requires an unforced reference recording')
    cases = [c['name'] for c in trace['cases']]
    if len(set(cases)) != len(cases) or case_name not in cases:
        raise ValueError('missing or duplicate case')
    ci = cases.index(case_name)
    if trace['generated_ids'] != report['generated_ids']:
        raise ValueError('recording trace/report token choices differ')
    selected, ranges, offset = [], [], 0
    for tensor in trace['tensors']:
        size = tensor['rows']*tensor['width']*4
        if size <= 0:
            raise ValueError('invalid tensor size')
        if tensor['case'] == case_name:
            selected.append(tensor)
            ranges.append([offset, offset+size])
        offset += size
    if not selected or offset != trace['payload_bytes'] or (source/'tensors.f32').stat().st_size != offset:
        raise ValueError('source tensor table/payload length differs')
    destination.mkdir(parents=True,exist_ok=False)
    pending = destination/'tensors.f32.incomplete'
    selected_hash = 0xcbf29ce484222325
    source_sha, selected_sha = hashlib.sha256(), hashlib.sha256()
    position = selected_size = 0
    with (source/'tensors.f32').open('rb') as inp, pending.open('xb') as out:
        for tensor in trace['tensors']:
            remaining = tensor['rows']*tensor['width']*4
            while remaining:
                data = inp.read(min(2**20, remaining))
                if not data:
                    raise ValueError('truncated source payload')
                source_sha.update(data)
                if tensor['case'] == case_name:
                    out.write(data)
                    selected_sha.update(data)
                    selected_size += len(data)
                    for byte in data:
                        selected_hash = ((selected_hash ^ byte)*0x100000001b3)&0xffffffffffffffff
                remaining -= len(data)
                position += len(data)
        if inp.read(1) or source_sha.hexdigest() != hashes['tensors.f32']:
            raise ValueError('source payload checksum differs')
    result_trace = dict(trace,cases=[trace['cases'][ci]],generated_ids=[trace['generated_ids'][ci]],
                        tensors=selected,payload_bytes=selected_size,payload_fnv1a64=f'{selected_hash:016x}')
    result_report = copy.deepcopy(report)
    for key in ['generated_ids','generated_text']:
        result_report[key] = [report[key][ci]]
    result_report['tensor_errors'] = []
    result_report['sliced_recording'] = True
    result_report['source_recording'] = str(source)
    pending.rename(destination/'tensors.f32')
    for name,data in [('trace.json',result_trace),('report.json',result_report)]:
        with (destination/name).open('x') as f:json.dump(data,f,indent=2);f.write('\n')
    output_hashes = {'tensors.f32':selected_sha.hexdigest()}
    for name in ['trace.json','report.json']:
        output_hashes[name] = hashlib.sha256((destination/name).read_bytes()).hexdigest()
    provenance = dict(source=str(source),source_sha256=hashes,case=case_name,selected_byte_ranges=ranges,
                      output_sha256=output_hashes,tensor_values_recomputed=False)
    with (destination/'slice-provenance.json').open('x') as f:json.dump(provenance,f,indent=2);f.write('\n')
    with (destination.parent/(destination.name+'-sha256.json')).open('x') as f:json.dump(output_hashes,f,indent=2);f.write('\n')
    return provenance


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',required=True,type=Path)
    p.add_argument('--hashes',required=True,type=Path)
    p.add_argument('--case',required=True)
    p.add_argument('--out',required=True,type=Path)
    a=p.parse_args()
    print(json.dumps(slice_case(a.source,a.hashes,a.case,a.out)))


if __name__=='__main__':main()
