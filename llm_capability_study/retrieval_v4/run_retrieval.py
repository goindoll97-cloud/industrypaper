"""Three-group Ollama benchmark: agent generated queries -> entire annex -> multi-constituent scope judgement.
All citations/search results are returned by a neutral lexical tool over all official 1451 rows.
The runner NEVER reads Gold. No internet required after Ollama models are downloaded.
"""
from __future__ import annotations
import argparse,hashlib,json,sqlite3,sys,time,urllib.request
from datetime import datetime,timezone
from pathlib import Path
from build_legal_db import build,DB
from search_legal_db import fused_search,evidence
ROOT=Path(__file__).resolve().parent;DATA=ROOT/'data';OUT=ROOT/'results'
MODELS=['qwen2.5:3b','qwen3:4b-instruct','qwen3.5:4b']
RELS=['DIRECT_SPECIFIC','GROUP_INCLUDED','EXPLICIT_EXCEPTION','NOT_COVERED','INSUFFICIENT_EVIDENCE']
QUERY_SCHEMA={'type':'object','properties':{'searches':{'type':'array','items':{'type':'object','properties':{'component_id':{'type':'string'},'queries':{'type':'array','items':{'type':'string'},'minItems':1,'maxItems':3}},'required':['component_id','queries'],'additionalProperties':False}}},'required':['searches'],'additionalProperties':False}
COMPONENT_SCHEMA={'type':'object','properties':{'component_id':{'type':'string'},'direct_cas_match':{'type':'boolean'},'covered_by_clause':{'type':'boolean'},'reasoning_category':{'type':'string','enum':RELS},'relevant_entry_id':{'type':['string','null']},'relevant_sub_number':{'type':['integer','null']}},'required':['component_id','direct_cas_match','covered_by_clause','reasoning_category','relevant_entry_id','relevant_sub_number'],'additionalProperties':False}
ANSWER_SCHEMA={'type':'object','properties':{'test_id':{'type':'string'},'components':{'type':'array','items':COMPONENT_SCHEMA},'all_components_designated':{'type':['boolean','null']},'reason_ko':{'type':'string'}},'required':['test_id','components','all_components_designated','reason_ko'],'additionalProperties':False}
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def load(path):return [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines() if s.strip()] if path.exists() else []
def request(base,ep,payload=None,timeout=210):
 data=json.dumps(payload,ensure_ascii=False).encode('utf-8') if payload is not None else None
 rq=urllib.request.Request(base+ep,data=data,headers={'Content-Type':'application/json'} if data else {})
 with urllib.request.urlopen(rq,timeout=timeout) as r:return json.loads(r.read().decode('utf-8'))
def parse_queries(s,expected):
 try:obj=json.loads(s)
 except (ValueError,TypeError):return None
 if not isinstance(obj,dict) or set(obj)!={'searches'} or not isinstance(obj['searches'],list):return None
 result={}
 for x in obj['searches']:
  if not isinstance(x,dict) or set(x)!={'component_id','queries'} or x['component_id'] not in expected or x['component_id'] in result:return None
  q=x['queries']
  if not isinstance(q,list) or not 1<=len(q)<=3 or any(not isinstance(z,str) or not 2<=len(z.strip())<=100 for z in q):return None
  result[x['component_id']]=list(dict.fromkeys(z.strip() for z in q))
 return result if set(result)==set(expected) else None
def parse_answer(s,test_id,component_ids,is_mixture):
 try:o=json.loads(s)
 except (ValueError,TypeError):return None
 if not isinstance(o,dict) or set(o)!=set(ANSWER_SCHEMA['properties']) or o['test_id']!=test_id or type(o['reason_ko']) is not str:return None
 if is_mixture and type(o['all_components_designated']) is not bool:return None
 if not is_mixture and o['all_components_designated'] is not None:return None
 a=o['components']
 if not isinstance(a,list) or len(a)!=len(component_ids):return None
 for x in a:
  if not isinstance(x,dict) or set(x)!=set(COMPONENT_SCHEMA['properties']) or x['component_id'] not in component_ids:return None
  if type(x['direct_cas_match']) is not bool or type(x['covered_by_clause']) is not bool:return None
  if x['reasoning_category'] not in RELS:return None
  if x['relevant_entry_id'] is not None and type(x['relevant_entry_id']) is not str:return None
  if x['relevant_sub_number'] is not None and type(x['relevant_sub_number']) is not int:return None
 return o if len({x['component_id'] for x in a})==len(component_ids) else None
def identity(case):
 lines=['시험 ID: '+case['test_id'], '상황: '+('가상 다성분 혼합물' if case['scenario_kind']=='FORMULATED_MIXTURE' else '단일 화학물질')]
 for c in case['components']:
  s=f"{c['component_id']}: CAS {c['cas']}; 물질명 {c['name_en']}"
  if c['mass_percent'] is not None:s+=f"; 질량함량 {c['mass_percent']}%"
  if case['condition']=='B' and c.get('formula'):s+=f"; 분자식 {c['formula']}"
  if case['condition']=='B' and c.get('smiles'):s+=f"; SMILES {c['smiles']}"
  lines.append(s)
 return '\n'.join(lines)
