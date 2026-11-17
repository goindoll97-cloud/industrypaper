#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Automatic PRE-REVIEW (triage) of PubChem candidates against the frozen 29-target catalog.

This script supports the human Gold review. It NEVER assigns a Gold label:
  * every output row keeps gold_status=REVIEW_PENDING and an empty gold_target_id;
  * auto_* columns are review priorities, not legal conclusions;
  * legal_basis_verification_required is always YES.
RDKit is used only as a structure-analysis helper for the reviewer, not as a Hybrid predictor.

Usage (from llm_capability_study/):
    python prereview_candidates.py --candidates collection_output/balanced_v2/candidates_for_review.csv
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

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from collect_pubchem_candidates import cas_list, read_csv, valid_cas  # noqa: E402

try:
    from rdkit import Chem, DataStructs, RDLogger
    from rdkit.Chem import rdFingerprintGenerator
    try:
        from rdkit.Chem.MolStandardize import rdMolStandardize
    except ImportError:  # older RDKit layout
        from rdkit.Chem import rdMolStandardize

    RDLogger.DisableLog("rdApp.*")
    HAVE_RDKIT = True
except ImportError:  # RDKit is optional: exact-CAS checks still work without it.
    HAVE_RDKIT = False

VERSION = "prereview_v1"
CAS_RE = re.compile(r"\b\d{2,7}-\d{2}-\d\b")

CLASSES = [
    "EXACT_CAS_MATCH",
    "POSSIBLE_GROUP_MEMBER",
    "POSSIBLE_PARENT_SALT",
    "POSSIBLE_OUT_OF_SCOPE",
    "AMBIGUOUS",
]
OUT_FIELDS = [
    "case_id", "cas_inputs", "source_category", "candidate_stratum", "discovery_method",
    "pubchem_title_human_only", "smiles", "suggested_target_ids_human_only",
    "auto_prereview_class", "auto_exact_target_ids", "auto_possible_target_ids",
    "auto_multi_target_overlap", "auto_nearest_target_id", "auto_max_similarity",
    "auto_flags", "auto_reasoning_ko", "review_priority",
    "legal_basis_verification_required", "auto_is_final_gold",
    "gold_status", "gold_target_id",
    "human_gold_target_id", "human_legal_basis", "human_review_status", "prereview_version",
]
HIT_FIELDS = ["case_id", "cas_inputs", "target_id", "target_type", "signal", "basis", "evidence"]


# ---------------------------------------------------------------- catalog
def load_catalog(path):
    catalog = {}
    for r in read_csv(path):
        catalog[r["target_id"]] = {
            "type": r["target_type"],
            "text": r["regulatory_scope_text"],
            "reference": set(cas_list(r["reference_cas_set"])),
            "members": set(cas_list(r["official_member_cas_set"])),
            "components": set(cas_list(r["mixture_component_cas_set"])),
            "mixture_cas": set(cas_list(r["official_mixture_cas"])),
        }
    return catalog


def catalog_warnings(catalog):
    """Internal-consistency checks on the frozen catalog (reported, never auto-fixed)."""
    warnings = []
    for tid, t in catalog.items():
        if t["type"] == "MIXTURE" and t["components"]:
            in_text = set(CAS_RE.findall(t["text"]))
            if in_text != t["components"]:
                warnings.append({
                    "target_id": tid,
                    "issue": "MIXTURE_TEXT_CAS_DIFFERS_FROM_COMPONENT_SET",
                    "cas_only_in_scope_text": sorted(in_text - t["components"]),
                    "cas_only_in_component_set": sorted(t["components"] - in_text),
                })
    return warnings


def exact_signals(cas, catalog):
    """CAS-level relations. Component CAS of a mixture is NOT an exact match."""
    out = []
    for tid, t in catalog.items():
        if cas in t["reference"]:
            out.append((tid, "EXACT", "REFERENCE_CAS"))
        if cas in t["members"]:
            out.append((tid, "EXACT", "OFFICIAL_MEMBER_CAS"))
        if cas in t["mixture_cas"]:
            out.append((tid, "EXACT", "OFFICIAL_MIXTURE_CAS"))
        if cas in t["components"]:
            out.append((tid, "COMPONENT", "MIXTURE_COMPONENT_CAS"))
    return out


