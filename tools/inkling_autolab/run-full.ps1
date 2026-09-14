param([Parameter(Mandatory=$true)][string]$Model,
      [Parameter(Mandatory=$true)][string]$Cases,
      [int]$Reads=0, [int]$Bf16Rows=1, [int]$Int4Rows=1,
      [int]$Tokens=64, [int]$Samples=3, [string]$Out='',
      [string]$Binary='full-decode.exe', [string]$RouteTrace='',
      [string]$LayerProfile='', [ValidateSet(0,1)][int]$MmapEmbed=0, [string]$Log='',
      [ValidateSet(0,1)][int]$ReuseBuffers=0, [ValidateSet(0,1)][int]$SkipBulkPrefetch=0,
      [ValidateSet(0,1)][int]$OwnShared=0,
      [ValidateSet(0,1)][int]$UncachedReads=0,
      [ValidateSet(0,1)][int]$PipelineReads=0,
      [ValidateRange(0,256)][int]$ExpertCacheMiB=0,
      [switch]$AllowFixture)
$ErrorActionPreference = 'Stop'
$root = 'C:\Users\devcloud\inkling-autolab'
if (!(Test-Path (Join-Path $Model 'manifest.json'))) {
    throw "Full Inkling checkpoint unavailable at $Model; cannot measure full-model throughput."
}
if (!(Test-Path $Cases)) { throw "Missing benchmark cases: $Cases" }
if ([System.IO.Path]::GetFileName($Binary) -ne $Binary) { throw 'Binary must be a filename under the task bin directory' }
if ($RouteTrace -and $Binary -eq 'full-decode.exe') { throw 'The frozen baseline has no routing observer; select full-routing.exe' }
if ($LayerProfile -and $Binary -in @('full-decode.exe', 'full-routing.exe')) { throw 'Select full-profile.exe for layer timing' }
if ($MmapEmbed -and $Binary -in @('full-decode.exe', 'full-routing.exe', 'full-profile.exe')) { throw 'Select full-mmap-embed.exe for mapped embedding' }
if (($ReuseBuffers -or $SkipBulkPrefetch) -and $Binary -notin @('full-read-buffers.exe', 'full-owned-shared.exe', 'full-uncached.exe', 'full-pipeline.exe', 'full-expert-cache.exe')) { throw 'Select a qualified read-buffer binary for reusable read options' }
if ($OwnShared -and $Binary -notin @('full-owned-shared.exe', 'full-uncached.exe', 'full-pipeline.exe', 'full-expert-cache.exe')) { throw 'Select a qualified owned-shared binary' }
if ($UncachedReads -and ($Binary -notin @('full-uncached.exe', 'full-pipeline.exe', 'full-expert-cache.exe') -or !$ReuseBuffers -or $Reads)) { throw 'Uncached reads require a qualified binary, ReuseBuffers1 and Reads0' }
if ($PipelineReads -and ($Binary -notin @('full-pipeline.exe', 'full-expert-cache.exe') -or !$ReuseBuffers -or $Reads)) { throw 'Pipelined reads require qualified full-pipeline.exe, ReuseBuffers1 and Reads0' }
if ($ExpertCacheMiB -and ($Binary -ne 'full-expert-cache.exe' -or !$PipelineReads -or !$ReuseBuffers -or $Reads)) { throw 'Expert caching requires qualified full-expert-cache.exe, PipelineReads1, ReuseBuffers1 and Reads0' }
$env:RAYON_NUM_THREADS = '16'
$env:CASCADIA_INKLING_SERIAL_EXPERTS = '0'
$env:CASCADIA_INKLING_SEQ_READS = "$Reads"
$env:CASCADIA_INKLING_PIN_EXPERTS = '0'
$env:CASCADIA_INKLING_MMAP_EMBED = "$MmapEmbed"
$env:CASCADIA_INKLING_REUSE_READ_BUFFERS = "$ReuseBuffers"
$env:CASCADIA_INKLING_SKIP_BULK_PREFETCH = "$SkipBulkPrefetch"
$env:CASCADIA_INKLING_OWN_SHARED = "$OwnShared"
$env:CASCADIA_INKLING_UNCACHED_READS = "$UncachedReads"
$env:CASCADIA_INKLING_PIPELINE_READS = "$PipelineReads"
$env:CASCADIA_INKLING_EXPERT_CACHE_MIB = "$ExpertCacheMiB"
$env:CASCADIA_BF16_GEMV_ROWS = "$Bf16Rows"
$env:CASCADIA_INT4_GEMV_ROWS = "$Int4Rows"
[System.Diagnostics.Process]::GetCurrentProcess().ProcessorAffinity = [IntPtr]65535
$benchArgs = @('--export', "`"$Model`"", '--cases', "`"$Cases`"", '--tokens', "$Tokens", '--samples', "$Samples")
if ($Out) { $benchArgs += @('--out', "`"$Out`"") }
if ($RouteTrace) { $benchArgs += @('--route-trace', "`"$RouteTrace`"") }
if ($LayerProfile) { $benchArgs += @('--layer-profile', "`"$LayerProfile`"") }
if ($AllowFixture) { $benchArgs += '--allow-fixture' }
$startOptions = @{}
if ($Log) {
    if ((Test-Path $Log) -or (Test-Path "$Log.stderr")) { throw "Refusing to overwrite benchmark log: $Log" }
    $startOptions.RedirectStandardOutput = $Log
    $startOptions.RedirectStandardError = "$Log.stderr"
}
$p = Start-Process -FilePath "$root\bin\$Binary" -ArgumentList $benchArgs -PassThru -NoNewWindow @startOptions
try {
    $p.PriorityClass = 'High'
    $p.ProcessorAffinity = [IntPtr]65535
    "bf16_rows=$Bf16Rows int4_rows=$Int4Rows reads=$Reads mmap_embed=$MmapEmbed reuse_buffers=$ReuseBuffers skip_bulk_prefetch=$SkipBulkPrefetch own_shared=$OwnShared uncached_reads=$UncachedReads pipeline_reads=$PipelineReads expert_cache_mib=$ExpertCacheMiB"
    $p.WaitForExit()
    if ($Log) {
        Get-Content -LiteralPath $Log -Encoding UTF8
        Get-Content -LiteralPath "$Log.stderr" -Encoding UTF8 | ForEach-Object { [Console]::Error.WriteLine($_) }
    }
    exit $p.ExitCode
} finally {
    if (!$p.HasExited) { $p.Kill(); $p.WaitForExit() }
    $p.Dispose()
}
