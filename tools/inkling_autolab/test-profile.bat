@echo off
call C:\BuildTools\VC\Auxiliary\Build\vcvars64.bat
if errorlevel 1 exit /b %errorlevel%
cd /d C:\Users\devcloud\inkling-autolab\repo
set CARGO_TARGET_DIR=C:\Users\devcloud\inkling-autolab\target
set RAYON_NUM_THREADS=16
set CASCADIA_BF16_GEMV_ROWS=2
set CASCADIA_INT4_GEMV_ROWS=4
set CASCADIA_INKLING_SEQ_READS=1
rustc +stable-x86_64-pc-windows-msvc -vV
cargo +stable-x86_64-pc-windows-msvc test --release -p cascadia-engine-sparse-moe --test inkling_attn --test inkling_conv --test inkling_ep --test inkling_gate --test inkling_loader --test inkling_model --test inkling_relpos --test inkling_wire
if errorlevel 1 exit /b %errorlevel%
cargo +stable-x86_64-pc-windows-msvc build --release -p cascadia-engine-sparse-moe --example inkling_decode_bench
if errorlevel 1 exit /b %errorlevel%
if exist C:\Users\devcloud\inkling-autolab\bin\full-profile.exe exit /b 1
copy C:\Users\devcloud\inkling-autolab\target\release\examples\inkling_decode_bench.exe C:\Users\devcloud\inkling-autolab\bin\full-profile.exe
if errorlevel 1 exit /b %errorlevel%
C:\Users\devcloud\inkling-autolab\bin\full-profile.exe --export crates/cascadia-engine-sparse-moe/tests/fixtures/inkling_export --cases C:/Users/devcloud/inkling-autolab/fixture-cases.json --allow-fixture --tokens 8 --samples 3 --out C:/Users/devcloud/inkling-autolab/fixture-profile-plain.json
if errorlevel 1 exit /b %errorlevel%
C:\Users\devcloud\inkling-autolab\bin\full-profile.exe --export crates/cascadia-engine-sparse-moe/tests/fixtures/inkling_export --cases C:/Users/devcloud/inkling-autolab/fixture-cases.json --allow-fixture --tokens 8 --samples 3 --out C:/Users/devcloud/inkling-autolab/fixture-profile-observed.json --route-trace C:/Users/devcloud/inkling-autolab/fixture-profile-trace.json --layer-profile C:/Users/devcloud/inkling-autolab/fixture-profile-timing.json
if errorlevel 1 exit /b %errorlevel%
exit /b %errorlevel%
