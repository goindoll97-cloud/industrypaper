#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gather MIXTURE validation candidates into the same review sheet (candidates/review_sheet.csv).

    python collect_mixtures.py --online                        # name -> CAS for the catalog mixtures without component CAS
    python collect_mixtures.py --input mixtures_input.csv      # real mixtures YOU found in an official source
    python collect_mixtures.py --online --input mixtures_input.csv

Two sources, no mixture is ever invented:
  1. Catalog mixtures that have no component CAS (6 of them): each component NAME is looked up in PubChem;
     a mixture row "CAS_A|CAS_B" is added only when every component resolves to exactly ONE CAS.
     Such rows are marked MIXTURE_NAME_RESOLVED_NEEDS_OFFICIAL_CAS: confirm the CAS in the official notice.
  2. --input CSV with columns  mixture_name, component_cas (CAS joined by "|"), source (URL or notice name).
     Use it for real mixtures from an official list, including ones NOT in the 29-target catalog (NOT_FOUND cases).

Rows are validated (CAS checksum, same component set as a baseline/pool mixture is dropped), appended to the
review sheet and pre-reviewed with the same rules as every other candidate. Gold is never assigned.
Not-resolved items and dropped rows are listed in candidates/summary.json (key "mixture_collection").
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import collect_candidates as cc  # noqa: E402
import collect_boundary_candidates as cbc  # noqa: E402
import prereview_candidates as pre  # noqa: E402
from collect_pubchem_candidates import PubChem, RequestBudget, cas_list, read_csv  # noqa: E402


def mixture_row(components, name, target, method, source):
    row = {k: "" for k in cc.POOL_FIELDS}
    row.update({
        "cas_inputs": "|".join(sorted(components)), "source_category": "MIXTURE",
        "candidate_stratum": "MIXTURE_COLLECTION", "discovery_method": method,
        "pubchem_title_human_only": f"{name} [source: {source}]" if source else name,
        "suggested_target_ids_human_only": target, "gold_status": "REVIEW_PENDING",
    })
    return row


def rows_from_input(path):
    rows, problems = [], []
    for i, r in enumerate(read_csv(Path(path)), 2):
        comps = cas_list(r.get("component_cas", ""))
        if len(comps) < 2:
            problems.append({"line": i, "name": r.get("mixture_name", ""), "reason": "NEEDS_AT_LEAST_TWO_COMPONENT_CAS"})
            continue
        rows.append(mixture_row(comps, r.get("mixture_name", ""), "", "MIXTURE_USER_INPUT", r.get("source", "")))
    return rows, problems


def rows_from_resolution(resolved):
    """One mixture row per catalog mixture whose every component has exactly one CID with exactly one CAS."""
    by_target = defaultdict(lambda: defaultdict(list))
    scope = {}
    for r in resolved:
        by_target[r["target_id"]][r["component_name"]].append(r)
        scope[r["target_id"]] = r["scope_text"]
    rows, unresolved = [], []
    for tid, comps in by_target.items():
        chosen, ok = [], True
        for name, items in comps.items():
            with_cas = [x for x in items if x["cas_candidates"]]
            cas_opts = {c for x in with_cas for c in x["cas_candidates"].split("|")}
            if len(with_cas) == 1 and len(cas_opts) == 1:
                chosen.append(next(iter(cas_opts)))
            else:
                ok = False
                unresolved.append({"target_id": tid, "component_name": name,
                                   "reason": f"{len(with_cas)}_CID_{len(cas_opts)}_CAS_CANDIDATES",
                                   "cas_candidates": sorted(cas_opts)})
        if ok and len(set(chosen)) == len(comps):
            rows.append(mixture_row(chosen, scope[tid], tid, "MIXTURE_NAME_RESOLUTION", "PubChem name lookup"))
    return rows, unresolved


