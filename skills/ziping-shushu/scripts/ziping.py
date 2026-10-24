"""Local chart calculation and source retrieval; no UI, account store or model API."""
from __future__ import annotations

import argparse
from datetime import date, datetime
import json
import os
from pathlib import Path
import re
import sys

SKILL_ROOT = Path(__file__).resolve().parents[1]
ENGINE_ROOT = SKILL_ROOT / "assets" / "engine"
BOOKS = ("穷通宝鉴", "三命通会", "子平真诠", "滴天髓")
PILLARS = ("年柱", "月柱", "日柱", "时柱")


def bounded(low: int, high: int):
    def parse(value: str) -> int:
        number = int(value)
        if not low <= number <= high:
            raise argparse.ArgumentTypeError(f"值必须在{low}～{high}之间")
        return number
    return parse


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="子平术数：本地排盘与有出处的古籍检索")
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("chart", "prepare", "luck-start"):
        command = commands.add_parser(name)
        inputs = command.add_mutually_exclusive_group(required=True)
        inputs.add_argument("--birth", help="YYYY-MM-DD HH:MM[:SS]，按所选历法解释")
        inputs.add_argument("--pillars", help="年柱 月柱 日柱 时柱")
        command.add_argument("--calendar", choices=("solar", "lunar"), default="solar")
        command.add_argument("--leap-month", action="store_true")
        command.add_argument("--matched-date", help="四柱反查返回的候选完整日期时刻")
        command.add_argument("--longitude", type=float)
        command.add_argument("--timezone", help="真太阳时修正所用出生地IANA时区")
        command.add_argument("--fold", type=int, choices=(0, 1))
        command.add_argument("--luck", action="store_true", help="添加前六步大运计算摘要")
        command.add_argument("--gender", choices=("男", "女"))
        command.add_argument("--output", type=Path)
        if name == "prepare":
            command.add_argument("--context", choices=("focused", "full"), default="focused")
            command.add_argument("--sources-per-book", type=bounded(1, 20), default=2)
            command.add_argument("--chars-per-book", type=bounded(400, 20000), default=2400)
        elif name == "luck-start":
            command.set_defaults(luck=True)
            command.add_argument("--confirm-extended", action="store_true", required=True,
                                 help="仅在用户明确要求大运深入分析或K线时传入")
            command.add_argument("--request", required=True, help="保留用户明确要求扩展分析的原话")
            command.add_argument("--workdir", type=Path, required=True, help="新建的私有分析任务目录")
            scope = command.add_mutually_exclusive_group()
            scope.add_argument("--cycle", action="append", help="选定大运ID，可重复；不默认分析六步")
            scope.add_argument("--first-six", action="store_true", help="仅在用户明确要求前六步时使用")
            command.add_argument("--model-label", default="当前AI会话")
    for name in ("luck-stage", "luck-accept", "luck-render"):
        command = commands.add_parser(name)
        command.add_argument("--workdir", type=Path, required=True)
        command.add_argument("--output", type=Path)
        if name == "luck-accept":
            command.add_argument("--stage-id", required=True)
            command.add_argument("--response", type=Path, required=True)
        elif name == "luck-render":
            command.add_argument("--outdir", type=Path)
    search = commands.add_parser("search")
    search.add_argument("--query", required=True)
    search.add_argument("--book", choices=BOOKS)
    search.add_argument("--count", type=bounded(1, 20), default=2)
    search.add_argument("--chars-per-book", type=bounded(400, 20000), default=2400)
    search.add_argument("--output", type=Path)
    source = commands.add_parser("source")
    source.add_argument("--id", dest="ids", action="append", required=True)
    source.add_argument("--output", type=Path)
    return root


def engine() -> None:
    if not (ENGINE_ROOT / "bazi.py").is_file():
        raise ValueError("技能缺少随包计算程序；请在项目中运行 tools/prepare_ziping_skill.py 完成打包。")
    # Use this bundle's resources even if the calling shell has website settings.
    os.environ["ZIPING_RESOURCE_ROOT"] = str(ENGINE_ROOT)
    sys.path.insert(0, str(ENGINE_ROOT))


def source_record(record: dict) -> dict:
    return {
        "source_id": record["source_id"],
        "book_name": record["book_name"],
        "chapter": record["section"],
        "source_file": record["source_file"],
        "line_number": record["line_number"],
        "end_line_number": record.get("end_line_number", record["line_number"]),
        "text": record["text"],
        "edition_note": record.get("citation", ""),
    }


