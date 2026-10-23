"""WeChat consultation entry; no collection codes, orders or payment APIs."""

from __future__ import annotations

import hashlib
import html
import json
from datetime import date, datetime

import streamlit as st

WECHAT_ID = "bxzgf-bxbgf"
PLANS = (
    {"id": "natal", "title": "原局解读", "price": "6.90", "description": "原局八步分析，结合古籍梳理旺衰、格局与取用。"},
    {"id": "annual", "title": "大运流年", "price": "12.90", "description": "原局、前六步大运详解与评分K线，再详解选定流年。"},
    {"id": "daily", "title": "运年月日详解", "price": "19.90", "description": "原局、前六步大运与评分K线，再详解选定流年、流月、流日。"},
)


def _select_plan(plan_id: str) -> None:
    st.session_state["paid_selected_plan"] = plan_id


def _esc(value) -> str:
    return html.escape(str(value))



def _change_period(kind: str, widget_key: str, signature: str) -> None:
    state = st.session_state.get("paid_period_selection", {})
    if state.get("signature") != signature:
        return
    value = st.session_state[widget_key]
    if state.get(kind) == value:
        return
    state[kind] = value
    order = ("cycle", "year", "month", "day")
    for later in order[order.index(kind) + 1:]:
        state.pop(later, None)
    st.session_state["paid_period_selection"] = state



def _pick_period(label: str, kind: str, items: list[dict], state: dict, default: dict,
                 parents: str, format_item) -> dict:
    options = [item["id"] for item in items]
    by_id = {item["id"]: item for item in items}
    preferred = state.get(kind) if state.get(kind) in by_id else default["id"]
    key = f"paid_pick_{state['signature']}_{kind}_{parents}"
    chosen = st.selectbox(label, options, index=options.index(preferred),
                          format_func=lambda value: format_item(by_id[value]), key=key,
                          on_change=_change_period, args=(kind, key, state["signature"]))
    state[kind] = chosen
    return by_id[chosen]



def _render_period_selector(chart: dict, plan_id: str, seed: dict | None) -> tuple[dict | None, str | None]:
    """Keep paid choices independent; use professional choices only as an initial seed."""
    if plan_id == "natal":
        return None, None
    from professional_chart import flow_days, flow_months, luck_cycles

    st.markdown("#### 选择本次解读时间")
    st.caption("先选大运，再选其中的流年；详细套餐可继续选择流月、流日。")
    birth = str(chart.get("公历") or chart.get("专业出生时刻") or "")
    gender = chart.get("性别")
    if not birth or gender not in ("男", "女"):
        return None, "计算大运需要出生时刻和性别。请先补齐出生资料并重新排盘，随后可直接在本页选择时间。"
    try:
        profile = luck_cycles(birth, gender, 1)
        if profile["pillars"] != chart.get("四柱"):
            return None, "出生时刻与当前四柱不一致，请核对出生资料后重新排盘。"
        cycles = [c for c in profile["cycles"] if c["years"]]
        if not cycles:
            return None, "当前出生资料未能计算出可选大运，请核对出生时刻。"
        signature = hashlib.sha256(json.dumps([chart["四柱"], birth, gender, 1], ensure_ascii=False,
                                               sort_keys=True).encode("utf-8")).hexdigest()[:16]
        state = st.session_state.get("paid_period_selection", {})
        if state.get("signature") != signature:
            state = {"signature": signature}
            if isinstance(seed, dict) and seed.get("四柱") == chart["四柱"]:
                seed_cycle = seed.get("大运", {})
                initial_cycle = next((c for c in cycles if c["pillar"] == seed_cycle.get("干支")
                                      and c["start_year"] == seed_cycle.get("起始年")
                                      and c["end_year"] == seed_cycle.get("结束年")), None)
                if initial_cycle:
                    state.update(cycle=initial_cycle["id"], year=str(seed.get("流年", {}).get("年份", "")))
                    seed_month = seed.get("流月", {})
                    state["month"] = str(seed_month.get("月序", ""))
                    state["day"] = seed.get("流日", {}).get("日期", "")
        st.session_state["paid_period_selection"] = state
        today = date.today()
        now = datetime.now()
        default_cycle = next((c for c in cycles if c["start_year"] <= today.year <= c["end_year"]), cycles[0])
        cycle_col, year_col = st.columns(2)
        with cycle_col:
            cycle = _pick_period("大运", "cycle", cycles, state, default_cycle, "root",
                                 lambda c: f"{c['pillar'] or '未起运'} · {c['period']} · {c['note']}")
        years = cycle["years"]
        default_year = next((y for y in years if y["id"] == str(today.year)), years[0])
        with year_col:
            year = _pick_period("流年", "year", years, state, default_year, cycle["id"],
                                lambda y: f"{y['id']}年 · {y['pillar']} · {y['note']}")
        chosen = {
            "四柱": dict(chart["四柱"]),
            "起运": {"年龄": profile["start_age"], "交运时刻": profile["start"],
                     "顺逆": "顺行" if profile["forward"] else "逆行", "算法": "按时辰起运"},
            "大运": {"名称": cycle["label"], "干支": cycle["pillar"],
                     "起始年": cycle["start_year"], "结束年": cycle["end_year"]},
            "流年": {"年份": int(year["id"]), "干支": year["pillar"]},
        }
        if plan_id == "daily":
            day_stem = chart["四柱"]["日柱"][0]
            months = flow_months(int(year["id"]), day_stem)
            default_month = next((m for m in months if datetime.fromisoformat(m["start"]) <= now
                                  < datetime.fromisoformat(m["end"])), months[0])
            month_col, day_col = st.columns(2)
            with month_col:
                month = _pick_period("流月（按节气）", "month", months, state, default_month,
                                     cycle["id"] + "_" + year["id"],
                                     lambda m: f"{m['label']} · {m['pillar']} · {m['period']}")
            days = flow_days(int(year["id"]), int(month["id"]), day_stem)
            default_day = next((d for d in days if d["id"] == today.isoformat()), days[0])
            with day_col:
                day = _pick_period("流日", "day", days, state, default_day,
                                   cycle["id"] + "_" + year["id"] + "_" + month["id"],
                                   lambda d: f"{d['id']} · {d['pillar']} · {d['note']}")
            chosen["流月"] = {"月序": int(month["id"]), "名称": month["label"], "干支": month["pillar"],
                              "起始时刻": month["start"], "结束时刻": month["end"]}
            chosen["流日"] = {"日期": day["id"], "干支": day["pillar"]}
            st.caption(f"当前节月：{month['start']} 至 {month['end']}，不含结束时刻。交节日可能出现在相邻两个月。")
        st.session_state["paid_period_selection"] = state
        st.caption("起运按时辰计算。大运年份沿用虚岁编排，交运当年仍需核对精确交接时刻。")
        return chosen, None
    except (ValueError, KeyError, IndexError, TypeError):
        return None, "当前时间范围暂时无法计算，请核对出生资料并重新排盘。"