def qmessages(case):
 sysmsg=('환경부 2026-5호 고시 전체 검색을 위한 검색어를 작성하십시오. 정답 조항은 제공하지 않습니다. '
  '각 성분의 CAS, 명칭, 추정 모체·화합물군에 근거하여 성분마다 검색어 1~3개를 쓰십시오. '
  '고시 적용 여부는 아직 판정하지 마십시오. 반드시 component_id별 검색어 JSON만 출력하십시오.')
 return [{'role':'system','content':sysmsg},{'role':'user','content':identity(case)+'\n각 component_id별 검색어를 생성하시오.'}]
def amessages(case,results):
 sysmsg=('2026-5호 지정고시의 전체 검색 DB가 반환한 공식 고시행만을 근거로 각각의 성분에 대해 판정하십시오. '
  '정답항목은 제공하지 않으며 검색에 실패했을 수도 있습니다. 직접 CAS 지정, 모체와 그 염류, 금속 및 화합물군, 특정 이성질체, 명시적 제외를 구분하십시오. '
  '직접 지정이라면 covered_by_clause=true, 특정 포괄항목에서 명시적 제외면 covered_by_clause=false입니다. '
  '근거 부족은 INSUFFICIENT_EVIDENCE로 답하십시오. NOT_COVERED는 충분한 근거가 있을 때만 사용하십시오. '
  '혼합물이면 모든 성분이 각각 고시 지정물질인지(all_components_designated)를 판단하십시오. '
  '이 값이 false여도 혼합물이 다른 법규나 별표의 개별 함량기준에서 완전히 비규제란 뜻이 아닙니다. '
  '현재 실험에서는 성분별 함량기준 충족, 혼합물의 영업상 준법 여부, 물질 간 화학적 반응을 판단하지 마십시오. '
  '단일 물질은 all_components_designated=null입니다. 짧은 한국어 근거를 JSON 한 개로 반환하십시오.')
 usr=identity(case)+'\n\n[2026-5호 전체 1,451행 검색 결과: 각 성분별 최대 8행]\n'+json.dumps(results,ensure_ascii=False,separators=(',',':'))+\
  '\n\n각 성분의 지정번호/소번호/포괄포함·예외 여부 및 혼합물 전부-지정성분 요건을 판단하시오.'
 return [{'role':'system','content':sysmsg},{'role':'user','content':usr}]
def infer(base,model,messages,schema,tokens,ctx,seed,timeout):
 payload={'model':model,'messages':messages,'format':schema,'stream':False,'keep_alive':'5m',
  'options':{'num_ctx':ctx,'num_predict':tokens,'temperature':0,'seed':seed}}
 if model.startswith('qwen3'):payload['think']=False
 t=time.perf_counter();r=request(base,'/api/chat',payload,timeout)
 return r,round(time.perf_counter()-t,3)
