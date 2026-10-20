"""Read item details without reusing coordinates from an earlier layout."""
import json
import math
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import time

from idle_control import IdlePause


class DetailUnavailable(Exception):
    """Keep the list observation when a detail click cannot be verified."""


ACTION = re.compile(r'\b(?:directions|play(?: sound)?|share|notify|remove|lost mode)\b', re.I)
AGE = re.compile(r'\b(?:\d+\s*(?:min\.?|hr\.?|hours?|days?|weeks?)\s+ago|now)\b', re.I)
MAX_FRAME_AGE = 3


def target(lines, scale, name, canonical, tab=False):
    """Return one legible label, rejecting ambiguous or action-overlapping text."""
    matches = []
    for line in lines:
        label = line['text'].strip()
        same = label == name if tab else canonical.get(label.casefold()) == name
        x, y, width, height = (line[key] / scale for key in ('x', 'y', 'width', 'height'))
        in_region = 0 <= x < 300 and 0 <= y < 85 if tab else 40 <= x < 240 and y > 140
        if same and in_region and float(line.get('confidence', 0)) >= .8:
            if all(math.isfinite(v) for v in (x, y, width, height)) and width > 0 and height > 0:
                matches.append((x, y, width, height))
    if len(matches) != 1:
        raise DetailUnavailable('ambiguous_target')
    box = matches[0]
    for line in lines:
        if not ACTION.search(line['text']):
            continue
        other = tuple(line[key] / scale for key in ('x', 'y', 'width', 'height'))
        if (box[0] < other[0] + other[2] + 2 and box[0] + box[2] > other[0] - 2
                and box[1] < other[1] + other[3] + 2 and box[1] + box[3] > other[1] - 2):
            raise DetailUnavailable('target_overlaps_action')
    return box


def extract(lines, scale, name, canonical, original):
    """Read beneath the selected name, preserving unknown or previously shown age."""
    headers = [line for line in lines if canonical.get(line['text'].strip().casefold()) == name
               and 40 * scale <= line['x'] < 250 * scale]
    if len(headers) != 1:
        return None
    header = headers[0]
    below = sorted([line for line in lines if 40 * scale <= line['x'] < 260 * scale
                    and header['y'] < line['y'] < header['y'] + 180 * scale], key=lambda line: line['y'])
    address, age = None, None
    for line in below:
        text = line['text'].strip()
        if text.casefold() in canonical:
            break
        if not text or ACTION.search(text) or re.fullmatch(r'[\s•·|–.\-]+', text):
            continue
        if re.fullmatch(r'\d+(?:[.,]\d+)?\s*(?:mi|km|ft|m|%)', text, re.I):
            continue
        if 'unavailable' in text.casefold():
            continue
        location, separator, shown_age = text.replace('·', '•').partition('•')
        if separator:
            address = address or location.strip()
            age = shown_age.strip() or age
        elif AGE.search(text):
            age = text
        elif not address:
            address = text
    if not address:
        return None
    old_age = original.replace('·', '•').partition('•')[2].strip()
    return address + ' • ' + (age or old_age or 'Age unavailable')


class DetailReader:
    def __init__(self, window, run, real, check, windows, canonical, event, image):
        self.window, self.run, self.real = window, run, real
        self.check, self.windows = check, windows
        self.canonical, self.event, self.image = canonical, event, image

    def context(self):
        self.check()
        current = next((w for w in self.windows() if w['windowID'] == self.window['windowID']), None)
        if (not current or not current['onScreen'] or current['layer'] != 0
                or any(abs(current[key] - self.window[key]) > 1 for key in ('x', 'y', 'width', 'height'))):
            raise DetailUnavailable('window_changed')
        front = subprocess.check_output(['/usr/bin/lsappinfo', 'front'], text=True, timeout=5)
        match = re.search(r'ASN:0x[0-9a-fA-F]+-0x[0-9a-fA-F]+', front)
        if not match:
            raise DetailUnavailable('focus_unavailable')
        info = subprocess.check_output(['/usr/bin/lsappinfo', 'info', '-only', 'bundleid', match[0]], text=True, timeout=5)
        if not re.search(r'bundleID="com\.apple\.findmy"', info):
            raise DetailUnavailable('focus_changed')
        self.check()

    def capture(self):
        self.context()
        self.run('/usr/sbin/screencapture', '-x', '-o', '-l', str(self.window['windowID']), '-t', 'png', str(self.image))
        captured = time.monotonic()
        scale = struct.unpack('>I', self.image.read_bytes()[16:20])[0] / self.window['width']
        if not math.isfinite(scale) or not 0 < scale <= 4:
            raise DetailUnavailable('invalid_capture_scale')
        lines = json.loads(self.run(self.real, 'ocr', str(self.image)))
        self.context()
        if time.monotonic() - captured > MAX_FRAME_AGE:
            raise DetailUnavailable('capture_too_old')
        return lines, scale, captured

    def click(self, name, tab=False):
        # Verify twice: expanding a row can move the next row over Directions.
        first, scale, _ = self.capture()
        before = target(first, scale, name, self.canonical, tab)
        time.sleep(.15)
        second, scale, captured = self.capture()
        box = target(second, scale, name, self.canonical, tab)
        if any(abs(a - b) > 2 for a, b in zip(before, box)):
            raise DetailUnavailable('target_moved')
        x, y = box[0] + box[2] / 2, box[1] + box[3] / 2
        if not (0 <= x < self.window['width'] and 0 <= y < self.window['height']):
            raise DetailUnavailable('target_outside_window')
        self.context()
        if time.monotonic() - captured > MAX_FRAME_AGE:
            raise DetailUnavailable('capture_too_old')
        # No item names, addresses, or geographic coordinates in the action log.
        self.event('detail_click', purpose='return_items' if tab else 'select_item',
                   window_id=self.window['windowID'], relative_x=round(x, 1), relative_y=round(y, 1))
        self.run(self.real, 'click', str(self.window['x'] + x), str(self.window['y'] + y))


def collect_details(records, window, run, real, check, windows, canonical, event):
    pending = [name for name, location in records.items() if 'address unavailable' in location.casefold()]
    if not pending:
        return
    with tempfile.TemporaryDirectory(prefix='tagtracker-detail-') as directory:
        reader = DetailReader(window, run, real, check, windows, canonical, event, Path(directory) / 'detail.png')
        sx, sy = window['x'] + 160, window['y'] + window['height'] * .60
        try:
            reader.context()
            run(real, 'scroll', str(sx), str(sy), '200')
            time.sleep(.4)
            for _ in range(25 + len(pending)):
                if not pending:
                    break
                lines, scale, _ = reader.capture()
                available = []
                for name in pending:
                    try:
                        target(lines, scale, name, canonical)
                        available.append(name)
                    except DetailUnavailable:
                        pass
                if available:
                    # One item per capture; never reuse this page after expanding it.
                    name = available[0]
                    reader.click(name)
                    time.sleep(.9)
                    card, scale, _ = reader.capture()
                    detail = extract(card, scale, name, canonical, records[name])
                    if detail:
                        records[name] = detail
                    pending.remove(name)
                    reader.click('Items', tab=True)
                    time.sleep(.3)
                    continue
                reader.context()
                run(real, 'scroll', str(sx), str(sy), '-12')
                time.sleep(.4)
        except IdlePause:
            # Let the collector discard the interrupted batch and close its window.
            raise
        except DetailUnavailable as error:
            event('detail_skipped', reason=str(error))
        except Exception as error:
            event('detail_skipped', reason='capture_or_control_failed', error_type=type(error).__name__)
