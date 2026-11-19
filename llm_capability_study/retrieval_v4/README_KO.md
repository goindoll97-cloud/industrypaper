# Retrieval v4 | 2026-5호 포괄 지정방식 전반의 LLM 법령 검색·판정 벤치마크

## 연구 질문

세대가 다른 Qwen 2.5 3B, Qwen 3 4B, Qwen 3.5 4B가 **동일한 화학적 정체정보와 동일한 2026-5호 전체 별표 검색 도구**를 사용했을 때, CAS 직접 지정이 없는 포괄적 규제범위와 명시적 예외·세부 지정·물리적 적용조건을 얼마나 정확하게 찾아내고 해석하는가?

이 폴더는 기존 v3에 덧붙이는 **신규 검증설계**입니다. v3는 보존됩니다. 고분자·반응생성물·UVCB를 **평가 대상 물질**에서 제외하였습니다. 다만 공식 별표 전체를 검색하는 DB에서는 삭제하지 않습니다(원본 충실성·검색 교란 조건 보존).

## 1. 1,451행 지정고시 범위 전수 스크리닝

- `data/scope_clause_audit.csv`: 원본 고시 1,451행에서 표현 기반으로 걸러진 **88개 후보행**. 원본 행번호, 명칭, CAS, 중첩 가능한 지정범위 태그, 연구상 제외 여부를 기록합니다.
- `data/scope_families.json`: 지정범위 표현을 11개 태그(포괄 지정·조건 및 예외·별도 지정 관련 표현)로 정리한 **비배타적 전수 스크리닝 분류표**입니다. 이 파일은 법령의 공식 분류체계가 아니며 용어 기반 스크리닝이므로, 법률적으로 모든 가능한 포괄행을 놓치지 않았다고 증명하는 자료는 아닙니다.
- 탄소수 범위로 표현된 *혼합조성 CAS* 행은 검토대상으로 기록하지만 고분자·반응생성물·UVCB 물질 자체를 본 실험에 넣지 않습니다.

## 2. 30개 검증 상황 × A/B 2조건

| 평가 가족(1차 유형) | 검증 상황 수 | 검증하는 법령 지정방식 |
|---|---:|---|
| `ORGANIC_PARENT_SALTS` | 3 | 특정 유기모체와 그 염류 |
| `INORGANIC_SALTS` | 3 | 무기 금속염·무기산 염류 |
| `ELEMENT_AND_COMPOUNDS` | 3 | 원소 및 그 화합물의 포괄 지정 |
| `ORGANOTIN_SUBCLASS` | 3 | 트리알킬·트리아릴주석, 산화물 포함, 개별 지정 |
| `INORG_ORG_SPECIES` | 3 | 무기시안화합물, 페리시안염 제외, 유기비소 구분 |
| `AROMATIC_ISOMER_CLASS` | 3 | 방향족 아민의 위치이성질체·명시적 제외 |
| `PCB_CHLORINE_COUNT` | 3 | PCB의 염소 치환 수에 따른 포함·제외 |
| `PHYSICAL_SIZE` | 6 | 납·구리·아연의 입자 크기 경계 및 세부 지정 |
| `CARBON_CHAIN_RANGE` | 2 | C12~C18 같은 알킬 탄소수 범위 (Gold 법률 검토 대기) |
| `NAMED_EXCEPTION` | 1 | 특정 염이 명시적으로 제외되는 조항 |
| **합계** | **30** | **27개 서로 다른 CAS**, 입자 크기만 다른 사례 포함 |

포괄 포함/명시적 제외/별도 세부항목 우선은 **1차 화학 유형과 교차하는 법적 관계**입니다. 30개 사례를 모두 서로 독립한 화학물질로 간주하지 마세요. 모든 유형이 동일한 표본 수가 아니므로 단순 유형별 평균을 동일 가중으로 일반화하지 마세요.

### 두 조건

- **A**: CAS + 영문 물질명 + 법적 판정에 필요한 **입자 크기(해당 사례에 한함)**.
- **B**: A 입력에 분자식과, 구조가 간단하고 검증 가능한 경우 연결성 SMILES를 추가.
- 입자 크기는 분자구조에서 알아낼 수 없으므로 양쪽 조건에 동일하게 명시합니다. 동일 CAS의 0.5mm·1.5mm는 **서로 다른 시험 상황**입니다.
- LLM에 후보 지정행/정답 고유번호/가족명/Gold/출처 행번호는 제공하지 않습니다.

## 3. 검색과 추론 분리

1. LLM은 입력된 화학물질 정보를 바탕으로 1~3개의 고시 검색어를 생성합니다.
2. 동일한 Python 검색기가 원본 **전체 1,451행 SQLite**에서 검색어를 조회해 8개 이내의 실제 검색행을 반환합니다.
3. 동일 LLM은 검색된 법령 근거로 직접 CAS 지정/포괄 포함/명시 제외/근거부족을 판단합니다.
4. Gold와 비교해 `Recall@8`(허용 가능한 복수 증거행 기준), 정확한 대표행 검색률, 조건부 추론 정확도, end-to-end 완전판정율과 A/B 차이를 기록합니다.

