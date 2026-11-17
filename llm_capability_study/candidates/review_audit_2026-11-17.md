# 규제 Gold 검토 감사기록 (2026-11-17)

## 범위와 원칙

- 비교 범위는 저장소의 동결된 **29개 target_id**로 한정함. `NOT_FOUND`는 국내 법 전체에서 규제가 없다는 뜻이 아님.
- 자료: `llm_capability_study/candidates/review_sheet.csv`(244행), `data/regulatory_catalog.csv`(29행).
- 지정 검토: `source_batch=mixture` 18행 전체 및 일반 행 20행 위험 우선 표본(일반 NOT_FOUND 12, PS 4, CG 4).
- CAS 직접 일치(카탈로그 reference/official_member/mixture_component/official_mixture), 화학명과 공개 SMILES에 따른 범위 판단, 공식 제한물질 고시의 별표를 구분하여 점검함. CAS 비일치는 규제범위 비해당의 충분조건이 아님.
- 카탈로그의 29개 항목 전체를 현행 법령상 모든 규제 화학물질이라고 해석하지 않음. 본 문서는 연구용 Gold의 위험표본 검토 기록이지 법적 자문이 아님.

## 공식 근거

- **「제한물질·금지물질의 지정」**, 기후에너지환경부고시 **제2025-28호**, 2025-11-19 일부개정, **2026-01-01 시행**, **제3조제2항, 별표 3**(총칭으로 지정된 제한물질의 구체적 목록). [고시 본문](https://www.law.go.kr/LSW/admRulInfoP.do?admRulSeq=2100000268296&chrClsCd=010201) / [별표 3](https://www.law.go.kr/LSW/flDownload.do?flSeq=158305589).
- 해당 별표의 구체적 목록: **06-5-1 말라카이트 그린, 06-5-4 트리알킬주석/트리부틸주석, 06-5-6 노닐페놀류, 06-5-8 납, 06-5-10 6가 크롬**.
- CAS 및 분자구조 확인 보조자료: [PubChem, Piperazine hydrochloride CAS 6094-40-2](https://pubchem.ncbi.nlm.nih.gov/compound/82044), [PubChem, Isocitric acid CAS 320-77-4](https://pubchem.ncbi.nlm.nih.gov/compound/1198), [PubChem, Lead chromate CAS 11119-70-3](https://pubchem.ncbi.nlm.nih.gov/compound/24460).
- PS:: 계열의 각 개별 공식 고시 원문·고시판·유효 범위는 이번 대조에서 별도 원문을 모두 확보한 것이 아니므로, **검토표의 '고시 원문 대조 필요'를 유지함**. 고시 확인 완료라고 과장하지 않음.

## 1순위: 혼합물 18건

- NOT_FOUND 혼합물: **12/12**건의 성분 CAS에 대해 카탈로그 명시 CAS 직접 일치 없음. 개별 물질에 대한 포괄 문구의 잠재적 적용 여부는 화학적 정체와 함께 검토함.
- 연구용 합성 2성분: **6/6**건의 두 성분 모두 각 Gold target ID의 명시 CAS에 1:1 대응. 실제 판매 혼합물이 아니므로 실재 혼합물 인식 성능과 구분하여 통계적으로 보고할 것.

| Case | 성분 CAS | Gold | 검토 결과 | 판정 근거 |
|---|---|---|---|---|
| CAND-0227 | 26172-55-4|2682-20-4 | NOT_FOUND | 유지 | 성분 CAS의 29개 카탈로그 명시 CAS 일치 없음 |
| CAND-0228 | 584-84-9|91-08-7 | NOT_FOUND | 유지 | 성분 CAS의 29개 카탈로그 명시 CAS 일치 없음 |
| CAND-0229 | 121-14-2|606-20-2 | NOT_FOUND | 유지 | 성분 CAS의 29개 카탈로그 명시 CAS 일치 없음 |
| CAND-0230 | 10061-01-5|10061-02-6 | NOT_FOUND | 유지 | 성분 CAS의 29개 카탈로그 명시 CAS 일치 없음 |
| CAND-0231 | 33213-65-9|959-98-8 | NOT_FOUND | 유지 | 성분 CAS의 29개 카탈로그 명시 CAS 일치 없음 |
| CAND-0232 | 101-68-8|2536-05-2|5873-54-1 | NOT_FOUND | 유지 | 성분 CAS의 29개 카탈로그 명시 CAS 일치 없음 |
| CAND-0233 | 106-42-3|108-38-3|95-47-6 | NOT_FOUND | 유지 | 성분 CAS의 29개 카탈로그 명시 CAS 일치 없음 |
| CAND-0234 | 106-44-5|108-39-4|95-48-7 | NOT_FOUND | 유지 | 성분 CAS의 29개 카탈로그 명시 CAS 일치 없음 |
| CAND-0235 | 134237-50-6|134237-51-7|134237-52-8 | NOT_FOUND | 유지 | 성분 CAS의 29개 카탈로그 명시 CAS 일치 없음 |
| CAND-0236 | 319-84-6|319-85-7|319-86-8|58-89-9 | NOT_FOUND | 유지 | 성분 CAS의 29개 카탈로그 명시 CAS 일치 없음 |
| CAND-0237 | 108-67-8|526-73-8|95-63-6 | NOT_FOUND | 유지 | 성분 CAS의 29개 카탈로그 명시 CAS 일치 없음 |
| CAND-0238 | 106-46-7|541-73-1|95-50-1 | NOT_FOUND | 유지 | 성분 CAS의 29개 카탈로그 명시 CAS 일치 없음 |
| CAND-0239 | 10309-95-2|65-85-0 | CG::MG_SALTS|PS::65-85-0 | 유지 | 10309-95-2=CG::MG_SALTS / 65-85-0=PS::65-85-0 |
| CAND-0240 | 10294-40-3|11066-49-2 | CG::CRVI_COMPOUNDS|CG::NONYLPHENOL_NPE | 유지 | 10294-40-3=CG::CRVI_COMPOUNDS / 11066-49-2=CG::NONYLPHENOL_NPE |
| CAND-0241 | 10099-74-8|10294-40-3 | CG::CRVI_COMPOUNDS|CG::LEAD_COMPOUNDS | 유지 | 10099-74-8=CG::LEAD_COMPOUNDS / 10294-40-3=CG::CRVI_COMPOUNDS |
| CAND-0242 | 1067-97-6|11066-49-2 | CG::NONYLPHENOL_NPE|CG::TBT_TRIALKYLTIN | 유지 | 1067-97-6=CG::TBT_TRIALKYLTIN / 11066-49-2=CG::NONYLPHENOL_NPE |
| CAND-0243 | 10099-74-8|1067-97-6 | CG::LEAD_COMPOUNDS|CG::TBT_TRIALKYLTIN | 유지 | 10099-74-8=CG::LEAD_COMPOUNDS / 1067-97-6=CG::TBT_TRIALKYLTIN |
| CAND-0244 | 144-62-7|69-72-7 | PS::144-62-7|PS::69-72-7 | 유지 | 144-62-7=PS::144-62-7 / 69-72-7=PS::69-72-7 |

## 2순위: 일반 위험표본 20건

- NOT_FOUND **12/12 유지**, PS:: **4/4 유지**, CG:: **3/4 유지 및 1건 EXCLUDED**.
- 혼합물 외 표본에서 **CAND-0125**만 배제함. 명시적 CAS 등재 부재와 '수산화 트리알킬주석의 염류' 포괄범위 해석에 대한 불확실성이 결합되어 금표준으로 확정하지 않음.

| Case | CAS | 물질명 | 기존 Gold | 수정 상태 | 핵심 근거 |
|---|---|---|---|---|---|
| CAND-0068 | 557-05-1 | /Z/i/n/c/ /S/t/e/a/r/a/t/e/ | NOT_FOUND | ADJUDICATED | Zn 스테아르산염으로 Pb 화합물이 아님. 금속 양이온까지 확인 |
| CAND-0073 | 603-48-5 | /L/e/u/c/o/c/r/y/s/t/a/l/ /V/i/o/l/e/t/ | NOT_FOUND | ADJUDICATED | 류코크리스탈 바이올렛은 말라카이트 그린 염과 다른 분자 |
| CAND-0081 | 683-18-1 | /D/i/b/u/t/y/l/t/i/n/ /d/i/c/h/l/o/r/i/d/e/ | NOT_FOUND | ADJUDICATED | 디부틸주석: 트리알킬주석·트리부틸주석이 아님 |
| CAND-0089 | 110-89-4 | /P/i/p/e/r/i/d/i/n/e/ | NOT_FOUND | ADJUDICATED | 피페리딘(한 개 N)과 피페라진(두 개 N)은 다름 |
| CAND-0103 | 10101-53-8 | /C/h/r/o/m/i/c/ /S/u/l/f/a/t/e/ | NOT_FOUND | ADJUDICATED | Cr(III) 황산염으로 Cr(VI) 항목 제외 |
| CAND-0118 | 2923-18-4 | /S/o/d/i/u/m/ /T/r/i/f/l/u/o/r/o/a/c/e/t/a/t/e/ | NOT_FOUND | ADJUDICATED | 트리플루오로아세트산염은 아세트산염이 아닌 별개의 카르복실산염 |
| CAND-0121 | 13548-38-4 | /C/h/r/o/m/i/c/ /n/i/t/r/a/t/e/ | NOT_FOUND | ADJUDICATED | Cr(III) 질산염으로 Cr(VI) 항목 제외 |
| CAND-0124 | 1987-50-4 | /4/-/n/-/H/e/p/t/y/l/p/h/e/n/o/l/ | NOT_FOUND | ADJUDICATED | 헵틸페놀(7C 치환기), 노닐페놀(9C 치환기)과 다름 |
| CAND-0128 | 79-11-8 | /C/h/l/o/r/o/a/c/e/t/i/c/ /A/c/i/d/ | NOT_FOUND | ADJUDICATED | 클로로아세트산은 아세트산 자체나 그 염이 아님 |
| CAND-0129 | 99-94-5 | /P/-/T/o/l/u/i/c/ /A/c/i/d/ | NOT_FOUND | ADJUDICATED | p-톨루산은 벤조산의 메틸 치환 유도체이며 벤조산염 아님 |
| CAND-0136 | 320-77-4 | /I/s/o/c/i/t/r/i/c/ /A/c/i/d/ | NOT_FOUND | ADJUDICATED | 이소시트르산은 시트르산의 위치이성질체이며 입체이성질체 아님 |
| CAND-0211 | 818-08-6 | /D/i/b/u/t/y/l/t/i/n/ /o/x/i/d/e/ | NOT_FOUND | ADJUDICATED | 디부틸주석 산화물로 트리알킬주석 산화물 아님. 별도 유해성물질 지정 여부와 29개 목록 판정은 구분 |
| CAND-0061 | 6094-40-2 | /P/i/p/e/r/a/z/i/n/e/,/ /h/y/d/r/o/c/h/l/o/r/i/d/e/ /(/1/:/?/)/ | PS::110-85-0 | ADJUDICATED | 피페라진 염산염(6094-40-2): PubChem 구조 확인, PS::110-85-0의 salts 범위. 상세 원문 확인 문구 유지 |
| CAND-0093 | 631-61-8 | /A/m/m/o/n/i/u/m/ /A/c/e/t/a/t/e/ | PS::64-19-7 | ADJUDICATED | 아세트산암모늄은 acetic acid의 염. 상세 원문 확인 문구 유지 |
| CAND-0111 | 2016-36-6 | /C/h/o/l/i/n/e/ /S/a/l/i/c/y/l/a/t/e/ | PS::69-72-7 | ADJUDICATED | 살리실산콜린은 salicylic acid의 염. 상세 원문 확인 문구 유지 |
| CAND-0120 | 3522-50-7 | /F/e/r/r/i/c/ /c/i/t/r/a/t/e/ | PS::77-92-9 | ADJUDICATED | 철(III) 시트르산염은 citric acid의 염. 상세 원문 확인 문구 유지 |
| CAND-0007 | 10309-95-2 | /M/a/l/a/c/h/i/t/e/ /g/r/e/e/n/ /c/a/t/i/o/n/ | CG::MG_SALTS | ADJUDICATED | 고시 별표3 06-5-1 세부목록에 CAS 10309-95-2 명시 |
| CAND-0063 | 13477-01-5 | /B/a/r/i/u/m/ /d/i/c/h/r/o/m/a/t/e/ | CG::CRVI_COMPOUNDS | ADJUDICATED | Ba dichromate는 Cr(VI) 포함; 06-5-10의 기타 Cr(VI) 범위 |
| CAND-0125 | 1066-45-1 | /T/r/i/m/e/t/h/y/l/t/i/n/ /c/h/l/o/r/i/d/e/ | CG::TBT_TRIALKYLTIN | EXCLUDED | Trimethyltin chloride는 직접 등재 CAS가 아니며 06-5-4 기타 수산화트리알킬주석의 염류에 포함되는지는 단정하기 어려움; EXCLUDED |
| CAND-0147 | 11119-70-3 | /L/e/a/d/ /C/h/r/o/m/a/t/e/ | CG::CRVI_COMPOUNDS|CG::LEAD_COMPOUNDS | ADJUDICATED | PbCrO4: 고시 06-5-10 직접 CAS와 06-5-8의 기타 납 화합물에 함께 해당 |

## 전체 카탈로그 직접 CAS 교차검증

- ADJUDICATED 전체 행 중에서, **입력 CAS가 카탈로그의 특정 target에 직접 일치하는데 Gold에서 그 target ID를 누락한 사례: 0건**.
- 이 자동 일치점검은 CAS 명시 목록의 정합성을 보는 것으로, 포괄적 염류·물질군·혼합물의 최종 법적 해석을 대체하지 않음.

## 실제 수정 내역

- **CAND-0125** `human_review_status`: `ADJUDICATED` → `EXCLUDED`; Gold target 값은 이력보존을 위해 변경하지 않음.
- 공식 별표의 CAS·범위 또는 합성 조합을 대조한 **11행**의 `human_legal_basis`에서 '고시 원문 대조 필요'를 공식 고시명·일자·조항 및 개별 번호로 대체함.
- 해당 11행: `CAND-0002`, `CAND-0004`, `CAND-0007`, `CAND-0009`, `CAND-0012`, `CAND-0063`, `CAND-0147`, `CAND-0240`, `CAND-0241`, `CAND-0242`, `CAND-0243`.
- 수정 후 전체 상태: **ADJUDICATED 193 / EXCLUDED 51**, 총 244건. 이전 194/50에서 1건만 상태 변경.
- 원본 `main` 브랜치와 기존 112건 동결 benchmark 파일은 수정하지 않음.

## 연구 설계상 별도 유의사항

- 저장소 프로토콜은 '실재가 확인되지 않은 혼합물 임의 조합 금지'를 안내하지만, `CAND-0239~0244`는 의도적으로 구성한 합성 2성분 사례임. 논문에서는 **constructed two-component queries**로 별도 표시하고 실재 혼합물의 사례 수나 모집단 분포에 포함하지 말 것.
- `CAND-0211` 산화디부틸주석(CAS 818-08-6)은 다른 유해화학물질 지정표에서 독립적으로 등재될 수 있지만, **이번 29개 동결 목록의 TBT/TRIALKYLTIN과는 다른 화학물질**이므로 NOT_FOUND 유지. 전체 법령 비규제라는 주장을 피할 것.
- 본 기록은 지명된 38건의 우선 검토 및 전체 244건에 대한 CAS **직접일치 자동검증**이다. 전체 244건의 원문 법규 검증 완료가 아니다.
