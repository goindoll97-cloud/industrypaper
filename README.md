# 2026-5호 화학물질 지정고시 기반 소형 LLM 연구

## 논문 작업은 아래 페이지 하나에서 시작하세요.

**[논문 방법론·현재 결과·실행코드 통합 안내](llm_capability_study/README.md)**

- 논문용 결과표 생성: `llm_capability_study/make_paper_report.py`
- 핵심 실험 코드: `llm_capability_study/retrieval_v4/run_retrieval.py`
- 정답 채점: `llm_capability_study/retrieval_v4/score_results.py`

나머지는 재현성을 위한 보조 코드와 이전 버전입니다. 실험 자료를 지우거나 새 실험을 수행할 필요는 없습니다.

**[후속 B 조건 90문항 확대 실험 준비·실행 안내](llm_capability_study/expanded_b90/README.md)** — 기존 30개 B 문항에 60개 신규 화학물질 규제 상황의 CAS·분자식·가상 혼합물 조성을 갖춘 **후보 초안은 작성했고**, 화학물질 정보와 전문가 Gold는 검증·동결 전입니다.

**[총 90개 B 질문 후보 파일 확인](llm_capability_study/expanded_b90/proposals/README.md)** — 기존 B 30문항 보존, 신규 60문항의 실제 CAS·명칭·분자식·혼합물 함량을 포함한 제안 자료.

**데이터 보호:** Gold 정답지(`private/`), 모델 원본 응답(`results_v4_1/`)은 로컬에만 보관합니다. 공개 저장소에 정답지 원문이나 원본 응답을 업로드하지 마세요. Gold는 아직 독립 법령 전문가 검증 전 잠정판정입니다.
