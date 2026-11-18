"""Validate public input data; additionally validate Gold if installed locally.
The public GitHub repository intentionally does not include the private Gold key.
"""
import hashlib, json, re
from collections import Counter, defaultdict
from pathlib import Path
R = Path(__file__).resolve().parent

def read(p):
    return [json.loads(s) for s in p.read_text(encoding="utf-8").splitlines() if s.strip()]
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    p = R / "data/prompts_72.jsonl"
    a = R / "data/pilot_6_ids.json"
    g = R / "private/gold_72.jsonl"
    m = json.loads((R / "data/manifest.json").read_text(encoding="utf-8"))
    assert sha(p) == m["prompts_sha256"] and sha(a) == m["pilot_ids_sha256"]
    prompts = read(p)
    assert len(prompts) == 72
    assert len({r["test_id"] for r in prompts}) == 72
    by_cas = defaultdict(list)
    for c in prompts:
        by_cas[c["cas_no"]].append(c)
        assert not any(k in c for k in ("stratum", "difficulty", "expected_output_json", "acute_applies"))
        assert c["prompt_sha256"] == hashlib.sha256(json.dumps(
            [c["system_prompt"], c["user_prompt"]], ensure_ascii=False).encode("utf-8")).hexdigest()
        assert len(re.findall(r"^\d{2}\. 고유번호=", c["user_prompt"], re.M)) == 12
    assert len(by_cas) == 36 and all(len(rows) == 2 for rows in by_cas.values())
    pilots = json.loads(a.read_text(encoding="utf-8"))
    assert len(pilots) == 6 and len(set(pilots)) == 6
    assert set(pilots).issubset({r["test_id"] for r in prompts})
    print("PASS: 36 CAS, 72 cases, 12 evidence rows per question, public SHA256 hashes")
    if not g.exists():
        print("Gold 미설치: 공개 입력 검증 완료. 채점하려면 로컬 private/gold_72.jsonl 파일을 추가하세요.")
        return
    assert sha(g) == m["gold_sha256"], "Private Gold SHA256 mismatch"
    gold = read(g)
    assert len(gold) == 72
    assert {r["test_id"] for r in gold} == {r["test_id"] for r in prompts}
    strata = defaultdict(set)
    for x in gold:
        strata[(x["stratum"], x["difficulty"])].add(x["chemical_case_id"])
    assert len(strata) == 12 and all(len(c) == 3 for c in strata.values())
    assert sum(x["listed_in_annex"] for x in gold) == 60
    assert Counter(x["scenario"] for x in gold) == {
        "AT_FIRST_THRESHOLD": 30, "BELOW_BOUNDARY": 30,
        "NOT_LISTED_5": 6, "NOT_LISTED_1": 6}
    print("PASS: Private Gold SHA256 and 12 strata x 3 CAS sampling verified")

if __name__ == "__main__":
    main()
