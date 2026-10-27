"""Version seven: one saved stage per action, stable basis, independent date reports."""
from __future__ import annotations
import copy
import hashlib
import json

from ai_analysis import AIError, _auto_repair_stage, _generate_report_once, build_context, context_signature
from luck_analysis import FACTORS, SCORE_NOTE, _focus, _generate_detail, build_luck_plan, calculate_scores, report_cycles

WORKFLOW_VERSION = "ziping-v7-basis-and-dates"
DATE_LEVELS = ("annual", "monthly", "daily")


def workspace_key(context, chart, *, provider, model, thinking):
    signature = context_signature(context, provider=provider, model=model, thinking=thinking)
    identity = [WORKFLOW_VERSION, signature, chart.get("公历") or chart.get("专业出生时刻"), chart.get("性别")]
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()


def next_basis_stage(job, plan=None):
    if job.get("imported_basis") and "base" in job:
        return None
    if "base" not in job:
        return "base", "原局八步与分析基线", None
    for cycle in report_cycles(plan) if plan else []:
        if cycle["id"] not in job.get("cycles", {}):
            return "luck:" + cycle["id"], f"{cycle['label']} · {cycle['pillar']} · {cycle['start_year']}—{cycle['end_year']}", cycle
    return None


def _repair(job, stage_id):
    saved = job.get("pending_draft", {})
    draft = saved.get("report")
    if not draft or (draft.get("_stage", "base") if isinstance(draft, dict) else "base") != stage_id:
        return None, None
    return draft, saved.get("issues", [])


def _detail(api_key, context, base, focus, facts, job, settings):
    draft, issues = _repair(job, focus["id"])
    def generate(saved, problems):
        repair = None
        if saved and saved.get("_stage") == focus["id"]:
            repair = {"draft": saved["payload"], "issues": problems or []}
            if "source_ids" in saved:
                repair["source_ids"] = saved["source_ids"]
        return _generate_detail(api_key, context, base, focus, facts, repair=repair, **settings)
    return _auto_repair_stage(generate, repair_report=draft, repair_issues=issues, checkpoint=job)


def advance_basis(api_key, context, job, *, plan=None, **settings):
    """Execute a single stage. The caller decides whether to request another."""
    pending = next_basis_stage(job, plan)
    if pending is None:
        return
    stage_id, label, cycle = pending
    job["stage"] = {"id": stage_id, "label": label, "status": "running"}
    if cycle is None:
        draft, issues = _repair(job, stage_id)
        job["base"] = _auto_repair_stage(
            lambda saved, problems: _generate_report_once(api_key, context, repair_report=saved, repair_issues=problems, **settings),
            repair_report=draft, repair_issues=issues, checkpoint=job)
    else:
        # The basis includes yearly trends and scores within each decade, but
        # does not launch the separate selected annual/monthly/daily stages.
        facts, focus = _focus(context, cycle)
        part = _detail(api_key, context, job["base"], focus, facts, job, settings)
        part["document"] = calculate_scores(part["document"], cycle)
        job.setdefault("cycles", {})[cycle["id"]] = part
    job["stage"]["status"] = "saved"
    job.pop("last_error", None)


def date_key(transit, level=None):
    value = transit if level is None else {"level": level, "transit": transit}
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def next_date_stage(date_job):
    return next((level for level in date_job.get("levels", DATE_LEVELS) if level not in date_job.get("parts", {})), None)


def advance_date(api_key, context, basis, date_job, *, transit, plan, **settings):
    if next_basis_stage(basis, plan) is not None:
        raise AIError("请先完成原局与大运基础报告。")
    level = next_date_stage(date_job)
    if level is None:
        return
    if level not in DATE_LEVELS:
        raise AIError("请选择仅分析年、月或日。")
    date_context = copy.deepcopy(context)
    # Validate the complete dependent selection against the calendar before any API call.
    from ai_analysis import _validated_transit
    date_context["facts"]["当前岁运"] = _validated_transit(transit, context["facts"]["四柱"])
    date_job["transit"] = copy.deepcopy(transit)
    selected_cycle = next((c for c in plan["cycles"] if c["pillar"] == transit["大运"]["干支"]
                           and c["start_year"] == transit["大运"]["起始年"]), None)
    narrative_cycle = basis.get("narrative_cycles", {}).get(selected_cycle["id"]) if selected_cycle else None
    if "levels" not in date_job and selected_cycle and selected_cycle["id"] not in basis.get("cycles", {}) and not narrative_cycle:
        # Complete an out-of-basis decade once, then reuse it for later ranges.
        facts, focus = _focus(context, selected_cycle)
        date_job["stage"] = {"id": focus["id"], "label": "所选大运详解 · "+selected_cycle["pillar"], "status": "running"}
        part = _detail(api_key, context, basis["base"], focus, facts, date_job, settings)
        part["document"] = calculate_scores(part["document"], selected_cycle)
        basis.setdefault("cycles", {})[selected_cycle["id"]] = part
        date_job["stage"]["status"] = "saved"
        date_job.pop("last_error", None)
        return
    facts, focus = _focus(date_context, level=level)
    focus["parent_period_reports"] = [item["document"] for item in date_job.get("parts", {}).values()]
    cycle = next((part["document"] for part in basis.get("cycles", {}).values()
                  if part["document"]["cycle"]["pillar"] == transit["大运"]["干支"]
                  and part["document"]["cycle"]["start_year"] == transit["大运"]["起始年"]), None)
    focus["luck_baseline"] = cycle
    if cycle is None and narrative_cycle:
        focus["luck_baseline"] = {"imported_text": narrative_cycle["text"], "cycle": narrative_cycle["cycle"]}
    label = {"annual": "指定流年", "monthly": "指定流月", "daily": "指定流日"}[level]
    from period_text import period_scope
    date_job["stage"] = {"id": level, "label": label + " · " + period_scope(transit), "status": "running"}
    part = _detail(api_key, date_context, basis["base"], focus, facts, date_job, settings)
    part["document"]["selected"] = focus["selected"]
    date_job.setdefault("parts", {})[level] = part
    date_job["transit"] = copy.deepcopy(transit)
    date_job["provider"], date_job["model"] = settings["provider"], settings["model"]
    date_job["stage"]["status"] = "saved"
    date_job.pop("last_error", None)


