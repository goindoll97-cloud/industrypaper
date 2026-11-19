# 최신 본실험: 전체 고시 검색 + 화학적 포괄 지정범위 추론 (retrieval_v2)

> **새 본실험은 [`retrieval_v2/README_KO.md`](retrieval_v2/README_KO.md)를 사용하세요.** LLM이 검색어를 만들고 전체 1,451행 법규 DB를 검색한 다음 관련 조항을 해석합니다. 아래 기존 설명과 `run_ollama.py`는 **16개 조항 제공 방식의 이전 실험(legacy)** 으로 보존되어 있습니다. 새 실험은 `retrieval_v2/run_retrieval.py`로 실행합니다. Gold는 비공개로 유지합니다.

---

# 화학적 정체·구조정보 기반 2026-5호 포괄 지정범위 판정 실험 — RTX 2060 6GB

## 연구 목적
CAS 직접 일치에 의존하지 않고 **염류 및 무기물질군 포함·직접 세부항목 우선·명시적 예외·비해당 인접물질**을 판별하는 능력이 Qwen 2.5/3/3.5 세대에 따라 달라지는지 비교한다. 여기에 **화학식/SMILES를 추가하면 판단 성능이 개선되는지**를 같은 물질의 A/B 대응 설계로 비교한다.

이 버전은 **20종 × 조건 2개 × 모델 3개 = 총 120회 추론**이다. 기존 72문항/216회 계획보다 44.4% 적은 추론 횟수다. 이전 측정 예상(216회에 114분)만 단순 적용하면 약 63분이나, 프롬프트·출력 길이 변화로 실제 실행시간은 달라진다.

## 실험 범위의 엄격한 한계

1. **2026-5호 공식 별표 전체에 대한 자유 검색이 아니다.** 원본 별표 중 명시적으로 발췌한 **16개 지정행**을 모든 문항에 동일하게 제공한다. 
2. `NOT_COVERED`는 **제공된 16개 조항의 범위에서 해당하지 않는다는 뜻**이지 한국 전체 법규의 비규제/안전/합법 판정이 아니다.
3. 포괄 지정에 의한 법적 포함 여부와 혼합물의 함량기준 적용은 별개의 과제다. 이 시험은 **지정 범위 식별까지만** 평가한다.
4. 단일 분자식이나 SMILES로 완전한 정보를 나타내기 어려운 **고분자·UVCB·미정 구조 반응생성물은 아직 검증셋에 포함하지 않았다**. 그 유형에 대해 검증하지 않았다고 보고해야 한다.
5. 표본 20종, 유형당 쉬움/어려움 각 2종인 **탐색적 실험**이다. 전체 법적 적용에 대한 확정적 결론이나 모든 LLM에 대한 일반화는 불가능하다.
6. 화학식·SMILES는 사용자 입력 구조단서이고, CAS 정체/연결성 정보의 근거는 Gold의 PubChem URL에서 확인한다. Gold의 SMILES는 **RDKit 분자식 대조를 통과한 대표 연결성 표기**이지 PubChem canonical SMILES 원문을 그대로 전사한 것이 아니다.
7. Gold는 연구용 판정 초안으로 **화학적·법률적 전문가 2인의 독립 검토를 거친 법적 공식 유권해석을 대체하지 않는다.** 사례별 근거와 제외 기준을 Gold에 함께 보존한다.

## 실험 입력 두 조건 (같은 20 CAS에 각각 적용)

- **A:** CAS + 영문 물질명 + 고시 발췌 16개 지정행.
- **B:** A와 동일하지만 **분자식과 구조정보(가능한 경우 SMILES)**를 추가한다.
- 두 조건에서 동일한 지정행을 제공하며, `DIRECT_SPECIFIC`, `GROUP_INCLUDED`, `EXPLICIT_EXCEPTION`, `NOT_COVERED` 중 하나로 분류한다.
- Gold에 기재된 `expected_relation`, `relevant_entry_id`, `relevant_sub_number` 등은 절대 모델에 제공하지 않는다.

## 유형별 구성

