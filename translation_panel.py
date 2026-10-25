"""An independent AI translation entry in each book's translation tab."""

from __future__ import annotations

import hashlib
import html
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st
from public_security import generation_slot, PublicSecurityError

from ai_analysis import AIError, PROVIDERS, api_key_widget_key
from ai_panel import configured_api_key
from book_translation import generate_translation, load_translation, source_plan


def _remember_key(widget: str, provider: str) -> None:
    st.session_state.setdefault("_ai_keys", {})[provider] = st.session_state.get(widget, "").strip()


def _display(record: dict, book_name: str, plan: dict, prefix: str) -> None:
    st.markdown("#### 白话译文")
    name = PROVIDERS.get(record.get("provider"), {}).get("name", record.get("provider", ""))
    st.caption(f"AI 辅助译文 · {name} / {record.get('model', '')} · 未经人工校订")
    created = record.get("created_at")
    if created:
        try:
            when = datetime.fromisoformat(created).astimezone(ZoneInfo("Asia/Shanghai"))
            st.caption(f"保存于 {when:%Y-%m-%d %H:%M}（北京时间）· 对应当前原文")
        except (ValueError, TypeError):
            pass
    paragraphs = {}
    notes = []
    for part in record["parts"]:
        paragraphs.setdefault(part["paragraph"], []).append(part["translation"])
        notes.extend(part["uncertainties"])
    text = "\n\n".join("\n".join(parts) for parts in paragraphs.values())
    st.markdown("<div class='source-reading'>" + "".join(
        "<p class='source-reading-line'>" + html.escape("\n".join(parts)).replace("\n", "<br>") + "</p>"
        for parts in paragraphs.values()) + "</div>", unsafe_allow_html=True)
    if notes:
        with st.expander("翻译中的待核词句"):
            for note in dict.fromkeys(notes):
                st.write(note)
    st.download_button("下载本篇 AI 译文", data=f"《{book_name}》· {plan['chapter']}\nAI辅助译文，未经人工校订\n\n{text}\n",
                       file_name=f"{book_name}-{plan['key'][:8]}-AI译文.txt", mime="text/plain; charset=utf-8",
                       key=prefix + "_download_" + plan["key"])
    usage = record.get("usage", {})
    if type(usage.get("total_tokens")) is int:
        st.caption(f"本次生成的成功请求合计用量：{usage['total_tokens']:,} Tokens（接口返回值，含平台计入的思考用量）。")


