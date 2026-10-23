"""Provider and model controls; credentials stay in local configuration/session."""

from __future__ import annotations

import os
import json
from datetime import datetime

import streamlit as st

from ai_analysis import (
    AIError, PROVIDERS, build_context, check_connection, context_signature, generate_report,
    requires_thinking, prepare_context, CitationError, compatible_report_signatures,
)


def _remember_failure(job: dict, error: AIError, *, provider: str, model: str) -> None:
    """Keep safe diagnostics in this session; never store credentials or request bodies."""
    stage = job.setdefault("stage", {"id": "unknown", "label": "准备报告"})
    stage["status"] = "failed"
    job["last_error"] = {
        "time": datetime.now().astimezone().isoformat(timespec="seconds"),
        "provider": provider, "model": model, "stage": dict(stage),
        "kind": getattr(error, "kind", "request"), "message": str(error),
    }


def configured_api_key(provider: str = "zhipu") -> str:
    key_env = PROVIDERS[provider]["key_env"]
    configured = os.environ.get(key_env, "").strip()
    if configured:
        return configured
    try:
        value = st.secrets.get(key_env, "")
        return value.strip() if isinstance(value, str) else ""
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        return ""


def render_ai_panel(chart: dict, retrieval: dict, *, preview_only: bool = False, preview_transit: dict | None = None) -> None:
    st.subheader("AI 解读")
    method = st.radio("解读方式", ["付费解读", "自备模型"], horizontal=True,
                      key="ai_service_mode_preview" if preview_only else "ai_service_mode")
    if method == "付费解读":
        import importlib
        import paid_analysis_panel

        paid_analysis_panel = importlib.reload(paid_analysis_panel)
        paid_analysis_panel.render_paid_panel(chart, retrieval, transit=preview_transit, preview_only=preview_only)
        return
    if preview_only:
        st.caption("使用自己的模型账户，Token 费用由模型平台结算。")
        with st.container(border=True):
            st.selectbox("模型平台", ["智谱", "DeepSeek"], key="self_preview_provider")
            st.text_input("API Key", type="password", disabled=True, placeholder="在实际解读页面填写自己的密钥", key="self_preview_key")
            st.button("生成 AI 解读", disabled=True, key="self_preview_generate")
        st.info("当前为独立界面预览。返回排盘页面后，可使用已有的自备模型解读功能。")
        return
    st.caption("第五版 · 白话概览在前 · 点击子平 K 线看分项 · 推导依据可展开")
    custom_window = None
    with st.container(border=True):
        col_platform, col_model = st.columns([1, 2])
        with col_platform:
            provider = st.selectbox("模型平台", list(PROVIDERS),
                                    format_func=lambda p: PROVIDERS[p]["name"], key="ai_provider")
        platform = PROVIDERS[provider]
        model_options = [*platform["models"], "custom"]
        remembered_models = st.session_state.setdefault("_ai_models", {})
        previous_model = remembered_models.get(provider, model_options[0])
        with col_model:
            choice = st.selectbox("选择模型", model_options,
                                  index=model_options.index(previous_model) if previous_model in model_options else 0,
                                  format_func=lambda m: "自定义模型 ID" if m == "custom" else platform["models"][m],
                                  key=f"ai_model_{provider}")
        remembered_models[provider] = choice
        if choice == "custom":
            custom_models = st.session_state.setdefault("_ai_custom_models", {})
            model = st.text_input("模型 ID", value=custom_models.get(provider, ""),
                                  placeholder="填写该平台官方文档中的模型 ID", key=f"ai_custom_{provider}").strip()
            custom_models[provider] = model
            custom_window = int(st.number_input("模型上下文窗口（Tokens）", min_value=8192, max_value=2000000,
                                                 value=32768, step=1024, key=f"ai_window_{provider}",
                                                 help="按该模型官方文档填写；增大此值不会改变模型实际能力。"))
            st.caption("自定义模型需支持长上下文、思考模式参数和 JSON 输出；是否可调用以平台权限为准。")
        else:
            model = choice
        if requires_thinking(provider, model):
            st.toggle("深度思考", value=True, disabled=True, key="ai_required_thinking")
            thinking = True
            st.caption("此模型必须开启思考。报告使用增强推理；连接检查使用轻量推理，等待时间和费用以实际用量为准。")
        else:
            thinking = st.toggle("深度思考", value=True, key="ai_thinking",
                                 help="开启后可能需要更长等待时间，并增加按量计费模型的用量。")
        if provider == "zhipu" and model == "glm-4.7-flash":
            st.caption("GLM-4.7-Flash 免费，仍受平台速率及服务可用性限制。")
        else:
            st.caption("此选择可能按量计费。点击检查连接或生成前，请在对应平台确认价格、余额和模型权限。")

    saved_key = configured_api_key(provider)
    session_keys = st.session_state.setdefault("_ai_keys", {})
    # Keep credentials across provider switches even when Streamlit removes hidden widgets.
    stored_key = session_keys.get(provider, st.session_state.get("glm_api_key", "") if provider == "zhipu" else "")
    with st.expander("模型连接设置", expanded=not bool(saved_key or stored_key)):
        st.markdown(f"在 [{platform['name']}控制台]({platform['console']}) 创建 API Key。不同平台的密钥分别填写。")
        entered_key = st.text_input(f"{platform['name']} API Key", type="password",
                                    value=stored_key, key="glm_api_key" if provider == "zhipu" else "deepseek_api_key",
                                    help="只保留在当前网页会话中；也可通过项目本地 secrets.toml 配置。")
        session_keys[provider] = entered_key.strip()
        api_key = entered_key.strip() or saved_key
        if saved_key and not entered_key:
            st.caption("已读取本地 API Key 配置。")
        if st.button("检查连接", disabled=not bool(api_key and model), key="glm_check_connection"):
            try:
                with st.spinner(f"正在检查 {platform['name']} / {model} 连接……"):
                    check_connection(api_key, provider=provider, model=model)
                st.success(f"{platform['name']} / {model} 连接正常，可以生成解读。")
            except AIError as error:
                st.error(str(error))
        st.caption("连接检查只发送测试短句；GLM-5.3 系列仍会产生必要的思考用量。无需将密钥发到聊天中。")

    if not retrieval or not retrieval.get("success"):
        st.info("请先点击‘古籍检索’，再生成解读。")
        return
    selected_transit = st.session_state.get("professional_transit")
    has_transit = isinstance(selected_transit, dict) and selected_transit.get("四柱") == chart.get("四柱")
    scopes = ["原局解读", "原局＋前六步大运、选定流年"] if has_transit else ["原局解读"]
    if has_transit and "流月" in selected_transit and "流日" in selected_transit:
        scopes.append("原局＋前六步大运、选定流年月日")
    old_scope = st.session_state.get("ai_analysis_scope")
    if isinstance(old_scope, str) and "全部大运" in old_scope:
        st.session_state["ai_analysis_scope"] = old_scope.replace("全部大运", "前六步大运")
    if st.session_state.get("ai_analysis_scope") not in scopes:
        st.session_state["ai_analysis_scope"] = scopes[0]
    analysis_scope = st.radio("解读范围", scopes, horizontal=True, key="ai_analysis_scope")
    transit = dict(selected_transit) if has_transit and analysis_scope != "原局解读" else None
    if transit and analysis_scope == "原局＋前六步大运、选定流年":
        transit.pop("流月", None)
        transit.pop("流日", None)
    if transit:
        cycle, annual = transit["大运"], transit["流年"]
        st.caption(f"当前大运：{cycle['干支'] or '未起运'}（{cycle['起始年']}—{cycle['结束年']}）；"
                   f"流年：{annual['年份']} {annual['干支']}。在专业细盘切换后，此处同步更新。")
        if "流月" in transit:
            month, day = transit["流月"], transit["流日"]
            st.caption(f"流月：{month['名称']} {month['干支']}（{month['起始时刻']} 至 {month['结束时刻']}，不含结束时刻）；"
                       f"流日：{day['日期']} {day['干支']}。")
        else:
            st.caption("另包含起运后的前六步正式大运及子平K线；本次所选流年单独详解。")
    try:
        context = build_context(chart, retrieval, transit=transit)
        context = prepare_context(context, provider=provider, model=model, thinking=thinking, custom_window=custom_window)
    except (AIError, ValueError, OSError) as error:
        st.error(f"资料准备失败：{error}")
        return
    signature = context_signature(context, provider=provider, model=model, thinking=thinking)
    job = st.session_state.setdefault("ai_extended_job", {})
    existing = [job, st.session_state.get("glm_analysis"), st.session_state.get("ai_failed_citations")]
    if any(isinstance(entry, dict) and entry.get("signature") and entry["signature"] != signature for entry in existing):
        legacy_signatures = compatible_report_signatures(context, provider=provider, model=model, thinking=thinking, custom_window=custom_window)
        for entry in existing:
            if isinstance(entry, dict) and entry.get("signature") in legacy_signatures:
                entry["signature"] = signature
    if job.get("signature") != signature:
        job.clear()
        job.update(signature=signature)
    previous = st.session_state.get("glm_analysis")
    if previous and previous.get("signature") != signature:
        st.session_state.pop("glm_analysis", None)
    if transit and previous and previous.get("signature") == signature:
        from luck_analysis import report_cycles
        previous_cycles = previous.get("result", {}).get("report", {}).get("luck_analysis", {}).get("cycles", [])
        if len(previous_cycles) > len(report_cycles(context["luck_plan"])):
            # Reassemble the narrower report from saved stages on the next click.
            st.session_state.pop("glm_analysis", None)
    failed = st.session_state.get("ai_failed_citations")
    if failed and failed.get("signature") != signature:
        st.session_state.pop("ai_failed_citations", None)
    elif failed and transit:
        from luck_analysis import report_cycles
        failed_stage = failed.get("report", {}).get("_stage", "base")
        valid_stages = {"base", "annual", *("luck:" + c["id"] for c in report_cycles(context["luck_plan"]))}
        if "流月" in transit:
            valid_stages.update(("monthly", "daily"))
        if failed_stage not in valid_stages:
            st.session_state.pop("ai_failed_citations", None)
            job.pop("last_error", None)

    budget = context["context_budget"]
    with st.expander("上下文与资料范围"):
        a, b, c = st.columns(3)
        a.metric("模型窗口", f"{budget['window']:,}")
        b.metric("输入保守估算", f"{budget['input_estimate']:,}")
        c.metric("思考与报告预留", f"{budget['output_reserved']:,}")
        st.caption(f"{budget['count_method']}；另留 {budget['safety_reserved']:,} Tokens 安全余量。实际用量以接口返回为准。")
        st.write("《子平真诠》全文保留；按书名、篇章组织资料，引用使用短编号。")
        st.write("；".join(f"{book}：{count} 段" for book, count in budget["book_counts"].items()))
        st.caption("原局请求独立发送当前资料；逐运阶段另附本次已完成的原局基线，不携带其他命盘或聊天历史。")
        if budget["omitted_paragraphs"]:
            st.warning(f"受窗口预算限制，本次省略其他古籍的 {budget['omitted_paragraphs']} 个完整段落；未截断段落或《子平真诠》。")

    st.write("分析依据：《子平真诠》全文与所附评注，以及本次检索到的其他古籍原文。")
    st.caption("原文引用可选：有适用原文再附引用；没有时直接给出模型推演。无法对应原文的摘录会省略，缺少引用不会阻断报告。")
    scope_caption = "从起运开始分段分析前六步正式大运，再详解所选流年；包含逐运评分、子平K线及关系现实表现。" if transit else "本次仅分析原局及关系可能表现，不发送岁运资料。"
    if transit and "流月" in transit:
        scope_caption = "从起运开始分段分析前六步正式大运，再分别详解所选流年、流月、流日。"
    st.caption(f"当前选择：{platform['name']} / {model or '请填写模型 ID'}。点击生成后，会把当前四柱、十神、干支关系和古籍资料发送至{platform['name']}。{scope_caption}")
    if context["missing_support_books"]:
        st.caption("本次未取得可引用的相关正文：" + "、".join(context["missing_support_books"]))
    if not api_key:
        st.info("请先在上方填写 API Key，或按项目文档配置本地密钥。")
    if transit:
        from luck_analysis import report_cycles
        cycles = report_cycles(context["luck_plan"])
        count = len(cycles)
        stages = 1 + count + (3 if "流月" in transit else 1)
        levels = ["annual", "monthly", "daily"] if "流月" in transit else ["annual"]
        done = int("base" in job) + sum(c["id"] in job.get("cycles", {}) for c in cycles) + sum(level in job.get("selected", {}) for level in levels)
        st.info(f"本次覆盖 {count} 步正式大运，首次完整生成共 {stages} 个模型请求阶段。已完成 {done}/{stages}。"
                "格式或内容校验失败时，每段最多额外请求一次自动修正；仍失败则暂停。自动修正另计模型用量。进度仅保留在当前网页会话。")
        st.caption("评分为项目解释性指标：格局救应35%、喜忌扶抑30%、调候通关20%、结构稳定15%。"
                   "古籍没有现成百分制，证据不足不补分；K线由代码根据逐年分数绘制。")
    st.caption("已启用自动修正：每次生成或继续时，每个出错阶段最多自动修正一次，通过后继续。网络、额度和限流错误直接暂停。")
    repairs = job.get("auto_repairs", {})
    if repairs:
        with st.expander("自动修正记录"):
            statuses = {"running": "进行中或上次运行中断", "completed": "修正通过", "failed": "修正后仍未通过", "interrupted": "修正请求未完成"}
            for entry in repairs.values():
                st.write(f"{entry['label']} · 累计自动修正 {entry['attempts']} 次 · {statuses.get(entry['status'], entry['status'])}")
    failed = st.session_state.get("ai_failed_citations")
    last_error = job.get("last_error")
    if last_error:
        last_stage = last_error.get("stage", {})
        st.error(f"上次中断于：{last_stage.get('label', '报告生成')}。{last_error['message']}")
        with st.expander("本次中断记录"):
            st.json(last_error)
            st.caption("记录仅保留在当前网页会话；不包含 API Key、请求正文或报告草稿。")
    can_resume = transit and "base" in job and not st.session_state.get("glm_analysis")
    button_label = ("修正本段并继续" if failed else "继续生成完整岁运报告" if can_resume else
                    "重新生成 AI 解读" if st.session_state.get("glm_analysis") else
                    "重试本段" if last_error else "生成 AI 解读")
    generate_clicked = st.button(button_label, type="primary", disabled=not bool(api_key and model), key="glm_generate_report")
    if failed:
        structure_issue = failed.get("kind") == "structure"
        st.warning("上次生成的本段内容或格式不完整，草稿已保留，可修正本段后继续。" if structure_issue else
                   "上次未完成的草稿已保留，可按当前可选引用规则修正后继续。")
        labels = {"missing_citation": "缺少原文引用", "unknown_source_id": "引用编号不存在",
                  "quote_not_in_source": "摘录不是该段原文的连续文字", "invalid_structure": "内容或格式需补充",
                  "stage_mismatch": "报告标识或时间范围不匹配",
                  "output_truncated": "模型输出达到 Token 上限"}
        with st.expander("查看失败位置与原因", expanded=True):
            for issue in failed["issues"]:
                location = f"第{issue['step']}步" if type(issue['step']) is int else str(issue['step'])
                source_label = f" · 引用编号：{issue['source_id']}" if issue.get("source_id") else ""
                st.write(f"{location} · {labels.get(issue['issue'], issue['issue'])}{source_label}")
                if issue.get("message"):
                    st.write(issue["message"])
                if issue["quote"]:
                    st.text(issue["quote"])
        st.download_button("下载本段草稿与错误记录", data=json.dumps({"report": failed["report"], "issues": failed["issues"]}, ensure_ascii=False, indent=2).encode("utf-8"),
                           file_name="子平术数-待修正草稿.json", mime="application/json", key="ai_failed_draft_download")
        st.caption("点击上方‘修正本段并继续’，会先在本地检查保存的岁运草稿；仅编号或外层格式差异且内容完整时直接恢复，不调用模型。仍有实质缺项才请求修正，最多再自动修正一次。已完成阶段不重复请求。")
    st.caption("长报告请求的读取等待上限为 600 秒。生成期间请保持当前页面，避免切换模型、范围或专业细盘时间。")
    if generate_clicked:
        # A failed new request must not leave an older report looking like the new result.
        if generate_clicked and st.session_state.get("glm_analysis"):
            job.clear()
            job.update(signature=signature)
        st.session_state.pop("glm_analysis", None)
        job.pop("last_error", None)
        generation_progress = st.progress(0, text="正在准备分析……")
        try:
            with st.spinner("正在分段分析并检查内容，请保留此页面……"):
                result = generate_report(api_key, context, provider=provider, model=model, thinking=thinking,
                                         custom_window=custom_window,
                                         repair_report=failed["report"] if failed else None,
                                         repair_issues=failed["issues"] if failed else None,
                                         checkpoint=job, progress=lambda done, total, label: generation_progress.progress(
                                             done / total, text=f"{done}/{total} · {label}"))
            st.session_state["glm_analysis"] = {"signature": signature, "result": result}
            st.session_state.pop("ai_failed_citations", None)
            st.rerun()
        except CitationError as error:
            _remember_failure(job, error, provider=provider, model=model)
            st.session_state["ai_failed_citations"] = {"signature": signature, "report": error.report,
                                                       "issues": error.issues, "kind": getattr(error, "kind", "citation")}
            st.rerun()
        except AIError as error:
            _remember_failure(job, error, provider=provider, model=model)
            pending = job.get("pending_draft")
            if pending:
                st.session_state["ai_failed_citations"] = {"signature": signature, **pending}
            else:
                st.session_state.pop("ai_failed_citations", None)
            st.rerun()

    analysis = st.session_state.get("glm_analysis")
    if not analysis:
        return
    result = analysis["result"]
    from luck_chart import render_extended
    render_extended(result["report"], context["sources"], key="life_report_" + signature[:16])
    with st.expander("报告信息与引用核定记录", expanded=False):
        st.caption(f"本报告模型：{PROVIDERS.get(result.get('provider'), platform)['name']} / {result.get('model', model)}")
        for change in result.get("citation_changes", []):
            st.write(change)
        for change in result.get("format_changes", []):
            st.write(change)
        usage = result.get("usage", {})
        if isinstance(usage, dict) and isinstance(usage.get("total_tokens"), int):
            st.caption(f"已通过校验阶段的接口返回用量：{usage['total_tokens']} Tokens")
            if isinstance(usage.get("prompt_tokens"), int) and isinstance(usage.get("completion_tokens"), int):
                st.caption(f"实际输入 {usage['prompt_tokens']:,} Tokens；实际输出用量（含平台计入的思考）{usage['completion_tokens']:,} Tokens。")
            st.caption("统计不含未通过校验或未取得完整响应的请求；实际总用量以模型平台账单为准。")
    from report_downloads import render_report_downloads
    render_report_downloads(result, context["sources"], key="self_" + signature[:16])
