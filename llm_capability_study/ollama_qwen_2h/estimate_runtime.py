"""Predict remaining runtime from the six real pilot calls per model."""
import argparse,json,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parent
MODELS=['qwen2.5:3b','qwen3:4b-instruct','qwen3.5:4b']

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--budget-hours',type=float,default=2.0)
    ap.add_argument('--models',nargs='+',choices=MODELS,default=MODELS,help='Select 2 models for fallback')
    args=ap.parse_args()
    projected=0
    missing=[]
    print('=== RTX2060 실제 예비실험 기준 추정 (메인 72문항/모델) ===')
    for name in args.models:
        path=ROOT/'results'/f'{name.replace(":","_")}__pilot.jsonl'
        if not path.exists():missing.append(name);continue
        rows=[json.loads(s) for s in path.read_text(encoding='utf-8').splitlines() if s.strip()]
        rows=[r for r in rows if r.get('status')=='ok' and r.get('wall_seconds') is not None]
        if len(rows)<3:missing.append(name);continue
        # median robust to one-time model loading spike; same 72 prompt format and evidence rows.
        t=statistics.median(float(r['wall_seconds']) for r in rows)
        m=statistics.mean(float(r['wall_seconds']) for r in rows)
        # first 6 successful pilot questions reused at identical settings
        remaining=72-len({r['test_id'] for r in rows})
        predicted=t*remaining/60
        projected+=predicted
        warn=' [CPU offload/컨텍스트 길이 확인]' if any(r.get('possible_context_truncation') for r in rows) else ''
        print(f'{name:22s}: 예비 {len(rows)}건, 평균 {m:.1f}초, 중앙값 {t:.1f}초, 잔여 {remaining}건 ≈ {predicted:.0f}분'+warn)
    if missing:
        print('측정 부족 모델:',', '.join(missing))
        print('선택한 모델 모두 pilot 6건을 마친 뒤 총 소요를 해석하세요.')
        return
    cap=args.budget_hours*60
    print(f'본실험 추가 예상: {projected:.0f}분; 예비실험 종료 시점부터 2시간 목표 여유: {cap-projected:+.0f}분')
    if projected>cap:print('WARNING: 이 GPU에서 72문항 × 3모델을 2시간 내 끝낸다는 보장이 없습니다. 실험을 축소하거나 실행 시간을 늘리세요.')
    else:print('예상상 2시간 이내. 다만 첫 모델 로드, 오류 재시도, 긴 물질명은 실제 시간을 늘릴 수 있습니다.')

if __name__=='__main__':main()
