param(
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

Write-Step "Using Python"
& $Python --version

Write-Step "Checking for staged real market data"
$stagedFiles = git diff --cached --name-only
$blockedFiles = @()
foreach ($file in $stagedFiles) {
    $normalized = $file -replace "\\", "/"
    $isMarketData = $normalized -like "data/market_data/*.csv" -or $normalized -like "data/market_data/*.txt"
    $isAllowedSample = $normalized -eq "data/market_data/sample_NQ_1m.csv" -or $normalized -eq "data/market_data/.gitkeep"
    if ($isMarketData -and -not $isAllowedSample) {
        $blockedFiles += $file
    }
}

if ($blockedFiles.Count -gt 0) {
    Write-Host "Blocked staged market data files:" -ForegroundColor Red
    $blockedFiles | ForEach-Object { Write-Host " - $_" -ForegroundColor Red }
    throw "Refusing to continue because real market data is staged."
}

Write-Step "Compiling app.py"
& $Python -m py_compile app.py

if (-not $SkipTests) {
    Write-Step "Running pytest"
    $env:PYTHONPATH = "src"
    & $Python -m pytest
}

Write-Host ""
Write-Host "All checks passed." -ForegroundColor Green
