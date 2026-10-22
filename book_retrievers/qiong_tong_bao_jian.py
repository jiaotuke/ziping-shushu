"""《穷通宝鉴》检索：日主/月令定位篇章，再匹配人工条件标注。"""


def retrieve(topic: str, conditions: dict, count: int, collection, rag_module) -> dict:
    results, issues = rag_module.retrieve_chart_records(topic, count, conditions, collection)
    mode = "verified_conditions"
    chapter = results[0]["metadata"].get("chapter") if results else None
    if not results:
        results, chapter = rag_module.retrieve_chapter_references(
            topic, conditions, count, collection
        )
        mode = "chapter_fallback" if results else "no_results"
    return {"results": results, "mode": mode, "chapter": chapter, "annotation_issues": issues}
