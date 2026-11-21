"""Score independently reviewed 90 B-only questions; keep every output local."""
from __future__ import annotations
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import sys

from prepare_b90 import ROOT, V4, assert_frozen, require
from run_b90 import ALL_MODELS, RESULTS
sys.path.insert(0,str(V4))
from score_audit_v4 import inspect_run
from diagnose_raw_failures import diagnose, audit_consistency
from run_retrieval import load

LABELS = {
    "qwen2.5:3b":"Qwen2.5 3B",
    "qwen3:4b-instruct":"Qwen3 4B",
    "qwen3.5:4b":"Qwen3.5 4B",
    "qwen3.5:9b":"Qwen3.5 9B",
}
METRICS=[
    ("검색어 형식 일치","query_valid"),
    ("응답 형식 유효","answer_valid"),
    ("정확한 근거 행을 모든 성분에서 찾음","all_gold_rows_retrieved"),
    ("지정범위·혼합물 요건 판정 일치","scope_plus_article3_correct"),
    ("관계 유형 모두 일치","all_relation_correct"),
    ("CAS 직접 지정 여부 모두 일치","all_direct_cas_correct"),
    ("지정번호 모두 일치","all_entry_correct"),
    ("소번호 모두 일치","all_sub_number_correct"),
    ("모든 세부 판단 일치","strict_case_exact"),
    ("모든 세부 판단+정답 근거 검색 성공","strict_end_to_end"),
]


def write_csv(path, rows):
    require(bool(rows),"빈 결과표: "+str(path))
    with path.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def pct(n,denom):
    return f"{n}/{denom} ({n/denom*100:.1f}%)" if denom else "—"


def table(headers, rows):
    return "\n".join(
        ["| "+" | ".join(headers)+" |",
         "| "+" | ".join(["---"]*len(headers))+" |"]+
        ["| "+" | ".join(map(str,row))+" |" for row in rows])


def paired(cases,field,first="qwen3.5:4b",second="qwen3.5:9b"):
    left={c["test_id"]:bool(c[field]) for c in cases if c["model"]==first}
    right={c["test_id"]:bool(c[field]) for c in cases if c["model"]==second}
    require(set(left)==set(right) and len(left)==90,"4B/9B 대응 문항 불일치")
    counts=Counter((left[tid],right[tid]) for tid in left)
    return (counts[True,True],counts[True,False],counts[False,True],counts[False,False])


def verify_runs(locked,cases):
    expected_ids={c["test_id"] for c in cases}
    for model in ALL_MODELS:
        path=RESULTS/(model.replace(":","_")+"__main.jsonl")
        require(path.is_file(),"미완료 모델 결과: "+str(path))
        rows=load(path)
        require(len(rows)==90 and {r["test_id"] for r in rows}==expected_ids,
                f"{model}: 고유한 90문항 전부 완료 후 채점하세요")
        require(all(r.get("condition")=="B" and r.get("model")==model
                    and r.get("status")!="api_error" for r in rows),
                f"{model}: 조건 또는 API 기록 오류")
        configs=[r.get("protocol_config") for r in rows]
        require(all(isinstance(c,dict) and c==configs[0] for c in configs),
                f"{model}: 실행 프로토콜 설정이 일치하지 않음")
        config=configs[0]
        require(config.get("cases_sha256")==locked["cases_sha256"] and
                config.get("annex_sha256")==locked["annex_sha256"] and
                config.get("protocol")=="b90_v1_B_only_same_v4_1_prompts" and
                config.get("model")==model,
                f"{model}: 90문항 동결 설정과 원본 JSONL 불일치")
        require(all(r.get("model_digest")==config.get("digest") and
                    isinstance(r.get("settings_sha256"),str)
                    for r in rows),f"{model}: 모델 버전 기록 오류")
        actual_hash=hashlib.sha256(
            json.dumps(config,sort_keys=True).encode()).hexdigest()
        require(all(r["settings_sha256"]==actual_hash for r in rows),
                f"{model}: 실행 설정 SHA256 불일치")
    return True


