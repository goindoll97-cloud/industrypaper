#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ONE entry point for building the validation-candidate pool.

    python collect_candidates.py --online --target-total 300

What it does, in one run and in ONE folder (candidates/):
  1. imports earlier batches (candidates/_sources/*.csv) the first time, then keeps accumulating;
  2. collects new candidates from PubChem until the pool can reach --target-total
     (target counts the frozen baseline cases; --overshoot adds a safety margin for rows
     the reviewer will exclude), using the existing stages: balanced collector
     (catalog-listed / near-catalog / independent general) and boundary probes;
  3. drops candidates that duplicate a BASELINE structure or CAS (logged, never silent);
  4. runs the automatic pre-review and writes ONE review sheet (review_sheet.csv).
Re-running tops up the same folder. Reviewer columns (human_*) you already filled are preserved.
No Gold label is ever assigned; every row stays REVIEW_PENDING.

Without --online it only (re)imports, de-duplicates and re-runs the pre-review (no network).
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import prereview_candidates as pre  # noqa: E402
from collect_pubchem_candidates import EXTRA, TEMPLATE, cas_list, read_csv, valid_cas  # noqa: E402

POOL_FIELDS = TEMPLATE + EXTRA + ["legacy_case_id", "source_batch"]
SHEET_FIELDS = pre.OUT_FIELDS + ["legacy_case_id", "source_batch", "pubchem_cid"]
HUMAN_COLS = ["human_gold_target_id", "human_legal_basis", "human_review_status"]
SEED_ORDER = ["balanced_v2_candidates_for_review.csv", "boundary_v1_candidates_from_prereview.csv"]
DEFAULT_OUT = HERE / "candidates"
DEFAULT_STAGES = HERE / "collection_output" / "_work"


# ------------------------------------------------------------------ pure helpers
def target_new_count(target_total, n_baseline, overshoot):
    """Candidate rows to keep so that target_total is reachable after reviewer exclusions."""
    return max(0, math.ceil((target_total - n_baseline) * overshoot))


def normalise(row, source_batch, legacy_id=""):
    out = {k: (row.get(k) or "") for k in POOL_FIELDS}
    out["gold_status"] = "REVIEW_PENDING"
    out["gold_target_id"] = ""
    for col in ("reviewer1_status", "reviewer2_status", "adjudication_status"):
        out[col] = out[col] or "PENDING"
    out["source_batch"] = source_batch
    out["legacy_case_id"] = legacy_id or row.get("legacy_case_id", "")
    return out


def carry_over_human(sheet_rows, previous_rows):
    """Keep reviewer input already typed into an earlier review_sheet.csv (matched by case_id)."""
    prev = {r["case_id"]: r for r in previous_rows}
    for r in sheet_rows:
        old = prev.get(r["case_id"])
        if old:
            for col in HUMAN_COLS:
                if (old.get(col) or "").strip():
                    r[col] = old[col]
    return sheet_rows


def reviewer_touched(row):
    """True once the reviewer typed a target/basis or moved the status off PENDING."""
    return bool((row.get("human_gold_target_id") or "").strip()
                or (row.get("human_legal_basis") or "").strip()
                or (row.get("human_review_status") or "PENDING").strip().upper() != "PENDING")


class Dedup:
    """CAS and structure filter against the frozen baseline and rows already kept."""

    def __init__(self, baseline_rows, smiles_by_cas, catalog_cas=frozenset()):
        self.baseline_cas = {c for r in baseline_rows for c in cas_list(r["cas_inputs"])}
        self.catalog_cas = set(catalog_cas)  # CAS printed in the frozen catalog are never dropped by structure
        self.baseline_struct = {}
        self.kept_cas = set()
        self.baseline_sets = {tuple(sorted(cas_list(r["cas_inputs"]))) for r in baseline_rows
                              if len(cas_list(r["cas_inputs"])) > 1}
        self.kept_sets = set()
        if pre.HAVE_RDKIT:
            for c in self.baseline_cas:
                mol = pre.parse(smiles_by_cas.get(c, ""))
                if mol is not None:
                    self.baseline_struct.setdefault(pre.structure_key(mol), c)

    def check(self, row):
        """Return a drop reason or ''. Duplicates among candidates are kept (flagged later)."""
        cas = row["cas_inputs"].strip()
        parts = cas_list(cas)
        if len(parts) > 1:  # mixture query: component-CAS set
            if not all(valid_cas(c) for c in parts):
                return "CAS_CHECKSUM_INVALID"
            sig = tuple(sorted(parts))
            if sig in self.baseline_sets:
                return "MIXTURE_IN_BASELINE"
            if sig in self.kept_sets:
                return "MIXTURE_ALREADY_IN_POOL"
            return ""
        if not valid_cas(cas):
            return "CAS_CHECKSUM_INVALID"
        if cas in self.baseline_cas:
            return "CAS_IN_BASELINE"
        if cas in self.kept_cas:
            return "CAS_ALREADY_IN_POOL"
        if pre.HAVE_RDKIT and row.get("smiles") and cas not in self.catalog_cas:
            mol = pre.parse(row["smiles"])
            if mol is not None:
                key = pre.structure_key(mol)
                if key in self.baseline_struct:
                    return f"SAME_STRUCTURE_AS_BASELINE:{self.baseline_struct[key]}"
        return ""

    def keep(self, row):
        parts = cas_list(row["cas_inputs"])
        if len(parts) > 1:
            self.kept_sets.add(tuple(sorted(parts)))
        else:
            self.kept_cas.add(row["cas_inputs"].strip())


def add_rows(pool, dropped, dedup, new_rows, batch, start_id):
    next_id = start_id
    for raw in new_rows:
        row = normalise(raw, batch, raw.get("case_id", ""))
        reason = dedup.check(row)
        if reason:
            dropped.append({"case_id": raw.get("case_id", ""), "cas_inputs": row["cas_inputs"],
                            "source_batch": batch, "reason": reason,
                            "pubchem_title_human_only": row.get("pubchem_title_human_only", "")})
            continue
        row["case_id"] = f"CAND-{next_id:04d}"
        next_id += 1
        dedup.keep(row)
        pool.append(row)
    return next_id


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


# ------------------------------------------------------------------ PubChem stages (subprocess)
def import_legacy_cache(stages, collection_root):
    """Re-use PubChem responses saved by earlier per-batch runs (saves requests)."""
    sources = [(collection_root / legacy / "pubchem_http_cache", stage)
               for legacy, stage in (("balanced_v2", "A"), ("boundary_v1", "B"))]
    sources += [(collection_root / "_stages" / stage / "pubchem_http_cache", stage) for stage in ("A", "B")]
    for src, stage in sources:
        dst = stages / stage / "pubchem_http_cache"
        if src.is_dir():
            dst.mkdir(parents=True, exist_ok=True)
            for f in src.glob("*.json"):
                if not (dst / f.name).exists():
                    shutil.copy2(f, dst / f.name)


def run_stage(cmd):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"stage failed: {' '.join(cmd[:3])}\n{proc.stderr[-800:]}")
    return proc.stdout


def stage_a(args, pool_csv, need, pass_no):
    """Balanced collector (catalog-listed / near-catalog / independent general)."""
    general_heavy = pass_no > 1
    cmd = [sys.executable, str(HERE / "collect_pubchem_candidates.py"), "--online",
           "--out", str(args.stages), "--run-id", "A", "--max-candidates", str(need),
           "--max-requests", str(max(350, need * 9)), "--catalog-per-target", "6",
           "--random-seed", str(20261117 + 7 * pass_no),
           "--random-cid-probes", str(min(5000, max(80, need * 6))),
           "--exclude-file", str(pool_csv)]
    if general_heavy:  # later passes: independent chemicals are the easiest to scale
        cmd += ["--listed-share", "0.0", "--general-share", "1.0"]
    run_stage(cmd)
    f = args.stages / "A" / "candidates_for_review.csv"
    return read_csv(f) if f.is_file() else []


def stage_b(args, pool_csv, need):
    """Boundary probes and the mixture-name research queue."""
    run_stage([sys.executable, str(HERE / "collect_boundary_candidates.py"), "--online",
               "--out", str(args.stages), "--run-id", "B", "--max-candidates", str(need),
               "--max-requests", "600", "--exclude-file", str(pool_csv)])
    d = args.stages / "B"
    rows = read_csv(d / "candidates_for_review.csv") if (d / "candidates_for_review.csv").is_file() else []
    return rows, d


# ------------------------------------------------------------------ main flow
def load_pool(out, sources):
    pool_file = out / "review_sheet.csv"
    if pool_file.is_file():
        return read_csv(pool_file), False
    return [], True  # first run: import earlier batches


def run(args):
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    catalog_path, baseline_path = Path(args.catalog), Path(args.baseline)
    smiles_path = Path(args.smiles)
    baseline_rows = read_csv(baseline_path)
    smiles_by_cas = {r["cas"]: r["smiles"] for r in read_csv(smiles_path) if r.get("smiles")}
    catalog = pre.load_catalog(catalog_path)
    catalog_cas = {c for t in catalog.values()
                   for c in t["reference"] | t["members"] | t["mixture_cas"] | t["components"]}
    dedup = Dedup(baseline_rows, smiles_by_cas, catalog_cas)
    dropped, passes = [], []

    pool, first_time = load_pool(out, args.sources)
    pool = [normalise(r, r.get("source_batch", ""), r.get("legacy_case_id", "")) | {"case_id": r["case_id"]}
            for r in pool]
    for r in pool:
        dedup.keep(r)
    next_id = max([int(r["case_id"].split("-")[1]) for r in pool] + [0]) + 1
    if first_time:  # one-time import of earlier batches, in a fixed order
        for name in SEED_ORDER:
            f = Path(args.sources) / name
            if f.is_file():
                next_id = add_rows(pool, dropped, dedup, read_csv(f), f.stem.split("_candidates")[0], next_id)

    target_rows = target_new_count(args.target_total, len(baseline_rows), args.overshoot)
    extra_files = {}
    if args.online:
        args.stages.mkdir(parents=True, exist_ok=True)
        import_legacy_cache(args.stages, args.stages.parent)
        for pass_no in range(1, args.max_passes + 1):
            need = target_rows - len(pool)
            if need <= 0:
                break
            pool_csv = args.stages / "pool.csv"  # scratch copy handed to the stages as exclude-file
            write_csv(pool_csv, pool, POOL_FIELDS)
            before = len(pool)
            if pass_no == 1:
                rows_b, bdir = stage_b(args, pool_csv, max(1, round(need * 0.4)))
                next_id = add_rows(pool, dropped, dedup, rows_b, "boundary", next_id)
                for fname in ("mixture_name_resolution.csv", "skipped_probes.csv",
                              "mixture_name_research_queue.csv"):
                    if (bdir / fname).is_file():
                        extra_files[fname] = bdir / fname
                write_csv(pool_csv, pool, POOL_FIELDS)
                need = target_rows - len(pool)
            if need > 0:
                rows_a = stage_a(args, pool_csv, need, pass_no)
                next_id = add_rows(pool, dropped, dedup, rows_a, "balanced", next_id)
            passes.append({"pass": pass_no, "added": len(pool) - before, "pool_size": len(pool)})
            if len(pool) == before:
                break  # nothing new is available: stop honestly instead of looping

    previous_sheet = read_csv(out / "review_sheet.csv") if (out / "review_sheet.csv").is_file() else []
    results, hits, summary = pre.run(pool, catalog_path, baseline_path, smiles_path)
    meta = {r["case_id"]: r for r in pool}
    for r in results:
        r["legacy_case_id"] = meta[r["case_id"]]["legacy_case_id"]
        r["source_batch"] = meta[r["case_id"]]["source_batch"]
        r["pubchem_cid"] = meta[r["case_id"]]["pubchem_cid"]
    results = carry_over_human(results, previous_sheet)

    write_csv(out / "review_sheet.csv", results, SHEET_FIELDS)

    n_base = len(baseline_rows)
    summary.update({
        "pool_size": len(pool), "baseline_cases": n_base,
        "target_total": args.target_total, "overshoot": args.overshoot,
        "target_candidate_rows": target_rows,
        "potential_total_if_all_adjudicated": n_base + len(pool),
        "shortfall_candidate_rows": max(0, target_rows - len(pool)),
        "by_source_batch": dict(Counter(r["source_batch"] for r in pool)),
        "dropped_by_reason": dict(Counter(d["reason"].split(":")[0] for d in dropped)),
        "collection_passes": passes, "mode": "ONLINE" if args.online else "OFFLINE_REBUILD",
        "rows_with_reviewer_input": sum(1 for r in results if reviewer_touched(r)),
        "dropped_candidates": [{k: d.get(k, "") for k in ("cas_inputs", "source_batch", "reason",
                                                          "pubchem_title_human_only")} for d in dropped],
    })
    if extra_files.get("mixture_name_resolution.csv"):
        summary["mixture_name_resolution"] = read_csv(extra_files["mixture_name_resolution.csv"])
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--online", action="store_true", help="collect new candidates from PubChem")
    p.add_argument("--target-total", type=int, default=300,
                   help="validation set size INCLUDING the frozen baseline cases (default 300)")
    p.add_argument("--overshoot", type=float, default=1.2,
                   help="collect this factor more than needed to absorb reviewer exclusions")
    p.add_argument("--max-passes", type=int, default=3)
    p.add_argument("--out", default=str(DEFAULT_OUT), help="the single output folder")
    p.add_argument("--stages", default=str(DEFAULT_STAGES), help="scratch + PubChem cache (not tracked)")
    p.add_argument("--sources", default=str(DEFAULT_OUT / "_sources"))
    p.add_argument("--catalog", default=str(ROOT / "data/regulatory_catalog.csv"))
    p.add_argument("--baseline", default=str(ROOT / "data/retrieval_INPUT.csv"))
    p.add_argument("--smiles", default=str(ROOT / "intermediate/shared_pubchem_smiles.csv"))
    args = p.parse_args()
    args.out, args.stages, args.sources = Path(args.out), Path(args.stages), Path(args.sources)
    s = run(args)
    print(f"\n후보 풀: {s['pool_size']}건  (기존 baseline {s['baseline_cases']}건 별도)")
    print(f"목표 {s['target_total']}건 도달에 필요한 후보 행: {s['target_candidate_rows']}건, 부족: {s['shortfall_candidate_rows']}건")
    print("출처:", s["by_source_batch"], " 제외(중복):", s["dropped_by_reason"])
    print("자동 분류:", s["by_class"], " 우선순위:", s["by_priority"])
    for w in s["catalog_warnings"]:
        print("CATALOG WARNING:", w)
    print(f"검토표: {args.out / 'review_sheet.csv'}")
    if s["shortfall_candidate_rows"] and args.online:
        print("목표에 못 미쳤습니다. 같은 명령을 다시 실행하면 같은 폴더에 이어서 추가합니다.")
    elif s["shortfall_candidate_rows"]:
        print("추가 수집은 --online 으로 실행하세요.")


if __name__ == "__main__":
    main()
