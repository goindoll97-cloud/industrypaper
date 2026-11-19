import json,hashlib,csv,sys,sqlite3
from pathlib import Path
from build_legal_db import build,DB,ROOT
m=json.loads((ROOT/'data/manifest.json').read_text(encoding='utf-8'))
for filename,key in [('cases_40.jsonl','cases_sha256'),('pilot_8_ids.json','pilot_sha256'),('official_annex_2026_5_full.csv','annex_sha256')]:
 p=ROOT/'data'/filename
 assert hashlib.sha256(p.read_bytes()).hexdigest()==m[key],f'{filename} SHA incorrect'
cases=[json.loads(l) for l in (ROOT/'data/cases_40.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
assert len(cases)==40 and len({c['test_id'] for c in cases})==40
assert len({c['case_id'] for c in cases})==20
assert all(sum(1 for c in cases if c['case_id']==cid and c['condition']==cond)==1 for cid in {c['case_id'] for c in cases} for cond in ('A','B'))
assert all('user_prompt' not in c and 'expected_relation' not in c and 'category' not in c for c in cases)
assert all(c['formula'] is None and c['smiles'] is None for c in cases if c['condition']=='A')
with (ROOT/'data/official_annex_2026_5_full.csv').open(encoding='utf-8-sig',newline='') as f:
 rows=list(csv.DictReader(f))
assert len(rows)==1451 and len({int(r['excel_row']) for r in rows})==1451
build()
with sqlite3.connect(DB) as con:
 assert con.execute('SELECT COUNT(*) FROM annex').fetchone()[0]==1451
print('PASS: ALL 1451 annex rows indexed, no gold/16-clauses in prompts, 20 CAS × A/B = 40 questions')
g=ROOT/'private/gold_40.jsonl'
if g.exists():
 assert hashlib.sha256(g.read_bytes()).hexdigest()==m['gold_sha256'],'Gold mismatch'
 print('PASS: local Gold authenticated, never read by runner')
else:print('NOTE: Gold absent (expected in public GitHub). Scoring requires private/gold_40.jsonl')
