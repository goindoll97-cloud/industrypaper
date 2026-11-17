> **알림:** 수집은 이제 `python collect_candidates.py --online --target-total 300` 한 번으로 끝나고 결과는 `candidates/` 폴더 하나에 쌓입니다. 절차는 [VALIDATION_DATASET_GUIDE_ko.md](VALIDATION_DATASET_GUIDE_ko.md)를 보세요. 아래 내용은 내부 단계 `collect_pubchem_candidates.py`의 설명입니다.

# PubChem 자동 후보 수집 v2: 규제목록과 무관한 일반 화학물질도 포함

## 1. 수정된 수집 설계

기존에는 29개 규제항목의 CAS와 그 구조적 이웃에 의존했습니다. v2에서는 규제목록을 출발점으로 삼지 않는 별도의 일반 화학물질 수집 경로를 추가했습니다.

| candidate_stratum | 온라인 기본 목표 비율 | 수집 방법 |
| --- | ---: | --- |
| CATALOG_LISTED | 최대 20% | 기존 규제목록에 명시된 CAS 중 기존 112건에 없는 후보 |
| NEAR_CATALOG | 최대 40% | 규제물질에서 출발한 염류·구조 유사성 검색 |
| INDEPENDENT_GENERAL | 목표 40% | 독립적인 일반 화학물질명 및 PubChem CID 표본 탐색 |

**수집 경로는 법적 정답이 아닙니다.** 일반 화학물질 검색에서 발견한 물질이 규제범위에 포함될 수도 있습니다. 수집된 모든 후보는 gold_status=REVIEW_PENDING이며 규제대상 여부를 자동 판정하지 않습니다.

## 2. 컴퓨터에서 기존 코드를 갱신하기

Git 저장소라면 상위 폴더에서 git pull을 실행하면 됩니다. 이전처럼 파일을 직접 다운받았다면 아래 **두 개 파일을 모두 갱신**해서 같은 llm_capability_study 폴더에 놓으세요.

- https://github.com/goindoll97-cloud/industrypaper/blob/main/llm_capability_study/collect_pubchem_candidates.py
- https://github.com/goindoll97-cloud/industrypaper/blob/main/llm_capability_study/independent_pubchem_sources.py

기존 data 및 intermediate 폴더도 같은 저장소 안에 있어야 합니다.

## 3. Windows PowerShell에서 실행

현재 작업 폴더가 D:\framework_chemical_regul_paper\llm_capability_study라면:

    # 기존 저장자료만 사용한 점검
    python collect_pubchem_candidates.py --max-candidates 30

    # PubChem에 실제 접속, 수집 경로별 목표 20:40:40, 신규 후보 최대 100건
    python collect_pubchem_candidates.py --online --max-candidates 100 --max-requests 350 --run-id balanced_v2

이 실행에서 CATALOG_LISTED 최대 20건, NEAR_CATALOG 최대 40건, INDEPENDENT_GENERAL 목표 40건으로 분리합니다. 이는 모집 목표이지 실제 수집 건수나 법적 정답 수의 보장이 아닙니다. PubChem 데이터 가용성과 CAS/CID 역조회 결과에 따라 더 적게 수집될 수 있습니다.

결과 경로:

    D:\framework_chemical_regul_paper\llm_capability_study\collection_output\balanced_v2\

- candidates_for_review.csv: CAS, SMILES, PubChem 출처, 검색 방법, candidate_stratum, 판정 검토 칸
- mixture_research_gaps.csv: 공식 혼합물 CAS가 없어 별도 조사해야 하는 경우
- collection_summary.json: 수집 경로별 결과, 실제 API 요청 수, 오류 및 입력 데이터 해시
- pubchem_http_cache/: 원본 PubChem API 응답 및 재실행 캐시

**기존 collection_output 폴더 바로 아래에 있던 이전 결과 CSV는 이 v2 실행에서 덮어쓰지 않습니다.** 다만 같은 run-id로 재실행하면 해당 run-id 폴더의 CSV는 갱신될 수 있으므로, 사람이 편집한 결과는 다른 곳에 보관하세요.

## 4. 추가 수집할 때 이전 후보도 제외하기

    python collect_pubchem_candidates.py --online --max-candidates 100 --max-requests 350 --run-id balanced_v2_batch2 --random-seed 20261118 --exclude-file ".\collection_output\balanced_v2\candidates_for_review.csv"

--exclude-file을 여러 번 지정하여 앞선 배치들을 계속 제외할 수도 있습니다. 기존 112건은 항상 중복 제외됩니다.

## 5. GitHub에서 직접 온라인 실행하기

1. https://github.com/goindoll97-cloud/industrypaper/actions/workflows/pubchem-candidate-collector.yml
2. Run workflow 클릭
3. online=true, max_candidates=100, max_requests=350 설정
4. 실행 완료 후 Artifacts에서 pubchem-candidate-review 다운로드

push로 실행되는 자동검사는 네트워크가 없는 점검입니다. **실제 PubChem 검색은 online=true로 수동 실행해야 합니다.**

## 6. 독립적인 일반 화학물질을 찾는 방식

- 일반 이름 검색: 용매, 생체물질, 아미노산, 의약품, 무기화합물, 천연물, 산업용 유기물 등의 여러 계열을 교대로 검색합니다. 연구자가 정한 이름의 목적표집이므로 무작위 대표표본은 아닙니다.
- CID 표본 탐색: 기본적으로 PubChem CID 1,000~1,000,000 사이의 숫자를 고정 난수 시드로 선택합니다. 해당 CID가 실제로 존재하는지, CAS가 연결되는지, SMILES가 있는지 확인합니다. **이는 PubChem 전체 화학물질을 균일하게 무작위 추출한 표본이 아닙니다.** CID 부여 순서와 결번에 따른 편향이 있습니다.

일반 후보라도 기존 규제 CAS가 명시된 것과 동일하면 독립 후보에서 제외합니다. 다만 모든 규제대상 여부를 자동으로 부정할 수는 없습니다.

수집 비율은 --listed-share 0.20 --general-share 0.40으로 조절하며, 나머지는 규제물질 관련 후보 몫입니다. 신규 PubChem 요청 수의 약 60%를 일반물질 수집에 배정하고, 나머지는 관련물질 검색에 남깁니다.

## 7. 정답 검토 및 LLM 평가 시 주의

- 규제대상 판정은 실제 고시의 적용범위와 화학적 동일성 근거로 **모델 평가 전에** 확정해야 합니다.
- NOT_FOUND는 오직 동결한 29개 규제항목을 기준으로 해당하지 않는다는 뜻입니다.
- PubChem에서 검색되지 않거나 CAS가 모호하면 비대상이라고 판단하지 않습니다.
- candidates_for_review.csv에는 물질명, 사람이 검토할 규제항목 힌트, 후보선정 경로가 있으므로 **CSV 전체를 그대로 LLM에 제공하면 안 됩니다.**
- 규제관련 후보와 독립 일반후보를 구별하여 성능을 집계해야 합니다. 의도적으로 균형을 맞춘 검증자료를 화학물질 전체의 대표 표본이라고 해석해서는 안 됩니다.
- 혼합물 성분의 임의 조합을 만들어 실제 등록 혼합물인 것처럼 검증자료에 포함하지 않습니다.

공식 API 설명: https://pubchem.ncbi.nlm.nih.gov/docs/pug-rest
