# Dot-source this file before starting a NEW Inkling process on tate-07:
#   . .\ptl-profile.ps1
# Settings affect this shell and its future children only. No service is restarted.
# See PERFORMANCE.md for validation status and measured hardware/launch conditions.
$env:RAYON_NUM_THREADS = '16'
$env:CASCADIA_INKLING_SERIAL_EXPERTS = '0'
$env:CASCADIA_INKLING_SEQ_READS = '0'
$env:CASCADIA_INKLING_PIN_EXPERTS = '0'
$env:CASCADIA_BF16_GEMV_ROWS = '2'
$env:CASCADIA_INT4_GEMV_ROWS = '4'
$env:CASCADIA_INKLING_MMAP_EMBED = '1'
$env:CASCADIA_INKLING_REUSE_READ_BUFFERS = '1'
$env:CASCADIA_INKLING_SKIP_BULK_PREFETCH = '1'
$env:CASCADIA_INKLING_OWN_SHARED = '1'
$env:CASCADIA_INKLING_UNCACHED_READS = '1'
$env:CASCADIA_INKLING_PIPELINE_READS = '1'
