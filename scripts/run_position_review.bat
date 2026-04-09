@echo off
cd /d C:\Users\kalec\options-chatbot
curl -s -X POST http://127.0.0.1:8100/api/positions/review -H "Content-Type: application/json" -d "{}" >> data\forward-tracking\position_review_log.txt 2>&1
echo. >> data\forward-tracking\position_review_log.txt
