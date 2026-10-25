"""Simple consultation UI with equal cards and a shared full-period selector."""
from __future__ import annotations
import html
from datetime import datetime
import re
import streamlit as st
from period_selection import period_scope, render_period_selector, render_analysis_level, PERIOD_LABELS
from referral_common import PLANS, WECHAT_ID, NATAL_PRICE, LUCK_PRICE, PERIOD_FEE


def _select_plan(plan_id):
    st.session_state["paid_selected_plan"] = plan_id


def render_paid_panel(chart, retrieval=None, *, transit=None, preview_only=False):
    from referral_public_panel import render_consultation_ticket
    st.subheader("付费解读")
    st.caption("不熟悉 API 大模型操作，或想联系作者本人，可以添加作者的私人微信进行付费解读。")
    with st.container(border=True, key="consult_wechat_contact"):
        st.markdown("#### 作者私人微信")
        st.code(WECHAT_ID, language=None)
        st.caption("先选择解读范围，登记后复制详细信息备注。")
    st.markdown("""<style>
    [class*="st-key-consult_card_"] {border-radius:16px!important;background:#17181b}
    .consult-card-copy {display:grid;grid-template-rows:58px 74px 105px;gap:10px}
    .consult-title {font:20px/1.45 serif;color:#ead7ad;overflow-wrap:anywhere}
    .consult-pricing {display:flex;flex-direction:column;justify-content:flex-start;gap:4px}
    .consult-amount {font-family:Arial,Helvetica,"Microsoft YaHei",sans-serif!important;font-size:32px!important;font-weight:600;font-style:normal!important;line-height:1.3;white-space:nowrap;color:#dfbf85;font-variant-numeric:lining-nums tabular-nums;font-feature-settings:"lnum" 1,"tnum" 1}
    .consult-unit {font-family:Arial,"Microsoft YaHei",sans-serif;font-size:14px;line-height:1.7;color:#c5b18b}
    .consult-description {font-size:14px;line-height:1.85;color:#aaa69d;margin:0}
    </style>""", unsafe_allow_html=True)
    selected = st.session_state.get("paid_selected_plan", "luck_v7")
    if selected not in {plan["id"] for plan in PLANS}:
        selected = "luck_v7"
    st.session_state["paid_selected_plan"] = selected
    st.markdown("#### 选择解读范围")
    for col, plan in zip(st.columns(3, gap="medium"), PLANS):
        with col, st.container(border=True, height=380, vertical_alignment="distribute", key="consult_card_"+plan["id"]):
            title = "原局＋大运<br>＋指定年月日详解" if plan["id"] == "date_v7" else html.escape(plan["title"])
            amount = NATAL_PRICE if plan["id"] == "natal_v7" else LUCK_PRICE
            unit = "每份原局解读" if plan["id"] == "natal_v7" else "原局与大运基础报告"
            if plan["id"] == "date_v7":
                unit = "＋年／月／日各" + PERIOD_FEE + "元 / 次"
            copy = ('<div class="consult-card-copy"><div class="consult-title">'+title+'</div>'
                    '<div class="consult-pricing"><div class="consult-amount">¥'+amount+'</div>'
                    '<div class="consult-unit">'+unit+'</div></div>'
                    '<div class="consult-description">'+html.escape(plan["description"])+"</div></div>")
            st.markdown(copy, unsafe_allow_html=True)
            st.button("已选择" if selected == plan["id"] else "选择此范围", key="consult_choose_"+plan["id"],
                      type="primary" if selected == plan["id"] else "secondary", width="stretch",
                      on_click=_select_plan, args=(plan["id"],))
    if selected == "date_v7":
        st.markdown("#### 选择年／月／日专项")
        st.write("年、月、日可分别选择，每次仅登记所选的一项，2元/次；大运及上层时间作为分析背景。")
        level = render_analysis_level(key="paid_v7_level")
        chosen, error = render_period_selector(chart, key="paid_v7", seed=transit, level=level)
        if error:
            st.info(error)
        if chosen:
            scope = "仅分析"+PERIOD_LABELS[level]+" · "+period_scope(chosen)+" · 专项参考费"+PERIOD_FEE+"元/次"
            st.write(scope)
            st.caption("基础报告"+LUCK_PRICE+"元；已有基础报告后，年、月、日专项各"+PERIOD_FEE+"元/次，三项分别登记共6元。可重复选择，微信人工确认费用与交付。")
            details = {"scope":scope}
            if "流日" in chosen:
                details["date"] = chosen["流日"]["日期"]
            parent = st.session_state.get("paid_v7_parent_id", "")
            if isinstance(parent, str) and re.fullmatch(r"ZP[A-F0-9]{12}", parent):
                details["parent_id"] = parent
            render_consultation_ticket("date_v7", key="paid_v7_period", preview_only=preview_only,
                                      details=details, compact=True, button_label="登记流"+PERIOD_LABELS[level]+"详解 · "+PERIOD_FEE+"元")
    else:
        st.markdown("#### 登记咨询")
        if selected == "natal_v7":
            st.write("原局八步解读，"+NATAL_PRICE+"元。")
        else:
            st.write("原局＋大运，含运内流年趋势、评分与子平K线，"+LUCK_PRICE+"元；不默认专项详解指定某一年。")
        ticket = render_consultation_ticket(selected, key="paid_v7_basis", preview_only=preview_only,
                                             compact=True, button_label="登记咨询")
        if ticket and selected == "luck_v7":
            st.session_state["paid_v7_parent_id"] = ticket["id"]


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

