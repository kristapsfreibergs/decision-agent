@echo off
setlocal
cd /d "%~dp0.."
set PYTHONPATH=backend/src
if exist "%USERPROFILE%\.pyenv\pyenv-win\bin\pyenv.bat" (
  call "%USERPROFILE%\.pyenv\pyenv-win\bin\pyenv.bat" exec python -m decision_agent.cli run examples/build-decision-agent.json
) else (
  python -m decision_agent.cli run examples/build-decision-agent.json
)
