#!/usr/bin/env python3
"""Stream fused shard IRs from existing packed bins, without OpenVINO/numpy.

recipe extracts a small graph recipe from a same-dimension u4zp fused IR.
build stacks only owned experts, converts BF16 scales to FP16, and creates a
shard manifest. Original packed nibbles are unchanged. No checkpoint export.
"""
import argparse
import array
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import time
import xml.etree.ElementTree as ET


def recipe(ir, out):
    xml = (ir / "openvino_model.xml").read_bytes()
    tree = ET.fromstring(xml)
    x = next(n for n in tree.findall("./layers/layer") if n.get("name") == "x")
    hidden = int(x.find("data").get("shape").split(",")[-1])
    constants = tree.findall("./layers/layer[@type='Const']")
    first = next(n for n in constants if n.find("data").get("element_type") == "u4")
    total, inter, groups, width = map(int, first.find("data").get("shape").split(","))
    if width != 32 or groups * 32 != hidden:
        raise ValueError("recipe requires standard Inkling u4zp group-32 IR")
    if total in (hidden, inter, hidden//32, inter//32, 32, 8):
        raise ValueError("ambiguous expert dimension in template")
    specs = []
    matrix = -1
    with (ir / "openvino_model.bin").open("rb") as blob:
        for node in constants:
            data = node.find("data")
            shape = [int(x) for x in data.get("shape").split(",") if x.strip()]
            typ, size, offset = data.get("element_type"), int(data.get("size")), int(data.get("offset"))
            spec = dict(id=node.get("id"), offset=offset, size=size, dtype=typ)
            if len(shape) == 4 and shape[0] == total:
                if typ == "u4" and shape[-1] == 32:
                    matrix += 1
                    kind = "packed"
                elif typ == "u4" and shape[-1] == 1:
                    kind = "zero_point"
                elif typ == "f16" and shape[-1] == 1:
                    kind = "scale"
                else:
                    raise ValueError("unknown expert constant")
                if matrix not in range(3) or size % total:
                    raise ValueError("invalid expert-major layout")
                spec.update(kind=kind, matrix=matrix, expert_bytes=size//total)
            else:
                if size > 1024:
                    raise ValueError("unexpected large constant")
                blob.seek(offset)
                spec.update(kind="literal", hex=blob.read(size).hex())
            specs.append(spec)
    if matrix != 2:
        raise ValueError("expected gate/up/down")
    result = dict(version=1, hidden_size=hidden, moe_intermediate=inter,
                  template_experts=total, xml=base64.b64encode(xml).decode(),
                  template_xml_sha256=hashlib.sha256(xml).hexdigest(), constants=specs)
    with out.open("x") as f:
        json.dump(result, f)


class Guard:
    """Check between bounded chunks; yield to CI/services and retain reserves."""
    def __init__(self, root, rate, reserve):
        import psutil
        self.psutil, self.root, self.rate, self.reserve = psutil, root, rate*2**20, reserve*2**30
        self.start, self.written = time.monotonic(), 0
        self.last_check = None
        self.watched = []
        for p in psutil.process_iter(["name", "create_time"]):
            if (p.info["name"] or "").lower() in {"ovms.exe", "cascadia-node.exe"}:
                p.cpu_percent()
                self.watched.append((p, p.create_time()))
        proc = psutil.Process()
        if sys.platform == "win32":
            proc.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
            proc.cpu_affinity([6, 7])
        self.check()

    def check(self):
        now = time.monotonic()
        if self.last_check is not None and now - self.last_check < 0.5:
            return
        self.last_check = now
        psutil = self.psutil
        if psutil.virtual_memory().available < self.reserve:
            raise RuntimeError("memory reserve reached")
        if shutil.disk_usage(self.root).free < 80*2**30:
            raise RuntimeError("disk reserve reached")
        if any((p.info["name"] or "").lower() == "runner.worker.exe" for p in psutil.process_iter(["name"])):
            raise RuntimeError("CI active")
        for p, created in self.watched:
            if not p.is_running() or p.create_time() != created or p.cpu_percent() > 20:
                raise RuntimeError("existing inference service active or changed")

    def write(self, f, data, digest):
        self.check()
        f.write(data)
        digest.update(data)
        self.written += len(data)
        delay = self.written/self.rate - (time.monotonic()-self.start)
        if delay > 0:
            time.sleep(min(delay, 1))


def build(args):
    rec = json.loads(args.recipe.read_text())
    model = json.loads((args.export / "manifest.json").read_text())
    plan = json.loads(args.placement.read_text())
    h, inter = rec["hidden_size"], rec["moe_intermediate"]
    for name in ("hidden_size", "moe_intermediate"):
        if rec[name] != model[name] or rec[name] != plan[name]:
            raise ValueError("recipe/model/placement dimension mismatch")
    if plan["version"] != 1 or not 0 <= args.index < len(plan["workers"]):
        raise ValueError("invalid placement/index")
    ids = [i for i, owners in enumerate(plan["layers"][args.layer]) if args.index in owners]
    if not ids:
        raise ValueError("empty shard")
    old = rec["template_experts"]
    padded = len(ids) + max(1, (len(ids)+98)//99)
    k = model["top_k"] + model["n_shared_experts"]
    if padded in (h, inter, h//32, inter//32, 32) or k != 8:
        raise ValueError("this recipe requires unambiguous dimensions and K=8")
    root = args.out
    root.mkdir(parents=True, exist_ok=True)
    final = root / f"layer_{args.layer:02}"
    temp = root / f"layer_{args.layer:02}.building"
    if final.exists() or temp.exists():
        raise FileExistsError("output exists; use a fresh destination")
    guard = Guard(root, args.rate_mib, args.reserve_gib) if args.guarded else None
    temp.mkdir()
    edir = args.export / "experts" / f"layer_{args.layer:02}"
    paths = {i: edir / (f"expert_{i:03}.bin" if i < model["num_experts"] else f"expert_shared{i-model['num_experts']}.bin") for i in ids}
    packed = h*inter//2
    scale = h*inter//32*2
    expert_bytes = 3*(packed+scale)
    if any(p.stat().st_size != expert_bytes for p in paths.values()):
        raise ValueError("packed expert byte count mismatch")
    source_hashes = {i: hashlib.sha256() for i in ids}
    # BF16 -> FP16 lookup avoids a numpy/OpenVINO dependency on workers.
    lut = []
    for value in range(65536):
        f = struct.unpack("<f", struct.pack("<I", value << 16))[0]
        try:
            lut.append(struct.pack("<e", f))
        except OverflowError:
            lut.append(None)
    tree = ET.fromstring(base64.b64decode(rec["xml"]))
    for dim in tree.iter("dim"):
        if dim.text == str(old):
            dim.text = str(padded)
    for data in tree.findall("./layers/layer/data"):
        if data.get("shape"):
            data.set("shape", ",".join(str(padded) if x.strip() == str(old) else x.strip() for x in data.get("shape").split(",")))
    nodes = {n.get("id"): n.find("data") for n in tree.findall("./layers/layer[@type='Const']")}
    offsets = {}
    blob_hash = hashlib.sha256()
    with (temp / "openvino_model.bin").open("xb") as out:
        def write(data):
            if guard:
                guard.write(out, data, blob_hash)
            else:
                out.write(data)
                blob_hash.update(data)
        for spec in rec["constants"]:
            data = nodes[spec["id"]]
            key = (spec["offset"], spec["size"])
            if key not in offsets:
                offset = out.tell()
                kind = spec["kind"]
                if kind == "literal":
                    raw = bytes.fromhex(spec["hex"])
                    if spec["dtype"] in ("i64", "i32"):
                        fmt = "q" if spec["dtype"] == "i64" else "i"
                        vals = struct.unpack("<" + fmt*(len(raw)//struct.calcsize(fmt)), raw)
                        raw = struct.pack("<" + fmt*len(vals), *(padded if v == old else v for v in vals))
                    write(raw)
                else:
                    length = spec["expert_bytes"]
                    for i in ids + [None]*(padded-len(ids)):
                        if kind == "zero_point" or i is None:
                            write(bytes([0 if kind == "scale" else 0x88])*length)
                            continue
                        offset_in_expert = spec["matrix"]*(packed+scale) + (packed if kind == "scale" else 0)
                        with paths[i].open("rb") as src:
                            src.seek(offset_in_expert)
                            raw = src.read(length)
                        if len(raw) != length:
                            raise ValueError("short source read")
                        source_hashes[i].update(raw)
                        if kind == "scale":
                            values = array.array("H", raw)
                            if sys.byteorder != "little":
                                values.byteswap()
                            raw = b"".join(lut[v] for v in values)
                            if any((v & 0x7fff) >= 0x7c00 for v in array.array("H", raw)):
                                raise ValueError("scale became nonfinite in FP16")
                        write(raw)
                offsets[key] = (offset, out.tell()-offset)
            offset, size = offsets[key]
            data.set("offset", str(offset))
            data.set("size", str(size))
    # Every source section was visited in file order, despite expert-major output.
    sources = {str(i): digest.hexdigest() for i, digest in source_hashes.items()}
    xml = ET.tostring(tree, encoding="utf-8", xml_declaration=True)
    (temp / "openvino_model.xml").write_bytes(xml)
    meta = dict(version=1, layer=args.layer, hidden_size=h, moe_intermediate=inter,
                k=k, expert_ids=ids, padded_experts=padded, ir_bytes=(temp / "openvino_model.bin").stat().st_size,
                bin_sha256=blob_hash.hexdigest(), xml_sha256=hashlib.sha256(xml).hexdigest(),
                source_sha256=sources, template_xml_sha256=rec["template_xml_sha256"],
                placement_sha256=hashlib.sha256(args.placement.read_bytes()).hexdigest())
    (temp / "shard.json").write_text(json.dumps(meta, indent=2)+"\n")
    if guard:
        guard.check()
    temp.rename(final)
    print(json.dumps(meta), flush=True)


def compact(src, out):
    """Make a K=1 graph sharing the immutable shard blob via a hard link.

    The worker expands real (token,expert) pairs into rows and combines their
    weighted outputs. Only routing dimensions change; weights stay identical.
    """
    meta = json.loads((src / "shard.json").read_text())
    old = meta["k"]
    if old != 8 or old in (meta["hidden_size"], meta["moe_intermediate"], meta["padded_experts"]):
        raise ValueError("compact requires an unambiguous K=8 shard")
    tree = ET.fromstring((src / "openvino_model.xml").read_bytes())
    for name in ("topk_indices", "routing_weights"):
        node = next(n for n in tree.findall("./layers/layer") if n.get("name") == name)
        if node.find("data").get("shape").replace(" ", "") != "?,8":
            raise ValueError("unexpected routing input shape")
        node.find("data").set("shape", "?,1")
    for dim in tree.iter("dim"):
        if dim.text == "8":
            dim.text = "1"
    xml = ET.tostring(tree, encoding="utf-8", xml_declaration=True)
    out.mkdir(parents=True, exist_ok=False)
    os.link(src / "openvino_model.bin", out / "openvino_model.bin")
    (out / "openvino_model.xml").write_bytes(xml)
    meta.update(k=1, xml_sha256=hashlib.sha256(xml).hexdigest(),
                compact_from_xml_sha256=meta["xml_sha256"])
    (out / "shard.json").write_text(json.dumps(meta, indent=2)+"\n")
    print(json.dumps(dict(out=str(out), k=1, shared_ir_bytes=meta["ir_bytes"])))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    r = sub.add_parser("recipe")
    r.add_argument("--ir-layer", type=Path, required=True)
    r.add_argument("--out", type=Path, required=True)
    c = sub.add_parser("compact")
    c.add_argument("--src", type=Path, required=True)
    c.add_argument("--out", type=Path, required=True)
    b = sub.add_parser("build")
    for key in ("recipe", "export", "placement", "out"):
        b.add_argument("--"+key, type=Path, required=True)
    for key in ("index", "layer"):
        b.add_argument("--"+key, type=int, required=True)
    b.add_argument("--guarded", action="store_true")
    b.add_argument("--rate-mib", type=float, default=48)
    b.add_argument("--reserve-gib", type=float, default=12)
    args = p.parse_args()
    if args.command == "recipe":
        recipe(args.ir_layer, args.out)
    elif args.command == "compact":
        compact(args.src, args.out)
    else:
        build(args)


if __name__ == "__main__":
    main()
