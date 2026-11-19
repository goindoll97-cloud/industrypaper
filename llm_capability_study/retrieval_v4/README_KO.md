# Retrieval v4 — 3개 평가분류 × 각 10사례 × 난이도 5:5

이 검증셋은 **2026-5호 인체급성·만성·생태유해성물질 지정고시**의 전체 1,451개 별표 행을 검색할 수 있는 조건에서, 작은 Qwen 모델들의 **조항 탐색**과 **화학적·법적 지정범위 판단**을 비교하기 위한 탐색적 벤치마크입니다. 정답이 되는 16개 법령 항목을 선택지로 제공하지 않습니다.

## 핵심 설계

| 평가 분류 | EASY | HARD | 1차 평가 단위 |
|---|---:|---:|---|
| 원물질과 그 염류 (`PARENT_AND_SALTS`) | 5 | 5 | 모체-염류 연결 1물질 |
| 화합물군 (`COMPOUND_CLASS`) | 5 | 5 | 금속화합물·무기/유기·유기금속·이성질체·치환 수·명시적 제외에 속하는 1물질 |
| 혼합물 (`MIXTURE`) | 5 | 5 | CAS와 질량비가 알려진 가상 조성 1상황 |
| **합계** | **15** | **15** | **30사례** |

화합물군의 세부 종류는 **기록용 하위 태그**일 뿐, 주 분석에서는 하나의 분류입니다. 실제 화학물질 분류와 법령 적용관계(`DIRECT_SPECIFIC`, `GROUP_INCLUDED`, `EXPLICIT_EXCEPTION`)는 **서로 다른 축**으로 별도 기록합니다. 

### 난이도는 실험 전에 정의

- **EASY:** 1개 모체·대상군 또는 직접 지정항목의 대응이 명확하며, 예외·상하위 우선순위 충돌이 없고 구조적 포함관계가 짧은 명칭으로 드러나는 물질. 혼합물은 2개의 명시 CAS 직접 지정 성분만으로 구성.
- **HARD:** 법령·화학 명칭이 달라 모체/집합명 추론이 필요하거나, 명시적 제외·특정 하위항목·이성질체·치환 수 조건을 확인해야 하는 물질. 혼합물은 3성분 중 포괄 지정 또는 명시 제외가 하나 이상 들어가 성분별 복수 조항을 비교해야 하는 상황.
- HARD가 **실제로 더 낮은 정확도를 보이는지는 후속 통계로 검증**할 가설입니다. 난이도 배정에 모델 실행 결과를 사용하지 않았습니다.

### 시험 입력 (A/B 대응 설계)

- **A:** CAS, 영문 물질명. 혼합물은 성분별 CAS·영문명·질량백분율을 제공합니다.
- **B:** A에 분자식(출처가 있는 단일 성분만)을 추가합니다. 대부분의 사례에서 단일 SMILES를 검증할 수 없었으므로 *SMILES만의 효과를 검증했다고 주장하지 않습니다*.
- 고분자, 불특정 반응생성물, UVCB는 검증 물질에서 제외했습니다. **혼합물은 독립 CAS를 가진 2~3개 단일 성분의 가상 제품 조성**이며 특정 제품, 실험실 배합 또는 화학적 호환성을 의미하지 않습니다.

## 혼합물의 법적 질문 범위 — 중요

- 고시 **제3조**는 “별표의 인체등유해성물질로만 구성된 혼합물도 인체등유해성물질로 본다”고 규정합니다. <https://www.law.go.kr/admRulLsInfoP.do?admRulSeq=2100000285142&chrClsCd=>
- 혼합물 10건은 5개 EASY(2성분 모두 직접 지정), 3개 HARD(3성분 모두 지정, 1개는 포괄 지정), 2개 HARD(3성분 중 1개는 특정 포괄항목에서 명시적 제외)로 설계했습니다. 후자의 `all_components_designated=false`는 **제3조의 '전부 지정물질 혼합물' 조건에 해당하지 않는다는 잠정 판단**만 뜻합니다. 다른 고시·함량기준에 따라 별도 규제대상이 되는지 판단하지 않았습니다.
- 성분별 질량백분율은 입력 맥락의 일부입니다. **본 버전에서는 함량 임계값 적용이나 제품 수준의 종합적인 규제·안전성·적법성을 평가하지 않습니다.** 그 평가는 별도의 법령 전문가 Gold와 다른 스키마가 필요합니다.
- CAS 직접 표기되지 않은 염류·화합물군의 포함 여부 및 일부 명시 제외는 전문가가 다시 검토해야 합니다.

