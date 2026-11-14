@echo off
cd /d "%~dp0"

rem 8124 端口：后端与大模型对话的监控台（server/llm_monitor.py）
rem 先踢掉上一次没关掉的进程，免得端口被占住起不来
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8124 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Write-Host ('  监控台端口 8124 被进程 PID ' + $_.OwningProcess + ' 占用'); Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"

".venv\Scripts\python.exe" server\llm_monitor.py --port 8124
if errorlevel 1 pause