def render_translation_panel(book_name: str, book_results: list[dict]) -> None:
    st.markdown("### AI 译文")
    st.caption("把检索到的古文转为白话 · 保留干支、术语与条件 · 无需先生成八字解读")
    if not book_results:
        st.info("请先检索到本书原文，再生成对应译文。")
        return
    prefix = "translation_" + hashlib.sha256(book_name.encode()).hexdigest()[:10]
    selected = 0
    if len(book_results) > 1:
        source_key = prefix + "_source"
        if st.session_state.get(source_key) not in range(len(book_results)):
            st.session_state[source_key] = 0
        selected = st.selectbox("选择要翻译的原文", list(range(len(book_results))), key=source_key,
                                format_func=lambda i: f"原文 {i + 1} · {book_results[i]['metadata'].get('retrieval_part', '')} {book_results[i]['metadata'].get('chapter', '')}")
    result = book_results[selected]
    try:
        plan = source_plan(book_name, result)
        saved = load_translation(plan)
    except AIError as error:
        st.error(str(error))
        return
    metadata = result.get("metadata", {})
    with st.container(border=True):
        st.markdown(f"**《{book_name}》· {plan['chapter']}**")
        a, b = st.columns(2)
        a.metric("原文范围", f"原文 {selected + 1}")
        b.metric("原文字符数", f"{plan['characters']:,}")
        st.caption(f"对应原文位置：第 {metadata.get('line_number', '—')} 行。长文按原有段落分批翻译。")
        with st.expander("查看本次待译原文"):
            st.text(str(result["document"]))

    with st.expander("翻译模型设置", expanded=not bool(saved)):
        platform_key = prefix + "_provider"
        if st.session_state.get(platform_key) not in PROVIDERS:
            st.session_state[platform_key] = st.session_state.get("ai_provider", "zhipu")
            if st.session_state[platform_key] not in PROVIDERS:
                st.session_state[platform_key] = "zhipu"
        left, right = st.columns([1, 2])
        with left:
            provider = st.selectbox("翻译平台", list(PROVIDERS), key=platform_key, format_func=lambda x: PROVIDERS[x]["name"])
        platform = PROVIDERS[provider]
        options = [*platform["models"], "custom"]
        model_key = prefix + "_model_" + provider
        if st.session_state.get(model_key) not in options:
            preferred = st.session_state.get("_ai_models", {}).get(provider)
            st.session_state[model_key] = preferred if preferred in options else options[0]
        with right:
            choice = st.selectbox("翻译模型", options, key=model_key,
                                  format_func=lambda x: "自定义模型 ID" if x == "custom" else platform["models"][x])
        custom_window = None
        if choice == "custom":
            model = st.text_input("翻译模型 ID", key=prefix + "_custom_" + provider,
                                  value=st.session_state.get("_ai_custom_models", {}).get(provider, "")).strip()
            custom_window = int(st.number_input("模型上下文窗口（Tokens）", min_value=8192, max_value=2000000,
                                                value=32768, step=1024, key=prefix + "_window_" + provider))
        else:
            model = choice
        if provider == "zhipu" and model == "glm-4.7-flash":
            st.caption("免费模型仍受平台速率与可用性限制；失败后可手动重试或更换模型。")
        elif provider == "inkstone":
            st.caption("使用端砚对应模型的默认推理设置；墨点价格与周期额度以平台为准。")
        else:
            st.caption("所选模型可能按量计费，价格与额度以对应平台为准。")
        session_key = st.session_state.get("_ai_keys", {}).get(provider, "")
        if not session_key:
            session_key = st.session_state.get(api_key_widget_key(provider), "")
        local_key = configured_api_key(provider)
        credential_widget = prefix + "_key_" + provider
        entered = st.text_input(f"{platform['name']} API Key", type="password", value=session_key,
                                key=credential_widget, max_chars=256, on_change=_remember_key, args=(credential_widget, provider),
                                help="可复用 AI 解读中的对应平台密钥；也可直接在这里填写，无需先生成解读。")
        api_key = entered.strip() or session_key or local_key
        if api_key:
            st.caption("已取得对应平台密钥；仅点击生成按钮时发送待译古文。")
        else:
            st.caption("填写对应平台密钥后即可生成译文；已保存的译文无需密钥即可阅读。")

    try:
        draft = load_translation(plan, provider=provider, model=model)
    except AIError as error:
        st.error(str(error))
        return
    if saved:
        st.success("本篇已有保存的 AI 译文，可直接阅读。")
    elif draft:
        st.info(f"已保存 {len(draft['parts'])}/{len(plan['pieces'])} 个原文片段，可继续生成剩余部分。")
    else:
        st.info("本篇尚未生成 AI 译文。点击下方按钮开始翻译，完成后自动保存在项目本地。")
    label = "重新生成 AI 译文" if saved else "继续生成 AI 译文" if draft else "生成 AI 译文"
    st.caption(f"点击后向{platform['name']}发送本篇原文；不附带出生资料、命盘或此前解读。切换书籍、模型或页签不会自动调用。")
    if st.button(label, type="primary", disabled=not bool(api_key and model), key=prefix + "_generate_" + plan["key"]):
        progress = st.progress(0, text="正在准备逐段翻译……")
        try:
            with generation_slot("translation"), st.spinner("正在翻译本篇原文，长文可能需要多批请求……"):
                saved = generate_translation(api_key, plan, provider=provider, model=model, custom_window=custom_window,
                                             regenerate=bool(saved), progress=lambda done, total: progress.progress(done / total, text=f"已完成 {done}/{total} 个片段"))
            st.success("AI 译文已生成并保存。")
        except (AIError, PublicSecurityError) as error:
            st.error(str(error))
        except OSError:
            st.error("本地译文保存失败，请检查项目目录的可写空间；已保存的旧译文仍可阅读。")
        finally:
            progress.empty()
    if saved:
        _display(saved, book_name, plan, prefix)
