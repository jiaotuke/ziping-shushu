"""Build a public-only source archive on D:. No dependency downloads or cloud calls."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
from zipfile import ZIP_DEFLATED, ZipFile

from prepare_public_site import ROOT, prepare

ASSETS = (
    "Dockerfile", ".dockerignore", "compose.yaml", "Caddyfile", ".env.example",
    "README.md", "maintenance/backup_public.py",
    "maintenance/deploy_release.py",
    "maintenance/security_monitor.py",
)


def build():
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    release = ROOT / ".tmp" / "cloud-releases" / ("ziping-public-" + stamp)
    release.mkdir(parents=True, exist_ok=False)
    site_files = prepare(release / "site")
    files = ["site/" + item for item in site_files]
    for name in ASSETS:
        target = release / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "deploy" / "public-site" / name, target)
        files.append(name)
    checksums = {name: hashlib.sha256((release / name).read_bytes()).hexdigest() for name in sorted(files)}
    manifest = {
        "format": "ziping-public-release-v1", "release": release.name,
        "contains_private_ledger": False, "contains_demo_data": False,
        "contains_model_keys": False, "sha256": checksums,
        "status": "source-prepared-not-deployed-or-runtime-tested",
    }
    (release / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    archive = release.with_suffix(".zip")
    with ZipFile(archive, "x", ZIP_DEFLATED) as bundle:
        for name in sorted([*files, "manifest.json"]):
            bundle.write(release / name, arcname=release.name + "/" + name)
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(".zip.sha256").write_text(checksum + "  " + archive.name + "\n", encoding="ascii")
    print(archive)
    print("Bytes:", archive.stat().st_size)
    print("SHA256:", checksum)
    return release, archive


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    build()
