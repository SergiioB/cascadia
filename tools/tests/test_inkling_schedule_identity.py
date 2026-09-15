"""The Inkling expert-schedule escape hatches are bit-identical to the default.

`CASCADIA_INKLING_SERIAL_EXPERTS=1` (run a token's experts one after another
instead of concurrently) and `CASCADIA_INKLING_SEQ_READS=1` (fault an mmap'd
expert's pages in during its own GEMV instead of the overlapped whole-bin
read), plus `--experts eager` vs `--experts mmap`, are all documented as
schedule-only switches that must not change any value. Both flags are read
once per process (OnceLock), so this drives the `inkling_layer_dump` example
in separate processes and asserts every dump is byte-for-byte identical.

Only needs cargo + the committed tiny export (no torch/transformers). The
first run pays for the release build of the crate.

    python -m pytest tools/tests/test_inkling_schedule_identity.py -v
"""
from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
from pathlib import Path

import pytest

if shutil.which("cargo") is None:
    pytest.skip("cargo not on PATH", allow_module_level=True)

REPO = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))).parent
EXPORT = REPO / "crates" / "cascadia-engine-sparse-moe" / "tests" / "fixtures" / "inkling_export"
TOKENS = [5, 33, 81, 53, 92, 85]


def _dump(out: Path, experts: str | None, env_flag: str | None) -> None:
    if not (EXPORT / "manifest.json").exists():
        pytest.skip(f"{EXPORT}/manifest.json missing (run export_inkling.py --tiny)")
    cmd = [shutil.which("cargo"), "run", "-p", "cascadia-engine-sparse-moe", "--release",
           "--example", "inkling_layer_dump", "--", "--export", str(EXPORT),
           "--layers", "4", "--tokens", ",".join(map(str, TOKENS)), "--out", str(out)]
    if experts:
        cmd += ["--experts", experts]
    env = dict(os.environ)
    if env_flag:
        env[env_flag] = "1"
    r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=1800, env=env)
    assert r.returncode == 0, f"inkling_layer_dump failed ({r.returncode}):\n{r.stdout}\n{r.stderr}"
    assert out.exists(), out


def _tensors(path: Path) -> tuple[dict, bytes]:
    """The dump's tensor descriptors (minus `__metadata__`) and its data
    section. The `--experts` mode is recorded in `__metadata__`, which is the
    only intended difference between eager and mmap dumps; the values must not
    differ, so compare the descriptors and the raw tensor bytes only."""
    b = path.read_bytes()
    n = struct.unpack("<Q", b[:8])[0]
    header = json.loads(b[8:8 + n])
    header.pop("__metadata__", None)
    return header, b[8 + n:]


def test_schedule_and_read_flags_are_bit_identical(tmp_path):
    # (label, --experts, env flag) — every dump's TENSOR VALUES must match the
    # eager default. eager vs mmap differ only in the recorded experts mode
    # (metadata); SERIAL_EXPERTS / SEQ_READS must change nothing at all.
    variants = [
        ("eager_default", "eager", None),
        ("eager_serial", "eager", "CASCADIA_INKLING_SERIAL_EXPERTS"),
        ("mmap_default", "mmap", None),
        ("mmap_seq_reads", "mmap", "CASCADIA_INKLING_SEQ_READS"),
        ("mmap_serial", "mmap", "CASCADIA_INKLING_SERIAL_EXPERTS"),
    ]
    dumps = {}
    for label, experts, flag in variants:
        out = tmp_path / f"dump_{label}.safetensors"
        _dump(out, experts, flag)
        dumps[label] = _tensors(out)

    base_hdr, base_data = dumps["eager_default"]
    for label, (hdr, data) in dumps.items():
        assert hdr == base_hdr, f"{label}: tensor set/shape/dtype differs from the eager default"
        assert data == base_data, (
            f"{label}: tensor bytes differ from the eager default — a "
            f"schedule/read switch changed a value (it must not)"
        )