def main(args=None):
 p=argparse.ArgumentParser(description='30 cases x A/B x 3 Qwen; each one model-query + one model-answer')
 p.add_argument('--stage',choices=['pilot','main'],required=True)
 p.add_argument('--model',choices=['all',*MODELS],default='all')
 p.add_argument('--condition',choices=['all','A','B'],default='all')
 p.add_argument('--group',choices=['all','PARENT_AND_SALTS','COMPOUND_CLASS','MIXTURE'],default='all',help='한 번에 한 화학물질군만 실행; 결과는 전체와 동일한 파일에 누적')
 p.add_argument('--endpoint',default='http://127.0.0.1:11434')
 p.add_argument('--num-ctx',type=int,default=4096)
 p.add_argument('--num-predict-query',type=int,default=220)
 p.add_argument('--num-predict-reason',type=int,default=650)
 p.add_argument('--seed',type=int,default=20261120)
 p.add_argument('--timeout',type=int,default=260)
 p.add_argument('--force',action='store_true')
 p.add_argument('--limit',type=int,default=None)
 ns=p.parse_args(args)
 m=json.loads((DATA/'manifest.json').read_text(encoding='utf-8'))
 for file,key in [('cases_60.jsonl','cases_sha256'),('official_annex_2026_5_full.csv','annex_sha256'),('pilot_12_ids.json','pilot_sha256')]:
  if sha(DATA/file)!=m[key]:sys.exit('데이터 SHA256 불일치: '+file)
 if not DB.exists():build()
 with sqlite3.connect(DB) as con:
  if con.execute('select count(*) from annex').fetchone()[0]!=1451:sys.exit('DB 행 수 불일치')
 cases=load(DATA/'cases_60.jsonl')
 if len(cases)!=60:sys.exit('60문항 불일치')
 pilot=set(json.loads((DATA/'pilot_12_ids.json').read_text(encoding='utf-8')))
 chosen=[c for c in cases if (ns.stage=='main' or c['test_id'] in pilot) and (ns.condition=='all' or c['condition']==ns.condition) and (ns.group=='all' or c['group']==ns.group)]
 if ns.limit:chosen=chosen[:ns.limit]
 models=MODELS if ns.model=='all' else [ns.model]
 url=ns.endpoint.rstrip('/')
 try:installed={x['name']:x for x in request(url,'/api/tags',timeout=20)['models']}
 except Exception as e:sys.exit('Ollama 연결 실패: '+str(e))
 if any(x not in installed for x in models):sys.exit('모델 미설치. ollama list 참조')
 OUT.mkdir(exist_ok=True)
 for model in models:
  slug=model.replace(':','_');dst=OUT/f'{slug}__{ns.stage}.jsonl'
  settings={'model':model,'digest':installed[model].get('digest'),'num_ctx':ns.num_ctx,
   'query_tokens':ns.num_predict_query,'reason_tokens':ns.num_predict_reason,'seed':ns.seed,
   'cases_sha256':m['cases_sha256'],'annex_sha256':m['annex_sha256'],
   'search':'lexical_rank_fusion_v1','protocol':'v4_three_groups_components_mixture_article3'}
  settings_hash=hashlib.sha256(json.dumps(settings,sort_keys=True).encode()).hexdigest()
  if ns.force and dst.exists():dst.unlink()
  previous=load(dst)
  if any(x.get('settings_sha256')!=settings_hash for x in previous):sys.exit('실험 설정 충돌: 기존 파일을 백업하고 조건을 통일하세요')
  completed={x['test_id'] for x in previous if x['status'] in ('ok','invalid_query','invalid_answer')}
  if ns.stage=='main':
   for x in load(OUT/f'{slug}__pilot.jsonl'):
    if x.get('settings_sha256')!=settings_hash:sys.exit('pilot/main 설정 다름')
    if x['status'] in ('ok','invalid_query','invalid_answer') and x['test_id'] not in completed:
     with dst.open('a',encoding='utf-8') as f:f.write(json.dumps({**x,'stage':'main','reused_pilot':True},ensure_ascii=False)+'\n')
     completed.add(x['test_id'])
  print(f'[{model}] {len(chosen)}문항 중 기완료 {sum(c["test_id"] in completed for c in chosen)}',flush=True)
  try:
   with sqlite3.connect(DB) as con:
    con.row_factory=sqlite3.Row
    for j,c in enumerate(chosen,1):
     if c['test_id'] in completed:continue
     qt=rt=0;qraw=araw=None;queries=None;hits={};logs={};error=None;qr=ar=None
     component_ids=[x['component_id'] for x in c['components']]
     try:
      qr,qt=infer(url,model,qmessages(c),QUERY_SCHEMA,ns.num_predict_query,ns.num_ctx,ns.seed,ns.timeout)
      qraw=qr.get('message',{}).get('content','')
      queries=parse_queries(qraw,component_ids)
      for component in c['components']:
       cid=component['component_id']
       found,log=fused_search(con,(queries or {}).get(cid,[]),k=8 if len(c['components'])==1 else (4 if len(c['components'])==3 else 5),per_query=10)
       hits[cid]=[evidence(x) for x in found];logs[cid]=log
      ar,rt=infer(url,model,amessages(c,hits),ANSWER_SCHEMA,ns.num_predict_reason,ns.num_ctx,ns.seed,ns.timeout)
      araw=ar.get('message',{}).get('content','')
     except Exception as e:error=str(e)
     parsed=parse_answer(araw,c['test_id'],component_ids,c['scenario_kind']=='FORMULATED_MIXTURE')
     status='api_error' if error else ('invalid_query' if not queries else ('ok' if parsed else 'invalid_answer'))
     row={'test_id':c['test_id'],'case_id':c['case_id'],'condition':c['condition'],'model':model,'status':status,
       'stage':ns.stage,'reused_pilot':False,'settings_sha256':settings_hash,'model_digest':installed[model].get('digest'),
       'timestamp_utc':datetime.now(timezone.utc).isoformat(),'query_raw':qraw,'queries':queries,'retrieved_by_component':hits,
       'search_logs':logs,'answer_raw':araw,'answer_valid':bool(parsed),
       'query_seconds':qt,'reason_seconds':rt,'wall_seconds':round(qt+rt,3),'error':error,
       'query_eval_count':qr.get('eval_count') if qr else None,'reason_eval_count':ar.get('eval_count') if ar else None}
     with dst.open('a',encoding='utf-8',newline='\n') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush()
     completed.add(c['test_id'])
     print(f'{j:02d}/{len(chosen)} {c["test_id"]} {status} query={qt:.1f}s answer={rt:.1f}s',flush=True)
     if error:sys.exit('API 오류: 현재 문항까지 저장됐습니다. 동일 명령 재실행으로 복구: '+error)
  finally:
   try:request(url,'/api/generate',{'model':model,'prompt':'','keep_alive':0},timeout=50)
   except Exception:pass
 print('완료: python score_results.py')
if __name__=='__main__':main()
