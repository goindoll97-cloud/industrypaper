"""Score main-stage results using *local-only* Gold; no LLM API calls here."""
from __future__ import annotations
import argparse,csv,hashlib,json,statistics,unicodedata
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parent
RESULTS=ROOT/'results';GOLD=ROOT/'private/gold_72.jsonl'
MODELS=['qwen2.5:3b','qwen3:4b-instruct','qwen3.5:4b']
CORE=['listed_in_annex','regulatory_entry_id','official_name_ko',
      'acute_applies','chronic_applies','ecological_applies','any_hazard_applies']
BOOL=['listed_in_annex','acute_applies','chronic_applies','ecological_applies','any_hazard_applies']
FULL=['test_id',*CORE,'reason_ko']

def load(p):
    if not p.exists():return []
    return [json.loads(s) for s in p.read_text(encoding='utf-8').splitlines() if s.strip()]

def parse_answer(raw,test_id):
    try:o=json.loads(raw)
    except (ValueError,TypeError):return None
    if not isinstance(o,dict) or set(o)!=set(FULL) or o.get('test_id')!=test_id:return None
    if any(type(o.get(k)) is not bool for k in BOOL):return None
    if any(o[k] is not None and type(o[k]) is not str for k in ('regulatory_entry_id','official_name_ko')):return None
    if type(o.get('reason_ko')) is not str:return None
    return o

def norm(x):return unicodedata.normalize('NFC',x.strip()) if isinstance(x,str) else x

def save_csv(p,rows):
    if not rows:return
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),extrasaction='ignore');w.writeheader();w.writerows(rows)

def main():
    ap=argparse.ArgumentParser(description="Score exactly the models used in the experiment")
    ap.add_argument("--models",nargs="+",choices=MODELS,default=MODELS)
    args=ap.parse_args()
    if len(args.models)<2 or len(set(args.models))!=len(args.models):ap.error("Choose 2 or 3 different models")
    m=json.loads((ROOT/'data/manifest.json').read_text(encoding='utf-8'))
    if hashlib.sha256(GOLD.read_bytes()).hexdigest()!=m['gold_sha256']:
        raise SystemExit('Gold 파일 SHA256 불일치: 채점 중단')
    gold=load(GOLD)
    if len(gold)!=72:raise SystemExit('Gold 질문 수 오류')
    detail=[]
    for model in args.models:
        out=RESULTS/f'{model.replace(":","_")}__main.jsonl'
        records=load(out)
        byid={r['test_id']:r for r in records if r.get('status')=='ok'}
        for g in gold:
            tid=g['test_id'];r=byid.get(tid)
            obj=parse_answer(r['output_text'],tid) if r else None
            valid=obj is not None
            matching={k:bool(valid and norm(obj[k])==norm(g[k])) for k in CORE}
            exact=all(matching.values())
            detail.append({'model':model,'test_id':tid,'chemical_case_id':g['chemical_case_id'],
                           'cas_no':g['cas_no'],'stratum':g['stratum'],'stratum_name':g['stratum_name'],
                           'difficulty':g['difficulty'],'scenario':g['scenario'],
                           'listed_gold':g['listed_in_annex'],'api_success':r is not None,
                           'json_valid':valid,'core_exact':exact,
                           'wall_seconds':r.get('wall_seconds') if r else '',
                           'reused_pilot':r.get('reused_pilot',False) if r else False,
                           **{'correct_'+k:matching[k] for k in CORE}})
    RESULTS.mkdir(parents=True,exist_ok=True)
    save_csv(RESULTS/'case_scores.csv',detail)
    model_rows=[];group_rows=[]
    for model in args.models:
        rows=[r for r in detail if r['model']==model]
        def aggregate(items,label):
            n=len(items)
            return {'model':model,'group':label,'n':n,
                    'api_ok':sum(r['api_success'] for r in items),
                    'json_valid_rate':round(sum(r['json_valid'] for r in items)/n,4),
                    'core_exact_n':sum(r['core_exact'] for r in items),
                    'core_exact_rate':round(sum(r['core_exact'] for r in items)/n,4),
                    **{'accuracy_'+k:round(sum(r['correct_'+k] for r in items)/n,4) for k in CORE}}
        model_rows.append(aggregate(rows,'ALL'))
        for kind in ['stratum','difficulty','scenario','listed_gold']:
            cats=sorted({str(x[kind]) for x in rows})
            for cat in cats:
                sub=[x for x in rows if str(x[kind])==cat]
                group_rows.append(aggregate(sub,kind+':'+cat))
    save_csv(RESULTS/'model_summary.csv',model_rows)
    save_csv(RESULTS/'subgroup_summary.csv',group_rows)
    print('=== 모델별 핵심 7필드 동시 일치 정확도(무응답·JSON 오류는 오답) ===')
    for r in model_rows:
        print(f'{r["model"]:22} {r["core_exact_n"]:2}/{r["n"]} = {r["core_exact_rate"]*100:5.1f}%, API 성공 {r["api_ok"]}/{r["n"]}')
    print('결과: results/case_scores.csv, model_summary.csv, subgroup_summary.csv')
    if any(r['api_ok']<72 for r in model_rows):print('주의: 일부 모델의 응답이 누락되었습니다. 비교 전에 본실험을 완료하세요.')

if __name__=='__main__':main()
