$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
Write-Host "1) 데이터 무결성 검사" -ForegroundColor Cyan
python .\preflight.py
Write-Host "2) 기술 예비실험: 각 모델 6건" -ForegroundColor Cyan
python .\run_ollama.py --stage pilot --model all
Write-Host "3) 2시간 목표 예상 소요 확인" -ForegroundColor Cyan
python .\estimate_runtime.py --budget-hours 2
Write-Host "이 값을 확인한 다음 아래 명령을 개별 실행하세요:"
Write-Host "python .\run_ollama.py --stage main --model all"
Write-Host "python .\score_results.py"
Write-Host "python .\compare_generations.py"
