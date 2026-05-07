$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$env:PYTHONPATH = "backend/src"
$pyenv = Join-Path $env:USERPROFILE ".pyenv\pyenv-win\bin\pyenv.bat"
if (Test-Path -LiteralPath $pyenv) {
  & $pyenv exec python -m decision_agent.cli run examples/build-decision-agent.json
} else {
  python -m decision_agent.cli run examples/build-decision-agent.json
}
