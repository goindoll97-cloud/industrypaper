"""Generate one concise manuscript-oriented results file from frozen local v4.1 outputs.

Usage (from llm_capability_study/retrieval_v4):
    python ..\make_paper_report.py

The program does not run a model, modify Gold, or rewrite legacy scoring CSVs.
Only provisional aggregate statistics are exported. No answers leave the PC.
"""
from __future__ import annotations

import argparse
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
        "동결 실험일: 2026-11-20; 결과는 고정 Gold·settings hash와 원본 JSONL에서 계산",
        "",
    ])
    for model in models:
        meta = run_info[model]
        lines.append(f"- {LABELS[model]}: settings SHA256 \`{meta['settings_sha256']}\`; "
                     f"JSONL SHA256 \`{meta['file_sha256']}\`")
    lines.append("")
    return "\n".join(lines)


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
    _, consistency = audit_consistency(details)
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
        _, new_consistency = audit_consistency(new_details)
        cases.extend(new_cases)
        components.extend(new_components)
        consistency.extend(new_consistency)
        run_info.update(new_meta)
        selected_models.append(stronger)
    report = render(cases, components, consistency, run_info, gold_sha,
                    models=selected_models)
    target = folder / "PAPER_RESULTS_v4_1.md"
    if target.exists() and target.read_text(encoding="utf-8") != report:
        print("주의: 기존 논문용 보고서를 덮어씁니다 (같은 고정 Gold·실험 설정)")
    target.write_text(report, encoding="utf-8")
    print(f"PASS: 논문용 요약 1개 생성: {target}")
    print("주의: 정답지 미검증 상태. 논문 최종 결과가 아닌 탐색적 분석입니다.")


if __name__ == "__main__":
    main()
