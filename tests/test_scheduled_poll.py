import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class ScheduledPollTests(unittest.TestCase):
    def invoke(self, code):
        with tempfile.TemporaryDirectory() as temporary:
            result = subprocess.run([sys.executable, '-c', 'from scheduled_poll import poll\nraise SystemExit(poll([' + repr(sys.executable) + ', "-c", ' + repr(code) + ']))'], env=dict(os.environ, PYTHONPATH=str(ROOT/'compat'), TAGTRACKER_DATA_DIR=temporary), capture_output=True, text=True)
            self.assertEqual(list(Path(temporary).iterdir()), [])
            return result

    def test_expected_pauses_are_successful_polls(self):
        for reason in ('Waiting for next scheduled scan', 'Waiting for two minutes without mouse or keyboard activity', 'Scan paused while Screen Sharing is connected', 'Scan stopped because mouse or keyboard activity resumed'):
            result = self.invoke('from scheduled_poll import record_pause\nimport sys\nrecord_pause(' + repr(reason) + ')\nprint("error: exit status 1",file=sys.stderr)\nsys.exit(1)')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(reason, result.stdout)
            self.assertEqual(result.stderr, '')

    def test_actual_activation_adapter_acknowledges_idle_pause(self):
        code = """import runpy,sys
from unittest.mock import patch
from idle_control import IdlePause
sys.argv=['osascript','-e','tell application "FindMy" to activate']
with patch('idle_control.begin',side_effect=IdlePause('Waiting for next scheduled scan')),patch('idle_control.cleanup_window'):
    runpy.run_path(""" + repr(str(ROOT/'compat/osascript')) + """,run_name='__main__')
"""
        result = self.invoke(code)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Waiting for next scheduled scan', result.stdout)

    def test_actual_ocr_adapter_acknowledges_pause_without_recording(self):
        code = """import json,os,pathlib,runpy,sys
from unittest.mock import patch
data=pathlib.Path(os.environ['TAGTRACKER_DATA_DIR'])
(data/'item-names.json').write_text(json.dumps({'expected':['Example bag'],'aliases':{}}))
sys.argv=['helper','ocr','items.png']
try:
    with patch('idle_control.read',return_value={'mode':'scheduled'}),patch('idle_control.cleanup_window'):
        runpy.run_path(""" + repr(str(ROOT/'compat/helper')) + """,run_name='__main__')
finally:
    (data/'item-names.json').unlink()
"""
        result = self.invoke(code)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Scan paused before the Items tab was selected', result.stdout)

    def test_real_error_is_not_hidden(self):
        result = self.invoke('import sys\nprint("OCR capture failed",file=sys.stderr)\nsys.exit(1)')
        self.assertEqual(result.returncode, 1)
        self.assertIn('OCR capture failed', result.stderr)
        self.assertNotIn('Scan paused', result.stdout)

    def test_invalid_or_other_invocation_acknowledgement_does_not_hide_error(self):
        for content in ('broken JSON', '[]', '{"token":"old","outcome":"paused"}'):
            result = self.invoke('import os,pathlib,sys\npathlib.Path(os.environ["TAGTRACKER_POLL_RESULT"]).write_text(' + repr(content) + ')\nsys.exit(1)')
            self.assertEqual(result.returncode, 1)

    def test_real_adapter_failure_overrides_an_ignored_pause(self):
        code = """from scheduled_poll import record_pause
record_pause('Earlier ignored pause')
import runpy,sys
from unittest.mock import patch
sys.argv=['osascript','-e','tell application "FindMy" to activate']
with patch('idle_control.begin',side_effect=RuntimeError('Capture unavailable')),patch('idle_control.fail_scan'):
    runpy.run_path(""" + repr(str(ROOT/'compat/osascript')) + """,run_name='__main__')
"""
        # The real adapter writes an automation diagnostic; supply its data file
        # within the child and remove it before the temporary-data assertion.
        code = """import os,pathlib
p=pathlib.Path(os.environ['TAGTRACKER_DATA_DIR'])/'automation.err'
try:
""" + ''.join('    '+line+'\n' for line in code.splitlines()) + """finally:
    p.unlink(missing_ok=True)
"""
        result = self.invoke(code)
        self.assertEqual(result.returncode, 1)
        self.assertIn('Capture unavailable', result.stderr)
        self.assertNotIn('Scan paused:', result.stdout)

    def test_non_pause_failure_even_with_acknowledgement(self):
        result = self.invoke('from scheduled_poll import record_pause\nrecord_pause("Waiting")\nraise SystemExit(2)')
        self.assertEqual(result.returncode, 2)

    def test_successful_collection_output_is_preserved(self):
        result = self.invoke('print("[]")')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '[]\n')

    def test_terminated_collector_still_fails(self):
        result = self.invoke('import os,signal\nos.kill(os.getpid(),signal.SIGTERM)')
        self.assertEqual(result.returncode, 143)

if __name__ == '__main__': unittest.main()