# ---------------------------------------------------------------- structure helpers
if HAVE_RDKIT:
    _UNCHARGER = rdMolStandardize.Uncharger()
    _FPGEN = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
    _MG_CATION = Chem.MolFromSmarts(
        "[CH3]N([CH3])c1ccc(cc1)C(=C1C=CC(=[N+]([CH3])[CH3])C=C1)c1[cH][cH][cH][cH][cH]1")
    _CR_VI = Chem.MolFromSmarts("[Cr](=O)=O")
    _ETHOXY = Chem.MolFromSmarts("cO[CH2][CH2]O")


def parse(smiles):
    if not HAVE_RDKIT or not smiles:
        return None
    return Chem.MolFromSmiles(smiles)


def fragments(mol):
    """Non-water fragments of a molecule."""
    frags = []
    for f in Chem.GetMolFrags(mol, asMols=True):
        if f.GetNumAtoms() == 1 and f.GetAtomWithIdx(0).GetSymbol() == "O" \
                and f.GetAtomWithIdx(0).GetFormalCharge() == 0:
            continue  # hydrate water
        frags.append(f)
    return frags


def is_organic(frag):
    """Carbon-containing fragment, excluding carbonate/bicarbonate/CO2-type (carbon bonded only to O, no C-H)."""
    return any(a.GetSymbol() == "C" and (a.GetTotalNumHs() > 0
                                         or any(n.GetSymbol() != "O" for n in a.GetNeighbors()))
               for a in frag.GetAtoms())


def frag_key(frag):
    """Connectivity-level identity of a neutralised fragment (stereo/charge-state independent)."""
    neutral = _UNCHARGER.uncharge(Chem.Mol(frag))
    try:
        key = Chem.MolToInchiKey(neutral)
    except Exception:
        key = ""
    return key.split("-")[0] if key else Chem.MolToSmiles(neutral, isomericSmiles=False)


def structure_key(mol):
    """Whole-entry identity ignoring hydrate water, stereo, charge state and ionic-vs-covalent metal drawing."""
    combined = Chem.Mol()
    for f in fragments(mol):
        combined = Chem.CombineMols(combined, f)
    try:
        key = Chem.MolToInchiKey(combined)
    except Exception:
        key = ""
    return key.split("-")[0] if key else ".".join(sorted(frag_key(f) for f in fragments(mol)))


def largest_organic(mol):
    organics = [f for f in fragments(mol) if is_organic(f)]
    return max(organics, key=lambda f: f.GetNumHeavyAtoms()) if organics else None


def _acyclic_sp3_carbons(mol, start, origin):
    """Count atoms in the acyclic sp3-carbon cluster starting at `start`; None if anything else."""
    seen, stack = {start}, [start]
    while stack:
        atom = mol.GetAtomWithIdx(stack.pop())
        if atom.GetSymbol() != "C" or atom.GetIsAromatic() or atom.IsInRing() \
                or atom.GetHybridization() != Chem.HybridizationType.SP3:
            return None
        for n in atom.GetNeighbors():
            if n.GetIdx() not in seen and n.GetIdx() != origin:
                seen.add(n.GetIdx())
                stack.append(n.GetIdx())
    return len(seen)


