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
# Requires qualified selective-second-read runtime (source ede10f98 or later).
# Cache budget is per MoE layer: 256 MiB × 64 layers, 16.31 GB retained.
$env:CASCADIA_INKLING_EXPERT_CACHE_MIB = '256'
$env:CASCADIA_INKLING_PREFILL_READS = '1'
$env:CASCADIA_INKLING_CACHE_RESET_HISTORY = '1'
$env:CASCADIA_INKLING_CACHE_DECAY_REQUESTS = '32'
# Prefer more recently used experts when decayed frequency counts tie.
$env:CASCADIA_INKLING_CACHE_RECENT_TIES = '1'

# Read one predicted uncached expert before attention; actual routing is unchanged.
$env:CASCADIA_INKLING_PREDICT_READS = '1'
# Earlier prediction remains experimental; retain the confirmed current-layer path.
$env:CASCADIA_INKLING_EARLY_PREDICT_READS = '0'
# Read a second uncached prediction only within the top three predicted ranks.
# Confirmed129; changes only future processes, preserving exact actual routing.
$env:CASCADIA_INKLING_SECOND_PREDICT_READS = '1'
$env:CASCADIA_INKLING_SECOND_PREDICT_RANK = '2'
