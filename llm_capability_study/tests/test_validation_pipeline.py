# -*- coding: utf-8 -*-
"""Offline tests: boundary collector (fake PubChem) and validation dataset builder gates."""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import build_validation_dataset as bvd  # noqa: E402
import collect_boundary_candidates as cbc  # noqa: E402
import prereview_candidates as pre  # noqa: E402
from collect_pubchem_candidates import read_csv  # noqa: E402

SHEET_FIELDS = ["case_id", "cas_inputs", "source_category", "candidate_stratum", "difficulty_tag", "smiles",
                "human_gold_target_id", "human_legal_basis", "human_review_status", "source_batch"]


def write_sheet(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, SHEET_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in SHEET_FIELDS})


class TestMixtureNames(unittest.TestCase):
    def test_names_split_on_comma_space_and_and(self):
        text = ("Mixture of 3,4,5,6,6-pentamethyl-2-heptanol, 3,4,5,5,6-pentamethyl-2-heptanol, "
                "3,5,6,6-tetramethyl-4-methylene-2-heptanol and 3,5,5,6-tetramethyl-4-methylene-2-heptanol")
        names = cbc.mixture_component_names(text)
        self.assertEqual(len(names), 4)
        self.assertEqual(names[0], "3,4,5,6,6-pentamethyl-2-heptanol")

    def test_queue_only_covers_mixtures_without_cas(self):
        queue = cbc.research_queue(read_csv(ROOT / "data/regulatory_catalog.csv"))
        self.assertEqual({q["target_id"] for q in queue},
                         {"MX::2017-886", "MX::2017-887", "MX::2017-890", "MX::2017-891",
                          "MX::2017-892", "MX::2026-1-1328"})
        self.assertEqual(len(queue), 15)


class FakeClient:
    """Minimal stand-in for the PubChem client."""
    def __init__(self):
        self.names = {
            "glutaric acid": [743], "diethyl succinate": [8844], "fumaric acid": [444972],
            "maleic acid": [444266], "adipic acid": [196],
        }
        self.cas_to_cid = {"110-94-1": [743], "123-25-1": [8844], "110-15-6": [444972],
                           "124-04-9": [743]}  # maleic CAS maps to other cid
        self.props = {743: ("Glutaric acid", "C(CC(=O)O)CC(=O)O"),
                      8844: ("Diethyl succinate", "CCOC(=O)CCC(=O)OCC"),
                      444972: ("Fumaric acid", "C(=CC(=O)O)C(=O)O"),
                      444266: ("Maleic acid", "C(=CC(=O)O)C(=O)O"),
                      196: ("Adipic acid", "C(CCC(=O)O)CC(=O)O")}
        self.syn = {743: ["110-94-1"], 8844: ["123-25-1"], 444972: ["110-15-6"],
                    444266: ["110-16-7"], 196: ["124-04-9"]}

    def cids_for_name(self, value):
        return self.names.get(value.lower(), self.cas_to_cid.get(value, []))

    def properties(self, cid):
        t, s = self.props.get(cid, ("", ""))
        return {"title": t, "smiles": s}

    def synonyms(self, cid):
        return self.syn.get(cid, [])


@unittest.skipUnless(pre.HAVE_RDKIT, "RDKit not installed")
class TestBoundaryCollector(unittest.TestCase):
    def test_skips_and_accepts(self):
        # glutaric acid is accepted; diethyl succinate accepted; CAS 110-15-6 is catalog-listed.
        cas_seen, catalog_cas, structures = set(), {"110-15-6"}, set()
        rows, skipped = cbc.collect_boundary(FakeClient(), cas_seen, catalog_cas, structures, 50, 8)
        got = {r["cas_inputs"] for r in rows}
        self.assertIn("110-94-1", got)
        self.assertIn("123-25-1", got)
        self.assertNotIn("110-15-6", got)
        reasons = {s["reason"] for s in skipped}
        self.assertIn("CATALOG_LISTED_CAS", reasons)
        for r in rows:
            self.assertEqual(r["gold_status"], "REVIEW_PENDING")
            self.assertEqual(r["gold_target_id"], "")
            self.assertEqual(r["candidate_stratum"], "BOUNDARY_PROBE")

    def test_duplicate_structure_is_skipped(self):
        structures = set()
        _, catalog_cas = set(), set()
        rows, skipped = cbc.collect_boundary(FakeClient(), set(), catalog_cas, structures, 50, 8)
        # maleic/fumaric share connectivity: at most one of them can be accepted
        ids = [r["pubchem_cid"] for r in rows]
        self.assertFalse({"444972", "444266"} <= set(ids))

    def test_per_target_cap(self):
        rows, _ = cbc.collect_boundary(FakeClient(), set(), set(), set(), 50, 1)
        targets = [r["suggested_target_ids_human_only"] for r in rows]
        self.assertEqual(len(targets), len(set(targets)))


