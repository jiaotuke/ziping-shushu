"""Prepare an explicit public deployment tree; never include local management."""
from pathlib import Path
import argparse
import shutil

ROOT = Path(__file__).resolve().parents[1]
MODULES = (
    "app.py","public_app.py","ai_panel.py","ai_analysis.py","bazi.py","book_translation.py",
    "china_regions.py","citation_audit.py","luck_analysis.py","luck_chart.py","paid_analysis_panel.py",
    "pillar_relationships.py","portable_retrieval.py","professional_chart.py","professional_panel.py",
    "rag.py","referral_common.py","referral_public_panel.py","referral_public_store.py","referral_site_sync.py",
    "report_downloads.py","report_presentation.py","runtime_paths.py","sanming_shensha.py","source_data.py",
    "structured_retrieval.py","translation_panel.py","requirements-public.txt",
)


def prepare(output: Path):
    output = output.resolve()
    if not output.is_relative_to((ROOT / ".tmp").resolve()):
        raise ValueError("公开站点暂存目录必须位于项目 D 盘 .tmp 内。")
    files = list(MODULES)
    files += [str(p.relative_to(ROOT)).replace("\\","/") for p in (ROOT/"book_retrievers").glob("*.py")]
    files += ["data/source/"+name for name in ("穷通宝鉴.txt","三命通会.txt","子平真诠.txt","滴天髓.txt","SOURCE.md")]
    files += ["data/annotations/conditions.json","data/annotations/ziping_chapters.json"]
    files += ["data/regions/"+name for name in ("china_regions.json","SOURCE.md","LICENSE-AreaCity.txt")]
    files += ["components/professional_chart/index.html","components/life_report/index.html",".streamlit/config.toml"]
    allowed = set(files)
    if output.exists():
        unexpected = []
        for path in output.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(output)
            name = relative.as_posix()
            own_cache = (relative.parent.name=="__pycache__" and path.suffix==".pyc"
                         and (relative.parent.parent / (path.name.split(".")[0]+".py")).as_posix() in allowed)
            if name not in allowed and not own_cache:
                unexpected.append(name)
        if unexpected:
            raise ValueError("目标目录存在白名单外文件，请选择新目录："+", ".join(unexpected[:5]))
    for name in files:
        target = output / name
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/name,target)
    print("公开站点源码已准备：",output)
    print("未包含本机后台、真实账本、管理员凭据、模型密钥、缓存或签名文件。")
    return tuple(files)


if __name__=="__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,default=ROOT/".tmp"/"public-site-v2")
    args = parser.parse_args()
    prepare(args.output)
