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
            csvfile=tmpdir/"new_cases_review.csv"
            data=tmpdir/"data"
            private=tmpdir/"private"
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
                r["regulatory_pattern"]="synthetic fixture tag"
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

    def test_duplicate_structure_blocks_experiment(self):
        old,_=b90.baseline_b()
        mixed=old+[dict(old[0],test_id="S-99-B",case_id="S-99")]
        with self.assertRaisesRegex(ValueError,"90문항"):
            b90.validate_cases(mixed)


if __name__=="__main__":
    unittest.main()
