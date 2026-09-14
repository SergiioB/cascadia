@echo off
call C:\BuildTools\VC\Auxiliary\Build\vcvars64.bat
if errorlevel 1 exit /b %errorlevel%
cd /d C:\Users\devcloud\inkling-autolab\repo
set CARGO_TARGET_DIR=C:\Users\devcloud\inkling-autolab\target
set RAYON_NUM_THREADS=16
set CASCADIA_INKLING_CACHE_DECAY_REQUESTS=32
set CASCADIA_INKLING_CACHE_RECENT_TIES=0
set CASCADIA_BF16_GEMV_ROWS=2
set CASCADIA_INT4_GEMV_ROWS=4
set CASCADIA_INKLING_SEQ_READS=0
set CASCADIA_INKLING_REUSE_READ_BUFFERS=1
set CASCADIA_INKLING_SKIP_BULK_PREFETCH=1
set CASCADIA_INKLING_MMAP_EMBED=1
set CASCADIA_INKLING_OWN_SHARED=1
set CASCADIA_INKLING_UNCACHED_READS=1
set CASCADIA_INKLING_PIPELINE_READS=1
set CASCADIA_INKLING_EXPERT_CACHE_MIB=1
set CASCADIA_INKLING_PREFILL_READS=1
set CASCADIA_INKLING_CACHE_RESET_HISTORY=0
if exist C:\Users\devcloud\inkling-autolab\bin\full-route-prediction.exe exit /b 1
rustc +stable-x86_64-pc-windows-msvc -vV
cargo +stable-x86_64-pc-windows-msvc test --locked --release -p cascadia-engine-sparse-moe --lib --test inkling_attn --test inkling_conv --test inkling_ep --test inkling_gate --test inkling_loader --test inkling_model --test inkling_relpos --test inkling_wire --test glm5_loader --test glm5_moe --test glm5_expert_mmap --test glm5_layer
if errorlevel 1 exit /b %errorlevel%
cargo +stable-x86_64-pc-windows-msvc build --locked --release -p cascadia-engine-sparse-moe --example inkling_decode_bench
if errorlevel 1 exit /b %errorlevel%
if exist C:\Users\devcloud\inkling-autolab\bin\full-route-prediction.exe exit /b 1
copy C:\Users\devcloud\inkling-autolab\target\release\examples\inkling_decode_bench.exe C:\Users\devcloud\inkling-autolab\bin\full-route-prediction.exe
if errorlevel 1 exit /b %errorlevel%
exit /b 0
