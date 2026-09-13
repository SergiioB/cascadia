"""Byte parity and failure checks for CUDA packing; no transformers model needed."""
import sys
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
torch = pytest.importorskip("torch")
import export_inkling
from inkling_cuda import CudaInt4Packer, CudaInt4PackerPool

cuda = pytest.mark.skipif(not torch.cuda.is_available(), reason="NVIDIA CUDA GPU required")


def test_cpu_default_does_not_initialize_cuda(monkeypatch):
    def forbidden():
        raise AssertionError("CPU export queried CUDA")
    monkeypatch.setattr(torch.cuda, "is_available", forbidden)
    assert export_inkling.make_packer() is export_inkling.pack_int4


def test_missing_cuda_fails_explicitly(monkeypatch):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    with pytest.raises(ValueError, match="accessible NVIDIA"):
        export_inkling.make_packer("cuda")
    with pytest.raises(ValueError, match="requires --device"):
        export_inkling.make_packer("cpu", verify_cuda=True)
    with pytest.raises(ValueError, match="accessible NVIDIA"):
        export_inkling.make_packer("cuda:all")


def test_missing_cuda_does_not_create_export_output(tmp_path, monkeypatch):
    from inkling_ref import TINY_CONFIG
    source, output = tmp_path / "source", tmp_path / "output"
    source.mkdir()
    (source / "config.json").write_text(json.dumps(TINY_CONFIG))
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    with pytest.raises(ValueError, match="accessible NVIDIA"):
        export_inkling.export_real(source, output, device="cuda")
    assert not output.exists()


@pytest.mark.parametrize("device,chunk", [("mps", 64), ("cuda", 0), ("cuda", 257)])
def test_invalid_configuration(device, chunk):
    with pytest.raises(ValueError):
        export_inkling.make_packer(device, chunk)


@cuda
@pytest.mark.parametrize("dtype", [torch.bfloat16, torch.float32, torch.float64])
def test_random_strided_and_multichunk_parity(dtype):
    generator = torch.Generator().manual_seed(271)
    w = (torch.randn(770, 1024, generator=generator) * .05).to(dtype)
    w[0, :32] = 0
    packer = CudaInt4Packer("cuda:0", chunk_mib=1)
    for matrix in (w, w[0::2], w[:768].t(), w[:0]):
        assert packer(matrix) == export_inkling.pack_int4(matrix)


@cuda
def test_half_integer_boundaries_and_scale_rounding():
    # Every half-integer, its two adjacent f32 values, and varied group magnitudes.
    half = torch.arange(-6.5, 7, 1, dtype=torch.float32)
    values = torch.cat((half, torch.nextafter(half, torch.full_like(half, float("inf"))),
                        torch.nextafter(half, torch.full_like(half, float("-inf")))))
    groups = torch.zeros(len(values), 32)
    groups[:, 0] = 7
    groups[:, 1] = values
    scales = torch.tensor([2.**e for e in (-60, -20, -1, 0, 1, 20, 60)] +
                          [1.00390625, 1.01171875, 1.01953125, 35 / 256])
    w = (groups[None] * scales[:, None, None]).reshape(-1, 32)
    packer = CudaInt4Packer(verify=True)
    assert packer(w) == export_inkling.pack_int4(w)
    assert packer(w.bfloat16()) == export_inkling.pack_int4(w.bfloat16())


@cuda
def test_shared_packer_is_safe_across_export_workers():
    packer = CudaInt4Packer(chunk_mib=1)
    generator = torch.Generator().manual_seed(591)
    tensors = [torch.randn(289, 1024, generator=generator).bfloat16() for _ in range(8)]
    expected = [export_inkling.pack_int4(w) for w in tensors]
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(packer, tensors)) == expected


@cuda
def test_verification_rejects_wrong_bytes(monkeypatch):
    packer = CudaInt4Packer(verify=True)
    monkeypatch.setattr(packer, "_pack_chunks", lambda w: (b"wrong", b"wrong"))
    with pytest.raises(RuntimeError, match="output was not written"):
        packer(torch.ones(1, 32))


@cuda
def test_gpu_pool_parity_and_recovery_after_failure():
    pool = CudaInt4PackerPool(chunk_mib=1, verify=True)
    assert len(pool.packers) == torch.cuda.device_count()
    generator = torch.Generator().manual_seed(790)
    matrices = [torch.randn(513, 1024, generator=generator).bfloat16()
                for _ in range(2 * len(pool.packers))]
    with ThreadPoolExecutor(max_workers=len(pool.packers)) as workers:
        assert list(workers.map(pool, matrices)) == [export_inkling.pack_int4(w) for w in matrices]
    # A failed matrix must return its device, otherwise a future export can deadlock.
    for _ in pool.packers:
        with pytest.raises(ValueError, match="CPU matrix"):
            pool(torch.ones(1, 31))
    assert pool(matrices[0]) == export_inkling.pack_int4(matrices[0])
