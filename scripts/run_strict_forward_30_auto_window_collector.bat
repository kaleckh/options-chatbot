@echo off
cd /d C:\Users\kalec\options-chatbot
set OPTIONS_SCAN_AUTO_TRACK=0
set OPTIONS_SCAN_ENFORCE_PORTFOLIO_CAPS=1
set OPTIONS_ENFORCE_LANE_PROFITABILITY_GATE=1
C:\Python312\python.exe scripts\run_regular_options_strict_forward_30_auto_window_collector.py --max-attempts 3 --sleep-seconds 300 --json >> data\forward-tracking\strict_forward_30_auto_window_collector_log.txt 2>&1
echo. >> data\forward-tracking\strict_forward_30_auto_window_collector_log.txt
C:\Python312\python.exe scripts\build_regular_options_strict_forward_30_scheduler_health.py --json >> data\forward-tracking\strict_forward_30_scheduler_health_log.txt 2>&1
echo. >> data\forward-tracking\strict_forward_30_scheduler_health_log.txt
C:\Python312\python.exe scripts\build_regular_options_strict_forward_scan_task_health.py --json >> data\forward-tracking\strict_forward_scan_task_health_log.txt 2>&1
echo. >> data\forward-tracking\strict_forward_scan_task_health_log.txt
C:\Python312\python.exe scripts\build_regular_options_strict_forward_30_candidate_review_packet.py --json >> data\forward-tracking\strict_forward_30_candidate_review_log.txt 2>&1
echo. >> data\forward-tracking\strict_forward_30_candidate_review_log.txt
C:\Python312\python.exe scripts\build_regular_options_strict_forward_30_exit_evidence_plan.py --json >> data\forward-tracking\strict_forward_30_exit_evidence_plan_log.txt 2>&1
echo. >> data\forward-tracking\strict_forward_30_exit_evidence_plan_log.txt
C:\Python312\python.exe scripts\build_regular_options_strict_forward_30_exit_completion_stager.py --json >> data\forward-tracking\strict_forward_30_exit_completion_stager_log.txt 2>&1
echo. >> data\forward-tracking\strict_forward_30_exit_completion_stager_log.txt
C:\Python312\python.exe scripts\build_regular_options_strict_forward_30_lifecycle_audit.py --json >> data\forward-tracking\strict_forward_30_lifecycle_audit_log.txt 2>&1
echo. >> data\forward-tracking\strict_forward_30_lifecycle_audit_log.txt
C:\Python312\python.exe scripts\build_regular_options_strict_forward_30_completion_monitor.py --json >> data\forward-tracking\strict_forward_30_completion_monitor_log.txt 2>&1
echo. >> data\forward-tracking\strict_forward_30_completion_monitor_log.txt
