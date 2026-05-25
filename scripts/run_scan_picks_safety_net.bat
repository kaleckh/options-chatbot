@echo off
cd /d C:\Users\kalec\options-chatbot
set OPTIONS_SCAN_PLAYBOOK=bullish_pullback_observation
C:\Python312\python.exe scripts\ensure_scan_picks_ran.py >> data\forward-tracking\scan_health_log.txt 2>&1
echo. >> data\forward-tracking\scan_health_log.txt
