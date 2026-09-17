#!/usr/bin/env python3
"""Describe existing per-expert IRs so their blobs can be reconstructed locally.

Only reads the IR files; the destination reconstructs bytes from packed expert
bins and verifies the original IR's SHA256. This does not export a model.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ir-layer', required=True, type=Path)
    p.add_argument('--expert-bytes', required=True, type=int)
    p.add_argument('--out', required=True, type=Path)
    a = p.parse_args()
    result = {}
    for xml in sorted(a.ir_layer.glob('*/openvino_model.xml')):
        blob = xml.with_suffix('.bin').read_bytes()
        constants = []
        cursor = 0
        for layer in ET.fromstring(xml.read_bytes()).findall('.//layer'):
            if layer.attrib['type'] != 'Const':
                continue
            data = layer.find('data').attrib
            offset, size = int(data['offset']), int(data['size'])
            c = dict(offset=offset, size=size)
            if data['element_type'] in ['u4', 'bf16']:
                c['source_offset'] = cursor
                cursor += size
            else:
                if size > 1024:
                    raise ValueError('unexpected large non-weight constant')
                c['hex'] = blob[offset:offset+size].hex()
            constants.append(c)
        if cursor != a.expert_bytes:
            raise ValueError('IR does not have the expected packed weight layout')
        result[xml.parent.name+'.bin'] = dict(bytes=len(blob),
            sha256=hashlib.sha256(blob).hexdigest(),
            xml=base64.b64encode(xml.read_bytes()).decode(), constants=constants)
    if not result:
        raise ValueError('no expert IRs found')
    with a.out.open('x') as f:
        json.dump(result, f)


if __name__ == '__main__':
    main()
