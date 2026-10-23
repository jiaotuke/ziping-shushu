"""Offline Android bridge, reusing the project's calendar, books and model protocol."""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime
from pathlib import Path

_state = {}


def initialize(resource_root: str, user_data: str) -> str:
    _state.clear()
    os.environ["ZIPING_RESOURCE_ROOT"] = resource_root
    os.environ["ZIPING_USER_DATA"] = user_data
    import certifi
    os.environ["SSL_CERT_FILE"] = certifi.where()
    return dispatch("catalog", "{}")


def _catalog():
    from ai_analysis import PROVIDERS, STEP_TITLES
    return {"providers": {key: {"name": item["name"], "models": item["models"]} for key, item in PROVIDERS.items()},
            "wechat": "bxzgf-bxbgf", "version": "0.2.0", "steps": STEP_TITLES,
            "retrieval": "本地段落关键词排序（非向量模型）"}


def _calculate(body):
    from bazi import calculate_chart, calculate_lunar_chart, calculate_pillars_chart, convert_to_true_solar_time
    from pillar_relationships import analyze_relationships

    if body.get("gender") not in ("男", "女"):
        raise ValueError("请先选择性别。")
    mode = body.get("calendar", "solar")
    if mode == "pillars":
        chart = calculate_pillars_chart(body["pillars"])
        if body.get("birth"):
            birth = datetime.fromisoformat(body["birth"])
            matched = calculate_chart(birth)
            if matched["四柱"] != chart["四柱"]:
                raise ValueError("选填出生时刻与所选四柱不一致。")
            chart["专业出生时刻"] = birth.isoformat()
    elif mode == "lunar":
        hour, minute = map(int, body["time"].split(":"))
        chart = calculate_lunar_chart(int(body["year"]), int(body["month"]), int(body["day"]), hour, minute,
                                      is_leap_month=bool(body.get("leap")))
    elif mode == "solar":
        birth = datetime.fromisoformat(body["birth"])
        chart = calculate_chart(birth)
        if body.get("longitude") not in (None, ""):
            corrected, offset, equation = convert_to_true_solar_time(birth, float(body["longitude"]),
                                                                   body.get("timezone") or "Asia/Shanghai")
            chart = calculate_chart(corrected, time_basis="已按所填经度、时区修正真太阳时")
            chart["时间修正"] = {"原时刻": birth.isoformat(), "真太阳时": corrected.isoformat(),
                                  "UTC偏移": offset, "均时差分钟": equation}
    else:
        raise ValueError("请选择有效历法。")
    chart["性别"] = body["gender"]
    _state.clear()
    _state["chart"] = chart
    return {"chart": chart, "relationships": analyze_relationships(chart["四柱"])}


def _periods(body):
    from professional_chart import luck_cycles, flow_months, flow_days
    from pillar_relationships import analyze_relationships
    chart = _state.get("chart")
    if not chart:
        raise ValueError("请先排盘。")
    birth = chart.get("公历") or chart.get("专业出生时刻")
    if not birth:
        raise ValueError("仅输入四柱时，请选填匹配的出生时刻后重新排盘，才能计算大运。")
    profile = luck_cycles(birth, chart["性别"], 1)
    if profile["pillars"] != chart["四柱"]:
        raise ValueError("出生资料与四柱不一致。")
    cycles = [c for c in profile["cycles"] if c["years"]]
    today = datetime.now()
    default_cycle = next((c for c in cycles if c["start_year"] <= today.year <= c["end_year"]), cycles[0])
    cycle = next((c for c in cycles if c["id"] == str(body.get("cycle", ""))), default_cycle)
    years = cycle["years"]
    annual = next((y for y in years if y["id"] == str(body.get("year", today.year))), years[0])
    stem = chart["四柱"]["日柱"][0]
    months = flow_months(int(annual["id"]), stem)
    default_month = next((m for m in months if datetime.fromisoformat(m["start"]) <= today < datetime.fromisoformat(m["end"])), months[0])
    month = next((m for m in months if m["id"] == str(body.get("month", ""))), default_month)
    days = flow_days(int(annual["id"]), int(month["id"]), stem)
    day = next((d for d in days if d["id"] == body.get("day", today.date().isoformat())), days[0])
    transit = {"四柱": chart["四柱"],
               "起运": {"年龄": profile["start_age"], "交运时刻": profile["start"],
                        "顺逆": "顺行" if profile["forward"] else "逆行", "算法": "按时辰起运"},
               "大运": {"名称": cycle["label"], "干支": cycle["pillar"], "起始年": cycle["start_year"], "结束年": cycle["end_year"]},
               "流年": {"年份": int(annual["id"]), "干支": annual["pillar"]},
               "流月": {"月序": int(month["id"]), "名称": month["label"], "干支": month["pillar"],
                        "起始时刻": month["start"], "结束时刻": month["end"]},
               "流日": {"日期": day["id"], "干支": day["pillar"]}}
    if _state.get("transit") != transit:
        for key in ("result", "report_sources", "citation_failure", "pending_context"):
            _state.pop(key, None)
    _state["transit"] = transit
    relation = analyze_relationships(chart["四柱"], luck_pillar=cycle["pillar"], annual_pillar=annual["pillar"],
                                     monthly_pillar=month["pillar"], daily_pillar=day["pillar"])
    return {"cycles": cycles, "years": years, "months": months, "days": days,
            "selected": {"cycle": cycle["id"], "year": annual["id"], "month": month["id"], "day": day["id"]},
            "transit": transit, "relationships": relation}


def _retrieve(_body):
    from portable_retrieval import retrieve_chart
    if "chart" not in _state:
        raise ValueError("请先排盘。")
    result = retrieve_chart(_state["chart"])
    _state["retrieval"] = result
    return result


