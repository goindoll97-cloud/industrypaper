# Run from this directory after downloading Ollama models.
$ErrorActionPreference = 'Stop'
python .\preflight.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python .\run_ollama.py --stage pilot --model all
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python .\estimate_runtime.py --budget-minutes 120
Write-Host "Check the estimated remaining time before running: python .\run_ollama.py --stage main --model all"
