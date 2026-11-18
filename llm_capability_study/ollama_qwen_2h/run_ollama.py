"""Reproducible, resumable 72-question Qwen-generation benchmark using local Ollama.
Pilot responses are incorporated into main without duplicate API calls.
No Gold is read or sent by this script. Python standard library only.
"""
from __future__ import annotations
import argparse, hashlib, json, sys, time, urllib.error, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data'
RESULTS=ROOT/'results'
MODELS=['qwen2.5:3b','qwen3:4b-instruct','qwen3.5:4b']
FIELDS=['test_id','listed_in_annex','regulatory_entry_id','official_name_ko','acute_applies',
        'chronic_applies','ecological_applies','any_hazard_applies','reason_ko']
BOOL=['listed_in_annex','acute_applies','chronic_applies','ecological_applies','any_hazard_applies']
SCHEMA={'type':'object','properties':{
    'test_id':{'type':'string'},
    'listed_in_annex':{'type':'boolean'},
    'regulatory_entry_id':{'type':['string','null']},
    'official_name_ko':{'type':['string','null']},
    'acute_applies':{'type':'boolean'},
    'chronic_applies':{'type':'boolean'},
    'ecological_applies':{'type':'boolean'},
    'any_hazard_applies':{'type':'boolean'},
    'reason_ko':{'type':'string'}},'required':FIELDS,'additionalProperties':False}


def sha256(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def jsonl(path):
    if not path.exists():return []
    return [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines() if s.strip()]

def send_json(url,payload=None,timeout=180):
    data=None if payload is None else json.dumps(payload,ensure_ascii=False).encode('utf-8')
    req=urllib.request.Request(url,data=data,headers={'Content-Type':'application/json'} if data else {})
    try:
        with urllib.request.urlopen(req,timeout=timeout) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'HTTP {e.code}: '+e.read().decode('utf-8',errors='replace')[:500]) from e

def valid_json_answer(raw,test_id):
    try:o=json.loads(raw)
    except (ValueError,TypeError):return False
    return (isinstance(o,dict) and set(o)==set(FIELDS) and o.get('test_id')==test_id and
            all(type(o[k]) is bool for k in BOOL) and
            all(o[k] is None or type(o[k]) is str for k in ('regulatory_entry_id','official_name_ko')) and
            type(o['reason_ko']) is str)

