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
            "wechat": "bxzgf-bxbgf", "version": "0.7.0", "steps": STEP_TITLES,
            "retrieval": "本地段落关键词排序（非向量模型）"}


def _calculate(body):
    from bazi import calculate_chart, calculate_lunar_chart, calculate_pillars_chart, convert_to_true_solar_time
    from pillar_relationships import analyze_relationships

    if body.get("gender") not in ("男", "女"):
        raise ValueError("请先选择性别。")
    mode = body.get("calendar", "solar")
    if mode == "pillars":
        from bazi import find_pillar_birth_times
        names = ("年柱", "月柱", "日柱", "时柱")
        chart = calculate_pillars_chart(body["pillars"])
        matches = find_pillar_birth_times(*(chart["四柱"][name] for name in names), datetime.now().date())
        if not matches:
            raise ValueError("1800年至今未找到匹配日期，请核对四柱。")
        chosen = body.get("matched_birth")
        if len(matches) > 1 and chosen not in matches:
            return {"birth_choices": list(matches)}
        chosen = chosen if chosen in matches else matches[0]
        chart["专业出生时刻"] = chosen
        chart["时间说明"] = "按四柱自动反查，采用所选日期及该时柱默认时刻。"
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
        raise ValueError("仅输入四柱时，请重新排盘并选择反查日期，才能计算大运。")
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


def _workspace(body):
    from ai_analysis import build_context, prepare_context
    from analysis_workflow import calendar_plan, workspace_key
    from report_import import birth_profile, chart_identity
    if not _state.get("chart"):
        raise ValueError("请先排盘。")
    if not _state.get("retrieval", {}).get("success"):
        _retrieve({})
    provider, model = body.get("provider", "zhipu"), body.get("model", "glm-4.7-flash")
    thinking = bool(body.get("thinking", True))
    settings = dict(provider=provider, model=model, thinking=thinking, custom_window=None, opener=None)
    context = prepare_context(build_context(_state["chart"], _state["retrieval"]),
                              provider=provider, model=model, thinking=thinking)
    identity = workspace_key(context, _state["chart"], provider=provider, model=model, thinking=thinking)
    selected = _state.get("imports", {}).get(identity, identity) if body.get("scope") == "date" else identity
    job = _state.setdefault("workspaces", {}).setdefault(selected, {"cycles": {}, "dates": {}})
    job.setdefault("chart_identity", chart_identity(_state["chart"]))
    job.setdefault("birth_profile", birth_profile(_state["chart"]))
    plan = calendar_plan(_state["chart"]) if body.get("scope", "natal") != "natal" else None
    return context, job, plan, settings, identity


def _status(body):
    from analysis_workflow import assemble_report, next_basis_stage
    from luck_analysis import report_cycles
    context, job, plan, settings, identity = _workspace(body)
    pending = next_basis_stage(job, plan)
    result = assemble_report(job, plan=plan)
    total = 1 + (len(report_cycles(plan)) if plan else 0)
    done = int("base" in job) + (sum(c["id"] in job.get("cycles", {}) for c in report_cycles(plan)) if plan else 0)
    value = {"complete": pending is None, "next": pending[1] if pending else "基础报告已完成",
             "done": done, "total": total, "imported": job.get("imported_basis", {}).get("warnings", []),
             "history": [{"id": key, "label": item.get("label", key[:10])} for key, item in job.get("dates", {}).items() if item.get("parts")]}
    if result:
        value.update(_report_result(result, context, store=bool(body.get("view_basis"))))
    return value


def _generate(body, progress=None):
    from analysis_workflow import advance_basis, advance_date, assemble_report, date_key, next_basis_stage
    from period_text import period_scope
    if not body.get("api_key", "").strip():
        raise ValueError("请填写你自己的模型 API Key。")
    context, job, plan, settings, identity = _workspace(body)
    if progress:
        progress(0, 1, "正在完成当前阶段，结束后保存；可暂停后续阶段")
    if body.get("operation") == "date":
        level = body.get("level", "annual")
        if level not in ("annual", "monthly", "daily") or body.get("scope") != "date":
            raise ValueError("请选择有效的时间详解层级。")
        if next_basis_stage(job, plan):
            raise ValueError("请先完成或导入基础报告。")
        if "transit" not in _state:
            _periods({})
        transit = json.loads(json.dumps(_state["transit"]))
        if level == "annual":
            transit.pop("流月", None)
        if level != "daily":
            transit.pop("流日", None)
        key = date_key(transit, level)
        date_job = job.setdefault("dates", {}).setdefault(key, {"parts": {}, "levels": [level], "transit": transit})
        advance_date(body["api_key"], context, job, date_job, transit=transit, plan=plan, **settings)
        date_job["label"] = {"annual": "流年", "monthly": "流月", "daily": "流日"}[level] + " · " + period_scope(transit)
        return {**_report_result(assemble_report(job, date_job=date_job), context), "complete": True}
    advance_basis(body["api_key"], context, job, plan=plan, **settings)
    return _status({**body, "view_basis": True})


