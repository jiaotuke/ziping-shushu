"""Create local Android signing settings without printing passwords."""

import json
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
folder = root / ".local/android-signing"
folder.mkdir(parents=True, exist_ok=True)
target = folder / "signing.json"
if not target.exists():
    target.write_text(json.dumps({"keystore": str(folder / "ziping-release.jks"),
                                  "password": secrets.token_urlsafe(36)}, indent=2), encoding="utf-8")
print("Local Android signing settings are ready; credentials were not printed.")
