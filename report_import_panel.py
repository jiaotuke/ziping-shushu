"""Explicit import action; each imported basis keeps its own workspace."""
import hashlib
import streamlit as st
from ai_analysis import AIError
from report_import import MAX_REPORT_BYTES, import_report


def render_basis_import(identity, *, chart, context, plan):
    workspaces = st.session_state.setdefault("v7_workspaces", {})
    choice_key = "v7_import_choice_"+identity
    original = workspaces.setdefault(identity, {"cycles": {}, "dates": {}})
    selected = st.session_state.get(choice_key, identity)
    current = workspaces.get(selected, original)
    with st.expander("导入已有报告，直接追加大运年月日详解", expanded=not bool(current.get("imported_basis"))):
        st.caption("支持本程序此前下载的 JSON、HTML、TXT 报告，最大2MB。导入不调用模型；请先核对当前出生资料和性别。")
        uploaded = st.file_uploader("选择已有报告", type=["json","html","htm","txt"],
                                    max_upload_size=2, key="v7_import_file_"+identity)
        if uploaded is not None:
            confirmed = st.checkbox("确认这份报告对应当前出生资料与性别", key="v7_import_confirm_"+identity)
            if st.button("导入并复用基础报告", type="primary", disabled=not confirmed, key="v7_import_apply_"+identity):
                try:
                    if uploaded.size > MAX_REPORT_BYTES:
                        raise AIError("请选择不超过2MB的报告。")
                    raw = uploaded.getvalue()
                    new_identity = identity+"_import_"+hashlib.sha256(raw).hexdigest()
                    if new_identity not in workspaces:
                        workspaces[new_identity] = import_report(raw, uploaded.name, chart=chart, context=context, plan=plan)
                    st.session_state[choice_key] = new_identity
                    for key in list(st.session_state):
                        if key.startswith(("v7_basis_auto_", "v7_date_auto_")):
                            st.session_state[key] = False
                    st.rerun()
                except AIError as error:
                    st.error(str(error))
                except (ValueError, TypeError, KeyError, IndexError, RecursionError):
                    st.error("报告内容结构无法识别，未修改当前报告或已有进度。请使用原下载文件。")
        if current.get("imported_basis"):
            st.text("已导入："+current["imported_basis"]["filename"])
            if st.button("返回原来的基础报告", key="v7_import_leave_"+identity):
                st.session_state.pop(choice_key, None)
                st.rerun()
    return selected, current
