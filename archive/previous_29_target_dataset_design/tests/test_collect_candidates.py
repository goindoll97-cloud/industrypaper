# -*- coding: utf-8 -*-
"""Offline tests for the unified candidate collector (no network; stages are faked)."""
import csv
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import collect_candidates as cc  # noqa: E402
import collect_mixtures as cm  # noqa: E402
import prereview_candidates as pre  # noqa: E402
from collect_pubchem_candidates import cas_list, read_csv, valid_cas  # noqa: E402

SOURCES = HERE / "candidates" / "_sources"


def make_args(tmp, **kw):
    out = tmp / "candidates"
    shutil.copytree(SOURCES, out / "_sources")
    base = dict(online=False, target_total=300, overshoot=1.2, max_passes=3, out=out,
                stages=tmp / "collection_output" / "_stages", sources=out / "_sources",
                catalog=str(ROOT / "data/regulatory_catalog.csv"),
                baseline=str(ROOT / "data/retrieval_INPUT.csv"),
                smiles=str(ROOT / "intermediate/shared_pubchem_smiles.csv"))
    base.update(kw)
    return SimpleNamespace(**base)


def fake_row(cas, smiles, title, method="PUBCHEM_GENERAL_NAME"):
    return {"case_id": "X-1", "cas_inputs": cas, "smiles": smiles, "pubchem_title_human_only": title,
            "source_category": "GENERAL_CHEMICAL", "candidate_stratum": "INDEPENDENT_GENERAL",
            "discovery_method": method, "gold_status": "REVIEW_PENDING"}


class TestHelpers(unittest.TestCase):
    def test_target_count_includes_baseline_and_margin(self):
        self.assertEqual(cc.target_new_count(300, 112, 1.0), 188)
        self.assertEqual(cc.target_new_count(300, 112, 1.2), 226)
        self.assertEqual(cc.target_new_count(100, 112, 1.2), 0)

    def test_carry_over_keeps_human_input_only(self):
        new = [{"case_id": "CAND-0001", "human_gold_target_id": "", "human_legal_basis": "",
                "human_review_status": "PENDING"}]
        old = [{"case_id": "CAND-0001", "human_gold_target_id": "NOT_FOUND",
                "human_legal_basis": "checked", "human_review_status": "ADJUDICATED"}]
        out = cc.carry_over_human(new, old)
        self.assertEqual(out[0]["human_gold_target_id"], "NOT_FOUND")
        self.assertEqual(out[0]["human_review_status"], "ADJUDICATED")

    @unittest.skipUnless(pre.HAVE_RDKIT, "RDKit not installed")
    def test_dedup_rules(self):
        baseline = read_csv(ROOT / "data/retrieval_INPUT.csv")
        smiles = {r["cas"]: r["smiles"] for r in read_csv(ROOT / "intermediate/shared_pubchem_smiles.csv")}
        d = cc.Dedup(baseline, smiles, catalog_cas={"110-85-0"})
        succ = cc.normalise(fake_row("14047-56-4", "C(CC(=O)[O-])C(=O)[O-].[Na+].[Na+]", "sodium succinate"), "t")
        self.assertTrue(d.check(succ).startswith("SAME_STRUCTURE_AS_BASELINE"))
        self.assertEqual(d.check(cc.normalise(fake_row(baseline[0]["cas_inputs"], "", "x"), "t")), "CAS_IN_BASELINE")
        self.assertEqual(d.check(cc.normalise(fake_row("67-64-1", "CC(C)=O", "acetone"), "t")), "")
        self.assertEqual(d.check(cc.normalise(fake_row("67-64-2", "CC(C)=O", "bad checksum"), "t")),
                         "CAS_CHECKSUM_INVALID")
        # a CAS printed in the frozen catalog is kept even if its structure duplicates a baseline case
        piper = cc.normalise(fake_row("110-85-0", "C1CNCCN1.O.O.O.O.O.O", "piperazine"), "t")
        self.assertEqual(d.check(piper), "")


