"""Small local v7 UI: basis first, then repeatable independent date appendices."""
from datetime import datetime
import json

import streamlit as st
from ai_analysis import AIError, PROVIDERS, build_context, prepare_context
from analysis_workflow import (advance_basis, advance_date, assemble_report, calendar_plan,
                               date_key, next_basis_stage, next_date_stage, workspace_key)
from luck_analysis import report_cycles
from period_selection import render_period_selector, period_scope, render_analysis_level, PERIOD_LABELS
from referral_common import PERIOD_FEE
from public_security import PublicSecurityError, generation_slot
from report_import import birth_profile, chart_identity


def _pause(key):
    st.session_state[key] = False


def _failure(job, error, settings):
    job.setdefault("stage", {})["status"] = "failed"
    job["last_error"] = {"time": datetime.now().astimezone().isoformat(timespec="seconds"),
                         "provider": settings["provider"], "model": settings["model"],
                         "stage": dict(job["stage"]), "message": str(error)}
    job["_admitted"] = False


def _error(job):
    if error := job.get("last_error"):
        st.error("上次暂停于：" + error["stage"].get("label", "当前阶段") + "。" + error["message"])
        with st.expander("查看中断记录"):
            st.json(error)
    if draft := job.get("pending_draft"):
        st.caption("未通过校验的本段草稿已保留；继续时优先修复本段，已完成阶段不重做。")
        st.download_button("下载待修正草稿", json.dumps(draft, ensure_ascii=False, indent=2),
                           file_name="子平术数-待修正草稿.json", key="v7_draft_"+str(id(job)))


def _report(result, sources, key):
    from beginner_report import render_reading_edition
    from report_downloads import render_report_downloads
    sources = list({s['source_id']:s for s in [*sources,*result.get('additional_sources',[])]}.values())
    edition = render_reading_edition(result["report"], sources, key=key, example=bool(result.get("example")))
    imported = result.get("imported_basis", {})
    if imported.get("mode") == "narrative":
        with st.expander("查看本次复用的历史基础报告原文"):
            st.text(imported["text"])
    render_report_downloads(result, sources, key=key, edition=edition)
    if result.get('retrieval_trace'):
        with st.expander("查看《千里命稿》各阶段／各年检索记录"):
            st.caption("列出各阶段及运内各年实际提供的原文编号；未找到条文或因预算省略会单独标明，命中不代表适用条件成立。")
            st.json(result['retrieval_trace'])
    with st.expander("报告模型与用量"):
        st.caption(PROVIDERS.get(result.get("provider"), {"name": "导入报告"})["name"] + " / " + str(result.get("model", "历史报告")))
        usage = result.get("usage", {})
        st.write("本报告已保存阶段的接口用量：", usage)
        st.caption("不含失败请求或未取得完整响应的用量，费用以模型平台账单为准。")
        if result.get("imported_basis"):
            st.caption("历史报告的用量未计入本次新增用量。旧文本引用只作历史资料，不能当作已重新核验的古籍证据。")


