"""Read-only bundled books and writable per-device data locations."""

import os
import sys
from pathlib import Path

RESOURCE_ROOT = Path(os.environ.get("ZIPING_RESOURCE_ROOT") or Path(__file__).resolve().parent)
DATA_ROOT = Path(os.environ.get("ZIPING_USER_DATA") or
                 ((Path(sys.executable).resolve().parent / "user-data") if getattr(sys, "frozen", False) else RESOURCE_ROOT))
CACHE_ROOT = DATA_ROOT / ".cache"
