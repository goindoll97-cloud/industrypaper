# -*- coding: utf-8 -*-
"""Offline sanity tests for analysis sampling strata, not a Gold legal signoff."""
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import audit_sampling_design as design
import build_validation_dataset as builder
from types import SimpleNamespace


class TestSamplingDesign(unittest.TestCase):
    def test_family_only_defined_for_found(self):
        self.assertEqual(design.target_families("NOT_FOUND"), "")
        self.assertEqual(design.target_families("CG::MG_SALTS|PS::64-19-7"),
                         "CHEMICAL_GROUP|PARENT_SALT")

    def test_synthetic_mixture_has_independent_provenance(self):
        r = {"query_mode": "COMPONENT_CAS_SET", "origin": "NEW_ADJUDICATED"}
        self.assertEqual(
            design.mixture_provenance(r, {"discovery_method": "MIXTURE_SYNTHETIC_PAIR"}),
            "SYNTHETIC_TWO_COMPONENT_CHALLENGE")

    def test_report_on_real_draft_has_expected_invariants(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            args = SimpleNamespace(
                reviewed=[str(HERE / "candidates/review_sheet.csv")],
                version="ci_unfrozen", out=str(root),
                catalog=str(ROOT / "data/regulatory_catalog.csv"),
                baseline_input=str(ROOT / "data/retrieval_INPUT.csv"),
                baseline_gold=str(ROOT / "data/retrieval_GOLD.csv"),
                smiles=str(ROOT / "intermediate/shared_pubchem_smiles.csv"),
                catalog_source_registry=str(HERE / "candidates/catalog_source_registry.csv"),
                target_min=300, target_max=400, min_per_category=30,
                allow_structure_duplicates=False, freeze=False,
                reviewer1=str(root / "reviewer1.csv"),
                reviewer2=str(root / "reviewer2.csv"),
            )
            composition, out = builder.build(args)
            r = design.analyze(out / "validation_GOLD.csv",
                               out / "validation_METADATA.csv",
                               HERE / "candidates/review_sheet.csv",
                               ROOT / "data/regulatory_catalog.csv",
                               root / "strata")
            self.assertEqual(r["n_total"], composition["n_total"])
            self.assertEqual(r["n_baseline"], 112)
            self.assertEqual(r["n_new"], composition["n_new_included"])
            self.assertEqual(sum(r["gold_counts"].values()), r["n_total"])
            self.assertEqual(len(r["positive_cases_per_target"]), 29)
            self.assertEqual(
                r["mixture_query_provenance"].get("SYNTHETIC_TWO_COMPONENT_CHALLENGE", 0),
                sum(1 for row in design.read_csv(HERE / "candidates/review_sheet.csv")
                    if row["human_review_status"] == "ADJUDICATED"
                    and row["discovery_method"] == "MIXTURE_SYNTHETIC_PAIR"))
            self.assertTrue((root / "strata/evaluation_strata.csv").exists())


if __name__ == "__main__":
    unittest.main()
