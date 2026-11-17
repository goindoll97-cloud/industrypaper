# PubChem 검증물질 후보 자동 수집 안내

기존 29개 규제항목, 112개 검증사례, Claude 실험결과는 **변경하지 않습니다**.
PubChem PUG REST를 이용해 관련 후보를 찾되, 법적 규제대상 여부는 자동으로 단정하지 않습니다.

## A. GitHub 웹페이지에서 바로 실행하기 (Python 설치 불필요)

1. https://github.com/goindoll97-cloud/industrypaper/actions 에 접속
2. 왼쪽에서 **PubChem candidate collection (review only)** 선택
3. 오른쪽의 **Run workflow** 클릭
4. 설정값: online=true, max_candidates=60, max_requests=200
5. 실행 완료 후 해당 실행 결과 화면의 **Artifacts**에서 **pubchem-candidate-review** 다운로드
6. 압축파일의 **candidates_for_review.csv**를 Excel로 열어 검토

GitHub의 온라인 실행은 이 안내서 작성 당시에는 아직 직접 수행하지 않았습니다. 압축파일 내 collection_summary.json에서 mode=ONLINE_PUBCHEM_PUG_REST, new_network_requests와 errors를 확인해야 실제 API 연결 성공 여부를 알 수 있습니다. PubChem 또는 GitHub 작업 환경에 따라 일부 요청이 실패할 수 있습니다.

## B. Windows PowerShell에서 실행하기

Python 3.10 이상 필요. 추가 pip 설치는 필요하지 않습니다.

    cd industrypaper
    git pull

    # 네트워크 없는 사전 검사: 기존 PubChem 정확 CAS 캐시 사용
    python llm_capability_study/collect_pubchem_candidates.py --max-candidates 30

    # PubChem 실제 검색: 기존 112건 제외, 신규 후보 최대 60건
    python llm_capability_study/collect_pubchem_candidates.py --online --max-candidates 60 --max-requests 200

    # 이후 다시 실행하면 이미 얻은 API 응답을 캐시에서 재활용
    python llm_capability_study/collect_pubchem_candidates.py --online --max-candidates 100 --max-requests 300

기본 저장 폴더는 llm_capability_study/collection_output/ 입니다.

- candidates_for_review.csv: CAS/SMILES, PubChem 근거, 검토할 법령 근거/정답을 기록할 빈 칸
- mixture_research_gaps.csv: 실제 확인된 혼합물 CAS 후보가 부족한 규제항목 목록
- collection_summary.json: 단계별 수집 건수, 네트워크 사용량 및 오류 목록
- pubchem_http_cache/: PubChem 원본 API 응답 캐시 (재실행 시 불필요한 요청 감소)

## C. 자동으로 수집하는 물질의 종류

1. **규제목록에 이미 명시된 CAS**: 기존 검증자료에 없는 CAS 중 CAS/CID가 PubChem에서 확인된 물질
2. **원물질과 관련 염류**: 9개 원물질의 염류 명칭을 PubChem에서 검색하는 후보 탐색
3. **화학구조가 유사한 물질**: PubChem 2D 구조 유사성 검색으로 난이도 높은 후보 확보
4. **혼합물**: 등록된 공식 혼합물 CAS가 있는 경우만 후보 수집. 구성성분을 임의로 바꾸어 실재하지 않는 혼합물을 생성하지 않음

PubChem 동의어에 포함된 새 CAS는 해당 CAS로 PubChem CID를 재조회하여 일치 여부를 추가 확인합니다. 이는 PubChem 내부의 교차확인으로, 독립적인 CAS 신원 보증이나 법적 규제대상 확인은 아닙니다.

PubChem은 화학물질 정보를 제공할 뿐 법령상의 포함 여부를 확정하지 않습니다.
모든 후보는 gold_status=REVIEW_PENDING, reviewer1_status=PENDING으로 저장합니다.
**발견된 후보 수 = 정답이 검증된 신규 물질 수가 아닙니다.**

## D. 후속 연구에서 꼭 지킬 점

- 고시의 해당 개정판과 규제범위, CAS/SMILES 출처를 확인하고 연구자가 최종 정답을 확정합니다.
- 29개 규제항목 중 정확히 어느 항목인지 확인해야 하며, NOT_FOUND는 해당 29개 항목에 한정된 판정입니다.
- 물질의 정체가 모호하거나 규제항목의 범위가 불분명하면 검토 대기 상태로 남깁니다.
- candidates_for_review.csv에는 사람을 위한 **물질명과 규제항목 힌트**가 있습니다. 이 파일을 그대로 LLM 평가에 입력하면 정보 누출이 발생하므로 금지합니다.
- 구조 유사성 검색으로 뽑은 후보는 일반 화학물질의 무작위 대표 표본이 아닙니다. 선정 편향을 논문에 명시합니다.
- 실제 신규 수집 수는 PubChem 데이터 및 CAS 가용성에 따라 달라집니다. max_candidates=60은 최대 수집 건수이고 60건 확보를 보장하지 않습니다.
- 새 연구에서는 Hybrid를 제외하고 모델별 정확도와 반복 판정 일관성을 평가합니다.

PubChem API 공식 문서: https://pubchem.ncbi.nlm.nih.gov/docs/pug-rest
