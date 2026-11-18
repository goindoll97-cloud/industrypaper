# -*- coding: utf-8 -*-
"""Pure standard-library tests for the legal Gold readiness audit."""
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import audit_gold_readiness as audit  # noqa: E402


class TestGoldAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = audit.read_csv(ROOT / "data/regulatory_catalog.csv")
        cls.index = audit.catalog_index(cls.catalog)

    def test_catalog_component_is_not_a_standalone_mixture_match(self):
        # A named mixture cannot be matched from only one component CAS.
        target = "MX::2020-1-975"
        self.assertNotIn(target, self.index.get("2550-59-6", set()))
        self.assertNotIn(target, self.index.get("3100-36-5", set()))

    def test_synthetic_pair_explicit_components(self):
        sample = {"human_gold_target_id": "CG::CRVI_COMPOUNDS|CG::NONYLPHENOL_NPE",
                  "cas_inputs": "10294-40-3|11066-49-2",
                  "candidate_stratum": "MIXTURE_COLLECTION", "review_priority": "HIGH",
                  "auto_flags": ""}
        priority, kind, hits, _ = audit.classify(sample, self.index)
        self.assertEqual((priority, kind), (4, "EXACT_CAS_POSITIVE"))
        self.assertIn("CG::CRVI_COMPOUNDS", hits)
        self.assertIn("CG::NONYLPHENOL_NPE", hits)

    def test_negative_scope_near_miss(self):
        sample = {"human_gold_target_id": "NOT_FOUND", "cas_inputs": "683-18-1",
                  "candidate_stratum": "BOUNDARY_PROBE", "review_priority": "HIGH",
                  "auto_flags": "NEAR_NEIGHBOR_OF_TARGET:CG::TBT_TRIALKYLTIN"}
        priority, kind, _, _ = audit.classify(sample, self.index)
        self.assertEqual((priority, kind), (2, "NEGATIVE_SCOPE_NEAR_MISS"))

    def test_known_catalog_scope_cas_typo_is_reported(self):
        self.assertFalse(audit.cas_valid("3084-48-0"))
        self.assertTrue(audit.cas_valid("3084-48-8"))

    def test_audit_does_not_change_sheet(self):
        sheet = HERE / "candidates/review_sheet.csv"
        before = sheet.read_bytes()
        with tempfile.TemporaryDirectory() as d:
            report = audit.run(sheet, ROOT / "data/regulatory_catalog.csv", Path(d))
            self.assertEqual(report["candidate_rows"], len(audit.read_csv(sheet)))
            self.assertTrue((Path(d) / "legal_review_queue.csv").is_file())
            self.assertIn({"target_id": "MX::97-1-127", "cas": "3084-48-0"},
                          report["catalog_scope_cas_checksum_invalid"])
        self.assertEqual(before, sheet.read_bytes())


if __name__ == "__main__":
    unittest.main()
