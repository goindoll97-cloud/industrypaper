"""Deterministic scoring: CAS and composition case-level, separate retrieval/decision metrics.
This module alone reads the private provisional Gold. It does NOT confer legal validity.
"""
from __future__ import annotations
import csv,json,hashlib,statistics,random,argparse,shutil
from datetime import datetime
from pathlib import Path
from gold_integrity import expected_gold_sha
from collections import defaultdict
from run_retrieval import ROOT,DATA,OUT,MODELS,ADDITIONAL_MODELS,load,parse_answer

def save(path,rows):
 if not rows:return
 OUT.mkdir(exist_ok=True)
 with path.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def rate(rs,key):return round(sum(int(bool(r[key])) for r in rs)/len(rs),4) if rs else None

def archive_previous_scores(folder):
 names = ['case_scores_three_groups.csv','component_scores_three_groups.csv',
          'subgroup_accuracy_three_groups.csv','paired_structure_effect_three_groups.csv']
 existing = [folder/name for name in names if (folder/name).exists()]
 if not existing:return
 backup=folder/'score_backups'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
 backup.mkdir(parents=True,exist_ok=False)
 for file in existing:shutil.copy2(file,backup/file.name)
 print('기존 채점 CSV 백업:',backup)


def main(argv=None):
 global OUT
 p=argparse.ArgumentParser();p.add_argument('--models',nargs='+',choices=[*MODELS,*ADDITIONAL_MODELS],default=MODELS)
 p.add_argument('--results-dir',default='results',help='원본 v4는 results, 개선된 v4.1은 results_v4_1')
 ns=p.parse_args(argv)
 OUT=ROOT/ns.results_dir
 if not OUT.is_dir() or not any(OUT.glob('*__main.jsonl')):
  raise SystemExit('선택된 결과 폴더에 본실험 JSONL이 없습니다: '+str(OUT))
 mf=json.loads((DATA/'manifest.json').read_text(encoding='utf-8'))
 gp=ROOT/'private/gold_60.jsonl'
 if not gp.exists():raise SystemExit('Gold 없음: private/gold_60.jsonl (ZIP에서 복사, GitHub 업로드 금지)')
 if hashlib.sha256(gp.read_bytes()).hexdigest()!=expected_gold_sha(ROOT,mf):raise SystemExit('Gold SHA 불일치: 수정되었으면 별도 버전으로 동결')
 gold=load(gp);assert len(gold)==60
 archive_previous_scores(OUT)
 out=[];component_scores=[]
 for model in ns.models:
  rows={x['test_id']:x for x in load(OUT/f'{model.replace(":","_")}__main.jsonl')}
  for g in gold:
   x=rows.get(g['test_id'])
   ids=[c['component_id'] for c in g['component_gold']]
   a=parse_answer(x.get('answer_raw'),g['test_id'],ids,g['group']=='MIXTURE') if x else None
   amap={c['component_id']:c for c in a['components']} if a else {}
   matches=[];evidence_hits=[];covered_fields=[];identity_fields=[]
   for c in g['component_gold']:
    cid=c['component_id'];ans=amap.get(cid)
    retrieved=x.get('retrieved_by_component',{}).get(cid,[]) if x else []
    hit=int(c['source_excel_row'] in [z['excel_row'] for z in retrieved])
    evidence_hits.append(hit)
    cor=bool(ans and ans['direct_cas_match']==c['direct_cas_match'] and
             ans['covered_by_clause']==c['covered_by_clause'] and
             ans['reasoning_category']==c['expected_relation'] and
             ans['relevant_entry_id']==c['relevant_entry_id'] and
             ans['relevant_sub_number']==c['relevant_sub_number'])
    matches.append(cor)
    covered_fields.append(bool(ans and ans['covered_by_clause']==c['covered_by_clause']))
    identity_fields.append(bool(ans and ans['direct_cas_match']==c['direct_cas_match']))
    component_scores.append({'model':model,'test_id':g['test_id'],'case_id':g['case_id'],
      'condition':g['condition'],'group':g['group'],'difficulty':g['difficulty'],'component_id':cid,
      'cas':c['cas'],'gold_relation':c['expected_relation'],'gold_entry':c['relevant_entry_id'],
      'gold_excel_row':c['source_excel_row'],'retrieval_hit':hit,'component_exact':int(cor),
      'scope_correct':int(covered_fields[-1]),'direct_match_correct':int(identity_fields[-1]),
      'status':x.get('status') if x else 'not_run'})
   mixture_ok=(a and a['all_components_designated']==g['mixture_article3_all_listed']) if g['group']=='MIXTURE' else True
   exact=bool(a and all(matches) and mixture_ok)
   out.append({'model':model,'test_id':g['test_id'],'case_id':g['case_id'],
    'condition':g['condition'],'group':g['group'],'difficulty':g['difficulty'],'component_count':len(ids),
    'gold_status':g['review_status'],'expert_verified':int(g['independent_expert_review_completed']),
    'status':x.get('status') if x else 'not_run','answer_valid':int(bool(a)),
    'all_components_retrieved':int(all(evidence_hits)),
    'retrieved_component_count':sum(evidence_hits),
    'component_recall':round(sum(evidence_hits)/len(ids),4),
    'all_scope_correct':int(all(covered_fields)),'all_direct_correct':int(all(identity_fields)),
    'all_component_exact':int(all(matches)),
    'article3_all_listed_correct':int(bool(mixture_ok)) if g['group']=='MIXTURE' and a else (0 if g['group']=='MIXTURE' else ''),
    'case_exact':int(exact),'end_to_end_success':int(exact and all(evidence_hits)),
    'query_seconds':x.get('query_seconds','') if x else '',
    'reason_seconds':x.get('reason_seconds','') if x else '',
    'wall_seconds':x.get('wall_seconds','') if x else ''})
 save(OUT/'case_scores_three_groups.csv',out)
 save(OUT/'component_scores_three_groups.csv',component_scores)
 agg=[]
 for m in ns.models:
  rows=[x for x in out if x['model']==m]
  for grouping in ['ALL','group','difficulty','condition','group_difficulty']:
   groups={'ALL':rows} if grouping=='ALL' else defaultdict(list)
   if grouping!='ALL':
    for r in rows:
     v=(r['group']+' / '+r['difficulty']) if grouping=='group_difficulty' else r[grouping]
     groups[v].append(r)
   for val,items in sorted(groups.items()):
    done=[x for x in items if x['status']!='not_run']
    agg.append({'model':m,'variable':grouping,'value':val,'planned':len(items),'observed':len(done),
       'provisional_gold':sum(x['gold_status']=='CURATED_PROVISIONAL' for x in done),
       'expert_verified':sum(x['expert_verified'] for x in done),
       'json_valid_rate':rate(done,'answer_valid'),
       'retrieval_all_recall':rate(done,'all_components_retrieved'),
       'component_recall_mean':round(statistics.mean(x['component_recall'] for x in done),4) if done else None,
       'scope_all_accuracy':rate(done,'all_scope_correct'),
       'case_exact_accuracy':rate(done,'case_exact'),
       'end_to_end_accuracy':rate(done,'end_to_end_success')})
 save(OUT/'subgroup_accuracy_three_groups.csv',agg)
 idx={(x['model'],x['case_id'],x['condition']):x for x in out}
 pairs=[]
 for m in ns.models:
  for cid in sorted({x['case_id'] for x in out}):
   a=idx[(m,cid,'A')];b=idx[(m,cid,'B')]
   if a['status']=='not_run' or b['status']=='not_run':continue
   pairs.append({'model':m,'case_id':cid,'group':a['group'],'difficulty':a['difficulty'],
     'A_e2e':a['end_to_end_success'],'B_e2e':b['end_to_end_success'],
     'delta_e2e':b['end_to_end_success']-a['end_to_end_success'],
     'A_retrieved':a['all_components_retrieved'],'B_retrieved':b['all_components_retrieved'],
     'delta_retrieved':b['all_components_retrieved']-a['all_components_retrieved']})
 save(OUT/'paired_structure_effect_three_groups.csv',pairs)
 print('\n=== 3분류 예비 성능(전문가 확인 전 잠정 Gold) ===')
 for x in agg:
  if x['variable']=='ALL':
   print(f"{x['model']:<20} {x['observed']}/{x['planned']} 실행, retrieval(all)={x['retrieval_all_recall']}, end-to-end={x['end_to_end_accuracy']}, JSON={x['json_valid_rate']}")
 print('CSV 저장 폴더:',OUT)
 print('주의: Gold 전부 잠정 판정이며 전문가 검증 완료=0. 본 실험 정답률 또는 법률 확정 판정으로 인용 금지.')
 print('주의: 혼합물의 false는 고시 제3조의 “지정물질만으로 구성” 요건 불충족이지 혼합물 전체의 비규제 뜻이 아닙니다.')
if __name__=='__main__':main()
