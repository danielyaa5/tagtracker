#!/usr/bin/env python3
"""Configure TagTracker without modifying another installation."""
import argparse,json,os,plistlib,shutil,sqlite3,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'compat'))
from runtime import BASE,DATA
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--item',action='append',default=[],help='Exact item name in Find My; repeat for each item')
p.add_argument('--devices',action='store_true',help='Also record the Devices sidebar during each idle scan')
p.add_argument('--devices-enabled',choices=['yes','no'],help='Explicitly enable or disable Devices collection')
p.add_argument('--load',action='store_true',help='Load the three generated user LaunchAgents')
p.add_argument('--update',action='store_true',help='Update this installation while preserving aliases and history')
p.add_argument('--python',default=sys.executable,help='Absolute Python interpreter path for the history service')
p.add_argument('--output',type=Path,default=Path.home()/'Library/LaunchAgents')
a=p.parse_args()
os.umask(0o077)
config=DATA/'item-names.json'
if not a.item and not config.exists():p.error('Provide at least one --item with its exact Find My name.')
for n in ['findmy','findmy-helper','idle-probe','close-findmy-window']:
 if not (BASE/'bin'/n).is_file():p.error('Run make build first; missing '+n)
if a.item and config.exists() and not a.update:p.error('Item configuration already exists. Edit it directly to preserve aliases.')
interpreter=Path(a.python).absolute()
if not interpreter.is_file():p.error('Python interpreter not found: '+str(interpreter))
env={'PYTHONDONTWRITEBYTECODE':'1','TAGTRACKER_DATA_DIR':str(DATA),'FINDMY_HISTORY_DB':str(DATA/'history.sqlite'),'FINDMY_HELPER':str(BASE/'compat/helper'),'PATH':str(BASE/'compat')+':'+str(interpreter.parent)+':/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:/usr/local/bin'}
jobs={
 'io.tagtracker.sharing-probe':{'ProgramArguments':[str(BASE/'compat/screen-sharing-probe')],'StartInterval':30,'ThrottleInterval':1},
 'io.tagtracker.history':{'ProgramArguments':[str(interpreter),str(BASE/'compat/history-server.py')],'KeepAlive':True},
 'io.tagtracker.collector':{'ProgramArguments':[str(BASE/'bin/findmy'),'items','--json'],'StartInterval':60},
}
a.output.mkdir(parents=True,exist_ok=True)
for label,job in jobs.items():
 path=a.output/(label+'.plist')
 if path.exists():
  old=plistlib.loads(path.read_bytes())
  if not a.update or old.get('WorkingDirectory')!=str(BASE):p.error('Refusing to overwrite another installation\'s LaunchAgent: '+str(path))
DATA.mkdir(parents=True,exist_ok=True,mode=0o700)
settings=json.loads(config.read_text()) if config.exists() else {'aliases':{}}
if a.item:settings['expected']=list(dict.fromkeys(a.item))
if a.devices or a.devices_enabled is not None:settings['collect_devices']=a.devices or a.devices_enabled=='yes'
config.write_text(json.dumps(settings,indent=2)+'\n')
with sqlite3.connect(DATA/'history.sqlite') as c:
 c.execute('CREATE TABLE IF NOT EXISTS observations (id INTEGER PRIMARY KEY AUTOINCREMENT,ts TEXT NOT NULL,kind TEXT NOT NULL,name TEXT NOT NULL,location TEXT,staleness TEXT,distance TEXT,battery TEXT,raw_json TEXT)')
for label,job in jobs.items():
 path=a.output/(label+'.plist')
 job.update(Label=label,RunAtLoad=True,Umask=63,WorkingDirectory=str(BASE),EnvironmentVariables=env,StandardOutPath=str(DATA/(label+'.log')),StandardErrorPath=str(DATA/(label+'.err')))
 path.write_bytes(plistlib.dumps(job))
 if a.load:
  if a.update:subprocess.run(['launchctl','bootout','gui/'+str(os.getuid())+'/'+label],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  subprocess.run(['launchctl','bootstrap','gui/'+str(os.getuid()),str(path)],check=True)
 print(path)
print('Configuration: '+str(DATA))
print('History: http://127.0.0.1:8768/')