def render_workflow(chart, retrieval, *, api_key, provider, model, thinking, custom_window):
    if not retrieval or not retrieval.get("success"):
        st.info("先完成古籍检索，再生成报告。")
        return
    labels = ["原局解读", "原局＋大运", "原局＋大运＋指定年月日详解"]
    scope = st.radio("解读范围", labels, horizontal=True, key="v7_scope")
    include_luck = scope != labels[0]
    settings = dict(provider=provider, model=model, thinking=thinking, custom_window=custom_window, opener=None)
    try:
        context = prepare_context(build_context(chart, retrieval), provider=provider, model=model,
                                  thinking=thinking, custom_window=custom_window)
        plan = calendar_plan(chart) if include_luck else None
    except (AIError, ValueError, KeyError, OSError) as error:
        st.error("资料准备失败：" + str(error))
        return
    identity = workspace_key(context, chart, provider=provider, model=model, thinking=thinking)
    workspace = st.session_state.setdefault("v7_workspaces", {}).setdefault(identity, {"cycles": {}, "dates": {}})
    workspace["chart_identity"] = chart_identity(chart)
    workspace["birth_profile"] = birth_profile(chart)
    if scope == labels[2]:
        from report_import_panel import render_basis_import
        identity, workspace = render_basis_import(identity, chart=chart, context=context, plan=plan)
    auto_key = "v7_basis_auto_" + identity
    active_identity = (identity, scope)
    if st.session_state.get("v7_active_scope") != active_identity:
        for flag in list(st.session_state):
            if flag.startswith(("v7_basis_auto_", "v7_date_auto_")):
                st.session_state[flag] = False
        st.session_state["v7_active_scope"] = active_identity
    pending = next_basis_stage(workspace, plan)
    total = 1 + (len(report_cycles(plan)) if plan else 0)
    done = int("base" in workspace) + (sum(c["id"] in workspace["cycles"] for c in report_cycles(plan)) if plan else 0)
    st.markdown("#### 第一步 · 基础报告")
    st.caption("原局先生成，大运逐步保存；包含运内逐年趋势、评分与子平K线，不默认展开指定某一年或月日的专项详解。")
    imported = workspace.get("imported_basis")
    if imported:
        st.success("已有报告已导入，可直接选择下方大运年月日，无需重新完成基础分析。")
        st.caption(f"已识别 {imported['matched_cycles']} 步大运范围；已有分析直接复用，未覆盖的大运以历法事实作为背景，本次不另行生成大运报告。")
        for warning in imported.get("warnings", []):
            st.caption(warning)
    else:
        st.progress(done/total, text=f"已保存 {done}/{total} 个基础阶段")
    with st.expander("古籍范围与上下文预算"):
        budget = context["context_budget"]
        st.write(f"窗口 {budget['window']:,}；输入保守估算 {budget['input_estimate']:,}；报告预留 {budget['output_reserved']:,} Tokens。")
        st.caption("《子平真诠》全文保留，其他书按检索结果提供完整段落；估算不是实际Token账单。")
    _error(workspace)
    if pending:
        st.write("下一阶段：" + pending[1])
        if st.session_state.get(auto_key):
            st.button("暂停后续阶段", key="v7_basis_pause", on_click=_pause, args=(auto_key,))
        elif st.button("完成基础报告", disabled=not bool(api_key and model), key="v7_basis_all", type="primary"):
            st.session_state[auto_key] = True
        st.caption("暂停在当前模型请求结束后生效；已提交请求仍可能计费。每完成一段即保存，可稍后继续。")
    else:
        st.session_state[auto_key] = False
        if not imported:
            st.success("基础报告已完成，可下载保存。")
    baseline = assemble_report(workspace, plan=plan)
    if baseline:
        with st.expander("查看基础报告", expanded=not bool(pending)):
            if imported and imported.get("mode") == "narrative":
                from report_downloads import report_filename
                st.text(imported["text"])
                st.download_button("下载导入报告原文TXT", imported["text"].encode('utf-8-sig'),
                                   file_name=report_filename(baseline["report"])+"-导入原文.txt", key="v7_import_text_"+identity)
                st.caption("旧版HTML/TXT的交互图表不在文字模式中重建，原有分析保留为基线。")
            else:
                _report(baseline, context["sources"], "v7_basis_"+identity[:16]+("_luck" if plan else "_natal"))
    date_task = None
    if scope == labels[2]:
        st.markdown("#### 第二步 · 年／月／日专项详解")
        st.caption("选择仅分析年、月或日，每次只生成所选层级；大运和上层时间作为背景，不额外生成其他层级报告。自备模型只按平台Token计费，不收取人工解读的"+PERIOD_FEE+"元/项服务费。")
        if pending:
            st.info("先完成原局与大运基础报告，再追加指定日期；切换日期不会重算基础报告。")
        else:
            date_auto = "v7_date_auto_"+identity
            level = render_analysis_level(key="self_v7_level", disabled=bool(st.session_state.get(date_auto)))
            transit, error = render_period_selector(chart, key="self_v7", level=level, disabled=bool(st.session_state.get(date_auto)))
            if error:
                st.info(error)
            elif transit:
                st.caption(period_scope(transit))
                token = date_key(transit, level)
                date_job = workspace["dates"].setdefault(token, {"parts": {}, "transit": transit, "levels": [level]})
                remaining = next_date_stage(date_job)
                st.progress(0.0 if remaining else 1.0, text="本次仅分析"+PERIOD_LABELS[level]+("：尚未完成" if remaining else "：已完成"))
                _error(date_job)
                if remaining:
                    if st.session_state.get(date_auto):
                        st.button("暂停后续生成", key="v7_date_pause", on_click=_pause, args=(date_auto,))
                    elif st.button("生成本次流"+PERIOD_LABELS[level]+"详解", disabled=not bool(api_key and model), key="v7_date_all", type="primary"):
                        st.session_state[date_auto] = True
                    if st.session_state.get(date_auto):
                        date_task = (date_job, transit, date_auto)
                else:
                    st.session_state[date_auto] = False
                    st.success("该范围的所选专项已完成，无需再次调用模型；可切换范围或年、月、日专项继续分析。")
                available = {k: job for k, job in workspace["dates"].items() if job.get("parts")}
                if available:
                    selected = st.selectbox("已保存的日期报告", list(available),
                        index=list(available).index(token) if token in available else len(available)-1,
                        format_func=lambda k: "／".join(PERIOD_LABELS[v] for v in available[k].get("levels", ("annual", "monthly", "daily")))+" · "+period_scope(available[k]["transit"])+f" · 已保存{len(available[k]['parts'])}项", key="v7_date_history_"+identity+"_"+token+"_"+str(len(available)))
                    _report(assemble_report(workspace, plan=plan, date_job=available[selected]), context["sources"],
                            "v7_date_"+identity[:12]+"_"+selected[:12])
    st.caption("当前会话保留基础进度和多个日期报告；请及时下载。关闭会话或重启服务可能清除会话进度。")
    active = pending and st.session_state.get(auto_key)
    if active or date_task:
        target, run_key = (workspace, auto_key) if active else (date_task[0], date_task[2])
        try:
            with generation_slot("report", rate_action=not target.get("_admitted", False)):
                target["_admitted"] = True
                with st.spinner("正在生成并校验当前阶段；结束后立即保存…"):
                    if active:
                        advance_basis(api_key, context, workspace, plan=plan, **settings)
                    else:
                        advance_date(api_key, context, workspace, target, transit=date_task[1], plan=plan, **settings)
        except (AIError, PublicSecurityError) as error:
            _failure(target, error, settings)
            st.session_state[run_key] = False
        st.rerun()
