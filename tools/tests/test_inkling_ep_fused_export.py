"""Independent byte-level checks of streaming shard packing and K=1 retargeting."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock
import sys
import xml.etree.ElementTree as ET

spec = importlib.util.spec_from_file_location('fused_export', Path(__file__).parents[1]/'inkling_ep_fused_export.py')
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)
sys.path.insert(0, str(Path(__file__).parents[1]))
import inkling_ep_rebalance as rebalance


class ExportTests(unittest.TestCase):
    def test_shards_keep_nibbles_convert_scales_and_preserve_source_identity(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ir = root/'template'; ir.mkdir()
            total, hidden, inter = 11, 96, 64
            net = ET.Element('net', version='11'); layers = ET.SubElement(net,'layers')
            for i,(name,shape) in enumerate([('x','1,?,96'),('topk_indices','?,8'),('routing_weights','?,8')]):
                n=ET.SubElement(layers,'layer',id=str(i),name=name,type='Parameter')
                ET.SubElement(n,'data',shape=shape)
                port=ET.SubElement(ET.SubElement(n,'output'),'port')
                for v in shape.split(','): ET.SubElement(port,'dim').text='-1' if v=='?' else v
            blob=bytearray(); constants=[]
            for matrix,(o,inn) in enumerate([(inter,hidden),(inter,hidden),(hidden,inter)]):
                for kind,typ,shape,raw in [
                    ('packed','u4',[total,o,inn//32,32],bytes([0x88])*(total*o*inn//2)),
                    ('zero_point','u4',[total,o,inn//32,1],bytes([0x88])*(total*o*inn//64)),
                    ('scale','f16',[total,o,inn//32,1],struct.pack('<e',1.0)*(total*o*inn//32))]:
                    node=ET.SubElement(layers,'layer',id=str(3+len(constants)),name='weight'+str(len(constants)),type='Const')
                    ET.SubElement(node,'data',element_type=typ,shape=','.join(map(str,shape)),offset=str(len(blob)),size=str(len(raw)))
                    port=ET.SubElement(ET.SubElement(node,'output'),'port')
                    for v in shape: ET.SubElement(port,'dim').text=str(v)
                    constants.append((matrix,kind));blob.extend(raw)
            (ir/'openvino_model.xml').write_bytes(ET.tostring(net))
            (ir/'openvino_model.bin').write_bytes(blob)
            rec=root/'recipe.json'; exporter.recipe(ir,rec)
            model=dict(hidden_size=hidden,moe_intermediate=inter,num_experts=8,n_shared_experts=2,top_k=6)
            source=root/'model'; edir=source/'experts/layer_02';edir.mkdir(parents=True)
            (source/'manifest.json').write_text(json.dumps(model))
            original={}
            # Deliberately nonconsecutive owner IDs, including a shared expert.
            ids=[0,3,8]
            for eid in ids:
                data=bytearray()
                for matrix in range(3):
                    data.extend(bytes([(eid*19+matrix*13)%256])*(hidden*inter//2))
                    data.extend(struct.pack('<H',0x3f80+matrix)*(hidden*inter//32))
                original[eid]=bytes(data)
                (edir/(f'expert_{eid:03}.bin' if eid<8 else 'expert_shared0.bin')).write_bytes(data)
            plan=dict(version=1,hidden_size=hidden,moe_intermediate=inter,workers=[{},{}],layers=[[],[],[[0] if i in ids else [1] for i in range(10)]])
            pp=root/'plan.json';pp.write_text(json.dumps(plan))
            exporter.build(argparse.Namespace(recipe=rec,export=source,placement=pp,index=0,layer=2,out=root/'out',guarded=False))
            result=root/'out/layer_02';meta=json.loads((result/'shard.json').read_text())
            self.assertEqual(meta['expert_ids'],ids)
            self.assertEqual(meta['source_sha256'],{str(i):hashlib.sha256(v).hexdigest() for i,v in original.items()})
            packed=(result/'openvino_model.bin').read_bytes()
            nodes=ET.fromstring((result/'openvino_model.xml').read_bytes()).findall("./layers/layer[@type='Const']")
            for node,(matrix,kind) in zip(nodes,constants):
                d=node.find('data'); offset,size=int(d.get('offset')),int(d.get('size'))
                rows=[]
                for eid in ids+[None]:
                    if kind=='packed': rows.append(bytes([0x88 if eid is None else (eid*19+matrix*13)%256])*(hidden*inter//2))
                    elif kind=='zero_point': rows.append(bytes([0x88])*(hidden*inter//64))
                    else:
                        value=0. if eid is None else struct.unpack('<f',struct.pack('<I',(0x3f80+matrix)<<16))[0]
                        rows.append(struct.pack('<e',value)*(hidden*inter//32))
                self.assertEqual(packed[offset:offset+size],b''.join(rows))
            compact=root/'compact';exporter.compact(result,compact)
            self.assertEqual((compact/'openvino_model.bin').stat().st_ino,(result/'openvino_model.bin').stat().st_ino)
            self.assertEqual(json.loads((compact/'shard.json').read_text())['k'],1)
            self.assertNotIn(b'<dim>8</dim>',(compact/'openvino_model.xml').read_bytes())
            with self.assertRaises(FileExistsError): exporter.compact(result,compact)
            old_meta = (result/'shard.json').read_bytes()
            # Failure after a scale write must restore both graphs and all bytes.
            with mock.patch.object(rebalance, 'digest', side_effect=[
                hashlib.sha256(packed[int(nodes[5].find('data').get('offset')):
                                      int(nodes[5].find('data').get('offset'))+int(nodes[5].find('data').get('size'))]).hexdigest(),
                RuntimeError('injected hash failure'),
                hashlib.sha256(packed[int(nodes[5].find('data').get('offset')):
                                      int(nodes[5].find('data').get('offset'))+int(nodes[5].find('data').get('size'))]).hexdigest(),
            ]):
                with self.assertRaisesRegex(RuntimeError, 'injected'):
                    rebalance.rebalance(result, compact, 4)
            self.assertEqual((result/'openvino_model.bin').read_bytes(), packed)
            self.assertEqual(json.loads((result/'shard.json').read_bytes()), json.loads(old_meta))
            self.assertFalse((result/'.rebalance').exists())
            rebalance.rebalance(result, compact, 4)
            scaled = (result/'openvino_model.bin').read_bytes()
            for node,(matrix,kind) in zip(nodes,constants):
                d=node.find('data'); offset,size=int(d.get('offset')),int(d.get('size'))
                before,after=packed[offset:offset+size],scaled[offset:offset+size]
                if matrix==1 and kind=='scale':
                    self.assertEqual(before,b''.join(struct.pack('<e',v[0]*16) for v in struct.iter_unpack('<e',after)))
                else:
                    self.assertEqual(before,after)
            balanced = json.loads((result/'shard.json').read_text())
            self.assertEqual(balanced['version'],2)
            self.assertEqual(balanced['up_scale_exponent'],4)
            self.assertEqual(balanced['bin_sha256'],hashlib.sha256(scaled).hexdigest())
            self.assertTrue(rebalance.rebalance(result,compact,4)['already_complete'])
            exporter.build(argparse.Namespace(recipe=rec,export=source,placement=pp,index=0,layer=2,out=root/'balanced',guarded=False,up_scale_exponent=4))
            self.assertEqual((root/'balanced/layer_02/openvino_model.bin').read_bytes(),scaled)

    def test_scale_transform_rejects_nonfinite_and_excess_underflow(self):
        for value in [float('nan'),float('inf'),2**-24]:
            with self.assertRaises(ValueError):
                exporter.scale_fp16(struct.pack('<e',value),4)

if __name__=='__main__': unittest.main()
