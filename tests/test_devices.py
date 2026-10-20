import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'compat'))
from device_collection import parse_page, save_observations, confirm_rows, SOURCE
import map_history


def line(text, x, y, width=130, confidence=1):
    return dict(text=text, x=x, y=y, width=width, height=18, confidence=confidence)


class DeviceCollectionTests(unittest.TestCase):
    def page(self, age='Now'):
        return [line('Devices', 130, 45), line('Example Phone', 65, 155),
                line('Example Park • ' + age, 65, 179), line('2.3 mi', 240, 157, 45),
                line('Example Laptop', 65, 230), line('This Mac • No location found', 65, 254),
                line('A map label • Now', 450, 179)]

    def test_rows_preserve_reported_age_and_distance(self):
        records = parse_page(self.page('7 min ago'), 1, 650, 1000)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]['name'], 'Example Phone')
        self.assertEqual(records[0]['location'], 'Example Park')
        self.assertEqual(records[0]['staleness'], '7 min ago')
        self.assertEqual(records[0]['distance'], '2.3 mi')
        self.assertEqual(records[1]['location'], 'No location found')
        self.assertEqual(records[1]['staleness'], '')

    def test_retina_coordinates(self):
        page = [{**row, **{key: row[key] * 2 for key in ('x', 'y', 'width', 'height')}} for row in self.page()]
        self.assertEqual(parse_page(page, 2, 650, 1000)[0]['name'], 'Example Phone')

    def test_missing_age_never_becomes_now(self):
        records = parse_page([line('Example Phone', 65, 155), line('Offline', 65, 179)], 1, 650, 1000)
        self.assertEqual(records[0]['staleness'], '')

    def test_taller_family_device_row_is_not_dropped(self):
        records = parse_page([line('Example Family Laptop', 65, 155), line('No location found', 65, 191)], 1, 650, 1000)
        self.assertEqual(records[0]['name'], 'Example Family Laptop')

    def test_distance_confirmation_requires_distinct_agreeing_captures(self):
        first = parse_page(self.page(), 1, 650, 1000)
        second = parse_page(self.page(), 1, 650, 1001)
        self.assertEqual(confirm_rows(first, second)[0]['confirmed_captures'], 2)
        second[0]['distance'] = 'Nearby'
        self.assertEqual(confirm_rows(first, second)[0]['confirmed_captures'], 1)
        self.assertEqual(confirm_rows(first, first)[0]['confirmed_captures'], 1)

    def test_duplicate_visible_names_are_ambiguous(self):
        rows = self.page() + [line('Example Phone', 65, 310), line('Elsewhere • Now', 65, 334)]
        with self.assertRaises(ValueError):
            parse_page(rows, 1, 650, 1000)

    def test_storage_retains_private_provenance_and_item_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'history.sqlite'
            records = parse_page(self.page(), 1, 650, 1000)
            save_observations(path, records, 'scan-example', 1010)
            with sqlite3.connect(path) as db:
                db.execute("INSERT INTO observations(ts,kind,name,location,staleness,raw_json) VALUES ('1970-01-01T00:20:00Z','items','Example Phone','Offline','','{}')")
                row = db.execute("SELECT kind,raw_json FROM observations WHERE kind='devices' LIMIT 1").fetchone()
            self.assertEqual(row[0], 'devices')
            raw = json.loads(row[1])
            self.assertEqual(raw['source'], SOURCE)
            self.assertTrue(raw['complete_scan'])
            self.assertEqual(raw['captured_at'], 1000)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with patch.object(map_history, 'locate', return_value=None):
                history = map_history.get_history(path, 'Example Phone', 'all', kind='devices')
            self.assertEqual(history['count'], 1)
            self.assertEqual(history['first'], '1970-01-01T00:16:40Z')

    def test_overview_shows_device_and_item_with_same_name(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'history.sqlite'
            save_observations(path, parse_page(self.page(), 1, 650, 1000), 'scan', 1010)
            with sqlite3.connect(path) as db:
                db.execute("INSERT INTO observations(ts,kind,name,location,staleness,raw_json) VALUES ('1970-01-01T00:20:00Z','items','Example Phone','Offline','','{}')")
            spec = importlib.util.spec_from_file_location('history_server', Path(__file__).resolve().parents[1] / 'compat/history-server.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            with patch.object(module, 'DB', path):
                html = module.render()
            self.assertIn('1 items · 2 devices', html)
            self.assertIn('kind=devices', html)
            self.assertIn('kind=items', html)
            self.assertIn('Displayed distance', html)


if __name__ == '__main__':
    unittest.main()
