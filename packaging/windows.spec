from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

root = Path(SPECPATH).parent
project_modules = ["bazi", "professional_chart", "professional_panel", "pillar_relationships", "sanming_shensha",
                   "ai_analysis", "ai_panel", "paid_analysis_panel", "report_downloads", "source_data", "runtime_paths", "china_regions",
                   "citation_audit", "book_translation", "translation_panel", "structured_retrieval", "portable_retrieval",
                   "luck_analysis", "luck_chart", "report_presentation", "referral_common", "referral_public_store", "referral_public_panel"]
datas = [(str(root / "app.py"), "."), (str(root / "data/source"), "data/source"),
         (str(root / "data/annotations"), "data/annotations"),
         (str(root / "data/regions"), "data/regions"),
         (str(root / "components/professional_chart"), "components/professional_chart"),
         (str(root / "components/life_report"), "components/life_report"),
         (str(root / ".streamlit/config.toml"), ".streamlit")]
# Application modules remain readable for Streamlit imports.
datas += [(str(root / (name + ".py")), ".") for name in project_modules]
datas += [(str(root / "book_retrievers"), "book_retrievers")]
datas += collect_data_files("streamlit") + collect_data_files("tzdata")
datas += copy_metadata("streamlit", recursive=True)
datas += copy_metadata("qrcode")
hidden = project_modules + collect_submodules("book_retrievers") + collect_submodules("streamlit") + collect_submodules("tzdata") + collect_submodules("qrcode")
a = Analysis([str(root / "desktop_launcher.py")], pathex=[str(root)], binaries=[], datas=datas,
             hiddenimports=hidden,
             excludes=["torch", "transformers", "sentence_transformers", "chromadb", "scipy", "sklearn", "pytest", "IPython"],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="ZipingShushu", debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=True)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="ZipingShushu-Windows")
