@echo off
cd /d C:\Users\kalec\options-chatbot
C:\Python312\python.exe scripts\run_regime_observation_lanes.py >> data\forward-tracking\observation_lanes_log.txt 2>&1
echo. >> data\forward-tracking\observation_lanes_log.txt
