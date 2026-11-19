"""Offline-free standard-library Ollama benchmark; Gold is never opened by this program."""
from __future__ import annotations
import argparse, hashlib, json, time, sys, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data'
RESULTS=ROOT/'results'
MODELS=['qwen2.5:3b','qwen3:4b-instruct','qwen3.5:4b']
FIELDS=['test_id','direct_cas_match','covered_by_clause','reasoning_category','relevant_entry_id','relevant_sub_number','reason_ko']
CATS=['DIRECT_SPECIFIC','GROUP_INCLUDED','EXPLICIT_EXCEPTION','NOT_COVERED']
SCHEMA={'type':'object','properties':{
    'test_id':{'type':'string'},'direct_cas_match':{'type':'boolean'},
    'covered_by_clause':{'type':'boolean'},
    'reasoning_category':{'type':'string','enum':CATS},
    'relevant_entry_id':{'type':['string','null']},
    'relevant_sub_number':{'type':['integer','null']},
    'reason_ko':{'type':'string'}},'required':FIELDS,'additionalProperties':False}

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):
    if not p.exists():return []
    return [json.loads(s) for s in p.read_text(encoding='utf-8').splitlines() if s.strip()]
def request(url,obj=None,timeout=180):
    payload=json.dumps(obj,ensure_ascii=False).encode('utf-8') if obj is not None else None
    rq=urllib.request.Request(url,data=payload,headers={'Content-Type':'application/json'} if payload else {})
    with urllib.request.urlopen(rq,timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))
def output_ok(text,tid):
    try:obj=json.loads(text)
    except (ValueError,TypeError):return False
    return (isinstance(obj,dict) and set(obj)==set(FIELDS) and obj['test_id']==tid and
            type(obj['direct_cas_match']) is bool and type(obj['covered_by_clause']) is bool and
            obj['reasoning_category'] in CATS and
            (obj['relevant_entry_id'] is None or type(obj['relevant_entry_id']) is str) and
            (obj['relevant_sub_number'] is None or type(obj['relevant_sub_number']) is int) and
            type(obj['reason_ko']) is str)

