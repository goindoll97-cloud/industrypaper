# RTX 2060 (전용 VRAM 6GB) — Qwen 3세대 1~2시간 목표 실험

## 이 패키지로 무엇을 테스트하나?

연구 질문: **동일 Qwen 계열의 세대가 발전할수록 2026-5호 지정고시의 명시적 CAS 식별 및 함량기준 판정 정확도가 달라지는가?**

- H1. 이후 세대의 핵심 7필드 동시 정답률이 더 높은가?
- H2. 사전 난이도 **HARD** 문항에서의 성능 향상이 **EASY**보다 큰가?
- H3. 함량기준 **바로 아래**와 **정확히 동일**한 문항에서 오류 패턴이 달라지는가?

**필수 연구 한계:** 이 데이터셋의 미등재는 *별표에서 명시된 CAS 번호가 없음*을 뜻합니다. 포괄 규제항목까지 법적으로 비규제임을 확정한 결과가 아닙니다. 모델이 보는 자료는 공식 별표 전체가 아니라 **문항당 동일하게 12개로 구성한 검색 후보행**이므로, 전체 법령 검색 능력이나 실제 화학물질 규제 준수성을 평가하는 실험이라고 주장할 수 없습니다.

## 규모 및 예상시간

| 항목 | 구성 |
|---|---|
| GPU | NVIDIA RTX 2060, **전용 VRAM 6GB** |
| 모델 | `qwen2.5:3b`, `qwen3:4b-instruct`, `qwen3.5:4b` |
| 물질 | 36종 (6개 평가층 × 각 6종) |
| 난이도 | 평가층별 EASY 3종 + HARD 3종 |
| 문항 | 물질당 2개 함량, 총 72개 |
| 전체 추론 | **72 × 3 = 216회** (예비실험 18회 포함) |
| 반복성 평가 | 별도 반복 없음. 본 패키지는 탐색적 세대 비교용 |

평균 추론 15초라면 약 54분, 20초라면 약 72분, 30초라면 약 108분입니다. **다운로드·첫 모델 로딩·오류 재시도는 별도**입니다. 모델별 6개 예비실험을 먼저 측정하고, 실제 속도가 예상보다 느리면 **아래의 두 모델 대안**을 선택하세요. 본 패키지는 2시간 내 완료를 **보장하지 않습니다**.

## 파일 구성

```text
2026_5_Ollama_Qwen_2H_RTX2060/
  README_KO.md                # 이 설명서
  RUN_WINDOWS.ps1            # 사전검사 + 예비실험 실행
  preflight.py               # SHA/난이도 균형 검사
  run_ollama.py              # Ollama 로컬 API, 자동 중간 저장·이어 실행
  estimate_runtime.py        # 실제 예비실험 측정 기반 시간 추정
  score_results.py           # Gold 대비 채점, 모델·유형별 결과
  compare_generations.py     # 대응 비교, CAS 군집·층화 부트스트랩
  data/
    prompts_72.jsonl         # 모델이 받는 질문과 공식 후보행
    pilot_6_ids.json         # 모델당 사전검사 6문항
    manifest.json            # 선정법과 SHA256
  private/                   # 로컬에만 보관 (공개 GitHub에 업로드 금지)
    gold_72.jsonl            # 별도 ZIP에서 로컬 복사; 모델 입력 금지
    selection_audit.csv      # 선택적 로컬 검토 자료
  results/                   # 실행 후 JSONL/CSV 생성 (Git에 미포함)
  tests/
    test_offline_pipeline.py # 모의 서버 테스트. 실제 모델 성능 아님
```

모두 Python 표준 라이브러리로 실행됩니다. **공개 GitHub에는 개인 Gold 및 실행결과를 업로드하지 않았습니다. 채점하려면 별도로 전달된 ZIP의 `private/gold_72.jsonl`을 본 폴더의 `private/`에 로컬 복사해야 합니다. `private/`를 Git에 추가하지 마세요.** 데이터는 이전 균형형 120종·240문항에서 **20261118 고정 시드로 6개 유형 × 2개 난이도 × 3종 = 36종**을 선택하고, 각 CAS의 두 문항을 함께 유지했습니다. 기존 120종 데이터와 Gold는 변경하지 않았습니다.

## 1. Ollama 준비 (최초 1회)

공식 다운로드: https://ollama.com/download/windows

```powershell
ollama --version
ollama pull qwen2.5:3b
ollama pull qwen3:4b-instruct
ollama pull qwen3.5:4b
ollama list
```

Ollama는 모델을 **순차** 실행합니다. VRAM 메모리가 부족해 CPU에 일부 연산이 넘어가면 더 오래 걸릴 수 있습니다. 별도 PowerShell에서 `ollama ps`를 입력해 GPU 탑재 여부를 확인하세요.

## 2. 데이터 무결성 검사

압축해제한 실험 폴더에서 실행합니다.

```powershell
python .\preflight.py
```

Gold 없이 GitHub를 클론한 상태에서는 공개 입력 데이터의 SHA 및 36종·72문항 균형을 검사합니다. 별도 ZIP에서 `private/gold_72.jsonl`을 복사하면 Gold까지 추가 검증됩니다. `PASS: 36 CAS, 72 cases ...`가 출력되면 됩니다.