def collect(args, online_resolved=None):
    """Append mixture rows to the review sheet and refresh the pre-review. Returns a report dict."""
    out = args.out
    sheet = out / "review_sheet.csv"
    if not sheet.is_file():
        raise SystemExit("review_sheet.csv가 없습니다. 먼저 python collect_candidates.py 를 실행하세요.")
    pool = read_csv(sheet)
    baseline_rows = read_csv(Path(args.baseline))
    smiles_by_cas = {r["cas"]: r["smiles"] for r in read_csv(Path(args.smiles)) if r.get("smiles")}
    dedup = cc.Dedup(baseline_rows, smiles_by_cas)
    for r in pool:
        dedup.keep(r)

    new_rows, problems, unresolved = [], [], []
    if args.input:
        rows, probs = rows_from_input(args.input)
        new_rows += rows
        problems += probs
    if online_resolved is not None:
        rows, unresolved = rows_from_resolution(online_resolved)
        new_rows += rows

    next_id = max([int(r["case_id"].split("-")[1]) for r in pool] + [0]) + 1
    dropped, added = [], []
    for raw in new_rows:
        row = cc.normalise(raw, "mixture")
        reason = dedup.check(row)
        if reason:
            dropped.append({"cas_inputs": row["cas_inputs"], "reason": reason})
            continue
        row["case_id"] = f"CAND-{next_id:04d}"
        next_id += 1
        dedup.keep(row)
        added.append(row)
    if added:
        cc.write_csv(sheet, pool + [{**a, "human_gold_target_id": "", "human_legal_basis": "",
                                     "human_review_status": "PENDING"} for a in added], cc.SHEET_FIELDS)
        cc.run(SimpleNamespace(online=False, target_total=args.target_total, overshoot=args.overshoot,
                               max_passes=1, out=out, stages=args.stages, sources=args.sources,
                               catalog=args.catalog, baseline=args.baseline, smiles=args.smiles))
    report = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "rows_added": len(added),
              "added_cas_sets": [a["cas_inputs"] for a in added], "dropped": dropped,
              "input_problems": problems, "unresolved_catalog_components": unresolved}
    summary_path = out / "summary.json"
    if summary_path.is_file():
        data = json.loads(summary_path.read_text(encoding="utf-8"))
        data["mixture_collection"] = report
        summary_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--online", action="store_true", help="resolve catalog mixture component names in PubChem")
    p.add_argument("--input", default="", help="CSV: mixture_name, component_cas (A|B), source")
    p.add_argument("--max-requests", type=int, default=300)
    p.add_argument("--target-total", type=int, default=300)
    p.add_argument("--overshoot", type=float, default=1.2)
    p.add_argument("--out", default=str(cc.DEFAULT_OUT))
    p.add_argument("--stages", default=str(cc.DEFAULT_STAGES))
    p.add_argument("--sources", default=str(cc.DEFAULT_OUT / "_sources"))
    p.add_argument("--catalog", default=str(ROOT / "data/regulatory_catalog.csv"))
    p.add_argument("--baseline", default=str(ROOT / "data/retrieval_INPUT.csv"))
    p.add_argument("--smiles", default=str(ROOT / "intermediate/shared_pubchem_smiles.csv"))
    args = p.parse_args()
    args.out, args.stages, args.sources = Path(args.out), Path(args.stages), Path(args.sources)
    if not args.online and not args.input:
        p.error("--online 또는 --input 중 하나는 필요합니다.")

    resolved = None
    if args.online:
        queue = cbc.research_queue(read_csv(Path(args.catalog)))
        cache = args.stages / "M"
        cache.mkdir(parents=True, exist_ok=True)
        client = PubChem(SimpleNamespace(max_requests=args.max_requests, rate_per_sec=2.0, timeout=45,
                                         threshold=90, max_records=30), cache)
        try:
            resolved = cbc.resolve_mixture_names(client, queue)
        except RequestBudget as exc:
            print("요청 한도 도달:", exc)
            resolved = []
    report = collect(args, resolved)
    print(f"추가된 혼합물 행: {report['rows_added']}건 {report['added_cas_sets']}")
    for d in report["dropped"]:
        print("제외:", d)
    for d in report["input_problems"]:
        print("입력 문제:", d)
    for d in report["unresolved_catalog_components"]:
        print("이름→CAS 미확정(공식 자료로 직접 확인 필요):", d)
    print(f"검토표: {args.out / 'review_sheet.csv'}  (요약: summary.json 의 mixture_collection)")


if __name__ == "__main__":
    main()
