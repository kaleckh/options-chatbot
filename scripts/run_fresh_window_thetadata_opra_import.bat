@echo off
cd /d C:\Users\kalec\options-chatbot
if not exist data\forward-tracking mkdir data\forward-tracking
C:\Python312\python.exe scripts\import_regular_options_fresh_window_thetadata_opra.py --approval-token APPROVE_FRESH_WINDOW_THETADATA_OPRA_IMPORT --timeout 20 --refresh-after-import --json >> data\forward-tracking\fresh_window_thetadata_opra_import_log.txt 2>&1
echo. >> data\forward-tracking\fresh_window_thetadata_opra_import_log.txt
C:\Python312\python.exe scripts\build_regular_options_fresh_window_import_scheduler_health.py --json >> data\forward-tracking\fresh_window_import_scheduler_health_log.txt 2>&1
echo. >> data\forward-tracking\fresh_window_import_scheduler_health_log.txt
