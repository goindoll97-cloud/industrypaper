"""Paired CAS-cluster, 12-stratum bootstrap; exploratory small-sample uncertainty."""
from __future__ import annotations
import argparse,csv,math,random,statistics
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parent
MODELS=['qwen2.5:3b','qwen3:4b-instruct','qwen3.5:4b']
SEED=20261118;BOOTSTRAPS=2000

def pctile(xs,p):
    xs=sorted(x for x in xs if math.isfinite(x))
    if not xs:return float('nan')
    pos=(len(xs)-1)*p;lo=int(pos);hi=min(lo+1,len(xs)-1)
    return xs[lo]*(hi-pos)+xs[hi]*(pos-lo)

def main():
    ap=argparse.ArgumentParser(description="Compare two or three Qwen versions with CAS-cluster paired bootstrap")
    ap.add_argument('--models',nargs='+',choices=MODELS,default=None)
    args=ap.parse_args()
    p=ROOT/'results/case_scores.csv' 
    if not p.exists():raise SystemExit('먼저 python score_results.py 실행')
    with p.open('r',encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    bymodel=defaultdict(dict)
    for row in rows:bymodel[row['model']][row['test_id']]=row
    selected=args.models if args.models is not None else [m for m in MODELS if m in bymodel]
    if len(selected)<2 or len(set(selected))!=len(selected):raise SystemExit('Need two or three different model results')
    if any(len(bymodel[m])!=72 for m in selected):raise SystemExit('선택한 모델의 72문항 채점 결과가 있어야 합니다.')
    if any(any(r['api_success']!='True' for r in bymodel[m].values()) for m in selected):
        raise SystemExit('선택한 모델의 72문항의 API 결과를 확보한 후 비교하세요.')
    if len(set.intersection(*[set(bymodel[m]) for m in selected]))!=72:
        raise SystemExit('모델별 test_id 집합이 다릅니다.')
    clusters=defaultdict(list)
    strata=defaultdict(list)
    for tid,r in bymodel[selected[0]].items():clusters[r['chemical_case_id']].append(tid)
    for cid,ids in clusters.items():
        r=bymodel[selected[0]][ids[0]]
        strata[(r['stratum'],r['difficulty'])].append(cid)
    if len(clusters)!=36 or any(len(v)!=2 for v in clusters.values()) or len(strata)!=12 or any(len(x)!=3 for x in strata.values()):
        raise SystemExit('36 CAS, 각 2문항, 12개 층 x 3종 필요')
    rng=random.Random(SEED)
    samples=[[cid for k in sorted(strata) for cid in rng.choices(strata[k],k=len(strata[k]))]
             for _ in range(BOOTSTRAPS)]
    allcids=list(clusters)
    def delta(a,b,ids,condition=None):
        diffs=[]
        for cid in ids:
            for tid in clusters[cid]:
                aa=bymodel[a][tid];bb=bymodel[b][tid]
                if condition and not condition(aa):continue
                diffs.append(int(bb['core_exact']=='True')-int(aa['core_exact']=='True'))
        return statistics.mean(diffs) if diffs else float('nan')
    out=[]
    for a,b in ([(selected[0],selected[1])] if len(selected)==2 else [(selected[0],selected[1]),(selected[1],selected[2]),(selected[0],selected[2])]):
        checks=[('ALL',None),('EASY',lambda x:x['difficulty']=='EASY_RELATIVE'),
                ('HARD',lambda x:x['difficulty']=='HARD_RELATIVE'),
                ('BELOW_BOUNDARY',lambda x:x['scenario']=='BELOW_BOUNDARY'),
                ('AT_FIRST_THRESHOLD',lambda x:x['scenario']=='AT_FIRST_THRESHOLD')]
        for label,flt in checks:
            v=delta(a,b,allcids,flt)
            boots=[delta(a,b,s,flt) for s in samples]
            out.append({'earlier_model':a,'later_model':b,'analysis':label,
                        'delta_later_minus_earlier':round(v,4),
                        'CI95_low':round(pctile(boots,.025),4),
                        'CI95_high':round(pctile(boots,.975),4),'bootstrap_replications':BOOTSTRAPS})
        hard=lambda x:x['difficulty']=='HARD_RELATIVE'
        easy=lambda x:x['difficulty']=='EASY_RELATIVE'
        v=delta(a,b,allcids,hard)-delta(a,b,allcids,easy)
        boots=[delta(a,b,s,hard)-delta(a,b,s,easy) for s in samples]
        out.append({'earlier_model':a,'later_model':b,'analysis':'HARD_MINUS_EASY_IMPROVEMENT',
                    'delta_later_minus_earlier':round(v,4),
                    'CI95_low':round(pctile(boots,.025),4),
                    'CI95_high':round(pctile(boots,.975),4),'bootstrap_replications':BOOTSTRAPS})
    path=ROOT/'results/generation_comparison_bootstrap.csv'
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(out[0]));w.writeheader();w.writerows(out)
    print('세대별 대응 비교 저장:',path)
    for r in out:
        if r['analysis'] in ('ALL','HARD_MINUS_EASY_IMPROVEMENT'):
            print(r)
    print('주의: 유형당 쉬움/어려움 각 3종뿐이므로 신뢰구간은 넓을 수 있으며 탐색적으로 해석하세요.')

if __name__=='__main__':main()
