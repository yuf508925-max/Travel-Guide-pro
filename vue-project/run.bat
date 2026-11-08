@echo off
title Travel Guide launcher
echo Starting: voice service / backend / frontend
echo   voice  http://127.0.0.1:9880
echo   api    http://127.0.0.1:8000
echo   web    http://127.0.0.1:5173
echo.
start "Furina Voice" "%~dp0_voice.bat"
timeout /t 2 /nobreak >nul
start "Travel Guide API" "%~dp0_api.bat"
timeout /t 2 /nobreak >nul
start "Travel Guide Web" "%~dp0_web.bat"
echo Three windows opened. Wait for "Local: http://localhost:5173".
timeout /t 5 /nobreak >nul
