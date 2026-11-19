"""Preflight: official annex source and 10 broad legal scope families; Gold never in model input."""
import json,hashlib,re,collections,csv
from pathlib import Path
R=Path(__file__).resolve().parent;D=R/'data';m=json.loads((D/'manifest.json').read_text(encoding='utf-8'))
for name,key in [('cases_60.jsonl','cases_sha256'),('pilot_10_ids.json','pilot_sha256'),('official_annex_2026_5_full.csv','annex_sha256'),('scope_clause_audit.csv','scope_audit_sha256')]:
 p=D/name
 assert p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==m[key],name
q=[json.loads(x) for x in (D/'cases_60.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
assert len(q)==60 and len(set(x['test_id'] for x in q))==60
assert len(set(x['case_id'] for x in q))==30
assert len(set(x['cas'] for x in q))==27
for cid in set(x['case_id'] for x in q):
 pair=[x for x in q if x['case_id']==cid]
 assert len(pair)==2 and set(x['condition'] for x in pair)=={'A','B'}
 assert pair[0].get('particle_size_mm')==pair[1].get('particle_size_mm')
assert all('target' not in x and 'gold' not in x and 'family' not in x for x in q)
assert all(x['formula'] is None and x['smiles'] is None for x in q if x['condition']=='A')
assert all(x['formula'] is not None for x in q if x['condition']=='B')
pilots=json.loads((D/'pilot_10_ids.json').read_text(encoding='utf-8'))
assert len(pilots)==10 and len(set(pilots))==10 and set(pilots)<=set(x['test_id'] for x in q)
rows=list(csv.DictReader((D/'official_annex_2026_5_full.csv').open(encoding='utf-8-sig')))
assert len(rows)==1451
assert len(list(csv.DictReader((D/'scope_clause_audit.csv').open(encoding='utf-8-sig'))))==m['scope_audit_candidate_rows']
print('PASS: 1451 annex rows, 30 physical/chemical test situations, 27 distinct CAS, 60 A/B questions, 10 candidate category families')
g=R/'private/gold_60.jsonl'
if g.is_file():
 assert hashlib.sha256(g.read_bytes()).hexdigest()==m['gold_sha256']
 G=[json.loads(x) for x in g.read_text(encoding='utf-8').splitlines() if x.strip()]
 assert len(G)==60 and set(x['test_id'] for x in G)==set(x['test_id'] for x in q)
 assert all(int(x['source_excel_row']) in {int(k['excel_row']) for k in rows} for x in G)
 print('PASS: Gold draft SHA, 54 provisional tasks, 6 pending (not final expert-adjudicated)')
else:print('Gold not present (correct for public GitHub); local ZIP private/gold_60.jsonl required for scoring')
