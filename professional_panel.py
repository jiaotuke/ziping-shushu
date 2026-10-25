"""Professional table and horizontal pickers, backed by the existing calendar library."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from professional_chart import describe_pillar, flow_days, flow_months, luck_cycles
from pillar_relationships import analyze_relationships
from source_data import load_source_records

wheel_chart = components.declare_component("ziping_professional_chart", path=str(Path(__file__).parent / "components" / "professional_chart"))
PANEL_VERSION = "relations-4-directed-and-hidden"


def _render_relationship_sources() -> None:
    with st.expander("干支关系的口径与原文依据"):
        st.markdown("关系按柱位查表：五合、六合、六冲、刑害破、三合、三会及半合。天干冲采用甲庚、乙辛、丙壬、丁癸四组；"
                    "三刑组内两支相刑与三支配齐分列。辰午酉亥须在两个不同位置重复才标记自刑。")
        st.markdown("半合采用含中神的生旺、旺墓配对；申辰、亥未、寅戌、巳丑列为拱合配对。"
                    "同一组的半合与完整三合只说明不同参与位置，不累计折算力量。午未六合的化神暂不预定。")
        st.caption("‘已记录’表示有可核对的命盘线索，不代表合化条件通过。按原局、大运、流年、流月、流日分层；流月不替代出生月令。")
        st.caption("天干生克及刑显示施方→受方。半会采用同会方任意两支配对，两端另标拱会；暗合采用寅丑、卯申、午亥。"
                   "扩展配对参考china-testing/bazi，不按完整合会判化，也不把暗合等同婚恋隐情。")
        st.caption("现实分析由模型结合柱位、十神、喜忌、根气和当前运程提出可能场景、成立条件与反证；关系本身不是具体事件结论。")
        quotes = ("譬如甲与己合，而甲己中间，以庚间隔之，则甲岂能越克我之庚而合己？",
                  "若以两合一而隔位，则全无争妒。", "是会合而不能解刑冲也。")
        try:
            records = load_source_records("子平真诠")
            for quote in quotes:
                record = next((r for r in records if quote in r["text"]), None)
                if record:
                    st.markdown("> " + quote)
                    st.caption(f"《子平真诠》· {record['section']} · 本地原文第 {record['line_number']}—{record['end_line_number']} 行")
        except (OSError, ValueError, KeyError):
            st.info("本地原文依据暂时无法加载，请核对《子平真诠》及篇章位置记录。")
        st.caption("工程结构参考 GitHub 上 bazi-shaoweihua 的岁运触发分层，以及 bazi-engine 的半合识别；本项目独立实现，合化结论仍保留待核。")


def render_professional_chart(chart: dict) -> None:
    # A prior chart or failed calculation must not supply stale periods to AI.
    st.session_state.pop("professional_transit", None)
    natal = []
    day_stem = str(chart["四柱"]["日柱"])[0]
    for name, pillar in chart["四柱"].items():
        column = {"name": name, **describe_pillar(pillar, day_stem, natal_day=name == "日柱")}
        column["stars"] = [s["名称"] for s in chart.get("命局神煞", []) if name in s.get("命中柱位", [])]
        natal.append(column)

    gender = chart.get("性别")
    birth_iso = str(chart.get("公历") or chart.get("专业出生时刻") or "")
    start_sect = 1

    payload = {"natal": natal, "flows": [], "rows": [], "summary": "请在排盘前选择性别，并提供对应出生时刻以计算运程。",
               "relationships": analyze_relationships(chart["四柱"])}
    if not gender or not birth_iso:
        if not gender:
            st.info("请在上方选择性别并重新点击‘开始排盘’。")
        elif not birth_iso:
            st.info("当前仅显示四柱原局；请重新排盘并选择匹配日期，或使用公历、农历方式查看大运。")
        wheel_chart(payload=payload, key=f"professional_empty_{PANEL_VERSION}", default=None)
        _render_relationship_sources()
        return
    try:
        luck = luck_cycles(birth_iso, gender, start_sect)
        if luck["pillars"] != chart["四柱"]:
            st.error("用于运程计算的日期与当前四柱不一致，请重新排盘。")
            wheel_chart(payload=payload, key=f"professional_mismatch_{PANEL_VERSION}", default=None)
            _render_relationship_sources()
            return
        signature = hashlib.sha256(json.dumps([chart["四柱"], birth_iso, gender, start_sect], ensure_ascii=False).encode()).hexdigest()[:16]
        state = st.session_state.get("professional_selection", {})
        if state.get("signature") != signature:
            state = {"signature": signature}
        today = date.today()
        cycles = luck["cycles"]
        default_cycle = next((c for c in cycles if c["start_year"] <= today.year <= c["end_year"]), cycles[0])
        chosen_cycle = next((c for c in cycles if c["id"] == state.get("cycle")), default_cycle)
        years = chosen_cycle["years"]
        chosen_year = next((y for y in years if y["id"] == state.get("year")),
                           next((y for y in years if y["id"] == str(today.year)), years[0]))
        months = flow_months(int(chosen_year["id"]), day_stem)
        now = datetime.now()
        default_month = next((m for m in months if datetime.fromisoformat(m["start"]) <= now < datetime.fromisoformat(m["end"])), months[0])
        chosen_month = next((m for m in months if m["id"] == state.get("month")), default_month)
        days = flow_days(int(chosen_year["id"]), int(chosen_month["id"]), day_stem)
        chosen_day = next((d for d in days if d["id"] == state.get("day")),
                          next((d for d in days if d["id"] == today.isoformat()), days[0]))
        selection = {"cycle": chosen_cycle["id"], "year": chosen_year["id"], "month": chosen_month["id"], "day": chosen_day["id"]}
        state.update(selection)
        st.session_state["professional_selection"] = state
        payload.update({
            "summary": f"出生后 {luck['start_age']} 起运　｜　{luck['start']} 交运　｜　{'顺行' if luck['forward'] else '逆行'} · 按时辰起运",
            "flows": [{"name": "流年", **chosen_year}, {"name": "大运", **chosen_cycle},
                      {"name": "流月", **chosen_month}, {"name": "流日", **chosen_day}],
            "rows": [{"kind": "cycle", "label": "大运", "items": cycles},
                     {"kind": "year", "label": "流年", "items": years},
                     {"kind": "month", "label": "流月", "items": months},
                     {"kind": "day", "label": "流日", "items": days}],
            "selection": selection,
            "relationships": analyze_relationships(
                chart["四柱"], luck_pillar=chosen_cycle["pillar"], annual_pillar=chosen_year["pillar"],
                monthly_pillar=chosen_month["pillar"], daily_pillar=chosen_day["pillar"],
                luck_label=f"大运{chosen_cycle['period']}", annual_label=f"流年{chosen_year['label']}",
                monthly_label=f"流月{chosen_month['label']}（{chosen_month['start']}起）", daily_label=f"流日{chosen_day['id']}"),
            "detail": f"当前流月：{chosen_month['start']} 至 {chosen_month['end']}（不含结束时刻）；流日：{chosen_day['id']}。交节日可能同时出现在相邻两个月。",
        })
        st.session_state["professional_transit"] = {
            "四柱": dict(chart["四柱"]),
            "起运": {"年龄": luck["start_age"], "交运时刻": luck["start"],
                     "顺逆": "顺行" if luck["forward"] else "逆行", "算法": "按时辰起运"},
            "大运": {"干支": chosen_cycle["pillar"], "起始年": chosen_cycle["start_year"],
                     "结束年": chosen_cycle["end_year"], "名称": chosen_cycle["label"]},
            "流年": {"年份": int(chosen_year["id"]), "干支": chosen_year["pillar"]},
            "流月": {"月序": int(chosen_month["id"]), "名称": chosen_month["label"], "干支": chosen_month["pillar"],
                     "起始时刻": chosen_month["start"], "结束时刻": chosen_month["end"]},
            "流日": {"日期": chosen_day["id"], "干支": chosen_day["pillar"]},
        }
        event = wheel_chart(payload=payload, key=f"professional_wheel_{signature}_{PANEL_VERSION}", default=None)
        if isinstance(event, dict) and event.get("event") != state.get("last_event"):
            kind, value = event.get("kind"), str(event.get("value", ""))
            allowed = {row["kind"]: {item["id"] for item in row["items"]} for row in payload["rows"]}
            if isinstance(kind, str) and kind in allowed and value in allowed[kind]:
                state["last_event"] = event.get("event")
                if state.get(kind) != value:
                    state[kind] = value
                    order = ["cycle", "year", "month", "day"]
                    for later in order[order.index(kind) + 1:]:
                        state.pop(later, None)
                    st.session_state["professional_selection"] = state
                    st.rerun()
    except (ValueError, KeyError, IndexError) as error:
        st.session_state.pop("professional_transit", None)
        st.error(f"专业细盘资料暂时无法计算：{error}")
        wheel_chart(payload=payload, key=f"professional_error_{PANEL_VERSION}", default=None)
    _render_relationship_sources()
    st.caption("流动各柱的十神、藏干、星运均以原局日干为基准。神煞暂展示原局已有规则结果；古籍检索仍按原局定位。AI 可选择原局、运年，或运年月日完整范围。")
