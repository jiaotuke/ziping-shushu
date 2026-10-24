"""《三命通会》四层检索：日时、日干、日干月令、五行月令。"""

from source_data import load_source_records

from .common import retrieve_sections

STEM_ELEMENT = {
    "甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
    "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水",
}


def _from_source_record(
    record: dict,
    part: str,
    query: str,
    method: str = "原文精确字串",
) -> dict:
    """命中某条原文后，按当前识别出的篇章展开全文。"""
    section = str(record["section"])
    chapter = [
        item for item in load_source_records("三命通会")
        if str(item["section"]) == section
    ]
    if not chapter:
        chapter = [record]
    return {
        "document": "\n".join(str(item["text"]) for item in chapter),
        "metadata": {
            "source_id": str(record["source_id"]),
            "book_name": str(record["book_name"]),
            "source_file": str(record["source_file"]),
            "citation": str(record["citation"]),
            "chapter": section,
            "line_number": f"{chapter[0]['line_number']}-{chapter[-1].get('end_line_number', chapter[-1]['line_number'])}",
            "source_ids": [str(item["source_id"]) for item in chapter],
            "matched_source_id": str(record["source_id"]),
            "retrieval_part": part,
            "retrieval_query": query,
            "retrieval_method": method,
        },
        "distance": 0.0,
    }


def _chapter_by_number(chapter_number: int, part: str, query: str) -> list[dict]:
    """按当前底本的章号取整章，不用语义向量猜章节。"""
    prefix = f"第{chapter_number}章 "
    record = next(
        (item for item in load_source_records("三命通会")
         if str(item["section"]).startswith(prefix)),
        None,
    )
    if record is None:
        return []
    return [_from_source_record(record, part, query, "按本书章节结构取整章")]


def _exact_day_time(chart: dict, collection, count: int) -> list[dict]:
    """第一层：先在原文中查找完整的“某日某时”组合，找不到再书内向量查找。"""
    day_pillar = str(chart.get("四柱", {}).get("日柱", ""))
    time_pillar = str(chart.get("四柱", {}).get("时柱", ""))
    query = f"{day_pillar}日{time_pillar}时"
    records = load_source_records("三命通会")
    normalized_query = "".join(query.split())
    for record in records:
        if normalized_query and normalized_query in "".join(str(record["text"]).split()):
            return [_from_source_record(record, "第一部分·日时组合", query)]

    results, mode, _chapter = retrieve_sections(
        "三命通会", query, [], collection, count
    )
    for result in results:
        result["metadata"]["retrieval_part"] = "第一部分·日时组合"
        result["metadata"]["retrieval_query"] = query
        result["metadata"]["retrieval_method"] = mode
    return results


def retrieve(chart: dict, topic: str, count: int, collection) -> dict:
    """按四个由具体到概括的线索分别检索《三命通会》。"""
    pillars = chart.get("四柱", {})
    day_pillar = str(pillars.get("日柱", ""))
    time_pillar = str(pillars.get("时柱", ""))
    day_stem = day_pillar[:1]
    month_branch = str(pillars.get("月柱", ""))[1:2]
    element = STEM_ELEMENT.get(day_stem, "")
    results: list[dict] = []

    # 第一部分：具体到日柱和时柱；有逐字匹配时保留书中原文所在行。
    results.extend(_exact_day_time(chart, collection, 1))

    # 第二部分：本书没有“论甲乙/论壬癸”独立篇名，十干内容见第14章。
    if day_stem:
        query = f"论{day_stem}日干"
        results.extend(_chapter_by_number(14, "第二部分·日干专论", query))

    # 第三部分：在本书按月令论日干吉凶的篇章中查“某日干生某月”。
    if day_stem and month_branch:
        query = f"{day_stem}生{month_branch}月"
        # 对应第63章“论十二月支得日干吉凶”，保留整章月令上下文。
        results.extend(_chapter_by_number(63, "第三部分·日干生月", query))

    # 第四部分：把日干归入五行，查该五行与出生月令相关的论述。
    if element and month_branch:
        query = f"{element}生{month_branch}月"
        element_chapter = {"木": 65, "火": 66, "土": 67, "金": 68, "水": 69}[element]
        results.extend(_chapter_by_number(element_chapter, "第四部分·五行生月", query))

    return {
        "results": results,
        "mode": "four_part",
        "chapter": None,
        "annotation_issues": [],
    }
