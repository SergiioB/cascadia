# Package a patched SYCL llama-server build (Windows) into a release zip.
#
# Usage: scripts\package-llama-stream-windows.ps1 BUILD_DIR OUT_ZIP
#   BUILD_DIR  the DEST passed to build-llama-stream-windows.bat (contains build\bin)
#   OUT_ZIP    e.g. cascadia-llama-sycl-windows-x86_64-v0.3.0.zip
#
# Run in the environment used to build the server: vcvars64.bat (for
# dumpbin.exe) and oneAPI setvars.bat (so PATH resolves the SYCL runtime the
# build linked against). Every non-host DLL that the server, its ggml/llama
# DLLs and the dynamically loaded Unified Runtime adapters import is copied flat
# beside llama-server.exe; Windows searches the executable's own directory
# first. Host dependencies, which the destination must provide: Windows system
# DLLs, the MSVC runtime (VC++ redistributable) and the Intel GPU driver
# (Level Zero / OpenCL loaders and ICDs). No oneAPI installation is required.
param(
    [Parameter(Mandatory = $true)][string]$BuildDir,
    [Parameter(Mandatory = $true)][string]$OutZip
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Fail([string]$msg) { [Console]::Error.WriteLine("ERROR: $msg"); exit 1 }

$binDir = (Resolve-Path (Join-Path $BuildDir "build\bin")).Path
$server = Join-Path $binDir "llama-server.exe"
if (-not (Test-Path $server)) { Fail "$server missing - run build-llama-stream-windows.bat first" }
$dumpbin = (Get-Command dumpbin.exe -ErrorAction SilentlyContinue).Source
if (-not $dumpbin) { Fail "dumpbin.exe not on PATH - call vcvars64.bat first" }
$runtimeDir = $env:PATH -split ';' | Where-Object { $_ -and (Test-Path (Join-Path $_ "ur_loader.dll")) } | Select-Object -First 1
if (-not $runtimeDir) { Fail "ur_loader.dll not on PATH - call oneAPI setvars.bat first" }

# The GPU driver owns these; a bundled copy would shadow the driver's own.
$hostNames = '^(ze_loader|ze_intel_gpu.*|ze_tracing_layer|ze_validation_layer|OpenCL|intelocl.*|igdrcl.*|igc.*|msvcp\d+.*|vcruntime\d+.*|concrt\d+|vcomp\d+|ucrtbase.*)\.dll$'

# Native tools write diagnostics to stderr; under "Stop" Windows PowerShell
# turns those into terminating errors. Merge the streams in cmd.exe instead.
function Invoke-Native([string]$exe, [string]$arguments) {
    $out = cmd.exe /d /c "`"$exe`" $arguments 2>&1" | Out-String
    return @{ Code = $LASTEXITCODE; Text = $out }
}

function Get-Imports([string]$file) {
    $r = Invoke-Native $dumpbin "/nologo /dependents `"$file`""
    if ($r.Code -ne 0) { Fail "dumpbin failed on ${file}: $($r.Text)" }
    # Both "Image has the following dependencies" and the delay-load section.
    $r.Text -split "`r?`n" | Select-String '^\s+(\S+\.dll)\s*$' | ForEach-Object { $_.Matches[0].Groups[1].Value }
}

function Resolve-Dll([string]$name, [string]$stage) {
    $staged = Join-Path $stage $name
    if (Test-Path $staged) { return $staged }
    foreach ($dir in ($env:PATH -split ';' | Where-Object { $_ })) {
        $candidate = Join-Path $dir $name
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return (Resolve-Path -LiteralPath $candidate).Path }
    }
    return $null
}

