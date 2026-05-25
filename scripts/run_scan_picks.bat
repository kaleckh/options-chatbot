@echo off
cd /d C:\Users\kalec\options-chatbot
set OPTIONS_SCAN_PLAYBOOK=bullish_pullback_observation
C:\Python312\python.exe scripts\log_scan_picks.py >> data\forward-tracking\scan_log.txt 2>&1
