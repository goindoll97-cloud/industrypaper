"""Run the independently reviewed 90-question B-only follow-up; never read Gold."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time

from prepare_b90 import ROOT, V4, assert_frozen, require
sys.path.insert(0, str(V4))
from run_retrieval import (MODELS, ADDITIONAL_MODELS, DB, build, load,
                           request, qmessages, amessages, infer,
                           parse_queries, parse_answer, answer_format)
from search_legal_db import fused_search, evidence

ALL_MODELS = [*MODELS, *ADDITIONAL_MODELS]
RESULTS = ROOT / "results_b90"


def main(argv=None):
    p = argparse.ArgumentParser(description="B 90문항(기존 30+신규 60) 독립 본실험")
    p.add_argument("--model",choices=["all",*ALL_MODELS],default="all")
    p.add_argument("--group",choices=["all","PARENT_AND_SALTS",
                       "COMPOUND_CLASS","MIXTURE"],default="all")
    p.add_argument("--limit",type=int,default=None,
                   help="파일을 보존한 상태로 일부만 실행; 같은 명령 재시작 가능")
    p.add_argument("--endpoint",default="http://127.0.0.1:11434")
    p.add_argument("--num-ctx",type=int,default=4096)
    p.add_argument("--num-predict-query",type=int,default=384)
    p.add_argument("--num-predict-reason",type=int,default=900)
    p.add_argument("--seed",type=int,default=20261120)
    p.add_argument("--timeout",type=int,default=480)
    args=p.parse_args(argv)
    if args.limit is not None and args.limit < 1:
        p.error("--limit는 1 이상이어야 합니다")
    try:
        cases,locked=assert_frozen(need_gold=False)
    except (ValueError,KeyError,FileNotFoundError) as exc:
        p.error(str(exc))
    selected=[c for c in cases if args.group=="all" or c["group"]==args.group]
    if args.limit is not None:
        selected=selected[:args.limit]
    models=ALL_MODELS if args.model=="all" else [args.model]
    try:
        installed={x["name"]:x for x in request(args.endpoint.rstrip("/"),
                                               "/api/tags",timeout=20)["models"]}
    except Exception as exc:
        p.error("Ollama 연결 실패: "+str(exc))
    for model in models:
        if model not in installed:
            p.error("모델 미설치: "+model+"; ollama list 참조")
        if not installed[model].get("digest"):
            p.error("모델 digest 누락으로 버전 동결 불가: "+model)
    if not DB.exists():
        build()
    with sqlite3.connect(DB) as connection:
        require(connection.execute("SELECT count(*) FROM annex").fetchone()[0]==1451,
                "공식 고시 DB 1,451행 불일치")
    RESULTS.mkdir(parents=True,exist_ok=True)
    for model in models:
        dest=RESULTS/(model.replace(":","_")+"__main.jsonl")
        settings={
            "model":model,"digest":installed[model]["digest"],
            "num_ctx":args.num_ctx,"query_tokens":args.num_predict_query,
            "reason_tokens":args.num_predict_reason,"seed":args.seed,
            "timeout":args.timeout,"cases_sha256":locked["cases_sha256"],
            "annex_sha256":locked["annex_sha256"],
            "search":"lexical_rank_fusion_v2_cas",
            "protocol":"b90_v1_B_only_same_v4_1_prompts",
        }
        shash=hashlib.sha256(json.dumps(settings,sort_keys=True).encode()).hexdigest()
        prior=load(dest)
        if len({x["test_id"] for x in prior})!=len(prior):
            p.error("기존 결과에 중복 test_id가 있습니다. 자동 덮어쓰기 금지: "+str(dest))
        if any(x.get("settings_sha256")!=shash for x in prior):
            p.error("기존 결과의 모델 설정 또는 입력 데이터가 다릅니다: "+str(dest))
        if any(x.get("test_id") not in {c["test_id"] for c in cases} for x in prior):
            p.error("이전 결과에 현 검증셋 밖의 문항 존재")
        complete={x["test_id"] for x in prior
                  if x["status"] in ("ok","invalid_query","invalid_answer")}
        # API 오류는 결과 파일에 남기고 중단합니다. 원본을 삭제하지 않고
        # 재실행할 수 있도록 새 시도는 이전 오류 행을 덮어쓰지 않습니다.
        failures=[x for x in prior if x["status"]=="api_error"]
        if failures:
            p.error("이전 API 실패 행이 있습니다. 기록 보존 후 별도 실험 검토 필요: "+str(dest))
        print(f"[{model}] {len(selected)}문항 / 완료 {sum(c['test_id'] in complete for c in selected)}",flush=True)
        try:
            with sqlite3.connect(DB) as con:
                con.row_factory=sqlite3.Row
                for j,case in enumerate(selected,1):
                    tid=case["test_id"]
                    if tid in complete:continue
                    ids=[x["component_id"] for x in case["components"]]
                    try:
                        query_obj,qt=infer(args.endpoint.rstrip("/"),model,qmessages(case),
                                           __import__("run_retrieval").QUERY_SCHEMA,
                                           args.num_predict_query,args.num_ctx,
                                           args.seed,args.timeout)
                        query_raw=query_obj.get("message",{}).get("content","")
                        parsed_queries=parse_queries(query_raw,ids,tid)
                        found_by_cid={}
                        search_logs={}
                        for component in case["components"]:
                            cid=component["component_id"]
                            n=len(case["components"])
                            items,logs=fused_search(
                                con,(parsed_queries or {}).get(cid,[]),
                                k=8 if n==1 else (5 if n==2 else 4),per_query=10)
                            found_by_cid[cid]=[evidence(x) for x in items]
                            search_logs[cid]=logs
                        answer_obj,rt=infer(args.endpoint.rstrip("/"),model,
                                            amessages(case,found_by_cid),
                                            answer_format(case),
                                            args.num_predict_reason,args.num_ctx,
                                            args.seed,args.timeout)
                        answer_raw=answer_obj.get("message",{}).get("content","")
                    except Exception as exc:
                        print("API 오류 (현재 문항은 저장하지 않음):",tid,str(exc))
                        raise SystemExit("모델 또는 RAM 문제 해결 후 동일 명령으로 재시도")
                    ans=parse_answer(answer_raw,tid,ids,case["group"]=="MIXTURE")
                    status="invalid_query" if not parsed_queries else (
                        "ok" if ans else "invalid_answer")
                    row={
                        "test_id":tid,"case_id":case["case_id"],
                        "condition":"B","model":model,"status":status,
                        "stage":"main","settings_sha256":shash,
                        "model_digest":installed[model]["digest"],
                        "protocol_config":settings,
                        "timestamp_utc":datetime.now(timezone.utc).isoformat(),
                        "query_raw":query_raw,"queries":parsed_queries,
                        "retrieved_by_component":found_by_cid,
                        "search_logs":search_logs,
                        "answer_raw":answer_raw,"answer_valid":bool(ans),
                        "query_seconds":qt,"reason_seconds":rt,
                        "wall_seconds":round(qt+rt,3),"error":None,
                        "query_eval_count":query_obj.get("eval_count"),
                        "reason_eval_count":answer_obj.get("eval_count"),
                    }
                    with dest.open("a",encoding="utf-8",newline="\n") as fp:
                        fp.write(json.dumps(row,ensure_ascii=False)+"\n")
                        fp.flush()
                    complete.add(tid)
                    print(f"{j:02d}/{len(selected)} {tid} {status} "
                          f"query={qt:.1f}s reason={rt:.1f}s",flush=True)
        finally:
            try:
                request(args.endpoint.rstrip("/"),"/api/generate",
                        {"model":model,"prompt":"","keep_alive":0},timeout=50)
            except Exception:
                pass
    print("완료: python score_b90.py 로 본실험 90문항 채점")


if __name__=="__main__":
    main()
