#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Assemble the validation dataset: frozen 112 baseline cases + human-adjudicated new cases.

Gate: a new row enters the dataset ONLY if the reviewer sheet says
    human_review_status == ADJUDICATED  and  human_gold_target_id is NOT_FOUND, one catalog target,
    or several catalog targets joined by "|" (overlap cases: the model must find ALL of them)
    and  human_legal_basis is filled.
Hard-to-adjudicate cases are simply left EXCLUDED / HOLD and never enter the dataset.
Everything else (PENDING / HOLD / EXCLUDED / unknown) is reported but never included.
The 112 baseline files in data/ are read-only; nothing here modifies them.

Model-visible file: validation_INPUT.csv (query_id, cas_inputs, smiles) -- no names, strata or labels.
Analysis files: validation_GOLD.csv, validation_METADATA.csv, composition_report.json.
--freeze writes VALIDATION_DATASET_FREEZE.json only if there are no errors
and each new included row has a documented, non-draft legal reference.
This syntactic evidence gate is NOT a substitute for independent legal review.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from collect_pubchem_candidates import cas_list, read_csv, valid_cas  # noqa: E402
import prereview_candidates as pre  # noqa: E402

INCLUDE = "ADJUDICATED"
EXCLUDE = "EXCLUDED"
INPUT_FIELDS = ["query_id", "cas_inputs", "smiles"]
GOLD_FIELDS = ["query_id", "gold_target_id", "gold_status", "n_gold_targets", "source_categories", "source_case_ids",
               "query_mode", "gold_derivation", "legal_basis", "origin"]
META_FIELDS = ["query_id", "origin", "source_batch", "source_category", "candidate_stratum",
               "difficulty_tag", "discovery_method", "pubchem_title_human_only"]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def load_baseline(input_path, gold_path, smiles_by_cas):
    gold = {g["query_id"]: g for g in read_csv(gold_path)}
    rows = []
    for r in read_csv(input_path):
        g = gold[r["query_id"]]
        cas = cas_list(r["cas_inputs"])
        rows.append({
            "query_id": r["query_id"], "cas_inputs": r["cas_inputs"],
            "smiles": smiles_by_cas.get(cas[0], "") if len(cas) == 1 else "",
            "gold_target_id": g["gold_target_id"], "gold_status": g["gold_status"],
            "n_gold_targets": 0 if g["gold_status"] == "NOT_FOUND" else len(g["gold_target_id"].split("|")),
            "source_categories": g["source_categories"], "source_case_ids": g["source_case_ids"],
            "query_mode": g["query_mode"], "gold_derivation": "FROZEN_BASELINE:" + g["gold_derivation"],
            "legal_basis": "", "origin": "BASELINE_FROZEN", "source_batch": "baseline",
            "candidate_stratum": "", "difficulty_tag": "", "discovery_method": "",
            "pubchem_title_human_only": "",
        })
    return rows


def gate_new_rows(sheet_paths, catalog_ids):
    """Split reviewer-sheet rows into included / excluded / held, with reasons."""
    included, excluded, held = [], [], []
    for path in sheet_paths:
        batch = Path(path).resolve().parent.name
        for r in read_csv(Path(path)):
            status = (r.get("human_review_status") or "").strip().upper()
            target = (r.get("human_gold_target_id") or "").strip()
            basis = (r.get("human_legal_basis") or "").strip()
            # Preserve the collection batch recorded for this case. The CSV lives
            # in candidates/, which is a folder name, not a meaningful source batch.
            rec = {**r, "source_batch": (r.get("source_batch") or "").strip() or batch}
            if status == EXCLUDE:
                excluded.append({**rec, "reason": "EXCLUDED_BY_REVIEWER"})
            elif status != INCLUDE:
                held.append({**rec, "reason": f"STATUS_{status or 'EMPTY'}"})
            elif not target or not basis:
                held.append({**rec, "reason": "ADJUDICATED_BUT_TARGET_OR_LEGAL_BASIS_EMPTY"})
            else:
                parts = sorted({t.strip() for t in target.split("|") if t.strip()})
                if "NOT_FOUND" in parts and len(parts) > 1:
                    held.append({**rec, "reason": "NOT_FOUND_MIXED_WITH_TARGETS"})
                elif any(t != "NOT_FOUND" and t not in catalog_ids for t in parts):
                    held.append({**rec, "reason": "UNKNOWN_TARGET_ID"})
                else:
                    rec["human_gold_target_id"] = "|".join(parts)
                    included.append(rec)
    return included, excluded, held


