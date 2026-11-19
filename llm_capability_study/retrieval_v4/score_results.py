"""v4: retrieval/reasoning scores against reviewed-eligible *provisional* reference, not certified legal conclusions."""
from __future__ import annotations
import csv,hashlib,json,sqlite3,argparse,collections,statistics,random
from pathlib import Path
from search_legal_db import DB,fused_search
from run_retrieval import MODELS,parse_answer,load,DATA,OUT,ROOT

def csvwrite(path,rows):
 if not rows:return
 with path.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def avg(rows,key):
 vals=[float(x[key]) for x in rows if x[key]!='' and x[key] is not None]
 return round(statistics.mean(vals),4) if vals else None

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument('--models',choices=MODELS,nargs='+',default=MODELS)
 ns=ap.parse_args()
 mf=json.loads((DATA/'manifest.json').read_text(encoding='utf-8'))
 goldpath=ROOT/'private/gold_60.jsonl'
 if not goldpath.exists():raise SystemExit('private/gold_60.jsonl 파일 필요 (공개 GitHub에 업로드하지 마세요)')
 if hashlib.sha256(goldpath.read_bytes()).hexdigest()!=mf['gold_sha256']:raise SystemExit('Gold SHA mismatch')
 gg=load(goldpath)
 assert len(gg)==60
 assert len({g['test_id'] for g in gg})==60
 with sqlite3.connect(DB) as con:
  con.row_factory=sqlite3.Row
  baseline={}
  for g in gg:
   hits,_=fused_search(con,[g['cas'],g['chemical_name_en']],k=8)
   baseline[g['test_id']]=set(int(x['excel_row']) for x in hits)
 rows=[]
 for model in ns.models:
  f=OUT/f'{model.replace(":","_")}__main.jsonl'
  d={r['test_id']:r for r in load(f)}
  for g in gg:
   rec=d.get(g['test_id']);ans=parse_answer(rec.get('answer_raw'),g['test_id']) if rec else None
   review=g['gold_status'];scorable=review=='CURATED_PROVISIONAL'
   acceptable=set(int(i) for i in g['acceptable_evidence_rows'])
   found=[int(x['excel_row']) for x in rec.get('retrieved_rows',[])] if rec else []
   retrieved=bool(acceptable.intersection(found))
   exactrow=int(g['source_excel_row']) in found
   ok_scope=bool(ans and ans['covered_by_clause']==g['covered_by_clause'])
   ok_relation=bool(ans and ans['reasoning_category']==g['expected_relation'])
   ok_cas=bool(ans and ans['direct_cas_match']==g['direct_cas_match'])
   ok_entry=bool(ans and ans['relevant_entry_id']==g['relevant_entry_id'] and ans['relevant_sub_number']==g['relevant_sub_number'])
   exact=ok_scope and ok_relation and ok_cas and ok_entry
   obs=bool(rec and rec['status']!='api_error')
   status=rec.get('status','not_run') if rec else 'not_run'
   rows.append({'model':model,'test_id':g['test_id'],'case_id':g['case_id'], 'cas':g['cas'],
    'condition':g['condition'],'family':g['category'],'gold_review_status':review,
    'independent_expert_review_completed':int(g['independent_expert_review_completed']),
    'provisional_score_eligible':int(scorable),
    'status':status,'query_valid':int(bool(rec and rec['query_valid'])),
    'answer_valid':int(ans is not None),
    'scope_correct_provisional':int(ok_scope) if scorable and obs else '',
    'relation_correct_provisional':int(ok_relation) if scorable and obs else '',
    'entry_correct_provisional':int(ok_entry) if scorable and obs else '',
    'direct_cas_correct_provisional':int(ok_cas) if scorable and obs else '',
    'complete_correct_provisional':int(exact) if scorable and obs else '',
    'retrieval_acceptable_at_8':int(retrieved) if scorable and obs else '',
    'retrieval_exact_row_at_8':int(exactrow) if scorable and obs else '',
    'baseline_acceptable_at_8':int(bool(acceptable & baseline[g['test_id']])) if scorable and obs else '',
    'end_to_end_provisional':int(retrieved and exact) if scorable and obs else '',
    'wall_seconds':rec.get('wall_seconds','') if rec else '',
    'search_queries':json.dumps(rec['queries'],ensure_ascii=False) if rec else '',
    'retrieved_excel_rows':';'.join(map(str,found))})
 OUT.mkdir(exist_ok=True)
 csvwrite(OUT/'case_scores_retrieval_v4.csv',rows)
 ag=[]
 for m in ns.models:
  rr=[x for x in rows if x['model']==m]
  for dimension in ['ALL','condition','family','gold_review_status']:
   groups={'ALL':rr} if dimension=='ALL' else {str(v):[x for x in rr if str(x[dimension])==str(v)] for v in sorted(set(x[dimension] for x in rr))}
   for val,sel in groups.items():
    obs=[x for x in sel if x['status']!='not_run']
    verified=[x for x in obs if x['provisional_score_eligible']]
    hit=[x for x in verified if x['retrieval_acceptable_at_8']==1]
    ag.append({'model':m,'dimension':dimension,'value':val,'planned_n':len(sel),'observed_n':len(obs),'provisional_scorable_n':len(verified),
     'pending_n':sum(x['gold_review_status']!='CURATED_PROVISIONAL' for x in sel),
     'json_valid_rate':avg(obs,'answer_valid'),'retrieval_recall_acceptable_at_8':avg(verified,'retrieval_acceptable_at_8'),
     'retrieval_exact_row_rate':avg(verified,'retrieval_exact_row_at_8'),
     'cas_name_baseline_recall':avg(verified,'baseline_acceptable_at_8'),
     'scope_accuracy':avg(verified,'scope_correct_provisional'),
     'relation_accuracy':avg(verified,'relation_correct_provisional'),
     'complete_accuracy_given_hit':avg(hit,'complete_correct_provisional'),
     'end_to_end_success':avg(verified,'end_to_end_provisional')})
 csvwrite(OUT/'subgroup_accuracy_retrieval_v4.csv',ag)
 paired=[]
 for model in ns.models:
  d={(x['case_id'],x['condition']):x for x in rows if x['model']==model}
  for cid in sorted(set(g['case_id'] for g in gg)):
   a=d[(cid,'A')];b=d[(cid,'B')]
   if not(a['provisional_score_eligible'] and b['provisional_score_eligible'] and a['status']!='not_run' and b['status']!='not_run'):continue
   paired.append({'model':model,'case_id':cid,'cas':a['cas'],'family':a['family'],
    'A_retrieval':a['retrieval_acceptable_at_8'],'B_retrieval':b['retrieval_acceptable_at_8'],
    'delta_retrieval':b['retrieval_acceptable_at_8']-a['retrieval_acceptable_at_8'],
    'A_end_to_end':a['end_to_end_provisional'],'B_end_to_end':b['end_to_end_provisional'],
    'delta_end_to_end':b['end_to_end_provisional']-a['end_to_end_provisional']})
 csvwrite(OUT/'paired_structure_effect_retrieval_v4.csv',paired)
 print('=== v4 exploratory scoring (provisional only; no Gold legally expert-adjudicated) ===')
 for a in ag:
  if a['dimension']=='ALL':
   print(f"{a['model']:<20} {a['observed_n']}/{a['planned_n']} 실행; 평가 가능한 잠정 문항 {a['provisional_scorable_n']}; "
         f"Recall@8={a['retrieval_recall_acceptable_at_8']}; scope={a['scope_accuracy']}; "
         f"end-to-end={a['end_to_end_success']}; JSON={a['json_valid_rate']}")
 print('CSV: results/case_scores_retrieval_v4.csv, subgroup_accuracy_retrieval_v4.csv, paired_structure_effect_retrieval_v4.csv')
 print('검증 한계: curated provisional은 전문가 확정 Gold가 아님. 탄소수 범위·위치이성질체 3종(6문항)은 자동 채점 제외.')
 print('절대 독립 표본 60건으로 가정하지 말 것: A/B 대응 + 입자크기 반복 CAS 자료.')
 print('EXPLICIT_EXCEPTION은 해당 그룹 조항에만 비해당을 의미; 전체 법규 비규제와 동일시하지 말 것.')
if __name__=='__main__':main()
