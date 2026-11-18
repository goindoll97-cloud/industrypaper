# 화학물질 LLM 규제판정 연구 — 2026-5호

이 저장소는 **현재 진행 중인 논문 실험**을 최상위에서 관리하며, 이전 Claude/Hybrid 실험은 `archive/previous_claude_experiment/`에 보존합니다.

## 연구 목적
화학물질안전원고시 제2026-5호 인체급성·인체만성·생태유해성물질 지정 별표를 공통 참고자료로 제공하고, LLM의 **물질 식별·고유번호·유해성 유형·가상 함량기준 판정 정확도와 반복 일관성**을 비교합니다.

이 평가의 결과는 **고시상 지정물질 해당 여부**이지, 제조·수입·판매 행위의 개별 법규 위반 여부가 아닙니다.

## 폴더 구성

```text
industrypaper/
├── README.md                      # 현행 연구 안내
├── EXPERIMENT_SCOPE_ko.md         # 현행 실험 범위
├── DATA_FILES_MANIFEST.json
├── llm_capability_study/          # ★ 현재 논문 연구의 기존 작업 폴더 (최상위로 복원)
│   ├── README.md
│   ├── candidates/               # 후보 선정 및 법령 원문 대조 기록
│   ├── validation_dataset/       # 앞 단계의 29개 카탈로그 검증셋 초안
│   ├── tests/
│   └── *.py                      # 이전 단계의 검토·구축 도구
├── data/                          # 2026-5호 실험 입력과 정답지
├── reference/                     # 2026-5호 공식 별표
├── scripts/                       # 2026-5호 함량 판정 LLM 실행·채점 코드 (추가 예정)
├── results/                       # 2026-5호 모델 결과
└── archive/
    └── previous_claude_experiment/
        ├── 04_run_retrieval_llm_hybrid.py
        ├── intermediate/         # 예전 Claude 응답·채점 결과
        ├── figures/              # 예전 그림
        └── ...                   # 과거 코드, frozen 112건, 설정
```

## 작업 단계와 주의
- `llm_capability_study/`는 **현재 논문을 위해 29개 항목으로 검증셋을 확장·점검하던 폴더**입니다. 이전 Claude 실험의 일부로 처리하면 안 됩니다.
- 다만 그 폴더의 `build_validation_dataset.py` 등은 **이전 단계의 29개 항목 검색 문제**를 대상으로 작성됐습니다. **2026-5호 전체 고시 + 가상 함량 실험에 그대로 실행하면 안 됩니다.** 새 입력·정답 스키마를 적용하는 코드가 필요합니다.
- 새 실험의 계획은 **300개 물질 × 4개 가상 함량 = 1,200개 질의**이며, 동일 물질 내 반복 질의는 통계적으로 독립 사례가 아닙니다.
- 새 엑셀 두 개와 원본 고시 파일은 아직 GitHub에 커밋되지 않았습니다. `data/README.md`, `reference/README.md`를 참고하여 업로드해야 실제 실행이 가능합니다.
- 이전 Claude 성능값은 **이번 연구의 모델 비교 결과에 포함하지 않습니다.**
