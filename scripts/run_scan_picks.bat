@echo off
cd /d C:\Users\kalec\options-chatbot
C:\Python312\python.exe scripts\log_scan_picks.py >> data\forward-tracking\scan_log.txt 2>&1
