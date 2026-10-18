#!/usr/bin/env python3
"""Build an optional approximate-town lookup from GeoNames (CC BY 4.0)."""
import io,os,sqlite3,sys,urllib.request,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'compat'))
from runtime import DATA
ROOT='https://download.geonames.org/export/dump/'
def fetch(name):
 with urllib.request.urlopen(ROOT+name,timeout=120) as r:return r.read()
def build():
 os.umask(0o077);DATA.mkdir(parents=True,exist_ok=True,mode=0o700)
 path=DATA/'places.sqlite';temp=DATA/'places.build.sqlite'
 if temp.exists():raise SystemExit('An unfinished places.build.sqlite exists; inspect it before retrying.')
 countries=fetch('countryInfo.txt').decode('utf-8')
 regions=fetch('admin1CodesASCII.txt').decode('utf-8')
 with zipfile.ZipFile(io.BytesIO(fetch('cities15000.zip'))) as archive:
  cities=archive.read('cities15000.txt').decode('utf-8')
 with sqlite3.connect(temp) as c:
  c.executescript('CREATE TABLE places(name TEXT,country TEXT,region TEXT,lat REAL,lon REAL,id INTEGER); CREATE TABLE countries(name TEXT,code TEXT); CREATE TABLE regions(country TEXT,code TEXT,name TEXT);')
  for line in countries.splitlines():
   if not line or line.startswith('#'):continue
   row=line.split('\t');c.execute('INSERT INTO countries VALUES (?,?)',(row[4].casefold(),row[0]))
  for line in regions.splitlines():
   row=line.split('\t');country,region=row[0].split('.',1)
   for name in set(row[1:3]):c.execute('INSERT INTO regions VALUES (?,?,?)',(country,region,name.casefold()))
  for line in cities.splitlines():
   row=line.split('\t')
   for name in set([row[1],row[2],*row[3].split(',')]):
    if name:c.execute('INSERT INTO places VALUES (?,?,?,?,?,?)',(name.casefold(),row[8],row[10],float(row[4]),float(row[5]),int(row[0])))
  c.execute('CREATE INDEX places_lookup ON places(name,country,region)')
 temp.replace(path);print('GeoNames town-center lookup saved to '+str(path))
if __name__=='__main__':build()
