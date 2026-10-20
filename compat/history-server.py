#!/usr/bin/env python3
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs, quote
from html import escape
import sqlite3,json
from map_history import get_history
BASE=Path(__file__).parent
from runtime import DATA
DB=DATA/'history.sqlite'
def render(item=None,kind=None):
 if kind is not None and kind not in {'items','devices','people'}:raise ValueError('Unknown observation type.')
 with closing(sqlite3.connect(DB.as_uri()+'?mode=ro',uri=True)) as db:
  db.row_factory=sqlite3.Row
  rows=db.execute('SELECT o.* FROM observations o JOIN (SELECT kind,name,max(id) id FROM observations GROUP BY kind,name) last ON o.id=last.id ORDER BY o.kind DESC,o.name COLLATE NOCASE').fetchall()
  latest=db.execute('SELECT max(ts) FROM observations').fetchone()[0]
 def e(s):return escape(str(s or '—'))
 def stamp(s):return '<time datetime="'+e(s)+'">'+e(s)+'</time>'
 cards=''.join('<tr><td><a href="/?item='+quote(r['name'],safe='')+'&amp;kind='+quote(r['kind'],safe='')+'">'+e(r['name'])+'</a></td><td>'+e({'items':'Item','devices':'Device','people':'Person'}.get(r['kind'],r['kind']))+'</td><td>'+e(r['location'])+'</td><td>'+e(r['distance'])+'</td><td>'+e(r['staleness'])+'</td><td>'+stamp(r['ts'])+'</td></tr>' for r in rows)
 detail=(BASE/'map-panel.html').read_text().replace('__ITEM__',e(item)) if item else ''
 health=''
 try:
  check=json.loads((DB.parent/'collection-status.json').read_text())
  if not check.get('ok'):
   message='Latest collection was incomplete. Some items may have older observations.' if check.get('missing') else 'Latest collection failed. Showing previously saved observations.'
   health='<p class="status stale">'+message+'</p>'
 except (OSError,ValueError):pass
 try:
  devices=json.loads((DB.parent/'device-collection-status.json').read_text())
  if not devices.get('ok'):health+='<p class="status stale">The latest Devices scan did not complete. Previously saved device readings may be old.</p>'
 except (OSError,ValueError):pass
 try:
  control=json.loads((DB.parent/'scan-control.json').read_text())
  if control.get('mode')=='waiting_for_idle':health='<p class="status">Scans paused while the Mac is in use. They resume after two minutes without mouse or keyboard activity.</p>'+health
  elif control.get('mode')=='waiting_for_screen_sharing':health='<p class="status">Scans paused while Screen Sharing is connected. They resume once it disconnects and the Mac has been idle for two minutes.</p>'+health
 except (OSError,ValueError):pass
 content=detail if item else '<div class="table-wrap"><table><tr><th>Name</th><th>Type</th><th>Last displayed location</th><th>Displayed distance</th><th>Find My age at recording</th><th>Recorded</th></tr>'+cards+'</table></div>'
 counts=' · '.join(str(sum(r['kind']==kind for r in rows))+' '+kind for kind in ('items','devices'))
 return '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TagTracker</title><link rel="icon" href="/static/favicon.svg" type="image/svg+xml"><style>body{font:16px system-ui;margin:40px auto;max-width:1100px;padding:0 20px;background:#f5f7fa;color:#182333}h1{font-size:32px}p{color:#536174;line-height:1.6}.table-wrap{max-width:100%;overflow-x:auto}table{width:100%;border-collapse:collapse;background:white;border-radius:12px}th,td{text-align:left;padding:14px;border-bottom:1px solid #e8edf2}th{font-size:13px;color:#536174}a{color:#155fc1;text-decoration:none}section{margin-top:36px}.status{padding:12px 16px;background:#e3f3e9;border-radius:10px}.stale{background:#fff0cc}@media(max-width:700px){body{margin:20px auto}table{font-size:12px}td,th{padding:8px}}</style><h1><a href="/">TagTracker</a></h1>'''+f'<p>{counts} · Scans every five minutes when this Mac is idle</p><p class="status" id="status" data-latest="{e(latest)}">Last collection: {stamp(latest)}</p><p>Locations and ages are copied from Find My. Collection time is when the server read the screen; it is not a new location report. Select an item or device to see its history.</p>{health}{content}'+'''<p>Keep this Mac awake, logged in and unlocked. This records displayed places, not precise GPS routes. History stays on that Mac.</p><script>document.querySelectorAll('time').forEach(t=>{t.textContent=new Date(t.dateTime).toLocaleString()});const s=document.getElementById('status');if(Date.now()-new Date(s.dataset.latest)>600000){s.classList.add('stale');s.prepend('Collection is overdue. ')}</script></html>'''
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  u=urlparse(self.path)
  if u.path=='/api/history':
   q=parse_qs(u.query)
   try:
    item=q.get('item',[''])[0]
    if not item:raise ValueError('Select an item.')
    data=get_history(DB,item,q.get('range',['24h'])[0],q.get('start',[None])[0],q.get('end',[None])[0],kind=q.get('kind',[None])[0])
    self.reply(200,'application/json',json.dumps(data).encode())
   except ValueError as e:self.reply(400,'application/json',json.dumps({'error':str(e)}).encode())
   except Exception:self.reply(503,'application/json',b'{"error":"History is unavailable. Try again shortly."}')
   return
  static={'/static/leaflet.js':'text/javascript','/static/leaflet.css':'text/css','/static/map.js':'text/javascript','/static/map.css':'text/css','/static/favicon.svg':'image/svg+xml'}
  if u.path in static:
   self.reply(200,static[u.path],(BASE/u.path.lstrip('/')).read_bytes());return
  if u.path!='/': self.send_error(404);return
  try:
   q=parse_qs(u.query);data=render(q.get('item',[None])[0],q.get('kind',[None])[0]).encode()
  except Exception:self.send_error(503,'History is not available yet');return
  self.reply(200,'text/html; charset=utf-8',data)
 def reply(self,status,kind,data):
  self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(data)
 def log_message(self,*args):pass
if __name__=='__main__':ThreadingHTTPServer(('127.0.0.1',8768),Handler).serve_forever()
