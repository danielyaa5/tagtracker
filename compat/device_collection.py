"""Read Devices during the existing idle-gated Find My scan.

Screen observations retain their displayed age. A collection timestamp never
means the device supplied a new location fix.
"""
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
import struct
import tempfile
import time
import uuid

SOURCE = 'tagtracker.findmy.devices.v1'
DISTANCE = re.compile(r'^\d+(?:[.,]\d+)?\s*(?:mi|km|ft|m)$', re.I)
def is_distance(text):
    return bool(DISTANCE.fullmatch(text) or text == 'Nearby')
BATTERY = re.compile(r'^\d{1,3}\s*%$')
UNKNOWN = re.compile(r'^(?:No location(?: found)?|Not found|Offline|Location unavailable)$', re.I)


def parse_page(lines, scale, height, captured_at):
    """Anchor each row on its location line, then pair only a nearby name."""
    sidebar = sorted((line for line in lines
                      if 48 * scale <= line['x'] < 285 * scale
                      and line['x'] + line['width'] / 2 < 300 * scale
                      and 140 * scale < line['y'] < (height - 10) * scale),
                     key=lambda line: (line['y'], line['x']))
    rows = []
    for index, line in enumerate(sidebar):
        text = line['text'].strip().replace('·', '•')
        if '•' not in text and not UNKNOWN.fullmatch(text):
            continue
        names = [candidate for candidate in sidebar[:index]
                 if 4 < (line['y'] - candidate['y']) / scale < 48
                 and candidate['x'] < 240 * scale
                 and not is_distance(candidate['text'].strip())
                 and not BATTERY.fullmatch(candidate['text'].strip())
                 and '•' not in candidate['text'] and '·' not in candidate['text']]
        if not names:
            continue
        name_line = names[-1]
        name = name_line['text'].strip()
        if name in {'People', 'Devices', 'Items', 'Me', 'Family', 'My Devices'}:
            continue
        location, separator, staleness = text.partition('•')
        if location.strip() in {'This Mac', 'This iPhone', 'This iPad', 'This Apple Watch'}:
            location, staleness = staleness, ''
        nearby = [candidate for candidate in sidebar
                  if abs(candidate['y'] - name_line['y']) < 38 * scale]
        distance_lines = [candidate for candidate in nearby if is_distance(candidate['text'].strip())]
        battery_lines = [candidate for candidate in nearby if BATTERY.fullmatch(candidate['text'].strip())]
        # A split relative-age line is age text, never another device name.
        below = [candidate['text'].strip() for candidate in sidebar
                 if 0 < (candidate['y'] - line['y']) / scale < 22]
        if staleness.strip().isdigit() and below and re.fullmatch(r'(?:min\.?|hr\.?|hours?|days?|weeks?) ago', below[0], re.I):
            staleness += ' ' + below[0]
        row = dict(name=name, location=location.strip(), staleness=staleness.strip(),
                   distance=distance_lines[0]['text'].strip() if len(distance_lines) == 1 else '',
                   battery=battery_lines[0]['text'].strip() if len(battery_lines) == 1 else '',
                   captured_at=captured_at, y=name_line['y'] / scale,
                   confidence=min(float(name_line.get('confidence', 0)), float(line.get('confidence', 0))),
                   distance_confidence=float(distance_lines[0].get('confidence', 0)) if len(distance_lines) == 1 else 0)
        if any(previous['name'] == name for previous in rows):
            raise ValueError('Ambiguous duplicate device name on the same page')
        rows.append(row)
    return rows


def confirm_rows(previous, current):
    """An actionable numeric distance must agree in two separate captures."""
    prior = {row['name']: row for row in previous}
    for row in current:
        row['confirmed_captures'] = 1
        first = prior.get(row['name'])
        if (first and .5 <= row['captured_at'] - first['captured_at'] <= 30
                and all(row[key] == first[key] for key in ('name', 'location', 'staleness', 'distance'))):
            row.update(confirmed_captures=2, confirmation_started_at=first['captured_at'],
                       confidence=min(row['confidence'], first['confidence']),
                       distance_confidence=min(row['distance_confidence'], first['distance_confidence']))
    return current


def save_observations(db_path, records, scan_id, finished_at):
    """Commit a complete Devices sweep to the existing history schema."""
    db_path = Path(db_path)
    with closing(sqlite3.connect(db_path, timeout=15)) as db, db:
        db.execute('CREATE TABLE IF NOT EXISTS observations (id INTEGER PRIMARY KEY, ts TEXT NOT NULL, kind TEXT NOT NULL, name TEXT NOT NULL, location TEXT, staleness TEXT, distance TEXT, battery TEXT, raw_json TEXT NOT NULL)')
        db.execute('CREATE INDEX IF NOT EXISTS idx_observations_kind_name_id ON observations(kind,name,id)')
        for record in records:
            raw = {key: value for key, value in record.items() if key != 'y'}
            raw.update(source=SOURCE, scan_id=scan_id, complete_scan=True, finished_at=finished_at)
            stamp = datetime.fromtimestamp(record['captured_at'], timezone.utc).isoformat().replace('+00:00', 'Z')
            db.execute('INSERT INTO observations(ts,kind,name,location,staleness,distance,battery,raw_json) VALUES (?,?,?,?,?,?,?,?)',
                       (stamp, 'devices', record['name'], record['location'], record['staleness'],
                        record['distance'], record['battery'], json.dumps(raw, ensure_ascii=False)))
    db_path.chmod(0o600)


