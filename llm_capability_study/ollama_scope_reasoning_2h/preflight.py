from pathlib import Path
import json,hashlib,collections
R=Path(__file__).resolve().parent
D=R/'data';m=json.loads((D/'manifest.json').read_text(encoding='utf-8'))
for k,name in [('prompts_sha256','prompts_40.jsonl'),('pilot_ids_sha256','pilot_8_ids.json')]:
 f=D/name
 if hashlib.sha256(f.read_bytes()).hexdigest()!=m[k]:raise SystemExit('FAIL '+name+' sha256')
q=[json.loads(x) for x in (D/'prompts_40.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
assert len(q)==40 and len({x['test_id'] for x in q})==40
assert len({x['cas'] for x in q})==20
assert all(sum(r['case_id']==cid and r['condition']==condition for r in q)==1 for cid in {x['case_id'] for x in q} for condition in ('A','B'))
for cat in {x['category'] for x in q}:
 for dif in ('EASY','HARD'):
  assert len({x['case_id'] for x in q if x['category']==cat and x['difficulty']==dif})==2
assert len({x['category'] for x in q})==5
assert all('Gold' not in str(x['user_prompt']) and 'expected_relation' not in str(x['user_prompt']) for x in q)
assert all(x['prompt_sha256']==hashlib.sha256((x['system_prompt']+'\n'+x['user_prompt']).encode('utf-8')).hexdigest() for x in q)
print('PASS: 20 CAS x 2 conditions = 40 questions; 5 strata x EASY/HARD 2 CAS each; Gold absent from prompts')
p=R/'private/gold_40.jsonl'
if p.exists():
 if hashlib.sha256(p.read_bytes()).hexdigest()!=m['gold_sha256']:raise SystemExit('Gold SHA mismatch')
 gs=[json.loads(z) for z in p.read_text(encoding='utf-8').splitlines() if z.strip()]
 assert len(gs)==40 and {z['test_id'] for z in gs}=={z['test_id'] for z in q}
 assert all(z['expected_relation'] in ('DIRECT_SPECIFIC','GROUP_INCLUDED','EXPLICIT_EXCEPTION','NOT_COVERED') for z in gs)
 print('PASS: Gold SHA and aligned test IDs')
else:
 print('Gold is intentionally absent from public GitHub; place private/gold_40.jsonl locally for scoring')
