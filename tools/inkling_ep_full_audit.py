#!/usr/bin/env python3
"""Read-only final service, disk and task-cleanup audit for the authorized NUCs."""
import argparse
import concurrent.futures
import json
from pathlib import Path

from inkling_ep_lan_control import ROOT, HOSTS, remote
from inkling_ep_full_run import RULE, PORT


def audit(host):
    script = '''from pathlib import Path
import sys,json,psutil,subprocess,urllib.request,datetime
root=Path(ROOT);sys.path.insert(0,str(root))
from inkling_ep_guard import protected
ours=[]
for p in psutil.process_iter(['pid','name','exe','cmdline']):
 exe=(p.info['exe'] or '').lower()
 args=' '.join(p.info['cmdline'] or []).replace('\\\\','/').lower()
 if exe.startswith(str(root).lower()) or str(root).replace('\\\\','/').lower() in args:
  ours.append(dict(pid=p.pid,name=p.info['name']))
ps="$r=@(Get-NetFirewallRule -Name 'RULE' -ErrorAction SilentlyContinue); ConvertTo-Json -Compress -InputObject @($r | Select-Object Name)"
r=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',ps],capture_output=True,text=True,check=True)
rules=json.loads(r.stdout.strip() or '[]')
listeners=[c.pid for c in psutil.net_connections(kind='tcp') if c.status=='LISTEN' and c.laddr.port in range(PORT,PORT+4)]
health={n:urllib.request.urlopen('http://127.0.0.1:9000/v2/health/'+n,timeout=3).status for n in ['live','ready']}
print(json.dumps(dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),protected=protected(),health=health,
 task_processes_absent=not ours,task_processes=ours,firewall_absent=not rules,firewall_rules=rules,
 task_listeners_absent=not listeners,task_listener_pids=listeners,
 free_gib=psutil.disk_usage(str(root)).free/2**30,available_gib=psutil.virtual_memory().available/2**30)))
'''.replace('ROOT',repr(ROOT)).replace('RULE',RULE).replace('PORT',str(PORT))
    return json.loads(remote(host,script,40))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',required=True,type=Path)
    a=p.parse_args()
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        result=dict(zip(HOSTS,pool.map(audit,HOSTS)))
    with a.out.open('x') as f:
        json.dump(result,f,indent=2)
        f.write('\n')
    print(json.dumps({h:{k:r[k] for k in ['health','task_processes_absent','firewall_absent','free_gib']} for h,r in result.items()}))


if __name__=='__main__':
    main()
