@echo off
cd /d C:\Users\kalec\options-chatbot
set OPTIONS_SCAN_PLAYBOOK=bullish_pullback_observation
set OPTIONS_SCAN_AUTO_TRACK=0
set OPTIONS_SCAN_ENFORCE_PORTFOLIO_CAPS=1
set OPTIONS_ENFORCE_LANE_PROFITABILITY_GATE=1
C:\Python312\python.exe scripts\run_forward_cohort_scan_sweep.py --force >> data\forward-tracking\scan_log.txt 2>&1
C:\Python312\python.exe scripts\run_regular_options_strict_forward_30_auto_window_collector.py --skip-scan-sweep --json >> data\forward-tracking\strict_forward_30_auto_window_collector_log.txt 2>&1
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
C:\Python312\python.exe scripts\ensure_daily_all_lanes_audit_ran.py --force >> data\forward-tracking\daily_all_lanes_audit_log.txt 2>&1
echo. >> data\forward-tracking\daily_all_lanes_audit_log.txt
C:\Python312\python.exe scripts\validate_pending_scan_candidates.py >> data\forward-tracking\pending_candidate_validation_log.txt 2>&1
echo. >> data\forward-tracking\pending_candidate_validation_log.txt
