"""Non-destructive diagnostic scoring for frozen v4/v4.1 results.

The existing score_results.py and its four CSV outputs stay unchanged.
No Gold, model answers or experiment records are uploaded to GitHub.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json

from gold_integrity import expected_gold_sha
from run_retrieval import MODELS, ROOT, DATA, load, parse_answer


def percent(num, denom):
    return round(100 * num / denom, 2) if denom else None


def write_csv(path, rows):
    if not rows:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def inspect_run(results_dir, gold):
    cases, components, summary, run_info = [], [], [], {}
    for model in MODELS:
        file = results_dir / (model.replace(":", "_") + "__main.jsonl")
        if not file.is_file():
            raise FileNotFoundError("본실험 원본 JSONL 없음: " + str(file))
        raw = load(file)
        by_id = {x["test_id"]: x for x in raw}
        hashes = {str(x.get("settings_sha256")) for x in raw}
        if len(hashes) != 1:
            raise ValueError(f"{model}: 실행 설정 해시가 섞여 있습니다: {hashes}")
        run_info[model] = {
            "settings_sha256": next(iter(hashes)),
            "raw_records": len(raw),
            "duplicates": len(raw) - len(by_id),
            "file_sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
        }
        for g in gold:
            test_id = g["test_id"]
            x = by_id.get(test_id)
            cg = g["component_gold"]
            ids = [c["component_id"] for c in cg]
            is_mix = g["group"] == "MIXTURE"
            ans = parse_answer(x.get("answer_raw"), test_id, ids, is_mix) if x else None
            answers = {a["component_id"]: a for a in ans["components"]} if ans else {}
            queries = x.get("queries") if x else None
            qvalid = isinstance(queries, dict) and set(queries) == set(ids) and all(
                isinstance(queries.get(cid), list) and len(queries[cid]) > 0 for cid in ids
            )
            component_scores = []
            k = 8 if len(cg) == 1 else (5 if len(cg) == 2 else 4)
            for c in cg:
                cid = c["component_id"]
                a = answers.get(cid)
                retrieved = (x or {}).get("retrieved_by_component", {}).get(cid, []) or []
                expected_row = int(c["source_excel_row"])
                strict_hit = any(int(z["excel_row"]) == expected_row for z in retrieved)
                same_item_hit = any(z.get("designation_id") == c["relevant_entry_id"] for z in retrieved)
                flags = {
                    "scope_correct": int(bool(a) and a["covered_by_clause"] == c["covered_by_clause"]),
                    "relation_correct": int(bool(a) and a["reasoning_category"] == c["expected_relation"]),
                    "direct_cas_correct": int(bool(a) and a["direct_cas_match"] == c["direct_cas_match"]),
                    "entry_correct": int(bool(a) and a["relevant_entry_id"] == c["relevant_entry_id"]),
                    "sub_number_correct": int(bool(a) and a["relevant_sub_number"] == c["relevant_sub_number"]),
                }
                component_scores.append({
                    "model": model, "test_id": test_id, "case_id": g["case_id"],
                    "condition": g["condition"], "group": g["group"], "difficulty": g["difficulty"],
                    "component_id": cid, "cas": c["cas"],
                    "gold_excel_row": expected_row, "gold_relation": c["expected_relation"],
                    "gold_entry": c["relevant_entry_id"], "gold_sub_number": c["relevant_sub_number"],
                    "nominal_top_k_per_component": k, "returned_rows": len(retrieved),
                    "strict_gold_row_hit": int(strict_hit),
                    "same_designation_hit_diagnostic": int(same_item_hit),
                    **flags, "component_exact": int(all(flags.values())),
                    "status": x.get("status") if x else "not_run",
                })
            components.extend(component_scores)
            all_retrieved = all(z["strict_gold_row_hit"] for z in component_scores)
            all_scope = all(z["scope_correct"] for z in component_scores)
            article3 = (ans["all_components_designated"] == g["mixture_article3_all_listed"]) if ans and is_mix else (None if not is_mix else False)
            scope_with_mix = bool(ans and all_scope and (not is_mix or article3))
            exact = bool(ans and all(z["component_exact"] for z in component_scores) and (not is_mix or article3))
            cases.append({
                "model": model, "test_id": test_id, "case_id": g["case_id"], "condition": g["condition"],
                "group": g["group"], "difficulty": g["difficulty"], "component_count": len(cg),
                "nominal_top_k_per_component": k, "status": x.get("status") if x else "not_run",
                "record_exists": int(x is not None), "query_valid": int(qvalid),
                "answer_valid": int(bool(ans)), "all_gold_rows_retrieved": int(all_retrieved),
                "retrieved_components": sum(z["strict_gold_row_hit"] for z in component_scores),
                "all_scope_correct": int(all_scope),
                "all_relation_correct": int(all(z["relation_correct"] for z in component_scores)),
                "all_entry_correct": int(all(z["entry_correct"] for z in component_scores)),
                "all_sub_number_correct": int(all(z["sub_number_correct"] for z in component_scores)),
                "all_direct_cas_correct": int(all(z["direct_cas_correct"] for z in component_scores)),
                "article3_correct": "" if not is_mix else int(bool(article3)),
                "scope_plus_article3_correct": int(scope_with_mix),
                "strict_case_exact": int(exact), "strict_end_to_end": int(exact and all_retrieved),
                "scope_correct_without_full_retrieval": int(scope_with_mix and not all_retrieved),
                "gold_status": g["review_status"],
                "expert_verified": int(g["independent_expert_review_completed"]),
            })
    for model in MODELS:
        rows = [r for r in cases if r["model"] == model]
        for dimension in ("ALL", "group", "difficulty", "condition", "group_difficulty"):
            groups = defaultdict(list)
            for r in rows:
                key = ("ALL" if dimension == "ALL" else
                       r["group"] + "/" + r["difficulty"] if dimension == "group_difficulty" else r[dimension])
                groups[key].append(r)
            for value, rs in sorted(groups.items()):
                n = len(rs)
                observed = sum(r["record_exists"] for r in rs)
                retrieved = [r for r in rs if r["all_gold_rows_retrieved"]]
                summary.append({
                    "model": model, "dimension": dimension, "value": value,
                    "planned": n, "observed": observed,
                    "query_valid_pct_observed": percent(sum(r["query_valid"] for r in rs), observed),
                    "answer_valid_pct_observed": percent(sum(r["answer_valid"] for r in rs), observed),
                    "all_gold_rows_retrieved_pct_planned": percent(len(retrieved), n),
                    "all_scope_correct_pct_planned": percent(sum(r["all_scope_correct"] for r in rs), n),
                    "scope_plus_article3_pct_planned": percent(sum(r["scope_plus_article3_correct"] for r in rs), n),
                    "all_relation_correct_pct_planned": percent(sum(r["all_relation_correct"] for r in rs), n),
                    "all_entry_correct_pct_planned": percent(sum(r["all_entry_correct"] for r in rs), n),
                    "strict_case_exact_pct_planned": percent(sum(r["strict_case_exact"] for r in rs), n),
                    "strict_e2e_pct_planned": percent(sum(r["strict_end_to_end"] for r in rs), n),
                    "scope_given_all_gold_retrieved_pct": percent(
                        sum(r["scope_plus_article3_correct"] for r in retrieved), len(retrieved)),
                    "all_gold_rows_retrieved_n": len(retrieved),
                    "scope_plus_article3_n": sum(r["scope_plus_article3_correct"] for r in rs),
                    "strict_case_exact_n": sum(r["strict_case_exact"] for r in rs),
                    "strict_e2e_n": sum(r["strict_end_to_end"] for r in rs),
                    "provisional_gold_n": sum(r["gold_status"] == "CURATED_PROVISIONAL" for r in rs),
                    "expert_verified_n": sum(r["expert_verified"] for r in rs),
                })
    return cases, components, summary, run_info


def main(argv=None):
    p = argparse.ArgumentParser(description="Re-score stage-wise metrics without changing original results")
    p.add_argument("--results-dir", default="results_v4_1")
    ns = p.parse_args(argv)
    results_dir = ROOT / ns.results_dir
    gold_file = ROOT / "private" / "gold_60.jsonl"
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    if not gold_file.is_file():
        p.error("비공개 Gold 없음: " + str(gold_file))
    gold_sha = hashlib.sha256(gold_file.read_bytes()).hexdigest()
    if gold_sha != expected_gold_sha(ROOT, manifest):
        p.error("Gold 무결성 오류: private/gold_registry.json 확인")
    gold = load(gold_file)
    if len(gold) != 60 or len({g["test_id"] for g in gold}) != 60:
        p.error("Gold 60문항 검증 실패")
    cases, components, summary, runs = inspect_run(results_dir, gold)
    dest = results_dir / "scoring_audit" / ("gold_" + gold_sha[:12])
    dest.mkdir(parents=True, exist_ok=True)
    write_csv(dest / "audit_cases.csv", cases)
    write_csv(dest / "audit_components.csv", components)
    write_csv(dest / "audit_summary.csv", summary)
    metadata = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "gold_sha256": gold_sha, "results_dir": str(results_dir),
        "model_runs": runs,
        "strict_evidence": "Only Gold source_excel_row is accepted for strict retrieval success",
        "same_designation_hit": "Diagnostic only; does NOT count as Gold evidence",
        "nominal_top_k": {"single": 8, "mixture_2_components": 5, "mixture_3_components": 4},
        "scope_definition": "Gold covered_by_clause match; not overall product legal compliance",
        "gold_status": "CURATED_PROVISIONAL; expert review not completed",
    }
    (dest / "audit_manifest.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("PASS: 원본 JSONL과 기존 4개 채점 CSV를 수정하지 않고 진단 완료")
    for row in summary:
        if row["dimension"] == "ALL":
            print(row["model"], f"{row['observed']}/{row['planned']}",
                  "scope+제3조:", row["scope_plus_article3_pct_planned"],
                  "strict:", row["strict_case_exact_pct_planned"],
                  "E2E:", row["strict_e2e_pct_planned"])
    print("분석 결과:", dest)
    print("Gold는 독립 전문가 검증 전 잠정 정답입니다.")


if __name__ == "__main__":
    main()
