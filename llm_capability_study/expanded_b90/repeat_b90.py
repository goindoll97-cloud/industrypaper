"""Fresh repeated B90 benchmark: fixed deterministic settings and real timings.

Separate from single-run results and the frozen original protocol. No Gold
read during inference. Each repeat runs all 90 B cases, with cold model
unload before each model block; resume skips only already recorded cases.
The scoring phase reads the corrected local provisional key.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
import platform
from pathlib import Path
import sqlite3
import statistics as st
import subprocess
import sys
import time

from prepare_b90 import ROOT, V4, require, sha
from prepare_provisional_b90 import assert_provisional
from run_b90 import ALL_MODELS
from run_retrieval import (DB, QUERY_SCHEMA, amessages, answer_format, build,
                           infer, load, parse_answer, parse_queries, qmessages, request)
from search_legal_db import evidence, fused_search
from score_audit_v4 import inspect_run
from score_b90 import METRICS, write_csv

OUT=ROOT/"results_b90_repeated"
PROTOCOL="b90_repeat_v1_fixed_temperature0_seed20261120"
SETTINGS=dict(num_ctx=4096,query_tokens=384,reason_tokens=900,
              temperature=0,seed=20261120,timeout=480,
              search="lexical_rank_fusion_v2_cas",keep_alive="5m",think=False)
TIMES=("query_seconds","retrieval_seconds","reason_seconds","task_seconds")
STATUS=("ok","invalid_query","invalid_answer")


def now():
    return datetime.now(timezone.utc).isoformat()


def digest_settings(meta):
    return hashlib.sha256(json.dumps(meta,sort_keys=True).encode()).hexdigest()


def save_json(path,data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")


def append(path,row):
    with path.open("a",encoding="utf-8",newline="\n") as fp:
        fp.write(json.dumps(row,ensure_ascii=False)+"\n")
        fp.flush()


def repeat_dir(root,r):
    return root/f"repeat_{r:02d}"


def raw_path(root,r,model):
    return repeat_dir(root,r)/(model.replace(":","_")+"__main.jsonl")


def model_order(r):
    # Rotate starting model to reduce systematic ordering effects.
    n=(r-1)%len(ALL_MODELS)
    return ALL_MODELS[n:]+ALL_MODELS[:n]


def code_hashes():
    from prepare_b90 import source_code_sha
    # Relative paths normalized only in this new manifest, which is independent
    # of the original frozen Gold manifest's platform-specific path keys.
    return {**{k.replace("\\","/"):v for k,v in source_code_sha().items()},
            "expanded_b90/repeat_b90.py":sha(Path(__file__))}


def environment(base):
    installed={x["name"]:x["digest"] for x in request(base,"/api/tags",timeout=20)["models"]
               if x.get("digest")}
    version=request(base,"/api/version",timeout=20).get("version")
    require(bool(version),"Ollama 버전 확인 불가")
    gpu=None
    try:
        gpu=subprocess.check_output(
            ["nvidia-smi","--query-gpu=name,driver_version,memory.total",
             "--format=csv,noheader"],text=True,timeout=10).strip()
    except (OSError,subprocess.SubprocessError):
        pass
    return installed,{"os":platform.platform(),"processor":platform.processor(),
                      "python":platform.python_version(),"ollama":version,
                      "gpu_driver_memory":gpu}


def init_run(root,repeats,locked,base,models):
    installed,env=environment(base)
    for m in models:
        require(m in installed,"Ollama 모델 미설치: "+m+" (ollama list 확인)")
    target=root/"repeat_manifest.json"
    head={"protocol":PROTOCOL,"repeats":repeats,"models":ALL_MODELS,
          "cases_sha256":locked["cases_sha256"],"annex_sha256":locked["annex_sha256"],
          "settings":SETTINGS,"code_sha256":code_hashes(),"environment":env,
          "endpoint":base}
    if target.exists():
        meta=json.loads(target.read_text(encoding="utf-8"))
        require(all(meta.get(k)==v for k,v in head.items()),
                "반복 실험의 설정·입력·환경·코드 변경 감지: 기존 결과와 혼합 금지")
        for m in models:
            if m in meta["model_digests"]:
                require(meta["model_digests"][m]==installed[m],
                        "모델 digest 변경: "+m)
    else:
        require(not root.exists() or not any(root.iterdir()),
                "manifest 없는 기존 결과 폴더 발견; 원본 보존 후 확인")
        root.mkdir(parents=True,exist_ok=True)
        meta={**head,"created_utc":now(),"model_digests":{}}
    for m in models:
        meta["model_digests"][m]=installed[m]
    save_json(target,meta)
    return meta


def config(meta,r,model):
    return {"protocol":meta["protocol"],"repeat":r,"model":model,
            "digest":meta["model_digests"][model],
            "cases_sha256":meta["cases_sha256"],"annex_sha256":meta["annex_sha256"],
            **meta["settings"]}


def verified_rows(path,conf,cases,complete=False):
    rows=load(path)
    by_id={c["test_id"]:c for c in cases}
    require(len(rows)==len({z["test_id"] for z in rows}),"중복 응답: "+str(path))
    if complete:
        require(len(rows)==len(cases),"완료되지 않은 반복: "+str(path))
    for x in rows:
        tid=x["test_id"]
        require(tid in by_id and x["case_id"]==by_id[tid]["case_id"]
                and x["condition"]=="B" and x["model"]==conf["model"]
                and x["repeat"]==conf["repeat"] and x["status"] in STATUS
                and x["protocol_config"]==conf
                and x["model_digest"]==conf["digest"]
                and x["settings_sha256"]==digest_settings(conf),
                "기존 원본 응답의 입력/설정 오류: "+str(path))
        require(all(isinstance(x.get(k),(int,float)) and
                    math.isfinite(x[k]) and x[k]>=0 for k in TIMES),
                "시간 측정값 오류: "+str(path))
    return rows


def unload(base,model):
    # No timed inference is performed here; the model's unload is separately
    # recorded at the block level. Check actual absence before a cold start.
    request(base,"/api/generate",{"model":model,"prompt":"","keep_alive":0},timeout=60)
    active=request(base,"/api/ps",timeout=20).get("models",[])
    require(not any(x.get("name")==model or x.get("model")==model for x in active),
            "모델 언로드 실패: "+model)


def run_case(base,con,case,conf,block_id,first):
    tid=case["test_id"]
    ids=[x["component_id"] for x in case["components"]]
    start=time.perf_counter()
    qr,qt=infer(base,conf["model"],qmessages(case),QUERY_SCHEMA,
                conf["query_tokens"],conf["num_ctx"],conf["seed"],conf["timeout"])
    qraw=qr.get("message",{}).get("content","")
    queries=parse_queries(qraw,ids,tid)
    found={}
    logs={}
    s=time.perf_counter()
    for cid in ids:
        k=8 if len(ids)==1 else (5 if len(ids)==2 else 4)
        items,log=fused_search(con,(queries or {}).get(cid,[]),k=k,per_query=10)
        found[cid]=[evidence(x) for x in items]
        logs[cid]=log
    search_s=time.perf_counter()-s
    ar,rt=infer(base,conf["model"],amessages(case,found),answer_format(case),
                conf["reason_tokens"],conf["num_ctx"],conf["seed"],conf["timeout"])
    araw=ar.get("message",{}).get("content","")
    ans=parse_answer(araw,tid,ids,case["group"]=="MIXTURE")
    status="invalid_query" if not queries else ("ok" if ans else "invalid_answer")
    elapsed=time.perf_counter()-start
    row={"test_id":tid,"case_id":case["case_id"],"condition":"B",
         "model":conf["model"],"repeat":conf["repeat"],"status":status,"stage":"main",
         "settings_sha256":digest_settings(conf),"model_digest":conf["digest"],
         "protocol_config":conf,"timestamp_utc":now(),"block_id":block_id,
         "cold_first_case":first,"query_raw":qraw,"queries":queries,
         "retrieved_by_component":found,"search_logs":logs,"answer_raw":araw,
         "answer_valid":bool(ans),"query_seconds":qt,"reason_seconds":rt,
         "retrieval_seconds":round(search_s,6),"task_seconds":round(elapsed,6),
         "wall_seconds":round(qt+rt,3),"error":None}
    for name,response in (("query",qr),("reason",ar)):
        for key in ("total_duration","load_duration","prompt_eval_duration","eval_duration"):
            val=response.get(key)
            row[f"{name}_{key}_seconds"]=val/1e9 if isinstance(val,(int,float)) else None
        for key in ("prompt_eval_count","eval_count"):
            row[f"{name}_{key}"]=response.get(key)
    return row


def run(args):
    cases,locked=assert_provisional(need_gold=False)
    root=Path(args.out_dir)
    models=ALL_MODELS if args.model=="all" else [args.model]
    base=args.endpoint.rstrip("/")
    meta=init_run(root,args.repeats,locked,base,models)
    # Regenerate the index using the frozen official source for each invocation.
    # Setup time is NOT part of model execution time.
    build()
    with sqlite3.connect(DB) as con:
        con.row_factory=sqlite3.Row
        for r in range(1,args.repeats+1):
            for m in model_order(r):
                if m not in models:
                    continue
                path=raw_path(root,r,m)
                path.parent.mkdir(parents=True,exist_ok=True)
                conf=config(meta,r,m)
                prior=verified_rows(path,conf,cases)
                done={x["test_id"] for x in prior}
                pending=[c for c in cases if c["test_id"] not in done]
                if not pending:
                    print(f"[{r}/{args.repeats}] {m}: 이미 90문항 완료",flush=True)
                    continue
                if args.limit is not None:
                    pending=pending[:args.limit]
                started=now()
                block_id=f"{r:02d}/{m}/{started}"
                log=root/"blocks.jsonl"
                # Record start before unloading, so an interrupted block is visible.
                append(log,dict(event="start",repeat=r,model=m,block_id=block_id,
                                timestamp_utc=started,prior_completed=len(done)))
                t=time.perf_counter()
                completed=0
                before=None
                active=None
                after=None
                problem=None
                try:
                    unload(base,m)
                    before=time.perf_counter()-t
                    active_start=time.perf_counter()
                    try:
                        for i,c in enumerate(pending):
                            row=run_case(base,con,c,conf,block_id,i==0)
                            append(path,row)
                            completed+=1
                            print(f"[반복 {r}/{args.repeats}] {m} "
                                  f"{len(done)+completed}/90 {c['test_id']} "
                                  f"{row['status']} "
                                  f"검색어 {row['query_seconds']:.2f}s / "
                                  f"검색 {row['retrieval_seconds']:.3f}s / "
                                  f"판단 {row['reason_seconds']:.2f}s / "
                                  f"전체 {row['task_seconds']:.2f}s",flush=True)
                    finally:
                        active=time.perf_counter()-active_start
                except BaseException as exc:
                    problem=type(exc).__name__+": "+str(exc)
                    raise
                finally:
                    u=time.perf_counter()
                    try:
                        unload(base,m)
                        after=time.perf_counter()-u
                    except Exception as exc:
                        if problem is None:
                            problem="cleanup: "+str(exc)
                    append(log,dict(event="end",repeat=r,model=m,block_id=block_id,
                                    timestamp_utc=now(),completed=completed,
                                    active_block_seconds=active,
                                    pre_unload_seconds=before,post_unload_seconds=after,
                                    wall_block_seconds=time.perf_counter()-t,error=problem))
                    print(f"[{m}, 반복 {r}] 이번 실행 {completed}문항, "
                          f"작업 블록 {active if active is not None else 0:.2f}s",flush=True)
                if problem:
                    raise RuntimeError(problem)
    print("완료. 모두 실행한 후 python repeat_b90.py --score --repeats "
          +str(args.repeats))


def mean_sd(values):
    require(bool(values),"빈 통계 자료")
    return st.mean(values), st.stdev(values) if len(values)>1 else None


def signature(raw,case):
    """Structured decision agreement; exclude free-text rationale and search wording."""
    ans=parse_answer(raw["answer_raw"],case["test_id"],
                     [c["component_id"] for c in case["components"]],
                     case["group"]=="MIXTURE")
    if not ans:
        return None
    return json.dumps({"components":sorted(ans["components"],key=lambda x:x["component_id"]),
                       "all_components_designated":ans["all_components_designated"]},
                      sort_keys=True,ensure_ascii=False)


def per_repeat_stats(rows,models,r,blocks):
    result=[]
    for m in models:
        rs=[x for x in rows if x["model"]==m]
        require(len(rs)==90,"반복별 90문항 누락")
        d={"repeat":r,"model":m,"n":len(rs),
           "cold_first_cases":sum(x["cold_first_case"] for x in rs)}
        for _,k in METRICS:
            d[k+"_n"]=sum(x[k] for x in rs)
            d[k+"_pct"]=100*d[k+"_n"]/len(rs)
        for k in TIMES:
            vals=[x[k] for x in rs]
            av,sd=mean_sd(vals)
            d[k+"_total"]=sum(vals)
            d[k+"_mean"]=av
            d[k+"_sd"]=sd
            d[k+"_median"]=st.median(vals)
        warm=[x["task_seconds"] for x in rs if not x["cold_first_case"]]
        d["warm_task_seconds_mean"]=st.mean(warm) if warm else None
        relevant=[x for x in blocks if x.get("repeat")==r and x.get("model")==m]
        starts={x["block_id"] for x in relevant if x["event"]=="start"}
        ends=[x for x in relevant if x["event"]=="end"]
        ends_ids={x["block_id"] for x in ends}
        d["block_count"]=len(starts)
        # A missing end event (power loss etc.) prevents claiming complete
        # wall time. Task time totals still use actual measured complete cases.
        d["block_timing_complete"]=int(bool(starts) and starts==ends_ids and
                                      len(ends)==len(ends_ids) and
                                      all(x.get("error") is None for x in ends))
        d["active_block_seconds_total"]=(sum(x["active_block_seconds"] for x in ends)
            if d["block_timing_complete"] and all(x.get("active_block_seconds") is not None
                                                  for x in ends) else None)
        d["wall_block_seconds_total"]=(sum(x["wall_block_seconds"] for x in ends)
                                        if d["block_timing_complete"] else None)
        result.append(d)
    return result


def summarize(rep_stats,case_scores,components,signatures,cases,repeats):
    model_summary=[]
    agreements=[]
    strata=[]
    for m in ALL_MODELS:
        rr=[x for x in rep_stats if x["model"]==m]
        require(len(rr)==repeats,"반복 수 불일치")
        z={"model":m,"repeats":repeats,"questions_per_repeat":90,
           "total_evaluations":90*repeats}
        for field in [k+"_pct" for _,k in METRICS]+[k+"_total" for k in TIMES]+[
                k+"_mean" for k in TIMES]+["warm_task_seconds_mean",
                "active_block_seconds_total","wall_block_seconds_total"]:
            vals=[x[field] for x in rr if x[field] is not None]
            mu,sd=mean_sd(vals) if vals else (None,None)
            z[field+"_mean_across_repeats"]=mu
            z[field+"_sd_across_repeats"]=sd
            z[field+"_repeats_observed"]=len(vals)
        # Total active case duration across all repeats is a measured sum,
        # not elapsed calendar time or an estimate.
        z["all_repeats_task_seconds"]=sum(x["task_seconds_total"] for x in rr)
        ar=[]
        by_case=defaultdict(list)
        for x in case_scores:
            if x["model"]==m:
                by_case[x["test_id"]].append(x)
        for c in cases:
            tid=c["test_id"]
            xs=sorted(by_case[tid],key=lambda x:x["repeat"])
            ss=[signatures[(m,r,tid)] for r in range(1,repeats+1)]
            valid=sum(x is not None for x in ss)
            exact=[x["strict_case_exact"] for x in xs]
            n_unique=len(set(x for x in ss if x is not None))
            a=dict(model=m,test_id=tid,group=c["group"],difficulty=c["difficulty"],
                   repeats=repeats,valid_responses=valid,distinct_valid_decisions=n_unique,
                   all_valid_identical=int(valid==repeats and n_unique==1),
                   all_invalid=int(valid==0),all_correct=int(all(exact)),
                   all_incorrect=int(not any(exact)),
                   correctness_constant=int(len(set(exact))==1),
                   correct_repeats=sum(exact))
            ar.append(a)
        agreements.extend(ar)
        for k in ("all_valid_identical","all_invalid","all_correct","all_incorrect",
                  "correctness_constant"):
            z[k+"_n"]=sum(x[k] for x in ar)
            z[k+"_pct"]=100*z[k+"_n"]/90
        model_summary.append(z)
        # Same subgroup definitions across repetitions; aggregate per-repeat
        # rates rather than claim 450 independent questions.
        for dimension in ("group","difficulty","gold_relation"):
            src=components if dimension=="gold_relation" else case_scores
            metric="component_exact" if dimension=="gold_relation" else "strict_case_exact"
            vals=sorted({x[dimension] for x in src})
            for value in vals:
                rates=[]
                for r in range(1,repeats+1):
                    subset=[x for x in src if x["model"]==m and x["repeat"]==r
                            and x[dimension]==value]
                    rates.append(100*sum(x[metric] for x in subset)/len(subset))
                mu,sd=mean_sd(rates)
                strata.append(dict(model=m,dimension=dimension,value=value,metric=metric,
                                   n_per_repeat=len(subset),repeats=repeats,
                                   accuracy_mean_pct=mu,accuracy_sd_pp=sd))
    return model_summary,agreements,strata


def score(args):
    cases,gold,locked=assert_provisional(need_gold=True)
    root=Path(args.out_dir)
    meta=json.loads((root/"repeat_manifest.json").read_text(encoding="utf-8"))
    require(meta["protocol"]==PROTOCOL and meta["repeats"]==args.repeats
            and meta["models"]==ALL_MODELS and meta["settings"]==SETTINGS
            and meta["cases_sha256"]==locked["cases_sha256"]
            and meta["annex_sha256"]==locked["annex_sha256"]
            and meta["code_sha256"]==code_hashes(),"반복 실험 manifest 설정 불일치")
    scores=[]
    components=[]
    rep_stats=[]
    signatures={}
    provenance=[]
    blocks=load(root/"blocks.jsonl")
    case_by_id={c["test_id"]:c for c in cases}
    for r in range(1,args.repeats+1):
        rd=repeat_dir(root,r)
        raw={}
        for m in ALL_MODELS:
            conf=config(meta,r,m)
            raw[m]=verified_rows(raw_path(root,r,m),conf,cases,complete=True)
        cs,co,_,info=inspect_run(rd,gold,models=ALL_MODELS)
        require(len(cs)==360 and len(co)==540,"반복별 문항/성분 채점 개수 오류")
        for m in ALL_MODELS:
            index={x["test_id"]:x for x in raw[m]}
            for x in cs:
                if x["model"]==m:
                    record=index[x["test_id"]]
                    x.update(repeat=r,cold_first_case=record["cold_first_case"],
                             **{k:record[k] for k in TIMES})
                    signatures[(m,r,x["test_id"])]=signature(record,case_by_id[x["test_id"]])
        for x in co:
            x["repeat"]=r
        scores.extend(cs)
        components.extend(co)
        rep_stats.extend(per_repeat_stats(cs,ALL_MODELS,r,blocks))
        provenance.append(dict(repeat=r,raw_files=info))
    ms,agreement,strata=summarize(rep_stats,scores,components,signatures,cases,args.repeats)
    dest=root/"analysis"
    dest.mkdir(exist_ok=True)
    for name,rows in (("REPEAT_per_run_PRIVATE.csv",rep_stats),
                      ("REPEAT_model_summary_PRIVATE.csv",ms),
                      ("REPEAT_case_scores_PRIVATE.csv",scores),
                      ("REPEAT_component_scores_PRIVATE.csv",components),
                      ("REPEAT_decision_agreement_PRIVATE.csv",agreement),
                      ("REPEAT_subgroups_PRIVATE.csv",strata)):
        write_csv(dest/name,rows)
    save_json(dest/"REPEAT_provenance_PRIVATE.json",
              {"manifest":meta,"gold_sha256":locked["gold_sha256"],
               "gold_status":locked["review_status"],
               "independent_expert_review_completed":False,"raw_files":provenance,
               "scored_utc":now()})
    def fmt(v):
        return f"{v:.2f}" if v is not None else "NA"
    lines=["# B90 반복실험 및 소요시간 (잠정 Gold)","",
           f"90 B문항 × 4모델 × {args.repeats}회; 고정 seed 20261120, temperature=0.",
           "반복 간 표본은 동일 90문항이며 독립적인 신규 표본이 아니다.",
           "동일 설정 재현성과 처리시간을 평가하며 확률적 샘플링 성능은 평가하지 않는다.","",
           "|모델|완전정답률 평균 ± SD (%p)|근거 검색률 평균 (%)|"
           "지정범위 정확도 평균 (%)|문항 평균 시간 (초)|90문항 평균 작업시간 (분)|"
           "유효 구조판정 모두 동일 (90문항)|",
           "|---|---:|---:|---:|---:|---:|---:|"]
    for x in ms:
        task=x["task_seconds_total_mean_across_repeats"]
        lines.append("|"+"|".join([x["model"],
            fmt(x["strict_case_exact_pct_mean_across_repeats"])+" ± "+
            fmt(x["strict_case_exact_pct_sd_across_repeats"]),
            fmt(x["all_gold_rows_retrieved_pct_mean_across_repeats"]),
            fmt(x["scope_plus_article3_correct_pct_mean_across_repeats"]),
            fmt(x["task_seconds_mean_mean_across_repeats"]),fmt(task/60),
            str(x["all_valid_identical_n"])+"/90"])+"|")
    lines+=["","## 모델별 처리시간 상세 (초, 5회 또는 지정 반복 수의 평균)","",
            "|모델|검색어 생성/문항|고시 검색/문항|최종 판단/문항|전체/문항|"
            "90문항 총시간 (분) 평균 ± SD|전체 반복 작업시간 (시간)|",
            "|---|---:|---:|---:|---:|---:|---:|"]
    for x in ms:
        task=x["task_seconds_total_mean_across_repeats"]
        sd=x["task_seconds_total_sd_across_repeats"]
        lines.append("|"+"|".join([
            x["model"],
            fmt(x["query_seconds_mean_mean_across_repeats"]),
            fmt(x["retrieval_seconds_mean_mean_across_repeats"]),
            fmt(x["reason_seconds_mean_mean_across_repeats"]),
            fmt(x["task_seconds_mean_mean_across_repeats"]),
            fmt(task/60)+" ± "+fmt(sd/60 if sd is not None else None),
            fmt(x["all_repeats_task_seconds"]/3600)])+"|")
    lines+=["","## 반복별 모델 처리시간 (분)","",
            "|반복|모델|90문항 작업시간|블록 전체 실측시간|cold-start 문항 수|",
            "|---:|---|---:|---:|---:|"]
    for x in rep_stats:
        wall=x["wall_block_seconds_total"]
        lines.append("|"+"|".join([str(x["repeat"]),x["model"],
            fmt(x["task_seconds_total"]/60),
            fmt(wall/60 if wall is not None else None),
            str(x["cold_first_cases"])])+"|")
    lines+=["","90문항 작업시간은 각 문항의 실제 end-to-end 측정값의 합이다. "
            "검색어 생성, 로컬 고시 검색, 최종 판단 및 파싱을 포함하며 파일 기록, "
            "출력, DB 준비, 블록 전후 모델 언로드는 제외한다.",
            "각 반복/모델 블록 시작 시 모델을 언로드하여 첫 문항의 로딩 비용이 포함된다. "
            "중단 후 재개하면 추가 cold-start가 생기며 raw 및 per_run 표에 기록된다.",
            "별도 블록 wall time에는 언로드/출력/저장 등 작업 블록 부대시간도 포함한다. "
            "중단·오류로 블록 기록이 완결되지 않으면 해당 값은 NA.",
            "모든 유효 구조판정 동일: 자유서술 이유를 제외한 성분별 판단과 혼합물 판정이 "
            "모든 반복에서 유효하고 동일한 문항 수. 동일 오답도 포함할 수 있다.",
            "전문가 검증 전 잠정 Gold 기준. 처리시간은 기록된 PC/Ollama 환경에 한정된다."]
    (dest/"REPEAT_REPORT_PRIVATE.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))
    print("분석 결과:",dest)


def main():
    p=argparse.ArgumentParser(description="90 B문항 고정 설정 반복실험, 실제 처리시간 기록 및 채점")
    p.add_argument("--score",action="store_true")
    p.add_argument("--repeats",type=int,default=5)
    p.add_argument("--model",choices=["all",*ALL_MODELS],default="all")
    p.add_argument("--endpoint",default="http://127.0.0.1:11434")
    p.add_argument("--out-dir",default=str(OUT))
    p.add_argument("--limit",type=int,default=None,
                   help="이번 호출의 반복별/모델별 남은 문항 중 최대 N개만 수행")
    args=p.parse_args()
    if args.repeats<2 or (args.limit is not None and args.limit<1):
        p.error("반복 2회 이상, --limit는 1 이상")
    try:
        if args.score:
            score(args)
        else:
            run(args)
    except (ValueError,KeyError,FileNotFoundError,RuntimeError,OSError) as e:
        p.error(str(e))


if __name__=="__main__":
    main()
