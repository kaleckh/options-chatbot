@echo off
cd /d C:\Users\kalec\options-chatbot
set OPTIONS_SCAN_PLAYBOOK=bullish_pullback_observation
set OPTIONS_SCAN_ENFORCE_PORTFOLIO_CAPS=1
C:\Python312\python.exe scripts\log_scan_picks.py >> data\forward-tracking\scan_log.txt 2>&1
C:\Python312\python.exe scripts\ensure_daily_all_lanes_audit_ran.py --force >> data\forward-tracking\daily_all_lanes_audit_log.txt 2>&1
echo. >> data\forward-tracking\daily_all_lanes_audit_log.txt
C:\Python312\python.exe scripts\validate_pending_scan_candidates.py >> data\forward-tracking\pending_candidate_validation_log.txt 2>&1
echo. >> data\forward-tracking\pending_candidate_validation_log.txt
