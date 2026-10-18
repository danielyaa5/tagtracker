"""Portable paths; personal configuration and runtime data never live in source."""
import os
from pathlib import Path
BASE=Path(__file__).resolve().parent.parent
DATA=Path(os.environ.get('TAGTRACKER_DATA_DIR',str(Path.home()/'Library/Application Support/TagTracker'))).expanduser()
