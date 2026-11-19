"""Ollama agent-directed full-annex retrieval + chemical regulatory scope reasoning.
Stage 1: model writes search queries; stage 2: deterministic full-annex search tool;
stage 3: SAME model evaluates returned evidence. Gold is never read here.
"""
from __future__ import annotations
import argparse, hashlib, json, sqlite3, sys, time, urllib.request
from datetime import datetime,timezone
from pathlib import Path
from build_legal_db import build,DB
from search_legal_db import fused_search,evidence
ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data';OUT=ROOT/'results'
MODELS=['qwen2.5:3b','qwen3:4b-instruct','qwen3.5:4b']
RELS=['DIRECT_SPECIFIC','GROUP_INCLUDED','EXPLICIT_EXCEPTION','NOT_COVERED','INSUFFICIENT_EVIDENCE']
QUERY_SCHEMA={'type':'object','properties':{'queries':{'type':'array','items':{'type':'string'},'minItems':1,'maxItems':3}},'required':['queries'],'additionalProperties':False}
ANSWER_SCHEMA={'type':'object','properties':{
 'test_id':{'type':'string'},'direct_cas_match':{'type':'boolean'},'covered_by_clause':{'type':'boolean'},
 'reasoning_category':{'type':'string','enum':RELS},
 'relevant_entry_id':{'type':['string','null']},'relevant_sub_number':{'type':['integer','null']},
 'reason_ko':{'type':'string'}},
 'required':['test_id','direct_cas_match','covered_by_clause','reasoning_category','relevant_entry_id','relevant_sub_number','reason_ko'],
 'additionalProperties':False}

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):
 return [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()] if p.exists() else []
def request(base,endpoint,payload=None,timeout=180):
 data=json.dumps(payload,ensure_ascii=False).encode('utf-8') if payload is not None else None
 req=urllib.request.Request(base+endpoint,data=data,headers={'Content-Type':'application/json'} if data else {})
 with urllib.request.urlopen(req,timeout=timeout) as response:
  return json.loads(response.read().decode('utf-8'))
def parse_queries(s):
 try:obj=json.loads(s)
 except (TypeError,ValueError):return None
 if not isinstance(obj,dict) or set(obj)!={'queries'} or type(obj['queries']) is not list:return None
 arr=obj['queries']
 if not 1<=len(arr)<=3 or any(type(q) is not str or not 2<=len(q.strip())<=100 for q in arr):return None
 return list(dict.fromkeys(q.strip() for q in arr))
def parse_answer(raw,tid):
 try:a=json.loads(raw)
 except (TypeError,ValueError):return None
 if not isinstance(a,dict) or set(a)!=set(ANSWER_SCHEMA['properties']) or a.get('test_id')!=tid:return None
 if any(type(a[k]) is not bool for k in ('direct_cas_match','covered_by_clause')):return None
 if a['reasoning_category'] not in RELS:return None
 if a['relevant_entry_id'] is not None and type(a['relevant_entry_id']) is not str:return None
 if a['relevant_sub_number'] is not None and type(a['relevant_sub_number']) is not int:return None
 if type(a['reason_ko']) is not str:return None
 return a

def identity(case):
 lines=[f"CAS: {case['cas']}",f"영문명: {case['name_en']}"]
 if case['condition']=='B':
  if case['formula']:lines.append(f"분자식: {case['formula']}")
  if case['smiles']:lines.append(f"SMILES: {case['smiles']}")
 return '\n'.join(lines)

def query_messages(case):
 sysmsg=('당신은 한국 환경부 2026-5호 전체 지정고시 검색 에이전트입니다. '\
 '다음 물질의 직접 지정, 포괄 물질군, 염류, 예외/별도 지정 항목을 찾기 위해 '\
 '실제 고시에서 쓰였을 법한 검색어를 1~3개 생성하세요. '\
 '모델에 고시 후보항목을 미리 제공하지 않습니다. '\
 '검색어에는 구조에서 추정한 모체·물질군 이름을 넣을 수 있습니다. '\
 '아직 지정 여부를 판단하지 마세요. 반드시 queries 배열만 포함하는 JSON으로 답하세요.')
 return [{'role':'system','content':sysmsg},
         {'role':'user','content':identity(case)+'\n대상 물질의 고시 지정항목을 찾을 검색어를 작성하시오.'}]

