"""各书检索器共用的出处过滤、向量排序和篇章展开工具。"""

from __future__ import annotations

from source_data import load_source_records


def retrieve_sections(book_name: str, topic: str, sections: list[str], collection, count: int = 1):
    """在本书匹配的候选篇章内排序，并返回命中篇章全文；无候选则书内语义检索。"""
    records = load_source_records(book_name)
    wanted = [section for section in dict.fromkeys(sections) if section]
    candidates = [
        record for record in records
        if any(term in str(record["section"]) for term in wanted)
    ]
    if candidates:
        ids = list(dict.fromkeys(str(record["source_id"]) for record in candidates))
        indexed_ids = set(collection.get(include=[])["ids"])
        ids = [source_id for source_id in ids if source_id in indexed_ids]
        if ids:
            result = collection.query(
                query_texts=[topic],
                n_results=min(max(count, 1), len(ids)),
                where={"source_id": {"$in": ids}},
            )
            if result["documents"] and result["documents"][0]:
                hit_metadata = result["metadatas"][0][0]
                matched_source_id = str(hit_metadata.get("source_id", ""))
                matched_record = next(
                    (record for record in candidates if str(record["source_id"]) == matched_source_id),
                    None,
                )
                hit_section = str(
                    matched_record["section"] if matched_record else hit_metadata.get("chapter", "")
                )
                chapter = [record for record in candidates if str(record["section"]) == hit_section]
                if chapter:
                    metadata = dict(hit_metadata)
                    metadata["chapter"] = hit_section
                    end_line = chapter[-1].get("end_line_number", chapter[-1]["line_number"])
                    metadata["line_number"] = f"{chapter[0]['line_number']}-{end_line}"
                    metadata["source_ids"] = [str(record["source_id"]) for record in chapter]
                    metadata["matched_source_id"] = matched_source_id
                    return [{
                        "document": "\n".join(str(record["text"]) for record in chapter),
                        "metadata": metadata,
                        "distance": result["distances"][0][0],
                    }], "chapter_conditioned", hit_section

    # 每本书仍限定自己的书名；没有匹配章节时不跨书借用结果。
    results = collection.query(
        query_texts=[topic],
        n_results=min(max(count, 1), max(len(records), 1)),
        where={"book_name": book_name},
    )
    ranked = [
        {"document": document, "metadata": metadata, "distance": distance}
        for document, metadata, distance in zip(
            results["documents"][0], results["metadatas"][0], results["distances"][0]
        )
    ]
    return ranked, "semantic_reference", None
