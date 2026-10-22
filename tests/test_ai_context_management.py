import ast
import copy
import io
import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from ai_analysis import (
    AIError, CitationError, build_context, build_messages, context_signature,
    generate_report, prepare_context, check_connection, validate_report,
)
from citation_audit import reconcile_citations
from tests.test_ai_analysis import make_context, make_report, response_for, PILLARS


class ContextManagementTests(unittest.TestCase):
    def test_full_book_survives_and_wire_uses_short_ids_grouped_by_chapter(self):
        context = build_context({"四柱": PILLARS}, {"success": True, "results_by_book": {}})
        prepared = prepare_context(context)
        self.assertEqual([s["text"] for s in prepared["sources"]], [s["text"] for s in context["sources"]])
        self.assertEqual(prepared["sources"][0]["source_id"], "S001")
        wire = json.loads(build_messages(prepared)[1]["content"])
        self.assertEqual(len(wire["source_chapters"]), len({s["chapter"] for s in context["sources"]}))
        self.assertNotIn("sources", wire)
        self.assertNotIn("original_source_id", build_messages(prepared)[1]["content"])
        self.assertTrue(prepared["context_budget"]["fits"])
        self.assertEqual(prepare_context(prepared), prepared)

    def test_model_windows_and_output_budgets(self):
        for provider, model, window in (("zhipu", "glm-4.7-flash", 200000),
                                         ("zhipu", "glm-5.3", 1000000),
                                         ("deepseek", "deepseek-flash", 1000000)):
            prepared = prepare_context(make_context(), provider=provider, model=model)
            budget = prepared["context_budget"]
            self.assertEqual(budget["window"], window)
            self.assertGreater(budget["output_reserved"], 16000)
            self.assertLess(budget["input_estimate"] + budget["output_reserved"] + budget["safety_reserved"], window)

    def test_overflow_keeps_method_and_drops_whole_support_paragraph(self):
        context = make_context()
        context["sources"].append({"source_id": "support", "book_name": "滴天髓", "chapter": "论甲日干",
                                   "line_number": "1-5", "text": "甲" * 10000})
        prepared = prepare_context(context, model="custom", custom_window=16384, thinking=False)
        self.assertEqual(len(prepared["sources"]), 1)
        self.assertEqual(prepared["sources"][0]["text"], context["sources"][0]["text"])
        self.assertEqual(prepared["context_budget"]["omitted_paragraphs"], 1)
        self.assertEqual(prepare_context(prepared, model="custom", custom_window=16384, thinking=False), prepared)

    def test_method_overflow_blocks_before_network(self):
        context = make_context()
        context["sources"][0]["text"] *= 10000
        opener = MagicMock()
        with self.assertRaisesRegex(AIError, "全文未截断"):
            generate_report("dummy", context, model="custom", custom_window=16384, opener=opener)
        opener.assert_not_called()

    def test_glm53_checks_and_generation_use_enabled_thinking(self):
        requests = []
        def opener(request, timeout):
            requests.append(json.loads(request.data))
            return io.BytesIO(b'{"choices":[{"message":{"content":"ok"}}]}')
        check_connection("dummy", model="glm-5.3", opener=opener)
        self.assertEqual(requests[0]["thinking"]["type"], "enabled")
        self.assertEqual(requests[0]["reasoning_effort"], "low")
        self.assertGreater(requests[0]["max_tokens"], 64)
        prepared = prepare_context(make_context(), model="glm-5.3", thinking=False)
        self.assertEqual(context_signature(prepared, model="glm-5.3", thinking=False),
                         context_signature(prepared, model="glm-5.3", thinking=True))

    def test_explicit_repair_sends_draft_and_checks_budget_and_result(self):
        requests = []
        def opener(request, timeout):
            requests.append(json.loads(request.data))
            return response_for(make_report())
        result = generate_report("dummy", make_context(), repair_report=make_report(),
                                 repair_issues=[{"step": 2, "issue": "unknown_source_id"}], opener=opener)
        self.assertEqual(len(requests), 1)
        self.assertEqual(len(requests[0]["messages"]), 3)
        self.assertTrue(result["context_budget"]["fits"])
        too_large = {"text": "甲" * 100000}
        opener = MagicMock()
        with self.assertRaisesRegex(AIError, "本次未发送请求"):
            generate_report("dummy", make_context(), repair_report=too_large, opener=opener)
        opener.assert_not_called()


class CitationDiagnosticsTests(unittest.TestCase):
    def test_whitespace_is_restored_to_exact_original(self):
        context = make_context()
        context["sources"][0]["text"] = "八字用神，\n专求月令。"
        report = make_report()
        report["steps"][1]["citations"][0]["quote"] = "八字用神，专求月令"
        fixed, changes = reconcile_citations(report, context["sources"])
        self.assertEqual(fixed["steps"][1]["citations"][0]["quote"], "八字用神，\n专求月令")
        self.assertTrue(changes)
        validate_report(fixed, context)
        self.assertNotEqual(report, fixed)

    def test_unique_full_quote_resolves_bad_id_but_ambiguity_does_not(self):
        context = make_context()
        report = make_report()
        citation = report["steps"][1]["citations"][0]
        citation.update(source_id="wrong", quote="八字用神，专求月令")
        fixed, changes = reconcile_citations(report, context["sources"])
        self.assertEqual(fixed["steps"][1]["citations"][0]["source_id"], "source-a")
        context["sources"].append({**context["sources"][0], "source_id": "duplicate"})
        fixed, changes = reconcile_citations(report, context["sources"])
        self.assertEqual(fixed["steps"][1]["citations"][0]["source_id"], "wrong")
        self.assertFalse(changes)

    def test_fabricated_quote_stays_rejected_and_has_actual_step_number(self):
        report = make_report()
        report["steps"][4]["citations"][0]["quote"] = "并非书中原文的虚构语句"
        fixed, changes = reconcile_citations(report, make_context()["sources"])
        with self.assertRaises(CitationError) as caught:
            validate_report(fixed, make_context())
        self.assertEqual(caught.exception.issues[0]["step"], 5)
        self.assertEqual(caught.exception.issues[0]["issue"], "quote_not_in_source")
        self.assertEqual(caught.exception.report, fixed)

    def test_malformed_draft_is_not_a_crash_in_reconciliation(self):
        for report in ([], {"steps": None}, {"steps": [None]}):
            fixed, changes = reconcile_citations(report, make_context()["sources"])
            with self.assertRaises(AIError):
                validate_report(fixed, make_context())


class RetrievalNavigationTests(unittest.TestCase):
    def test_successful_retrieval_only_navigates_and_new_chart_retrieves(self):
        # Extract the pure callback without executing Streamlit's page or loading models.
        tree = ast.parse(Path("app.py").read_text(encoding="utf-8"))
        callback = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "queue_retrieval")
        module = ast.Module(body=[callback], type_ignores=[])
        ui = MagicMock()
        namespace = {"st": ui, "RETRIEVAL_VERSION": "current"}
        exec(compile(module, "app.py", "exec"), namespace)
        ui.session_state = {"retrieval_result": {"success": True, "version": "current"}, "active_panel": "ai"}
        namespace["queue_retrieval"]()
        self.assertEqual(ui.session_state["active_panel"], "books")
        self.assertNotIn("retrieval_requested", ui.session_state)
        ui.session_state = {}
        namespace["queue_retrieval"]()
        self.assertTrue(ui.session_state["retrieval_requested"])
        self.assertTrue(ui.session_state["retrieval_running"])


if __name__ == "__main__":
    unittest.main()
