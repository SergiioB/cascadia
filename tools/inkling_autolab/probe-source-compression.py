"""Read-only representational probe on the existing miner source export.

No compressed model files are written. Timing includes subprocess/pipe overhead
on the source CPU and must not be interpreted as Panther Lake performance.
"""
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import time

root = Path('/mnt/external_ssd/inkling/out')
samples = []
version = subprocess.run(['zstd', '--version'], capture_output=True, text=True, check=True).stdout.strip()
for layer in (2, 14, 27, 40, 53, 65):
    for expert in (0, 85, 170):
        path = root / f'experts/layer_{layer:02}/expert_{expert:03}.bin'
        raw = path.read_bytes()
        assert len(raw) == 31850496
        source_sha = hashlib.sha256(raw).hexdigest()
        for level in (1, 3):
            start = time.perf_counter()
            packed = subprocess.run(['zstd', '-q', '-c', f'-{level}'], input=raw, capture_output=True, check=True).stdout
            compression_seconds = time.perf_counter() - start
            start = time.perf_counter()
            decoded = subprocess.run(['zstd', '-q', '-d', '-c'], input=packed, capture_output=True, check=True).stdout
            decompression_seconds = time.perf_counter() - start
            assert decoded == raw and hashlib.sha256(decoded).hexdigest() == source_sha
            samples.append(dict(path=str(path.relative_to(root)), level=level, original_bytes=len(raw),
                                compressed_bytes=len(packed), compressed_over_original=len(packed) / len(raw),
                                original_sha256=source_sha, byte_verified=True,
                                source_host_compression_seconds=compression_seconds,
                                source_host_decompression_seconds=decompression_seconds))
report = dict(scope='source_host_lossless_compressibility_probe', source_host=platform.node(),
              zstd_version=version, panther_lake_throughput_measured=False, samples=samples,
              caveats=['18 fixed experts across six layers, not all model weights.',
                       'All compressed data stays in memory; original model files are read only.',
                       'Times include source-host subprocess and pipe overhead; they are not PTL codec throughput.'])
print(json.dumps(report, indent=2))
