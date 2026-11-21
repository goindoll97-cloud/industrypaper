"""Build a fully populated but UNVERIFIED provisional B-only 90-case answer key.

- Reuses the private, already frozen original B Gold (30 cases).
- Derives 60 NEW provisional answers from the locally indexed 2026-5 annex.
- Checks direct CAS listing, each explicit-exclusion clause, source row and ID.
- Never asserts independent legal/identity review; never changes v4.1 Gold.
- Model runner never receives these answers.

For exploratory benchmark execution only, NOT journal-ready legal ground truth.
"""
from __future__ import annotations

from collections import Counter
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import shutil

import prepare_b90 as b90

ROOT=b90.ROOT
V4=b90.V4
PRIVATE=b90.PRIVATE/"provisional_b90"
PROPOSALS=ROOT/"proposals"
GOLD=PRIVATE/"gold_90_B_PROVISIONAL.jsonl"
CASES=PRIVATE/"cases_90_B_PROVISIONAL.jsonl"
MANIFEST=PRIVATE/"provisional_manifest.json"
REVIEW=PRIVATE/"gold_90_B_review_queue_PROVISIONAL.csv"

# Only deliberate *non-direct-CAS* entries. Map each CAS to the actual
# OFFICIAL annex clause row and relation. Do NOT derive these from the
# proposed case's difficulty or regulatory_pattern tag.
# Each exception is an exception FROM THIS CLAUSE, not a finding that
# the substance is wholly unregulated by every other rule.
CLAUSE_ONLY = {
    "13755-29-8": (466, "GROUP_INCLUDED"),     # tetrafluoroboric acid salts
    "13826-83-0": (466, "GROUP_INCLUDED"),
    "7774-29-0": (187, "EXPLICIT_EXCEPTION"),  # mercuric iodide
    "95-80-7": (376, "GROUP_INCLUDED"),        # 2,4-toluenediamine
    "95-70-5": (376, "GROUP_INCLUDED"),        # 2,5-toluenediamine
    "13943-58-3": (112, "EXPLICIT_EXCEPTION"), # ferrocyanide salts
    "14075-53-7": (466, "EXPLICIT_EXCEPTION"), # potassium tetrafluoroborate
    "823-40-5": (376, "EXPLICIT_EXCEPTION"),   # 2,6-toluenediamine
    "2051-60-7": (483, "EXPLICIT_EXCEPTION"),  # 1 chlorine substitution PCB
}