def private_json(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False))
    temp.chmod(0o600)
    temp.replace(path)


def collect_devices(window, run, real, data, check, config=None):
    """Use the caller's guarded runner and exact window; return to Items."""
    from idle_control import IdlePause
    pages, records = [], {}
    config = config or {}
    aliases = config.get('device_aliases', {})
    scan_id = uuid.uuid4().hex
    with tempfile.TemporaryDirectory(prefix='tagtracker-devices-') as directory:
        image = Path(directory) / 'devices.png'

        def capture():
            run('/usr/sbin/screencapture', '-x', '-o', '-l', str(window['windowID']), '-t', 'png', str(image))
            scale = struct.unpack('>I', image.read_bytes()[16:20])[0] / window['width']
            return json.loads(run(real, 'ocr', str(image))), scale

        def select_tab(label):
            lines, scale = capture()
            tabs = [line for line in lines if line['text'].strip() == label
                    and line['y'] < 85 * scale and line['x'] < 400 * scale]
            if len(tabs) != 1:
                raise RuntimeError('Cannot uniquely locate the ' + label + ' tab')
            tab = tabs[0]
            run(real, 'click', str(window['x'] + (tab['x'] + tab['width'] / 2) / scale),
                str(window['y'] + (tab['y'] + tab['height'] / 2) / scale))
            time.sleep(.6)

        try:
            select_tab('Devices')
            sx, sy = window['x'] + 160, window['y'] + window['height'] * .60
            # Find My can restore a list offset after tab selection. Verify the
            # top has settled before collecting, rather than trusting one scroll.
            previous, stable = None, 0
            for _ in range(8):
                run(real, 'scroll', str(sx), str(sy), '200')
                time.sleep(.5)
                captured = time.time()
                lines, scale = capture()
                pages.append(dict(phase='seek_top', captured_at=captured, scale=scale, lines=lines))
                rows = parse_page(lines, scale, window['height'], captured)
                signature = tuple((row['name'], round(row['y'])) for row in rows)
                stable = stable + 1 if signature and signature == previous else 0
                previous = signature
                if stable >= 2:
                    break
            else:
                raise RuntimeError('Could not verify the top of the Devices list')
            previous, stable = None, 0
            for _ in range(35):
                captured = time.time()
                lines, scale = capture()
                pages.append(dict(captured_at=captured, scale=scale, lines=lines))
                rows = parse_page(lines, scale, window['height'], captured)
                if any(is_distance(row['distance']) for row in rows):
                    time.sleep(.5)
                    verified_at = time.time()
                    second, second_scale = capture()
                    pages.append(dict(captured_at=verified_at, scale=second_scale, lines=second))
                    rows = confirm_rows(rows, parse_page(second, second_scale, window['height'], verified_at))
                signature = tuple((row['name'], round(row['y'])) for row in rows)
                stable = stable + 1 if signature and signature == previous else 0
                previous = signature
                for row in rows:
                    original = row['name']
                    row['name'] = aliases.get(original, original)
                    if row['name'] != original:
                        row['ocr_name'] = original
                    records[row['name']] = row
                if stable >= 2:
                    break
                run(real, 'scroll', str(sx), str(sy), '-12')
                time.sleep(.45)
            else:
                raise RuntimeError('Could not verify the bottom of the Devices list')
            if not records:
                raise RuntimeError('No complete Devices rows found')
            if not set(config.get('expected_devices', [])).issubset(records):
                raise RuntimeError('Some configured devices were not read; sweep is incomplete')
            check()
            finished = time.time()
            save_observations(os.environ.get('FINDMY_HISTORY_DB', str(data / 'history.sqlite')),
                              list(records.values()), scan_id, finished)
            private_json(data / 'device-collection-status.json', dict(ok=True, count=len(records), checked_at=finished, scan_id=scan_id))
        except IdlePause:
            raise
        except Exception as error:
            private_json(data / 'device-collection-status.json', dict(ok=False, checked_at=time.time(), error=str(error)))
        finally:
            private_json(data / 'last-device-collection.json', dict(scan_id=scan_id, captured_at=time.time(), records=records, pages=pages))
        # Failure to return to the known tab aborts the entire Items scan.
        select_tab('Items')
        (data / 'tab-selected').touch()
