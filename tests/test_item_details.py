import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'compat'))
import item_details as details
from idle_control import IdlePause


WINDOW = dict(windowID=42, x=100, y=80, width=800, height=650, layer=0, onScreen=True)
CANONICAL = {'demo keys': 'Demo keys', 'demo bag': 'Demo bag'}


def line(text, x, y, width=110, confidence=1):
    return dict(text=text, x=x * 2, y=y * 2, width=width * 2, height=18 * 2, confidence=confidence)


class Scene:
    """Expansion moves the next item and leaves Directions at its old position."""
    def __init__(self):
        self.expanded = None
        self.clicks = []
        self.events = []
        self.windows = [dict(WINDOW)]
        self.interrupt = False

    def lines(self):
        tab_x = 220 if self.expanded else 170
        rows = [line('Items', tab_x, 60, 50), line('Demo keys', 60, 200)]
        if self.expanded:
            rows += [line('101 Example Street', 60, 225), line('Directions', 60, 270)]
        else:
            rows += [line('Address unavailable • 7 min ago', 60, 225)]
        rows += [line('Demo bag', 60, 380 if self.expanded else 270)]
        if self.expanded == 'Demo bag':
            rows += [line('202 Example Avenue', 60, 405)]
        return rows

    def check(self):
        if self.interrupt:
            raise IdlePause('Screen Sharing connected')

    def command(self, *args):
        if args[0] == '/usr/sbin/screencapture':
            Path(args[-1]).write_bytes(b'\x89PNG\r\n\x1a\n' + b'\0' * 8 + struct.pack('>II', 1600, 1300))
            return ''
        if args[1] == 'ocr':
            return json.dumps(self.lines())
        if args[1] == 'scroll':
            return '{}'
        if args[1] == 'click':
            x, y = float(args[2]) - WINDOW['x'], float(args[3]) - WINDOW['y']
            hit = next((row['text'] for row in self.lines()
                        if row['x'] / 2 <= x <= (row['x'] + row['width']) / 2
                        and row['y'] / 2 <= y <= (row['y'] + row['height']) / 2), 'empty')
            self.clicks.append((hit, x, y))
            if hit in ('Demo keys', 'Demo bag'):
                self.expanded = hit
            return '{}'
        raise AssertionError(args)

    def log(self, kind, **data):
        self.events.append((kind, data))


class DetailTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.scene = Scene()
        self.reader = details.DetailReader(WINDOW, self.scene.command, 'helper', self.scene.check,
                                          lambda: self.scene.windows, CANONICAL, self.scene.log,
                                          Path(self.directory.name) / 'image.png')
        def focus(args, **kwargs):
            return 'ASN:0x0-0x123: ' if args[1] == 'front' else 'bundleID="com.apple.findmy"'
        self.focus = patch.object(details.subprocess, 'check_output', side_effect=focus)
        self.focus.start()
        self.addCleanup(self.focus.stop)
        self.sleep = patch.object(details.time, 'sleep')
        self.sleep.start()
        self.addCleanup(self.sleep.stop)

    def test_real_detail_loop_uses_new_layout_after_each_expansion(self):
        records = {'Demo keys': 'Address unavailable • 7 min ago', 'Demo bag': 'Address unavailable • Age unavailable'}
        details.collect_details(records, WINDOW, self.scene.command, 'helper', self.scene.check,
                                lambda: self.scene.windows, CANONICAL, self.scene.log)
        self.assertEqual([hit for hit, _, _ in self.scene.clicks], ['Demo keys', 'Items', 'Demo bag', 'Items'])
        # The obsolete y=279 would click Directions in the expanded layout.
        self.assertEqual(self.scene.clicks[2][2], 389)
        self.assertEqual(self.scene.clicks[1][1], 245)
        self.assertEqual(records['Demo keys'], '101 Example Street • 7 min ago')
        self.assertEqual(records['Demo bag'], '202 Example Avenue • Age unavailable')
        self.assertTrue(all('name' not in data for _, data in self.scene.events))

    def test_moving_target_is_not_clicked(self):
        first, second = self.scene.lines(), self.scene.lines()
        second[1]['y'] += 80
        with patch.object(self.reader, 'capture', side_effect=[(first, 2, 0), (second, 2, 0)]):
            with self.assertRaisesRegex(details.DetailUnavailable, 'target_moved'):
                self.reader.click('Demo keys')
        self.assertEqual(self.scene.clicks, [])

    def test_window_resize_is_not_clicked(self):
        self.scene.windows[0]['width'] = 1000
        with self.assertRaisesRegex(details.DetailUnavailable, 'window_changed'):
            self.reader.click('Demo keys')
        self.assertEqual(self.scene.clicks, [])

    def test_lost_focus_is_not_clicked(self):
        with patch.object(details.subprocess, 'check_output', side_effect=['ASN:0x0-0x123:', 'bundleID="com.apple.Maps"']):
            with self.assertRaisesRegex(details.DetailUnavailable, 'focus_changed'):
                self.reader.click('Demo keys')
        self.assertEqual(self.scene.clicks, [])

    def test_slow_ocr_expires_before_click(self):
        with patch.object(details.time, 'monotonic', side_effect=[0, 4]):
            with self.assertRaisesRegex(details.DetailUnavailable, 'capture_too_old'):
                self.reader.click('Demo keys')
        self.assertEqual(self.scene.clicks, [])

    def test_interruption_propagates_without_further_actions(self):
        def interrupted(*args):
            result = self.scene.command(*args)
            if len(args) > 1 and args[1] == 'click':
                self.scene.interrupt = True
            return result
        with self.assertRaises(IdlePause):
            details.collect_details({'Demo keys': 'Address unavailable • 7 min ago'}, WINDOW,
                                    interrupted, 'helper', self.scene.check, lambda: self.scene.windows,
                                    CANONICAL, self.scene.log)
        self.assertEqual(len(self.scene.clicks), 1)

    def test_action_overlap_and_duplicate_labels_are_rejected(self):
        for extra in [line('Directions', 60, 200), line('Demo keys', 60, 300)]:
            with self.subTest(extra=extra['text']), self.assertRaises(details.DetailUnavailable):
                details.target(self.scene.lines() + [extra], 2, 'Demo keys', CANONICAL)

    def test_missing_or_low_confidence_tab_has_no_fallback_coordinate(self):
        for rows in [[], [line('Items', 170, 60, confidence=.4)]]:
            with self.subTest(rows=rows), self.assertRaises(details.DetailUnavailable):
                details.target(rows, 2, 'Items', CANONICAL, tab=True)

    def test_unverified_detail_keeps_original_observation(self):
        records = {'Demo keys': 'Address unavailable • 7 min ago'}
        self.scene.windows.clear()
        details.collect_details(records, WINDOW, self.scene.command, 'helper', self.scene.check,
                                lambda: self.scene.windows, CANONICAL, self.scene.log)
        self.assertEqual(records['Demo keys'], 'Address unavailable • 7 min ago')
        self.assertEqual(self.scene.clicks, [])
        self.assertIn(('detail_skipped', {'reason': 'window_changed'}), self.scene.events)


if __name__ == '__main__':
    unittest.main()