def legal_evidence_pending(basis):
    """Conservative freeze gate: a draft note is not legal source verification.

    This verifies documentation presence, NOT the substance of a legal claim.
    Source quality and target membership still require expert adjudication.
    """
    text = (basis or "").strip()
    if not text or any(term in text for term in (
        "고시 원문 대조 필요",
        "공식 고시 원문과 대조 필요",
        "29개 항목 범위 대조(초안)",
        "출처 확인(초안)",
    )):
        return True
    # A source name/version or an explicit URL is the minimum auditable trail.
    has_source = bool(re.search(r"https?://|고시\s*제\d{4}[-–]\d+호", text))
    return not has_source


def catalog_source_pending(registry_path, catalog_ids):
    """A separate, explicit provenance gate for all 29 frozen target definitions."""
    path = Path(registry_path)
    if not path.is_file():
        return sorted(catalog_ids)
    entries = {r["target_id"]: r for r in read_csv(path)}
    pending = []
    for target_id in sorted(catalog_ids):
        r = entries.get(target_id, {})
        verified = (r.get("verification_status") or "").strip().upper() == "VERIFIED"
        named_reviewer = bool((r.get("verified_by") or "").strip())
        dated = bool((r.get("verified_on") or "").strip())
        documented = bool((r.get("source_candidate_url") or "").strip()
                          or (r.get("verification_notes") or "").strip())
        if not (verified and named_reviewer and dated and documented):
            pending.append(target_id)
    return pending


def independent_review_issues(included, reviewer1, reviewer2):
    """Require two distinct, cited, concordant independent judgments before freeze.

    Blank/missing templates are not approval. Substantive source verification
    remains a reviewer responsibility and cannot be proven by these fields.
    """
    if not included:
        return []

    def load_review(path):
        path = Path(path)
        if not path.is_file():
            return {}, [f"MISSING_REVIEW_FILE {path}"]
        data = read_csv(path)
        records, issues = {}, []
        for r in data:
            case = (r.get("case_id") or "").strip()
            if not case:
                issues.append(f"REVIEW_WITHOUT_CASE_ID {path}")
            elif case in records:
                issues.append(f"DUPLICATE_REVIEW_CASE {path} {case}")
            else:
                records[case] = r
        return records, issues

    r1, issues = load_review(reviewer1)
    r2, more = load_review(reviewer2)
    issues.extend(more)
    for rec in included:
        case = rec["case_id"]
        a, b = r1.get(case), r2.get(case)
        if not a or not b:
            issues.append(f"MISSING_INDEPENDENT_REVIEW {case}")
            continue
        reviewers = []
        for index, item in enumerate((a, b), 1):
            reviewer_id = (item.get("reviewer_id") or "").strip()
            reviewers.append(reviewer_id)
            target = "|".join(sorted(set((item.get("reviewed_target_id") or "").strip().split("|"))))
            if (item.get("decision") or "").strip().upper() != "CONFIRMED":
                issues.append(f"UNCONFIRMED_REVIEW_{index} {case}")
            if not reviewer_id or not (item.get("reviewed_on") or "").strip():
                issues.append(f"REVIEWER_ID_OR_DATE_MISSING_{index} {case}")
            if not (item.get("official_legal_source") or "").strip():
                issues.append(f"REVIEWER_LEGAL_SOURCE_MISSING_{index} {case}")
            if not (item.get("chemical_identity_source") or "").strip():
                issues.append(f"REVIEWER_IDENTITY_SOURCE_MISSING_{index} {case}")
            if target != rec["human_gold_target_id"]:
                issues.append(f"REVIEW_TARGET_DISAGREEMENT_{index} {case}")
        if reviewers[0] and reviewers[0] == reviewers[1]:
            issues.append(f"REVIEWERS_NOT_INDEPENDENT {case}")
    return issues


