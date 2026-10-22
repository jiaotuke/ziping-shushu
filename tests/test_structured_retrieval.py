import unittest
import json
from pathlib import Path

from source_data import load_source_records, make_source_id
from rag import chart_chapter, expand_result_to_chapter, records_in_chapter
from structured_retrieval import (
    filter_annotations,
    load_annotations,
    retrieval_metrics,
    validate_annotations,
)


class SourceRecordTests(unittest.TestCase):
    def test_source_record_keeps_full_original_line_and_location(self):
        records = load_source_records("穷通宝鉴")
        target = next(record for record in records if record["line_number"] == 24)
        self.assertEqual(target["section"], "三春甲木")
        self.assertIn("癸藏丙透", target["text"])
        self.assertEqual(
            target["source_id"],
            make_source_id(target["source_file"], 24, str(target["text"])),
        )

    def test_curated_annotation_points_to_exact_source_and_quote(self):
        records = {record["source_id"]: record for record in load_source_records()}
        annotations = load_annotations()
        self.assertGreaterEqual(len(annotations), 1)
        for annotation in annotations:
            record = records[annotation["source_id"]]
            self.assertIn(annotation["quote"], record["text"])

    def test_retrieval_eval_case_has_a_matching_condition_annotation(self):
        root = Path(__file__).resolve().parents[1]
        cases = json.loads((root / "eval" / "retrieval_cases.json").read_text(encoding="utf-8"))["cases"]
        annotations = load_annotations()
        for case in cases:
            eligible = filter_annotations(annotations, case["conditions"])
            eligible_ids = {annotation["source_id"] for annotation in eligible}
            self.assertTrue(set(case["expected_source_ids"]).issubset(eligible_ids))

    def test_stale_source_or_quote_annotations_are_rejected(self):
        source = load_source_records()[:1]
        valid = {
            "annotation_id": "valid",
            "source_id": source[0]["source_id"],
            "quote": source[0]["text"],
        }
        stale_source = {**valid, "annotation_id": "stale", "source_id": "changed"}
        stale_quote = {**valid, "annotation_id": "wrong-quote", "quote": "not present"}
        accepted, issues = validate_annotations([valid, stale_source, stale_quote], source)
        self.assertEqual([item["annotation_id"] for item in accepted], ["valid"])
        self.assertEqual(len(issues), 2)

    def test_gui_water_chou_month_returns_the_complete_month_chapter(self):
        records = load_source_records()
        conditions = {"day_master": "癸", "month_branch": "丑"}
        chapter = chart_chapter(conditions, records)
        self.assertEqual(chapter, "十二月癸水")

        chapter_records = records_in_chapter(records, chapter)
        self.assertEqual(len(chapter_records), 9)
        matched = chapter_records[3]
        result = expand_result_to_chapter(
            {
                "document": matched["text"],
                "metadata": {
                    "chapter": chapter,
                    "source_id": matched["source_id"],
                    "source_file": matched["source_file"],
                    "citation": matched["citation"],
                    "line_number": matched["line_number"],
                },
                "distance": 0.1,
            },
            records,
        )

        expected_text = "\n".join(str(record["text"]) for record in chapter_records)
        self.assertEqual(result["document"], expected_text)
        self.assertEqual(result["metadata"]["line_number"], "1361-1369")
        self.assertEqual(
            result["metadata"]["source_ids"],
            [str(record["source_id"]) for record in chapter_records],
        )
        self.assertEqual(result["metadata"]["matched_source_id"], matched["source_id"])


class ConditionFilterTests(unittest.TestCase):
    def setUp(self):
        self.annotations = [
            {
                "source_id": "rule-1",
                "status": "provisional",
                "conditions": {
                    "day_master": "甲",
                    "month_branch": "寅",
                    "required_exposed_stems": ["丙"],
                    "required_hidden_stems": ["癸"],
                },
            },
            {
                "source_id": "rule-draft",
                "status": "draft",
                "conditions": {"day_master": "甲", "month_branch": "寅"},
            },
        ]
        self.chart_conditions = {
            "day_master": "甲",
            "month_branch": "寅",
            "exposed_stems": ["甲", "丙"],
            "hidden_stems": ["癸", "戊"],
        }

    def test_filters_conditions_before_candidates_are_ranked(self):
        results = filter_annotations(self.annotations, self.chart_conditions)
        self.assertEqual([item["source_id"] for item in results], ["rule-1"])

    def test_missing_required_exposed_or_hidden_stem_excludes_rule(self):
        no_bing = {**self.chart_conditions, "exposed_stems": ["甲"]}
        no_gui_hidden = {**self.chart_conditions, "hidden_stems": ["戊"]}
        self.assertEqual(filter_annotations(self.annotations, no_bing), [])
        self.assertEqual(filter_annotations(self.annotations, no_gui_hidden), [])

    def test_wrong_day_master_or_month_branch_excludes_rule(self):
        for key, value in (("day_master", "乙"), ("month_branch", "卯")):
            with self.subTest(key=key):
                self.assertEqual(
                    filter_annotations(self.annotations, {**self.chart_conditions, key: value}),
                    [],
                )

    def test_draft_annotations_are_never_used(self):
        only_draft = [self.annotations[1]]
        self.assertEqual(filter_annotations(only_draft, self.chart_conditions), [])

    def test_provisional_annotation_can_be_excluded_for_strict_mode(self):
        self.assertEqual(
            filter_annotations(
                self.annotations, self.chart_conditions, include_provisional=False
            ),
            [],
        )


class RetrievalMetricTests(unittest.TestCase):
    def test_reports_recall_precision_and_reciprocal_rank_at_k(self):
        metrics = retrieval_metrics(
            {"relevant-a", "relevant-b"},
            ["noise", "relevant-a", "relevant-b", "outside-k"],
            k=3,
        )
        self.assertEqual(metrics, {"recall@3": 1.0, "precision@3": 2 / 3, "reciprocal_rank": 0.5})


if __name__ == "__main__":
    unittest.main()