def _scope(chart: dict, plan_id: str, transit: dict | None) -> tuple[list[tuple[str, str]], str | None]:
    rows = [("解读内容", "原局八步分析 · 关系现实表现 · 古籍引用与待核条件")]
    if plan_id == "natal":
        return rows, None
    if not isinstance(transit, dict) or transit.get("四柱") != chart.get("四柱"):
        return rows, "请先补齐出生时刻和性别，再在本页选择大运、流年。"
    cycle, annual = transit.get("大运", {}), transit.get("流年", {})
    if not all(k in cycle for k in ("干支", "起始年", "结束年")) or not all(k in annual for k in ("年份", "干支")):
        return rows, "当前岁运资料不完整，请在本页重新选择大运、流年。"
    rows += [("完整大运", "起运后的前六步正式大运 · 综合评分 · 子平K线 · 事业/财务/感情分项"),
             ("所选流年所在大运", f"{cycle['干支'] or '未起运'} · {cycle['起始年']}—{cycle['结束年']}"),
             ("选定流年", f"{annual['年份']}年 · {annual['干支']}")]
    if plan_id == "daily":
        month, day = transit.get("流月", {}), transit.get("流日", {})
        if not all(k in month for k in ("名称", "干支", "起始时刻", "结束时刻")) or not all(k in day for k in ("日期", "干支")):
            return rows, "请先在本页选择流月、流日，再确认详细解读。"
        rows += [("选定流月", f"{month['名称']} · {month['干支']}"),
                 ("节月区间", f"{month['起始时刻']} 至 {month['结束时刻']}，不含结束时刻"),
                 ("选定流日", f"{day['日期']} · {day['干支']}")]
    return rows, None



