#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2026-5 검증셋·정답지를 공식 별표 엑셀에서 독립적으로 다시 계산해 대조한다 (로컬 실행용, openpyxl만 필요).

    python verify_2026_5.py --official "2026-5_(별표) 인체등유해성물질 목록(전체).xlsx" \
        --validation 2026_5_LLM_Validation_Set.xlsx --gold 2026_5_LLM_GOLD_Answer_Key.xlsx [--out mismatches.csv]

공식 별표만 근거로 삼고 정답지의 값을 빌리지 않는다. 불일치가 있으면 종료 코드 1.
점검 항목: 원본 해시 / LEGAL_REFERENCE 원본 일치 / 선정 규칙 / 질의 구조(300 CAS x 4) / 농도 패턴 /
행별 정답 재계산 / expected_output_json 일관성 / 질의·정답 파일 간 일치 / 정답 유출 / QC 요약 수치 /
별표 CAS-영문명 PubChem 교차확인(300개 CAS; 인터넷 필요, 접속 불가면 이 항목만 건너뜀. 결과는 '사람이 볼 후보'이며 FAIL이 아님).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

import openpyxl

HAZ = [("acute", "급성"), ("chronic", "만성"), ("ecological", "생태")]
CAS_RE = re.compile(r"\d{2,7}-\d{2}-\d")
FIRST_DATA_ROW, LAST_DATA_ROW = 5, 1455

results = []          # (name, ok, detail)
mismatches = []       # rows for --out


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


def bad(check_name, key, field, expected, actual):
    mismatches.append({"check": check_name, "key": key, "field": field, "expected": expected, "actual": actual})


def valid_cas(cas):
    m = re.fullmatch(r"(\d{2,7})-(\d{2})-(\d)", cas or "")
    if not m:
        return False
    digits = (m.group(1) + m.group(2))[::-1]
    return sum((i + 1) * int(d) for i, d in enumerate(digits)) % 10 == int(m.group(3))


def text(v):
    return "" if v is None else str(v).strip()


def num(v):
    """'-'/빈칸 -> None, 숫자 -> float, 해석 불가 -> 'BAD'."""
    s = text(v)
    if s in ("", "-"):
        return None
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return "BAD"


def close(a, b):
    if a is None or b is None or a == "BAD" or b == "BAD":
        return a == b
    return math.isclose(float(a), float(b), rel_tol=1e-6, abs_tol=1e-9)


def to_bool(v):
    return v is True or text(v).lower() == "true"


def sheet_rows(path, name):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    return [list(r) for r in wb[name].iter_rows(values_only=True)]


