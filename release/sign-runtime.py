#!/usr/bin/env python3
"""Sign nested Mach-O files before Xcode seals the enclosing application."""
import subprocess, sys
from pathlib import Path
runtime = Path(sys.argv[1])
identity = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else '-'
magic = {b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca'}
for path in sorted(runtime.rglob('*')):
    if not path.is_file() or path.is_symlink(): continue
    with path.open('rb') as stream: header = stream.read(4)
    if header not in magic: continue
    command = ['codesign', '--force', '--options', 'runtime', '--sign', identity]
    if identity != '-': command.append('--timestamp')
    subprocess.run([*command, str(path)], check=True)
