import tempfile
import unittest
from pathlib import Path

from book_retrievers.ditian_sui import SOURCE_FILE, STEM_OPENERS, load_day_stem_records, retrieve
from source_data import load_source_records


class ExactCollection:
    def __init__(self, records):
        self.records = records

    def get(self, where, include):
        rules = {key: value for rule in where["$and"] for key, value in rule.items()}
        assert rules["book_name"] == "滴天髓"
        records = [r for r in self.records if r["day_master"] == rules["day_master"]]
        return {
            "ids": [r["source_id"] for r in records],
            "documents": [r["text"] for r in records],
            "metadatas": [{"chapter": r["section"], "source_id": r["source_id"]} for r in records],
        }

    def query(self, **kwargs):
        raise AssertionError("日干专论不应调用语义检索")


class DitianSuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = load_day_stem_records()

    def test_index_contains_only_ten_day_stem_articles(self):
        self.assertEqual([r["day_master"] for r in self.records], list(STEM_OPENERS))
        self.assertEqual(load_source_records("滴天髓"), self.records)
        self.assertEqual(len({r["source_id"] for r in self.records}), 10)

    def test_each_article_preserves_source_paragraphs_and_punctuation(self):
        lines = SOURCE_FILE.read_text(encoding="utf-8").splitlines()
        for record in self.records:
            original = [line.strip() for line in lines[record["line_number"] - 1:record["end_line_number"]] if line.strip()]
            self.assertEqual(record["text"].split("\n\n"), original)
            self.assertEqual(len(original), 3)
            if record["day_master"] == "己":
                self.assertTrue(original[1].startswith("己土卑薄软湿"))
            else:
                self.assertTrue(original[1].startswith("原注："))
            self.assertTrue(original[2].startswith("任氏曰："))
            self.assertNotIn("八、地支", record["text"])

    def test_all_ten_day_stems_return_exact_article_despite_unrelated_topic(self):
        collection = ExactCollection(self.records)
        for record in self.records:
            output = retrieve({"四柱": {"日柱": record["day_master"] + "子"}}, "月令 旺衰 其他天干", 5, collection)
            self.assertEqual(output["mode"], "day_stem_exact")
            self.assertEqual(len(output["results"]), 1)
            self.assertEqual(output["results"][0]["document"], record["text"])

    def test_missing_day_or_article_reports_error_without_fallback(self):
        with self.assertRaisesRegex(ValueError, "有效的日干"):
            retrieve({}, "", 1, ExactCollection(self.records))
        with self.assertRaisesRegex(ValueError, "索引缺失或重复"):
            retrieve({"四柱": {"日柱": "癸丑"}}, "", 1, ExactCollection([]))

    def test_missing_source_opener_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "滴天髓.txt"
            path.write_text(SOURCE_FILE.read_text(encoding="utf-8").replace("癸水至弱", "此起句已变"), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "起句缺失"):
                load_day_stem_records(path)


if __name__ == "__main__":
    unittest.main()
