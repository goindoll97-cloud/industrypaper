param(
    [ValidateSet('pilot','main')][string]$Stage = 'pilot',
    [ValidateSet('all','A','B')][string]$Condition = 'all'
)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
python .\preflight.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python .\run_retrieval.py --stage $Stage --model all --condition $Condition
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if ($Stage -eq 'pilot') {
    python .\estimate_runtime.py --budget-minutes 120 --condition $Condition
} else {
    python .\score_results.py
}