def _report_result(result, context, *, store=True):
    from luck_chart import dashboard_document, reasoning_html, results_html
    sources = list({item["source_id"]: item for item in [*context["sources"], *result.get("additional_sources", [])]}.values())
    if store:
        _state["result"], _state["report_sources"] = result, sources
    period = result["report"].get("kind") == "period-only"
    return {"dashboard_html": None if period else dashboard_document(result["report"]),
            "results_html": results_html(result["report"]) if period else "",
            "reasoning_html": reasoning_html(result["report"], sources),
            "retrieval_trace": result.get("retrieval_trace", [])}


def _history(body):
    from analysis_workflow import assemble_report
    context, job, plan, settings, identity = _workspace(body)
    saved = job.get("dates", {}).get(body.get("id"))
    if not saved or not saved.get("parts"):
        raise ValueError("本次会话未保存该专项报告。")
    return _report_result(assemble_report(job, date_job=saved), context)


def _import(body):
    import hashlib
    from report_import import import_report, MAX_REPORT_BYTES
    if not body.get("confirmed") or body.get("scope") != "date":
        raise ValueError("请先选择第三档，确认报告对应当前出生资料与性别。")
    raw = base64.b64decode(body.get("base64", ""), validate=True)
    if not raw or len(raw) > MAX_REPORT_BYTES:
        raise ValueError("请选择不超过2MB的报告。")
    context, job, plan, settings, identity = _workspace(body)
    imported = import_report(raw, body["filename"], chart=_state["chart"], context=context, plan=plan)
    key = identity + "_import_" + hashlib.sha256(raw).hexdigest()
    _state["workspaces"].setdefault(key, imported)
    _state.setdefault("imports", {})[identity] = key
    return _status({**body, "view_basis": True})


def _leave_import(body):
    context, job, plan, settings, identity = _workspace(body)
    _state.setdefault("imports", {}).pop(identity, None)
    return _status(body)


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
    from report_downloads import report_exports, report_filename
    if "result" not in _state:
        raise ValueError("请先生成通过引用校验的报告。")
    extension = body.get("format", "html")
    if extension not in ("html", "txt", "json"):
        raise ValueError("请选择有效格式。")
    data = report_exports(_state["result"], _state["report_sources"])[extension]
    return {"filename": report_filename(_state["result"]["report"]) + "." + extension, "base64": base64.b64encode(data).decode("ascii"),
            "mime": {"html": "text/html", "txt": "text/plain", "json": "application/json"}[extension]}


def dispatch(method: str, payload: str, progress=None) -> str:
    handlers = {"catalog": lambda _: _catalog(), "calculate": _calculate, "periods": _periods,
                "retrieve": _retrieve, "generate": _generate, "status": _status, "history": _history,
                "import": _import, "leave_import": _leave_import, "translate": _translate, "export": _export}
    try:
        if method not in handlers or len(payload) > (2_750_000 if method == "import" else 50000):
            raise ValueError("不支持的操作。")
        body = json.loads(payload)
        if method == "generate":
            listener = (lambda done, total, label: progress.update(f"{done}/{total} · {label}")) if progress is not None else None
            value = handlers[method](body, progress=listener)
        else:
            value = handlers[method](body)
        return json.dumps({"ok": True, "value": value}, ensure_ascii=False)
    except (ValueError, KeyError, TypeError, OSError) as error:
        message = str(error)[:450] if isinstance(error, ValueError) else "资料不完整或本地文件暂不可用，请重新排盘。"
        return json.dumps({"ok": False, "error": message}, ensure_ascii=False)
    except Exception:
        return json.dumps({"ok": False, "error": "当前操作未完成，请重新打开应用或核对输入资料。"}, ensure_ascii=False)
