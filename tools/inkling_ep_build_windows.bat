@echo off
call C:\BuildTools\VC\Auxiliary\Build\vcvars64.bat
if errorlevel 1 exit /b %errorlevel%
cd /d "%~dp0.."
cargo +stable-x86_64-pc-windows-msvc build --locked --release -j 4 -p cascadia-engine-sparse-moe --example inkling_ep_worker --example inkling_decode_bench --example inkling_ep_layer_bench
exit /b %errorlevel%
