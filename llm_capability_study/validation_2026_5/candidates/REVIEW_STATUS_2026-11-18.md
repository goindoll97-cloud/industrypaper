# 2026-5호 미등재 후보 100종 — Gold 편입 전 검증 현황

검토일: 2026-11-18

## 원본
- 사용자 업로드: `nonlisted_candidates_REVIEW.csv` (100종)
- 검증 원본: `2026-5_(별표) 인체등유해성물질 목록(전체)(2).xlsx` (1,451개 데이터 행)
- 기존 평가파일: `../2026_5_LLM_Validation_Set.xlsx`, `../2026_5_LLM_GOLD_Answer_Key.xlsx`

## 기계적 대조 결과
| 항목 | 결과 |
|---|---:|
| 수집 후보 | 100종 |
| CAS 번호 중복 | 0건 |
| 원본 별표 E열 CAS 직접 일치 | 0종 |
| 별표 A~J열 모든 텍스트에서 CAS 일치 | 0종 |
| 후보의 PubChem CAS 동의어와 별표 전체의 명시적 CAS 겹침 | 0종 |
| CAS 독립 확인 완료 (`cas_independently_verified`) | 0종 |
| 포괄 화합물군·염류 등 법적 범위 확인 완료 (`legal_scope_checked`) | 0종 |
| 법적 검토 완료 (`legal_review_status`) | 0종 |
| `REVIEW_PENDING` | **100종** |
| 현재 Gold에 안전하게 추가할 수 있는 물질 | **0종** |

검토 우선순위는 `HIGH_PRIORITY_GROUP_OR_SALT_REVIEW` 10종, `MANDATORY_GENERAL_SCOPE_REVIEW` 90종입니다.

## 연구 무결성 주의
- CAS가 별표 E열에 **없다**는 사실은 **해당 물질이 법적으로 고시 미등재**라는 확증이 아닙니다.
- 포괄물질군(예: 특정 금속과 그 화합물), 염류, 이성질체, 동의어 및 예외조항 검토가 필요합니다.
- `nonlisted_candidates_REVIEW.csv`의 `gold_status`는 **100종 모두 공란**이며 검토 상태는 `REVIEW_PENDING`입니다.
- 따라서 이번 변경에서는 기존 1,200건의 **검증셋과 Gold XLSX는 변경하지 않았습니다.**
- 이전 Gold가 아닌 새 Gold를 확정하려면 각 후보에 독립적 CAS 증빙 및 법적 범위 판단 근거 URL을 기록하고, `legal_scope_checked`, `legal_review_status`, `gold_status`를 확정한 뒤 **동일 시점에 두 XLSX를 함께 버전 갱신**해야 합니다.

## 파일 무결성
기존 GitHub XLSX의 blob SHA-1:
- `2026_5_LLM_Validation_Set.xlsx`: `32bb10816a300f078dd6afe41cfb9b250650f962`
- `2026_5_LLM_GOLD_Answer_Key.xlsx`: `dcbca85763b9d34f6156fe65dbbe9056ee0b3e82`

이 SHA는 이 대화에서 작성된 원본 엑셀 파일과 일치합니다.

**이 문서는 후보 검토 현황 기록이지, 100종의 Gold 확정 보고서가 아닙니다.**
