# Inkling on 12 boxes — from this SSD

Everything the installation needs is on this drive:

```
inkling-deploy/          this folder: installers, binaries, runtimes, tools, fleet layout
inkling/out/             the Inkling int4 export (549 GB) + int8 attention/head IRs
```

Twelve Intel Panther Lake boxes (10 × Ubuntu, 2 × Windows 11), one wired
switch, no internet. Each box becomes one rank of a 12-rank pipeline that
serves the OpenAI-compatible API (and the dashboard) from rank 0.

## Per box (about 10 minutes, mostly copying)

1. Plug the SSD in. Decide the box's rank (0–11). Ranks 0 and 11 hold the
   embedding and the output head; the two Windows boxes can be any rank (the
   installer gives them 3 fused layers on the iGPU instead of 5).
2. **Ubuntu:**
   ```
   sudo /media/$USER/<ssd>/inkling-deploy/install.sh <rank>
   ```
   **Windows 11** (PowerShell as administrator):
   ```
   Set-ExecutionPolicy -Scope Process Bypass -Force
   E:\inkling-deploy\install.ps1 -Rank <rank>
   ```
3. Unplug the SSD. The rank starts by itself, now and at every boot, and
   restarts if it stops. `status.sh` / `status.ps1` in the install folder show
   one screen of health.

Order does not matter: a rank keeps retrying its downstream neighbour until
it is up. Rank 0 answers on `http://<IP_0>:8000` once every rank is up.

## Addresses

`fleet.env` assigns `192.168.50.10 + rank` to each box's wired port (added
alongside DHCP, not replacing it). Change the addresses there before
installing if the venue's network is different, or install with `--no-net` /
`-NoNet` and set addresses yourself; the `NEXT` line in each box's `rank.env`
must point at the next rank.

## What runs where

- Experts stay on the CPU with the tuned read profile (the whole slice is
  resident in the expert cache after the first request), except the layers
  the iGPU takes as fused MoE (4 per Ubuntu box, 3 per Windows box, generated
  on the box at install time in about a minute each; `fleet.env` sets the
  counts).
- Attention projections and the output head run on the iGPU from the int8
  IRs on the SSD.
- Without a usable iGPU (no `/dev/dri` render node, no Intel GPU, or
  `--cpu-only`) the rank runs the same CPU profile for everything.

## Showing throughput

From any box on the network (Python 3):

```
python3 inkling-deploy/bench.py http://192.168.50.10:8000 --streams 16 --tokens 64
```

prints per-stream tokens/s, time to first token and the aggregate
tokens/s. `CASCADIA_STREAMS` in `fleet.env` (16) is the most simultaneous
requests the pipeline serves; raise it on every box together.

## If something is off

- `journalctl -u cascadia-inkling -f` (Ubuntu) / `C:\cascadia-inkling\logs\worker.log` (Windows).
- A rank that says `stream slot ... beyond this rank's capacity` has a
  different `CASCADIA_STREAMS` than rank 0.
- `no /dev/dri render node`: the kernel does not expose the Panther Lake
  iGPU; the rank runs on the CPU. Ubuntu 24.04 needs its HWE kernel (6.14+).
- Re-running the installer is safe; it skips what is already done.
