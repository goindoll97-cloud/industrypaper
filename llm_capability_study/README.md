# 논문 작업용 — 이 문서만 보세요

2026-5호 인체급성·만성·생태유해성물질 지정고시의 **소형 Qwen LLM 법령 검색·지정범위 판정 실험**입니다. 원래 실험 코드와 자료를 유지하면서, 논문 작성에 필요한 실행법·방법론·결과를 **한 페이지**로 정리했습니다.

## 2026-11-20 추가 비교: Qwen3.5 9B

**목적:** 더 큰 모델에서는 규제정보 검색과 복잡한 지정범위 판단의 오류가 줄어드는지 동일한 v4.1 조건에서 확인합니다. 기존 세 모델은 재실행하지 않습니다. 정답지·프롬프트·검색 결과 수·채점 기준은 그대로 유지합니다.

**모델 선택:** 공식 Ollama 모델 `qwen3.5:9b` (다운로드 약 6.6GB). RTX 2060 6GB에서는 GPU 메모리를 초과해 일반 RAM 일부를 사용할 수 있어 느릴 수 있습니다. RAM에 여유가 있어야 하며, 이 모델이 모든 LLM 중 가장 성능이 좋다는 뜻은 아닙니다.

PowerShell 명령어 (아래 순서대로):

~~~powershell
cd F:\framework_chemical_regul_paper
git pull origin main
cd .\llm_capability_study\retrieval_v4
ollama pull qwen3.5:9b
python .\preflight.py --fix-windows-eol
python .\preflight.py
# 먼저 예비 12문항으로 실행·JSON·속도 확인 (본실험에서 재사용됨)
python .\run_retrieval.py --stage pilot --model qwen3.5:9b --results-dir results_v4_1_strong
# 예비시험이 정상이면 동일한 설정으로 60문항 실행
python .\run_retrieval.py --stage main --model qwen3.5:9b --results-dir results_v4_1_strong
# 새 모델만 분리 채점
python .\score_results.py --results-dir results_v4_1_strong --models qwen3.5:9b
# 원래 3개 모델 + 9B 모델 비교를 기존 논문용 한 파일로 생성
python ..\make_paper_report.py --strong-results-dir results_v4_1_strong
~~~

최종 비교 표 위치: `retrieval_v4/results_v4_1/PAPER_RESULTS_v4_1.md` (한 개). 기존 원본 데이터는 그대로 유지합니다. 추가 모델 원본은 `retrieval_v4/results_v4_1_strong/`에만 저장됩니다.

**Windows 무결성 참고:** 세 입력 데이터의 해시가 줄바꿈(CRLF) 때문에 달라졌다면 `--fix-windows-eol`이 **LF 변환 후 공식 SHA256이 정확히 일치하는 파일만** 복구합니다. 줄바꿈 이외의 차이가 있으면 파일을 수정하지 않고 중단합니다. GitHub에 정답지·실험 결과가 올라가지 않도록 `results_v4_1_strong/`도 Git에서 제외했습니다.

**주의:** 예비 단계에서 API 오류가 발생했다면 RAM/모델 로딩 문제를 먼저 해결한 뒤 같은 명령으로 이어서 실행하세요. GPU와 RAM 사용량은 `ollama ps`로 확인할 수 있습니다. `--force`는 기존 실행파일 삭제 옵션이므로 사용하지 마세요. 9B 평가 또한 기존 30원사례를 재사용하므로 독립 외부 검증은 아니며, Gold의 전문가 독립 검토는 여전히 필요합니다.

---

## 1. 일상적으로 필요한 파일 3개

| 작업 | 사용할 파일 | 역할 |
|---|---|---|
| 논문용 표 생성 | [make_paper_report.py](make_paper_report.py) | **이미 끝난 v4.1 결과를 하나의 Markdown 요약 파일로 변환** |
| 실제 LLM 본실험 | [retrieval_v4/run_retrieval.py](retrieval_v4/run_retrieval.py) | 성분별 검색어 생성, 고시 검색, JSON 법령 판단 |
| 정답 비교 | [retrieval_v4/score_results.py](retrieval_v4/score_results.py) | 검색·완전정답·End-to-end 채점 |

**그 외 파일은 직접 열어볼 필요가 없습니다.** 법령 검색기, 정답지 무결성, 오류 상세 분석, 테스트는 위 코드에서 사용하거나 연구 재현성을 위해 보존한 **보조 파일**입니다. 이전 연구는 `retrieval_v3/`와 저장소의 `archive/`에 보존돼 있습니다.

## 2. 현재 결과로 논문용 요약 1개 생성

PowerShell에서 **아래 명령어만** 실행하세요.

~~~powershell
cd F:\framework_chemical_regul_paper
git pull origin main
cd .\llm_capability_study\retrieval_v4
python ..\make_paper_report.py
~~~

결과는 `retrieval_v4/results_v4_1/PAPER_RESULTS_v4_1.md` **한 파일**로 생성됩니다. 신규 LLM 호출이 없고, 기존 `__main.jsonl`, Gold, 채점 CSV는 변경하지 않습니다. 수정 Gold와 해당 v4.1 실행 설정의 SHA256을 확인한 후에만 결과를 생성합니다.

> 로컬의 `private/gold_60.jsonl` 및 `results_v4_1/`이 있어야 합니다. 정답지와 원본 모델 출력은 **GitHub에 공개하지 않습니다.**

## 3. 학술논문 Methods에 기술할 핵심