| 평가유형 | 물질 수 | 쉬움 | 어려움 |
|---|---:|---:|---:|
| 유기물질의 염류 포괄 포함 | 4 | 2 | 2 |
| 무기염/금속염 포괄 포함 | 4 | 2 | 2 |
| 명시 CAS/세부번호 직접 지정 | 4 | 2 | 2 |
| 조항에서 명시적으로 제외 | 4 | 2 | 2 |
| 화학적으로 유사하지만 제공 조항 비해당 | 4 | 2 | 2 |
| **합계** | **20** | **10** | **10** |

난이도는 **사전 내용·관계 복잡도에 대한 연구자 구분**이며 실제 LLM 성능을 보고 정하지 않았다.

## 파일 구조

```text
ollama_scope_reasoning_2h/
  README_KO.md
  run_ollama.py
  preflight.py
  estimate_runtime.py
  score_results.py
  RUN_WINDOWS.ps1
  data/
    prompts_40.jsonl
    pilot_8_ids.json
    manifest.json
    legal_clauses_16.json
    2026_5_scope_Validation_Set_40.xlsx
  private/                  (공개 GitHub 업로드 금지)
    gold_40.jsonl
    2026_5_scope_GOLD_Answer_Key_40.xlsx
    chemical_identity_audit.csv
  results/                  (GitHub 업로드 금지)
```

## Windows PowerShell 실행

Ollama 설치: https://ollama.com/download/windows

```powershell
ollama pull qwen2.5:3b
ollama pull qwen3:4b-instruct
ollama pull qwen3.5:4b

cd D:\framework_chemical_regul_paper\llm_capability_study\ollama_scope_reasoning_2h
python .\preflight.py
python .\run_ollama.py --stage pilot --model all
python .\estimate_runtime.py --budget-minutes 120
```

Pilot은 4물질의 A/B 문제, **모델당 8건·전체 24건**으로 구성된다. Pilot은 동일 설정의 본실험에 재사용되므로 중복 호출되지 않는다. 예측시간이 120분에 가까우면 두 모델 비교로 줄일 수 있지만, 주분석의 모델 수 변경을 실험 시작 전에 명시하고 모든 문항을 유지해야 한다.

```powershell
python .\run_ollama.py --stage main --model all
python .\score_results.py
```

결과는 `results/`에 저장되며, 중단되면 같은 명령으로 이어서 실행한다. `score_results.py`는 **로컬에 저장된 `private/gold_40.jsonl`만** 읽어 채점한다. `run_ollama.py`는 Gold 파일을 절대로 읽지 않는다.

### 재현성 조건

- Temperature=0, seed=20261119, `num_ctx=3072`, `num_predict=220`, JSON schema
- Qwen3 계열에서는 `think=false` 전달
- 각 모델 한 번에 하나만 호출, 추론 완료 후 GPU에서 언로드
- 프롬프트 및 Gold SHA256을 `data/manifest.json`에 고정
- API 응답 원문, 추론 소요시간, 모델 digest, JSON 출력 성공 여부 기록
- API 오류와 JSON 출력 실패도 성능 평가에 반영

## 논문 분석 및 주의

- 1차 지표는 `covered_by_clause`의 판단 정확도와 `reasoning_category` 4분류 정확도, 핵심 5필드 동시 정답률이다.
- 동일 CAS의 A/B 응답은 독립 표본이 아니므로, **CAS 단위 대응 비교**를 수행한다.
- 모델 간 세대 차이와 구조정보 투입 효과는 `results/paired_structure_effect.csv`, `results/generation_comparison.csv`에서 탐색한다.
- 같은 개발 계열이지만 세대별 학습량, 훈련 데이터, 매개변수 수가 달라져, 결과를 세대 발전의 인과효과로 해석하지 않는다.
- 법령의 전체 검색 성능이나 혼합물의 위법 여부를 직접 검증하지 않는다.

## 출처

공식 고시 근거는 사용자가 제공한 `2026-5_(별표) 인체등유해성물질 목록(전체)(2).xlsx`의 해당 물리행이다. 실제 입력에는 `LEGAL_CLAUSES` 16개 지정행만 제공한다. 물질 식별 출처는 Gold `pubchem_url` 항목에 각 물질별로 기록했다.
