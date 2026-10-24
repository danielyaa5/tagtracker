#!/usr/bin/env python3
"""Run one scheduled poll, distinguishing explicit idle pauses from failures."""
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import tempfile
import time
from runtime import BASE, DATA


def record_outcome(outcome, reason):
    """Adapters report only to the wrapper for this invocation."""
    target = os.environ.get('TAGTRACKER_POLL_RESULT')
    token = os.environ.get('TAGTRACKER_POLL_TOKEN')
    if not target or not token:
        return
    Path(target).write_text(json.dumps({'token': token, 'outcome': outcome, 'reason': str(reason)}))


def record_pause(reason):
    record_outcome('paused', reason)


def record_failure(reason):
    # A later real adapter error must override an earlier ignored pause.
    record_outcome('failed', reason)


def poll(command=None):
    DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix='poll-', dir=DATA) as temporary:
        result_path = Path(temporary) / 'result.json'
        token = secrets.token_hex(24)
        environment = dict(os.environ, TAGTRACKER_POLL_RESULT=str(result_path), TAGTRACKER_POLL_TOKEN=token)
        child = subprocess.Popen(command or [str(BASE/'bin/findmy'), 'items', '--json'], env=environment, stderr=subprocess.PIPE)
        previous = {}
        def forward(signum, frame):
            try:
                child.send_signal(signum)
            except ProcessLookupError:
                pass
        try:
            for signum in (signal.SIGTERM, signal.SIGINT):
                previous[signum] = signal.signal(signum, forward)
            _, errors = child.communicate()
        finally:
            for signum, handler in previous.items():
                signal.signal(signum, handler)
        try:
            result = json.loads(result_path.read_text())
            if not isinstance(result, dict):
                result = {}
        except (OSError, ValueError):
            result = {}
        if child.returncode == 1 and result.get('token') == token and result.get('outcome') == 'paused':
            print(time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()) + ' Scan paused: ' + result.get('reason', 'Waiting for next scan'), flush=True)
            return 0
        if errors:
            sys.stderr.buffer.write(errors)
            sys.stderr.buffer.flush()
        # A terminated child must still produce a nonzero scheduler outcome.
        return child.returncode if child.returncode >= 0 else 128 - child.returncode


if __name__ == '__main__':
    raise SystemExit(poll())
