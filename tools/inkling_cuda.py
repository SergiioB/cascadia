"""Optional, bounded CUDA int4 packing for export_inkling (CPU remains the default)."""
from __future__ import annotations

import threading
from queue import SimpleQueue


class CudaInt4PackerPool:
    """Use every visible NVIDIA GPU, assigning matrices to the next available one."""

    def __init__(self, *, chunk_mib=64, verify=False):
        import torch

        if not torch.cuda.is_available() or torch.version.hip is not None:
            raise ValueError("CUDA export needs an accessible NVIDIA GPU and a CUDA-enabled PyTorch build")
        self.packers = [CudaInt4Packer(f"cuda:{index}", chunk_mib=chunk_mib, verify=verify)
                        for index in range(torch.cuda.device_count())]
        self.available = SimpleQueue()
        for packer in self.packers:
            self.available.put(packer)

    def __call__(self, w):
        packer = self.available.get()
        try:
            return packer(w)
        finally:
            self.available.put(packer)


class CudaInt4Packer:
    """CPU tensor -> the existing packed-nibble/bf16-scale byte layout.

    One exporter shares this object across its I/O workers. A lock bounds GPU
    allocations to one chunk's operations, while other workers can read/write.
    chunk_mib limits the f32-equivalent input, not the total temporary allocation.
    All device-to-host copies complete before bytes are returned to atomic writers.
    """

    def __init__(self, device="cuda", *, chunk_mib=64, verify=False):
        import torch

        self.device = torch.device(device)
        if self.device.type != "cuda":
            raise ValueError("export device must be cpu, cuda or cuda:N")
        if not isinstance(chunk_mib, int) or not 1 <= chunk_mib <= 256:
            raise ValueError("--cuda-chunk-mib must be between 1 and 256")
        if not torch.cuda.is_available() or torch.version.hip is not None:
            raise ValueError("CUDA export needs an accessible NVIDIA GPU and a CUDA-enabled PyTorch build")
        index = self.device.index if self.device.index is not None else torch.cuda.current_device()
        if index >= torch.cuda.device_count():
            raise ValueError(f"CUDA device {index} is unavailable")
        self.device = torch.device("cuda", index)
        # A Python scalar divisor triggers PyTorch CUDA's reciprocal-multiply
        # shortcut, which changes rounding (and int4 nibbles at half-integers).
        # A device tensor selects true division, matching the CPU format.
        self.seven = torch.tensor(7.0, dtype=torch.float32, device=self.device)
        self.chunk_bytes = chunk_mib * 1024 * 1024
        self.verify = verify
        self.lock = threading.Lock()
        self._self_test()
        print(f"[quantizer] device={self.device} gpu={torch.cuda.get_device_name(index)} "
              f"chunk_mib={chunk_mib} verify_every_matrix={int(verify)} startup_parity=passed", flush=True)

    def __call__(self, w):
        import torch
        from export_inkling import pack_int4

        if w.device.type != "cpu" or w.ndim != 2 or w.shape[1] == 0 or w.shape[1] % 32:
            raise ValueError("CUDA packer expects a CPU matrix with positive input width divisible by 32")
        with self.lock, torch.inference_mode(), torch.cuda.device(self.device):
            result = self._pack_chunks(w)
        if self.verify and result != pack_int4(w):
            raise RuntimeError("CUDA int4 bytes differ from the CPU reference; output was not written")
        return result

    def _pack_chunks(self, w):
        import torch

        out, inn = w.shape
        rows = max(1, self.chunk_bytes // (inn * 4))
        packed_bytes = bytearray(out * inn // 2)
        scale_bytes = bytearray(out * (inn // 32) * 2)
        for lo in range(0, out, rows):
            hi = min(lo + rows, out)
            # Copy bf16 as bf16, then promote on the GPU instead of doubling PCIe traffic.
            x = w[lo:hi].to(self.device).float().contiguous()
            grouped = x.view(hi - lo, inn // 32, 32)
            maximum = grouped.abs().amax(dim=2)
            scale = torch.where(maximum > 0, maximum / self.seven, torch.ones_like(maximum))
            q = torch.clamp(torch.round(grouped / scale[:, :, None]), -8, 7).to(torch.int16)
            nibble = (q + 8).to(torch.uint8).view(hi - lo, inn)
            packed = (nibble[:, 0::2] | (nibble[:, 1::2] << 4)).contiguous()
            bf = scale.to(torch.bfloat16).view(torch.int16).contiguous()
            packed_bytes[lo * inn // 2:hi * inn // 2] = packed.cpu().numpy().tobytes()
            scale_bytes[lo * (inn // 32) * 2:hi * (inn // 32) * 2] = bf.cpu().numpy().tobytes()
        return bytes(packed_bytes), bytes(scale_bytes)

    def _self_test(self):
        """Reject a backend whose arithmetic changes the established format before export writes."""
        import torch
        from export_inkling import pack_int4

        generator = torch.Generator(device="cpu").manual_seed(817)
        random = torch.randn(65, 96, generator=generator, device="cpu") * 0.05
        boundary = torch.tensor([0., -0., 7., -7., .5, -.5, 1.5, -1.5,
                                 2.5, -2.5, 3.5, -3.5, 4.5, -4.5, 5.5, -5.5,
                                 6.5, -6.5, 0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0., 0.],
                                dtype=torch.float32, device="cpu").reshape(1, 32)
        for w in (torch.zeros(1, 32), boundary, random, random.bfloat16(), random[0::2]):
            with torch.inference_mode(), torch.cuda.device(self.device):
                if self._pack_chunks(w) != pack_int4(w):
                    raise RuntimeError("CUDA startup byte parity failed; use --device cpu")
