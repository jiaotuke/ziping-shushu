"""八字排盘与四本古籍独立检索的 Streamlit 入门网页。"""

from __future__ import annotations

import os
import json
import html
import re
import importlib
from datetime import date, datetime, time
from calendar import monthrange
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import streamlit as st

from runtime_paths import RESOURCE_ROOT as ROOT, CACHE_ROOT

PORTABLE_MODE = os.environ.get("ZIPING_PORTABLE") == "1"
BOOK_NAMES = ["穷通宝鉴", "三命通会", "子平真诠", "滴天髓"]
RETRIEVAL_VERSION = "paragraphs-qiongtong-stem-month-2"

# 模型缓存放在项目 D 盘目录，避免新下载默认进入 C 盘用户缓存。
os.environ["HF_HOME"] = str(CACHE_ROOT / "huggingface")
os.environ["SENTENCE_TRANSFORMERS_HOME"] = str(CACHE_ROOT / "sentence-transformers")
os.environ["TRANSFORMERS_CACHE"] = str(CACHE_ROOT / "transformers")

st.set_page_config(
    page_title="子平术数",
    page_icon="📜",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    .stApp {
        background: radial-gradient(ellipse at 50% 0%, #202126 0%, #0c0d10 48%, #070809 100%);
        color: #f2eee6;
    }
    .block-container { max-width: 920px; padding-top: 3.2rem; padding-bottom: 4rem; }
    .hero { text-align: center; margin: 0 auto 2.5rem; }
    .hero-rule { width: 72px; height: 1px; margin: 0 auto 1.4rem; background: #c99b55; opacity: .8; }
    .hero-title {
        color: #ead7ad; font-family: "Noto Serif CJK SC", "Songti SC", "STSong", serif;
        font-size: clamp(2rem, 5vw, 3.25rem); font-weight: 500; letter-spacing: .22em;
        text-shadow: 0 2px 24px rgba(201, 155, 85, .17); white-space: nowrap;
    }
    .hero-subtitle { color: #aaa49a; font-size: .92rem; letter-spacing: .3em; margin-top: .8rem; }
    h2, h3 { color: #ead7ad !important; font-family: "Noto Serif CJK SC", "Songti SC", "STSong", serif !important; }
    [data-testid="stWidgetLabel"] p { color: #ddd7ca; }
    div[data-baseweb="select"] > div, div[data-baseweb="input"] > div,
    div[data-baseweb="textarea"] > div { background-color: #17191d; border-color: #393a3d; }
    .stButton button[kind="primary"] { background: #b88948; color: #101010; border: 0; letter-spacing: .12em; }
    .stButton button[kind="primary"]:hover { background: #d1aa6d; color: #101010; border-color: #d1aa6d; }
    .stButton button:disabled { background: #25272b; color: #73757a; border-color: #34363a; opacity: .72; }
    hr { border-color: #33343a; }
    .pillar-card { min-height: 440px; padding: 16px 10px 14px; border: 1px solid #393a3d;
        border-radius: 12px; background: linear-gradient(180deg, rgba(30,31,35,.94), rgba(17,18,21,.96));
        text-align: center; box-shadow: 0 8px 28px rgba(0,0,0,.18); }
    .pillar-name { color: #c9b98f; font-size: .82rem; letter-spacing: .18em; margin-bottom: 12px; }
    .pillar-god { color: #b9b2a5; font-size: .76rem; min-height: 1.2em; margin-bottom: 4px; }
    .pillar-glyph { font-family: "Noto Serif CJK SC", "Songti SC", serif; font-size: 2.7rem;
        font-weight: 600; line-height: 1.15; }
    .pillar-hidden { display: grid; grid-template-rows: repeat(3, 1.75em); align-content: center;
        margin: 13px auto 14px; padding: 10px 0; border-top: 1px solid #34353a;
        color: #ddd7ca; font-size: .78rem; line-height: 1.75; }
    .pillar-hidden-row { display: grid; grid-template-columns: 1.5em 3.4em; justify-content: center;
        gap: .45em; text-align: left; white-space: nowrap; }
    .pillar-meta { text-align: left; padding-top: 9px; border-top: 1px solid #34353a;
        color: #bdb7ac; font-size: .76rem; line-height: 1.85; }
    .pillar-meta b { color: #e0d8c9; font-weight: 500; }
    .pillar-shensha { text-align: left; margin-top: 9px; padding-top: 9px; border-top: 1px solid #34353a;
        color: #e4c98f; font-size: .75rem; line-height: 1.7; }
    .source-reading { padding: 8px 4px; color: #e2ddd2; font-family: "Noto Serif CJK SC", "Songti SC", serif;
        font-size: 1rem; line-height: 2; }
    .source-chapter-title { color: #ead7ad; margin: 0 0 .7rem; font-size: 1.15rem; }
    .source-reading-line { margin: 0 0 .65rem; text-indent: 2em; }
    </style>
    <div class="hero">
      <div class="hero-rule"></div>
      <div class="hero-title">盈虚有数，宇宙无穷</div>
      <div class="hero-subtitle">-子平术数，以古籍观命理</div>
    </div>
    """,
    unsafe_allow_html=True,
)


if st.query_params.get("preview") == "paid":
    st.caption("付费咨询入口预览 · 使用演示出生资料，不覆盖实际命盘")
    if st.button("返回排盘页面", key="leave_paid_preview"):
        st.query_params.clear()
        st.rerun()
    import paid_analysis_panel as paid_preview_module
    import ai_panel as ai_preview_module

    paid_preview_module = importlib.reload(paid_preview_module)
    ai_preview_module = importlib.reload(ai_preview_module)
    preview_chart, preview_transit = paid_preview_module.preview_data()
    ai_preview_module.render_ai_panel(preview_chart, {"success": True}, preview_only=True, preview_transit=preview_transit)
    st.stop()


@st.cache_resource(show_spinner=False)
def get_retrieval_collection(collection_name: str):
    """首次检索时加载 Chroma 和向量模型，之后在本进程中复用。"""
    if PORTABLE_MODE:
        from portable_retrieval import PortableCollection
        return PortableCollection()
    from rag import get_collection

    return get_collection(collection_name)


REGION_DATA_DIR = CACHE_ROOT / "china_admin"
REGION_API = "https://geo.datav.aliyun.com/areas_v3/bound"


@st.cache_data(ttl=7 * 86400, show_spinner=False)
def load_regions(adcode: str) -> list[dict]:
    """Fetch and cache one level of China's administrative divisions on D drive."""
    REGION_DATA_DIR.mkdir(parents=True, exist_ok=True)
    cached_file = REGION_DATA_DIR / f"{adcode}_full.json"
    if cached_file.exists():
        payload = json.loads(cached_file.read_text(encoding="utf-8"))
    else:
        request = Request(
            f"{REGION_API}/{adcode}_full.json",
            headers={"User-Agent": "QiongTongBaoJian-Learning-App/0.1"},
        )
        try:
            with urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            # County-level cities such as Jiyuan have no county-level children.
            # DataV may return 404 for that missing *_full.json endpoint.
            if error.code == 404:
                return []
            raise
        cached_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    regions = []
    for feature in payload.get("features", []):
        properties = feature.get("properties") or {}
        name = properties.get("name")
        code = properties.get("adcode")
        center = properties.get("center")
        if name and code and center and len(center) >= 2:
            regions.append(
                {
                    "name": name,
                    "adcode": str(code),
                    "longitude": center[0],
                    "latitude": center[1],
                    "children_num": int(properties.get("childrenNum") or 0),
                }
            )
    return regions


def location_label(location: dict) -> str:
    """Format the selected Chinese administrative path."""
    return "，".join(part for part in location.get("path", []) if part)


def make_chart(
    calendar_type: str,
    birth_date: date | None,
    lunar_year: int,
    lunar_month: int,
    lunar_day: int,
    is_leap_month: bool,
    birth_time: time,
    use_true_solar_time: bool,
    location: dict | None,
    fold_choice: str,
) -> tuple[dict, dict | None]:
    """根据网页输入排盘，返回最终采用的命盘和可选时间修正详情。"""
    # Keep the calendar library out of the initial page startup path.
    from bazi import calculate_chart, calculate_lunar_chart, convert_to_true_solar_time

    if calendar_type == "公历":
        if birth_date is None:
            raise ValueError("请选择出生日期。")
        civil_time = datetime.combine(birth_date, birth_time)
        civil_chart = calculate_chart(civil_time)
    else:
        civil_chart = calculate_lunar_chart(
            lunar_year,
            lunar_month,
            lunar_day,
            birth_time.hour,
            birth_time.minute,
            is_leap_month=is_leap_month,
        )
        civil_time = datetime.strptime(str(civil_chart["公历"]), "%Y-%m-%d %H:%M:%S")
    civil_chart["输入出生时间"] = civil_time.strftime("%Y-%m-%d %H:%M")

    if not use_true_solar_time:
        return civil_chart, None
    if location is None:
        raise ValueError("请先搜索并选择出生地点，再使用真太阳时修正。")

    fold = {"自动": None, "夏令时第一次": 0, "夏令时第二次": 1}[fold_choice]
    true_solar_time, utc_offset, equation_minutes = convert_to_true_solar_time(
        civil_time,
        float(location["longitude"]),
        str(location["timezone"]),
        fold=fold,
    )
    final_chart = calculate_chart(
        true_solar_time,
        time_basis="根据出生地经度和时区修正后的真太阳时",
    )
    if calendar_type == "农历":
        final_chart["输入历法"] = "农历"
        final_chart["输入农历日期"] = civil_chart["输入农历日期"]
    final_chart["输入出生时间"] = civil_chart["输入出生时间"]

    correction = {
        "当地钟表时间": civil_time.strftime("%Y-%m-%d %H:%M"),
        "真太阳时": true_solar_time.strftime("%Y-%m-%d %H:%M"),
        "时区": str(location["timezone"]),
        "UTC偏移": utc_offset,
        "经度": float(location["longitude"]),
        "地点": location_label(location),
        "均时差分钟": equation_minutes,
        "原始排盘": civil_chart,
    }
    return final_chart, correction


def show_pillars(chart: dict) -> None:
    element_colors = {"木": "#72c982", "火": "#f07870", "土": "#a97945", "金": "#e7bd45", "水": "#438bc5"}
    stem_elements = dict(zip("甲乙丙丁戊己庚辛壬癸", "木木火火土土金金水水"))
    branch_elements = {"子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土", "巳": "火",
                       "午": "火", "未": "土", "申": "金", "酉": "金", "戌": "土", "亥": "水"}

    def color_for(character: str, stem: bool = False) -> str:
        element = (stem_elements if stem else branch_elements).get(character, "土")
        return element_colors[element]

    natal_shensha = chart.get("命局神煞", [])
    columns = st.columns(4, gap="small")
    for column, (name, pillar) in zip(columns, chart["四柱"].items()):
        details = chart.get("四柱详情", {}).get(name, {})
        stem, branch = (pillar[0], pillar[1]) if len(pillar) >= 2 else ("—", "—")
        stem_color = color_for(stem, stem=True)
        branch_color = color_for(branch)
        hidden = details.get("地支藏干", [])
        hidden_rows = []
        for index in range(3):
            if index < len(hidden):
                item = hidden[index]
                stem_char = str(item.get("天干", ""))
                hidden_rows.append(
                    f"<span class='pillar-hidden-row'><span style='color:{color_for(stem_char, stem=True)};font-weight:600'>"
                    f"{html.escape(stem_char)}</span><span>{html.escape(str(item.get('十神', '')))}</span></span>"
                )
            else:
                hidden_rows.append("<span class='pillar-hidden-row'><span>&nbsp;</span><span>&nbsp;</span></span>")
        hidden_html = "".join(hidden_rows)
        shensha_here = [
            str(item.get("名称", "")) for item in natal_shensha
            if name in item.get("命中柱位", [])
        ]
        shensha_html = "<br>".join(html.escape(item) for item in shensha_here) or "未匹配到"
        safe_name = html.escape(name)
        safe_god = html.escape(str(details.get("天干十神", "—")))
        safe_nayin = html.escape(str(details.get("纳音", "—")))
        safe_xunkong = html.escape(str(details.get("旬空", "—")))
        safe_star = html.escape(str(details.get("星运", "—")))
        safe_self = html.escape(str(details.get("自坐", "—")))
        card = (
            f"<div class='pillar-card'><div class='pillar-name'>{safe_name}</div>"
            f"<div class='pillar-god'>{safe_god}</div>"
            f"<div class='pillar-glyph' style='color:{stem_color}'>{html.escape(stem)}</div>"
            f"<div class='pillar-glyph' style='color:{branch_color}'>{html.escape(branch)}</div>"
            f"<div class='pillar-hidden'>{hidden_html}</div>"
            f"<div class='pillar-meta'><div><b>纳音</b>　{safe_nayin}</div>"
            f"<div><b>空亡</b>　{safe_xunkong}</div><div><b>星运</b>　{safe_star}</div>"
            f"<div><b>自坐</b>　{safe_self}</div></div>"
            f"<div class='pillar-shensha'><b>神煞</b><br>{shensha_html}</div></div>"
        )
        with column:
            st.markdown(card, unsafe_allow_html=True)

    st.caption("天干十神和藏干十神均以日干为基准；藏干按本气、中气、余气顺序显示。星运按日主看各柱地支，自坐按各柱天干看本柱地支。颜色按对应天干或地支的五行显示。")
    with st.expander("查看《三命通会》规则匹配到的命局神煞"):
        natal_shensha = chart.get("命局神煞", [])
        if not natal_shensha:
            st.info("按当前采用的取法，四柱中没有匹配到这些神煞。")
        else:
            for item in natal_shensha:
                positions = "、".join(item["命中柱位"])
                st.markdown(f"**{item['名称']}** · 命中：{positions}")
                st.caption(f"起法：{item['起法']}｜依据：{item['出处']}")
        st.caption(
            "首批只计算原文中可明确转成查表规则的项目；这里只标记是否出现，不据此断吉凶。"
            "部分神煞原文另载异说，程序当前采用的取法会在每项旁注明。"
        )

def refresh_legacy_chart_details(chart: dict) -> None:
    """补齐热更新前已保存在 Streamlit session_state 中的旧命盘字段。"""
    chart.pop("农历日神煞", None)
    details = chart.get("四柱详情") or {}
    required = ("天干十神", "地支藏干", "纳音", "旬空", "星运", "自坐")
    if all(
        all(chart_pillar.get(field) for field in required)
        for chart_pillar in (details.get(name, {}) for name in chart.get("四柱", {}))
    ):
        return
    birth_text = chart.get("公历")
    if not birth_text:
        return
    try:
        from bazi import calculate_chart

        fresh = calculate_chart(datetime.strptime(str(birth_text), "%Y-%m-%d %H:%M:%S"))
    except (ValueError, TypeError):
        return
    # Reuse the newly calculated annotations only when the pillar text agrees.
    # This avoids attaching details from a different calendar or time basis.
    if fresh.get("四柱") != chart.get("四柱"):
        return
    chart["四柱详情"] = fresh["四柱详情"]
    chart["命局神煞"] = fresh["命局神煞"]


def queue_analysis() -> None:
    """排盘提交后锁住按钮，防止重复计算。"""
    if not st.session_state.get("analysis_running", False):
        st.session_state["analysis_requested"] = True
        st.session_state["analysis_running"] = True


def queue_retrieval() -> None:
    """Reuse successful retrieval for this chart; the button then navigates only."""
    st.session_state["active_panel"] = "books"
    cached = st.session_state.get("retrieval_result", {})
    if cached.get("success") and cached.get("version") == RETRIEVAL_VERSION:
        return
    if not st.session_state.get("retrieval_running", False):
        st.session_state["retrieval_requested"] = True
        st.session_state["retrieval_running"] = True
        st.session_state["active_panel"] = "books"


def render_book_result(
    book_name: str,
    book_results: list[dict],
    retrieval_result: dict,
    chart: dict | None = None,
) -> None:
    """Give every book its own original/translation reading tabs."""
    original_tab, translation_tab = st.tabs(["原文", "译文"])
    with original_tab:
        _render_book_original(book_name, book_results, retrieval_result, chart)
    with translation_tab:
        import book_translation as book_translation_module

        importlib.reload(book_translation_module)
        import translation_panel as translation_panel_module

        translation_panel_module = importlib.reload(translation_panel_module)
        translation_panel_module.render_translation_panel(book_name, book_results)


def _render_book_original(
    book_name: str,
    book_results: list[dict],
    retrieval_result: dict,
    chart: dict | None = None,
) -> None:
    """Render one book as soon as its individual retrieval has completed."""
    if not book_results:
        st.info(f"《{book_name}》本次没有检索到可展示的原文。")
        return
    book_mode = retrieval_result.get("book_modes", {}).get(book_name)
    if book_name == "滴天髓" and book_mode != "day_stem_exact":
        st.info("《滴天髓》已改为按日干定位专论，请重新点击‘古籍检索’。")
        return
    if book_name == "穷通宝鉴":
        if retrieval_result.get("annotation_issues"):
            st.warning(
                f"有 {len(retrieval_result['annotation_issues'])} 条标注未通过原文校验，已排除。"
            )
        if book_mode in {"day_month_exact", "day_month_shared"}:
            st.caption("按日干和月令直接定位原文，不使用五行总论代替对应月份。条文的具体条件仍需结合命盘判断。")
            if book_mode == "day_month_shared":
                st.caption("底本部分内容采用合月或季节合论；此处保留目标月份的条文及涵盖该月的共论，原文篇名和出处照录。")
        elif retrieval_result.get("retrieval_mode") == "chapter_fallback":
            st.warning(
                f"未命中已人工核对的适用条件。以下是“{retrieval_result.get('selected_chapter') or '对应篇章'}”篇内的语义参考，"
                "尚未确认适用于此命盘。"
            )
        else:
            st.caption("以下原文命中已整理的条件标注；命理结论仍需另行判断。")
    elif book_mode == "four_part":
        st.caption("《三命通会》按日时组合、日干、日干生月、五行生月四层线索分别检索；结果是相关原文线索，仍需结合原文判断适用性。")
    elif book_name == "滴天髓" and book_mode == "day_stem_exact":
        st.caption("《滴天髓》按命盘日干精确定位‘七、天干’中的对应专论，依次展示正文、原注与任氏注。")
    elif book_mode == "chapter_conditioned":
        st.caption(f"已按《{book_name}》自身的篇章结构筛选候选篇，再在篇内排序；是否适用于此命盘仍需结合原文判断。")
    else:
        st.caption("以下为本书内的语义参考结果；不同古籍的适用条件尚未结构化核对。")
    def render_result(result: dict, rank: int, show_part: bool = True) -> None:
        metadata = result["metadata"]
        with st.container(border=True):
            retrieval_part = metadata.get("retrieval_part")
            part_label = f"{retrieval_part} · " if show_part and retrieval_part else ""
            location_mode = "按日干定位" if book_name == "滴天髓" else "按日干月令定位" if book_name == "穷通宝鉴" else "段落检索"
            st.markdown(
                f"**{part_label}原文 {rank}** · {metadata['chapter']} · "
                f"原文位置：第 {metadata['line_number']} 行（{location_mode}）"
            )
            if metadata.get("retrieval_query"):
                st.caption(f"检索线索：{metadata['retrieval_query']}")
            retrieval_method = metadata.get("retrieval_method")
            method_labels = {
                "原文精确字串": "在原文中精确匹配",
                "按本书章节结构取整章": "按本书实际目录定位并返回整章",
                "chapter_conditioned": "限制在对应篇章内做语义排序",
                "semantic_reference": "未找到对应篇章，回退到本书语义检索",
                "按日干精确定位": "按日干精确定位对应专论",
                "按日干月令精确定位": "按日干与月令定位完整原文段落",
            }
            if retrieval_method in method_labels:
                st.caption(f"检索方式：{method_labels[retrieval_method]}")
            source_document = str(result["document"])
            source_ids = metadata.get("source_ids", [])
            if book_name == "滴天髓":
                paragraphs = source_document.split("\n\n")
                formatted = []
                for index, paragraph in enumerate(paragraphs):
                    escaped = html.escape(paragraph)
                    if index == 0:
                        escaped = f"<strong>{escaped}</strong>"
                    formatted.append(f"<p class='source-reading-line'>{escaped}</p>")
                st.markdown("<div class='source-reading'>" + "".join(formatted) + "</div>", unsafe_allow_html=True)
                with st.expander("查看原文文本"):
                    st.text(source_document)
            elif book_name == "穷通宝鉴":
                st.markdown("<div class='source-reading'>" + "".join(
                    f"<p class='source-reading-line'>{html.escape(paragraph)}</p>"
                    for paragraph in source_document.split("\n\n") if paragraph.strip()
                ) + "</div>", unsafe_allow_html=True)
                with st.expander("查看原文文本"):
                    st.text(source_document)
            elif book_name == "三命通会" and len(source_ids) > 1:
                readable_lines = []
                for index, raw_line in enumerate(source_document.splitlines()):
                    line = raw_line.strip()
                    if not line:
                        continue
                    if index == 0 and line == str(metadata.get("chapter", "")):
                        readable_lines.append(
                            f"<h4 class='source-chapter-title'>{html.escape(line)}</h4>"
                        )
                        continue
                    readable_lines.append(f"<p class='source-reading-line'>{html.escape(line)}</p>")
                st.markdown(
                    "<div class='source-reading'>" + "".join(readable_lines) + "</div>",
                    unsafe_allow_html=True,
                )
                st.caption("正文保留电子文本的标点和分段；标点属于整理文本，不代表古籍原刻标点。")
                with st.expander("查看检索到的原文文本"):
                    st.text(source_document)
            else:
                st.text(source_document)
            if book_name == "穷通宝鉴" and retrieval_result.get("retrieval_mode") == "verified_conditions":
                annotation = result.get("annotation", {})
                st.caption(f"出处：{metadata['citation']}｜条件标注：{annotation.get('status', '已匹配')}")
            elif book_name == "穷通宝鉴" and book_mode in {"day_month_exact", "day_month_shared"}:
                st.caption(f"出处：{metadata['citation']}｜按日干与月令定位；具体条文适用条件需结合命盘核对。")
            elif book_mode == "chapter_conditioned":
                st.caption(f"出处：{metadata['citation']}｜依据本书篇章结构筛选，命理适用条件未核定")
            elif book_mode == "four_part":
                st.caption(f"出处：{metadata['citation']}｜本条为对应层级的检索结果，适用条件未核定")
            elif book_name == "滴天髓" and book_mode == "day_stem_exact":
                st.caption(f"出处：{metadata['citation']}｜本条为日干专论，含原注与任氏注；篇名为整理标签。")
            else:
                reference_label = "本地段落关键词参考（非向量检索）" if retrieval_result.get("book_modes", {}).get(book_name) == "local_text_reference" else "语义参考"
                st.caption(f"出处：{metadata['citation']}｜{reference_label}，适用条件未核定")
            st.caption(f"引用 ID：{metadata['source_id']}")

    if book_name == "三命通会" and book_mode == "four_part":
        grouped: dict[str, list[dict]] = {
            "第一部分·日时组合": [],
            "第二部分·日干专论": [],
            "第三部分·日干生月": [],
            "第四部分·五行生月": [],
        }
        for result in book_results:
            grouped.setdefault(result["metadata"].get("retrieval_part", ""), []).append(result)

        pillars = (chart or {}).get("四柱", {})
        day_pillar = str(pillars.get("日柱", ""))
        time_pillar = str(pillars.get("时柱", ""))
        day_stem = day_pillar[:1]
        month_branch = str(pillars.get("月柱", ""))[1:2]
        element_map = {"甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土", "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水"}
        labels = {
            "第一部分·日时组合": f"{day_pillar}日{time_pillar}时" if day_pillar and time_pillar else "日时组合",
            "第二部分·日干专论": f"论{day_stem}日干" if day_stem else "日干专论",
            "第三部分·日干生月": f"{day_stem}生{month_branch}月" if day_stem and month_branch else "日干生月",
            "第四部分·五行生月": f"{element_map.get(day_stem, '')}生{month_branch}月" if day_stem and month_branch else "五行生月",
        }
        part_tabs = st.tabs([labels[key] for key in grouped])
        for (part, part_results), part_tab in zip(grouped.items(), part_tabs):
            with part_tab:
                if not part_results:
                    st.info("这一层本次没有找到可展示的原文。")
                    continue
                for rank, result in enumerate(part_results, start=1):
                    render_result(result, rank, show_part=False)
        return

    for rank, result in enumerate(book_results, start=1):
        render_result(result, rank)


@st.fragment
def render_birth_form() -> None:
    """Keep ordinary input changes inside this small, independently rerun area."""
    st.markdown("### 出生日期与时间")
    calendar_type = st.radio("历法", ["公历", "农历", "四柱八字"], horizontal=True, label_visibility="collapsed", key="calendar_type")
    gender = st.radio("性别", ["男", "女"], index=None, horizontal=True, key="birth_gender")
    if calendar_type == "四柱八字":
        from lunar_python.util import LunarUtil

        stems = "甲乙丙丁戊己庚辛壬癸"
        branches = "子丑寅卯辰巳午未申酉戌亥"
        pillar_cols = st.columns(4)
        manual_pillars = {}
        for column, name in zip(pillar_cols, ("年柱", "月柱", "日柱", "时柱")):
            options = list(LunarUtil.JIA_ZI)
            prerequisite = ""
            if name == "月柱":
                year_pillar = manual_pillars.get("年柱")
                prerequisite = "年柱" if not year_pillar else ""
                start = stems.index(year_pillar[0]) % 5 * 2 + 2 if year_pillar else 0
                options = [stems[(start + i) % 10] + branch for i, branch in enumerate("寅卯辰巳午未申酉戌亥子丑")] if year_pillar else []
            elif name == "时柱":
                day_pillar = manual_pillars.get("日柱")
                prerequisite = "日柱" if not day_pillar else ""
                start = stems.index(day_pillar[0]) % 5 * 2 if day_pillar else 0
                options = [stems[(start + i) % 10] + branch for i, branch in enumerate(branches)] if day_pillar else []
                if day_pillar:
                    options.append(stems[(start + 2) % 10] + "子")
            select_key = f"manual_select_{name}"
            if st.session_state.get(select_key) not in options:
                st.session_state[select_key] = None
            with column:
                manual_pillars[name] = st.selectbox(
                    name, options, index=None, key=select_key, disabled=bool(prerequisite),
                    placeholder=f"请先选择{prerequisite}" if prerequisite else f"请选择{name}",
                    format_func=lambda p, late_choice=options[-1] if name == "时柱" and options else None: p + "（晚子时）" if p == late_choice else p,
                )
        st.caption("选择年柱后可选月柱，选择日柱后可选时柱；无需出生日期和地点。时柱末项兼容晚子时取法。")
        professional_birth = None
        with st.expander("补充出生时刻（可选，用于专业细盘）"):
            st.caption("四柱不能唯一确定出生日期。需要查看大运时，请补充与所选四柱对应的公历日期和排盘时刻。")
            extra_date_col, extra_time_col = st.columns([2, 1])
            with extra_date_col:
                extra_date = st.date_input("对应公历出生日期", value=None, min_value=date(1800, 1, 1),
                                            max_value=date(2200, 12, 31), key="manual_professional_birth_date")
            with extra_time_col:
                extra_time = st.time_input("对应排盘时刻", value=None, key="manual_professional_birth_time")
            if extra_date is not None and extra_time is not None:
                professional_birth = datetime.combine(extra_date, extra_time).isoformat(sep=" ")
        st.button("开始排盘", type="primary", use_container_width=True,
                  disabled=st.session_state.get("analysis_running", False) or not gender or not all(manual_pillars.values()),
                  on_click=queue_analysis, key="start_analysis")
        if st.session_state.get("analysis_running", False):
            st.info("正在排盘，请稍候……")
        st.session_state["birth_form"] = {"calendar_type": calendar_type, "pillars": manual_pillars,
                                          "gender": gender, "professional_birth": professional_birth}
        if st.session_state.get("analysis_requested") and not st.session_state.get("analysis_dispatching"):
            st.session_state["analysis_dispatching"] = True
            st.rerun()
        return
    date_col, time_col = st.columns([2.2, 1], vertical_alignment="bottom")
    with date_col:
        if calendar_type == "公历":
            initial_date = st.session_state.get("birth_date", date(1990, 1, 1))
            if not isinstance(initial_date, date):
                initial_date = date(1990, 1, 1)
            solar_cols = st.columns([1.3, 1, 1])
            with solar_cols[0]:
                birth_year = st.selectbox("出生年份", list(range(1800, 2201)),
                                          index=min(2200, max(1800, initial_date.year)) - 1800, key="solar_birth_year")
            with solar_cols[1]:
                birth_month = st.selectbox("月", list(range(1, 13)), index=initial_date.month - 1, key="solar_birth_month")
            days = list(range(1, monthrange(birth_year, birth_month)[1] + 1))
            if st.session_state.get("solar_birth_day", days[0]) not in days:
                st.session_state["solar_birth_day"] = days[-1]
            with solar_cols[2]:
                birth_day = st.selectbox("日", days, index=min(initial_date.day, days[-1]) - 1, key="solar_birth_day")
            birth_date = date(birth_year, birth_month, birth_day)
            lunar_year, lunar_month, lunar_day, is_leap_month = 1990, 1, 1, False
        else:
            birth_date = None
            lunar_cols = st.columns([1.3, 1, 1], vertical_alignment="bottom")
            with lunar_cols[0]:
                lunar_year = st.selectbox("出生年份", list(range(1800, 2201)), index=190, key="lunar_birth_year")
            with lunar_cols[1]:
                month_names = ("正月", "二月", "三月", "四月", "五月", "六月", "七月", "八月", "九月", "十月", "冬月", "腊月")
                lunar_month = st.selectbox("农历月", list(range(1, 13)),
                                           index=int(st.session_state.get("lunar_month", 1)) - 1,
                                           format_func=lambda m: month_names[m - 1], key="lunar_birth_month")
            with lunar_cols[2]:
                day_names = ("初一", "初二", "初三", "初四", "初五", "初六", "初七", "初八", "初九", "初十",
                             "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十",
                             "廿一", "廿二", "廿三", "廿四", "廿五", "廿六", "廿七", "廿八", "廿九", "三十")
                lunar_day = st.selectbox("农历日", list(range(1, 31)),
                                         index=int(st.session_state.get("lunar_day", 1)) - 1,
                                         format_func=lambda d: day_names[d - 1], key="lunar_birth_day")
    with time_col:
        birth_time = st.time_input("出生时刻", value=time(12, 0), key="birth_time")
    if calendar_type == "农历":
        is_leap_month = st.checkbox("闰月", key="is_leap_month", help="出生月份属于当年的闰月时勾选。")

    st.markdown("### 出生地点")
    location = None
    load_location = not PORTABLE_MODE or st.checkbox(
        "选择出生地点（需联网加载地点）", value=False, key="portable_load_location"
    )
    if load_location:
        try:
            with st.spinner("正在载入省份列表……"):
                provinces = load_regions("100000")
            province_col, city_col, county_col = st.columns(3)
            with province_col:
                selected_province = st.selectbox("省 / 直辖市 / 自治区", provinces, format_func=lambda item: item["name"], key="birth_province", index=None, placeholder="请选择省份")
            selected_city = None
            selected_county = None
            cities = []
            if selected_province:
                is_municipality = selected_province["adcode"] in {"110000", "120000", "310000", "500000", "810000", "820000"}
                if is_municipality:
                    province_children = []
                else:
                    with st.spinner("正在载入城市列表……"):
                        province_children = load_regions(selected_province["adcode"])
                cities = [selected_province] if is_municipality else (province_children or [selected_province])
            with city_col:
                selected_city = st.selectbox(
                    "城市",
                    cities,
                    format_func=lambda item: item["name"],
                    key=f"birth_city_{selected_province['adcode']}" if selected_province else "birth_city_waiting",
                    index=None,
                    placeholder="请选择城市" if selected_province else "请先选择省份",
                    disabled=not bool(selected_province),
                )

            counties = []
            if selected_city and selected_city.get("children_num", 1) > 0:
                with st.spinner("正在载入县区列表……"):
                    counties = load_regions(selected_city["adcode"])
            if not selected_city:
                with county_col:
                    st.selectbox("县 / 区", [], key="birth_county_waiting", index=None, placeholder="请先选择城市", disabled=True)
            elif counties:
                with county_col:
                    selected_county = st.selectbox(
                        "县 / 区",
                        counties,
                        format_func=lambda item: item["name"],
                        key=f"birth_county_{selected_city['adcode']}",
                        index=None,
                        placeholder="请选择县区",
                    )
            if selected_province and selected_city and (selected_county or not counties):
                final_region = selected_county or {**selected_city, "coordinate_level": "市中心"}
                place_path = [selected_province["name"], selected_city["name"]]
                if selected_county:
                    place_path.append(selected_county["name"])
                location = {
                    **final_region,
                    "path": place_path,
                    "coordinate_level": final_region.get("coordinate_level", "区县中心"),
                    "timezone": {"台湾省": "Asia/Taipei", "香港特别行政区": "Asia/Hong_Kong", "澳门特别行政区": "Asia/Macau"}.get(selected_province["name"], "Asia/Shanghai"),
                }
                st.caption(f"地点：{location_label(location)}　｜　{location['coordinate_level']}坐标：{float(location['latitude']):.4f}, {float(location['longitude']):.4f}　｜　时区：{location['timezone']}")
        except Exception as error:
            st.error(f"行政区地点数据暂时无法加载，请检查网络后刷新页面：{error}")
        st.caption("仅提供中国省、市、县区三级选择。区县中心坐标用于真太阳时修正，不等同于具体医院坐标。行政区数据由 DataV.GeoAtlas 提供。")

    else:
        st.caption("按输入的当地钟表时间排盘；需要真太阳时修正时，再勾选加载出生地点。")
        st.session_state["use_true_solar_time"] = False

    use_true_solar_time = st.checkbox(
        "按出生地经度修正真太阳时",
        value=not PORTABLE_MODE,
        disabled=not load_location,
        help="使用已选地点返回的经度和时区计算；取消勾选则按输入的当地钟表时间排盘。",
        key="use_true_solar_time",
    )
    fold_choice = "自动"
    if use_true_solar_time:
        fold_choice = st.selectbox("夏令时回拨时刻重复怎么办？", ["自动", "夏令时第一次", "夏令时第二次"], key="fold_choice")

    st.button(
        "开始排盘",
        type="primary",
        use_container_width=True,
        disabled=st.session_state.get("analysis_running", False) or not gender,
        on_click=queue_analysis,
        key="start_analysis",
    )
    if st.session_state.get("analysis_running", False):
        st.info("正在排盘，请稍候……")
    st.session_state["birth_form"] = {
        "calendar_type": calendar_type,
        "gender": gender,
        "birth_date": birth_date,
        "lunar_year": int(lunar_year),
        "lunar_month": int(lunar_month),
        "lunar_day": int(lunar_day),
        "is_leap_month": is_leap_month,
        "birth_time": birth_time,
        "use_true_solar_time": use_true_solar_time,
        "location": location,
        "fold_choice": fold_choice,
    }
    if st.session_state.get("analysis_requested") and not st.session_state.get("analysis_dispatching"):
        st.session_state["analysis_dispatching"] = True
        st.rerun()


render_birth_form()
form_data = st.session_state.get("birth_form", {})
submitted = bool(st.session_state.pop("analysis_requested", False))
if submitted:
    st.session_state["analysis_dispatching"] = False
    st.session_state.pop("chart_result", None)
    st.session_state.pop("retrieval_result", None)

if submitted:
    try:
        if form_data.get("gender") not in ("男", "女"):
            raise ValueError("请先选择性别。")
        if form_data["calendar_type"] == "四柱八字":
            import bazi as bazi_module

            importlib.reload(bazi_module)
            chart = bazi_module.calculate_pillars_chart(form_data["pillars"])
            if form_data.get("professional_birth"):
                chart["专业出生时刻"] = form_data["professional_birth"]
            correction = None
        else:
            chart, correction = make_chart(
                form_data["calendar_type"],
                form_data["birth_date"],
                form_data["lunar_year"],
                form_data["lunar_month"],
                form_data["lunar_day"],
                form_data["is_leap_month"],
                form_data["birth_time"],
                form_data["use_true_solar_time"],
                form_data["location"],
                form_data["fold_choice"],
            )
            chart["输入地点"] = location_label(form_data["location"]) if form_data["location"] else "未选择"
        chart["性别"] = form_data["gender"]
        st.session_state["chart_result"] = {
            "chart": chart,
            "correction": correction,
        }
        st.session_state.pop("retrieval_result", None)
        st.session_state.pop("retrieval_error", None)
        st.session_state["active_panel"] = None
        st.session_state.pop("chart_error", None)
    except Exception as error:
        st.session_state["chart_error"] = f"排盘时遇到问题：{error}"
    finally:
        st.session_state["analysis_running"] = False
    st.rerun()

if error_message := st.session_state.get("chart_error"):
    st.error(error_message)

chart_result = st.session_state.get("chart_result")
if chart_result:
    chart = chart_result["chart"]
    refresh_legacy_chart_details(chart)
    st.divider()
    st.subheader("四柱排盘")
    basic_tab, professional_tab = st.tabs(["基础排盘", "专业细盘"])
    with basic_tab:
        show_pillars(chart)
    with professional_tab:
        import professional_chart as professional_chart_module

        importlib.reload(professional_chart_module)
        import pillar_relationships as pillar_relationships_module

        importlib.reload(pillar_relationships_module)
        import professional_panel as professional_panel_module

        professional_panel_module = importlib.reload(professional_panel_module)
        professional_panel_module.render_professional_chart(chart)
    if chart.get("输入历法") == "四柱八字":
        st.caption("四柱输入：" + "　".join(f"{name} {pillar}" for name, pillar in chart["四柱"].items())
                   + "｜直接按输入四柱排盘")
    else:
        st.caption(
            f"出生信息：{chart.get('输入历法', '公历')} {chart.get('输入出生时间')}｜"
            f"地点：{chart.get('输入地点', '未填写')}｜排盘采用时刻：{chart.get('公历')}｜"
            f"{chart.get('时间说明')}"
        )

    correction = chart_result["correction"]
    if correction:
        with st.expander("查看时间修正详情"):
            st.write(f"出生地时区：{correction['时区']}（该日期 UTC 偏移 {correction['UTC偏移']:+g} 小时）")
            st.write(f"经度：{correction['经度']:+g}°；均时差：{correction['均时差分钟']:+.2f} 分钟")
            st.write(f"当地钟表时间：{correction['当地钟表时间']}；修正后：{correction['真太阳时']}")
            st.write(f"修正前四柱：{correction['原始排盘']['四柱']}")

    retrieval_result = st.session_state.get("retrieval_result")
    if retrieval_result and retrieval_result.get("version") != RETRIEVAL_VERSION:
        st.session_state.pop("retrieval_result", None)
        retrieval_result = None
    retrieval_ready = bool(retrieval_result and retrieval_result.get("success"))
    book_col, ai_col = st.columns(2)
    with book_col:
        st.button(
            "古籍检索",
            type="primary" if st.session_state.get("active_panel") == "books" else "secondary",
            use_container_width=True,
            disabled=st.session_state.get("retrieval_running", False),
            on_click=queue_retrieval,
            help="已检索成功，点击返回原文页面。重新排盘后会重新检索。" if retrieval_ready else "检索当前命盘对应的古籍原文。",
            key="run_book_retrieval",
        )
    with ai_col:
        st.button(
            "AI 解读",
            type="primary" if st.session_state.get("active_panel") == "ai" else "secondary",
            use_container_width=True,
            disabled=not retrieval_ready,
            on_click=lambda: st.session_state.update(active_panel="ai"),
            key="open_ai_explanation",
        )

    if st.session_state.get("retrieval_running"):
        st.info("正在检索古籍，请稍候……")

    if st.session_state.pop("retrieval_requested", False):
        st.session_state["active_panel"] = "books"
        conditions = chart["检索条件"]
        exposed = "、".join(conditions.get("exposed_stems", [])) or "无"
        hidden = "、".join(conditions.get("hidden_stems", [])) or "无"
        pillars = "，".join(f"{name}{pillar}" for name, pillar in chart["四柱"].items())
        query_topic = (
            f"四柱：{pillars}；"
            f"日主{conditions.get('day_master', '')}；月令{conditions.get('month_branch', '')}；"
            f"天干透出{exposed}；地支藏干{hidden}；寻找与此日主和月令组合相关的原文"
        )
        results_by_book: dict[str, list[dict]] = {}
        book_modes: dict[str, str] = {}
        book_errors: dict[str, str] = {}
        annotation_issues: list[str] = []
        retrieval_mode = "no_results"
        selected_chapter = None
        books_available: set[str] = set()
        retrieval_result = {
            "version": RETRIEVAL_VERSION,
            "results_by_book": results_by_book,
            "book_modes": book_modes,
            "book_errors": book_errors,
            "books_available": [],
            "annotation_issues": annotation_issues,
            "retrieval_mode": retrieval_mode,
            "selected_chapter": selected_chapter,
            "success": False,
        }
        st.session_state["retrieval_result"] = retrieval_result
        try:
            # Initialize the model/index once, then query books in the same
            # order as the tabs. Each completed tab is rendered immediately.
            with st.spinner("正在准备本地古籍……" if PORTABLE_MODE else "正在准备检索模型……"):
                collection = get_retrieval_collection("bazi_classics_paragraphs")
                # Streamlit may keep imported modules alive across hot reloads.
                import source_data as source_data_module

                importlib.reload(source_data_module)
                if PORTABLE_MODE:
                    import portable_retrieval as rag_module
                else:
                    import rag as rag_module

                rag_module = importlib.reload(rag_module)
                retriever_module_names = (
                    "book_retrievers.common",
                    "book_retrievers.qiong_tong_bao_jian",
                    "book_retrievers.sanming_tonghui",
                    "book_retrievers.ziping_zhenquan",
                    "book_retrievers.ditian_sui",
                    "book_retrievers.registry",
                )
                for module_name in retriever_module_names:
                    importlib.reload(importlib.import_module(module_name))
                retriever_registry = importlib.import_module("book_retrievers.registry")
                source_records = rag_module.load_source_records()
                books_available = {str(record["book_name"]) for record in source_records}
                retrieval_result["books_available"] = sorted(books_available)

            book_tabs = st.tabs(BOOK_NAMES)
            for book_name, tab in zip(BOOK_NAMES, book_tabs):
                with tab:
                    if book_name not in books_available:
                        st.info(f"《{book_name}》尚未录入书库。")
                        results_by_book[book_name] = []
                        continue
                    try:
                        with st.spinner(f"正在检索《{book_name}》……"):
                            book_output = retriever_registry.retrieve(
                                book_name, chart, query_topic, 1, collection, rag_module
                            )
                            book_results = book_output["results"]
                            book_modes[book_name] = book_output["mode"]
                            if book_name == "穷通宝鉴":
                                retrieval_result["annotation_issues"] = book_output["annotation_issues"]
                                retrieval_result["retrieval_mode"] = book_output["mode"]
                                retrieval_result["selected_chapter"] = book_output["chapter"]
                        results_by_book[book_name] = book_results
                        retrieval_result["success"] = any(results_by_book.values())
                        st.session_state["retrieval_result"] = retrieval_result
                        render_book_result(book_name, book_results, retrieval_result, chart)
                    except Exception as error:
                        results_by_book[book_name] = []
                        book_errors[book_name] = str(error)
                        retrieval_result["success"] = any(results_by_book.values())
                        st.session_state["retrieval_result"] = retrieval_result
                        st.error(f"检索《{book_name}》时遇到问题：{error}")
            st.session_state["retrieval_result"] = retrieval_result
            st.session_state.pop("retrieval_error", None)
        except Exception as error:
            st.session_state["retrieval_error"] = f"古籍检索时遇到问题：{error}"
            retrieval_result["success"] = any(results_by_book.values())
            st.session_state["retrieval_result"] = retrieval_result
        finally:
            st.session_state["retrieval_running"] = False
        st.rerun()

    if error_message := st.session_state.get("retrieval_error"):
        st.error(error_message)

    if st.session_state.get("active_panel") == "books":
        if not retrieval_ready:
            st.info("检索没有返回原文，因此 AI 解读暂不可用。")
        else:
            book_tabs = st.tabs(["穷通宝鉴", "三命通会", "子平真诠", "滴天髓"])
            for tab, book_name in zip(book_tabs, BOOK_NAMES):
                with tab:
                    if book_name not in retrieval_result["books_available"]:
                        st.info(f"《{book_name}》尚未录入书库。")
                        continue
                    if book_name in retrieval_result.get("book_errors", {}):
                        st.error(f"检索本书时遇到问题：{retrieval_result['book_errors'][book_name]}")
                        continue
                    book_results = retrieval_result["results_by_book"].get(book_name, [])
                    if not book_results:
                        st.info(f"《{book_name}》已在书库中，但本次没有检索到可展示的原文。")
                        continue
                    render_book_result(book_name, book_results, retrieval_result, chart)
    elif st.session_state.get("active_panel") == "ai":
        import citation_audit as citation_audit_module

        importlib.reload(citation_audit_module)
        import ai_analysis as ai_analysis_module
        importlib.reload(ai_analysis_module)

        import ai_panel as ai_panel_module
        ai_panel_module = importlib.reload(ai_panel_module)
        ai_panel_module.render_ai_panel(chart, retrieval_result)
    elif not retrieval_ready:
        st.caption("四柱已排出。点击“古籍检索”查看原文；检索成功后可继续使用“AI 解读”。")

with st.expander("关于当前版本"):
    st.write("这是本机学习版网页。出生地点通过省、市、县区逐级选择；真太阳时修正使用所选区县中心的经度和对应时区。")
    st.write("《穷通宝鉴》按日干与月令直接定位正文；原文中的具体条件仍需结合命盘核对。")
    st.write("排盘由 lunar-python 计算；专业细盘支持运程浏览及原局与运年月日关系。AI 解读可选择智谱或 DeepSeek，默认分析原局，也可结合当前选定运年、流月、流日及古籍资料。")
    st.caption("行政区数据来源：DataV.GeoAtlas。区县中心坐标为近似位置，不代表具体出生医院。")
