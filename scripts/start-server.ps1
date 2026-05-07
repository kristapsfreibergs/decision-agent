$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$env:PYTHONPATH = "backend/src"
$pyenv = Join-Path $env:USERPROFILE ".pyenv\pyenv-win\bin\pyenv.bat"
if (Test-Path -LiteralPath $pyenv) {
  & $pyenv exec python -m decision_agent.server
} else {
  python -m decision_agent.server
}