def to_dataset_row(rec, query_id):
    target = rec["human_gold_target_id"].strip()
    cas = cas_list(rec["cas_inputs"])
    return {
        "query_id": query_id, "cas_inputs": rec["cas_inputs"],
        "smiles": rec.get("smiles", "") if len(cas) == 1 else "",
        "gold_target_id": target, "gold_status": "NOT_FOUND" if target == "NOT_FOUND" else "FOUND",
        "n_gold_targets": 0 if target == "NOT_FOUND" else len(target.split("|")),
        "source_categories": rec.get("source_category", ""), "source_case_ids": rec["case_id"],
        "query_mode": "SINGLE_CAS" if len(cas) == 1 else "COMPONENT_CAS_SET",
        "gold_derivation": "HUMAN_ADJUDICATED_LEGAL_REVIEW", "legal_basis": rec["human_legal_basis"].strip(),
        "origin": "NEW_ADJUDICATED", "source_batch": rec["source_batch"],
        "candidate_stratum": rec.get("candidate_stratum", ""), "difficulty_tag": rec.get("difficulty_tag", ""),
        "discovery_method": rec.get("discovery_method", ""),
        "pubchem_title_human_only": rec.get("pubchem_title_human_only", ""),
    }


def run_checks(rows, catalog, allow_structure_duplicates=False):
    errors, warnings = [], []
    seen_sig = {}
    structure_owner = {}
    for r in rows:
        sig = tuple(sorted(cas_list(r["cas_inputs"])))
        new = r["origin"] != "BASELINE_FROZEN"
        if sig in seen_sig:
            errors.append(f"DUPLICATE_CAS_SET {r['query_id']} == {seen_sig[sig]}")
        seen_sig[sig] = r["query_id"]
        for cas in sig:
            if not valid_cas(cas):
                errors.append(f"CAS_CHECKSUM_INVALID {r['query_id']} {cas}")
        if len(sig) == 1 and not r["smiles"]:
            warnings.append(f"SMILES_MISSING {r['query_id']} {sig[0]}")
        # contradiction with exact catalog CAS (single-CAS rows)
        if len(sig) == 1:
            exact = {tid for tid, sg in pre_signals(sig[0], catalog) if sg == "EXACT"}
            if exact and not exact.issubset(set(r["gold_target_id"].split("|"))):
                msg = f"GOLD_DIFFERS_FROM_EXACT_CATALOG_CAS {r['query_id']} {sig[0]} gold={r['gold_target_id']} exact={sorted(exact)}"
                (errors if new else warnings).append(msg)
        if len(sig) > 1:  # component-CAS set equal to a catalog mixture must carry that mixture as Gold
            same = {tid for tid, t in catalog.items() if t["type"] == "MIXTURE" and t["components"] == set(sig)}
            if same and not same.issubset(set(r["gold_target_id"].split("|"))):
                msg = f"GOLD_DIFFERS_FROM_CATALOG_MIXTURE_SET {r['query_id']} gold={r['gold_target_id']} set={sorted(same)}"
                (errors if new else warnings).append(msg)
        if pre.HAVE_RDKIT and len(sig) == 1 and r["smiles"]:
            mol = pre.parse(r["smiles"])
            if mol is not None:
                key = pre.structure_key(mol)
                if key in structure_owner:
                    other = structure_owner[key]
                    msg = f"DUPLICATE_STRUCTURE {r['query_id']} ~ {other['query_id']}"
                    is_err = (new or other["origin"] != "BASELINE_FROZEN") and not allow_structure_duplicates
                    (errors if is_err else warnings).append(msg)
                else:
                    structure_owner[key] = r
    return errors, warnings


def pre_signals(cas, catalog):
    return [(tid, sg) for tid, sg, _ in pre.exact_signals(cas, catalog)]


