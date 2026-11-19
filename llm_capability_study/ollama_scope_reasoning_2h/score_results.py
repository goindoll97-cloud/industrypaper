"""Local-only scoring of CAS/structure scope reasoning. Never sends or reads Gold in Ollama runner."""
from __future__ import annotations
import csv,json,hashlib,random,statistics,unicodedata,argparse
from pathlib import Path
from collections import defaultdict
R=Path(__file__).resolve().parent; D=R/'data';RESULTS=R/'results'
MODELS=['qwen2.5:3b','qwen3:4b-instruct','qwen3.5:4b']
KEYS=['direct_cas_match','covered_by_clause','reasoning_category','relevant_entry_id','relevant_sub_number']

def load(p):
 if not p.exists():return []
 return [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()]
def csvwrite(path,rs):
 if not rs:return
 with path.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rs[0]));w.writeheader();w.writerows(rs)
def clean(x):return unicodedata.normalize('NFC',x.strip()) if isinstance(x,str) else x

def parse(text,tid):
 try:d=json.loads(text)
 except (ValueError,TypeError):return None
 if not isinstance(d,dict) or d.get('test_id')!=tid:return None
 if type(d.get('direct_cas_match')) is not bool or type(d.get('covered_by_clause')) is not bool:return None
 if d.get('reasoning_category') not in ['DIRECT_SPECIFIC','GROUP_INCLUDED','EXPLICIT_EXCEPTION','NOT_COVERED']:return None
 if d.get('relevant_entry_id') is not None and type(d.get('relevant_entry_id')) is not str:return None
 if d.get('relevant_sub_number') is not None and type(d.get('relevant_sub_number')) is not int:return None
 if type(d.get('reason_ko')) is not str:return None
 return d

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--models',nargs='+',choices=MODELS,default=MODELS);args=ap.parse_args()
 gpath=R/'private/gold_40.jsonl'
 if not gpath.exists():raise SystemExit('Gold not found: private/gold_40.jsonl (never upload to public GitHub)')
 manifest=json.loads((D/'manifest.json').read_text(encoding='utf-8'))
 if hashlib.sha256(gpath.read_bytes()).hexdigest()!=manifest['gold_sha256']:raise SystemExit('Gold SHA mismatch')
 gold=load(gpath)
 assert len(gold)==40
 all_rows=[]
 for model in args.models:
  p=RESULTS/f'{model.replace(":","_")}__main.jsonl'
  ret={row['test_id']:row for row in load(p) if row.get('status')=='ok'}
  for g in gold:
   r=ret.get(g['test_id']);answer=parse(r['output_text'],g['test_id']) if r else None
   valid=answer is not None
   expected={'direct_cas_match':g['direct_cas_match'],'covered_by_clause':g['covered_by_clause'],
            'reasoning_category':g['expected_relation'],'relevant_entry_id':g['relevant_entry_id'],
            'relevant_sub_number':g['relevant_sub_number']}
   fields={k:bool(valid and clean(answer[k])==clean(expected[k])) for k in KEYS}
   all_rows.append({'model':model,'test_id':g['test_id'],'case_id':g['case_id'],
                    'condition':g['condition'],'category':g['category'],'difficulty':g['difficulty'],
                    'expected_relation':g['expected_relation'],'cas':g['cas'],'api_success':bool(r),
                    'json_valid':valid,'case_exact':all(fields.values()),
                    'covered_correct':fields['covered_by_clause'],
                    'match_type_correct':fields['reasoning_category'],
                    'entry_correct':fields['relevant_entry_id'],
                    'sub_number_correct':fields['relevant_sub_number'],
                    'direct_match_correct':fields['direct_cas_match'],
                    'wall_seconds':r.get('wall_seconds') if r else '',
                    'reused_pilot':r.get('reused_pilot') if r else False})
 RESULTS.mkdir(exist_ok=True)
 csvwrite(RESULTS/'case_scores.csv',all_rows)
 aggregate=[]
 for model in args.models:
  rr=[r for r in all_rows if r['model']==model]
  for col in ['ALL','condition','category','difficulty','expected_relation']:
   groups={'ALL':rr} if col=='ALL' else {str(v):[r for r in rr if str(r[col])==str(v)] for v in sorted({r[col] for r in rr})}
   for v,sub in groups.items():
    n=len(sub)
    aggregate.append({'model':model,'variable':col,'level':v,'n':n,'responded':sum(x['api_success'] for x in sub),
                      'case_exact':round(sum(x['case_exact'] for x in sub)/n,4),
                      'scope_accuracy':round(sum(x['covered_correct'] for x in sub)/n,4),
                      'type_accuracy':round(sum(x['match_type_correct'] for x in sub)/n,4),
                      'entry_accuracy':round(sum(x['entry_correct'] for x in sub)/n,4),
                      'json_valid_rate':round(sum(x['json_valid'] for x in sub)/n,4)})
 csvwrite(RESULTS/'subgroup_accuracy.csv',aggregate)
 by={}
 for r in all_rows:by[(r['model'],r['case_id'],r['condition'])]=r
 paired=[]
 for model in args.models:
  for cid in sorted({g['case_id'] for g in gold}):
   a=by[(model,cid,'A')];b=by[(model,cid,'B')]
   paired.append({'model':model,'case_id':cid,'category':a['category'],'difficulty':a['difficulty'],
                  'A_exact':int(a['case_exact']),'B_exact':int(b['case_exact']),
                  'B_minus_A_exact':int(b['case_exact'])-int(a['case_exact']),
                  'A_scope':int(a['covered_correct']),'B_scope':int(b['covered_correct']),
                  'B_minus_A_scope':int(b['covered_correct'])-int(a['covered_correct'])})
 csvwrite(RESULTS/'paired_structure_effect.csv',paired)
 def diff(model_a,model_b,cond):
  ids=sorted({g['case_id'] for g in gold})
  return [int(by[(model_b,cid,cond)]['case_exact'])-int(by[(model_a,cid,cond)]['case_exact']) for cid in ids]
 cmp=[];rng=random.Random(20261119)
 pairs=[(args.models[i],args.models[j]) for i in range(len(args.models)) for j in range(i+1,len(args.models))]
 for a,b in pairs:
  for condition in ['A','B']:
   vals=diff(a,b,condition)
   n=len(vals);boots=[statistics.mean(rng.choices(vals,k=n)) for _ in range(3000)]
   boots.sort()
   cmp.append({'earlier_model':a,'later_model':b,'condition':condition,'n_compounds':n,
               'delta_exact_new_minus_old':round(statistics.mean(vals),4),
               'ci95_low':round(boots[74],4),'ci95_high':round(boots[2924],4)})
 csvwrite(RESULTS/'generation_comparison.csv',cmp)
 print('\n=== 분석 결과 (결측과 JSON 오류는 오답 처리) ===')
 for x in aggregate:
  if x['variable']=='condition':print(f"{x['model']:<20} {x['level']}: {x['case_exact']*100:5.1f}% exact, {x['scope_accuracy']*100:5.1f}% scope, n={x['n']}")
 print('결과 저장: results/case_scores.csv, subgroup_accuracy.csv, paired_structure_effect.csv, generation_comparison.csv')
 if any(x['responded']<x['n'] for x in aggregate if x['variable']=='ALL'):
  print('주의: 본실험 미완료 모델이 있습니다. 추론을 끝낸 후 논문 통계로 사용하세요.')
 print('주의: 물질 20종의 탐색적 비교이므로 신뢰구간이 넓을 수 있습니다.')
if __name__=='__main__':main()
