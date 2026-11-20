"""Regression tests for read-only staged scoring; no Ollama or expert Gold required."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from score_audit_v4 import inspect_run
from run_retrieval import MODELS


def component_gold(cid, cas, row, entry, direct, relation="DIRECT_SPECIFIC"):
    return {
        "component_id": cid, "cas": cas, "source_excel_row": row,
        "relevant_entry_id": entry, "relevant_sub_number": None,
        "direct_cas_match": direct, "covered_by_clause": True,
        "expected_relation": relation,
    }


def answer_component(c):
    return {
        "component_id": c["component_id"],
        "direct_cas_match": c["direct_cas_match"],
        "covered_by_clause": c["covered_by_clause"],
        "reasoning_category": c["expected_relation"],
        "relevant_entry_id": c["relevant_entry_id"],
        "relevant_sub_number": c["relevant_sub_number"],
    }


class StagedScoreTests(unittest.TestCase):
    def create_fixture(self, directory):
        salt = component_gold("C1", "65-30-5", 33, "97-1-11", False, "GROUP_INCLUDED")
        m1 = component_gold("C1", "98-95-3", 34, "97-1-12", True)
        m2 = component_gold("C2", "67-56-1", 102, "97-1-80", True)
        gold = [
            dict(test_id="S-01-A", case_id="S-01", condition="A",
                 group="PARENT_AND_SALTS", difficulty="EASY",
                 component_gold=[salt], mixture_article3_all_listed=None,
                 review_status="CURATED_PROVISIONAL", independent_expert_review_completed=False),
            dict(test_id="M-01-A", case_id="M-01", condition="A",
                 group="MIXTURE", difficulty="EASY",
                 component_gold=[m1, m2], mixture_article3_all_listed=True,
                 review_status="CURATED_PROVISIONAL", independent_expert_review_completed=False),
        ]
        for model in MODELS:
            outputs = []
            for g in gold:
                comp = g["component_gold"]
                hits = {}
                for c in comp:
                    evidence_row = c["source_excel_row"]
                    # The salt row has the correct designation but NOT the Gold row.
                    if g["case_id"] == "S-01":
                        evidence_row = 999
                    hits[c["component_id"]] = [{
                        "excel_row": evidence_row,
                        "designation_id": c["relevant_entry_id"],
                    }]
                outputs.append({
                    "test_id": g["test_id"], "model": model,
                    "settings_sha256": "same_settings_for_a_model",
                    "status": "ok",
                    "queries": {c["component_id"]: ["test query"] for c in comp},
                    "retrieved_by_component": hits,
                    "answer_raw": json.dumps({
                        "test_id": g["test_id"],
                        "components": [answer_component(c) for c in comp],
                        "all_components_designated": True if g["group"] == "MIXTURE" else None,
                        "reason_ko": "test case",
                    }),
                })
            (directory / (model.replace(":", "_") + "__main.jsonl")).write_text(
                "".join(json.dumps(x) + "\n" for x in outputs), encoding="utf-8")
        return gold

    def test_strict_definition_preserved_and_scope_separated(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            gold = self.create_fixture(dest)
            cases, comps, summary, runs = inspect_run(dest, gold)
            self.assertEqual(len(cases), 2 * len(MODELS))
            self.assertEqual(len(comps), 3 * len(MODELS))
            for model in MODELS:
                rows = [r for r in cases if r["model"] == model]
                by_id = {r["test_id"]: r for r in rows}
                salt, mixture = by_id["S-01-A"], by_id["M-01-A"]
                self.assertEqual(salt["all_scope_correct"], 1)
                self.assertEqual(salt["strict_case_exact"], 1)
                self.assertEqual(salt["all_gold_rows_retrieved"], 0)
                self.assertEqual(salt["strict_end_to_end"], 0)
                self.assertEqual(salt["nominal_top_k_per_component"], 8)
                self.assertEqual(mixture["scope_plus_article3_correct"], 1)
                self.assertEqual(mixture["strict_end_to_end"], 1)
                self.assertEqual(mixture["nominal_top_k_per_component"], 5)
                same = [c for c in comps if c["model"] == model and c["test_id"] == "S-01-A"][0]
                self.assertEqual(same["same_designation_hit_diagnostic"], 1)
                self.assertEqual(same["strict_gold_row_hit"], 0)
                all_summary = next(r for r in summary if r["model"] == model and r["dimension"] == "ALL")
                self.assertEqual(all_summary["strict_case_exact_n"], 2)
                self.assertEqual(all_summary["strict_e2e_n"], 1)
                self.assertEqual(all_summary["all_gold_rows_retrieved_n"], 1)
                self.assertEqual(all_summary["scope_plus_article3_n"], 2)
                self.assertEqual(all_summary["query_valid_pct_observed"], 100)
                self.assertEqual(runs[model]["duplicates"], 0)

    def test_mixed_settings_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            gold = self.create_fixture(dest)
            name = MODELS[0].replace(":", "_") + "__main.jsonl"
            path = dest / name
            records = [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines()]
            records[1]["settings_sha256"] = "different"
            path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
            with self.assertRaises(ValueError):
                inspect_run(dest, gold)


if __name__ == "__main__":
    unittest.main()