def main(args=None):
    ap=argparse.ArgumentParser(description='RTX 2060: 36 CAS x 2 cases x 3 Qwen generations = 216 calls')
    ap.add_argument('--stage',choices=['pilot','main'],required=True)
    ap.add_argument('--model',choices=['all',*MODELS],default='all')
    ap.add_argument('--endpoint',default='http://localhost:11434')
    ap.add_argument('--timeout',type=int,default=180)
    ap.add_argument('--num-ctx',type=int,default=3072)
    ap.add_argument('--num-predict',type=int,default=240)
    ap.add_argument('--temperature',type=float,default=0.0)
    ap.add_argument('--seed',type=int,default=20261118)
    ap.add_argument('--max-attempts',type=int,default=2)
    ap.add_argument('--no-schema',action='store_true',help='Only if the Ollama server rejects JSON Schema')
    ap.add_argument('--force',action='store_true',help='Start fresh, deleting this stage output only')
    ap.add_argument('--limit',type=int,default=None,help='Debug only; do not report partial run as full experiment')
    ns=ap.parse_args(args)
    if ns.limit is not None and ns.limit<1:ap.error('--limit must be >=1')
    if ns.num_predict<100:ap.error('--num-predict too small for full JSON')
    manifest=json.loads((DATA/'manifest.json').read_text(encoding='utf-8'))
    prompt_path=DATA/'prompts_72.jsonl'
    pilot_path=DATA/'pilot_6_ids.json'
    if sha256(prompt_path)!=manifest['prompts_sha256'] or sha256(pilot_path)!=manifest['pilot_ids_sha256']:
        ap.error('입력 자료 해시 불일치. 실험 중단')
    cases=jsonl(prompt_path)
    if len(cases)!=72 or len({x['test_id'] for x in cases})!=72:ap.error('Expected 72 unique cases')
    pilot=set(json.loads(pilot_path.read_text(encoding='utf-8')))
    if len(pilot)!=6:ap.error('Expected 6 pilot cases')
    chosen=[c for c in cases if ns.stage=='main' or c['test_id'] in pilot]
    if ns.limit:chosen=chosen[:ns.limit]
    models=MODELS if ns.model=='all' else [ns.model]
    url=ns.endpoint.rstrip('/')
    try:tags=send_json(url+'/api/tags',timeout=20).get('models',[])
    except Exception as e:sys.exit(f'Ollama API 연결 실패: {e}\nollama list 를 확인하세요.')
    installed={r.get('name'):r for r in tags}
    missing=[m for m in models if m not in installed]
    if missing:sys.exit('다운로드되지 않은 모델: '+', '.join(missing))
    try:server_version=send_json(url+'/api/version',timeout=10).get('version')
    except Exception:server_version=None
    RESULTS.mkdir(parents=True,exist_ok=True)
    for model in models:
        slug=model.replace(':','_').replace('/','_')
        dst=RESULTS/f'{slug}__{ns.stage}.jsonl'
        settings={'model':model,'model_digest':installed[model].get('digest'),
                  'num_ctx':ns.num_ctx,'num_predict':ns.num_predict,'temperature':ns.temperature,
                  'seed':ns.seed,'schema':not ns.no_schema,'prompts_sha256':manifest['prompts_sha256']}
        setting_hash=hashlib.sha256(json.dumps(settings,sort_keys=True).encode('utf-8')).hexdigest()
        if ns.force and dst.exists():dst.unlink()
        previous=jsonl(dst)
        if any(row.get('settings_sha256')!=setting_hash for row in previous):
            sys.exit(f'{dst.name} 기존 실행 설정 충돌. 실험조건 변경 시 폴더를 분리하거나 --force를 명시하세요.')
        done={row['test_id'] for row in previous if row.get('status')=='ok'}
        # Pilot results count as main responses, preserving exact inference settings and model digest.
        if ns.stage=='main':
            pilot_file=RESULTS/f'{slug}__pilot.jsonl'
            prior_pilot=jsonl(pilot_file)
            for row in prior_pilot:
                if row.get('settings_sha256')!=setting_hash:
                    sys.exit(f'{model}: 예비실험 설정과 본실험 설정이 다릅니다. 동일 조건으로 실행하세요.')
                if row.get('status')=='ok' and row['test_id'] not in done:
                    saved={**row,'stage':'main','reused_pilot':True}
                    with dst.open('a',encoding='utf-8',newline='\n') as out:
                        out.write(json.dumps(saved,ensure_ascii=False)+'\n')
                    done.add(row['test_id'])
        print(f'\n[{model}] {ns.stage}: 총 {len(chosen)}문항, 기존/예비에서 확보 {len(done)}건',flush=True)
        for idx,case in enumerate(chosen,1):
            if case['test_id'] in done:continue
            body={'model':model,'messages':[{'role':'system','content':case['system_prompt']},
                                             {'role':'user','content':case['user_prompt']}],
                  'stream':False,'format':'json' if ns.no_schema else SCHEMA,'keep_alive':'5m',
                  'options':{'num_ctx':ns.num_ctx,'num_predict':ns.num_predict,
                             'temperature':ns.temperature,'seed':ns.seed}}
            if model.startswith('qwen3'):body['think']=False
            err=None;response=None;started=time.perf_counter()
            for attempt in range(ns.max_attempts):
                try:response=send_json(url+'/api/chat',body,timeout=ns.timeout);err=None;break
                except Exception as exc:
                    err=str(exc)
                    if attempt+1<ns.max_attempts:time.sleep(min(2**(attempt+1),8))
            elapsed=round(time.perf_counter()-started,3)
            content=response.get('message',{}).get('content','') if response else ''
            row={'test_id':case['test_id'],'model':model,'stage':ns.stage,
                 'timestamp_utc':datetime.now(timezone.utc).isoformat(),
                 'settings_sha256':setting_hash,'prompt_sha256':case['prompt_sha256'],
                 'model_digest':installed[model].get('digest'),'ollama_version':server_version,
                 'status':'ok' if response is not None else 'api_error',
                 'json_valid':valid_json_answer(content,case['test_id']),
                 'output_text':content,'api_error':err,'wall_seconds':elapsed,
                 'prompt_eval_count':response.get('prompt_eval_count') if response else None,
                 'eval_count':response.get('eval_count') if response else None,
                 'possible_context_truncation':bool(response and response.get('prompt_eval_count',0)+ns.num_predict>=ns.num_ctx),
                 'reused_pilot':False}
            with dst.open('a',encoding='utf-8',newline='\n') as out:
                out.write(json.dumps(row,ensure_ascii=False)+'\n');out.flush()
            if response is not None:done.add(case['test_id'])
            print(f' {idx:02d}/{len(chosen)} {case["test_id"]}: {row["status"]}, JSON={row["json_valid"]}, {elapsed:.1f}s',flush=True)
            if response is None:sys.exit('API 오류: 결과 저장됨. 문제 해결 후 명령 재실행(성공 사례 자동 건너뜀).')
        print(f'저장완료: {dst}',flush=True)
        try:send_json(url+'/api/generate',{'model':model,'prompt':'','keep_alive':0},timeout=60)
        except Exception:pass
    print('\n완료. 본실험 결과는 python score_results.py 로 채점하세요.')

if __name__=='__main__':main()