def main(argv=None):
    ap=argparse.ArgumentParser(description='20 compounds x 2 conditions x 3 Qwen versions = 120 inferences')
    ap.add_argument('--stage',choices=['pilot','main'],required=True)
    ap.add_argument('--model',choices=['all',*MODELS],default='all')
    ap.add_argument('--endpoint',default='http://127.0.0.1:11434')
    ap.add_argument('--timeout',type=int,default=180)
    ap.add_argument('--num-ctx',type=int,default=3072)
    ap.add_argument('--num-predict',type=int,default=220)
    ap.add_argument('--temperature',type=float,default=0)
    ap.add_argument('--seed',type=int,default=20261119)
    ap.add_argument('--force',action='store_true')
    ap.add_argument('--limit',type=int,default=None,help='Debug only; incomplete runs are not final')
    args=ap.parse_args(argv)
    m=json.loads((DATA/'manifest.json').read_text(encoding='utf-8'))
    paths={'prompts_sha256':DATA/'prompts_40.jsonl','pilot_ids_sha256':DATA/'pilot_8_ids.json'}
    if any(digest(p)!=m[k] for k,p in paths.items()):sys.exit('SHA 불일치. 평가자료가 변경됐습니다.')
    cases=load(paths['prompts_sha256'])
    if len(cases)!=40 or len({c['test_id'] for c in cases})!=40:sys.exit('40문항 무결성 오류')
    pilot=set(json.loads(paths['pilot_ids_sha256'].read_text(encoding='utf-8')))
    if len(pilot)!=8:sys.exit('pilot 8문항 오류')
    subset=cases if args.stage=='main' else [c for c in cases if c['test_id'] in pilot]
    if args.limit:subset=subset[:args.limit]
    models=MODELS if args.model=='all' else [args.model]
    base=args.endpoint.rstrip('/')
    try:tags=request(base+'/api/tags',timeout=20)['models']
    except Exception as exc:sys.exit(f'Ollama 연결 실패: {exc}')
    installed={r['name']:r for r in tags}
    if any(model not in installed for model in models):sys.exit('설치된 모델 확인: ollama list')
    RESULTS.mkdir(exist_ok=True)
    for model in models:
        name=model.replace(':','_').replace('/','_')
        path=RESULTS/f'{name}__{args.stage}.jsonl'
        setting={'model':model,'digest':installed[model].get('digest'),'num_ctx':args.num_ctx,
                 'num_predict':args.num_predict,'temperature':args.temperature,
                 'seed':args.seed,'schema':True,'prompt_hash':m['prompts_sha256']}
        settings_sha=hashlib.sha256(json.dumps(setting,sort_keys=True).encode()).hexdigest()
        if args.force and path.exists():path.unlink()
        past=load(path)
        if any(x.get('settings_sha256')!=settings_sha for x in past):sys.exit('실험 조건 변경! 새 폴더에서 실행하거나 --force 사용')
        completed={x['test_id'] for x in past if x.get('status')=='ok'}
        if args.stage=='main':
            pilot_path=RESULTS/f'{name}__pilot.jsonl'
            prior=load(pilot_path)
            if any(x.get('settings_sha256')!=settings_sha for x in prior):sys.exit('pilot와 main 설정 불일치')
            for x in prior:
                if x.get('status')=='ok' and x['test_id'] not in completed:
                    with path.open('a',encoding='utf-8') as out:
                        out.write(json.dumps({**x,'stage':'main','reused_pilot':True},ensure_ascii=False)+'\n')
                    completed.add(x['test_id'])
        print(f'\n{model}: {len(subset)}문항 중 기존 완료 {len(completed)}문항',flush=True)
        for no,c in enumerate(subset,1):
            if c['test_id'] in completed:continue
            payload={'model':model,'messages':[{'role':'system','content':c['system_prompt']},
                                               {'role':'user','content':c['user_prompt']}],
                     'stream':False,'format':SCHEMA,'keep_alive':'5m',
                     'options':{'num_ctx':args.num_ctx,'num_predict':args.num_predict,
                                'temperature':args.temperature,'seed':args.seed}}
            if model.startswith('qwen3'):payload['think']=False
            started=time.perf_counter();reply=None;error=None
            try:reply=request(base+'/api/chat',payload,timeout=args.timeout)
            except Exception as e:error=str(e)
            dt=round(time.perf_counter()-started,3)
            raw=reply.get('message',{}).get('content','') if reply else ''
            row={'test_id':c['test_id'],'case_id':c['case_id'],'condition':c['condition'],
                 'stage':args.stage,'model':model,'timestamp_utc':datetime.now(timezone.utc).isoformat(),
                 'settings_sha256':settings_sha,'prompt_sha256':c['prompt_sha256'],
                 'status':'ok' if reply else 'api_error','json_valid':output_ok(raw,c['test_id']),
                 'output_text':raw,'api_error':error,'wall_seconds':dt,'reused_pilot':False,
                 'prompt_eval_count':reply.get('prompt_eval_count') if reply else None,
                 'eval_count':reply.get('eval_count') if reply else None,
                 'eval_duration_ns':reply.get('eval_duration') if reply else None,
                 'model_digest':installed[model].get('digest')}
            with path.open('a',encoding='utf-8',newline='\n') as out:
                out.write(json.dumps(row,ensure_ascii=False)+'\n');out.flush()
            if reply:completed.add(c['test_id'])
            print(f"{no:02d}/{len(subset)} {c['test_id']} : {dt:.1f}s JSON={'OK' if row['json_valid'] else 'FAIL'}",flush=True)
            if error:sys.exit(f'API 실패(중간 결과 저장): {error}')
        try:request(base+'/api/generate',{'model':model,'prompt':'','keep_alive':0},timeout=40)
        except Exception:pass
    print('완료. python score_results.py 실행')

if __name__=='__main__':main()
