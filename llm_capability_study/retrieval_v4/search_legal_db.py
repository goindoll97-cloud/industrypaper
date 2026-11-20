"""Full-annex lexical search. No Gold, manually preselected candidates, or test-label hints.
Works over ALL 1451 official annex rows (SQLite backed; Python standard library).
The LLM chooses queries. This module only ranks the requested strings.
"""
from __future__ import annotations
import re, sqlite3, unicodedata, math
from pathlib import Path
ROOT=Path(__file__).resolve().parent
DB=ROOT/'data'/'official_annex_2026_5.sqlite'
CAS_PATTERN=re.compile(r'\b\d{2,7}-\d\d-\d\b')

def norm(s):
    return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',str(s or '')).lower().replace('–','-')).strip()

def tokens(s):
    return [w for w in re.findall(r'[a-z0-9가-힣]+',norm(s)) if len(w)>1 and w not in {'and','with','the','its','그','및','와','과','또는','다만','본','고시에서','chemical','compounds'}]

def cas_tokens(s):return set(CAS_PATTERN.findall(str(s or '')))

def row_score(query,row):
    q=norm(query)
    if not q:return 0
    title=norm(row['name_ko']+' '+row['name_en'])
    raw_cas=row['cas_field'] or ''
    # Accept both bare CAS and model-generated prefixed CAS (e.g. CAS 67-56-1).
    if cas_tokens(q) & cas_tokens(raw_cas):return 1500
    if CAS_PATTERN.fullmatch(q):return 0
    score=0.0
    if q==norm(row['name_ko']) or q==norm(row['name_en']):score+=350
    if len(q)>=3 and q in title:score+=170+min(len(q),40)
    wq=tokens(q)
    wr=tokens(title)
    if not wq:return score
    for t in wq:
        if t in wr:score+=52
        elif len(t)>=3 and any(t in item or item in t for item in wr if len(item)>=3):score+=22
    # Short Hangul descriptions often form long compound tokens. Character overlap
    # rewards those with the same real characters without requiring curated labels.
    qchars={q[i:i+2] for i in range(len(q)-1) if ' ' not in q[i:i+2]}
    rchars={title[i:i+2] for i in range(len(title)-1) if ' ' not in title[i:i+2]}
    if qchars:score+=30*len(qchars&rchars)/len(qchars)
    # Do not rank a completely unrelated term merely due to generic type names.
    return round(score,4) if score>=23 else 0.0

def all_rows(con):
    return [dict(r) for r in con.execute('SELECT * FROM annex ORDER BY excel_row')]

def search(con,query,k=8):
    if not 1<=k<=100:raise ValueError('k must be 1..100')
    scored=[(row_score(query,r),r) for r in all_rows(con)]
    scored=[(s,r) for s,r in scored if s>0]
    scored.sort(key=lambda t:(-t[0],int(t[1]['excel_row'])))
    return [{**r,'search_score':s} for s,r in scored[:k]]

def fused_search(con,queries,k=8,per_query=10):
    """Rank fusion of model-requested searches only; no knowledge of correct labels."""
    combined={}; logs=[]
    for query in queries[:3]:
        hits=search(con,query,k=per_query)
        logs.append({'query':query,'rows':[int(x['excel_row']) for x in hits]})
        for rank,r in enumerate(hits,1):
            key=int(r['excel_row'])
            if key not in combined:combined[key]=dict(r,rrf_score=0.0,matched_queries=[])
            combined[key]['rrf_score']+=1/(5+rank)
            combined[key]['matched_queries'].append(query)
    picked=sorted(combined.values(),key=lambda r:(-r['rrf_score'],-r['search_score'],int(r['excel_row'])))[:k]
    for r in picked:r['rrf_score']=round(r['rrf_score'],6)
    return picked,logs

def evidence(r):
    return {'excel_row':int(r['excel_row']),'designation_id':r['parent_designation_id'],
            'sub_number':int(r['sub_number']) if str(r.get('sub_number','')).isdigit() else None,
            'name_ko':r['name_ko'],'name_en':r['name_en'],'cas_field':r['cas_field'],
            'acute_percent':r['acute_percent'],'chronic_percent':r['chronic_percent'],
            'ecological_percent':r['ecological_percent']}

if __name__=='__main__':
    import argparse,json
    p=argparse.ArgumentParser();p.add_argument('query');p.add_argument('--top-k',type=int,default=8)
    ns=p.parse_args()
    if not DB.exists():raise SystemExit('먼저 python build_legal_db.py 실행')
    with sqlite3.connect(DB) as con:
        con.row_factory=sqlite3.Row
        print(json.dumps([evidence(r) for r in search(con,ns.query,ns.top_k)],ensure_ascii=False,indent=2))
