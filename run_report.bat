@echo off
rem Daily Lead with Test Ride report - called by Windows Task Scheduler
cd /d "%~dp0"
echo ===== %date% %time% ===== >> logs\scheduled_run.log
"C:\Python314\python.exe" -m lead_report >> logs\scheduled_run.log 2>&1
