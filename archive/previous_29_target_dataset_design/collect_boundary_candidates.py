#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Supplementary candidate collection: structure-similar non-listed (boundary) chemicals
and a research queue for catalog mixtures that have no component CAS.

Never assigns Gold. Every candidate is REVIEW_PENDING. Mixtures are NOT invented:
the mixture stage only resolves the component NAMES printed in the frozen catalog to
PubChem CAS candidates; the official CAS must still be confirmed in the regulatory source.

Offline (no network): writes probe_plan.csv and mixture_name_research_queue.csv.
Online (--online):    also queries PubChem PUG REST (rate limited, cached, budgeted).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from boundary_probes import BOUNDARY_PROBES, probe_plan  # noqa: E402
from collect_pubchem_candidates import (  # noqa: E402
    EXTRA, TEMPLATE, PubChem, RequestBudget, cas_list, from_synonyms, read_csv, sha, valid_cas,
    write_csv,
)
import prereview_candidates as pre  # noqa: E402

STRATUM = "BOUNDARY_PROBE"
FRAME = "CURATED_BOUNDARY_PROBE_LIST"
METHOD = "PUBCHEM_BOUNDARY_NAME"


def mixture_component_names(scope_text):
    """Component names from 'Mixture of A, B and C' (CAS in parentheses removed)."""
    text = re.sub(r"^\s*Mixture of\s+", "", scope_text, flags=re.I)
    text = re.sub(r"\((?:\d{2,7}-\d{2}-\d)\)", "", text)
    parts = re.split(r",\s+|\s+and\s+", text)
    return [p.strip() for p in parts if p.strip()]


def research_queue(catalog_rows):
    """Catalog mixtures that cannot be queried by CAS yet (no component CAS, no official CAS)."""
    queue = []
    for r in catalog_rows:
        if r["target_type"] != "MIXTURE":
            continue
        if cas_list(r["mixture_component_cas_set"]) or cas_list(r["official_mixture_cas"]):
            continue
        for name in mixture_component_names(r["regulatory_scope_text"]):
            queue.append({"target_id": r["target_id"], "component_name": name,
                          "scope_text": r["regulatory_scope_text"],
                          "status": "NAME_ONLY_NEEDS_OFFICIAL_CAS"})
    return queue


def known_sets(catalog_rows, baseline_rows, exclude_files):
    """CAS signatures that must not reappear, and structure keys of everything already used."""
    cas_seen, catalog_cas = set(), set()
    for r in catalog_rows:
        for col in ("reference_cas_set", "official_member_cas_set", "official_mixture_cas",
                    "mixture_component_cas_set"):
            catalog_cas.update(cas_list(r[col]))
    for r in baseline_rows:
        cas_seen.update(cas_list(r["cas_inputs"]))
    smiles_by_cas = {}
    shared = ROOT / "intermediate/shared_pubchem_smiles.csv"
    if shared.is_file():
        smiles_by_cas = {r["cas"]: r["smiles"] for r in read_csv(shared) if r.get("smiles")}
    structures = set()
    for cas in cas_seen | catalog_cas:
        mol = pre.parse(smiles_by_cas.get(cas, ""))
        if mol is not None:
            structures.add(pre.structure_key(mol))
    for f in exclude_files:
        for r in read_csv(Path(f)):
            cas_seen.update(cas_list(r.get("cas_inputs", "")))
            mol = pre.parse(r.get("smiles", ""))
            if mol is not None:
                structures.add(pre.structure_key(mol))
    return cas_seen, catalog_cas, structures


def make_row(cas, target, kind, name, cid, title, smiles):
    row = {k: "" for k in TEMPLATE + EXTRA}
    row.update({
        "cas_inputs": cas, "source_category": "BOUNDARY_CANDIDATE", "difficulty_tag": f"BOUNDARY_{kind}",
        "gold_status": "REVIEW_PENDING",
        "identity_evidence_url": f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}",
        "smiles": smiles, "smiles_qc_status": "PUBCHEM_RECORDED_NEEDS_REVIEW",
        "reviewer1_status": "PENDING", "reviewer2_status": "PENDING", "adjudication_status": "PENDING",
        "notes_human_only": "Boundary probe: structurally near a listed target, legal membership UNKNOWN. "
                            "PubChem does NOT establish regulatory status. Compare against ALL 29 targets.",
        "discovery_method": METHOD, "suggested_target_ids_human_only": target,
        "seed_cas": name, "pubchem_cid": str(cid), "pubchem_title_human_only": title,
        "pubchem_identity_check": "CAS_CID_RECIPROCAL_PUG_REST",
        "pubchem_record_url": f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "candidate_stratum": STRATUM, "sampling_frame": FRAME,
    })
    return row


def collect_boundary(client, cas_seen, catalog_cas, structures, max_candidates, per_target_cap):
    rows, skipped, per_target = [], [], Counter()
    taken_cas, taken_cid = set(), set()
    for target, name, kind in probe_plan():
        if len(rows) >= max_candidates:
            break
        if per_target[target] >= per_target_cap:
            continue
        accepted = False
        for cid in client.cids_for_name(name)[:2]:
            if cid in taken_cid:
                continue
            props = client.properties(cid)
            if not props.get("smiles"):
                skipped.append({"probe": name, "cid": cid, "cas": "", "reason": "NO_SMILES"})
                continue
            for cas in from_synonyms(client.synonyms(cid))[:3]:
                if cid not in client.cids_for_name(cas):
                    continue  # CAS/CID must be reciprocal
                reason = ""
                if cas in cas_seen or cas in taken_cas:
                    reason = "ALREADY_USED_CAS"
                elif cas in catalog_cas:
                    reason = "CATALOG_LISTED_CAS"  # covered by the CATALOG_LISTED stratum
                else:
                    mol = pre.parse(props["smiles"])
                    if mol is not None and pre.structure_key(mol) in structures:
                        reason = "DUPLICATE_STRUCTURE_OF_USED_OR_CATALOG"
                if reason:
                    skipped.append({"probe": name, "cid": cid, "cas": cas, "reason": reason})
                    continue
                rows.append(make_row(cas, target, kind, name, cid, props["title"], props["smiles"]))
                taken_cas.add(cas)
                taken_cid.add(cid)
                mol = pre.parse(props["smiles"])
                if mol is not None:
                    structures.add(pre.structure_key(mol))
                per_target[target] += 1
                accepted = True
                break
            if accepted:
                break
        if not accepted:
            skipped.append({"probe": name, "cid": "", "cas": "", "reason": "NO_USABLE_RECORD"})
    return rows, skipped


