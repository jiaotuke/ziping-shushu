"""Refresh a self-contained skill with an explicit source whitelist; no cloud calls."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "ziping-shushu"
MODULES = (
    "bazi.py", "sanming_shensha.py", "professional_chart.py", "pillar_relationships.py",
    "portable_retrieval.py", "source_data.py", "runtime_paths.py",
    "ai_analysis.py", "citation_audit.py", "luck_analysis.py", "luck_chart.py",
    "report_presentation.py", "report_downloads.py", "components/life_report/index.html",
    "book_retrievers/__init__.py", "book_retrievers/common.py", "book_retrievers/registry.py",
    "book_retrievers/qiong_tong_bao_jian.py", "book_retrievers/sanming_tonghui.py",
    "book_retrievers/ziping_zhenquan.py", "book_retrievers/ditian_sui.py",
    "data/source/穷通宝鉴.txt", "data/source/三命通会.txt", "data/source/子平真诠.txt",
    "data/source/滴天髓.txt", "data/source/SOURCE.md", "data/annotations/ziping_chapters.json",
)
SKILL_FILES = (
    "SKILL.md", "requirements.txt", "agents/openai.yaml", "scripts/ziping.py", "scripts/luck_workflow.py",
    "references/commands.md", "references/report-guide.md", "references/token-budget.md",
    "references/luck-workflow.md",
)


def main() -> None:
    engine = SKILL / "assets" / "engine"
    for name in MODULES:
        target = engine / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    hashes = {name: hashlib.sha256((engine / name).read_bytes()).hexdigest() for name in MODULES}
    manifest_name = "assets/bundle-manifest.json"
    (SKILL / manifest_name).write_text(json.dumps({
        "format": "ziping-skill-bundle-v1", "source_sha256": hashes,
        "includes_model_keys": False, "includes_business_databases": False,
        "runtime_examples_executed": False, "token_estimate": "planning-only-not-measured",
        "extended_luck": "explicit-request-staged-host-ai-no-provider-api",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    files = [*SKILL_FILES, manifest_name, *("assets/engine/" + name for name in MODULES)]
    archive_dir = ROOT / ".tmp" / "skill-releases"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive = archive_dir / ("ziping-shushu-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".zip")
    with ZipFile(archive, "x", ZIP_DEFLATED) as bundle:
        for name in files:
            bundle.write(SKILL / name, "ziping-shushu/" + name)
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(".zip.sha256").write_text(checksum + "  " + archive.name + "\n", encoding="ascii")
    print("Skill folder:", SKILL)
    print("Archive:", archive)
    print("Whitelisted files:", len(files))
    print("Bytes:", archive.stat().st_size)
    print("SHA256:", checksum)


if __name__ == "__main__":
    main()
