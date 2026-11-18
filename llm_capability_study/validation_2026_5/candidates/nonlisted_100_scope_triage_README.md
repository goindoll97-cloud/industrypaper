# 2026-5호 미등재 후보 100종 — 1차 구조 및 범위 검토

검토 기준판: 사용자 제공 `2026-5_(별표) 인체등유해성물질 목록(전체)(2).xlsx`.
검토일: 2026-11-18.

## 검증 절차
1. 공식 별표 1,451행을 원문 그대로 읽고 CAS 정규표현식으로 A~J열 명시적 CAS를 추출했습니다.
2. 100종의 후보 CAS 및 PubChem 제공 모든 CAS 동의어에 대한 공식 별표 명시적 CAS와의 교집합을 확인했습니다.
3. 후보의 제공 SMILES를 RDKit으로 파싱하여 금속·준금속 원자, 분리된 분자 성분, 염류 키워드 등을 점검했습니다.
4. 기존 수집기의 위험 분류도 참고해 **추가 법적 범위 검토 우선순위**를 분류했습니다.

| 항목 | 결과 |
|---|---:|
| 후보 | 100종 |
| 별표에 명시된 CAS와 충돌 | 0종 |
| 구조·염류 등 **우선 법적 검토** | 11종 |
| 나머지 일반 범위 검토 | 89종 |
| **법적 범위 검증 완료** | **0종** |
| **Gold `NOT_FOUND` 확정** | **0종** |

## 우선 확인할 후보
`NF-CAND-0009`, `NF-CAND-0020`, `NF-CAND-0037`, `NF-CAND-0046`, `NF-CAND-0052`, `NF-CAND-0057`, `NF-CAND-0066`, `NF-CAND-0070`, `NF-CAND-0080`, `NF-CAND-0081`, `NF-CAND-0095`.

특히 **NF-CAND-0020 (CAS 60522-34-1)**은 SMILES에 Sn 원자가 있는 유기주석 화합물입니다.
고시의 `97-1-138` 및 `97-1-139` 등 트리아릴·트리알킬주석 관련 포괄 규정과의 관계를 검토해야 하며, 구조에 Sn이 있다는 사실만으로 해당한다고 결론 내려서도 안 됩니다.

`NF-CAND-0006` 페닐 벤조에이트(CAS 93-99-2, PubChem CID 7169)는 공식 PubChem 및 시판업체 자료로 물질 정체를 우선 대조했습니다. **화학물질 신원 확인과 법적 비대상 판정은 독립적인 단계**입니다.

- 공식 고시: https://www.law.go.kr/admRulLsInfoP.do?admRulSeq=2100000276378
- PubChem 93-99-2: https://pubchem.ncbi.nlm.nih.gov/compound/7169
- 공급업체 93-99-2: https://www.fishersci.com/shop/products/phenyl-benzoate-99-thermo-scientific/AC162060050
- PubChem 60522-34-1: https://pubchem.ncbi.nlm.nih.gov/compound/326737

## 중요: 본 점검은 2차 법적 검증이 아님

`NO_SIMPLE_STRUCTURAL_FLAG` 또는 `GENERAL`도 **고시상 비대상이란 뜻이 아닙니다.**

`gold_status`는 **100종 모두 공란**으로 두었고, `legal_scope_checked`는 모두 NO입니다.
사용자가 원한 최종 Gold로 확정하려면 후보별로 해당 CAS의 물질 정체, 전체 지정항목의 적용범위,
포괄 화합물군·염류·이성질체·예외조항을 고시 원문과 연결하여 근거를 남겨야 합니다.

최종 상태는 `VERIFIED_NOT_LISTED`, `LISTED_VIA_GROUP`, `UNRESOLVED_EXCLUDE` 등의 내부 심사값으로 관리할 수 있으며,
**반드시 법적 검증이 완료된 `VERIFIED_NOT_LISTED`만 검증셋의 `listed_in_annex=false`로 채택합니다.**

현재 GitHub의 1,200건 XLSX 두 파일은 변경하지 않았습니다.