def composition(rows, catalog, target_min, target_max, min_per_category):
    by_origin = Counter(r["origin"] for r in rows)
    by_category = Counter(r["source_categories"] or "UNSPECIFIED" for r in rows)
    by_cat_status = Counter((r["source_categories"] or "UNSPECIFIED", r["gold_status"]) for r in rows)
    found_per_target = Counter(t for r in rows if r["gold_status"] == "FOUND" for t in r["gold_target_id"].split("|"))
    total = len(rows)
    short = {c: min_per_category - n for c, n in by_category.items() if n < min_per_category}
    return {
        "n_total": total, "target_range": [target_min, target_max],
        "shortfall_to_target_min": max(0, target_min - total),
        "within_target_range": target_min <= total <= target_max,
        "multi_target_cases": sum(1 for r in rows if int(r["n_gold_targets"]) > 1),
        "by_origin": dict(by_origin), "by_category": dict(by_category),
        "by_category_and_status": {f"{c}|{s}": n for (c, s), n in sorted(by_cat_status.items())},
        "found_share": round(sum(1 for r in rows if r["gold_status"] == "FOUND") / total, 3) if total else 0,
        "categories_below_planning_minimum": {c: {"count": by_category[c], "short_by": n}
                                              for c, n in short.items()},
        "planning_minimum_per_category": min_per_category,
        "targets_without_any_found_case": sorted(set(catalog) - set(found_per_target)),
        "found_cases_per_target": dict(sorted(found_per_target.items())),
        "note": "Category minimum is a planning heuristic set by --min-per-category, not a statistical power result.",
    }


