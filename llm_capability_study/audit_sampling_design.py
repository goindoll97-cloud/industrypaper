#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stratification and selection-bias audit for the *draft* Study 3 benchmark.

Read-only toward the frozen 112 baseline, regulatory catalog and review sheet.
This script describes sample structure; it does NOT validate legal Gold labels.
It must be run on the current assembled draft (not an obsolete versioned CSV).
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

STRATA_COLUMNS = [
    "query_id", "origin", "gold_status", "n_gold_targets", "source_category",
    "candidate_stratum", "source_batch", "sampling_frame", "query_mode",
    "mixture_provenance", "positive_target_families", "is_frozen_baseline",
    "difficulty_tag", "source_case_ids",
]


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def ratio(n, d):
    return round(n / d, 4) if d else None


def cross_counts(rows, key):
    counts = defaultdict(Counter)
    for row in rows:
        counts[key(row)][row["gold_status"]] += 1
    return {
        category: {
            "FOUND": count["FOUND"],
            "NOT_FOUND": count["NOT_FOUND"],
            "total": count["FOUND"] + count["NOT_FOUND"],
            "found_share": ratio(count["FOUND"], sum(count.values())),
        }
        for category, count in sorted(counts.items())
    }


def target_families(gold):
    if gold == "NOT_FOUND":
        return ""
    family = {"CG": "CHEMICAL_GROUP", "PS": "PARENT_SALT", "MX": "MIXTURE"}
    return "|".join(sorted({family.get(t.split("::", 1)[0], "UNKNOWN") for t in gold.split("|")}))


def mixture_provenance(row, candidate):
    if row["query_mode"] != "COMPONENT_CAS_SET":
        return "SINGLE_CAS"
    if row["origin"] == "BASELINE_FROZEN":
        return "FROZEN_NAMED_MIXTURE"
    method = candidate.get("discovery_method", "")
    if method == "MIXTURE_SYNTHETIC_PAIR":
        return "SYNTHETIC_TWO_COMPONENT_CHALLENGE"
    if method == "MIXTURE_OFFICIAL_LIST":
        return "REPORTED_COMPONENT_MIXTURE"
    return "OTHER_COMPONENT_SET_REVIEW"


