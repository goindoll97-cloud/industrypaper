"""Offline regression: public legacy B cases and synthetic-only draft fixtures."""
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
import prepare_b90 as b90


def valid_cas_for(n):
    digits=str(100000+n)
    check=sum((i+1)*int(x) for i,x in enumerate(reversed(digits)))%10
    return f"{digits[:4]}-{digits[4:]}-{check}"


class ExpansionTests(unittest.TestCase):
    def test_legacy_30_b_unchanged_and_no_smiles(self):
        old, m=b90.baseline_b()
        self.assertEqual(len(old),30)
        self.assertEqual(len({x["test_id"] for x in old}),30)
        self.assertTrue(all(x["test_id"].endswith("-B") for x in old))
        self.assertTrue(all(all(x["formula"] and x["smiles"] is None
                                for x in c["components"]) for c in old))

    def test_new_slot_quotas_and_no_fabricated_chemical_entries(self):
        rows=b90.slots()
        self.assertEqual(len(rows),90)
        ids={r["case_id"] for r in rows}
        self.assertEqual(len(ids),60)
        from collections import Counter
        dist=Counter((r["group"],r["difficulty"])
                     for r in rows if r["component_id"]=="C1")
        self.assertEqual(set(dist.values()),{10})
        for row in rows:
            self.assertEqual(row["cas"],"")
            self.assertEqual(row["formula"],"")
            self.assertEqual(row["identity_verified"],"")
        self.assertEqual(len({r["case_id"] for r in rows
                              if r["group"]=="MIXTURE" and r["component_id"]=="C3"}),10)

    def test_build_refuses_missing_chemistry_and_preserves_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"draft.csv"
            b90.init_candidates(path)
            with self.assertRaisesRegex(ValueError,"/cas"):
                b90.build_cases(path)
            self.assertTrue(path.exists())
            with self.assertRaisesRegex(ValueError,"덮어쓰지"):
                b90.init_candidates(path)

    def test_synthetic_validated_90_and_freeze_block_until_expert_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir=Path(tmp)
            data=tmpdir/"data"
            private=tmpdir/"private"
            csvfile=private/"new_cases_review.csv"
            records=b90.slots()
            for j,r in enumerate(records):
                r["cas"]=valid_cas_for(j+1)
                r["name_en"]="UNIT TEST SYNTHETIC "+str(j)
                r["formula"]="C2H6"
                r["mass_percent"]=("50" if r["group"]=="MIXTURE"
                   and r["difficulty"]=="EASY" else
                   ("34" if r["component_id"]=="C1" else "33")
                   if r["group"]=="MIXTURE" else "")
                r["identity_source_url"]="https://example.invalid/fixture"
                r["identity_reviewer"]="synthetic_only"
                r["identity_verified"]="YES"
                r["selection_rationale"]="pre-registered fixture"
                r["difficulty_rationale"]="synthetic difficulty fixture"
                r["regulatory_pattern"]=sorted(b90.PATTERNS[r["group"]])[int(r["case_id"].split("-")[1])%2]
            b90.write_csv(csvfile,b90.CANDIDATE_COLS,records)
            with patch.object(b90,"DATA",data),patch.object(b90,"PRIVATE",private):
                casepath=b90.build_cases(csvfile)
                new=b90.load(casepath)
                self.assertEqual(len(new),90)
                b90.validate_cases(new)
                old,_=b90.baseline_b()
                original_by_id={x["test_id"]:x for x in new}
                for x in old:
                    self.assertEqual(original_by_id[x["test_id"]],x)
                self.assertEqual(sum(len(c["components"]) for c in new),135)
                b90.init_gold()
                gold=b90.read_csv(private/"gold_review_90_B.csv")
                self.assertEqual(len(gold),135)
                self.assertTrue(all(x["independent_legal_reviewed"]=="NO"
                                    for x in gold))
                with self.assertRaisesRegex(ValueError,"독립 전문가 검토"):
                    b90.freeze()
                self.assertFalse((private/"frozen_manifest.json").exists())
                with self.assertRaisesRegex(ValueError,"--freeze"):
                    b90.assert_frozen()
                with self.assertRaisesRegex(ValueError,"덮어쓰기"):
                    b90.build_cases(csvfile)

    def test_cas_check_digit(self):
        self.assertTrue(b90.valid_cas("65-30-5"))
        self.assertFalse(b90.valid_cas("65-30-4"))
        self.assertFalse(b90.valid_cas("fake-cas"))

    def test_paired_scoring_uses_same_90_questions_not_independent_totals(self):
        from score_b90 import ALL_MODELS, METRICS, paired, build_report
        cases=[]
        comps=[]
        cons=[]
        info={}
        for model in ALL_MODELS:
            info[model]={"file_sha256":"a"*64, "settings_sha256":"b"*64}
            cons.append({
                "model":model,"group":"ALL","difficulty":"ALL",
                "relation_scope_contradiction_n":0,
                "relation_scope_checkable_n":90})
            for i in range(90):
                rec={"model":model,"test_id":f"C-{i+1:02d}-B",
                     "case_id":f"C-{i+1:02d}","group":"COMPOUND_CLASS",
                     "difficulty":"EASY" if i%2 else "HARD"}
                for _,field in METRICS:
                    rec[field]=0
                if model=="qwen3.5:4b":
                    rec["strict_end_to_end"]=int(i<15)
                elif model=="qwen3.5:9b":
                    rec["strict_end_to_end"]=int(i<10 or 20<=i<25)
                cases.append(rec)
                comps.append({"model":model,"test_id":rec["test_id"],
                    "component_id":"C1",**{key:0 for key in
                     ("strict_gold_row_hit","scope_correct","relation_correct",
                      "direct_cas_correct","entry_correct","sub_number_correct",
                      "component_exact")}})
        self.assertEqual(paired(cases,"strict_end_to_end"),(10,5,5,70))
        report=build_report(cases,comps,cons,info,
                            {"cases_sha256":"1"*64, "gold_sha256":"2"*64})
        self.assertIn("Qwen3.5 9B",report)
        self.assertIn("15/90",report)
        self.assertIn("10",report)

    def test_duplicate_structure_blocks_experiment(self):
        old,_=b90.baseline_b()
        mixed=old+[dict(old[0],test_id="S-99-B",case_id="S-99")]
        with self.assertRaisesRegex(ValueError,"90문항"):
            b90.validate_cases(mixed)


if __name__=="__main__":
    unittest.main()
