"""Operator-only SQLite online backup. Does not import application modules."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    source = Path(os.environ.get("ZIPING_PUBLIC_DATA", "/var/lib/ziping/public")) / "public-live.sqlite3"
    if not source.is_file():
        parser.exit(1, "No live public database exists yet; no backup created.\n")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = args.output or Path("/var/lib/ziping/backups") / ("public-live-" + stamp + ".sqlite3")
    target = target.resolve()
    if target == source.resolve() or target.exists():
        parser.exit(1, "Backup destination already exists or is the source.\n")
    target.parent.mkdir(parents=True, exist_ok=True)
    # Reserve the destination to avoid overwriting an existing backup.
    with target.open("xb"):
        pass
    try:
        with sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True) as origin:
            with sqlite3.connect(target) as destination:
                origin.backup(destination)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    print(target)


if __name__ == "__main__":
    main()
