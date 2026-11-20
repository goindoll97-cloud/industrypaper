"""Trace frozen v4/v4.1 model outputs against private provisional Gold.

Purely diagnostic: never calls Ollama, never changes Gold, model outputs or prior
CSV scores. The new CSVs contain provisional answer labels and must stay local.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from gold_integrity import expected_gold_sha
from run_retrieval import DATA, MODELS, ROOT, load, parse_answer
from score_audit_v4 import inspect_run

FIELDS = (
    ("direct_cas_match", "direct_cas_match"),
    ("covered_by_clause", "covered_by_clause"),
    ("reasoning_category", "expected_relation"),
    ("relevant_entry_id", "relevant_entry_id"),
    ("relevant_sub_number", "relevant_sub_number"),
)
FAILURE_ORDER = ("missing_record", "api_error", "invalid_query", "invalid_answer",
                 "gold_row_not_retrieved", "scope_mismatch", "article3_mismatch",
                 "relation_mismatch", "direct_cas_mismatch", "entry_mismatch",
                 "sub_number_mismatch")


def _csv(path, rows):
    if not rows:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def diagnose(gold, run_rows, audit_cases, audit_components):
    """Return reproducible diagnosis from original saved JSONL, not inferred CSV scores.

    run_rows maps model to a list of original records; the last record for each
    test_id is authoritative (same convention as score_results.py).
    """
    gold_by_id = {g["test_id"]: g for g in gold}
    case_by_id = {(r["model"], r["test_id"]): r for r in audit_cases}
    comp_by_id = {(r["model"], r["test_id"], r["component_id"]): r for r in audit_components}
    details, cases, confusion = [], [], Counter()

    for model in MODELS:
        latest = {r["test_id"]: r for r in run_rows[model]}
        for test_id, g in gold_by_id.items():
            case = case_by_id[(model, test_id)]
            raw = latest.get(test_id)
            ids = [c["component_id"] for c in g["component_gold"]]
            answer = parse_answer(raw.get("answer_raw"), test_id, ids, g["group"] == "MIXTURE") if raw else None
            pred = {c["component_id"]: c for c in answer["components"]} if answer else {}
            mismatches = Counter()
            evidence_missed = []
            component_failures = []
            for c in g["component_gold"]:
                cid = c["component_id"]
                p = pred.get(cid)
                row = comp_by_id[(model, test_id, cid)]
                hit = bool(row["strict_gold_row_hit"])
                if not hit:
                    evidence_missed.append(cid)
                wrong = []
                for predkey, goldkey in FIELDS:
                    if p is None or p[predkey] != c[goldkey]:
                        wrong.append(predkey)
                if p:
                    for field in wrong:
                        mismatches[field] += 1
                elif answer is None:
                    mismatches["invalid_answer"] += 1
                if wrong:
                    component_failures.append(cid)
                predicted_rel = p["reasoning_category"] if p else "INVALID_ANSWER"
                confusion[(model, g["group"], g["difficulty"], c["expected_relation"], predicted_rel)] += 1
                retrieved = (raw or {}).get("retrieved_by_component", {}).get(cid, []) or []
                query_map = (raw or {}).get("queries") or {}
                details.append({
                    "model": model, "test_id": test_id, "case_id": g["case_id"],
                    "condition": g["condition"], "group": g["group"], "difficulty": g["difficulty"],
                    "component_id": cid, "cas": c["cas"],
                    "model_status": raw.get("status") if raw else "not_run",
                    "query_terms": json.dumps(query_map.get(cid, []), ensure_ascii=False),
                    "gold_row": c["source_excel_row"], "retrieved_gold_row": int(hit),
                    "retrieved_row_ids": json.dumps([z["excel_row"] for z in retrieved]),
                    "retrieved_designation_ids": json.dumps([z.get("designation_id") for z in retrieved], ensure_ascii=False),
                    "same_designation_different_row_candidate": int(
                        bool(row["same_designation_hit_diagnostic"]) and not hit),
                    "gold_relation": c["expected_relation"],
                    "predicted_relation": p["reasoning_category"] if p else "",
                    "gold_scope": c["covered_by_clause"],
                    "predicted_scope": p["covered_by_clause"] if p else "",
                    "gold_direct_cas": c["direct_cas_match"],
                    "predicted_direct_cas": p["direct_cas_match"] if p else "",
                    "gold_designation_id": c["relevant_entry_id"],
                    "predicted_designation_id": p["relevant_entry_id"] if p else "",
                    "gold_sub_number": c["relevant_sub_number"],
                    "predicted_sub_number": p["relevant_sub_number"] if p else "",
                    "wrong_fields": ";".join(wrong),
                    "provisional_human_review_only": 1,
                })
            flags = []
            if not raw:
                flags.append("missing_record")
            elif raw.get("status") == "api_error":
                flags.append("api_error")
            if raw and not case["query_valid"]:
                flags.append("invalid_query")
            if raw and not answer:
                flags.append("invalid_answer")
            if evidence_missed:
                flags.append("gold_row_not_retrieved")
            if answer:
                if mismatches["covered_by_clause"]:
                    flags.append("scope_mismatch")
                if g["group"] == "MIXTURE" and not case["article3_correct"]:
                    flags.append("article3_mismatch")
                for key, label in (("reasoning_category", "relation_mismatch"),
                                   ("direct_cas_match", "direct_cas_mismatch"),
                                   ("relevant_entry_id", "entry_mismatch"),
                                   ("relevant_sub_number", "sub_number_mismatch")):
                    if mismatches[key]:
                        flags.append(label)
            first_failure = next((f for f in FAILURE_ORDER if f in flags), "strict_success")
            cases.append({
                "model": model, "test_id": test_id, "case_id": g["case_id"],
                "condition": g["condition"], "group": g["group"], "difficulty": g["difficulty"],
                "status": raw.get("status") if raw else "not_run",
                "first_failure": first_failure, "all_failures": ";".join(flags),
                "missing_evidence_components": ";".join(evidence_missed),
                "mismatched_answer_components": ";".join(component_failures),
                "query_valid": case["query_valid"], "answer_valid": case["answer_valid"],
                "all_gold_rows_retrieved": case["all_gold_rows_retrieved"],
                "scope_plus_article3_correct": case["scope_plus_article3_correct"],
                "strict_case_exact": case["strict_case_exact"],
                "strict_end_to_end": case["strict_end_to_end"],
                "query_tokens": raw.get("query_eval_count") if raw else "",
                "answer_tokens": raw.get("reason_eval_count") if raw else "",
                "query_seconds": raw.get("query_seconds") if raw else "",
                "answer_seconds": raw.get("reason_seconds") if raw else "",
                "raw_error": raw.get("error") if raw else "",
                "model_reason_ko": answer.get("reason_ko", "") if answer else "",
            })

    relation_rows = [{
        "model": model, "group": group, "difficulty": difficulty,
        "gold_relation": expected, "predicted_relation": predicted, "n": n
    } for (model, group, difficulty, expected, predicted), n in sorted(confusion.items())]
    first_counts = Counter((r["model"], r["group"], r["difficulty"], r["first_failure"]) for r in cases)
    failure_rows = [{
        "model": model, "group": group, "difficulty": difficulty,
        "first_failure": reason, "n": n
    } for (model, group, difficulty, reason), n in sorted(first_counts.items())]

    pairs = []
    by_pair = {(r["model"], r["case_id"], r["condition"]): r for r in cases}
    for model in MODELS:
        for case_id in sorted({g["case_id"] for g in gold}):
            if (model, case_id, "A") not in by_pair or (model, case_id, "B") not in by_pair:
                continue  # Partial diagnostic fixtures or incomplete A/B cases
            a, b = by_pair[(model, case_id, "A")], by_pair[(model, case_id, "B")]
            pairs.append({
                "model": model, "case_id": case_id,
                "group": a["group"], "difficulty": a["difficulty"],
                "A_first_failure": a["first_failure"], "B_first_failure": b["first_failure"],
                "A_scope_plus_article3": a["scope_plus_article3_correct"],
                "B_scope_plus_article3": b["scope_plus_article3_correct"],
                "A_all_gold_rows_retrieved": a["all_gold_rows_retrieved"],
                "B_all_gold_rows_retrieved": b["all_gold_rows_retrieved"],
                "A_strict_end_to_end": a["strict_end_to_end"],
                "B_strict_end_to_end": b["strict_end_to_end"],
                "delta_scope": int(b["scope_plus_article3_correct"]) - int(a["scope_plus_article3_correct"]),
                "delta_e2e": int(b["strict_end_to_end"]) - int(a["strict_end_to_end"]),
            })
    return details, cases, relation_rows, failure_rows, pairs



RELATION_SCOPE = {
    "DIRECT_SPECIFIC": True,
    "GROUP_INCLUDED": True,
    "EXPLICIT_EXCEPTION": False,
    "NOT_COVERED": False,
}


def audit_consistency(component_rows):
    """Descriptive only: never reinterpret provisional Gold or repair model answers.

    'INSUFFICIENT_EVIDENCE' and empty/invalid relation output have no
    deterministic scope implication and are intentionally left unclassified.
    """
    import re
    output = []
    for c in component_rows:
        relation = c["predicted_relation"]
        scope = c["predicted_scope"]
        expected = RELATION_SCOPE.get(relation)
        scope_checkable = expected is not None and type(scope) is bool
        contradictory = int(scope_checkable and scope != expected)
        entry = c["predicted_designation_id"] or ""
        returned = json.loads(c["retrieved_designation_ids"])
        if not entry:
            grounding = "not_reported"
        elif entry in returned:
            grounding = "cited_returned_evidence"
        elif re.fullmatch(r"\d{2,4}-1-\d+", str(entry)):
            grounding = "legal_id_not_in_returned_evidence"
        else:
            grounding = "invalid_designation_id_format"
        output.append({
            "model": c["model"], "test_id": c["test_id"], "case_id": c["case_id"],
            "condition": c["condition"], "group": c["group"],
            "difficulty": c["difficulty"], "component_id": c["component_id"],
            "gold_relation": c["gold_relation"], "predicted_relation": relation,
            "predicted_scope": scope, "implied_scope": expected if expected is not None else "",
            "relation_scope_checkable": int(scope_checkable),
            "relation_scope_contradiction": contradictory,
            "predicted_designation_id": entry, "designation_grounding": grounding,
            "gold_row_retrieved": c["retrieved_gold_row"],
            "diagnostic_only_not_rescored": 1,
        })
    by_group = defaultdict(list)
    for row in output:
        by_group[(row["model"], "ALL", "ALL")].append(row)
        by_group[(row["model"], row["group"], "ALL")].append(row)
        by_group[(row["model"], row["group"], row["difficulty"])].append(row)
    summary = []
    for (model, group, difficulty), rows in sorted(by_group.items()):
        n = len(rows)
        checked = sum(r["relation_scope_checkable"] for r in rows)
        contrad = sum(r["relation_scope_contradiction"] for r in rows)
        counts = Counter(r["designation_grounding"] for r in rows)
        summary.append({
            "model": model, "group": group, "difficulty": difficulty,
            "component_n": n, "relation_scope_checkable_n": checked,
            "relation_scope_contradiction_n": contrad,
            "relation_scope_contradiction_pct_checked": round(100 * contrad / checked, 2) if checked else "",
            "cited_returned_evidence_n": counts["cited_returned_evidence"],
            "legal_id_not_in_returned_evidence_n": counts["legal_id_not_in_returned_evidence"],
            "invalid_designation_id_format_n": counts["invalid_designation_id_format"],
            "designation_id_not_reported_n": counts["not_reported"],
            "predicted_not_covered_n": sum(r["predicted_relation"] == "NOT_COVERED" for r in rows),
            "diagnostic_only_not_rescored": 1,
        })
    return output, summary



def main(argv=None):
    parser = argparse.ArgumentParser(description="원본 LLM 응답으로 오류 원인을 추적하는 로컬 전용 진단")
    parser.add_argument("--results-dir", default="results_v4_1")
    ns = parser.parse_args(argv)
    folder = ROOT / ns.results_dir
    gp = ROOT / "private" / "gold_60.jsonl"
    mf = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    if not gp.is_file():
        parser.error("Gold 파일이 없습니다: private/gold_60.jsonl")
    gold_sha = hashlib.sha256(gp.read_bytes()).hexdigest()
    if gold_sha != expected_gold_sha(ROOT, mf):
        parser.error("Gold SHA256 검증 실패")
    gold = load(gp)
    if len(gold) != 60 or len({g["test_id"] for g in gold}) != 60:
        parser.error("Gold는 고유한 test_id 60개여야 합니다")

    audit_cases, audit_components, _, runs = inspect_run(folder, gold)
    raws = {model: load(folder / (model.replace(":", "_") + "__main.jsonl")) for model in MODELS}
    detailed, cases, relations, failures, pairs = diagnose(gold, raws, audit_cases, audit_components)
    consistency_components, consistency_summary = audit_consistency(detailed)
    queue = []
    for d in detailed:
        reasons = []
        if d["same_designation_different_row_candidate"]:
            reasons.append("same_designation_different_gold_row")
        if d["predicted_relation"] and d["predicted_relation"] != d["gold_relation"]:
            reasons.append("relation_disagreement")
        if d["predicted_scope"] != "" and d["predicted_scope"] != d["gold_scope"]:
            reasons.append("scope_disagreement")
        if d["predicted_designation_id"] != "" and d["predicted_designation_id"] != d["gold_designation_id"]:
            reasons.append("entry_disagreement")
        if reasons:
            queue.append({"review_reason": ";".join(reasons), **d})
    out = folder / "scoring_audit" / ("gold_" + gold_sha[:12]) / "error_diagnosis"
    out.mkdir(parents=True, exist_ok=True)
    for name, data in (
        ("component_discrepancies.csv", detailed),
        ("case_failure_taxonomy.csv", cases),
        ("relation_confusion.csv", relations),
        ("first_failure_counts.csv", failures),
        ("paired_AB_failure_comparison.csv", pairs),
        ("expert_review_queue.csv", queue),
    ):
        _csv(out / name, data)
    consistency_dir = out / "consistency_audit"
    consistency_dir.mkdir(parents=True, exist_ok=True)
    _csv(consistency_dir / "component_consistency.csv", consistency_components)
    _csv(consistency_dir / "consistency_summary.csv", consistency_summary)
    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "gold_sha256": gold_sha, "run_files": runs,
        "case_rows": len(cases), "component_rows": len(detailed),
        "review_queue_rows": len(queue),
        "consistency_component_rows": len(consistency_components),
        "consistency_definition": "Predicted relation-scope contradictions; INSUFFICIENT_EVIDENCE is not logically classified",
        "grounding_definition": "Whether predicted designation ID appeared in the component returned evidence; NOT an independent truth judgement",
        "strict_retrieval": "Only exact Gold source_excel_row is counted as a retrieval success",
        "failure_attribution": "First failure is a diagnostic ordering; all_failures is multivariate, not causal",
        "alternative_entry_rule": "Same designation but different Gold row is NOT credited automatically",
        "gold_review": "CURATED_PROVISIONAL; no independent expert verification",
    }
    (out / "diagnosis_manifest.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("PASS: 기존 실험 출력·점수 변경 없음; 오류 진단 완료")
    print("분석 경로:", out)
    print("Qwen 2.5의 관계 유형 오답과 HARD 혼합물 근거/판정 오류를 CSV별로 확인할 수 있습니다.")


if __name__ == "__main__":
    main()