def reason_messages(case,hits):
 sysmsg=('당신은 한국 화학물질 포괄 지정범위 판독 모델입니다. 검색 도구가 반환한 공식 고시행만을 근거로 판정하세요. '\
 '검색된 행은 정답 선택지가 아니라 검색 결과이며, 관련 조항이 없을 수 있습니다. '\
 'CAS 직접 일치가 없더라도 실제 염류·화합물·명시적 예외 관계를 분석하세요. '\
 '특정 소번호 CAS가 직접 지정되면 직접 지정을 우선합니다. '\
 '명시적으로 제외된 경우 covered_by_clause=false, reasoning_category=EXPLICIT_EXCEPTION으로 분류하세요. '\
 '검색 결과에서 확실한 법적 근거가 없으면 INSUFFICIENT_EVIDENCE를 선택하세요. '\
 'NOT_COVERED는 제시된 고시 정보로 비해당이 충분히 확인된 경우에만 사용하세요. '\
 '단순히 검색되지 않았다는 사실을 전체 고시 비규제의 증거로 취급하지 마세요. '\
 '혼합물 함량기준과 위법 여부는 판단하지 마세요. 짧은 한국어 이유와 JSON 객체 한 개만 출력하세요.')
 rows=[evidence(r) for r in hits]
 usr=('시험 ID: '+case['test_id']+'\n'+identity(case)+'\n\n'
      +'[전체 1451행 고시 데이터베이스 검색 도구의 실제 반환 결과, 최대 8행]\n'
      +json.dumps(rows,ensure_ascii=False,separators=(',',':'))+'\n\n'
      +'적용 고유번호, 소번호, 직접 CAS 일치 여부, 포괄 포함/예외 여부를 근거로 판단하시오. '
      +'관계 유형은 '+', '.join(RELS)+' 중 선택.')
 return [{'role':'system','content':sysmsg},{'role':'user','content':usr}]

def infer(base,model,messages,schema,num_predict,num_ctx,seed,timeout):
 payload={'model':model,'messages':messages,'stream':False,'format':schema,'keep_alive':'5m',
          'options':{'num_ctx':num_ctx,'num_predict':num_predict,'temperature':0,'seed':seed}}
 if model.startswith('qwen3'):payload['think']=False
 t=time.perf_counter();ans=request(base,'/api/chat',payload,timeout)
 return ans,round(time.perf_counter()-t,3)