class TestBuilderGates(unittest.TestCase):
    def args(self, tmp, sheets, **kw):
        base = dict(reviewed=sheets, version="t", out=str(tmp / "out"),
                    catalog=str(ROOT / "data/regulatory_catalog.csv"),
                    baseline_input=str(ROOT / "data/retrieval_INPUT.csv"),
                    baseline_gold=str(ROOT / "data/retrieval_GOLD.csv"),
                    smiles=str(ROOT / "intermediate/shared_pubchem_smiles.csv"),
                    catalog_source_registry=str(tmp / "catalog_source_registry.csv"),
                    target_min=300, target_max=400, min_per_category=30,
                    allow_structure_duplicates=False, freeze=False)
        base.update(kw)
        return SimpleNamespace(**base)

    def test_gate_statuses(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            sheet = tmp / "batch1" / "sheet.csv"
            good = dict(case_id="A-1", cas_inputs="56-40-6", source_category="GENERAL_CHEMICAL",
                        smiles="C(C(=O)O)N", human_gold_target_id="NOT_FOUND",
                        human_legal_basis="29-target catalog checked", human_review_status="ADJUDICATED",
                        source_batch="balanced_v2")
            write_sheet(sheet, [
                good,
                {**good, "case_id": "A-2", "cas_inputs": "56-41-7", "human_review_status": "PENDING"},
                {**good, "case_id": "A-3", "cas_inputs": "56-45-1", "human_legal_basis": ""},
                {**good, "case_id": "A-4", "cas_inputs": "56-84-8", "human_gold_target_id": "PS::50-21-5|PS::64-19-7"},
                {**good, "case_id": "A-5", "cas_inputs": "56-87-1", "human_gold_target_id": "PS::NOPE"},
                {**good, "case_id": "A-6", "cas_inputs": "50-99-7", "human_review_status": "EXCLUDED"},
                {**good, "case_id": "A-7", "cas_inputs": "50-78-2", "human_gold_target_id": "NOT_FOUND|PS::64-19-7"},
            ])
            report, out = bvd.build(self.args(tmp, [str(sheet)]))
            self.assertEqual(report["n_new_included"], 2)
            self.assertEqual(report["n_new_excluded_by_reviewer"], 1)
            self.assertEqual(report["n_new_held"], 4)
            self.assertEqual(report["n_total"], 114)
            self.assertEqual(report["multi_target_cases"], 1)
            self.assertEqual({h["reason"] for h in report["held_cases"]},
                             {"STATUS_PENDING", "ADJUDICATED_BUT_TARGET_OR_LEGAL_BASIS_EMPTY", "UNKNOWN_TARGET_ID",
                              "NOT_FOUND_MIXED_WITH_TARGETS"})
            self.assertEqual(report["excluded_cases"][0]["case_id"], "A-6")
            gold = {g["query_id"]: g for g in read_csv(out / "validation_GOLD.csv")}
            self.assertEqual(gold["RQ-0113"]["gold_status"], "NOT_FOUND")
            self.assertEqual(gold["RQ-0114"]["gold_target_id"], "PS::50-21-5|PS::64-19-7")
            self.assertEqual(gold["RQ-0114"]["n_gold_targets"], "2")
            self.assertFalse((out / "held_not_included.csv").exists())
            meta = {r["query_id"]: r for r in read_csv(out / "validation_METADATA.csv")}
            self.assertEqual(meta["RQ-0113"]["source_batch"], "balanced_v2")

    def test_model_input_has_no_labels_or_names(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _, out = bvd.build(self.args(tmp, []))
            header = (out / "validation_INPUT.csv").read_text(encoding="utf-8-sig").splitlines()[0]
            self.assertEqual(header, "query_id,cas_inputs,smiles")
            self.assertEqual(len(read_csv(out / "validation_INPUT.csv")), 112)

    def test_baseline_is_not_modified_and_errors_block_freeze(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            sheet = tmp / "b" / "sheet.csv"
            # same CAS as a baseline case -> duplicate; and a gold that contradicts an exact catalog CAS
            baseline_cas = read_csv(ROOT / "data/retrieval_INPUT.csv")[0]["cas_inputs"]
            write_sheet(sheet, [
                dict(case_id="D-1", cas_inputs=baseline_cas, source_category="GENERAL_CHEMICAL",
                     human_gold_target_id="NOT_FOUND", human_legal_basis="x", human_review_status="ADJUDICATED"),
                dict(case_id="D-2", cas_inputs="110-85-0", source_category="PARENT_SALT", smiles="C1CNCCN1",
                     human_gold_target_id="NOT_FOUND", human_legal_basis="x", human_review_status="ADJUDICATED"),
            ])
            before = bvd.sha256(ROOT / "data/retrieval_GOLD.csv")
            report, out = bvd.build(self.args(tmp, [str(sheet)], freeze=True))
            self.assertEqual(bvd.sha256(ROOT / "data/retrieval_GOLD.csv"), before)
            joined = " ".join(report["errors"])
            self.assertIn("DUPLICATE_CAS_SET", joined)
            self.assertIn("GOLD_DIFFERS_FROM_EXACT_CATALOG_CAS", joined)
            self.assertFalse(report["frozen"])
            self.assertFalse((out / "VALIDATION_DATASET_FREEZE.json").exists())

    def test_mixture_set_gold_must_match_catalog(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            sheet = tmp / "b" / "sheet.csv"
            # a catalog component set that is not part of the baseline: 8-/7-cyclohexadecen-1-one is, so use a made-up gold
            comp = "3100-36-5|2550-59-6"
            write_sheet(sheet, [dict(case_id="M-1", cas_inputs=comp, source_category="MIXTURE",
                                     human_gold_target_id="NOT_FOUND", human_legal_basis="x",
                                     human_review_status="ADJUDICATED")])
            report, _ = bvd.build(self.args(tmp, [str(sheet)]))
            joined = " ".join(report["errors"])
            self.assertIn("DUPLICATE_CAS_SET", joined)  # already a baseline mixture
            self.assertIn("GOLD_DIFFERS_FROM_CATALOG_MIXTURE_SET", joined)

    def test_unverified_legal_basis_blocks_freeze(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            sheet = tmp / "sheet.csv"
            write_sheet(sheet, [dict(case_id="T-1", cas_inputs="506-26-3",
                                     source_category="GENERAL_CHEMICAL",
                                     human_gold_target_id="NOT_FOUND",
                                     human_legal_basis="초안, 고시 원문 대조 필요",
                                     human_review_status="ADJUDICATED")])
            report, out = bvd.build(self.args(tmp, [str(sheet)], freeze=True))
            self.assertEqual(report["n_legal_basis_pending"], 1)
            self.assertFalse(report["frozen"])
            self.assertIn("UNVERIFIED_LEGAL_BASIS T-1", report["errors"])
            self.assertFalse((out / "VALIDATION_DATASET_FREEZE.json").exists())

    def test_exact_catalog_overlap_must_include_all_ids(self):
        catalog = pre.load_catalog(ROOT / "data/regulatory_catalog.csv")
        row = dict(query_id="RQ-9999", cas_inputs="12656-85-8",
                   gold_target_id="CG::CRVI_COMPOUNDS", origin="NEW_ADJUDICATED",
                   smiles="")
        errors, _ = bvd.run_checks([row], catalog)
        self.assertTrue(any("GOLD_DIFFERS_FROM_EXACT_CATALOG_CAS" in x for x in errors))

    def test_source_registry_requires_signoff(self):
        with tempfile.TemporaryDirectory() as d:
            catalog_ids = set(pre.load_catalog(ROOT / "data/regulatory_catalog.csv"))
            pending = bvd.catalog_source_pending(Path(d) / "absent.csv", catalog_ids)
            self.assertEqual(len(pending), 29)


    def test_two_independent_reviewers_must_match_gold_and_have_sources(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            files = [tmp / "r1.csv", tmp / "r2.csv"]
            fields = ["case_id", "reviewer_id", "reviewed_on", "reviewed_target_id",
                      "official_legal_source", "chemical_identity_source", "decision"]
            for i, filename in enumerate(files, 1):
                with filename.open("w", encoding="utf-8", newline="") as handle:
                    w = csv.DictWriter(handle, fieldnames=fields)
                    w.writeheader()
                    w.writerow({
                        "case_id": "T-1", "reviewer_id": f"expert-{i}",
                        "reviewed_on": "2026-11-17", "reviewed_target_id": "NOT_FOUND",
                        "official_legal_source": "notice-reference",
                        "chemical_identity_source": "identity-reference",
                        "decision": "CONFIRMED",
                    })
            included = [{"case_id": "T-1", "human_gold_target_id": "NOT_FOUND"}]
            self.assertEqual(bvd.independent_review_issues(included, *files), [])
            with files[1].open("w", encoding="utf-8", newline="") as handle:
                w = csv.DictWriter(handle, fieldnames=fields)
                w.writeheader()
                w.writerow({"case_id": "T-1", "reviewer_id": "expert-1",
                            "reviewed_on": "2026-11-17", "reviewed_target_id": "CG::MG_SALTS",
                            "official_legal_source": "notice-reference",
                            "chemical_identity_source": "identity-reference",
                            "decision": "CONFIRMED"})
            issues = " ".join(bvd.independent_review_issues(included, *files))
            self.assertIn("REVIEW_TARGET_DISAGREEMENT_2", issues)
            self.assertIn("REVIEWERS_NOT_INDEPENDENT", issues)

    def test_freeze_writes_manifest_when_clean(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            registry = tmp / "catalog_source_registry.csv"
            with registry.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["target_id", "verification_status", "verified_by", "verified_on", "verification_notes"])
                writer.writeheader()
                for target in read_csv(ROOT / "data/regulatory_catalog.csv"):
                    writer.writerow({"target_id": target["target_id"], "verification_status": "VERIFIED",
                                     "verified_by": "test-fixture", "verified_on": "2026-11-17",
                                     "verification_notes": "synthetic test fixture; not a real legal source"})
            report, out = bvd.build(self.args(tmp, [], freeze=True))
            self.assertTrue(report["frozen"])
            manifest = json.loads((out / "VALIDATION_DATASET_FREEZE.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["n_total"], 112)
            self.assertIn("validation_GOLD.csv", manifest["file_sha256"])


if __name__ == "__main__":
    unittest.main()
