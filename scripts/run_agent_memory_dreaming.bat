@echo off
setlocal

cd /d "%~dp0\.."
if not exist "data\agent-control\dream-runs" mkdir "data\agent-control\dream-runs"

echo ==== %DATE% %TIME% ====>> "data\agent-control\dream-runs\scheduler.log"
uv run --locked python scripts\agent_control.py dream run --json >> "data\agent-control\dream-runs\scheduler.log" 2>&1
exit /b %ERRORLEVEL%