def nonylphenol_like(mol):
    """Mono-nonyl phenol (or its ethoxylate): benzene ring with one O-substituent and one C9 alkyl."""
    for ring in mol.GetRingInfo().AtomRings():
        if len(ring) != 6 or not all(mol.GetAtomWithIdx(i).GetIsAromatic()
                                     and mol.GetAtomWithIdx(i).GetSymbol() == "C" for i in ring):
            continue
        oxy, alkyl, other = [], [], 0
        for i in ring:
            for n in mol.GetAtomWithIdx(i).GetNeighbors():
                if n.GetIdx() in ring:
                    continue
                if n.GetSymbol() == "O":
                    oxy.append(n)
                elif n.GetSymbol() == "C":
                    alkyl.append((i, n.GetIdx()))
                else:
                    other += 1
        if other or len(oxy) != 1 or len(alkyl) != 1:
            continue
        if _acyclic_sp3_carbons(mol, alkyl[0][1], alkyl[0][0]) == 9:
            if oxy[0].GetTotalNumHs() == 1:
                return True, "NONYLPHENOL"
            if mol.HasSubstructMatch(_ETHOXY):
                return True, "NONYLPHENOL_ETHOXYLATE"
    return False, ""


def group_rule(target_id, mol):
    """Structural group heuristics for the five chemical-group targets. Returns (hit, reason)."""
    if target_id == "CG::LEAD_COMPOUNDS":
        if any(a.GetSymbol() == "Pb" for a in mol.GetAtoms()):
            return True, "Pb 원자 포함(납 화합물 후보)"
    elif target_id == "CG::CRVI_COMPOUNDS":
        if mol.HasSubstructMatch(_CR_VI):
            return True, "Cr(=O)=O 단위 포함(크로뮴산염·중크로뮴산염류, 6가 후보; 산화수는 SMILES만으로 확정 불가)"
    elif target_id == "CG::MG_SALTS":
        if mol.HasSubstructMatch(_MG_CATION):
            return True, "말라카이트 그린 양이온 골격 포함(염류 후보)"
    elif target_id == "CG::NONYLPHENOL_NPE":
        hit, kind = nonylphenol_like(mol)
        if hit:
            return True, f"C9 알킬 페놀 구조({kind})"
    elif target_id == "CG::TBT_TRIALKYLTIN":
        for a in mol.GetAtoms():
            if a.GetSymbol() == "Sn" and sum(
                    1 for n in a.GetNeighbors()
                    if n.GetSymbol() == "C" and not n.GetIsAromatic()) >= 3:
                return True, "Sn에 알킬 탄소 3개 이상 결합(트리알킬주석 후보)"
    return False, ""


# ---------------------------------------------------------------- main analysis
class Context:
    def __init__(self, catalog, smiles_by_cas, baseline_cas, near_threshold):
        self.catalog = catalog
        self.smiles_by_cas = smiles_by_cas
        self.near_threshold = near_threshold
        self.parent_keys = {}      # PS target -> connectivity key of parent
        self.reference_fps = {}    # target -> [(cas, fingerprint)]
        self.known_structures = {}  # structure key -> label (catalog / baseline structures)
        if not HAVE_RDKIT:
            return
        for tid, t in catalog.items():
            for cas in sorted(t["reference"] | t["members"]):
                mol = parse(smiles_by_cas.get(cas, ""))
                if mol is None:
                    continue
                big = largest_organic(mol)
                if big is not None:
                    self.reference_fps.setdefault(tid, []).append((cas, _FPGEN.GetFingerprint(big)))
                self.known_structures.setdefault(structure_key(mol), f"CATALOG:{cas}")
                if t["type"] == "PARENT_SALT" and cas in t["reference"] and big is not None:
                    self.parent_keys[tid] = frag_key(big)
        for cas in baseline_cas:
            mol = parse(smiles_by_cas.get(cas, ""))
            if mol is not None:
                self.known_structures.setdefault(structure_key(mol), f"BASELINE:{cas}")


