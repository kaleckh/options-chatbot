@echo off
setlocal
cd /d "%~dp0\.."
if not exist "data\agent-control" mkdir "data\agent-control"
echo [%date% %time%] memory auto-maintenance start >>"data\agent-control\maintenance-scheduler.log"
uv run --locked python scripts\agent_control.py memory auto-maintenance --prompt-only >>"data\agent-control\maintenance-scheduler.log" 2>&1
set EXIT_CODE=%ERRORLEVEL%
echo [%date% %time%] memory auto-maintenance exit %EXIT_CODE% >>"data\agent-control\maintenance-scheduler.log"
exit /b %EXIT_CODE%
