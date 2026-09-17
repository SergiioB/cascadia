@echo off
rem Usage: inkling_ep_qualify_windows.bat PYTHON_EXE NEW_RESULTS_DIR
if "%~2"=="" exit /b 2
call C:\BuildTools\VC\Auxiliary\Build\vcvars64.bat
if errorlevel 1 exit /b %errorlevel%
cd /d "%~dp0.."
if not defined CARGO_TARGET_DIR set CARGO_TARGET_DIR=%CD%\target
set RAYON_NUM_THREADS=4
cargo +stable-x86_64-pc-windows-msvc test --locked -p cascadia-engine-sparse-moe --test inkling_ep
if errorlevel 1 exit /b %errorlevel%
cargo +stable-x86_64-pc-windows-msvc build --locked -p cascadia-engine-sparse-moe --example inkling_decode_bench --example inkling_ep_worker
if errorlevel 1 exit /b %errorlevel%
"%~1" tools\inkling_ep_smoke.py --bin-dir "%CARGO_TARGET_DIR%\debug\examples" --out "%~2"
if errorlevel 1 exit /b %errorlevel%
"%~1" tools\inkling_ep_smoke.py --bin-dir "%CARGO_TARGET_DIR%\debug\examples" --out "%~2-owned" --owned-workers
exit /b %errorlevel%
