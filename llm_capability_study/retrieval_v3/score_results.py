"""Retrieval and reasoning scored separately, with unverified negatives excluded.
Gold is read ONLY by this postprocessing script and never the LLM runner.
"""
from __future__ import annotations
import csv,hashlib,json,sqlite3,random,statistics,argparse
from pathlib import Path
from search_legal_db import DB,search,fused_search
from run_retrieval import MODELS,parse_answer,load,DATA,OUT,ROOT

def write_csv(p,rows):
 if not rows:return
 with p.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)

def mean(rs,k):return round(sum(float(x[k]) for x in rs)/len(rs),4) if rs else None

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--models',nargs='+',choices=MODELS,default=MODELS)
 args=ap.parse_args()
 path=ROOT/'private/gold_48.jsonl'
 if not path.exists():raise SystemExit('private/gold_48.jsonl 파일을 로컬에 두세요 (GitHub 업로드 금지).')
 mf=json.loads((DATA/'manifest.json').read_text(encoding='utf-8'))
 if hashlib.sha256(path.read_bytes()).hexdigest()!=mf['gold_sha256']:raise SystemExit('Gold SHA 불일치')
 gold={g['test_id']:g for g in load(path)}
 if len(gold)!=48:raise SystemExit('Gold 48건 확인 실패')
 with sqlite3.connect(DB) as con:
  con.row_factory=sqlite3.Row
  # Deterministic plain-identity baseline: CAS and full name, no model-generated search terms.
  baseline={}
  for g in gold.values():
   base_queries=[g['cas'],g['chemical_name_en']]
   hits,_=fused_search(con,base_queries,k=8)
   baseline[g['test_id']]=[int(x['excel_row']) for x in hits]
 rows=[]
 for m in args.models:
  d={x['test_id']:x for x in load(OUT/f'{m.replace(":","_")}__main.jsonl')}
  for tid,g in gold.items():
   x=d.get(tid)
   label=g['expected_relation']
   confirmed=(g.get('gold_status')=='CURATED_PROVISIONAL')  # 5 unreviewed negatives excluded.
   gold_row=g.get('source_excel_row')
   expected_row=int(gold_row) if confirmed and gold_row else None
   retrieved=[int(r['excel_row']) for r in x.get('retrieved_rows',[])] if x else []
   hit=(expected_row in retrieved) if expected_row is not None else False
   answer=parse_answer(x.get('answer_raw'),tid) if x else None
   identity_correct=bool(answer and answer['direct_cas_match']==g['direct_cas_match'])
   scope_correct=bool(answer and answer['covered_by_clause']==g['covered_by_clause']) if confirmed else False
   relation_correct=bool(answer and answer['reasoning_category']==g['expected_relation']) if confirmed else False
   entry_correct=bool(answer and answer['relevant_entry_id']==g['relevant_entry_id'] and answer['relevant_sub_number']==g['relevant_sub_number']) if confirmed else False
   exact=bool(confirmed and identity_correct and scope_correct and relation_correct and entry_correct)
   rows.append({'model':m,'test_id':tid,'case_id':g['case_id'],'condition':g['condition'],
    'category':g['category'],'difficulty':g['difficulty'],'expected_relation':label,
    'gold_scope_verified':int(confirmed),'gold_status':g.get('gold_status','UNKNOWN'),'gold_row':gold_row or '',
    'query_valid':int(bool(x and x.get('query_valid'))),'answer_valid':int(bool(answer)),
    'retrieved_count':len(retrieved),'retrieval_hit_at_8':int(hit),
    'baseline_hit_at_8':int(expected_row in baseline[tid]) if confirmed else '',
    'gold_rank':retrieved.index(expected_row)+1 if hit else '',
    'scope_correct':int(scope_correct) if confirmed else '',
    'relation_correct':int(relation_correct) if confirmed else '',
    'entry_correct':int(entry_correct) if confirmed else '',
    'direct_cas_correct':int(identity_correct) if confirmed else '',
    'exact_correct':int(exact) if confirmed else '',
    'end_to_end_success':int(hit and exact) if confirmed else '',
     'failure_stage':('UNVERIFIED_GOLD' if not confirmed else 'NOT_RUN' if not x else 'QUERY_INVALID' if not x.get('query_valid') else 'RETRIEVAL_MISS' if not hit else 'ANSWER_INVALID' if not answer else 'INFERENCE_OR_FIELD_ERROR' if not exact else 'SUCCESS'),
    'status':x['status'] if x else 'not_run',
    'query_seconds':x.get('query_seconds','') if x else '',
    'reason_seconds':x.get('reason_seconds','') if x else '',
    'wall_seconds':x.get('wall_seconds','') if x else ''})
 OUT.mkdir(exist_ok=True)
 write_csv(OUT/'case_scores_retrieval_v3.csv',rows)
 agg=[]
 for m in args.models:
  chunk=[r for r in rows if r['model']==m]
  for variable in ['ALL','condition','category','difficulty','expected_relation']:
   d={'ALL':chunk} if variable=='ALL' else {str(v):[x for x in chunk if str(x[variable])==str(v)] for v in sorted({x[variable] for x in chunk})}
   for name,group in d.items():
    verified=[r for r in group if r['gold_scope_verified'] and r['status']!='not_run']
    hits=[r for r in verified if r['retrieval_hit_at_8']]
    observed=[r for r in group if r['status']!='not_run']
    agg.append({'model':m,'variable':variable,'value':name,'planned_cases':len(group),
      'observed_cases':len(observed),'verified_cases':len(verified),
      'unverified_negative_cases':sum(not r['gold_scope_verified'] for r in group),
      'valid_query_rate':mean(observed,'query_valid'),
      'json_valid_rate':mean(observed,'answer_valid'),
      'retrieval_recall_at_8':mean(verified,'retrieval_hit_at_8'),
      'identity_baseline_recall_at_8':mean(verified,'baseline_hit_at_8'),
      'reasoning_accuracy_given_retrieval':mean(hits,'exact_correct'),
      'scope_accuracy_verified':mean(verified,'scope_correct'),
      'relation_accuracy_verified':mean(verified,'relation_correct'),
      'end_to_end_success_rate':mean(verified,'end_to_end_success')})
 write_csv(OUT/'subgroup_accuracy_retrieval_v3.csv',agg)
 pair=[]
 for m in args.models:
  idx={(x['case_id'],x['condition']):x for x in rows if x['model']==m}
  for cid in sorted(set(g['case_id'] for g in gold.values())):
   a=idx[(cid,'A')];b=idx[(cid,'B')]
   if a['gold_scope_verified'] and b['gold_scope_verified'] and a['status']!='not_run' and b['status']!='not_run':
    pair.append({'model':m,'case_id':cid,'category':a['category'],
     'A_retrieved':a['retrieval_hit_at_8'],'B_retrieved':b['retrieval_hit_at_8'],
     'delta_retrieval':b['retrieval_hit_at_8']-a['retrieval_hit_at_8'],
     'A_end_to_end':a['end_to_end_success'],'B_end_to_end':b['end_to_end_success'],
     'delta_end_to_end':b['end_to_end_success']-a['end_to_end_success']})
 write_csv(OUT/'paired_structure_effect_retrieval_v3.csv',pair)
 print('\n=== 전체 별표 검색 및 근거추론 분석 ===')
 for a in agg:
  if a['variable']=='ALL':
   print(f"{a['model']:<20} {a['observed_cases']}/{a['planned_cases']}문항 실행 (평가 대상 Gold {a['verified_cases']}문항): "
    f"검색 recall@8={a['retrieval_recall_at_8']}, "
    f"검색 성공 시 완전판정={a['reasoning_accuracy_given_retrieval']}, "
    f"end-to-end={a['end_to_end_success_rate']}, "
    f"JSON 성공={a['json_valid_rate']}")
 print('CSV: results/case_scores_retrieval_v3.csv, subgroup_accuracy_retrieval_v3.csv, paired_structure_effect_retrieval_v3.csv')
 print('주요 한계: V3 비해당 후보 5종(10문항)은 독립 검토 전까지 정확도 계산에서 제외함.')
 print('검색 성공 시 판정 지표는 검색 성공 표본에 조건부로 계산됐으므로 인과적으로 독립된 추론능력 지표는 아님.')
 if any(a['observed_cases']<a['planned_cases'] for a in agg if a['variable']=='ALL'):
  print('주의: 일부 문항 미실행. 미실행은 0점으로 처리하지 않았으며 완전한 전체 비교 결과가 아닙니다.')

if __name__=='__main__':main()
