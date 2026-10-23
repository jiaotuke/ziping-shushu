"""Offline report exports with escaped data and a hash-authorized local dashboard script."""

from __future__ import annotations

import html
import json
import re
from datetime import datetime


def report_exports(result: dict, sources: list[dict], *, title: str = "子平术数解读报告") -> dict[str, bytes]:
    import base64
    import hashlib
    from luck_chart import dashboard_document, extended_text, reasoning_html, results_html

    report = result["report"]
    metadata = [title, "生成模型：" + str(result.get("model", "")),
                "四柱：" + "　".join(str(report["pillars"].get(k, "")) for k in ("年柱", "月柱", "日柱", "时柱"))]
    text = "\n".join(metadata) + "\n\n" + extended_text(report, sources)
    page = dashboard_document(report)
    script = re.search(r'<script id="ziping-dashboard-script">(.*?)</script>', page, re.S).group(1)
    digest = base64.b64encode(hashlib.sha256(script.encode("utf-8")).digest()).decode("ascii")
    policy = f"default-src 'none'; style-src 'unsafe-inline'; script-src 'sha256-{digest}'"
    extra_head = ('<meta http-equiv="Content-Security-Policy" content="' + html.escape(policy, quote=True) + '">'
                  '<style>html,body{background:#101114}body{max-width:1100px;margin:28px auto;padding:0 24px}'
                  '.export-meta{font-size:13px;color:#aaa;line-height:1.8;margin-bottom:22px}'
                  '.export-reasoning{margin:24px 0;padding:20px;border:1px solid #49433a;border-radius:14px}'
                  '.export-reasoning summary{cursor:pointer;line-height:1.8;color:#d7c198}'
                  '.export-reasoning details{margin:12px 0;padding:12px;border:1px solid #3e3b37;border-radius:8px}'
                  '.export-reasoning p,.export-reasoning li{line-height:1.9;overflow-wrap:anywhere}'
                  'blockquote{border-left:2px solid #a87b40;padding-left:12px}'
                  '.summary-cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}'
                  '.summary-cards article{border:1px solid #aaa;padding:14px;border-radius:10px}'
                  '@media print{html,body{background:white;color:#222;margin:0;padding:8px;max-width:none}'
                  '#root{display:none}.print-only{display:block}svg{min-width:0!important}'
                  'details>*{display:block!important}details::details-content{content-visibility:visible;height:auto}'
                  '.export-reasoning summary{color:#222}.export-reasoning{padding:0;border:0}'
                  '.result-summary{break-inside:avoid}.summary-cards p{font-size:11pt}}'
                  '</style>')
    page = page.replace('<title>子平术数 · 人生概览</title>', '<title>' + html.escape(title) + '</title>')
    page = page.replace('</head>', extra_head + '</head>')
    meta_html = '<header class="export-meta">' + '<br>'.join(html.escape(line) for line in metadata) + '</header>'
    page = page.replace('<main id="root"', meta_html + '<main id="root"', 1)
    appendix = ('<section class="print-only">' + results_html(report) + '</section>'
                '<details class="export-reasoning"><summary>查看完整推导与古籍依据</summary>'
                + reasoning_html(report, sources) + '</details>')
    page = page.replace('</body>', appendix + '</body>')
    artifact = {"format": "ziping-report-v3-results-first", "exported_at": datetime.now().isoformat(timespec="seconds"),
                "result": result, "sources": [{k: s.get(k, "") for k in
                ("source_id", "book_name", "chapter", "line_number")} for s in sources]}
    return {"html": page.encode("utf-8"), "txt": text.encode("utf-8-sig"),
            "json": json.dumps(artifact, ensure_ascii=False, indent=2).encode("utf-8")}


def render_report_downloads(result: dict, sources: list[dict], *, key: str) -> None:
    import streamlit as st

    exports = report_exports(result, sources)
    base = "子平术数-" + re.sub(r"[^A-Za-z0-9_-]", "", key)[:60]
    st.markdown("#### 下载报告")
    for col, ext, label, mime in zip(st.columns(3), ("html", "txt", "json"),
                                    ("排版报告 HTML", "纯文本 TXT", "完整数据 JSON"),
                                    ("text/html", "text/plain", "application/json")):
        with col:
            st.download_button(label, exports[ext], file_name=f"{base}.{ext}", mime=mime,
                               key=f"report_download_{key}_{ext}", use_container_width=True)
    st.caption("HTML 报告可离线点击 K 线切换大运，打印时包含全部大运与推导；也可另存为 PDF。文件不含模型密钥。")