def build(args):
    catalog = pre.load_catalog(Path(args.catalog))
    smiles_by_cas = {r["cas"]: r["smiles"] for r in read_csv(Path(args.smiles)) if r.get("smiles")}
    baseline = load_baseline(Path(args.baseline_input), Path(args.baseline_gold), smiles_by_cas)
    included, excluded, held = gate_new_rows(args.reviewed, set(catalog))
    source_pending = catalog_source_pending(args.catalog_source_registry, set(catalog))
    included.sort(key=lambda r: (r["source_batch"], r["case_id"]))
    independent_issues = independent_review_issues(included,
        getattr(args, "reviewer1", HERE / "candidates/reviewer_1_completed.csv"),
        getattr(args, "reviewer2", HERE / "candidates/reviewer_2_completed.csv"))
    legal_pending = [r for r in included if legal_evidence_pending(r["human_legal_basis"])]
    next_id = max(int(r["query_id"].split("-")[1]) for r in baseline) + 1
    new_rows = [to_dataset_row(r, f"RQ-{next_id + i:04d}") for i, r in enumerate(included)]
    rows = baseline + new_rows
    errors, warnings = run_checks(rows, catalog, args.allow_structure_duplicates)
    report = composition(rows, catalog, args.target_min, args.target_max, args.min_per_category)
    report.update({
        "version": args.version, "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "n_new_included": len(new_rows), "n_new_excluded_by_reviewer": len(excluded),
        "n_new_held": len(held), "held_by_reason": dict(Counter(h["reason"] for h in held)),
        "n_legal_basis_pending": len(legal_pending),
        "legal_basis_pending_case_ids": [r["case_id"] for r in legal_pending],
        "gold_ready_for_freeze": not bool(legal_pending or source_pending or independent_issues),
        "n_catalog_source_pending": len(source_pending),
        "n_independent_review_issues": len(independent_issues),
        "independent_review_issues": independent_issues,
        "catalog_source_pending_target_ids": source_pending,
        "excluded_cases": [{k: e.get(k, "") for k in ("case_id", "cas_inputs", "source_batch", "reason")}
                           for e in excluded],
        "held_cases": [{k: h.get(k, "") for k in ("case_id", "cas_inputs", "human_review_status",
                                                  "human_gold_target_id", "reason")} for h in held],
        "errors": errors, "warnings": warnings,
        "frozen": False,
    })
    out = Path(args.out) / args.version
    if args.freeze and (out / "VALIDATION_DATASET_FREEZE.json").exists():
        raise FileExistsError(f"Already frozen: {out}. Use a new --version; never overwrite a freeze.")
    write(out / "validation_INPUT.csv", rows, INPUT_FIELDS)
    write(out / "validation_GOLD.csv", rows, GOLD_FIELDS)
    write(out / "validation_METADATA.csv", rows, META_FIELDS)
    if args.freeze:
        if legal_pending:
            errors.extend(f"UNVERIFIED_LEGAL_BASIS {r['case_id']}" for r in legal_pending)
        if source_pending:
            errors.extend(f"UNVERIFIED_CATALOG_SOURCE {tid}" for tid in source_pending)
        errors.extend(independent_issues)
        report["errors"] = errors
        if errors:
            report["freeze_refused"] = "errors present; fix them before --freeze"
        else:
            manifest = {
                "version": args.version, "frozen_at_utc": report["created_at_utc"],
                "n_total": len(rows), "n_baseline": len(baseline), "n_new": len(new_rows),
                "file_sha256": {n: sha256(out / n) for n in
                                ("validation_INPUT.csv", "validation_GOLD.csv", "validation_METADATA.csv")},
                "baseline_sha256": {"retrieval_INPUT.csv": sha256(args.baseline_input),
                                    "retrieval_GOLD.csv": sha256(args.baseline_gold)},
                "reviewed_sheet_sha256": {str(p): sha256(p) for p in args.reviewed},
                "catalog_sha256": sha256(args.catalog),
                "catalog_source_registry_sha256": sha256(args.catalog_source_registry),
                "independent_review_sha256": {
                    "reviewer_1": sha256(args.reviewer1),
                    "reviewer_2": sha256(args.reviewer2),
                } if included else {},
                "rule": "Gold must be fixed before any model prediction is viewed; do not edit after freeze.",
            }
            (out / "VALIDATION_DATASET_FREEZE.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            report["frozen"] = True
    (out / "composition_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report, out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--reviewed", action="append", default=[],
                   help="reviewer sheet CSV with human_* columns filled; repeatable "
                        "(default: candidates/review_sheet.csv)")
    p.add_argument("--version", default="draft")
    p.add_argument("--out", default=str(HERE / "validation_dataset"))
    p.add_argument("--catalog", default=str(ROOT / "data/regulatory_catalog.csv"))
    p.add_argument("--baseline-input", default=str(ROOT / "data/retrieval_INPUT.csv"))
    p.add_argument("--baseline-gold", default=str(ROOT / "data/retrieval_GOLD.csv"))
    p.add_argument("--smiles", default=str(ROOT / "intermediate/shared_pubchem_smiles.csv"))
    p.add_argument("--catalog-source-registry",
                   default=str(HERE / "candidates/catalog_source_registry.csv"))
    p.add_argument("--reviewer1",
                   default=str(HERE / "candidates/reviewer_1_completed.csv"))
    p.add_argument("--reviewer2",
                   default=str(HERE / "candidates/reviewer_2_completed.csv"))
    p.add_argument("--target-min", type=int, default=300)
    p.add_argument("--target-max", type=int, default=400)
    p.add_argument("--min-per-category", type=int, default=30)
    p.add_argument("--allow-structure-duplicates", action="store_true")
    p.add_argument("--freeze", action="store_true")
    args = p.parse_args()
    if not args.reviewed:
        default_sheet = HERE / "candidates" / "review_sheet.csv"
        args.reviewed = [str(default_sheet)] if default_sheet.is_file() else []
    report, out = build(args)
    print(f"dataset={out}  total={report['n_total']}  new_included={report['n_new_included']}  "
          f"held={report['n_new_held']}  excluded={report['n_new_excluded_by_reviewer']}")
    print("by_category:", report["by_category"], " found_share:", report["found_share"])
    print(f"shortfall to {args.target_min}: {report['shortfall_to_target_min']}")
    if report["categories_below_planning_minimum"]:
        print("below planning minimum:", report["categories_below_planning_minimum"])
    for e in report["errors"][:15]:
        print("ERROR:", e)
    if len(report["errors"]) > 15:
        print(f"... {len(report['errors']) - 15} more errors in composition_report.json")
    print(f"warnings: {len(report['warnings'])}  frozen: {report['frozen']}")
    print(f"unverified legal bases: {report['n_legal_basis_pending']} / {report['n_new_included']} new rows")
    print(f"unverified catalog source definitions: {report['n_catalog_source_pending']} / {len(report['found_cases_per_target']) + len(report['targets_without_any_found_case'])} targets")
    print(f"independent reviewer signoff issues: {report['n_independent_review_issues']}")
    if report.get("freeze_refused"):
        print("FREEZE REFUSED:", report["freeze_refused"])
    sys.exit(1 if report["errors"] and args.freeze else 0)


if __name__ == "__main__":
    main()
