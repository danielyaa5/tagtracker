#!/usr/bin/env python3
"""Prepare pinned release dependencies and a self-contained Apple silicon payload."""
import hashlib, os, shutil, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / '.tools'
DEPENDENCIES = {
    'Sparkle-2.10.0.tar.xz': ('https://github.com/sparkle-project/Sparkle/releases/download/2.10.0/Sparkle-2.10.0.tar.xz', 'c2bf58aa8387266ac179357b1415d6f2635f044da8be41042af32425dae6da0c'),
    'python.tar.gz': ('https://github.com/astral-sh/python-build-standalone/releases/download/20261013/cpython-3.13.16%2B20261013-aarch64-apple-darwin-install_only_stripped.tar.gz', '16a5332fb0dcb77f163fc8f8cbccd95be1644cc53e68e5d2a79f50afd6680a0e'),
}

def main():
    os.chdir(ROOT)
    downloads = TOOLS / 'downloads'
    downloads.mkdir(parents=True, exist_ok=True)
    for name, (url, digest) in DEPENDENCIES.items():
        archive = downloads / name
        if not archive.exists():
            subprocess.run(['curl', '-fL', '--retry', '2', url, '-o', str(archive)], check=True)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != digest:
            raise SystemExit('Checksum mismatch: ' + name)
    sparkle = TOOLS / 'sparkle'
    sparkle.mkdir(exist_ok=True)
    subprocess.run(['tar', '-xf', str(downloads / 'Sparkle-2.10.0.tar.xz'), '-C', str(sparkle)], check=True)
    subprocess.run(['make', 'build'], check=True)
    runtime = TOOLS / 'payload/runtime'
    if runtime.exists(): shutil.rmtree(runtime)
    runtime.mkdir(parents=True)
    # Only checksum-verified upstream archives are extracted.
    subprocess.run(['tar', '-xzf', str(downloads / 'python.tar.gz'), '-C', str(runtime)], check=True)
    # Python must never add bytecode files to the signed app's sealed resources.
    launcher = runtime / 'python/bin/python3'
    launcher.unlink()
    launcher.write_text('#!/bin/sh\nexport PYTHONDONTWRITEBYTECODE=1\nexec "$(dirname "$0")/python3.13" -B "$@"\n')
    launcher.chmod(0o755)
    for folder in ['bin', 'compat', 'scripts']:
        shutil.copytree(ROOT / folder, runtime / folder, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.sqlite*'))
    licenses = runtime / 'licenses'
    licenses.mkdir()
    for source in [ROOT / 'LICENSE', ROOT / 'THIRD_PARTY_NOTICES.md', ROOT / 'docs/LEAFLET-LICENSE.txt']:
        shutil.copy2(source, licenses / source.name)
    shutil.copy2(sparkle / 'LICENSE', licenses / 'SPARKLE-LICENSE.txt')
    for p in runtime.rglob('*.pyc'): p.unlink()
    subprocess.run(['swift', 'release/make-icon.swift', 'site/assets/logo.svg', 'app/TagTracker.icns'], check=True)
    subprocess.run(['xcodegen', 'generate', '--spec', 'project.yml'], check=True)
    print('Prepared pinned Sparkle, Python, collector, and native project.')

if __name__ == '__main__': main()
