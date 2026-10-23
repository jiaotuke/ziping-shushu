"""Windows portable launcher; bundled Python and local-only Streamlit server."""

from __future__ import annotations

import ctypes
import logging
import os
import shutil
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path


def main():
    frozen = getattr(sys, "frozen", False)
    resource = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    base = Path(sys.executable).resolve().parent if frozen else resource
    user_data = base / "user-data"
    user_data.mkdir(parents=True, exist_ok=True)
    cache = user_data / ".cache"
    cache.mkdir(exist_ok=True)
    settings_dir = user_data / ".streamlit"
    settings_dir.mkdir(exist_ok=True)
    if not (settings_dir / "config.toml").exists():
        shutil.copyfile(resource / ".streamlit/config.toml", settings_dir / "config.toml")
    os.environ.update(ZIPING_PORTABLE="1", ZIPING_RESOURCE_ROOT=str(resource), ZIPING_USER_DATA=str(user_data),
                      STREAMLIT_BROWSER_GATHER_USAGE_STATS="false", STREAMLIT_SERVER_FILE_WATCHER_TYPE="none",
                      HF_HOME=str(cache / "huggingface"), SENTENCE_TRANSFORMERS_HOME=str(cache / "sentence-transformers"))
    # The distributable never reads the developer's working-directory secrets.
    os.chdir(user_data)
    log = open(user_data / "startup.log", "a", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = log
    if sys.stderr is None:
        sys.stderr = log
    logging.basicConfig(stream=log, level=logging.WARNING)
    print("子平术数正在启动，将自动打开浏览器。请保留此窗口，关闭窗口即可退出应用。", flush=True)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    url = f"http://127.0.0.1:{port}"

    def open_when_ready():
        for _ in range(120):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=.5):
                    webbrowser.open(url)
                    return
            except OSError:
                time.sleep(.5)

    threading.Thread(target=open_when_ready, daemon=True).start()
    from streamlit.web import cli
    sys.argv = ["streamlit", "run", str(resource / "app.py"), "--server.address=127.0.0.1",
                f"--server.port={port}", "--server.headless=true", "--server.fileWatcherType=none",
                "--browser.gatherUsageStats=false", "--global.developmentMode=false"]
    cli.main()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        pass
    except Exception:
        logging.exception("启动失败")
        ctypes.windll.user32.MessageBoxW(None, "启动未完成，请解压整个文件夹后运行。详细信息见 user-data/startup.log。", "子平术数", 0x10)