def chart_payload(args: argparse.Namespace) -> dict:
    from bazi import (calculate_chart, calculate_lunar_chart, calculate_pillars_chart,
                      convert_to_true_solar_time, find_pillar_birth_times)
    from pillar_relationships import analyze_relationships, relationship_facts

    if args.luck and not args.gender:
        raise ValueError("计算起运和大运需要性别，请传 --gender 男 或 女。")
    notes: list[str] = []
    candidates: list[str] = []
    birth: datetime | None = None
    status = "resolved"
    if args.pillars:
        if args.calendar != "solar" or args.leap_month or args.longitude is not None or args.timezone or args.fold is not None:
            raise ValueError("四柱模式直接使用输入干支；请勿附加历法或真太阳时修正参数。")
        values = re.split(r"[\s,，]+", args.pillars.strip())
        if len(values) != 4:
            raise ValueError("请按年柱、月柱、日柱、时柱顺序提供四柱。")
        chart = calculate_pillars_chart(dict(zip(PILLARS, values)))
        candidates = list(find_pillar_birth_times(*values, latest_date=date.today()))
        if args.matched_date:
            selected = datetime.fromisoformat(args.matched_date).strftime("%Y-%m-%d %H:%M:%S")
            if selected not in candidates:
                raise ValueError("选择的日期时刻不在本次四柱反查候选中，请使用返回的完整候选值。")
            birth = datetime.fromisoformat(selected)
        elif len(candidates) == 1:
            birth = datetime.fromisoformat(candidates[0])
        else:
            status = "choose_date" if candidates else "no_match"
            notes.append("有多个公历候选，请让用户选择日期。" if candidates else "反查范围内没有匹配日期，保留四柱，不计算起运。")
        if birth is not None:
            chart["公历"] = birth.strftime("%Y-%m-%d %H:%M:%S")
            chart["专业出生时刻"] = chart["公历"]
            chart["时间说明"] = "直接使用输入四柱；公历日期已匹配，出生时刻采用程序反查的时柱默认匹配时刻，未校正真太阳时。"
    else:
        if args.matched_date:
            raise ValueError("--matched-date 仅用于四柱输入。")
        match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?", args.birth)
        if not match:
            raise ValueError("生日格式必须是 YYYY-MM-DD HH:MM[:SS]。")
        parts = [int(value or 0) for value in match.groups()]
        if args.calendar == "lunar":
            chart = calculate_lunar_chart(*parts, is_leap_month=args.leap_month)
            birth = datetime.fromisoformat(chart["公历"])
        else:
            if args.leap_month:
                raise ValueError("--leap-month 仅用于农历。")
            birth = datetime(*parts)
            chart = calculate_chart(birth)
        if (args.longitude is None) != (args.timezone is None):
            raise ValueError("真太阳时修正必须同时提供 --longitude 和 --timezone。")
        if args.fold is not None and args.timezone is None:
            raise ValueError("--fold 需要配合出生地时区和经度。")
        if args.longitude is not None:
            original = chart
            corrected, offset, equation = convert_to_true_solar_time(birth, args.longitude, args.timezone, args.fold)
            chart = calculate_chart(corrected, time_basis="按用户要求使用经度、出生地时区和均时差校正真太阳时")
            chart["输入民用时刻"] = birth.strftime("%Y-%m-%d %H:%M:%S")
            chart["真太阳时修正"] = {"经度": args.longitude, "时区": args.timezone,
                                   "UTC偏移小时": offset, "均时差分钟": equation}
            for key in ("输入历法", "输入农历日期"):
                if key in original:
                    chart[key] = original[key]
            birth = corrected
    result = {
        "ok": True, "format": "ziping-skill-v1", "chart": chart,
        "date_resolution": status, "matching_dates": candidates,
        "relationships": relationship_facts(analyze_relationships(chart["四柱"])),
        "notes": notes,
    }
    if args.gender:
        result["gender"] = args.gender
    if args.luck:
        if birth is None:
            result["luck"] = None
            result["notes"].append("尚未确定匹配日期，大运暂不计算。")
        else:
            from professional_chart import luck_cycles
            luck = luck_cycles(birth.isoformat(sep=" "), args.gender)
            result["luck"] = {
                "start": luck["start"], "start_age": luck["start_age"],
                "forward": luck["forward"], "start_sect": luck["start_sect"],
                "cycles": [{key: cycle[key] for key in ("id", "label", "pillar", "period", "start_year", "end_year")}
                           for cycle in [c for c in luck["cycles"] if c["id"] != "0"][:6]],
                "scope": "前六步大运计算摘要；未执行逐年解释、评分或K线生成",
            }
    return result


