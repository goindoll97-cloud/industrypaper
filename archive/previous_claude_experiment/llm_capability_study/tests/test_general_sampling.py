# -*- coding: utf-8 -*-
"""Pure offline tests for the independent PubChem selection frame."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from independent_pubchem_sources import collect_general, independent_names
from collect_pubchem_candidates import valid_cas, from_synonyms


class FakePubChem:
    def __init__(self):
        self.calls = []

    def cids_for_name(self, value):
        self.calls.append(("name", value))
        if value.lower() == "ethanol":
            return [101]
        if value == "64-17-5":
            return [101]
        return []

    def properties(self, cid):
        self.calls.append(("properties", cid))
        return {"title": "Ethanol", "smiles": "CCO"} if cid == 101 else {}

    def synonyms(self, cid):
        self.calls.append(("synonyms", cid))
        return ["64-17-5", "ethanol"] if cid == 101 else []


class TestGeneralDiscovery(unittest.TestCase):
    def test_cas_checksum(self):
        self.assertEqual(valid_cas("64-17-5"), "64-17-5")
        self.assertEqual(valid_cas("64-17-4"), "")
        self.assertEqual(from_synonyms(["water", "64-17-5", "64-17-4"]), ["64-17-5"])

    def test_general_names_are_interleaved(self):
        names = list(independent_names())
        self.assertEqual(names[:2], ["ethanol", "D-glucose"])
        self.assertGreater(len(names), 100)

    def test_general_named_candidate_without_catalog_seed(self):
        fake = FakePubChem()
        added = []
        args = SimpleNamespace(
            general_name_share=1.0, random_seed=20261117,
            random_cid_min=1, random_cid_max=100, random_cid_probes=0,
        )

        def add(cas, category, method, target, **kwargs):
            added.append((cas, category, method, target, kwargs))
            return True

        out = collect_general(fake, add, from_synonyms, args, set(), 1)
        self.assertEqual(out["collected"], 1)
        self.assertEqual(added[0][0], "64-17-5")
        self.assertEqual(added[0][1], "GENERAL_CHEMICAL")
        self.assertEqual(added[0][2], "PUBCHEM_GENERAL_NAME")
        self.assertEqual(added[0][3], "")
        self.assertEqual(added[0][4]["qc"], "CAS_CID_RECIPROCAL_PUG_REST")

    def test_reserved_cid_is_not_accepted(self):
        fake = FakePubChem()
        collected = []
        args = SimpleNamespace(
            general_name_share=1.0, random_seed=42,
            random_cid_min=101, random_cid_max=101, random_cid_probes=1,
        )
        result = collect_general(fake, lambda *a, **k: collected.append(a) or True,
                                 from_synonyms, args, {"101"}, 1)
        self.assertEqual(result["collected"], 0)
        self.assertEqual(collected, [])

    def test_seeded_cid_probe_reproducible_and_distinct(self):
        class RandomPubChem(FakePubChem):
            def properties(self, cid):
                return {"title": "Ethanol", "smiles": "CCO"} if cid == 101 else {}
            def synonyms(self, cid):
                return ["64-17-5"] if cid == 101 else []
            def cids_for_name(self, value):
                return [101] if value == "64-17-5" else []

        args = SimpleNamespace(
            general_name_share=0.0, random_seed=25,
            random_cid_min=101, random_cid_max=101, random_cid_probes=1,
        )
        result = []
        summary = collect_general(
            RandomPubChem(),
            lambda *a, **k: result.append((a, k)) or True,
            from_synonyms, args, set(), 1)
        self.assertEqual(summary["collected"], 1)
        self.assertEqual(result[0][0][2], "PUBCHEM_RANDOM_CID_PROBE")
        self.assertEqual(result[0][0][3], "")
        self.assertEqual(result[0][1]["seed"], "SEED=25;RANGE=101-101")


if __name__ == "__main__":
    unittest.main()
