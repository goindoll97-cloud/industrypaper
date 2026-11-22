# B 조건 90문항 · 4개 모델 · 5회 반복 (현재 논문 기준)

현재 논문 결과는 **`repeat_b90.py`의 5회 반복실험**입니다. 이전 단일 실행 `run_b90.py`와 v4 A/B 실험 결과는 현재 논문 통계에 합산하지 않습니다. 실행/채점의 입력 및 소스 해시는 동결되어 있으며, 기존 코드는 재현성 때문에 유지합니다.

## 준비

Windows PowerShell에서 기존 프로젝트 폴더를 사용합니다. Ollama에 `qwen2.5:3b`, `qwen3:4b-instruct`, `qwen3.5:4b`, `qwen3.5:9b`가 설치되어 있어야 합니다.

```powershell
cd F:\framework_chemical_regul_paper
git pull origin main
cd .\llm_capability_study\expanded_b90
python .\prepare_provisional_b90.py --check
```

위 검사는 로컬 `private/provisional_b90/`의 잠정 정답지, 고시 1,451행 및 프로토콜 해시가 일치하는지 확인합니다. **수정 전 Gold/manifest**라서 불일치하면, 일회성으로 `python .\prepare_provisional_b90.py --apply-correction` 실행 후 `--check`를 다시 시도하십시오. 이미 올바르게 검증된 파일에는 이 조치를 반복할 필요가 없습니다. 처음 환경에서 로컬 Gold 자체가 없다면 `python .\prepare_provisional_b90.py --create`가 필요하며, v4의 비공개 원본 Gold가 필요합니다.

## 실행 및 채점

```powershell
# 90문항 × 네 모델 × 5회 실행
python .\repeat_b90.py

# 모든 원본 결과가 준비된 후에 채점
python .\repeat_b90.py --score
```

- 기본 5회(4모델 × 90문항 = 각 반복 360문항), 총 1,800개 문항 평가. 검색어 생성과 판정 각각 한 번씩 호출합니다.
- 중단된 경우 같은 명령으로 재실행하면 완료한 질문을 건너뜁니다. 서로 다른 모델을 별도 실행하려면 `--model qwen3.5:9b` 등의 옵션을 사용하십시오.
- 입력, 실행 코드 해시, Ollama 버전, 모델 digest, PC 환경이나 반복 수가 바뀌면 동일 결과 폴더에 이어 쓰지 못하도록 차단합니다.
- Temperature 0, 고정 seed 20261120, context 4096, 검색어 384·판단 900 출력토큰, 동일한 고시 검색/프롬프트. 다른 온도 조건의 실험이 아닙니다.

## 결과와 처리시간의 정의

로컬 전용 출력 폴더: `results_b90_repeated/`

- `repeat_01`부터 `repeat_05`: 모델별 원본 JSONL, 20개 파일.
- `repeat_manifest.json`, `blocks.jsonl`: 설정, 모델 digest, 장치정보 및 실행 블록 시작/종료.
- `analysis/REPEAT_REPORT_PRIVATE.md`: 모델·반복·검색/추론 단계별 정확도와 실측시간.
- `analysis/REPEAT_model_summary_PRIVATE.csv`: 5회 평균/SD/모델별 총시간과 일관성.
- `analysis/REPEAT_per_run_PRIVATE.csv`, `REPEAT_case_scores_PRIVATE.csv`, `REPEAT_component_scores_PRIVATE.csv`, `REPEAT_decision_agreement_PRIVATE.csv`, `REPEAT_subgroups_PRIVATE.csv`: 나머지 상세 분석.

문항별 task time은 **검색어 생성 LLM API 시간, 고시 검색, 최종 판단 LLM API 시간, 프롬프트/파싱 시간**의 실제 합계입니다. 파일 기록과 모델 블록 전후의 언로드는 제외하고, 각 모델 블록 첫 질문에는 모델 로딩이 포함됩니다. 별도의 block wall time에는 블록 부대시간이 포함됩니다. 사용자의 RTX 2060 6GB/Windows/Ollama 환경에 해당하는 값입니다.

## 논문용 자료

공개 [보충자료 S1–S6](../supplementary/b90_repeat5/README.md)에서 90문항/5회 실측 결과를 확인할 수 있습니다. 잠정 Gold 원본, 개별 오답, 모델 응답 및 상세 감사자료는 **GitHub에 공개하지 않습니다**. 전부 로컬 파일로 보존하십시오.

```powershell
Compress-Archive -Path .\results_b90_repeated -DestinationPath .\B90_REPEATED_RESULTS.zip -Force
```

## 디렉터리 설명

- `proposals/`: **동결된 90문항 질문·검토 파일**. 파일명에 남은 이전 작업 표기는 해시 검증과 재현성을 위해 변경하지 않습니다.
- `prepare_b90.py`, `prepare_provisional_b90.py`, `run_b90.py`, `score_b90.py`: 동결된 자료 구축·채점 의존 코드. 이 파일을 삭제하거나 변경하면 기존 실험의 무결성 검사가 실패할 수 있습니다.
- `../retrieval_v4/`: 고시 검색 및 채점에 쓰이는 **필수 내부 엔진과 입력 데이터**. 연구에서 사용한 고시·문항의 SHA 검증 때문에 유지합니다.
- `tests/`: 재현성 회귀 테스트.
- `results_b90_repeated/`, `private/`: 로컬에만 생성되며 GitHub 추적/공개 대상이 아닙니다.

**연구상 주의:** 결과는 독립 전문가 검증 전인 `CURATED_PROVISIONAL` 정답지와의 일치율입니다. 인간 업무시간 및 CAS 번호의 단순 조회만 실시한 통제군은 없습니다. 완전 자동 대체나 사람 대비 속도 향상은 실험 결과로 직접 입증할 수 없습니다.
