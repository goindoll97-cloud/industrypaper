from pathlib import Path
import argparse,statistics,json
R=Path(__file__).resolve().parent
m=['qwen2.5:3b','qwen3:4b-instruct','qwen3.5:4b']
p=argparse.ArgumentParser();p.add_argument('--budget-minutes',type=float,default=120);ns=p.parse_args()
total=0
for model in m:
 f=R/'results'/f'{model.replace(":","_")}__pilot.jsonl'
 if not f.exists():print('pilot 미실행:',model);continue
 a=[json.loads(s) for s in f.read_text(encoding='utf-8').splitlines() if s.strip()]
 ok=[x for x in a if x['status']=='ok']
 if len(ok)<3:print('표본 부족:',model);continue
 avg=statistics.mean(x['wall_seconds'] for x in ok)
 rem=(60-len({x['test_id'] for x in a if x['status'] in ('ok','invalid_query','invalid_answer')}))*avg/60
 total+=rem
 print(f'{model:<20} valid={len(ok)} avg={avg:.1f}s, remaining ~{rem:.1f} min')
print(f'본실험 추가 예상: {total:.1f}분 (예비실험과 모델 로딩 제외); 목표 {ns.budget_minutes:.0f}분')
print('참고: 혼합물 3성분 문항의 응답 길이가 길면 속도가 느려질 수 있습니다.')
