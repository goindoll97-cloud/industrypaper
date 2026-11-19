python .\preflight.py
if ($LASTEXITCODE -ne 0) { throw 'preflight failed' }
python .\run_retrieval.py --stage pilot --model all
python .\estimate_runtime.py --budget-minutes 120
