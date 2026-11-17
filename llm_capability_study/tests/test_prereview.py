# -*- coding: utf-8 -*-
"""Offline tests for the candidate pre-review (triage) script."""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import prereview_candidates as pr  # noqa: E402
from collect_pubchem_candidates import read_csv  # noqa: E402

BATCH = HERE / "candidates/_sources/balanced_v2_candidates_for_review.csv"


class TestCatalogLogic(unittest.TestCase):
    def test_component_cas_is_not_exact(self):
        catalog = {"MX::T": {"type": "MIXTURE", "text": "", "reference": set(), "members": set(),
                             "components": {"753-73-1"}, "mixture_cas": {"78643-41-1"}}}
        self.assertEqual(pr.exact_signals("753-73-1", catalog), [("MX::T", "COMPONENT", "MIXTURE_COMPONENT_CAS")])
        self.assertEqual(pr.exact_signals("78643-41-1", catalog)[0][1], "EXACT")

    def test_catalog_warning_detects_scope_text_mismatch(self):
        catalog = {"MX::T": {"type": "MIXTURE", "text": "mix of A(111-11-1) and B(222-22-2)",
                             "reference": set(), "members": set(),
                             "components": {"111-11-1", "222-22-3"}, "mixture_cas": set()}}
        warnings = pr.catalog_warnings(catalog)
        self.assertEqual(warnings[0]["cas_only_in_scope_text"], ["222-22-2"])
        self.assertEqual(warnings[0]["cas_only_in_component_set"], ["222-22-3"])


@unittest.skipUnless(pr.HAVE_RDKIT, "RDKit not installed")
class TestStructureRules(unittest.TestCase):
    def rule(self, target, smiles):
        return pr.group_rule(target, pr.parse(smiles))[0]

    def test_nonylphenol(self):
        self.assertTrue(self.rule("CG::NONYLPHENOL_NPE", "CCCCCCCCCC1=CC=CC=C1O"))
        self.assertFalse(self.rule("CG::NONYLPHENOL_NPE", "CCC(C)(C)C1=CC=C(C=C1)O"))  # pentylphenol

    def test_malachite_green_vs_ethyl_analogue(self):
        mg = "CN(C)C1=CC=C(C=C1)C(=C2C=CC(=[N+](C)C)C=C2)C3=CC=CC=C3.[Cl-]"
        ethyl = mg.replace("N(C)C", "N(CC)CC").replace("[N+](C)C", "[N+](CC)CC")
        leuco = "CN(C)C1=CC=C(C=C1)C(C2=CC=CC=C2)C3=CC=C(C=C3)N(C)C"
        self.assertTrue(self.rule("CG::MG_SALTS", mg))
        self.assertFalse(self.rule("CG::MG_SALTS", ethyl))
        self.assertFalse(self.rule("CG::MG_SALTS", leuco))

    def test_metal_rules(self):
        self.assertTrue(self.rule("CG::TBT_TRIALKYLTIN", "CCCC[Sn](CCCC)(CCCC)Cl"))
        self.assertFalse(self.rule("CG::TBT_TRIALKYLTIN", "C[Sn](C)(Cl)Cl"))
        self.assertTrue(self.rule("CG::CRVI_COMPOUNDS", "[O-][Cr](=O)(=O)[O-].[Na+].[Na+]"))
        self.assertFalse(self.rule("CG::CRVI_COMPOUNDS", "Cl[Cr](Cl)Cl"))
        self.assertTrue(self.rule("CG::LEAD_COMPOUNDS", "[Pb]"))

    def test_carbonate_is_not_organic(self):
        frag = pr.fragments(pr.parse("C(=O)(O)[O-].[Na+]"))
        self.assertFalse(any(pr.is_organic(f) for f in frag))
        self.assertTrue(pr.is_organic(pr.parse("C(=N)(N)N")))  # guanidine

    def test_ionic_and_covalent_lead_nitrate_share_key(self):
        ionic = pr.parse("[N+](=O)([O-])[O-].[N+](=O)([O-])[O-].[Pb+2]")
        covalent = pr.parse("[N+](=O)([O-])O[Pb]O[N+](=O)[O-]")
        self.assertEqual(pr.structure_key(ionic), pr.structure_key(covalent))

    def test_hydrate_water_is_ignored(self):
        self.assertEqual(pr.structure_key(pr.parse("[O-][Cr](=O)(=O)[O-].[Na+].[Na+]")),
                         pr.structure_key(pr.parse("O.O.O.[O-][Cr](=O)(=O)[O-].[Na+].[Na+]")))


