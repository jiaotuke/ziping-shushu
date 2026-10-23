"""Create clean customer archives and checksums without copying local user data."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
LOCATION = ROOT / ".tmp/windows-release-location.txt"
WINDOWS = Path(LOCATION.read_text(encoding="utf-8-sig").strip()) if LOCATION.is_file() else DIST / "ZipingShushu-Windows"
if not WINDOWS.resolve().is_relative_to(ROOT):
    raise SystemExit("Windows release must remain inside the project directory.")
FORBIDDEN = {"user-data", ".local", ".cache", ".git", "__pycache__"}


def releasable(path: Path) -> bool:
    relative = path.relative_to(WINDOWS)
    return not (set(relative.parts) & FORBIDDEN or path.name.lower() == "secrets.toml"
                or path.name.startswith(".env") or path.suffix.lower() in (".jks", ".keystore"))


def main():
    if not (WINDOWS / "ZipingShushu.exe").is_file() or not (WINDOWS / "_internal").is_dir():
        raise SystemExit("Build the full Windows application first.")
    apk = DIST / "ZipingShushu-Android.apk"
    if not apk.is_file():
        raise SystemExit("Build the Android release APK first.")
    instructions = ROOT / "packaging/使用说明.txt"
    shutil.copyfile(instructions, DIST / instructions.name)
    shutil.copyfile(instructions, WINDOWS / instructions.name)
    archive = DIST / "ZipingShushu-Windows.zip"
    with ZipFile(archive, "w", ZIP_DEFLATED, compresslevel=6) as output:
        for path in sorted(WINDOWS.rglob("*")):
            if path.is_file() and releasable(path):
                output.write(path, "ZipingShushu-Windows/" + path.relative_to(WINDOWS).as_posix())
    manifest = {"version": "0.5.0", "files": []}
    for artifact in (archive, apk):
        digest = hashlib.sha256()
        with artifact.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        manifest["files"].append({"name": artifact.name, "bytes": artifact.stat().st_size, "sha256": digest.hexdigest()})
    (DIST / "release-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