def main(argv=None):
 ap=argparse.ArgumentParser(description='Model-chosen retrieval over all 1451 annex rows, then model reasoning (no prechosen clauses)')
 ap.add_argument('--stage',choices=['pilot','main'],required=True)
 ap.add_argument('--model',choices=['all',*MODELS],default='all')
 ap.add_argument('--condition',choices=['all','A','B'],default='all')
 ap.add_argument('--endpoint',default='http://127.0.0.1:11434')
 ap.add_argument('--num-ctx',type=int,default=3072)
 ap.add_argument('--num-predict-query',type=int,default=125)
 ap.add_argument('--num-predict-reason',type=int,default=420)
 ap.add_argument('--seed',type=int,default=20261119)
 ap.add_argument('--timeout',type=int,default=210)
 ap.add_argument('--force',action='store_true',help='해당 단계·모델의 기존 결과를 삭제하고 재실행')
 ap.add_argument('--limit',type=int,default=None,help='디버그 전용. 부분실행은 본실험 결과 아님')
 ns=ap.parse_args(argv)
 if ns.num_predict_query<75 or ns.num_predict_reason<250:ap.error('출력 토큰 제한이 너무 작습니다.')
 mf=json.loads((DATA/'manifest.json').read_text(encoding='utf-8'))
 for n,key in [('cases_48.jsonl','cases_sha256'),('pilot_8_ids.json','pilot_sha256'),('official_annex_2026_5_full.csv','annex_sha256')]:
  if sha(DATA/n)!=mf[key]:sys.exit(f'SHA 불일치: {n}')
 if not DB.exists():build()
 with sqlite3.connect(DB) as con:
  if con.execute('SELECT count(*) FROM annex').fetchone()[0]!=1451:sys.exit('DB 고시 1451행 검사 실패')
 cases=load(DATA/'cases_48.jsonl')
 if len(cases)!=48:sys.exit('48문항 오류')
 pilot=set(json.loads((DATA/'pilot_8_ids.json').read_text(encoding='utf-8')))
 chosen=[c for c in cases if (ns.stage=='main' or c['test_id'] in pilot) and (ns.condition=='all' or c['condition']==ns.condition)]
 if ns.limit:chosen=chosen[:ns.limit]
 models=MODELS if ns.model=='all' else [ns.model]
 base=ns.endpoint.rstrip('/')
 try:tags={x['name']:x for x in request(base,'/api/tags',timeout=20)['models']}
 except Exception as e:sys.exit(f'Ollama API 연결 안 됨: {e}')
 for model in models:
  if model not in tags:sys.exit(f'{model} 미설치: ollama pull {model}')
 OUT.mkdir(exist_ok=True)
 for model in models:
  slug=model.replace(':','_'); path=OUT/f'{slug}__{ns.stage}.jsonl'
  settings={'model':model,'digest':tags[model].get('digest'),'num_ctx':ns.num_ctx,
            'num_predict_query':ns.num_predict_query,'num_predict_reason':ns.num_predict_reason,
            'seed':ns.seed,'cases_sha256':mf['cases_sha256'],'annex_sha256':mf['annex_sha256'],
            'search_algorithm':'lexical_rank_fusion_v1','top_k':8}
  key=hashlib.sha256(json.dumps(settings,sort_keys=True).encode()).hexdigest()
  if ns.force and path.exists():path.unlink()
  old=load(path)
  if any(x.get('settings_sha256')!=key for x in old):sys.exit('이전 실험과 설정이 다릅니다. 재실험 시 pilot/main 모두 별도 백업 후 --force로 시작하세요.')
  done={x['test_id'] for x in old if x.get('status') in ('ok','invalid_query','invalid_answer')}
  if ns.stage=='main':
   for x in load(OUT/f'{slug}__pilot.jsonl'):
    if x.get('settings_sha256')!=key:sys.exit('pilot/main 설정 불일치')
    if x.get('status') in ('ok','invalid_query','invalid_answer') and x['test_id'] not in done:
     with path.open('a',encoding='utf-8') as f:f.write(json.dumps({**x,'stage':'main','reused_pilot':True},ensure_ascii=False)+'\n')
     done.add(x['test_id'])
  print(f'[{model}] {ns.stage}, {ns.condition}: {len(chosen)}문항 중 기완료 {len(done & {c["test_id"] for c in chosen})}',flush=True)
  try:
   with sqlite3.connect(DB) as con:
    con.row_factory=sqlite3.Row
    for ix,c in enumerate(chosen,1):
     if c['test_id'] in done:continue
     qreply=qraw=areply=araw=None; queries=[];hits=[];search_logs=[];qt=rt=0;err=None
     try:
      qreply,qt=infer(base,model,query_messages(c),QUERY_SCHEMA,ns.num_predict_query,ns.num_ctx,ns.seed,ns.timeout)
      qraw=qreply.get('message',{}).get('content','')
      queries=parse_queries(qraw) or []
      hits,search_logs=fused_search(con,queries,k=8,per_query=10)
      areply,rt=infer(base,model,reason_messages(c,hits),ANSWER_SCHEMA,ns.num_predict_reason,ns.num_ctx,ns.seed,ns.timeout)
      araw=areply.get('message',{}).get('content','')
     except Exception as e:err=str(e)
     valid=parse_answer(araw,c['test_id']) is not None
     status='api_error' if err else ('invalid_query' if not queries else ('ok' if valid else 'invalid_answer'))
     row={'test_id':c['test_id'],'case_id':c['case_id'],'condition':c['condition'],'model':model,
          'timestamp_utc':datetime.now(timezone.utc).isoformat(),'stage':ns.stage,'reused_pilot':False,
          'settings_sha256':key,'model_digest':tags[model].get('digest'),'status':status,'error':err,
          'query_raw':qraw,'query_valid':bool(queries),'queries':queries,'search_logs':search_logs,
          'retrieved_rows':[evidence(r) for r in hits],
          'answer_raw':araw,'answer_valid':valid,
          'query_seconds':qt,'reason_seconds':rt,'wall_seconds':round(qt+rt,3),
          'query_eval_count':qreply.get('eval_count') if qreply else None,
          'reason_eval_count':areply.get('eval_count') if areply else None}
     with path.open('a',encoding='utf-8',newline='\n') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush()
     done.add(c['test_id'])
     print(f'{ix:02d}/{len(chosen)} {c["test_id"]}: 검색어 {len(queries)}, 검색행 {len(hits)}, JSON={valid}, {qt+rt:.1f}s',flush=True)
     if err:sys.exit(f'API 오류: 중간결과 저장. 다시 같은 명령을 실행하여 이어서 진행: {err}')
  finally:
   try:request(base,'/api/generate',{'model':model,'prompt':'','keep_alive':0},timeout=60)
   except Exception:pass
 print('완료. python score_results.py 실행')

if __name__=='__main__':main()