def analyse(row, ctx, own_keys):
    cas = (row.get("cas_inputs") or "").strip()
    signals = []        # (target_id, signal, basis, evidence)
    flags = []
    reasons = []

    if not valid_cas(cas):
        flags.append("CAS_CHECKSUM_INVALID")
    for tid, signal, basis in exact_signals(cas, ctx.catalog):
        signals.append((tid, signal, basis, f"CAS {cas} in {basis}"))

    mol = parse(row.get("smiles", ""))
    max_sim, nearest, sims = None, "", {}
    if not row.get("smiles"):
        flags.append("STRUCTURE_MISSING")
    elif not HAVE_RDKIT:
        flags.append("RDKIT_UNAVAILABLE")
    elif mol is None:
        flags.append("SMILES_PARSE_FAILED")

    same_as_parent = []
    if mol is not None:
        frags = fragments(mol)
        if len(frags) > 1:
            flags.append("MULTI_COMPONENT_ENTRY")
        # chemical-group heuristics
        for tid, t in ctx.catalog.items():
            if t["type"] == "CHEMICAL_GROUP":
                hit, why = group_rule(tid, mol)
                if hit:
                    signals.append((tid, "GROUP_RULE", "STRUCTURE_RULE", why))
        # parent / salt relationship
        for tid, parent_key in ctx.parent_keys.items():
            matching = [f for f in frags if is_organic(f) and frag_key(f) == parent_key]
            if not matching:
                continue
            others = [f for f in frags if f not in matching]
            charged = any(a.GetFormalCharge() for f in matching for a in f.GetAtoms())
            if others or charged:
                signals.append((tid, "PARENT_SALT_RULE", "STRUCTURE_RULE",
                                "원물질 골격 + 대이온/다성분 구성(염류 후보)"))
            else:
                same_as_parent.append(tid)
                signals.append((tid, "SAME_PARENT_STRUCTURE", "STRUCTURE_RULE",
                                "원물질과 동일 구조이나 CAS가 다름"))
        # nearest catalog structure (largest organic fragment, Morgan/Tanimoto)
        big = largest_organic(mol)
        if big is not None:
            fp = _FPGEN.GetFingerprint(big)
            for tid, refs in ctx.reference_fps.items():
                sim = max((DataStructs.TanimotoSimilarity(fp, rfp) for _, rfp in refs), default=0.0)
                sims[tid] = sim
                if max_sim is None or sim > max_sim:
                    max_sim, nearest = sim, tid
        # duplicate structures (other candidates / catalog / baseline)
        key = structure_key(mol)
        dups = [cid for cid, k in own_keys.items() if k == key and cid != row["case_id"]]
        if dups:
            flags.append("DUPLICATE_STRUCTURE_OF_CANDIDATE:" + "|".join(sorted(dups)))
        known = ctx.known_structures.get(key)
        if known and known.split(":", 1)[1] != cas:
            flags.append(f"DUPLICATE_STRUCTURE_OF_{known}")

    exact = sorted({s[0] for s in signals if s[1] == "EXACT"})
    component = sorted({s[0] for s in signals if s[1] == "COMPONENT"})
    rule_targets = sorted({s[0] for s in signals if s[1] in ("GROUP_RULE", "PARENT_SALT_RULE")})
    possible = sorted(set(rule_targets) - set(exact))
    all_targets = set(exact) | set(rule_targets) | set(same_as_parent)
    overlap = len(all_targets) >= 2

    # exact CAS in a group but the structure rule does not confirm it -> reviewer must look
    for tid in exact:
        if ctx.catalog[tid]["type"] == "CHEMICAL_GROUP" and mol is not None \
                and tid not in rule_targets:
            flags.append(f"EXACT_CAS_BUT_RULE_NOT_CONFIRMED:{tid}")
    hint = set(cas_list(row.get("suggested_target_ids_human_only", "")))
    if hint and not (hint & (set(exact) | set(rule_targets))):
        flags.append("COLLECTION_HINT_NOT_CONFIRMED")
    if overlap:
        flags.append("MULTI_TARGET_OVERLAP")
    near_targets = sorted(t for t, v in sims.items() if v >= ctx.near_threshold and t not in all_targets)
    for tid in near_targets:
        flags.append(f"NEAR_NEIGHBOR_OF_TARGET:{tid}")
    if any(f.startswith("DUPLICATE_STRUCTURE_OF_BASELINE") for f in flags):
        reasons.append("기존 112건과 동일 구조(CAS만 다름): 신규 검증물질로 중복 포함할지 검토")

    # ---- class assignment (priority order) ----
    if exact:
        cls = "EXACT_CAS_MATCH"
        reasons.append("규제목록 CAS 직접 일치(" + ", ".join(exact) + "). 공식 고시 원문과 대조 필요")
    elif component:
        cls = "AMBIGUOUS"
        reasons.append("등재 혼합물의 구성성분 CAS(" + ", ".join(component)
                       + "). 단일물질이 혼합물 항목에 해당하는지는 법적 판단 필요")
    elif len(rule_targets) >= 2 or (rule_targets and same_as_parent):
        cls = "AMBIGUOUS"
        reasons.append("복수 규제항목에 중첩 가능(" + ", ".join(sorted(all_targets)) + ")")
    elif same_as_parent:
        cls = "AMBIGUOUS"
        reasons.append("원물질(" + ", ".join(same_as_parent) + ")과 구조는 같으나 CAS가 달라 동일성 확인 필요")
    elif rule_targets:
        tid = rule_targets[0]
        cls = "POSSIBLE_PARENT_SALT" if ctx.catalog[tid]["type"] == "PARENT_SALT" \
            else "POSSIBLE_GROUP_MEMBER"
    elif any(f in flags for f in ("STRUCTURE_MISSING", "SMILES_PARSE_FAILED", "RDKIT_UNAVAILABLE")):
        cls = "AMBIGUOUS"
        reasons.append("구조 분석 불가: 구조 정보를 확인한 뒤 재검토")
    else:
        cls = "POSSIBLE_OUT_OF_SCOPE"
        if near_targets:
            reasons.append(f"구조 규칙에는 해당하지 않으나 {', '.join(near_targets)}와 구조 유사"
                           f"(최대 Tanimoto {max_sim:.2f}). 경계 사례일 수 있어 우선 검토")
        else:
            reasons.append("등재 CAS·구조 규칙 모두 해당 없음(규제항목과 무관해 보임). 단, 자동 NOT_FOUND 아님")
    for _, _, _, why in signals:
        if why and why not in reasons and cls not in ("EXACT_CAS_MATCH",):
            reasons.append(why)

    if cls == "POSSIBLE_OUT_OF_SCOPE":
        # Boundary probes are built to sit near a target, so an unconfirmed collection hint
        # carries no information there and must not raise the priority by itself.
        hint_unconfirmed = ("COLLECTION_HINT_NOT_CONFIRMED" in flags
                            and row.get("candidate_stratum") != "BOUNDARY_PROBE")
        priority = "HIGH" if near_targets or hint_unconfirmed \
            or any(f.startswith("DUPLICATE_STRUCTURE_OF_BASELINE") for f in flags) else "LOW"
    elif cls == "EXACT_CAS_MATCH":
        priority = "HIGH" if overlap or any(f.startswith("EXACT_CAS_BUT") or f.startswith("DUPLICATE")
                                            for f in flags) else "MEDIUM"
    else:
        priority = "HIGH"

    return {
        "cls": cls, "exact": exact, "possible": possible, "overlap": overlap,
        "nearest": nearest, "max_sim": max_sim, "flags": flags, "reasons": reasons,
        "priority": priority, "signals": signals,
    }


