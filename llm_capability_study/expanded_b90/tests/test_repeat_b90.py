"""Offline end-to-end repeated execution/scoring with fake Ollama responses.

Synthetic labels are used only in the temporary test directory. No real
Gold or model results are checked into this test.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
import repeat_b90 as rb


def csv_rows(path):
    with path.open(encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))


class RepeatTests(unittest.TestCase):
    def test_same_structured_answer_excludes_free_text(self):
        case={"test_id":"S-01-B","group":"PARENT_AND_SALTS",
              "components":[{"component_id":"C1"}]}
        a={"test_id":"S-01-B","components":[dict(component_id="C1",
              direct_cas_match=True,covered_by_clause=True,
              reasoning_category="DIRECT_SPECIFIC",relevant_entry_id="97-1-80",
              relevant_sub_number=None)],"all_components_designated":None,
              "reason_ko":"first"}
        sig=lambda x:rb.signature({"answer_raw":json.dumps(x)},case)
        first=sig(a)
        self.assertIsNotNone(first)
        a["reason_ko"]="second"
        self.assertEqual(first,sig(a))
        a["components"][0]["direct_cas_match"]=False
        self.assertNotEqual(first,sig(a))
        self.assertIsNone(rb.signature({"answer_raw":"invalid"},case))

    def test_full_repeat_resume_and_scoring(self):
        cases=rb.load(HERE/"proposals"/"PROPOSED_90_B_cases.jsonl")
        self.assertEqual(len(cases),90)
        ids={x["test_id"]:x for x in cases}
        gold=[]
        for c in cases:
            comps=[dict(component_id=z["component_id"],cas=z["cas"],
                source_excel_row=102,expected_relation="DIRECT_SPECIFIC",
                direct_cas_match=True,covered_by_clause=True,
                relevant_entry_id="97-1-80",relevant_sub_number=None)
                   for z in c["components"]]
            gold.append(dict(test_id=c["test_id"],case_id=c["case_id"],
                condition="B",group=c["group"],difficulty=c["difficulty"],
                component_gold=comps,mixture_article3_all_listed=(
                    True if c["group"]=="MIXTURE" else None),
                review_status="CURATED_PROVISIONAL",
                independent_expert_review_completed=False))
        frozen=dict(cases_sha256="a"*64,annex_sha256="b"*64,
                    gold_sha256="c"*64,review_status="CURATED_PROVISIONAL")
        calls=[]
        def fake_infer(base,model,messages,schema,tokens,ctx,seed,timeout):
            tid=messages[1]["content"].splitlines()[0].split(": ")[1]
            case=ids[tid]
            cids=[x["component_id"] for x in case["components"]]
            calls.append((model,tid))
            self.assertEqual(seed,20261120)
            self.assertEqual(ctx,4096)
            if schema==rb.QUERY_SCHEMA:
                ans={"searches":[dict(component_id=cid,queries=["synthetic"])
                                 for cid in cids]}
            else:
                ans=dict(test_id=tid,components=[dict(component_id=cid,
                    direct_cas_match=True,covered_by_clause=True,
                    reasoning_category="DIRECT_SPECIFIC",relevant_entry_id="97-1-80",
                    relevant_sub_number=None) for cid in cids],
                    all_components_designated=True if case["group"]=="MIXTURE" else None,
                    reason_ko="synthetic test")
            return {"message":{"content":json.dumps(ans)},"total_duration":100,
                    "load_duration":10,"eval_duration":20,"eval_count":5},0.001
        def fake_assert(need_gold=False):
            return (cases,gold,frozen) if need_gold else (cases,frozen)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"results"
            args=argparse.Namespace(out_dir=str(root),repeats=2,model="all",
                                  endpoint="http://test.invalid",limit=2)
            with patch.object(rb,"assert_provisional",side_effect=fake_assert), \
                 patch.object(rb,"environment",return_value=(
                     {m:"digest-"+m for m in rb.ALL_MODELS},{"ollama":"test"})), \
                 patch.object(rb,"build"), \
                 patch.object(rb,"DB",Path(tmp)/"test.sqlite"), \
                 patch.object(rb,"unload"), \
                 patch.object(rb,"infer",side_effect=fake_infer), \
                 patch.object(rb,"fused_search",return_value=([],{})), \
                 patch("builtins.print"):
                rb.run(args)
                self.assertEqual(len(calls),2*2*4*2)
                args.limit=None
                rb.run(args)
                self.assertEqual(len(calls),2*90*4*2)
                rb.run(args)
                self.assertEqual(len(calls),2*90*4*2)
                rb.score(args)
                out=root/"analysis"
                runs=csv_rows(out/"REPEAT_per_run_PRIVATE.csv")
                models=csv_rows(out/"REPEAT_model_summary_PRIVATE.csv")
                cs=csv_rows(out/"REPEAT_case_scores_PRIVATE.csv")
                co=csv_rows(out/"REPEAT_component_scores_PRIVATE.csv")
                agree=csv_rows(out/"REPEAT_decision_agreement_PRIVATE.csv")
                self.assertEqual(len(runs),8)
                self.assertEqual(len(models),4)
                self.assertEqual(len(cs),720)
                self.assertEqual(len(co),1080)
                self.assertEqual(len(agree),360)
                for row in runs:
                    self.assertEqual(float(row["strict_case_exact_pct"]),100)
                    self.assertEqual(float(row["strict_end_to_end_pct"]),0)
                    self.assertEqual(int(row["cold_first_cases"]),2)
                    self.assertEqual(int(row["block_timing_complete"]),1)
                    self.assertGreaterEqual(float(row["task_seconds_total"]),0)
                for row in models:
                    self.assertEqual(float(row["strict_case_exact_pct_mean_across_repeats"]),100)
                    self.assertEqual(float(row["strict_case_exact_pct_sd_across_repeats"]),0)
                    self.assertEqual(int(row["all_valid_identical_n"]),90)
                # Complete-case resume cannot silently change run settings.
                args.repeats=3
                with self.assertRaisesRegex(ValueError,"변경 감지"):
                    rb.run(args)
                args.repeats=2
                f=rb.raw_path(root,1,rb.ALL_MODELS[0])
                rows=rb.load(f)
                rows[0]["repeat"]=2
                f.write_text("".join(json.dumps(x)+"\n" for x in rows),encoding="utf-8")
                with self.assertRaisesRegex(ValueError,"입력/설정 오류"):
                    rb.score(args)


if __name__=="__main__":
    unittest.main()
