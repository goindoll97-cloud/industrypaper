#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Audit existing 112-case gold benchmark without altering frozen inputs.

Uses only Python standard library. No API, RDKit, Ollama or Anthropic required.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
FILES = {
    "inputs": ROOT / "data/retrieval_INPUT.csv",
    "gold": ROOT / "data/retrieval_GOLD.csv",
    "catalog": ROOT / "data/regulatory_catalog.csv",
    "smiles": ROOT / "intermediate/shared_pubchem_smiles.csv",
    "manual_review": ROOT / "review/retrieval_gold_manual_review.csv",
}


def load(path: Path) -> list[dict]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def export(path: Path, data: list[dict]) -> None:
    if not data:
        raise ValueError(f"Empty export: {path}")
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(data[0]))
        w.writeheader()
        w.writerows(data)


def canonical_cas(text: str) -> tuple[str, ...]:
    return tuple(sorted(set(p.strip() for p in text.split("|") if p.strip())))


def main() -> None:
    data = {k: load(v) for k, v in FILES.items()}
    query = data["inputs"]
    gold = {r["query_id"]: r for r in data["gold"]}
    catalog = {r["target_id"]: r for r in data["catalog"]}
    review = {r["query_id"]: r for r in data["manual_review"]}
    smiles = {r["cas"]: r for r in data["smiles"]}

    qids = [r["query_id"] for r in query]
    if len(query) != 112 or len(set(qids)) != 112:
        raise ValueError("Original benchmark must contain exactly 112 distinct query IDs.")
    if len(data["gold"]) != 112 or len(gold) != 112 or set(gold) != set(qids):
        raise ValueError("Gold rows must match query IDs one-to-one.")
    if len(catalog) != 29 or len(data["catalog"]) != 29:
        raise ValueError("Expected the original frozen 29-target catalog.")
    if set(review) != set(qids):
        raise ValueError("Manual review records do not cover all queries.")
    signatures = [canonical_cas(r["cas_inputs"]) for r in query]
    if len(set(signatures)) != 112 or any(not sig for sig in signatures):
        raise ValueError("Duplicate or empty candidate CAS signature.")

    result = []
    for q in query:
        qid = q["query_id"]
        goldrow = gold[qid]
        rv = review[qid]
        status, target = goldrow["gold_status"], goldrow["gold_target_id"]
        if status == "FOUND" and target not in catalog:
            raise ValueError(f"Unknown gold target for {qid}: {target}")
        if status == "NOT_FOUND" and target != "NOT_FOUND":
            raise ValueError(f"Invalid NOT_FOUND target for {qid}: {target}")
        if status not in {"FOUND", "NOT_FOUND"}:
            raise ValueError(f"Unresolved frozen gold label at {qid}: {status}")
        if rv["derived_gold_target_id"] != target:
            raise ValueError(f"Review/gold label mismatch at {qid}")
        if goldrow["retrieval_scope_review_required"] == "YES" and rv["researcher_status"] != "APPROVED":
            raise ValueError(f"Missing researcher approval at {qid}")
        source = goldrow["source_categories"]
        if source not in {"PARENT_SALT", "CHEMICAL_GROUP", "MIXTURE"}:
            raise ValueError(f"Unrecognized source category at {qid}: {source}")
        ids = canonical_cas(q["cas_inputs"])
        missing = [x for x in ids if not smiles.get(x, {}).get("smiles", "").strip()]
        result.append({
            "query_id": qid,
            "cas_inputs": q["cas_inputs"],
            "source_category": source,
            "query_mode": goldrow["query_mode"],
            "gold_status": status,
            "gold_target_id": target,
            "gold_source": goldrow["gold_derivation"],
            "not_found_scope": "ONLY_29_FROZEN_TARGETS",
            "review_required": goldrow["retrieval_scope_review_required"],
            "manual_review_status": rv["researcher_status"],
            "cas_count": len(ids),
            "missing_smiles_cas_count": len(missing),
            "missing_smiles_cas": "|".join(missing),
        })
    count_status = Counter(r["gold_status"] for r in result)
    count_type = Counter(r["source_category"] for r in result)
    joint = {
        typ: {
            s: sum(r["source_category"] == typ and r["gold_status"] == s for r in result)
            for s in ("FOUND", "NOT_FOUND")
        }
        for typ in ("PARENT_SALT", "CHEMICAL_GROUP", "MIXTURE")
    }
    report = {
        "audit_time_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "retrieval among original 29 regulatory targets, not all current chemical law",
        "benchmark_n": len(result),
        "catalog_target_n": len(catalog),
        "status_counts": dict(count_status),
        "source_type_counts": dict(count_type),
        "source_type_by_gold_status": joint,
        "queries_with_missing_smiles": sum(r["missing_smiles_cas_count"] > 0 for r in result),
        "review_required_and_approved": sum(r["review_required"] == "YES"
                                             and r["manual_review_status"] == "APPROVED"
                                             for r in result),
        "input_sha256": {
            k: hashlib.sha256(p.read_bytes()).hexdigest() for k, p in FILES.items()
        },
    }
    OUT.mkdir(exist_ok=True)
    export(OUT / "baseline_inventory.csv", result)
    (OUT / "baseline_summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("Audit complete. New-candidate expansion does NOT start until labelling rules are approved.")


if __name__ == "__main__":
    main()