# Prevent silently reading an unrelated CSV or mixing the original 30
# with a different version of the new 60.
def _hash(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def annex_rows():
    manifest=json.loads((V4/"data"/"manifest.json").read_text(encoding="utf-8"))
    f=V4/"data"/"official_annex_2026_5_full.csv"
    b90.require(_hash(f)==manifest["annex_sha256"],
                "공식 고시 원본 SHA256 검증 실패")
    with f.open(encoding="utf-8-sig",newline="") as fp:
        rows={int(z["excel_row"]):z for z in csv.DictReader(fp)}
    b90.require(len(rows)==1451,"고시의 1,451개 행이 완결되지 않았습니다")
    return rows,manifest


def exact_cas(row, cas):
    """In CAS field itself, not in an exception sentence in the name."""
    return bool(re.search(r"(?<![0-9])"+re.escape(cas)+r"(?![0-9])",
                          row["cas_field"]))


def proof_clause(row, cas, relation):
    name=row["name_en"]+" "+row["name_ko"]
    if relation=="GROUP_INCLUDED":
        if cas in ("13755-29-8","13826-83-0"):
            return "Tetrafluoroboric acid" in name and "salts" in name
        if cas in ("95-80-7","95-70-5"):
            return "Toluenediamines" in name and "823-40-5" in name
    if relation=="EXPLICIT_EXCEPTION":
        if cas=="13943-58-3":
            # The class is excluded by chemical family, not enumerated by CAS.
            return "ferrocyanide salts" in name.lower()
        if cas=="2051-60-7":
            # 2-chlorobiphenyl has one chlorine substitution (<3).
            return "pcbs" in name.lower() and "less than 3 chlorine" in name.lower()
        return cas in name
    return False


def derive_new(cases, review_rows, annex):
    """Pure audit-friendly derivation of 60 proposed new cases, 90 components.

    Every new component must either be CAS-exact in its selected official
    annex source row, or belong to a restricted explicit mapped clause.
    """
    records={(r["case_id"],r["component_id"]):r for r in review_rows}
    expected={(c["case_id"],z["component_id"])
              for c in cases if int(c["case_id"].split("-")[1])>10
              for z in c["components"]}
    b90.require(len(expected)==90 and len(records)==90 and set(records)==expected,
                "신규 60개 사례의 성분별 90행을 모두 확인해야 합니다")
    gold=[]
    audit=[]
    for case in cases:
        if int(case["case_id"].split("-")[1])<=10:
            continue
        cs=[]
        for comp in case["components"]:
            key=(case["case_id"],comp["component_id"])
            proposal=records[key]
            cas=comp["cas"]
            b90.require(proposal["cas"]==cas and
                        proposal["name_en"]==comp["name_en"] and
                        proposal["formula"]==comp["formula"],
                        f"{key}: 공개 후보와 실제 입력 물질정보 불일치")
            b90.require(proposal["identity_verified"]=="NO",
                        "이 스크립트는 검증 이전 공개 후보 버전만 수용합니다")
            if cas in CLAUSE_ONLY:
                row_id, relation=CLAUSE_ONLY[cas]
                mode="NON_DIRECT_CLASS_OR_EXCEPTION"
            else:
                row_text=proposal["candidate_annex_row"]
                b90.require(str(row_text).isdigit(),
                            f"{key}: 공식 고시 근거 후보 행 미지정")
                row_id=int(row_text)
                relation="DIRECT_SPECIFIC"
                mode="CAS_EXACT_IN_ANNEX"
            b90.require(row_id in annex,
                        f"{key}: 근거 원본 고시 행 {row_id} 미존재")
            source=annex[row_id]
            direct=exact_cas(source,cas)
            if cas=="2051-60-7":
                b90.require(comp["formula"]=="C12H9Cl" and "Chlorobiphenyl" in comp["name_en"],
                            "PCB 염소치환 수를 확인할 분자식/명칭 불일치")
            if mode=="CAS_EXACT_IN_ANNEX":
                b90.require(direct, f"{key}: 고시 CAS 필드에 {cas} 직접 표기되지 않음")
                b90.require(proposal["annex_match_kind"]=="SAME_CAS_APPEARS_IN_ANNEX",
                            f"{key}: 직기재 근거 데이터 유형 불일치")
            else:
                b90.require(not direct and proof_clause(source,cas,relation),
                            f"{key}: 명시적 포함/제외 원문 {row_id} 검증 실패")
                b90.require(proposal["annex_match_kind"]==
                            "POTENTIAL_CLASS_OR_EXCEPTION_CLAUSE",
                            f"{key}: 포괄 조항 후보 데이터 유형 불일치")
            b90.require(str(row_id)==proposal["candidate_annex_row"],
                        f"{key}: 고시행이 제안서와 다름")
            sub=source["sub_number"]
            covered=(relation!="EXPLICIT_EXCEPTION")
            cs.append({
                "component_id":comp["component_id"],"cas":cas,
                "source_excel_row":row_id,
                "direct_cas_match":direct,
                "covered_by_clause":covered,
                "expected_relation":relation,
                "relevant_entry_id":source["parent_designation_id"],
                "relevant_sub_number":int(sub) if sub.isdigit() else None,
            })
            audit.append({
                "test_id":case["test_id"],
                "component_id":comp["component_id"],
                "cas":cas,"name_en":comp["name_en"],
                "provisional_gold_relation":relation,
                "provisional_scope_of_clause":int(covered),
                "exact_cas_in_selected_annex_row":int(direct),
                "annex_excel_row":row_id,
                "annex_designation_id":source["parent_designation_id"],
                "annex_sub_number":sub,
                "annex_name_ko":source["name_ko"],
                "annex_name_en":source["name_en"],
                "method":mode,
                "review_status":"CURATED_PROVISIONAL",
                "independent_expert_verified":0,
                "identity_verified":0,
                "review_note":(
                    "Selected clause exclusion; does not imply no regulation anywhere"
                    if not covered else "Verify legal scope / designation order manually"
                ),
            })
        mixture=(all(x["covered_by_clause"] for x in cs)
                 if case["group"]=="MIXTURE" else None)
        gold.append({
            "test_id":case["test_id"],"case_id":case["case_id"],
            "condition":"B","group":case["group"],
            "difficulty":case["difficulty"],"component_gold":cs,
            "mixture_article3_all_listed":mixture,
            "review_status":"CURATED_PROVISIONAL",
            "independent_expert_review_completed":False,
        })
    b90.require(len(gold)==60 and len(audit)==90,
                "신규 잠정 Gold 생성 행 수 불일치")
    return gold,audit


def build_provisional():
    b90.require(not any(x.exists() for x in (GOLD,CASES,MANIFEST,REVIEW)),
                "이미 잠정 90문항 세트가 있습니다. 원본을 보존하고 같은 파일을 덮어쓰지 않습니다")
    old_b,_=b90.baseline_b()
    proposal=PROPOSALS/"PROPOSED_90_B_cases.jsonl"
    review_file=PROPOSALS/"PROPOSED_new_60_component_review.csv"
    b90.require(proposal.is_file() and review_file.is_file(),
                "GitHub에 반영된 90문항 후보 파일이 없습니다")
    all_cases=b90.load(proposal)
    b90.validate_cases(all_cases)
    by_id={x["test_id"]:x for x in all_cases}
    b90.require(len(old_b)==30 and
                all(by_id[x["test_id"]]==x for x in old_b),
                "기존 B 30문항의 원본 일치 확인 실패")
    annex,original_manifest=annex_rows()
    extra,audit=derive_new(all_cases,b90.read_csv(review_file),annex)
    original_gold=V4/"private"/"gold_60.jsonl"
    b90.require(original_gold.is_file(),
                "기존 비공개 정답지 필요: retrieval_v4/private/gold_60.jsonl "
                "(공개 GitHub에 Gold를 업로드하지 마세요)")
    from gold_integrity import expected_gold_sha
    b90.require(_hash(original_gold)==expected_gold_sha(V4,original_manifest),
                "기존 Gold SHA256 불일치; 이전 검증본을 보존·확인하세요")
    old_gold=[x for x in b90.load(original_gold) if x["condition"]=="B"]
    b90.require(len(old_gold)==30 and
                {x["test_id"] for x in old_gold}=={x["test_id"] for x in old_b},
                "기존 B Gold 30문항의 일대일 대응 불일치")
    for g in old_gold:
        b90.require(g["review_status"]=="CURATED_PROVISIONAL" and
                    g["independent_expert_review_completed"] is False,
                    "이 스크립트는 기존 잠정 Gold와만 결합합니다")
        given=by_id[g["test_id"]]
        b90.require(len(g["component_gold"])==len(given["components"]) and
                    all(a["component_id"]==b["component_id"] and a["cas"]==b["cas"]
                        for a,b in zip(g["component_gold"],given["components"])),
                    "기존 Gold의 성분별 CAS가 B 질문과 일치하지 않음: "+g["test_id"])
    combined=sorted([*old_gold,*extra],key=lambda x:x["test_id"])
    b90.require(len(combined)==90 and
                {x["test_id"] for x in combined}==set(by_id),
                "90문항 잠정 정답 누락·중복")
    PRIVATE.mkdir(parents=True,exist_ok=True)
    # Exact existing proposal bytes; no A-question can enter this dataset.
    shutil.copyfile(proposal,CASES)
    with GOLD.open("w",encoding="utf-8",newline="\n") as fp:
        for row in combined:
            fp.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+"\n")
    with REVIEW.open("w",encoding="utf-8-sig",newline="") as fp:
        writer=csv.DictWriter(fp,fieldnames=list(audit[0]))
        writer.writeheader()
        writer.writerows(audit)
    meta={
        "version":"b90_PROVISIONAL_v1",
        "review_status":"CURATED_PROVISIONAL",
        "independent_expert_review_completed":False,
        "identity_verified":False,
        "cases_sha256":_hash(CASES),
        "gold_sha256":_hash(GOLD),
        "annex_sha256":original_manifest["annex_sha256"],
        "legacy_cases_sha256":original_manifest["cases_sha256"],
        "legacy_gold_sha256":_hash(original_gold),
        "proposals_sha256":_hash(proposal),
        "new_component_review_sha256":_hash(review_file),
        "n_cases":90,"n_original_B":30,"n_new_B":60,
        "protocol_code_sha256":b90.source_code_sha(),
        "provisional_builder_sha256":_hash(Path(__file__)),
        "caution":"NOT independently reviewed. Exploratory scores only. Not regulatory advice.",
    }
    MANIFEST.write_text(json.dumps(meta,ensure_ascii=False,indent=2)+"\n",
                        encoding="utf-8")
    print("PASS: B 조건만 90문항, 잠정 Gold 90문항, 신규 90성분 고시 근거 대조표 작성")
    print("비공개 답지:",GOLD)
    print("비공개 검토표:",REVIEW)
    print("상태: CURATED_PROVISIONAL (독립 전문가 검증 전)")
    return meta


