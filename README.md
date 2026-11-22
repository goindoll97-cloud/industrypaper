# 화학물질 규제 확인 업무의 LLM 수행 가능성 연구

**현재 논문 기준: 화학물질안전원고시 제2026-5호, B 조건 90문항, 4개 Qwen 모델, 각 5회 반복.**

CAS 번호의 단순 대조만으로 판단하기 어려운 포괄 지정·제외 조건을 포함하여, LLM이 화학물질 규제 확인 업무를 어디까지 수행할 수 있는지 **정확성·동일 설정 재현성·실제 처리시간**을 평가합니다.

- [논문용 연구 개요 및 결과](llm_capability_study/README.md)
- [최신 보충자료 S1–S6 (공개 집계표)](llm_capability_study/supplementary/b90_repeat5/README.md)
- [90문항 실행·채점과 환경](llm_capability_study/expanded_b90/README.md)
- [반복실험 실행 코드](llm_capability_study/expanded_b90/repeat_b90.py)

**핵심 수치:** 모델당 90문항 × 5회. 완전정답률 0.00%, 58.89%, 48.89%, 55.56% (Qwen2.5 3B, Qwen3 4B, Qwen3.5 4B, Qwen3.5 9B). 모델별 90문항 평균 처리시간 5.37, 10.95, 9.45, 46.20분 (RTX 2060 6GB 기반).

**중요:** 전문가 독립 검증 전인 잠정 Gold에 대한 일치율입니다. 최종 법적 판단, 업무 완전 대체, 사람 대비 시간 절약률을 입증한 결과가 아닙니다. 개인 연구 자료인 Gold, 상세 모델 응답 및 성분별 감사자료는 공개하지 않습니다.

이전 연구 파일은 메인 브랜치에서 정리했습니다. 정리 전 저장소 상태는 [보존 브랜치](https://github.com/goindoll97-cloud/industrypaper/tree/archive/pre-b90-cleanup-20261122)에 유지되어 복구할 수 있습니다.
