import json,sqlite3,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from run_retrieval import parse_queries,parse_answer,QUERY_SCHEMA,ANSWER_SCHEMA
from build_legal_db import build,DB
from search_legal_db import fused_search
build()
with sqlite3.connect(DB) as con:
 con.row_factory=sqlite3.Row
 for q in ['니코틴','아닐린','유기비소','니트로벤젠','메탄올','테트라플루오로붕산']:
  r,_=fused_search(con,[q],k=8)
  assert r,(q,'no search rows')
c={'test_id':'M-06-B','components':[{'component_id':'C1','cas':'65-30-5'},{'component_id':'C2','cas':'67-56-1'},{'component_id':'C3','cas':'75-05-8'}]}
s=json.dumps({'searches':[{'component_id':x['component_id'],'queries':['Methanol','니코틴']} for x in c['components']]})
assert parse_queries(s,[x['component_id'] for x in c['components']])
answer={'test_id':'M-06-B','components':[{'component_id':x['component_id'],'direct_cas_match':False,
 'covered_by_clause':True,'reasoning_category':'GROUP_INCLUDED','relevant_entry_id':'97-1-11','relevant_sub_number':None} for x in c['components']],
 'all_components_designated':True,'reason_ko':'검증용 모의 JSON'}
assert parse_answer(json.dumps(answer),c['test_id'],['C1','C2','C3'],True)
assert parse_answer(json.dumps({**answer,'all_components_designated':None}),c['test_id'],['C1','C2','C3'],True) is None
print('PASS: source DB search, 3-component query parser, structured judgement schema')