def assert_provisional(need_gold=False):
    b90.require(MANIFEST.is_file(),
                "먼저 python prepare_provisional_b90.py --create 실행")
    m=json.loads(MANIFEST.read_text(encoding="utf-8"))
    b90.require(m.get("review_status")=="CURATED_PROVISIONAL" and
                m.get("independent_expert_review_completed") is False and
                m.get("identity_verified") is False,
                "잠정 검증셋 상태 표시가 변경됨")
    b90.require(CASES.is_file() and _hash(CASES)==m["cases_sha256"],
                "잠정 질문 90개 SHA256 불일치")
    b90.require(_hash(PROPOSALS/"PROPOSED_90_B_cases.jsonl")==m["proposals_sha256"] and
                _hash(PROPOSALS/"PROPOSED_new_60_component_review.csv")==
                m["new_component_review_sha256"],
                "GitHub 후보 목록이 변경되어 별도 프로토콜 버전 필요")
    b90.require(m["protocol_code_sha256"]==b90.source_code_sha() and
                m["provisional_builder_sha256"]==_hash(Path(__file__)),
                "잠정 실험 고정 이후 관련 코드가 변경됨; 실험을 섞지 마세요")
    cases=b90.load(CASES)
    b90.validate_cases(cases)
    old,_=b90.baseline_b()
    ids={c["test_id"]:c for c in cases}
    b90.require(all(ids[c["test_id"]]==c for c in old),
                "이전 B 30문항의 입력이 변경됨")
    if need_gold:
        b90.require(GOLD.is_file() and _hash(GOLD)==m["gold_sha256"],
                    "잠정 Gold 파일 해시 오류")
        records=b90.load(GOLD)
        b90.require(len(records)==90 and
                    {x["test_id"] for x in records}==set(ids),
                    "잠정 정답 90문항 불일치")
        b90.require(all(x["review_status"]=="CURATED_PROVISIONAL" and
                        x["independent_expert_review_completed"] is False
                        for x in records),
                    "Gold 상태가 전문가 검증으로 잘못 표기됨")
        return cases,records,m
    return cases,m


def main():
    ap=argparse.ArgumentParser(description="90 B-only 잠정 답지 생성/검산 (전문가 확정 아님)")
    group=ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--create",action="store_true")
    group.add_argument("--check",action="store_true")
    args=ap.parse_args()
    if args.create:
        build_provisional()
    if args.check:
        c,g,meta=assert_provisional(need_gold=True)
        print(f"PASS: B-only {len(c)}문항 / provisional Gold {len(g)}문항 / "
              f"SHA256 {meta['gold_sha256']}")
        print("주의: 이 결과는 법령 전문가 검증 전 잠정 정답에 대한 실험입니다")


if __name__=="__main__":
    main()
