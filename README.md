# Chemical Regulatory Identification with Large Language Models

**연구 진행 상태: LLM 성능 수준별 비교 및 규제대상 식별 검증자료 확대 (2026-11-17)**

이 저장소는 화학물질의 CAS 번호·화학구조와 규제범위 정보를 바탕으로 규제대상 해당 여부를 판정하는 LLM 연구자료 및 실험 코드를 보관합니다.

## 현재 진행 중인 연구

### 연구 주제

**LLM의 성능 향상이 화학물질 규제대상 식별의 정확성과 반복 판정 일관성을 얼마나 개선하는가?**

모델의 능력이 향상되어도 염류, 화학물질군, 혼합물, 규제범위 경계 사례에서 지속적으로 발생하는 오류가 있는지 검증합니다. 이번 연구는 **LLM 단독 모델들의 성능 수준 및 반복평가 결과**를 비교하며 Hybrid 방식은 주된 비교에서 제외합니다.

> **[연구 방향, 연구질문, 가설, 데이터셋 구축 및 평가계획 전체 보기](llm_capability_study/README.md)**

### 현재 자료

| 항목 | 내용 |
| --- | --- |
| 고정 규제목록 | 29개 규제항목 |
| 기존 검증자료 | 112건 (Gold 확보, 기존 Claude 결과와 비교 가능) |
| 신규 PubChem 수집물질 | 87건 (**전부 REVIEW_PENDING**, Gold 미확정) |
| 확보 사례/후보 합계 | 199건 (정답 검증 완료 199건을 뜻하지 않음) |
| 검증자료 목표 | 잠정 300~400건, 법령·화학정보 검증과 통계설계에 따라 결정 |
| 현재 우선작업 | 신규 후보의 법적 범위 정답 검토, 혼합물·경계 사례 추가 확보 |

신규 물질은 규제목록 직접 등재(20건), 규제목록 주변(27건), 규제목록과 **독립적으로 선정한 일반 화학물질**(40건)로 수집했습니다. 이 구분은 검색 출처이며 규제대상 해당/비해당를 나타내지 않습니다.

### 중요한 연구 범위

본 연구가 검증하는 것은 **정해진 규제목록에 대한 식별 성능**입니다. 법률에 규정이 없는 '입법적 공백'을 LLM이 채울 수 있다는 주장이나, LLM 판단이 공식 법적 해석을 대체한다는 주장이 아닙니다.

## 바로가기

| 경로 | 내용 |
| --- | --- |
| [llm_capability_study/README.md](llm_capability_study/README.md) | **새 논문의 방향성과 단계별 연구계획 (주 문서)** |
| [llm_capability_study/PROTOCOL.md](llm_capability_study/PROTOCOL.md) | Gold 확인, 표본 선정, 모델·반복평가 프로토콜 |
| [llm_capability_study/PUBCHEM_COLLECTION_GUIDE_ko.md](llm_capability_study/PUBCHEM_COLLECTION_GUIDE_ko.md) | PubChem 수집기 사용법 |
| [llm_capability_study/collect_pubchem_candidates.py](llm_capability_study/collect_pubchem_candidates.py) | 규제목록·유사물질·독립 일반 화학물질 후보 수집 |
| [llm_capability_study/new_cases_template.csv](llm_capability_study/new_cases_template.csv) | 신규 후보 법적 정답 검토 양식 |
| [data/regulatory_catalog.csv](data/regulatory_catalog.csv) | 고정된 29개 규제대상 목록 |
| [data/retrieval_INPUT.csv](data/retrieval_INPUT.csv) | 기존 112건 입력자료 |
| [data/retrieval_GOLD.csv](data/retrieval_GOLD.csv) | 기존 112건 Gold |
| [ollama_followup/README.md](ollama_followup/README.md) | **별도 보존 중인 과거 Claude/Hybrid 후속 실험** |

## 다음 작업 순서

1. 기존 112건은 변경하지 않고, 신규 87건의 CAS/SMILES 및 규제범위 근거를 독립적으로 검토합니다.
2. 혼합물·규제범위 경계 사례·독립 일반 화학물질 등 부족한 유형을 추가 수집하고 Gold를 확정합니다.
3. 검증자료를 버전 고정한 다음, 여러 성능 수준의 LLM에 동일한 규제목록과 프롬프트를 제공해 물질별 5회 이상 반복 평가합니다.
4. 정확한 규제 target ID 식별, 대상 재현율, 비대상 특이도, 잘못된 규제포함/누락 및 반복 일관성을 비교합니다.
5. 모델 성능 향상으로 개선되는 부분과 반복적으로 남는 오류를 구분하여 결과를 해석합니다.

연구가 진행되면 **[새 연구의 상세 README](llm_capability_study/README.md)**를 기준으로 버전별 실험조건과 의사결정을 업데이트합니다.
