# 90문항 평가 입력 및 후보 검토자료

현재 논문은 [B 조건 90문항, 네 모델, 각 5회](../README.md) 실험만 사용합니다.

- `PROPOSED_90_B_cases.jsonl`: 90개 평가 질문의 화학물질 정보(정답 없음). 로컬 `private/provisional_b90/cases_90_B_PROVISIONAL.jsonl`와 같은 SHA256으로 확인됩니다.
- `PROPOSED_new_60_component_review.csv`: 잠정 Gold 생성에 필요한 자료. 파일명에 남은 이력상 명칭은 기존 Gold manifest의 파일 해시와 연결되므로 바꾸지 않습니다.
- `PROPOSED_new_60_cases_summary.csv`, `check_pubchem.py`: 연구 입력 감사용 보조 자료.

질문과 정답/규제 근거는 별개입니다. **비공개 Gold와 모델 원본 응답은 공개하지 않습니다.** 현재 원본 자료의 법령 적용과 물질 식별은 독립 전문가 검증 전입니다.