**자료 및 평가셋.** 2026-5호 고시의 별표 전체 1,451행을 검색 대상으로 사용했습니다. 평가 유형은 (i) 모체·염류, (ii) 화합물군, (iii) 2~3성분 가상 혼합물입니다. 유형별 10사례(EASY 5, HARD 5), 총 **30개 원사례**에 A/B 대응 조건을 적용하여 모델당 60문항을 구성했습니다. A/B 문항을 독립된 60개 화학물질 표본으로 취급하지 않습니다.

**입력 조건.** A는 CAS와 영문 물질명(혼합물에는 성분별 함량 포함), B는 이용 가능하고 검증 가능한 분자식 및 일부 구조정보를 추가합니다. SMILES의 효과만 독립적으로 평가한 실험은 아닙니다.

**모델 및 추론 설정.** Qwen2.5 3B, Qwen3 4B Instruct, Qwen3.5 4B를 Ollama에서 비교했습니다. Temperature 0, seed 20261120, 문맥창 4,096토큰을 사용했고, Qwen3 계열은 non-thinking 설정입니다. 현재 **v4.1** 검색어·최종 응답 출력 상한은 384/900토큰입니다.

**2단계 검색·판단 파이프라인.**

1. LLM이 성분별 검색어 1~3개 생성
2. 공식 고시 전체를 대상으로 어휘 검색 및 점수 융합 수행(CAS 번호 접두어 정규화 포함)
3. 검색된 고시 행을 근거로 성분별 직접 CAS 지정, 지정범위, 관계 유형, 지정번호·소번호를 JSON으로 판정
4. 비공개 잠정 Gold와 비교해 단계별 성공과 엄격한 완전정답을 평가

검색 결과 수는 **단일물질 8행/성분, 2성분 혼합물 5행/성분, 3성분 혼합물 4행/성분**으로 서로 다릅니다. 이 값들을 동일한 `Recall@8`로 표기하면 안 됩니다.

**평가지표.** (i) 검색어·최종 JSON 유효율, (ii) 모든 성분의 정확한 Gold 고시행 검색 성공, (iii) 지정범위 `covered_by_clause` 일치, (iv) 관계 유형·지정번호·소번호 등을 포함한 엄격한 완전정답, (v) 엄격한 완전정답과 Gold 근거행 검색을 모두 만족한 End-to-end 성공을 구분했습니다. 혼합물은 고시 제3조의 모든 성분 지정 여부를 별도 검증하며, 제품 전체의 규제 적법성은 판단하지 않았습니다.

**재현 가능한 핵심 코드:** 사례 구성 `retrieval_v4/data/cases_60.jsonl`, 고시 검색 `retrieval_v4/search_legal_db.py`, 모델 실행 `retrieval_v4/run_retrieval.py`, 기본 채점 `retrieval_v4/score_results.py`. 보조 분석 `retrieval_v4/score_audit_v4.py`와 `retrieval_v4/diagnose_raw_failures.py`는 논문의 추가 분석에만 필요합니다.

## 4. v4.1 결과 (모델당 60문항)

| 지표 | Qwen2.5 3B | Qwen3 4B | Qwen3.5 4B |
|---|---:|---:|---:|
| 검색어 유효 | 51/60 (85.0%) | 57/60 (95.0%) | 60/60 (100%) |
| 최종 JSON 유효 | 60/60 (100%) | 51/60 (85.0%) | 60/60 (100%) |
| Gold 근거행 전체 검색 | 32/60 (53.3%) | 34/60 (56.7%) | 40/60 (66.7%) |
| 지정범위 및 혼합물 제3조 판단 일치 | 8/60 (13.3%) | 24/60 (40.0%) | 38/60 (63.3%) |
| 엄격한 완전정답 | 0/60 (0%) | 17/60 (28.3%) | 17/60 (28.3%) |
| End-to-end 성공 | 0/60 (0%) | 17/60 (28.3%) | 17/60 (28.3%) |

관계 유형과 지정범위 필드의 **논리적 모순**은 Qwen2.5 0/84, Qwen3 2/73(2.7%), Qwen3.5 38/85(44.7%)였습니다(분모는 검사 가능한 성분 수). Qwen2.5는 전체 성분에 대해 비지정 판단을 반복했으므로, 모순 0건이 좋은 성능을 의미하지 않습니다.

기존 **v4** End-to-end 성공은 Qwen2.5 **0/60**, Qwen3 **4/60**, Qwen3.5 **5/60**이었습니다. **v4.1은 출력 형식·검색 로직을 변경한 별도 프로토콜**이며 모델 자체가 향상됐다는 인과적 결론을 내릴 수 없습니다.

## 5. 논문에 명시할 한계

- Gold는 2026-11-20 수정본(SHA256 `ed817e989ec828c767fb09d39d9d912030a661b82b7b054250c8146167055c50`)을 사용한 **잠정 정답**이며, 독립 법령 전문가 검토가 완료되지 않았습니다.
- 근거 검색은 Gold의 지정된 **원본 고시행**을 찾았을 때만 성공으로 계산했습니다. 같은 지정번호의 다른 행은 자동 정답으로 인정하지 않았습니다.
- 30개 사례와 A/B 대응 설계로 인해 일반적인 모든 화학물질·고시로의 일반화에 제한이 있습니다.
- Qwen3.5의 필드 간 모순, Qwen2.5의 과도한 `NOT_COVERED` 경향은 보조 오류 분석 결과이며, 사후에 Gold·프롬프트를 변경해 기존 점수를 높이지 않았습니다.

**현재 원칙:** 본실험 v4.1과 정답지는 동결하고, 논문에는 위 방법론과 단계별 결과를 중심으로 기술합니다. 추가 프로토콜 변경 실험은 별도 버전으로 수행합니다.
