import sys,unittest,sqlite3,json,tempfile
from pathlib import Path
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from build_legal_db import build,DB,ROOT
from search_legal_db import search,fused_search,evidence
from run_retrieval import parse_queries,parse_answer,identity,reason_messages,query_messages
import run_retrieval as runner

class PipelineTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):build()
 def test_full_annex(self):
  with sqlite3.connect(DB) as c:
   self.assertEqual(c.execute('SELECT count(*) FROM annex').fetchone()[0],1451)
   self.assertEqual(c.execute('SELECT count(*) FROM annex WHERE parent_designation_id="97-1-156"').fetchone()[0],1)
 def test_CAS_direct(self):
  with sqlite3.connect(DB) as c:
   c.row_factory=sqlite3.Row
   hits=search(c,'7761-88-8',8)
   self.assertEqual(int(hits[0]['excel_row']),121)
 def test_group_search(self):
  with sqlite3.connect(DB) as c:
   c.row_factory=sqlite3.Row
   hits,_=fused_search(c,['aniline'],8)
   self.assertTrue(any(r['parent_designation_id']=='97-1-156' for r in hits))
   hits,_=fused_search(c,['니코틴'],8)
   self.assertTrue(any(r['parent_designation_id']=='97-1-11' for r in hits))
 def test_queries_parse(self):
  self.assertEqual(parse_queries('{"queries":["aniline","aniline","염류"]}'),['aniline','염류'])
  self.assertIsNone(parse_queries('{"queries":[]}'))
 def test_prompt_no_choices_no_gold(self):
  c=json.loads((ROOT/'data/cases_48.jsonl').read_text(encoding='utf-8').splitlines()[0])
  texts=str(query_messages(c))
  self.assertNotIn('97-1-156',texts)
  self.assertNotIn('16개',texts)
  self.assertNotIn('expected_relation',texts)
  self.assertIn('CAS:',texts)
  self.assertNotIn('97-1-156',str(reason_messages(c,[])))
 def test_stubbed_end_to_end_no_gold(self):
  cases=runner.load(ROOT/'data/cases_48.jsonl')
  pilot=set(json.loads((ROOT/'data/pilot_8_ids.json').read_text(encoding='utf-8')))
  case=next(c for c in cases if c['test_id'] in pilot)
  calls=[]
  def fake_request(base,endpoint,payload=None,timeout=180):
   if endpoint=='/api/tags':return {'models':[{'name':'qwen2.5:3b','digest':'test-digest'}]}
   if endpoint=='/api/generate':return {}
   raise AssertionError(endpoint)
  def fake_infer(base,model,messages,schema,num_predict,num_ctx,seed,timeout):
   calls.append(messages)
   if len(calls)==1:return {'message':{'content':'{"queries":["무기시안화합물"]}'},'eval_count':35},0.01
   answer={'test_id':case['test_id'],'direct_cas_match':False,'covered_by_clause':False,
    'reasoning_category':'INSUFFICIENT_EVIDENCE','relevant_entry_id':None,'relevant_sub_number':None,
    'reason_ko':'관련 근거 불충분'}
   return {'message':{'content':json.dumps(answer,ensure_ascii=False)},'eval_count':60},0.01
  with tempfile.TemporaryDirectory() as temporary:
   with mock.patch.object(runner,'request',side_effect=fake_request), \
        mock.patch.object(runner,'infer',side_effect=fake_infer), \
        mock.patch.object(runner,'OUT',Path(temporary)):
    runner.main(['--stage','pilot','--model','qwen2.5:3b','--limit','1'])
    rows=runner.load(Path(temporary)/'qwen2.5_3b__pilot.jsonl')
   self.assertEqual(rows[0]['status'],'ok')
   self.assertEqual(len(calls),2)
   self.assertGreaterEqual(len(rows[0]['retrieved_rows']),1)
   self.assertNotIn('97-1-156',str(calls[0]))
 def test_json_answer(self):
  r={'test_id':'T','direct_cas_match':False,'covered_by_clause':True,'reasoning_category':'GROUP_INCLUDED','relevant_entry_id':'97-1-156','relevant_sub_number':None,'reason_ko':'맞음'}
  self.assertIsNotNone(parse_answer(json.dumps(r,ensure_ascii=False),'T'))

if __name__=='__main__':unittest.main()
