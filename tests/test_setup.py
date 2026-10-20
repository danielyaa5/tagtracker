import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.data = self.base / 'private'
        self.agents = self.base / 'agents'

    def setup(self, *arguments):
        return subprocess.run([sys.executable, str(ROOT / 'scripts/setup.py'), '--output', str(self.agents), *arguments], env={**os.environ, 'TAGTRACKER_DATA_DIR': str(self.data)}, text=True, capture_output=True)

    def test_interpreter_and_private_paths_are_preserved(self):
        result = self.setup('--item', 'Example bag', '--devices', '--python', sys.executable)
        self.assertEqual(result.returncode, 0, result.stderr)
        job = plistlib.loads((self.agents / 'io.tagtracker.history.plist').read_bytes())
        self.assertEqual(job['ProgramArguments'][0], sys.executable)
        self.assertEqual(job['EnvironmentVariables']['TAGTRACKER_DATA_DIR'], str(self.data))
        self.assertIn(str(Path(sys.executable).parent), job['EnvironmentVariables']['PATH'])
        self.assertEqual(job['EnvironmentVariables']['PYTHONDONTWRITEBYTECODE'], '1')
        self.assertEqual((self.data / 'item-names.json').stat().st_mode & 0o777, 0o600)

    def test_update_retains_aliases_and_can_disable_devices(self):
        self.assertEqual(self.setup('--item', 'Example bag', '--devices').returncode, 0)
        config = self.data / 'item-names.json'
        settings = json.loads(config.read_text())
        settings['aliases'] = {'Example OCR bag': 'Example bag'}
        settings['device_aliases'] = {'Example OCR phone': 'Example phone'}
        config.write_text(json.dumps(settings))
        result = self.setup('--update', '--item', 'Example bag', '--item', 'Example keys', '--devices-enabled', 'no')
        self.assertEqual(result.returncode, 0, result.stderr)
        updated = json.loads(config.read_text())
        self.assertEqual(updated['aliases'], settings['aliases'])
        self.assertEqual(updated['device_aliases'], settings['device_aliases'])
        self.assertFalse(updated['collect_devices'])
        self.assertEqual(updated['expected'], ['Example bag', 'Example keys'])

    def test_other_installation_is_rejected_before_config_changes(self):
        self.assertEqual(self.setup('--item', 'Example bag').returncode, 0)
        config = self.data / 'item-names.json'
        before = config.read_bytes()
        path = self.agents / 'io.tagtracker.collector.plist'
        job = plistlib.loads(path.read_bytes())
        job['WorkingDirectory'] = str(self.base / 'another-installation')
        path.write_bytes(plistlib.dumps(job))
        result = self.setup('--update', '--item', 'Example keys')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('another installation', result.stderr)
        self.assertEqual(config.read_bytes(), before)
        self.assertEqual(plistlib.loads(path.read_bytes()), job)

if __name__ == '__main__': unittest.main()
