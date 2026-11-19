"""Total two-stage time from actual pilot (including invalid-but-returned outputs)."""
from pathlib import Path
import statistics,json,argparse
R=Path(__file__).resolve().parent
M=['qwen2.5:3b','qwen3:4b-instruct','qwen3.5:4b']
p=argparse.ArgumentParser();p.add_argument('--budget-minutes',type=float,default=120);p.add_argument('--condition',choices=['all','A','B'],default='all');ns=p.parse_args()
all_extra=0;pilot_total=0;valid_models=0
for m in M:
 f=R/'results'/f'{m.replace(":","_")}__pilot.jsonl'
 if not f.exists():print('No pilot:',m);continue
 data=[json.loads(s) for s in f.read_text(encoding='utf-8').splitlines() if s.strip()]
 xs=[x for x in data if x.get('status')!='api_error' and (ns.condition=='all' or x['condition']==ns.condition)]
 if len(xs)<3:print('Pilot observations insufficient:',m);continue
 mean=statistics.mean(x['wall_seconds'] for x in xs)
 alln=60 if ns.condition=='all' else 30
 extra=max(0,alln-len({x['test_id'] for x in xs}))*mean/60
 all_extra+=extra;pilot_total+=sum(x['wall_seconds'] for x in xs)/60;valid_models+=1
 print(f'{m:<20} pilot {len(xs)}, 평균 2단계 {mean:.1f}s (검색+추론), 본실험 추가 {extra:.1f}분')
if valid_models==3:
 print(f'추가 {all_extra:.1f}분, 예비 사용 {pilot_total:.1f}분, 합계 추정 {all_extra+pilot_total:.1f}분 / 목표 {ns.budget_minutes:g}분')
 print('참고: 모든 모델의 초기 로딩, 재시도/실패, 운영체제 부하 및 추가 실험은 포함되지 않음.')
