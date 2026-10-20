from pathlib import Path
from datetime import datetime,timedelta,timezone
import sqlite3,json,math,os,subprocess
BASE=Path(__file__).parent
try:
 from runtime import DATA
except ImportError:
 DATA=Path.home()/'Library/Application Support/AirTag Tracking'
RANGES={'24h':1,'7d':7,'30d':30,'90d':90,'all':None}
NON_PLACES={'address unavailable','unknown','not found','offline','nearby','unavailable','no location','age unavailable'}

def _cache_db():
 p=DATA/'geocoded-places.sqlite'
 if not p.exists():
  try:
   with sqlite3.connect(p) as c:
    c.execute('CREATE TABLE IF NOT EXISTS geocoded (label TEXT PRIMARY KEY, lat REAL, lon REAL, precision TEXT, source TEXT)')
  except OSError:pass
 return p

def _query_cache(label):
 p=DATA/'geocoded-places.sqlite'
 if not p.exists():return False,None
 try:
  with sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True) as c:
   r=c.execute('SELECT lat,lon,precision,source FROM geocoded WHERE label=?',(label,)).fetchone()
   if r is None:return False,None
   if r[0] is not None and r[1] is not None:
    return True,dict(lat=r[0],lon=r[1],precision=r[2],source=r[3])
   return True,None
 except (sqlite3.Error,OSError):return False,None

def _save_cache(label,result):
 try:
  p=_cache_db()
  with sqlite3.connect(p) as c:
   if result:
    c.execute('INSERT OR REPLACE INTO geocoded VALUES (?,?,?,?,?)',(label,result['lat'],result['lon'],result.get('precision',''),result.get('source','')))
   else:
    c.execute('INSERT OR REPLACE INTO geocoded VALUES (?,NULL,NULL,NULL,NULL)',(label,))
 except (sqlite3.Error,OSError):pass

def _find_geocoder():
 for cand in [BASE/'geocoder', BASE.parent/'bin/geocoder', Path(__file__).resolve().parent/'geocoder', Path(__file__).resolve().parent.parent/'bin/geocoder']:
  if cand.is_file() and os.access(cand,os.X_OK):return str(cand)
 return None

def _run_geocoder(label):
 b=_find_geocoder()
 if not b:return None
 try:
  res=subprocess.run([b,label],capture_output=True,text=True,timeout=4)
  if res.returncode==0 and res.stdout.strip():
   d=json.loads(res.stdout.strip())
   lat,lon=float(d['lat']),float(d['lon'])
   if math.isfinite(lat) and math.isfinite(lon) and -90<=lat<=90 and -180<=lon<=180:
    return dict(lat=lat,lon=lon,source=d.get('source','macOS Geocoder'),precision=d.get('precision','macOS geocoded location'))
 except Exception:pass
 return None

def locate(label):
 if not label or not isinstance(label,str):return None
 clean=label.strip()
 if clean.casefold() in NON_PLACES:return None
 settings=DATA/'saved-places.json'
 if settings.exists():
  try:
   saved=json.loads(settings.read_text()).get(clean)
   if saved:
    lat,lon=float(saved['lat']),float(saved['lon'])
    if math.isfinite(lat) and math.isfinite(lon) and -90<=lat<=90 and -180<=lon<=180:
     return dict(lat=lat,lon=lon,source='User configured',precision=saved.get('precision','Saved location for this label'))
  except (ValueError,KeyError,TypeError,OSError):pass
 cached,res=_query_cache(clean)
 if cached:return res
 parts=[x.strip().casefold() for x in clean.split(',')]
 places_db=DATA/'places.sqlite' if (DATA/'places.sqlite').exists() else (BASE/'places.sqlite' if (BASE/'places.sqlite').exists() else None)
 if len(parts)>=2 and places_db:
  try:
   with sqlite3.connect('file:'+str(places_db)+'?mode=ro',uri=True) as c:
    country,region=None,None
    if len(parts)==2 and len(parts[1])==2:country='US';region=parts[1].upper()
    elif len(parts)>=3:
     countries=c.execute('select code from countries where name=?',(parts[-1],)).fetchall()
     if len(countries)==1:
      country=countries[0][0]
      regions=c.execute('select distinct code from regions where country=? and name=?',(country,parts[-2])).fetchall()
      if len(regions)==1:region=regions[0][0]
    if country and region:
     matches=c.execute('select distinct lat,lon,id from places where name=? and country=? and region=?',(parts[0],country,region)).fetchall()
     if matches:
      lat,lon,gid=matches[0]
      out=dict(lat=lat,lon=lon,source='GeoNames',id=gid,precision='Town center (approximate)')
      _save_cache(clean,out)
      return out
  except (sqlite3.Error,OSError):pass
 geo=_run_geocoder(clean)
 _save_cache(clean,geo)
 return geo
def get_history(db,item,period='24h',start=None,end=None,now=None):
 now=now or datetime.now(timezone.utc)
 if period=='custom':
  try:
   lo=datetime.fromisoformat(start.replace('Z','+00:00'));hi=datetime.fromisoformat(end.replace('Z','+00:00'))
   if lo.tzinfo is None or hi.tzinfo is None or lo>=hi:raise ValueError()
  except (ValueError,AttributeError):raise ValueError('Choose a valid start and end date.')
 elif period in RANGES:
  lo=now-timedelta(days=RANGES[period]) if RANGES[period] else None;hi=None
 else:raise ValueError('Unknown date range.')
 where=['name=?'];args=[item]
 if lo:where.append('julianday(ts)>=julianday(?)');args.append(lo.isoformat())
 if hi:where.append('julianday(ts)<julianday(?)');args.append(hi.isoformat())
 with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True) as c:
  c.row_factory=sqlite3.Row
  rows=[dict(r) for r in c.execute('select ts,location,staleness from observations where '+' AND '.join(where)+' order by ts,id',args)]
  first=c.execute('select min(ts) from observations where name=?',(item,)).fetchone()[0]
 points={loc:locate(loc) for loc in set(r['location'] for r in rows) if loc}
 return dict(item=item,period=period,rows=rows,places=points,first=first,count=len(rows))
