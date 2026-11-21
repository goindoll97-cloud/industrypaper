"""Generate one concise manuscript-oriented results file from frozen local v4.1 outputs.

Usage (from llm_capability_study/retrieval_v4):
    python ..\make_paper_report.py

The program does not run a model, modify Gold, or rewrite legacy scoring CSVs.
Only provisional aggregate statistics are exported. No answers leave the PC.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

STUDY_DIR = Path(__file__).resolve().parent
ENGINE_DIR = STUDY_DIR / "retrieval_v4"
sys.path.insert(0, str(ENGINE_DIR))

from gold_integrity import expected_gold_sha  # noqa: E402
from run_retrieval import DATA, MODELS, ADDITIONAL_MODELS, load  # noqa: E402
from score_audit_v4 import inspect_run  # noqa: E402
from diagnose_raw_failures import diagnose, audit_consistency  # noqa: E402

# Frozen 2026-11-20 v4.1 experiment. Do not silently combine changed protocols.
GOLD_SHA = "ed817e989ec828c767fb09d39d9d912030a661b82b7b054250c8146167055c50"
SETTINGS = {
    "qwen2.5:3b": "92bf4dbc8b7c883d8647635add71eb4eec3f045b7d2c014e3a866210a8944572",
    "qwen3:4b-instruct": "b5db7cf6a80cf1382b6f2f58ef45f34f87e279b02a265e8416693390b87404ab",
    "qwen3.5:4b": "7e6839b89a4c0e667fc9fd069845a749810daa24265345c2ac7561b02bc7ef11",
}
LABELS = {
    "qwen2.5:3b": "Qwen2.5 3B",
    "qwen3:4b-instruct": "Qwen3 4B",
    "qwen3.5:4b": "Qwen3.5 4B",
    "qwen3.5:9b": "Qwen3.5 9B (추가)",
}
GROUP_LABELS = {
    "PARENT_AND_SALTS": "모체 및 염류",
    "COMPOUND_CLASS": "화합물군",
    "MIXTURE": "혼합물",
}


def count(rows, name):
    return sum(int(r[name]) for r in rows)


def proportion(k, n):
    return f"{k}/{n} ({100*k/n:.1f}%)" if n else "해당 없음"


def table(headers, rows):
    def clean(v):
        return str(v).replace("|", "/").replace("\n", " ")
    return "\n".join([
        "| " + " | ".join(map(clean, headers)) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
        *["| " + " | ".join(map(clean, row)) + " |" for row in rows],
    ])


def render(cases, components, consistency, run_info, gold_sha, models=None):
    """Pure rendering function; independent of local file paths."""
    models = MODELS if models is None else models
    total_cases = len(cases)
    total_components = len(components)
    lines = [
        "# 논문용 결과표 — v4.1 (2026-11-20 고정 실험)",
        "",
        "**분석 상태:** 잠정 Gold(CURATED_PROVISIONAL), 독립 법령 전문가 검증 미완료.",
        "**해석:** 이 표의 정확도는 최종 법적 판단의 적법성이나 실제 규제 준수를 보증하지 않습니다.",
        "",
        f"Gold SHA256: \`{gold_sha}\`  ",
        f"분석 단위: {total_cases} 문항-모델 결과, {total_components} 성분-모델 결과. "
        "A/B는 동일한 원사례 30건의 대응 조건입니다.",
        "",
        "## 1. 1차 성능지표",
        "",
    ]
    if len(models) > len(MODELS):
        lines.append("**추가 비교:** 9B 모델은 같은 30개 사례에 추후 평가한 대조군입니다. 독립 외부 검증은 아니며 모델 크기 외의 차이도 존재합니다.")
        lines.append("")
    rows = []
    for model in models:
        selected = [r for r in cases if r["model"] == model]
        n = len(selected)
        rows.append([
            LABELS[model], n,
            proportion(count(selected, "query_valid"), n),
            proportion(count(selected, "answer_valid"), n),
            proportion(count(selected, "all_gold_rows_retrieved"), n),
            proportion(count(selected, "scope_plus_article3_correct"), n),
            proportion(count(selected, "strict_case_exact"), n),
            proportion(count(selected, "strict_end_to_end"), n),
        ])
    lines.extend([
        table(["모델", "N", "검색어 유효", "응답 JSON 유효", "전 성분 Gold 근거 검색",
               "지정범위+제3조 일치", "엄격한 완전정답", "End-to-end"], rows),
        "",
        "주: '지정범위+제3조 일치'는 성분별 covered_by_clause 및 혼합물의 제3조 요건 일치이며, "
        "정답 근거 행 검색 성공을 필수로 요구하지 않습니다. "
        "엄격한 완전정답은 성분별 직접 CAS·지정범위·관계 유형·지정번호·소번호와 "
        "혼합물 제3조의 일치를 요구합니다. End-to-end는 완전정답과 Gold 근거 행 전부 검색을 동시에 요구합니다.",
        "",
        "## 2. 유형별 End-to-end 성능",
        "",
    ])
    by_group = []
    for group in GROUP_LABELS:
        row = [GROUP_LABELS[group]]
        for model in models:
            selected = [r for r in cases if r["model"] == model and r["group"] == group]
            row.append(proportion(count(selected, "strict_end_to_end"), len(selected)))
        by_group.append(row)
    lines.extend([table(["분류", *[LABELS[m] for m in models]], by_group), "",
                  "## 3. 난이도별 End-to-end 성능", ""])
    by_diff = []
    for difficulty in ("EASY", "HARD"):
        row = [difficulty]
        for model in models:
            selected = [r for r in cases if r["model"] == model and r["difficulty"] == difficulty]
            row.append(proportion(count(selected, "strict_end_to_end"), len(selected)))
        by_diff.append(row)
    lines.extend([table(["난이도", *[LABELS[m] for m in models]], by_diff), "",
                  "## 4. 응답 일관성 (보조 진단)", ""])
    rows = []
    for model in models:
        selected = next(r for r in consistency if r["model"] == model and
                        r["group"] == "ALL" and r["difficulty"] == "ALL")
        rows.append([
            LABELS[model],
            proportion(selected["relation_scope_contradiction_n"],
                       selected["relation_scope_checkable_n"]),
            proportion(selected["cited_returned_evidence_n"], selected["component_n"]),
            selected["invalid_designation_id_format_n"],
            selected["designation_id_not_reported_n"],
        ])
    lines.extend([
        table(["모델", "지정범위·관계 유형 모순 / 검사 가능", "제시 지정번호가 반환된 검색 결과에 존재",
               "지정번호 형식 오류", "번호 미제시"], rows),
        "",
        "모순은 모델 출력 필드 사이의 실험 스키마상 자기일관성 검사입니다. "
        "검색 결과에 없는 지정번호가 실제 법령 전체에도 없다는 뜻은 아닙니다.",
        "",
        "## 5. 방법론 요약",
        "",
        "평가 자료: 환경부 2026-5호 고시 별표의 1,451행. 3개 분류 각 10사례(총 30사례), "
        "각 분류의 EASY/HARD 5사례씩; A/B 대응 입력을 적용하여 모델당 60문항. "
        "A는 CAS·영문명(혼합물은 조성 포함), B는 검증 가능한 구조정보를 추가한 조건입니다.",
        "",
        "각 질문에 대해 LLM이 성분별 검색어 1~3개를 생성하고, 공식 별표 전체를 대상으로 "
        "어휘 기반 검색을 수행한 뒤 제공된 근거 행을 활용하여 지정범위·관계 유형·지정번호·소번호를 JSON으로 판정했습니다. "
        "최대 검색 행 수는 단일물질 8개/성분, 2성분 혼합물 5개/성분, 3성분 혼합물 4개/성분으로 서로 다릅니다.",
        "",
        "실험 설정: Ollama, temperature=0, seed=20261120, num_ctx=4096, "
        "v4.1 검색/판정 출력상한 각각 384/900토큰; Qwen3 계열 think=false. "
        "정답지는 검색·생성 단계에 사용하지 않고 채점에서만 참조했습니다.",
        "",
        "## 6. 연구 해석상 주의",
        "",
        "- GOLD는 전문가 독립 검증 전 잠정 정답입니다. 법령 해석 확정치로 인용하지 마세요.",
        "- 같은 원사례의 A/B 두 문항은 독립 표본 60개가 아닙니다.",
        "- v4와 v4.1은 검색 규칙과 출력 제약이 달라, 모델 능력 자체의 인과적 향상으로 해석할 수 없습니다.",
        "- 엄격 검색은 지정된 Gold 원본 행과의 일치를 요구합니다. 같은 지정번호의 다른 행은 자동 정답으로 인정하지 않습니다.",
        "- 실험의 혼합물 판정은 고시 제3조의 지정성분 전부 해당 여부이며 일반적인 제품 적법성 판단이 아닙니다.",
        "",
        "## 7. 재현 정보",
        "",
        "v4.1 기준 프로토콜 확정: 2026-11-20; 결과는 고정 Gold·settings hash와 원본 JSONL에서 계산",
        "",
    ])
    for model in models:
        meta = run_info[model]
        lines.append(f"- {LABELS[model]}: settings SHA256 \`{meta['settings_sha256']}\`; "
                     f"JSONL SHA256 \`{meta['file_sha256']}\`")
    lines.append("")
    return "\n".join(lines)



def render_paired_failure_analysis(cases, components, details, consistency_components):
    """Compare 4B vs 9B for the very same test_ids and Gold components.

    The generated local Markdown is diagnostic only; multi-label errors are
    descriptive, not exclusive causal attributions. Never change scores/Gold.
    """
    small, large = "qwen3.5:4b", "qwen3.5:9b"
    by_case = {
        model: {r["test_id"]: r for r in cases if r["model"] == model}
        for model in (small, large)
    }
    keys = set(by_case[small])
    if not keys or keys != set(by_case[large]):
        raise ValueError("4B와 9B의 동일 test_id가 일치하지 않습니다")
    by_comp = {
        model: {(r["test_id"], r["component_id"]): r
                for r in components if r["model"] == model}
        for model in (small, large)
    }
    component_keys = set(by_comp[small])
    if not component_keys or component_keys != set(by_comp[large]):
        raise ValueError("4B와 9B의 성분별 식별자가 일치하지 않습니다")
    by_detail = {
        (r["model"], r["test_id"], r["component_id"]): r
        for r in details if r["model"] in (small, large)
    }
    by_cons = {
        model: [r for r in consistency_components if r["model"] == model]
        for model in (small, large)
    }
    if (len(by_detail) != 2 * len(component_keys)
            or any(len(by_cons[model]) != len(component_keys) for model in (small, large))):
        raise ValueError("성분별 오류 진단 또는 응답 일관성 자료가 누락되었습니다")

    metrics = [
        ("정답 근거 행 전체 검색", "all_gold_rows_retrieved"),
        ("지정범위·혼합물 규정 판단", "scope_plus_article3_correct"),
        ("최종 완전정답 및 근거 검색", "strict_end_to_end"),
    ]
    lines = [
        "## 8. Qwen3.5 4B와 9B의 동일 문항 오류 비교",
        "",
        "두 모델에 동일한 질문을 제시했을 때 성공과 실패가 어떻게 달라졌는지를 확인했습니다. "
        "모델당 같은 원사례 30개에 A/B 두 조건을 적용한 60문항이며, "
        "아래 결과는 사례별 대응 비교입니다.",
        "",
        "### 8.1. 같은 질문에서 어느 모델이 맞혔는가?",
        "",
    ]
    transitions = []
    for label, field in metrics:
        both = only4 = only9 = neither = 0
        for tid in sorted(keys):
            a = bool(by_case[small][tid][field])
            b = bool(by_case[large][tid][field])
            if a and b:
                both += 1
            elif a:
                only4 += 1
            elif b:
                only9 += 1
            else:
                neither += 1
        transitions.append([label, both, only4, only9, neither])
    lines.extend([
        table(["비교 기준", "둘 다 성공", "4B만 성공", "9B만 성공", "둘 다 실패"], transitions),
        "",
        "주: 성공 여부는 같은 문항에서 각각 확인한 것입니다. "
        "특히 '4B만 성공'과 '9B만 성공'을 함께 봐야 모델별 정답 수의 차이를 해석할 수 있습니다.",
        "",
        "### 8.2. 어떤 세부 판단에서 오류가 발생했는가?",
        "",
    ])
    component_measures = [
        ("정답 고시 행 검색", "strict_gold_row_hit"),
        ("지정범위 포함 여부", "scope_correct"),
        ("지정 관계 유형", "relation_correct"),
        ("CAS 직접 지정 여부", "direct_cas_correct"),
        ("지정번호", "entry_correct"),
        ("고시 소번호", "sub_number_correct"),
        ("성분의 세부 항목 모두", "component_exact"),
    ]
    component_table = []
    ncomp = len(component_keys)
    for label, field in component_measures:
        correct = [sum(int(by_comp[m][key][field]) for key in component_keys)
                   for m in (small, large)]
        component_table.append([
            label, proportion(correct[0], ncomp), proportion(correct[1], ncomp),
            f"{correct[1] - correct[0]:+d}건",
        ])
    lines.extend([
        table(["성분별 평가 항목", "4B 정답", "9B 정답", "9B-4B"], component_table),
        "",
        "주: 각 질문에 여러 성분이 포함될 수 있으므로 성분 수는 질문 수와 다릅니다. "
        "위 항목은 서로 독립적인 오류 원인을 뜻하지 않습니다.",
        "",
    ])
    contradictions = []
    for m, name in ((small, "4B"), (large, "9B")):
        checked = sum(int(r["relation_scope_checkable"]) for r in by_cons[m])
        wrong = sum(int(r["relation_scope_contradiction"]) for r in by_cons[m])
        contradictions.append([name, proportion(wrong, checked)])
    lines.extend([
        table(["모델", "답변 내부의 논리적 모순"], contradictions),
        "",
        "이 모순은 '지정된 물질'이라고 분류하면서 동시에 '지정범위에 해당하지 않는다'고 답하는 "
        "등의 필드 간 불일치입니다. 모순이 적더라도 실제 판단이 반드시 맞는 것은 아닙니다.",
        "",
        "### 8.3. 9B가 지정범위를 맞히고도 최종 정답을 놓친 이유",
        "",
    ])

    # One case can contribute to multiple rows, so do not call these causal shares.
    labels = (
        ("정답 고시 행을 검색하지 못함", "missing_retrieval", "all_gold_rows_retrieved"),
        ("지정 관계 유형이 다름", "wrong_relation", "relation_correct"),
        ("CAS 직접 지정 판단이 다름", "wrong_direct_cas", "direct_cas_correct"),
        ("지정번호가 다름", "wrong_entry", "entry_correct"),
        ("고시 소번호가 다름", "wrong_sub_number", "sub_number_correct"),
    )
    selected = sorted(tid for tid in keys
                      if bool(by_case[large][tid]["scope_plus_article3_correct"])
                      and not bool(by_case[large][tid]["strict_end_to_end"]))
    reasons = {}
    for tid in selected:
        parts = [r for k, r in by_comp[large].items() if k[0] == tid]
        misses = {}
        for label, name, field in labels:
            if name == "missing_retrieval":
                misses[name] = not bool(by_case[large][tid][field])
            else:
                misses[name] = any(not bool(r[field]) for r in parts)
        reasons[tid] = misses
    totals = []
    for label, name, _ in labels:
        matched = [tid for tid in selected if reasons[tid][name]]
        totals.append([label, f"{len(matched)}건", ", ".join(matched[:4]) or "—"])
    lines.extend([
        f"9B 모델에서 **지정범위 및 혼합물 규정 판단은 맞았지만 최종 완전정답에는 "
        f"이르지 못한 문항은 {len(selected)}건**입니다.",
        "",
        table(["함께 발견된 오류 유형", "해당 문항 수", "사례 번호(최대 4개)"], totals),
        "",
        "주의: 한 문항에 검색 오류, 관계 해석 오류, 번호 오류 등이 동시에 발생할 수 있으므로 "
        "위 건수를 더해도 전체 문항 수와 같지 않습니다. "
        "첫 번째로 표시된 오류가 반드시 실제 원인이라는 뜻도 아닙니다.",
        "",
        "### 8.4. 완전정답 여부가 서로 달랐던 문항",
        "",
    ])
    different = []
    def _explain(model, tid):
        x = by_case[model][tid]
        if bool(x["strict_end_to_end"]):
            return "완전정답"
        issues = []
        if not bool(x["answer_valid"]):
            issues.append("응답 형식")
        if not bool(x["all_gold_rows_retrieved"]):
            issues.append("근거 행")
        if not bool(x["scope_plus_article3_correct"]):
            issues.append("지정범위/혼합물")
        parts = [r for k, r in by_comp[model].items() if k[0] == tid]
        for label, field in (
            ("관계 유형", "relation_correct"),
            ("CAS 직접 일치", "direct_cas_correct"),
            ("지정번호", "entry_correct"),
            ("소번호", "sub_number_correct"),
        ):
            if any(not bool(r[field]) for r in parts):
                issues.append(label)
        return ", ".join(issues) or "기타 확인 필요"

    for tid in sorted(keys):
        a, b = by_case[small][tid], by_case[large][tid]
        if bool(a["strict_end_to_end"]) == bool(b["strict_end_to_end"]):
            continue
        different.append([
            tid, GROUP_LABELS.get(a["group"], a["group"]), a["difficulty"],
            "정답" if a["strict_end_to_end"] else "오답",
            "정답" if b["strict_end_to_end"] else "오답",
            _explain(large, tid) if not b["strict_end_to_end"] else _explain(small, tid) + " (4B)",
        ])
    lines.extend([
        table(["문항 ID", "유형", "난이도", "4B", "9B", "틀린 모델의 오류 항목"],
              different or [["—", "—", "—", "—", "—", "완전정답 변동 없음"]]),
        "",
        "**해석:** 관련 규정 검색, 지정범위 판단, 세부 근거번호 및 답변의 자기일관성은 "
        "서로 다른 평가 항목입니다. 어느 한 항목의 개선만으로 완전정답률의 향상을 단정할 수 없습니다. "
        "이 비교는 같은 30개 원사례에서 수행한 기술적 분석이며, "
        "모델 규모의 인과효과나 다른 고시에 대한 일반화 가능성을 입증하지 않습니다. "
        "잠정 Gold의 전문가 검토 결과에 따라 판단 일치율은 달라질 수 있습니다.",
        "",
    ])
    return "\n".join(lines)



def export_local_supplementary(output_dir, cases, components, details,
                               consistency_rows, run_info, gold_sha, models):
    """Private evidence appendix: never commit these provisional Gold labels."""
    required = ("qwen3.5:4b", "qwen3.5:9b")
    if not all(model in models for model in required):
        raise ValueError("4B와 9B 결과가 모두 필요합니다")
    by_case = {(r["model"], r["test_id"]): r for r in cases}
    by_comp = {(r["model"], r["test_id"], r["component_id"]): r for r in components}
    by_detail = {(r["model"], r["test_id"], r["component_id"]): r for r in details}
    by_cons = {(r["model"], r["test_id"], r["component_id"]): r
               for r in consistency_rows}
    test_ids = sorted(set(r["test_id"] for r in cases))
    if any((m, tid) not in by_case for m in models for tid in test_ids):
        raise ValueError("대응 문항 누락")
    aliases = {"qwen2.5:3b":"q25", "qwen3:4b-instruct":"q3",
               "qwen3.5:4b":"q35_4b", "qwen3.5:9b":"q35_9b"}
    fields = ("query_valid","answer_valid","all_gold_rows_retrieved",
              "scope_plus_article3_correct","all_relation_correct",
              "all_direct_cas_correct","all_entry_correct",
              "all_sub_number_correct","strict_case_exact","strict_end_to_end")
    case_rows = []
    for tid in test_ids:
        base = by_case[models[0], tid]
        row = {key:base[key] for key in
               ("test_id","case_id","condition","group","difficulty","component_count")}
        for model in models:
            q = by_case[model, tid]
            if any(q[k] != base[k] for k in
                   ("case_id","condition","group","difficulty","component_count")):
                raise ValueError("모델 간 문항 정보 불일치: "+tid)
            for fld in fields:
                row[aliases[model]+"_"+fld] = int(q[fld])
        row["only_4b_strict"] = int(bool(by_case[required[0],tid]["strict_end_to_end"]) and
                                     not bool(by_case[required[1],tid]["strict_end_to_end"]))
        row["only_9b_strict"] = int(bool(by_case[required[1],tid]["strict_end_to_end"]) and
                                     not bool(by_case[required[0],tid]["strict_end_to_end"]))
        case_rows.append(row)
    comp_rows = []
    for model in models:
        source = sorted((r for r in components if r["model"] == model),
                        key=lambda r:(r["test_id"],r["component_id"]))
        for r in source:
            k = (model,r["test_id"],r["component_id"])
            if k not in by_detail or k not in by_cons:
                raise ValueError("성분별 진단 누락: "+str(k))
            d, c = by_detail[k], by_cons[k]
            comp_rows.append({
                "model":model,"test_id":r["test_id"],"case_id":r["case_id"],
                "condition":r["condition"],"group":r["group"],
                "difficulty":r["difficulty"],"component_id":r["component_id"],
                "cas":d["cas"],"gold_row":d["gold_row"],
                "gold_row_retrieved":r["strict_gold_row_hit"],
                "retrieved_row_ids":d["retrieved_row_ids"],
                "retrieved_designation_ids":d["retrieved_designation_ids"],
                "gold_scope":d["gold_scope"],"predicted_scope":d["predicted_scope"],
                "scope_correct":r["scope_correct"],
                "gold_relation":d["gold_relation"],"predicted_relation":d["predicted_relation"],
                "relation_correct":r["relation_correct"],
                "gold_direct_cas":d["gold_direct_cas"],
                "predicted_direct_cas":d["predicted_direct_cas"],
                "direct_cas_correct":r["direct_cas_correct"],
                "gold_entry_id":d["gold_designation_id"],
                "predicted_entry_id":d["predicted_designation_id"],
                "entry_correct":r["entry_correct"],
                "gold_sub_number":d["gold_sub_number"],
                "predicted_sub_number":d["predicted_sub_number"],
                "sub_number_correct":r["sub_number_correct"],
                "component_exact":r["component_exact"],
                "relation_scope_contradiction":c["relation_scope_contradiction"],
                "designation_grounding":c["designation_grounding"],
                "wrong_fields":d["wrong_fields"],
                "gold_review_status":"CURATED_PROVISIONAL",
                "independent_expert_reviewed":0})
    pending = []
    for tid in test_ids:
        q = by_case[required[1],tid]
        if not (q["scope_plus_article3_correct"] and not q["strict_end_to_end"]):
            continue
        cs = [r for r in components if r["model"] == required[1] and r["test_id"] == tid]
        pending.append({
            "test_id":tid,"group":q["group"],"difficulty":q["difficulty"],
            "4b_strict_correct":int(by_case[required[0],tid]["strict_end_to_end"]),
            "9b_scope_correct":1,"9b_strict_correct":0,
            "gold_row_not_found":int(not q["all_gold_rows_retrieved"]),
            "relation_wrong":int(any(not x["relation_correct"] for x in cs)),
            "direct_cas_wrong":int(any(not x["direct_cas_correct"] for x in cs)),
            "entry_wrong":int(any(not x["entry_correct"] for x in cs)),
            "sub_number_wrong":int(any(not x["sub_number_correct"] for x in cs))})
    if len(test_ids)==60 and not (len(pending)==32 and
          sum(by_case[required[1],tid]["scope_plus_article3_correct"] for tid in test_ids)==48 and
          sum(by_case[required[1],tid]["strict_end_to_end"] for tid in test_ids)==16):
        raise ValueError("동결 9B 결과와 보충자료 집계 불일치")
    output_dir.mkdir(parents=True,exist_ok=True)
    def write(name,rows):
        filepath = output_dir/name
        with filepath.open("w",encoding="utf-8-sig",newline="") as fp:
            writer=csv.DictWriter(fp,fieldnames=list(rows[0]),extrasaction="raise")
            writer.writeheader()
            writer.writerows(rows)
        return filepath
    paths = [
        write("S8_60_case_outcomes_PRIVATE.csv",case_rows),
        write("S9_360_component_evidence_PRIVATE.csv",comp_rows),
        write("S10_9B_32_scope_correct_failed_PRIVATE.csv",pending)]
    meta = {"gold_sha256":gold_sha,
            "gold_status":"CURATED_PROVISIONAL; expert validation pending",
            "model_run_sha256":{m:run_info[m]["file_sha256"] for m in models},
            "n_case_rows":len(case_rows),"n_component_rows":len(comp_rows),
            "n_9b_scope_correct_failed":len(pending),
            "privacy":"PRIVATE: contains provisional Gold labels and model predictions",
            "note":"Flags overlap; no causal error attribution; A/B cases paired"}
    manifest = output_dir/"S0_provenance_PRIVATE.json"
    manifest.write_text(json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return [manifest,*paths]

def main():
    parser = argparse.ArgumentParser(description="기존 3개 JSONL만으로 논문용 결과표 1개 생성")
    parser.add_argument("--results-dir", default="results_v4_1",
                        help="retrieval_v4 폴더 안의 원본 결과 디렉터리")
    parser.add_argument("--strong-results-dir", default=None,
                        help="선택: 같은 v4.1 조건으로 추가 실행한 Qwen3.5 9B 별도 폴더")
    ns = parser.parse_args()
    folder = ENGINE_DIR / ns.results_dir
    gold_path = ENGINE_DIR / "private" / "gold_60.jsonl"
    if not gold_path.is_file():
        parser.error("Gold 파일이 없습니다: retrieval_v4/private/gold_60.jsonl")
    gold_sha = hashlib.sha256(gold_path.read_bytes()).hexdigest()
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    if gold_sha != GOLD_SHA or gold_sha != expected_gold_sha(ENGINE_DIR, manifest):
        parser.error("고정 v4.1 논문용 Gold 해시 불일치: 최신 수정 Gold 적용 확인")
    gold = load(gold_path)
    if len(gold) != 60 or len({g["test_id"] for g in gold}) != 60:
        parser.error("Gold는 고유한 60문항이어야 합니다")
    cases, components, _, run_info = inspect_run(folder, gold)
    if len(cases) != 180 or len(components) != 270:
        parser.error("3모델 × 60문항 × 90성분(모델별) 조건을 충족하지 못했습니다")
    for model in MODELS:
        info = run_info[model]
        if info["raw_records"] != 60 or info["duplicates"]:
            parser.error(f"{model}: 원본 문항이 60개가 아니거나 중복 기록이 있습니다")
        if info["settings_sha256"] != SETTINGS[model]:
            parser.error(f"{model}: 현재 실험 설정이 동결한 v4.1 결과와 다릅니다")
    runs = {m: load(folder / (m.replace(":", "_") + "__main.jsonl")) for m in MODELS}
    details, _, _, _, _ = diagnose(gold, runs, cases, components)
    consistency_components, consistency = audit_consistency(details)
    selected_models = list(MODELS)
    if ns.strong_results_dir is not None:
        strong_folder = ENGINE_DIR / ns.strong_results_dir
        if strong_folder.resolve() == folder.resolve():
            parser.error("추가 모델은 기존 baseline 결과 폴더와 반드시 분리하세요")
        if not strong_folder.is_dir():
            parser.error(f"추가 모델 결과 폴더가 없습니다: {strong_folder}")
        stronger = ADDITIONAL_MODELS[0]
        new_cases, new_components, _, new_meta = inspect_run(strong_folder, gold, models=[stronger])
        raw_new = load(strong_folder / (stronger.replace(":", "_") + "__main.jsonl"))
        expected_ids = {g["test_id"] for g in gold}
        if (len(raw_new) != 60 or {r["test_id"] for r in raw_new} != expected_ids
                or len(new_cases) != 60 or len(new_components) != 90
                or new_meta[stronger]["duplicates"] != 0):
            parser.error("추가 모델은 동일한 60문항·90성분을 모두 실행해야 비교할 수 있습니다")
        expected_config = {
            "num_ctx": 4096, "query_tokens": 384, "reason_tokens": 900,
            "seed": 20261120, "timeout": 480,
            "search": "lexical_rank_fusion_v2_cas",
            "protocol": "v4_1_three_groups_format_recovery",
            "cases_sha256": manifest["cases_sha256"],
            "annex_sha256": manifest["annex_sha256"],
        }
        if any(r.get("protocol_config") != expected_config for r in raw_new):
            parser.error("추가 모델의 컨텍스트·토큰·검색·시드·타임아웃이 기존 v4.1과 다릅니다")
        if any(r.get("model") != stronger or not r.get("model_digest") for r in raw_new):
            parser.error("추가 모델 태그와 digest 기록을 확인하세요")
        new_details, _, _, _, _ = diagnose(
            gold, {stronger: raw_new}, new_cases, new_components, models=[stronger])
        new_consistency_components, new_consistency = audit_consistency(new_details)
        cases.extend(new_cases)
        components.extend(new_components)
        consistency.extend(new_consistency)
        consistency_components.extend(new_consistency_components)
        details.extend(new_details)
        run_info.update(new_meta)
        selected_models.append(stronger)
    report = render(cases, components, consistency, run_info, gold_sha,
                    models=selected_models)
    if ns.strong_results_dir is not None:
        report += "\n" + render_paired_failure_analysis(cases, components, details, consistency_components)
    target = folder / "PAPER_RESULTS_v4_1.md"
    if target.exists() and target.read_text(encoding="utf-8") != report:
        print("주의: 기존 논문용 보고서를 덮어씁니다 (같은 고정 Gold·실험 설정)")
    target.write_text(report, encoding="utf-8")
    if ns.strong_results_dir is not None:
        paths = export_local_supplementary(
            folder/"supplementary_PRIVATE", cases, components, details,
            consistency_components, run_info, gold_sha, selected_models)
        print("PASS: 로컬 보충자료 증거표 60문항·360성분·9B 불일치 생성:",paths[0].parent)
        print("주의: 이 폴더에는 잠정 정답값과 모델 판단값이 포함되어 공개 GitHub에 올리지 않습니다.")

    print(f"PASS: 논문용 요약 1개 생성: {target}")
    print("주의: 정답지 미검증 상태. 논문 최종 결과가 아닌 탐색적 분석입니다.")


if __name__ == "__main__":
    main()