def run(candidates, catalog_path, baseline_path, smiles_path, near_threshold=0.5):
    catalog = load_catalog(catalog_path)
    smiles_by_cas = {r["cas"]: r["smiles"] for r in read_csv(smiles_path) if r.get("smiles")}
    for row in candidates:  # candidate rows carry their own PubChem SMILES
        if row.get("cas_inputs") and row.get("smiles"):
            smiles_by_cas.setdefault(row["cas_inputs"], row["smiles"])
    baseline_cas = {c for r in read_csv(baseline_path) for c in cas_list(r["cas_inputs"])}
    ctx = Context(catalog, smiles_by_cas, baseline_cas, near_threshold)
    own_keys = {}
    for row in candidates:
        mol = parse(row.get("smiles", ""))
        if mol is not None:
            own_keys[row["case_id"]] = structure_key(mol)

    results, hits = [], []
    for row in candidates:
        a = analyse(row, ctx, own_keys)
        results.append({
            "case_id": row["case_id"], "cas_inputs": row["cas_inputs"],
            "source_category": row.get("source_category", ""),
            "candidate_stratum": row.get("candidate_stratum", ""),
            "discovery_method": row.get("discovery_method", ""),
            "pubchem_title_human_only": row.get("pubchem_title_human_only", ""),
            "smiles": row.get("smiles", ""),
            "suggested_target_ids_human_only": row.get("suggested_target_ids_human_only", ""),
            "auto_prereview_class": a["cls"],
            "auto_exact_target_ids": "|".join(a["exact"]),
            "auto_possible_target_ids": "|".join(a["possible"]),
            "auto_multi_target_overlap": "YES" if a["overlap"] else "NO",
            "auto_nearest_target_id": a["nearest"],
            "auto_max_similarity": "" if a["max_sim"] is None else f"{a['max_sim']:.3f}",
            "auto_flags": "|".join(a["flags"]),
            "auto_reasoning_ko": " / ".join(a["reasons"]),
            "review_priority": a["priority"],
            "legal_basis_verification_required": "YES",
            "auto_is_final_gold": "NO",
            "gold_status": "REVIEW_PENDING",
            "gold_target_id": "",
            "human_gold_target_id": "", "human_legal_basis": "",
            "human_review_status": "PENDING", "prereview_version": VERSION,
        })
        for tid, signal, basis, evidence in a["signals"]:
            hits.append({"case_id": row["case_id"], "cas_inputs": row["cas_inputs"],
                         "target_id": tid, "target_type": catalog[tid]["type"],
                         "signal": signal, "basis": basis, "evidence": evidence})
    summary = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "prereview_version": VERSION,
        "rdkit_available": HAVE_RDKIT,
        "n_candidates": len(results),
        "by_class": dict(Counter(r["auto_prereview_class"] for r in results)),
        "by_priority": dict(Counter(r["review_priority"] for r in results)),
        "by_stratum_and_class": {
            s: dict(Counter(r["auto_prereview_class"] for r in results if r["candidate_stratum"] == s))
            for s in sorted({r["candidate_stratum"] for r in results})},
        "multi_target_overlap_case_ids": [r["case_id"] for r in results
                                          if r["auto_multi_target_overlap"] == "YES"],
        "catalog_warnings": catalog_warnings(catalog),
        "near_neighbor_threshold": near_threshold,
        "gold_labels_assigned": 0,
        "disclaimer": "auto_* values are review priorities, not legal conclusions or Gold labels. "
                      "NOT_FOUND is never assigned automatically.",
    }
    return results, hits, summary


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--candidates", default=str(HERE / "collection_output/balanced_v2/candidates_for_review.csv"))
    p.add_argument("--catalog", default=str(ROOT / "data/regulatory_catalog.csv"))
    p.add_argument("--baseline", default=str(ROOT / "data/retrieval_INPUT.csv"))
    p.add_argument("--smiles", default=str(ROOT / "intermediate/shared_pubchem_smiles.csv"))
    p.add_argument("--out", default="", help="output folder (default: prereview_output/<candidate-file-parent>)")
    p.add_argument("--near-threshold", type=float, default=0.5)
    args = p.parse_args()

    cand_path = Path(args.candidates)
    out = Path(args.out) if args.out else HERE / "prereview_output" / cand_path.resolve().parent.name
    results, hits, summary = run(read_csv(cand_path), Path(args.catalog), Path(args.baseline),
                                 Path(args.smiles), args.near_threshold)
    write_csv(out / "prereview_results.csv", results, OUT_FIELDS)
    write_csv(out / "prereview_target_hits.csv", hits, HIT_FIELDS)
    (out / "prereview_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"candidates={summary['n_candidates']}  rdkit={HAVE_RDKIT}")
    for k, v in sorted(summary["by_class"].items()):
        print(f"  {k:24s} {v}")
    print("priority:", summary["by_priority"])
    for w in summary["catalog_warnings"]:
        print("CATALOG WARNING:", w)
    print("wrote:", out)


if __name__ == "__main__":
    main()
