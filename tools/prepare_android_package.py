"""Whitelist-only Android staging: no development cache, credentials or user reports."""

from pathlib import Path
import shutil
import importlib.util
from importlib.metadata import distribution

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / ".tmp/android-stage"
PYTHON_FILES = ("mobile_runtime.py", "runtime_paths.py", "bazi.py", "professional_chart.py", "pillar_relationships.py",
                "sanming_shensha.py", "source_data.py", "structured_retrieval.py", "portable_retrieval.py",
                "ai_analysis.py", "citation_audit.py", "book_translation.py", "report_downloads.py", "luck_analysis.py", "luck_chart.py", "report_presentation.py")
BOOKS = ("穷通宝鉴.txt", "三命通会.txt", "子平真诠.txt", "滴天髓.txt", "SOURCE.md")


def main():
    python_root = STAGE / "python"
    assets = STAGE / "assets"
    python_root.mkdir(parents=True, exist_ok=True)
    assets.mkdir(exist_ok=True)
    for name in PYTHON_FILES:
        shutil.copyfile(ROOT / name, python_root / name)
    dashboard = python_root / "components/life_report"
    dashboard.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "components/life_report/index.html", dashboard / "index.html")
    dashboard_asset = assets / "core-data/components/life_report"
    dashboard_asset.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "components/life_report/index.html", dashboard_asset / "index.html")
    for package_name in ("lunar_python", "tzdata", "certifi"):
        spec = importlib.util.find_spec(package_name)
        origin = Path(next(iter(spec.submodule_search_locations)))
        shutil.copytree(origin, python_root / package_name, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    notices = []
    for package_name in ("lunar_python", "tzdata", "certifi"):
        dist = distribution(package_name)
        notices.append(f"{dist.metadata['Name']} {dist.version}\nLicense: {dist.metadata.get('License', '')}\n")
        for path in dist.files or []:
            if path.name.lower() in ("license", "license.txt", "license.md", "copying"):
                notices.append(Path(dist.locate_file(path)).read_text(encoding="utf-8", errors="replace"))
    package = python_root / "book_retrievers"
    package.mkdir(exist_ok=True)
    for source in (ROOT / "book_retrievers").glob("*.py"):
        shutil.copyfile(source, package / source.name)
    for name in BOOKS:
        target = assets / "core-data/data/source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "data/source" / name, target)
    for name in ("conditions.json", "ziping_chapters.json"):
        target = assets / "core-data/data/annotations" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "data/annotations" / name, target)
    shutil.copyfile(ROOT / "mobile/index.html", assets / "index.html")
    (assets / "THIRD_PARTY_NOTICES.txt").write_text("\n\n".join(notices), encoding="utf-8")
    print("Android whitelisted sources staged under D drive project cache.")


if __name__ == "__main__":
    main()
