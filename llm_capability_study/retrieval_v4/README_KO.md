# B90 논문용 내부 검색·채점 엔진 (동결된 의존 폴더)

이 디렉터리의 코드와 자료는 현재 논문 기준인 [B 조건 90문항 × 네 모델 × 5회 반복](../expanded_b90/README.md)에서 불러옵니다.

- `run_retrieval.py`: Ollama 요청, 프롬프트, JSON 검증.
- `search_legal_db.py`: 2026-5호 고시 1,451행의 근거 검색.
- `build_legal_db.py`, `data/`: 고시 원본 검색 DB 및 SHA 검증.
- `score_audit_v4.py`, `diagnose_raw_failures.py`: 문항/성분별 결과 산정.
- `gold_integrity.py`, `data/cases_60.jsonl`, `data/manifest.json`: B90 생성 원천자료의 동결 해시 검증에 필요.
- `tests/`: 실행 전/후 무결성·채점 검증.

이 폴더의 이전 A/B 실험은 **현 논문 분석 대상이 아니며**, 기존 소스의 SHA가 새 실험 manifest에 기록되어 있으므로 파일을 이름 변경·삭제·수정하지 마십시오. 이 디렉터리 아래의 `results_*`와 `private/`는 로컬 비공개 결과입니다.
