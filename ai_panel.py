"""Provider and model controls; credentials stay in local configuration/session."""

from __future__ import annotations

import os

import streamlit as st
from public_security import generation_slot, PublicSecurityError

from ai_analysis import (
    AIError, PROVIDERS, check_connection, requires_thinking, api_key_widget_key,
)


def configured_api_key(provider: str = "zhipu") -> str:
    if os.environ.get("ZIPING_PUBLIC_SITE") == "1":
        # The public deployment only accepts this visitor's own key. Never
        # fall back to an operator environment/secrets key for public users.
        return ""
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
    st.markdown("**国学教育，仅供娱乐**")
    method = st.radio("解读方式", ["付费解读", "自备模型"], horizontal=True,
                      key="ai_service_mode_preview" if preview_only else "ai_service_mode")
    if method == "付费解读":
        import paid_analysis_panel
        paid_analysis_panel.render_paid_panel(chart, retrieval, transit=preview_transit, preview_only=preview_only)
        return
    if preview_only:
        st.caption("使用自己的模型账户，Token 费用由模型平台结算。")
        with st.container(border=True):
            st.selectbox("模型平台", [platform["name"] for platform in PROVIDERS.values()], key="self_preview_provider")
            st.text_input("API Key", type="password", disabled=True, placeholder="在实际解读页面填写自己的密钥", key="self_preview_key")
            st.button("生成 AI 解读", disabled=True, key="self_preview_generate")
        st.info("当前为独立界面预览。返回排盘页面后，可使用已有的自备模型解读功能。")
        st.markdown("#### 指定年月日选择预览")
        st.caption("与付费解读使用同一套选择器。实际使用时先完成或导入基础报告，再仅生成所选年、月或日专项。")
        from period_selection import render_period_selector, render_analysis_level
        level = render_analysis_level(key="self_v7_preview_level")
        render_period_selector(chart, key="self_v7_preview", seed=preview_transit, level=level)
        return
    st.caption("第七版 · 先看原局与大运，再逐次追加年月日详解")
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
            st.caption("自定义模型需支持 Chat Completions、足够长的上下文和 JSON 正文；是否可调用以平台权限为准。")
        else:
            model = choice
        if provider == "inkstone":
            thinking = False
            st.caption("推理方式使用端砚对应模型的默认设置；不发送其他平台的深度思考参数。")
        elif requires_thinking(provider, model):
            st.toggle("深度思考", value=True, disabled=True, key="ai_required_thinking")
            thinking = True
            st.caption("此模型必须开启思考。报告使用增强推理；连接检查使用轻量推理，等待时间和费用以实际用量为准。")
        else:
            thinking = st.toggle("深度思考", value=True, key="ai_thinking",
                                 help="开启后可能需要更长等待时间，并增加按量计费模型的用量。")
        if provider == "zhipu" and model == "glm-4.7-flash":
            st.caption("GLM-4.7-Flash 免费，仍受平台速率及服务可用性限制。")
        elif provider == "inkstone":
            st.caption("消耗端砚账户额度；限时免费、墨点价格和周期限额以平台实时页面为准。")
        else:
            st.caption("此选择可能按量计费。点击检查连接或生成前，请在对应平台确认价格、余额和模型权限。")

    saved_key = configured_api_key(provider)
    session_keys = st.session_state.setdefault("_ai_keys", {})
    # Keep credentials across provider switches even when Streamlit removes hidden widgets.
    stored_key = session_keys.get(provider, st.session_state.get(api_key_widget_key(provider), ""))
    with st.expander("模型连接设置", expanded=not bool(saved_key or stored_key)):
        st.markdown(f"在 [{platform['name']}控制台]({platform['console']}) 创建 API Key。不同平台的密钥分别填写。")
        entered_key = st.text_input(f"{platform['name']} API Key", type="password",
                                    value=stored_key, max_chars=256, key=api_key_widget_key(provider),
                                    help="只保留在当前网页会话中；也可通过项目本地 secrets.toml 配置。")
        if provider == "inkstone":
            st.caption("API 地址已设置：https://discovery-api.intern-ai.org.cn/v1；请选择端砚模型列表中的生成模型。")
            st.markdown(f"[查看端砚使用文档]({platform['docs']})")
        session_keys[provider] = entered_key.strip()
        api_key = entered_key.strip() or saved_key
        if saved_key and not entered_key:
            st.caption("已读取本地 API Key 配置。")
        if st.button("检查密钥与模型" if provider == "inkstone" else "检查连接", disabled=not bool(api_key and model), key="glm_check_connection"):
            try:
                with generation_slot("connection"), st.spinner(f"正在检查 {platform['name']} / {model} 连接……"):
                    check_connection(api_key, provider=provider, model=model)
                if provider == "inkstone":
                    st.success(f"{platform['name']}密钥有效，模型 {model} 在可用列表中。报告生成效果以实际返回为准。")
                else:
                    st.success(f"{platform['name']} / {model} 连接正常，可以生成解读。")
            except (AIError, PublicSecurityError) as error:
                st.error(str(error))
        if provider == "inkstone":
            st.caption("检查只读取可用模型列表，按端砚文档不扣墨点；不发送排盘或古籍内容。无需将密钥发到聊天中。")
        else:
            st.caption("连接检查只发送测试短句；GLM-5.3 系列仍会产生必要的思考用量。无需将密钥发到聊天中。")

    from analysis_workflow_panel import render_workflow
    render_workflow(chart, retrieval, api_key=api_key, provider=provider, model=model,
                    thinking=thinking, custom_window=custom_window)