## 3. 예비실험: 모델당 6문항, 총 18회

```powershell
python .\run_ollama.py --stage pilot --model all
python .\estimate_runtime.py --budget-hours 2
ollama ps
```

예비실험에서 측정한 실제 시간이 출력됩니다. 예비 18회 응답은 **동일한 추론 조건으로** 본실험에 합쳐져 중복 호출되지 않습니다. 따라서 본실험 완료 후 총 유효 응답 수는 여전히 216개입니다.

### 시간이 허용되면 3세대 비교 (추천)

```powershell
python .\run_ollama.py --stage main --model all
python .\score_results.py  # 먼저 ZIP의 gold_72.jsonl을 private/에 복사해야 실행 가능
python .\compare_generations.py
```

### 실제 속도가 너무 느리면 2세대 비교 (시간 우선 대안)

초기 Qwen 2.5와 최신 Qwen 3.5만 실행하여 **72문항 × 2모델 = 144회**로 줄입니다. 다만 이 경우 **3단계 세대별 추세**를 검증할 수 없고 구버전과 신버전의 차이만 분석할 수 있습니다. 초기 예비실험은 3모델 모두 수행했더라도 구버전과 신버전의 6문항씩을 그대로 재사용할 수 있습니다.

```powershell
python .\run_ollama.py --stage main --model qwen2.5:3b
python .\run_ollama.py --stage main --model qwen3.5:4b
python .\score_results.py --models qwen2.5:3b qwen3.5:4b
python .\compare_generations.py --models qwen2.5:3b qwen3.5:4b
```

필요하다면 남는 시간에 Qwen 3도 추가 실행하고 위 3모델 채점 명령을 다시 사용하면 됩니다.

**분석 대상 수는 실행 속도나 정확도를 보고 일부 행만 골라 변경하지 마세요.** 미완료라면 보고서에서 표본과 결측을 명확하게 밝혀야 합니다.

## 4. 중단·재개 및 데이터 관리

- 실행 로그는 `results/qwen...__pilot.jsonl`, `...__main.jsonl`에 문항마다 **즉시 저장**됩니다.
- 명령을 다시 실행하면 성공한 문항을 건너뛰고 남은 문항부터 처리합니다.
- 실험 중 `--num-ctx`, `--num-predict`, 출력 형식 또는 모델을 바꾸면 기존 결과와 혼합하지 않도록 차단합니다. 실험 설정을 바꿔야 하면 별도의 실행 폴더에서 새 실험으로 진행하세요.
- 디폴트 `num_ctx=3072`, `num_predict=240`, `temperature=0`, `seed=20261118`, `think=false`(Qwen3 계열), JSON Schema를 적용합니다. 6GB GPU에서 문맥이 잘리거나 CPU 연산이 발생하는 경우 설정을 조정할 수 있으나, **세 모델 모두 동일 설정으로 새로운 실험**을 시작해야 합니다.
- Gold는 `private/`에 따로 보관하며 `run_ollama.py`는 이 경로를 열지 않습니다. JSON의 `reason_ko`는 자유서술이므로 문자 단위로 채점하지 않고 주요 7필드만 비교합니다.

## 5. 해석 및 논문상 주의사항

1. **36종은 탐색적 소표본입니다.** 여섯 평가유형에 EASY/HARD 3종씩밖에 없어 하위그룹 비교의 통계적 검정력은 제한적입니다. 따라서 본 실험 하나로 모델 발전의 일반적 법규 판단성능 향상을 *입증*할 수는 없습니다.
2. 7개 핵심 정답 필드의 동시 일치율(엄격 지표), 유해성 타입별 필드 정확도, 난이도별 정확도, CAS 군집을 보존한 대응 부트스트랩 95% CI를 함께 보고합니다.
3. 각 물질에 2문항이 있으므로 문항 72개가 서로 완전히 독립은 아닙니다. 통계 단위는 CAS 클러스터 36종입니다.
4. 세대별 모델 크기(3B, 4B, 4B) 및 학습자료가 다릅니다. 세대 효과와 매개변수/구조 차이를 인과적으로 분리할 수 없습니다.
5. 공개 GitHub에 Gold를 두면 평가 오염 위험이 있으므로 **실험용 Gold는 비공개로 취급**하는 것이 좋습니다.
6. 정확도와 처리시간뿐 아니라 JSON 출력실패율도 함께 보고하세요. 성능 향상 경향이 없거나 신세대가 오히려 낮은 경우도 연구 결과입니다.
7. 공식 지정 CAS를 찾은 경우 해당 행이 12개 후보 가운데 포함되어 있어, 이 실험은 **폐쇄형 근거목록에서의 정보 추출·수치 적용 시험**입니다. 범위가 제한적이므로 일부 모델의 정답률이 매우 높을 수 있습니다.

## 6. GitHub

이 GitHub 폴더에는 **실행 코드와 72개 질문 및 공개 메타데이터만** 포함합니다. Gold·선정감사·모델 응답결과는 포함하지 않습니다. 기존 제공된 실험 패키지 ZIP 안의 `private/gold_72.jsonl`을 로컬에 복사해야 채점·통계분석을 실행할 수 있습니다. 이전 공개 GitHub에 포함된 다른 Gold 파일도 평가 오염 우려가 있으므로 접근 범위를 검토해야 합니다.
