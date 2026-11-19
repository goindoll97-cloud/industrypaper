# Retrieval v3: 신규 24종, 전체 고시 검색형 LLM 2차 실험

이 폴더는 `llm_capability_study/` 안의 **유일한 실험 폴더**입니다. 이전 실험은 `main`에서 정리했고 Git 커밋/보존 브랜치에 남아 있습니다.

## 실험
- 기존 v2와 CAS가 겹치지 않는 **24종 × A/B 2조건 = 48문항**.
- Qwen 2.5 3B, Qwen 3 4B Instruct, Qwen 3.5 4B, 총 **144개 문항-모델 조합**, 검색어 생성+판정 **기본 288회 모델 호출**.
- A는 CAS+영문 물질명, B는 A+검증용 분자식입니다. 하나의 정확한 SMILES로 대표하기 어려운 염류/무기화합물에 억지 SMILES를 넣지 않았습니다. **SMILES 단독 효과로 해석하지 마세요.**
- 5개 유형: 유기물질 염류 5 / 무기·금속염 5 / 직접 지정 4 / 명시 제외 5 / 비해당 후보 5.
- 법령 16개 선택지 사전 제공 **없음**. LLM이 검색어 1~3개를 생성하고, 동일 Python 검색기가 공식 2026-5호 고시 **전체 1,451행**을 SQLite로 검색해 최대 8행을 반환합니다. 동일 모델이 조항의 포괄 지정범위를 판정합니다.
- Recall@8 / 정답행 검색 시 조건부 판단 / end-to-end / A/B 쌍 비교 / 형식 오류 등을 기록합니다.

## Gold 검증 상태 (중요)
- 19종(38문항)은 공식 고시의 **직접 지정/포괄 포함/명시 제외** 관계를 매칭한 *잠정 Gold*입니다. 논문 확정 전 화학·법규 분야 독립 검토를 권장합니다.
- 5종(10문항)의 **비해당 후보는 독립 법령 검토가 끝나지 않았습니다**. 그래서 현재 채점기의 확정분석에서 제외됩니다.
- `EXPLICIT_EXCEPTION`은 **그 포괄 조항의 제외**이지 국내 모든 법규에서 비규제라는 뜻이 아닙니다.
- Gold는 모델이 사용하는 데이터에서 분리했습니다. 공개 GitHub에는 `private/`를 올리지 않으므로, 별도 제공 ZIP 안의 `private/gold_48.jsonl`을 로컬에 복사해야 채점할 수 있습니다.
- 정답지에 `PENDING_INDEPENDENT_REVIEW`가 남아 있으며, 확정 법적 유권해석을 대신하지 않습니다.

## RTX 2060 / Windows 실행

```powershell
cd D:\framework_chemical_regul_paper
git pull origin main
cd llm_capability_study\retrieval_v3
ollama pull qwen2.5:3b
ollama pull qwen3:4b-instruct
ollama pull qwen3.5:4b
python .\preflight.py
python .\run_retrieval.py --stage pilot --model all
python .\estimate_runtime.py --budget-minutes 120
python .\run_retrieval.py --stage main --model all
python .\score_results.py
```

- Pilot: 8문항/모델. 같은 설정의 본실험에서 재사용되며 중복 호출하지 않습니다.
- 중단 후 같은 명령으로 재개할 수 있습니다. **`--force`는 결과 삭제**이므로 재개 시 사용하지 마세요.
- 기본 문맥 3072, 검색어 최대 125토큰, 판정 JSON 최대 420토큰, temperature 0, Qwen3 계열 nonthinking. RTX 2060에서 약 1~2시간은 목표일 뿐 보장 시간이 아니며, 새 예비실험으로 확인하세요.
- 구 실험과 검증셋이 다르므로 점수를 동일 표본의 성능 변화로 해석하지 마세요.
- 기존 PC의 미추적/비공개 `results/` 자료는 `git pull`로 이동하지 않습니다. 필요하면 반드시 외부 폴더에 백업하세요.

이전 실험 보존 브랜치: `archive/llm_capability_before_v3_2026-11-19`.
