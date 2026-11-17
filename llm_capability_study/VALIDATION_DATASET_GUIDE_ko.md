# 검증물질 데이터셋 구축 절차 (기존 112건 + 신규 검증물질 → 300~400건)

지금은 LLM을 평가하는 단계가 아니라 **정답이 검증된 평가자료를 완성하는 단계**입니다. 아래 순서로 진행합니다.

## 전체 흐름

| 단계 | 담당 | 도구 | 산출물 |
| --- | --- | --- | --- |
| 1. 후보 수집 | 자동 | `collect_pubchem_candidates.py`(완료), `collect_boundary_candidates.py`(신규) | `candidates_for_review.csv` |
| 2. 자동 사전검토 | 자동 | `prereview_candidates.py` | `prereview_results.csv` (검토 우선순위, Gold 아님) |
| 3. 정답 검토 | **연구자** | 검토표의 `human_*` 열 | 법적 근거가 붙은 정답 |
| 4. 데이터셋 조립·점검 | 자동 | `build_validation_dataset.py` | `validation_dataset/<version>/` |
| 5. 고정(freeze) | 연구자 확인 후 | `--freeze` | `VALIDATION_DATASET_FREEZE.json` |

모델 평가 코드는 5단계 이후에 개발합니다. `validation_INPUT.csv`에는 `query_id, cas_inputs, smiles`만 있어서 정답·물질명·수집경로가 모델에 전달될 수 없습니다.

## 3단계: 검토표 작성 규칙

`prereview_results.csv`에서 아래 3개 열만 채웁니다. 나머지 `auto_*`와 `gold_*` 열은 건드리지 않습니다.

| 열 | 입력값 |
| --- | --- |
| `human_gold_target_id` | 해당 규제항목 ID 하나, 또는 `NOT_FOUND` (29개 항목 어디에도 해당하지 않음) |
| `human_legal_basis` | 근거: 고시 이름·개정일·조항 또는 URL, 화학적 동일성 근거 |
| `human_review_status` | `ADJUDICATED`(검토 완료, 데이터셋에 포함) / `EXCLUDED`(제외: 중복 등) / `PENDING`·`HOLD`(보류) |

- 빌더는 `ADJUDICATED`이면서 정답과 법적 근거가 모두 채워진 행만 포함합니다.
- 정답에 항목 ID를 둘 이상 적으면(`A|B`) 보류됩니다. 중첩 사례의 판정 규칙을 먼저 정해야 합니다.
- 우선순위: `review_priority=HIGH`부터, 플래그 `DUPLICATE_STRUCTURE_OF_BASELINE`는 먼저 `EXCLUDED` 여부를 판단하세요.
- `auto_prereview_class`가 `POSSIBLE_OUT_OF_SCOPE`여도 자동으로 `NOT_FOUND`가 되지 않습니다. 직접 확인한 뒤에 입력합니다.

## 4~5단계: 조립과 고정

초안 점검(몇 건이 모였는지, 유형별 구성, 오류):

    python build_validation_dataset.py --reviewed .\prereview_output\balanced_v2\prereview_results.csv

배치가 여러 개면 `--reviewed`를 반복합니다. 결과는 `validation_dataset\draft\`에 저장되며 `composition_report.json`에 다음이 들어 있습니다.

- 전체 건수와 300~400건 목표 대비 부족분, 유형별·FOUND/NOT_FOUND별 구성
- 신규 행 중 보류·제외된 건수와 사유
- 유형별 최소 건수(`--min-per-category`, 기본 30)에 못 미치는 유형. 이 값은 계획용 기준이며 통계적 검정력 계산 결과가 아닙니다.
- FOUND 사례가 하나도 없는 규제항목
- 오류(중복 CAS, 구조 중복, 정답이 카탈로그 CAS 일치와 모순)와 경고

오류가 없고 구성이 만족스러우면 고정합니다. 고정 후에는 정답을 고치지 않습니다.

    python build_validation_dataset.py --reviewed .\prereview_output\balanced_v2\prereview_results.csv --version v1 --freeze

## 혼합물 보강 방침

- 기존 코드의 원칙대로 **성분을 바꿔 끼워 혼합물을 만들지 않습니다.**
- 카탈로그의 혼합물 15개 중 9개는 이미 기존 112건에 들어 있습니다. 나머지 6개(`MX::2017-886, 887, 890, 891, 892, 2026-1-1328`)는 성분 CAS가 카탈로그에 없어 질의를 만들 수 없습니다.
- `collect_boundary_candidates.py`가 이 6개의 성분 이름을 PubChem에서 찾아 CAS 후보를 `mixture_name_resolution.csv`로 냅니다. 이는 후보일 뿐이며 **공식 규제자료의 혼합물 CAS로 확인**한 뒤에만 혼합물 질의로 추가할 수 있습니다.
- 규제 대상이 아닌 실제 혼합물(NOT_FOUND 사례)은 공식 자료(정부·공공기관 화학물질 정보)에서 근거가 확인되는 것만 추가해야 합니다. 어떤 자료를 출처로 삼을지는 연구자가 정해야 합니다.

## 지금 실행할 명령어

### A. 보강 수집 (PubChem 접속 필요)

방법 1. GitHub에서 실행 (설치 불필요)

1. https://github.com/goindoll97-cloud/industrypaper/actions/workflows/boundary-candidate-collector.yml
2. Run workflow: online=true, max_candidates=100, max_requests=600, run_id=boundary_v1
3. 끝나면 Artifacts의 `boundary-candidate-batch-boundary_v1` 내려받기 (후보 CSV와 사전검토 결과가 함께 들어 있음)

방법 2. PowerShell에서 실행 (`D:\framework_chemical_regul_paper\llm_capability_study`, 환경 `chemprop`)

    git pull
    conda activate chemprop
    pip install rdkit
    python collect_boundary_candidates.py --online --run-id boundary_v1 --max-candidates 100 --max-requests 600 --exclude-file .\collection_output\balanced_v2\candidates_for_review.csv
    python prereview_candidates.py --candidates .\collection_output\boundary_v1\candidates_for_review.csv

### B. 기존 87건 정답 검토

수집 없이 바로 가능합니다. `git pull` 후 `prereview_output\balanced_v2\prereview_results.csv`를 엑셀로 열어 3단계 규칙대로 채우세요.