def resolve_mixture_names(client, queue):
    out = []
    for item in queue:
        found = False
        for cid in client.cids_for_name(item["component_name"])[:3]:
            props = client.properties(cid)
            cas = [c for c in from_synonyms(client.synonyms(cid)) if cid in client.cids_for_name(c)]
            out.append({**item, "pubchem_cid": cid, "pubchem_title": props["title"],
                        "pubchem_smiles": props["smiles"], "cas_candidates": "|".join(cas[:3]),
                        "status": "RESOLVED_NEEDS_OFFICIAL_CAS_CHECK" if cas else "NO_RECIPROCAL_CAS"})
            found = True
        if not found:
            out.append({**item, "pubchem_cid": "", "pubchem_title": "", "pubchem_smiles": "",
                        "cas_candidates": "", "status": "NOT_RESOLVED_BY_NAME"})
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--online", action="store_true", help="Actually call PubChem PUG REST.")
    p.add_argument("--out", default=str(HERE / "collection_output"))
    p.add_argument("--run-id", default="boundary_v1")
    p.add_argument("--max-candidates", type=int, default=100)
    p.add_argument("--per-target-cap", type=int, default=8)
    p.add_argument("--max-requests", type=int, default=600)
    p.add_argument("--rate-per-sec", type=float, default=2.0)
    p.add_argument("--timeout", type=int, default=45)
    p.add_argument("--exclude-file", action="append", default=[],
                   help="earlier candidates_for_review.csv to exclude (repeatable)")
    p.add_argument("--catalog", default=str(ROOT / "data/regulatory_catalog.csv"))
    p.add_argument("--baseline", default=str(ROOT / "data/retrieval_INPUT.csv"))
    args = p.parse_args()

    out = Path(args.out) / args.run_id
    out.mkdir(parents=True, exist_ok=True)
    catalog = read_csv(Path(args.catalog))
    baseline = read_csv(Path(args.baseline))
    plan = [{"target_id": t, "probe_name": n, "kind": k} for t, n, k in probe_plan()]
    queue = research_queue(catalog)
    write_csv(out / "probe_plan.csv", plan, ["target_id", "probe_name", "kind"])
    write_csv(out / "mixture_name_research_queue.csv", queue,
              ["target_id", "component_name", "scope_text", "status"])

    summary = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "run_id": args.run_id,
               "mode": "ONLINE_PUBCHEM_PUG_REST" if args.online else "OFFLINE_PLAN_ONLY",
               "n_probes_planned": len(plan), "n_mixture_names_queued": len(queue),
               "rdkit_available": pre.HAVE_RDKIT, "exclusion_files": args.exclude_file,
               "all_new_labels": "REVIEW_PENDING", "candidate_gold_labels_assigned": 0,
               "source_sha256": {"catalog": sha(Path(args.catalog)), "baseline": sha(Path(args.baseline))},
               "errors": []}
    if args.online:
        client_args = SimpleNamespace(max_requests=args.max_requests, rate_per_sec=args.rate_per_sec,
                                      timeout=args.timeout, threshold=90, max_records=30)
        client = PubChem(client_args, out)
        cas_seen, catalog_cas, structures = known_sets(catalog, baseline, args.exclude_file)
        try:
            client.phase_max_requests = int(args.max_requests * 0.8)  # keep budget for mixture names
            rows, skipped = collect_boundary(client, cas_seen, catalog_cas, structures,
                                             args.max_candidates, args.per_target_cap)
        except RequestBudget as exc:
            summary["errors"].append(str(exc))
            rows, skipped = [], []
        for i, row in enumerate(rows, 1):
            row["case_id"] = f"BND-{i:04d}"
        write_csv(out / "candidates_for_review.csv", rows, TEMPLATE + EXTRA)
        write_csv(out / "skipped_probes.csv", skipped, ["probe", "cid", "cas", "reason"])
        try:
            client.phase_max_requests = None
            resolved = resolve_mixture_names(client, queue)
        except RequestBudget as exc:
            summary["errors"].append(str(exc))
            resolved = []
        write_csv(out / "mixture_name_resolution.csv", resolved,
                  ["target_id", "component_name", "pubchem_cid", "pubchem_title", "pubchem_smiles",
                   "cas_candidates", "status", "scope_text"])
        summary.update({"new_candidate_count": len(rows),
                        "candidates_by_target_hint": dict(Counter(r["suggested_target_ids_human_only"] for r in rows)),
                        "candidates_by_kind": dict(Counter(r["difficulty_tag"] for r in rows)),
                        "skipped_by_reason": dict(Counter(s["reason"] for s in skipped)),
                        "new_network_requests": client.requests, "cached_network_requests": client.cached})
        summary["errors"].extend(client.failures)
    (out / "collection_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                                 encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "source_sha256"}, ensure_ascii=False, indent=2))
    print("wrote:", out)


if __name__ == "__main__":
    main()
