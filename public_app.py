"""Public entry point. Deploy only the public-site whitelist bundle."""
import os
from pathlib import Path
import runpy

SITE_ROOT = Path(__file__).resolve().parent
os.environ["ZIPING_PUBLIC_SITE"] = "1"
for key in ("GLM_API_KEY","ZHIPU_API_KEY","DEEPSEEK_API_KEY"):
    os.environ.pop(key,None)
os.environ.setdefault("ZIPING_PORTABLE","1")
os.environ.setdefault("ZIPING_RESOURCE_ROOT",str(SITE_ROOT))
os.environ.setdefault("ZIPING_USER_DATA",str(SITE_ROOT / ".local" / "site-runtime"))
runpy.run_path(str(SITE_ROOT / "app.py"),run_name="__main__")
