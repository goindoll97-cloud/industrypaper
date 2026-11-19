from pathlib import Path
import json,statistics,argparse
R=Path(__file__).resolve().parent
M=['qwen2.5:3b','qwen3:4b-instruct','qwen3.5:4b']
p=argparse.ArgumentParser();p.add_argument('--budget-minutes',type=float,default=120);args=p.parse_args()
all_est=0;pilot_count=0
for m in M:
 f=R/'results'/f'{m.replace(":","_")}__pilot.jsonl'
 if not f.exists():print('No pilot for',m);continue
 xs=[json.loads(x) for x in f.read_text(encoding='utf-8').splitlines() if x.strip()]
 d=[x['wall_seconds'] for x in xs if x.get('status')=='ok' and x.get('json_valid')]
 if len(d)<4:print('Not enough valid pilot observations:',m);continue
 mean=statistics.mean(d);remaining=(40-len(set(x['test_id'] for x in xs if x.get('status')=='ok')))*mean/60
 all_est+=remaining;pilot_count+=1
 print(f'{m:<20} pilot valid {len(d)} mean {mean:.1f}s | remaining ~{remaining:.1f}min')
if pilot_count==3:
 print(f'본실험 추가 예상: {all_est:.1f}분, 목표 {args.budget_minutes:.0f}분; remaining budget = {args.budget_minutes-all_est:+.1f}분 (현재까지 사용한 pilot 시간 제외)')
else:print('세 모델 모두 pilot 결과가 있어야 전체 예상시간이 출력됩니다.')
