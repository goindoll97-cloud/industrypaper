# 신규 후보물질 규제대상 자동 사전검토 (prereview_candidates.py)

## 1. 목적과 한계

PubChem에서 수집한 신규 후보(기본 `REVIEW_PENDING`)를 고정된 29개 규제항목과 자동 비교해 **사람이 먼저 검토할 순서와 근거**를 만들어 줍니다.

- 자동 사전검토 결과는 **최종 Gold가 아닙니다.** 모든 행의 `gold_status`는 `REVIEW_PENDING`, `gold_target_id`는 빈칸으로 유지됩니다.
- `NOT_FOUND`는 자동으로 부여하지 않습니다. `POSSIBLE_OUT_OF_SCOPE`는 "비대상 가능성, 추가 검토 필요"라는 뜻입니다.
- CAS가 목록과 일치해도(`EXACT_CAS_MATCH`) 공식 고시 원문과 대조해야 하므로 `legal_basis_verification_required`는 항상 `YES`입니다.
- RDKit은 검토자를 돕는 구조 분석 보조 도구로만 쓰며, 논문에서 평가할 Hybrid 예측모델이 아닙니다.

## 2. 자동 분류(`auto_prereview_class`)

| 분류 | 의미 | 근거 |
| --- | --- | --- |
| `EXACT_CAS_MATCH` | 규제목록 CAS 직접 일치 | 원물질 기준 CAS, 공식 구성원 CAS, 공식 혼합물 CAS |
| `POSSIBLE_GROUP_MEMBER` | 화학물질군 해당 가능성 | 구조 규칙(Pb 포함, Cr(=O)=O, 말라카이트 그린 양이온, C9 알킬페놀, 트리알킬주석) |
| `POSSIBLE_PARENT_SALT` | 원물질·염류 관련성 | 원물질 골격을 가진 조각 + 대이온 또는 다성분 구성 |
| `POSSIBLE_OUT_OF_SCOPE` | 비대상 가능성 | 위 항목에 모두 해당 없음. 구조가 유사하면 `NEAR_NEIGHBOR_OF_TARGET` 플래그와 함께 우선 검토 |
| `AMBIGUOUS` | 법적 범위 또는 동일성 판단 불명확 | 복수 항목 중첩, 혼합물 구성성분 CAS만 일치, 원물질과 같은 구조인데 CAS가 다름, 구조 정보 없음 |

혼합물(`MX::`) 항목은 구성성분 CAS가 일치해도 단일 물질이 혼합물 항목에 해당하는지는 법적 판단이 필요하므로 `EXACT`가 아니라 `AMBIGUOUS`로 분류합니다.

## 3. 주요 플래그(`auto_flags`)

- `MULTI_TARGET_OVERLAP`: 둘 이상의 규제항목에 중첩 가능 (예: 말라카이트 그린 옥살산염은 말라카이트 그린 염류와 옥살산 및 그 염류에 모두 해당할 수 있음)
- `DUPLICATE_STRUCTURE_OF_CANDIDATE:<case_id>`, `DUPLICATE_STRUCTURE_OF_CATALOG:<CAS>`, `DUPLICATE_STRUCTURE_OF_BASELINE:<CAS>`: 다른 CAS이지만 같은 물질로 보이는 경우(수화물, 입체이성질체, 이온/공유 결합 표기 차이). 기존 112건과 겹치면 신규 검증물질에서 제외할지 검토
- `EXACT_CAS_BUT_RULE_NOT_CONFIRMED:<target>`: CAS는 일치하나 구조 규칙으로는 확인되지 않음
- `COLLECTION_HINT_NOT_CONFIRMED`: 수집 단계가 제시한 대상 힌트를 사전검토에서 확인하지 못함
- `NEAR_NEIGHBOR_OF_TARGET:<target>`: 해당 항목에는 해당하지 않지만 구조가 유사함(Tanimoto 0.5 이상, `--near-threshold`로 조정)
- `MULTI_COMPONENT_ENTRY`, `STRUCTURE_MISSING`, `SMILES_PARSE_FAILED`, `CAS_CHECKSUM_INVALID`

## 4. 출력 파일 (`prereview_output/<배치명>/`)

- `prereview_results.csv`: 후보 1건당 1행. `auto_*` 열(자동 결과)과 `human_*` 열(사람이 채울 칸)이 분리되어 있음
- `prereview_target_hits.csv`: 후보와 규제항목의 관계를 1건씩 풀어 쓴 근거 목록
- `prereview_summary.json`: 분류별 건수, 중첩 사례, **규제목록 자체의 불일치 경고**(`catalog_warnings`)

## 5. Windows PowerShell 실행

현재 위치가 `D:\framework_chemical_regul_paper\llm_capability_study`이고 Python 환경이 `chemprop`이라면:

    git pull
    conda activate chemprop
    pip install rdkit
    python prereview_candidates.py --candidates .\collection_output\balanced_v2\candidates_for_review.csv

결과는 `.\prereview_output\balanced_v2\`에 저장됩니다. 저장소에는 현재 87건 배치 사본이 `candidate_batches\balanced_v2\`에 들어 있어서 아래처럼 바로 재현할 수도 있습니다.

    python prereview_candidates.py --candidates .\candidate_batches\balanced_v2\candidates_for_review.csv

RDKit이 없어도 CAS 직접 일치 확인은 동작하지만, 구조 기반 판정은 모두 `AMBIGUOUS`(`RDKIT_UNAVAILABLE`)로 표시됩니다.

테스트:

    python tests\test_prereview.py

## 6. 알려진 한계

- 구조 규칙은 검토 우선순위를 정하는 휴리스틱입니다. 예를 들어 크로뮴 6가는 SMILES의 `Cr(=O)=O` 단위로만 추정하며 산화수를 계산하지 않습니다.
- 목록에 CAS가 열거되지 않은 염류나 화합물이 군 항목에 포함되는지는 법령 해석 문제이므로 자동으로 확정하지 않습니다.
- 규제항목 29개 안에서만 비교합니다. 다른 법령의 규제 여부는 다루지 않습니다.