def analyze(gold_file, metadata_file, reviewed_file, catalog_file, out_dir):
    gold_rows = read_csv(gold_file)
    metadata_rows = read_csv(metadata_file)
    reviews = {r["case_id"]: r for r in read_csv(reviewed_file)}
    catalog = read_csv(catalog_file)
    cats = {r["target_id"]: r["target_type"] for r in catalog}
    meta = {r["query_id"]: r for r in metadata_rows}
    if len(meta) != len(metadata_rows) or len(meta) != len(gold_rows):
        raise ValueError("Every Gold row requires one unique metadata row")
    rows = []
    per_target = Counter()
    for gold in gold_rows:
        m = meta.get(gold["query_id"])
        if m is None:
            raise ValueError("Metadata missing query_id: " + gold["query_id"])
        cid = gold["source_case_ids"]
        rec = reviews.get(cid, {}) if gold["origin"] != "BASELINE_FROZEN" else {}
        if gold["origin"] != "BASELINE_FROZEN" and not rec:
            raise ValueError("Review sheet missing source_case_id: " + cid)
        if gold["gold_status"] == "FOUND":
            for tid in gold["gold_target_id"].split("|"):
                if tid not in cats:
                    raise ValueError("Gold target missing from catalog: " + tid)
                per_target[tid] += 1
        rows.append({
            "query_id": gold["query_id"],
            "origin": gold["origin"],
            "gold_status": gold["gold_status"],
            "n_gold_targets": gold["n_gold_targets"],
            "source_category": gold["source_categories"],
            "candidate_stratum": m.get("candidate_stratum", ""),
            "source_batch": m.get("source_batch", ""),
            "sampling_frame": (m.get("candidate_stratum", "") or
                               ("FROZEN_HISTORICAL" if gold["origin"] == "BASELINE_FROZEN" else "UNRECORDED")),
            "query_mode": gold["query_mode"],
            "mixture_provenance": mixture_provenance(gold, rec),
            "positive_target_families": target_families(gold["gold_target_id"]),
            "is_frozen_baseline": "YES" if gold["origin"] == "BASELINE_FROZEN" else "NO",
            "difficulty_tag": m.get("difficulty_tag", ""),
            "source_case_ids": cid,
        })
    counts = Counter(r["gold_status"] for r in rows)
    mix = Counter(r["mixture_provenance"] for r in rows if r["query_mode"] == "COMPONENT_CAS_SET")
    positive_coverage = [
        {"target_id": t["target_id"], "target_type": t["target_type"], "n_found_cases": per_target[t["target_id"]]}
        for t in catalog
    ]
    report = {
        "n_total": len(rows),
        "n_baseline": sum(x["origin"] == "BASELINE_FROZEN" for x in rows),
        "n_new": sum(x["origin"] != "BASELINE_FROZEN" for x in rows),
        "gold_counts": dict(counts),
        "not_found_only_guess_accuracy": ratio(counts["NOT_FOUND"], len(rows)),
        "by_source_category": cross_counts(rows, lambda x: x["source_category"]),
        "by_origin": cross_counts(rows, lambda x: x["origin"]),
        "by_sampling_frame": cross_counts(rows, lambda x: x["sampling_frame"]),
        "by_query_mode": cross_counts(rows, lambda x: x["query_mode"]),
        "by_positive_target_family": cross_counts(rows, lambda x: x["positive_target_families"] or "NOT_FOUND_NOT_APPLICABLE"),
        "mixture_query_provenance": dict(sorted(mix.items())),
        "positive_cases_per_target": positive_coverage,
        "n_targets_with_no_positive": sum(x["n_found_cases"] == 0 for x in positive_coverage),
        "target_ids_with_no_positive": [x["target_id"] for x in positive_coverage if x["n_found_cases"] == 0],
        "target_ids_with_only_one_positive": [x["target_id"] for x in positive_coverage if x["n_found_cases"] == 1],
        "sampling_design_warnings": [],
        "interpretation": {
            "source_category": "This is a mixed provenance/source label, NOT one coherent taxonomy of chemistry.",
            "positive_target_families": "Derived only from Gold FOUND target IDs; not a valid chemical-type classifier for NOT_FOUND.",
            "sampling_frame": "Recruitment strata, not a chemical population probability sample.",
            "not_found_only_guess_accuracy": "A majority-class reference, NOT a model measurement.",
            "mixture": "Synthetic two-component challenges are not observed commercial mixtures.",
            "baseline": "Historical 112-case benchmark previously used with Claude; report separately from new extension.",
        },
        "recommended_reporting": [
            "Report baseline (112) and fresh extension separately, then pooled results as secondary.",
            "Report FOUND sensitivity and NOT_FOUND specificity, balanced accuracy and exact target-set match.",
            "Report source-category, query mode, and sampling-frame strata; avoid conflating type with provenance.",
            "Report real/reported mixture queries separately from six synthetic two-component challenges.",
            "Do not generalize accuracy to all chemicals or to legal regimes outside the frozen 29-target catalog.",
            "For paired model comparisons, resample chemical cases, not repeated answers as independent observations.",
        ],
    }
    warning = report["sampling_design_warnings"]
    if counts["NOT_FOUND"] > counts["FOUND"]:
        warning.append("OVERALL_NEGATIVE_MAJORITY: NOT_FOUND exceeds FOUND; raw accuracy has a strong majority baseline")
    if any(x["n_found_cases"] == 0 for x in positive_coverage):
        warning.append("SIX_OR_MORE_UNTESTED_TARGETS: one or more of 29 targets has no positive evaluation case")
    if mix["SYNTHETIC_TWO_COMPONENT_CHALLENGE"]:
        warning.append("SYNTHETIC_MIXTURE_QUERIES: report synthetic two-component queries separately")
    for category in ("CHEMICAL_GROUP", "PARENT_SALT", "MIXTURE"):
        count = report["by_source_category"].get(category, {})
        if count and count["total"] < 30:
            warning.append("PLANNING_SMALL_STRATUM: " + category + " n=" + str(count["total"]))
    out = Path(out_dir)
    write_csv(out / "evaluation_strata.csv", rows, STRATA_COLUMNS)
    out.mkdir(parents=True, exist_ok=True)
    (out / "sampling_design_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--draft", type=Path, default=HERE / "validation_dataset/ci_readiness_draft")
    p.add_argument("--reviewed", type=Path, default=HERE / "candidates/review_sheet.csv")
    p.add_argument("--catalog", type=Path, default=ROOT / "data/regulatory_catalog.csv")
    p.add_argument("--out", type=Path, default=HERE / "candidates/review_audit_output")
    args = p.parse_args()
    report = analyze(args.draft / "validation_GOLD.csv", args.draft / "validation_METADATA.csv",
                     args.reviewed, args.catalog, args.out)
    print("Total:", report["n_total"], "Baseline:", report["n_baseline"], "New:", report["n_new"])
    print("Gold counts:", report["gold_counts"])
    print("Majority-class accuracy reference:", report["not_found_only_guess_accuracy"])
    print("Missing positive target IDs:", report["target_ids_with_no_positive"])
    print("Sampling design warnings:", report["sampling_design_warnings"])


if __name__ == "__main__":
    main()
