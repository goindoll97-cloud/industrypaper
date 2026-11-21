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

    def test_proposal_is_complete_90_b_only_but_unverified(self):
        path = HERE/"proposals"/"PROPOSED_90_B_cases.jsonl"
        cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        self.assertTrue(b90.validate_cases(cases))
        original,_=b90.baseline_b()
        lookup={r["test_id"]:r for r in cases}
        self.assertEqual(len(lookup),90)
        for row in original:
            self.assertEqual(lookup[row["test_id"]],row,
                             "Prior 30 B questions must remain literally unchanged")
        proposal=b90.read_csv(HERE/"proposals"/"PROPOSED_new_60_component_review.csv")
        self.assertEqual(len(proposal),90)
        self.assertEqual(len({r["case_id"] for r in proposal}),60)
        self.assertTrue(all(r["cas"] and r["name_en"] and r["formula"]
                            and r["identity_source_url"]
                            and r["identity_verified"]=="NO"
                            for r in proposal))
        self.assertTrue(all(b90.valid_cas(r["cas"]) for r in proposal))
        self.assertEqual(sum(c["group"]=="MIXTURE" for c in cases),30)

    def test_import_proposal_requires_blank_existing_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch.object(b90,"PRIVATE",root/"private"),\
                 patch.object(b90,"DATA",root/"data"):
                b90.init_candidates(b90.PRIVATE/"new_cases_review.csv")
                b90.import_proposals()
                target=b90.PRIVATE/"new_cases_review.csv"
                rows=b90.read_csv(target)
                self.assertEqual(len(rows),90)
                self.assertEqual(rows[0]["identity_verified"],"NO")
                self.assertEqual(sum(x["group"]=="MIXTURE" for x in rows),50)
                with self.assertRaisesRegex(ValueError,"덮어쓰기|입력"):
                    b90.import_proposals()
                with self.assertRaisesRegex(ValueError,"identity_reviewer|독립 확인"):
                    b90.build_cases(target)

    def test_pubchem_composition_is_structural_not_legal(self):
        sys.path.insert(0,str(HERE/"proposals"))
        from check_pubchem import composition
        self.assertEqual(composition("BF4.Na"),composition("BF4Na"))
        self.assertEqual(composition("PbO"),composition("OPb"))
        self.assertIsNone(composition("C6H5+"))

    def test_60_annex_based_new_b_gold_and_explicit_exclusions(self):
        import prepare_provisional_b90 as p90
        data=b90.load(HERE/"proposals"/"PROPOSED_90_B_cases.jsonl")
        annex,legacy=p90.annex_rows()
        candidates=b90.read_csv(HERE/"proposals"/"PROPOSED_new_60_component_review.csv")
        new,flags=p90.derive_new(data,candidates,annex)
        self.assertEqual(len(new),60)
        self.assertEqual(len(flags),90)
        self.assertTrue(all(x["test_id"].endswith("-B") for x in new))
        for row in new:
            self.assertEqual(row["review_status"],"CURATED_PROVISIONAL")
            self.assertFalse(row["independent_expert_review_completed"])
            for comp in row["component_gold"]:
                raw=annex[comp["source_excel_row"]]
                self.assertEqual(comp["relevant_entry_id"],raw["parent_designation_id"])
                self.assertEqual(comp["direct_cas_match"],
                    p90.exact_cas(raw,comp["cas"]))
                self.assertEqual(comp["covered_by_clause"],
                    comp["expected_relation"]!="EXPLICIT_EXCEPTION")
        by_test={c["test_id"]:c for c in new}
        def val(case_id):
            return by_test[case_id]["component_gold"][0]
        self.assertEqual(val("S-28-B")["expected_relation"],"GROUP_INCLUDED")
        self.assertEqual(val("S-28-B")["source_excel_row"],466)
        self.assertEqual(val("S-30-B")["expected_relation"],"EXPLICIT_EXCEPTION")
        self.assertEqual(val("C-28-B")["expected_relation"],"GROUP_INCLUDED")
        for tid in ("C-29-B","M-26-B"):
            fixed=val(tid)
            self.assertEqual(fixed["source_excel_row"],377)
            self.assertEqual(fixed["relevant_sub_number"],2)
            self.assertEqual(fixed["relevant_entry_id"],"97-1-299")
            self.assertEqual(fixed["expected_relation"],"GROUP_INCLUDED")
            self.assertFalse(fixed["direct_cas_match"])
        self.assertFalse(p90.proof_clause(annex[376],"95-70-5","GROUP_INCLUDED"))
        self.assertEqual(val("C-30-B")["expected_relation"],"EXPLICIT_EXCEPTION")
        self.assertEqual(val("M-29-B")["expected_relation"],"EXPLICIT_EXCEPTION")
        self.assertFalse(by_test["M-23-B"]["mixture_article3_all_listed"])
        self.assertTrue(by_test["M-21-B"]["mixture_article3_all_listed"])
        self.assertTrue(all(not r["independent_expert_verified"] for r in flags))

    def test_unreviewed_source_clause_mismatch_refused(self):
        import prepare_provisional_b90 as p90
        original=b90.load(HERE/"proposals"/"PROPOSED_90_B_cases.jsonl")
        rows=b90.read_csv(HERE/"proposals"/"PROPOSED_new_60_component_review.csv")
        row=next(x for x in rows if x["case_id"]=="C-30")
        row["candidate_annex_row"]="120"
        annex,_=p90.annex_rows()
        with self.assertRaisesRegex(ValueError,"검증 실패|고시행이 제안서와 다름"):
            p90.derive_new(original,rows,annex)

    def test_end_to_end_provisional_90_b_gold_using_synthetic_old_gold(self):
        import hashlib
        import prepare_provisional_b90 as p90
        with tempfile.TemporaryDirectory() as tmp:
            temp=Path(tmp)
            old_b,_=b90.baseline_b()
            new_v4=temp/"legacy_v4"
            (new_v4/"private").mkdir(parents=True)
            # Purely synthetic prior labels; never used for any real benchmark.
            mock_gold=[]
            for old in old_b:
                comps=[]
                for z in old["components"]:
                    comps.append({
                        "component_id":z["component_id"],
                        "cas":z["cas"],
                        "source_excel_row":102,
                        "direct_cas_match":False,
                        "covered_by_clause":False,
                        "expected_relation":"EXPLICIT_EXCEPTION",
                        "relevant_entry_id":"97-1-80",
                        "relevant_sub_number":None,
                    })
                record={
                    "test_id":old["test_id"],"case_id":old["case_id"],
                    "condition":"B","group":old["group"],
                    "difficulty":old["difficulty"],
                    "component_gold":comps,
                    "mixture_article3_all_listed":(
                        False if old["group"]=="MIXTURE" else None),
                    "review_status":"CURATED_PROVISIONAL",
                    "independent_expert_review_completed":False,
                }
                mock_gold.append(record)
                mock_gold.append(dict(record,test_id=old["case_id"]+"-A",
                                     condition="A"))
            oldfile=new_v4/"private"/"gold_60.jsonl"
            oldfile.write_text("".join(json.dumps(x)+"\n" for x in mock_gold),
                               encoding="utf-8")
            expected=hashlib.sha256(oldfile.read_bytes()).hexdigest()
            private=temp/"provisional_b90"
            fixture_annex=p90.annex_rows()
            with patch.object(p90,"V4",new_v4),\
                 patch.object(p90,"PRIVATE",private),\
                 patch.object(p90,"GOLD",private/"gold_90_B_PROVISIONAL.jsonl"),\
                 patch.object(p90,"CASES",private/"cases_90_B_PROVISIONAL.jsonl"),\
                 patch.object(p90,"MANIFEST",private/"provisional_manifest.json"),\
                 patch.object(p90,"REVIEW",private/"gold_90_B_review_queue_PROVISIONAL.csv"),\
                 patch.object(p90,"annex_rows",return_value=fixture_annex),\
                 patch("gold_integrity.expected_gold_sha",return_value=expected):
                p90.build_provisional()
                cases,gold,meta=p90.assert_provisional(need_gold=True)
                self.assertEqual(len(cases),90)
                self.assertEqual(len(gold),90)
                self.assertTrue(all(x["condition"]=="B" for x in gold))
                self.assertEqual(sum(len(x["component_gold"]) for x in gold),135)
                self.assertEqual(len(b90.read_csv(p90.REVIEW)),135)
                self.assertEqual(meta["review_status"],"CURATED_PROVISIONAL")
                self.assertFalse(meta["independent_expert_review_completed"])
                self.assertTrue(all(not x["independent_expert_review_completed"]
                                    for x in gold))
                with self.assertRaisesRegex(ValueError,"덮어쓰지"):
                    p90.build_provisional()
                # Simulate a frozen v1 key and a manual researcher update.
                # Use synthetic hashes in tests; production only accepts real
                # researcher-confirmed old/new hashes.
                corrected_bytes=p90.GOLD.read_bytes()
                revised_sha=hashlib.sha256(corrected_bytes).hexdigest()
                for row in gold:
                    for comp in row["component_gold"]:
                        if comp["cas"]=="95-70-5":
                            comp.update(source_excel_row=376,relevant_sub_number=1)
                prior_bytes=p90._canonical_gold(gold)
                prior_sha=hashlib.sha256(prior_bytes).hexdigest()
                review_file=HERE/"proposals"/"PROPOSED_new_60_component_review.csv"
                previous_csv=b"".join(
                    line.replace(b",377,,POTENTIAL_CLASS_OR_EXCEPTION_CLAUSE,",
                                 b",376,,POTENTIAL_CLASS_OR_EXCEPTION_CLAUSE,")
                    if b",95-70-5," in line else line
                    for line in review_file.read_bytes().splitlines(keepends=True))
                meta.pop("gold_revision",None)
                meta["gold_sha256"]=prior_sha
                meta["new_component_review_sha256"]=hashlib.sha256(previous_csv).hexdigest()
                p90.MANIFEST.write_text(json.dumps(meta),encoding="utf-8")
                p90.GOLD.write_bytes(prior_bytes)
                # Corrected existing answer key or original key are both supported.
                with patch.object(p90,"PREVIOUS_GOLD_SHA",prior_sha),\
                     patch.object(p90,"RESEARCHER_GOLD_SHA",revised_sha):
                    p90.apply_researcher_correction()
                    self.assertEqual(p90.GOLD.read_bytes(),corrected_bytes)
                    self.assertEqual((private/"before_row377_correction"/p90.GOLD.name).read_bytes(),
                                     prior_bytes)
                    p90.apply_researcher_correction() # idempotent
                    _,_,revised=p90.assert_provisional(need_gold=True)
                    self.assertEqual(revised["gold_revision"],p90.GOLD_REVISION)
                    self.assertEqual(revised["previous_gold_sha256"],prior_sha)
                    self.assertEqual(revised["gold_sha256"],revised_sha)
                p90.GOLD.write_text("tampered",encoding="utf-8")
                with self.assertRaisesRegex(ValueError,"SHA|해시"):
                    p90.assert_provisional(need_gold=True)

    def test_duplicate_structure_blocks_experiment(self):
        old,_=b90.baseline_b()
        mixed=old+[dict(old[0],test_id="S-99-B",case_id="S-99")]
        with self.assertRaisesRegex(ValueError,"90문항"):
            b90.validate_cases(mixed)


if __name__=="__main__":
    unittest.main()
