from pathlib import Path
from datetime import datetime,timedelta,timezone
import sqlite3,json,math
BASE=Path(__file__).parent
from runtime import DATA
RANGES={'24h':1,'7d':7,'30d':30,'90d':90,'all':None}
def locate(label):
 settings=DATA/'saved-places.json'
 if settings.exists():
  try:
   saved=json.loads(settings.read_text()).get(label)
   if saved:
    lat,lon=float(saved['lat']),float(saved['lon'])
    if math.isfinite(lat) and math.isfinite(lon) and -90<=lat<=90 and -180<=lon<=180:
     return dict(lat=lat,lon=lon,source='User configured',precision=saved.get('precision','Saved location for this label'))
  except (ValueError,KeyError,TypeError,OSError):pass
 parts=[x.strip().casefold() for x in label.split(',')]
 if len(parts)<2:return None
 if not (DATA/'places.sqlite').exists():return None
 with sqlite3.connect('file:'+str(DATA/'places.sqlite')+'?mode=ro',uri=True) as c:
  if len(parts)==2 and len(parts[1])==2:country='US';region=parts[1].upper()
  elif len(parts)>=3:
   countries=c.execute('select code from countries where name=?',(parts[-1],)).fetchall()
   if len(countries)!=1:return None
   country=countries[0][0]
   regions=c.execute('select distinct code from regions where country=? and name=?',(country,parts[-2])).fetchall()
   if len(regions)!=1:return None
   region=regions[0][0]
  else:return None
  matches=c.execute('select distinct lat,lon,id from places where name=? and country=? and region=?',(parts[0],country,region)).fetchall()
  if len(matches)!=1:return None
  lat,lon,gid=matches[0]
  return dict(lat=lat,lon=lon,source='GeoNames',id=gid,precision='Town center (approximate)')
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