이는 **LLM이 검색어를 생성하고 고정된 검색기가 검색하는 1회 검색 시스템**입니다. 인터넷을 자유 탐색하거나 검색 결과를 반복 조회하는 에이전트가 아닙니다.

## 4. Gold 신뢰성

**중요:** 전문가의 독립 검토를 마친 **확정 법적 Gold는 아직 없습니다.** 

- `private/gold_60.jsonl`: 규제조항·물질 정보를 연결한 연구자 **잠정 Gold**.
- `CURATED_PROVISIONAL`: 27상황(54문항). **예비 성능 채점에만 포함**하며 논문 본문에 '법적으로 검증 완료'라고 쓰면 안 됩니다.
- `PENDING_INDEPENDENT_REVIEW`: 3상황(6문항). 위치이성질체의 하위번호/탄소수 범위 혼합물 지정범위가 불명확하여 **자동 성능 채점에서 제외**합니다.
- `private/candidate_review.csv`: 사례별 CAS, 법령 근거행, 구조정보 출처, 전문가 확인 체크란. 추후 전문가 검토 결과에 따라 Gold를 확정하고 **새 버전의 manifest/hash로 실험을 동결**해야 합니다.
- `EXPLICIT_EXCEPTION`은 *지목한 특정 포괄 지정항목의 적용 제외*입니다. 대한민국 전체 화학법령에 규제되지 않음을 뜻하지 않습니다.

고분자·반응생성물·UVCB는 사례에서 제외하였으므로 해당 물질군에 대한 결과를 주장할 수 없습니다. **본 자료는 비해당 대조군의 전체 법규상 비규제성을 검증한 자료가 아닙니다.**

## 5. RTX 2060 6GB 실행

총 **30상황 × A/B × 3모델 = 180개 문항-모델 조합**이며, 각각 검색어 생성과 법령 추론에 2회 호출하므로 기본 **360 LLM 호출**입니다. 1~2시간 목표는 **보장하지 않습니다**. 이전 v3 288호출보다 많으므로 반드시 예비실험 시간을 확인하세요.

Windows PowerShell:

```powershell
cd D:\framework_chemical_regul_paper
# GitHub 업데이트 이후
git pull origin main
cd llm_capability_study\retrieval_v4
python .\preflight.py
python .\run_retrieval.py --stage pilot --model all
python .\estimate_runtime.py --budget-minutes 120
```

예비실험(5상황×2조건×3모델 = 30 문항-모델 조합, 총 LLM 60회 호출)은 본실험에서 중복 호출하지 않습니다.

```powershell
python .\run_retrieval.py --stage main --model all
python .\score_results.py
```

- 실험 도중 `Ctrl+C`로 중단해도 **문항별 완료 기록**이 `results/*.jsonl`에 저장되어 같은 명령으로 재개됩니다.
- `--force`는 이전 파일을 **삭제**하여 다시 실행하는 기능이므로 주의하세요.
- 예비실험 실행 옵션과 본실험 실행 옵션은 동일해야 하며 모델 해시·원천자료 SHA가 고정됩니다.
- `num_ctx=3072`, 검색어 `num_predict=125`, 최종판정 `num_predict=420`, temperature=0, Qwen3 계열 nonthinking, 순차 GPU 실행입니다.
- 예상시간이 120분을 초과하면 A/B 전체 비교를 포기하고 B-only로 축소할 수 있습니다. **축소는 본실험 시작 전** 결정하고 논문에서 A/B 비교 결론을 내리지 마세요.

```powershell
python .\run_retrieval.py --stage main --model all --condition B
python .\score_results.py
```

## 6. 폴더 내용 및 보안

```text
llm_capability_study/
  retrieval_v3/                     # 기존 결과 재현용; 변경 안 함
  retrieval_v4/
    README_KO.md
    RUN_WINDOWS.ps1
    build_legal_db.py
    search_legal_db.py
    run_retrieval.py
    preflight.py
    estimate_runtime.py
    score_results.py
    data/
      official_annex_2026_5_full.csv
      scope_clause_audit.csv
      scope_families.json
      cases_60.jsonl
      pilot_10_ids.json
      manifest.json
    private/                       # GitHub 미업로드
      gold_60.jsonl
      candidate_review.csv
    results/                       # GitHub 미업로드
    tests/test_offline.py
```

원본 법령 근거는 사용자가 제공한 `2026-5_(별표) 인체등유해성물질 목록(전체)(2).xlsx`입니다. CAS/분자식 동정 근거는 개별 `private/candidate_review.csv`에 출처 URL로 함께 기록했습니다.
