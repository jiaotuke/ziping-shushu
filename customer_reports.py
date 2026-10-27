"""Explicit private report favorites. Uploaded HTML is never executed in the page."""
from __future__ import annotations
from datetime import datetime
import hashlib
from html.parser import HTMLParser
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo
import streamlit as st
from customer_store import CustomerError, MAX_FAVORITE_REPORTS, MAX_FAVORITE_TOTAL
from public_security import check_action, PublicSecurityError


def _notify(message):
    st.session_state["customer_flash"] = message
    st.session_state["customer_show_reports"] = True
    st.rerun()


class _ReadableHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.ignored = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "svg", "iframe", "object", "template"):
            self.ignored.append(tag)
        elif not self.ignored and tag in ("p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "summary", "header"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if self.ignored:
            if tag == self.ignored[-1]:
                self.ignored.pop()
        elif tag in ("p", "div", "li", "tr", "h1", "h2", "h3", "h4", "header"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.ignored:
            self.parts.append(data)


def readable_report(raw, *, html=False):
    encodings = ("utf-16",) if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else ("utf-8-sig", "gb18030")
    for encoding in encodings:
        try:
            text = raw.decode(encoding)
            if "\x00" not in text:
                break
        except UnicodeError:
            continue
    else:
        raise CustomerError("报告编码无法识别，请使用UTF-8、UTF-16或GB18030文本。")
    if html:
        parser = _ReadableHTML()
        parser.feed(text)
        parser.close()
        text = "".join(parser.parts)
    if not text.strip():
        raise CustomerError("报告中没有可读取的文字内容。")
    return text


def _chart_choice(rows, *, key):
    options = {row["id"]:row for row in rows}
    if st.session_state.get(key) is not None and st.session_state[key] not in options:
        st.session_state.pop(key, None)
    return st.selectbox("关联排盘（选填）", [None, *options],
                        format_func=lambda cid: "独立收藏，不关联排盘" if cid is None else options[cid]["title"]+" · "+options[cid]["summary"],
                        key=key)


def render_collect_report(exports, base, *, key):
    """Use existing export bytes only; never submit a model request."""
    from customer_panel import store
    try:
        service = store()
        token = st.session_state.get("customer_token", "")
        if not service.identity(token):
            st.caption("登录后可将这份报告加入账号中的“报告收藏”。")
            return
        identity = hashlib.sha256(key.encode()).hexdigest()[:20]
        with st.expander("收藏这份报告"):
            st.caption("收藏当前报告版本；后续生成不会自动覆盖。相同文件重复收藏会更新名称与关联，不重复占空间。不保存模型密钥。")
            with st.form("customer_collect_"+identity, clear_on_submit=True):
                title = st.text_input("收藏名称", value=base.removeprefix("子平术数-")[:80], max_chars=80)
                note = st.text_area("收藏备注（选填）", max_chars=300)
                chart_id = _chart_choice(service.list_charts(token), key="customer_collect_chart_"+identity)
                consent = st.checkbox("确认报告与所选排盘对应，并收藏这份报告到账号")
                submitted = st.form_submit_button("加入报告收藏", type="primary", use_container_width=True)
            if submitted:
                check_action("customer_save")
                if not consent:
                    raise CustomerError("请先勾选确认收藏。")
                service.save_report(token,title,note,chart_id,base,exports)
                _notify("报告已收藏，可在页面上方“我的排盘 → 报告收藏”查看和下载。")
    except (CustomerError, PublicSecurityError) as error:
        st.error(str(error))
    except (OSError, sqlite3.Error):
        st.error("报告暂时无法收藏，请稍后重试。")


def render_report_library(service, token):
    usage = service.report_usage(token)
    st.caption(f"已收藏 {usage['count']} / {MAX_FAVORITE_REPORTS} 份 · 已用 {usage['bytes']/1024/1024:.2f} / {MAX_FAVORITE_TOTAL//1024//1024} MB。单份收藏含全部下载格式最多5MB。")
    rows = service.list_reports(token)
    if not rows:
        st.info("还没有收藏报告。可在报告下载区点击“收藏这份报告”，或在下方上传以前下载的HTML、TXT报告。")
    else:
        charts = service.list_charts(token)
        with st.expander("筛选关联的排盘"):
            selected_chart = _chart_choice(charts, key="customer_report_filter_chart")
            all_reports = st.checkbox("显示全部报告（含独立收藏）", value=True, key="customer_report_filter_all")
        visible = rows if all_reports else [row for row in rows if row["chart_id"] == selected_chart]
        if not visible:
            st.info("当前筛选下没有报告，可勾选“显示全部报告”，或上传并关联这份排盘的报告。")
        by_id = {row["id"]:row for row in visible}
        selected_key = "customer_report_selection"
        if st.session_state.get(selected_key) not in by_id:
            st.session_state.pop(selected_key, None)
        rid = st.selectbox("选择收藏的报告", list(by_id), index=None,
                           format_func=lambda rid: by_id[rid]["title"], key=selected_key,
                           placeholder="请选择要查看或下载的报告")
        if rid:
            row = service.load_report(token,rid)
            meta = by_id[rid]
            st.caption("关联排盘："+(meta["chart_title"] or "独立收藏／原排盘已删除"))
            stamp = datetime.fromtimestamp(row["updated"],ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M")
            st.caption(f"最近收藏：{stamp} · 文件总大小 {row['size_bytes']/1024:.1f} KB")
            if row["note"]:
                st.text(row["note"])
            raw = row["txt"] or row["html"]
            if raw:
                with st.expander("查看报告正文"):
                    text = readable_report(raw, html=not bool(row["txt"]))
                    st.text_area("报告正文（只读）",value=text[:50000],height=360,disabled=True,key="customer_report_text_"+rid)
                    if len(text)>50000:
                        st.caption("此处展示前5万字，完整内容请下载。")
            for ext, label, mime in (("html","下载排版HTML","text/html"),("txt","下载纯文本TXT","text/plain"),("json","下载报告数据JSON","application/json")):
                if row[ext]:
                    st.download_button(label,row[ext],file_name=row["filename"]+"."+ext,mime=mime,
                                       key="customer_report_download_"+rid+"_"+ext,use_container_width=True)
            if st.button("问问AI",key="ask_favorite_"+rid,type="primary",use_container_width=True):
                from report_chat_panel import open_report_chat
                open_report_chat(readable_report(row["txt"] or row["html"],html=not bool(row["txt"])),row['title'],return_screen='account',report_id=rid)
            with st.form("customer_delete_report_"+rid, clear_on_submit=True):
                confirmed = st.checkbox("确认删除这份报告收藏")
                delete = st.form_submit_button("删除报告收藏")
            if delete:
                check_action("customer_save")
                if not confirmed:
                    raise CustomerError("请先勾选确认删除报告收藏。")
                service.delete_report(token,rid)
                _notify("报告收藏已删除，已保存的排盘不受影响。")
    with st.expander("收藏以前下载的报告"):
        st.caption("支持HTML、TXT，单个上传文件最多2MB。请核对报告与关联排盘是否对应；HTML仅提取文字预览，不在网页内执行脚本。")
        with st.form("customer_report_upload", clear_on_submit=True):
            upload = st.file_uploader("选择报告文件",type=["html","htm","txt"],max_upload_size=2,key="customer_report_upload_file")
            title = st.text_input("报告收藏名称",value="历史报告",max_chars=80)
            note = st.text_area("历史报告备注（选填）",max_chars=300)
            chart_id = _chart_choice(service.list_charts(token),key="customer_upload_chart")
            confirmed = st.checkbox("确认报告与所选排盘对应，并同意保存报告内容")
            submit = st.form_submit_button("收藏上传的报告",type="primary",use_container_width=True)
        if submit:
            check_action("customer_save")
            if not upload or not confirmed:
                raise CustomerError("请先选择报告文件，并勾选确认保存。")
            raw = upload.getvalue()
            if not raw or len(raw)>2*1024*1024:
                raise CustomerError("上传报告不能为空，且不能超过2MB。")
            ext = Path(upload.name).suffix.lower()
            if ext not in (".html",".htm",".txt"):
                raise CustomerError("请选择HTML或TXT报告。")
            readable_report(raw,html=ext!=".txt")
            service.save_report(token,title,note,chart_id,Path(upload.name).stem,{"txt" if ext==".txt" else "html":raw})
            _notify("历史报告已加入收藏。")
