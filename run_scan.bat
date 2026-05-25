@echo off
setlocal
cd /d "%~dp0"
set OPTIONS_SCAN_PLAYBOOK=bullish_pullback_observation
set OPTIONS_SCAN_USE_RECOMMENDED_POLICY=0
if exist C:\Python312\python.exe (
    C:\Python312\python.exe auto_scan.py
) else (
    uv run python auto_scan.py
)
