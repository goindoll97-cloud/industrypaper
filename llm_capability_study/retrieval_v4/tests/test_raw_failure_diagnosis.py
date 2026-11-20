"""Offline tests for raw-response diagnosis. No real Gold/LLM needed."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from run_retrieval import MODELS
from score_audit_v4 import inspect_run
from diagnose_raw_failures import diagnose


def gold_comp(cid, cas, row, entry, relation, covered, direct=False):
    return {
        "component_id": cid, "cas": cas, "source_excel_row": row,
        "relevant_entry_id": entry, "relevant_sub_number": None,
        "expected_relation": relation, "covered_by_clause": covered, "direct_cas_match": direct,
    }


def predicted(comp, *, relation=None, covered=None, entry=None):
    return {
        "component_id": comp["component_id"],
        "direct_cas_match": comp["direct_cas_match"],
        "covered_by_clause": comp["covered_by_clause"] if covered is None else covered,
        "reasoning_category": relation or comp["expected_relation"],
        "relevant_entry_id": comp["relevant_entry_id"] if entry is None else entry,
        "relevant_sub_number": comp["relevant_sub_number"],
    }


class DiagnoseTests(unittest.TestCase):
    def fixture(self, tmp):
        s = gold_comp("C1", "65-30-5", 33, "97-1-11", "GROUP_INCLUDED", True)
        a = gold_comp("C1", "14075-53-7", 466, "97-1-377", "EXPLICIT_EXCEPTION", False)
        b = gold_comp("C2", "67-56-1", 102, "97-1-80", "DIRECT_SPECIFIC", True, True)
        gold = [
            dict(test_id="S-01-A", case_id="S-01", condition="A", group="PARENT_AND_SALTS",
                 difficulty="EASY", component_gold=[s], mixture_article3_all_listed=None,
                 review_status="CURATED_PROVISIONAL", independent_expert_review_completed=False),
            dict(test_id="M-09-B", case_id="M-09", condition="B", group="MIXTURE",
                 difficulty="HARD", component_gold=[a, b], mixture_article3_all_listed=False,
                 review_status="CURATED_PROVISIONAL", independent_expert_review_completed=False),
        ]
        run_rows = {}
        for model in MODELS:
            data = [
                dict(model=model, test_id="S-01-A", status="ok", settings_sha256="unchanged",
                     queries={"C1": ["nicotine sulfate"]},
                     retrieved_by_component={"C1": [{"excel_row": 999, "designation_id": "97-1-11"}]},
                     answer_raw=json.dumps({"test_id": "S-01-A",
                         "components": [predicted(s, relation="NOT_COVERED", entry="97-1-999")],
                         "all_components_designated": None, "reason_ko": "wrong link"})),
                dict(model=model, test_id="M-09-B", status="ok", settings_sha256="unchanged",
                     queries={"C1": ["salt"], "C2": ["methanol"]},
                     retrieved_by_component={
                         "C1": [{"excel_row": 466, "designation_id": "97-1-377"}],
                         "C2": [{"excel_row": 102, "designation_id": "97-1-80"}]},
                     answer_raw=json.dumps({"test_id": "M-09-B",
                         "components": [predicted(a, covered=True), predicted(b)],
                         "all_components_designated": True, "reason_ko": "wrong exclusion"})),
            ]
            file = tmp / (model.replace(":", "_") + "__main.jsonl")
            file.write_text("".join(json.dumps(x) + "\n" for x in data), encoding="utf-8")
            run_rows[model] = data
        return gold, run_rows

    def test_relation_confusion_and_mixture_article3(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            gold, runs = self.fixture(folder)
            audited_cases, audited_components, _, _ = inspect_run(folder, gold)
            details, cases, confusion, failures, pairs = diagnose(
                gold, runs, audited_cases, audited_components)
            self.assertEqual(len(details), 3 * len(MODELS))
            self.assertEqual(len(cases), 2 * len(MODELS))
            for model in MODELS:
                salt = next(x for x in cases if x["model"] == model and x["test_id"] == "S-01-A")
                self.assertEqual(salt["first_failure"], "gold_row_not_retrieved")
                self.assertIn("relation_mismatch", salt["all_failures"])
                self.assertIn("entry_mismatch", salt["all_failures"])
                self.assertEqual(salt["strict_end_to_end"], 0)
                mix = next(x for x in cases if x["model"] == model and x["test_id"] == "M-09-B")
                self.assertIn("scope_mismatch", mix["all_failures"])
                self.assertIn("article3_mismatch", mix["all_failures"])
                self.assertEqual(mix["first_failure"], "scope_mismatch")
                comp = next(x for x in details if x["model"] == model and x["test_id"] == "S-01-A")
                self.assertEqual(comp["same_designation_different_row_candidate"], 1)
                self.assertEqual(comp["predicted_relation"], "NOT_COVERED")
                self.assertTrue(any(x["model"] == model and
                    x["gold_relation"] == "GROUP_INCLUDED" and
                    x["predicted_relation"] == "NOT_COVERED" for x in confusion))

    def test_invalid_answer_is_not_graded_as_reasoning(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            gold, runs = self.fixture(folder)
            for model in MODELS:
                runs[model][0]["answer_raw"] = "{invalid json"
                path = folder / (model.replace(":", "_") + "__main.jsonl")
                path.write_text("".join(json.dumps(x) + "\n" for x in runs[model]), encoding="utf-8")
            audited_cases, audited_components, _, _ = inspect_run(folder, gold)
            details, cases, confusion, *_ = diagnose(gold, runs, audited_cases, audited_components)
            for model in MODELS:
                salt = next(x for x in cases if x["model"] == model and x["test_id"] == "S-01-A")
                self.assertEqual(salt["first_failure"], "invalid_answer")
                self.assertNotIn("relation_mismatch", salt["all_failures"])
                self.assertTrue(any(x["model"] == model and x["predicted_relation"] == "INVALID_ANSWER" for x in confusion))


if __name__ == "__main__":
    unittest.main()
