"""Check provisional CAS/formula pairs against PubChem PUG REST without approving Gold.

This never changes the candidate CSV or auto-sets identity_verified=YES.
Independent review is still necessary before constructing the frozen B90 test.
"""
from __future__ import annotations
import csv
from collections import Counter
import json
import re
from pathlib import Path
import time
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

BASE = Path(__file__).resolve().parents[1]
CANDIDATES = BASE / "private" / "new_cases_review.csv"
OUT = BASE / "private" / "pubchem_cas_formula_crosscheck.csv"
FIELDS = ("cas", "candidate_formula", "pubchem_formula", "pubchem_cid",
          "pubchem_url", "formula_element_match", "status", "error")


def composition(formula: str):
    """Compare elemental composition, ignoring ordering and fragment dots.

    A formula with charge or isotopic labels is left for manual review instead
    of silently treating it as equivalent.
    """
    if not isinstance(formula, str) or not formula:
        return None
    s = formula.replace("·", ".").replace(" ", "")
    if any(c in s for c in "()+-[]^"):
        return None
    counts = Counter()
    for piece in s.split("."):
        if not piece:
            return None
        pos = 0
        for m in re.finditer(r"([A-Z][a-z]?)([0-9]*)", piece):
            if m.start() != pos:
                return None
            counts[m.group(1)] += int(m.group(2) or 1)
            pos = m.end()
        if pos != len(piece):
            return None
    return dict(counts)


def lookup(cas, tries=3):
    url = ("https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/"
           + quote(cas, safe="") + "/property/MolecularFormula/JSON")
    last_error = ""
    for attempt in range(tries):
        try:
            rq = Request(url, headers={"User-Agent": "B90-chemical-identity-check/1.0"})
            with urlopen(rq, timeout=30) as res:
                data = json.loads(res.read().decode("utf-8"))
            properties = data.get("PropertyTable", {}).get("Properties", [])
            return properties, url, ""
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            last_error = str(exc)
            if attempt < tries - 1:
                time.sleep((attempt + 1) * 2)
    return [], url, last_error


def main():
    if not CANDIDATES.exists():
        raise SystemExit("먼저 python prepare_b90.py --import-proposals 실행")
    with CANDIDATES.open(encoding="utf-8-sig", newline="") as fp:
        rows = list(csv.DictReader(fp))
    expected = {}
    for row in rows:
        cas, formula = row["cas"].strip(), row["formula"].strip()
        if cas in expected and expected[cas] != formula:
            raise SystemExit("같은 CAS에서 분자식이 서로 다름: " + cas)
        expected[cas] = formula
    outcome = []
    for idx, (cas, formula) in enumerate(sorted(expected.items()), 1):
        props, url, err = lookup(cas)
        chosen = next((p for p in props
                       if composition(p.get("MolecularFormula", "")) == composition(formula)
                       and composition(formula) is not None), None)
        p = chosen or (props[0] if props else {})
        matches = chosen is not None
        outcome.append({
            "cas": cas, "candidate_formula": formula,
            "pubchem_formula": p.get("MolecularFormula", ""),
            "pubchem_cid": p.get("CID", ""),
            "pubchem_url": url,
            "formula_element_match": "YES" if matches else "NO",
            "status": "MATCH_AUTOMATED_ONLY" if matches else "CHECK_MANUALLY",
            "error": err,
        })
        print(f"{idx}/{len(expected)} {cas}: {'MATCH' if matches else 'CHECK'}",
              flush=True)
        time.sleep(0.4)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(outcome)
    print("검사표 저장:", OUT)
    print("MATCH:", sum(x["formula_element_match"] == "YES" for x in outcome),
          "/", len(outcome))
    print("**주의: 이 검사는 CAS 질의에 대한 분자식 교차검사일 뿐이며,"
          "전문가 독립 검증이나 법령 적용 여부 검증을 대체하지 않습니다.**")


if __name__ == "__main__":
    main()
