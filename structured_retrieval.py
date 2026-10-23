"""Condition-first filtering and evaluation helpers for curated book annotations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from runtime_paths import RESOURCE_ROOT as ROOT
ANNOTATION_FILE = ROOT / "data" / "annotations" / "conditions.json"


def load_annotations(path: Path = ANNOTATION_FILE) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("不支持的条件标注 schema_version")
    return data["annotations"]


def validate_annotations(
    annotations: list[dict[str, Any]], source_records: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Reject annotations whose stable source ID or exact excerpt no longer matches."""
    records_by_id = {
        source_id: record
        for record in source_records
        for source_id in [
            str(record["source_id"]),
            *(str(alias) for alias in record.get("source_aliases", [])),
        ]
    }
    valid: list[dict[str, Any]] = []
    issues: list[str] = []
    for annotation in annotations:
        source_id = str(annotation.get("source_id", ""))
        record = records_by_id.get(source_id)
        if record is None:
            issues.append(f"{annotation.get('annotation_id', source_id)}: stale source_id")
        elif not annotation.get("quote") or str(annotation["quote"]) not in str(record["text"]):
            issues.append(f"{annotation.get('annotation_id', source_id)}: quote not in source")
        else:
            valid.append(annotation)
    return valid, issues


def filter_annotations(
    annotations: list[dict[str, Any]],
    conditions: dict[str, Any],
    *,
    include_provisional: bool = True,
) -> list[dict[str, Any]]:
    """Apply explicit chart-condition filters before semantic ranking."""
    day_master = conditions.get("day_master")
    month_branch = conditions.get("month_branch")
    exposed_stems = set(conditions.get("exposed_stems", []))
    hidden_stems = set(conditions.get("hidden_stems", []))
    eligible = []

    for annotation in annotations:
        status = annotation.get("status")
        if status not in {"provisional", "verified"}:
            continue
        if status == "provisional" and not include_provisional:
            continue
        rule = annotation["conditions"]
        if rule.get("day_master") not in (None, day_master):
            continue
        if rule.get("month_branch") not in (None, month_branch):
            continue
        if not set(rule.get("required_exposed_stems", [])).issubset(exposed_stems):
            continue
        if not set(rule.get("required_hidden_stems", [])).issubset(hidden_stems):
            continue
        eligible.append(annotation)
    return eligible


def retrieval_metrics(expected_ids: set[str], actual_ids: list[str], k: int) -> dict[str, float]:
    """Calculate basic retrieval metrics for a manually judged query case."""
    top = actual_ids[:k]
    hits = [source_id for source_id in top if source_id in expected_ids]
    first_rank = next(
        (rank for rank, source_id in enumerate(top, start=1) if source_id in expected_ids),
        None,
    )
    return {
        f"recall@{k}": len(set(hits)) / len(expected_ids) if expected_ids else 1.0,
        f"precision@{k}": len(set(hits)) / k if k else 0.0,
        "reciprocal_rank": 1 / first_rank if first_rank else 0.0,
    }
