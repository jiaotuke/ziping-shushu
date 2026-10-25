"""Offline report exports with escaped data and a hash-authorized local dashboard script."""

from __future__ import annotations

import html
import json
import re
from datetime import datetime


def report_filename(report: dict) -> str:
    pillars = "-".join(str(report["pillars"].get(name, "")) for name in ("年柱", "月柱", "日柱", "时柱"))
    if report.get("kind") == "period-only":
        scopes = []
        for item in report["periods"]:
            selected = item["selected"]
            if item["id"] == "annual":
                scopes.append(str(selected["流年"]["年份"])+"年流年")
            elif item["id"] == "monthly":
                scopes.append(selected["流月"]["起始时刻"][:10]+"起-流月")
            elif item["id"] == "daily":
                scopes.append(selected["流日"]["日期"]+"-流日")
        scope = "-".join(scopes)+"专项报告"
    else:
        scope = "原局大运报告" if report.get("luck_analysis") else "原局报告"
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", "子平术数-"+pillars+"-"+scope)[:160].rstrip(" .")


def report_exports(result: dict, sources: list[dict], *, title: str = "子平术数解读报告") -> dict[str, bytes]:
    import base64
    import hashlib
    from luck_chart import dashboard_document, extended_html, extended_text, reasoning_html, results_html

    report = result["report"]
    sources = list({s['source_id']:s for s in [*sources,*result.get('additional_sources',[])]}.values())
    period_only = report.get("kind") == "period-only"
    if period_only:
        labels = {"annual": "流年", "monthly": "流月", "daily": "流日"}
        title = "子平术数 · " + "／".join(labels[item['id']] for item in report['periods']) + "专项报告"
    artifact = {"format": "ziping-period-report-v1" if period_only else "ziping-report-v4-importable", "exported_at": datetime.now().isoformat(timespec="seconds"),
                "result": result, "sources": [{k: s.get(k, "") for k in
                ("source_id", "book_name", "chapter", "line_number")} for s in sources]}
    metadata = [title, "生成模型：" + str(result.get("model", "")),
                "四柱：" + "　".join(str(report["pillars"].get(k, "")) for k in ("年柱", "月柱", "日柱", "时柱"))]
    if period_only:
        metadata.append("报告类型：时间专项（不含基础报告）")
    profile = result.get("birth_profile", {})
    metadata += ["性别：" + str(profile.get("gender") or "未记录"),
                 "公历出生时刻：" + str(profile.get("birth_datetime") or "未记录").replace('T', ' ')]
    if profile.get("source") == "confirmed_on_import":
        metadata.append("出生资料来源：导入时按当前命盘补充确认，旧报告未记载完整出生资料。")
    text = "\n".join(metadata) + "\n\n" + extended_text(report, sources)
    if period_only:
        meta_html = '<header>' + '<br>'.join(html.escape(line) for line in metadata) + '</header>'
        page = ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">'
                '<title>'+html.escape(title)+'</title><style>'
                'body{max-width:1000px;margin:28px auto;padding:0 24px;font-family:Arial,sans-serif;line-height:1.8;background:#101114;color:#eee}'
                'header{color:#aaa;font-size:13px}h2,h3,h4{color:#d7c198}.summary-cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}'
                '.summary-cards article{border:1px solid #666;padding:14px;border-radius:10px}summary{cursor:pointer}'
                'blockquote{border-left:2px solid #a87b40;padding-left:12px}p,li{overflow-wrap:anywhere}'
                '@media(max-width:600px){.summary-cards{grid-template-columns:1fr}}'
                '@media print{body{background:white;color:#222}h2,h3,h4{color:#222}details>*{display:block!important}'
                'details::details-content{content-visibility:visible;height:auto}}'
                '</style></head><body>'+meta_html+extended_html(report,sources)+'</body></html>')
        return {"html":page.encode('utf-8'), "txt":text.encode('utf-8-sig'),
                "json":json.dumps(artifact,ensure_ascii=False,indent=2).encode('utf-8')}
    imported = result.get("imported_basis", {})
    historical_text = imported.get("text", "") if imported.get("mode") == "narrative" else ""
    if historical_text:
        text += "\n\n导入的历史基础报告原文（未重新生成或评分）\n" + historical_text
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
    if historical_text:
        appendix += ('<details class="export-reasoning"><summary>导入的历史基础报告原文（未重新生成或评分）</summary>'
                     '<p style="white-space:pre-wrap">' + html.escape(historical_text) + '</p></details>')
    snapshot = json.dumps(artifact, ensure_ascii=False).replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')
    page = page.replace('</body>', appendix + '<script id="ziping-report-snapshot" type="application/json">' + snapshot + '</script></body>')
    return {"html": page.encode("utf-8"), "txt": text.encode("utf-8-sig"),
            "json": json.dumps(artifact, ensure_ascii=False, indent=2).encode("utf-8")}


def render_report_downloads(result: dict, sources: list[dict], *, key: str) -> None:
    import streamlit as st

    exports = report_exports(result, sources)
    base = report_filename(result["report"])
    period_only = result["report"].get("kind") == "period-only"
    st.markdown("#### 下载专项报告" if period_only else "#### 下载报告")
    for col, ext, label, mime in zip(st.columns(3), ("html", "txt", "json"),
                                    ("排版报告 HTML", "纯文本 TXT", "专项数据 JSON" if period_only else "完整数据 JSON"),
                                    ("text/html", "text/plain", "application/json")):
        with col:
            st.download_button(label, exports[ext], file_name=f"{base}.{ext}", mime=mime,
                               key=f"report_download_{key}_{ext}", use_container_width=True)
    if result["report"].get("kind") == "period-only":
        st.caption("仅下载当前年／月／日专项及其依据；基础报告请在上方单独保存。专项文件不能替代基础报告导入。")
    else:
        st.caption("HTML 报告可离线点击 K 线切换大运，打印时包含全部大运与推导；也可另存为 PDF。文件不含模型密钥。")
        st.caption("JSON或新版HTML可恢复原局、大运及评分用于追加分析；旧版HTML和TXT也可按文字基线导入。")
