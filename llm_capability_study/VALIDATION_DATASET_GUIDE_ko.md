# 2026-11-17: Gold 확정 전 검증 절차 (우선 실행)

**현재 Gold 데이터셋은 아직 논문용으로 고정된 상태가 아닙니다. 독립 검토자 두 명은 필수 조건이 아니며, 물질별 공식 근거 대조와 Gold 정합성 확인이 기준입니다.**
29개 규제항목 안에서의 식별 성능을 검증하는 연구이며, 국내 모든 법령의 비규제 여부를 판정하는 것이 아닙니다.
기존 112건은 읽기 전용 역사적 기준자료로 보존합니다.

- [검토 중인 Pull Request #14](https://github.com/goindoll97-cloud/industrypaper/pull/14)
- 이 브랜치의 신규 후보 244건 중 ADJUDICATED 193건, EXCLUDED 51건
- **182건의 법적 근거 문구에 원문 대조 필요가 남아 있음**. 이들의 검증이 완료되었다는 뜻이 아닙니다.
- 고정 규제항목 29개 정의의 독립된 공식 출처 확인도 별도로 필요합니다.
- 경고 문구만 지우거나 PENDING을 VERIFIED로 바꾸어 검증 완료로 표시하지 마세요. 검토자 2명의 별도 서명 파일은 필수로 요구하지 않습니다.


## 현재 GitHub에 있는 법적 자료와 없는 자료

- \`data/regulatory_catalog.csv\`: **29개 규제항목의 범위·CAS 목록** 보유. 이 파일은 원문 법령 PDF가 아닙니다.
- \`candidates/catalog_source_registry.csv\`: 법제처 공식 링크가 **물질군 5개와 지정 혼합물 1개**에 기재됨. 나머지 23개 target에는 공식 출처 링크가 기록되지 않았습니다. 29개 전체가 아직 PENDING입니다.
- \`reference/mixture_regulatory_reference.csv\` 및 \`data/mixture_regulatory_reference_applied.csv\`: \`MX::2023-1-1162\` 1건의 법제처 고시 별표 링크 수록.
- \`review/retrieval_gold_manual_review.csv\`: 기존 112건의 Gold 검토 이력이며 법령 원문 파일은 아닙니다.
- **추가 원문이 필요한 대상:** PS 모체·염류 9개 및 공식 출처가 없는 MX 혼합물 14개 항목. 5개 물질군도 이미 있는 공식 링크의 시행판·조항을 다시 검증해야 합니다.
- 법제처 API에서 내려받은 고시 **PDF·HWP·HTML·XML·엑셀**을 주시면 기존 자료와 대조할 수 있습니다. 2인 독립 검토는 요구하지 않습니다.

## A. GitHub Actions에서 자동 점검 (로컬 없이 진행 가능)

1. PR #14의 Checks 또는 [Actions 화면](https://github.com/goindoll97-cloud/industrypaper/actions/workflows/llm-capability-audit.yml)에서 LLM capability study baseline audit를 엽니다.
2. 성공한 실행의 Artifacts에서 gold-readiness-draft를 내려받습니다.
3. 아래 파일을 확인합니다.
   - review_audit_output/legal_review_summary.json: 보류된 근거 및 CAS 이상
   - review_audit_output/legal_review_queue.csv: 우선순위별 법적 검토 대기열
   - ci_readiness_draft/composition_report.json: 조립 오류, 중복, 표본 구성, Gold 확정 준비 여부
4. **CI 통과는 기계적 점검의 성공이지 182건 법적 범위 확인의 완료가 아닙니다.**

## B. 이미 생성된 검토용 자료

- [우선순위별 미대조 182건 CSV](candidates/legal_review_queue_2026-11-17.csv)
- [규제항목 29개 공식 출처 검토표](candidates/catalog_source_registry.csv)
- [혼합물 18건 + 일반 20건 감사기록](candidates/review_audit_2026-11-17.md)

**검토 순서:** 규제대상 범위 판정 사례(SCOPE_POSITIVE), 경계형 비대상(NEGATIVE_SCOPE_NEAR_MISS),
일반 비대상(NEGATIVE_SCOPE_GENERAL), CAS 직접 일치 양성(EXACT_CAS_POSITIVE).

- 정답인 경우: 검증한 고시명, 발령번호 및 시행일, 별표·조항, CAS 정체성 또는 염류/물질군 근거를 review_sheet.csv의 human_legal_basis에 기재
- 비대상인 경우: 단순한 CAS 미등재가 아니라 동결된 29개 규제범위 어디에도 포함되지 않음을 확인
- 경계 사례: human_review_status를 EXCLUDED로 변경하고 사유 기재
- catalog_source_registry.csv: 검증자 이름, 검증일, 신뢰할 공식 출처 URL/문서 식별정보를 남긴 뒤에만 verification_status=VERIFIED 처리
- 9개 PS 항목과 일부 MX 항목은 공식 근거가 아직 명시되지 않았으므로 우선 보완

**중요한 카탈로그 문제:** MX::97-1-127의 설명에는 3084-48-0이 들어 있지만 CAS 체크디지트가
성립하지 않습니다. 카탈로그 성분 목록의 3084-48-8과 다릅니다.
공식 문서에도 같은 오타가 있을 수 있으므로 원문 및 실제 물질정보를 대조하고,
기존 112건 및 동결 카탈로그는 자동 변경하지 마세요.

## C. 로컬에서 재현하는 경우 (저장소 최상위 폴더에서)

PR 수정내용이 들어 있는 브랜치를 사용해야 합니다. main에서 실행하면 변경 전 데이터가 사용됩니다.

~~~powershell
git fetch origin review/cas-gold-audit-2026-11-17
git switch --track origin/review/cas-gold-audit-2026-11-17
# 같은 이름의 로컬 브랜치가 이미 있으면 git switch review/cas-gold-audit-2026-11-17
conda activate chemprop
python -m pip install rdkit

python llm_capability_study/tests/test_validation_pipeline.py
python llm_capability_study/tests/test_gold_readiness.py
python llm_capability_study/audit_gold_readiness.py
python llm_capability_study/build_validation_dataset.py --version local_audit_draft
~~~

실행 결과를 함께 보려면 다음 **두 파일**을 이 대화에 업로드해 주세요.

- llm_capability_study/candidates/review_audit_output/legal_review_summary.json
- llm_capability_study/validation_dataset/local_audit_draft/composition_report.json

오류로 중단되면 터미널 마지막 30줄을 보내주세요. 인증 토큰 등은 제외합니다.

## D. 최종 동결은 지금 실행하지 마세요

182개 물질별 법적 근거, 29개 규제항목 출처, 구조 및 CAS 중복 검토가
완료된 후 오류가 없는 경우에만 아래를 실행합니다.

~~~powershell
python llm_capability_study/build_validation_dataset.py --version v2_verified --freeze
~~~

빌더는 고시 원문 미대조, 출처 형식 미비, 29개 항목 출처검토 미승인, CAS·구조 오류가 남아 있으면
동결을 거부합니다. 이 자동 게이트만으로 법적 정답의 실질적 정확성이 보증되지는 않습니다.
이미 동결된 버전은 덮어쓰지 못하게 보호합니다.

---

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
- 같은 명령을 다시 실행하면 **같은 폴더에 이어서 추가**합니다. 이미 채운 `human_*` 열은 그대로 보존됩니다.
- `--online` 없이 실행하면 네트워크 없이 가져오기·중복 제거·사전검토만 다시 합니다.
- 목표에 못 미치면 실행 끝에 부족한 건수가 출력됩니다. PubChem에서 새로 찾을 수 있는 후보가 소진되면 더 늘릴 수 없으니, 그때는 `boundary_probes.py`의 탐색 이름을 늘리거나 목표를 조정해야 합니다.
- GitHub에서 실행하려면 Actions의 `Collect validation candidates`(Run workflow)를 쓰고 Artifacts의 `candidates`를 내려받아 이 폴더에 덮어 넣으세요.
- 이전 실행의 `collection_output\_stages` 캐시는 첫 실행 때 `_work`로 자동 복사됩니다.

예전에 만든 `collection_output\balanced_v2`, `collection_output\boundary_v1` 폴더는 더 이상 필요 없습니다. 안에 있던 PubChem 응답 캐시는 첫 실행 때 자동으로 가져옵니다. 실행이 끝난 뒤 지워도 됩니다.

## 2. `candidates/` 폴더 (파일 2개)

| 파일 | 내용 |
| --- | --- |
| **`review_sheet.csv`** | **여기에 정답을 채웁니다.** 후보 1건당 1행. 수집 정보, 자동 사전검토 결과(`auto_*`), 사람이 채울 열(`human_*`)이 한 파일에 있고, 이 파일이 후보 목록 자체이기도 합니다 |
| `summary.json` | 건수, 출처별·분류별 집계, 목표 대비 부족분, 제외된 후보와 사유(`dropped_candidates`), 성분 CAS가 없는 혼합물 6개의 PubChem 후보(`mixture_name_resolution`), 카탈로그 경고 |

`_sources/`는 첫 실행 때 가져오는 이전 배치 원본이며 이후에는 쓰이지 않습니다. 수집 중간 파일과 PubChem 응답 캐시는 `collection_output\_work\`(A=균형 수집, B=경계 프로브)에만 쌓이며 열어볼 필요가 없고 Git에도 올라가지 않습니다.

`case_id`는 `CAND-0001`부터 한 가지 체계로 붙고, 이전 배치의 번호는 `legacy_case_id`에 남아 있습니다.

## 3. 검토표 작성 규칙 (`review_sheet.csv`)

`auto_*`와 `gold_*` 열은 건드리지 않고 아래 3개 열만 채웁니다.

| 열 | 입력값 |
| --- | --- |
| `human_gold_target_id` | 해당 규제항목 ID 하나, 또는 `NOT_FOUND` (29개 항목 어디에도 해당하지 않음) |
| `human_legal_basis` | 근거: 고시 이름·개정일·조항 또는 URL, 화학적 동일성 근거 |
| `human_review_status` | `ADJUDICATED`(검토 완료, 데이터셋에 포함) / `EXCLUDED`(제외) / `PENDING`·`HOLD`(보류) |

- 빌더는 `ADJUDICATED`이면서 정답과 법적 근거가 모두 채워진 행만 포함합니다.
- **규제항목이 겹치는 물질은 겹치는 그대로 정답을 적습니다.** 해당하는 항목 ID를 `|`로 모두 적으면(예: `CG::LEAD_COMPOUNDS|PS::64-19-7`) 모델이 모두 찾아야 정답으로 보는 고난도 문항이 됩니다. 후보는 `auto_possible_target_ids`와 `auto_multi_target_overlap`을 참고하세요. `NOT_FOUND`는 다른 항목과 함께 적을 수 없습니다.
- **정답을 확정하기 어려운 후보는 `EXCLUDED`로 두고 빼면 됩니다.** `AMBIGUOUS` 분류나 근거를 확인하지 못한 후보가 해당합니다. 제외·보류된 행의 목록과 사유는 `composition_report.json`의 `excluded_cases`, `held_cases`에 나옵니다.
- `auto_prereview_class`는 **검토 우선순위일 뿐 정답이 아닙니다.** `NOT_FOUND`는 자동으로 붙지 않습니다. `legal_basis_verification_required`는 항상 `YES`입니다.
- `review_priority=HIGH`부터 보세요. 같은 물질이 다른 CAS로 겹치는 후보(`DUPLICATE_STRUCTURE_OF_...` 플래그)는 하나만 남기고 나머지는 `EXCLUDED`로 두면 됩니다.

## 4. 조립과 고정

    python build_validation_dataset.py                       # 초안 점검 (기본으로 candidates\review_sheet.csv 사용)
    python build_validation_dataset.py --version v1 --freeze # 오류가 없을 때 고정

결과(`validation_dataset\<version>\`, 파일 4개 + 고정 시 1개):

| 파일 | 내용 |
| --- | --- |
| `validation_INPUT.csv` | 모델에 줄 `query_id, cas_inputs, smiles`만 |
| `validation_GOLD.csv` | 정답(`gold_target_id`, 다중이면 `A|B`, `n_gold_targets`), 근거, 출처 |
| `validation_METADATA.csv` | 분석용 출처·층·이름(모델에 주지 않음) |
| `composition_report.json` | 건수, 유형별 구성, 300~400건 대비 부족분, 다중 정답 문항 수, 제외·보류 목록, 오류와 경고 |
| `VALIDATION_DATASET_FREEZE.json` | `--freeze` 성공 시에만. 파일 해시 |

기존 112건은 그대로 두고 `ADJUDICATED` 행만 `RQ-0113`부터 이어 붙입니다. 고정 후에는 정답을 고치지 않습니다.

## 5. 혼합물 방침

- 기존 코드의 원칙대로 **성분을 바꿔 끼워 혼합물을 만들지 않습니다.**
- 카탈로그 혼합물 15개 중 9개는 이미 기존 112건에 있습니다. 나머지 6개(`MX::2017-886, 887, 890, 891, 892, 2026-1-1328`)는 성분 CAS가 없어 질의를 만들 수 없습니다. `mixture_name_resolution.csv`의 CAS 후보를 **공식 규제자료로 확인**한 뒤에만 혼합물 질의로 추가할 수 있습니다.
- 규제 대상이 아닌 실제 혼합물(NOT_FOUND 사례)은 공식 자료에서 근거가 확인되는 것만 추가해야 합니다. 출처는 연구자가 정해야 합니다.

## 5-1. 혼합물만 따로 추가 수집

    python collect_mixtures.py --builtin                      # 공식·권위 자료로 성분 CAS를 확인한 실제 이성질체 혼합물 12건(카탈로그 밖, NOT_FOUND 초안) 추가
    python collect_mixtures.py --pairs 8                      # 합성 2성분 질의: 성분마다 서로 다른 카탈로그 항목에 직접 일치 → 정답 A|B (실제 제품 아님, 'MIXTURE_SYNTHETIC_PAIR'로 표시)
    python collect_mixtures.py --online                       # 성분 CAS가 없는 카탈로그 혼합물 6개: 성분 이름 → PubChem CAS
    python collect_mixtures.py --input mixtures_input.csv     # 공식 자료에서 직접 찾은 실제 혼합물 (NOT_FOUND 사례 포함)

- `mixtures_input.csv` 열: `mixture_name`, `component_cas`(CAS를 `|`로 연결, 예: `67-64-1|67-56-1`), `source`(고시명 또는 URL).
- 결과는 새 파일 없이 같은 `candidates\review_sheet.csv`에 행으로 추가되고, 확정하지 못한 성분은 `summary.json`의 `mixture_collection`에 남습니다.
- 이름으로 찾은 CAS는 `MIXTURE_NAME_RESOLVED_NEEDS_OFFICIAL_CAS` 표시가 붙으며 반드시 공식 자료로 확인해야 합니다. 성분당 CAS가 하나로 정해지지 않으면 행을 만들지 않습니다.
- 기존 112건이나 이미 있는 혼합물과 성분 조합이 같으면 제외하고, 카탈로그 혼합물의 성분 일부만 든 경우는 `AMBIGUOUS`로 표시합니다.

## 6. 고급: 개별 단계

`collect_pubchem_candidates.py`(균형 수집), `collect_boundary_candidates.py`(경계 프로브), `prereview_candidates.py`(사전검토)는 통합 수집기가 내부에서 호출하는 단계입니다. 평소에는 `collect_candidates.py`만 쓰면 됩니다.