def _scope(body):
    scope = body.get("scope", "natal")
    if scope not in ("natal", "annual", "daily"):
        raise ValueError("请选择有效解读范围。")
    if scope == "natal":
        return None
    if "transit" not in _state:
        raise ValueError("请先在专业细盘中选择大运、流年和需要的月日。")
    transit = json.loads(json.dumps(_state["transit"]))
    if scope == "annual":
        transit.pop("流月", None)
        transit.pop("流日", None)
    return transit


def _generate(body, progress=None):
    from ai_analysis import build_context, generate_report, prepare_context, context_signature
    if not body.get("api_key", "").strip():
        raise ValueError("请填写你自己的模型 API Key。")
    if not _state.get("retrieval", {}).get("success"):
        raise ValueError("请先检索古籍。")
    if _state.get("result"):
        _state.pop("extended_job", None)
    _state.pop("result", None)
    _state.pop("report_sources", None)
    provider, model = body.get("provider", "zhipu"), body.get("model", "glm-4.7-flash")
    context = prepare_context(build_context(_state["chart"], _state["retrieval"], transit=_scope(body)),
                              provider=provider, model=model, thinking=bool(body.get("thinking", True)))
    _state.pop("citation_failure", None)
    _state["pending_context"] = context
    job = _state.get("extended_job", {})
    failed = job.get("pending_draft") if job.get("signature") == context_signature(context, provider=provider, model=model, thinking=bool(body.get("thinking", True))) else None
    result = generate_report(body["api_key"], context, provider=provider, model=model, thinking=bool(body.get("thinking", True)),
                             repair_report=failed["report"] if failed else None, repair_issues=failed["issues"] if failed else None,
                             checkpoint=_state.setdefault("extended_job", {}), progress=progress)
    return _report_result(result, context)


def _report_result(result, context):
    from luck_analysis import claims_in
    from luck_chart import dashboard_document, reasoning_html
    _state.pop("citation_failure", None)
    _state["result"], _state["report_sources"] = result, context["sources"]
    used = {c["source_id"] for claim in claims_in(result["report"]) for c in claim["citations"]}
    return {"result": result, "dashboard_html": dashboard_document(result["report"]),
            "reasoning_html": reasoning_html(result["report"], context["sources"]),
            "sources": [{k: s[k] for k in ("source_id", "book_name", "chapter", "line_number")}
                                           for s in context["sources"] if s["source_id"] in used]}


def _repair(body, progress=None):
    from ai_analysis import generate_report, prepare_context
    failed = _state.get("citation_failure")
    if not failed or not body.get("api_key", "").strip():
        raise ValueError("没有待修正报告，或尚未填写模型密钥。")
    context = prepare_context(_state["pending_context"], provider=body["provider"], model=body["model"],
                              thinking=bool(body.get("thinking", True)))
    result = generate_report(body["api_key"], context, provider=body["provider"], model=body["model"],
                             thinking=bool(body.get("thinking", True)), repair_report=failed["report"],
                             repair_issues=failed["issues"], checkpoint=_state.setdefault("extended_job", {}), progress=progress)
    return _report_result(result, context)


def _translate(body):
    from book_translation import source_plan, generate_translation
    if not body.get("api_key", "").strip():
        raise ValueError("请先在 AI 解读页填写自己的模型密钥。")
    book = body["book"]
    articles = _state.get("retrieval", {}).get("results_by_book", {}).get(book, [])
    index = int(body.get("index", 0))
    if not 0 <= index < len(articles):
        raise ValueError("请先检索并选择有效文章。")
    return generate_translation(body["api_key"], source_plan(book, articles[index]),
                                provider=body.get("provider", "zhipu"), model=body.get("model", "glm-4.7-flash"))


def _export(body):
    from report_downloads import report_exports
    if "result" not in _state:
        raise ValueError("请先生成通过引用校验的报告。")
    extension = body.get("format", "html")
    if extension not in ("html", "txt", "json"):
        raise ValueError("请选择有效格式。")
    data = report_exports(_state["result"], _state["report_sources"])[extension]
    return {"filename": "子平术数-解读报告." + extension, "base64": base64.b64encode(data).decode("ascii"),
            "mime": {"html": "text/html", "txt": "text/plain", "json": "application/json"}[extension]}


def dispatch(method: str, payload: str, progress=None) -> str:
    handlers = {"catalog": lambda _: _catalog(), "calculate": _calculate, "periods": _periods,
                "retrieve": _retrieve, "generate": _generate, "repair": _repair, "translate": _translate, "export": _export}
    try:
        if method not in handlers or len(payload) > 50000:
            raise ValueError("不支持的操作。")
        body = json.loads(payload)
        if method in ("generate", "repair"):
            listener = (lambda done, total, label: progress.update(f"{done}/{total} · {label}")) if progress is not None else None
            value = handlers[method](body, progress=listener)
        else:
            value = handlers[method](body)
        return json.dumps({"ok": True, "value": value}, ensure_ascii=False)
    except (ValueError, KeyError, TypeError, OSError) as error:
        message = str(error)[:450] if isinstance(error, ValueError) else "资料不完整或本地文件暂不可用，请重新排盘。"
        repair_available = hasattr(error, "report") and hasattr(error, "issues")
        if repair_available:
            _state["citation_failure"] = {"report": error.report, "issues": error.issues}
        elif method in ("generate", "repair") and _state.get("extended_job", {}).get("pending_draft"):
            _state["citation_failure"] = _state["extended_job"]["pending_draft"]
            repair_available = True
        return json.dumps({"ok": False, "error": message, "repair_available": repair_available}, ensure_ascii=False)
    except Exception:
        return json.dumps({"ok": False, "error": "当前操作未完成，请重新打开应用或核对输入资料。"}, ensure_ascii=False)
