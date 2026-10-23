"""Portable report exports. All text in HTML is escaped; no scripts or remote assets."""

from __future__ import annotations

import html
import json
import re
from datetime import datetime


def report_exports(result: dict, sources: list[dict], *, title: str = "子平术数解读报告") -> dict[str, bytes]:
    from ai_analysis import STEP_TITLES
    report = result["report"]
    by_id = {s["source_id"]: s for s in sources}
    lines = [title, "生成模型：" + str(result.get("model", "")),
             "四柱：" + "　".join(str(report["pillars"].get(k, "")) for k in ("年柱", "月柱", "日柱", "时柱"))]
    lines += ["", "摘要", str(report["summary"])]
    for step in report["steps"]:
        number = step["step"]
        step_title = STEP_TITLES[number - 1] if type(number) is int and 1 <= number <= len(STEP_TITLES) else "分析"
        lines += ["", f"第 {number} 步 · {step_title}", str(step["conclusion"])]
        lines += ["命盘依据：" + value for value in step.get("chart_evidence", [])]
        for citation in step.get("citations", []):
            source = by_id.get(citation["source_id"], {})
            lines += [f"原文依据：《{source.get('book_name', '来源待核')}》 · {source.get('chapter', '')}"
                      f" · 第 {source.get('line_number', '')} 行", citation["quote"]]
        lines += ["待核：" + value for value in step.get("uncertainties", [])]
    lines += ["", "本次局限", *report.get("limitations", []), "",
              "本报告为传统文献的 AI 辅助解读。摘录字面校验不代表解释适用性已获证实。"]
    text = "\n".join(lines)
    escaped = html.escape(text)
    page = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">'
            f'<title>{html.escape(title)}</title><style>'
            'body{max-width:820px;margin:40px auto;padding:0 24px;color:#25221c;background:#faf7ef;'
            'font-family:serif}pre{font-family:inherit;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.9}'
            '@media print{body{background:white;margin:0;max-width:none}pre{font-size:11pt}}'
            f'</style><body><h1>{html.escape(title)}</h1><pre>{escaped}</pre></body></html>')
    artifact = {"format": "ziping-report-v1", "exported_at": datetime.now().isoformat(timespec="seconds"),
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
    st.caption("HTML 报告可离线打开，再用浏览器“打印 → 另存为 PDF”。文件不含模型密钥。")
