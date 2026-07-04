@echo off
cd /d C:\Users\kalec\options-chatbot
if not exist data\forward-tracking mkdir data\forward-tracking
.venv\Scripts\python.exe scripts\run_daily_ops.py --continue-on-failure --json >> data\forward-tracking\daily_ops_task_log.txt 2>&1
echo. >> data\forward-tracking\daily_ops_task_log.txt
