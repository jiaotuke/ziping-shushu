import unittest
from pathlib import Path

from book_retrievers.ziping_zhenquan import retrieve
from source_data import load_source_records, ziping_chapter_boundaries


class ZipingChapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = load_source_records("子平真诠")

    def test_contents_entries_are_excluded_and_all_body_chapters_exist(self):
        self.assertGreaterEqual(min(r["line_number"] for r in self.records), 109)
        chapters = {r["section"] for r in self.records if r["section"] != "序"}
        self.assertEqual(len(chapters), 48)
        for chapter in chapters:
            body = [r for r in self.records if r["section"] == chapter]
            self.assertGreater(len(body), 1, chapter)

    def test_killing_chapter_returns_body_instead_of_contents_title(self):
        records = self.records
        hit = next(r for r in records if r["line_number"] == 1039)

        class Collection:
            def get(self, include):
                return {"ids": [r["source_id"] for r in records]}

            def query(self, **kwargs):
                self_query_ids = kwargs["where"]["source_id"]["$in"]
                assert hit["source_id"] in self_query_ids
                return {
                    "documents": [[hit["text"]]],
                    "metadatas": [[{"source_id": hit["source_id"], "chapter": hit["section"]}]],
                    "distances": [[0.1]],
                }

        output = retrieve({"四柱详情": {"年柱": {"天干十神": "七杀"}}}, "偏官取运", 1, Collection())
        result = output["results"][0]
        self.assertEqual(output["chapter"], "第40篇 论偏官取运")
        self.assertEqual(len(result["metadata"]["source_ids"]), 6)
        self.assertEqual(result["metadata"]["line_number"], "1039-1059")
        self.assertIn("偏官取运，即以偏官所成之局分而配之", result["document"])
        self.assertIn("七煞既纯，杂官不利", result["document"])
        self.assertNotIn("伤官虽非吉神", result["document"])

    def test_changed_chapter_anchor_fails_instead_of_misassigning_body(self):
        path = Path(__file__).resolve().parents[1] / "data" / "source" / "子平真诠.txt"
        lines = path.read_text(encoding="utf-8").splitlines()
        lines[1038] = "this source edition has changed"
        with self.assertRaisesRegex(ValueError, "篇章起句失效"):
            ziping_chapter_boundaries(lines)


if __name__ == "__main__":
    unittest.main()
