"""Temporary read-only Inkling export transfer, restricted to tate-07 on Tailscale."""
import hashlib, hmac, json, os, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

ROOT=Path('/mnt/external_ssd/inkling/out').resolve()
STATE=Path('/tmp/inkling-direct-transfer')
TOKEN=(STATE/'token').read_text().strip()
CLIENT='100.82.253.76'
records=[]
for p in sorted(ROOT.rglob('*')):
 if p.is_file() and not p.is_symlink():
  s=p.stat();records.append({'path':p.relative_to(ROOT).as_posix(),'size':s.st_size,'mtime_ns':s.st_mtime_ns})
by_name={r['path']:r for r in records}
manifest=json.dumps({'files':records,'bytes':sum(r['size'] for r in records)}).encode()

class Handler(BaseHTTPRequestHandler):
 protocol_version='HTTP/1.1'
 def authenticated(self):
  return self.client_address[0]==CLIENT and hmac.compare_digest(self.headers.get('Authorization',''), 'Bearer '+TOKEN)
 def reply(self,code,data):
  self.send_response(code);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
 def do_GET(self):
  if not self.authenticated():self.reply(403,b'Forbidden');return
  if self.path=='/manifest':self.reply(200,manifest);return
  kind,sep,name=self.path.lstrip('/').partition('/')
  name=unquote(name)
  if kind not in {'file','sha256'} or name not in by_name:self.reply(404,b'Not found');return
  p=ROOT/name;r=by_name[name]
  if p.is_symlink() or not p.resolve().is_relative_to(ROOT):self.reply(403,b'Forbidden');return
  s=p.stat()
  if s.st_size!=r['size'] or s.st_mtime_ns!=r['mtime_ns']:self.reply(409,b'Source changed');return
  if kind=='sha256':
   h=hashlib.sha256()
   with p.open('rb') as f:
    for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
   self.reply(200,h.hexdigest().encode());return
  start=0;range_header=self.headers.get('Range')
  if range_header:
   if not range_header.startswith('bytes=') or not range_header.endswith('-'):self.reply(400,b'Bad range');return
   try:start=int(range_header[6:-1])
   except ValueError:self.reply(400,b'Bad range');return
   if not 0<=start<r['size']:self.reply(416,b'Bad range');return
  self.send_response(206 if start else 200)
  self.send_header('Content-Length',str(r['size']-start))
  if start:self.send_header('Content-Range',f'bytes {start}-{r["size"]-1}/{r["size"]}')
  self.end_headers()
  try:
   with p.open('rb') as f:
    f.seek(start)
    for b in iter(lambda:f.read(1024*1024),b''):self.wfile.write(b)
  except (BrokenPipeError,ConnectionResetError):pass
 def do_POST(self):
  if not self.authenticated():self.reply(403,b'Forbidden');return
  if self.path!='/shutdown':self.reply(404,b'Not found');return
  self.reply(200,b'Stopping');threading.Thread(target=self.server.shutdown,daemon=True).start()
 def log_message(self,*args):pass

server=ThreadingHTTPServer(('100.103.4.77',18867),Handler)
server.daemon_threads=True
(STATE/'pid').write_text(str(os.getpid()))
# Automatic expiry avoids leaving a transfer endpoint behind after interruption.
timer=threading.Timer(96*3600,server.shutdown);timer.daemon=True;timer.start()
print('Serving only the Inkling export to tate-07; bound to Tailscale; expires in 96h.',flush=True)
try:server.serve_forever()
finally:
 server.server_close();(STATE/'token').unlink(missing_ok=True)
