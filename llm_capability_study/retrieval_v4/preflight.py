from pathlib import Path
import collections,hashlib,json
R=Path(__file__).resolve().parent;D=R/'data';m=json.loads((D/'manifest.json').read_text(encoding='utf-8'))
for k,n in [('annex_sha256','official_annex_2026_5_full.csv'),('cases_sha256','cases_60.jsonl'),('pilot_sha256','pilot_12_ids.json')]:
 assert hashlib.sha256((D/n).read_bytes()).hexdigest()==m[k],n
q=[json.loads(x) for x in (D/'cases_60.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
assert len(q)==60 and len({x['test_id'] for x in q})==60
assert len({x['case_id'] for x in q})==30
strata=collections.Counter((x['group'],x['difficulty']) for x in q if x['condition']=='A')
assert len(strata)==6 and set(strata.values())=={5},strata
for c in q:
 assert all(k not in c for k in ['expected_relation','gold','source_excel_row','relevant_entry_id']),c
 assert len(c['components']) in (2,3) if c['group']=='MIXTURE' else len(c['components'])==1
 if c['group']=='MIXTURE':assert sum(x['mass_percent'] for x in c['components'])==100
 g=[x for x in q if x['case_id']==c['case_id']]
 assert {x['condition'] for x in g}=={'A','B'}
 assert all(x['formula'] is None and x['smiles'] is None for x in c['components']) if c['condition']=='A' else True
pilot=set(json.loads((D/'pilot_12_ids.json').read_text(encoding='utf-8')))
assert len(pilot)==12 and pilot.issubset({x['test_id'] for x in q})
print('PASS: 공식 고시 1451행 / 30상황 / 유형별 10건 / EASY-HARD 각5 / 60문항 / Gold 입력 누출 없음')
p=R/'private/gold_60.jsonl'
if p.exists():
 assert hashlib.sha256(p.read_bytes()).hexdigest()==m['gold_sha256'],'Gold SHA mismatch'
 print('PASS: 잠정 Gold 무결성 (법률 전문가의 검증을 의미하지 않음)')
else:print('비공개 Gold는 공개 GitHub에서 제외함; 개인 ZIP에서 private/gold_60.jsonl 복사')
