#!/usr/bin/env python3
"""Session operator for the three LAN NUCs; credentials remain in ~/.secrets.

exec HOST SCRIPT; put HOST ZIP; job HOST JOB_JSON; get HOST REMOTE_RELATIVE LOCAL
Only put/job create files, under the dedicated benchmark root. The SSH config's
old LAN addresses are overridden explicitly; no shared SSH config is edited.
"""
import argparse
import base64
import json
from pathlib import Path, PureWindowsPath
import subprocess

HOSTS = {"alpha": "192.168.0.101", "beta": "192.168.0.103", "charlie": "192.168.0.188"}
ROOT = "C:/Users/tatef/inkling-ep-lan-20260915"
PYTHON = "C:/cascadia/fleet/venv/Scripts/python.exe"


def ssh(host):
    return ["ssh", "-F", str(Path.home()/".secrets/nuc_ssh_config"),
            "-o", "HostName="+HOSTS[host], "-o", "ConnectTimeout=10",
            "-o", "ServerAliveInterval=15", "nuc-"+host]


def ensure_connection(host):
    check = subprocess.run(ssh(host)[:-1]+["-O", "check", ssh(host)[-1]], capture_output=True)
    if check.returncode:
        subprocess.run(["expect", str(Path.home()/".secrets/pexec.exp"),
                        str(Path.home()/".secrets/nuc_pass")]+ssh(host)+["hostname"], check=True, timeout=30)


def remote(host, script, timeout=660):
    ensure_connection(host)
    result = subprocess.run(ssh(host)+[PYTHON+" -"], input=script, text=True,
                            capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"{host}: exit {result.returncode}\n{result.stdout}\n{result.stderr}")
    return result.stdout


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=["exec", "put", "job", "get"])
    p.add_argument("host", choices=HOSTS)
    p.add_argument("path")
    p.add_argument("destination", nargs="?")
    a = p.parse_args()
    if a.command == "exec":
        print(remote(a.host, Path(a.path).read_text()))
    elif a.command == "put":
        data = base64.b64encode(Path(a.path).read_bytes()).decode()
        print(remote(a.host, f'''import pathlib,base64,zipfile,io,json
root=pathlib.Path({ROOT!r})
if root.exists() and any(root.iterdir()) and not (root/'.inkling_ep_deployment').exists():
 raise RuntimeError('refusing an existing unmarked directory')
root.mkdir(parents=True,exist_ok=True)
(root/'.inkling_ep_deployment').write_text('expert routing LAN qualification')
archive=zipfile.ZipFile(io.BytesIO(base64.b64decode({data!r})))
for info in archive.infolist():
 name=pathlib.PurePosixPath(info.filename)
 windows=pathlib.PureWindowsPath(info.filename)
 if name.is_absolute() or windows.drive or windows.root or '..' in windows.parts: raise ValueError('invalid archive path')
archive.extractall(root)
print(json.dumps(dict(root=str(root),files=len(archive.infolist()))))
'''))
    elif a.command == "job":
        job = json.loads(Path(a.path).read_text())
        print(remote(a.host, f'''import pathlib,json,subprocess
root=pathlib.Path({ROOT!r})
job=json.loads({json.dumps(job)!r})
label=job['label']
if not label.replace('-','').replace('_','').isalnum(): raise ValueError('invalid label')
path=root/(label+'.job.json')
with path.open('x') as f: json.dump(job,f)
r=subprocess.run([{PYTHON!r},str(root/'inkling_ep_guard.py'),'--root',str(root),'--job',str(path)],timeout=650)
raise SystemExit(r.returncode)
'''))
    elif a.command == "get":
        name = PureWindowsPath(a.path)
        if name.drive or name.root or ".." in name.parts or not a.destination:
            p.error("get requires a safe relative remote path and local destination")
        data = json.loads(remote(a.host, f'''import json,base64,pathlib
p=pathlib.Path({ROOT!r})/{a.path!r}
print(json.dumps(base64.b64encode(p.read_bytes()).decode()))
'''))
        Path(a.destination).write_bytes(base64.b64decode(data))


if __name__ == "__main__":
    main()
