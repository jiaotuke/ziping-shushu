"""One dependent period selector shared by paid and self-key analysis."""
from datetime import date, datetime
import hashlib
import json

import streamlit as st
from professional_chart import flow_days, flow_months, luck_cycles

from period_text import PERIOD_LABELS, period_scope

def render_analysis_level(*, key, disabled=False):
    return st.radio("专项解读范围", list(PERIOD_LABELS), horizontal=True,
                    format_func=lambda level: "仅分析"+PERIOD_LABELS[level], key=key, disabled=disabled)


def _changed(state_key, kind, widget):
    state = st.session_state[state_key]
    state[kind] = st.session_state[widget]
    order = ("cycle", "year", "month", "day")
    for child in order[order.index(kind)+1:]:
        state.pop(child, None)


def render_period_selector(chart, *, key, seed=None, disabled=False, level="daily"):
    if level not in PERIOD_LABELS:
        raise ValueError("Unknown analysis level")
    birth = str(chart.get("公历") or chart.get("专业出生时刻") or "")
    gender = chart.get("性别")
    if not birth or gender not in ("男", "女"):
        return None, "选择大运及年月日需要有效出生资料和性别，请先重新排盘。"
    try:
        profile = luck_cycles(birth, gender, 1)
        if profile["pillars"] != chart["四柱"]:
            return None, "出生资料与当前四柱不一致，请重新排盘。"
        cycles = [c for c in profile["cycles"] if c["years"]]
        signature = hashlib.sha256(json.dumps([chart["四柱"], birth, gender], sort_keys=True).encode()).hexdigest()[:16]
        state_key = key + "_selection_" + signature
        state = st.session_state.setdefault(state_key, {})
        if not state and isinstance(seed, dict) and seed.get("四柱") == chart["四柱"]:
            matching = next((c for c in cycles if c["pillar"] == seed.get("大运", {}).get("干支")
                             and c["start_year"] == seed.get("大运", {}).get("起始年")), None)
            if matching:
                state.update(cycle=matching["id"], year=str(seed.get("流年", {}).get("年份", "")),
                             month=str(seed.get("流月", {}).get("月序", "")), day=seed.get("流日", {}).get("日期", ""))
        def choose(label, kind, items, default, parent, formatter):
            by_id = {item["id"]: item for item in items}
            preferred = state.get(kind) if state.get(kind) in by_id else default["id"]
            widget = key + "_pick_" + signature + "_" + kind + "_" + parent
            # The parent is part of the widget key, so stale child values cannot replay.
            value = st.selectbox(label, list(by_id), index=list(by_id).index(preferred),
                                 format_func=lambda item: formatter(by_id[item]), key=widget,
                                 on_change=_changed, args=(state_key, kind, widget), disabled=disabled)
            state[kind] = value
            return by_id[value]
        today, now = date.today(), datetime.now()
        left, right = st.columns(2)
        with left:
            cycle = choose("大运", "cycle", cycles,
                           next((c for c in cycles if c["start_year"] <= today.year <= c["end_year"]), cycles[0]),
                           "root", lambda c: f"{c['pillar'] or '未起运'} · {c['period']} · {c['note']}")
        with right:
            year = choose("流年", "year", cycle["years"],
                          next((y for y in cycle["years"] if y["id"] == str(today.year)), cycle["years"][0]),
                          cycle["id"], lambda y: f"{y['id']}年 · {y['pillar']} · {y['note']}")
        selection = {"四柱": dict(chart["四柱"]),
                     "起运": {"年龄": profile["start_age"], "交运时刻": profile["start"], "顺逆": "顺行" if profile["forward"] else "逆行", "算法": "按时辰起运"},
                     "大运": {"名称": cycle["label"], "干支": cycle["pillar"], "起始年": cycle["start_year"], "结束年": cycle["end_year"]},
                     "流年": {"年份": int(year["id"]), "干支": year["pillar"]}}
        if level == "annual":
            return selection, None
        day_stem = chart["四柱"]["日柱"][0]
        months = flow_months(int(year["id"]), day_stem)
        left, right = st.columns(2)
        with left:
            month = choose("流月（按节气）", "month", months,
                           next((m for m in months if datetime.fromisoformat(m["start"]) <= now < datetime.fromisoformat(m["end"])), months[0]),
                           cycle["id"] + "_" + year["id"], lambda m: f"{m['label']} · {m['pillar']} · {m['period']}")
        selection["流月"] = {"月序": int(month["id"]), "名称": month["label"], "干支": month["pillar"], "起始时刻": month["start"], "结束时刻": month["end"]}
        if level == "daily":
            days = flow_days(int(year["id"]), int(month["id"]), day_stem)
            with right:
                day = choose("流日", "day", days, next((d for d in days if d["id"] == today.isoformat()), days[0]),
                             cycle["id"] + "_" + year["id"] + "_" + month["id"], lambda d: f"{d['id']} · {d['pillar']} · {d['note']}")
            selection["流日"] = {"日期": day["id"], "干支": day["pillar"]}
        st.caption(f"节月范围：{month['start']} 至 {month['end']}，不含结束时刻；交节日按具体交节时刻核对。")
        return selection, None
    except (ValueError, KeyError, IndexError, TypeError):
        return None, "当前时间范围无法计算，请核对出生资料。"
