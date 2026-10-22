import unittest

from citation_audit import audit_report_citations


class CitationAuditTests(unittest.TestCase):
    def setUp(self):
        self.records = [
            {
                "source_id": "src-1",
                "source_file": "book.txt",
                "line_number": 12,
                "text": "此处为古籍原文。",
            }
        ]

    def test_accepts_exact_quote_from_known_source(self):
        claims = [
            {
                "text": "报告中的说法",
                "citations": [{"source_id": "src-1", "quote": "古籍原文"}],
            }
        ]
        self.assertEqual(audit_report_citations(claims, self.records), [])

    def test_flags_missing_citation_unknown_source_and_invented_quote(self):
        claims = [
            {"text": "无引用说法"},
            {"text": "未知出处", "citations": [{"source_id": "missing", "quote": "古籍原文"}]},
            {"text": "错误原文", "citations": [{"source_id": "src-1", "quote": "书中没有这句"}]},
        ]
        self.assertEqual(
            [item["issue"] for item in audit_report_citations(claims, self.records)],
            ["missing_citation", "unknown_source_id", "quote_not_in_source"],
        )


if __name__ == "__main__":
    unittest.main()