def select_sources(retrieval: dict, *, context: str, count: int, budget: int) -> tuple[list[dict], list[str]]:
    from source_data import load_source_records
    records = load_source_records()
    by_id = {str(row["source_id"]): row for row in records}
    selected: list[dict] = []
    notes: list[str] = []
    seen: set[str] = set()
    for book in BOOKS:
        if context == "full" and book == "子平真诠":
            full = [row for row in records if row["book_name"] == book]
            if not full:
                notes.append("子平真诠全文不可用。")
            selected.extend(source_record(row) for row in full)
            seen.update(str(row["source_id"]) for row in full)
            continue
        ids: list[str] = []
        for hit in retrieval.get("results_by_book", {}).get(book, []):
            meta = hit.get("metadata", {})
            ids.extend(str(value) for value in [meta.get("matched_source_id"), meta.get("source_id"), *meta.get("source_ids", [])] if value)
        used, kept = 0, 0
        omitted = False
        for source_id in dict.fromkeys(ids):
            row = by_id.get(source_id)
            if row is None or row["book_name"] != book or source_id in seen:
                continue
            text = str(row["text"])
            if len(text) < 30:
                continue
            if kept >= count or used + len(text) > budget:
                omitted = True
                continue
            selected.append(source_record(row))
            seen.add(source_id)
            used += len(text)
            kept += 1
        if kept == 0:
            notes.append(f"《{book}》没有可返回的完整支持段落，请补充检索或调整预算。")
        elif omitted:
            notes.append(f"《{book}》按段落数量和字符预算返回部分完整原文，未读取的部分不作为已审阅依据。")
    for book, error in retrieval.get("book_errors", {}).items():
        notes.append(f"《{book}》检索提示：{error}")
    return selected, notes


def prepare_payload(args: argparse.Namespace) -> dict:
    from portable_retrieval import retrieve_chart
    result = chart_payload(args)
    found = retrieve_chart(result["chart"])
    sources, notes = select_sources(found, context=args.context, count=args.sources_per_book, budget=args.chars_per_book)
    result.update({
        "context_mode": args.context, "sources": sources,
        "source_notes": notes, "retrieval_modes": found.get("book_modes", {}),
        "source_scope": "子平真诠全文及其底本附注，另三书按篇检索" if args.context == "full" else "四书分别按篇检索的完整段落，不是四书全文复核",
        "report_generation": "由调用本技能的AI会话完成；本程序未调用语言模型",
    })
    return result


def search_payload(args: argparse.Namespace) -> dict:
    from portable_retrieval import get_collection
    from source_data import load_source_records
    if not args.query.strip():
        raise ValueError("检索问题不能为空。")
    collection = get_collection()
    records = {str(row["source_id"]): row for row in load_source_records()}
    output, notes = [], []
    for book in (args.book,) if args.book else BOOKS:
        hits = collection.query(query_texts=[args.query], n_results=args.count, where={"book_name": book})
        used = 0
        for source_id in hits["ids"][0]:
            row = records[str(source_id)]
            if used + len(row["text"]) > args.chars_per_book:
                notes.append(f"《{book}》一条完整段落超过剩余预算，未截断返回；需要时使用source读取。source_id={source_id}")
                continue
            output.append(source_record(row))
            used += len(row["text"])
    return {"ok": True, "format": "ziping-skill-v1", "sources": output, "source_notes": notes,
            "ranking": "本地BM25段落检索；排名不代表命理结论正确率"}


def source_payload(args: argparse.Namespace) -> dict:
    from source_data import load_source_records
    records = {str(row["source_id"]): row for row in load_source_records()}
    missing = [value for value in args.ids if value not in records]
    if missing:
        raise ValueError("来源编号不存在，请从本技能最近一次检索结果中复制source_id。")
    return {"ok": True, "format": "ziping-skill-v1", "sources": [source_record(records[value]) for value in dict.fromkeys(args.ids)]}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parser().parse_args()
    try:
        engine()
        if args.command == "chart":
            result = chart_payload(args)
        elif args.command == "prepare":
            result = prepare_payload(args)
        elif args.command == "search":
            result = search_payload(args)
        elif args.command.startswith("luck-"):
            from luck_workflow import execute
            result = execute(args, chart_payload)
        else:
            result = source_payload(args)
        payload = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as target:
                target.write(payload + "\n")
            print(json.dumps({"ok": result.get("ok", True), "output_file": str(args.output.resolve())}, ensure_ascii=False))
        else:
            print(payload)
        return 0 if result.get("ok", True) else 2
    except ModuleNotFoundError as error:
        print(json.dumps({"ok": False, "error": f"缺少Python依赖{error.name}，请安装技能requirements.txt。"}, ensure_ascii=False))
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
