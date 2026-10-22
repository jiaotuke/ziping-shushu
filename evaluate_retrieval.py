"""Run the manually judged top-k retrieval set against the current Chroma index."""

from __future__ import annotations

import json
from pathlib import Path

from rag import get_collection, retrieve_chart_records
from structured_retrieval import retrieval_metrics

ROOT = Path(__file__).resolve().parent
CASE_FILE = ROOT / "eval" / "retrieval_cases.json"


def main() -> None:
    cases = json.loads(CASE_FILE.read_text(encoding="utf-8"))["cases"]
    collection = get_collection()
    if collection.count() == 0:
        raise SystemExit("Chroma 索引为空；请先运行 python rag.py ingest")

    for case in cases:
        ranked, issues = retrieve_chart_records(
            case["topic"],
            case["top_k"],
            case["conditions"],
            collection=collection,
        )
        returned_ids = [item["metadata"]["source_id"] for item in ranked]
        metrics = retrieval_metrics(
            set(case["expected_source_ids"]), returned_ids, case["top_k"]
        )
        print(f"\n案例：{case['case_id']}")
        print(f"返回的原文 ID：{returned_ids}")
        print(f"指标：{metrics}")
        if issues:
            print(f"标注校验问题：{issues}")
        missed = set(case["expected_source_ids"]) - set(returned_ids)
        if missed:
            print(f"未召回的人工标注原文：{sorted(missed)}")


if __name__ == "__main__":
    main()
