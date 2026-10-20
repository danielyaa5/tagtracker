#!/usr/bin/env python3
"""Create a drag-to-Applications disk image recognized by TagTracker's cleanup."""
import argparse, plistlib, shutil, subprocess, tempfile
from pathlib import Path
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('app', type=Path)
p.add_argument('output', type=Path)
a = p.parse_args()
info = plistlib.loads((a.app / 'Contents/Info.plist').read_bytes())
if info.get('CFBundleIdentifier') != 'io.tagtracker.app': p.error('Expected a TagTracker app bundle')
if a.output.exists(): p.error('Output already exists')
a.output.parent.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix='tagtracker-dmg-') as temporary:
    stage = Path(temporary)
    subprocess.run(['ditto', str(a.app), str(stage / 'TagTracker.app')], check=True)
    (stage / 'Applications').symlink_to('/Applications')
    (stage / '.tagtracker-installer').write_text(info['CFBundleVersion'])
    (stage / 'Install TagTracker.txt').write_text('Drag TagTracker into Applications.\nThen open TagTracker from Applications.\nThe installed app ejects this disk automatically.\n\nRequires Apple silicon and macOS 14 or later.\nUse Start Tracking to configure your items and permissions.\n')
    subprocess.run(['hdiutil', 'create', '-volname', 'TagTracker Installer', '-srcfolder', str(stage), '-format', 'UDZO', str(a.output)], check=True)
print(a.output)
