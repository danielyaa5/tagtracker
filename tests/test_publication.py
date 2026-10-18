import importlib.util,json,os,sqlite3,subprocess,sys,tempfile,unittest
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'compat'))
import map_history
class Maps(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.data=Path(self.t.name)
  from unittest.mock import patch
  self.p=patch.object(map_history,'DATA',self.data);self.p.start();self.addCleanup(self.p.stop)
 def test_saved_place_and_missing_gazetteer(self):
  (self.data/'saved-places.json').write_text(json.dumps({'Example':{'lat':10,'lon':20}}))
  self.assertEqual(map_history.locate('Example')['lat'],10)
  self.assertIsNone(map_history.locate('Unknown Town, ZZ'))
 def test_date_range_filters_observation_time(self):
  db=self.data/'history.sqlite'
  with sqlite3.connect(db) as c:
   c.execute('CREATE TABLE observations(id INTEGER PRIMARY KEY,ts TEXT,name TEXT,location TEXT,staleness TEXT)')
   c.executemany('INSERT INTO observations VALUES (?,?,?,?,?)',[(1,'2026-01-01T00:00:00Z','Example','Unknown','Now'),(2,'2026-01-03T00:00:00Z','Example','Unknown','Now')])
  h=map_history.get_history(db,'Example','24h',now=datetime(2026,1,3,12,tzinfo=timezone.utc))
  self.assertEqual(h['count'],1);self.assertEqual(h['rows'][0]['ts'],'2026-01-03T00:00:00Z')
 def test_unsafe_coordinates_are_not_mapped(self):
  (self.data/'saved-places.json').write_text('{"Example":{"lat":999,"lon":20}}')
  self.assertIsNone(map_history.locate('Example'))
class Privacy(unittest.TestCase):
 def test_runtime_data_is_outside_checkout(self):
  import runtime
  self.assertNotEqual(runtime.DATA,ROOT)
 def test_sources_have_no_original_server_path(self):
  for p in (ROOT/'compat').iterdir():
   if p.is_file() and p.suffix not in ['.sqlite']:
    self.assertNotIn('Developer/findmy-cli',p.read_text())
if __name__=='__main__':unittest.main()
