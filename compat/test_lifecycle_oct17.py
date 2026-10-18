import importlib.util,json,os,tempfile,threading,time,unittest,sys
sys.path.insert(0,str(__import__("pathlib").Path(__file__).parent))
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('idle',Path(__file__).parent/'idle_control.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
W={'windowID':5,'x':336,'y':165,'width':800,'height':659,'onScreen':True,'layer':0}
class Lifecycle(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.st=patch.object(m,'STATE',Path(self.tmp.name)/'scan-control.json');self.st.start();self.addCleanup(self.st.stop)
  self.probe={'counts':{'1':0},'idle':300,'x':0,'y':0}
 def status(self,name):return json.loads(m.STATE.with_name(name).read_text())
 def events(self):
  p=m.STATE.with_name('scan-events.jsonl');return [json.loads(l)['event'] for l in p.read_text().splitlines()] if p.exists() else []
 def sharing(self,connected,age=0):
  m.STATE.with_name('screen-sharing-status.json').write_text(json.dumps({'checked_at':time.time()-age,'valid':True,'connected':connected}))
 # Carried over from the October 16 tests.
 def test_sharing_blocks_before_input_or_activation(self):
  with patch.object(m,'screen_sharing_connected',return_value=True),patch.object(m,'probe',side_effect=AssertionError('Must not start')):
   with self.assertRaises(m.IdlePause):m.begin(42)
  self.assertEqual(m.read()['mode'],'waiting_for_screen_sharing')
 def test_disconnected_admits_idle_scan(self):
  with patch.object(m,'screen_sharing_connected',return_value=False),patch.object(m,'probe',return_value=self.probe):m.begin(42)
  self.assertEqual(m.read()['mode'],'scanning')
 def test_fresh_connection_snapshots(self):
  for connected in [True,False]:
   self.sharing(connected);self.assertEqual(m.screen_sharing_connected(),connected)
 def test_unavailable_probe_never_means_disconnected(self):
  with patch.object(m.subprocess,'run',side_effect=RuntimeError('probe unavailable')):
   with self.assertRaises(m.IdlePause):m.begin(42)
  self.assertEqual(m.read()['mode'],'waiting_for_screen_sharing')
 def test_failure_closes_backs_off_and_records(self):
  m.save({'mode':'scanning','pid':42,'baseline':self.probe,'scan_window':dict(W,owner=os.getppid())})
  with patch.object(m,'probe',return_value=self.probe),patch.object(m,'find_my_windows',return_value=[W]),patch.object(m.subprocess,'check_output',return_value='{"closed":true}') as command:m.fail_scan('tab selection timed out')
  self.assertEqual(command.call_count,1);self.assertNotIn('scan_window',m.read());self.assertEqual(m.read()['mode'],'scheduled');self.assertGreater(m.read()['next_due'],time.time()+290)
  q=self.status('collection-status.json');self.assertFalse(q['ok']);self.assertEqual(q['error'],'tab selection timed out')
 # October 17: the window this run opened closes even when input interrupted the scan.
 def test_input_no_longer_defers_own_window(self):
  m.save({'mode':'scanning','pid':42,'baseline':self.probe,'scan_window':dict(W,owner=os.getppid())})
  with patch.object(m,'probe',return_value=dict(self.probe,x=100,idle=0)),patch.object(m,'find_my_windows',return_value=[W]),patch.object(m.subprocess,'check_output',return_value='{"closed":true}') as command:
   with self.assertRaises(m.IdlePause):m.check()
   m.cleanup_window()
  command.assert_called_once();self.assertTrue(self.status('window-close-status.json')['closed']);self.assertNotIn('scan_window',m.read())
 def test_leftover_waits_for_input_pause_then_closes(self):
  m.save({'mode':'waiting_for_screen_sharing','scan_window':dict(W,owner=-1)})
  with patch.object(m,'probe',return_value=dict(self.probe,idle=3)),patch.object(m,'find_my_windows',return_value=[W]),patch.object(m.subprocess,'check_output') as command:m.cleanup_window()
  command.assert_not_called();self.assertTrue(self.status('window-close-status.json')['deferred']);self.assertIn('scan_window',m.read())
  with patch.object(m,'probe',return_value=dict(self.probe,idle=20)),patch.object(m,'find_my_windows',return_value=[W]),patch.object(m.subprocess,'check_output',return_value='{"closed":true}') as command:m.cleanup_window()
  command.assert_called_once();self.assertNotIn('scan_window',m.read())
 def test_old_state_without_owner_is_a_leftover(self):
  m.save({'mode':'scheduled','scan_window':W})
  with patch.object(m,'probe',return_value=dict(self.probe,idle=0)),patch.object(m,'find_my_windows',return_value=[W]),patch.object(m.subprocess,'check_output') as command:m.cleanup_window()
  command.assert_not_called()
 def test_window_already_gone_is_closed_without_touching_new_windows(self):
  m.save({'mode':'scheduled','scan_window':dict(W,owner=-1)})
  mine=dict(W,windowID=99)
  with patch.object(m,'probe',return_value=self.probe),patch.object(m,'find_my_windows',return_value=[mine]),patch.object(m.subprocess,'check_output') as command:m.cleanup_window()
  command.assert_not_called();self.assertTrue(self.status('window-close-status.json')['already_closed']);self.assertNotIn('scan_window',m.read())
 def test_close_uses_current_frame_after_display_change(self):
  m.save({'mode':'scanning','pid':42,'baseline':self.probe,'scan_window':dict(W,owner=os.getppid())})
  moved=dict(W,x=120,y=40,width=1000,height=700)
  with patch.object(m,'probe',return_value=self.probe),patch.object(m,'find_my_windows',return_value=[moved]),patch.object(m.subprocess,'check_output',return_value='{"closed":true}') as command:m.cleanup_window()
  self.assertEqual(command.call_args.args[0][1:],['120','40','1000','700'])
 def test_close_failure_keeps_window_for_retry(self):
  m.save({'mode':'scanning','pid':42,'baseline':self.probe,'scan_window':dict(W,owner=os.getppid())})
  with patch.object(m,'probe',return_value=self.probe),patch.object(m,'find_my_windows',return_value=[W]),patch.object(m.subprocess,'check_output',side_effect=m.subprocess.CalledProcessError(1,'close',stderr='Find My close button unavailable')):m.cleanup_window()
  self.assertEqual(self.status('window-close-status.json')['error'],'Find My close button unavailable');self.assertIn('scan_window',m.read())
 def test_unknown_sharing_mid_scan_backs_off_instead_of_looping(self):
  m.save({'mode':'scanning','pid':42,'baseline':self.probe})
  with patch.object(m,'probe',return_value=self.probe),patch.object(m,'screen_sharing_connected',side_effect=RuntimeError('status unavailable')):
   with self.assertRaises(m.IdlePause):m.check()
  self.assertEqual(m.read()['mode'],'scheduled');self.assertGreater(m.read()['next_due'],time.time()+290)
  self.assertIn('sharing_status_unavailable',self.events());self.assertNotIn('interrupted_by_screen_sharing',self.events())
 def test_real_sharing_mid_scan_waits_for_disconnect(self):
  m.save({'mode':'scanning','pid':42,'baseline':self.probe})
  with patch.object(m,'probe',return_value=self.probe),patch.object(m,'screen_sharing_connected',return_value=True):
   with self.assertRaises(m.IdlePause):m.check()
  self.assertEqual(m.read()['mode'],'waiting_for_screen_sharing')
 def test_running_scan_is_not_readmitted_through_sharing_check(self):
  m.save({'mode':'scanning','pid':42,'started':time.time(),'baseline':self.probe})
  with patch.object(m,'screen_sharing_connected',side_effect=AssertionError('begin must not re-check a running scan')):m.begin(42)
  self.assertEqual(self.events(),[])
 def test_status_waits_past_launchd_throttle(self):
  # launchd held the probe's second kickstart for 7.2 s on the server (2026-10-17); the old 3 s wait called that "connected".
  self.sharing(False,age=30)
  def late():time.sleep(3.5);self.sharing(False)
  with patch.object(m.subprocess,'run'):
   threading.Thread(target=late).start();started=time.time()
   self.assertFalse(m.screen_sharing_connected())
  self.assertGreater(time.time()-started,3)
 def test_finish_clears_stale_error(self):
  m.save({'mode':'scanning','pid':42,'started':time.time(),'last_error':'old'})
  m.finish();self.assertNotIn('last_error',m.read())
unittest.main()
