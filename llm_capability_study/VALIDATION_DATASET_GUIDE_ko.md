# 검증물질 데이터셋 구축: 한 폴더, 한 검토표

지금은 LLM을 평가하는 단계가 아니라 **정답이 검증된 평가자료를 완성하는 단계**입니다. 수집·사전검토는 명령 하나로 끝나고, 결과는 `candidates/` 폴더 하나에만 쌓입니다.

## 1. 명령 두 개

PowerShell (`D:\framework_chemical_regul_paper\llm_capability_study`, Python 환경 `chemprop`):

    git pull
    conda activate chemprop
    pip install rdkit

    # (1) 수집 + 중복 제거 + 자동 사전검토 → candidates\review_sheet.csv
    python collect_candidates.py --online --target-total 300

    # (2) 검토표에 정답을 채운 뒤: 조립·점검 → validation_dataset\draft\
    python build_validation_dataset.py

- `--target-total 300`은 **기존 112건을 포함한** 전체 규모입니다. 정답 검토에서 빠질 후보를 감안해 20% 더 모으므로 후보 행은 226건이 목표입니다(`--overshoot`로 조정).
- 같은 명령을 다시 실행하면 **같은 폴더에 이어서 추가**합니다. 이미 채운 `human_*` 열은 그대로 보존됩니다(직전 검토표는 `review_sheet.previous.csv`로 백업).
- `--online` 없이 실행하면 네트워크 없이 가져오기·중복 제거·사전검토만 다시 합니다.
- 목표에 못 미치면 실행 끝에 부족한 건수가 출력됩니다. PubChem에서 새로 찾을 수 있는 후보가 소진되면 더 늘릴 수 없으니, 그때는 `boundary_probes.py`의 탐색 이름을 늘리거나 목표를 조정해야 합니다.
- GitHub에서 실행하려면 Actions의 `Collect validation candidates`(Run workflow)를 쓰고 Artifacts의 `candidates`를 내려받아 이 폴더에 덮어 넣으세요.

예전에 만든 `collection_output\balanced_v2`, `collection_output\boundary_v1` 폴더는 더 이상 필요 없습니다. 안에 있던 PubChem 응답 캐시는 첫 실행 때 자동으로 가져옵니다. 실행이 끝난 뒤 지워도 됩니다.

## 2. `candidates/` 폴더

| 파일 | 내용 |
| --- | --- |
| **`review_sheet.csv`** | **여기에 정답을 채웁니다.** 후보 1건당 1행, 자동 사전검토 결과(`auto_*`)와 사람이 채울 열(`human_*`) |
| `candidates_for_review.csv` | 수집 원본(PubChem 식별 정보, 수집 경로). 직접 고치지 않습니다 |
| `review_target_hits.csv` | 후보와 규제항목의 관계를 1건씩 풀어 쓴 근거 목록 |
| `dropped_candidates.csv` | 기존 112건과 같은 CAS·구조라서 제외한 후보와 사유 |
| `summary.json` | 건수, 출처별·분류별 집계, 목표 대비 부족분, 카탈로그 경고 |
| `mixture_name_resolution.csv` | 성분 CAS가 없는 카탈로그 혼합물 6개의 성분 이름 → PubChem CAS 후보 (수집 실행 후 생성) |
| `_sources/` | 첫 실행 때 가져오는 이전 배치 원본(87건, 65건) |

`case_id`는 `CAND-0001`부터 한 가지 체계로 붙고, 이전 배치의 번호는 `legacy_case_id`에 남아 있습니다.

## 3. 검토표 작성 규칙 (`review_sheet.csv`)

`auto_*`와 `gold_*` 열은 건드리지 않고 아래 3개 열만 채웁니다.

| 열 | 입력값 |
| --- | --- |
| `human_gold_target_id` | 해당 규제항목 ID 하나, 또는 `NOT_FOUND` (29개 항목 어디에도 해당하지 않음) |
| `human_legal_basis` | 근거: 고시 이름·개정일·조항 또는 URL, 화학적 동일성 근거 |
| `human_review_status` | `ADJUDICATED`(검토 완료, 데이터셋에 포함) / `EXCLUDED`(제외) / `PENDING`·`HOLD`(보류) |

- 빌더는 `ADJUDICATED`이면서 정답과 법적 근거가 모두 채워진 행만 포함합니다. 정답에 항목 ID를 둘 이상 적으면(`A|B`) 보류됩니다.
- `auto_prereview_class`는 **검토 우선순위일 뿐 정답이 아닙니다.** `NOT_FOUND`는 자동으로 붙지 않습니다. `legal_basis_verification_required`는 항상 `YES`입니다.
- `review_priority=HIGH`부터 보세요. 같은 물질이 다른 CAS로 겹치는 후보(`DUPLICATE_STRUCTURE_OF_...` 플래그)는 하나만 남기고 나머지는 `EXCLUDED`로 두면 됩니다.

## 4. 조립과 고정

    python build_validation_dataset.py                       # 초안 점검 (기본으로 candidates\review_sheet.csv 사용)
    python build_validation_dataset.py --version v1 --freeze # 오류가 없을 때 고정

결과(`validation_dataset\<version>\`): `validation_INPUT.csv`(모델에 줄 `query_id, cas_inputs, smiles`만), `validation_GOLD.csv`, `validation_METADATA.csv`, `composition_report.json`(건수, 유형별 구성, 300~400건 대비 부족분, 오류와 경고). 기존 112건은 그대로 두고 `ADJUDICATED` 행만 `RQ-0113`부터 이어 붙입니다. 고정 후에는 정답을 고치지 않습니다.

## 5. 혼합물 방침

- 기존 코드의 원칙대로 **성분을 바꿔 끼워 혼합물을 만들지 않습니다.**
- 카탈로그 혼합물 15개 중 9개는 이미 기존 112건에 있습니다. 나머지 6개(`MX::2017-886, 887, 890, 891, 892, 2026-1-1328`)는 성분 CAS가 없어 질의를 만들 수 없습니다. `mixture_name_resolution.csv`의 CAS 후보를 **공식 규제자료로 확인**한 뒤에만 혼합물 질의로 추가할 수 있습니다.
- 규제 대상이 아닌 실제 혼합물(NOT_FOUND 사례)은 공식 자료에서 근거가 확인되는 것만 추가해야 합니다. 출처는 연구자가 정해야 합니다.

## 6. 고급: 개별 단계

`collect_pubchem_candidates.py`(균형 수집), `collect_boundary_candidates.py`(경계 프로브), `prereview_candidates.py`(사전검토)는 통합 수집기가 내부에서 호출하는 단계입니다. 평소에는 `collect_candidates.py`만 쓰면 됩니다.
