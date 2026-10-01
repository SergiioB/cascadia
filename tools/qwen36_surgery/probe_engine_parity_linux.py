#!/usr/bin/env python3
"""Whole-model greedy reference on Linux, for engine-parity acceptance.

Same recipe as tools/qwen36_surgery/probe_engine_parity.py (hard-coded to the
Windows 35B tree): T=1 prefill, greedy decode, EOS-stop-before-emit,
decode(skip_special_tokens). Prints the reference text as JSON.

Why this exists: the committed qwen38 golden was blessed on Windows
(`QWEN38_SHARDS=C:\\cascadia\\models\\qwen38-shards-2stage`), and greedy decode
is sensitive enough that a different oneDNN kernel set picks a different token
at a near-tie. The golden therefore only validates the platform it was recorded
on. This probe answers the question the golden cannot: does the WHOLE MODEL,
here, produce what the shard chain produces?

Measured on B70 (Linux, OpenVINO 2026.5, Qwen3.8-27B-int4-ov, 2-stage tree):

  whole model vs committed golden : 7/64 tokens in common  -> golden is Windows-only
  whole model vs shard chain      : 64/64 tokens           -> engine is correct

Usage:
  INTEL_OPENVINO_DIR=... LD_LIBRARY_PATH=... \
  python3 probe_engine_parity_linux.py [--model DIR] [--shards DIR]
"""
import argparse
import json
import time

import numpy as np
import openvino as ov
from tokenizers import Tokenizer

USER = "Explain how rainbows form."
N_TOK = 64


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True,
                    help="whole-model IR dir (has openvino_language_model.xml)")
    ap.add_argument("--shards", required=True,
                    help="exported shard tree (has tokenizer.json)")
    ap.add_argument("--hidden", type=int, required=True)
    ap.add_argument("--tokens", type=int, default=N_TOK)
    a = ap.parse_args()

    tok = Tokenizer.from_file(a.shards + "/tokenizer.json")
    prompt_ids = tok.encode("user: " + USER).ids
    eos = json.load(open(a.shards + "/generation_config.json"))["eos_token_id"]
    if isinstance(eos, list):
        eos = eos[0]
    print("prompt_tokens:", len(prompt_ids), "eos:", eos, flush=True)

    core = ov.Core()
    emb = core.compile_model(a.model + "/openvino_text_embeddings_model.xml", "CPU")
    emb_req = emb.create_infer_request()

    def embed(t):
        arr = np.array([[t]], dtype=np.int64)
        return (emb_req.infer({emb.inputs[0].get_any_name(): arr})[emb.outputs[0]]
                .astype(np.float32).reshape(1, 1, a.hidden))

    full = core.compile_model(a.model + "/openvino_language_model.xml", "CPU")
    req = full.create_infer_request()

    def feeds(step):
        f = {}
        for inp in full.inputs:
            nm = inp.get_any_name()
            ps = inp.get_partial_shape()
            dims = [(d.get_length() if d.is_static else 1) for d in ps]
            et = inp.get_element_type().to_dtype()
            if "embed" in nm:
                continue  # set separately
            elif "attention_mask" in nm:
                f[nm] = np.ones([1, step + 1], dtype=et)
            elif "position" in nm:
                f[nm] = np.full([dims[0], 1, 1], step, dtype=et)
            else:
                f[nm] = np.zeros(dims, dtype=et)
        return f

    emb_name = next(i.get_any_name() for i in full.inputs
                    if "embed" in i.get_any_name())

    def run(t, step):
        f = feeds(step)
        f[emb_name] = embed(t)
        return req.infer(f)[full.outputs[0]].astype(np.float32).reshape(-1)

    step, logits = 0, None
    t0 = time.perf_counter()
    for t in prompt_ids:
        logits = run(t, step)
        step += 1
    gen = []
    for _ in range(a.tokens):
        nxt = int(np.argmax(logits))
        if nxt == eos:
            break
        gen.append(nxt)
        logits = run(nxt, step)
        step += 1
    dt = time.perf_counter() - t0

    print("ref_tokens:", len(gen), "wall %.1fs" % dt, flush=True)
    print("REF_TEXT_JSON:", json.dumps(tok.decode(gen, skip_special_tokens=True)),
          flush=True)
    print("REF_IDS:", gen, flush=True)


if __name__ == "__main__":
    main()
