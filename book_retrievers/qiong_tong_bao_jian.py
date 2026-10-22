"""《穷通宝鉴》按日干和月令直接定位正文，不回退到五行总论。"""

from __future__ import annotations

import re

from source_data import load_source_records

STEM_ELEMENT = dict(zip("甲乙丙丁戊己庚辛壬癸", "木木火火土土金金水水"))
MONTHS = ("正月", "二月", "三月", "四月", "五月", "六月", "七月", "八月", "九月", "十月", "十一月", "十二月")
BRANCHES = "寅卯辰巳午未申酉戌亥子丑"
SEASONS = ("三春", "三夏", "三秋", "三冬")


def _month_scope(prefix: str) -> set[int]:
    if prefix in SEASONS:
        first = SEASONS.index(prefix) * 3
        return set(range(first, first + 3))
    if prefix in MONTHS:
        return {MONTHS.index(prefix)}
    if prefix == "腊月":
        return {11}
    if prefix == "冬月":
        return {10}
    if prefix.endswith("月"):
        singles = "正二三四五六七八九"
        chars = prefix[:-1]
        if chars and all(c in singles for c in chars):
            return {singles.index(c) for c in chars}
    return set()


def retrieve(topic: str, conditions: dict, count: int, collection, rag_module) -> dict:
    stem = str(conditions.get("day_master", ""))
    branch = str(conditions.get("month_branch", ""))
    if stem not in STEM_ELEMENT or branch not in BRANCHES or len(branch) != 1:
        raise ValueError("《穷通宝鉴》检索需要有效的日干和月令。")
    month = BRANCHES.index(branch)
    suffix = stem + STEM_ELEMENT[stem]
    records = load_source_records("穷通宝鉴")
    exact = MONTHS[month] + suffix
    selected = []
    scope = set()
    previous_section = None
    shared = False
    for record in records:
        section = str(record["section"])
        if not section.endswith(suffix):
            continue
        chapter_scope = _month_scope(section[:-len(suffix)])
        if not chapter_scope and section != "论" + suffix:
            continue
        if section != previous_section:
            scope = chapter_scope
            previous_section = section
        # Some month openers occur in prose inside a seasonal/previous month chapter.
        match = re.match(r"^([正一二三四五六七八九十冬腊]+月|三[春夏秋冬])" + re.escape(suffix), record["text"])
        if match:
            new_scope = _month_scope(match[1])
            if new_scope:
                scope = new_scope
        if month in scope:
            selected.append(record)
            shared = shared or len(scope) > 1
    if not selected or not any(len(str(r["text"])) >= 30 for r in selected):
        return {"results": [], "mode": "no_results", "chapter": exact, "annotation_issues": []}
    source_chapters = list(dict.fromkeys(str(r["section"]) for r in selected))
    chapter = exact if any(str(r["text"]).startswith(exact) for r in selected) else "、".join(source_chapters)
    first = selected[0]
    ranges = []
    for record in selected:
        start, end = int(record["line_number"]), int(record.get("end_line_number", record["line_number"]))
        if ranges and start <= ranges[-1][1] + 1:
            ranges[-1][1] = end
        else:
            ranges.append([start, end])
    location = "、".join(str(a) if a == b else f"{a}-{b}" for a, b in ranges)
    mode = "day_month_shared" if shared else "day_month_exact"
    result = {
        "document": "\n\n".join(str(r["text"]) for r in selected),
        "metadata": {
            "source_id": first["source_id"], "source_ids": [r["source_id"] for r in selected],
            "book_name": "穷通宝鉴", "source_file": first["source_file"], "citation": first["citation"],
            "chapter": f"{stem}生{branch}月 · {chapter}", "source_chapter": "、".join(source_chapters),
            "day_master": stem, "month_branch": branch,
            "line_number": location,
            "retrieval_method": "按日干月令精确定位", "shared_scope": shared,
        },
    }
    return {"results": [result], "mode": mode, "chapter": chapter, "annotation_issues": []}
