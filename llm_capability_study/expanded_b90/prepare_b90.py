"""Prepare and lock a B-only 90-case regulatory benchmark (no generated legal labels).

Workflow: --init-candidates -> fill & verify 60 new candidates ->
--build-cases -> --init-gold -> independent legal review of all 90 ->
--freeze. Does not modify frozen v4.1 files.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent
V4 = ROOT.parent / "retrieval_v4"
DATA = ROOT / "data"
PRIVATE = ROOT / "private"
sys.path.insert(0, str(V4))
from run_retrieval import load  # noqa: E402

GROUPS = {"S": "PARENT_AND_SALTS", "C": "COMPOUND_CLASS", "M": "MIXTURE"}
RELATIONS = {"DIRECT_SPECIFIC", "GROUP_INCLUDED", "EXPLICIT_EXCEPTION"}
PATTERNS = {
    "PARENT_AND_SALTS": {"DIRECT", "SALT_INCLUDED", "PARENT_NAMING", "EXPLICIT_EXCEPTION"},
    "COMPOUND_CLASS": {"DIRECT", "CLASS_INCLUDED", "ISOMER_CONDITION", "EXPLICIT_EXCEPTION"},
    "MIXTURE": {"ALL_DIRECT", "GROUP_INCLUDED", "ONE_EXCEPTION", "MIXED_CLAUSES"},
}
CANDIDATE_COLS = (
    "case_id", "group", "difficulty", "component_id", "cas", "name_en",
    "formula", "mass_percent", "identity_source_url", "identity_reviewer",
    "identity_verified", "selection_rationale", "difficulty_rationale",
    "regulatory_pattern",
)
GOLD_COLS = (
    "test_id", "case_id", "group", "difficulty", "component_id", "cas",
    "source_excel_row", "expected_relation", "mixture_article3_all_listed",
    "legal_basis_note", "legal_reviewer", "independent_legal_reviewed",
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def valid_cas(text):
    """CAS check-digit validation; catches common transcription errors."""
    if not re.fullmatch(r"\d{2,7}-\d\d-\d", text):
        return False
    digits = text.replace("-", "")
    check = sum(position * int(digit) for position, digit in
                enumerate(reversed(digits[:-1]), start=1)) % 10
    return check == int(digits[-1])


def source_code_sha():
    """Pin key source and preprocessing code so a later pull cannot silently
    run a different retrieval protocol against the same frozen cases."""
    paths = (V4 / "run_retrieval.py", V4 / "search_legal_db.py",
             V4 / "build_legal_db.py", ROOT / "prepare_b90.py",
             ROOT / "run_b90.py")
    return {str(p.relative_to(ROOT.parent)): sha(p) for p in paths}


def require(flag, message):
    if not flag:
        raise ValueError(message)


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, columns, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="raise")
        w.writeheader()
        w.writerows(rows)


def baseline_b():
    manifest = json.loads((V4 / "data" / "manifest.json").read_text(encoding="utf-8"))
    old = V4 / "data" / "cases_60.jsonl"
    annex = V4 / "data" / "official_annex_2026_5_full.csv"
    require(sha(old) == manifest["cases_sha256"], "기존 60문항 SHA256 변경 감지")
    require(sha(annex) == manifest["annex_sha256"], "공식 고시 SHA256 변경 감지")
    cases = [x for x in load(old) if x["condition"] == "B"]
    require(len(cases) == 30, "기존 B 문항은 정확히 30개여야 합니다")
    require(Counter((c["group"], c["difficulty"]) for c in cases)
            == Counter({(g, d): 5 for g in GROUPS.values()
                        for d in ("EASY", "HARD")}), "기존 B 문항의 층화 오류")
    require(all(all(comp["formula"] and not comp["smiles"] for comp in c["components"])
                for c in cases), "기존 B에는 분자식만 있고 SMILES는 없어야 합니다")
    return cases, manifest


def slots():
    """20 new cases/type, 10 EASY + 10 HARD; 2/3 ingredients for mixtures."""
    rows = []
    for initial, group in GROUPS.items():
        for n in range(11, 31):
            difficulty = "EASY" if n <= 20 else "HARD"
            ncomp = 1 if initial != "M" else (2 if difficulty == "EASY" else 3)
            for j in range(1, ncomp + 1):
                x = dict.fromkeys(CANDIDATE_COLS, "")
                x.update(case_id=f"{initial}-{n:02d}", group=group,
                         difficulty=difficulty, component_id=f"C{j}")
                rows.append(x)
    return rows


def init_candidates(path):
    require(not path.exists(), "기존 후보 표가 있습니다. 덮어쓰지 않습니다: " + str(path))
    write_csv(path, CANDIDATE_COLS, slots())
    print(f"후보 입력표 생성: {path} (60개 새 사례, 성분 90행; 화학적 사실은 빈칸)")


def validate_cases(cases):
    require(len(cases) == 90, "총 90문항이 아닙니다")
    ids = [c["test_id"] for c in cases]
    require(len(set(ids)) == 90, "중복 test_id")
    require(all(c["condition"] == "B" and c["test_id"] == c["case_id"]+"-B"
                for c in cases), "B 조건만 허용")
    distribution = Counter((c["group"], c["difficulty"]) for c in cases)
    require(distribution == Counter({(g, d):15 for g in GROUPS.values()
                                    for d in ("EASY", "HARD")}),
            "유형별 30, EASY/HARD 각 15 배분 불일치")
    for c in cases:
        comps = c["components"]
        n = 2 if c["group"] == "MIXTURE" and c["difficulty"] == "EASY" else (
            3 if c["group"] == "MIXTURE" else 1)
        require(len(comps) == n, f"{c['test_id']}: 성분 수 오류")
        require([z["component_id"] for z in comps] ==
                [f"C{i}" for i in range(1, n+1)], "성분 ID 불일치")
        for z in comps:
            require(z["cas"] and z["name_en"] and z["formula"] and z["smiles"] is None,
                    f"{c['test_id']}: CAS/영문명/분자식 누락 또는 SMILES 혼입")
            if n == 1:
                require(z["mass_percent"] is None, "단일물질의 질량백분율은 null")
            else:
                require(isinstance(z["mass_percent"], (float, int)) and
                        0 < z["mass_percent"] <= 100, "혼합물 성분함량 오류")
        if n > 1:
            require(abs(sum(x["mass_percent"] for x in comps)-100) < 1e-8,
                    "혼합물 성분함량 합계는 100이어야 합니다")
            require(len({z["cas"] for z in comps}) == n, "한 혼합물에 CAS 중복")
    signatures = []
    for c in cases:
        if c["group"] == "MIXTURE":
            signatures.append(("MIXTURE", tuple(sorted(
                (z["cas"], round(z["mass_percent"], 6)) for z in c["components"]))))
        else:
            signatures.append(("SINGLE", c["components"][0]["cas"]))
    require(len(set(signatures)) == 90,
            "동일 단일 CAS 또는 동일 혼합물 조성 중복; 독립 사례로 계산 금지")
    return True


def build_cases(csv_path):
    original, m = baseline_b()
    rows = read_csv(csv_path)
    require(len(rows) == 90, "신규 후보표는 60사례, 성분별 90행이어야 합니다")
    expected = {(r["case_id"], r["component_id"]):r for r in slots()}
    found = {}
    for r in rows:
        key = r["case_id"], r["component_id"]
        require(key in expected and key not in found, "새 사례 슬롯 ID 중복/오류: "+str(key))
        require(r["group"] == expected[key]["group"] and
                r["difficulty"] == expected[key]["difficulty"],
                "유형/난이도 슬롯은 바꿀 수 없습니다: "+str(key))
        for key2 in ("cas","name_en","formula","identity_source_url",
                     "identity_reviewer","selection_rationale",
                     "difficulty_rationale","regulatory_pattern"):
            require(r[key2].strip(), f"{key}/{key2}: 비어 있음")
        require(r["identity_verified"].strip().upper() == "YES",
                str(key)+": CAS·영문명·분자식의 독립 확인 필요")
        require(r["identity_source_url"].startswith(("https://","http://")),
                str(key)+": 검증 가능한 출처 URL 필요")
        require(valid_cas(r["cas"].strip()),
                str(key)+": CAS 형식 또는 검사숫자(check digit)가 잘못되었습니다")
        require(r["regulatory_pattern"] in PATTERNS[r["group"]],
                str(key)+": 규제 상황 태그가 사전정의된 값과 다릅니다. "
                + ", ".join(sorted(PATTERNS[r["group"]])))
        found[key] = r
    require(set(found) == set(expected), "후보 슬롯 누락")
    # One scenario has one pre-assigned regulatory-pattern tag even if
    # its mixture contains 2–3 chemical components. Require diversity
    # within each of the six group/difficulty strata.
    by_case_pattern = defaultdict(set)
    by_stratum_pattern = defaultdict(set)
    for row in found.values():
        by_case_pattern[row["case_id"]].add(row["regulatory_pattern"])
        by_stratum_pattern[row["group"], row["difficulty"]].add(row["regulatory_pattern"])
    require(all(len(patterns) == 1 for patterns in by_case_pattern.values()),
            "같은 혼합물의 성분별 규제 상황 태그가 일치하지 않습니다")
    require(all(len(patterns) >= 2 for patterns in by_stratum_pattern.values()),
            "각 유형·난이도 10개 신규 사례에는 규제 상황을 2종 이상 포함하세요")
    created = []
    for first, group in GROUPS.items():
        for n in range(11, 31):
            cid = f"{first}-{n:02d}"
            difficulty = "EASY" if n <= 20 else "HARD"
            count = 1 if first != "M" else (2 if difficulty=="EASY" else 3)
            comps = []
            for j in range(1, count+1):
                r = found[cid, f"C{j}"]
                percent = None if count==1 else float(r["mass_percent"])
                comps.append({"cas":r["cas"].strip(),"component_id":f"C{j}",
                              "formula":r["formula"].strip(),"mass_percent":percent,
                              "name_en":r["name_en"].strip(),"smiles":None})
            created.append({"case_id":cid,"test_id":cid+"-B","condition":"B",
                            "group":group,"difficulty":difficulty,
                            "scenario_kind":"FORMULATED_MIXTURE" if first=="M" else "PURE_SUBSTANCE",
                            "components":comps})
    cases = sorted([*original,*created], key=lambda c:c["test_id"])
    validate_cases(cases)
    DATA.mkdir(exist_ok=True)
    target = DATA / "cases_90_B.jsonl"
    require(not target.exists(), "이미 생성된 90문항이 있습니다. 사후 수정·덮어쓰기 금지")
    with target.open("w",encoding="utf-8",newline="\n") as f:
        for case in cases:
            f.write(json.dumps(case,ensure_ascii=False,sort_keys=True)+"\n")
    print("검증 통과: 30개 기존 B + 60개 신규 B = 90개. 작성:",target)
    print("입력 SHA256:", sha(target))
    return target


def init_gold():
    cases_path = DATA/"cases_90_B.jsonl"
    require(cases_path.exists(), "먼저 --build-cases 실행")
    cases = load(cases_path)
    validate_cases(cases)
    old_gold_path = V4/"private"/"gold_60.jsonl"
    oldgold={}
    if old_gold_path.exists():
        from gold_integrity import expected_gold_sha
        m=json.loads((V4/"data"/"manifest.json").read_text(encoding="utf-8"))
        require(sha(old_gold_path)==expected_gold_sha(V4,m),
                "기존 30사례 Gold 해시 불일치")
        oldgold={x["test_id"]:x for x in load(old_gold_path) if x["condition"]=="B"}
        require(len(oldgold)==30,"기존 B Gold 30건 누락")
    rows=[]
    for c in cases:
        src = oldgold.get(c["test_id"])
        for j, comp in enumerate(c["components"]):
            g = src["component_gold"][j] if src else {}
            rows.append({
                "test_id":c["test_id"],"case_id":c["case_id"],
                "group":c["group"],"difficulty":c["difficulty"],
                "component_id":comp["component_id"],"cas":comp["cas"],
                "source_excel_row":g.get("source_excel_row",""),
                "expected_relation":g.get("expected_relation",""),
                "mixture_article3_all_listed":(
                    "" if c["group"]!="MIXTURE" else
                    ("YES" if src["mixture_article3_all_listed"] else "NO") if src else ""),
                "legal_basis_note":"","legal_reviewer":"",
                "independent_legal_reviewed":"NO"})
    target=PRIVATE/"gold_review_90_B.csv"
    require(not target.exists(),"기존 검토표를 덮어쓰지 않습니다")
    write_csv(target,GOLD_COLS,rows)
    print(f"독립 법령 검토표 생성: {target}. 기존 B Gold는 참고용으로만 사전기입.")
    print("모든 90문항의 근거·관계·예외를 별도 전문가가 검토하고 YES로 표시하세요.")


def freeze():
    candidates_path=DATA/"cases_90_B.jsonl"
    review_path=PRIVATE/"gold_review_90_B.csv"
    require(candidates_path.exists() and review_path.exists(),"90문항/Gold 검토표 준비 필요")
    cases=load(candidates_path)
    validate_cases(cases)
    rows=read_csv(review_path)
    expected={(c["test_id"],x["component_id"]):(c,x) for c in cases for x in c["components"]}
    require(len(rows)==len(expected),"Gold 검토 성분 행 수 불일치")
    grouped=defaultdict(list)
    for r in rows:
        key=(r["test_id"],r["component_id"])
        require(key in expected,"Gold 문항/성분 ID 오류: "+str(key))
        c,comp=expected[key]
        require(r["case_id"]==c["case_id"] and r["cas"]==comp["cas"] and
                r["group"]==c["group"] and r["difficulty"]==c["difficulty"],
                str(key)+": 검토표의 문항/성분이 고정 입력과 불일치")
        require(r["independent_legal_reviewed"].upper()=="YES",
                str(key)+": 독립 전문가 검토를 완료해야 고정할 수 있습니다")
        require(r["legal_reviewer"].strip() and len(r["legal_basis_note"].strip())>=8,
                str(key)+": 검토자와 법령 근거 설명 필요")
        require(r["expected_relation"] in RELATIONS,
                str(key)+": 법령 적용관계 검토 필요")
        grouped[r["test_id"]].append(r)
    require(len(grouped)==90 and all(len(grouped[c["test_id"]])==len(c["components"])
                                      for c in cases), "Gold 성분 누락/중복")
    with (V4/"data"/"official_annex_2026_5_full.csv").open(encoding="utf-8-sig",newline="") as f:
        annex={int(r["excel_row"]):r for r in csv.DictReader(f)}
    gold=[]
    for case in cases:
        comp_gold=[]
        for comp in case["components"]:
            r=next(x for x in grouped[case["test_id"]]
                   if x["component_id"]==comp["component_id"])
            try:
                rowid=int(r["source_excel_row"])
            except (ValueError,TypeError) as exc:
                raise ValueError("근거 원본 고시 행 필수: "+case["test_id"]) from exc
            require(rowid in annex,"공식 고시 근거행 미존재")
            reference=annex[rowid]
            cas=comp["cas"]
            direct=bool(re.search(r"(?<!\d)"+re.escape(cas)+r"(?!\d)",
                                  reference["cas_field"]))
            relation=r["expected_relation"]
            require(direct == (relation=="DIRECT_SPECIFIC"),
                    case["test_id"]+": 직접 CAS 기재와 관계 유형 불일치")
            sub=reference["sub_number"]
            comp_gold.append({
                "component_id":comp["component_id"],"cas":cas,
                "source_excel_row":rowid,"direct_cas_match":direct,
                "covered_by_clause":relation!="EXPLICIT_EXCEPTION",
                "expected_relation":relation,
                "relevant_entry_id":reference["parent_designation_id"],
                "relevant_sub_number":int(sub) if sub.isdigit() else None,
            })
        is_mix=case["group"]=="MIXTURE"
        given={r["mixture_article3_all_listed"].upper()
               for r in grouped[case["test_id"]]} if is_mix else set()
        if is_mix:
            require(len(given)==1 and given <= {"YES","NO"},
                    "혼합물 Gold 제3조 전부 지정 요건 누락/불일치")
            mix=next(iter(given))=="YES"
            require(mix==all(c["covered_by_clause"] for c in comp_gold),
                    "혼합물 제3조와 성분별 지정범위 판단 모순")
        else:
            mix=None
        gold.append({
            "test_id":case["test_id"],"case_id":case["case_id"],
            "condition":"B","group":case["group"],"difficulty":case["difficulty"],
            "component_gold":comp_gold,"mixture_article3_all_listed":mix,
            "review_status":"INDEPENDENT_EXPERT_REVIEWED",
            "independent_expert_review_completed":True,
        })
    PRIVATE.mkdir(exist_ok=True)
    gpath=PRIVATE/"gold_90_B.jsonl"
    lock=PRIVATE/"frozen_manifest.json"
    require(not gpath.exists() and not lock.exists(),
            "Gold/고정 manifest가 존재합니다. 기존 버전을 덮어쓰지 마세요.")
    with gpath.open("w",encoding="utf-8",newline="\n") as f:
        for g in gold:f.write(json.dumps(g,ensure_ascii=False,sort_keys=True)+"\n")
    _, old_manifest=baseline_b()
    metadata={
        "version":"b90_v1","cases_sha256":sha(candidates_path),
        "gold_sha256":sha(gpath),
        "annex_sha256":old_manifest["annex_sha256"],
        "legacy_cases_sha256":old_manifest["cases_sha256"],
        "n_cases":90,"n_original_B":30,"n_new_B":60,
        "review_status":"INDEPENDENT_EXPERT_REVIEWED",
        "identity_review_csv_sha256":sha(PRIVATE/"new_cases_review.csv"),
        "legal_review_csv_sha256":sha(review_path),
        "protocol_code_sha256":source_code_sha(),
        "note":"Locally validated Gold; reviewer responsibility remains with research team",
    }
    lock.write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("PASS: B 조건 90문항 및 전문가 검토 Gold 고정 완료")
    print("실험용 lock:",lock)
    return metadata


def assert_frozen(need_gold=False):
    p=PRIVATE/"frozen_manifest.json"
    require(p.exists(),"독립 전문가 검토 및 --freeze가 완료되지 않았습니다")
    m=json.loads(p.read_text(encoding="utf-8"))
    cases_path=DATA/"cases_90_B.jsonl"
    require(cases_path.exists() and sha(cases_path)==m["cases_sha256"],
            "동결한 90문항 SHA256 불일치")
    cases=load(cases_path)
    validate_cases(cases)
    orig, legacy=baseline_b()
    by_id={x["test_id"]:x for x in cases}
    require(all(by_id[c["test_id"]]==c for c in orig),
            "기존 B 30문항이 변경되었습니다")
    require(m["annex_sha256"]==legacy["annex_sha256"] and
            m["legacy_cases_sha256"]==legacy["cases_sha256"],
            "기존 고시/문항 원본 변경")
    require(m.get("protocol_code_sha256")==source_code_sha(),
            "동결 이후 검색·추론 코드가 바뀌었습니다. 새 버전으로 검토 필요")
    require(m.get("identity_review_csv_sha256")==
            sha(PRIVATE/"new_cases_review.csv"),
            "동결 이후 화학물질 원자료 검토표가 변경됨")
    if need_gold:
        require(m.get("legal_review_csv_sha256")==
                sha(PRIVATE/"gold_review_90_B.csv"),
                "동결 이후 법령 전문가 검토표가 변경됨")
        g=PRIVATE/"gold_90_B.jsonl"
        require(g.exists() and sha(g)==m["gold_sha256"],"90문항 Gold SHA 불일치")
        rows=load(g)
        require(len(rows)==90 and {x["test_id"] for x in rows}==set(by_id),
                "90문항 Gold 완결성 오류")
        require(all(x["independent_expert_review_completed"] and
                    x["review_status"]=="INDEPENDENT_EXPERT_REVIEWED"
                    for x in rows),"Gold 독립 검토 누락")
        return cases, rows, m
    return cases, m


def main():
    ap=argparse.ArgumentParser(description="기존 B 30개를 유지한 90문항 신규 평가셋 구축")
    g=ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--init-candidates",action="store_true")
    g.add_argument("--build-cases",action="store_true")
    g.add_argument("--init-gold",action="store_true")
    g.add_argument("--freeze",action="store_true")
    g.add_argument("--check",action="store_true")
    args=ap.parse_args()
    if args.init_candidates:init_candidates(PRIVATE/"new_cases_review.csv")
    if args.build_cases:build_cases(PRIVATE/"new_cases_review.csv")
    if args.init_gold:init_gold()
    if args.freeze:freeze()
    if args.check:
        cases,gold,m=assert_frozen(need_gold=True)
        print("PASS:",len(cases),"문항 /",len(gold),"Gold / frozen",m["cases_sha256"])


if __name__=="__main__":
    main()
