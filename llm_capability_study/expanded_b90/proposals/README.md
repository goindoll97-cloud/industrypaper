# B 조건 90문항 — 실제 물질을 채운 후보 초안

**작성 완료: 기존 B 조건 30문항(내용 그대로 유지) + 신규 60문항(실제 물질·CAS·영문명·분자식·가상 혼합물 함량 후보).** 현재 파일은 **화학물질 정체와 법적 정답의 독립 검증 전 후보**입니다. 이 데이터로 현재 모델의 정확도를 측정했다고 주장하지 마세요.

## 90문항 후보 파일

| 파일 | 행 | 의미 |
|---|---:|---|
| [PROPOSED_90_B_cases.jsonl](PROPOSED_90_B_cases.jsonl) | 90 | 기존 B 질문 30건 원문 보존, 신규 B 질문 60건; CAS·명칭·분자식·혼합물의 질량비 |
| [PROPOSED_new_60_cases_summary.csv](PROPOSED_new_60_cases_summary.csv) | 60 | 한 사례당 1행, 유형·난이도·구성 성분·사전 선정 목적 |
| [PROPOSED_new_60_component_review.csv](PROPOSED_new_60_component_review.csv) | 90 | 신규 60개 사례의 모든 성분 입력을 채운 연구용 검토표; PubChem CAS 페이지와 **공식 고시 근거 후보 행** 포함 |
| [check_pubchem.py](check_pubchem.py) | 코드 | 신규 성분의 CAS 질의에 대한 PubChem 분자식 교차점검 결과를 별도 CSV로 저장 |

**후보 사례 선정:** 모체·염류 20건(S-11~S-30), 화합물군 20건(C-11~C-30), 가상 혼합물 20건(M-11~M-30). 유형별 10 EASY + 10 HARD를 추가하여 기존 B 30건과 합치면 **각 유형 30건, EASY/HARD 각 15건, 총 90건**입니다.

## 기존 빈 입력표 대신 후보 정보를 가져오기

이미 `python prepare_b90.py --init-candidates`를 실행한 경우에는 **다음 명령 하나**로 새 60개 사례의 정보를 기존 빈 CSV에 넣습니다.

~~~powershell
cd F:\framework_chemical_regul_paper
git pull origin main
cd .\llm_capability_study\expanded_b90
python .\prepare_b90.py --import-proposals
~~~

생성·갱신 위치: `private/new_cases_review.csv`. 이 명령은 **아직 입력 내용이 없는 빈 표에만 작동**하며, 사용자가 편집한 자료는 절대 덮어쓰지 않습니다. 원래 빈 표는 `private/new_cases_review_original_blank.csv`에 별도 보존됩니다.

**중요: 후보 정보 90개 성분행의 `identity_verified`는 모두 `NO`입니다.** 연구에서 분자식과 CAS를 임의로 검증 완료 처리하지 않도록 했습니다. `candidate_annex_row` 역시 확인해야 할 고시의 **근거 후보**이지 확정 Gold가 아닙니다.

## PubChem과 화학물질 정체 교차검사

~~~powershell
python .\proposals\check_pubchem.py
~~~

출력: `private/pubchem_cas_formula_crosscheck.csv`. 각 CAS의 PubChem 분자식과 제안 분자식을 비교합니다. **이 검사는 자동 교차점검일 뿐 사람의 정체 확인이나 법령 전문가 검증을 대체하지 않습니다.** CAS가 중복된 경우 1회만 조회하며, 연결 오류나 분자식 불일치는 `CHECK_MANUALLY`로 표시됩니다.

해당 결과와 고시 원문을 대조하여 `new_cases_review.csv`의 `identity_reviewer`를 실제 확인자 이름으로 채우고 `identity_verified`를 검토를 완료한 행에 한해서 `YES`로 변경합니다. 그다음 아래 명령으로 90문항을 고정 입력으로 만들 수 있습니다.

~~~powershell
python .\prepare_b90.py --build-cases
python .\prepare_b90.py --init-gold
~~~

여기서 **법적 정답 검토는 별도 단계**입니다. 기존 30문항의 Gold도 독립 검토가 끝나지 않았으므로 90문항 전체의 근거행·지정 관계·혼합물 요건을 검토하고 `--freeze`를 수행해야 본실험으로 진행할 수 있습니다.

## 후보 선정의 근거·한계

신규 단일물질에서는 공식 고시 1,451행에 **CAS가 직접 나오는 경우**를 우선 선정했고, 일부에는 **고시에 CAS가 직접 나오지 않지만 포괄 지정 또는 예외 조항의 적용 여부를 검토해야 하는 물질**을 포함했습니다. 가상 혼합물은 이러한 성분들을 다른 직접 지정물질과 조합하여 두 성분(쉬움) 또는 세 성분(어려움)으로 구성했습니다. 혼합물 합계는 모두 100%이며, **물질의 화학적 혼합 가능성이나 실제 제품의 법규 준수 여부를 평가하는 설계는 아닙니다.**

사전 태그(`regulatory_pattern`)는 왜 후보로 선정했는지 설명하는 **연구설계 가설**입니다. `DIRECT`, `CLASS_INCLUDED`, `EXPLICIT_EXCEPTION` 등이 실제 법령 해석의 확정값이라는 의미가 아닙니다. 특히 고시에 CAS가 등장하는 물질도 다른 포괄 조항과의 우선순위를 별도로 검토해야 합니다. CAS와 화학식은 가능한 경우 고시와 PubChem 자료에 근거했지만 **전체 90문항의 정체·수화물·동의어·고시 근거를 일대일로 독립 확인하지는 않았습니다.**

### 연구적 유의점

- 기존 B 30문항은 모델이 이미 평가한 사례입니다. 새 60문항의 선정은 **모델의 과거 오답 여부가 아니라 사전 정의된 규제 상황을 다양하게 포함하기 위한 목적**으로 진행해야 합니다.
- 일부 새 사례는 고시에 직접 지정된 물질이 다수이며, 염류의 포괄 포함 및 명시적 제외 사례가 충분히 대표되는지는 전문가와 함께 다시 점검해야 합니다. 90개라는 수치 자체가 충분한 통계적 대표성을 보증하지는 않습니다.
- 가상 혼합물은 동일 성분이 다른 문항에도 반복될 수 있어 독립 표본 90개가 아닙니다.
- 논문에는 입력 CAS·분자식과 Gold를 완전히 검증한 뒤 결과를 사용해야 합니다.

**원본 공식 고시:** `../retrieval_v4/data/official_annex_2026_5_full.csv`가 아니라, 이 폴더 기준 `../../retrieval_v4/data/official_annex_2026_5_full.csv` (연구자료 파일). [전체 B90 실행 방법](../README.md)
