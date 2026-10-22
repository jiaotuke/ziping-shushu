"""Mechanical citation checks for generated reports; not a semantic truth judge."""

from __future__ import annotations

from typing import Any
import copy


def reconcile_citations(report: dict, source_records: list[dict]) -> tuple[dict, list[str]]:
    """Resolve only unique literal matches; never fuzzy-match or invent a quote."""
    result = copy.deepcopy(report)
    by_id = {str(r["source_id"]): r for r in source_records}
    aliases = {str(r.get("original_source_id", r["source_id"])): r for r in source_records}
    changes = []

    def exact_span(text: str, quote: str) -> str | None:
        if quote and quote in text:
            return quote
        # Whitespace alone may differ because the model joined wrapped source lines.
        needle = "".join(c for c in quote if not c.isspace())
        if len(needle) < 4:
            return None
        positions = [i for i, c in enumerate(text) if not c.isspace()]
        plain = "".join(text[i] for i in positions)
        start = plain.find(needle)
        if start < 0 or plain.find(needle, start + 1) >= 0:
            return None
        return text[positions[start]:positions[start + len(needle) - 1] + 1]

    steps = result.get("steps", []) if isinstance(result, dict) else []
    if not isinstance(steps, list):
        return result, changes
    for step in steps:
        if not isinstance(step, dict) or not isinstance(step.get("citations"), list):
            continue
        for citation in step["citations"]:
            if not isinstance(citation, dict):
                continue
            source_id, quote = citation.get("source_id"), citation.get("quote")
            if not isinstance(source_id, str) or not isinstance(quote, str) or not quote.strip():
                continue
            record = by_id.get(source_id) or aliases.get(source_id)
            span = exact_span(record["text"], quote) if record else None
            if span is None:
                matches = [(r, exact_span(r["text"], quote)) for r in source_records]
                matches = [(r, q) for r, q in matches if q is not None]
                # Short generic fragments cannot establish a different source.
                if len(matches) != 1 or len("".join(quote.split())) < 8:
                    continue
                record, span = matches[0]
            if citation != {"source_id": record["source_id"], "quote": span}:
                citation["source_id"] = record["source_id"]
                citation["quote"] = span
                changes.append(f"第{step.get('step', '?')}步：已按原文核定引用编号或空白格式。")
    return result, changes


def audit_report_citations(
    claims: list[dict[str, Any]], source_records: list[dict[str, Any]]
) -> list[dict[str, str]]:
    """Check citation existence and exact quotation; semantic support still needs review."""
    by_id = {str(record["source_id"]): record for record in source_records}
    issues: list[dict[str, str]] = []
    for claim_index, claim in enumerate(claims, start=1):
        citations = claim.get("citations", [])
        if not citations:
            issues.append({"claim": str(claim_index), "issue": "missing_citation"})
            continue
        for citation in citations:
            source_id = str(citation.get("source_id", ""))
            record = by_id.get(source_id)
            if record is None:
                issues.append({"claim": str(claim_index), "issue": "unknown_source_id"})
                continue
            quote = str(citation.get("quote", ""))
            if not quote or quote not in str(record["text"]):
                issues.append({"claim": str(claim_index), "issue": "quote_not_in_source"})
    return issues
