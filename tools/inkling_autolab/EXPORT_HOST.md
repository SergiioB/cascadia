# A100 export host lifecycle

The qualified host is `ubuntu@129.146.170.51`, Lambda.ai, eight A100 SXM4
40 GB GPUs, no attached persistent filesystem. The default export profile is
eight independent CUDA processes, one worker per process, 64 MiB chunks.

## Release readiness, 2026-09-13

All exporter tests/benchmarks ended, GPUs idle. No raw checkpoint was downloaded;
`source` contains only the 2,415-byte model config and `exports` is empty.
The deployed exporter code, all task logs, source config and exact package freeze
are backed up on the controller at:

`/Users/tatef/Workspaces/inkling-export-backups/20260913/inkling-export-release-20260913.tar.gz`

The archive is 345,278 bytes. Its SHA-256 matches the source:
`743ebc8229913500e5eda01bea4994128503e7ea2eaf819cb633b913d7b2a5f2`.
An extracted copy is alongside it under `snapshot`. Quantization tests, export
measurements and source code are also committed in this branch. The 5.4 GiB
virtual environment is reproducible from `export-requirements.lock.txt`.

The full exported model remains independently on miner and is SHA-256 verified
on PTL. Current PTL inference experiments need no rental or new export.

Lambda bills until instance termination; guest shutdown still bills, and
suspension is unsupported. Termination destroys the instance's local storage.
Use the Lambda console for **129.146.170.51** when releasing it. No provider
account access or termination was performed by this session.

Source: https://docs.lambda.ai/public-cloud/on-demand/creating-managing-instances/

## Restore on a future Linux NVIDIA rental

Use the committed branch `perf/inkling-panther-autolab`. Set up only the isolated
`/home/ubuntu/inkling-export` root; keep any unrelated host services intact.
Copy the repository's `tools` directory into `inkling-export/repo/tools`.
The following recipe reconstructs the qualified environment; the pinned install dry run against the qualified environment checked 56 packages
and would make no changes. A fresh rebuild has not been timed. It requires a compatible NVIDIA driver (qualified: 580.105.08).

```sh
mkdir -p /home/ubuntu/inkling-export/{repo,source,exports,scratch,logs}
python3 -m venv /home/ubuntu/inkling-export/bootstrap
/home/ubuntu/inkling-export/bootstrap/bin/pip install uv==0.12.13
/home/ubuntu/inkling-export/bootstrap/bin/uv python install 3.12.14
/home/ubuntu/inkling-export/bootstrap/bin/uv venv --python 3.12.14 /home/ubuntu/inkling-export/venv
/home/ubuntu/inkling-export/bootstrap/bin/uv pip install \
  --python /home/ubuntu/inkling-export/venv/bin/python \
  --extra-index-url https://download.pytorch.org/whl/cu130 \
  -r /home/ubuntu/inkling-export/repo/tools/inkling_autolab/export-requirements.lock.txt
cd /home/ubuntu/inkling-export/repo
/home/ubuntu/inkling-export/venv/bin/python -m pytest tools/tests/test_inkling_cuda.py tools/tests/test_inkling_export.py -q
```

Update the controller's `export-host.json` with the replacement host/SSH identity
before launching. Do not embed keys in the repository. `export-remote.py --host`
also supports an override. Full parallel exports require all raw source shards
locally and retain them for reproducibility/resumption. Do not initiate the
1.905 TB download until the loop needs an actual new export.

## Planning estimate

Eight independent GPU processes converted 64 production-sized synthetic experts
at a median **58.980 experts/s**, with CPU-byte-exact output in all repetitions.
Scaling only that measured expert stage gives **4.67 minutes / $1.17** at $15/h.
Budget **15–30 minutes / $4–8** for a full export with source local, or **2–3
hours / $30–45** including the first download. These are extrapolations, not
timed full exports. Cold I/O, shell conversion and network variance remain.
The per-expert rate is 4.62x miner CUDA / 10.93x miner CPU across different batch
sizes; this is not a matched full-export comparison. See results 017, 018, 021.

Delivery is a separate stage. At the observed miner-to-PTL rate of 103.70 MB/s,
copying a fresh 548.99 GB export would take about **88 minutes**. The rental's
direct path has not been timed, so this is a PTL-link planning estimate. If
the A100 must stay running solely to serve that copy, budget roughly **$22
more** at $15/hour. The current model is already fully on PTL and incurs no
such dependency. Do not keep the rental waiting for PTL inference experiments.
