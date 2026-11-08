@echo off
cd /d "%~dp0voice-service"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0voice-service\start_furina_api.ps1"
if errorlevel 1 pause
