"""Idle-only scheduling; compare input counters between collector actions."""
import json,os,subprocess,time
from pathlib import Path
from runtime import BASE, DATA
STATE=DATA/'scan-control.json'
THRESHOLD=120
# A Find My window left by an earlier run is closed once input has paused this long,
# so someone clicking in it over Screen Sharing is not cut off mid-click.
LEFTOVER_IDLE=15
# launchd delays a kickstart until 10 s after the job's previous run unless the
# probe plist lowers ThrottleInterval; wait past that instead of reporting a connection.
SHARING_FRESH=5
SHARING_WAIT=12
class IdlePause(Exception):pass
def probe():return json.loads(subprocess.check_output([str(BASE/'bin/idle-probe')],text=True,timeout=10))
def read():
 try:return json.loads(STATE.read_text())
 except FileNotFoundError:return {}
def save(s):
 s['checked_at']=time.time();p=STATE.with_suffix('.tmp');p.write_text(json.dumps(s));p.chmod(0o600);p.replace(STATE)
def keep_display_awake():
 # The signed CLI's 3-second wake expires mid-scan. Hold a display assertion
 # only after the idle gate admits a scan, tied to the responsible CLI PID.
 check()
 s=read();pid=s['pid']
 if s.get('display_guard_owner')==pid and s.get('display_guard_pid'):
  try:
   os.kill(s['display_guard_pid'],0)
   return
  except ProcessLookupError:pass
 guard=subprocess.Popen(['/usr/bin/caffeinate','-d','-u','-t','300','-w',str(pid)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
 time.sleep(.2)
 if guard.poll() is not None:raise RuntimeError('Could not keep the display awake for the scan')
 s.update(display_guard_pid=guard.pid,display_guard_owner=pid)
 save(s)
def event(kind,**data):
 # Record why a gap happened without storing keystrokes or screen contents.
 try:
  p=STATE.with_name('scan-events.jsonl')
  fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
  with os.fdopen(fd,'a') as f:f.write(json.dumps(dict(event=kind,at=time.time(),**data))+'\n')
 except OSError:pass
def record_status(**data):
 # Collection outcome for the history page; pauses are not failures and write nothing.
 data['checked_at']=time.time();quality=STATE.with_name('collection-status.json')
 temp=quality.with_suffix('.tmp');temp.write_text(json.dumps(data));temp.chmod(0o600);temp.replace(quality)
 with quality.with_name('collection-runs.jsonl').open('a') as f:f.write(json.dumps(data)+'\n')
def screen_sharing_connected():
 # The signed collector's process context cannot enumerate TCP connections.
 # A separate native LaunchAgent publishes only connection state, no addresses.
 p=STATE.with_name('screen-sharing-status.json')
 def snapshot():
  try:
   data=json.loads(p.read_text())
   if data.get('valid') and 0<=time.time()-data['checked_at']<SHARING_FRESH:return bool(data['connected'])
  except (OSError,ValueError,KeyError):pass
  return None
 result=snapshot()
 if result is not None:return result
 old=p.stat().st_mtime_ns if p.exists() else 0
 label=os.environ.get('TAGTRACKER_SHARING_PROBE_LABEL','io.tagtracker.sharing-probe')
 subprocess.run(['/bin/launchctl','kickstart',f'gui/{os.getuid()}/{label}'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=5)
 for _ in range(SHARING_WAIT*10):
  time.sleep(.1)
  if p.exists() and p.stat().st_mtime_ns!=old:
   result=snapshot()
   if result is not None:return result
 raise RuntimeError('Screen Sharing connection status unavailable; scan paused')

def begin(pid):
 # Admits new scans only; check() polices a scan that is already running.
 s=read();now=time.time()
 if s.get('pid')==pid and s.get('mode')=='scanning' and now-s.get('started',0)<300:return
 try:sharing=screen_sharing_connected()
 except Exception as e:
  s.update(mode='waiting_for_screen_sharing',reason='Could not verify Screen Sharing is disconnected');save(s)
  raise IdlePause('Cannot verify Screen Sharing is disconnected') from e
 if sharing:
  if s.get('mode')!='waiting_for_screen_sharing':event('waiting_for_screen_sharing')
  s.update(mode='waiting_for_screen_sharing',reason='Screen Sharing is connected');save(s)
  raise IdlePause('Scan paused while Screen Sharing is connected')
 if now<s.get('next_due',0):
  s['mode']='scheduled';save(s);raise IdlePause('Waiting for next scheduled scan')
 p=probe()
 if p['idle']<THRESHOLD:
  if s.get('mode')!='waiting_for_idle':event('waiting_for_idle',idle_seconds=round(p['idle']))
  s.update(mode='waiting_for_idle',idle_seconds=round(p['idle']),threshold=THRESHOLD);save(s);raise IdlePause('Waiting for two minutes without mouse or keyboard activity')
 s.update(mode='scanning',pid=pid,started=now,baseline=p,threshold=THRESHOLD);save(s);event('started',pid=pid)
def check(ignore_sharing=False):
 s=read()
 if s.get('mode')!='scanning':raise IdlePause('Scan is waiting for inactivity')
 p=probe();b=s['baseline']
 if p['counts']!=b['counts'] or abs(p['x']-b['x'])>1 or abs(p['y']-b['y'])>1:
  event('interrupted_by_input',pid=s.get('pid'),changed_event_types=[k for k,v in p['counts'].items() if b['counts'].get(k)!=v],pointer_moved=abs(p['x']-b['x'])>1 or abs(p['y']-b['y'])>1)
  s.update(mode='waiting_for_idle',next_due=0,idle_seconds=round(p['idle']));save(s);raise IdlePause('Scan stopped because mouse or keyboard activity resumed')
 if not ignore_sharing:
  try:sharing=screen_sharing_connected()
  except Exception as e:
   # Unknown is not "connected": back off five minutes instead of reopening Find My every minute.
   event('sharing_status_unavailable',pid=s.get('pid'),error=str(e))
   s.update(mode='scheduled',next_due=time.time()+300,reason='Could not verify Screen Sharing is disconnected');save(s)
   raise IdlePause('Scan paused because Screen Sharing status is unavailable')
  if sharing:
   event('interrupted_by_screen_sharing',pid=s.get('pid'))
   s.update(mode='waiting_for_screen_sharing',reason='Screen Sharing is connected');save(s)
   raise IdlePause('Scan paused because Screen Sharing connected')
def acknowledge_automation():
 s=read();s['baseline']=probe();save(s)
def finish():
 s=read();s.update(mode='scheduled',next_due=s.get('started',time.time())+300);s.pop('last_error',None);save(s);event('finished',pid=s.get('pid'),duration_seconds=round(time.time()-s.get('started',time.time()),1))


def find_my_windows():
 return json.loads(subprocess.check_output([str(BASE/'bin/findmy-helper'),'window','--owner','Find My'],text=True,timeout=10))
def visible_window(windows):
 return next((w for w in windows if w['onScreen'] and w['layer']==0 and w['height']>100),None)
def idle_seconds():
 try:return probe()['idle']
 except Exception:return 0
def remember_window(window):
 # Every exit path closes the window recorded here; owner marks which collector run opened it.
 s=read();s['scan_window']=dict(window,owner=os.getppid());save(s)

def cleanup_window():
 # Close the Find My window the collector opened, whatever ended the scan.
 # Matching by window ID never touches a Find My window opened later by hand.
 s=read();window=s.get('scan_window')
 if not window:return
 result={'checked_at':time.time(),'window_id':window['windowID']}
 try:current=next((w for w in find_my_windows() if w['windowID']==window['windowID']),None)
 except Exception:current=window
 if current is None:
  result.update(closed=True,already_closed=True)
 elif window.get('owner')!=os.getppid() and idle_seconds()<LEFTOVER_IDLE:
  result.update(closed=False,deferred=True,reason='Left by an earlier scan; closing once input pauses')
 else:
  try:
   # Current frame: Screen Sharing can resize the display after the window was recorded.
   output=subprocess.check_output([str(BASE/'bin/close-findmy-window'),*[str(current[k]) for k in ('x','y','width','height')]],text=True,stderr=subprocess.PIPE,timeout=10)
   result.update(json.loads(output))
   if s.get('mode')=='scanning':acknowledge_automation()
  except Exception as e:
   result.update(closed=False,error=(getattr(e,'stderr',None) or str(e)).strip())
 p=STATE.with_name('window-close-status.json');tmp=p.with_suffix('.tmp')
 tmp.write_text(json.dumps(result));tmp.chmod(0o600);tmp.replace(p)
 event('window_cleanup',**result)
 if result.get('closed'):
  s=read();s.pop('scan_window',None);save(s)

def fail_scan(error):
 cleanup_window()
 s=read()
 if s.get('mode')=='scanning':
  s.update(mode='scheduled',next_due=time.time()+300,last_error=str(error));save(s)
 event('failed',error=str(error))
 record_status(ok=False,error=str(error))