@unittest.skipUnless(pre.HAVE_RDKIT and SOURCES.is_dir(), "RDKit or committed sources missing")
class TestUnifiedRun(unittest.TestCase):
    def test_offline_import_is_single_folder_and_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            args = make_args(tmp)
            s1 = cc.run(args)
            self.assertEqual(s1["by_source_batch"], {"balanced_v2": 78, "boundary_v1": 65})
            self.assertEqual(s1["pool_size"], 143)
            self.assertEqual(s1["gold_labels_assigned"], 0)
            sheet = read_csv(args.out / "review_sheet.csv")
            self.assertEqual([r["case_id"] for r in sheet][:2], ["CAND-0001", "CAND-0002"])
            self.assertTrue(all(r["gold_status"] == "REVIEW_PENDING" and r["gold_target_id"] == "" for r in sheet))
            s2 = cc.run(args)
            self.assertEqual(s2["pool_size"], 143)
            self.assertEqual(sorted(p.name for p in args.out.iterdir()),
                             ["_sources", "review_sheet.csv", "summary.json"])

    def test_human_columns_survive_a_rerun(self):
        with tempfile.TemporaryDirectory() as d:
            args = make_args(Path(d))
            cc.run(args)
            sheet = read_csv(args.out / "review_sheet.csv")
            sheet[5]["human_gold_target_id"] = "NOT_FOUND"
            sheet[5]["human_legal_basis"] = "manual check"
            sheet[5]["human_review_status"] = "ADJUDICATED"
            cc.write_csv(args.out / "review_sheet.csv", sheet, cc.SHEET_FIELDS)
            s = cc.run(args)
            again = read_csv(args.out / "review_sheet.csv")
            self.assertEqual(again[5]["human_review_status"], "ADJUDICATED")
            self.assertEqual(s["rows_with_reviewer_input"], 1)

    def test_online_top_up_continues_ids_and_stops_at_target(self):
        calls = []
        orig_a, orig_b = cc.stage_a, cc.stage_b

        def fake_b(args, pool_csv, need):
            calls.append(("B", need))
            return [fake_row("67-64-1", "CC(C)=O", "acetone", "PUBCHEM_BOUNDARY_NAME")], args.stages

        def fake_a(args, pool_csv, need, pass_no):
            calls.append(("A", need, pass_no))
            return [fake_row("75-09-2", "ClCCl", "dichloromethane")]

        cc.stage_a, cc.stage_b = fake_a, fake_b
        try:
            with tempfile.TemporaryDirectory() as d:
                tmp = Path(d)
                # need = 144 - 143 = 1 -> one pass adds up to 1 boundary row, then stops (no stage A)
                args = make_args(tmp, online=True, target_total=112 + 144, overshoot=1.0)
                s = cc.run(args)
                self.assertEqual(s["pool_size"], 144)
                self.assertEqual([c[0] for c in calls], ["B"])
                ids = [r["case_id"] for r in read_csv(args.out / "review_sheet.csv")]
                self.assertEqual(ids[-1], "CAND-0144")
                # target already met -> no further stage calls
                calls.clear()
                cc.run(args)
                self.assertEqual(calls, [])
        finally:
            cc.stage_a, cc.stage_b = orig_a, orig_b

    def test_online_stops_when_nothing_new_is_available(self):
        orig_a, orig_b = cc.stage_a, cc.stage_b
        cc.stage_b = lambda args, pool_csv, need: ([], args.stages)
        cc.stage_a = lambda args, pool_csv, need, pass_no: []
        try:
            with tempfile.TemporaryDirectory() as d:
                args = make_args(Path(d), online=True)
                s = cc.run(args)
                self.assertEqual(len(s["collection_passes"]), 1)
                self.assertGreater(s["shortfall_candidate_rows"], 0)
        finally:
            cc.stage_a, cc.stage_b = orig_a, orig_b


