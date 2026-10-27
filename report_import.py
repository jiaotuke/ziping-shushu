"""Read report data without executing HTML, contacting models, or changing ledgers."""
from __future__ import annotations
import copy
from datetime import datetime
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re

from ai_analysis import AIError, validate_report
from citation_audit import optional_citations
from luck_analysis import _focus, calculate_scores, validate_detail

MAX_REPORT_BYTES = 2_000_000
STEMS = "甲乙丙丁戊己庚辛壬癸"
BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
PILLAR = f"[{STEMS}][{BRANCHES}]"
CYCLE_HEADING = re.compile(r"第\s*(\d{1,2})\s*运[\s·：:]*?("+PILLAR+r")[\s·：:]*(\d{4})\s*[—–\-~至]\s*(\d{4})")
FORMATS = {"ziping-report-v1", "ziping-report-v2", "ziping-report-v3-results-first", "ziping-report-v4-importable"}


def birth_profile(chart):
    birth = str(chart.get("公历") or chart.get("专业出生时刻") or "")
    if birth:
        birth = datetime.fromisoformat(birth).isoformat()
    return {"birth_datetime": birth, "gender": chart.get("性别", ""), "source": "chart"}


def chart_identity(chart):
    profile = birth_profile(chart)
    values = [chart["四柱"], profile["birth_datetime"], chart.get("性别")]
    return hashlib.sha256(json.dumps(values, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


class _HTMLText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.snapshot = [], []
        self.ignored = []
        self.capture = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script":
            self.capture = attrs.get("id") == "ziping-report-snapshot" and attrs.get("type", "").lower() == "application/json"
        if self.ignored:
            if tag in ("script", "style", "svg", "iframe", "object"):
                self.ignored.append(tag)
            return
        if tag in ("script", "style", "svg", "iframe", "object"):
            self.ignored.append(tag)
        elif tag in ("p", "div", "br", "h1", "h2", "h3", "h4", "summary", "li", "blockquote", "header"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if self.ignored:
            if tag == self.ignored[-1]:
                self.ignored.pop()
            if tag == "script":
                self.capture = False
            return
        if tag in ("p", "div", "h1", "h2", "h3", "h4", "summary", "li", "blockquote", "header"):
            self.parts.append("\n")

    def handle_data(self, data):
        if self.capture:
            self.snapshot.append(data)
        elif not self.ignored:
            self.parts.append(data)


def _decode(raw):
    encodings = ("utf-16",) if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else ("utf-8-sig", "gb18030")
    for encoding in encodings:
        try:
            text = raw.decode(encoding)
            if "\x00" not in text:
                return text
        except UnicodeError:
            pass
    raise AIError("报告编码无法识别，请使用原下载文件，或另存为UTF-8文本。")


def _json(text):
    def invalid_constant(value):
        raise ValueError("Non-finite number")
    try:
        value = json.loads(text, parse_constant=invalid_constant)
        count = 0
        def visit(item, depth=0):
            nonlocal count
            count += 1
            if depth > 45 or count > 100000:
                raise ValueError("Too complex")
            if isinstance(item, dict):
                for child in item.values():
                    visit(child, depth+1)
            elif isinstance(item, list):
                for child in item:
                    visit(child, depth+1)
        visit(value)
        return value
    except (ValueError, RecursionError):
        raise AIError("报告JSON不完整、格式不正确或内容层级过深，请重新选择原下载文件。") from None


def _text_pillars(text):
    match = re.search(r"四柱\s*[：:]\s*("+PILLAR+r")[\s、,，|/]+("+PILLAR+r")[\s、,，|/]+("+PILLAR+r")[\s、,，|/]+("+PILLAR+r")", text)
    if not match:
        raise AIError("未识别到报告中的四柱，无法确认命盘；请使用本程序下载的完整报告。")
    return dict(zip(("年柱", "月柱", "日柱", "时柱"), match.groups()))


def _text_cycles(text, plan):
    known = {(c["pillar"], c["start_year"], c["end_year"]): c for c in plan["cycles"]}
    matches = list(CYCLE_HEADING.finditer(text))
    result = {}
    for index, match in enumerate(matches):
        key = (match[2], int(match[3]), int(match[4]))
        if key not in known:
            raise AIError("报告的大运干支或年份与当前出生资料、性别不一致，请核对排盘后再导入。")
        cycle = known[key]
        end = matches[index+1].start() if index+1 < len(matches) else len(text)
        block = text[match.start():end]
        # Do not attach a following period appendix to the last decade's baseline.
        block = re.split(r"所选流年推导|所选流月推导|所选流日推导|原局判断与推导依据", block)[0]
        if cycle["id"] in result:
            result[cycle["id"]]["text"] += "\n" + block
        else:
            result[cycle["id"]] = {"cycle": {k: cycle[k] for k in ("id", "pillar", "start_year", "end_year")}, "text": block}
    return result


def _natal_text(text):
    section = re.search(r"原局判断与推导依据(.*?)(?:逐运推导与评分依据|\Z)", text, re.S)
    return section[1].strip() if section else text.strip()


def _remap_citations(report, metadata, sources):
    current = {(s.get("book_name"), s.get("chapter"), str(s.get("line_number", ""))): s["source_id"] for s in sources}
    mapping = {s.get("source_id"): current.get((s.get("book_name"), s.get("chapter"), str(s.get("line_number", ""))))
               for s in metadata if isinstance(s, dict) and isinstance(s.get("source_id"), str)
               and isinstance(s.get("book_name"), str) and isinstance(s.get("chapter"), str)}
    def visit(item):
        if isinstance(item, dict):
            if "citations" in item:
                refs = item["citations"] if isinstance(item["citations"], list) else []
                item["citations"] = [{"source_id": mapping[ref["source_id"]], "quote": ref["quote"]}
                    for ref in refs if isinstance(ref, dict) and isinstance(ref.get("source_id"), str)
                    and mapping.get(ref["source_id"]) and isinstance(ref.get("quote"), str)]
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)
    visit(report)
    return optional_citations(report, sources)[0]


def import_report(raw, filename, *, chart, context, plan):
    """Return a new workspace only after local validation; never mutate a live one."""
    if not raw or len(raw) > MAX_REPORT_BYTES:
        raise AIError("请选择不超过2MB的完整报告文件。")
    kind = Path(filename).suffix.lower()
    if kind not in (".json", ".html", ".htm", ".txt"):
        raise AIError("支持导入JSON、HTML或TXT报告。")
    text = _decode(raw)
    artifact = None
    if kind in (".html", ".htm"):
        parser = _HTMLText()
        try:
            parser.feed(text)
            parser.close()
        except (ValueError, RecursionError):
            raise AIError("HTML报告无法读取，请选择原下载文件。") from None
        text = re.sub(r"\n[ \t]*\n+", "\n\n", "".join(parser.parts)).strip()
        if parser.snapshot:
            artifact = _json("".join(parser.snapshot))
    elif kind == ".json":
        artifact = _json(text)
    if "报告类型：时间专项（不含基础报告）" in text or isinstance(artifact, dict) and artifact.get("format") == "ziping-period-report-v1":
        raise AIError("这是仅含年／月／日专项的报告，不能代替原局大运基础报告。请导入单独下载的基础报告。")
    if "【文风示例，不作实际报告导入】" in text or isinstance(artifact,dict) and (artifact.get("example") or isinstance(artifact.get("result"),dict) and artifact["result"].get("example")):
        raise AIError("文风示例不是真实分析报告，不能导入为实际排盘的分析基线。")
    warnings, native_cycles, native_base = [], {}, None
    profile = birth_profile(chart)
    saved_profile = None
    if artifact is None:
        birth_match = re.search(r"(?m)^公历出生时刻：\s*(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})\s*$", text)
        gender_match = re.search(r"(?m)^性别：\s*([男女])\s*$", text)
        if birth_match and gender_match:
            saved_profile = {"birth_datetime": birth_match[1], "gender": gender_match[1],
                             "source": "confirmed_on_import" if "出生资料来源：导入时按当前命盘补充确认" in text else "report"}
    prior_text = ""
    history_marker = "导入的历史基础报告原文（未重新生成或评分）"
    if artifact is None and history_marker in text:
        prior_text = text.rsplit(history_marker, 1)[1].strip()
        if _text_pillars(prior_text) != chart["四柱"]:
            raise AIError("报告附带的历史基线与当前四柱不一致。")
    provenance = {"filename": Path(filename.replace('\\', '/')).name[:120], "sha256": hashlib.sha256(raw).hexdigest(),
                  "kind": kind.lstrip('.'), "chart_identity": chart_identity(chart)}
    if artifact is not None:
        if not isinstance(artifact, dict) or artifact.get("format") not in FORMATS:
            raise AIError("这不是可识别的子平术数完整数据报告，请选择报告下载区保存的文件。")
        original = artifact.get("result")
        report = original.get("report") if isinstance(original, dict) else None
        if not isinstance(report, dict) or report.get("pillars") != chart["四柱"]:
            raise AIError("报告四柱与当前命盘不一致，未导入，也未修改已有进度。")
        if original.get("chart_identity") and original["chart_identity"] != chart_identity(chart):
            raise AIError("报告出生资料或性别与当前排盘不一致，请先核对。")
        saved_profile = original.get("birth_profile")
        wrapped_text = original.get("imported_basis", {})
        text_basis = isinstance(wrapped_text, dict) and wrapped_text.get("mode") == "narrative" and isinstance(wrapped_text.get("natal_text"), str)
        if text_basis and isinstance(wrapped_text.get("text"), str):
            prior_text = wrapped_text["text"]
            if _text_pillars(prior_text) != chart["四柱"]:
                raise AIError("报告附带的历史基线与当前四柱不一致。")
        if not isinstance(report.get("steps"), list) or (len(report["steps"]) != 8 and not (not report["steps"] and text_basis)):
            raise AIError("报告缺少完整原局八步分析，不能替代基础报告。")
        life = report.get("luck_analysis") or {}
        if not isinstance(life, dict) or not isinstance(life.get("cycles", []), list):
            raise AIError("报告大运数据格式不正确。")
        if life.get("start") and str(life["start"]).replace('T', ' ') != str(plan["start"]).replace('T', ' '):
            raise AIError("报告起运时刻与当前排盘不一致，请核对出生资料和起运算法。")
        # Rebuild plaintext from the report's known schema; never serialize credentials or other result fields.
        from luck_chart import extended_text
        try:
            text = "四柱：" + " ".join(report["pillars"][key] for key in ("年柱", "月柱", "日柱", "时柱")) + "\n" + extended_text(report, artifact.get("sources", []))
        except (ValueError, KeyError, TypeError, IndexError, AttributeError):
            raise AIError("报告内容结构不完整，无法提取已有分析；请改用此前下载的HTML或TXT。") from None
        metadata = artifact.get("sources", [])
        if not isinstance(metadata, list):
            metadata = []
        cleaned = _remap_citations(copy.deepcopy(report), metadata, context["sources"])
        try:
            validate_report(cleaned, context)
            original_provider = original.get("provider") if original.get("provider") in ("zhipu", "deepseek", "inkstone") else "imported"
            original_model = original.get("model", "")
            original_model = original_model if isinstance(original_model, str) and re.fullmatch(r"[A-Za-z0-9_.:/-]{1,120}", original_model) else "历史报告"
            native_base = {"report": copy.deepcopy(cleaned), "provider": original_provider,
                           "model": original_model, "usage": {},
                           "citation_changes": [], "format_changes": [], "context_budget": context.get("context_budget", {})}
            native_base["report"].pop("luck_analysis", None)
        except AIError:
            native_base = None
            warnings.append("旧版原局结构以原文基线复用，不会重新调用模型转换。")
        for document in (cleaned.get("luck_analysis") or {}).get("cycles", []):
            saved = document.get("cycle") if isinstance(document, dict) else None
            if not isinstance(saved, dict) or not all(key in saved for key in ("pillar", "start_year", "end_year")):
                raise AIError("报告包含不完整的大运范围，未修改已有进度。")
            cycle = next((c for c in plan["cycles"] if c["pillar"] == saved["pillar"]
                          and c["start_year"] == saved["start_year"] and c["end_year"] == saved["end_year"]), None)
            if cycle is None:
                raise AIError("报告的大运范围与当前排盘不一致。")
            facts, focus = _focus(context, cycle)
            try:
                validate_detail(document, focus, context["sources"], focus["id"])
                native_cycles[cycle["id"]] = {"document": calculate_scores(document, cycle), "usage": {},
                    "citation_changes": [], "format_changes": [], "omitted_paragraphs": 0}
            except AIError:
                warnings.append(cycle["label"]+"以文字基线复用，原有评分结构没有完整恢复。")
    if saved_profile is not None:
        if not isinstance(saved_profile, dict):
            raise AIError("报告出生资料格式不正确。")
        try:
            saved_birth = datetime.fromisoformat(saved_profile["birth_datetime"]).isoformat()
        except (ValueError, TypeError, KeyError):
            raise AIError("报告出生时刻无法识别，请核对原文件。") from None
        if saved_birth != profile["birth_datetime"] or saved_profile.get("gender") != profile["gender"]:
            raise AIError("报告出生时刻或性别与当前排盘不一致，未修改已有进度。")
        profile["source"] = "confirmed_on_import" if saved_profile.get("source") == "confirmed_on_import" else "report"
    else:
        profile["source"] = "confirmed_on_import"
        warnings.append("旧报告未保存完整出生资料；本次出生时刻和性别来自你确认的当前命盘，不是从旧报告恢复。")
    if _text_pillars(text) != chart["四柱"]:
        raise AIError("报告四柱与当前命盘不一致，未导入，也未修改已有进度。")
    if len(text.strip()) < 200 or "原局" not in text:
        raise AIError("未识别到完整原局分析正文，请选择此前下载的完整报告。")
    narratives = _text_cycles(text, plan)
    if prior_text:
        for key, value in _text_cycles(prior_text, plan).items():
            narratives.setdefault(key, value)
    basis_text = prior_text or text
    provenance.update(text=basis_text, natal_text=_natal_text(basis_text), warnings=warnings,
                      mode="structured" if native_base else "narrative", matched_cycles=len(set(narratives) | set(native_cycles)))
    if not artifact or not artifact.get("result", {}).get("chart_identity"):
        warnings.append("旧报告按四柱和可识别的大运年份核对；请确认原报告的出生资料、性别和起运算法一致。")
    if native_base is None:
        native_base = {"report": {"pillars": dict(chart["四柱"]), "steps": [], "summary": provenance["natal_text"],
                        "relation_implications": [], "limitations": ["导入旧报告文字作为基线，未重新评分；原有文字引用未重新核验适用性。"]},
                       "provider": "imported", "model": "导入的历史报告", "usage": {}, "citation_changes": [],
                       "format_changes": [], "context_budget": context.get("context_budget", {})}
        native_base["imported_basis_text"] = provenance["natal_text"]
    return {"base": native_base, "cycles": native_cycles, "dates": {}, "imported_basis": provenance,
            "narrative_cycles": narratives, "chart_identity": chart_identity(chart), "birth_profile": profile}
