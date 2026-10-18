#!/usr/bin/env python3
"""Run the real dashboard against temporary, fictional data. No Find My access."""
import argparse,importlib.util,json,os,sqlite3,sys,tempfile
from datetime import datetime,timedelta,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PLACES={
 'Ferry Building':(37.7955,-122.3937),
 'Embarcadero':(37.8024,-122.3981),
 'Coit Tower':(37.8024,-122.4058),
 'Museum stop':(37.7857,-122.4011),
 'Dolores Park':(37.7596,-122.4269),
 'Golden Gate Park':(37.7694,-122.4862),
 'Golden Gate Bridge':(37.8199,-122.4783),
}
def seed(data):
 now=datetime.now(timezone.utc)
 items={'Demo backpack':[(0,0),(.12,1),(.25,2),(.5,3),(1.2,4),(2,3),(3,5),(5,4),(7,5),(10,6)],'Demo keys':[(0,0),(1,0),(3,0),(8,0)],'Demo suitcase':[(0,5),(2,5),(6,0),(9,3)]}
 with sqlite3.connect(data/'history.sqlite') as c:
  c.execute('CREATE TABLE observations(id INTEGER PRIMARY KEY,ts TEXT,kind TEXT,name TEXT,location TEXT,staleness TEXT,distance TEXT,battery TEXT,raw_json TEXT)')
  for item,records in items.items():
   for days,index in reversed(records):
    c.execute('INSERT INTO observations(ts,kind,name,location,staleness,distance,battery,raw_json) VALUES (?,?,?,?,?,?,?,?)',((now-timedelta(days=days)).isoformat(),'item',item,list(PLACES)[index],'Now','','','{}'))
 (data/'saved-places.json').write_text(json.dumps({name:{'lat':lat,'lon':lon,'precision':'Fictional demo observation at a public landmark'} for name,(lat,lon) in PLACES.items()}))
 (data/'collection-status.json').write_text('{"ok":true}')
 (data/'scan-control.json').write_text('{"mode":"scheduled"}')
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--port',type=int,default=8769);args=parser.parse_args()
 with tempfile.TemporaryDirectory(prefix='tagtracker-demo-') as temp:
  data=Path(temp);seed(data)
  os.environ['TAGTRACKER_DATA_DIR']=str(data)
  sys.path.insert(0,str(ROOT/'compat'))
  spec=importlib.util.spec_from_file_location('demo_dashboard',ROOT/'compat/history-server.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  server=module.ThreadingHTTPServer(('127.0.0.1',args.port),module.Handler)
  print(f'http://127.0.0.1:{server.server_port}/',flush=True)
  try:server.serve_forever()
  except KeyboardInterrupt:pass
  finally:server.server_close()
if __name__=='__main__':main()