def build_report(scored_cases, comps, consistency, run_info, locked):
    lines=[
        "# 확장 B 조건 90문항의 화학물질 규제 LLM 평가",
        "",
        "**검증 상태:** 법령 전문가가 확인하여 잠근 Gold를 사용한 90문항 분석. "
        "본 연구 범위에 한정되며 현장 규제 준수 판정을 보증하지 않음.",
        "",
        f"입력 90문항 SHA256: \u0060{locked['cases_sha256']}\u0060  ",
        f"전문가 검토 Gold SHA256: \u0060{locked['gold_sha256']}\u0060  ",
        "기존 30개 B 질문과 새로 검증한 60개 B 질문을 함께 평가함. "
        "기존 v4.1의 60문항 전체 성능표와 합산하지 않음.",
        "",
        "## 1. 네 모델의 전체 성능 (각 90문항)",
        "",
    ]
    overall=[]
    for label,field in METRICS:
        row=[label]
        for model in ALL_MODELS:
            records=[x for x in scored_cases if x["model"]==model]
            row.append(pct(sum(int(r[field]) for r in records),len(records)))
        overall.append(row)
    lines.extend([table(["평가 기준",*[LABELS[m] for m in ALL_MODELS]],overall),"",
                  "## 2. 유형별·난이도별 엄격한 완전정답 및 검색 성공",
                  ""])
    subgroup=[]
    for group in ("PARENT_AND_SALTS","COMPOUND_CLASS","MIXTURE"):
        for diff in ("EASY","HARD","ALL"):
            row=[group,diff]
            for model in ALL_MODELS:
                data=[r for r in scored_cases if r["model"]==model
                      and r["group"]==group and
                      (diff=="ALL" or r["difficulty"]==diff)]
                row.append(pct(sum(int(x["strict_end_to_end"]) for x in data),len(data)))
            subgroup.append(row)
    lines.extend([table(["규제 유형","난이도",*[LABELS[m] for m in ALL_MODELS]],subgroup),
                  "","## 3. 같은 질문에서 4B와 9B가 어떻게 달랐는가?",""])
    comp=[]
    for label,field in (("정확한 근거 행 검색","all_gold_rows_retrieved"),
                        ("지정범위 및 혼합물 요건","scope_plus_article3_correct"),
                        ("모든 판단+근거 검색","strict_end_to_end")):
        both,only4,only9,neither=paired(scored_cases,field)
        comp.append([label,both,only4,only9,neither])
    lines.extend([table(["평가 항목","두 모델 모두 성공","4B만 성공",
                         "9B만 성공","두 모델 모두 실패"],comp),"",
                  "## 4. 세부 판단(성분 단위) 및 답변 내부 모순",""])
    ncomp=sum(r["model"]==ALL_MODELS[0] for r in comps)
    extra=[]
    for title,field in (("정확한 근거 행","strict_gold_row_hit"),
                        ("지정범위","scope_correct"),
                        ("관계 유형","relation_correct"),
                        ("CAS 직접 지정 여부","direct_cas_correct"),
                        ("지정번호","entry_correct"),
                        ("소번호","sub_number_correct"),
                        ("세부 항목 전체","component_exact")):
        row=[title]
        for m in ALL_MODELS:
            items=[r for r in comps if r["model"]==m]
            row.append(pct(sum(r[field] for r in items),len(items)))
        extra.append(row)
    lines.extend([table(["성분별 항목",*[LABELS[m] for m in ALL_MODELS]],extra),""])
    contra=[]
    for m in ALL_MODELS:
        row=next(x for x in consistency if x["model"]==m and
                 x["group"]=="ALL" and x["difficulty"]=="ALL")
        contra.append([LABELS[m],
                       pct(row["relation_scope_contradiction_n"],
                           row["relation_scope_checkable_n"])])
    lines.extend([table(["모델","관계 유형·지정범위의 내부 모순"],contra),
                  "",
                  "**해석 주의:** 유형별 30문항 중 EASY/HARD는 각각 15문항이며 "
                  "한 문제의 차이가 6.7%포인트입니다. 중복 CAS 및 혼합물 구성의 연관성을 "
                  "고려하지 않은 단순 비율 비교를 인과적·통계적 우월성으로 해석하지 마세요. "
                  "모든 평가값은 이 연구의 고시 제3조 등 한정된 조건에 대한 판정입니다.",
                  "",
                  "## 5. 재현 정보",""])
    for m in ALL_MODELS:
        x=run_info[m]
        lines.append(f"- {LABELS[m]}: 원본 JSONL SHA256 \u0060{x['file_sha256']}\u0060; "
                     f"설정 SHA256 \u0060{x['settings_sha256']}\u0060")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    p=argparse.ArgumentParser(description="90개 B 질문 전체 완료 후 독립 채점")
    p.add_argument("--out-dir",default=None,help="출력 폴더(기본: 결과 JSONL 폴더)")
    args=p.parse_args(argv)
    try:
        cases,gold,locked=assert_frozen(need_gold=True)
        verify_runs(locked,cases)
        scored,comps,_,run_info=inspect_run(RESULTS,gold,models=ALL_MODELS)
        require(len(scored)==360,"4모델 × 90문항 = 360 결과여야 합니다")
        require(len(comps)==sum(len(c["components"]) for c in cases)*4,
                "성분별 결과 행 수 불일치")
        raw={m:load(RESULTS/(m.replace(":","_")+"__main.jsonl")) for m in ALL_MODELS}
        details=diagnose(gold,raw,scored,comps,models=ALL_MODELS)[0]
        _,consistency=audit_consistency(details)
    except (ValueError,KeyError,FileNotFoundError) as e:
        p.error(str(e))
    dest=Path(args.out_dir) if args.out_dir else RESULTS
    dest.mkdir(parents=True,exist_ok=True)
    write_csv(dest/"B90_case_scores_PRIVATE.csv",scored)
    write_csv(dest/"B90_component_scores_PRIVATE.csv",comps)
    summary=[]
    for m in ALL_MODELS:
        for group in ("ALL","PARENT_AND_SALTS","COMPOUND_CLASS","MIXTURE"):
            for diff in ("ALL","EASY","HARD"):
                subset=[r for r in scored if r["model"]==m and
                        (group=="ALL" or r["group"]==group) and
                        (diff=="ALL" or r["difficulty"]==diff)]
                summary.append({
                    "model":m,"group":group,"difficulty":diff,"n":len(subset),
                    "retrieval_exact_n":sum(r["all_gold_rows_retrieved"] for r in subset),
                    "scope_plus_article3_n":sum(r["scope_plus_article3_correct"] for r in subset),
                    "strict_end_to_end_n":sum(r["strict_end_to_end"] for r in subset),
                })
    write_csv(dest/"B90_summary_PRIVATE.csv",summary)
    pairs=[]
    for label,field in (("gold_rows","all_gold_rows_retrieved"),
                        ("scope_article3","scope_plus_article3_correct"),
                        ("strict_end_to_end","strict_end_to_end")):
        a,b,c,d=paired(scored,field)
        pairs.append({"metric":label,"both_correct":a,"only_4b_correct":b,
                      "only_9b_correct":c,"neither_correct":d,"n":a+b+c+d})
    write_csv(dest/"B90_paired_4B_9B_PRIVATE.csv",pairs)
    write_csv(dest/"B90_component_discrepancies_PRIVATE.csv",details)
    (dest/"B90_REPORT_PRIVATE.md").write_text(
        build_report(scored,comps,consistency,run_info,locked),
        encoding="utf-8")
    meta={
        "dataset_sha256":locked["cases_sha256"],
        "gold_sha256":locked["gold_sha256"],
        "n_cases_per_model":90,"models":ALL_MODELS,
        "n_components_per_model":len(comps)//len(ALL_MODELS),
        "model_output_files":run_info,
        "caution":"Private Gold and exact returned evidence; never upload to public GitHub",
    }
    (dest/"B90_provenance_PRIVATE.json").write_text(
        json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("PASS: 전문가 검증 B 90문항 × 4모델 채점 완료", dest)
    print("원본 JSONL, 기존 v4.1 Gold/결과는 모두 보존했습니다")


if __name__=="__main__":
    main()
