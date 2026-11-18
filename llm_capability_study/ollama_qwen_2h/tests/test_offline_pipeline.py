"""Offline fake Ollama server smoke test; no network and no API payment.
Fake Gold-derived outputs are used ONLY for testing the evaluation pipeline,
never as actual model results. This test cleans up files it creates.
"""
from __future__ import annotations
import importlib.util,json,sys,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import run_ollama, score_results, compare_generations, preflight

def run_test():
    preflight.main()
    gold={g['test_id']:g for g in score_results.load(ROOT/'private/gold_72.jsonl')}
    api_calls=[]
    def mock(url,payload=None,timeout=180):
        if url.endswith('/api/tags'):
            return {'models':[{'name':m,'digest':'offline-demo-'+m} for m in run_ollama.MODELS]}
        if url.endswith('/api/version'):return {'version':'offline-test'}
        if url.endswith('/api/generate'):return {}
        assert url.endswith('/api/chat')
        system=payload['messages'][0]['content'];user=payload['messages'][1]['content']
        assert 'gold_status' not in system and 'gold_72' not in user
        tid=user.split('시험 ID: ')[1].split('\n',1)[0]
        g=gold[tid]
        answer={k:g[k] for k in run_ollama.FIELDS if k!='reason_ko'}
        answer['reason_ko']='offline mock'
        api_calls.append((payload['model'],tid))
        return {'message':{'content':json.dumps(answer,ensure_ascii=False)},
                'eval_count':50,'prompt_eval_count':600,'total_duration':10000}
    old=run_ollama.send_json
    run_ollama.send_json=mock
    try:
        assert not list((ROOT/'results').glob('*__*.jsonl')), 'Do not run smoke test over user results'
        run_ollama.main(['--stage','pilot','--model','all'])
        assert len(api_calls)==18,len(api_calls)
        run_ollama.main(['--stage','main','--model','all'])
        assert len(api_calls)==216,len(api_calls)
        assert len(set(api_calls))==216
        for model in run_ollama.MODELS:
            p=ROOT/'results'/f'{model.replace(":","_")}__main.jsonl'
            records=score_results.load(p)
            assert len(records)==72 and sum(r['reused_pilot'] for r in records)==6
        score_results.main()
        compare_generations.main()
        assert (ROOT/'results/case_scores.csv').exists()
        assert (ROOT/'results/model_summary.csv').exists()
        assert (ROOT/'results/generation_comparison_bootstrap.csv').exists()
        print('PASS: 18 pilot + 198 remaining main = 216 unique calls; score; stratified CAS bootstrap; all fake results cleaned')
    finally:
        run_ollama.send_json=old
        for item in (ROOT/'results').iterdir():
            if item.name!='.gitkeep' and item.is_file():item.unlink()

if __name__=='__main__':run_test()