@unittest.skipUnless(pre.HAVE_RDKIT and SOURCES.is_dir(), "RDKit or committed sources missing")
class TestMixtures(unittest.TestCase):
    def test_input_csv_flow(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            args = make_args(tmp)
            cc.run(args)
            n0 = len(read_csv(args.out / "review_sheet.csv"))
            inp = tmp / "m.csv"
            inp.write_text("mixture_name,component_cas,source\n"
                           "acetone+methanol,67-64-1|67-56-1,official list\n"
                           "dup of baseline,1027326-93-7|31775-89-0,x\n"
                           "bad checksum,67-64-2|67-56-1,x\n"
                           "single,67-64-1,x\n"
                           "partial of catalog,35184-08-8|67-64-1,x\n", encoding="utf-8")
            margs = SimpleNamespace(**{**vars(args), "input": str(inp)})
            rep = cm.collect(margs)
            self.assertEqual(rep["rows_added"], 2)
            self.assertEqual({d["reason"] for d in rep["dropped"]}, {"MIXTURE_IN_BASELINE", "CAS_CHECKSUM_INVALID"})
            self.assertEqual(len(rep["input_problems"]), 1)
            sheet = read_csv(args.out / "review_sheet.csv")
            self.assertEqual(len(sheet), n0 + 2)
            by = {r["cas_inputs"]: r for r in sheet}
            self.assertEqual(by["67-56-1|67-64-1"]["auto_prereview_class"], "POSSIBLE_OUT_OF_SCOPE")
            self.assertEqual(by["35184-08-8|67-64-1"]["auto_prereview_class"], "AMBIGUOUS")
            self.assertEqual(by["67-56-1|67-64-1"]["gold_target_id"], "")
            self.assertEqual(by["67-56-1|67-64-1"]["human_review_status"], "PENDING")
            # rerun is idempotent: same component set is not added twice
            self.assertEqual(cm.collect(margs)["rows_added"], 0)

    def test_builtin_list_is_clean(self):
        baseline = {tuple(sorted(cas_list(r["cas_inputs"]))) for r in read_csv(ROOT / "data/retrieval_INPUT.csv")}
        catalog = pre.load_catalog(ROOT / "data/regulatory_catalog.csv")
        seen = set()
        for name, cas, source in cm.OFFICIAL_MIXTURES:
            parts = cas_list(cas)
            sig = tuple(sorted(parts))
            self.assertGreaterEqual(len(parts), 2, name)
            self.assertTrue(all(valid_cas(c) for c in parts), name)
            self.assertNotIn(sig, baseline, name)
            self.assertNotIn(sig, seen, name)
            seen.add(sig)
            self.assertTrue(source, name)
            for t in catalog.values():  # outside the 29 targets: no overlap with any catalog CAS
                self.assertFalse(set(parts) & (t["reference"] | t["members"] | t["components"] | t["mixture_cas"]), name)

    def test_name_resolution_needs_unique_cas(self):
        base = {"scope_text": "Mixture of A and B", "pubchem_title": "", "pubchem_smiles": "", "status": ""}
        resolved = [
            {**base, "target_id": "MX::T1", "component_name": "A", "pubchem_cid": "1", "cas_candidates": "50-00-0"},
            {**base, "target_id": "MX::T1", "component_name": "B", "pubchem_cid": "2", "cas_candidates": "67-56-1"},
            {**base, "target_id": "MX::T2", "component_name": "A", "pubchem_cid": "3", "cas_candidates": "64-17-5"},
            {**base, "target_id": "MX::T2", "component_name": "B", "pubchem_cid": "4", "cas_candidates": "67-64-1|75-07-0"},
        ]
        rows, unresolved = cm.rows_from_resolution(resolved)
        self.assertEqual([r["cas_inputs"] for r in rows], ["50-00-0|67-56-1"])
        self.assertEqual(rows[0]["suggested_target_ids_human_only"], "MX::T1")
        self.assertEqual(unresolved[0]["target_id"], "MX::T2")


if __name__ == "__main__":
    unittest.main()
