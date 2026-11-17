#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Create a deterministic, human-readable legal Gold verification queue.

This tool never changes Gold labels or human review statuses. It separates
explicit catalog CAS matches from decisions requiring substantive legal scope
review. Output is audit material, NOT model input.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CAS_RE = re.compile(r"^\d{2,7}-\d{2}-\d$")

FIELDS = [
    "priority", "review_class", "case_id", "cas_inputs",
    "pubchem_title_human_only", "human_gold_target_id",
    "direct_catalog_target_ids", "human_review_status", "source_batch",
    "candidate_stratum", "discovery_method", "auto_flags",
    "human_legal_basis", "required_action",
]


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, records, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)


def cas_valid(cas):
    if not CAS_RE.fullmatch(cas):
        return False
    digits, check = cas.replace("-", "")[:-1], int(cas[-1])
    return sum(int(digit) * i for i, digit in enumerate(reversed(digits), 1)) % 10 == check


def split_cas(text):
    return [value.strip() for value in (text or "").split("|") if value.strip()]


def catalog_index(catalog):
    """Only direct identity CAS. A mixture component alone is not that mixture."""
    index = {}
    for item in catalog:
        tid = item["target_id"]
        for field in ("reference_cas_set", "official_member_cas_set", "official_mixture_cas"):
            for cas in split_cas(item.get(field, "")):
                index.setdefault(cas, set()).add(tid)
    return index


def classify(record, direct):
    gold = record["human_gold_target_id"]
    components = split_cas(record["cas_inputs"])
    explicit = set().union(*(direct.get(c, set()) for c in components))
    hits = "|".join(sorted(explicit))
    if gold == "NOT_FOUND":
        risky = (record.get("candidate_stratum") in ("NEAR_CATALOG", "BOUNDARY_PROBE", "MIXTURE_COLLECTION")
                 or record.get("review_priority") == "HIGH"
                 or "NEAR_NEIGHBOR" in record.get("auto_flags", ""))
        if explicit:
            return 0, "DIRECT_CAS_CONTRADICTION", hits, "Investigate catalog identity and Gold immediately"
        if risky:
            return 2, "NEGATIVE_SCOPE_NEAR_MISS", hits, "Verify all 29 scopes, related salts/groups, and identity; document negative evidence"
        return 3, "NEGATIVE_SCOPE_GENERAL", hits, "Verify out-of-scope identity and record source/version"
    targets = set(split_cas(gold))
    if explicit and not explicit.issubset(targets):
        return 0, "MULTI_TARGET_OMISSION", hits, "An explicitly matched target ID is missing from Gold"
    if targets and targets.issubset(explicit):
        return 4, "EXACT_CAS_POSITIVE", hits, "Verify official list revision and record exact CAS, section and date"
    return 1, "SCOPE_POSITIVE", hits, "Verify salt, group, oxidation state and applicable exact wording in original notice"


def run(sheet_path, catalog_path, output_dir):
    sheet = read_csv(sheet_path)
    catalog = read_csv(catalog_path)
    direct = catalog_index(catalog)
    records = []
    missing = []
    for r in sheet:
        if r.get("human_review_status") != "ADJUDICATED":
            continue
        basis = r.get("human_legal_basis", "")
        if "고시 원문 대조 필요" not in basis and "원문과 대조 필요" not in basis:
            continue
        priority, review_class, direct_ids, action = classify(r, direct)
        records.append({
            "priority": priority, "review_class": review_class,
            "case_id": r["case_id"], "cas_inputs": r["cas_inputs"],
            "pubchem_title_human_only": r["pubchem_title_human_only"],
            "human_gold_target_id": r["human_gold_target_id"],
            "direct_catalog_target_ids": direct_ids,
            "human_review_status": r["human_review_status"],
            "source_batch": r.get("source_batch", ""),
            "candidate_stratum": r.get("candidate_stratum", ""),
            "discovery_method": r.get("discovery_method", ""),
            "auto_flags": r.get("auto_flags", ""),
            "human_legal_basis": basis,
            "required_action": action,
        })
        for cas in split_cas(r["cas_inputs"]):
            if not cas_valid(cas):
                missing.append({"case_id": r["case_id"], "cas": cas})
    records.sort(key=lambda x: (x["priority"], x["case_id"]))
    output_dir = Path(output_dir)
    write_csv(output_dir / "legal_review_queue.csv", records, FIELDS)

    scope_invalid = []
    for item in catalog:
        for match in re.findall(r"\b\d{2,7}-\d{2}-\d\b", item["regulatory_scope_text"]):
            if not cas_valid(match):
                scope_invalid.append({"target_id": item["target_id"], "cas": match})
    out = {
        "candidate_rows": len(sheet),
        "adjudicated": sum(r["human_review_status"] == "ADJUDICATED" for r in sheet),
        "excluded": sum(r["human_review_status"] == "EXCLUDED" for r in sheet),
        "source_pending_total": len(records),
        "queue_by_class": dict(Counter(x["review_class"] for x in records)),
        "candidate_cas_invalid": missing,
        "catalog_scope_cas_checksum_invalid": scope_invalid,
        "note": "Queue is for source adjudication. No Gold status or label was automatically changed.",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "legal_review_summary.json").open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sheet", type=Path, default=HERE / "candidates/review_sheet.csv")
    ap.add_argument("--catalog", type=Path, default=ROOT / "data/regulatory_catalog.csv")
    ap.add_argument("--out", type=Path, default=HERE / "candidates/review_audit_output")
    args = ap.parse_args()
    result = run(args.sheet, args.catalog, args.out)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("Review queue:", args.out / "legal_review_queue.csv")


if __name__ == "__main__":
    main()
