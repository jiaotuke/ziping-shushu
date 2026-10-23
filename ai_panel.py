"""Provider and model controls; credentials stay in local configuration/session."""

from __future__ import annotations

import os

import streamlit as st

from ai_analysis import (
    AIError, PROVIDERS, STEP_TITLES, build_context, check_connection, context_signature, generate_report,
    requires_thinking, prepare_context, CitationError,
)


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
    st.caption("选择平台和模型 · 固定八步分析 · 原文引用校验")
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
    scopes = ["原局解读", "原局＋当前大运、流年"] if has_transit else ["原局解读"]
    if has_transit and "流月" in selected_transit and "流日" in selected_transit:
        scopes.append("原局＋当前运年、流月、流日")
    if st.session_state.get("ai_analysis_scope") not in scopes:
        st.session_state["ai_analysis_scope"] = scopes[0]
    analysis_scope = st.radio("解读范围", scopes, horizontal=True, key="ai_analysis_scope")
    transit = dict(selected_transit) if has_transit and analysis_scope != "原局解读" else None
    if transit and analysis_scope == "原局＋当前大运、流年":
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
            st.caption("当前解读范围仅包含运年；如需月日，选择‘原局＋当前运年、流月、流日’。")
    try:
        context = build_context(chart, retrieval, transit=transit)
        context = prepare_context(context, provider=provider, model=model, thinking=thinking, custom_window=custom_window)
    except (AIError, ValueError, OSError) as error:
        st.error(f"资料准备失败：{error}")
        return
    signature = context_signature(context, provider=provider, model=model, thinking=thinking)
    previous = st.session_state.get("glm_analysis")
    if previous and previous.get("signature") != signature:
        st.session_state.pop("glm_analysis", None)
    failed = st.session_state.get("ai_failed_citations")
    if failed and failed.get("signature") != signature:
        st.session_state.pop("ai_failed_citations", None)

    budget = context["context_budget"]
    with st.expander("上下文与资料范围"):
        a, b, c = st.columns(3)
        a.metric("模型窗口", f"{budget['window']:,}")
        b.metric("输入保守估算", f"{budget['input_estimate']:,}")
        c.metric("思考与报告预留", f"{budget['output_reserved']:,}")
        st.caption(f"{budget['count_method']}；另留 {budget['safety_reserved']:,} Tokens 安全余量。实际用量以接口返回为准。")
        st.write("《子平真诠》全文保留；按书名、篇章组织资料，引用使用短编号。")
        st.write("；".join(f"{book}：{count} 段" for book, count in budget["book_counts"].items()))
        st.caption("每次生成独立发送当前资料，不附带此前报告或聊天历史。")
        if budget["omitted_paragraphs"]:
            st.warning(f"受窗口预算限制，本次省略其他古籍的 {budget['omitted_paragraphs']} 个完整段落；未截断段落或《子平真诠》。")

    st.write("分析依据：《子平真诠》全文与所附评注，以及本次检索到的其他古籍原文。")
    scope_caption = "同时发送当前选定岁运、起运资料及干支关系；只解释此范围。" if transit else "本次仅分析原局，不发送岁运资料。"
    if transit and "流月" in transit:
        scope_caption = "同时发送当前选定运年、流月、流日、起运资料及干支关系；只解释此范围。"
    st.caption(f"当前选择：{platform['name']} / {model or '请填写模型 ID'}。点击生成后，会把当前四柱、十神、干支关系和古籍资料发送至{platform['name']}。{scope_caption}")
    if context["missing_support_books"]:
        st.caption("本次未取得可引用的相关正文：" + "、".join(context["missing_support_books"]))
    if not api_key:
        st.info("请先在上方填写 API Key，或按项目文档配置本地密钥。")
    generate_clicked = st.button("重新生成 AI 解读" if st.session_state.get("glm_analysis") else "生成 AI 解读",
                                  type="primary", disabled=not bool(api_key and model), key="glm_generate_report")
    failed = st.session_state.get("ai_failed_citations")
    repair_clicked = False
    if failed:
        st.warning("上次报告未通过引用检查，尚未作为正式报告展示。")
        labels = {"missing_citation": "缺少原文引用", "unknown_source_id": "引用编号不存在",
                  "quote_not_in_source": "摘录不是该段原文的连续文字"}
        with st.expander("查看失败位置与原因", expanded=True):
            for issue in failed["issues"]:
                st.write(f"第{issue['step']}步 · {labels.get(issue['issue'], issue['issue'])} · 编号：{issue['source_id'] or '未填写'}")
                if issue["quote"]:
                    st.text(issue["quote"])
        repair_clicked = st.button("修正引用并重新校验", disabled=not bool(api_key and model), key="ai_repair_citations",
                                   help="将上次报告、问题及原始资料发送至当前模型，会产生一次新的 API 调用及对应费用。")
        st.caption("修正按钮会再调用一次当前模型，不自动重试。编造的摘录不会直接放行。")
    error_slot = st.empty()
    if generate_clicked or repair_clicked:
        # A failed new request must not leave an older report looking like the new result.
        st.session_state.pop("glm_analysis", None)
        try:
            with st.spinner("正在阅读全文并按八步分析，可能需要一至三分钟……"):
                result = generate_report(api_key, context, provider=provider, model=model, thinking=thinking,
                                         custom_window=custom_window,
                                         repair_report=failed["report"] if repair_clicked else None,
                                         repair_issues=failed["issues"] if repair_clicked else None)
            st.session_state["glm_analysis"] = {"signature": signature, "result": result}
            st.session_state.pop("ai_failed_citations", None)
            st.rerun()
        except CitationError as error:
            st.session_state["ai_failed_citations"] = {"signature": signature, "report": error.report,
                                                       "issues": error.issues}
            st.rerun()
        except AIError as error:
            error_slot.error(str(error))

    analysis = st.session_state.get("glm_analysis")
    if not analysis:
        return
    result = analysis["result"]
    from report_downloads import render_report_downloads
    render_report_downloads(result, context["sources"], key="self_" + signature[:16])
    st.caption(f"本报告模型：{PROVIDERS.get(result.get('provider'), platform)['name']} / {result.get('model', model)}")
    report = result["report"]
    sources = {source["source_id"]: source for source in context["sources"]}
    st.caption("引用 ID 与摘录已逐字检查；规则是否适用仍需结合原文核对。")
    if result.get("citation_changes"):
        with st.expander("引用格式核定记录"):
            for change in result["citation_changes"]:
                st.write(change)
    st.markdown(report["summary"])
    for title, step in zip(STEP_TITLES, report["steps"]):
        st.markdown(f"### {step['step']}. {title}")
        st.write(step["conclusion"])
        if step["chart_evidence"]:
            st.markdown("**命盘依据**")
            for evidence in step["chart_evidence"]:
                st.write("• " + evidence)
        if step["citations"]:
            with st.expander("查看原文依据"):
                for citation in step["citations"]:
                    source = sources[citation["source_id"]]
                    st.caption(f"《{source['book_name']}》· {source['chapter']} · 原文第 {source['line_number']} 行")
                    st.text(citation["quote"])
        for uncertainty in step["uncertainties"]:
            st.caption("待核：" + uncertainty)
    if report["limitations"]:
        st.markdown("**本次局限**")
        for limitation in report["limitations"]:
            st.write("• " + limitation)
    usage = result.get("usage", {})
    if isinstance(usage, dict) and isinstance(usage.get("total_tokens"), int):
        st.caption(f"本次接口报告用量：{usage['total_tokens']} Tokens")
        if isinstance(usage.get("prompt_tokens"), int) and isinstance(usage.get("completion_tokens"), int):
            st.caption(f"实际输入 {usage['prompt_tokens']:,} Tokens；实际输出用量（含平台计入的思考）{usage['completion_tokens']:,} Tokens。")
