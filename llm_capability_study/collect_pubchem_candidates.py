#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Collect candidate chemicals for human review, never assign regulatory gold labels.

Python >= 3.10. Standard library only. PubChem PUG REST optional (--online).
Source: frozen 29-target catalog + verified PubChem CAS/CID cache + new API queries.
Original Claude benchmark is READ-ONLY and excluded from new suggestions.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
FILES = {
    "catalog": ROOT / "data/regulatory_catalog.csv",
    "baseline": ROOT / "data/retrieval_INPUT.csv",
    "pubchem_cache": ROOT / "intermediate/pubchem_exact_cas_cache.csv",
    "shared_smiles": ROOT / "intermediate/shared_pubchem_smiles.csv",
}
PUG = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
CAS = re.compile(r"^(?:CAS(?: Registry)?(?: Number)?[ :#]+)?(\d{2,7}-\d{2}-\d)$", re.I)
TEMPLATE = [
    "case_id", "cas_inputs", "source_category", "difficulty_tag", "gold_status",
    "gold_target_id", "regulatory_source_url", "regulatory_source_date",
    "regulatory_evidence", "identity_evidence_url", "smiles", "smiles_qc_status",
    "reviewer1_status", "reviewer2_status", "adjudication_status", "notes_human_only",
]
EXTRA = [
    "discovery_method", "suggested_target_ids_human_only", "seed_cas",
    "similarity_threshold", "pubchem_cid", "pubchem_title_human_only",
    "pubchem_identity_check", "pubchem_record_url", "retrieved_at_utc",
]
# Discovery probes, NOT regulatory evidence and NOT labels.
# The name-to-CID and CID-to-CAS links are cross-checked via PubChem.
SALT_PROBES = {
    "110-15-6": ["disodium succinate", "potassium succinate", "sodium hydrogen succinate"],
    "110-85-0": ["piperazine dihydrochloride", "piperazine hydrochloride"],
    "113-00-8": ["guanidine hydrochloride", "guanidinium chloride"],
    "144-62-7": ["sodium oxalate", "potassium oxalate"],
    "50-21-5": ["sodium lactate", "calcium lactate"],
    "64-19-7": ["sodium acetate", "potassium acetate"],
    "65-85-0": ["sodium benzoate", "potassium benzoate"],
    "69-72-7": ["sodium salicylate", "calcium salicylate"],
    "77-92-9": ["trisodium citrate", "potassium citrate"],
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path):
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def write_csv(path, data, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(data)


def cas_list(s):
    return [x.strip() for x in (s or "").split("|") if x.strip()]


def signature(s):
    return tuple(sorted(set(cas_list(s))))


def valid_cas(s):
    m = CAS.fullmatch(str(s or "").strip())
    if not m:
        return ""
    a = m.group(1)
    digits = (a.replace("-", ""))[:-1]
    check = sum(int(d) * (i + 1) for i, d in enumerate(reversed(digits))) % 10
    return a if check == int(a[-1]) else ""


def from_synonyms(synonyms):
    result = []
    seen = set()
    for s in synonyms:
        cas = valid_cas(s)
        if cas and cas not in seen:
            result.append(cas)
            seen.add(cas)
    return result


def json_atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


class RequestBudget(Exception):
    pass


class PubChem:
    def __init__(self, args, out):
        self.args = args
        self.dir = out / "pubchem_http_cache"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.requests = 0
        self.cached = 0
        self.last = 0.0
        self.failures = []

    def get(self, path, params=None):
        url = PUG + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        key = hashlib.sha256(url.encode()).hexdigest()
        file = self.dir / (key + ".json")
        if file.is_file():
            self.cached += 1
            return json.loads(file.read_text(encoding="utf-8"))
        if self.requests >= self.args.max_requests:
            raise RequestBudget("Maximum new PubChem request budget reached")
        for attempt in range(4):
            if self.requests >= self.args.max_requests:
                raise RequestBudget("Maximum new PubChem request budget reached")
            pause = 1.0 / self.args.rate_per_sec - (time.monotonic() - self.last)
            if pause > 0:
                time.sleep(pause)
            self.last = time.monotonic()
            self.requests += 1
            req = urllib.request.Request(url, headers={
                "User-Agent": "AcademicCASBenchmarkCollector/1.0 (research; PubChem PUG REST)",
                "Accept": "application/json",
            })
            try:
                with urllib.request.urlopen(req, timeout=self.args.timeout) as response:
                    result = json.loads(response.read().decode("utf-8"))
                json_atomic(file, result)
                return result
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    result = {"_notfound": True}
                    json_atomic(file, result)
                    return result
                if exc.code in (429, 500, 502, 503, 504) and attempt < 3:
                    time.sleep(min(30, 2 ** attempt * 3))
                    continue
                self.failures.append(f"HTTP {exc.code}: {url}")
                return {}
            except (urllib.error.URLError, TimeoutError, ValueError) as exc:
                if attempt < 3:
                    time.sleep(min(30, 2 ** attempt * 3))
                    continue
                self.failures.append(f"{type(exc).__name__}: {url}")
                return {}
        return {}

    def cids_for_name(self, name):
        path = "/compound/name/" + urllib.parse.quote(name, safe="") + "/cids/JSON"
        payload = self.get(path)
        return [int(x) for x in (payload.get("IdentifierList") or {}).get("CID", [])[:15]]

    def near_cids(self, cid):
        path = f"/compound/fastsimilarity_2d/cid/{int(cid)}/cids/JSON"
        payload = self.get(path, {
            "Threshold": self.args.threshold,
            "MaxRecords": self.args.max_records,
        })
        return [int(x) for x in (payload.get("IdentifierList") or {}).get("CID", [])]

    def synonyms(self, cid):
        data = self.get(f"/compound/cid/{int(cid)}/synonyms/JSON")
        entries = data.get("InformationList", {}).get("Information", [])
        return entries[0].get("Synonym", []) if entries else []

    def properties(self, cid):
        # PubChem supports SMILES/ConnectivitySMILES in modern PUG REST.
        data = self.get(f"/compound/cid/{int(cid)}/property/Title,SMILES,ConnectivitySMILES/JSON")
        props = data.get("PropertyTable", {}).get("Properties", [])
        if not props:
            # Backward-compatible aliases are still used by historical frozen data.
            data = self.get(f"/compound/cid/{int(cid)}/property/Title,IsomericSMILES,CanonicalSMILES/JSON")
            props = data.get("PropertyTable", {}).get("Properties", [])
        p = props[0] if props else {}
        return {
            "title": str(p.get("Title") or ""),
            "smiles": str(p.get("SMILES") or p.get("IsomericSMILES")
                          or p.get("ConnectivitySMILES") or p.get("CanonicalSMILES") or ""),
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--online", action="store_true", help="Actually call PubChem PUG REST.")
    parser.add_argument("--out", default=str(HERE / "collection_output"))
    parser.add_argument("--max-candidates", type=int, default=80)
    parser.add_argument("--catalog-per-target", type=int, default=3)
    parser.add_argument("--seeds-per-target", type=int, default=2)
    parser.add_argument("--max-seeds", type=int, default=18)
    parser.add_argument("--neighbors-per-seed", type=int, default=4)
    parser.add_argument("--max-neighbor-cids", type=int, default=10)
    parser.add_argument("--max-records", type=int, default=30)
    parser.add_argument("--threshold", type=int, default=90)
    parser.add_argument("--salts-per-parent", type=int, default=2)
    parser.add_argument("--rate-per-sec", type=float, default=2.0)
    parser.add_argument("--max-requests", type=int, default=240)
    parser.add_argument("--timeout", type=int, default=45)
    args = parser.parse_args()
    if not 1 <= args.max_candidates <= 3000:
        parser.error("--max-candidates must be 1..3000.")
    if not 80 <= args.threshold <= 100:
        parser.error("--threshold must be 80..100.")
    if not 0 < args.rate_per_sec <= 3:
        parser.error("--rate-per-sec must be >0 and <=3.")
    if min(args.catalog_per_target, args.seeds_per_target, args.max_seeds,
           args.neighbors_per_seed, args.max_neighbor_cids, args.max_records,
           args.salts_per_parent, args.max_requests) < 0:
        parser.error("Limits cannot be negative.")
    out = Path(args.out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    catalog = read_csv(FILES["catalog"])
    baseline = read_csv(FILES["baseline"])
    p_cache = read_csv(FILES["pubchem_cache"])
    frozen_smiles = read_csv(FILES["shared_smiles"])
    if len(catalog) != 29 or len(baseline) != 112:
        raise RuntimeError("Frozen 29-target / 112-case baseline changed.")
    old = {signature(r["cas_inputs"]) for r in baseline}
    known = {
        r["cas"]: r for r in p_cache
        if r.get("structure_status") == "PUBCHEM_EXACT_CAS_VERIFIED"
        and (r.get("pubchem_cas_verified") or "").lower() == "true"
        and r.get("pubchem_cid", "").isdigit()
    }
    smiles = {r["cas"]: r["smiles"] for r in frozen_smiles}
    per_cas_targets = {}
    for r in catalog:
        cas_fields = ["reference_cas_set", "official_member_cas_set", "official_mixture_cas"]
        for field in cas_fields:
            for cas in cas_list(r[field]):
                per_cas_targets.setdefault(cas, set()).add(r["target_id"])
    proposals = {}
    errors = []
    client = PubChem(args, out) if args.online else None

    def add(cas, typ, method, target, seed="", cid="", title="", struct="",
            qc="", difficulty="", threshold="", identity_url=""):
        cas = valid_cas(cas)
        if not cas or signature(cas) in old:
            return False
        if cas in proposals:
            previous = proposals[cas]
            ids = set(previous["suggested_target_ids_human_only"].split("|")) - {""}
            ids.add(target)
            ids.update(per_cas_targets.get(cas, set()))
            previous["suggested_target_ids_human_only"] = "|".join(sorted(ids))
            methods = set(previous["discovery_method"].split("|"))
            methods.add(method)
            previous["discovery_method"] = "|".join(sorted(methods))
            return False
        if len(proposals) >= args.max_candidates:
            return False
        hints = sorted({target} | per_cas_targets.get(cas, set()))
        structure = struct or smiles.get(cas, "")
        row = {k: "" for k in TEMPLATE + EXTRA}
        row.update({
            "cas_inputs": cas,
            "source_category": typ,
            "difficulty_tag": difficulty,
            "gold_status": "REVIEW_PENDING",
            "gold_target_id": "",
            "regulatory_source_url": "",
            "regulatory_source_date": "",
            "regulatory_evidence": "",
            "identity_evidence_url": identity_url or (
                f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}" if cid else ""),
            "smiles": structure,
            "smiles_qc_status": "PUBCHEM_RECORDED_NEEDS_REVIEW" if structure else "MISSING_NEEDS_REVIEW",
            "reviewer1_status": "PENDING",
            "reviewer2_status": "PENDING",
            "adjudication_status": "PENDING",
            "notes_human_only": "PubChem does NOT establish regulatory status. "
                                "Compare against ALL 29 targets and verify CAS identity independently.",
            "discovery_method": method,
            "suggested_target_ids_human_only": "|".join(hints),
            "seed_cas": seed,
            "similarity_threshold": str(threshold),
            "pubchem_cid": str(cid),
            "pubchem_title_human_only": title,
            "pubchem_identity_check": qc,
            "pubchem_record_url": (
                f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}" if cid else ""),
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        })
        proposals[cas] = row
        return True

    # STAGE 1: official CAS members and parent references from already verified
    # frozen inventory. Not automatic truth: multi-target overlaps exist.
    for r in catalog:
        typ = r["target_type"]
        if typ == "MIXTURE":
            names = cas_list(r["official_mixture_cas"])  # components are NOT mixture CAS
        else:
            names = cas_list(r["reference_cas_set"]) + cas_list(r["official_member_cas_set"])
        added = 0
        for cas in names:
            if added >= args.catalog_per_target:
                break
            if cas not in known:
                continue
            rec = known[cas]
            if add(cas, typ, "ARCHIVED_CATALOG_CAS", r["target_id"],
                   cid=rec["pubchem_cid"], title=rec["pubchem_title"],
                   struct=smiles.get(cas, rec["pubchem_isomeric_smiles"]),
                   qc="ARCHIVED_EXACT_CAS_VERIFIED",
                   difficulty="EXACT_LISTED" if typ != "MIXTURE" else "MIXTURE_CAS",
                   identity_url=rec.get("pubchem_record_url", "")):
                added += 1

    # STAGE 2: PubChem name search for salts (good positive prospects, NO LABEL).
    # STAGE 3: 2D similarity search for related compounds (not necessarily negatives).
    if args.online and len(proposals) < args.max_candidates:
        try:
            for r in catalog:
                if r["target_type"] != "PARENT_SALT":
                    continue
                ref = cas_list(r["reference_cas_set"])
                if len(ref) != 1:
                    continue
                for name in SALT_PROBES.get(ref[0], [])[:args.salts_per_parent]:
                    if len(proposals) >= args.max_candidates:
                        break
                    for cid in client.cids_for_name(name)[:2]:
                        syn = client.synonyms(cid)
                        props = client.properties(cid)
                        for candidate in from_synonyms(syn)[:3]:
                            if signature(candidate) in old or candidate in proposals:
                                continue
                            if cid not in client.cids_for_name(candidate):
                                continue  # Reciprocal CAS->CID check
                            if add(candidate, r["target_type"], "PUBCHEM_SALT_NAME_SEARCH",
                                   r["target_id"], seed=ref[0], cid=cid,
                                   title=props["title"], struct=props["smiles"],
                                   qc="CAS_CID_RECIPROCAL_PUG_REST",
                                   difficulty="SALT_CANDIDATE"):
                                break
                        if len(proposals) >= args.max_candidates:
                            break

            seeds = []
            # One/two seeds per parent or group; avoid inferring mixture status from
            # a structurally similar SINGLE COMPONENT.
            for r in catalog:
                if r["target_type"] == "MIXTURE":
                    continue
                vals = cas_list(r["reference_cas_set"]) + cas_list(r["official_member_cas_set"])
                take = 0
                for cas in vals:
                    if cas in known and cas not in {s["cas"] for s in seeds}:
                        seeds.append({
                            "cas": cas, "target": r["target_id"], "type": r["target_type"],
                            "cid": known[cas]["pubchem_cid"]})
                        take += 1
                        if take >= args.seeds_per_target:
                            break
                if len(seeds) >= args.max_seeds:
                    break
            for seed in seeds[:args.max_seeds]:
                if len(proposals) >= args.max_candidates:
                    break
                accepted = 0
                cid_ids = client.near_cids(seed["cid"])
                for cid in cid_ids[:args.max_neighbor_cids]:
                    if accepted >= args.neighbors_per_seed or len(proposals) >= args.max_candidates:
                        break
                    if str(cid) == str(seed["cid"]):
                        continue
                    syn = client.synonyms(cid)
                    cas_candidates = from_synonyms(syn)[:3]
                    if not cas_candidates:
                        continue
                    props = client.properties(cid)
                    for c in cas_candidates:
                        if signature(c) in old or c in proposals:
                            continue
                        if cid not in client.cids_for_name(c):
                            continue
                        if add(c, seed["type"], "PUBCHEM_2D_SIMILARITY",
                               seed["target"], seed=seed["cas"], cid=cid,
                               title=props["title"], struct=props["smiles"],
                               qc="CAS_CID_RECIPROCAL_PUG_REST",
                               difficulty="SIMILARITY_NEEDS_SCOPE_REVIEW",
                               threshold=args.threshold):
                            accepted += 1
                            break
        except RequestBudget as exc:
            errors.append(str(exc))
    if client:
        errors.extend(client.failures)

    # Audit mixture cases that cannot be mined as actual registered substances.
    gaps = []
    for r in catalog:
        if r["target_type"] != "MIXTURE":
            continue
        own = cas_list(r["official_mixture_cas"])
        baseline_has = any(signature(c) in old for c in own)
        gaps.append({
            "target_id": r["target_id"],
            "official_mixture_cas": "|".join(own),
            "component_cas": r["mixture_component_cas_set"],
            "candidate_from_official_mixture_cas": int(
                any(c in proposals for c in own)),
            "official_mixture_cas_in_baseline": int(baseline_has),
            "manual_followup_needed": "YES",
            "note": "Never invent a mixture by swapping components. "
                    "Look for an independently documented mixture/mixture CAS.",
        })
    result = list(proposals.values())
    for i, row in enumerate(result, 1):
        row["case_id"] = f"NEW-{i:04d}"
    write_csv(out / "candidates_for_review.csv", result, TEMPLATE + EXTRA)
    write_csv(out / "mixture_research_gaps.csv", gaps, list(gaps[0]))
    summary = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "ONLINE_PUBCHEM_PUG_REST" if args.online else "OFFLINE_ARCHIVED_CATALOG",
        "n_regulatory_targets": len(catalog),
        "n_existing_baseline_cases": len(old),
        "new_candidate_count": len(result),
        "candidates_by_method": dict(Counter(
            method for r in result for method in r["discovery_method"].split("|"))),
        "candidates_by_source_category": dict(Counter(r["source_category"] for r in result)),
        "candidate_gold_labels_assigned": 0,
        "all_new_labels": "REVIEW_PENDING",
        "new_network_requests": client.requests if client else 0,
        "cached_network_requests": client.cached if client else 0,
        "errors": errors,
        "args": vars(args),
        "source_sha256": {key: sha(path) for key, path in FILES.items()},
        "disclaimer": (
            "PubChem verifies chemical identifiers/structures, not legal scope. "
            "Even exact catalog CAS and reciprocal CAS-CID matches must be independently "
            "reviewed for target-specific membership. NOT_FOUND cannot be auto-labeled."
        ),
    }
    json_atomic(out / "collection_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nReview CSV: {out / 'candidates_for_review.csv'}")
    print(f"Mixture coverage gaps: {out / 'mixture_research_gaps.csv'}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