def _attach_stage_evidence(result,parts):
    result['additional_sources'] = list({s['source_id']:copy.deepcopy(s)
        for part in parts for s in part.get('additional_sources',[])}.values())
    result['retrieval_trace'] = [{'stage':part['document']['id'],**copy.deepcopy(part['retrieval_trace'])}
        for part in parts if part.get('retrieval_trace')]


def assemble_report(job, *, plan=None, date_job=None):
    """Assemble saved validated stages without a model request or duplicate usage."""
    if "base" not in job:
        return None
    if date_job is not None:
        parts = [date_job["parts"][level] for level in DATE_LEVELS if level in date_job.get("parts", {})]
        result = {key: copy.deepcopy(job[key]) for key in ("chart_identity", "birth_profile") if key in job}
        result.update(provider=date_job.get("provider", job["base"].get("provider")),
                      model=date_job.get("model", job["base"].get("model")), usage={},
                      workflow_version=WORKFLOW_VERSION, generation_stages=len(parts),
                      citation_changes=[], format_changes=[])
        for part in parts:
            result["citation_changes"].extend(part.get("citation_changes", []))
            result["format_changes"].extend(part.get("format_changes", []))
            for key, value in part.get("usage", {}).items():
                if type(value) is int and value >= 0:
                    result["usage"][key] = result["usage"].get(key, 0) + value
        result["report"] = {"kind": "period-only", "pillars": copy.deepcopy(job["base"]["report"]["pillars"]),
                            "periods": [copy.deepcopy(part["document"]) for part in parts],
                            "limitations": ["本报告仅包含所选时间专项分析，属于有条件的传统命理推演，不是现实事件保证。"]}
        _attach_stage_evidence(result,parts)
        return result
    result = copy.deepcopy(job["base"])
    if job.get("imported_basis"):
        result["imported_basis"] = copy.deepcopy(job["imported_basis"])
    if job.get("chart_identity"):
        result["chart_identity"] = job["chart_identity"]
    if job.get("birth_profile"):
        result["birth_profile"] = copy.deepcopy(job["birth_profile"])
    result["usage"] = dict(result.get("usage") or {})
    cycles = [job["cycles"][cycle["id"]] for cycle in report_cycles(plan) if cycle["id"] in job.get("cycles", {})] if plan else []
    base_cycle_count = len(cycles)
    parts = cycles
    result.setdefault("format_changes", [])
    for part in parts:
        result.setdefault("citation_changes", []).extend(part.get("citation_changes", []))
        result["format_changes"].extend(part.get("format_changes", []))
        for key, value in part.get("usage", {}).items():
            if type(value) is int and value >= 0:
                result.setdefault("usage", {})[key] = result.get("usage", {}).get(key, 0) + value
    result["workflow_version"] = WORKFLOW_VERSION
    result["generation_stages"] = 1 + len(parts)
    _attach_stage_evidence(result,parts)
    if plan:
        note = f"原局与前{len(report_cycles(plan))}步正式大运基础报告；已完成{base_cycle_count}步。包含大运内逐年趋势、评分及子平K线，不默认展开指定某一年的专项详解。"
        if job.get("imported_basis"):
            note = "基础报告由已有文件导入复用，未重新生成原局或全部大运；旧文本未恢复的图表和评分不会补造。"
        result["report"]["luck_analysis"] = {
            "version": WORKFLOW_VERSION, "note": SCORE_NOTE, "scope_note": note,
            "start": plan["start"], "start_age": plan["start_age"],
            "factors": [{"key": key, "label": label, "weight": weight} for key, label, weight in FACTORS],
            "cycles": [part["document"] for part in cycles], "selected": [],
            "source_omissions": [part.get("omitted_paragraphs", 0) for part in parts],
        }
        if len(result["report"]["steps"]) >= 7:
            result["report"]["steps"][6] = {"step": 7, "conclusion": note,
                "chart_evidence": [f"{plan['start_age']}起运，{plan['start']}交运。"], "citations": [],
                "uncertainties": [SCORE_NOTE, "交运及交节日期须核对具体时刻；排表终点不是寿命结论。"]}
        result["report"]["limitations"] = [SCORE_NOTE, note, "解释属于有条件的传统命理推演，不是现实事件保证。"]
    return result


def calendar_plan(chart):
    return build_luck_plan(chart)
