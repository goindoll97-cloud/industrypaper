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


    def test_paper_report_renders_without_changing_run_files(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from make_paper_report import render
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            gold = self.create_fixture(dest)
            cases, components, _, runs = inspect_run(dest, gold)
            before = {m: runs[m]["file_sha256"] for m in MODELS}
            consistency = [{
                "model": m, "group": "ALL", "difficulty": "ALL",
                "relation_scope_contradiction_n": 0,
                "relation_scope_checkable_n": 3,
                "cited_returned_evidence_n": 2, "component_n": 3,
                "invalid_designation_id_format_n": 0,
                "designation_id_not_reported_n": 0,
            } for m in MODELS]
            report = render(cases, components, consistency, runs, "a" * 64)
            self.assertIn("논문용 결과표", report)
            self.assertIn("엄격한 완전정답", report)
            self.assertIn("Qwen3.5 4B", report)
            self.assertIn("End-to-end", report)
            after = inspect_run(dest, gold)[3]
            self.assertEqual(before, {m: after[m]["file_sha256"] for m in MODELS})

    def test_stronger_control_is_opt_in_and_comparable(self):
        from run_retrieval import ADDITIONAL_MODELS
        from diagnose_raw_failures import diagnose, audit_consistency
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from make_paper_report import render
        self.assertEqual(ADDITIONAL_MODELS, ["qwen3.5:9b"])
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            gold = self.create_fixture(folder)
            strong = ADDITIONAL_MODELS[0]
            original = folder / (MODELS[-1].replace(":", "_") + "__main.jsonl")
            records = [json.loads(x) for x in original.read_text(encoding="utf-8").splitlines()]
            for row in records:
                row["model"] = strong
                row["settings_sha256"] = "isolated-strong-setting"
            (folder / (strong.replace(":", "_") + "__main.jsonl")).write_text(
                "".join(json.dumps(x) + "\n" for x in records), encoding="utf-8")
            base_cases, base_comps, _, base_info = inspect_run(folder, gold)
            extra_cases, extra_comps, _, extra_info = inspect_run(folder, gold, models=[strong])
            self.assertEqual(len(base_cases), 2 * len(MODELS))
            self.assertEqual(len(extra_cases), 2)
            self.assertEqual(len(extra_comps), 3)
            raw_by_model = {m: [
                json.loads(x) for x in
                (folder / (m.replace(":", "_") + "__main.jsonl")).read_text(
                    encoding="utf-8").splitlines()] for m in MODELS}
            base_detail = diagnose(gold, raw_by_model, base_cases, base_comps, models=MODELS)[0]
            extra_detail = diagnose(gold, {strong: records}, extra_cases,
                                    extra_comps, models=[strong])[0]
            cons = audit_consistency(base_detail + extra_detail)[1]
            report = render(base_cases + extra_cases, base_comps + extra_comps,
                            cons, {**base_info, **extra_info}, "a"*64,
                            models=[*MODELS, strong])
            self.assertIn("Qwen3.5 9B (추가)", report)
            self.assertIn("추후 평가한 대조군", report)
            self.assertIn("8 문항-모델", report)

    def test_pairwise_4b_9b_exposes_opposite_wins_and_overlapping_errors(self):
        from run_retrieval import ADDITIONAL_MODELS
        from diagnose_raw_failures import diagnose, audit_consistency
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from make_paper_report import render_paired_failure_analysis

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            gold = self.create_fixture(folder)
            small, large = MODELS[-1], ADDITIONAL_MODELS[0]
            original = folder / (small.replace(":", "_") + "__main.jsonl")
            records = [json.loads(x) for x in original.read_text(encoding="utf-8").splitlines()]
            for rec in records:
                rec["model"] = large
                rec["settings_sha256"] = "9b-frozen"
            # Original 4B misses the Gold salt row while 9B finds it.
            records[0]["retrieved_by_component"]["C1"][0]["excel_row"] = 33
            # Original 4B gets the mixture right; 9B has correct scope but wrong entry ID.
            answer = json.loads(records[1]["answer_raw"])
            answer["components"][0]["relevant_entry_id"] = "97-1-999"
            records[1]["answer_raw"] = json.dumps(answer)
            (folder / (large.replace(":", "_") + "__main.jsonl")).write_text(
                "".join(json.dumps(x) + "\n" for x in records), encoding="utf-8")

            case_small, comp_small, _, _ = inspect_run(folder, gold, models=[small])
            case_large, comp_large, _, _ = inspect_run(folder, gold, models=[large])
            original_rows = [json.loads(x) for x in original.read_text(encoding="utf-8").splitlines()]
            detail_small = diagnose(
                gold, {small: original_rows}, case_small, comp_small, models=[small])[0]
            detail_large = diagnose(
                gold, {large: records}, case_large, comp_large, models=[large])[0]
            consistency_rows = audit_consistency(detail_small + detail_large)[0]

            report = render_paired_failure_analysis(
                case_small + case_large, comp_small + comp_large,
                detail_small + detail_large, consistency_rows)
            self.assertIn("4B만 성공", report)
            self.assertIn("9B만 성공", report)
            self.assertIn("S-01-A", report)
            self.assertIn("M-01-A", report)
            self.assertIn("지정번호가 다름", report)
            self.assertIn("1건", report)
            # No raw scores or JSONLs are written over by the diagnostic.
            self.assertEqual(
                original.read_text(encoding="utf-8").splitlines()[0],
                json.dumps(original_rows[0]))

            with self.assertRaisesRegex(ValueError, "동일 test_id"):
                render_paired_failure_analysis(
                    case_small + case_large[:-1], comp_small + comp_large,
                    detail_small + detail_large, consistency_rows)

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
