# 실험 v2 — 전체 2026-5호 고시 검색 + 화학적 포괄 지정범위 추론

> **기존 16개 조항을 선택지로 제공하는 실험은 폐기하지 않고 상위 폴더에 그대로 보존합니다.** 이 폴더는 새로 설계한 본실험으로, 모델에 사전에 선정한 고시 조항을 제공하지 않습니다.

## 1. 무엇을 평가하나

입력: CAS와 영어 물질명(A), 여기에 화학식/SMILES가 추가된 입력(B). Qwen 2.5 3B, Qwen 3 4B, Qwen 3.5 4B를 동일한 로컬 RTX 2060에서 비교합니다.

1. **독립된 검색 단계:** LLM은 검색 대상 물질 정보만 보고 공식 고시를 찾을 검색어 1~3개를 JSON으로 생성합니다. 고시의 정답 후보나 16개 법령 목록은 제공되지 않습니다.
2. **검색 도구:** Python 검색기는 **2026-5호 원본 별표의 전체 1,451개 행**을 SQLite로 인덱싱한 데이터베이스에서 LLM이 생성한 검색어를 실행합니다. 후보 선별·정답의 개입 없이, 동일한 문자열 유사도 및 순위결합 규칙을 모든 모델에 적용합니다. 최대 8개 실제 검색 결과를 반환합니다.
3. **독립된 판정 단계:** 동일 LLM은 반환된 고시행과 원래 물질 정보만 보고 직접 지정, 염류·포괄 포함, 명시적 제외, 비해당/증거부족을 판단합니다.
4. **채점 단계:** Gold 파일은 모델 실행 스크립트에서 읽지 않고, 별도의 로컬 채점기가 검색 recall@8, 검색 성공 조건부 판정 정확도, 최종 정답률, JSON 오류율 및 A/B 차이를 분석합니다.

**이 검색 방식은 LLM이 검색어를 생성하고 Python 검색 도구를 호출하는 통제된 1회 검색 방식입니다.** 검색 결과에 대한 재질문·자율적 웹 브라우징까지 가능한 무제한 에이전트는 아닙니다. 또한 검색 성공은 LLM의 검색어 생성 능력과 고정 검색 알고리즘의 합성 결과이므로 LLM 단독의 웹 검색 능력을 뜻하지 않습니다.

## 2. 자료·범위·정답 유의사항

- `data/official_annex_2026_5_full.csv`: 사용자가 제공한 `2026-5_(별표) 인체등유해성물질 목록(전체)(2).xlsx`의 A:J, 원본 엑셀 5~1455행의 **1,451개 항목 전체**. 원본 행번호, CAS 열, 유해성별 기준과 하위 번호, 상위 고유번호를 보존했습니다. 원본에서 비어 있는 상위 지정번호는 가장 가까운 기존 고유번호를 `parent_designation_id`로 기록합니다. CSV/manifest의 SHA256으로 무결성을 검사합니다.
- `data/official_annex_2026_5.sqlite`: 실행 전에 자동으로 생성되는 **전체 고시 검색 DB**. GitHub에는 DB의 재현 가능한 원천 CSV와 구축 코드만 업로드합니다.
- `data/cases_40.jsonl`: 기존 20종×A/B의 **물질·CAS·화학식·SMILES 입력만** 추출했습니다. 기존 프롬프트의 16개 조항은 완전히 제거했습니다. 연구자의 정답/난이도/분류 정보도 모델에 전달하지 않습니다.
- `private/gold_40.jsonl`은 이전 16개 조항 실험의 Gold입니다. **`NOT_COVERED` 4종(8문항)은 16개 조항 내 비해당으로만 검증되었으므로, 전체 1,451개 법령 대상의 확정 음성 정답으로 간주할 수 없습니다.** 새 본실험의 검색·판정 정확도에서는 이 8문항을 제외하고 별도로 표시합니다. 나머지 16종×2조건=32문항도 기존 Gold 초안이므로 전문가의 독립적 재검토를 권장합니다.
- 본 실험의 **주요 지표는 지정범위 판정**입니다. 함량기준 수치 적용, 실제 제품 혼합물의 법적 판단, 고분자/UVCB 일반화는 평가하지 않습니다.

### 지표의 해석

| 지표 | 의미 |
|---|---|
| Retrieval recall@8 | Gold가 지목한 공식 엑셀 행을 LLM의 검색어로 검색한 상위 8개 근거행 중 찾았는가? |
| Identity-only baseline recall@8 | 모델 생성 검색어 없이 CAS+물질명만으로 같은 검색기를 사용한 경우의 기준 성능 |
| Reasoning accuracy given retrieval | 정답 조항이 실제 검색된 사례에서만 판정이 정확했는가? **조건부 분석이며 독립적인 순수 추론 능력 지표는 아닙니다.** |
| End-to-end success | 정답 조항 검색 성공 **및** 화학적 범위 판정·고유번호 모두 정답 |
| A/B paired comparison | 동일 CAS에 화학식·SMILES를 추가했을 때 검색/추론이 어떻게 달라졌는가? |