$stageRoot = Join-Path ([IO.Path]::GetTempPath()) ("cascadia-llama-sycl-" + [guid]::NewGuid().ToString("N"))
$pkg = Join-Path $stageRoot "cascadia-llama-sycl"
New-Item -ItemType Directory -Force $pkg | Out-Null
try {
    # The build outputs: server, its wrapper DLLs and the ggml backends.
    Copy-Item $server $pkg
    Get-ChildItem $binDir -Filter *.dll | Copy-Item -Destination $pkg
    # Unified Runtime loads its adapters by name at run time, so imports
    # alone never reach them. Take them from the runtime the build resolved.
    foreach ($pattern in "ur_loader.dll", "ur_win_proxy_loader.dll", "ur_adapter_level_zero*.dll", "ur_adapter_opencl.dll") {
        $found = @(Get-ChildItem $runtimeDir -Filter $pattern)
        if ($found.Count -eq 0 -and $pattern -ne "ur_adapter_opencl.dll") { Fail "$pattern not found in $runtimeDir" }
        $found | Copy-Item -Destination $pkg
    }

    # Walk imports of every bundled PE to a fixed point.
    $queue = [Collections.Generic.Queue[string]]::new()
    $seen = @{}
    Get-ChildItem $pkg -Include *.exe, *.dll -Recurse | ForEach-Object { $queue.Enqueue($_.FullName) }
    $hostDeps = [Collections.Generic.SortedSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    while ($queue.Count -gt 0) {
        $file = $queue.Dequeue()
        if ($seen[$file]) { continue }
        $seen[$file] = $true
        foreach ($dep in Get-Imports $file) {
            if ($dep -match '^(api|ext)-ms-') { continue }          # API sets: resolved by the OS loader
            if ($dep -match $hostNames) { [void]$hostDeps.Add($dep); continue }
            # OS DLLs (dbghelp, wintrust, ...) also ship inside VS/oneAPI dirs
            # that sit earlier on PATH; System32 wins, like the real loader.
            if (Test-Path -LiteralPath (Join-Path "$env:SystemRoot\System32" $dep) -PathType Leaf) { [void]$hostDeps.Add($dep); continue }
            $resolved = Resolve-Dll $dep $pkg
            if (-not $resolved) { Fail "unresolved dependency of ${file}: $dep" }
            $dest = Join-Path $pkg $dep
            if (-not (Test-Path $dest)) {
                Copy-Item -LiteralPath $resolved $dest
                $queue.Enqueue($dest)
            }
        }
    }

    # Patch markers must have survived into the packaged binaries.
    $base = @(Get-ChildItem $pkg -Filter "ggml-base*.dll") + @(Get-Item (Join-Path $pkg "llama-server.exe"))
    if (-not ($base | Select-String -SimpleMatch -Quiet "GGML_STREAM_WEIGHTS")) { Fail "GGML_STREAM_WEIGHTS marker missing - patch 0001 not in this build" }
    $syclDll = @(Get-ChildItem $pkg -Filter "ggml-sycl*.dll")
    if (-not ($syclDll | Select-String -SimpleMatch -Quiet "GGML_STREAM_EXPERT_CACHE_MB")) { Fail "GGML_STREAM_EXPERT_CACHE_MB marker missing - patch 0002 not in this build" }

    # Exercise the staged server as a user would: no oneAPI, no build tree on
    # PATH. --version loads every import; --list-devices loads the UR adapters.
    $savedPath = $env:PATH
    $savedOneApi = $env:ONEAPI_ROOT
    try {
        $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot;$env:SystemRoot\System32\WindowsPowerShell\v1.0"
        Remove-Item Env:ONEAPI_ROOT -ErrorAction SilentlyContinue
        $staged = Join-Path $pkg "llama-server.exe"
        $version = Invoke-Native $staged "--version"
        if ($version.Code -ne 0) { Fail "relocated llama-server --version failed: $($version.Text)" }
        $devices = Invoke-Native $staged "--list-devices"
        if ($devices.Code -ne 0) { Fail "relocated llama-server --list-devices failed: $($devices.Text)" }
    } finally {
        $env:PATH = $savedPath
        if ($savedOneApi) { $env:ONEAPI_ROOT = $savedOneApi }
    }
    Set-Content -Path (Join-Path $pkg "VERSION.txt") -Value $version.Text.Trim()
    Set-Content -Path (Join-Path $pkg "DEVICES.txt") -Value $devices.Text.Trim()
    Set-Content -Path (Join-Path $pkg "HOST-DEPENDENCIES.txt") -Value ($hostDeps -join "`r`n")

    $outFull = [IO.Path]::GetFullPath($OutZip)
    if (Test-Path $outFull) { Remove-Item $outFull }
    Compress-Archive -Path $pkg -DestinationPath $outFull
    $count = @(Get-ChildItem $pkg -Include *.exe, *.dll -Recurse).Count
    $mb = [math]::Round((Get-Item $outFull).Length / 1MB)
    Write-Output "packaged: $outFull ($mb MB, $count PE files)"
    Write-Output "host DLLs (destination provides): $($hostDeps -join ', ')"
} finally {
    Remove-Item -Recurse -Force $stageRoot -ErrorAction SilentlyContinue
}
