@echo off
setlocal
cd /d "%~dp0"
uv run python auto_scan.py