검색·추론을 더 엄격하게 인과적으로 분리하려면 모든 모델에 Gold로 검증된 **동일 조항**을 제공하는 보충 진단 실험이 필요합니다. 그러나 그러한 조건은 정답 조항을 제공하기 때문에 **실제 전체 고시 검색 실험의 주평가로 사용하지 않습니다.** 본 패키지는 두 단계를 로그와 평가 지표로 구분합니다.

## 3. RTX 2060 설치 및 실행

PowerShell에서 이 폴더(`.../llm_capability_study/ollama_scope_reasoning_2h/retrieval_v2`)로 이동합니다.

```powershell
ollama pull qwen2.5:3b
ollama pull qwen3:4b-instruct
ollama pull qwen3.5:4b
python .\preflight.py
python .\search_legal_db.py "니코틴"
python .\run_retrieval.py --stage pilot --model all
python .\estimate_runtime.py --budget-minutes 120
```

예비실험은 모델당 8문항(각 4종 A/B, 총 24문항)으로 구성되며, 같은 추론 설정으로 본실험에 재사용됩니다. **문항당 2회 LLM 호출(검색어 생성 + 근거 판단)**이 발생합니다. 이전 16항목 실험의 48.6분 추정을 그대로 사용할 수 없으며, 반드시 새로운 예비실험 측정값을 기준으로 본실험 여부를 결정하세요.

```powershell
python .\run_retrieval.py --stage main --model all
python .\score_results.py
```

현재 기본 설정은 검색어 출력 125토큰, 최종 판단 출력 420토큰, `num_ctx=3072`, temperature=0, `think=false`(Qwen3 계열), JSON schema, 모델 순차 실행입니다. 220토큰 출력 잘림 문제가 있었으므로 최종 JSON 생성 제한을 420으로 상향했습니다. 결과는 문항별로 즉시 저장되며 중단 후 동일 명령으로 재개합니다.

2시간을 초과할 것으로 예상될 경우, **추론 시작 전에** `--condition B`로 20종(60개 검색/판정 쌍)을 주평가로 확정할 수 있습니다. 이 경우 A/B 구조정보 추가 효과를 논문에서 검증했다고 주장하면 안 됩니다.

```powershell
python .\run_retrieval.py --stage main --model all --condition B
python .\score_results.py
```

`--condition B`도 파일에는 기존 A/B의 조건 구분이 남고, `score_results.py`는 미실행 A를 결측으로 기록합니다. 해당 경우 B 결과만 보고해 주세요.

## 4. GitHub, 비공개 정답지 및 재현성

- 이 폴더의 `data/official_annex_2026_5_full.csv`에는 **공식 고시 전체**만 포함됩니다. 특정 시험물질에 대한 정답 매칭은 포함하지 않습니다.
- `private/`와 `results/`, `*.sqlite`는 `.gitignore`로 제외합니다. 공개 GitHub에서 `private/gold_40.jsonl`을 받을 수 없습니다. 기존 전체 실험 ZIP의 `private/gold_40.jsonl`을 로컬의 이 폴더 `private/`에 복사해야 정확도 채점이 가능합니다.
- `run_retrieval.py`는 Gold를 가져오거나 읽지 않습니다. `score_results.py`만 로컬 Gold를 읽습니다.
- 모든 호출의 모델 버전(digest), 검색어 원문, DB에서 반환된 고시행, JSON 원문, 시간, 출력 토큰 수를 `results/`에 저장합니다.
- 연구자가 실험 결과를 확인한 뒤 물질 일부를 제거하거나 검색 알고리즘·프롬프트를 바꾸어 같은 시험이라고 보고하면 안 됩니다. 변경 시 새 버전의 실험으로 기록해야 합니다.

## 5. 파일 구조

```text
retrieval_v2/
  README_KO.md
  build_legal_db.py
  search_legal_db.py
  run_retrieval.py
  preflight.py
  estimate_runtime.py
  score_results.py
  data/
    official_annex_2026_5_full.csv     # 1451행 전체 검색 소스
    cases_40.jsonl                    # CAS/물질명/(화학식/SMILES)만 포함
    pilot_8_ids.json
    manifest.json
    official_annex_2026_5.sqlite      # 실행 시 생성, Git 제외
  private/gold_40.jsonl               # 로컬만, Git 제외
  results/                            # 모델 응답/분석, Git 제외
  tests/test_offline.py
  .gitignore
```

출처: 2026-5호 원본 별표 엑셀(사용자가 제공), 기존 `ollama_scope_reasoning_2h` 검증셋의 물질정체 정보. 코드/검색 알고리즘은 이번 실험을 위해 신규 구축했습니다.