@unittest.skipUnless(pr.HAVE_RDKIT and BATCH.is_file(), "RDKit or committed batch missing")
class TestBatchEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rows = read_csv(BATCH)
        cls.results, cls.hits, cls.summary = pr.run(
            rows, ROOT / "data/regulatory_catalog.csv", ROOT / "data/retrieval_INPUT.csv",
            ROOT / "intermediate/shared_pubchem_smiles.csv")
        cls.by_id = {r["case_id"]: r for r in cls.results}

    def test_no_gold_is_assigned(self):
        self.assertEqual(len(self.results), 87)
        for r in self.results:
            self.assertEqual(r["gold_status"], "REVIEW_PENDING")
            self.assertEqual(r["gold_target_id"], "")
            self.assertEqual(r["auto_is_final_gold"], "NO")
            self.assertEqual(r["legal_basis_verification_required"], "YES")
        self.assertEqual(self.summary["gold_labels_assigned"], 0)

    def test_known_cases(self):
        self.assertEqual(self.by_id["NEW-0001"]["auto_prereview_class"], "EXACT_CAS_MATCH")
        self.assertEqual(self.by_id["NEW-0021"]["auto_prereview_class"], "POSSIBLE_OUT_OF_SCOPE")  # ethanol
        self.assertEqual(self.by_id["NEW-0061"]["auto_prereview_class"], "POSSIBLE_PARENT_SALT")
        self.assertEqual(self.by_id["NEW-0073"]["auto_prereview_class"], "POSSIBLE_GROUP_MEMBER")
        self.assertEqual(self.by_id["NEW-0084"]["auto_prereview_class"], "AMBIGUOUS")
        self.assertIn("DUPLICATE_STRUCTURE_OF_CANDIDATE:NEW-0004", self.by_id["NEW-0074"]["auto_flags"])

    def test_catalog_typo_is_reported(self):
        ids = [w["target_id"] for w in self.summary["catalog_warnings"]]
        self.assertIn("MX::97-1-127", ids)


BOUNDARY = HERE / "candidates/_sources/boundary_v1_candidates_from_prereview.csv"


@unittest.skipUnless(pr.HAVE_RDKIT and BOUNDARY.is_file(), "RDKit or committed boundary batch missing")
class TestBoundaryBatchPriority(unittest.TestCase):
    def test_unconfirmed_hint_alone_does_not_raise_priority(self):
        results, _, summary = pr.run(read_csv(BOUNDARY), ROOT / "data/regulatory_catalog.csv",
                                     ROOT / "data/retrieval_INPUT.csv",
                                     ROOT / "intermediate/shared_pubchem_smiles.csv")
        by_id = {r["case_id"]: r for r in results}
        self.assertEqual(len(results), 65)
        self.assertEqual(by_id["BND-0001"]["review_priority"], "LOW")    # sodium molybdate
        self.assertEqual(by_id["BND-0003"]["review_priority"], "HIGH")   # dibutyltin dichloride, near neighbour
        self.assertEqual(by_id["BND-0047"]["auto_prereview_class"], "POSSIBLE_GROUP_MEMBER")  # trimethyltin chloride
        self.assertEqual(summary["gold_labels_assigned"], 0)


if __name__ == "__main__":
    unittest.main()
