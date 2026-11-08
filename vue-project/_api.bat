@echo off
cd /d "%~dp0"

rem 8000 端口如果被上次没关干净的进程占着，先清掉再启动
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Write-Host ('  清掉占用 8000 的进程 PID ' + $_.OwningProcess); Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"

".venv\Scripts\python.exe" -m uvicorn server.app:app --port 8000 --reload
if errorlevel 1 pause