def table(path, name):
    rows = sheet_rows(path, name)
    head = [text(h) for h in rows[0]]
    return [dict(zip(head, r)) for r in rows[1:] if any(c is not None and text(c) != "" for c in r)]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_official(path):
    """공식 별표 -> {엑셀 행번호: 레코드}. 고유번호가 빈 행은 직전 고유번호를 잇는다."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["유해성물질 지정"]
    rows, last_id = {}, ""
    for rno, r in enumerate(ws.iter_rows(values_only=True), 1):
        if rno < FIRST_DATA_ROW or rno > LAST_DATA_ROW:
            continue
        r = list(r) + [None] * (10 - len(r))
        orig = text(r[0])
        if orig:
            last_id = orig
        rows[rno] = {
            "row": rno, "orig_id": orig, "eff_id": last_id, "sub": text(r[1]), "ko": text(r[2]), "en": text(r[3]),
            "cas_raw": text(r[4]), "acute": num(r[5]), "chronic": num(r[6]), "ecological": num(r[7]),
            "types": text(r[8]), "former": text(r[9]),
        }
    return rows


# ---- PubChem 교차확인: 별표의 CAS와 영문명이 서로 맞는지 (별표 자체의 오탈자 후보 탐지) -------------------
PUG = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{}/{}/JSON"


def norm_name(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def classify_name(official_en, names):
    """MATCH(정규화 일치) / SIMILAR(유사도>=0.8 또는 포함) / MISMATCH."""
    target = norm_name(official_en)
    pool = [norm_name(n) for n in names if n]
    if not target or not pool:
        return "MISMATCH", 0.0
    if target in pool:
        return "MATCH", 1.0
    best = max(SequenceMatcher(None, target, n).ratio() for n in pool[:200])
    if best >= 0.8 or any(target in n or (len(n) > 6 and n in target) for n in pool[:200]):
        return "SIMILAR", best
    return "MISMATCH", best


def pug_get(cas, what, retries=3):
    url = PUG.format(urllib.parse.quote(cas), what)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "verify_2026_5"}), timeout=30) as r:
                return json.loads(r.read().decode("utf-8")), ""
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None, "NOT_FOUND"
            if e.code in (429, 503):
                time.sleep(2 * (attempt + 1))
                continue
            return None, f"HTTP_{e.code}"
        except Exception as e:  # 네트워크 불가 등
            return None, f"NETWORK:{type(e).__name__}"
    return None, "RETRY_EXCEEDED"


def pubchem_crosscheck(cas_to_name, cache_path):
    """cas_to_name: {CAS: 별표 영문명}. 반환: (건수 Counter, 검토 후보 목록, 건너뜀 사유)."""
    cache = {}
    if cache_path.is_file():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    rows = []
    for i, (cas, en) in enumerate(sorted(cas_to_name.items()), 1):
        rec = cache.get(cas)
        if rec is None:
            props, err = pug_get(cas, "property/Title,MolecularFormula")
            if err.startswith("NETWORK") and i == 1:
                return None, [], err
            syn, err2 = (pug_get(cas, "synonyms") if props else (None, err))
            title = formula = ""
            names = []
            if props:
                p = props["PropertyTable"]["Properties"][0]
                title, formula = p.get("Title", ""), p.get("MolecularFormula", "")
            if syn:
                names = syn["InformationList"]["Information"][0].get("Synonym", [])
            rec = {"cid": (props["PropertyTable"]["Properties"][0].get("CID") if props else None),
                   "title": title, "formula": formula, "names": names[:200], "error": err or err2}
            if not rec["error"] or rec["error"] == "NOT_FOUND":
                cache[cas] = rec
            time.sleep(0.25)
            if i % 25 == 0:
                cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
                print(f"  PubChem 조회 {i}/{len(cas_to_name)}", flush=True)
        if rec["error"] and rec["error"] != "NOT_FOUND":
            rows.append({"cas": cas, "official_en": en, "status": "ERROR", "pubchem_title": "", "similarity": "", "note": rec["error"]})
        elif not rec["cid"]:
            rows.append({"cas": cas, "official_en": en, "status": "NOT_RESOLVED", "pubchem_title": "", "similarity": "", "note": "PubChem에 이 CAS 없음"})
        else:
            status, sim = classify_name(en, [rec["title"]] + rec["names"])
            rows.append({"cas": cas, "official_en": en, "status": status, "pubchem_title": rec["title"],
                         "similarity": round(sim, 2), "note": rec["formula"]})
    cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return Counter(r["status"] for r in rows), rows, ""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--official", required=True)
    ap.add_argument("--validation", required=True)
    ap.add_argument("--gold", required=True)
    ap.add_argument("--out", default="", help="불일치 목록 CSV 저장 경로 (선택)")
    ap.add_argument("--pubchem-out", default="pubchem_name_review.csv", help="PubChem 교차확인 결과 CSV")
    ap.add_argument("--cache", default="pubchem_cache.json", help="PubChem 조회 캐시(재실행 시 재사용)")
    args = ap.parse_args()

    official = parse_official(args.official)
    cases = table(args.validation, "TEST_CASES")
    legal = table(args.validation, "LEGAL_REFERENCE")
    gold = table(args.gold, "GOLD_ANSWERS")
    qc = {text(r[0]): text(r[1]) for r in sheet_rows(args.gold, "DATASET_QC")[1:] if r and r[0]}

    # 1. 원본 해시
    h = sha256(args.official)
    rec = qc.get("공식 엑셀 원본 SHA-256", "")
    check("원본 해시: 업로드한 공식 파일 = QC에 적힌 해시", h == rec, f"파일 {h[:16]}… / 기록 {rec[:16]}…")
    check("공식 별표 행 수 = 1,451 (5~1455행)", len(official) == 1451, str(len(official)))

    # 2. LEGAL_REFERENCE 원본 일치
    lr_by_row = {int(float(text(r["annex_excel_row"]))): r for r in legal}
    n_bad = 0
    check("LEGAL_REFERENCE 행 수 = 공식 별표", len(legal) == len(official), f"{len(legal)} vs {len(official)}")
    for rno, o in official.items():
        r = lr_by_row.get(rno)
        if r is None:
            n_bad += 1
            bad("LEGAL_REFERENCE", rno, "row", "present", "missing")
            continue
        pairs = [("original_entry_id", o["orig_id"], text(r["original_entry_id"])),
                 ("effective_entry_id", o["eff_id"], text(r["effective_entry_id"])),
                 ("official_name_ko", o["ko"], text(r["official_name_ko"])),
                 ("official_name_en", o["en"], text(r["official_name_en"])),
                 ("cas_raw", o["cas_raw"], text(r["cas_raw"]))]
        for f, e, a in pairs:
            if e != a:
                n_bad += 1
                bad("LEGAL_REFERENCE", rno, f, e, a)
        for key, col in (("acute", "acute_threshold_pct"), ("chronic", "chronic_threshold_pct"),
                         ("ecological", "ecological_threshold_pct")):
            if not close(o[key], num(r[col])):
                n_bad += 1
                bad("LEGAL_REFERENCE", rno, col, o[key], r[col])
    check("LEGAL_REFERENCE 전 행·전 필드가 공식 별표와 일치", n_bad == 0, f"불일치 {n_bad}건")

    # 3. 공식 별표 기준 선정 적격성 (CAS 1개·체크디지트·별표 내 유일·수치기준 명시·유해성명 일치)
    tok_rows = defaultdict(set)
    for rno, o in official.items():
        for t in CAS_RE.findall(o["cas_raw"]):
            tok_rows[t].add(rno)

    def eligibility(o, cas):
        why = []
        toks = CAS_RE.findall(o["cas_raw"])
        if len(toks) != 1 or o["cas_raw"] != toks[0]:
            why.append("CAS_NOT_SINGLE")
        if not valid_cas(cas):
            why.append("CHECKDIGIT")
        if len(tok_rows.get(cas, ())) != 1:
            why.append("CAS_NOT_UNIQUE_IN_ANNEX")
        for k, _ in HAZ:
            if o[k] == "BAD":
                why.append("THRESHOLD_UNPARSEABLE")
        named = {ko for k, ko in HAZ if o[k] not in (None, "BAD")}
        listed = {ko for ko in re.split(r"[/,·\s]+", o["types"]) if ko}
        if named != listed:
            why.append(f"HAZARD_TYPE_MISMATCH({'/'.join(sorted(named))} vs {o['types']})")
        return why

    # 4. 질의 구조
    check("TEST_CASES·GOLD_ANSWERS 모두 1,200행", len(cases) == 1200 and len(gold) == 1200, f"{len(cases)} / {len(gold)}")
    check("test_id 중복 없음", len({c["test_id"] for c in cases}) == len(cases) and len({g["test_id"] for g in gold}) == len(gold))
    cases_by_id = {c["test_id"]: c for c in cases}
    gold_by_id = {g["test_id"]: g for g in gold}
    check("TEST_CASES와 GOLD의 test_id 집합 동일", set(cases_by_id) == set(gold_by_id))
    per_cas = defaultdict(list)
    for g in gold:
        per_cas[text(g["cas_no"])].append(g)
    check("독립 CAS 300개", len(per_cas) == 300, str(len(per_cas)))
    check("CAS마다 질의 4개", all(len(v) == 4 for v in per_cas.values()),
          str(Counter(len(v) for v in per_cas.values())))
    chem_ids = defaultdict(set)
    for g in gold:
        chem_ids[text(g["chemical_case_id"])].add(text(g["cas_no"]))
    check("chemical_case_id ↔ CAS 1:1", all(len(v) == 1 for v in chem_ids.values()) and len(chem_ids) == 300)

    # 5. 행별 정답 재계산
    n_row_bad = 0
    below = above = 0
    types_count = Counter()
    kinds = Counter()
    for g in gold:
        tid = text(g["test_id"])
        cas, pct = text(g["cas_no"]), float(g["virtual_mass_percent"])
        rno = int(float(text(g["annex_excel_row"])))
        o = official.get(rno)
        if o is None:
            n_row_bad += 1
            bad("GOLD", tid, "annex_excel_row", "1~1455 범위 내 행", rno)
            continue
        if o["cas_raw"] != cas:
            n_row_bad += 1
            bad("GOLD", tid, "cas_no", o["cas_raw"], cas)
        why = eligibility(o, cas)
        if why:
            n_row_bad += 1
            bad("GOLD", tid, "eligibility", "선정 규칙 충족", "; ".join(why))
        exp = {
            "regulatory_entry_id": o["eff_id"], "official_name_ko": o["ko"], "official_name_en": o["en"],
            "annex_sub_number": o["sub"],
        }
        for f, e in exp.items():
            a = text(g[f])
            a = a[:-2] if f == "annex_sub_number" and a.endswith(".0") else a
            if a != e:
                n_row_bad += 1
                bad("GOLD", tid, f, e, a)
        kind = "SPECIFIC_COMPONENT" if o["sub"] else "DIRECT_NAMED_SUBSTANCE"
        kinds[kind] += 1
        if text(g["annex_record_kind"]) != kind:
            n_row_bad += 1
            bad("GOLD", tid, "annex_record_kind", kind, text(g["annex_record_kind"]))
        if not to_bool(g["listed_in_annex"]):
            n_row_bad += 1
            bad("GOLD", tid, "listed_in_annex", True, g["listed_in_annex"])
        applies = {}
        for k, ko in HAZ:
            thr = o[k]
            if not close(thr, num(g[f"{k}_threshold_percent"])):
                n_row_bad += 1
                bad("GOLD", tid, f"{k}_threshold_percent", thr, g[f"{k}_threshold_percent"])
            applies[k] = thr is not None and thr != "BAD" and pct >= thr  # 기준 '이상'이면 해당
            if to_bool(g[f"{k}_applies"]) != applies[k]:
                n_row_bad += 1
                bad("GOLD", tid, f"{k}_applies", applies[k], g[f"{k}_applies"])
        any_h = any(applies.values())
        if to_bool(g["any_hazard_applies"]) != any_h:
            n_row_bad += 1
            bad("GOLD", tid, "any_hazard_applies", any_h, g["any_hazard_applies"])
        below += (not any_h)
        above += any_h
        for k, ko in HAZ:
            types_count[k] += applies[k]
        # expected_output_json 일관성
        try:
            js = json.loads(text(g["expected_output_json"]))
        except json.JSONDecodeError:
            n_row_bad += 1
            bad("GOLD", tid, "expected_output_json", "유효한 JSON", "파싱 실패")
            continue
        for f, e in (("test_id", tid), ("listed_in_annex", True), ("regulatory_entry_id", o["eff_id"]),
                     ("official_name_ko", o["ko"]), ("acute_applies", applies["acute"]),
                     ("chronic_applies", applies["chronic"]), ("ecological_applies", applies["ecological"]),
                     ("any_hazard_applies", any_h)):
            if js.get(f) != e:
                n_row_bad += 1
                bad("GOLD.expected_output_json", tid, f, e, js.get(f))
    check("행별 정답(고유번호·명칭·기준·해당 여부)이 공식 별표 재계산과 일치", n_row_bad == 0, f"불일치 {n_row_bad}건")

    # 6. 농도 패턴 (최저×0.5, 최저×0.99, 최저, 최고 / 기준이 하나면 ×1.10)
    n_pat = 0
    for cas, rows in per_cas.items():
        o = official.get(int(float(text(rows[0]["annex_excel_row"]))))
        if not o:
            continue
        thr = [o[k] for k, _ in HAZ if o[k] not in (None, "BAD")]
        if not thr:
            continue
        lo, hi = min(thr), max(thr)
        want = sorted([0.5 * lo, 0.99 * lo, lo, hi if len(set(thr)) > 1 else 1.1 * lo])
        got = sorted(float(r["virtual_mass_percent"]) for r in rows)
        if not all(close(a, b) for a, b in zip(want, got)):
            n_pat += 1
            bad("농도패턴", cas, "virtual_mass_percent", want, got)
    check("CAS별 가상 함량 4개가 설계 패턴과 일치", n_pat == 0, f"불일치 {n_pat} CAS")

    # 7. 질의 파일 ↔ 정답 파일, 정답 유출
    n_x = 0
    for tid, c in cases_by_id.items():
        g = gold_by_id.get(tid)
        if not g:
            continue
        if text(c["cas_no"]) != text(g["cas_no"]) or not close(num(c["virtual_mass_percent"]), num(g["virtual_mass_percent"])):
            n_x += 1
            bad("TEST↔GOLD", tid, "cas/percent", f"{g['cas_no']} {g['virtual_mass_percent']}", f"{c['cas_no']} {c['virtual_mass_percent']}")
        p = text(c["model_input_prompt_ko"])
        pct_txt = text(c["virtual_mass_percent"])
        if tid not in p or text(c["cas_no"]) not in p or f"{pct_txt}%" not in p:
            n_x += 1
            bad("PROMPT", tid, "test_id/CAS/함량 포함", "모두 포함", "누락")
    check("질의 파일과 정답 파일의 CAS·함량 일치, 프롬프트에 ID·CAS·함량 포함", n_x == 0, f"불일치 {n_x}건")
    cols = list(cases[0].keys())
    check("TEST_CASES에 정답 열 없음", cols == ["test_id", "chemical_case_id", "cas_no", "virtual_mass_percent", "model_input_prompt_ko"], str(cols))
    leaks = 0
    for tid, c in cases_by_id.items():
        g, p = gold_by_id.get(tid), text(c["model_input_prompt_ko"])
        if g and (text(g["regulatory_entry_id"]) in p or text(g["official_name_ko"]) in p):
            leaks += 1
            bad("LEAK", tid, "prompt", "정답 미포함", "고유번호 또는 물질명 포함")
    check("프롬프트에 정답(고유번호·물질명) 유출 없음", leaks == 0, f"{leaks}건")

    # 8. QC 요약 수치
    def qcnum(key):
        try:
            return int(qc.get(key, "").replace(",", ""))
        except ValueError:
            return None
    for label, key, val in (("함량기준 미만(유해성 0개)", "함량기준 미만(유해성 0개)", below),
                            ("함량기준 이상(유해성 1개 이상)", "함량기준 이상(유해성 1개 이상)", above),
                            ("인체급성 해당 질의", "인체급성 해당 질의", types_count["acute"]),
                            ("인체만성 해당 질의", "인체만성 해당 질의", types_count["chronic"]),
                            ("생태유해성 해당 질의", "생태유해성 해당 질의", types_count["ecological"])):
        check(f"QC 요약 '{label}' = 재계산", qcnum(key) == val, f"기록 {qc.get(key)} / 재계산 {val}")
    check("QC 요약 개별 지정행 275·세부행 25 = 재계산",
          qcnum("명시적 개별 지정행 선정 수") == kinds["DIRECT_NAMED_SUBSTANCE"] // 4 and
          qcnum("고유번호의 세부행 선정 수") == kinds["SPECIFIC_COMPONENT"] // 4,
          f"재계산 {kinds['DIRECT_NAMED_SUBSTANCE'] // 4}/{kinds['SPECIFIC_COMPONENT'] // 4}")

    # 9. 별표 CAS ↔ 영문명 PubChem 교차확인 (별표 자체의 오탈자 후보; FAIL이 아니라 사람이 볼 목록)
    pc_names = {}
    for cas, rows in per_cas.items():
        pc_names[cas] = text(rows[0]["official_name_en"])
    print("\nPubChem 교차확인 중(300개 CAS, 약 2~4분; 캐시 사용)…", flush=True)
    counts, pc_rows, skipped = pubchem_crosscheck(pc_names, Path(args.cache))
    pubchem_note = ""
    if skipped:
        pubchem_note = f"PubChem 교차확인 건너뜀: 인터넷 접속 불가 ({skipped})"
    else:
        with open(args.pubchem_out, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["cas", "official_en", "status", "pubchem_title", "similarity", "note"])
            w.writeheader()
            w.writerows(sorted(pc_rows, key=lambda r: ({"MISMATCH": 0, "NOT_RESOLVED": 1, "ERROR": 2, "SIMILAR": 3, "MATCH": 4}[r["status"]], r["cas"])))
        pubchem_note = (f"PubChem 교차확인(300 CAS): 일치 {counts['MATCH']} / 유사 {counts['SIMILAR']} / "
                        f"불일치 {counts['MISMATCH']} / 조회불가 {counts['NOT_RESOLVED']} / 오류 {counts['ERROR']} "
                        f"-> 불일치·조회불가·오류는 {args.pubchem_out} 맨 위에서 사람이 확인")

    # 출력
    width = max(len(n) for n, _, _ in results)
    for name, ok, detail in results:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  -> {detail}" if detail and not ok else ""))
    n_fail = sum(1 for _, ok, _ in results if not ok)
    print(f"\n{len(results) - n_fail}/{len(results)} 통과, 불일치 상세 {len(mismatches)}건")
    print(pubchem_note)
    if args.out and mismatches:
        with open(args.out, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["check", "key", "field", "expected", "actual"])
            w.writeheader()
            w.writerows(mismatches)
        print(f"불일치 목록 저장: {args.out}")
    elif mismatches:
        for m in mismatches[:15]:
            print("  ", m)
        print("  (전체는 --out mismatches.csv 로 저장)")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