## 모델과 계산량

- 모델: `qwen2.5:3b`, `qwen3:4b-instruct`, `qwen3.5:4b`
- 사례 30 × A/B 2 = 질문 60개 × 모델 3개 = 180개 문항-모델 조합.
- 질문 1개당 검색어 생성 1회 + 법령 판정 1회 = **총 360회 LLM 호출**. 예비 12문항/모델은 본 실험에서 재사용됩니다.
- `num_ctx=4096`, 검색어 최대 220토큰, 최종 답변 최대 650토큰, temperature 0, seed 고정, Qwen3 non-thinking. 혼합물의 3성분 JSON은 기존보다 길어서 RTX 2060 6GB에서 2시간을 **초과할 수 있습니다.** `--group`으로 각 그룹을 나누어 실행하고 동일 출력에 누적할 수 있습니다.

## Windows PowerShell 실행

```powershell
cd D:\framework_chemical_regul_paper
# git pull origin main
cd llm_capability_study\retrieval_v4
python .\preflight.py
python .\run_retrieval.py --stage pilot --model all
python .\estimate_runtime.py --budget-minutes 120
```

이어서 전체 실행 또는 그룹별 분할 실행 중 하나를 선택합니다.

```powershell
# 한 번에 전부
python .\run_retrieval.py --stage main --model all

# 또는 구분해서 실행(결과는 동일 파일에 누적, 중복 실행 없음)
python .\run_retrieval.py --stage main --model all --group PARENT_AND_SALTS
python .\run_retrieval.py --stage main --model all --group COMPOUND_CLASS
python .\run_retrieval.py --stage main --model all --group MIXTURE

# Gold를 private/에 둔 후
python .\score_results.py
```

완료한 질문은 `results/qwen...__main.jsonl`에 **즉시 저장**되며 같은 조건으로 재실행하면 이어서 진행됩니다. `--force`는 기존 해당 단계 파일을 삭제하므로 사용하지 마세요. 과거 v4의 결과는 **다른 연구설계라 호환되지 않습니다.** 기존 결과가 PC에 있다면 `results/`를 먼저 별도 폴더로 백업하고 새 실험용 폴더에서 실행하세요.

## 파일과 정답 관리

- 공개 입력: `data/cases_60.jsonl`, `data/official_annex_2026_5_full.csv`, `data/pilot_12_ids.json`, `data/manifest.json`, `data/validation_three_groups_60.xlsx`.
- 로컬 전용 비공개: `private/gold_60.jsonl`, `private/candidate_review.csv`, 별도의 전문가 검토 엑셀. 공개 GitHub에 올리지 마세요.
- **Gold는 30사례 모두 연구자 잠정판정(`CURATED_PROVISIONAL`)입니다.** 이 상태에서의 채점은 디버깅·예비실험용이지 전문가 판정이 완료된 법적 정답률이 아닙니다.
- 평가 지표: 성분별 법령행 검색 성공, 혼합물에서 전 성분 증거 확보, 성분별 관계분류·규제범위 판단, 제3조 전부 지정물질 요건 판정, 문항별 완전정답률, A/B 차이.
- 2개 이상의 가상 혼합물에 **같은 CAS 성분이 재사용**되므로, 모든 사례/성분이 완전히 독립적인 표본이라고 주장하면 안 됩니다. 사례 단위 대응 비교를 기본으로 하고, 중복 CAS의 영향은 별도 감도분석이 필요합니다.

공식 데이터 출처: 사용자가 제공한 `2026-5_(별표) 인체등유해성물질 목록(전체)(2).xlsx`. 화학물질 구조정보는 기존 v2/v3/v4 자료 및 PubChem CAS 동의어를 참고한 잠정 자료이며, 화학적 정체 및 법령 적용범위의 독립 검증은 별도 절차입니다.
