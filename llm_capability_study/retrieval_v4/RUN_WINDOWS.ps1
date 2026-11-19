$ErrorActionPreference = 'Stop'
python .\preflight.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python .\run_retrieval.py --stage pilot --model all
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python .\estimate_runtime.py --budget-minutes 120