def render_paid_panel(chart: dict, retrieval: dict | None, *, transit: dict | None = None,
                      preview_only: bool = False) -> None:
    # Discard obsolete payment handles left in sessions from the removed checkout UI.
    for key in ("paid_current_order", "paid_recent_orders", "paid_creation_tokens", "paid_preview_order"):
        st.session_state.pop(key, None)
    st.markdown("""
    <style>
    .consult-intro {color:#aaa69d;font-size:14px;line-height:1.9;margin-bottom:18px}
    .consult-heading {font:25px/1.6 serif;color:#ead7ad;margin:6px 0 12px}
    .consult-title {font:21px/1.6 serif;color:#ead7ad;margin-bottom:10px}
    .consult-price {font:30px/1.6 Georgia,serif;color:#dfbf85}
    .consult-price small {font:12px sans-serif;color:#99948a;margin-left:7px}
    .consult-description {font-size:13px;line-height:1.9;color:#aaa69d;min-height:72px;margin:10px 0}
    .consult-scope {display:grid;grid-template-columns:70px 1fr;gap:10px;margin:8px 0;font-size:14px;line-height:1.8}
    .consult-scope span {color:#99948a}
    [class*="st-key-consult_card_"] {background:#17181b;border-color:#3d3a32!important;border-radius:14px!important}
    [class*="st-key-consult_card_"]:has(.consult-selected) {border-color:#bd9558!important;background:#292319}
    @media(max-width:640px){.consult-description{min-height:0}}
    </style>
    """, unsafe_allow_html=True)
    st.subheader("付费解读")
    st.caption("不熟悉大模型 API、密钥申请或接入操作？可以添加作者微信，咨询付费解读。")
    with st.container(border=True, key="consult_wechat_contact"):
        st.markdown('<div class="consult-heading">添加作者微信</div>', unsafe_allow_html=True)
        st.code(WECHAT_ID, language=None)
        st.caption("点击右侧复制图标，打开微信搜索添加；添加时请备注「子平术数」。")
        st.write("解读范围、费用与交付方式，请添加微信后沟通确认。")
    st.markdown('<div class="consult-intro">可先选择希望咨询的范围，再通过微信与作者沟通。</div>', unsafe_allow_html=True)
    selected = st.session_state.get("paid_selected_plan", "annual")
    if selected not in {p["id"] for p in PLANS}:
        selected = "natal"
    st.session_state["paid_selected_plan"] = selected
    for col, plan in zip(st.columns(3), PLANS):
        active = selected == plan["id"]
        with col, st.container(border=True, key="consult_card_" + plan["id"]):
            st.markdown(f'<div class="{"consult-selected" if active else ""}">'
                        f'<div class="consult-title">{plan["title"]}</div>'
                        f'<div class="consult-price">¥{plan["price"]}<small>参考 / 份</small></div>'
                        f'<div class="consult-description">{plan["description"]}</div></div>', unsafe_allow_html=True)
            st.button("已选择" if active else "选择咨询范围", type="primary" if active else "secondary",
                      key="consult_choose_" + plan["id"], use_container_width=True,
                      on_click=_select_plan, args=(plan["id"],))
    st.caption("以上为参考价格，具体费用与交付安排在微信确认。基础排盘、古籍检索及自备模型功能可继续使用。")
    if transit is None:
        transit = st.session_state.get("professional_transit")
    chosen, selector_error = _render_period_selector(chart, selected, transit)
    rows, unavailable = _scope(chart, selected, chosen)
    with st.container(border=True):
        st.markdown("#### 本次咨询范围")
        pillars = chart.get("四柱", {})
        st.write("四柱：" + "　".join(str(pillars.get(k, "—")) for k in ("年柱", "月柱", "日柱", "时柱")))
        for label, value in rows:
            st.markdown(f'<div class="consult-scope"><span>{_esc(label)}</span><div>{_esc(value)}</div></div>', unsafe_allow_html=True)
        if selector_error or unavailable:
            st.info(selector_error or unavailable)
        st.caption("可将选定范围告知作者。此页面仅展示咨询信息，联系微信：" + WECHAT_ID)
    if preview_only:
        st.caption("当前使用演示命盘预览咨询入口，不影响你的实际排盘资料。")


def preview_data() -> tuple[dict, dict]:
    """Synthetic birth data for the standalone UI route; never changes the real chart session."""
    from bazi import calculate_chart
    from professional_chart import flow_days, flow_months, luck_cycles

    chart = calculate_chart(datetime(1990, 6, 15, 12))
    chart["性别"] = "男"
    profile = luck_cycles("1990-06-15T12:00:00", "男")
    cycle = next(c for c in profile["cycles"] if c["start_year"] <= 2026 <= c["end_year"])
    annual = next(y for y in cycle["years"] if y["id"] == "2026")
    stem = chart["四柱"]["日柱"][0]
    month = flow_months(2026, stem)[8]
    day = flow_days(2026, 8, stem)[0]
    transit = {
        "四柱": chart["四柱"],
        "大运": {"干支": cycle["pillar"], "起始年": cycle["start_year"], "结束年": cycle["end_year"]},
        "流年": {"年份": 2026, "干支": annual["pillar"]},
        "流月": {"月序": 8, "名称": month["label"], "干支": month["pillar"], "起始时刻": month["start"], "结束时刻": month["end"]},
        "流日": {"日期": day["id"], "干支": day["pillar"]},
    }
    return chart, transit

